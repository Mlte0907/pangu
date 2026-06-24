"""盘古混合检索引擎 — 融合 FTS + 向量 + KG 的 RRF 排序

核心算法：Reciprocal Rank Fusion (RRF)
- 对每路召回结果计算 RRF 分数
- RRF(d) = Σ 1 / (k + rank_i(d))，k=60
- 融合多路排序，返回统一结果
"""
import json
import logging
import math
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.hybrid_search")

RRF_K = 60  # RRF 常数


def hybrid_search(
    query: str,
    drawers: list[Drawer],
    config: PanguConfig = None,
    limit: int = 10,
    fts_weight: float = 1.0,
    vector_weight: float = 1.0,
    kg_weight: float = 0.5,
) -> list[dict]:
    """混合检索 — 带缓存"""
    # 检查缓存
    try:
        from pangu.memory.search_cache import get_search_cache
        cache = get_search_cache()
        cached = cache.get(query, limit=limit)
        if cached is not None:
            return cached
    except Exception:
        pass
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
    config = config or PanguConfig.load()
    all_ids = {d.id: d for d in drawers}

    # 收集各路排名 {memory_id: rank}
    fts_ranks: dict[str, int] = {}
    vector_ranks: dict[str, int] = {}
    kg_ranks: dict[str, int] = {}

    # ── FTS 召回（使用缓存的 FTS 引擎） ──
    try:
        from pangu.memory.fts_search import FTS5SearchEngine, _get_fts_engine
        fts = _get_fts_engine()
        if not fts._indexed or fts._indexed_count != len(drawers):
            fts.build_index(drawers)
        fts_results = fts._fts_search(query, drawers)
        for rank, (mid, score) in enumerate(fts_results.items()):
            if mid in all_ids:
                fts_ranks[mid] = rank + 1
    except Exception as e:
        logger.debug(f"FTS search failed: {e}")

    # ── 向量召回（ONNX 优先） ──
    try:
        query_vec = None
        try:
            from pangu.memory.onnx_embedder import get_onnx_embedder
            onnx = get_onnx_embedder()
            if onnx.is_available:
                query_vec = onnx.embed(query)
        except Exception:
            pass
        if query_vec is None:
            from pangu.memory.embedding import get_embedding_service
            embed_svc = get_embedding_service()
            query_vec = embed_svc.embed(query)
        if query_vec:
            scored = []
            for d in drawers:
                stored_vec = d.metadata.get("embedding")
                if not stored_vec:
                    continue
                try:
                    n = min(len(query_vec), len(stored_vec))
                    dot = sum(a * b for a, b in zip(query_vec[:n], stored_vec[:n]))
                    norm_a = sum(a * a for a in query_vec[:n]) ** 0.5
                    norm_b = sum(b * b for b in stored_vec[:n]) ** 0.5
                    sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
                    if sim > 0.2:
                        scored.append((d.id, sim))
                except Exception:
                    continue
            scored.sort(key=lambda x: -x[1])
            for rank, (mid, _) in enumerate(scored):
                vector_ranks[mid] = rank + 1
    except Exception as e:
        logger.debug(f"Vector search failed: {e}")

    # ── KG 召回 ──
    try:
        from pangu.memory.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(config)
        # 用 query 中的关键词搜索 KG 实体
        keywords = [w for w in query.split() if len(w) >= 2]
        kg_entities = set()
        for kw in keywords:
            entities = kg.list_entities()
            for e in entities:
                if kw.lower() in e.get("name", "").lower():
                    kg_entities.add(e["id"])
        # 从实体找关联的记忆
        for eid in list(kg_entities)[:5]:
            relations = kg.query_relations(subject_id=eid)
            for rel in relations:
                obj_id = rel.get("object_id", "")
                if obj_id in all_ids:
                    kg_ranks[obj_id] = len(kg_ranks) + 1
    except Exception as e:
        logger.debug(f"KG search failed: {e}")

    # ── RRF 融合 ──
    rrf_scores: dict[str, float] = {}
    all_ranks = [
        (fts_ranks, fts_weight),
        (vector_ranks, vector_weight),
        (kg_ranks, kg_weight),
    ]

    for ranks, weight in all_ranks:
        for mid, rank in ranks.items():
            rrf_scores[mid] = rrf_scores.get(mid, 0.0) + weight / (RRF_K + rank)

    # 排序
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: -rrf_scores[x])

    results = []
    for mid in sorted_ids[:limit]:
        d = all_ids[mid]
        results.append({
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
        })

    # 语义重排序
    try:
        from pangu.memory.reranker import rerank_search_results
        results = rerank_search_results(query, results, drawers=drawers, limit=limit)
    except Exception as e:
        logger.debug(f"Reranking skipped: {e}")

    # 生成搜索解释
    try:
        from pangu.memory.search_explainer import get_search_explainer
        explainer = get_search_explainer()
        for r in results:
            exp = explainer.explain(query, r, all_results=results)
            r["explanation"] = exp.summary
            r["match_reasons"] = exp.match_reasons
            r["match_type"] = exp.match_type
    except Exception as e:
        logger.debug(f"Search explanation skipped: {e}")

    # 存入缓存
    try:
        from pangu.memory.search_cache import get_search_cache
        cache = get_search_cache()
        cache.set(query, results, limit=limit)
    except Exception:
        pass

    return results
