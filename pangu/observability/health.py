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


def drawer_scope_stats(drawers: list[Any] | None, *, total_tunnels: int = 0) -> dict[str, int]:
    """按同一份可见 drawers 集合统计翼、房间和抽屉数。

    ``pangu_stats`` 与 ``pangu_system_health`` 必须共享这份口径：调用方传入的
    ``drawers`` 已经过 MCP 请求级租户/密级过滤，不能再绕回进程 HOME 去扫描另一套
    遗留目录。空列表是合法结果（该租户确实没有可见记忆），不得回退到全库。
    """
    scoped = list(drawers or [])
    wings = {(getattr(drawer, "wing", None) or "default") for drawer in scoped}
    rooms = {
        (
            (getattr(drawer, "wing", None) or "default"),
            (getattr(drawer, "room", None) or "general"),
        )
        for drawer in scoped
    }
    return {
        "total_wings": len(wings),
        "total_rooms": len(rooms),
        "total_drawers": len(scoped),
        "total_tunnels": int(total_tunnels or 0),
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


def _check_memory_health(
    drawers: list[Any] | None = None,
    config=None,
    total_tunnels: int = 0,
) -> dict[str, Any]:
    """检查记忆存储健康状态。

    MCP handler 会传入本请求已裁剪的 ``drawers``，从而与 ``pangu_stats`` 完全同口径；
    REST/CLI 未传时才通过 ``MemoryStack`` 读取权威 v2 主存（并合并非空 v1 只读源）。

    旧实现固定扫描 ``~/.pangu/palace/<wing>/<room>/*.json``。生产数据早已迁到
    ``db_path/v2_memories/drawers.json`` 单文件格式，因此 v2 有记忆而 health 仍恒报 0。
    """
    try:
        if drawers is None:
            from pangu.core.config import PanguConfig
            from pangu.memory.layers import MemoryStack

            base = config or PanguConfig.load()
            drawers = MemoryStack(
                config=base.authoritative_memory_config(),
                extra_drawers_files=base.authoritative_extra_drawers_files(),
            ).get_drawers()
        return {"status": "ok", **drawer_scope_stats(drawers, total_tunnels=total_tunnels)}
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


def deep_health_check(drawers: list[Any] | None = None, config=None, total_tunnels: int = 0) -> dict:
    """深度健康检查（含宫殿结构/嵌入/记忆统计）。

    ``drawers`` 是 MCP 请求级可见集合；传 ``None`` 时按权威 v2 存储现读。
    """
    checks: dict[str, Any] = {}

    # 宫殿结构完整性
    try:
        checks["structure"] = _check_palace_structure()
    except Exception as e:
        checks["structure"] = {"status": "fail", "errors": [str(e)]}

    # 记忆统计（与 pangu_stats 共用同一份 scoped drawers）
    try:
        checks["memory"] = _check_memory_health(
            drawers=drawers,
            config=config,
            total_tunnels=total_tunnels,
        )
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
