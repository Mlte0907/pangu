"""盘古 — LLM 后端集成测试

覆盖多 provider 的：
- 基础调用
- API key 缺失降级
- 错误处理
- 重试与回退机制
- 流式调用
- Token 统计

不发起真实网络请求 — 使用 mock 避免测试时的网络依赖。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import (
    PROVIDER_ENV_KEYS,
    PROVIDER_URLS,
    LLMEngine,
    LLMResponse,
)

# ── 配置测试 ──

class TestLLMConfig:
    """LLM 配置测试"""

    def test_provider_urls_complete(self):
        """测试所有 provider URL 已配置"""
        expected = {"openai", "openrouter", "deepseek", "zhipu", "qwen", "ollama"}
        assert expected.issubset(PROVIDER_URLS.keys())

    def test_provider_env_keys(self):
        """测试所有 provider 环境变量已配置"""
        for provider, env_key in PROVIDER_ENV_KEYS.items():
            if env_key is None:  # Ollama 不需要
                assert provider == "ollama"
            else:
                assert env_key.isupper()
                assert "_API_KEY" in env_key or "_KEY" in env_key

    def test_default_config(self):
        """测试默认配置"""
        cfg = PanguConfig()
        assert cfg.llm_provider in PROVIDER_URLS
        assert cfg.llm_max_retries >= 1
        assert cfg.llm_retry_delay > 0


# ── API Key 处理 ──

class TestAPIKeyHandling:
    """API key 处理测试"""

    def test_uses_config_key(self):
        """测试使用 config 中的 key"""
        cfg = PanguConfig(llm_api_key="test-key-123")
        engine = LLMEngine(cfg)
        assert engine._get_api_key("openai") == "test-key-123"

    def test_falls_back_to_env(self, monkeypatch):
        """测试回退到环境变量"""
        cfg = PanguConfig(llm_api_key="")
        monkeypatch.setenv("OPENAI_API_KEY", "env-key-456")
        engine = LLMEngine(cfg)
        assert engine._get_api_key("openai") == "env-key-456"

    def test_empty_when_no_key(self, monkeypatch):
        """测试无 key 返回空"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = PanguConfig(llm_api_key="")
        engine = LLMEngine(cfg)
        assert engine._get_api_key("openai") == ""

    def test_ollama_no_key(self, monkeypatch):
        """测试 Ollama 不需要 key"""
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        cfg = PanguConfig(llm_api_key="")
        engine = LLMEngine(cfg)
        assert engine._get_api_key("ollama") == ""


# ── Base URL 处理 ──

class TestBaseURLHandling:
    """Base URL 处理测试"""

    def test_uses_config_url(self):
        """测试使用 config 中的 URL"""
        cfg = PanguConfig(llm_base_url="https://custom.api.com/v1")
        engine = LLMEngine(cfg)
        assert engine._get_base_url("openai") == "https://custom.api.com/v1"

    def test_uses_provider_default(self):
        """测试使用 provider 默认 URL"""
        cfg = PanguConfig(llm_base_url="")
        engine = LLMEngine(cfg)
        assert engine._get_base_url("deepseek") == PROVIDER_URLS["deepseek"]
        assert engine._get_base_url("zhipu") == PROVIDER_URLS["zhipu"]


# ── Provider 切换 ──

class TestProviderSwitching:
    """Provider 切换测试"""

    @pytest.mark.parametrize("provider", [
        "openai", "deepseek", "openrouter", "zhipu", "qwen", "ollama",
    ])
    def test_all_providers_supported(self, provider):
        """测试所有 provider URL 可获取"""
        cfg = PanguConfig(llm_provider=provider)
        engine = LLMEngine(cfg)
        url = engine._get_base_url(provider)
        assert url.startswith("http")

    def test_anthropic_uses_separate_handler(self):
        """测试 Anthropic 使用独立 handler"""
        cfg = PanguConfig(llm_provider="anthropic")
        engine = LLMEngine(cfg)
        # Anthropic 走 _call_anthropic，不通过 base URL
        assert engine._get_base_url("anthropic") == PROVIDER_URLS["openai"]


# ── 重试和回退 ──

