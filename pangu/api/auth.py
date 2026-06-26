"""
盘古 — 双鉴权模块 (API Key + JWT)
========================================

提供：
  • 密码哈希（bcrypt）
  • JWT 颁发/验证（HS256，支持 access + refresh 双 token）
  • UserStore：用户密码与 refresh token 撤销表
  • 凭据校验：API Key 或 JWT 二选一通过

使用示例：
    >>> from pangu.api.auth import UserStore, create_access_token, verify_credentials
    >>> users = UserStore({"admin": "$2b$12$..."})
    >>> users.verify("admin", "secret")      # True / False
    >>> token = create_access_token("admin", scope="read write")
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import PyJWTError

from pangu.core.config import config

logger = logging.getLogger("pangu.api.auth")


# ──────────────────────────────────────────────
# 异常
# ──────────────────────────────────────────────
class AuthError(Exception):
    """鉴权失败基类"""

    def __init__(self, message: str = "Unauthorized", code: str = "auth_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


class InvalidCredentialsError(AuthError):
    code = "invalid_credentials"


class TokenExpiredError(AuthError):
    code = "token_expired"


class TokenInvalidError(AuthError):
    code = "token_invalid"


# ──────────────────────────────────────────────
# 密码哈希
# ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希（cost=12）"""
    if not plain:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。空密码或格式错误返回 False。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ──────────────────────────────────────────────
# 密钥管理
# ──────────────────────────────────────────────
def load_or_create_secret(secret_file: str | Path) -> str:
    """从文件加载 JWT 密钥；不存在则生成一个并持久化。"""
    path = Path(secret_file)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    path.parent.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_urlsafe(48)
    path.write_text(new_secret, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows 不支持
    return new_secret


# ──────────────────────────────────────────────
# JWT 颁发/验证
# ──────────────────────────────────────────────
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


@dataclass
class TokenClaims:
    sub: str
    type: str
    jti: str
    iat: int
    exp: int
    scope: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "sub": self.sub,
            "type": self.type,
            "jti": self.jti,
            "iat": self.iat,
            "exp": self.exp,
        }
        if self.scope:
            d["scope"] = self.scope
        if self.extra:
            d.update(self.extra)
        return d


def _encode(
    claims: TokenClaims,
    secret: str,
    algorithm: str = "HS256",
) -> str:
    return jwt.encode(claims.to_dict(), secret, algorithm=algorithm)


def _decode(token: str, secret: str, algorithm: str = "HS256") -> TokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Token expired") from e
    except PyJWTError as e:
        raise TokenInvalidError(f"Invalid token: {e}") from e

    return TokenClaims(
        sub=payload.get("sub", ""),
        type=payload.get("type", ""),
        jti=payload.get("jti", ""),
        iat=int(payload.get("iat", 0)),
        exp=int(payload.get("exp", 0)),
        scope=payload.get("scope", ""),
        extra={k: v for k, v in payload.items() if k not in {"sub", "type", "jti", "iat", "exp", "scope"}},
    )


