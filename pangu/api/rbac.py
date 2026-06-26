"""
盘古 — RBAC 角色权限模型
========================================

提供：
  • 内置角色：admin / operator / viewer / service
  • 权限 scope 字符串（如 `memories:read`，通配符 `*`）
  • 角色 → 权限映射
  • 权限检查装饰器 / 依赖

权限命名约定：`<resource>:<action>`
  - memories:read / memories:write / memories:delete
  - search:query
  - engines:run
  - system:read / system:configure
  - auth:manage
  - admin:*     (admin 角色专属通配)

使用：
    from pangu.api.rbac import ROLE_PRESETS, requires_scope, has_scope, Role

    @app.get("/api/v2/memories")
    @requires_scope("memories:read")
    async def list_memories(): ...
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import wraps

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

# ──────────────────────────────────────────────
# 角色定义
# ──────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"
ROLE_SERVICE = "service"  # 用于 API Key 用户

# 内置角色的默认权限集
ROLE_PRESETS: dict[str, list[str]] = {
    ROLE_ADMIN: ["*"],  # 超级权限
    ROLE_OPERATOR: [
        "memories:read",
        "memories:write",
        "memories:delete",
        "search:query",
        "engines:run",
        "system:read",
    ],
    ROLE_VIEWER: [
        "memories:read",
        "search:query",
        "system:read",
    ],
    ROLE_SERVICE: [
        "memories:read",
        "memories:write",
        "search:query",
        "engines:run",
        "system:read",
    ],
}


# ──────────────────────────────────────────────
# 权限检查
# ──────────────────────────────────────────────
def parse_scope(scope: str | Iterable[str] | None) -> set[str]:
    """把 'a b c' / ['a','b','c'] / None 统一为 set。"""
    if not scope:
        return set()
    if isinstance(scope, str):
        return set(scope.split())
    return set(scope)


def has_scope(granted: Iterable[str] | str | None, required: str) -> bool:
    """检查 granted scopes 是否包含 required。

    支持：
      - 精确匹配
      - 资源通配：`memories:*` 匹配 `memories:read`
      - 超级通配：`*` 匹配所有
    """
    granted_set = parse_scope(granted)
    if not granted_set:
        return False
    if "*" in granted_set:
        return True
    if required in granted_set:
        return True
    # 资源通配：memories:* 覆盖 memories:read
    resource_prefix = required.split(":", 1)[0] + ":*"
    if resource_prefix in granted_set:
        return True
    return False


def has_any_scope(granted: Iterable[str] | str | None, required: Iterable[str]) -> bool:
    """检查 granted 是否至少含 required 中一项。"""
    for r in required:
        if has_scope(granted, r):
            return True
    return False


def has_all_scopes(granted: Iterable[str] | str | None, required: Iterable[str]) -> bool:
    """检查 granted 是否包含 required 的全部。"""
    for r in required:
        if not has_scope(granted, r):
            return False
    return True


# ──────────────────────────────────────────────
# 角色 → 权限解析
# ──────────────────────────────────────────────
def resolve_scopes(
    user_role: str | None,
    extra_scopes: Iterable[str] | str | None = None,
    role_map: dict[str, list[str]] | None = None,
) -> set[str]:
    """根据角色和额外权限返回最终 scope 集合。"""
    role_map = role_map or ROLE_PRESETS
    scopes: set[str] = set()
    if user_role and user_role in role_map:
        scopes.update(role_map[user_role])
    if extra_scopes:
        scopes.update(parse_scope(extra_scopes))
    return scopes


# ──────────────────────────────────────────────
# FastAPI 依赖
# ──────────────────────────────────────────────
@dataclass
class Principal:
    """当前请求的主体（用户/服务）。"""

    user_id: str
    method: str  # "jwt" | "api_key" | "anonymous"
    role: str = ""
    scopes: set[str] = field(default_factory=set)
    claims: object = None  # TokenClaims | None

    def has_scope(self, required: str) -> bool:
        return has_scope(self.scopes, required)

    def is_admin(self) -> bool:
        return ROLE_ADMIN in {self.role} or "*" in self.scopes


def get_principal(request: Request) -> Principal:
    """从 ASGI scope 提取由 AuthMiddleware 注入的鉴权信息。"""
    auth = request.scope.get("state", {}).get("auth", {}) or {}
    user_id = auth.get("user_id", "anonymous")
    method = auth.get("method", "anonymous")
    claims = auth.get("claims")
    role = ""
    scopes: set[str] = set()

    if method == "jwt" and claims is not None:
        role = getattr(claims, "extra", {}).get("role", "")
        token_scopes = getattr(claims, "scope", "")
        scopes = parse_scope(token_scopes)
        # 若 token 没带 role 字段但带了 scope，回填 role 推断
        if not role and "*" in scopes:
            role = ROLE_ADMIN
    elif method == "api_key":
        # API Key 默认赋予 service 角色权限
        role = ROLE_SERVICE
        scopes = set(ROLE_PRESETS.get(ROLE_SERVICE, []))

    # admin 用户总是拥有 *
    if role == ROLE_ADMIN and "*" not in scopes:
        scopes.add("*")

    return Principal(
        user_id=user_id,
        method=method,
        role=role,
        scopes=scopes,
        claims=claims,
    )


def require_scope(*required_scopes: str, require_all: bool = True):
    """FastAPI 依赖：检查当前请求的 principal 是否具备所需 scope。

    用法：
        @app.get("/api/v2/memories")
        async def list_memories(_: Principal = Depends(require_scope("memories:read"))):
            ...
    """
    required = list(required_scopes)

    def _dep(request: Request) -> Principal:
        principal = get_principal(request)
        if principal.method == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": 401, "message": "Authentication required", "data": None},
                headers={"WWW-Authenticate": 'Bearer realm="pangu"'},
            )
        if require_all:
            ok = has_all_scopes(principal.scopes, required)
        else:
            ok = has_any_scope(principal.scopes, required)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 403,
                    "message": f"Forbidden: missing scope ({', '.join(required)})",
                    "data": {"required": required, "granted": sorted(principal.scopes)},
                },
            )
        return principal

    return _dep


# ──────────────────────────────────────────────
# 同步装饰器（用于纯 ASGI 中间件）
# ──────────────────────────────────────────────
def requires_scope(*required_scopes: str, require_all: bool = True):
    """装饰器：用于包装 FastAPI 路由函数（与 require_scope 依赖等效）。"""
    required = list(required_scopes)

    def deco(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if request is None:
                return JSONResponse(
                    status_code=500,
                    content={"code": 500, "message": "Request not found in scope", "data": None},
                )
            principal = get_principal(request)
            if principal.method == "anonymous":
                return JSONResponse(
                    status_code=401,
                    content={"code": 401, "message": "Authentication required", "data": None},
                    headers={"WWW-Authenticate": 'Bearer realm="pangu"'},
                )
            if require_all:
                ok = has_all_scopes(principal.scopes, required)
            else:
                ok = has_any_scope(principal.scopes, required)
            if not ok:
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": 403,
                        "message": f"Forbidden: missing scope ({', '.join(required)})",
                        "data": {"required": required, "granted": sorted(principal.scopes)},
                    },
                )
            # 把 principal 注入 kwargs 便于路由使用
            kwargs["principal"] = principal
            return await func(*args, **kwargs)

        return wrapper

    return deco


__all__ = [
    "ROLE_ADMIN",
    "ROLE_OPERATOR",
    "ROLE_VIEWER",
    "ROLE_SERVICE",
    "ROLE_PRESETS",
    "Principal",
    "has_scope",
    "has_any_scope",
    "has_all_scopes",
    "parse_scope",
    "resolve_scopes",
    "get_principal",
    "require_scope",
    "requires_scope",
]