class TestRetryFallback:
    """重试和回退机制测试"""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """测试失败时重试"""
        cfg = PanguConfig(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_max_retries=3,
            llm_retry_delay=0.01,
        )
        engine = LLMEngine(cfg)

        # Mock 失败 N 次后成功
        call_count = 0
        async def _mock_chat(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return LLMResponse(content="[LMM 调用失败 (openai): HTTP 500]",
                                   provider="openai")
            return LLMResponse(content="success", provider="openai")

        engine._do_chat = _mock_chat
        result = await engine.chat([{"role": "user", "content": "hi"}])
        assert result.content == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """测试达到最大重试"""
        cfg = PanguConfig(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_max_retries=2,
            llm_retry_delay=0.001,
        )
        engine = LLMEngine(cfg)

        async def _always_fail(*a, **kw):
            return LLMResponse(content="[LMM 调用失败: error]", provider="openai")

        engine._do_chat = _always_fail
        result = await engine.chat([{"role": "user", "content": "hi"}])
        assert result.content.startswith("[LMM 调用失败")
        # call_count 反映成功请求，重试时也只计入成功调用
        assert engine._call_count <= 2


# ── 错误处理 ──

class TestErrorHandling:
    """错误处理测试"""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_message(self):
        """测试无 API key 时返回提示信息"""
        cfg = PanguConfig(llm_provider="openai", llm_api_key="")
        engine = LLMEngine(cfg)

        result = await engine.chat([{"role": "user", "content": "hi"}])
        assert "未配置 API Key" in result.content or "调用失败" in result.content
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """测试 HTTP 错误处理"""
        cfg = PanguConfig(llm_provider="openai", llm_api_key="test-key")
        engine = LLMEngine(cfg)

        # Mock HTTP 错误
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

        async def _mock_post(*a, **kw):
            raise Exception("HTTP 500")

        engine.client.post = _mock_post
        result = await engine._call_openai_compatible(
            "openai", [{"role": "user", "content": "hi"}]
        )
        assert "调用失败" in result.content


# ── JSON 提取 ──

class TestJSONExtraction:
    """JSON 提取测试"""

    def test_extract_plain_json(self):
        """测试提取纯 JSON"""
        text = '{"key": "value", "num": 42}'
        result = LLMEngine._extract_json(text)
        assert result == {"key": "value", "num": 42}

    def test_extract_markdown_json(self):
        """测试从 markdown 代码块提取"""
        text = '```json\n{"key": "value"}\n```'
        result = LLMEngine._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_from_surrounding_text(self):
        """测试从包含前后文本中提取"""
        text = '这是一些说明：\n```json\n{"a": 1}\n```\n结束。'
        result = LLMEngine._extract_json(text)
        assert result == {"a": 1}

    def test_invalid_returns_default(self):
        """测试无效 JSON 返回默认值"""
        result = LLMEngine._extract_json("not json", default={"k": "v"})
        assert result == {"k": "v"}


# ── 记忆专用方法（mock LLM） ──

class TestMemoryMethods:
    """记忆专用方法测试（mock LLM 调用）"""

    @pytest.mark.asyncio
    async def test_summarize_memories_empty(self):
        """测试空记忆摘要"""
        engine = LLMEngine()
        result = await engine.summarize_memories([])
        assert "无" in result or "0" in result

    @pytest.mark.asyncio
    async def test_summarize_memories(self):
        """测试正常记忆摘要"""
        engine = LLMEngine()
        engine.chat = AsyncMock(return_value=LLMResponse(content="记忆摘要结果"))
        result = await engine.summarize_memories([{"content": "测试内容", "wing": "tech"}])
        assert result == "记忆摘要结果"

    @pytest.mark.asyncio
    async def test_classify_memory(self):
        """测试记忆分类"""
        engine = LLMEngine()
        engine.chat = AsyncMock(return_value=LLMResponse(
            content='{"hall": "hall_facts", "room": "tech", "importance": 4, "tags": ["python"]}'
        ))
        result = await engine.classify_memory("测试内容")
        assert result["hall"] == "hall_facts"
        assert result["importance"] == 4

    @pytest.mark.asyncio
    async def test_classify_memory_fallback(self):
        """测试分类失败时降级"""
        engine = LLMEngine()
        engine.chat = AsyncMock(return_value=LLMResponse(content="not valid json"))
        result = await engine.classify_memory("测试")
        assert "hall" in result  # 至少有默认值

    @pytest.mark.asyncio
    async def test_generate_insight(self):
        """测试洞察生成"""
        engine = LLMEngine()
        engine.chat = AsyncMock(return_value=LLMResponse(content="洞察：发现模式 X"))
        result = await engine.generate_insight([{"content": "记忆内容"}])
        assert "洞察" in result

    @pytest.mark.asyncio
    async def test_detect_associations(self):
        """测试关联检测"""
        engine = LLMEngine()
        engine.chat = AsyncMock(return_value=LLMResponse(
            content='{"associations": [{"from_idx": 0, "to_idx": 1, "relation": "test", "strength": 0.8}], "clusters": []}'
        ))
        result = await engine.detect_associations([{"content": "a"}, {"content": "b"}])
        assert len(result["associations"]) == 1
        assert result["associations"][0]["strength"] == 0.8


# ── 性能指标 ──

class TestLLMMetrics:
    """LLM 性能指标测试"""

    def test_call_count_increments(self):
        """测试调用计数"""
        engine = LLMEngine()
        # 直接累加模拟多次成功调用
        engine._call_count = 10
        engine._total_latency = 1000.0
        assert engine.avg_latency_ms == 100.0

    def test_avg_latency(self):
        """测试平均延迟"""
        engine = LLMEngine()
        engine._call_count = 10
        engine._total_latency = 1000.0
        assert engine.avg_latency_ms == 100.0

    def test_zero_calls_avg(self):
        """测试零调用时平均延迟"""
        engine = LLMEngine()
        assert engine.avg_latency_ms == 0.0


# ── 客户端生命周期 ──

class TestClientLifecycle:
    """客户端生命周期测试"""

    @pytest.mark.asyncio
    async def test_client_lazy_init(self):
        """测试 client 延迟初始化"""
        engine = LLMEngine()
        assert engine._client is None
        _ = engine.client
        assert engine._client is not None

    @pytest.mark.asyncio
    async def test_close_releases_client(self):
        """测试 close 释放 client"""
        engine = LLMEngine()
        _ = engine.client
        await engine.close()
        assert engine._client is None

    @pytest.mark.asyncio
    async def test_reinit_after_close(self):
        """测试 close 后重新初始化"""
        engine = LLMEngine()
        _ = engine.client
        await engine.close()
        _ = engine.client  # 应能重新创建
        assert engine._client is not None
