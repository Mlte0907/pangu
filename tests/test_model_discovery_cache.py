"""模型列表的 TTL 缓存与偏好落空回退。

## 为什么要有这些测试

`discover_chat_models` 是 LLM 选型的唯一入口，2026-09-27 加了两件事：

1. **TTL 缓存**（默认 6 小时）：模型列表是**一个整体**，过期才重新拉。
   没有它，每次首选模型失败都要为「找备选」额外打一次平台接口。
2. **偏好落空回退**：`deepseek` 和 `minicpm` 家族**都不在**平台列表时，
   回退到未过滤的完整列表（仍排除 mineru）。

第 2 条是真正的风险点：没有回退时返回空列表 → 没有任何候选 →
LLM 调用全部失败，而且**没有任何日志**说明是偏好序把模型全过滤掉了。
2026-09-26 实测：平台只剩 GLM/Qwen/MiMo 时，旧逻辑返回 0 个候选。
"""

import time

import pytest

import pangu.core.llm as llm


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    """每个用例前后清空模块级缓存，避免互相污染。"""
    llm._DISCOVERY_CACHE.clear()
    yield
    llm._DISCOVERY_CACHE.clear()


class _FakeResp:
    def __init__(self, payload):
        import json

        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, names, counter):
    """把 urllib.request.urlopen 换成可控假实现，并计数。"""
    import urllib.request

    def fake(req, timeout=0):
        counter["calls"] += 1
        return _FakeResp({"data": [{"id": n} for n in names]})

    monkeypatch.setattr(urllib.request, "urlopen", fake)


# ── TTL 缓存 ──


def test_second_call_uses_cache(monkeypatch):
    """同一 base 的第二次发现不应再打平台接口。"""
    counter = {"calls": 0}
    _patch_urlopen(monkeypatch, ["DeepSeek-V4-Flash", "MiniCPM5-2B"], counter)

    base, key = "https://example.test/v1", "sk-test"
    first = llm.discover_chat_models(base, key)
    second = llm.discover_chat_models(base, key)

    assert counter["calls"] == 1, f"第二次仍打了接口（{counter['calls']} 次）—— 缓存没生效"
    assert first == second


def test_expired_cache_refetches(monkeypatch):
    """超过 TTL 后必须重新拉取。"""
    counter = {"calls": 0}
    _patch_urlopen(monkeypatch, ["DeepSeek-V4-Flash"], counter)

    base, key = "https://example.test/v1", "sk-test"
    llm.discover_chat_models(base, key)
    assert counter["calls"] == 1

    # 把 TTL 压到 0，强制过期
    monkeypatch.setattr(llm, "_DISCOVERY_TTL", 0.0)
    time.sleep(0.01)
    llm.discover_chat_models(base, key)
    assert counter["calls"] == 2, "TTL 过期后没有重新拉取"


def test_cache_keyed_by_base_not_key(monkeypatch):
    """不同 base 各自缓存；同一 base 换 key 仍命中缓存。

    模型列表与用哪个密钥无关，所以 key 不该参与缓存键 —— 否则同一平台
    换个密钥就白打一次接口。
    """
    counter = {"calls": 0}
    _patch_urlopen(monkeypatch, ["DeepSeek-V4-Flash"], counter)

    base = "https://example.test/v1"
    llm.discover_chat_models(base, "sk-one")
    llm.discover_chat_models(base, "sk-two")   # 换 key，同 base
    assert counter["calls"] == 1, "key 参与了缓存键，导致重复请求"

    llm.discover_chat_models("https://other.test/v1", "sk-one")
    assert counter["calls"] == 2, "不同 base 应各自缓存"


# ── 偏好落空回退 ──