def issue_token_pair(
    user_id: str,
    secret: str,
    *,
    access_ttl: int = 3600,
    refresh_ttl: int = 7 * 86400,
    scope: str = "",
    role: str = "",
    tenant_id: str = "default",
    department: str = "",
    clearance: int = 0,
    groups: list | None = None,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """颁发 access + refresh token 对。

    Returns:
        {
          "access_token": "...",
          "refresh_token": "...",
          "token_type": "bearer",
          "expires_in": 3600,
          "scope": "...",
          "role": "...",
          "tenant_id": "...",
        }
    """
    now = int(time.time())
    access_extra: dict = {
        "role": role,
        "tenant_id": tenant_id,
        "department": department,
        "clearance": clearance,
        "groups": list(groups or []),
    }
    refresh_extra: dict = {
        "tenant_id": tenant_id,
        "department": department,
    }
    access = TokenClaims(
        sub=user_id,
        type=TOKEN_TYPE_ACCESS,
        jti=uuid.uuid4().hex,
        iat=now,
        exp=now + access_ttl,
        scope=scope,
        extra=access_extra,
    )
    refresh = TokenClaims(
        sub=user_id,
        type=TOKEN_TYPE_REFRESH,
        jti=uuid.uuid4().hex,
        iat=now,
        exp=now + refresh_ttl,
        extra=refresh_extra,
    )
    return {
        "access_token": _encode(access, secret, algorithm),
        "refresh_token": _encode(refresh, secret, algorithm),
        "token_type": "bearer",
        "expires_in": access_ttl,
        "scope": scope,
        "role": role,
        "tenant_id": tenant_id,
        "department": department,
        "clearance": clearance,
        "groups": list(groups or []),
        "refresh_expires_in": refresh_ttl,
    }


def verify_token(
    token: str,
    secret: str,
    *,
    expected_type: str = TOKEN_TYPE_ACCESS,
    algorithm: str = "HS256",
) -> TokenClaims:
    """验证 token 签名、过期、类型。失败抛 AuthError。"""
    claims = _decode(token, secret, algorithm)
    if claims.type != expected_type:
        raise TokenInvalidError(f"Expected {expected_type} token, got {claims.type}")
    return claims


# ──────────────────────────────────────────────
# UserStore：用户密码 + refresh token 撤销
# ──────────────────────────────────────────────
class UserStore:
    """轻量用户存储（SQLite 持久化）。

    参数:
        users:        dict[username, bcrypt_hash] 或 {username: plain}（仅用于初始化）
        revoked_jtis: 已撤销的 refresh token jti 集合（运行期维护）
        persist_path: 撤销表持久化文件（可选）
    """

    def __init__(
        self,
        users: dict[str, str] | None = None,
        *,
        persist_path: str | Path | None = None,
    ):
        self._users: dict[str, str] = {}
        self._revoked: set[str] = set()
        self._persist_path = Path(persist_path) if persist_path else None
        self._db_path = Path(config.palace_path) / "users.db"

        # 初始化 SQLite
        self._init_db()

        # 加载已有用户
        self._load_users_from_db()

        if users:
            for username, value in users.items():
                if not username or not value:
                    continue
                # 自动检测：bcrypt 哈希以 $2 开头
                if value.startswith(("$2a$", "$2b$", "$2y$")):
                    self._users[username] = value
                    self._save_user_to_db(username, value)
                else:
                    # 视为明文，自动哈希
                    hashed = hash_password(value)
                    self._users[username] = hashed
                    self._save_user_to_db(username, hashed)

        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text(encoding="utf-8"))
                self._revoked = set(data.get("revoked", []))
            except (json.JSONDecodeError, OSError):
                self._revoked = set()

    def _init_db(self) -> None:
        """初始化用户表"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
        finally:
            conn.close()

        # 清理旧测试数据
        if self._db_path.exists():
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                conn.execute("DELETE FROM users WHERE password_hash = 'test_hash'")
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    def _load_users_from_db(self) -> None:
        """从数据库加载用户"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                rows = conn.execute("SELECT username, password_hash FROM users").fetchall()
                for username, password_hash in rows:
                    self._users[username] = password_hash
            finally:
                conn.close()
        except Exception:
            pass

    def _save_user_to_db(self, username: str, password_hash: str) -> None:
        """保存用户到数据库"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, password_hash, datetime.now().isoformat()),
                )
                conn.commit()
                logger.debug(f"User saved to DB: {username}")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to save user to DB: {e}")

    # ── 密码 ──
    def add_user(self, username: str, password_hash: str) -> None:
        self._users[username] = password_hash
        self._save_user_to_db(username, password_hash)

    def verify(self, username: str, password: str) -> bool:
        h = self._users.get(username)
        if not h:
            return False
        return verify_password(password, h)

    def has_user(self, username: str) -> bool:
        return username in self._users

    def list_users(self) -> list[str]:
        return sorted(self._users.keys())

    # ── refresh token 撤销 ──
    def revoke(self, jti: str) -> None:
        self._revoked.add(jti)
        self._persist()

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    def _persist(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps({"revoked": sorted(self._revoked)}, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                self._persist_path.chmod(0o600)
            except OSError:
                pass
        except OSError:
            pass  # 持久化失败不应阻塞主流程


# ──────────────────────────────────────────────
# 双鉴权统一入口
# ──────────────────────────────────────────────
@dataclass
class AuthResult:
    """鉴权结果"""

    ok: bool
    method: str = ""  # "api_key" | "jwt" | "anonymous"
    user_id: str = ""  # 凭据对应的用户（JWT 模式下为 sub）
    claims: TokenClaims | None = None
    reason: str = ""


def verify_credentials(
    *,
    headers: dict[str, str],
    api_key: str = "",
    secret: str = "",
    algorithm: str = "HS256",
    user_store: UserStore | None = None,
) -> AuthResult:
    """统一鉴权：先看 X-API-Key（或 Authorization: Bearer <key>），再看 JWT。

    Args:
        headers: 小写化的 header 字典
        api_key: 服务端配置的 API Key；空表示不启用 API Key 鉴权
        secret: JWT 签名密钥；空表示不启用 JWT 鉴权
        user_store: 用于校验 refresh token 是否被撤销
    """
    if not api_key and not secret:
        return AuthResult(ok=True, method="anonymous")

    api_key_provided = headers.get("x-api-key", "")
    auth_header = headers.get("authorization", "")
    bearer = ""
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()

    # ── 1) API Key 路径 ──
    # X-API-Key 或 Authorization: Bearer <key> 形式
    # 修复：api_key 有值时，同时接受 X-API-Key 和 Authorization: Bearer <key>
    # 原逻辑要求 api_key and secret 同时有值才处理 bearer，导致只配 api_key 时 Bearer 格式被忽略
    bearer_candidate = bearer if api_key and not _looks_like_jwt(bearer) else ""
    candidate = api_key_provided or bearer_candidate
    if api_key and candidate and hmac.compare_digest(candidate, api_key):
        return AuthResult(ok=True, method="api_key", user_id="api_key_user")

    # ── 2) JWT 路径 ──
    if secret and bearer and _looks_like_jwt(bearer):
        try:
            claims = verify_token(bearer, secret, algorithm=algorithm)
        except TokenExpiredError as e:
            return AuthResult(ok=False, reason=e.message)
        except TokenInvalidError as e:
            return AuthResult(ok=False, reason=e.message)

        if user_store and user_store.is_revoked(claims.jti):
            return AuthResult(ok=False, reason="Token revoked")

        if claims.exp <= int(time.time()):
            return AuthResult(ok=False, reason="Token expired")

        return AuthResult(ok=True, method="jwt", user_id=claims.sub, claims=claims)

    return AuthResult(ok=False, reason="Missing or invalid credentials")


def _looks_like_jwt(s: str) -> bool:
    """粗略判断是否是 JWT（两段 .，三段 Base64URL）。"""
    if not s or len(s) < 10 or s.count(".") != 2:
        return False
    head, _, _ = s.partition(".")
    return bool(head)


__all__ = [
    "AuthError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "TokenInvalidError",
    "UserStore",
    "TokenClaims",
    "hash_password",
    "verify_password",
    "load_or_create_secret",
    "issue_token_pair",
    "verify_token",
    "verify_credentials",
    "AuthResult",
    "TOKEN_TYPE_ACCESS",
    "TOKEN_TYPE_REFRESH",
]
