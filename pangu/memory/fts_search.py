"""盘古 FTS5 全文搜索 + RRF 混合搜索引擎

从伏羲移植：FTS5 全文搜索 + 向量语义搜索 + RRF 倒数排名融合
支持自适应权重、结果缓存、多级过滤、中文分词
"""

import json
import logging
import re
import threading
import time
from datetime import datetime

from pangu.core.hashing import hex_digest

from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.fts_search")

# 中文分词器（jieba）
_jieba = None


def _get_jieba():
    """获取 jieba 分词器（懒加载）"""
    global _jieba
    if _jieba is None:
        try:
            import jieba
            jieba.setLogLevel(logging.WARNING)
            _jieba = jieba
        except ImportError:
            logger.debug("jieba not available, using regex fallback")
    return _jieba

_FTS_SPECIAL_RE = re.compile(r'\b(AND|OR|NOT|NEAR)\b|[()"*^]')

_SEARCH_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 60  # 1分钟缓存


def _sanitize_fts_query(query: str) -> str:
    """清理 FTS 查询中的特殊字符"""
    return _FTS_SPECIAL_RE.sub(" ", query).strip()


def _make_cache_key(*args) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hex_digest(raw)


def cosine_similarity(a: list, b: list) -> float:
    """计算余弦相似度，支持不同维度向量"""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    a_trunc = a[:n]
    b_trunc = b[:n]
    dot = sum(x * y for x, y in zip(a_trunc, b_trunc, strict=False))
    norm_a = sum(x * x for x in a_trunc) ** 0.5
    norm_b = sum(x * x for x in b_trunc) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _rrf_fuse(fts_scores: dict, vec_scores: dict, k: int = 60) -> dict:
    """倒数排名融合（Reciprocal Rank Fusion）

    公式: RRF(d) = Σ 1/(k + rank(d))
    将 FTS 和向量搜索结果按排名加权融合，无需归一化分数
    """
    merged: dict[str, float] = {}

    for rank, (drawer_id, _) in enumerate(sorted(fts_scores.items(), key=lambda x: -x[1])):
        merged[drawer_id] = merged.get(drawer_id, 0) + 1.0 / (k + rank)

    for rank, (drawer_id, _) in enumerate(sorted(vec_scores.items(), key=lambda x: -x[1])):
        merged[drawer_id] = merged.get(drawer_id, 0) + 1.0 / (k + rank)

    return dict(sorted(merged.items(), key=lambda x: x[1], reverse=True))


