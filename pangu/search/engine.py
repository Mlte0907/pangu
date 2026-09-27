"""盘古搜索模块 — 多模式记忆搜索"""

import logging

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger(__name__)


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
        for r in hits:
            d = by_id.get(r.get("id"))
            item = dict(r)
            item["score"] = float(r.get("rrf_score") or 0.0)
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
