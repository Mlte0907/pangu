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
from pathlib import Path

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
            import warnings

            warnings.filterwarnings("ignore", message=".*pkg_resources.*deprecated.*")
            import jieba

            jieba.setLogLevel(logging.WARNING)
            _jieba = jieba
        except ImportError:
            logger.debug("jieba not available, using regex fallback")
    return _jieba


_FTS_SPECIAL_RE = re.compile(r'\b(AND|OR|NOT|NEAR)\b|[()"*^]')

from .utils import LRUCache

_SEARCH_CACHE = LRUCache(max_size=100, ttl_seconds=60)
_CACHE_TTL = 60  # 搜索缓存 TTL（秒）


def _sanitize_fts_query(query: str) -> str:
    """清理 FTS 查询中的特殊字符"""
    return _FTS_SPECIAL_RE.sub(" ", query).strip()


def _make_cache_key(*args) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hex_digest(raw)


def cosine_similarity(a: list, b: list) -> float:
    """计算余弦相似度，支持不同维度向量（委托给统一实现）"""
    from .utils import cosine_similarity as _cos_sim

    return _cos_sim(a, b)


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
        self._tokenizer: str = ""  # 构建索引时用的分词器（"jieba"/"regex"）
        self._indexed: bool = False
        # ⚠ B7-b：这里**必须**用 `None` 表示"尚未得知目标文档数"，不能用 0。
        # 此前初始值是 0，而磁盘索引 `doc_count` 也可能是 0，于是
        # `_load_index_from_disk` 里的 `data.get("doc_count", 0) != self._indexed_count`
        # 退化成 `0 != 0` → False → 空索引被判为"最新"加载，`_indexed=True`
        # 且 `_fts_index` 只有 0 个 token，搜索恒返回空；而 `build_index`
        # 开头又因 `self._indexed` 为真而短路，**索引永远不会重建**。
        # 磁盘上只要曾出现 `doc_count=0` 的索引（warmup 曾用 v1 空库生成），
        # 就形成**永久性自我锁死**，重启也不自愈。
        # 用 None 表达"未知"，任何具体的 doc_count 都不等于 None ⇒ 必判 stale。
        self._indexed_count: int | None = None  # 索引的文档数量；None=未知

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService

                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

        self._tokenizer = "jieba" if jieba else "regex"

    def _tokenize(self, text: str) -> list[str]:
        """统一的索引/查询分词器。

        2026-09-20 修：此前索引走 `re.findall(r"[\\u4e00-\\u9fff]{1,}|[a-zA-Z]{2,}")`
        （整段中文连成一个 token），查询走 `safe_query.split()`（按空白切）。
        无空格的中文查询永远切不出与索引相等的 token ⇒ 中文召回直接失效，
        且同一句话在不同进程里（有无 jieba）表现还不一样。
        索引与查询必须走**同一个**函数，并用 `_tokenizer` 记录构建者，
        避免"用 jieba 建的索引被 regex 查询"。
        """
        jieba = _get_jieba()
        if jieba:
            return [w.strip() for w in jieba.cut(text) if w.strip()]
        return re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z]{2,}", text)

    def _tokenize_for_query(self, text: str) -> list[str]:
        """查询分词：与构建索引时的分词器保持一致。

        若磁盘索引是用不同分词器构建的（`_tokenizer` 记录），宁可走子串兜底
        （`_fallback_keyword_search`），也不要用错分词器产生"看似命中率正常、
        实则全空"的结果。
        """
        current = "jieba" if _get_jieba() else "regex"
        if self._tokenizer and current != self._tokenizer:
            logger.warning(
                f"FTS 分词器与索引构建者不一致（index={self._tokenizer}, query={current}），本次改走子串兜底"
            )
            return []
        return self._tokenize(text)

    def build_index(self, drawers: list[Drawer]) -> int:
        """构建 FTS 内存索引（支持中文分词）+ 磁盘持久化"""
        from .encryption import decrypt_drawers

        # content 落库时可能已加密；索引记的是分词 token，拿密文建出来后
        # 明文查询永远匹配不上（见 decrypt_drawers）。
        drawers = decrypt_drawers(drawers)

        # 如果索引已构建且文档数量相同，跳过重建
        if self._indexed and self._indexed_count == len(drawers):
            return len(self._fts_index)

        # 尝试从磁盘加载索引
        if self._load_index_from_disk():
            return len(self._fts_index)

        self._fts_index.clear()
        self._fts_content_map = {}
        self._indexed_count = len(drawers)
        jieba = _get_jieba()
        self._tokenizer = "jieba" if jieba else "regex"

        for d in drawers:
            content_lower = d.content.lower()
            self._fts_content_map[d.id] = content_lower

            # 与查询共用同一个分词器（见 _tokenize）：此前索引/查询各用一套
            # 正则，无空格中文查询永远切不出命中 token。
            tokens = set(self._tokenize(content_lower))

            for tag in d.tags:
                tokens.add(tag.lower())

            for token in tokens:
                if token not in self._fts_index:
                    self._fts_index[token] = set()
                self._fts_index[token].add(d.id)

        self._indexed = True
        total_tokens = len(self._fts_index)
        logger.info(
            f"FTS index built: {total_tokens} tokens, {len(drawers)} documents, jieba={'yes' if jieba else 'no'}"
        )

        # 持久化到磁盘
        self._save_index_to_disk()

        return total_tokens

    def _get_index_path(self) -> Path:
        """FTS 索引文件路径。

        ⚠ 必须走 `config.base_dir`，不能硬编码 `~/.pangu`：此前写死 home 目录，
        `PANGU_BASE_DIR` 隔离对它无效 —— 后台 pytest 因此把**真实**的
        `~/.pangu/fts_index.json` 覆盖成 doc_count=5000（实际库仅 183 条），
        条数收缩保护又把正确重建拦在门外，搜索长期命中脏索引。
        """
        try:
            base = Path(getattr(self.config, "base_dir", "") or (Path.home() / ".pangu"))
        except Exception:
            base = Path.home() / ".pangu"
        return base / "fts_index.json"

    def _save_index_to_disk(self):
        """保存索引到磁盘

        ⚠ B7-b：**空索引不落盘**。写入 `doc_count=0` 的索引只会有害——
        它既是"空索引锁死"的触发条件（历史 warmup 用 v1 空库生成过），
        又没有任何检索价值。宁可保留旧的（有效）索引文件。

        ⚠ B7-c：**条数收缩守卫**。如果本次 build 的文档数 < 磁盘已有索引
        的 50%，拒绝写入。这防止 wing 过滤等子集操作把 70+ 条的全量索引
        覆盖成几条的子集索引（routes_memory.py / retrieval.py 的历史问题）。
        """
        try:
            if not self._indexed_count:
                logger.info("FTS index empty, skip saving to disk")
                return
            # B7-c 条数收缩守卫：防止子集调用方覆盖全量索引。
            # ⚠ 但若磁盘索引明显**大于**当前真实库（历史污染，实测 5000 vs 183），
            # 守卫会把每一次正确的重建都拦下，搜索永远命中脏索引。故当磁盘条数
            # 反而大于新索引时，判定磁盘为陈旧污染，放行重建。
            path = self._get_index_path()
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        old_data = json.load(f)
                    old_count = old_data.get("doc_count", 0)
                    # ⚠ 必须先判「磁盘比真实库更大」：污染索引（实测 5000 vs 183）
                    # 也满足收缩条件（new < old*0.5），若先走收缩守卫就会被永久保留。
                    if old_count > self._indexed_count:
                        logger.warning(
                            f"FTS index on disk is larger than the live store "
                            f"(disk={old_count} > new={self._indexed_count}); "
                            f"treating disk as stale and rebuilding"
                        )
                    elif old_count > 0 and self._indexed_count < old_count * 0.5:
                        logger.warning(
                            f"FTS index shrinkage blocked: new={self._indexed_count} "
                            f"< 50% of disk={old_count}, keeping disk version"
                        )
                        return
                except Exception:
                    pass  # 读旧索引失败，继续写入
            index_data = {}
            for token, ids in self._fts_index.items():
                index_data[token] = list(ids)
            path = self._get_index_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tokens": index_data,
                        "doc_count": self._indexed_count,
                        "built_at": datetime.now().isoformat(),
                        # 与 tokens 一同落盘：只有 token→ids 的话，重启后
                        # `_fallback_keyword_search` 无内容可查（见 _load_index_from_disk）。
                        "content_map": self._fts_content_map,
                    },
                    f,
                )
            logger.info(f"FTS index saved to disk: {len(index_data)} tokens")
        except Exception as e:
            logger.warning(f"Failed to save FTS index: {e}")

    def _load_index_from_disk(self) -> bool:
        """从磁盘加载索引"""
        try:
            path = self._get_index_path()
            if not path.exists():
                return False
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # 检查文档数量是否匹配。
            # B7-b 双重防御：
            #   ① `self._indexed_count is None`（未知目标）⇒ 不能证明磁盘索引可用，
            #      必须重建（旧代码用 0 做初始值，此处会误判为"匹配"）；
            #   ② 磁盘索引 doc_count=0 ⇒ **空索引不算有效索引**，直接拒绝加载。
            #      空索引是 warmup 用空库生成的历史残留，加载它等于让搜索永久归零。
            if self._indexed_count is None:
                logger.info("FTS index target count unknown, rebuilding")
                return False
            disk_count = data.get("doc_count", 0)
            if not disk_count:
                logger.info("FTS index on disk is empty (doc_count=0), rebuilding")
                return False
            if disk_count != self._indexed_count:
                logger.info("FTS index stale, rebuilding")
                return False
            self._fts_index = {token: set(ids) for token, ids in data["tokens"].items()}
            # ⚠ 必须一并恢复 id→内容映射：兜底搜索 `_fallback_keyword_search` 依赖它，
            # 此前只恢复 token→ids，从磁盘加载后兜底路径遍历空 map 恒返回空 ——
            # 表现为「索引明明加载成功，分词没命中时却搜不到任何东西」。
            raw_map = data.get("content_map") or {}
            self._fts_content_map = {k: str(v) for k, v in raw_map.items()}
            self._indexed = True
            logger.info(f"FTS index loaded from disk: {len(self._fts_index)} tokens, {len(self._fts_content_map)} docs")
            return True
        except Exception as e:
            logger.warning(f"Failed to load FTS index: {e}")
            return False

    def _fts_search(self, query: str, drawers: list[Drawer], limit: int = 50) -> dict[str, float]:
        """FTS 全文搜索，返回 {drawer_id: score}"""
        safe_query = _sanitize_fts_query(query).lower()

        # 中文分词：与构建索引共用同一函数（见 _tokenize / _tokenize_for_query）
        keywords = self._tokenize_for_query(safe_query)

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

        items = [
            {
                "id": d.id,
                "content": d.content,
            }
            for d in drawers
        ]

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
            cached = _SEARCH_CACHE.get(cache_key)
            if cached is not None:
                return cached

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
        for did, score in list(fused.items())[offset : offset + limit]:
            d = drawer_map.get(did)
            if not d:
                continue
            results.append(
                {
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
                }
            )

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
            _SEARCH_CACHE.set(cache_key, response)

        return response

    def clear_cache(self):
        """清除搜索缓存"""
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
                    sim = cosine_similarity(query_vec, dim_vec[: len(query_vec)])
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
        results.append(
            {
                "id": d.id,
                "content": d.content[:200],
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "holographic_score": round(score, 4),
            }
        )

    return results


_fts_engine: FTS5SearchEngine | None = None
_fts_engine_lock = threading.Lock()


def _get_fts_engine() -> FTS5SearchEngine:
    """获取全局 FTS 引擎实例（线程安全）"""
    global _fts_engine
    if _fts_engine is None:
        with _fts_engine_lock:
            if _fts_engine is None:
                _fts_engine = FTS5SearchEngine()
    return _fts_engine
