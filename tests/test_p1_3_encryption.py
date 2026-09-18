"""加密边界回归（2026-09-19）。

背景：encryption.decrypt 旧实现把"解密失败"与"本来就是明文"混为一谈 ——
任何异常都 return ciphertext。实测：换密钥 / 密文损坏后原样返回密文，上层当
明文用，用户看到 gAAAAAB… 乱码却查不到原因（dsh 插件 recall 出密文即此路径）。

本文件锁定新的三态语义 + 多密钥轮换 + 启动自检 + 非法密钥的显式降级。
"""

import pytest
from cryptography.fernet import Fernet

from pangu.memory import encryption as enc


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """加密模块用模块级单例缓存实例 —— 每个测试前重置，避免互相污染。"""
    for attr, val in (
        ("_fernet", None),
        ("_enabled", False),
        ("_key_count", 0),
        ("_decrypt_failed_warned", False),
        ("_encrypt_disabled_warned", False),
    ):
        monkeypatch.setattr(enc, attr, val)
    yield


def _fresh_key(monkeypatch, *keys):
    """设置密钥并重置单例（模拟进程重启 / 密钥变更）"""
    monkeypatch.setattr(enc, "_fernet", None)
    monkeypatch.setattr(enc, "_enabled", False)
    monkeypatch.setenv("PANGU_ENCRYPTION_KEY", ",".join(keys))


def test_roundtrip(monkeypatch):
    _fresh_key(monkeypatch, Fernet.generate_key().decode())
    ct = enc.encrypt("敏感内容")
    assert ct.startswith("gAAAAA")
    assert enc.decrypt(ct) == "敏感内容"


def test_plaintext_passthrough(monkeypatch):
    """非 Fernet 格式 → 本来就是明文，原样返回（保留旧行为）。"""
    _fresh_key(monkeypatch, Fernet.generate_key().decode())
    assert enc.decrypt("普通明文") == "普通明文"


def test_decrypt_failure_is_not_silent(monkeypatch):
    """★ 核心回归：换密钥后不能原样返回密文。"""
    _fresh_key(monkeypatch, Fernet.generate_key().decode())
    ct = enc.encrypt("秘密")

    _fresh_key(monkeypatch, Fernet.generate_key().decode())  # 换了密钥
    out = enc.decrypt(ct)
    assert out != ct, "换钥后仍原样返回密文（旧 bug 复活）"
    assert "解密失败" in out


def test_corrupted_ciphertext_is_marked(monkeypatch):
    _fresh_key(monkeypatch, Fernet.generate_key().decode())
    ct = enc.encrypt("内容")
    bad = ct[:-4] + "AAAA"  # 破坏 HMAC
    out = enc.decrypt(bad)
    assert out != bad and "解密失败" in out


def test_multi_key_rotation(monkeypatch):
    """轮换：新钥在前、旧钥在后 —— 旧密文仍可解，新数据用新钥写。"""
    old = Fernet.generate_key().decode()
    _fresh_key(monkeypatch, old)
    old_ct = enc.encrypt("旧数据")

    new = Fernet.generate_key().decode()
    _fresh_key(monkeypatch, new, old)  # ★ 轮换：新钥优先，旧钥保留
    assert enc.decrypt(old_ct) == "旧数据"
    new_ct = enc.encrypt("新数据")
    assert enc.decrypt(new_ct) == "新数据"
    assert new_ct != old_ct

    # 撤掉旧钥后：新密文照常，旧密文变占位符
    _fresh_key(monkeypatch, new)
    assert enc.decrypt(new_ct) == "新数据"
    assert "解密失败" in enc.decrypt(old_ct)


def test_self_check_detects_key_mismatch(monkeypatch):
    k = Fernet.generate_key().decode()
    _fresh_key(monkeypatch, k)
    ct = enc.encrypt("x")
    v = enc.self_check(ct)
    assert v["enabled"] is True and v["sample_ok"] is True

    _fresh_key(monkeypatch, Fernet.generate_key().decode())
    v2 = enc.self_check(ct)
    assert v2["sample_ok"] is False and "无法解密" in v2["error"]

    # 无样本：不判断
    assert enc.self_check(None)["sample_ok"] is None


def test_invalid_key_disables_and_encrypt_fails_open(monkeypatch):
    """非法密钥：显式禁用（不是崩溃），encrypt 走 fail-open 存明文。"""
    monkeypatch.setattr(enc, "_fernet", None)
    monkeypatch.setattr(enc, "_enabled", False)
    monkeypatch.setenv("PANGU_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    v = enc.self_check()
    assert v["enabled"] is False and v["error"]
    assert enc.encrypt("明文写入") == "明文写入"  # fail-open（有 WARNING 留痕）
