"""盘古预测分析 — 预测用户需求和记忆趋势

核心能力：
1. 需求预测：基于历史行为预测用户下一步需求
2. 趋势分析：分析记忆增长/衰减趋势
3. 热点预测：预测即将成为热点的主题
4. 遗忘预测：预测哪些记忆即将被遗忘
"""
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger("pangu.memory.predictive_analytics")


@dataclass
class Prediction:
    """预测结果"""
    prediction_type: str
    statement: str
    confidence: float
    evidence: list[str]
    timeframe: str


class PredictiveAnalytics:
    """预测分析引擎"""

    def __init__(self, config=None):
        self.config = config
        self._prediction_history: list[dict] = []

    def predict_next_queries(self, query_history: list[str], top_k: int = 5) -> list[Prediction]:
        """预测用户下一步查询"""
        if not query_history:
            return []

        word_freq: dict[str, int] = {}
        for q in query_history[-50:]:
            for word in q.split():
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

        predictions = []
        for word, freq in sorted_words[:top_k]:
            predictions.append(Prediction(
                prediction_type="next_query",
                statement=f"用户可能搜索: {word}",
                confidence=min(0.8, freq / max(len(query_history), 1)),
                evidence=[f"该词在最近 {len(query_history)} 次查询中出现 {freq} 次"],
                timeframe="immediate",
            ))

        return predictions

    def predict_forgetting(self, drawers: list, days_threshold: int = 30) -> list[Prediction]:
        """预测即将被遗忘的记忆"""
        predictions = []

        now = datetime.now()
        for d in drawers:
            if not d.importance or d.importance / 5.0 < 0.3:
                if hasattr(d, 'last_accessed') and d.last_accessed:
                    try:
                        last = datetime.fromisoformat(d.last_accessed)
                        days_since = (now - last).days
                        if days_since > days_threshold:
                            predictions.append(Prediction(
                                prediction_type="forgetting",
                                statement=f"记忆 '{d.content[:40]}' 可能被遗忘 (已 {days_since} 天未访问)",
                                confidence=min(0.9, days_since / 100),
                                evidence=[f"重要性: {d.importance}", f"未访问: {days_since} 天"],
                                timeframe=f"{days_threshold}+ days",
                            ))
                    except (ValueError, TypeError):
                        pass

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions[:20]

    def analyze_growth_trend(self, drawers: list) -> dict:
        """分析记忆增长趋势"""
        if not drawers:
            return {"trend": "no_data", "total": 0}

        wing_counts: dict[str, int] = {}
        for d in drawers:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1

        total = len(drawers)
        avg_importance = statistics.mean([d.importance for d in drawers])
        tag_diversity = len(set(t for d in drawers for t in d.tags))

        return {
            "total_memories": total,
            "wing_distribution": wing_counts,
            "avg_importance": round(avg_importance, 2),
            "tag_diversity": tag_diversity,
            "growth_rate": f"{total / max(1, 30)} 条/天 (估算)",
            "health_score": round(min(1.0, tag_diversity / max(total, 1) + avg_importance / 10), 2),
        }

    def predict_hot_topics(self, drawers: list, top_k: int = 5) -> list[Prediction]:
        """预测热点主题"""
        tag_recent: dict[str, int] = {}
        tag_all: dict[str, int] = {}

        for d in drawers:
            for tag in d.tags:
                tag_all[tag] = tag_all.get(tag, 0) + 1
                if d.importance / 5.0 > 0.6:
                    tag_recent[tag] = tag_recent.get(tag, 0) + 1

        predictions = []
        for tag, recent_count in sorted(tag_recent.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            all_count = tag_all.get(tag, 0)
            momentum = recent_count / max(all_count, 1)
            predictions.append(Prediction(
                prediction_type="hot_topic",
                statement=f"主题 '{tag}' 正在升温 (活跃度: {momentum:.2f})",
                confidence=min(0.85, momentum),
                evidence=[f"近期 {recent_count} 条", f"总计 {all_count} 条"],
                timeframe="near_term",
            ))

        return predictions

    def full_analysis(self, drawers: list, query_history: list[str] = None) -> dict:
        """完整预测分析"""
        result = {
            "growth_trend": self.analyze_growth_trend(drawers),
            "hot_topics": [
                {"statement": p.statement, "confidence": p.confidence}
                for p in self.predict_hot_topics(drawers)
            ],
            "forgetting_risk": len(self.predict_forgetting(drawers)),
        }

        if query_history:
            result["next_queries"] = [
                {"statement": p.statement, "confidence": p.confidence}
                for p in self.predict_next_queries(query_history)
            ]

        self._prediction_history.append({
            "timestamp": datetime.now().isoformat(),
            "total_memories": len(drawers),
        })

        return result

    def get_prediction_stats(self) -> dict:
        """获取预测统计"""
        return {
            "predictions_count": len(self._prediction_history),
            "latest": self._prediction_history[-1] if self._prediction_history else None,
        }


_analytics: PredictiveAnalytics | None = None


def get_analytics(config=None) -> PredictiveAnalytics:
    """获取全局预测分析实例"""
    global _analytics
    if _analytics is None:
        _analytics = PredictiveAnalytics(config)
    return _analytics
