"""盘古 REST API 路由 — /api/v2/admin/keys（钥匙管理）

红线：管理能力绝不暴露为 MCP 工具。
鉴权：admin secret（~/.pangu/.admin_secret, 0600）+ X-Admin-Key header。
房间钥匙无管理权限（双重隔离）。
"""

import hashlib
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("pangu.api.routes_keys")

router = APIRouter(tags=["admin-keys"])

# admin secret 路径
_ADMIN_SECRET_PATH = Path.home() / ".pangu" / ".admin_secret"


def _ensure_admin_secret() -> str:
    """确保 admin secret 存在（首次自动生成）"""
    if _ADMIN_SECRET_PATH.exists():
        return _ADMIN_SECRET_PATH.read_text().strip()
    secret = secrets.token_urlsafe(32)
    _ADMIN_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ADMIN_SECRET_PATH.write_text(secret)
    _ADMIN_SECRET_PATH.chmod(0o600)
    logger.info(f"admin secret 已生成: {_ADMIN_SECRET_PATH}")
    return secret


def _verify_admin(request: Request) -> bool:
    """验证 X-Admin-Key header（常量时间比较）"""
    admin_key = request.headers.get("X-Admin-Key", "")
    if not admin_key:
        return False
    secret = _ensure_admin_secret()
    return secrets.compare_digest(admin_key, secret)


class KeyCreateRequest(BaseModel):
    room: str = Field(..., description="房间名")
    scope: str = Field(default="readwrite", description="权限: readwrite/readonly/admin")


class KeyRevokeRequest(BaseModel):
    key_id: str = Field(..., description="钥匙 ID")


class KeyRekeyRequest(BaseModel):
    room: str = Field(..., description="房间名")


@router.post("/admin/keys")
async def create_key(req: KeyCreateRequest, request: Request):
    """创建钥匙（需 admin 凭据）"""
    if not _verify_admin(request):
        # 房间钥匙（能通过 KeyManager.verify 的）→ 403
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            from pangu.keys import KeyManager

            km = KeyManager()
            if km.verify(api_key):
                return {"error": "房间钥匙无管理权限", "code": 403}
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.keys import KeyManager

    km = KeyManager()
    record = km.create(room=req.room, scope=req.scope)
    return {
        "key_id": record["key_id"],
        "room": record["room"],
        "scope": record["scope"],
        "key": record["key"],
    }


@router.get("/admin/keys")
async def list_keys(request: Request, include_revoked: bool = False):
    """列出所有钥匙"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.keys import KeyManager

    km = KeyManager()
    return {"keys": km.list_keys(include_revoked=include_revoked)}


@router.post("/admin/keys/revoke")
async def revoke_key(req: KeyRevokeRequest, request: Request):
    """吊销钥匙"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.keys import KeyManager

    km = KeyManager()
    if km.revoke(req.key_id):
        return {"ok": True, "key_id": req.key_id}
    else:
        return {"error": f"未找到钥匙: {req.key_id}", "code": 404}


