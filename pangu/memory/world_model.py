"""盘古预测性世界模型 — 基于记忆状态推演未来情景

移植自伏羲 world_model.py，适配盘古架构：
- 使用 PanguConfig + Drawer 替代 Fuxi 的 CognitiveEngine
- 基于记忆趋势和系统状态预测未来
- 纯大脑能力：只输出预测和预案，不执行实际动作
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime

from ..core.config import PanguConfig
from ..memory.attention import get_attention_system
from ..memory.working_memory import get_working_memory

logger = logging.getLogger("pangu.memory.world_model")

FORECAST_HORIZON = 3
MIN_PROBABILITY = 0.05
TOP_SCENARIOS = 10


@dataclass
class Scenario:
    id: str
    trigger: str
    description: str
    probability: float
    causal_path: list[str] = field(default_factory=list)
    severity: float = 0.5
    estimated_impact: str = ""
    suggested_actions: list[dict] = field(default_factory=list)
    matched: bool = False

    def hash_key(self) -> str:
        return hashlib.md5(self.trigger.encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass
class Plan:
    scenario_id: str
    description: str
    suggested_actions: list[dict] = field(default_factory=list)
    estimated_effect: str = ""


class PredictiveWorldModel:
    """预测性世界模型 — 基于记忆状态推演未来情景

    核心能力：
    1. 情景预测：基于工作记忆和注意力状态预测未来
    2. 预案生成：为高概率情景生成应对计划
    3. 事件匹配：将实际事件与预测匹配
    4. 贝叶斯学习：从匹配结果中学习权重
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._scenario_cache: dict[str, list[Scenario]] = {}
        self._prediction_history: list[dict] = []
        self._bayesian_weights: dict[str, float] = {}
        self._plan_cache: dict[str, Plan] = {}

    def forecast(self) -> list[Scenario]:
        """基于当前状态预测未来情景"""
        current_state = self._snapshot_current_state()
        state_hash = self._hash_state(current_state)

        if state_hash in self._scenario_cache:
            return self._scenario_cache[state_hash]

        scenarios: list[Scenario] = []
        scenarios.extend(self._forecast_wm_pressure(current_state))
        scenarios.extend(self._forecast_attention_shift(current_state))
        scenarios.extend(self._forecast_memory_trends(current_state))

        scenarios.sort(key=lambda s: s.probability * s.severity, reverse=True)

        self._scenario_cache[state_hash] = scenarios
        if len(self._scenario_cache) > 50:
            oldest = next(iter(self._scenario_cache))
            del self._scenario_cache[oldest]

        return scenarios[: TOP_SCENARIOS * 2]

    def generate_plan(self, scenario: Scenario) -> Plan:
        """为指定情景生成应对计划"""
        return Plan(
            scenario_id=scenario.id,
            description=f"如果检测到 [{scenario.trigger}]，建议:",
            suggested_actions=scenario.suggested_actions,
            estimated_effect=scenario.estimated_impact,
        )

    def match_event(self, event_type: str, event_data: dict) -> Scenario | None:
        """将实际事件与预测情景匹配"""
        for scenarios in list(self._scenario_cache.values()):
            for s in scenarios:
                if s.matched:
                    continue
                trigger_match = False

                if "failure" in event_type.lower() or "error" in event_type.lower():
                    source = event_data.get("source", "")
                    if source and source in s.trigger:
                        trigger_match = True

                if "memory" in event_type and ("overload" in str(event_data) or "pressure" in str(event_data)):
                    trigger_match = True

                if trigger_match:
                    s.matched = True
                    logger.info(f"预判命中: {s.trigger} → 预案已就绪 (prob={s.probability:.2f})")
                    self._learn_from_match(s)
                    return s

        return None

    def get_stats(self) -> dict:
        """获取世界模型统计"""
        return {
            "scenarios_cached": sum(len(v) for v in self._scenario_cache.values()),
            "cache_states": len(self._scenario_cache),
            "predictions_made": len(self._prediction_history),
            "plans_cached": len(self._plan_cache),
            "matched_count": sum(1 for h in self._prediction_history if h.get("outcome") == "matched"),
            "timestamp": datetime.now().isoformat(),
        }

    def _snapshot_current_state(self) -> dict:
        """快照当前系统状态"""
        state: dict = {
            "timestamp": datetime.now().isoformat(),
            "working_memory": {},
            "attention": {},
            "recent_events": [],
        }

        wm = get_working_memory()
        state["working_memory"] = {
            "slots_used": len(wm.slots),
            "capacity": wm.capacity,
            "high_urgency": sum(1 for s in wm.slots if s.urgency > 0.6),
            "high_activation": sum(1 for s in wm.slots if s.activation > 0.7),
        }

        attention = get_attention_system()
        state["attention"] = {
            "strategy": attention.active_strategy.value,
            "budget": attention.budget,
        }

        return state

    def _forecast_wm_pressure(self, state: dict) -> list[Scenario]:
        """预测工作记忆压力"""
        scenarios = []
        wm = state.get("working_memory", {})
        slots_used = wm.get("slots_used", 0)
        capacity = wm.get("capacity", 7)

        if slots_used >= capacity - 1:
            prob = min(0.85, 0.5 + (slots_used / capacity) * 0.3)
            scenarios.append(
                Scenario(
                    id="wm_pressure",
                    trigger="工作记忆接近满载",
                    description=f"工作记忆已用 {slots_used}/{capacity} 槽位，可能需要释放或巩固",
                    probability=round(prob, 3),
                    causal_path=["wm_near_capacity", "eviction_pressure", "potential_data_loss"],
                    severity=0.6,
                    estimated_impact="低激活项可能被驱逐",
                    suggested_actions=[
                        {"target": "consolidation", "type": "consolidate_low_activation"},
                    ],
                )
            )

        high_urgency = wm.get("high_urgency", 0)
        if high_urgency > 3:
            prob = min(0.85, 0.4 + high_urgency * 0.1)
            scenarios.append(
                Scenario(
                    id="wm_urgency_crowd",
                    trigger="多个高紧急度项积压",
                    description=f"工作记忆中有 {high_urgency} 个高紧急度项，处理压力大",
                    probability=round(prob, 3),
                    causal_path=["urgent_items_crowd", "attention_split", "reduced_effectiveness"],
                    severity=0.55,
                    estimated_impact="注意力分散，处理效率下降",
                    suggested_actions=[
                        {"target": "attention", "type": "switch_to_focus"},
                    ],
                )
            )

        return scenarios

    def _forecast_attention_shift(self, state: dict) -> list[Scenario]:
        """预测注意力策略偏移"""
        scenarios = []
        attention = state.get("attention", {})
        strategy = attention.get("strategy", "bottom_up")
        budget = attention.get("budget", 100)

        if strategy == "bottom_up" and budget < 30:
            scenarios.append(
                Scenario(
                    id="attn_depleted",
                    trigger="注意力预算不足",
                    description=f"注意力预算仅剩 {budget}，底部向上模式下信息处理受限",
                    probability=0.6,
                    causal_path=["budget_depleted", "info_overload", "missed_important"],
                    severity=0.5,
                    estimated_impact="可能错过重要信息",
                    suggested_actions=[
                        {"target": "attention", "type": "replenish_budget"},
                    ],
                )
            )

        if strategy in ("emotion", "urgency"):
            scenarios.append(
                Scenario(
                    id="attn_biased",
                    trigger=f"注意力偏向 {strategy} 驱动",
                    description=f"当前策略为 {strategy}，可能忽略中性但重要的信息",
                    probability=0.4,
                    causal_path=["biased_attention", "selective_processing", "blind_spots"],
                    severity=0.4,
                    estimated_impact="可能产生认知盲区",
                    suggested_actions=[
                        {"target": "attention", "type": "periodic_explore"},
                    ],
                )
            )

        return scenarios

    def _forecast_memory_trends(self, state: dict) -> list[Scenario]:
        """预测记忆增长趋势"""
        scenarios = []
        wm = state.get("working_memory", {})
        slots_used = wm.get("slots_used", 0)

        if slots_used == 0:
            scenarios.append(
                Scenario(
                    id="wm_empty",
                    trigger="工作记忆为空",
                    description="工作记忆无焦点项，系统可能处于空闲或刚启动状态",
                    probability=0.7,
                    causal_path=["wm_empty", "no_focus", "idle_state"],
                    severity=0.3,
                    estimated_impact="系统等待新输入",
                    suggested_actions=[
                        {"target": "ingestion", "type": "check_new_memories"},
                    ],
                )
            )

        return scenarios

    def _learn_from_match(self, matched: Scenario):
        """从匹配结果中学习"""
        path_key = "→".join(matched.causal_path)
        current = self._bayesian_weights.get(path_key, 0.5)
        self._bayesian_weights[path_key] = min(1.0, current + 0.1)

        self._prediction_history.append(
            {
                "ts": datetime.now().isoformat(),
                "predicted": matched.trigger,
                "probability": matched.probability,
                "outcome": "matched",
            }
        )

    def _hash_state(self, state: dict) -> str:
        key_parts = [
            str(state.get("working_memory", {}).get("slots_used", 0)),
            str(state.get("working_memory", {}).get("high_urgency", 0)),
            state.get("attention", {}).get("strategy", ""),
            str(state.get("attention", {}).get("budget", 0)),
        ]
        return hashlib.md5("|".join(key_parts).encode(), usedforsecurity=False).hexdigest()[:16]


_world_model: PredictiveWorldModel | None = None


def get_world_model(config=None) -> PredictiveWorldModel:
    """获取全局世界模型实例"""
    global _world_model
    if _world_model is None:
        _world_model = PredictiveWorldModel(config)
    return _world_model
