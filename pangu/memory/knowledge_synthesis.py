"""盘古知识综合 — 从多源记忆中综合提炼新知识

核心能力：
1. 多源融合：从不同 Wing/Agent 的记忆中综合知识
2. 知识提炼：从大量记忆中提炼核心洞察
3. 矛盾检测：发现不同来源的矛盾信息
4. 知识图谱增强：将综合结果反馈到知识图谱
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.knowledge_synthesis")


@dataclass
class Insight:
    """洞察"""
    topic: str
    summary: str
    sources: list[str]
    confidence: float
    supporting_count: int
    contradicting_count: int


@dataclass
class Contradiction:
    """矛盾"""
    claim_a: str
    claim_b: str
    source_a: str
    source_b: str
    topic: str
    severity: str  # major / minor


class KnowledgeSynthesizer:
    """知识综合引擎"""

    def __init__(self, config=None):
        self.config = config
        self._synthesis_history: list[dict] = []

    def synthesize_by_topic(self, drawers: list) -> list[Insight]:
        """按主题综合知识"""
        tag_groups: dict[str, list] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        insights = []
        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue

            sources = list(set(d.wing for d in group))
            avg_importance = sum(d.importance for d in group) / len(group)
            contents = [d.content[:100] for d in group]

            summary = f"[{tag}] {len(group)} 条记忆来自 {len(sources)} 个领域"
            if len(contents) > 0:
                summary += f"。核心内容: {contents[0][:60]}..."

            insights.append(Insight(
                topic=tag,
                summary=summary,
                sources=sources,
                confidence=min(0.9, 0.3 + len(group) * 0.1),
                supporting_count=len(group),
                contradicting_count=0,
            ))

        insights.sort(key=lambda i: i.confidence, reverse=True)
        return insights[:20]

    def detect_contradictions(self, drawers: list) -> list[Contradiction]:
        """检测矛盾信息"""
        contradictions = []

        negative_keywords = ["不好", "失败", "问题", "错误", "不行", "有缺陷"]
        positive_keywords = ["好", "成功", "优秀", "正常", "通过", "完善"]

        tag_groups: dict[str, list] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue

            pos = [d for d in group if any(k in d.content for k in positive_keywords)]
            neg = [d for d in group if any(k in d.content for k in negative_keywords)]

            if pos and neg:
                contradictions.append(Contradiction(
                    claim_a=pos[0].content[:80],
                    claim_b=neg[0].content[:80],
                    source_a=pos[0].wing,
                    source_b=neg[0].wing,
                    topic=tag,
                    severity="minor",
                ))

        return contradictions

    def extract_core_insights(self, drawers: list, top_k: int = 10) -> list[dict]:
        """提取核心洞察"""
        scored = []
        for d in drawers:
            score = d.importance / 5.0
            score += min(len(d.tags) * 0.05, 0.2)
            score += min(len(d.content) / 500, 0.1)
            scored.append((d, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        insights = []
        for d, score in scored[:top_k]:
            insights.append({
                "id": d.id,
                "content": d.content[:100],
                "wing": d.wing,
                "importance": d.importance,
                "score": round(score, 3),
                "tags": d.tags[:5],
            })

        self._synthesis_history.append({
            "timestamp": datetime.now().isoformat(),
            "total_drawers": len(drawers),
            "insights_extracted": len(insights),
        })

        return insights

    def get_synthesis_stats(self) -> dict:
        """获取综合统计"""
        return {
            "synthesis_count": len(self._synthesis_history),
            "latest": self._synthesis_history[-1] if self._synthesis_history else None,
        }


_synthesizer: KnowledgeSynthesizer | None = None


def get_synthesizer(config=None) -> KnowledgeSynthesizer:
    """获取全局知识综合实例"""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = KnowledgeSynthesizer(config)
    return _synthesizer
