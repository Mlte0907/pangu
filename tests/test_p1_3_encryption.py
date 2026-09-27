"""加密边界回归（2026-09-19）。

背景：encryption.decrypt 旧实现把"解密失败"与"本来就是明文"混为一谈 ——
任何异常都 return ciphertext。实测：换密钥 / 密文损坏后原样返回密文，上层当
明文用，用户看到 gAAAAAB… 乱码却查不到原因（dsh 插件 recall 出密文即此路径）。

本文件锁定新的三态语义 + 多密钥轮换 + 启动自检 + 非法密钥的显式降级。
"""

from __future__ import annotations

from pathlib import Path

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


# ── 读侧 fail-open（2026-09-27）────────────────────────────
#
# 上面那条测的是**写**侧 fail-open。读侧曾经是同一个洞的另一半：
# `decrypt()` 在 `_get_fernet()` 返回 None 时 `return ciphertext` ——
# 与本文件 docstring 宣称的「不再静默返回密文」直接矛盾（2026-09-19 修过
# 同款坑，但只修了「密钥不匹配」那一态，漏了「加密根本不可用」这一态）。
# 于是 cryptography 缺失 / 密钥非法时，gAAAAAB… 照样直出到搜索结果与仪表盘。


def _disable_encryption(monkeypatch):
    """让加密进入不可用态：密钥非法 ⇒ `_get_fernet()` 返回 None。"""
    monkeypatch.setattr(enc, "_fernet", None)
    monkeypatch.setattr(enc, "_enabled", False)
    monkeypatch.setenv("PANGU_ENCRYPTION_KEY", "not-a-valid-fernet-key")


def test_decrypt_when_unavailable_returns_placeholder_not_ciphertext(monkeypatch):
    """★ 加密不可用时不得把密文当内容吐出 —— 与写侧 fail-open 对称。"""
    _disable_encryption(monkeypatch)
    out = enc.decrypt("gAAAAABqsmaq49WZk9K9xgxNNDXBx127UbIsVCm42vVz5")
    assert out != "gAAAAABqsmaq49WZk9K9xgxNNDXBx127UbIsVCm42vVz5", (
        "加密不可用仍原样返回密文：gAAAAAB… 会直出到搜索结果与仪表盘，"
        "用户看到乱码且查不到原因（正是 2026-09-19 修过的那个坑）"
    )
    assert "解密失败" in out, f"应给出明确占位符，实际: {out!r}"


def test_decrypt_when_unavailable_still_passes_plaintext_through(monkeypatch):
    """明文必须原样返回 —— 库里绝大多数内容是明文，别被这步改坏。"""
    _disable_encryption(monkeypatch)
    assert enc.decrypt("普通明文") == "普通明文"
    assert enc.decrypt("") == ""


def test_decrypt_when_unavailable_warns_once_not_per_call(monkeypatch):
    """留痕但不刷屏：与「密钥不匹配」那一态共用同一条去重标志。"""
    _disable_encryption(monkeypatch)
    monkeypatch.setattr(enc, "_decrypt_failed_warned", False)

    enc.decrypt("gAAAAAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    first = enc._decrypt_failed_warned
    enc.decrypt("gAAAAAbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert first is True, "首次解密失败必须留痕"


# ── 启动自检的采样面（2026-09-27）──────────────────────────
#
# server.py 的启动体检只采样 drawers.json。而归档表 forgetting_archive.json
# 里的密文**同样可能是旧密钥写的**（实测云端就有 1 条解不开）—— 不进采样面
# 就永远不会被 self_check 发现，启动日志照样打「加密可用」。


def _cfg_for(tmp_path):
    from pangu.core.config import PanguConfig

    cfg = PanguConfig()
    cfg.palace_path = str(tmp_path / "pangu.db" / "v2_memories")
    return cfg


def test_probe_collects_drawers_sample(tmp_path):
    import json

    from pangu.api.server import collect_encryption_samples

    cfg = _cfg_for(tmp_path)
    p = Path(cfg.palace_path)
    p.mkdir(parents=True, exist_ok=True)
    (p / "drawers.json").write_text(
        json.dumps([{"id": "a", "content": "gAAAAAplain-old"}, {"id": "b", "content": "明文"}]),
        encoding="utf-8",
    )

    samples = collect_encryption_samples(cfg)
    assert any("gAAAAA" in c for _, c in samples), samples
    assert any(label.startswith("drawers") for label, _ in samples), samples


def test_probe_collects_archive_sample(tmp_path):
    """★ 归档表必须进采样面 —— 否则解不开的旧归档永远无人知晓。"""
    import json

    from pangu.api.server import collect_encryption_samples

    cfg = _cfg_for(tmp_path)
    p = Path(cfg.palace_path)
    p.mkdir(parents=True, exist_ok=True)
    (p.parent / "forgetting_archive.json").write_text(
        json.dumps([{"id": "x", "content": "gAAAAAarchived-old"}]),
        encoding="utf-8",
    )

    samples = collect_encryption_samples(cfg)
    assert any("gAAAAAarchived-old" in c for _, c in samples), (
        f"归档表没进采样面: {samples}"
    )
    assert any("archive" in label for label, _ in samples), samples


def test_probe_tolerates_missing_files(tmp_path):
    """两个文件都不存在时返回空，不能抛。"""
    from pangu.api.server import collect_encryption_samples

    assert collect_encryption_samples(_cfg_for(tmp_path)) == []


def test_probe_collects_every_ciphertext_not_just_first(tmp_path):
    """★ 必须全量收集，不能 break 在第一条。

    云端实测：归档表**首条密文恰好可解**、坏数据在后面 —— 每来源只取一条会
    报「全部解密通过」而漏掉真问题（本函数初版就是这么写的）。
    """
    import json

    from pangu.api.server import collect_encryption_samples

    cfg = _cfg_for(tmp_path)
    p = Path(cfg.palace_path)
    p.mkdir(parents=True, exist_ok=True)
    (p / "drawers.json").write_text(
        json.dumps(
            [
                {"id": "a", "content": "gAAAAA第一条能解开"},
                {"id": "b", "content": "明文混在里面"},
                {"id": "c", "content": "gAAAAA第二条解不开"},
            ]
        ),
        encoding="utf-8",
    )

    samples = collect_encryption_samples(cfg)
    drawers_samples = [c for label, c in samples if label.startswith("drawers")]
    assert len(drawers_samples) == 2, f"应采到全部 2 条密文而非首条: {drawers_samples}"


def test_probe_skips_plaintext_and_corrupt_json(tmp_path):
    """只收密文样本；明文与损坏文件都不能污染样本集。"""
    import json

    from pangu.api.server import collect_encryption_samples

    cfg = _cfg_for(tmp_path)
    p = Path(cfg.palace_path)
    p.mkdir(parents=True, exist_ok=True)
    (p / "drawers.json").write_text(json.dumps([{"id": "a", "content": "全是明文"}]), encoding="utf-8")
    (p.parent / "forgetting_archive.json").write_text("{ 这不是合法 json", encoding="utf-8")

    assert collect_encryption_samples(cfg) == []
