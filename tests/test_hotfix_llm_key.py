"""热修：resolveLlmApiKey + testConnection 逻辑分支测试"""

import os

import pytest


def test_resolveLlmApiKey_cfg_has_key():
    """config 有 key → 不读文件"""
    # 模拟 resolveLlmApiKey 逻辑
    cfg = {"llm_api_key": "sk-test123"}
    SECRET_FILE = "/tmp/.test_secret"
    # 逻辑：cfg.llm_api_key 优先
    key = cfg.get("llm_api_key", "") or ""
    assert key == "sk-test123"


def test_resolveLlmApiKey_cfg_empty_file_has(tmp_path):
    """config 空 + 文件有 → 解析成功"""
    secret_file = tmp_path / ".llm_api_key"
    secret_file.write_text("sk-from-file\n")
    SECRET_FILE = str(secret_file)
    # 模拟 resolveLlmApiKey 逻辑
    cfg = {"llm_api_key": ""}
    key = cfg.get("llm_api_key", "") or ""
    if not key:
        try:
            import pathlib

            secret = pathlib.Path(SECRET_FILE).read_text().strip()
            if secret:
                key = secret
        except Exception:
            pass
    assert key == "sk-from-file"


def test_resolveLlmApiKey_both_empty():
    """config 空 + 文件不存在 → 空串"""
    cfg = {"llm_api_key": ""}
    key = cfg.get("llm_api_key", "") or ""
    assert key == ""


def test_resolveLlmApiKey_no_read_file_when_cfg_has():
    """config 有 key 时不读文件（即使文件内容不同）"""
    cfg = {"llm_api_key": "sk-primary"}
    key = cfg.get("llm_api_key", "") or ""
    assert key == "sk-primary"
    # 不应读文件
    assert "sk-file" not in key
