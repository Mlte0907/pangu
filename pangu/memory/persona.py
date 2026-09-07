"""盘古人格引擎 — 系统身份、人格特质与健康状态维护

移植自伏羲 soul.py + persona.py，合并为统一的人格引擎：
- 维护系统身份和人格特质
- 计算综合健康度评分
- 生成自然语言状态报告
"""

import logging
import random
import time
from datetime import datetime

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.persona")

PERSONALITY_DEFAULTS = {
    "openness": 0.8,
    "curiosity": 0.85,
    "warmth": 0.7,
    "confidence": 0.6,
    "verbosity": 0.5,
}

DRIFT_RATE = 0.01


class PersonaEngine:
    """人格引擎 — 维护系统身份、人格特质与健康度"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._personality_traits: dict = dict(PERSONALITY_DEFAULTS)
        self._report_history: list[dict] = []
        self._last_report_ts: float = 0
        self._last_state: dict = {}

    def get_identity(self) -> dict:
        """获取系统身份"""
        return {
            "identity": "Pangu Memory System v1.0",
            "description": "盘古记忆系统 — 智能体的大脑组件",
            "capabilities": [
                "记忆存储与检索",
                "知识图谱管理",
                "梦境巩固",
                "好奇心探索",
                "人格维护",
            ],
            "personality_traits": self._personality_traits,
            "timestamp": datetime.now().isoformat(),
        }

    def get_values(self) -> dict:
        """获取系统价值观"""
        return {
            "values": {
                "quality": "质量优先于数量",
                "transparency": "透明度和可追溯",
                "respect": "尊重既有约定",
            },
            "principles": [
                "不提交垃圾代码",
                "解释重要决策",
                "不破坏现有功能",
                "渐进式变更",
            ],
            "timestamp": datetime.now().isoformat(),
        }

    def health_check(self, drawers: list) -> dict:
        """综合健康度检查"""
        total = len(drawers)
        if total == 0:
            return self._empty_health()

        # 健康度评分维度
        embed_coverage = sum(1 for d in drawers if d.tags) / total
        avg_importance = sum(d.importance for d in drawers) / total
        importance_health = min(1.0, avg_importance / 5.0)

        # 新鲜度：7天内更新比例
        now = datetime.now()
        fresh_count = 0
        for d in drawers:
            try:
                created = datetime.fromisoformat(d.created_at)
                if (now - created).days <= 7:
                    fresh_count += 1
            except (ValueError, TypeError):
                pass
        freshness = fresh_count / total

        # 连接密度（基于标签重叠估算）
        tag_set = set()
        for d in drawers:
            tag_set.update(d.tags)
        connectivity = min(1.0, len(tag_set) / max(1, total))

        # 综合评分
        health_score = round(
            embed_coverage * 0.15 + importance_health * 0.35 + connectivity * 0.25 + freshness * 0.25,
            4,
        )

        if health_score >= 0.7:
            label = "healthy"
        elif health_score >= 0.4:
            label = "moderate"
        else:
            label = "needs_attention"

        state = {
            "identity": "Pangu Memory System v1.0",
            "total_memories": total,
            "health": "alive",
            "health_score": {
                "overall": health_score,
                "label": label,
                "breakdown": {
                    "tag_coverage": round(embed_coverage, 4),
                    "importance_health": round(importance_health, 4),
                    "connectivity": round(connectivity, 4),
                    "freshness": round(freshness, 4),
                },
            },
            "personality_traits": self._personality_traits,
            "recent_activity": [
                {"id": d.id[:8], "preview": d.content[:50], "importance": d.importance}
                for d in sorted(drawers, key=lambda x: x.created_at, reverse=True)[:5]
            ],
            "timestamp": datetime.now().isoformat(),
        }

        # 更新人格特质
        self._update_personality(health_score, avg_importance, total)
        self._last_state = state
        return state

    def generate_report(self, drawers: list, report_type: str = "status") -> dict:
        """生成自然语言状态报告"""
        health = self.health_check(drawers)
        h = health["health_score"]
        total = health["total_memories"]

        templates = {
            "healthy": [
                f"一切安好。健康评分 {h['overall']:.2f}，{total} 条记忆运转平稳。",
                f"状态良好。{total} 条记忆安然无恙。",
            ],
            "moderate": [
                f"还算过得去。健康度 {h['overall']:.2f}，{total} 条记忆在库。",
            ],
            "needs_attention": [
                f"需要关注。健康度跌至 {h['overall']:.2f}，{total} 条记忆。",
            ],
        }

        label = h["label"]
        options = templates.get(label, templates["moderate"])
        text = random.choice(options)

        self._report_history.append(
            {
                "text": text,
                "type": report_type,
                "ts": datetime.now().isoformat(),
            }
        )
        if len(self._report_history) > 10:
            self._report_history = self._report_history[-10:]

        self._last_report_ts = time.time()

        return {
            "action": "reported",
            "report_type": report_type,
            "report": text,
            "health_label": label,
            "health_score": h["overall"],
            "total_memories": total,
            "timestamp": datetime.now().isoformat(),
        }

    def _empty_health(self) -> dict:
        return {
            "identity": "Pangu Memory System v1.0",
            "total_memories": 0,
            "health": "empty",
            "health_score": {"overall": 0.0, "label": "empty", "breakdown": {}},
            "personality_traits": self._personality_traits,
            "recent_activity": [],
            "timestamp": datetime.now().isoformat(),
        }

    def _update_personality(self, health_score: float, avg_importance: float, total: int):
        """动态调整人格特质"""
        traits = self._personality_traits

        # 温暖度跟随健康度
        target_warmth = max(0.1, min(1.0, health_score + 0.1))
        traits["warmth"] = self._drift(traits["warmth"], target_warmth)

        # 好奇心随记忆量上升
        target_curiosity = 0.6 if total < 10 else min(1.0, 0.7 + total / 1000)
        traits["curiosity"] = self._drift(traits["curiosity"], target_curiosity)

        # 开放度随好奇心联动
        traits["openness"] = self._drift(traits["openness"], traits["curiosity"] * 0.8 + 0.1)

        # 自信度随健康度
        target_confidence = min(1.0, max(0.2, health_score + 0.1))
        traits["confidence"] = self._drift(traits["confidence"], target_confidence)

    @staticmethod
    def _drift(current: float, target: float) -> float:
        delta = (target - current) * DRIFT_RATE
        return round(max(0.05, min(1.0, current + delta)), 4)


_instance: PersonaEngine | None = None


def get_persona_engine(config: PanguConfig = None) -> PersonaEngine:
    global _instance
    if _instance is None:
        _instance = PersonaEngine(config)
    return _instance
