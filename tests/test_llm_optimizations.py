"""盘古 — LLM 优化功能测试

覆盖：
1. JSON Mode 启用
2. _extract_json 鲁棒性（4 种输入格式）
3. 成本估算（多种 provider/model）
4. token 跟踪
5. JSON 失败重试
6. LRU 响应缓存
7. 批量并发
8. 缓存性能基准
"""

import asyncio
import time

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import PRICING_PER_1K, PROVIDER_URLS, LLMEngine


# ─────────────────────────────────────────────────────
# 1. JSON Mode
# ─────────────────────────────────────────────────────
class TestJSONMode:
    """JSON 模式相关测试"""

    def test_extract_json_pure(self):
        """纯 JSON 解析"""
        result = LLMEngine._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_markdown(self):
        """Markdown 包裹的 JSON"""
        result = LLMEngine._extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_extract_json_markdown_no_lang(self):
        """无语言标记的 Markdown"""
        result = LLMEngine._extract_json('```\n{"b": 2}\n```')
        assert result == {"b": 2}

    def test_extract_json_with_prefix(self):
        """带前缀文字的 JSON"""
        result = LLMEngine._extract_json('好的，输出如下：\n{"x": 2}\n如上')
        assert result == {"x": 2}

    def test_extract_json_array(self):
        """纯数组自动包装为 dict"""
        result = LLMEngine._extract_json('[{"a": 1}, {"b": 2}]')
        assert result == {"items": [{"a": 1}, {"b": 2}]}

    def test_extract_json_array_in_markdown(self):
        """Markdown 数组自动包装"""
        result = LLMEngine._extract_json('```json\n[{"a":1}, {"b":2}]\n```')
        assert result == {"items": [{"a": 1}, {"b": 2}]}

    def test_extract_json_empty(self):
        """空字符串返回默认值"""
        result = LLMEngine._extract_json("", default={"fallback": True})
        assert result == {"fallback": True}

    def test_extract_json_invalid(self):
        """完全无效输入返回默认值"""
        result = LLMEngine._extract_json("not json at all", default={"x": 0})
        assert result == {"x": 0}

    def test_extract_json_partial(self):
        """部分 JSON（不完整）返回默认值"""
        result = LLMEngine._extract_json('{"a": 1, ', default={"x": 0})
        assert result == {"x": 0}

    def test_extract_json_nested(self):
        """嵌套 JSON"""
        text = '{"level1": {"level2": [1, 2, 3]}}'
        result = LLMEngine._extract_json(text)
        assert result == {"level1": {"level2": [1, 2, 3]}}


# ─────────────────────────────────────────────────────
# 2. 成本估算
# ─────────────────────────────────────────────────────
class TestCostEstimation:
    """成本估算测试"""

    def test_pricing_table_exists(self):
        """价格表已配置"""
        assert "openai" in PRICING_PER_1K
        assert "zhipu" in PRICING_PER_1K
        assert "deepseek" in PRICING_PER_1K

    def test_estimate_zhipu_free(self):
        """智谱 glm-4-flash 新用户免费"""
        engine = LLMEngine(
            PanguConfig(
                llm_provider="zhipu",
                llm_model="glm-4-flash",
                llm_api_key="dummy",
            )
        )
        cost = engine._estimate_cost("zhipu", 1000, 1000)
        assert cost == 0.0

    def test_estimate_openai_gpt4o_mini(self):
        """OpenAI gpt-4o-mini 价格"""
        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="dummy",
            )
        )
        # 1000 input + 1000 output = 0.15 + 0.6 = 0.75 USD cents
        cost = engine._estimate_cost("openai", 1000, 1000)
        assert abs(cost - 0.00075) < 1e-6

    def test_estimate_deepseek(self):
        """DeepSeek 价格"""
        engine = LLMEngine(
            PanguConfig(
                llm_provider="deepseek",
                llm_model="deepseek-chat",
                llm_api_key="dummy",
            )
        )
        # 1000 input + 1000 output = 0.14 + 0.28 = 0.42 USD mills
        cost = engine._estimate_cost("deepseek", 1000, 1000)
        assert abs(cost - 0.00042) < 1e-6

    def test_estimate_unknown_model(self):
        """未知模型返回 0"""
        engine = LLMEngine(
            PanguConfig(
                llm_provider="zhipu",
                llm_model="unknown-model-xyz",
                llm_api_key="dummy",
            )
        )
        cost = engine._estimate_cost("zhipu", 1000, 1000)
        assert cost == 0.0

    def test_estimate_ollama_free(self):
        """Ollama 本地免费"""
        engine = LLMEngine(
            PanguConfig(
                llm_provider="ollama",
                llm_model="qwen2:7b",
                llm_base_url="http://localhost:11434/v1",
            )
        )
        cost = engine._estimate_cost("ollama", 10000, 5000)
        assert cost == 0.0


