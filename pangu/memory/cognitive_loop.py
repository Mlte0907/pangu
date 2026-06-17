"""盘古认知循环 — 编排记忆系统的思考周期

移植自伏羲 cognitive_loop.py，适配盘古架构：
- 使用 PanguConfig + Drawer 替代 Fuxi 的 CognitiveEngine
- 调用 pangu 的 working_memory 和 attention 系统
- 纯记忆层编排，不执行实际任务
"""

import logging
import time
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from ..memory.working_memory import get_working_memory
from ..memory.attention import AttentionStrategy, get_attention_system

logger = logging.getLogger("pangu.memory.cognitive_loop")

PHASE_TIMEOUTS = {
    "observe": 10,
    "think": 30,
    "evaluate": 60,
    "act": 30,
    "consolidate": 15,
}


class CognitiveLoop:
    """认知循环 — 编排观察→思考→评估→行动的记忆周期"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._cycle_count = 0
        self._phase_timestamps: dict[str, float] = {}
        self._last_result: dict = {}
        self._iteration_counter: dict[str, int] = {}

    def run_cycle(self) -> dict:
        """运行一次完整的认知循环（observe→think→evaluate→act）"""
        t_start = time.time()
        wm = get_working_memory()
        attention = get_attention_system()

        wm.decay_tick(dt=10.0)
        attention.replenish(20)

        self._adjust_attention_strategy(wm, attention)

        phase_results: dict[str, Any] = {}

        phase_results["observe"] = self._observe(wm, attention)
        phase_results["think"] = self._think(wm, attention)
        phase_results["evaluate"] = self._evaluate(phase_results)
        phase_results["act"] = self._act(phase_results)

        self._cycle_count += 1
        total_time_ms = round((time.time() - t_start) * 1000)

        state = {
            "cycle_count": self._cycle_count,
            "phases": phase_results,
            "attention": attention.stats,
            "working_memory": wm.stats,
            "wm_focus": [
                {"id": s.id, "urgency": s.urgency, "activation": round(s.activation, 2)}
                for s in wm.slots if s.activation > 0.3
            ][:3],
            "total_time_ms": total_time_ms,
            "timestamp": datetime.now().isoformat(),
        }
        self._last_result = state
        return state

    def get_stats(self) -> dict:
        """获取认知循环统计"""
        return {
            "cycle_count": self._cycle_count,
            "last_result": {
                "phases": list(self._last_result.get("phases", {}).keys()),
                "total_time_ms": self._last_result.get("total_time_ms", 0),
            },
            "timestamp": datetime.now().isoformat(),
        }

    def _observe(self, wm, attention) -> dict:
        """观察阶段：扫描工作记忆和注意力状态"""
        focus_items = [
            {"id": s.id, "content": s.content[:80], "activation": round(s.activation, 2), "urgency": round(s.urgency, 2)}
            for s in wm.slots if s.activation > 0.3
        ][:5]
        return {
            "wm_slots_used": len(wm.slots),
            "wm_capacity": wm.capacity,
            "attention_strategy": attention.active_strategy.value,
            "attention_budget": attention.budget,
            "focus_items": focus_items,
        }

    def _think(self, wm, attention) -> dict:
        """思考阶段：分析工作记忆中的焦点项，提取洞察"""
        insights = []
        high_urgency = [s for s in wm.slots if s.urgency > 0.6]
        high_activation = [s for s in wm.slots if s.activation > 0.7]

        if high_urgency:
            insights.append(f"发现 {len(high_urgency)} 个高紧急度项")
        if high_activation:
            insights.append(f"发现 {len(high_activation)} 个高激活度项")

        if attention.active_strategy == AttentionStrategy.FOCUS:
            insights.append("当前处于聚焦模式，信息处理效率高")
        elif attention.active_strategy == AttentionStrategy.EXPLORE:
            insights.append("当前处于探索模式，适合发现新关联")

        return {
            "insights": insights,
            "high_urgency_count": len(high_urgency),
            "high_activation_count": len(high_activation),
        }

    def _evaluate(self, phase_results: dict) -> dict:
        """评估阶段：评估思考结果，判断是否需要调整"""
        think_result = phase_results.get("think", {})
        insights = think_result.get("insights", [])

        recommendations = []
        if think_result.get("high_urgency_count", 0) > 3:
            recommendations.append("多个高紧急项积压，建议优先处理")
        if think_result.get("high_activation_count", 0) > 5:
            recommendations.append("工作记忆激活度过高，可能需要释放低激活项")

        return {
            "insight_count": len(insights),
            "recommendations": recommendations,
            "needs_action": bool(recommendations),
        }

    def _act(self, phase_results: dict) -> dict:
        """行动阶段：根据评估结果执行调整"""
        eval_result = phase_results.get("evaluate", {})
        actions = []

        if eval_result.get("needs_action"):
            actions.append("recommendation_generated")

        return {
            "actions": actions,
            "action_count": len(actions),
        }

    def _adjust_attention_strategy(self, wm, attention) -> None:
        """根据工作记忆状态调整注意力策略"""
        wm_focus = [s for s in wm.slots if s.activation > 0.3]
        max_urgency = max((s.urgency for s in wm_focus), default=0.0)
        has_reflection = any("reflection" in s.source for s in wm_focus)

        if max_urgency > 0.6 and attention.active_strategy != AttentionStrategy.FOCUS:
            old, _ = attention.switch(AttentionStrategy.FOCUS, "wm_urgency_high")
            logger.debug(f"Intent-driven: {old.value} -> FOCUS (urgency={max_urgency:.2f})")
        elif has_reflection and attention.active_strategy != AttentionStrategy.EXPLORE:
            old, _ = attention.switch(AttentionStrategy.EXPLORE, "wm_has_reflection")
            logger.debug(f"Intent-driven: {old.value} -> EXPLORE (reflection questions)")

    def _check_health(self) -> dict:
        """健康检查"""
        return {
            "cycle_count": self._cycle_count,
            "last_cycle_time": self._last_result.get("total_time_ms", 0),
            "timestamp": datetime.now().isoformat(),
        }


_loop: CognitiveLoop | None = None


def get_cognitive_loop(config=None) -> CognitiveLoop:
    """获取全局认知循环实例"""
    global _loop
    if _loop is None:
        _loop = CognitiveLoop(config)
    return _loop
