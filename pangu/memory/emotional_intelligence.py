"""盘古情感智能 — 理解用户情绪，调整记忆优先级

核心功能：
1. 情感识别：从文本中识别用户情绪
2. 情绪分类：正面/负面/中性
3. 优先级调整：根据情绪调整记忆重要性
4. 情感记忆：记录用户的情感状态
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.emotional_intelligence")


class EmotionType(str, Enum):
    """情绪类型"""
    POSITIVE = "positive"    # 正面
    NEGATIVE = "negative"    # 负面
    NEUTRAL = "neutral"      # 中性
    EXCITED = "excited"      # 兴奋
    FRUSTRATED = "frustrated"  # 沮丧


@dataclass
class EmotionResult:
    """情感分析结果"""
    emotion: EmotionType
    intensity: float  # 0.0-1.0
    keywords: list[str]
    confidence: float


class EmotionalIntelligence:
    """情感智能 — 理解用户情绪"""

    # 情感关键词
    EMOTION_KEYWORDS = {
        EmotionType.POSITIVE: {
            "keywords": ["好的", "不错", "满意", "成功", "完成", "优秀", "感谢", "谢谢", "赞"],
            "weight": 0.8,
        },
        EmotionType.NEGATIVE: {
            "keywords": ["失败", "错误", "问题", "困难", "麻烦", "不好", "抱歉", "对不起"],
            "weight": 0.8,
        },
        EmotionType.EXCITED: {
            "keywords": ["太棒了", "厉害", "牛", "优秀", "完美", "惊喜", "哇"],
            "weight": 0.9,
        },
        EmotionType.FRUSTRATED: {
            "keywords": ["烦", "累", "难", "不想", "算了", "随便"],
            "weight": 0.7,
        },
    }

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._emotion_history: list[dict] = []

    def analyze_emotion(self, text: str) -> EmotionResult:
        """分析文本情感"""
        text_lower = text.lower()
        scores = {}

        for emotion, config in self.EMOTION_KEYWORDS.items():
            score = 0.0
            matched_keywords = []
            for kw in config["keywords"]:
                if kw in text_lower:
                    score += config["weight"]
                    matched_keywords.append(kw)
            if score > 0:
                scores[emotion] = (score, matched_keywords)

        if not scores:
            return EmotionResult(
                emotion=EmotionType.NEUTRAL,
                intensity=0.0,
                keywords=[],
                confidence=0.5,
            )

        # 选择最高分的情绪
        best_emotion, (best_score, best_keywords) = max(scores.items(), key=lambda x: x[1][0])
        intensity = min(best_score, 1.0)

        return EmotionResult(
            emotion=best_emotion,
            intensity=intensity,
            keywords=best_keywords,
            confidence=min(intensity, 0.9),
        )

    def adjust_importance(self, drawer: Drawer, emotion: EmotionResult) -> float:
        """根据情感调整记忆重要性"""
        base_importance = drawer.importance

        # 正面情绪：提升重要性
        if emotion.emotion in (EmotionType.POSITIVE, EmotionType.EXCITED):
            boost = 1.0 + emotion.intensity * 0.2
            return min(5.0, base_importance * boost)

        # 负面情绪：降低重要性
        elif emotion.emotion in (EmotionType.NEGATIVE, EmotionType.FRUSTRATED):
            boost = 1.0 - emotion.intensity * 0.1
            return max(0.5, base_importance * boost)

        # 中性：保持不变
        return base_importance

    def get_emotion_stats(self) -> dict:
        """获取情感统计"""
        if not self._emotion_history:
            return {"total": 0}

        emotion_counts = {}
        for entry in self._emotion_history:
            emotion = entry.get("emotion", "neutral")
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

        return {
            "total": len(self._emotion_history),
            "distribution": emotion_counts,
        }

    def record_emotion(self, text: str, emotion: EmotionResult) -> None:
        """记录情感"""
        self._emotion_history.append({
            "text": text[:50],
            "emotion": emotion.emotion.value,
            "intensity": emotion.intensity,
            "timestamp": datetime.now().isoformat(),
        })
        # 限制历史记录大小
        if len(self._emotion_history) > 100:
            self._emotion_history = self._emotion_history[-100:]


# 全局单例
_emotional_intelligence: EmotionalIntelligence | None = None


def get_emotional_intelligence(config: PanguConfig = None) -> EmotionalIntelligence:
    """获取全局情感智能实例"""
    global _emotional_intelligence
    if _emotional_intelligence is None:
        _emotional_intelligence = EmotionalIntelligence(config)
    return _emotional_intelligence
