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
- **密钥轮换**：PANGU_ENCRYPTION_KEY / 密钥文件均可放多个密钥
  （逗号、分号或换行分隔）。第一个用于加密，全部用于解密
  （MultiFernet 语义）。轮换步骤：新密钥放最前、旧密钥留在后面 →
  新数据用新密钥写、旧数据仍可读；确认旧密文重写完后删除旧密钥。

开关：PANGU_ENCRYPTION=off（或 0/false/no）**只关闭写入加密**，新内容以明文落库；
解密路径保持可用，历史密文仍能正常读取（关开关 ≠ fernet 不初始化，否则旧密文
会原样吐回成 gAAAA 乱码）。适用场景：单人本地部署，不需要落盘加密。
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("pangu.memory.encryption")

_fernet = None
_enabled = False
_key_count = 0
_encrypt_disabled_warned = False
_decrypt_failed_warned = False

# Fernet token 的固定前缀（base64 的版本字节 0x80）。用它区分"密文"与"明文"：
# 不以它开头的字符串当作本来就是明文，原样返回。
_FERNET_PREFIX = "gAAAAA"

# 解密失败时的占位符。为什么不抛异常：读路径调用方众多且大多没有 try，
# 抛错会让"一条坏数据"升级成"整次读取失败"。为什么不返回密文：
# 旧实现就是这么干的，上层会把密文当明文用 —— 用户看到 gAAAAAB… 乱码
# 却没有任何线索（2026-09-19 实测：换密钥后 decrypt 原样吐回密文）。
_DECRYPT_FAILED_PLACEHOLDER = "[[解密失败：密钥不匹配或数据损坏]]"


def _write_disabled_by_config() -> bool:
    """PANGU_ENCRYPTION=off/0/false/no 时关闭写入加密（解密不受影响）"""
    return os.environ.get("PANGU_ENCRYPTION", "").strip().lower() in ("off", "0", "false", "no")


def _get_fernet():
    """获取或初始化 Fernet / MultiFernet 实例（支持多密钥轮换）"""
    global _fernet, _enabled, _key_count

    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet, MultiFernet
    except ImportError:
        logger.debug("cryptography not installed, encryption disabled")
        _enabled = False
        return None

    # 优先从环境变量获取密钥（可多密钥）
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

    # 逗号 / 分号 / 换行分隔的多密钥；顺序即优先级（第一个用于加密）
    keys = [k.strip() for k in re.split(r"[,;\n]+", key_str) if k.strip()]
    if not keys:
        _enabled = False
        return None

    try:
        fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
    except Exception as e:
        # 密钥格式非法（不是 32 字节 base64）—— 大声报，别静默降级成明文
        logger.error(f"加密密钥格式非法，加密已禁用（数据将以明文写入！）: {e}")
        _enabled = False
        return None

    _key_count = len(fernets)
    _fernet = fernets[0] if len(fernets) == 1 else MultiFernet(fernets)
    _enabled = True
    if _key_count > 1:
        logger.info(f"加密已启用（{_key_count} 把密钥，MultiFernet 轮换模式）")
    return _fernet


def is_enabled() -> bool:
    """检查加密是否启用"""
    _get_fernet()
    return _enabled


def _looks_encrypted(value) -> bool:
    """是否像 Fernet 密文（用于区分"密文"与"本来就是明文"）"""
    return isinstance(value, str) and value.startswith(_FERNET_PREFIX)


def encrypt(plaintext: str) -> str:
    """加密字符串。

    加密不可用时（cryptography 缺失 / 密钥非法）**原样返回明文** —— 刻意的
    fail-open：拒绝写入会让整个系统不可用。但必须留痕：这里打一次 WARNING，
    避免"以为在加密、其实在存明文"（旧实现只有 debug 级日志，等于静默）。
    """
    global _encrypt_disabled_warned
    if _write_disabled_by_config():
        # 配置性关闭是有意为之，留痕一次 INFO 即可，不套用依赖缺失的 WARNING
        if not _encrypt_disabled_warned:
            logger.info("PANGU_ENCRYPTION=off：写入加密已按配置关闭，内容以明文落库（历史密文仍可解密）")
            _encrypt_disabled_warned = True
        return plaintext
    f = _get_fernet()
    if f is None:
        if not _encrypt_disabled_warned:
            logger.warning("加密不可用：内容将以**明文**写入（检查 cryptography 依赖与密钥配置）")
            _encrypt_disabled_warned = True
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """解密字符串（三态）。

    1. 非 Fernet 格式 → 本来就是明文，原样返回
    2. Fernet 格式且解密成功 → 明文
    3. Fernet 格式但解密失败（密钥不匹配 / 数据损坏）→ 返回明确占位符 + 一次
       WARNING。**不再静默返回密文** —— 旧行为会让上层把密文当明文用，用户
       看到 gAAAAAB… 乱码却查不到原因（2026-09-19 实测：换密钥后原样吐回密文）。
    """
    global _decrypt_failed_warned
    f = _get_fernet()
    if f is None:
        return ciphertext
    if not _looks_encrypted(ciphertext):
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        if not _decrypt_failed_warned:
            logger.warning(
                f"解密失败（密钥不匹配或数据损坏）: {type(e).__name__}。若刚轮换过密钥，"
                f"请确认旧密钥仍在 PANGU_ENCRYPTION_KEY / ~/.pangu/.encryption_key 中；"
                f"受影响内容将显示为 {_DECRYPT_FAILED_PLACEHOLDER}"
            )
            _decrypt_failed_warned = True
        return _DECRYPT_FAILED_PLACEHOLDER


def self_check(sample_ciphertext: str | None = None) -> dict:
    """启动自检：加密开关状态 + 已有密文能否解开。

    Args:
        sample_ciphertext: 库中一条已知密文（运维侧可用来判断"旧数据是否还能解"）。
            None 表示没有样本，sample_ok 返回 None。

    Returns:
        {"enabled": bool, "keys": int, "sample_ok": bool|None, "error": str|None}

    典型用途：服务启动时拿库里的第一条 gAAAAA 密文跑一次 —— 若 sample_ok=False，
    说明密钥已变（换机器/重装/迁移时丢了 .encryption_key），旧密文全部不可解，
    需要立刻告警而不是等用户看到乱码。
    """
    result = {
        "enabled": False,
        "keys": _key_count,
        "sample_ok": None,
        "error": None,
        "write_disabled_by_config": _write_disabled_by_config(),
    }
    f = _get_fernet()
    result["enabled"] = _enabled
    result["keys"] = _key_count
    if not _enabled:
        result["error"] = "加密不可用（cryptography 缺失或密钥非法）"
        return result
    if sample_ciphertext is None:
        return result
    if not _looks_encrypted(sample_ciphertext):
        result["sample_ok"] = None  # 给的样本本来就不是密文
        return result
    try:
        f.decrypt(sample_ciphertext.encode()).decode()
        result["sample_ok"] = True
    except Exception as e:
        result["sample_ok"] = False
        result["error"] = f"已有密文无法解密: {type(e).__name__}"
    return result


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
