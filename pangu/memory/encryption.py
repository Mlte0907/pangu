"""盘古 — 记忆数据加密模块

支持对记忆内容进行加密存储，保护敏感数据。
使用 Fernet 对称加密（AES-128-CBC + HMAC-SHA256）。

加密流程：
1. 生成或加载主密钥
2. 对记忆 content 字段加密后存储
3. 读取时自动解密

密钥管理：
- 首次启动自动生成密钥并保存到 ~/.pangu/.encryption_key
- 支持环境变量 PANGU_ENCRYPTION_KEY 覆盖
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("pangu.memory.encryption")

_fernet = None
_enabled = False


def _get_fernet():
    """获取或初始化 Fernet 实例"""
    global _fernet, _enabled

    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.debug("cryptography not installed, encryption disabled")
        _enabled = False
        return None

    # 优先从环境变量获取密钥
    key_str = os.environ.get("PANGU_ENCRYPTION_KEY", "")

    if not key_str:
        # 从文件加载或生成
        key_file = Path.home() / ".pangu" / ".encryption_key"
        if key_file.exists():
            key_str = key_file.read_text().strip()
        else:
            key_str = Fernet.generate_key().decode()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(key_str)
            key_file.chmod(0o600)
            logger.info(f"Generated new encryption key: {key_file}")

    if isinstance(key_str, str):
        key_str = key_str.encode()

    _fernet = Fernet(key_str)
    _enabled = True
    return _fernet


def is_enabled() -> bool:
    """检查加密是否启用"""
    _get_fernet()
    return _enabled


def encrypt(plaintext: str) -> str:
    """加密字符串

    Args:
        plaintext: 明文

    Returns:
        加密后的 base64 字符串（带前缀 gAAAAA）
    """
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密字符串

    Args:
        ciphertext: 加密字符串

    Returns:
        解密后的明文
    """
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # 可能是未加密的明文，直接返回
        return ciphertext


def encrypt_dict(data: dict, fields: list[str] | None = None) -> dict:
    """加密字典中的指定字段

    Args:
        data: 数据字典
        fields: 要加密的字段列表，默认加密 "content"

    Returns:
        加密后的字典（新对象）
    """
    if not is_enabled():
        return data

    fields = fields or ["content"]
    result = dict(data)

    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = encrypt(result[field])

    return result


def decrypt_dict(data: dict, fields: list[str] | None = None) -> dict:
    """解密字典中的指定字段

    Args:
        data: 数据字典
        fields: 要解密的字段列表，默认解密 "content"

    Returns:
        解密后的字典（新对象）
    """
    if not is_enabled():
        return data

    fields = fields or ["content"]
    result = dict(data)

    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = decrypt(result[field])

    return result
