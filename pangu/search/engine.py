"""盘古搜索模块 — 多模式记忆搜索"""

import logging

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger(__name__)

# 可信阈值：**原始余弦相似度**（未归一化）低于它 = 「有结果但不值得当答案」。
# 2026-09-19 实测相关查询 Top1 是 0.36+、无关查询 0.19-0.31，0.32 落在两者之间。
# ⚠ 这个阈值只能配**原始 sim**：`hybrid_search` 的 rrf_score 被归一化到 0-1、
# 第一名恒为 1.0，拿去比阈值会恒判命中（2026-09-28 实测）。
# 由 `memory_ops.py` 导入共用，别在两处各写一份。
STRONG_MATCH_THRESHOLD = 0.32


class SemanticSearch:
    """语义搜索 — 支持关键词匹配和向量搜索双模式"""

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
        self._embedder = None

    @property
    def embedder(self):
        """懒加载向量嵌入器"""
        if self._embedder is None:
            try:
                from .embedder import VectorEmbedder

                self._embedder = VectorEmbedder(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    def search(
        self,
        query: str,
        drawers: list[Drawer],
        wing: str = None,
        room: str = None,
        hall: str = None,
        source: str = None,  # 新增：按来源平台过滤
        n_results: int = 10,
        use_embeddings: bool = True,
    ) -> list[dict]:
        """语义搜索 — 优先使用向量搜索，回退到关键词匹配"""
        # 过滤
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if room and d.room != room:
                continue
            if hall and d.hall != hall:
                continue
            if source and d.source != source:
                continue
            filtered.append(d)

        if not filtered:
            return []

        # 尝试向量搜索
        if use_embeddings and self.embedder:
            items = []
            for d in filtered:
                content = d.content
                # 密文在嵌入前解密（2026-09-19）：这是第 4 条同类泄露路径——
                # search/recall/hybrid 之后这条也漏了。密文既不能当文本嵌入
                # （无语义），也不能原样返回给用户（gAAAAAB… 乱码）。
                if isinstance(content, str) and content.startswith("gAAAAA"):
                    try:
                        from ..memory.encryption import decrypt

                        content = decrypt(content)
                    except Exception:
                        pass
                items.append(
                    {
                        "id": d.id,
                        "content": content,
                        "wing": d.wing,
                        "room": d.room,
                        "hall": d.hall,
                        "importance": d.importance,
                        "source": d.source,
                        "source_file": d.source_file,
                        "tags": d.tags,
                        "created_at": d.created_at,
                    }
                )
            try:
                results = self.embedder.search(query, items, top_k=n_results)
                return results
            except Exception:
                pass  # 回退到关键词匹配

        # 关键词匹配回退
        query_lower = query.lower()
        keywords = query_lower.split()

        scored = []
        for d in filtered:
            content_lower = d.content.lower()
            kw_score = sum(content_lower.count(kw) for kw in keywords)
            title_bonus = 2.0 if query_lower in d.room.lower() else 0
            imp = d.importance if isinstance(d.importance, (int, float)) else 3.0
            importance_weight = imp * 0.3
            tag_score = sum(2.0 for tag in d.tags if tag.lower() in query_lower)

            total_score = kw_score + title_bonus + importance_weight + tag_score
            scored.append((total_score, d))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, drawer in scored[:n_results]:
            content = drawer.content
            if isinstance(content, str) and content.startswith("gAAAAA"):
                try:
                    from ..memory.encryption import decrypt

                    content = decrypt(content)
                except Exception:
                    pass
            results.append(
                {
                    "id": drawer.id,
                    "content": content,
                    "wing": drawer.wing,
                    "room": drawer.room,
                    "hall": drawer.hall,
                    "score": round(score, 2),
                    "importance": drawer.importance,
                    "source_file": drawer.source_file,
                    "tags": drawer.tags,
                    "created_at": drawer.created_at,
                    "source": "keyword",
                }
            )

        return results


class LexicalSearch:
    """词汇搜索 — 精确文本匹配"""

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()

    def search(self, query: str, drawers: list[Drawer], wing: str = None, n_results: int = 10) -> list[dict]:
        """精确文本搜索"""
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if query.lower() in d.content.lower():
                filtered.append(d)

        filtered.sort(key=lambda d: d.importance if isinstance(d.importance, (int, float)) else 0.0, reverse=True)

        results = []
        for drawer in filtered[:n_results]:
            # 找到匹配位置
            idx = drawer.content.lower().index(query.lower())
            start = max(0, idx - 50)
            end = min(len(drawer.content), idx + len(query) + 150)
            snippet = drawer.content[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(drawer.content):
                snippet = snippet + "..."

            results.append(
                {
                    "id": drawer.id,
                    "content": drawer.content,
                    "snippet": snippet,
                    "wing": drawer.wing,
                    "room": drawer.room,
                    "importance": drawer.importance,
                    "source_file": drawer.source_file,
                    "created_at": drawer.created_at,
                }
            )

        return results


class HybridSearch:
    """混合搜索 — 结合语义和词汇搜索"""

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
        self.semantic = SemanticSearch(config)
        self.lexical = LexicalSearch(config)

    def _relevance_map(self, query: str, pool: list) -> dict:
        """取 query 与候选的**原始余弦相似度**（`VectorEmbedder` 体系）。

        三套分数体系实测对比（2026-09-28，350 条真实库）—— **别再用错**：

        | 体系 | 相关查询 top | 无关查询 top | 能否卡 0.32 阈值 |
        |---|---|---|---|
        | `hybrid_search.rrf_score` | 归一化后**第一名恒 1.0** | 同左 | ❌ 恒判命中 |
        | `vector_index` 的 sim | 0.48 ~ 0.56 | **0.49 ~ 0.65** | ❌ 完全重叠，无关最高 0.65 反超所有相关查询 |
        | **`VectorEmbedder` 的 sim** | 0.44 ~ 0.78（4/4 正确） | 0.10 / 0.26 正确拒绝 | ✅ 这才是 `RELEVANCE_FLOOR=0.32` 的原生体系 |

        本轮复测 8 条查询：6 条正确、2 条边界（`蓝鲸迁徙量子隧穿` 0.396 误收，
        `Photoshop 海报渐变` 0.437 —— 而库里确实有视觉重构记忆，可能算真相关）。

        性能：`EmbeddingCache` 让条目嵌入只算一次 —— **冷启动 3.06s、
        稳态 0.00~0.05s**（换查询只重算 query 向量）。
        """
        if not pool:
            return {}
        try:
            from ..memory.encryption import decrypt
            from ..search.embedder import VectorEmbedder

            items = []
            for d in pool:
                c = d.content or ""
                if c.startswith("gAAAAA"):
                    try:
                        c = decrypt(c)
                    except Exception:
                        continue  # 解不开就跳过：密文没有语义，嵌入它只会污染分数
                items.append({"id": d.id, "content": c})
            if not items:
                return {}

            res = VectorEmbedder(self.config).search(query, items, top_k=len(items))
            return {
                r.get("id"): float(r.get("score"))
                for r in res
                if isinstance(r, dict) and r.get("id") and r.get("score") is not None
            }
        except Exception:
            return {}  # 取不到相似度 = 降级，绝不能因此把搜索弄崩

    def _search_rrf(
        self, query: str, drawers: list[Drawer], wing: str | None, room: str | None, n_results: int
    ) -> list[dict]:
        """三路 RRF 召回（FTS + 向量 + KG），并把字段对齐到本类的返回契约。

        为什么要有它（2026-09-28 实测）：本类原本是 `SemanticSearch`（纯向量）+
        `LexicalSearch`（**整串子串**匹配 `query.lower() in content.lower()`）。
        于是「精确标识符查询」两路全废 —— 实测查询
        ``llmDaily ReferenceError 概览全显 根因``：

            本类      n=10/30/100 → 目标记忆**连 top-100 都进不去**（向量排 271/331，
                                 词法因整串不匹配返回 0 条）
            三路 RRF            → **第 7 名，fts_rank=1**（FTS 精确命中标识符）

        字段对齐要点（下游有硬依赖，别改）：
        * ``score`` ← ``rrf_score`` —— `memory_ops.py` 用它算「最高相似度」并对比
          0.32 可信阈值；
        * ``source`` 必须落回 ``semantic`` / ``lexical`` —— `memory_ops.py:388`
          按它分桶统计 `vector_hits` / `fts_hits`，写别的值统计就恒 0；
        * 补 ``hall`` / ``source_file`` —— RRF 结果不带这两个字段，而
          SemanticSearch 的返回契约里有。
        """
        pool = list(drawers or [])
        if wing:
            pool = [d for d in pool if d.wing == wing]
        if room:
            pool = [d for d in pool if d.room == room]
        if not pool:
            return []

        from ..memory.hybrid_search import hybrid_search as rrf_search

        hits = rrf_search(query, pool, config=self.config, limit=max(1, n_results))
        if not hits:
            return []  # 无命中是合法结果，不要回退去硬凑不相关的条目

        by_id = {d.id: d for d in pool}
        out: list[dict] = []
        # 相关性判据：VectorEmbedder 的原始余弦相似度。见 `_relevance_map` 的
        # 三体系实测对比 —— rrf_score 归一化后第一名恒 1、vector_index 的 sim
        # 相关与无关完全重叠，两者都做不了阈值判断。
        rel_map = self._relevance_map(query, pool)
        for r in hits:
            d = by_id.get(r.get("id"))
            item = dict(r)
            item["score"] = float(r.get("rrf_score") or 0.0)
            # relevance = 原始相似度（可能 None：纯字面命中、无向量命中）
            # relevant  = 是否达到可信阈值 —— 补上 RRF 路径**一直缺失**的这个字段，
            #             老的 `no_strong_match`（memory_ops）依赖它，此前因取不到
            #             默认 True 而**恒不触发**，等于失效。
            _rel = rel_map.get(r.get("id"))
            item["relevance"] = None if _rel is None else round(float(_rel), 4)
            item["relevant"] = bool(_rel is not None and _rel >= STRONG_MATCH_THRESHOLD)
            if r.get("vector_rank") is not None:
                item["source"] = "semantic"
            elif r.get("fts_rank") is not None:
                item["source"] = "lexical"
            else:
                item["source"] = "semantic"
            item["hall"] = getattr(d, "hall", "") if d else ""
            item["source_file"] = getattr(d, "source_file", "") if d else ""
            out.append(item)
        return out

    def search(
        self, query: str, drawers: list[Drawer], wing: str = None, room: str = None, n_results: int = 10
    ) -> list[dict]:
        """混合搜索。

        优先走三路 RRF（见 `_search_rrf`）；**只在抛异常时**回退到
        Semantic + Lexical 合并 —— 返回空列表是合法结果，不代表失败，
        否则会拿不相关的条目去凑数。
        """
        try:
            return self._search_rrf(query, drawers, wing, room, n_results)
        except Exception:
            logger.debug("RRF 搜索失败，回退 Semantic+Lexical 合并", exc_info=True)

        semantic_results = self.semantic.search(query, drawers, wing=wing, room=room, n_results=n_results * 2)
        lexical_results = self.lexical.search(query, drawers, wing=wing, n_results=n_results * 2)

        # 合并去重
        seen_ids = set()
        merged = []

        # 优先语义搜索结果
        for r in semantic_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                r["source"] = "semantic"
                merged.append(r)

        # 补充词汇搜索结果
        for r in lexical_results:
            if r["id"] not in seen_ids and len(merged) < n_results * 2:
                seen_ids.add(r["id"])
                r["score"] = r.get("score", 0.5)
                r["source"] = "lexical"
                merged.append(r)

        return merged[:n_results]
