"""盘古数据库Schema — 增量迁移系统（伏羲移植）"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("pangu.store.migrations")

Migration = tuple[str, str, dict, dict | None]  # (version, label, forward_op, rollback_op_or_None)

MIGRATIONS: list[Migration] = []


# ── v1: 基础Schema ──
MIGRATIONS.append(
    (
        "v1",
        "Initial schema — 宫殿基础结构",
        {
            "action": "ensure_schema",
            "version": 1,
            "description": "确保 palace_meta.json 基础结构存在",
        },
        None,
    )
)

# ── v2: 记忆索引增强 ──
MIGRATIONS.append(
    (
        "v2",
        "添加 embedding 缓存和 FTS 索引支持",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "embedding_cache": {},
                "fts_index_version": 1,
                "index_stats": {"total_indexed": 0, "last_indexed": None},
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["embedding_cache", "fts_index_version", "index_stats"],
        },
    )
)

# ── v3: 任务追踪 ──
MIGRATIONS.append(
    (
        "v3",
        "添加任务追踪支持",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "task_tracking": {
                    "tasks": [],
                    "last_updated": None,
                },
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["task_tracking"],
        },
    )
)

# ── v4: 用户画像 ──
MIGRATIONS.append(
    (
        "v4",
        "添加用户画像支持",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "user_profile": {
                    "preferences": {},
                    "habits": [],
                    "taboos": [],
                },
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["user_profile"],
        },
    )
)

# ── v5: 模型路由规则 ──
MIGRATIONS.append(
    (
        "v5",
        "添加模型路由规则",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "model_routing": {
                    "rules": [],
                    "default_model": "auto",
                },
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["model_routing"],
        },
    )
)

# ── v6: 经验银行 ──
MIGRATIONS.append(
    (
        "v6",
        "添加经验银行支持",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "experience_bank": {
                    "entries": [],
                    "total_count": 0,
                },
                "skill_registry": {
                    "skills": [],
                    "last_generated": None,
                },
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["experience_bank", "skill_registry"],
        },
    )
)

# ── v7: 软删除支持 ──
MIGRATIONS.append(
    (
        "v7",
        "添加软删除支持",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "deleted_items": [],
                "deletion_log": [],
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["deleted_items", "deletion_log"],
        },
    )
)

# ── v8: 访问计数 ──
MIGRATIONS.append(
    (
        "v8",
        "添加访问计数和记忆分层",
        {
            "action": "add_field",
            "target": "palace_meta",
            "fields": {
                "access_stats": {
                    "total_accesses": 0,
                    "by_wing": {},
                    "by_room": {},
                },
                "memory_tiers": {
                    "A": {"count": 0, "threshold": 0.8},
                    "B": {"count": 0, "threshold": 0.5},
                    "C": {"count": 0, "threshold": 0.0},
                },
            },
        },
        {
            "action": "remove_field",
            "target": "palace_meta",
            "fields": ["access_stats", "memory_tiers"],
        },
    )
)


def _get_palace_meta_path() -> Path:
    """获取宫殿元数据文件路径"""
    base = Path(os.path.expanduser("~/.pangu/palace"))
    return base / "palace_meta.json"


def _current_version() -> str | None:
    """读取当前已应用的版本"""
    meta_path = _get_palace_meta_path()
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("schema_version")
    except Exception:
        return None


def _record_version(meta: dict, version: str) -> None:
    """记录迁移版本"""
    meta["schema_version"] = version
    meta_path = _get_palace_meta_path()
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_meta() -> dict:
    """加载宫殿元数据"""
    meta_path = _get_palace_meta_path()
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    # 初始结构
    return {
        "name": "盘古记忆宫殿",
        "version": "0.1.0",
        "created_at": "",
        "wings": ["default"],
        "rooms": {},
        "tunnels": [],
        "schema_version": None,
    }


def _apply_migration(meta: dict, version: str, label: str, forward_op: dict) -> dict:
    """应用单个迁移"""
    action = forward_op.get("action")
    target = forward_op.get("target")

    if action == "ensure_schema":
        # 确保基础字段存在
        defaults = {
            "name": "盘古记忆宫殿",
            "wings": ["default"],
            "rooms": {},
            "tunnels": [],
            "wing_descriptions": {},
            "room_descriptions": {},
        }
        for k, v in defaults.items():
            meta.setdefault(k, v)

    elif action == "add_field":
        if target == "palace_meta":
            for k, v in forward_op.get("fields", {}).items():
                meta.setdefault(k, v)

    elif action == "remove_field":
        if target == "palace_meta":
            for k in forward_op.get("fields", []):
                meta.pop(k, None)

    return meta


def run_migrations() -> str:
    """按序应用所有未执行的迁移，返回最终版本号"""
    current = _current_version()
    meta = _load_meta()

    def _already_done(ver: str) -> bool:
        if current is None:
            return False
        versions = [m[0] for m in MIGRATIONS]
        if current not in versions:
            return False
        idx_current = versions.index(current)
        idx_target = versions.index(ver)
        return idx_target <= idx_current

    for version, label, forward_op, _rollback in MIGRATIONS:
        if _already_done(version):
            continue
        logger.info(f"Applying migration {version}: {label}")
        try:
            meta = _apply_migration(meta, version, label, forward_op)
            _record_version(meta, version)
            current = version
        except Exception as e:
            logger.error(f"Migration {version} failed: {e}")
            raise

    return current or "none"


def init_db():
    """初始化数据库（幂等）。首次调用时自动运行所有待执行的迁移。"""
    run_migrations()
    _ensure_defaults()


def _ensure_defaults():
    """确保默认数据结构存在"""
    meta = _load_meta()
    meta.setdefault("wings", ["default"])
    meta.setdefault("rooms", {})

    if "default" not in meta.get("rooms", {}):
        meta["rooms"]["default"] = ["general"]

    _record_version(meta, meta.get("schema_version") or "v1")


def get_schema_version() -> str:
    """返回当前 schema 版本"""
    return _current_version() or "none"


def get_available_migrations() -> list[dict]:
    """列出所有已定义的迁移版本"""
    return [{"version": v, "label": lbl, "has_rollback": r is not None} for v, lbl, _, r in MIGRATIONS]
