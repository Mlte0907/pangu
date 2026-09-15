"""盘古 REST API 路由 — /api/v2/admin/keys（钥匙管理）

红线：管理能力绝不暴露为 MCP 工具。
本路由用 verify_credentials 保护，不在豁免清单内。
"""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("pangu.api.routes_keys")

router = APIRouter(tags=["admin-keys"])


class KeyCreateRequest(BaseModel):
    room: str = Field(..., description="房间名")
    scope: str = Field(default="readwrite", description="权限: readwrite/readonly/admin")


class KeyRevokeRequest(BaseModel):
    key_id: str = Field(..., description="钥匙 ID")


@router.post("/admin/keys")
async def create_key(req: KeyCreateRequest, request: Request):
    """创建钥匙（需 admin 凭据）"""
    # 验证 admin 凭据（不在豁免清单）
    from pangu.api.auth import verify_credentials
    from pangu.keys import KeyManager

    try:
        verify_credentials(request)
    except Exception:
        from pangu.api.abac import ApiResponse

        return ApiResponse.error(401, "需要 admin 凭据")

    km = KeyManager()
    record = km.create(room=req.room, scope=req.scope)
    return {
        "key_id": record["key_id"],
        "room": record["room"],
        "scope": record["scope"],
        "key": record["key"],  # 明文只此一次
    }


@router.get("/admin/keys")
async def list_keys(request: Request, include_revoked: bool = False):
    """列出所有钥匙"""
    from pangu.api.auth import verify_credentials

    try:
        verify_credentials(request)
    except Exception:
        from pangu.api.abac import ApiResponse

        return ApiResponse.error(401, "需要 admin 凭据")

    from pangu.keys import KeyManager

    km = KeyManager()
    return {"keys": km.list_keys(include_revoked=include_revoked)}


@router.post("/admin/keys/revoke")
async def revoke_key(req: KeyRevokeRequest, request: Request):
    """吊销钥匙"""
    from pangu.api.auth import verify_credentials

    try:
        verify_credentials(request)
    except Exception:
        from pangu.api.abac import ApiResponse

        return ApiResponse.error(401, "需要 admin 凭据")

    from pangu.keys import KeyManager

    km = KeyManager()
    if km.revoke(req.key_id):
        return {"ok": True, "key_id": req.key_id}
    else:
        from pangu.api.abac import ApiResponse

        return ApiResponse.error(404, f"未找到钥匙: {req.key_id}")