@router.post("/admin/rooms/{room}/rekey")
async def rekey_room(room: str, request: Request):
    """重发钥匙：吊销该房间所有活跃钥匙，创建新钥匙并返回明文（仅此一次）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.keys import KeyManager

    km = KeyManager()
    all_keys = km.list_keys(include_revoked=False)
    room_keys = [k for k in all_keys if k.get("room") == room]

    # 吊销所有活跃钥匙
    revoked = []
    for k in room_keys:
        if km.revoke(k["key_id"]):
            revoked.append(k["key_id"])

    # 用原 scope 创建新钥匙（默认 readwrite）
    scope = room_keys[0]["scope"] if room_keys else "readwrite"
    new_record = km.create(room=room, scope=scope)

    return {
        "ok": True,
        "room": room,
        "revoked": revoked,
        "key_id": new_record["key_id"],
        "key": new_record["key"],
    }


@router.get("/admin/stats")
async def admin_stats(request: Request):
    """全局统计（管理视角）：记忆/宫殿等数字**不做租户裁剪**。

    面板（盘古标签页概览、侧栏卡片的「记忆」）要显示全库规模；而 /mcp 的 pangu_stats
    自 P1-3 收口后按调用方租户裁剪，只显示本租户那一份。与其给 MCP 开一个「谁都能要
    全局」的后门，不如走本模块的管理通道 —— admin secret（0600）+ X-Admin-Key，且该
    凭据只在插件后端读取，前端 JS 永不接触（见 dsh-pangu/lib/index.js）。
    """
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.routes_tools import _get_server
    from pangu.server.handlers.system import collect_stats

    return collect_stats(_get_server())


@router.get("/admin/rooms")
async def list_rooms(request: Request):
    """房间总览：按 tenant_id 聚合记忆条数、字符体积、钥匙数"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from collections import Counter

    from pangu.core.config import PanguConfig
    from pangu.keys import KeyManager
    from pangu.memory.drawer_storage import JsonDrawerStorage

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers = JsonDrawerStorage(str(cfg.authoritative_drawers_path)).load()
    km = KeyManager()
    all_keys = km.list_keys(include_revoked=True)

    # 按 tenant_id 聚合
    room_data: dict[str, dict] = {}
    for d in drawers:
        tid = (d.metadata or {}).get("tenant_id", "default") if isinstance(d.metadata, dict) else "default"
        if tid not in room_data:
            room_data[tid] = {"room": tid, "memory_count": 0, "chars": 0, "last_write_at": None}
        room_data[tid]["memory_count"] += 1
        room_data[tid]["chars"] += len(d.content or "")
        cat = d.created_at or ""
        if cat > (room_data[tid]["last_write_at"] or ""):
            room_data[tid]["last_write_at"] = cat

    # 补钥匙数（只算未吊销的）
    key_counts = Counter(k["room"] for k in all_keys if not k.get("revoked_at"))

    # 有钥匙但没有记忆的房间也要出现：例如刚入住、还没写入过记忆的平台房间
    # （实测 dsh 房间此前因为 0 条记忆而完全不显示）。房间列表取两侧的并集。
    for room in key_counts:
        room_data.setdefault(room, {"room": room, "memory_count": 0, "chars": 0, "last_write_at": None})

    for room, data in room_data.items():
        data["key_count"] = key_counts.get(room, 0)

    # 未分房的记忆单独列出
    if "none" in room_data:
        room_data["none"]["room"] = "(unmigrated)"

    # 排序：记忆多的在前，其次钥匙多的，最后按名字；便于 UI 直接按顺序渲染
    rooms = sorted(
        room_data.values(),
        key=lambda r: (-r.get("memory_count", 0), -r.get("key_count", 0), str(r.get("room", ""))),
    )
    return {"rooms": rooms}


@router.get("/admin/public-memories")
async def list_public_memories(request: Request):
    """公共区知识卡片：visibility=public 的记忆，只读"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.core.config import PanguConfig
    from pangu.memory.drawer_storage import JsonDrawerStorage
    from pangu.memory.encryption import decrypt, is_enabled

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers = JsonDrawerStorage(str(cfg.authoritative_drawers_path)).load()

    public = []
    for d in drawers:
        md = d.metadata if isinstance(d.metadata, dict) else {}
        vis = md.get("visibility")
        if vis != "public":
            continue
        tid = md.get("tenant_id", "default")
        # 摘要（本轮补）：加密条目此前在面板只显示"（加密内容）"四个字，信息量为零。
        # 这里给一个可读摘要 —— 优先写入者提供的 facts，否则**解密正文**后截断
        # （管理端点已有 admin 鉴权，返回明文属预期；面板是管理 UI）。
        summary = str(md.get("facts") or "").strip()
        body = d.content or ""
        encrypted = body.startswith("gAAAAA")
        if not summary:
            text = body
            if encrypted and is_enabled():
                try:
                    text = decrypt(body)
                except Exception:
                    text = ""
            summary = " ".join(str(text).split())[:120]
        public.append(
            {
                "id": d.id,
                "content": body,  # 保留原字段：面板据它盖章（是否加密）
                "summary": summary,
                "encrypted": encrypted,
                "wing": d.wing,
                "importance": getattr(d, "importance", None),
                "tags": d.tags or [],
                "source_wing": d.wing,
                "source_room": tid or d.room,
                "graduated_at": md.get("graduated_at"),
                "created_at": d.created_at,
                "chars": len(body),
            }
        )

    # 按 graduated_at 降序
    public.sort(key=lambda x: x.get("graduated_at") or x.get("created_at") or "", reverse=True)
    return {"memories": public, "count": len(public)}
