"""P1-3 阶段 3：REST 侧租户收口（租户由凭据决定，不能由调用方声明）。

背景（实测漏洞）：`/api/v2/memories` 只要带 `x-tenant-id: dsh` 头就能读到 dsh 的 124 条记忆
（不带则 0）—— 任何本地调用方都能自称任意租户。MCP 侧早已是"租户由钥匙决定"，本测试锁定
REST 侧对齐到同一模型：

  1. 带**盘古钥匙**（X-API-Key / Bearer）→ 钥匙的 room（权威）
  2. 带**admin 凭据** → 允许用声明头代指定租户（管理动作）
  3. 其它情况 → **忽略**声明头（客户端无权声明租户）
  4. 兜底：JWT claim 的 tenant_id → abac_default_tenant
"""

import pytest
from starlette.requests import Request

from pangu.api import routes_memory as rm
from pangu.api.routes_memory import _resolve_tenant_id
from pangu.keys import KeyManager


def _request(headers: dict | None = None, jwt_tenant: str | None = None) -> Request:
    """构造最小 Request（get_principal 从 scope.state.auth 读鉴权信息）。"""
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v2/memories",
        "query_string": b"",
        "headers": raw,
        "client": ("127.0.0.1", 12345),
        "state": {},
    }
    if jwt_tenant is not None:
        class _Claims:
            extra = {"tenant_id": jwt_tenant}
            scope = ""

        scope["state"]["auth"] = {"user_id": "u", "method": "jwt", "claims": _Claims()}
    return Request(scope)


@pytest.fixture
def key_room():
    """在隔离库里造一把真钥匙，返回 (明文, room)。"""
    km = KeyManager()
    created = km.create(room="room-x", scope="readwrite")
    plain = created.get("key") or created.get("api_key") or created.get("plaintext") or ""
    assert plain, f"create() 未返回明文，实际字段: {list(created)}"
    return plain, "room-x"


def test_tenant_comes_from_key(key_room):
    """★ 带钥匙 → 租户由钥匙决定（X-API-Key 与 Bearer 两种形式都要认）。"""
    plain, room = key_room
    assert _resolve_tenant_id(_request({"X-API-Key": plain})) == room
    assert _resolve_tenant_id(_request({"Authorization": f"Bearer {plain}"})) == room


def test_declared_header_is_ignored_without_credentials(monkeypatch):
    """★ 没有凭据时，声明头必须被忽略（这正是实测漏洞的入口）。"""
    monkeypatch.setattr(rm, "_is_admin_request", lambda r: False)
    assert _resolve_tenant_id(_request({"x-tenant-id": "dsh"})) == rm.config.abac_default_tenant


def test_declared_header_honored_for_admin(monkeypatch):
    """admin 凭据存在时允许代指定租户（管理动作，例如面板按租户排查）。"""
    monkeypatch.setattr(rm, "_is_admin_request", lambda r: True)
    assert _resolve_tenant_id(_request({"x-tenant-id": "dsh"})) == "dsh"


def test_invalid_key_falls_back_to_default(monkeypatch):
    """无效钥匙不能成为租户来源，也不能因为带了声明头就生效。"""
    monkeypatch.setattr(rm, "_is_admin_request", lambda r: False)
    assert _resolve_tenant_id(_request({"X-API-Key": "pgk_bogus", "x-tenant-id": "dsh"})) == rm.config.abac_default_tenant


def test_jwt_claim_is_last_resort():
    """无钥匙无声明头 → 用 JWT claim 的 tenant_id。"""
    assert _resolve_tenant_id(_request(jwt_tenant="room-jwt")) == "room-jwt"
