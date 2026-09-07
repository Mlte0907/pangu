"""盘古生产加固 — 结构化日志、请求指标、启动校验、优雅关闭"""

import json
import logging
import os
import signal
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ── 结构化日志 ──


class StructuredFormatter(logging.Formatter):
    """JSON 结构化日志格式"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_structured_logging(level: str = "INFO", log_file: str = None):
    """配置结构化日志"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(StructuredFormatter())
    root.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(StructuredFormatter())
        root.addHandler(file_handler)


# ── 请求指标收集 ──


@dataclass
class RequestMetric:
    """请求指标"""

    endpoint: str
    method: str
    status: int
    duration_ms: float
    timestamp: float
    user_agent: str = ""


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._request_metrics: list[RequestMetric] = []
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()
        self._lock = threading.Lock()

    def record_request(self, endpoint: str, method: str, status: int, duration_ms: float, user_agent: str = ""):
        """记录请求指标"""
        with self._lock:
            self._request_metrics.append(
                RequestMetric(
                    endpoint=endpoint,
                    method=method,
                    status=status,
                    duration_ms=duration_ms,
                    timestamp=time.time(),
                    user_agent=user_agent,
                )
            )
            self._counters[f"requests_{status}"] += 1
            self._counters[f"requests_{method}"] += 1
            self._histograms[f"duration_{endpoint}"].append(duration_ms)

    def increment(self, name: str, value: int = 1):
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float):
        with self._lock:
            self._gauges[name] = value

    def get_summary(self) -> dict:
        """获取指标摘要"""
        with self._lock:
            uptime = time.time() - self._start_time
            total_requests = sum(v for k, v in self._counters.items() if k.startswith("requests_"))
            error_requests = sum(v for k, v in self._counters.items() if k.startswith("requests_5"))

            avg_duration = 0
            if self._request_metrics:
                durations = [m.duration_ms for m in self._request_metrics[-100:]]
                avg_duration = sum(durations) / len(durations)

            return {
                "uptime_seconds": round(uptime),
                "total_requests": total_requests,
                "error_requests": error_requests,
                "error_rate": round(error_requests / max(total_requests, 1), 4),
                "avg_response_ms": round(avg_duration, 2),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }

    def get_prometheus_format(self) -> str:
        """导出 Prometheus 格式"""
        lines = []
        for name, value in sorted(self._counters.items()):
            lines.append(f"pangu_{name} {value}")
        for name, value in sorted(self._gauges.items()):
            lines.append(f"pangu_{name} {value}")
        uptime = time.time() - self._start_time
        lines.append(f"pangu_uptime_seconds {int(uptime)}")
        return "\n".join(lines)


# ── 启动校验 ──


class StartupValidator:
    """启动校验器"""

    def __init__(self):
        self._checks: list[tuple[str, callable, str]] = []

    def check(self, name: str, func, description: str = ""):
        self._checks.append((name, func, description))

    def validate(self) -> tuple[bool, list[dict]]:
        results = []
        all_ok = True

        for name, func, desc in self._checks:
            try:
                ok = func()
                results.append({"check": name, "status": "ok" if ok else "fail", "description": desc})
                if not ok:
                    all_ok = False
            except Exception as e:
                results.append({"check": name, "status": "error", "description": desc, "error": str(e)})
                all_ok = False

        return all_ok, results


def default_startup_checks() -> StartupValidator:
    """默认启动校验"""
    validator = StartupValidator()

    validator.check("python_version", lambda: __import__("sys").version_info >= (3, 10), "Python >= 3.10")

    validator.check("data_dir", lambda: Path.home().joinpath(".pangu").exists(), "~/.pangu 目录存在")

    validator.check("config_file", lambda: Path.home().joinpath(".pangu/config.json").exists(), "配置文件存在")

    validator.check(
        "drawers_file", lambda: Path.home().joinpath(".pangu/palace/drawers.json").exists(), "记忆数据文件存在"
    )

    validator.check(
        "onnx_model", lambda: any(Path.home().joinpath(".cache/pangu/onnx").rglob("*.onnx")), "ONNX 嵌入模型可用"
    )

    return validator


# ── 优雅关闭 ──


class GracefulShutdown:
    """优雅关闭管理器"""

    def __init__(self):
        self._shutdown_event = threading.Event()
        self._cleanup_hooks: list[callable] = []
        self._is_shutting_down = False

    def register_cleanup(self, hook: callable):
        self._cleanup_hooks.append(hook)

    def request_shutdown(self, signum=None, frame=None):
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger = logging.getLogger("pangu.shutdown")
        logger.info(f"收到关闭信号 {signum}，开始优雅关闭...")

        for hook in self._cleanup_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"清理钩子执行失败: {e}")

        self._shutdown_event.set()
        logger.info("优雅关闭完成")

    def is_shutting_down(self) -> bool:
        return self._is_shutting_down

    def wait(self, timeout: float = 30.0) -> bool:
        return self._shutdown_event.wait(timeout)

    def install_signal_handlers(self):
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)


_shutdown_manager = GracefulShutdown()


def get_shutdown_manager() -> GracefulShutdown:
    return _shutdown_manager


# ── 环境检查 ──


def check_environment() -> dict:
    """检查运行环境"""
    checks = {
        "python": {
            "version": __import__("sys").version,
            "executable": __import__("sys").executable,
        },
        "memory": {},
        "disk": {},
        "pangu": {},
    }

    # 内存
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemTotal" in line:
                    kb = int(line.split()[1])
                    checks["memory"]["total_mb"] = round(kb / 1024)
                elif "MemAvailable" in line:
                    kb = int(line.split()[1])
                    checks["memory"]["available_mb"] = round(kb / 1024)
    except Exception:
        pass

    # 磁盘
    try:
        stat = os.statvfs(str(Path.home()))
        checks["disk"]["free_gb"] = round(stat.f_bavail * stat.f_frsize / (1024**3), 1)
    except Exception:
        pass

    # 盘古
    pangu_dir = Path.home() / ".pangu"
    checks["pangu"]["data_dir_exists"] = pangu_dir.exists()
    if pangu_dir.exists():
        drawers = pangu_dir / "palace" / "drawers.json"
        if drawers.exists():
            import json as _json

            try:
                data = _json.loads(drawers.read_text())
                checks["pangu"]["memory_count"] = len(data)
            except Exception:
                pass

    return checks
