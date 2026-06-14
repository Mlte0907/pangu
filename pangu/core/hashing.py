"""盘古 — 统一哈希工具

集中提供 blake2b 哈希接口，统一替换散落的 hashlib.md5。
- 安全：blake2b 是抗碰撞的现代哈希（RFC 7693），无已知安全弱点
- 性能：与 md5/sha1 相当，CPU 友好
- API：与 hashlib.md5().hexdigest() 兼容
"""
from __future__ import annotations

import hashlib

# 8 字节 = 16 hex 字符；缓存键/ID 前缀常用长度
_DEFAULT_HEX_LEN = 32


def hex_digest(data: str | bytes, *, length: int = _DEFAULT_HEX_LEN) -> str:
    """字符串/字节的 blake2b 十六进制摘要。

    Args:
        data: 输入数据（str 自动 utf-8 编码）
        length: 返回的十六进制字符数（4-128）

    Returns:
        length 长度的 hex 字符串
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    length = max(4, min(128, length))
    # digest_size 决定原始字节数（hex 长度的 1/2）
    return hashlib.blake2b(data, digest_size=length // 2).hexdigest()


def int_hash(data: str | bytes, *, mod: int = 1 << 32) -> int:
    """字符串/字节的 blake2b 整数哈希（用于 [0, mod) 桶映射）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.blake2b(data, digest_size=8).digest()
    return int.from_bytes(h, "big") % mod
