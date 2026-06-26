"""盘古 RBAC 角色权限测试"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── 测试夹具：构造带角色的 app ──
@pytest.fixture
def role_app(tmp_path, monkeypatch):
    """带 RBAC 配置的 FastAPI app。"""
    monkeypatch.setenv("PANGU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PANGU_JWT_DEFAULT_PASSWORD", "admin-pass-123")  # 显式启用 JWT
    monkeypatch.setenv(
        "PANGU_JWT_USERS",
        '{"admin":"admin-pass-123","alice":"alice-pass-456","viewer1":"viewer-pass-789"}',
    )
    monkeypatch.setenv(
        "PANGU_JWT_USER_ROLES",
        '{"admin":"admin","alice":"operator","viewer1":"viewer"}',
    )
    from pangu.api.server import create_app
    from pangu.core.config import config

    # 重新加载 config 让 env var 生效
    config.__init__()
    app = create_app()
    return app, config


@pytest.fixture
def role_client(role_app):
    app, _ = role_app
    return TestClient(app)


def _login(client, username, password):
    r = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password},
    )
    return r


# ──────────────────────────────────────────────
# 单元测试：纯函数
# ──────────────────────────────────────────────
class TestScopeParsing:
    def test_parse_string(self):
        from pangu.api.rbac import parse_scope

        assert parse_scope("a b c") == {"a", "b", "c"}
        assert parse_scope("") == set()

    def test_parse_list(self):
        from pangu.api.rbac import parse_scope

        assert parse_scope(["a", "b"]) == {"a", "b"}

    def test_parse_none(self):
        from pangu.api.rbac import parse_scope

        assert parse_scope(None) == set()


class TestScopeCheck:
    def test_exact_match(self):
        from pangu.api.rbac import has_scope

        assert has_scope("memories:read", "memories:read")

    def test_no_match(self):
        from pangu.api.rbac import has_scope

        assert not has_scope("memories:read", "memories:write")

    def test_super_wildcard(self):
        from pangu.api.rbac import has_scope

        assert has_scope("*", "anything:here")
        assert has_scope(["*"], "x")

    def test_resource_wildcard(self):
        from pangu.api.rbac import has_scope

        assert has_scope("memories:*", "memories:read")
        assert has_scope("memories:*", "memories:delete")
        assert not has_scope("memories:*", "search:query")

    def test_empty_denied(self):
        from pangu.api.rbac import has_scope

        assert not has_scope("", "memories:read")
        assert not has_scope(None, "memories:read")


class TestRoleResolution:
    def test_builtin_admin(self):
        from pangu.api.rbac import ROLE_PRESETS, resolve_scopes

        scopes = resolve_scopes("admin", role_map=ROLE_PRESETS)
        assert "*" in scopes

    def test_builtin_operator(self):
        from pangu.api.rbac import ROLE_PRESETS, resolve_scopes

        scopes = resolve_scopes("operator", role_map=ROLE_PRESETS)
        assert "memories:read" in scopes
        assert "memories:write" in scopes
        assert "memories:delete" in scopes
        assert "engines:run" in scopes
        assert "*" not in scopes

    def test_builtin_viewer(self):
        from pangu.api.rbac import ROLE_PRESETS, resolve_scopes

        scopes = resolve_scopes("viewer", role_map=ROLE_PRESETS)
        assert "memories:read" in scopes
        assert "search:query" in scopes
        assert "memories:write" not in scopes
        assert "memories:delete" not in scopes

    def test_custom_role_override(self):
        from pangu.api.rbac import resolve_scopes

        custom = {"custom_role": ["foo:read", "foo:write"]}
        scopes = resolve_scopes("custom_role", role_map=custom)
        assert scopes == {"foo:read", "foo:write"}


# ──────────────────────────────────────────────
# HTTP 集成测试
# ──────────────────────────────────────────────
class TestHTTPRBAC:
    def test_login_returns_role_and_scopes(self, role_client):
        r = _login(role_client, "alice", "alice-pass-456")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["role"] == "operator"
        assert "memories:read" in data["scope"]
        assert "memories:write" in data["scope"]
        assert "engines:run" in data["scope"]

    def test_admin_login_has_wildcard(self, role_client):
        r = _login(role_client, "admin", "admin-pass-123")
        data = r.json()["data"]
        assert data["role"] == "admin"
        assert "*" in data["scope"]

    def test_viewer_login_readonly(self, role_client):
        r = _login(role_client, "viewer1", "viewer-pass-789")
        data = r.json()["data"]
        assert data["role"] == "viewer"
        assert "memories:read" in data["scope"]
        assert "memories:write" not in data["scope"]
        assert "memories:delete" not in data["scope"]

    def test_me_returns_principal_info(self, role_client):
        token = _login(role_client, "alice", "alice-pass-456").json()["data"]["access_token"]
        r = role_client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["username"] == "alice"
        assert data["role"] == "operator"
        assert "memories:read" in data["scopes"]

    def test_whoami_admin(self, role_client):
        token = _login(role_client, "admin", "admin-pass-123").json()["data"]["access_token"]
        r = role_client.get("/api/v2/rbac/whoami", headers={"Authorization": f"Bearer {token}"})
        data = r.json()["data"]
        assert data["is_admin"] is True
        assert data["role"] == "admin"

    def test_admin_only_admin_can_access(self, role_client):
        admin_tok = _login(role_client, "admin", "admin-pass-123").json()["data"]["access_token"]
        alice_tok = _login(role_client, "alice", "alice-pass-456").json()["data"]["access_token"]
        viewer_tok = _login(role_client, "viewer1", "viewer-pass-789").json()["data"]["access_token"]

        # admin 通行
        r = role_client.get("/api/v2/rbac/admin-only", headers={"Authorization": f"Bearer {admin_tok}"})
        assert r.status_code == 200

        # operator/viewer 被拒
        for tok in (alice_tok, viewer_tok):
            r = role_client.get("/api/v2/rbac/admin-only", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 403
            body = r.json()
            assert body["code"] == 403
            assert "admin:*" in body["data"]["required"]
            assert "*" not in body["data"]["granted"]

    def test_api_key_default_service_role(self, tmp_path, monkeypatch):
        """API Key 鉴权默认赋 service 角色（含 memories:read+write+engines:run，但不含 admin）。"""
        monkeypatch.setenv("PANGU_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("PANGU_API_KEY", "sk-test-123456")
        monkeypatch.setenv("PANGU_JWT_DEFAULT_PASSWORD", "")  # 关掉 JWT
        from pangu.api.server import create_app
        from pangu.core.config import config

        config.__init__()
        app = create_app()
        client = TestClient(app)

        r = client.get("/api/v2/rbac/whoami", headers={"X-API-Key": "sk-test-123456"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["method"] == "api_key"
        assert data["role"] == "service"
        assert "memories:read" in data["scopes"]
        assert "engines:run" in data["scopes"]
        assert data["is_admin"] is False

        # 验证无法访问 admin 端点
        r2 = client.get("/api/v2/rbac/admin-only", headers={"X-API-Key": "sk-test-123456"})
        assert r2.status_code == 403

    def test_unauthenticated_request_denied(self, role_client):
        """未提供凭证应返回 401（_AuthMiddleware）。"""
        r = role_client.get("/api/v2/rbac/whoami")
        assert r.status_code == 401


# ──────────────────────────────────────────────
# 角色变更
# ──────────────────────────────────────────────
class TestRoleChange:
    def test_principal_scopes_contain_role_permissions(self, role_client):
        token = _login(role_client, "alice", "alice-pass-456").json()["data"]["access_token"]
        r = role_client.get("/api/v2/rbac/whoami", headers={"Authorization": f"Bearer {token}"})
        scopes = r.json()["data"]["scopes"]
        # operator 角色应包含完整 memories:* + engines:run
        assert "memories:read" in scopes
        assert "memories:write" in scopes
        assert "memories:delete" in scopes
        assert "engines:run" in scopes
        assert "system:read" in scopes

    def test_refresh_preserves_role(self, role_client):
        login = _login(role_client, "alice", "alice-pass-456")
        refresh = login.json()["data"]["refresh_token"]
        r = role_client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200
        new_data = r.json()["data"]
        assert new_data["role"] == "operator"
        assert "memories:write" in new_data["scope"]