def test_fallback_when_no_preferred_family(monkeypatch):
    """deepseek 和 minicpm 都不在时，回退到平台剩余模型。"""
    counter = {"calls": 0}
    _patch_urlopen(
        monkeypatch,
        ["GLM-5.3-Flash", "Qwen3.8-27B", "MiMo-V2.6-Flash"],
        counter,
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert got == ["GLM-5.3-Flash", "Qwen3.8-27B", "MiMo-V2.6-Flash"], (
        f"偏好落空时没有回退到全部可用模型：{got}"
    )


def test_fallback_still_excludes_mineru(monkeypatch):
    """回退时 mineru 仍必须被排除 —— 它是文档解析模型，不是对话模型。"""
    _patch_urlopen(
        monkeypatch,
        ["GLM-5.3-Flash", "MinerU2.5-Pro", "Qwen3.8-27B"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert "MinerU2.5-Pro" not in got, f"回退时 mineru 没被排除：{got}"
    assert got == ["GLM-5.3-Flash", "Qwen3.8-27B"]


def test_no_fallback_when_preference_matches(monkeypatch):
    """偏好家族存在时**不**该触发回退，且仍按偏好序排。"""
    _patch_urlopen(
        monkeypatch,
        ["Qwen3.8-27B", "DeepSeek-V4-Flash", "MiniCPM5-2B", "GLM-5.3-Flash"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    # deepseek 家族在前，minicpm 其次，未识别家族不入选
    assert got == ["DeepSeek-V4-Flash", "MiniCPM5-2B"], f"偏好序不对：{got}"


# ── 精确优先序（LLM_MODEL_PRIORITY）──


def test_priority_lifts_faster_model_within_family(monkeypatch):
    """同家族内更快的模型应被提到最前。

    2026-09-27 实测：DeepSeek-V4.1-Flash 首次调用 88~121s（高负载排队），
    DeepSeek-V4-Flash 首次只要 1.4s。二者同属 deepseek 家族，家族偏好无法区分，
    所以用 LLM_MODEL_PRIORITY 把 V4-Flash 提到 #1。
    """
    _patch_urlopen(
        monkeypatch,
        ["DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash", "DeepSeek-V4-Flash-Vision-Exp", "MiniCPM5-2B"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert got[0] == "DeepSeek-V4-Flash", f"V4-Flash 应排第一，实际 {got}"
    # V4.1 仍留在家族偏好档，排在 V4-Flash 之后
    assert got.index("DeepSeek-V4.1-Flash") > got.index("DeepSeek-V4-Flash")


def test_priority_does_not_mis_match_v41(monkeypatch):
    """精确优先序不能误匹配 V4.1 —— 中间有个点。

    "deepseek-v4-flash" 不是 "deepseek-v4.1-flash" 的子串，所以 V4.1
    不该被提级，仍按家族偏好排在后面。
    """
    _patch_urlopen(
        monkeypatch,
        ["DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert got == ["DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash"], f"误匹配了 V4.1：{got}"


def test_priority_respects_exclude(monkeypatch):
    """精确优先序也要遵守排除项。"""
    _patch_urlopen(
        monkeypatch,
        ["MinerU2.5-Pro", "DeepSeek-V4-Flash"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert "MinerU2.5-Pro" not in got, f"精确优先序没排除 mineru：{got}"
    assert got == ["DeepSeek-V4-Flash"]


def test_priority_empty_falls_back_to_family(monkeypatch):
    """精确优先序为空时，完全回退到家族偏好。"""
    monkeypatch.setattr(llm, "LLM_MODEL_PRIORITY", ())
    _patch_urlopen(
        monkeypatch,
        ["DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash", "MiniCPM5-2B"],
        {"calls": 0},
    )
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert got == ["DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash", "MiniCPM5-2B"], (
        f"精确优先序为空时应回退到家族偏好：{got}"
    )


def test_only_mineru_available_returns_empty(monkeypatch):
    """平台只剩 mineru 时，回退也救不了 —— 返回空列表（调用方走无备选路径）。"""
    _patch_urlopen(monkeypatch, ["MinerU2.5-Pro"], {"calls": 0})
    got = llm.discover_chat_models("https://example.test/v1", "sk-test")
    assert got == [], f"只剩 mineru 时应返回空列表，实际 {got}"


def test_empty_platform_list_returns_empty(monkeypatch):
    _patch_urlopen(monkeypatch, [], {"calls": 0})
    assert llm.discover_chat_models("https://example.test/v1", "sk-test") == []


# ── 真实平台回归（可选，默认跳过）──


@pytest.mark.skip(reason="会打真实平台接口，CI/本地手动跑")
def test_live_platform_still_discovers_deepseek():
    import json
    import os

    cfg = json.load(open(os.path.expanduser("~/.pangu/config.json")))
    got = llm.discover_chat_models(cfg["llm_base_url"], cfg["llm_api_key"])
    assert any("deepseek" in m.lower() for m in got), f"真实平台没发现 deepseek：{got}"
