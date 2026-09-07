"""盘古混合检索引擎 — 融合 FTS + 向量 + KG 的 RRF 排序

核心算法：Reciprocal Rank Fusion (RRF)
- 对每路召回结果计算 RRF 分数
- RRF(d) = Σ 1 / (k + rank_i(d))，k=60
- 融合多路排序，返回统一结果
"""

import logging

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.hybrid_search")

RRF_K = 60  # RRF 常数
VECTOR_SIM_THRESHOLD = 0.2  # 向量相似度阈值
KG_KEYWORD_MIN_LEN = 2  # KG 关键词最小长度
KG_MAX_ENTITIES = 5  # KG 最大实体数
ONNX_EMBED_FAILED_MSG = "ONNX embedding failed: {}"
CACHE_RETRIEVAL_FAILED_MSG = "Cache retrieval failed: {}"
CACHE_STORAGE_FAILED_MSG = "Cache storage failed: {}"
FTS_SEARCH_FAILED_MSG = "FTS search failed: {}"
VECTOR_SEARCH_FAILED_MSG = "Vector search failed: {}"
KG_SEARCH_FAILED_MSG = "KG search failed: {}"
RERANKING_SKIPPED_MSG = "Reranking skipped: {}"
SEARCH_EXPLANATION_SKIPPED_MSG = "Search explanation skipped: {}"


def _cache_get(query: str, limit: int) -> list[dict] | None:
    """从缓存获取搜索结果"""
    try:
        from pangu.memory.search_cache import get_search_cache
        cache = get_search_cache()
        return cache.get(query, limit=limit)
    except Exception as e:
        logger.debug(CACHE_RETRIEVAL_FAILED_MSG.format(e))
        return None


def _cache_set(query: str, results: list[dict], limit: int) -> None:
    """将搜索结果存入缓存"""
    try:
        from pangu.memory.search_cache import get_search_cache
        cache = get_search_cache()
        cache.set(query, results, limit=limit)
    except Exception as e:
        logger.debug(CACHE_STORAGE_FAILED_MSG.format(e))


def _fts_recall(
    query: str,
    drawers: list[Drawer],
    all_ids: dict[str, Drawer],
) -> dict[str, int]:
    """FTS 召回，返回 {memory_id: rank}"""
    fts_ranks: dict[str, int] = {}
    try:
        from pangu.memory.fts_search import _get_fts_engine
        fts = _get_fts_engine()
        if not fts._indexed or fts._indexed_count != len(drawers):
            fts.build_index(drawers)
        fts_results = fts._fts_search(query, drawers)
        for rank, (mid, _score) in enumerate(fts_results.items()):
            if mid in all_ids:
                fts_ranks[mid] = rank + 1
    except Exception as e:
        logger.debug(FTS_SEARCH_FAILED_MSG.format(e))
    return fts_ranks


def _vector_recall(
    query: str,
    drawers: list[Drawer],
    all_ids: dict[str, Drawer],
) -> dict[str, int]:
    """向量召回，返回 {memory_id: rank}"""
    vector_ranks: dict[str, int] = {}
    try:
        query_vec = _get_query_embedding(query)
        if query_vec is None:
            return vector_ranks
        
        scored = []
        for d in drawers:
            stored_vec = d.metadata.get("embedding")
            if not stored_vec:
                continue
            try:
                n = min(len(query_vec), len(stored_vec))
                dot = sum(a * b for a, b in zip(query_vec[:n], stored_vec[:n], strict=False))
                norm_a = sum(a * a for a in query_vec[:n]) ** 0.5
                norm_b = sum(b * b for b in stored_vec[:n]) ** 0.5
                sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
                if sim > VECTOR_SIM_THRESHOLD:
                    scored.append((d.id, sim))
            except Exception:
                continue
        scored.sort(key=lambda x: -x[1])
        for rank, (mid, _) in enumerate(scored):
            vector_ranks[mid] = rank + 1
    except Exception as e:
        logger.debug(VECTOR_SEARCH_FAILED_MSG.format(e))
    return vector_ranks


def _get_query_embedding(query: str) -> list[float] | None:
    """获取查询的嵌入向量"""
    # ONNX 优先
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        if onnx.is_available:
            query_vec = onnx.embed(query)
            if query_vec:
                return query_vec
    except Exception as e:
        logger.debug(ONNX_EMBED_FAILED_MSG.format(e))
    
    # 降级到 embedding service
    try:
        from pangu.memory.embedding import get_embedding_service
        embed_svc = get_embedding_service()
        return embed_svc.embed(query)
    except Exception as e:
        logger.debug(f"Embedding service failed: {e}")
        return None


