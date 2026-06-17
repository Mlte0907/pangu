"""盘古异常检测 — 发现记忆系统中的异常模式

核心能力：
1. 分布异常检测：发现记忆分布中的异常
2. 时序异常检测：发现时间序列中的异常变化
3. 内容异常检测：发现内容质量异常
4. 行为异常检测：发现搜索/写入行为异常
"""
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.anomaly_detection")


@dataclass
class Anomaly:
    """异常"""
    anomaly_type: str
    severity: str  # critical / warning / info
    description: str
    affected_items: list[str]
    metric_name: str
    metric_value: float
    expected_range: tuple[float, float]
    suggestion: str


class AnomalyDetector:
    """异常检测引擎"""

    def __init__(self, config=None):
        self.config = config
        self._baseline: dict[str, dict] = {}
        self._anomaly_history: list[dict] = []

    def _check_wing_distribution(self, wing_counts: dict[str, int]) -> list[Anomaly]:
        anomalies = []
        counts = list(wing_counts.values())
        if len(counts) < 3:
            return anomalies

        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts) if len(counts) > 1 else 0

        for wing, count in wing_counts.items():
            if stdev > 0 and abs(count - mean) > 2 * stdev:
                anomalies.append(Anomaly(
                    anomaly_type="wing_distribution",
                    severity="warning",
                    description=f"Wing '{wing}' 记忆数量异常: {count} (均值 {mean:.1f})",
                    affected_items=[wing],
                    metric_name=f"wing_{wing}",
                    metric_value=count,
                    expected_range=(max(0, mean - stdev), mean + stdev),
                    suggestion="平衡各领域记忆收集",
                ))
        return anomalies

    def detect_distribution_anomalies(self, drawers: list) -> list[Anomaly]:
        anomalies = []

        if not drawers:
            return anomalies

        wing_counts: dict[str, int] = {}
        for d in drawers:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1

        anomalies.extend(self._check_wing_distribution(wing_counts))

        importances = [d.importance for d in drawers]
        if len(importances) >= 5:
            imp_mean = statistics.mean(importances)
            imp_stdev = statistics.stdev(importances)
            low_count = sum(1 for i in importances if i < imp_mean - 2 * imp_stdev)
            high_count = sum(1 for i in importances if i > imp_mean + 2 * imp_stdev)

            if low_count > len(importances) * 0.1:
                anomalies.append(Anomaly(
                    anomaly_type="importance_outlier",
                    severity="info",
                    description=f"发现 {low_count} 条异常低重要性记忆",
                    affected_items=[],
                    metric_name="low_importance_count",
                    metric_value=low_count,
                    expected_range=(0, len(importances) * 0.05),
                    suggestion="检查低重要性记忆是否需要清理",
                ))

        return anomalies

    def detect_content_anomalies(self, drawers: list) -> list[Anomaly]:
        """检测内容异常"""
        anomalies = []

        empty_content = [d for d in drawers if not d.content.strip()]
        if empty_content:
            anomalies.append(Anomaly(
                anomaly_type="empty_content",
                severity="critical",
                description=f"发现 {len(empty_content)} 条空内容记忆",
                affected_items=[d.id for d in empty_content[:5]],
                metric_name="empty_count",
                metric_value=len(empty_content),
                expected_range=(0, 0),
                suggestion="清理空内容记忆",
            ))

        very_long = [d for d in drawers if len(d.content) > 10000]
        if very_long:
            anomalies.append(Anomaly(
                anomaly_type="oversized_content",
                severity="warning",
                description=f"发现 {len(very_long)} 条超长记忆 (>10000字符)",
                affected_items=[d.id for d in very_long[:5]],
                metric_name="oversized_count",
                metric_value=len(very_long),
                expected_range=(0, 1),
                suggestion="考虑压缩超长记忆",
            ))

        seen = {}
        exact_dupes = []
        for d in drawers:
            if d.content in seen:
                exact_dupes.append(d.id)
            else:
                seen[d.content] = d.id

        if exact_dupes:
            anomalies.append(Anomaly(
                anomaly_type="exact_duplicates",
                severity="warning",
                description=f"发现 {len(exact_dupes)} 条完全重复记忆",
                affected_items=exact_dupes[:5],
                metric_name="exact_dup_count",
                metric_value=len(exact_dupes),
                expected_range=(0, 0),
                suggestion="运行去重清理",
            ))

        no_tags = [d for d in drawers if not d.tags]
        if len(no_tags) > len(drawers) * 0.3:
            anomalies.append(Anomaly(
                anomaly_type="missing_tags",
                severity="info",
                description=f"{len(no_tags)}/{len(drawers)} 条记忆缺少标签 ({len(no_tags)/len(drawers):.0%})",
                affected_items=[d.id for d in no_tags[:5]],
                metric_name="no_tag_ratio",
                metric_value=len(no_tags) / max(len(drawers), 1),
                expected_range=(0, 0.2),
                suggestion="为记忆添加标签以提高检索质量",
            ))

        return anomalies

    def detect_behavior_anomalies(self, search_log: list[dict] = None) -> list[Anomaly]:
        """检测行为异常"""
        anomalies = []

        if not search_log:
            return anomalies

        if len(search_log) > 100:
            recent = search_log[-100:]
            queries = [s.get("query", "") for s in recent]
            query_counts: dict[str, int] = {}
            for q in queries:
                query_counts[q] = query_counts.get(q, 0) + 1

            for q, count in query_counts.items():
                if count > 20:
                    anomalies.append(Anomaly(
                        anomaly_type="repeated_query",
                        severity="warning",
                        description=f"查询 '{q[:30]}' 重复 {count} 次",
                        affected_items=[],
                        metric_name="query_repeat",
                        metric_value=count,
                        expected_range=(1, 10),
                        suggestion="考虑缓存高频查询结果",
                    ))

        return anomalies

    def full_scan(self, drawers: list, search_log: list[dict] = None) -> dict:
        """完整扫描"""
        all_anomalies = []
        all_anomalies.extend(self.detect_distribution_anomalies(drawers))
        all_anomalies.extend(self.detect_content_anomalies(drawers))
        all_anomalies.extend(self.detect_behavior_anomalies(search_log))

        critical = sum(1 for a in all_anomalies if a.severity == "critical")
        warnings = sum(1 for a in all_anomalies if a.severity == "warning")

        self._anomaly_history.append({
            "timestamp": datetime.now().isoformat(),
            "total": len(all_anomalies),
            "critical": critical,
            "warnings": warnings,
        })

        return {
            "anomalies": [
                {"type": a.anomaly_type, "severity": a.severity,
                 "description": a.description, "suggestion": a.suggestion}
                for a in all_anomalies
            ],
            "total": len(all_anomalies),
            "critical": critical,
            "warnings": warnings,
            "healthy": len(all_anomalies) == 0,
        }

    def get_anomaly_stats(self) -> dict:
        """获取异常统计"""
        return {
            "scans_count": len(self._anomaly_history),
            "latest": self._anomaly_history[-1] if self._anomaly_history else None,
        }


_detector: AnomalyDetector | None = None


def get_detector(config=None) -> AnomalyDetector:
    """获取全局异常检测实例"""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector(config)
    return _detector
