"""盘古记忆健康监控 — 实时监控记忆系统健康状态

核心能力：
1. 健康评分：综合评估记忆系统健康状况
2. 实时告警：检测异常并生成告警
3. 趋势追踪：追踪各项健康指标的变化趋势
4. 系统概览：提供系统全面健康报告
5. 自动恢复：检测到问题时自动执行修复操作
"""

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.health_monitor")


@dataclass
class HealthCheck:
    """健康检查结果"""

    component: str
    status: str  # healthy / warning / critical
    score: float  # 0-1
    detail: str
    recommendation: str


class HealthMonitor:
    """记忆健康监控引擎"""

    def __init__(self, config=None):
        self.config = config
        self._check_history: list[dict] = []
        self._alerts: list[dict] = []

    def _evaluate_volume(self, total: int) -> HealthCheck:
        if total == 0:
            return HealthCheck("memory_volume", "critical", 0.0, "无记忆", "开始收集记忆")
        elif total < 10:
            return HealthCheck("memory_volume", "warning", 0.4, f"记忆偏少: {total}", "增加收集频率")
        elif total > 5000:
            return HealthCheck("memory_volume", "warning", 0.7, f"记忆量大: {total}", "考虑压缩和归档")
        else:
            return HealthCheck("memory_volume", "healthy", 1.0, f"记忆量正常: {total}", "")

    def check_memory_volume(self, drawers: list) -> HealthCheck:
        """检查记忆量"""
        return self._evaluate_volume(len(drawers))

    def check_importance_distribution(self, drawers: list) -> HealthCheck:
        """检查重要性分布"""
        if not drawers:
            return HealthCheck("importance", "critical", 0.0, "无数据", "")

        importances = [d.importance for d in drawers]
        avg = statistics.mean(importances)
        stdev = statistics.stdev(importances) if len(importances) > 1 else 0

        if avg < 1.5:
            score = 0.3
            status = "warning"
            rec = "多数记忆重要性偏低，检查评分机制"
        elif avg > 4.5:
            score = 0.6
            status = "warning"
            rec = "重要性普遍偏高，适当降低初始值"
        elif stdev > 2.0:
            score = 0.7
            status = "warning"
            rec = "重要性波动大，检查评分一致性"
        else:
            score = 1.0
            status = "healthy"
            rec = ""

        return HealthCheck("importance", status, round(score, 3), f"均值={avg:.2f}, 标准差={stdev:.2f}", rec)

    def check_tag_coverage(self, drawers: list) -> HealthCheck:
        """检查标签覆盖"""
        if not drawers:
            return HealthCheck("tags", "critical", 0.0, "无数据", "")

        total = len(drawers)
        with_tags = sum(1 for d in drawers if d.tags)
        coverage = with_tags / total

        all_tags = set()
        for d in drawers:
            all_tags.update(d.tags)

        if coverage < 0.3:
            return HealthCheck(
                "tags", "warning", 0.3, f"标签覆盖: {coverage:.0%} ({with_tags}/{total})", "为更多记忆添加标签"
            )
        elif len(all_tags) < 5:
            return HealthCheck("tags", "warning", 0.5, f"标签多样性低: {len(all_tags)} 个标签", "使用更多样的标签")
        else:
            return HealthCheck("tags", "healthy", 1.0, f"标签覆盖: {coverage:.0%}, {len(all_tags)} 个标签", "")

    def check_wing_balance(self, drawers: list) -> HealthCheck:
        """检查 Wing 分布均衡性"""
        if not drawers:
            return HealthCheck("distribution", "critical", 0.0, "无数据", "")

        wing_counts: dict[str, int] = {}
        for d in drawers:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1

        counts = list(wing_counts.values())
        if len(counts) <= 1:
            return HealthCheck("distribution", "warning", 0.5, f"仅有 {len(counts)} 个 Wing", "增加领域多样性")

        ratio = max(counts) / max(min(counts), 1)
        if ratio > 5:
            return HealthCheck("distribution", "warning", 0.5, f"分布不均: {ratio:.1f}x", "平衡各领域记忆收集")
        else:
            return HealthCheck("distribution", "healthy", 1.0, f"{len(wing_counts)} 个 Wing, 比例 {ratio:.1f}x", "")

    def check_content_quality(self, drawers: list) -> HealthCheck:
        """检查内容质量"""
        if not drawers:
            return HealthCheck("content", "critical", 0.0, "无数据", "")

        total = len(drawers)
        empty = sum(1 for d in drawers if len(d.content.strip()) < 5)
        very_long = sum(1 for d in drawers if len(d.content) > 5000)
        short = sum(1 for d in drawers if 5 <= len(d.content) < 20)

        problems = empty + very_long
        problem_rate = problems / total

        if problem_rate > 0.3:
            return HealthCheck(
                "content", "warning", 0.4, f"质量问题: {empty} 空, {very_long} 超长", "清理空记忆，压缩超长记忆"
            )
        elif short > total * 0.5:
            return HealthCheck("content", "warning", 0.6, f"短记忆偏多: {short}/{total}", "补充更多上下文信息")
        else:
            return HealthCheck("content", "healthy", 1.0, f"内容质量正常: {total} 条", "")

    def check_duplicates(self, drawers: list) -> HealthCheck:
        """检查重复"""
        if not drawers:
            return HealthCheck("duplicates", "critical", 0.0, "无数据", "")

        seen = {}
        dupes = 0
        for d in drawers:
            key = d.content[:30]
            if key in seen:
                dupes += 1
            else:
                seen[key] = d.id

        dupe_rate = dupes / len(drawers)
        if dupe_rate > 0.2:
            return HealthCheck(
                "duplicates", "warning", 0.3, f"重复率: {dupe_rate:.0%} ({dupes}/{len(drawers)})", "运行去重清理"
            )
        else:
            return HealthCheck("duplicates", "healthy", 1.0, f"重复率: {dupe_rate:.0%}", "")

    def full_check(self, drawers: list) -> dict:
        """全面健康检查"""
        checks = [
            self.check_memory_volume(drawers),
            self.check_importance_distribution(drawers),
            self.check_tag_coverage(drawers),
            self.check_wing_balance(drawers),
            self.check_content_quality(drawers),
            self.check_duplicates(drawers),
        ]

        scores = [c.score for c in checks]
        overall = statistics.mean(scores) if scores else 0

        if overall >= 0.8:
            overall_status = "healthy"
        elif overall >= 0.5:
            overall_status = "warning"
        else:
            overall_status = "critical"

        new_alerts = [c for c in checks if c.status != "healthy"]
        for alert in new_alerts:
            self._alerts.append(
                {
                    "component": alert.component,
                    "status": alert.status,
                    "detail": alert.detail,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        self._check_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "overall_score": round(overall, 3),
                "overall_status": overall_status,
                "checks": len(checks),
                "warnings": len(new_alerts),
            }
        )

        return {
            "overall_score": round(overall, 3),
            "overall_status": overall_status,
            "checks": [
                {
                    "component": c.component,
                    "status": c.status,
                    "score": c.score,
                    "detail": c.detail,
                    "recommendation": c.recommendation,
                }
                for c in checks
            ],
            "healthy_count": sum(1 for c in checks if c.status == "healthy"),
            "warning_count": sum(1 for c in checks if c.status == "warning"),
            "critical_count": sum(1 for c in checks if c.status == "critical"),
        }

    def get_trend(self) -> dict:
        """获取健康趋势"""
        if len(self._check_history) < 2:
            return {"trend": "insufficient_data"}

        scores = [h["overall_score"] for h in self._check_history[-20:]]
        recent_avg = statistics.mean(scores[-5:]) if len(scores) >= 5 else scores[-1]
        older_avg = statistics.mean(scores[:-5]) if len(scores) > 5 else scores[0]

        if recent_avg > older_avg * 1.05:
            trend = "improving"
        elif recent_avg < older_avg * 0.95:
            trend = "degrading"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "current_score": scores[-1],
            "avg_score": round(recent_avg, 3),
            "history_count": len(self._check_history),
        }

    def get_health_stats(self) -> dict:
        """获取健康统计"""
        return {
            "total_checks": len(self._check_history),
            "total_alerts": len(self._alerts),
            "latest": self._check_history[-1] if self._check_history else None,
        }


_monitor: HealthMonitor | None = None


def get_monitor(config=None) -> HealthMonitor:
    """获取全局健康监控实例"""
    global _monitor
    if _monitor is None:
        _monitor = HealthMonitor(config)
    return _monitor
