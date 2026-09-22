"""盘古 — LLM 候选模型发现与切换测试

覆盖三件事：
  1. discover_chat_models — 家族偏好排序、排除规则、响应格式
  2. _discover_models / _candidate_models — 各种"发现不了"的退化路径
  3. chat() 的候选切换与**懒发现** —— 配置了模型且调用成功时绝不触网

不发起真实网络请求：urlopen 与 discover_chat_models 均被 mock。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine, LLMResponse, discover_chat_models

# /models 的响应样本（顺序即平台返回顺序，排序由被测代码负责）
_MODELS_PAYLOAD = {
    "data": [
        {"id": "GLM-5.3-Flash"},
        {"id": "DeepSeek-V4-Flash"},
        {"id": "MinerU2.5-Pro"},      # 应被 LLM_MODEL_EXCLUDE 剔除
        {"id": "DeepSeek-V4.1-Flash"},
        {"id": "MiniCPM5-2B"},
        {"id": "Qwen3.8-27B"},        # 未识别家族，不入选
    ]
}


def _urlopen_mock(payload: dict) -> MagicMock:
    """构造一个可作上下文管理器的 urlopen mock，read() 返回 payload。"""
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    resp.__exit__.return_value = False
    return MagicMock(return_value=resp)


def _fail(content: str = "[LMM 调用失败 (openai): HTTP 429]") -> LLMResponse:
    return LLMResponse(content=content, provider="openai")


def _ok(content: str = "success") -> LLMResponse:
    return LLMResponse(content=content, provider="openai")


# ── 1. discover_chat_models ──


class TestDiscoverChatModels:
    """动态模型发现的排序与过滤"""

    def test_ranks_by_family_preference_and_excludes(self):
        with patch("urllib.request.urlopen", _urlopen_mock(_MODELS_PAYLOAD)):
            got = discover_chat_models("https://api.test.com/v1", "key")

        # 排序契约：按 LLM_MODEL_PREFERENCE 分族，族内**保持平台返回顺序**
        # （源码注释「新版本在前」的前提是平台自己已排序），故 V4-Flash 在
        # V4.1-Flash 之前 —— 断言跟随实现，而非按版本号自作主张。
        assert got == ["DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash", "MiniCPM5-2B"]

    def test_unrecognized_family_not_used(self):
        with patch("urllib.request.urlopen", _urlopen_mock(_MODELS_PAYLOAD)):
            got = discover_chat_models("https://api.test.com/v1", "key")
        assert not any(m.startswith(("GLM", "Qwen")) for m in got)

    def test_excluded_model_never_returned(self):
        with patch("urllib.request.urlopen", _urlopen_mock(_MODELS_PAYLOAD)):
            got = discover_chat_models("https://api.test.com/v1", "key")
        assert not any("mineru" in m.lower() for m in got)

    def test_accepts_models_key_and_string_ids(self):
        payload = {"models": ["deepseek-one", {"id": "deepseek-two"}, "", None]}
        with patch("urllib.request.urlopen", _urlopen_mock(payload)):
            got = discover_chat_models("https://api.test.com/v1", "key")
        assert got == ["deepseek-one", "deepseek-two"]

    def test_empty_payload_returns_empty(self):
        with patch("urllib.request.urlopen", _urlopen_mock({"data": []})):
            assert discover_chat_models("https://api.test.com/v1", "key") == []


# ── 2. _discover_models / _candidate_models ──


class TestCandidateModels:
    """候选列表的构造与各种退化路径"""

    @staticmethod
    def _cfg(**kw) -> PanguConfig:
        base = dict(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_model="cfg-model",
            # 必填：_discover_models 见不到 base_url 会直接 return []，
            # patch 就不会被触发，断言会误判成「发现结果为空」。
            llm_base_url="https://api.test.com/v1",
        )
        base.update(kw)
        return PanguConfig(**base)

    def test_configured_model_is_always_first(self):
        eng = LLMEngine(self._cfg())
        with patch("pangu.core.llm.discover_chat_models", return_value=["other-a", "other-b"]):
            got = eng._candidate_models()
        assert got[0] == "cfg-model"
        assert set(got) == {"cfg-model", "other-a", "other-b"}

    def test_empty_config_takes_discovered_list(self):
        eng = LLMEngine(self._cfg(llm_model=""))
        discovered = ["DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash"]
        with patch("pangu.core.llm.discover_chat_models", return_value=discovered) as m:
            got = eng._candidate_models()
        assert got == discovered
        m.assert_called_once()

    def test_no_duplicates(self):
        eng = LLMEngine(self._cfg(llm_model="other-a"))
        with patch("pangu.core.llm.discover_chat_models", return_value=["other-a", "other-b"]):
            got = eng._candidate_models()
        assert len(got) == len(set(got))

    def test_discover_without_base_url_returns_empty(self):
        """未配 base_url → 不发起任何请求，直接空列表"""
        eng = LLMEngine(self._cfg(llm_base_url=""))
        with patch("pangu.core.llm.discover_chat_models") as m:
            assert eng._discover_models() == []
        m.assert_not_called()

    def test_discover_without_key_returns_empty(self):
        eng = LLMEngine(self._cfg(llm_api_key="", llm_api_key_file="/nonexistent/key"))
        with patch("pangu.core.llm.discover_chat_models") as m:
            assert eng._discover_models() == []
        m.assert_not_called()

    def test_discover_failure_degrades_to_empty(self):
        """网络失败不抛异常，按「没有备选」继续"""
        eng = LLMEngine(self._cfg(llm_base_url="https://api.test.com/v1"))
        with patch("pangu.core.llm.discover_chat_models", side_effect=OSError("no route")):
            assert eng._discover_models() == []

    def test_candidate_models_degrades_to_configured_only(self):
        eng = LLMEngine(self._cfg(llm_base_url="https://api.test.com/v1"))
        with patch("pangu.core.llm.discover_chat_models", side_effect=OSError("no route")):
            assert eng._candidate_models() == ["cfg-model"]


# ── 3. chat() 的懒发现与切换 ──


class TestChatLazyDiscovery:
    """chat() 的核心契约：配置了模型且成功 → 绝不触网"""

    @staticmethod
    def _engine(**cfg_kw) -> LLMEngine:
        base = dict(llm_provider="openai", llm_api_key="test-key",
                    llm_model="cfg-model", llm_base_url="https://api.test.com/v1",
                    llm_max_retries=3, llm_retry_delay=0.001)
        base.update(cfg_kw)
        eng = LLMEngine(PanguConfig(**base))
        eng._cache_enabled = False
        return eng

    @pytest.mark.asyncio
    async def test_success_never_discovers(self):
        """配置了模型且首次成功 → 不调用 discover（本回归的判据）"""
        eng = self._engine()
        eng._do_chat = AsyncMock(return_value=_ok("fine"))
        with patch("pangu.core.llm.discover_chat_models") as m:
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert r.content == "fine"
        m.assert_not_called()          # ← A1 的核心断言

    @pytest.mark.asyncio
    async def test_discovery_happens_only_after_first_model_fails(self):
        """首选失败 → 此刻才发现备选并切换"""
        eng = self._engine()
        calls: list[str | None] = []

        async def fake(provider, messages, system="", temperature=0.7,
                       max_tokens=4096, json_mode=False, model=None):
            calls.append(model)
            return _ok() if model == "backup-model" else _fail()

        eng._do_chat = fake
        with patch("pangu.core.llm.discover_chat_models", return_value=["backup-model"]) as m:
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)

        assert r.content == "success"
        assert calls == ["cfg-model", "backup-model"]
        m.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_config_discovers_upfront(self):
        """配置留空 → 一开始就发现（否则连候选都没有）"""
        eng = self._engine(llm_model="")
        eng._do_chat = AsyncMock(return_value=_ok())
        with patch("pangu.core.llm.discover_chat_models", return_value=["auto-model"]) as m:
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert r.content == "success"
        m.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_on_rate_limit(self):
        """首选限流 → 切到下一候选，成功即返回"""
        eng = self._engine()
        calls: list[str | None] = []

        async def fake(provider, messages, system="", temperature=0.7,
                       max_tokens=4096, json_mode=False, model=None):
            calls.append(model)
            return _ok("from-backup") if model == "m2" else _fail()

        eng._do_chat = fake
        with patch("pangu.core.llm.discover_chat_models", return_value=["m2"]):
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert r.content == "from-backup"
        assert calls == ["cfg-model", "m2"]   # 成功即停，不打剩余候选

    @pytest.mark.asyncio
    async def test_switch_on_invalid_json(self):
        """JSON 模式下输出不可解析 → 换下一候选"""
        eng = self._engine()
        calls: list[str | None] = []

        async def fake(provider, messages, system="", temperature=0.7,
                       max_tokens=4096, json_mode=False, model=None):
            calls.append(model)
            if model == "m2":
                return _ok('{"title": "t"}')
            return _ok("不是 JSON 的纯文本")

        eng._do_chat = fake
        with patch("pangu.core.llm.discover_chat_models", return_value=["m2"]):
            r = await eng.chat([{"role": "user", "content": "hi"}],
                               temperature=0.7, json_mode=True)
        assert r.content == '{"title": "t"}'
        assert calls == ["cfg-model", "m2"]

    @pytest.mark.asyncio
    async def test_all_fail_returns_last_response(self):
        """候选全败且轮次耗尽 → 返回最后一次响应，交由调用方降级"""
        eng = self._engine(llm_max_retries=2, llm_model="")
        eng._do_chat = AsyncMock(return_value=_fail())
        with patch("pangu.core.llm.discover_chat_models", return_value=["m1"]):
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert r.content.startswith("[LMM 调用失败")

    @pytest.mark.asyncio
    async def test_no_network_when_discovery_unavailable(self):
        """首选失败但发现不可用 → 不因发现失败而抛异常"""
        eng = self._engine(llm_max_retries=2)
        eng._do_chat = AsyncMock(return_value=_fail())
        with patch("pangu.core.llm.discover_chat_models", side_effect=OSError("no route")):
            r = await eng.chat([{"role": "user", "content": "hi"}], temperature=0.7)
        assert r.content.startswith("[LMM 调用失败")
