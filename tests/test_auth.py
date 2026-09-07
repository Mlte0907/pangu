"""
盘古 — 双鉴权 (API Key + JWT) 单元测试
==============================================
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from pangu.api.auth import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    TokenExpiredError,
    TokenInvalidError,
    UserStore,
    hash_password,
    issue_token_pair,
    load_or_create_secret,
    verify_credentials,
    verify_password,
    verify_token,
)


# ─────────────────────────────────────
# 1) 密码哈希
# ─────────────────────────────────────
class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_password("hello world")
        assert h.startswith(("$2a$", "$2b$", "$2y$"))
        assert verify_password("hello world", h)
        assert not verify_password("wrong", h)

    def test_empty_password(self):
        with pytest.raises(ValueError):
            hash_password("")
        assert not verify_password("", "$2b$12$abcdef")

    def test_invalid_hash_format(self):
        assert not verify_password("anything", "not-a-bcrypt-hash")


# ─────────────────────────────────────
# 2) 密钥加载/创建
# ─────────────────────────────────────
class TestSecretManagement:
    def test_create_and_persist(self, tmp_path: Path):
        f = tmp_path / ".jwt_secret"
        s1 = load_or_create_secret(f)
        assert len(s1) >= 32
        s2 = load_or_create_secret(f)
        assert s1 == s2  # 复用

    def test_empty_file_regen(self, tmp_path: Path):
        f = tmp_path / ".jwt_secret"
        f.write_text("")
        s = load_or_create_secret(f)
        assert len(s) >= 32

    def test_permissions(self, tmp_path: Path):
        f = tmp_path / ".jwt_secret"
        load_or_create_secret(f)
        if f.exists():
            mode = f.stat().st_mode & 0o777
            # Windows/某些 fs 可能不严格；只检查 Unix 场景
            if mode != 0:
                assert mode == 0o600


# ─────────────────────────────────────
# 3) JWT 颁发/验证
# ─────────────────────────────────────
class TestJWTTokens:
    SECRET = "unit-test-secret-key"

    def test_issue_and_verify_access(self):
        pair = issue_token_pair("alice", self.SECRET, access_ttl=60, refresh_ttl=3600)
        assert pair["token_type"] == "bearer"
        assert pair["expires_in"] == 60
        assert pair["access_token"] and pair["refresh_token"]

        claims = verify_token(pair["access_token"], self.SECRET, expected_type=TOKEN_TYPE_ACCESS)
        assert claims.sub == "alice"
        assert claims.type == TOKEN_TYPE_ACCESS
        assert claims.exp > int(time.time())

    def test_access_cannot_be_used_as_refresh(self):
        pair = issue_token_pair("bob", self.SECRET)
        with pytest.raises(TokenInvalidError):
            verify_token(pair["access_token"], self.SECRET, expected_type=TOKEN_TYPE_REFRESH)

    def test_refresh_cannot_be_used_as_access(self):
        pair = issue_token_pair("bob", self.SECRET)
        with pytest.raises(TokenInvalidError):
            verify_token(pair["refresh_token"], self.SECRET, expected_type=TOKEN_TYPE_ACCESS)

    def test_expired_token(self):
        pair = issue_token_pair("bob", self.SECRET, access_ttl=1, refresh_ttl=1)
        time.sleep(1.5)
        with pytest.raises(TokenExpiredError):
            verify_token(pair["access_token"], self.SECRET)

    def test_tampered_signature(self):
        pair = issue_token_pair("bob", self.SECRET)
        bad = pair["access_token"][:-4] + "XXXX"
        with pytest.raises(TokenInvalidError):
            verify_token(bad, self.SECRET)

    def test_wrong_secret(self):
        pair = issue_token_pair("bob", self.SECRET)
        with pytest.raises(TokenInvalidError):
            verify_token(pair["access_token"], "different-secret")

    def test_scope_propagation(self):
        pair = issue_token_pair("bob", self.SECRET, scope="read write admin")
        claims = verify_token(pair["access_token"], self.SECRET)
        assert claims.scope == "read write admin"


# ─────────────────────────────────────
# 4) UserStore
# ─────────────────────────────────────
class TestUserStore:
    def test_plain_password_auto_hash(self):
        s = UserStore({"alice": "secret123"})
        assert s.has_user("alice")
        assert s.verify("alice", "secret123")
        assert not s.verify("alice", "wrong")

    def test_pre_hashed_password(self):
        h = hash_password("secret123")
        s = UserStore({"alice": h})
        assert s.verify("alice", "secret123")

    def test_unknown_user(self):
        s = UserStore({})
        assert not s.verify("nobody", "x")

    def test_revoke_and_persist(self, tmp_path: Path):
        f = tmp_path / "revoked.json"
        s = UserStore({"alice": "x"}, persist_path=f)
        s.revoke("jti-1")
        assert s.is_revoked("jti-1")

        # 重新加载
        s2 = UserStore({}, persist_path=f)
        assert s2.is_revoked("jti-1")

    def test_persist_invalid_file_ignored(self, tmp_path: Path):
        f = tmp_path / "revoked.json"
        f.write_text("not valid json{")
        s = UserStore({}, persist_path=f)
        assert not s.is_revoked("anything")


# ─────────────────────────────────────
# 5) 双鉴权统一入口
# ─────────────────────────────────────
class TestVerifyCredentials:
    SECRET = "test-secret-abc"
    API_KEY = "test-api-key-xyz"

    def test_anonymous_when_nothing_configured(self):
        r = verify_credentials(headers={}, api_key="", secret="")
        assert r.ok
        assert r.method == "anonymous"

    def test_api_key_via_x_api_key_header(self):
        r = verify_credentials(
            headers={"x-api-key": self.API_KEY},
            api_key=self.API_KEY,
            secret=self.SECRET,
        )
        assert r.ok
        assert r.method == "api_key"

    def test_api_key_wrong(self):
        r = verify_credentials(
            headers={"x-api-key": "wrong"},
            api_key=self.API_KEY,
            secret=self.SECRET,
        )
        assert not r.ok
        assert "Invalid" in r.reason or "credentials" in r.reason.lower()

    def test_jwt_via_bearer(self):
        pair = issue_token_pair("alice", self.SECRET)
        r = verify_credentials(
            headers={"authorization": f"Bearer {pair['access_token']}"},
            api_key="",
            secret=self.SECRET,
        )
        assert r.ok
        assert r.method == "jwt"
        assert r.user_id == "alice"
        assert r.claims is not None
        assert r.claims.sub == "alice"

    def test_jwt_expired(self):
        pair = issue_token_pair("alice", self.SECRET, access_ttl=1)
        time.sleep(1.5)
        r = verify_credentials(
            headers={"authorization": f"Bearer {pair['access_token']}"},
            api_key="",
            secret=self.SECRET,
        )
        assert not r.ok

    def test_jwt_revoked_via_userstore(self, tmp_path: Path):
        pair = issue_token_pair("alice", self.SECRET)
        store = UserStore({}, persist_path=tmp_path / "r.json")
        from pangu.api.auth import _decode

        c = _decode(pair["access_token"], self.SECRET)
        store.revoke(c.jti)
        r = verify_credentials(
            headers={"authorization": f"Bearer {pair['access_token']}"},
            api_key="",
            secret=self.SECRET,
            user_store=store,
        )
        assert not r.ok

    def test_both_api_key_and_jwt_configured_accept_either(self):
        # API key 优先
        r1 = verify_credentials(
            headers={"x-api-key": self.API_KEY},
            api_key=self.API_KEY,
            secret=self.SECRET,
        )
        assert r1.method == "api_key"

        # JWT 也接受
        pair = issue_token_pair("alice", self.SECRET)
        r2 = verify_credentials(
            headers={"authorization": f"Bearer {pair['access_token']}"},
            api_key=self.API_KEY,
            secret=self.SECRET,
        )
        assert r2.method == "jwt"

    def test_no_credentials_when_required(self):
        r = verify_credentials(
            headers={},
            api_key=self.API_KEY,
            secret=self.SECRET,
        )
        assert not r.ok

    def test_garbage_bearer_rejected(self):
        r = verify_credentials(
            headers={"authorization": "Bearer not.a.jwt"},
            api_key="",
            secret=self.SECRET,
        )
        assert not r.ok


# ─────────────────────────────────────
# 6) HTTP 端到端（FastAPI TestClient）
# ─────────────────────────────────────
@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    """构造一个临时配置 + TestClient。"""
    from fastapi.testclient import TestClient

    from pangu.api import server as srv_mod
    from pangu.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.config, "base_dir", tmp_path, raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_secret_file", str(tmp_path / ".jwt"), raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_default_user", "testadmin", raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_default_password", "test-pass-123", raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_users", {}, raising=False)
    monkeypatch.setattr(cfg_mod.config, "api_key", "TEST_API_KEY_42", raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_access_ttl", 60, raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_refresh_ttl", 3600, raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_algorithm", "HS256", raising=False)

    # 重新构造 app
    app = srv_mod.create_app()
    return TestClient(app), app


class TestHTTPAuth:
    def test_health_open_without_auth(self, test_client):
        client, _ = test_client
        r = client.get("/health")
        assert r.status_code in (200, 503)

    def test_no_api_key_when_required_returns_401(self, test_client):
        client, _ = test_client
        r = client.get("/api/v2/system/info")
        assert r.status_code == 401
        assert r.headers.get("www-authenticate", "").lower().startswith("bearer")

    def test_api_key_passes(self, test_client):
        client, _ = test_client
        r = client.get(
            "/api/v2/system/info",
            headers={"X-API-Key": "TEST_API_KEY_42"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["auth"]["api_key_configured"] is True
        assert body["data"]["auth"]["jwt_configured"] is True

    def test_login_wrong_password(self, test_client):
        client, _ = test_client
        r = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "wrong"})
        assert r.status_code == 401
        assert "Invalid" in r.json()["message"]

    def test_login_success(self, test_client):
        client, _ = test_client
        r = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "test-pass-123"})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 0
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"

    def test_me_with_jwt(self, test_client):
        client, _ = test_client
        login = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "test-pass-123"})
        token = login.json()["data"]["access_token"]

        r = client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["username"] == "testadmin"

    def test_me_with_api_key_rejected(self, test_client):
        client, _ = test_client
        r = client.get("/api/v2/auth/me", headers={"X-API-Key": "TEST_API_KEY_42"})
        assert r.status_code == 401  # /me 必须是 JWT

    def test_refresh_token_rotation(self, test_client):
        client, _ = test_client
        login = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "test-pass-123"})
        refresh = login.json()["data"]["refresh_token"]

        r = client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200
        new_pair = r.json()["data"]
        assert new_pair["refresh_token"] != refresh  # 旋转

        # 旧 refresh 不应再可用
        r2 = client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 401

    def test_jwt_protected_endpoint(self, test_client):
        client, _ = test_client
        # 错误 token
        r = client.get("/api/v2/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

        # 正确 token
        login = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "test-pass-123"})
        token = login.json()["data"]["access_token"]
        r = client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_logout_revokes_token(self, test_client):
        client, _ = test_client
        login = client.post("/api/v2/auth/login", json={"username": "testadmin", "password": "test-pass-123"})
        access = login.json()["data"]["access_token"]
        refresh = login.json()["data"]["refresh_token"]

        # 带上 refresh_token 一起撤销
        r = client.post(
            "/api/v2/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
            json={"refresh_token": refresh},
        )
        assert r.status_code == 200
        assert r.json()["data"]["revoked"] == 2

        # refresh 不可再用
        r2 = client.post("/api/v2/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 401