class FTS5SearchEngine:
    """FTS5 全文搜索 + 向量语义搜索 + RRF 融合引擎

    核心特性：
    1. 关键词全文搜索（内存 FTS 索引）
    2. 向量语义搜索（sentence-transformers）
    3. RRF 倒数排名融合（无需分数归一化）
    4. 结果缓存（可配置 TTL）
    5. 自适应权重调整
    """

    def __init__(self, config=None, vector_weight: float = 0.6, similarity_threshold: float = 0.25):
        self.config = config
        self.vector_weight = vector_weight
        self.similarity_threshold = similarity_threshold
        self._embedder = None
        self._fts_index: dict[str, set[str]] = {}  # token -> drawer_ids
        self._fts_content_map: dict[str, str] = {}  # drawer_id -> content
        self._indexed: bool = False
        self._indexed_count: int = 0  # 索引的文档数量

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService
                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    def build_index(self, drawers: list[Drawer]) -> int:
        """构建 FTS 内存索引（支持中文分词）"""
        # 如果索引已构建且文档数量相同，跳过重建
        if self._indexed and self._indexed_count == len(drawers):
            return len(self._fts_index)

        self._fts_index.clear()
        self._fts_content_map = {}
        self._indexed_count = len(drawers)
        jieba = _get_jieba()

        for d in drawers:
            content_lower = d.content.lower()
            self._fts_content_map[d.id] = content_lower

            # 中文分词 + 英文单词
            tokens = set()
            if jieba:
                # jieba 分词
                words = jieba.cut(content_lower)
                for w in words:
                    w = w.strip()
                    if len(w) >= 1:
                        tokens.add(w)
            else:
                # 降级：正则分词
                tokens = set(re.findall(r'[\u4e00-\u9fff]{1,}|[a-zA-Z]{2,}', content_lower))

            # 标签也加入索引
            for tag in d.tags:
                tokens.add(tag.lower())

            for token in tokens:
                if token not in self._fts_index:
                    self._fts_index[token] = set()
                self._fts_index[token].add(d.id)

        self._indexed = True
        total_tokens = len(self._fts_index)
        logger.info(f"FTS index built: {total_tokens} tokens, {len(drawers)} documents, jieba={'yes' if jieba else 'no'}")
        return total_tokens

    def _fts_search(self, query: str, drawers: list[Drawer], limit: int = 50) -> dict[str, float]:
        """FTS 全文搜索，返回 {drawer_id: score}"""
        safe_query = _sanitize_fts_query(query).lower()

        # 中文分词
        jieba = _get_jieba()
        if jieba:
            keywords = [w.strip() for w in jieba.cut(safe_query) if w.strip()]
        else:
            keywords = safe_query.split()

        if not keywords:
            return {}

        drawer_map = {d.id: d for d in drawers}  # noqa: F841
        scores: dict[str, float] = {}

        for kw in keywords:
            if kw in self._fts_index:
                for did in self._fts_index[kw]:
                    scores[did] = scores.get(did, 0) + 1.0

        if not scores:
            for kw in keywords:
                if len(kw) >= 2:
                    self._fallback_keyword_search(kw, scores)

        # 按重要性排序，取 top-k
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        return dict(sorted_items)

    def _fallback_keyword_search(self, kw: str, scores: dict[str, float]):
        for did, content in self._fts_content_map.items():
            if kw in content:
                scores[did] = scores.get(did, 0) + 0.5

    def _try_batch_embed(self, query_vec: list, items: list[dict]) -> dict[str, float]:
        scores: dict[str, float] = {}
        ids = [item["id"] for item in items]
        texts = [item["content"] for item in items]
        embeddings = self.embedder.embed_batch(texts)
        if embeddings:
            for i, emb in enumerate(embeddings):
                if emb:
                    sim = cosine_similarity(query_vec, emb)
                    if sim >= self.similarity_threshold:
                        scores[ids[i]] = sim
        return scores

    def _fallback_embed(self, query_vec: list, items: list[dict]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for item in items:
            try:
                emb = self.embedder.embed(item["content"])
                if emb:
                    sim = cosine_similarity(query_vec, emb)
                    if sim >= self.similarity_threshold:
                        scores[item["id"]] = sim
            except Exception:
                continue
        return scores

    def _vector_search(self, query: str, drawers: list[Drawer], limit: int = 50) -> dict[str, float]:
        """向量语义搜索，返回 {drawer_id: similarity}"""
        if not self.embedder:
            return {}

        try:
            query_vec = self.embedder.embed(query)
            if not query_vec:
                return {}
        except Exception:
            return {}

        items = [{
            "id": d.id,
            "content": d.content,
        } for d in drawers]

        try:
            scores = self._try_batch_embed(query_vec, items)
        except Exception:
            scores = self._fallback_embed(query_vec, items)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        return dict(sorted_items)

    def search(
        self,
        query: str,
        drawers: list[Drawer],
        wing: str = None,
        room: str = None,
        agent_id: str = None,
        limit: int = 10,
        offset: int = 0,
        min_importance: float = 0.0,
        use_cache: bool = True,
        vector_weight: float = None,
    ) -> dict:
        """混合搜索主入口

        Args:
            query: 搜索查询
            drawers: 记忆列表
            wing: 限定 Wing
            room: 限定 Room
            agent_id: 限定 agent_id（多租户隔离）
            limit: 返回数量
            offset: 偏移量
            min_importance: 最低重要性
            use_cache: 是否使用缓存
            vector_weight: 向量搜索权重（0-1）

        Returns:
            {"results": [...], "total": int, "method": str, "fts_used": bool, "vector_used": bool}
        """
        if vector_weight is None:
            vector_weight = self.vector_weight

        if not query or not query.strip():
            return {"results": [], "total": 0, "query": query, "method": "empty"}

        # 结果缓存
        cache_key = None
        if use_cache:
            cache_key = _make_cache_key(query, wing, room, limit, offset, min_importance, vector_weight)
            with _CACHE_LOCK:
                if cache_key in _SEARCH_CACHE:
                    entry = _SEARCH_CACHE[cache_key]
                    if time.time() - entry["ts"] < _CACHE_TTL:
                        return entry["data"]

        # 过滤
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if room and d.room != room:
                continue
            if agent_id and d.author != agent_id:
                continue
            if min_importance > 0 and d.importance < min_importance:
                continue
            filtered.append(d)

        if not filtered:
            return {"results": [], "total": 0, "query": query, "method": "empty"}

        # 确保索引已构建
        if not self._indexed:
            self.build_index(filtered)

        # FTS 搜索
        fts_results = self._fts_search(query, filtered, limit=limit * 3)

        # 向量搜索
        vec_results = self._vector_search(query, filtered, limit=limit * 3)

        # RRF 融合
        fused = _rrf_fuse(fts_results, vec_results)

        if not fts_results and not vec_results:
            return {"results": [], "total": 0, "query": query, "method": "empty"}

        fts_used = len(fts_results) > 0
        vec_used = len(vec_results) > 0
        if fts_used and vec_used:
            method = "hybrid"
        elif fts_used:
            method = "fts"
        elif vec_used:
            method = "vector_only"
        else:
            method = "empty"

        # 提取结果
        drawer_map = {d.id: d for d in filtered}
        results = []
        for did, score in list(fused.items())[offset:offset + limit]:
            d = drawer_map.get(did)
            if not d:
                continue
            results.append({
                "id": d.id,
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "hall": d.hall,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": d.created_at,
                "search_score": round(score, 4),
                "source": method,
            })

        response = {
            "results": results,
            "total": len(results),
            "query": query,
            "method": method,
            "fts_used": fts_used,
            "vector_used": vec_used,
            "weights": {"vector": vector_weight, "fts": round(1 - vector_weight, 2)},
        }

        if cache_key:
            with _CACHE_LOCK:
                if len(_SEARCH_CACHE) >= 100:
                    oldest = next(iter(_SEARCH_CACHE))
                    del _SEARCH_CACHE[oldest]
                _SEARCH_CACHE[cache_key] = {"ts": time.time(), "data": response}

        return response

    def clear_cache(self):
        """清除搜索缓存"""
        global _SEARCH_CACHE
        with _CACHE_LOCK:
            _SEARCH_CACHE.clear()
        logger.debug("Search cache cleared")

    def get_stats(self) -> dict:
        """获取搜索引擎统计"""
        return {
            "fts_index_size": len(self._fts_index),
            "indexed": self._indexed,
            "vector_weight": self.vector_weight,
            "similarity_threshold": self.similarity_threshold,
            "cache_size": len(_SEARCH_CACHE),
            "cache_ttl": _CACHE_TTL,
        }


# ── 伏羲移植：增强函数 ──

def _compute_method(fts_used: bool, vec_used: bool) -> str:
    """标记搜索降级状态（从伏羲移植）"""
    if fts_used and vec_used:
        return "hybrid"
    if fts_used:
        return "fts_only"
    if vec_used:
        return "vector_only"
    return "empty"


def get_search_stats() -> dict:
    """获取搜索引擎统计（含嵌入服务健康状态，从伏羲移植）"""
    try:
        from pangu.memory.embedding import get_embedding_service
        es = get_embedding_service()
        embed_stats = es.stats
    except Exception:
        embed_stats = {}

    return {
        **embed_stats,
        "cache_size": len(_SEARCH_CACHE),
        "cache_ttl": _CACHE_TTL,
    }


def holographic_search(
    query: str,
    drawers: list,
    weights: dict | None = None,
    top_k: int = 10,
) -> list[dict]:
    """全息搜索 — 跨维度加权融合检索（从伏羲移植）

    将查询编码为多维度投影，跨维度加权融合检索。
    支持 "昨天下午让我焦虑的那件事" 这样的跨维度自然语言查询。
    """
    try:
        from pangu.memory.embedding import get_embedding_service
        from pangu.memory.hologram import DEFAULT_FUSION_WEIGHTS, FUSION_ORDER, HolographicEncoder
    except ImportError:
        return []

    if weights is None:
        weights = DEFAULT_FUSION_WEIGHTS

    encoder = HolographicEncoder()

    # 编码查询为多维度投影
    now_str = datetime.now().isoformat()
    query_projections = {}
    embed_svc = get_embedding_service()

    for dim in FUSION_ORDER:
        if weights.get(dim, 0) <= 0:
            continue
        if dim == "semantic":
            vec = embed_svc.embed(query)
            if vec:
                query_projections["semantic"] = vec
        elif dim == "temporal":
            query_projections["temporal"] = encoder.temporal.encode(created_at=now_str).tolist()
        elif dim == "emotional":
            query_projections["emotional"] = encoder.emotional.encode(valence=0.0, arousal=0.0, dominance=0.5).tolist()
        elif dim == "causal":
            query_projections["causal"] = encoder.causal.encode(causal_summary=query).tolist()
        elif dim == "source":
            query_projections["source"] = encoder.source.encode(source_type="query", agent_id="").tolist()

    if not query_projections:
        return []

    # 对所有记忆进行全息匹配
    scored = []
    for d in drawers:
        hologram_data = d.metadata.get("hologram")
        if not hologram_data:
            continue
        try:
            total_score = 0.0
            total_weight = 0.0
            for dim, query_vec in query_projections.items():
                dim_vec = hologram_data.get(dim)
                if dim_vec and weights.get(dim, 0) > 0:
                    sim = cosine_similarity(query_vec, dim_vec[:len(query_vec)])
                    w = weights[dim]
                    total_score += sim * w
                    total_weight += w
            if total_weight > 0:
                final_score = total_score / total_weight
                scored.append((d, final_score))
        except Exception:
            continue

    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for d, score in scored[:top_k]:
        results.append({
            "id": d.id,
            "content": d.content[:200],
            "wing": d.wing,
            "room": d.room,
            "importance": d.importance,
            "holographic_score": round(score, 4),
        })

    return results


_fts_engine: FTS5SearchEngine | None = None


def _get_fts_engine() -> FTS5SearchEngine:
    """获取全局 FTS 引擎实例（避免重复创建）"""
    global _fts_engine
    if _fts_engine is None:
        _fts_engine = FTS5SearchEngine()
    return _fts_engine
