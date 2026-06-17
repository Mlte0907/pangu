"""盘古审计与分析 — 追踪所有记忆操作

核心能力：
1. 操作审计：记录所有记忆操作（增删改查）
2. 访问分析：分析记忆访问模式
3. 安全日志：记录敏感操作和异常行为
4. 操作统计：统计各类型操作的频率和性能
5. 审计查询：按时间/操作类型/用户查询审计日志
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger("pangu.memory.audit_analytics")


@dataclass
class AuditEntry:
    """审计条目"""
    entry_id: str
    timestamp: str
    operation: str  # create / read / update / delete / search / backup
    target_id: str
    user_id: str
    details: dict
    duration_ms: float
    success: bool


class AuditAnalytics:
    """审计分析引擎"""

    def __init__(self, config=None):
        self.config = config
        self._entries: list[AuditEntry] = []
        self._max_entries = 10000

    def log(self, operation: str, target_id: str = "", user_id: str = "system",
            details: dict = None, duration_ms: float = 0, success: bool = True) -> AuditEntry:
        """记录审计条目"""
        entry = AuditEntry(
            entry_id=f"audit_{len(self._entries)}_{int(time.time())}",
            timestamp=datetime.now().isoformat(),
            operation=operation,
            target_id=target_id,
            user_id=user_id,
            details=details or {},
            duration_ms=duration_ms,
            success=success,
        )
        self._entries.append(entry)

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        return entry

    def log_operation(self, operation: str, target_id: str = "", **kwargs) -> AuditEntry:
        """便捷日志记录"""
        return self.log(operation, target_id, **kwargs)

    def get_entries(self, operation: str = None, user_id: str = None,
                    limit: int = 50) -> list[dict]:
        """查询审计条目"""
        filtered = self._entries

        if operation:
            filtered = [e for e in filtered if e.operation == operation]
        if user_id:
            filtered = [e for e in filtered if e.user_id == user_id]

        return [
            {"id": e.entry_id, "timestamp": e.timestamp, "operation": e.operation,
             "target": e.target_id, "user": e.user_id, "duration_ms": e.duration_ms,
             "success": e.success}
            for e in filtered[-limit:]
        ]

    def get_operation_stats(self) -> dict:
        """获取操作统计"""
        op_counts: dict[str, int] = {}
        op_durations: dict[str, list[float]] = {}
        success_count = 0
        fail_count = 0

        for e in self._entries:
            op_counts[e.operation] = op_counts.get(e.operation, 0) + 1
            op_durations.setdefault(e.operation, []).append(e.duration_ms)
            if e.success:
                success_count += 1
            else:
                fail_count += 1

        avg_durations = {}
        for op, durations in op_durations.items():
            avg_durations[op] = round(sum(durations) / len(durations), 2)

        return {
            "total_operations": len(self._entries),
            "operation_counts": op_counts,
            "avg_durations_ms": avg_durations,
            "success_rate": round(success_count / max(len(self._entries), 1), 3),
            "success_count": success_count,
            "fail_count": fail_count,
        }

    def get_access_patterns(self, drawers: list = None) -> dict:
        """分析访问模式"""
        hour_counts: dict[int, int] = {}
        for e in self._entries:
            try:
                dt = datetime.fromisoformat(e.timestamp)
                hour_counts[dt.hour] = hour_counts.get(dt.hour, 0) + 1
            except (ValueError, TypeError):
                pass

        peak_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else -1

        user_ops: dict[str, int] = {}
        for e in self._entries:
            user_ops[e.user_id] = user_ops.get(e.user_id, 0) + 1

        return {
            "total_entries": len(self._entries),
            "peak_hour": peak_hour,
            "hour_distribution": dict(sorted(hour_counts.items())),
            "user_activity": user_ops,
        }

    def _accumulate_fail_rates(self, entries: list) -> dict[str, dict]:
        user_fail_rates: dict[str, dict] = {}
        for e in entries:
            if e.user_id not in user_fail_rates:
                user_fail_rates[e.user_id] = {"total": 0, "failed": 0}
            user_fail_rates[e.user_id]["total"] += 1
            if not e.success:
                user_fail_rates[e.user_id]["failed"] += 1
        return user_fail_rates

    def detect_anomalies(self) -> list[dict]:
        anomalies = []

        user_fail_rates = self._accumulate_fail_rates(self._entries)

        for user, stats in user_fail_rates.items():
            if stats["total"] >= 5:
                fail_rate = stats["failed"] / stats["total"]
                if fail_rate > 0.5:
                    anomalies.append({
                        "type": "high_fail_rate",
                        "user": user,
                        "fail_rate": round(fail_rate, 3),
                        "detail": f"失败率 {fail_rate:.0%} ({stats['failed']}/{stats['total']})",
                    })

        recent = self._entries[-20:]
        delete_count = sum(1 for e in recent if e.operation == "delete")
        if delete_count > 5:
            anomalies.append({
                "type": "high_delete_rate",
                "detail": f"最近 20 操作中有 {delete_count} 次删除",
                "count": delete_count,
            })

        slow_ops = [e for e in recent if e.duration_ms > 1000]
        if len(slow_ops) > 3:
            anomalies.append({
                "type": "slow_operations",
                "detail": f"最近有 {len(slow_ops)} 个慢操作 (>1000ms)",
                "count": len(slow_ops),
            })

        return anomalies

    def get_security_summary(self) -> dict:
        """安全摘要"""
        anomalies = self.detect_anomalies()
        stats = self.get_operation_stats()

        return {
            "total_operations": stats["total_operations"],
            "success_rate": stats["success_rate"],
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:5],
            "risk_level": "low" if len(anomalies) < 2 else "medium" if len(anomalies) < 5 else "high",
        }


_audit: AuditAnalytics | None = None


def get_audit(config=None) -> AuditAnalytics:
    """获取全局审计分析实例"""
    global _audit
    if _audit is None:
        _audit = AuditAnalytics(config)
    return _audit
