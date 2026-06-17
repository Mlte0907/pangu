"""盘古好奇心探索引擎 — 知识空白发现与探索建议

移植自伏羲 curiosity.py，适配盘古架构：
- 使用 PanguConfig + Drawer 替代 Fuxi 的 CognitiveEngine
- 发现知识空白（未连接、孤立的记忆）
- 基于身份话题生成探索建议
"""

import logging
from datetime import datetime

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.curiosity")

CURIOSITY_ACTIVATION_THRESHOLD = 0.5


class CuriosityEngine:
    """好奇心探索 — 主动发现知识空白 + 身份驱动探索"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._last_state: dict = {}

    def explore(self, drawers: list, emotion_valence: float = 0.0, frustration: float = 0.0) -> dict:
        """运行一次好奇心探索周期"""
        identity_topics = self._identify_identity_topics(drawers)
        emotion_boost = abs(emotion_valence) > CURIOSITY_ACTIVATION_THRESHOLD
        frustration_boost = frustration > 0.3

        knowledge_gaps = self._find_gaps(drawers)
        suggestions = self._generate_suggestions(knowledge_gaps, identity_topics)

        state = {
            "knowledge_gaps": len(knowledge_gaps),
            "gaps": knowledge_gaps[:5],
            "identity_topics": identity_topics[:3],
            "emotion_boost": emotion_boost,
            "frustration_boost": frustration_boost,
            "suggestions": suggestions,
            "recommendation": (
                "Consider linking isolated memories"
                if knowledge_gaps
                else "Memory graph is well-connected"
            ),
            "timestamp": datetime.now().isoformat(),
        }
        self._last_state = state
        return state

    def find_gaps(self, drawers: list) -> dict:
        """发现知识空白"""
        gaps = self._find_gaps(drawers)
        identity_topics = self._identify_identity_topics(drawers)
        suggestions = self._generate_suggestions(gaps, identity_topics)
        return {
            "gaps": gaps,
            "identity_topics": identity_topics[:5],
            "suggestions": suggestions,
            "count": len(gaps),
        }

    def suggest_topics(self, drawers: list) -> dict:
        """生成探索主题建议"""
        gaps = self._find_gaps(drawers)
        identity_topics = self._identify_identity_topics(drawers)
        suggestions = self._generate_suggestions(gaps, identity_topics)
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
        }

    def _identify_identity_topics(self, drawers: list) -> list:
        """识别与身份叙事相关的话题"""
        identity_keywords = {"身份", "identity", "自我", "价值观", "原则"}
        return [
            {"id": d.id[:8], "preview": d.content[:80]}
            for d in drawers
            if any(kw in d.content.lower() for kw in identity_keywords)
        ][:5]

    def _find_gaps(self, drawers: list) -> list:
        """找出未连接的孤立记忆"""
        gaps = []
        for d in drawers:
            if d.importance >= 3.0 and not d.tags:
                gaps.append({
                    "item_id": d.id,
                    "item_preview": d.content[:80],
                    "importance": d.importance,
                    "gap_type": "unlinked",
                })
        return gaps[:10]

    def _generate_suggestions(self, gaps: list, identity_topics: list) -> list:
        """基于空白和身份话题生成探索建议"""
        suggestions = []
        for g in gaps[:3]:
            suggestions.append(f"探索未连接记忆: {g['item_preview'][:30]}")
        for t in identity_topics[:2]:
            suggestions.append(f"深入身份话题: {t['preview'][:30]}")
        return suggestions


_instance: CuriosityEngine | None = None


def get_curiosity_engine(config: PanguConfig = None) -> CuriosityEngine:
    global _instance
    if _instance is None:
        _instance = CuriosityEngine(config)
    return _instance
