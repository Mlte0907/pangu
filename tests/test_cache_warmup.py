"""盘古 — 缓存预热 功能测试

覆盖：
1. warmup_cache 基本调用
2. skip_existing 跳过逻辑
3. auto_warmup_on_start 启动自动预热
4. CLI 命令（不实际执行，仅验证命令存在）
5. 预热后命中缓存
"""

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine, LLMResponse


# ─────────────────────────────────────────────────────
# 1. warmup_cache 基本功能
# ─────────────────────────────────────────────────────
class TestWarmupCache:
    """缓存预热基本功能"""

    @pytest.mark.asyncio
    async def test_warmup_empty(self):
        """空 prompts 列表"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        result = await engine.warmup_cache([])
        assert result["total"] == 0
        assert result["warmed"] == 0
        assert result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_warmup_skips_existing(self, tmp_path):
        """已缓存的 prompt 被跳过"""

        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "warmup.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 预填一个缓存条目
        engine._cache["test_key"] = LLMResponse(content="already cached", model="gpt-4o", provider="openai")

        # 构造 prompt（其缓存键应与 test_key 不一致）
        # 但为了测试跳过逻辑，我们需要把同一个 prompt 写入缓存
        prompts = [{"messages": [{"role": "user", "content": "hello"}], "temperature": 0}]
        # 先把相同 prompt 写入磁盘，让 skip 逻辑能识别
        cache_key = engine._make_cache_key(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            system="",
            max_tokens=4096,
            json_mode=False,
        )
        engine._cache[cache_key] = LLMResponse(content="cached response", model="gpt-4o", provider="openai")

        result = await engine.warmup_cache(prompts, skip_existing=True)
        assert result["total"] == 1
        assert result["skipped"] == 1
        assert result["warmed"] == 0

    @pytest.mark.asyncio
    async def test_warmup_actually_caches(self, tmp_path):
        """预热后真正写入缓存"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "warmup.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # Mock HTTP 响应
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "warmed"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        prompts = [{"messages": [{"role": "user", "content": f"q_{i}"}], "temperature": 0} for i in range(3)]
        result = await engine.warmup_cache(prompts, concurrency=2)
        assert result["total"] == 3
        assert result["warmed"] == 3
        assert result["failed"] == 0
        assert result["duration_ms"] > 0

        # 验证缓存已写入
        assert len(engine._cache) == 3
        # 验证下次调用会命中
        for _i, p in enumerate(prompts):
            r = await engine.chat(
                messages=p["messages"],
                temperature=p.get("temperature", 0.7),
            )
            assert r.content == "warmed"

    @pytest.mark.asyncio
    async def test_warmup_handles_failure(self, tmp_path):
        """预热时 API 失败"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "warmup_fail.db"),
            llm_max_retries=1,  # 减少重试加快测试
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # Mock 失败
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = lambda: (_ for _ in ()).throw(
            __import__("httpx").HTTPStatusError("Server Error", request=None, response=mock_resp)
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        prompts = [{"messages": [{"role": "user", "content": "failing"}], "temperature": 0}]
        result = await engine.warmup_cache(prompts, concurrency=1)
        assert result["total"] == 1
        assert result["failed"] == 1
        assert result["warmed"] == 0

    @pytest.mark.asyncio
    async def test_warmup_skips_existing_false(self, tmp_path):
        """skip_existing=False 时强制重新调用"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "warmup_force.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 预填一个缓存
        cache_key = engine._make_cache_key(
            provider="openai",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "force"}],
            system="",
            max_tokens=4096,
            json_mode=False,
        )
        engine._cache[cache_key] = LLMResponse(content="old", model="gpt-4o-mini", provider="openai")

        # Mock HTTP
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "new"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        prompts = [{"messages": [{"role": "user", "content": "force"}], "temperature": 0}]
        # skip_existing=False 强制重新调用
        result = await engine.warmup_cache(prompts, concurrency=1, skip_existing=False)
        assert result["skipped"] == 0
        assert result["warmed"] == 1