# ─────────────────────────────────────────────────────
# 3. 引擎统计
# ─────────────────────────────────────────────────────
class TestEngineStats:
    """引擎统计测试"""

    def test_initial_stats(self):
        """初始统计"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        stats = engine.get_stats()
        assert stats["call_count"] == 0
        assert stats["total_prompt_tokens"] == 0
        assert stats["total_completion_tokens"] == 0
        assert stats["total_tokens"] == 0
        assert stats["estimated_cost_usd"] == 0.0
        assert stats["provider"] == "openai"  # default
        assert "avg_latency_ms" in stats

    def test_stats_after_call(self):
        """调用后统计更新"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        # 手动更新内部状态
        engine._call_count = 5
        engine._total_latency = 1000
        engine._total_prompt_tokens = 100
        engine._total_completion_tokens = 50
        engine._estimated_cost_usd = 0.001

        stats = engine.get_stats()
        assert stats["call_count"] == 5
        assert stats["total_prompt_tokens"] == 100
        assert stats["total_completion_tokens"] == 50
        assert stats["total_tokens"] == 150
        assert stats["estimated_cost_usd"] == 0.001
        assert stats["avg_latency_ms"] == 200.0


# ─────────────────────────────────────────────────────
# 4. 配置 + 提供商矩阵
# ─────────────────────────────────────────────────────
class TestProviderMatrix:
    """提供商配置矩阵测试"""

    @pytest.mark.parametrize(
        "provider,env_key,model",
        [
            ("zhipu", "ZHIPU_API_KEY", "glm-4-flash"),
            ("openai", "OPENAI_API_KEY", "gpt-4o-mini"),
            ("deepseek", "DEEPSEEK_API_KEY", "deepseek-chat"),
            ("qwen", "DASHSCOPE_API_KEY", "qwen-turbo"),
            ("openrouter", "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
        ],
    )
    def test_provider_url_configured(self, provider, env_key, model):
        """所有 provider URL 已配置"""
        assert provider in PROVIDER_URLS
        assert PROVIDER_URLS[provider].startswith("http")

    def test_all_providers_have_pricing(self):
        """所有 provider 都有价格表条目"""
        for provider in ["openai", "zhipu", "deepseek", "qwen"]:
            assert provider in PRICING_PER_1K
            assert len(PRICING_PER_1K[provider]) > 0

    def test_estimate_for_all_models(self):
        """为每个 provider 的每个模型估算成本"""
        for provider, models in PRICING_PER_1K.items():
            for model in models:
                engine = LLMEngine(
                    PanguConfig(
                        llm_provider=provider,
                        llm_model=model,
                        llm_api_key="dummy",
                    )
                )
                cost = engine._estimate_cost(provider, 1000, 1000)
                # 应该有合理的成本（除非免费）
                assert cost >= 0


# ─────────────────────────────────────────────────────
# 5. JSON Mode 集成（mock）
# ─────────────────────────────────────────────────────
class TestJSONModeIntegration:
    """JSON Mode 端到端集成（mock HTTP）"""

    @pytest.mark.asyncio
    async def test_json_mode_payload(self):
        """JSON mode 启用时 payload 包含 response_format"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        # 跟踪实际 payload
        captured_payload = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"key": "value"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        async def mock_post(url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return mock_resp

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=mock_post)
        # 直接设置私有属性
        engine._client = mock_client

        response = await engine._call_openai_compatible(
            "openai",
            messages=[{"role": "user", "content": "test"}],
            json_mode=True,
        )

        assert response.content == '{"key": "value"}'
        assert captured_payload.get("response_format") == {"type": "json_object"}
        # Token 累计
        assert engine._total_prompt_tokens == 10
        assert engine._total_completion_tokens == 5

    @pytest.mark.asyncio
    async def test_json_extract_after_chat(self):
        """chat json_mode=True 时解析 JSON"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
                llm_max_retries=2,
            )
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '```json\n{"x": 42}\n```'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        response = await engine.chat(
            messages=[{"role": "user", "content": "test"}],
            json_mode=True,
        )
        assert response.content == '```json\n{"x": 42}\n```'


