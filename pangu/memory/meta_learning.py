"""盘古元学习引擎 — 学习如何更好地学习

核心能力：
1. 性能观察：观察各模块的性能指标
2. 参数调优：基于观察结果自动调优系统参数
3. 策略进化：自动选择最优的搜索/记忆/巩固策略
4. 效果反馈：学习哪些策略有效、哪些无效
5. 自我改进：持续自我改进，形成正反馈循环
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.meta_learning")


@dataclass
class LearningStrategy:
    """学习策略"""
    name: str
    params: dict
    success_rate: float
    total_uses: int
    successful_uses: int
    last_used: str


@dataclass
class PerformanceObservation:
    """性能观察"""
    module: str
    metric: str
    value: float
    timestamp: str
    context: str


class MetaLearningEngine:
    """元学习引擎 — 学习如何更好地学习"""

    DEFAULT_STRATEGIES = {
        "search_balanced": {
            "vector_weight": 0.5,
            "fts_weight": 0.5,
            "recency_boost": 0.1,
        },
        "search_semantic": {
            "vector_weight": 0.8,
            "fts_weight": 0.2,
            "recency_boost": 0.05,
        },
        "search_keyword": {
            "vector_weight": 0.2,
            "fts_weight": 0.8,
            "recency_boost": 0.15,
        },
        "conservation": {
            "decay_rate": 0.9,
            "compression_threshold": 200,
            "min_importance": 0.3,
        },
        "aggressive": {
            "decay_rate": 0.98,
            "compression_threshold": 50,
            "min_importance": 0.6,
        },
    }

    def __init__(self, config=None):
        self.config = config
        self._strategies: dict[str, LearningStrategy] = {}
        self._observations: list[PerformanceObservation] = []
        self._active_strategy: str = "search_balanced"
        self._evolution_history: list[dict] = []

        for name, params in self.DEFAULT_STRATEGIES.items():
            self._strategies[name] = LearningStrategy(
                name=name, params=params,
                success_rate=0.5, total_uses=0, successful_uses=0,
                last_used="",
            )

    def observe(self, module: str, metric: str, value: float, context: str = "") -> None:
        """记录性能观察"""
        obs = PerformanceObservation(
            module=module, metric=metric, value=value,
            timestamp=datetime.now().isoformat(), context=context,
        )
        self._observations.append(obs)

        if len(self._observations) > 500:
            self._observations = self._observations[-500:]

    def record_strategy_result(self, strategy_name: str, success: bool) -> None:
        """记录策略使用结果"""
        if strategy_name not in self._strategies:
            return

        s = self._strategies[strategy_name]
        s.total_uses += 1
        if success:
            s.successful_uses += 1
        s.success_rate = s.successful_uses / max(s.total_uses, 1)
        s.last_used = datetime.now().isoformat()

    def recommend_strategy(self, task_type: str = "search") -> dict:
        """推荐最优策略"""
        candidates = [
            (name, s) for name, s in self._strategies.items()
            if task_type in name or task_type == "all"
        ]

        if not candidates:
            candidates = list(self._strategies.items())

        if not candidates:
            return {"strategy": "search_balanced", "params": self.DEFAULT_STRATEGIES["search_balanced"]}

        best_name, best = max(candidates, key=lambda x: x[1].success_rate)
        return {"strategy": best_name, "params": best.params, "success_rate": best.success_rate}

    def auto_tune(self) -> dict:
        """自动调优 — 基于观察结果调整策略参数"""
        recent = self._observations[-50:]
        if not recent:
            return {"status": "no_data"}

        module_metrics: dict[str, dict[str, list[float]]] = {}
        for obs in recent:
            module_metrics.setdefault(obs.module, {}).setdefault(obs.metric, []).append(obs.value)

        adjustments = []
        for module, metrics in module_metrics.items():
            for metric, values in metrics.items():
                avg = sum(values) / len(values)
                if "search" in metric and avg < 0.3:
                    self._adjust_strategy("search_semantic", "vector_weight", 0.05)
                    adjustments.append(f"search score low ({avg:.3f}), boosting vector weight")
                elif "latency" in metric and avg > 50:
                    self._adjust_strategy("search_balanced", "fts_weight", -0.1)
                    adjustments.append(f"latency high ({avg:.0f}ms), reducing FTS weight")
                elif "recall" in metric and avg > 0.8:
                    self._adjust_strategy("search_keyword", "fts_weight", 0.05)
                    adjustments.append(f"recall good ({avg:.3f}), favoring keyword search")

        return {
            "adjusted": len(adjustments),
            "adjustments": adjustments,
        }

    def _adjust_strategy(self, strategy_name: str, param: str, delta: float) -> None:
        """调整策略参数"""
        if strategy_name in self._strategies:
            s = self._strategies[strategy_name]
            if param in s.params:
                old = s.params[param]
                s.params[param] = round(max(0, min(1, old + delta)), 3)

    def get_learning_insights(self) -> dict:
        """获取学习洞察"""
        if not self._observations:
            return {"status": "no_data"}

        module_perf: dict[str, dict[str, float]] = {}
        for obs in self._observations:
            if obs.module not in module_perf:
                module_perf[obs.module] = {}
            m = module_perf[obs.module]
            m[obs.metric] = (m.get(obs.metric, 0) + obs.value) / 2

        best_strategies = sorted(
            self._strategies.items(),
            key=lambda x: x[1].success_rate,
            reverse=True,
        )[:3]

        return {
            "modules_tracked": len(module_perf),
            "total_observations": len(self._observations),
            "best_strategies": [
                {"name": name, "success_rate": round(s.success_rate, 3), "uses": s.total_uses}
                for name, s in best_strategies
            ],
            "active_strategy": self._active_strategy,
        }

    def get_meta_stats(self) -> dict:
        """获取元学习统计"""
        total_uses = sum(s.total_uses for s in self._strategies.values())
        total_success = sum(s.successful_uses for s in self._strategies.values())
        return {
            "strategies": len(self._strategies),
            "total_uses": total_uses,
            "overall_success_rate": round(total_success / max(total_uses, 1), 3),
            "observations": len(self._observations),
            "active_strategy": self._active_strategy,
        }

    def monitor_system_health(self) -> dict:
        """系统级长期监测 — 分析记忆系统运行状态并生成健康报告"""
        now = datetime.now()
        health_report: dict = {
            "timestamp": now.isoformat(),
            "strategies": {},
            "observations": {},
            "recommendations": [],
        }

        total_uses = sum(s.total_uses for s in self._strategies.values())
        total_success = sum(s.successful_uses for s in self._strategies.values())
        overall_rate = round(total_success / max(total_uses, 1), 3)

        health_report["strategies"] = {
            "total": len(self._strategies),
            "total_uses": total_uses,
            "overall_success_rate": overall_rate,
            "active": self._active_strategy,
        }

        recent_obs = self._observations[-50:] if self._observations else []
        module_counts: dict[str, int] = {}
        for obs in recent_obs:
            module_counts[obs.module] = module_counts.get(obs.module, 0) + 1

        health_report["observations"] = {
            "total": len(self._observations),
            "recent": len(recent_obs),
            "modules_tracked": len(module_counts),
            "top_modules": sorted(module_counts.items(), key=lambda x: x[1], reverse=True)[:5],
        }

        if overall_rate < 0.3 and total_uses > 10:
            health_report["recommendations"].append("整体成功率过低，建议重置策略参数")
        if len(self._observations) == 0:
            health_report["recommendations"].append("无性能观察数据，建议开始记录")
        if total_uses == 0:
            health_report["recommendations"].append("策略未被使用，建议主动调优")

        best = max(self._strategies.values(), key=lambda s: s.success_rate) if self._strategies else None
        worst = min(self._strategies.values(), key=lambda s: s.success_rate) if self._strategies else None
        if best and worst and best.success_rate - worst.success_rate > 0.5:
            health_report["recommendations"].append(
                f"策略效果差异大: {best.name}({best.success_rate:.2f}) vs {worst.name}({worst.success_rate:.2f})"
            )

        return health_report

    def detect_self_reconfig(self) -> dict:
        """自重构检测 — 基于策略表现判断是否需要调整配置"""
        actions = []

        low_perf = [
            (name, s) for name, s in self._strategies.items()
            if s.total_uses >= 5 and s.success_rate < 0.3
        ]
        for name, s in low_perf:
            actions.append({
                "strategy": name,
                "action": "reduce_frequency",
                "reason": f"low_success_rate({s.success_rate:.3f}, uses={s.total_uses})",
            })

        unused = [name for name, s in self._strategies.items() if s.total_uses == 0]
        if len(unused) > 2:
            actions.append({
                "action": "review_unused_strategies",
                "strategies": unused,
                "reason": f"{len(unused)} strategies never used",
            })

        recent = self._observations[-20:] if self._observations else []
        if recent:
            module_failures: dict[str, int] = {}
            for obs in recent:
                if obs.value < 0.3:
                    module_failures[obs.module] = module_failures.get(obs.module, 0) + 1
            for module, count in module_failures.items():
                if count >= 3:
                    actions.append({
                        "module": module,
                        "action": "investigate",
                        "reason": f"{count} low-value observations",
                    })

        status = "reconfig_needed" if actions else "stable"
        return {"status": status, "actions": actions}


_meta_engine: MetaLearningEngine | None = None


def get_meta_engine(config=None) -> MetaLearningEngine:
    """获取全局元学习引擎实例"""
    global _meta_engine
    if _meta_engine is None:
        _meta_engine = MetaLearningEngine(config)
    return _meta_engine
