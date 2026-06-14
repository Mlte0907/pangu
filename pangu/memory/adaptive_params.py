"""盘古自适应参数系统 — 动态调整记忆策略参数

从伏羲移植：根据系统运行状态，自动调整记忆衰减率、搜索权重、
相似度阈值等关键参数，使记忆系统持续优化。

纯大脑能力：只做参数建议和调整，不执行具体任务。
"""

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.adaptive_params")


@dataclass
class AdaptiveParams:
    """可自适应调整的记忆策略参数"""

    # 衰减参数
    decay_base: float = 0.95       # 基础衰减率 (0.9-0.99)
    decay_floor: float = 0.15      # 衰减底限 (0.05-0.3)
    touch_boost_short: float = 1.35  # 短期增益 (1.1-1.5)
    touch_boost_long: float = 1.06   # 长期保护 (1.0-1.2)

    # 搜索参数
    vector_weight: float = 0.6        # 向量搜索权重 (0.3-0.8)
    similarity_threshold: float = 0.25  # 向量相似度阈值 (0.15-0.4)

    # 记忆参数
    consolidation_interval: float = 24.0  # 巩固间隔（小时）
    compression_threshold: int = 100      # 压缩触发阈值
    min_importance: float = 0.5           # 最低重要性阈值

    # 去重参数
    dedup_similarity: float = 0.85  # 去重相似度阈值 (0.7-0.95)

    # 元数据
    last_updated: str = ""
    update_reason: str = ""
    confidence: float = 0.5  # 参数置信度 (0-1)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# 参数调整范围约束
PARAM_BOUNDS = {
    "decay_base": (0.9, 0.99),
    "decay_floor": (0.05, 0.3),
    "touch_boost_short": (1.1, 1.5),
    "touch_boost_long": (1.0, 1.2),
    "vector_weight": (0.3, 0.8),
    "similarity_threshold": (0.15, 0.4),
    "consolidation_interval": (1.0, 72.0),
    "compression_threshold": (20, 500),
    "min_importance": (0.1, 0.9),
    "dedup_similarity": (0.7, 0.95),
}


def clamp_params(params: AdaptiveParams) -> AdaptiveParams:
    """将参数约束到合法范围内"""
    for attr, (lo, hi) in PARAM_BOUNDS.items():
        val = getattr(params, attr)
        setattr(params, attr, max(lo, min(hi, val)))
    return params


class AdaptiveParamEngine:
    """自适应参数引擎 — 根据系统状态动态调整参数

    调整信号：
    1. 记忆增长过快 → 提高衰减率、降低压缩阈值
    2. 搜索精度低 → 提高向量权重、降低相似度阈值
    3. 重复记忆多 → 提高去重阈值
    4. 遗忘过多 → 降低衰减率、提高巩固频率
    """

    def __init__(self, config=None):
        self.config = config
        self.params = AdaptiveParams()
        self._history: list[dict] = []
        self._signal_buffer: list[dict] = []

    def feed_signal(self, signal_type: str, value: float, context: str = "") -> None:
        """输入调整信号"""
        self._signal_buffer.append({
            "type": signal_type,
            "value": value,
            "context": context,
            "ts": datetime.now().isoformat(),
        })
        if len(self._signal_buffer) > 100:
            self._signal_buffer = self._signal_buffer[-100:]

    def evaluate(self, stats: dict) -> AdaptiveParams:
        """根据系统统计评估并调整参数

        Args:
            stats: 系统统计信息，包含：
                - total_memories: 记忆总数
                - growth_rate: 增长率（条/天）
                - duplicate_rate: 重复率
                - forget_rate: 遗忘率
                - avg_search_score: 平均搜索得分
        """
        new_params = AdaptiveParams(
            decay_base=self.params.decay_base,
            decay_floor=self.params.decay_floor,
            touch_boost_short=self.params.touch_boost_short,
            touch_boost_long=self.params.touch_boost_long,
            vector_weight=self.params.vector_weight,
            similarity_threshold=self.params.similarity_threshold,
            consolidation_interval=self.params.consolidation_interval,
            compression_threshold=self.params.compression_threshold,
            min_importance=self.params.min_importance,
            dedup_similarity=self.params.dedup_similarity,
        )
        reasons = []

        total = stats.get("total_memories", 0)
        growth_rate = stats.get("growth_rate", 0)
        duplicate_rate = stats.get("duplicate_rate", 0)
        forget_rate = stats.get("forget_rate", 0)
        avg_search_score = stats.get("avg_search_score", 0.5)

        # 信号1: 记忆增长过快 → 提高衰减、降低压缩阈值
        if growth_rate > 50:
            new_params.decay_base = min(0.98, self.params.decay_base + 0.02)
            new_params.compression_threshold = max(30, self.params.compression_threshold - 20)
            reasons.append(f"high_growth_rate({growth_rate})")

        # 信号2: 搜索精度低 → 提高向量权重
        if avg_search_score < 0.3:
            new_params.vector_weight = min(0.8, self.params.vector_weight + 0.1)
            new_params.similarity_threshold = max(0.15, self.params.similarity_threshold - 0.05)
            reasons.append(f"low_search_score({avg_search_score:.2f})")

        # 信号3: 重复记忆多 → 提高去重阈值
        if duplicate_rate > 0.1:
            new_params.dedup_similarity = max(0.75, self.params.dedup_similarity - 0.05)
            reasons.append(f"high_duplicate_rate({duplicate_rate:.2f})")

        # 信号4: 遗忘过多 → 降低衰减率
        if forget_rate > 0.2:
            new_params.decay_base = max(0.9, self.params.decay_base - 0.03)
            new_params.consolidation_interval = max(1.0, self.params.consolidation_interval - 4.0)
            reasons.append(f"high_forget_rate({forget_rate:.2f})")

        # 信号5: 记忆太少 → 放宽阈值
        if total < 20:
            new_params.min_importance = max(0.1, self.params.min_importance - 0.1)
            new_params.compression_threshold = min(200, self.params.compression_threshold + 50)
            reasons.append(f"low_total({total})")

        # 信号6: 记忆太多 → 收紧阈值
        if total > 1000:
            new_params.min_importance = min(0.8, self.params.min_importance + 0.05)
            new_params.compression_threshold = max(50, self.params.compression_threshold - 30)
            reasons.append(f"high_total({total})")

        new_params = clamp_params(new_params)
        new_params.last_updated = datetime.now().isoformat()
        new_params.update_reason = "; ".join(reasons) if reasons else "no_change"
        new_params.confidence = min(0.9, 0.5 + len(reasons) * 0.1)

        # 记录历史
        self._history.append({
            "old": self.params.to_dict(),
            "new": new_params.to_dict(),
            "reasons": reasons,
            "stats": stats,
            "ts": new_params.last_updated,
        })
        if len(self._history) > 50:
            self._history = self._history[-50:]

        if reasons:
            self.params = new_params
            logger.info(f"Params adjusted: {reasons}")

        return new_params

    def get_params(self) -> AdaptiveParams:
        """获取当前参数"""
        return self.params

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取调整历史"""
        return self._history[-limit:]

    def reset(self) -> AdaptiveParams:
        """重置为默认参数"""
        self.params = AdaptiveParams()
        return self.params


_adaptive_engine: AdaptiveParamEngine | None = None


def get_adaptive_engine(config=None) -> AdaptiveParamEngine:
    """获取自适应参数引擎单例"""
    global _adaptive_engine
    if _adaptive_engine is None:
        _adaptive_engine = AdaptiveParamEngine(config)
    return _adaptive_engine
