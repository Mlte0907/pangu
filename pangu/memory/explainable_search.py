"""盘古可解释搜索 — 为什么这条记忆被返回

核心能力：
1. 搜索解释：解释每条结果为什么被返回
2. 因果追溯：追溯搜索结果的生成路径
3. 权重可视化：展示各因素对排序的贡献
4. 搜索改进建议：基于解释给出搜索优化建议
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("pangu.memory.explainable_search")


@dataclass
class SearchExplanation:
    """搜索结果解释"""

    memory_id: str
    content_preview: str
    score: float
    factors: dict[str, float]  # 各因素贡献
    primary_reason: str
    matched_terms: list[str]


class ExplainableSearchEngine:
    """可解释搜索引擎"""

    def __init__(self, config=None):
        self.config = config
        self._explanation_history: list[dict] = []

    def explain_results(self, query: str, results: list, drawers: list) -> list[SearchExplanation]:
        """解释搜索结果"""
        explanations = []
        query_terms = set(query.lower().split())

        for result in results:
            memory_id = result.get("id", result.get("memory_id", ""))
            score = result.get("score", result.get("final_score", 0))

            drawer = None
            for d in drawers:
                if d.id == memory_id:
                    drawer = d
                    break

            if not drawer:
                continue

            factors = {}
            matched = []

            content_lower = drawer.content.lower()
            for term in query_terms:
                if term in content_lower:
                    matched.append(term)
                    factors["keyword_match"] = factors.get("keyword_match", 0) + 0.2

            if hasattr(drawer, "tags") and drawer.tags:
                tag_overlap = len(set(query_terms) & set(t.lower() for t in drawer.tags))
                if tag_overlap > 0:
                    factors["tag_match"] = tag_overlap * 0.15

            if hasattr(drawer, "importance"):
                imp_factor = (drawer.importance / 5.0) * 0.1
                factors["importance"] = imp_factor

            if score > 0.5:
                factors["vector_similarity"] = score * 0.3

            if not factors:
                factors["partial_match"] = 0.1

            sum(factors.values())
            if factors:
                primary = max(factors.items(), key=lambda x: x[1])
                primary_reason = f"{primary[0]} (贡献 {primary[1]:.2f})"
            else:
                primary_reason = "弱匹配"

            explanations.append(
                SearchExplanation(
                    memory_id=memory_id,
                    content_preview=drawer.content[:80],
                    score=score,
                    factors=factors,
                    primary_reason=primary_reason,
                    matched_terms=matched,
                )
            )

        explanations.sort(key=lambda e: e.score, reverse=True)

        self._explanation_history.append(
            {
                "query": query,
                "result_count": len(explanations),
                "top_score": explanations[0].score if explanations else 0,
            }
        )

        return explanations

    def suggest_improvement(self, query: str, explanations: list[SearchExplanation]) -> list[str]:
        """搜索改进建议"""
        suggestions = []

        if not explanations:
            suggestions.append("未找到结果，尝试使用更宽泛的关键词")
            suggestions.append("检查拼写或使用同义词替换")
            return suggestions

        all_matched = set()
        for e in explanations:
            all_matched.update(e.matched_terms)

        query_terms = set(query.lower().split())
        unmatched = query_terms - all_matched

        if unmatched:
            suggestions.append(f"关键词 {unmatched} 未直接匹配，建议尝试同义词")

        avg_score = sum(e.score for e in explanations) / len(explanations)
        if avg_score < 0.3:
            suggestions.append("整体匹配度偏低，建议提供更多上下文")

        high_importance = [e for e in explanations if e.factors.get("importance", 0) > 0.08]
        if len(high_importance) < len(explanations) * 0.3:
            suggestions.append("大部分结果重要性偏低，建议增加高价值记忆")

        return suggestions

    def get_explanation_stats(self) -> dict:
        """获取解释统计"""
        return {
            "total_explanations": len(self._explanation_history),
            "avg_results_per_query": (
                sum(e["result_count"] for e in self._explanation_history) / len(self._explanation_history)
                if self._explanation_history
                else 0
            ),
        }


_explainable_engine: ExplainableSearchEngine | None = None


def get_explainable_engine(config=None) -> ExplainableSearchEngine:
    """获取全局可解释搜索引擎实例"""
    global _explainable_engine
    if _explainable_engine is None:
        _explainable_engine = ExplainableSearchEngine(config)
    return _explainable_engine
