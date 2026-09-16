"""盘古钥匙管理器

keys.json 0600，只存 SHA-256 哈希，明文一次性输出（pgk_ 前缀）。
"""

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional


def _hash_key(key: str) -> str:
    """SHA-256 哈希（不加盐，因为明文只输出一次）"""
    return hashlib.sha256(key.encode()).hexdigest()


def _gen_key() -> str:
    """生成 pgk_ 前缀 + 32 字节 base64url 密钥"""
    raw = secrets.token_urlsafe(32)
    return f"pgk_{raw}"


class KeyManager:
    """钥匙表管理（~/.pangu/keys.json, 0600）"""

    def __init__(self, keys_path: str = None):
        if keys_path is None:
            # ⚠ 默认路径必须走 PanguConfig.base_dir，**不要**用 Path.home()：
            # conftest 隔离的是 base_dir（PANGU_BASE_DIR），硬编码 home 会让每个用例把
            # 钥匙写进**真实**钥匙表 —— 实测跑几轮测试就在生产库里攒了 13 把 room-x 的
            # 测试钥匙。生产环境 base_dir 就是 ~/.pangu，路径不变。
            try:
                from pangu.core.config import PanguConfig

                self.keys_path = Path(PanguConfig.load().base_dir) / "keys.json"
            except Exception:  # noqa: BLE001 — 配置不可用时退回历史路径
                self.keys_path = Path.home() / ".pangu" / "keys.json"
        else:
            self.keys_path = Path(keys_path)
        self._ensure_file()

    def _ensure_file(self):
        """确保 keys.json 存在且权限正确"""
        if not self.keys_path.exists():
            self.keys_path.parent.mkdir(parents=True, exist_ok=True)
            self._write([])
            os.chmod(self.keys_path, 0o600)
        else:
            # 修复权限（600）
            current = oct(self.keys_path.stat().st_mode)[-3:]
            if current != "600":
                os.chmod(self.keys_path, 0o600)

    def _read(self) -> list[dict]:
        try:
            with open(self.keys_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, keys: list[dict]):
        tmp = self.keys_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.keys_path)
        os.chmod(self.keys_path, 0o600)

    def create(self, room: str, scope: str = "readwrite", clearance: int = 0) -> dict:
        """创建新钥匙（返回含明文的完整记录，明文只此一次）"""
        key = _gen_key()
        record = {
            "key_id": f"key_{secrets.token_hex(8)}",
            "room": room,
            "scope": scope,  # readwrite | readonly | admin
            "key_hash": _hash_key(key),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_used_at": None,
            "revoked_at": None,
            # 密级（clearance）：0=public / 1=internal / 2=confidential / 3=secret
            # 与 ABAC 的 Subject.clearance 同一套；默认 0＝失败关闭（需要时由管理员授予）
            "clearance": int(clearance or 0),
        }
        keys = self._read()
        keys.append(record)
        self._write(keys)
        # 明文只在创建时返回一次
        record["key"] = key
        return record

    def list_keys(self, include_revoked: bool = False) -> list[dict]:
        """列出所有钥匙（不含明文，不含 key_hash）"""
        keys = self._read()
        result = []
        for k in keys:
            if not include_revoked and k.get("revoked_at"):
                continue
            result.append(
                {
                    "key_id": k["key_id"],
                    "room": k["room"],
                    "scope": k["scope"],
                    "created_at": k["created_at"],
                    "last_used_at": k.get("last_used_at"),
                    # revoked_at 必须带出来：调用方（如 admin/rooms 的房间钥匙计数）
                    # 依赖它区分有效/已吊销。此前这个字段被丢弃，导致
                    # `not k.get("revoked_at")` 恒为真 —— 吊销过的钥匙仍被计数
                    # （实测 dsh 房间显示 2 把，实际只有 1 把有效）。
                    "revoked_at": k.get("revoked_at"),
                    "clearance": int(k.get("clearance", 0) or 0),
                }
            )
        return result

    def revoke(self, key_id: str) -> bool:
        """吊销钥匙"""
        keys = self._read()
        for k in keys:
            if k["key_id"] == key_id:
                k["revoked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._write(keys)
                return True
        return False

    def verify(self, key: str) -> dict | None:
        """验证钥匙，返回 {key_id, room, scope} 或 None"""
        key_hash = _hash_key(key)
        keys = self._read()
        for k in keys:
            if k["key_hash"] == key_hash and not k.get("revoked_at"):
                # 更新 last_used_at
                k["last_used_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._write(keys)
                return {
                    "key_id": k["key_id"],
                    "room": k["room"],
                    "scope": k["scope"],
                    "clearance": int(k.get("clearance", 0) or 0),
                }
        return None
