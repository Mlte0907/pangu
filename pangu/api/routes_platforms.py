"""盘古 REST API 路由 — /api/v2/platforms（平台接入审核）

提供平台接入 Token 的请求、审核、管理功能。
替代原有的房间/钥匙系统，简化认证流程。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pangu.api.admin_auth import verify_admin as _verify_admin

logger = logging.getLogger("pangu.api.routes_platforms")

router = APIRouter(tags=["platforms"])


class PlatformRequest(BaseModel):
    """平台接入请求"""

    platform: str = Field(..., description="平台标识（如 dsh, mcp, api）")
    platform_name: str = Field(..., description="平台名称（如 DeepSeek Harness）")
    permissions: list[str] = Field(default=["read", "write", "search"], description="请求的权限")


class PlatformApproveRequest(BaseModel):
    """审核通过请求"""

    token_id: str = Field(..., description="Token ID")
    permissions: list[str] | None = Field(default=None, description="授权的权限（可选，不传则使用原请求权限）")


class PlatformRejectRequest(BaseModel):
    """审核拒绝请求"""

    token_id: str = Field(..., description="Token ID")


class PlatformRevokeRequest(BaseModel):
    """撤销接入请求"""

    token_id: str = Field(..., description="Token ID")


@router.post("/platforms/request")
async def request_platform_access(req: PlatformRequest, request: Request):
    """请求平台接入（生成临时 Token，等待审核）"""
    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    request_ip = request.client.host if request.client else ""

    record = manager.request_access(
        platform=req.platform,
        platform_name=req.platform_name,
        request_ip=request_ip,
    )

    return {
        "token_id": record["token_id"],
        "platform": record["platform"],
        "platform_name": record["platform_name"],
        "status": record["status"],
        "token": record["token"],  # 临时 Token，只返回一次
        "message": "接入请求已提交，请等待审核",
    }


@router.get("/platforms/pending")
async def list_pending_platforms(request: Request):
    """获取待审核列表（需 admin 权限）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    pending = manager.get_pending()

    return {"platforms": pending, "count": len(pending)}


@router.post("/platforms/approve")
async def approve_platform(req: PlatformApproveRequest, request: Request):
    """审核通过（需 admin 权限）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    if manager.approve(req.token_id, req.permissions):
        return {"ok": True, "token_id": req.token_id, "status": "active"}
    else:
        return {"error": f"未找到待审核请求: {req.token_id}", "code": 404}


@router.post("/platforms/reject")
async def reject_platform(req: PlatformRejectRequest, request: Request):
    """审核拒绝（需 admin 权限）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    if manager.reject(req.token_id):
        return {"ok": True, "token_id": req.token_id, "status": "revoked"}
    else:
        return {"error": f"未找到待审核请求: {req.token_id}", "code": 404}


@router.get("/platforms")
async def list_platforms(request: Request, include_revoked: bool = False):
    """获取已接入平台列表（需 admin 权限）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    platforms = manager.list_tokens(include_revoked=include_revoked)

    return {"platforms": platforms, "count": len(platforms)}


@router.delete("/platforms/{token_id}")
async def revoke_platform(token_id: str, request: Request):
    """撤销平台接入（需 admin 权限）"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    if manager.revoke(token_id):
        return {"ok": True, "token_id": token_id, "status": "revoked"}
    else:
        return {"error": f"未找到活跃平台: {token_id}", "code": 404}
