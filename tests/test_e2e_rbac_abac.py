"""盘古 E2E 联调测试 — RBAC + ABAC + 记忆业务路由

覆盖场景：
- alice (operator@acme) 创建记忆 → 写入时 owner=alice, tenant=acme
- alice 列出记忆 → 看到自己本租户的
- bob (operator@globex) 列出记忆 → 看不到 alice 的（租户隔离）
- bob 跨租户读 alice 的记忆 → 403（tenant_isolation）
- alice 删除自己的记忆 → 200（owner_or_admin）
- bob 删除 alice 的记忆 → 403
- admin 跨租户读 → 200（admin_full）
- alice 写 classification=3 → clearance=1 < 3 → 403（classification_based）
- 公开 visibility 资源 → 跨租户可读
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def e2e_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PANGU_DB_PATH", str(tmp_path))
    monkeypatch.setenv("PANGU_JWT_DEFAULT_PASSWORD", "admin-pwd")
    monkeypatch.setenv(
        "PANGU_JWT_USERS",
        json.dumps({"admin": "admin-pwd", "alice": "alice-pwd", "bob": "bob-pwd", "carol": "carol-pwd"}),
    )
    monkeypatch.setenv(
        "PANGU_JWT_USER_ROLES",
        json.dumps({"admin": "admin", "alice": "operator", "bob": "operator", "carol": "viewer"}),
    )
    monkeypatch.setenv(
        "PANGU_ABAC_USER_ATTRS",
        json.dumps(
            {
                "admin": {"tenant_id": "acme", "clearance": 3, "department": "ops", "groups": ["admins"]},
                "alice": {"tenant_id": "acme", "clearance": 1, "department": "rd", "groups": ["dev"]},
                "bob": {"tenant_id": "globex", "clearance": 2, "department": "sales", "groups": ["sales"]},
                "carol": {"tenant_id": "acme", "clearance": 0, "department": "qa", "groups": ["qa"]},
            }
        ),
    )

    from pangu.api.abac import clear_policies, register_builtin_policies
    from pangu.api.server import create_app
    from pangu.core.config import config

    config.__init__()
    clear_policies()
    register_builtin_policies()
    app = create_app()
    return app, config


@pytest.fixture
def e2e_client(e2e_app):
    from fastapi.testclient import TestClient

    app, _ = e2e_app
    return TestClient(app)


def _login(client, username: str, password: str) -> dict:
    r = client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestMemoryE2E:
    """RBAC + ABAC + 记忆业务路由联调。"""

    def test_alice_creates_and_lists_own_tenant(self, e2e_client):
        tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "alice 的第一条记忆"},
            headers=_h(tok),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["tenant_id"] == "acme"
        assert data["owner_id"] == "alice"
        mid = data["id"]

        r = e2e_client.get("/api/v2/memories", headers=_h(tok))
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(it["id"] == mid for it in items)

    def test_cross_tenant_list_isolated(self, e2e_client):
        # alice 在 acme 写 2 条
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        e2e_client.post("/api/v2/memories", json={"text": "a1"}, headers=_h(a_tok))
        e2e_client.post("/api/v2/memories", json={"text": "a2"}, headers=_h(a_tok))
        # bob 在 globex 写 1 条
        b_tok = _login(e2e_client, "bob", "bob-pwd")["access_token"]
        e2e_client.post("/api/v2/memories", json={"text": "b1"}, headers=_h(b_tok))
        # bob 列不到 alice 的
        r = e2e_client.get("/api/v2/memories", headers=_h(b_tok))
        items = r.json()["data"]["items"]
        assert all((it.get("metadata") or {}).get("tenant_id") == "globex" for it in items)

    def test_cross_tenant_get_blocked(self, e2e_client):
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "secret"},
            headers=_h(a_tok),
        )
        mid = r.json()["data"]["id"]
        b_tok = _login(e2e_client, "bob", "bob-pwd")["access_token"]
        r = e2e_client.get(f"/api/v2/memories/{mid}", headers=_h(b_tok))
        assert r.status_code == 403

    def test_admin_cross_tenant_get_allowed(self, e2e_client):
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "alice-secret"},
            headers=_h(a_tok),
        )
        mid = r.json()["data"]["id"]
        admin_tok = _login(e2e_client, "admin", "admin-pwd")["access_token"]
        r = e2e_client.get(f"/api/v2/memories/{mid}", headers=_h(admin_tok))
        assert r.status_code == 200
        assert r.json()["data"]["_policy"] == "admin_full"

    def test_owner_can_delete_own(self, e2e_client):
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post("/api/v2/memories", json={"text": "tmp"}, headers=_h(a_tok))
        mid = r.json()["data"]["id"]
        r = e2e_client.delete(f"/api/v2/memories/{mid}", headers=_h(a_tok))
        assert r.status_code == 200

    def test_non_owner_cannot_delete(self, e2e_client):
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post("/api/v2/memories", json={"text": "alice"}, headers=_h(a_tok))
        mid = r.json()["data"]["id"]
        b_tok = _login(e2e_client, "bob", "bob-pwd")["access_token"]
        r = e2e_client.delete(f"/api/v2/memories/{mid}", headers=_h(b_tok))
        assert r.status_code == 403

    def test_classification_blocks_low_clearance_writer(self, e2e_client):
        """alice clearance=1 写 classification=3（top_secret）→ 被拒。"""
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "top-secret", "classification": 3, "visibility": "tenant"},
            headers=_h(a_tok),
        )
        assert r.json()["code"] == 403

    def test_classification_allows_equal_clearance(self, e2e_client):
        """bob clearance=2 写 classification=2 → 放行。"""
        b_tok = _login(e2e_client, "bob", "bob-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "bob-conf", "classification": 2, "visibility": "tenant"},
            headers=_h(b_tok),
        )
        assert r.status_code == 200, r.text

    def test_public_resource_readable_cross_tenant(self, e2e_client):
        """alice 写 public → bob 也能读。"""
        a_tok = _login(e2e_client, "alice", "alice-pwd")["access_token"]
        r = e2e_client.post(
            "/api/v2/memories",
            json={"text": "public-info", "visibility": "public"},
            headers=_h(a_tok),
        )
        mid = r.json()["data"]["id"]
        b_tok = _login(e2e_client, "bob", "bob-pwd")["access_token"]
        r = e2e_client.get(f"/api/v2/memories/{mid}", headers=_h(b_tok))
        assert r.status_code == 200
        assert r.json()["data"]["_policy"] == "public_resource"

    def test_unauthenticated_post_rejected(self, e2e_client):
        r = e2e_client.post("/api/v2/memories", json={"text": "x"})
        assert r.json()["code"] == 401
