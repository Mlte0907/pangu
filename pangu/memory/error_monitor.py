"""盘古错误监控 — 集中日志 + 异常追踪 + 健康报告

核心能力：
1. 错误收集：捕获所有工具调用异常
2. 错误统计：按类型/工具/时间维度统计
3. 错误趋势：最近错误率变化
4. 健康报告：综合系统健康评分
5. 告警：严重错误自动告警
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.error_monitor")


class ErrorMonitor:
    """错误监控引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._errors: list[dict] = []
        self._max_errors = 1000
        self._stats = defaultdict(int)
        self._state_file = Path(self.config.palace_path) / "error_monitor.json"
        self._load_state()

    def _load_state(self):
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    state = json.load(f)
                    self._stats = defaultdict(int, state.get("stats", {}))
            except Exception:
                pass

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump({"stats": dict(self._stats)}, f, indent=2)
        except Exception:
            pass

    def record_error(self, tool_name: str, error: str, severity: str = "error") -> dict:
        """记录错误"""
        entry = {
            "tool": tool_name,
            "error": str(error)[:500],
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        }
        self._errors.append(entry)
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

        self._stats[f"{tool_name}:error"] += 1
        self._stats[f"total:{severity}"] += 1
        self._stats["total_events"] += 1
        self._save_state()

        if severity == "critical":
            logger.error(f"CRITICAL: {tool_name}: {error}")

        return entry

    def record_success(self, tool_name: str) -> None:
        """记录成功调用"""
        self._stats[f"{tool_name}:success"] += 1
        self._stats["total_events"] += 1

    def get_errors(self, tool: str = None, severity: str = None, limit: int = 20) -> list[dict]:
        """获取最近的错误"""
        errors = self._errors
        if tool:
            errors = [e for e in errors if e.get("tool") == tool]
        if severity:
            errors = [e for e in errors if e.get("severity") == severity]
        return errors[-limit:]

    def get_stats(self) -> dict:
        """获取错误统计"""
        total_errors = self._stats.get("total:error", 0) + self._stats.get("total:warning", 0)
        total_events = self._stats.get("total_events", 1)

        # 按工具统计错误
        tool_errors = {}
        for key, count in self._stats.items():
            if ":error" in key and key.startswith("total:") is False:
                tool_name = key.replace(":error", "")
                tool_errors[tool_name] = count

        # 最近错误率
        recent_errors = [e for e in self._errors if
                         (datetime.now() - datetime.fromisoformat(e["timestamp"])).total_seconds() < 3600]

        return {
            "total_errors": total_errors,
            "total_events": total_events,
            "error_rate": round(total_errors / max(total_events, 1), 4),
            "recent_errors_1h": len(recent_errors),
            "top_error_tools": dict(sorted(tool_errors.items(), key=lambda x: -x[1])[:5]),
            "critical_errors": self._stats.get("total:critical", 0),
        }

    def get_health_report(self) -> dict:
        """生成综合健康报告"""
        stats = self.get_stats()
        error_rate = stats["error_rate"]

        # 计算健康评分 (0-100)
        score = 100
        if error_rate > 0.1:
            score -= min(50, int(error_rate * 100))
        if stats["critical_errors"] > 0:
            score -= stats["critical_errors"] * 10
        score = max(0, min(100, score))

        if score >= 90:
            status = "healthy"
        elif score >= 70:
            status = "degraded"
        else:
            status = "unhealthy"

        recommendations = []
        if error_rate > 0.05:
            recommendations.append("错误率偏高，建议检查最近的错误日志")
        if stats["critical_errors"] > 0:
            recommendations.append(f"有 {stats['critical_errors']} 个严重错误需要处理")
        if not recommendations:
            recommendations.append("系统运行正常")

        return {
            "score": score,
            "status": status,
            "error_rate": error_rate,
            "total_errors": stats["total_errors"],
            "total_events": stats["total_events"],
            "recent_errors_1h": stats["recent_errors_1h"],
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat(),
        }

    def get_recent(self, limit: int = 20) -> list[dict]:
        return self._errors[-limit:]


_monitor: ErrorMonitor | None = None


def get_error_monitor(config: PanguConfig = None) -> ErrorMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ErrorMonitor(config)
    return _monitor
