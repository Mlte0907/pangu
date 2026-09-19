"""盘古平台接入 Token 管理

提供平台接入 Token 的生成、验证、审核功能。
替代原有的房间/钥匙系统，简化认证流程。
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pangu.api.platform_tokens")

# 并发保护：approve/reject/revoke/verify 都是「读整个 JSON → 改 → 写回」，
# 无锁时并发请求会互相覆盖（丢审批、丢吊销）。verify 由每个已接入请求触发，
# 是最热路径，必须与写操作共用同一把锁。
_TOKENS_LOCK = threading.RLock()

# last_used_at 落盘节流间隔（秒）：verify 是每请求都跑的，没必要每次都写盘。
_LAST_USED_PERSIST_INTERVAL = 60.0


def _hash_token(token: str) -> str:
    """SHA-256 哈希 Token"""
    return hashlib.sha256(token.encode()).hexdigest()


def _gen_token() -> str:
    """生成 pgp_ 前缀 + 32 字节 base64url Token"""
    raw = secrets.token_urlsafe(32)
    return f"pgp_{raw}"


class PlatformTokenManager:
    """平台接入 Token 管理器"""

    def __init__(self, tokens_path: str = None):
        if tokens_path is None:
            try:
                from pangu.core.config import PanguConfig
                self.tokens_path = Path(PanguConfig.load().base_dir) / "platform_tokens.json"
            except Exception:
                self.tokens_path = Path.home() / ".pangu" / "platform_tokens.json"
        else:
            self.tokens_path = Path(tokens_path)
        self._ensure_file()

    def _ensure_file(self):
        """确保 tokens.json 存在且权限正确"""
        if not self.tokens_path.exists():
            self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
            self._write([])
            self.tokens_path.chmod(0o600)
        else:
            current = oct(self.tokens_path.stat().st_mode)[-3:]
            if current != "600":
                self.tokens_path.chmod(0o600)

    def _read(self) -> list[dict]:
        try:
            with open(self.tokens_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except json.JSONDecodeError as e:
            # ⚠ 此前与 FileNotFoundError 一起静默返回 []：一次 JSON 损坏会让**全部
            # token 瞬间消失**（所有已接入平台被登出），且没有任何日志。损坏必须显式
            # 告警；返回 [] 只是为了让调用方能继续，但不能无声。
            logger.error(f"platform_tokens.json 解析失败（已按空处理，请检查文件）: {e}")
            return []

    def _write(self, tokens: list[dict]):
        tmp = self.tokens_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.tokens_path)
        self.tokens_path.chmod(0o600)

    def request_access(self, platform: str, platform_name: str, request_ip: str = "") -> dict:
        """请求接入（生成临时 Token，等待审核）"""
        token = _gen_token()
        record = {
            "token_id": f"ptok_{secrets.token_hex(8)}",
            "platform": platform,
            "platform_name": platform_name,
            "token_hash": _hash_token(token),
            "permissions": ["read", "write", "search"],
            "status": "pending",  # pending / active / revoked
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_used_at": None,
            "revoked_at": None,
            "approved_at": None,
            "request_ip": request_ip,
        }
        with _TOKENS_LOCK:
            tokens = self._read()
            tokens.append(record)
            self._write(tokens)
        # 临时 Token 只在请求时返回一次
        record["token"] = token
        return record

    def approve(self, token_id: str, permissions: list[str] = None) -> bool:
        """审核通过"""
        with _TOKENS_LOCK:
            tokens = self._read()
            for t in tokens:
                if t["token_id"] == token_id and t["status"] == "pending":
                    t["status"] = "active"
                    t["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    if permissions:
                        t["permissions"] = permissions
                    self._write(tokens)
                    return True
        return False

    def reject(self, token_id: str) -> bool:
        """审核拒绝"""
        with _TOKENS_LOCK:
            tokens = self._read()
            for t in tokens:
                if t["token_id"] == token_id and t["status"] == "pending":
                    t["status"] = "revoked"
                    t["revoked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    self._write(tokens)
                    return True
        return False

    def revoke(self, token_id: str) -> bool:
        """撤销接入"""
        with _TOKENS_LOCK:
            tokens = self._read()
            for t in tokens:
                if t["token_id"] == token_id and t["status"] == "active":
                    t["status"] = "revoked"
                    t["revoked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    self._write(tokens)
                    return True
        return False

    def verify(self, token: str) -> Optional[dict]:
        """验证 Token，返回平台信息或 None。

        2026-09-20：`last_used_at` 改为**节流更新**（默认 60s 内不重复落盘）。
        原因：此前**每个请求**都做一次整表 read→改→write，既无锁（并发请求会丢掉
        彼此的审批/吊销变更）又是纯写放大（MCP 每次 tools/call 一次全文件重写）。
        返回值不依赖更新是否落盘，写失败只记日志。
        """
        token_hash = _hash_token(token)
        with _TOKENS_LOCK:
            tokens = self._read()
            for t in tokens:
                if t["token_hash"] == token_hash and t["status"] == "active":
                    ident = {
                        "token_id": t["token_id"],
                        "platform": t["platform"],
                        "platform_name": t["platform_name"],
                        "permissions": t["permissions"],
                    }
                    now = time.time()
                    last = float(t.get("_last_used_persist") or 0)
                    if now - last >= _LAST_USED_PERSIST_INTERVAL:
                        t["last_used_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                        t["_last_used_persist"] = now
                        try:
                            self._write(tokens)
                        except Exception as e:  # 记录用途，失败不影响鉴权
                            logger.warning(f"platform token last_used_at 落盘失败: {e}")
                    return ident
            return None

    def list_tokens(self, include_revoked: bool = False, include_pending: bool = True) -> list[dict]:
        """列出所有 Token"""
        tokens = self._read()
        result = []
        for t in tokens:
            if not include_revoked and t.get("revoked_at"):
                continue
            if not include_pending and t["status"] == "pending":
                continue
            result.append({
                "token_id": t["token_id"],
                "platform": t["platform"],
                "platform_name": t["platform_name"],
                "permissions": t["permissions"],
                "status": t["status"],
                "created_at": t["created_at"],
                "last_used_at": t.get("last_used_at"),
                "approved_at": t.get("approved_at"),
                "revoked_at": t.get("revoked_at"),
                "request_ip": t.get("request_ip"),
            })
        return result

    def get_pending(self) -> list[dict]:
        """获取待审核列表"""
        tokens = self._read()
        result = []
        for t in tokens:
            if t["status"] == "pending" and not t.get("revoked_at"):
                result.append({
                    "token_id": t["token_id"],
                    "platform": t["platform"],
                    "platform_name": t["platform_name"],
                    "permissions": t["permissions"],
                    "status": t["status"],
                    "created_at": t["created_at"],
                    "request_ip": t.get("request_ip"),
                })
        return result


# 全局实例
_platform_token_manager: Optional[PlatformTokenManager] = None


def get_platform_token_manager() -> PlatformTokenManager:
    """获取全局 PlatformTokenManager 实例"""
    global _platform_token_manager
    if _platform_token_manager is None:
        _platform_token_manager = PlatformTokenManager()
    return _platform_token_manager
