"""盘古健康检查系统（伏羲移植）"""
import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("pangu")
except Exception:
    __version__ = "0.1.0"

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
    """快速健康检查（<10ms）"""
    return {
        "status": "ok",
        "version": __version__,
        "uptime_seconds": round(time.time() - _start_time),
        "timestamp": time.time(),
    }


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
    """检查嵌入服务健康状态"""
    try:
        es = get_embedding_service()
        stats = es.stats if hasattr(es, "stats") else {}
        test_vec = es.embed("health check")
        return {"status": "ok" if test_vec and len(test_vec) > 0 else "empty", **stats}
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
