"""盘古语义重排序 — 搜索结果多维重排序

在 RRF 融合排序基础上，加入上下文感知、时效性、重要性、质量等维度的重排序。

评分公式：
  final_score = rrf_score * w_rrf
              + context_match * w_ctx
              + recency * w_rec
              + importance * w_imp
              + quality * w_qua
              + access_freq * w_acc
"""
import logging
import math
import time
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.reranker")

# 默认权重
DEFAULT_WEIGHTS = {
    "rrf": 0.35,       # RRF 基础分
    "context": 0.25,   # 上下文匹配
    "recency": 0.15,   # 时效性
    "importance": 0.15, # 重要性
    "quality": 0.10,   # 内容质量
}


class SemanticReranker:
    """语义重排序引擎"""

    def __init__(self, config: PanguConfig = None, weights: dict = None):
        self.config = config or PanguConfig.load()
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    def rerank(
        self,
        query: str,
        results: list[dict],
        context: str = "",
        drawers: list[Drawer] = None,
        limit: int = 10,
    ) -> list[dict]:
        """重排序搜索结果

        Args:
            query: 原始搜索查询
            results: RRF 排序后的结果列表
            context: 当前对话上下文（可选）
            drawers: 完整记忆列表（用于统计）
            limit: 返回数量
        """
        if not results:
            return []

        drawer_map = {}
        if drawers:
            drawer_map = {d.id: d for d in drawers}

        scored = []
        for r in results:
            mid = r.get("id", "")
            d = drawer_map.get(mid)

            rrf_s = r.get("rrf_score", 0.0)
            ctx_s = self._context_score(query, context, r, d)
            rec_s = self._recency_score(d or r)
            imp_s = self._importance_score(d or r)
            qua_s = self._quality_score(d or r)

            final = (
                rrf_s * self.weights["rrf"]
                + ctx_s * self.weights["context"]
                + rec_s * self.weights["recency"]
                + imp_s * self.weights["importance"]
                + qua_s * self.weights["quality"]
            )

            r_copy = dict(r)
            r_copy["rerank_score"] = round(final, 6)
            r_copy["rerank_breakdown"] = {
                "rrf": round(rrf_s, 6),
                "context": round(ctx_s, 4),
                "recency": round(rec_s, 4),
                "importance": round(imp_s, 4),
                "quality": round(qua_s, 4),
            }
            scored.append(r_copy)

        scored.sort(key=lambda x: -x["rerank_score"])
        return scored[:limit]

    def _context_score(self, query: str, context: str, result: dict, drawer: Drawer = None) -> float:
        """上下文匹配分"""
        if not context:
            return 0.5

        raw = result.get("content", "")
        if not raw and drawer:
            raw = drawer.content or ""
        content = raw.lower()
        context_lower = context.lower()
        query_lower = query.lower()

        score = 0.0

        # 查询关键词匹配（词级 + 字符级）
        query_words = set(self._tokenize(query_lower))
        if query_words:
            matched = sum(1 for w in query_words if w in content)
            # 字符级 fallback：提取 query 中文字符匹配
            if matched < len(query_words):
                import re
                cn_chars = set(re.findall(r'[\u4e00-\u9fff]', query_lower))
                if cn_chars:
                    char_matched = sum(1 for c in cn_chars if c in content)
                    matched = max(matched, char_matched)
            score += (matched / max(len(query_words), 1)) * 0.4

        # 上下文关键词匹配
        ctx_words = set(self._tokenize(context_lower)) - query_words
        if ctx_words:
            ctx_matched = sum(1 for w in ctx_words if w in content)
            if ctx_matched == 0:
                import re
                cn_chars = set(re.findall(r'[\u4e00-\u9fff]', context_lower))
                if cn_chars:
                    ctx_matched = sum(1 for c in cn_chars if c in content)
            score += min(ctx_matched / max(len(ctx_words), 1) * 0.3, 0.3)

        # 标签匹配
        tags = result.get("tags") or (drawer.tags if drawer else [])
        for tag in tags:
            if tag.lower() in context_lower:
                score += 0.1

        return min(1.0, score)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词：支持中英文混合"""
        import re
        # 提取中文2字以上词组 + 英文单词
        cn_words = re.findall(r'[\u4e00-\u9fff]{2,}', text)
        en_words = [w for w in re.findall(r'[a-zA-Z0-9_]{2,}', text)]
        return cn_words + en_words

    def _recency_score(self, source) -> float:
        """时效性分 — 越新越高"""
        created = None
        if hasattr(source, "created_at"):
            created = source.created_at
        elif isinstance(source, dict):
            created = source.get("created_at")

        if not created:
            return 0.5

        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created)
            elif isinstance(created, float):
                created_dt = datetime.fromtimestamp(created)
            else:
                return 0.5

            days_old = (datetime.now() - created_dt).total_seconds() / 86400
            # 7天内满分，30天衰减，90天以上低分
            if days_old <= 7:
                return 1.0
            elif days_old <= 30:
                return 0.8 - (days_old - 7) * 0.02
            elif days_old <= 90:
                return 0.3 - (days_old - 30) * 0.003
            else:
                return max(0.05, 0.3 - days_old * 0.001)
        except Exception:
            return 0.5

    def _importance_score(self, source) -> float:
        """重要性分 — importance 直接映射"""
        imp = 0.0
        if hasattr(source, "importance"):
            imp = source.importance
        elif isinstance(source, dict):
            imp = source.get("importance", 0)

        # importance 通常 0-5，映射到 0-1
        return min(1.0, imp / 5.0) if imp else 0.5

    def _quality_score(self, source) -> float:
        """内容质量分"""
        content = ""
        if hasattr(source, "content"):
            content = source.content or ""
        elif isinstance(source, dict):
            content = source.get("content", "")

        if not content:
            return 0.0

        score = 0.3  # 基础分

        # 长度
        if len(content) > 100:
            score += 0.1
        if len(content) > 300:
            score += 0.1
        if len(content) > 500:
            score += 0.05

        # 结构化特征
        if "```" in content:
            score += 0.1
        if any(c in content for c in ["#", "-", "|", "1."]):
            score += 0.05

        # 有标签
        tags = []
        if hasattr(source, "tags"):
            tags = source.tags or []
        elif isinstance(source, dict):
            tags = source.get("tags", [])
        if len(tags) >= 2:
            score += 0.1

        return min(1.0, score)


_reranker: SemanticReranker | None = None


def get_reranker(config: PanguConfig = None) -> SemanticReranker:
    global _reranker
    if _reranker is None:
        _reranker = SemanticReranker(config)
    return _reranker


def rerank_search_results(
    query: str,
    results: list[dict],
    context: str = "",
    drawers: list[Drawer] = None,
    limit: int = 10,
) -> list[dict]:
    """便捷函数：重排序搜索结果"""
    return get_reranker().rerank(query, results, context=context, drawers=drawers, limit=limit)
