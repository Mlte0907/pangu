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