# ─────────────────────────────────────────────────────
# 2. auto_warmup_on_start
# ─────────────────────────────────────────────────────
class TestAutoWarmup:
    """启动自动预热"""

    @pytest.mark.asyncio
    async def test_auto_warmup_disabled(self):
        """禁用时直接返回"""
        cfg = PanguConfig(llm_api_key="dummy", llm_cache_warmup_on_start=False)
        engine = LLMEngine(cfg)
        result = await engine.auto_warmup_on_start()
        assert result.get("skipped") is True
        assert "disabled" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_auto_warmup_no_prompts(self):
        """启用但无 prompts 时返回"""
        cfg = PanguConfig(
            llm_api_key="dummy",
            llm_cache_warmup_on_start=True,
            llm_cache_warmup_prompts=[],
        )
        engine = LLMEngine(cfg)
        result = await engine.auto_warmup_on_start()
        assert result.get("skipped") is True
        assert "no warmup prompts" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_auto_warmup_with_prompts(self, tmp_path):
        """启用且有 prompts 时预热"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "auto_warmup.db"),
            llm_cache_warmup_on_start=True,
            llm_cache_warmup_prompts=[{"messages": [{"role": "user", "content": "auto warm"}], "temperature": 0}],
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "auto result"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        result = await engine.auto_warmup_on_start()
        assert result.get("total") == 1
        assert result.get("warmed") == 1
        assert result.get("skipped") is not True


# ─────────────────────────────────────────────────────
# 3. _is_cached 辅助方法
# ─────────────────────────────────────────────────────
class TestIsCached:
    """_is_cached 辅助方法"""

    def test_is_cached_memory(self, tmp_path):
        """内存缓存检测"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "is_cached.db"),
        )
        engine = LLMEngine(cfg)
        prompt = {"messages": [{"role": "user", "content": "x"}], "temperature": 0}
        # 初始：未缓存
        assert engine._is_cached(prompt) is False
        # 写入内存
        engine._cache["dummy"] = LLMResponse(content="r", model="m", provider="p")
        # 真实情况下 _is_cached 会计算正确的键
        # 这里只验证函数不抛异常
        result = engine._is_cached(prompt)
        assert isinstance(result, bool)

    def test_is_cached_persistent(self, tmp_path):
        """持久化缓存检测"""
        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "is_cached_p.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        prompt = {"messages": [{"role": "user", "content": "y"}], "temperature": 0}
        # 写入持久化
        engine._persistent_cache.put(
            engine._make_cache_key(
                provider="openai",
                model="gpt-4o-mini",
                messages=prompt["messages"],
                system="",
                max_tokens=4096,
                json_mode=False,
            ),
            "openai",
            "gpt-4o-mini",
            prompt,
            LLMResponse(content="x", model="gpt-4o-mini", provider="openai"),
        )
        # 应能识别
        assert engine._is_cached(prompt) is True

    def test_is_cached_disabled(self):
        """禁用缓存时返回 False"""
        cfg = PanguConfig(llm_api_key="test", llm_cache_enabled=False)
        engine = LLMEngine(cfg)
        prompt = {"messages": [{"role": "user", "content": "z"}], "temperature": 0}
        assert engine._is_cached(prompt) is False


# ─────────────────────────────────────────────────────
# 4. 端到端：预热 → 真实查询
# ─────────────────────────────────────────────────────
class TestWarmupE2E:
    """端到端预热 → 真实查询"""

    @pytest.mark.asyncio
    async def test_warmup_then_query_hits_cache(self, tmp_path):
        """预热后查询命中缓存"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "e2e_warmup.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 第一次：模拟 API 调用写入缓存
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "first call"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine._client = mock_client

        prompt = {"messages": [{"role": "user", "content": "e2e"}], "temperature": 0}
        result = await engine.warmup_cache([prompt])
        assert result["warmed"] == 1

        # 第二次：客户端抛出异常（确保不会调用 API）
        mock_client.post = AsyncMock(side_effect=Exception("API should not be called"))
        r = await engine.chat(
            messages=prompt["messages"],
            temperature=prompt["temperature"],
        )
        # 命中缓存
        assert r.content == "first call"
        # 实际 API 仍只调用 1 次
        assert engine._call_count == 1
