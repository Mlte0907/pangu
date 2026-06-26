"""盘古搜索结果解释 — 为每条搜索结果生成匹配原因说明

核心能力：
1. 关键词匹配解释：哪些词命中了
2. 语义相似度解释：向量匹配程度
3. 上下文关联解释：与当前对话的关联
4. 时效性解释：为什么这条记忆被排在前面
5. 综合解释：一句话总结匹配原因
"""

import logging
import re
from dataclasses import dataclass, field

from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.search_explainer")


@dataclass
class SearchExplanation:
    """单条搜索结果的解释"""

    memory_id: str
    summary: str  # 一句话总结
    match_reasons: list[str] = field(default_factory=list)  # 匹配原因列表
    matched_keywords: list[str] = field(default_factory=list)  # 命中的关键词
    match_type: str = "keyword"  # keyword / semantic / context / tag
    confidence: float = 0.0  # 解释置信度 0-1


class SearchExplainer:
    """搜索结果解释引擎"""

    def __init__(self):
        self._stopwords = {
            "的",
            "了",
            "是",
            "在",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
            "那",
            "什么",
            "怎么",
            "如何",
            "可以",
            "吗",
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "of",
            "in",
            "to",
            "for",
            "with",
            "on",
            "at",
            "from",
            "by",
            "as",
            "or",
            "and",
            "not",
            "but",
        }

    def explain(
        self,
        query: str,
        result: dict,
        context: str = "",
        drawer: Drawer = None,
        all_results: list[dict] = None,
    ) -> SearchExplanation:
        """为一条搜索结果生成解释"""
        content = result.get("content", "")
        if not content and drawer:
            content = drawer.content or ""

        tags = result.get("tags", [])
        if not tags and drawer:
            tags = drawer.tags or []

        reasons = []
        matched_kws = []

        # 1. 关键词匹配
        kw_reasons, kw_matches = self._explain_keyword_match(query, content)
        reasons.extend(kw_reasons)
        matched_kws.extend(kw_matches)

        # 2. 标签匹配
        tag_reasons = self._explain_tag_match(query, tags)
        reasons.extend(tag_reasons)

        # 3. 上下文匹配
        if context:
            ctx_reasons, ctx_kws = self._explain_context_match(context, content)
            reasons.extend(ctx_reasons)
            matched_kws.extend(ctx_kws)

        # 4. FTS/向量排名
        rank_reason = self._explain_rank(result, all_results or [])
        if rank_reason:
            reasons.append(rank_reason)

        # 5. 时效性
        recency_reason = self._explain_recency(result, drawer)
        if recency_reason:
            reasons.append(recency_reason)

        # 综合总结
        summary = self._generate_summary(query, matched_kws, reasons, content)

        # 匹配类型判断
        if matched_kws:
            match_type = "keyword"
        elif tags and any(t.lower() in query.lower() for t in tags):
            match_type = "tag"
        elif context:
            match_type = "context"
        else:
            match_type = "semantic"

        confidence = min(1.0, len(reasons) * 0.25)

        return SearchExplanation(
            memory_id=result.get("id", ""),
            summary=summary,
            match_reasons=reasons,
            matched_keywords=list(set(matched_kws)),
            match_type=match_type,
            confidence=round(confidence, 2),
        )

    def explain_batch(
        self,
        query: str,
        results: list[dict],
        context: str = "",
    ) -> list[SearchExplanation]:
        """批量解释搜索结果"""
        explanations = []
        for r in results:
            exp = self.explain(query, r, context=context, all_results=results)
            explanations.append(exp)
        return explanations

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词（去停用词）"""
        words = text.lower().split()
        keywords = [w for w in words if len(w) >= 2 and w not in self._stopwords]
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", text.lower())
        en_words = re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
        return list(set(keywords + cn_words + en_words))

    def _explain_keyword_match(self, query: str, content: str) -> tuple[list[str], list[str]]:
        """解释关键词匹配"""
        query_kws = self._extract_keywords(query)
        content_lower = content.lower()
        matched = []
        reasons = []

        for kw in query_kws:
            if kw in content_lower:
                matched.append(kw)

        if matched:
            if len(matched) == len(query_kws):
                reasons.append(f"所有查询关键词命中: {', '.join(matched[:5])}")
            else:
                reasons.append(f"命中关键词: {', '.join(matched[:5])}")

        return reasons, matched

    def _explain_tag_match(self, query: str, tags: list[str]) -> list[str]:
        """解释标签匹配"""
        reasons = []
        query_lower = query.lower()
        matched_tags = [t for t in tags if t.lower() in query_lower]
        if matched_tags:
            reasons.append(f"标签匹配: {', '.join(matched_tags[:3])}")
        return reasons

    def _explain_context_match(self, context: str, content: str) -> tuple[list[str], list[str]]:
        """解释上下文匹配"""
        ctx_kws = self._extract_keywords(context)
        content_lower = content.lower()
        matched = [kw for kw in ctx_kws if kw in content_lower]

        reasons = []
        if matched:
            reasons.append(f"与当前对话相关: {', '.join(matched[:3])}")

        return reasons, matched

    def _explain_rank(self, result: dict, all_results: list[dict]) -> str:
        """解释排名"""
        fts_rank = result.get("fts_rank")
        vec_rank = result.get("vector_rank")
        kg_rank = result.get("kg_rank")

        parts = []
        if fts_rank and fts_rank <= 3:
            parts.append(f"全文搜索排名第{fts_rank}")
        if vec_rank and vec_rank <= 3:
            parts.append(f"语义排名第{vec_rank}")
        if kg_rank:
            parts.append("知识图谱关联")

        return "，".join(parts) if parts else ""

    def _explain_recency(self, result: dict, drawer: Drawer = None) -> str:
        """解释时效性"""
        created = result.get("created_at")
        if not created and drawer:
            created = drawer.created_at
        if not created:
            return ""

        try:
            if isinstance(created, str):
                from datetime import datetime

                dt = datetime.fromisoformat(created)
                days_old = (datetime.now() - dt).total_seconds() / 86400
            else:
                return ""

            if days_old < 1:
                return "今天创建"
            elif days_old < 7:
                return f"{int(days_old)}天前创建"
            elif days_old < 30:
                return "近一个月"
            return ""
        except Exception:
            return ""

    def _generate_summary(self, query: str, keywords: list[str], reasons: list[str], content: str) -> str:
        """生成一句话总结"""
        if not reasons:
            return f'与查询 "{query[:20]}" 语义相关'

        if keywords:
            return f"匹配关键词 {', '.join(keywords[:3])}，{reasons[0]}"
        return reasons[0]


_explainer: SearchExplainer | None = None


def get_search_explainer() -> SearchExplainer:
    global _explainer
    if _explainer is None:
        _explainer = SearchExplainer()
    return _explainer