# ─────────────────────────────────────────────────────
# 6. LRU 响应缓存
# ─────────────────────────────────────────────────────
class TestResponseCache:
    """响应缓存测试"""

    def test_cache_key_uniqueness(self):
        """不同参数生成不同缓存键"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        key1 = engine._make_cache_key(
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "a"}],
            "sys",
            100,
            False,
        )
        key2 = engine._make_cache_key(
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "b"}],
            "sys",
            100,
            False,
        )
        assert key1 != key2

    def test_cache_key_consistency(self):
        """相同参数生成相同键"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        args = (
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "x"}],
            "sys",
            100,
            False,
        )
        key1 = engine._make_cache_key(*args)
        key2 = engine._make_cache_key(*args)
        assert key1 == key2

    def test_cache_lru_eviction(self):
        """LRU 淘汰机制"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        engine._cache_max = 3

        for i in range(5):
            engine._put_cache(f"key_{i}", f"value_{i}")

        assert len(engine._cache) == 3
        # 最旧的两个被淘汰
        assert "key_0" not in engine._cache
        assert "key_1" not in engine._cache
        # 最新的三个保留
        assert "key_2" in engine._cache
        assert "key_3" in engine._cache
        assert "key_4" in engine._cache

    def test_cache_lru_update(self):
        """访问已存在键会更新 LRU 顺序"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        engine._cache_max = 3

        engine._put_cache("a", "A")
        engine._put_cache("b", "B")
        engine._put_cache("c", "C")
        # 访问 a（移到末尾）
        if "a" in engine._cache:
            engine._cache.move_to_end("a")
        # 添加 d（应淘汰 b）
        engine._put_cache("d", "D")

        assert "a" in engine._cache
        assert "b" not in engine._cache
        assert "c" in engine._cache
        assert "d" in engine._cache

    def test_clear_cache(self):
        """清空缓存"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        for i in range(5):
            engine._put_cache(f"k_{i}", f"v_{i}")
        count = engine.clear_cache()
        assert count == 5
        assert len(engine._cache) == 0

    def test_cache_disabled(self):
        """禁用时不写入"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        engine._cache_enabled = False
        engine._put_cache("k", "v")
        assert len(engine._cache) == 0

    def test_stats_includes_cache(self):
        """get_stats 包含缓存统计"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        engine._cache_hits = 3
        engine._cache_misses = 2
        engine._put_cache("k1", "v1")

        stats = engine.get_stats()
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "cache_hit_rate" in stats
        assert "cache_size" in stats
        assert stats["cache_hits"] == 3
        assert stats["cache_misses"] == 2
        assert stats["cache_size"] == 1
        assert stats["cache_hit_rate"] == 60.0  # 3/(3+2)*100

    @pytest.mark.asyncio
    async def test_chat_uses_cache(self):
        """chat 使用缓存（temperature=0）"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )
        # 清空持久化缓存（避免之前测试残留）
        engine.clear_persistent_cache()
        engine.clear_cache()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "cached response"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        # 第一次调用
        r1 = await engine.chat(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0,
        )
        assert r1.content == "cached response"
        assert engine._cache_misses == 1
        assert engine._call_count == 1

        # 第二次相同调用（应命中缓存）
        r2 = await engine.chat(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0,
        )
        assert r2.content == "cached response"
        assert engine._cache_hits == 1
        assert engine._call_count == 1  # 不应再增加

    @pytest.mark.asyncio
    async def test_chat_skips_cache_for_stochastic(self):
        """temperature>0 时不使用缓存"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "r"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        # 两次相同 temperature=0.7 调用
        await engine.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)
        await engine.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)
        # 两次都未命中缓存（temperature > 0）
        assert engine._call_count == 2
        assert engine._cache_misses == 2


# ─────────────────────────────────────────────────────
# 7. 批量并发
# ─────────────────────────────────────────────────────
class TestBatchOperations:
    """批量并发测试"""

    @pytest.mark.asyncio
    async def test_batch_chat_empty(self):
        """空 batch 返回空列表"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        result = await engine.batch_chat([])
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_chat_concurrent(self):
        """批量并发调用"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        call_count = 0
        call_log = []

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            call_log.append(call_count)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": f"response_{call_count}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            }
            mock_resp.raise_for_status = lambda: None
            # 模拟 100ms 延迟
            await asyncio.sleep(0.1)
            return mock_resp

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=mock_post)
        engine._client = mock_client

        batch = [{"messages": [{"role": "user", "content": f"q_{i}"}], "temperature": 0.7} for i in range(5)]
        start = time.time()
        results = await engine.batch_chat(batch, concurrency=3)
        elapsed = time.time() - start

        assert len(results) == 5
        # 5 个并发任务，每个 0.1s，并发度 3 → 约 0.2s（2 批）
        # 串行需要 0.5s
        assert elapsed < 0.4, f"并发应该更快，实际 {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_batch_chat_uses_cache(self):
        """批量调用使用缓存"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )
        # 清空持久化缓存
        engine.clear_persistent_cache()
        engine.clear_cache()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "r"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        # 3 个完全相同的请求（temperature=0）
        batch = [{"messages": [{"role": "user", "content": "same"}], "temperature": 0} for _ in range(3)]
        results = await engine.batch_chat(batch, concurrency=2, use_cache=True)
        assert len(results) == 3
        # 第一次 miss，后续 2 次 hit
        assert engine._cache_misses == 1
        assert engine._cache_hits == 2
        assert engine._call_count == 1  # 只实际调用 1 次

    @pytest.mark.asyncio
    async def test_batch_classify_memories(self):
        """批量分类"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": '{"hall": "hall_facts", "room": "test", "importance": 3, "tags": ["t1"]}'}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        memories = [{"id": f"m_{i}", "content": f"content {i}"} for i in range(5)]
        results = await engine.batch_classify_memories(memories, concurrency=2)

        assert len(results) == 5
        for i, r in enumerate(results):
            assert r["id"] == f"m_{i}"
            assert "classification" in r
            assert "hall" in r["classification"]

    @pytest.mark.asyncio
    async def test_batch_generate_wiki_pages(self):
        """批量 Wiki"""
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"title": "T", "summary": "S", "content": "C", "tags": ["a"]}'}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 50},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        pages = [
            {"title": f"Topic {i}", "memories": [{"wing": "w", "room": "r", "content": f"m {i}"}]} for i in range(3)
        ]
        results = await engine.batch_generate_wiki_pages(pages, concurrency=2)

        assert len(results) == 3
        for r in results:
            assert "title" in r
            assert "content" in r


# ─────────────────────────────────────────────────────
# 8. 缓存性能基准
# ─────────────────────────────────────────────────────
class TestCachePerformance:
    """缓存性能基准"""

    @pytest.mark.asyncio
    async def test_cache_speedup(self):
        """缓存命中应远快于实际调用"""
        import time as time_mod
        from unittest.mock import AsyncMock, MagicMock

        engine = LLMEngine(
            PanguConfig(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                llm_api_key="test-key",
                llm_base_url="https://api.test.com/v1",
            )
        )

        async def slow_mock(*args, **kwargs):
            await asyncio.sleep(0.2)  # 模拟 200ms 延迟
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "r"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            }
            mock_resp.raise_for_status = lambda: None
            return mock_resp

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=slow_mock)
        engine._client = mock_client

        # 第一次（无缓存）
        start = time_mod.time()
        await engine.chat(messages=[{"role": "user", "content": "x"}], temperature=0)
        t1 = time_mod.time() - start
        assert t1 >= 0.15  # 实际调用 ~200ms

        # 第二次（缓存命中）
        start = time_mod.time()
        await engine.chat(messages=[{"role": "user", "content": "x"}], temperature=0)
        t2 = time_mod.time() - start
        # 缓存命中应 < 5ms
        assert t2 < 0.01
        # 加速比
        speedup = t1 / max(t2, 0.001)
        assert speedup > 20, f"缓存加速比应 > 20x，实际 {speedup:.1f}x"
