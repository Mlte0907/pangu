"""盘古 ABAC 多租户测试"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pangu.api.abac import (
    Effect,
    Policy,
    RequestContext,
    Resource,
    Rule,
    Subject,
    clear_policies,
    evaluate,
    load_policies_from_config,
    policy_from_dict,
    register_builtin_policies,
    register_policy,
)


# ──────────────────────────────────────────────
# 单元测试：纯函数
# ──────────────────────────────────────────────
class TestSubjectFromPrincipal:
    def test_default_tenant(self):
        from pangu.api.rbac import Principal

        p = Principal(user_id="alice", method="jwt", role="operator", scopes={"memories:read"})
        s = Subject.from_principal(p)
        assert s.user_id == "alice"
        assert s.role == "operator"
        assert s.tenant_id == "default"
        assert s.clearance == 0


class TestRuleEvaluation:
    def test_empty_condition_always_matches(self):
        rule = Rule(effect=Effect.ALLOW, description="")
        ctx = RequestContext(
            subject=Subject(user_id="x"),
            action="read",
            resource=Resource(type="memories"),
        )
        assert rule.matches(ctx)

    def test_simple_expression(self):
        rule = Rule(Effect.ALLOW, condition='act == "read"')
        ctx_read = RequestContext(subject=Subject(user_id="x"), action="read", resource=Resource(type="m"))
        ctx_write = RequestContext(subject=Subject(user_id="x"), action="write", resource=Resource(type="m"))
        assert rule.matches(ctx_read)
        assert not rule.matches(ctx_write)

    def test_attribute_check(self):
        rule = Rule(Effect.ALLOW, condition="r.tenant_id == s.tenant_id")
        s = Subject(user_id="alice", tenant_id="acme")
        r1 = Resource(type="m", tenant_id="acme")
        r2 = Resource(type="m", tenant_id="other")
        ctx1 = RequestContext(subject=s, action="read", resource=r1)
        ctx2 = RequestContext(subject=s, action="read", resource=r2)
        assert rule.matches(ctx1)
        assert not rule.matches(ctx2)


class TestPolicyRegistration:
    def test_register_and_clear(self):
        clear_policies()
        register_policy(Policy(name="test", rules=[Rule(Effect.ALLOW)]))
        assert any(p.name == "test" for p in __import__("pangu.api.abac", fromlist=["get_policies"]).get_policies())
        clear_policies()
        assert __import__("pangu.api.abac", fromlist=["get_policies"]).get_policies() == []

    def test_priority_order(self):
        clear_policies()
        register_policy(Policy(name="low", priority=999, rules=[Rule(Effect.DENY)]))
        register_policy(Policy(name="high", priority=1, rules=[Rule(Effect.ALLOW)]))
        policies = __import__("pangu.api.abac", fromlist=["get_policies"]).get_policies()
        assert policies[0].name == "high"
        clear_policies()


class TestPolicyFromDict:
    def test_minimal(self):
        p = policy_from_dict({"name": "x", "rules": [{"effect": "allow"}]})
        assert p.name == "x"
        assert p.priority == 100
        assert len(p.rules) == 1
        assert p.rules[0].effect == Effect.ALLOW

    def test_full(self):
        p = policy_from_dict(
            {
                "name": "y",
                "priority": 50,
                "rules": [
                    {"effect": "deny", "description": "t1", "condition": 'act == "admin"'},
                    {"effect": "allow", "description": "t2"},
                ],
            }
        )
        assert p.priority == 50
        assert p.rules[0].condition == 'act == "admin"'


class TestDecisionEngine:
    def setup_method(self):
        clear_policies()
        register_builtin_policies()

    def teardown_method(self):
        clear_policies()

    def test_admin_full_allow(self):
        ctx = RequestContext(
            subject=Subject(user_id="admin", is_admin=True),
            action="read",
            resource=Resource(type="m", tenant_id="t1"),
        )
        d = evaluate(ctx)
        assert d.allowed is True
        assert d.policy == "admin_full"

    def test_tenant_isolation_blocks(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1"),
            action="read",
            resource=Resource(type="m", tenant_id="t2", visibility="tenant"),
        )
        d = evaluate(ctx)
        assert d.allowed is False
        assert d.policy == "tenant_isolation"

    def test_same_tenant_visibility_allow(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1"),
            action="read",
            resource=Resource(type="m", tenant_id="t1", visibility="tenant"),
        )
        d = evaluate(ctx)
        assert d.allowed is True

    def test_owner_allow(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1"),
            action="write",
            resource=Resource(type="m", tenant_id="t1", owner_id="alice", visibility="private"),
        )
        d = evaluate(ctx)
        assert d.allowed is True
        assert d.policy == "owner_or_admin"

    def test_classification_blocks(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1", clearance=1),
            action="read",
            resource=Resource(type="m", tenant_id="t1", classification=3, visibility="tenant"),
        )
        d = evaluate(ctx)
        assert d.allowed is False
        assert d.policy == "classification_based"

    def test_classification_pass(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1", clearance=3),
            action="read",
            resource=Resource(type="m", tenant_id="t1", classification=2, visibility="tenant"),
        )
        d = evaluate(ctx)
        assert d.allowed is True

    def test_public_resource_allow(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1"),
            action="read",
            resource=Resource(type="m", tenant_id="other", visibility="public", classification=0),
        )
        d = evaluate(ctx)
        assert d.allowed is True
        assert d.policy == "public_resource"

    def test_default_deny(self):
        ctx = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1"),
            action="write",
            resource=Resource(type="m", tenant_id="t1", owner_id="bob", visibility="private"),
        )
        d = evaluate(ctx)
        assert d.allowed is False
        # default_deny 来自 evaluate() 兜底分支
        assert d.policy == ""  # fallback
        assert "默认拒绝" in d.reason or "无 allow" in d.reason


class TestCustomPolicy:
    def setup_method(self):
        clear_policies()
        register_builtin_policies()

    def teardown_method(self):
        clear_policies()

    def test_department_based_allow(self):
        """自定义策略：研发部门可写本租户的资源。"""
        load_policies_from_config(
            [
                {
                    "name": "rd_can_write_own_tenant",
                    "priority": 25,  # 高于 tenant_isolation
                    "rules": [
                        {
                            "effect": "allow",
                            "description": "研发部写本租户",
                            "condition": 's.department == "rd" and r.tenant_id == s.tenant_id and act in ("write", "read", "delete")',
                        },
                    ],
                }
            ]
        )
        # rd 写本租户：rd 策略先 allow，tenant_isolation 不会 deny（同租户），owner 也没匹配
        # 应允许
        ctx1 = RequestContext(
            subject=Subject(user_id="alice", tenant_id="t1", department="rd"),
            action="write",
            resource=Resource(type="m", tenant_id="t1", owner_id="bob", visibility="private"),
        )
        d1 = evaluate(ctx1)
        assert d1.allowed is True
        assert d1.policy == "rd_can_write_own_tenant"


# ──────────────────────────────────────────────
# HTTP 集成测试
# ──────────────────────────────────────────────
@pytest.fixture
def abac_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PANGU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PANGU_JWT_DEFAULT_PASSWORD", "admin-pass-xyz")
    monkeypatch.setenv(
        "PANGU_JWT_USERS",
        json.dumps({"admin": "admin-pass-xyz", "alice": "alice-pwd", "bob": "bob-pwd"}),
    )
    monkeypatch.setenv(
        "PANGU_JWT_USER_ROLES",
        json.dumps({"admin": "admin", "alice": "operator", "bob": "operator"}),
    )
    monkeypatch.setenv(
        "PANGU_ABAC_USER_ATTRS",
        json.dumps(
            {
                "admin": {"tenant_id": "acme", "clearance": 3, "department": "ops", "groups": ["admins"]},
                "alice": {"tenant_id": "acme", "clearance": 1, "department": "rd", "groups": ["dev"]},
                "bob": {"tenant_id": "globex", "clearance": 2, "department": "sales", "groups": ["sales"]},
            }
        ),
    )
    from pangu.api.server import create_app
    from pangu.core.config import config

    config.__init__()
    app = create_app()
    return app, config


@pytest.fixture
def abac_client(abac_app):
    app, _ = abac_app
    return TestClient(app)


def _login(client, username, password):
    return client.post("/api/v2/auth/login", json={"username": username, "password": password})


class TestHTTPABAC:
    def test_login_embeds_tenant_and_clearance(self, abac_client):
        r = _login(abac_client, "alice", "alice-pwd")
        data = r.json()["data"]
        assert data["tenant_id"] == "acme"
        assert data["clearance"] == 1
        assert data["department"] == "rd"
        assert "dev" in data["groups"]

    def test_whoami_shows_abac_attrs(self, abac_client):
        tok = _login(abac_client, "alice", "alice-pwd").json()["data"]["access_token"]
        r = abac_client.get("/api/v2/abac/whoami", headers={"Authorization": f"Bearer {tok}"})
        data = r.json()["data"]
        assert data["tenant_id"] == "acme"
        assert data["clearance"] == 1
        assert data["department"] == "rd"
        assert data["is_admin"] is False

    def test_admin_whoami(self, abac_client):
        tok = _login(abac_client, "admin", "admin-pass-xyz").json()["data"]["access_token"]
        r = abac_client.get("/api/v2/abac/whoami", headers={"Authorization": f"Bearer {tok}"})
        data = r.json()["data"]
        assert data["is_admin"] is True
        assert data["tenant_id"] == "acme"

    def test_same_tenant_access_allowed(self, abac_client):
        """alice@acme 访问 acme 租户的资源 → 放行（tenant_visibility）。"""
        tok = _login(abac_client, "alice", "alice-pwd").json()["data"]["access_token"]
        r = abac_client.get(
            "/api/v2/abac/tenants/acme/memories/123",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["tenant_id"] == "acme"

    def test_cross_tenant_blocked(self, abac_client):
        """alice@acme 访问 globex 租户的资源 → 拒绝（tenant_isolation）。"""
        tok = _login(abac_client, "alice", "alice-pwd").json()["data"]["access_token"]
        r = abac_client.get(
            "/api/v2/abac/tenants/globex/memories/999",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 403
        body = r.json()
        assert body["code"] == 403
        assert "tenant_isolation" in body["data"]["policy"]
        assert body["data"]["subject"]["tenant_id"] == "acme"
        assert body["data"]["resource"]["tenant_id"] == "globex"

    def test_admin_cross_tenant_allowed(self, abac_client):
        """admin 跨租户访问 → 放行（admin_full）。"""
        tok = _login(abac_client, "admin", "admin-pass-xyz").json()["data"]["access_token"]
        r = abac_client.get(
            "/api/v2/abac/tenants/globex/memories/999",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["policy"] == "admin_full"

    def test_unauth_request_rejected(self, abac_client):
        """未鉴权 → 401。"""
        r = abac_client.get("/api/v2/abac/tenants/acme/memories/123")
        assert r.status_code == 401


class TestABACPolicyReload:
    def test_config_policies_loaded(self, abac_app):
        """通过 PANGU_ABAC_POLICIES 配置加载自定义策略。"""
        import os

        from pangu.core.config import config

        # 在 fixture 创建的 app 之外加新策略
        os.environ["PANGU_ABAC_POLICIES"] = json.dumps(
            [
                {
                    "name": "rd_global_read",
                    "priority": 35,  # 排在 tenant_isolation 之后
                    "rules": [
                        {
                            "effect": "allow",
                            "description": "rd 部门可读所有租户",
                            "condition": 's.department == "rd" and act == "read"',
                        }
                    ],
                }
            ]
        )
        config.__init__()
        clear_policies()
        register_builtin_policies()
        load_policies_from_config(config.abac_policies)

        # 验证 bob(sales, globex) 跨租户读 acme 仍被拒（不在 rd 部门 → tenant_isolation 命中）
        ctx1 = RequestContext(
            subject=Subject(user_id="bob", tenant_id="globex", department="sales"),
            action="read",
            resource=Resource(type="m", tenant_id="acme", visibility="tenant"),
        )
        d1 = evaluate(ctx1)
        assert d1.allowed is False
        assert d1.policy == "tenant_isolation"

        # alice(rd, acme) 跨租户读 globex：deny 优先于 allow
        ctx2 = RequestContext(
            subject=Subject(user_id="alice", tenant_id="acme", department="rd"),
            action="read",
            resource=Resource(type="m", tenant_id="globex", visibility="tenant"),
        )
        # tenant_isolation deny → rd_global_read allow 被跳过
        d2 = evaluate(ctx2)
        assert d2.allowed is False
        assert d2.policy == "tenant_isolation"
