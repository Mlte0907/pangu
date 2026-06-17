"""盘古深度情绪智能 — 情绪轨迹追踪 / 混合情绪解耦 / 个性化情绪模型

核心功能：
1. 情绪轨迹追踪 — 追踪情绪随时间的变化趋势（速度/加速度/趋势）
2. 混合情绪解耦 — 识别复杂情绪状态中的多个成分
3. 个性化情绪学习 — 基于用户特征建立个性化情绪基线
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.deep_emotion")


@dataclass
class EmotionTrajectory:
    trend: str = "stable"
    velocity: float = 0.0
    acceleration: float = 0.0
    data_points: list = field(default_factory=list)


@dataclass
class MixedEmotion:
    drawer_id: str
    preview: str
    components: list[str]
    primary: str


@dataclass
class PersonalModel:
    baseline_valence: float = 0.0
    typical_arousal: float = 0.5
    emotion_patterns: list = field(default_factory=list)
    personalization_score: float = 0.0


class DeepEmotionEngine:
    """深度情绪智能 — 情绪轨迹追踪、混合情绪解耦、个性化情绪学习"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def analyze_trajectory(self, drawers: list[Drawer]) -> dict:
        """情绪轨迹追踪 — 追踪情绪随时间的变化趋势"""
        emotion_points = []
        cutoff = datetime.now() - timedelta(hours=24)

        for d in drawers:
            if d.emotional_weight == 0:
                continue
            try:
                created = datetime.fromisoformat(d.created_at)
                if created < cutoff:
                    continue
                emotion_points.append({"ts": d.created_at, "valence": d.emotional_weight})
            except (ValueError, TypeError):
                continue

        emotion_points.sort(key=lambda p: p["ts"])
        emotion_points = emotion_points[:20]

        trajectory = EmotionTrajectory(data_points=[{"ts": p["ts"], "valence": p["valence"]} for p in emotion_points[-5:]])

        if len(emotion_points) >= 2:
            velocities = []
            for i in range(1, len(emotion_points)):
                dv = emotion_points[i]["valence"] - emotion_points[i - 1]["valence"]
                velocities.append(dv)

            avg_velocity = sum(velocities) / len(velocities) if velocities else 0.0
            accelerations = [velocities[i] - velocities[i - 1] for i in range(1, len(velocities))]
            avg_acceleration = sum(accelerations) / len(accelerations) if accelerations else 0.0

            if avg_velocity > 0.1:
                trend = "improving"
            elif avg_velocity < -0.1:
                trend = "declining"
            else:
                trend = "stable"

            trajectory = EmotionTrajectory(
                trend=trend,
                velocity=round(avg_velocity, 4),
                acceleration=round(avg_acceleration, 4),
                data_points=[{"ts": p["ts"], "valence": p["valence"]} for p in emotion_points[-5:]],
            )

        return {
            "trend": trajectory.trend,
            "velocity": trajectory.velocity,
            "acceleration": trajectory.acceleration,
            "data_points": trajectory.data_points,
        }

    def decompose_emotions(self, drawers: list[Drawer]) -> list[dict]:
        """混合情绪解耦 — 识别复杂情绪状态中的多个成分"""
        decomposed = []
        cutoff = datetime.now() - timedelta(hours=6)

        for d in drawers:
            if d.emotional_weight == 0:
                continue
            try:
                created = datetime.fromisoformat(d.created_at)
                if created < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

            components = []
            valence = d.emotional_weight

            if valence > 0.2:
                components.append("positive")
            elif valence < -0.2:
                components.append("negative")

            tags_lower = [t.lower() for t in d.tags]
            if "frustrated" in tags_lower or "沮丧" in tags_lower:
                components.append("frustrated")
            if "excited" in tags_lower or "兴奋" in tags_lower:
                components.append("high_arousal")
            if "calm" in tags_lower or "平静" in tags_lower:
                components.append("low_arousal")
            if "interested" in tags_lower or "兴趣" in tags_lower:
                components.append("interested")

            if len(components) >= 2:
                decomposed.append(MixedEmotion(
                    drawer_id=d.id[:8],
                    preview=d.content[:50],
                    components=components,
                    primary=components[0],
                ).__dict__)

        return decomposed

    def get_personal_model(self, drawers: list[Drawer]) -> dict:
        """个性化情绪学习 — 基于用户特征建立个性化情绪基线"""
        model = PersonalModel()

        emotion_drawers = [d for d in drawers if d.emotional_weight != 0]
        cutoff_7d = datetime.now() - timedelta(days=7)

        recent = []
        for d in emotion_drawers:
            try:
                created = datetime.fromisoformat(d.created_at)
                if created >= cutoff_7d:
                    recent.append(d)
            except (ValueError, TypeError):
                continue

        if len(recent) > 5:
            avg_valence = sum(d.emotional_weight for d in recent) / len(recent)
            model.baseline_valence = round(avg_valence, 4)
            model.typical_arousal = 0.5
            model.personalization_score = min(1.0, len(recent) / 50.0)

        pattern_counts: dict[float, int] = {}
        for d in recent:
            rounded = round(d.emotional_weight, 1)
            pattern_counts[rounded] = pattern_counts.get(rounded, 0) + 1

        sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        model.emotion_patterns = [{"valence": v, "frequency": c} for v, c in sorted_patterns]

        return {
            "baseline_valence": model.baseline_valence,
            "typical_arousal": model.typical_arousal,
            "emotion_patterns": model.emotion_patterns,
            "personalization_score": model.personalization_score,
        }

    def get_stats(self, drawers: list[Drawer]) -> dict:
        """获取情绪统计"""
        emotion_count = sum(1 for d in drawers if d.emotional_weight != 0)
        positive = sum(1 for d in drawers if d.emotional_weight > 0.2)
        negative = sum(1 for d in drawers if d.emotional_weight < -0.2)
        return {
            "total_memories": len(drawers),
            "emotion_tagged": emotion_count,
            "positive": positive,
            "negative": negative,
            "neutral": emotion_count - positive - negative,
        }


_engine: DeepEmotionEngine | None = None


def get_deep_emotion_engine(config: PanguConfig = None) -> DeepEmotionEngine:
    global _engine
    if _engine is None:
        _engine = DeepEmotionEngine(config)
    return _engine
