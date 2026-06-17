"""盘古记忆推荐系统 — 主动推荐相关记忆

核心能力：
1. 上下文推荐：基于当前对话上下文推荐相关记忆
2. 协同过滤推荐：基于相似用户的访问模式推荐
3. 关联推荐：推荐与当前查看记忆相关的其他记忆
4. 时效推荐：推荐近期重要但可能被遗忘的记忆
5. 跨域推荐：推荐不同领域但相关的记忆
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.recommendation")


@dataclass
class MemoryRecommendation:
    """记忆推荐"""
    memory_id: str
    content_preview: str
    wing: str
    score: float
    reason: str
    category: str  # context / similar / related / timely / cross_domain


class RecommendationEngine:
    """记忆推荐引擎"""

    def __init__(self, config=None):
        self.config = config
        self._recommendation_history: list[dict] = []
        self._user_feedback: dict[str, list[str]] = {}  # user_id -> liked memory_ids

    def recommend_by_context(self, context: str, drawers: list, top_k: int = 5) -> list[MemoryRecommendation]:
        """基于上下文推荐"""
        import re
        keywords = set()
        for segment in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', context):
            keywords.add(segment.lower())

        scored = []
        for d in drawers:
            score = 0
            d_lower = d.content.lower()

            for kw in keywords:
                if kw in d_lower:
                    score += 2
                for tag in d.tags:
                    if kw in tag.lower():
                        score += 3

            if score > 0:
                scored.append((d, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for d, score in scored[:top_k]:
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=min(1.0, score / 10),
                reason="上下文关键词匹配",
                category="context",
            ))

        return results

    def recommend_similar(self, memory_id: str, drawers: list, top_k: int = 5) -> list[MemoryRecommendation]:
        """推荐相似记忆"""
        target = None
        for d in drawers:
            if d.id == memory_id:
                target = d
                break

        if not target:
            return []

        target_tags = set(target.tags)
        target_wing = target.wing

        scored = []
        for d in drawers:
            if d.id == memory_id:
                continue

            tag_overlap = len(target_tags & set(d.tags))
            wing_match = 1 if d.wing == target_wing else 0
            score = tag_overlap * 3 + wing_match * 2

            if score > 0:
                scored.append((d, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for d, score in scored[:top_k]:
            overlap_tags = target_tags & set(d.tags)
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=min(1.0, score / 10),
                reason=f"共享标签: {', '.join(list(overlap_tags)[:3])}",
                category="similar",
            ))

        return results

    def recommend_timely(self, drawers: list, top_k: int = 5) -> list[MemoryRecommendation]:
        """推荐时效性记忆"""
        now = datetime.now()
        scored = []

        for d in drawers:
            if hasattr(d, 'created_at') and d.created_at:
                try:
                    created = datetime.fromisoformat(d.created_at)
                    age_days = (now - created).days
                    if 1 <= age_days <= 7:
                        imp = d.importance / 5.0
                        score = imp * 0.6 + (7 - age_days) / 7 * 0.4
                        scored.append((d, score, f"创建于 {age_days} 天前"))
                except (ValueError, TypeError):
                    pass

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for d, score, reason in scored[:top_k]:
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=round(score, 3),
                reason=reason,
                category="timely",
            ))

        return results

    def recommend_cross_domain(self, current_wing: str, drawers: list, top_k: int = 5) -> list[MemoryRecommendation]:
        """跨域推荐"""
        scored = []
        for d in drawers:
            if d.wing != current_wing:
                imp = d.importance / 5.0
                score = imp * 0.7 + 0.3
                scored.append((d, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for d, score in scored[:top_k]:
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=round(score, 3),
                reason=f"来自 {d.wing} 领域的新视角",
                category="cross_domain",
            ))

        return results

    def recommend_related(self, memory_id: str, drawers: list, top_k: int = 5) -> list[MemoryRecommendation]:
        """推荐关联记忆"""
        target = None
        for d in drawers:
            if d.id == memory_id:
                target = d
                break

        if not target:
            return []

        target_words = set()
        for word in target.content.split():
            if len(word) >= 2:
                target_words.add(word.lower())

        scored = []
        for d in drawers:
            if d.id == memory_id:
                continue

            d_words = set()
            for word in d.content.split():
                if len(word) >= 2:
                    d_words.add(word.lower())

            word_overlap = len(target_words & d_words)
            if word_overlap >= 2:
                scored.append((d, word_overlap))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for d, score in scored[:top_k]:
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=min(1.0, score / 10),
                reason=f"共享 {score} 个关键词",
                category="related",
            ))

        return results

    def get_full_recommendations(self, context: str = "", memory_id: str = "",
                                 drawers: list = None, top_k: int = 3) -> dict:
        """获取综合推荐"""
        if not drawers:
            return {"recommendations": [], "count": 0}

        all_recs = []

        if context:
            all_recs.extend(self.recommend_by_context(context, drawers, top_k))

        if memory_id:
            all_recs.extend(self.recommend_similar(memory_id, drawers, top_k))
            all_recs.extend(self.recommend_related(memory_id, drawers, top_k))

        all_recs.extend(self.recommend_timely(drawers, top_k))

        if context and drawers:
            wings = set(d.wing for d in drawers)
            for wing in wings:
                if wing not in context.lower():
                    all_recs.extend(self._collect_cross_domain(wing, drawers))

        seen = set()
        unique = []
        for r in all_recs:
            if r.memory_id not in seen:
                seen.add(r.memory_id)
                unique.append(r)

        unique.sort(key=lambda r: r.score, reverse=True)

        self._recommendation_history.append({
            "timestamp": datetime.now().isoformat(),
            "context": context[:50] if context else "",
            "recommended": len(unique[:top_k * 3]),
        })

        return {
            "recommendations": [
                {"id": r.memory_id, "preview": r.content_preview,
                 "wing": r.wing, "score": r.score, "reason": r.reason,
                 "category": r.category}
                for r in unique[:top_k * 3]
            ],
            "count": min(len(unique), top_k * 3),
        }

    def _collect_cross_domain(self, wing, drawers):
        scored = []
        for d in drawers:
            if d.wing != wing:
                imp = d.importance / 5.0
                score = imp * 0.7 + 0.3
                scored.append((d, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for d, score in scored[:2]:
            results.append(MemoryRecommendation(
                memory_id=d.id,
                content_preview=d.content[:80],
                wing=d.wing,
                score=round(score, 3),
                reason=f"来自 {d.wing} 领域的新视角",
                category="cross_domain",
            ))
        return results

    def record_feedback(self, user_id: str, memory_id: str, liked: bool) -> None:
        """记录用户反馈"""
        if user_id not in self._user_feedback:
            self._user_feedback[user_id] = []

        if liked and memory_id not in self._user_feedback[user_id]:
            self._user_feedback[user_id].append(memory_id)

    def get_recommendation_stats(self) -> dict:
        """获取推荐统计"""
        return {
            "total_recommendations": len(self._recommendation_history),
            "users_with_feedback": len(self._user_feedback),
        }


_recommendation: RecommendationEngine | None = None


def get_recommendation(config=None) -> RecommendationEngine:
    """获取全局推荐引擎实例"""
    global _recommendation
    if _recommendation is None:
        _recommendation = RecommendationEngine(config)
    return _recommendation
