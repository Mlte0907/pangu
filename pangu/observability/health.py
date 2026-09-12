"""盘古健康检查系统（伏羲移植）"""

import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    # 以 pangu.__init__ 的 __version__ 为唯一事实源。
    from pangu import __version__
except Exception:
    # 仅在包本身不可导入时（极罕见：src 布局异常）才退到安装元数据。
    from importlib.metadata import version as _get_version

    __version__ = _get_version("pangu")

from pangu.memory.embedding import get_embedding_service

logger = logging.getLogger("pangu.observability.health")

_start_time = time.time()

# 必需的表/文件及其必需字段
REQUIRED_FILES: dict[str, list[str]] = {
    "palace_meta.json": ["name", "wings", "rooms", "tunnels"],
    "wings.json": [],
    "rooms.json": [],
}


def quick_health_check() -> dict:
    """快速健康检查（<10ms）

    不触发嵌入（保持低成本），只读取**已确定**的后端状态：
    若嵌入服务已降级到 hash，则本接口也必须反映出来——否则监控系统
    轮询这个便宜的端点时会看到恒定的 "ok"，完全错过降级。
    （状态由首次 embed()/启动体检确定；未确定时记 "unknown"，不谎报 ok。）
    """
    status = "ok"
    result: dict[str, Any] = {
        "status": status,
        "version": __version__,
        "uptime_seconds": round(time.time() - _start_time),
        "timestamp": time.time(),
    }

    try:
        es = get_embedding_service()
        backend = getattr(es, "active_backend", None)
        if backend:
            result["embedding_backend"] = backend
        # 仅在状态**已确定且为降级**时才改判，避免把 unknown 当异常
        if backend == "hash":
            result["status"] = "degraded"
            result["embedding_degraded"] = True
    except Exception:
        # 健康检查自身不得抛错
        pass

    return result


def _check_palace_structure() -> dict[str, Any]:
    """检查宫殿文件结构完整性"""
    issues: list[str] = []
    palace_dir = Path(os.path.expanduser("~/.pangu/palace"))

    if not palace_dir.exists():
        return {"status": "fail", "errors": ["palace directory not found"]}

    for filename, required_fields in REQUIRED_FILES.items():
        filepath = palace_dir / filename
        if not filepath.exists():
            if required_fields:
                issues.append(f"missing file: {filename}")
            continue

        if required_fields:
            try:
                import json

                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                for field in required_fields:
                    if field not in data:
                        issues.append(f"missing field in {filename}: {field}")
            except Exception as e:
                issues.append(f"cannot read {filename}: {e}")

    return {"status": "ok" if not issues else "fail", "schema_issues": issues} if issues else {"status": "ok"}


def _check_memory_health() -> dict[str, Any]:
    """检查记忆存储健康状态"""
    palace_dir = Path(os.path.expanduser("~/.pangu/palace"))
    stats = {"total_wings": 0, "total_rooms": 0, "total_drawers": 0}

    try:
        import json

        meta_path = palace_dir / "palace_meta.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            stats["total_wings"] = len(meta.get("wings", []))
            stats["total_rooms"] = sum(len(v) for v in meta.get("rooms", {}).values())
            stats["total_tunnels"] = len(meta.get("tunnels", []))

        # 统计抽屉文件
        for wing_dir in palace_dir.iterdir():
            if wing_dir.is_dir() and not wing_dir.name.startswith("."):
                for room_dir in wing_dir.iterdir():
                    if room_dir.is_dir():
                        drawer_count = len(list(room_dir.glob("*.json")))
                        stats["total_drawers"] += drawer_count

        return {"status": "ok", **stats}
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def _check_embedding_health() -> dict[str, Any]:
    """检查嵌入服务健康状态

    ⚠ 关键：**不能只看"有没有拿到向量"**。
    `_local_embed` 的 hash 向量是合法的 384 维、truthy，`len(vec) > 0` 恒成立，
    所以旧写法 `"ok" if test_vec and len(test_vec) > 0` 在 ONNX 完全失效时
    依然报 `ok`——这正是"静默降级"能长期不被发现的原因。
    现在改为按**实际生效的后端**判定。
    """
    try:
        es = get_embedding_service()
        # 必须先触发一次真实嵌入，再读 stats——ONNX 是惰性加载的，
        # 且 `stats` 是**属性**（每次调用重建 dict），提前读会拿到
        # active_backend="unknown" 的初始快照。顺序反了就永远测不出降级。
        test_vec = es.embed("health check")
        stats = es.stats if hasattr(es, "stats") else {}

        backend = stats.get("active_backend", "unknown")
        degraded = bool(stats.get("degraded"))

        if not test_vec:
            status = "empty"
        elif degraded:
            # 能拿到向量，但它是无语义的 hash 向量——这是**降级**，不是健康
            status = "degraded"
        else:
            status = "ok"

        result: dict[str, Any] = {"status": status, "backend": backend, **stats}
        if degraded:
            result["error"] = (
                f"嵌入后端已降级为 hash 向量，检索结果没有语义能力。原因: {stats.get('degraded_reason', '未知')}"
            )
        return result
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def deep_health_check() -> dict:
    """深度健康检查（含宫殿结构/嵌入/记忆统计）"""
    checks: dict[str, Any] = {}

    # 宫殿结构完整性
    try:
        checks["structure"] = _check_palace_structure()
    except Exception as e:
        checks["structure"] = {"status": "fail", "errors": [str(e)]}

    # 记忆统计
    try:
        checks["memory"] = _check_memory_health()
    except Exception as e:
        checks["memory"] = {"status": "fail", "error": str(e)}

    # 嵌入服务
    try:
        checks["embedding"] = _check_embedding_health()
    except Exception as e:
        checks["embedding"] = {"status": "fail", "error": str(e)}

    structure_ok = isinstance(checks.get("structure"), dict) and checks["structure"].get("status") == "ok"
    embed_ok = isinstance(checks.get("embedding"), dict) and checks["embedding"].get("status") == "ok"

    all_ok = structure_ok and embed_ok

    return {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": round(time.time() - _start_time),
        "checks": checks,
        "timestamp": time.time(),
    }
