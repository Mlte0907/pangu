"""盘古注意力系统 — 5策略 + 预算分配 + A/B测试

从伏羲移植：模拟人类注意力机制的多策略系统。
- BOTTOM_UP: 自底向上，由刺激驱动
- FOCUS: 聚焦模式，专注当前任务
- EXPLORE: 探索模式，寻找新信息
- EMOTION_DRIVEN: 情感驱动，由情感信号引导
- URGENCY_DRIVEN: 紧急驱动，由紧迫度引导

纯大脑能力：只做注意力分配，不执行任务。
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("pangu.memory.attention")


class AttentionStrategy(Enum):
    BOTTOM_UP = "bottom_up"
    FOCUS = "focus"
    EXPLORE = "explore"
    EMOTION_DRIVEN = "emotion"
    URGENCY_DRIVEN = "urgency"


@dataclass
class ABTestConfig:
    strategy_a: AttentionStrategy
    strategy_b: AttentionStrategy
    start_time: float
    duration_days: float = 7
    sample_size: int = 0
    metrics_a: list[dict] = field(default_factory=list)
    metrics_b: list[dict] = field(default_factory=list)


class AttentionSystem:
    """注意力系统 — 多策略注意力分配

    核心特性：
    1. 5种注意力策略，自动切换
    2. 注意力预算分配（100单位）
    3. FOCUS 模式超时自动恢复
    4. A/B 测试框架
    5. 策略效果统计
    """

    FOCUS_TIMEOUT = 60  # FOCUS 模式超时（秒）

    def __init__(self):
        self._active_strategy = AttentionStrategy.BOTTOM_UP
        self._budget = 100
        self._last_switch = time.time()
        self._strategy_counts: dict[AttentionStrategy, int] = dict.fromkeys(AttentionStrategy, 0)
        self._lock = threading.Lock()
        self._ab_test: ABTestConfig | None = None
        self._ab_records: list[dict] = []
        self._metadata: dict = {}

    @property
    def active_strategy(self) -> AttentionStrategy:
        with self._lock:
            if self._active_strategy == AttentionStrategy.FOCUS:
                if time.time() - self._last_switch > self.FOCUS_TIMEOUT:
                    self._active_strategy = AttentionStrategy.BOTTOM_UP
                    logger.debug("FOCUS timeout, reverted to BOTTOM_UP")
        return self._active_strategy

    @property
    def budget(self) -> int:
        return self._budget

    def allocate(self, amount: int) -> bool:
        """分配注意力预算"""
        with self._lock:
            if self._budget >= amount:
                self._budget -= amount
                return True
            return False

    def replenish(self, amount: int = 10):
        """恢复注意力预算"""
        with self._lock:
            self._budget = min(100, self._budget + amount)

    def switch(self, strategy: AttentionStrategy, reason: str = "") -> tuple[AttentionStrategy, AttentionStrategy]:
        """切换注意力策略"""
        with self._lock:
            if self._ab_test is not None:
                if strategy not in (self._ab_test.strategy_a, self._ab_test.strategy_b):
                    return self._active_strategy, self._active_strategy
            old = self._active_strategy
            self._active_strategy = strategy
            self._strategy_counts[strategy] += 1
            self._last_switch = time.time()
            logger.debug(f"Attention: {old.value} -> {strategy.value} ({reason})")
        return old, strategy

    def evaluate(self, emotional_valence: float, urgency: float, novelty: float) -> AttentionStrategy:
        """根据信号评估应采用哪种注意力策略

        Args:
            emotional_valence: 情感值 (-1.0 ~ 1.0)
            urgency: 紧迫度 (0.0 ~ 1.0)
            novelty: 新颖度 (0.0 ~ 1.0)
        """
        if self._ab_test is not None:
            chosen = random.choice([self._ab_test.strategy_a, self._ab_test.strategy_b])
            self._record_ab_metric(chosen)
            return chosen

        if urgency > 0.7:
            return AttentionStrategy.URGENCY_DRIVEN
        if abs(emotional_valence) > 0.6:
            return AttentionStrategy.EMOTION_DRIVEN
        if novelty > 0.5:
            return AttentionStrategy.EXPLORE
        return AttentionStrategy.BOTTOM_UP

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "active_strategy": self._active_strategy.value,
                "budget": self._budget,
                "counts": {s.value: c for s, c in self._strategy_counts.items()},
                "ab_test_active": self._ab_test is not None,
            }

    def start_ab_test(self, strategy_a: AttentionStrategy, strategy_b: AttentionStrategy, duration_days: float = 7):
        """启动 A/B 测试"""
        with self._lock:
            self._ab_test = ABTestConfig(
                strategy_a=strategy_a,
                strategy_b=strategy_b,
                start_time=time.time(),
                duration_days=duration_days,
            )
            self._ab_records = []
        logger.info(f"A/B test started: {strategy_a.value} vs {strategy_b.value}")

    def stop_ab_test(self) -> dict:
        """停止 A/B 测试并返回结果"""
        with self._lock:
            if self._ab_test is None:
                return {"error": "no active A/B test"}
            result = self._evaluate_ab_test()
            self._ab_test = None
            self._ab_records = []
        return result

    def _evaluate_ab_test(self) -> dict:
        """评估 A/B 测试结果"""
        if self._ab_test is None:
            return {"error": "no active A/B test"}

        records_a = [r for r in self._ab_records if r["strategy"] == self._ab_test.strategy_a.value]
        records_b = [r for r in self._ab_records if r["strategy"] == self._ab_test.strategy_b.value]

        def _compute_stats(records: list) -> dict:
            if not records:
                return {"count": 0, "avg_latency": 0.0, "avg_quality": 0.0}
            latencies = [r.get("latency", 0.0) for r in records]
            qualities = [r.get("quality", 0.0) for r in records]
            return {
                "count": len(records),
                "avg_latency": sum(latencies) / len(latencies),
                "avg_quality": sum(qualities) / len(qualities),
            }

        stats_a = _compute_stats(records_a)
        stats_b = _compute_stats(records_b)

        total = stats_a["count"] + stats_b["count"]
        if total < 30:
            return {
                "winner": None,
                "confidence": 0.0,
                "recommendation": "insufficient data",
                "strategy_a": stats_a,
                "strategy_b": stats_b,
            }

        winner = (
            self._ab_test.strategy_a.value
            if stats_a["avg_quality"] >= stats_b["avg_quality"]
            else self._ab_test.strategy_b.value
        )
        diff = abs(stats_a["avg_quality"] - stats_b["avg_quality"])
        pooled = max((stats_a["avg_quality"] + stats_b["avg_quality"]) / 2, 0.01)
        confidence = min(diff / pooled, 1.0)

        return {
            "winner": winner,
            "confidence": round(confidence, 3),
            "recommendation": f"switch to {winner}" if confidence >= 0.95 else "no significant difference",
            "strategy_a": stats_a,
            "strategy_b": stats_b,
        }

    def _record_ab_metric(self, strategy: AttentionStrategy):
        record = {
            "strategy": strategy.value,
            "latency": time.time() - self._last_switch,
            "quality": 0.0,
            "timestamp": time.time(),
        }
        self._ab_records.append(record)
        if self._ab_test:
            if strategy == self._ab_test.strategy_a:
                self._ab_test.metrics_a.append(record)
                self._ab_test.sample_size += 1
            else:
                self._ab_test.metrics_b.append(record)
                self._ab_test.sample_size += 1

    def record_feedback(self, strategy: AttentionStrategy, quality: float = 0.0):
        """记录策略反馈"""
        with self._lock:
            if self._ab_test is None:
                return
            for r in reversed(self._ab_records):
                if r["strategy"] == strategy.value and r.get("quality", 0.0) == 0.0:
                    r["quality"] = quality
                    break


_attention_system: AttentionSystem | None = None


def get_attention_system() -> AttentionSystem:
    """获取注意力系统单例"""
    global _attention_system
    if _attention_system is None:
        _attention_system = AttentionSystem()
    return _attention_system