def _kg_recall(
    query: str,
    all_ids: dict[str, Drawer],
    config: PanguConfig,
) -> dict[str, int]:
    """KG 召回，返回 {memory_id: rank}"""
    kg_ranks: dict[str, int] = {}
    try:
        from pangu.memory.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(config)
        keywords = [w for w in query.split() if len(w) >= KG_KEYWORD_MIN_LEN]
        kg_entities = set()
        for kw in keywords:
            entities = kg.list_entities()
            for e in entities:
                if kw.lower() in e.get("name", "").lower():
                    kg_entities.add(e["id"])
        for eid in list(kg_entities)[:KG_MAX_ENTITIES]:
            relations = kg.query_relations(subject_id=eid)
            for rel in relations:
                obj_id = rel.get("object_id", "")
                if obj_id in all_ids:
                    kg_ranks[obj_id] = len(kg_ranks) + 1
    except Exception as e:
        logger.debug(KG_SEARCH_FAILED_MSG.format(e))
    return kg_ranks


def _rrf_fusion(
    fts_ranks: dict[str, int],
    vector_ranks: dict[str, int],
    kg_ranks: dict[str, int],
    fts_weight: float,
    vector_weight: float,
    kg_weight: float,
) -> dict[str, float]:
    """RRF 融合排序，返回 {memory_id: score}"""
    rrf_scores: dict[str, float] = {}
    all_ranks = [
        (fts_ranks, fts_weight),
        (vector_ranks, vector_weight),
        (kg_ranks, kg_weight),
    ]
    for ranks, weight in all_ranks:
        for mid, rank in ranks.items():
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + weight / (RRF_K + rank)
    
    # 归一化 RRF 分数到 0-1
    if rrf_scores:
        max_score = max(rrf_scores.values())
        if max_score > 0:
            rrf_scores = {mid: score / max_score for mid, score in rrf_scores.items()}
    return rrf_scores


def _build_results(
    sorted_ids: list[str],
    all_ids: dict[str, Drawer],
    rrf_scores: dict[str, float],
    fts_ranks: dict[str, int],
    vector_ranks: dict[str, int],
    kg_ranks: dict[str, int],
    limit: int,
) -> list[dict]:
    """构建结果列表"""
    results = []
    for mid in sorted_ids[:limit]:
        d = all_ids[mid]
        results.append(
            {
                "id": mid,
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": d.created_at,
                "rrf_score": round(rrf_scores[mid], 6),
                "fts_rank": fts_ranks.get(mid),
                "vector_rank": vector_ranks.get(mid),
                "kg_rank": kg_ranks.get(mid),
            }
        )
    return results


def _rerank_results(
    query: str,
    results: list[dict],
    drawers: list[Drawer],
    limit: int,
) -> list[dict]:
    """语义重排序"""
    try:
        from pangu.memory.reranker import rerank_search_results
        return rerank_search_results(query, results, drawers=drawers, limit=limit)
    except Exception as e:
        logger.debug(RERANKING_SKIPPED_MSG.format(e))
        return results


def _explain_results(
    query: str,
    results: list[dict],
) -> None:
    """生成搜索解释"""
    try:
        from pangu.memory.search_explainer import get_search_explainer
        explainer = get_search_explainer()
        for r in results:
            exp = explainer.explain(query, r, all_results=results)
            r["explanation"] = exp.summary
            r["match_reasons"] = exp.match_reasons
            r["match_type"] = exp.match_type
    except Exception as e:
        logger.debug(SEARCH_EXPLANATION_SKIPPED_MSG.format(e))


def hybrid_search(
    query: str,
    drawers: list[Drawer],
    config: PanguConfig = None,
    limit: int = 10,
    fts_weight: float = 1.0,
    vector_weight: float = 1.0,
    kg_weight: float = 0.5,
) -> list[dict]:
    """混合检索 — FTS + 向量 + KG 三路召回，RRF 融合排序

    Args:
        query: 搜索查询
        drawers: 记忆列表
        config: 配置
        limit: 返回数量
        fts_weight: FTS 权重
        vector_weight: 向量权重
        kg_weight: KG 权重

    Returns:
        排序后的记忆列表
    """
    # 检查缓存
    cached = _cache_get(query, limit)
    if cached is not None:
        return cached
    
    config = config or PanguConfig.load()
    all_ids = {d.id: d for d in drawers}

    # 三路召回
    fts_ranks = _fts_recall(query, drawers, all_ids)
    vector_ranks = _vector_recall(query, drawers, all_ids)
    kg_ranks = _kg_recall(query, all_ids, config)

    # RRF 融合
    rrf_scores = _rrf_fusion(
        fts_ranks, vector_ranks, kg_ranks,
        fts_weight, vector_weight, kg_weight,
    )
    
    # 排序
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: -rrf_scores[x])
    
    # 构建结果
    results = _build_results(
        sorted_ids, all_ids, rrf_scores,
        fts_ranks, vector_ranks, kg_ranks,
        limit,
    )
    
    # 语义重排序
    results = _rerank_results(query, results, drawers, limit)
    
    # 生成搜索解释
    _explain_results(query, results)
    
    # 存入缓存
    _cache_set(query, results, limit)
    
    return results
