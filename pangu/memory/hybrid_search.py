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
VECTOR_TOP_K = 50  # 向量通道进入 RRF 融合前的候选上限
VECTOR_MIN_COUNT = 1  # VectorIndex 至少要有这么多条才可信（空索引一律不信）
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


def _cache_get(query: str, limit: int, scope: str = "") -> list[dict] | None:
    """从缓存获取搜索结果"""
    try:
        from pangu.memory.search_cache import get_search_cache

        cache = get_search_cache()
        return cache.get(query, limit=limit, scope=scope)
    except Exception as e:
        logger.debug(CACHE_RETRIEVAL_FAILED_MSG.format(e))
        return None


def _cache_set(query: str, results: list[dict], limit: int, scope: str = "") -> None:
    """将搜索结果存入缓存"""
    try:
        from pangu.memory.search_cache import get_search_cache

        cache = get_search_cache()
        cache.set(query, results, limit=limit, scope=scope)
    except Exception as e:
        logger.debug(CACHE_STORAGE_FAILED_MSG.format(e))


def _cache_scope(drawers: list[Drawer] | None) -> str:
    """缓存作用域指纹：当前租户 + drawers 的 id/更新时间集合。

    租户保证「A 身份的结果不给 B 身份」；id+updated_at 保证「记忆增删改后不命中旧结果」。
    两者共同替代此前只按 (query,limit) 的裸键。
    """
    try:
        from pangu.memory.layers import current_tenant

        tenant = current_tenant() or ""
    except Exception:
        tenant = ""
    try:
        from pangu.core.hashing import hex_digest

        # Drawer 没有 updated_at（那是 WikiPage 的字段），用 created_at + 重要度
        # 作为变更指纹；配合 id 集合即可覆盖"增/删/改"三类变化。
        ids = "|".join(
            f"{d.id}:{getattr(d, 'created_at', '') or ''}:{round(float(getattr(d, 'importance', 0) or 0), 3)}"
            for d in (drawers or [])
        )
        return f"{tenant}:{hex_digest(ids)[:16]}:{len(drawers or [])}"
    except Exception:
        return f"{tenant}:{len(drawers or [])}"


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
    """向量召回，返回 {memory_id: rank}。

    数据源（2026-09-19）：优先用 **VectorIndex**（系统真正的向量存储，
    `vector_rebuild` 任务的产物）。此前只用 `metadata.embedding`，而库里非加密
    记忆根本没有这个字段（实测 165 条中 0 条命中），向量通道恒为空 ——
    hybrid_search 实际退化成 FTS+KG 两路，许多正常查询返回 0 条。
    VectorIndex 不可用或规模不足时回退到 metadata.embedding（兼容旧数据）。
    """
    vector_ranks: dict[str, int] = {}
    try:
        query_vec = _get_query_embedding(query)
        if query_vec is None:
            return vector_ranks

        scored: list[tuple[str, float]] = []

        # ① 优先：共享向量索引（先确认它真的可用再信它）
        try:
            from .vector_index import get_vector_index

            idx = get_vector_index()
            if idx is not None and idx.is_built and idx.size >= VECTOR_MIN_COUNT:
                for mid, sim in idx.search(query_vec, top_k=VECTOR_TOP_K):
                    if mid in all_ids and sim > VECTOR_SIM_THRESHOLD:
                        scored.append((mid, float(sim)))
        except Exception as e:
            logger.debug(f"VectorIndex 召回失败，回退 metadata.embedding: {e}")

        # ② 回退：逐条 metadata.embedding（跳过加密内容 —— 密文无语义）
        if not scored:
            for d in drawers:
                content = d.content or ""
                if content.startswith("gAAAAA"):
                    continue
                stored_vec = (d.metadata or {}).get("embedding")
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
        # 密文在返回前解密（2026-09-19）：search / recall 两条路径此前各修过一次
        # "返回 gAAAAAB… 乱码"，hybrid 这条漏了 —— 实测 hybrid_search 的 Top-3 直接
        # 返回密文。这里解密后再进 rerank（rerank 也依赖可读文本）。
        # decrypt 对非密文原样返回；真解密失败会给明确占位符（见 encryption.py 三态）。
        content = d.content
        if isinstance(content, str) and content.startswith("gAAAAA"):
            try:
                from .encryption import decrypt

                content = decrypt(content)
            except Exception:
                pass
        # P0-1 supersede 标注：当 drawer 的 metadata.memory_status == "superseded" 时
        # 标记 superseded=True 并填 superseded_by（list）+ warning="⚠ 已被更新"。
        # 客户端可据此高亮/折叠/排序。
        superseded = False
        superseded_by: list[str] = []
        if d.metadata:
            status = d.metadata.get("memory_status")
            if status == "superseded":
                superseded = True
                by = d.metadata.get("superseded_by", [])
                if isinstance(by, list):
                    superseded_by = by
        results.append(
            {
                "id": mid,
                "content": content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": d.created_at,
                "rrf_score": round(rrf_scores[mid], 6),
                "fts_rank": fts_ranks.get(mid),
                "vector_rank": vector_ranks.get(mid),
                "kg_rank": kg_ranks.get(mid),
                "superseded": superseded,
                "superseded_by": superseded_by,
                "warning": "⚠ 已被更新" if superseded else None,
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
    fts_weight: float = 1.5,
    vector_weight: float = 0.8,
    kg_weight: float = 0.5,
) -> list[dict]:
    """混合检索 — FTS + 向量 + KG 三路召回，RRF 融合排序

    P0-2：fts_weight 从 1.0 提升到 1.5，vector_weight 从 1.0 降到 0.8。
    理由：FTS 天然偏长文本（需要足够 token 才能命中），提升 FTS 权重
    间接惩罚短文本（短文本在 FTS 通道排名低）。实测 7 字噪声 vs 32 字
    真实内容，FTS 通道能正确区分。

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
    # 检查缓存（键含身份作用域：租户 + drawers 指纹）
    scope = _cache_scope(drawers)
    cached = _cache_get(query, limit, scope)
    if cached is not None:
        return cached

    config = (config or PanguConfig.load()).authoritative_memory_config()
    all_ids = {d.id: d for d in drawers}

    # 三路召回
    fts_ranks = _fts_recall(query, drawers, all_ids)
    vector_ranks = _vector_recall(query, drawers, all_ids)
    kg_ranks = _kg_recall(query, all_ids, config)

    # RRF 融合
    rrf_scores = _rrf_fusion(
        fts_ranks,
        vector_ranks,
        kg_ranks,
        fts_weight,
        vector_weight,
        kg_weight,
    )

    # 排序
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: -rrf_scores[x])

    # 构建结果
    results = _build_results(
        sorted_ids,
        all_ids,
        rrf_scores,
        fts_ranks,
        vector_ranks,
        kg_ranks,
        limit,
    )

    # 语义重排序
    results = _rerank_results(query, results, drawers, limit)

    # 生成搜索解释
    _explain_results(query, results)

    # 存入缓存（带作用域）
    _cache_set(query, results, limit, scope)

    return results
