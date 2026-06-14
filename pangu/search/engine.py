"""盘古搜索模块 — 多模式记忆搜索"""

from ..core.config import PanguConfig
from ..core.palace import Drawer


class SemanticSearch:
    """语义搜索 — 支持关键词匹配和向量搜索双模式"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
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

    def search(self, query: str, drawers: list[Drawer],
               wing: str = None, room: str = None,
               hall: str = None, n_results: int = 10,
               use_embeddings: bool = True) -> list[dict]:
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
            filtered.append(d)

        if not filtered:
            return []

        # 尝试向量搜索
        if use_embeddings and self.embedder:
            items = [{
                "id": d.id,
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "hall": d.hall,
                "importance": d.importance,
                "source_file": d.source_file,
                "tags": d.tags,
                "created_at": d.created_at,
            } for d in filtered]
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
            importance_weight = d.importance * 0.3
            tag_score = sum(2.0 for tag in d.tags if tag.lower() in query_lower)

            total_score = kw_score + title_bonus + importance_weight + tag_score
            scored.append((total_score, d))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, drawer in scored[:n_results]:
            results.append({
                "id": drawer.id,
                "content": drawer.content,
                "wing": drawer.wing,
                "room": drawer.room,
                "hall": drawer.hall,
                "score": round(score, 2),
                "importance": drawer.importance,
                "source_file": drawer.source_file,
                "tags": drawer.tags,
                "created_at": drawer.created_at,
                "source": "keyword",
            })

        return results


class LexicalSearch:
    """词汇搜索 — 精确文本匹配"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def search(self, query: str, drawers: list[Drawer],
               wing: str = None, n_results: int = 10) -> list[dict]:
        """精确文本搜索"""
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if query.lower() in d.content.lower():
                filtered.append(d)

        filtered.sort(key=lambda d: d.importance, reverse=True)

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

            results.append({
                "id": drawer.id,
                "content": drawer.content,
                "snippet": snippet,
                "wing": drawer.wing,
                "room": drawer.room,
                "importance": drawer.importance,
                "source_file": drawer.source_file,
                "created_at": drawer.created_at,
            })

        return results


class HybridSearch:
    """混合搜索 — 结合语义和词汇搜索"""

    def __init__(self, config: PanguConfig = None):
        self.semantic = SemanticSearch(config)
        self.lexical = LexicalSearch(config)

    def search(self, query: str, drawers: list[Drawer],
               wing: str = None, room: str = None,
               n_results: int = 10) -> list[dict]:
        """混合搜索"""
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
