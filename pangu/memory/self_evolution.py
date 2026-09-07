"""盘古自进化引擎 — 系统自我评估与自动优化

核心能力：
1. 自我诊断：分析系统健康状况，识别瓶颈
2. 自动调优：根据诊断结果自动调整参数
3. 架构进化：根据使用模式建议架构改进
4. 性能预测：预测系统在不同负载下的表现
"""

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.self_evolution")


@dataclass
class DiagnosisResult:
    """诊断结果"""

    category: str
    severity: str  # critical / warning / info
    description: str
    recommendation: str
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0


@dataclass
class EvolutionPlan:
    """进化计划"""

    name: str
    actions: list[str]
    expected_improvement: str
    priority: int  # 1-5
    status: str = "pending"  # pending / executing / completed / failed


class SelfEvolutionEngine:
    """自进化引擎 — 系统自我优化"""

    def __init__(self, config=None):
        self.config = config
        self._diagnosis_history: list[dict] = []
        self._evolution_plans: list[EvolutionPlan] = []
        self._performance_log: list[dict] = []

    def diagnose(self, drawers: list, search_stats: dict = None, lifecycle_stats: dict = None) -> list[DiagnosisResult]:
        """全面诊断系统健康状况"""
        results = []

        # 1. 记忆量诊断
        total = len(drawers)
        if total == 0:
            results.append(
                DiagnosisResult(
                    category="memory",
                    severity="critical",
                    description="系统中没有记忆",
                    recommendation="开始收集和存储记忆",
                    metric_name="total_memories",
                    metric_value=0,
                )
            )
        elif total < 10:
            results.append(
                DiagnosisResult(
                    category="memory",
                    severity="warning",
                    description=f"记忆量偏少: {total} 条",
                    recommendation="增加记忆收集频率",
                    metric_name="total_memories",
                    metric_value=total,
                )
            )

        # 2. 重要性分布诊断
        if drawers:
            importances = [d.importance for d in drawers]
            avg_imp = statistics.mean(importances)
            if avg_imp < 2.0:
                results.append(
                    DiagnosisResult(
                        category="importance",
                        severity="warning",
                        description=f"平均重要性偏低: {avg_imp:.2f}",
                        recommendation="调整重要性评分阈值，避免低质量记忆堆积",
                        metric_name="avg_importance",
                        metric_value=avg_imp,
                        threshold=2.0,
                    )
                )
            elif avg_imp > 4.5:
                results.append(
                    DiagnosisResult(
                        category="importance",
                        severity="info",
                        description=f"平均重要性偏高: {avg_imp:.2f}",
                        recommendation="适当降低新记忆的初始重要性",
                        metric_name="avg_importance",
                        metric_value=avg_imp,
                        threshold=4.5,
                    )
                )

        # 3. Wing 分布诊断
        wing_counts: dict[str, int] = {}
        for d in drawers:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1

        if wing_counts:
            max_wing = max(wing_counts.values())
            min_wing = min(wing_counts.values())
            if max_wing > 0 and min_wing > 0 and max_wing / min_wing > 10:
                results.append(
                    DiagnosisResult(
                        category="distribution",
                        severity="warning",
                        description=f"Wing 分布不均: {max_wing}/{min_wing} = {max_wing / min_wing:.1f}x",
                        recommendation="平衡各领域的记忆收集",
                        metric_name="wing_balance",
                        metric_value=max_wing / min_wing,
                        threshold=10.0,
                    )
                )

        # 4. 标签多样性诊断
        all_tags = set()
        for d in drawers:
            all_tags.update(d.tags)
        tag_ratio = len(all_tags) / max(total, 1)
        if total > 20 and tag_ratio < 0.3:
            results.append(
                DiagnosisResult(
                    category="diversity",
                    severity="warning",
                    description=f"标签多样性不足: {len(all_tags)} 标签 / {total} 记忆 = {tag_ratio:.2f}",
                    recommendation="鼓励使用更多元的标签",
                    metric_name="tag_diversity",
                    metric_value=tag_ratio,
                    threshold=0.3,
                )
            )

        # 5. 搜索质量诊断
        if search_stats:
            avg_score = search_stats.get("avg_score", 0)
            hit_rate = search_stats.get("hit_rate", 0)
            if hit_rate < 0.3:
                results.append(
                    DiagnosisResult(
                        category="search",
                        severity="warning",
                        description=f"搜索命中率偏低: {hit_rate:.2%}",
                        recommendation="优化搜索参数，检查向量索引",
                        metric_name="search_hit_rate",
                        metric_value=hit_rate,
                        threshold=0.3,
                    )
                )
            if avg_score < 0.25:
                results.append(
                    DiagnosisResult(
                        category="search",
                        severity="critical",
                        description=f"搜索平均得分过低: {avg_score:.3f}",
                        recommendation="检查 embedding 模型和分词质量",
                        metric_name="search_avg_score",
                        metric_value=avg_score,
                        threshold=0.25,
                    )
                )

        # 6. 生命周期诊断
        if lifecycle_stats:
            pending_review = lifecycle_stats.get("due_review_count", 0)
            if pending_review > 50:
                results.append(
                    DiagnosisResult(
                        category="lifecycle",
                        severity="warning",
                        description=f"待复习记忆积压: {pending_review} 条",
                        recommendation="增加巩固频率或降低复习阈值",
                        metric_name="pending_review",
                        metric_value=pending_review,
                        threshold=50,
                    )
                )

        # 7. 重复记忆诊断
        seen_contents = {}
        duplicates = 0
        for d in drawers:
            content_key = d.content[:50]
            if content_key in seen_contents:
                duplicates += 1
            else:
                seen_contents[content_key] = d.id
        dup_rate = duplicates / max(total, 1)
        if dup_rate > 0.15:
            results.append(
                DiagnosisResult(
                    category="dedup",
                    severity="warning",
                    description=f"重复记忆比例: {dup_rate:.2%} ({duplicates}/{total})",
                    recommendation="提高去重阈值或运行去重清理",
                    metric_name="duplicate_rate",
                    metric_value=dup_rate,
                    threshold=0.15,
                )
            )

        # 记录诊断历史
        self._diagnosis_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "total_memories": total,
                "issues_found": len(results),
                "critical": sum(1 for r in results if r.severity == "critical"),
                "warnings": sum(1 for r in results if r.severity == "warning"),
            }
        )

        return results

    def generate_evolution_plan(self, diagnosis: list[DiagnosisResult]) -> EvolutionPlan:
        """基于诊断结果生成进化计划"""
        actions = []
        for d in diagnosis:
            if d.severity in ("critical", "warning"):
                actions.append(f"[{d.severity}] {d.recommendation}")

        critical_count = sum(1 for d in diagnosis if d.severity == "critical")
        warning_count = sum(1 for d in diagnosis if d.severity == "warning")

        if critical_count > 0:
            priority = 1
            expected = f"修复 {critical_count} 个严重问题"
        elif warning_count > 2:
            priority = 2
            expected = f"改善 {warning_count} 个警告"
        else:
            priority = 3
            expected = "常规优化"

        plan = EvolutionPlan(
            name=f"进化计划 {len(self._evolution_plans) + 1}",
            actions=actions,
            expected_improvement=expected,
            priority=priority,
        )
        self._evolution_plans.append(plan)
        return plan

    def record_performance(self, metric: str, value: float) -> None:
        """记录性能指标"""
        self._performance_log.append(
            {
                "metric": metric,
                "value": value,
                "timestamp": datetime.now().isoformat(),
            }
        )
        if len(self._performance_log) > 500:
            self._performance_log = self._performance_log[-500:]

    def get_performance_trend(self, metric: str, limit: int = 20) -> dict:
        """获取性能趋势"""
        entries = [e for e in self._performance_log if e["metric"] == metric][-limit:]
        if not entries:
            return {"metric": metric, "values": [], "trend": "no_data"}

        values = [e["value"] for e in entries]
        if len(values) >= 2:
            avg_first = statistics.mean(values[: len(values) // 2])
            avg_second = statistics.mean(values[len(values) // 2 :])
            if avg_second > avg_first * 1.1:
                trend = "improving"
            elif avg_second < avg_first * 0.9:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "metric": metric,
            "values": values,
            "current": values[-1],
            "avg": statistics.mean(values),
            "trend": trend,
        }

    def get_evolution_stats(self) -> dict:
        """获取进化统计"""
        return {
            "diagnosis_count": len(self._diagnosis_history),
            "plans_count": len(self._evolution_plans),
            "plans_completed": sum(1 for p in self._evolution_plans if p.status == "completed"),
            "performance_entries": len(self._performance_log),
            "latest_diagnosis": self._diagnosis_history[-1] if self._diagnosis_history else None,
        }


_evolution_engine: SelfEvolutionEngine | None = None


def get_evolution_engine(config=None) -> SelfEvolutionEngine:
    """获取全局自进化引擎实例"""
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = SelfEvolutionEngine(config)
    return _evolution_engine
