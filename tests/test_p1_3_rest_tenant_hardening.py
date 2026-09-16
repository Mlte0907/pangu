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
    assert (
        _resolve_tenant_id(_request({"X-API-Key": "pgk_bogus", "x-tenant-id": "dsh"})) == rm.config.abac_default_tenant
    )


def test_jwt_claim_is_last_resort():
    """无钥匙无声明头 → 用 JWT claim 的 tenant_id。"""
    assert _resolve_tenant_id(_request(jwt_tenant="room-jwt")) == "room-jwt"


# ── REST 凭据统一：verify_credentials 认盘古钥匙（与 MCP 共用一套凭据）──


def test_verify_credentials_accepts_pangu_key(key_room):
    """★ 盘古钥匙成为 REST 的合法凭据，两种头形式都认，并带出租户。"""
    from pangu.api.auth import verify_credentials

    plain, room = key_room
    for headers in ({"x-api-key": plain}, {"authorization": f"Bearer {plain}"}):
        res = verify_credentials(headers=headers)
        assert res.ok is True
        assert res.method == "pangu_key"
        assert res.tenant == room, "租户必须来自钥匙的 room"
        assert res.key_id


def test_verify_credentials_rejects_bogus_pangu_key():
    """形如盘古钥匙但校验失败 → 明确失败（不能被当成匿名放过）。"""
    from pangu.api.auth import verify_credentials

    res = verify_credentials(headers={"x-api-key": "pgk_not_a_real_key"})
    assert res.ok is False
    assert res.method == "pangu_key"
    assert "盘古钥匙" in (res.reason or "")


def test_verify_credentials_anonymous_when_nothing_provided():
    """没配静态 key/JWT 且没带凭据 → 仍是 anonymous（保持既有放行语义）。"""
    from pangu.api.auth import verify_credentials

    res = verify_credentials(headers={})
    assert res.ok is True and res.method == "anonymous"


def test_principal_carries_tenant_from_pangu_key():
    """中间件注入的身份要能被 get_principal 还原出 tenant/key_id，并给 service 角色。"""
    from pangu.api.rbac import ROLE_SERVICE, get_principal

    req = _request()
    req.scope["state"]["auth"] = {
        "method": "pangu_key",
        "user_id": "key_abc",
        "tenant": "room-x",
        "key_id": "key_abc",
    }
    p = get_principal(req)
    assert p.method == "pangu_key"
    assert p.tenant == "room-x"
    assert p.key_id == "key_abc"
    assert p.role == ROLE_SERVICE


def test_middleware_identity_short_circuits_key_lookup(monkeypatch):
    """中间件已确认身份时，路由直接用它的租户，不再重复查钥匙表。"""
    req = _request(headers={"x-tenant-id": "dsh"})  # 带上声明头，但应以身份里的租户为准
    req.scope["state"]["auth"] = {"method": "pangu_key", "user_id": "k", "tenant": "room-x", "key_id": "k"}

    called = {"n": 0}

    def _boom(r):
        called["n"] += 1
        return {}

    monkeypatch.setattr(rm, "_tenant_from_key", _boom)
    assert _resolve_tenant_id(req) == "room-x"
    assert called["n"] == 0, "不应再次查钥匙表"
