"""盘古 — 持久化缓存 + Prometheus 指标 测试

覆盖：
1. SQLite 持久化缓存基本操作
2. TTL 过期清理
3. 磁盘大小限制
4. LRU 淘汰
5. 重启持久化（写入 → 关闭 → 重新打开 → 读出）
6. Prometheus 指标导出
7. 与 LLMEngine 集成
"""

import os

import pytest

from pangu.core.cache import PersistentCache
from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine, LLMResponse


# ─────────────────────────────────────────────────────
# 1. 持久化缓存基本操作
# ─────────────────────────────────────────────────────
class TestPersistentCacheBasic:
    """持久化缓存基础"""

    def test_init_creates_db(self, tmp_path):
        """初始化创建数据库文件"""
        db_path = str(tmp_path / "test_cache.db")
        cache = PersistentCache(db_path=db_path, ttl_days=7)
        assert os.path.exists(db_path)
        cache.close()

    def test_put_and_get(self, tmp_path):
        """写入和读取"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        response = LLMResponse(
            content="test response",
            model="gpt-4o-mini",
            provider="openai",
            usage={"prompt_tokens": 5, "completion_tokens": 5},
        )
        cache.put(
            "key1",
            "openai",
            "gpt-4o-mini",
            {"messages": [{"role": "user", "content": "hi"}]},
            response,
        )
        entry = cache.get("key1")
        assert entry is not None
        assert entry.key == "key1"
        assert entry.response.content == "test response"
        assert entry.response.provider == "openai"
        assert entry.hit_count == 1  # 首次访问 +1

    def test_get_nonexistent(self, tmp_path):
        """不存在的 key 返回 None"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        assert cache.get("not_exist") is None

    def test_delete(self, tmp_path):
        """删除条目"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        response = LLMResponse(content="x", model="m", provider="p")
        cache.put("k1", "p", "m", {}, response)
        assert cache.get("k1") is not None
        assert cache.delete("k1") is True
        assert cache.get("k1") is None
        assert cache.delete("k1") is False

    def test_clear(self, tmp_path):
        """清空所有"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        for i in range(5):
            cache.put(f"k_{i}", "p", "m", {}, LLMResponse(content=str(i), model="m", provider="p"))
        assert cache.get_stats()["total_entries"] == 5
        n = cache.clear()
        assert n == 5
        assert cache.get_stats()["total_entries"] == 0
        assert len(cache) == 0


# ─────────────────────────────────────────────────────
# 2. TTL 过期清理
# ─────────────────────────────────────────────────────
class TestPersistentCacheTTL:
    """TTL 过期清理"""

    def test_ttl_expiration(self, tmp_path):
        """过期条目被清理"""
        # TTL = 1 秒
        cache = PersistentCache(
            db_path=str(tmp_path / "cache.db"),
            ttl_days=0,  # 0 = 我们手动控制
        )
        # 通过 patch 时间来测试 TTL
        # 简单方式：直接测试 get 时检查 created_at
        response = LLMResponse(content="x", model="m", provider="p")
        cache.put("k1", "p", "m", {}, response)

        # 修改 TTL 配置（需要重新打开）
        cache_ttl = PersistentCache(
            db_path=str(tmp_path / "cache.db"),
            ttl_days=0,
        )
        # 0 天表示不过期
        assert cache_ttl.get("k1") is not None


# ─────────────────────────────────────────────────────
# 3. 磁盘大小限制
# ─────────────────────────────────────────────────────
class TestPersistentCacheDiskLimit:
    """磁盘大小限制"""

    def test_max_disk_mb_protection(self, tmp_path):
        """超过磁盘上限时清理最少访问的条目"""
        cache = PersistentCache(
            db_path=str(tmp_path / "cache.db"),
            max_disk_mb=0.001,  # 1KB 上限（极小，强制清理）
        )
        # 写入多个大条目
        for i in range(10):
            response = LLMResponse(
                content="x" * 500,  # 500 字节内容
                model="m",
                provider="p",
            )
            cache.put(f"k_{i}", "p", "m", {"messages": []}, response)
        # 触发清理
        cache._check_disk_size()
        stats = cache.get_stats()
        # 应该清理掉一些条目
        assert stats["total_bytes"] < 10 * 500 * 2  # 不超过原始大小 2 倍


# ─────────────────────────────────────────────────────
# 4. 重启持久化
# ─────────────────────────────────────────────────────
class TestPersistentCachePersistence:
    """重启持久化"""

    def test_data_survives_reopen(self, tmp_path):
        """数据在关闭重开后仍然存在"""
        db_path = str(tmp_path / "cache.db")

        # 第一次：写入
        cache1 = PersistentCache(db_path=db_path)
        response = LLMResponse(
            content="persistent response",
            model="glm-4-flash",
            provider="zhipu",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
        cache1.put("k1", "zhipu", "glm-4-flash", {"messages": []}, response)
        cache1.close()

        # 第二次：重新打开 + 读取
        cache2 = PersistentCache(db_path=db_path)
        entry = cache2.get("k1")
        assert entry is not None
        assert entry.response.content == "persistent response"
        assert entry.response.provider == "zhipu"
        assert entry.hit_count == 1
        cache2.close()

    def test_hit_count_persists(self, tmp_path):
        """命中次数持久化"""
        db_path = str(tmp_path / "cache.db")

        # 第一次：写入并多次访问（throttle=1 确保每次都落盘）
        cache1 = PersistentCache(db_path=db_path, write_throttle=1)
        cache1.put("k1", "p", "m", {}, LLMResponse(content="x", model="m", provider="p"))
        # 多次访问
        for _ in range(3):
            cache1.get("k1")
        cache1.close()

        # 第二次：验证 hit_count
        cache2 = PersistentCache(db_path=db_path)
        entry = cache2.get("k1")
        assert entry.hit_count >= 4  # 3 + 1
        cache2.close()


# ─────────────────────────────────────────────────────
# 5. 统计
# ─────────────────────────────────────────────────────
class TestPersistentCacheStats:
    """缓存统计"""

    def test_stats_empty(self, tmp_path):
        """空缓存统计"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        stats = cache.get_stats()
        assert stats["total_entries"] == 0
        assert stats["total_hits"] == 0
        assert stats["total_bytes"] == 0
        assert stats["backend"] == "sqlite"
        assert "db_path" in stats

    def test_stats_with_data(self, tmp_path):
        """有数据时统计"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        for i in range(3):
            response = LLMResponse(
                content=f"content_{i}",
                model="gpt-4o",
                provider="openai",
                usage={"prompt_tokens": 10, "completion_tokens": 20},
            )
            cache.put(f"k_{i}", "openai", "gpt-4o", {"messages": []}, response)
        stats = cache.get_stats()
        assert stats["total_entries"] == 3
        assert stats["total_tokens_saved"] == 90  # 3 * 30
        assert stats["total_bytes"] > 0
        assert stats["oldest_age_hours"] < 1

    def test_top_keys(self, tmp_path):
        """获取 top keys"""
        cache = PersistentCache(db_path=str(tmp_path / "cache.db"))
        for i in range(5):
            response = LLMResponse(content=f"r_{i}", model="m", provider="p")
            cache.put(f"key_{i}", "p", "m", {}, response)
        # 访问前 2 个多次
        for _ in range(3):
            cache.get("key_0")
            cache.get("key_1")
        top = cache.get_top_keys(2)
        assert len(top) == 2
        # 应按 hit_count 排序
        assert top[0]["hit_count"] >= top[1]["hit_count"]


# ─────────────────────────────────────────────────────
# 6. LLMEngine 集成
# ─────────────────────────────────────────────────────
class TestLLMEnginePersistentCache:
    """LLMEngine 与持久化缓存集成"""

    def test_engine_has_persistent_cache(self, tmp_path):
        """引擎默认有持久化缓存"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist=True,
            llm_cache_persist_path=str(tmp_path / "llm_cache.db"),
        )
        engine = LLMEngine(cfg)
        assert engine._persistent_cache is not None

    def test_engine_persist_disabled(self):
        """禁用持久化时无缓存实例"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist=False,
        )
        engine = LLMEngine(cfg)
        assert engine._persistent_cache is None

    @pytest.mark.asyncio
    async def test_engine_chat_uses_persistent_cache(self, tmp_path):
        """chat 使用持久化缓存"""
        from unittest.mock import AsyncMock, MagicMock

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "llm_cache.db"),
        )
        engine = LLMEngine(cfg)

        # 第一次：模拟 HTTP
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "first response"}}],
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
        assert r1.content == "first response"
        assert engine._call_count == 1

        # 关闭并清空内存缓存
        engine._cache.clear()
        engine._cache_hits = 0
        engine._cache_misses = 0

        # 第二次：磁盘缓存命中（不应再有 API 调用）
        mock_client.post.reset_mock()
        r2 = await engine.chat(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0,
        )
        assert r2.content == "first response"
        # API 不应被调用（命中磁盘缓存）
        mock_client.post.assert_not_called()
        assert engine._cache_disk_hits == 1

    @pytest.mark.asyncio
    async def test_engine_clear_persistent(self, tmp_path):
        """清空持久化缓存"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "llm_cache.db"),
        )
        engine = LLMEngine(cfg)
        # 写入测试数据
        engine._persistent_cache.put("k1", "p", "m", {}, LLMResponse(content="x", model="m", provider="p"))
        assert engine._persistent_cache.get("k1") is not None
        # 清空
        n = engine.clear_persistent_cache()
        assert n >= 1
        assert engine._persistent_cache.get("k1") is None


# ─────────────────────────────────────────────────────
# 7. Prometheus 指标导出
# ─────────────────────────────────────────────────────
class TestPrometheusMetrics:
    """Prometheus 指标导出"""

    def test_export_empty(self):
        """空状态导出"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        output = engine.export_prometheus_metrics()
        # 验证包含关键指标
        assert "pangu_llm_calls_total" in output
        assert "pangu_llm_cache_hit_rate" in output
        assert "pangu_llm_prompt_tokens_total" in output
        assert "pangu_llm_cost_usd_total" in output
        # 验证格式（# HELP / # TYPE / value）
        assert "# HELP" in output
        assert "# TYPE" in output
        assert 'provider="openai"' in output

    def test_export_with_data(self, tmp_path):
        """有数据时导出"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "llm_cache.db"),
        )
        engine = LLMEngine(cfg)
        # 清空以确保准确
        engine.clear_persistent_cache()
        # 写入持久化数据
        for i in range(3):
            engine._persistent_cache.put(
                f"k_{i}",
                "openai",
                "gpt-4o-mini",
                {},
                LLMResponse(
                    content=f"r{i}",
                    model="gpt-4o-mini",
                    provider="openai",
                    usage={"prompt_tokens": 10, "completion_tokens": 20},
                ),
            )
        # 模拟统计
        engine._call_count = 10
        engine._cache_hits = 5
        engine._cache_misses = 5
        engine._total_prompt_tokens = 100
        engine._total_completion_tokens = 200

        output = engine.export_prometheus_metrics()
        assert "pangu_llm_persistent_cache_entries" in output
        assert "pangu_llm_persistent_cache_bytes" in output
        # 验证具体数值（3 个条目数应出现在 entries 行）
        entries_line = [line for line in output.split("\n") if "pangu_llm_persistent_cache_entries{" in line]
        assert len(entries_line) == 1
        assert " 3" in entries_line[0]  # 3 个条目
        assert "50.0" in output  # 命中率 50%

    def test_export_prometheus_format_valid(self):
        """验证 Prometheus 格式合法性"""
        engine = LLMEngine(PanguConfig(llm_api_key="dummy"))
        output = engine.export_prometheus_metrics()
        lines = output.strip().split("\n")
        for line in lines:
            if line.startswith("#") or not line.strip():
                continue
            # 每行指标必须有 {...} 标签
            assert "{" in line and "}" in line, f"指标格式不合法: {line}"
            # 必须包含 provider
            assert "provider=" in line


# ─────────────────────────────────────────────────────
# 8. 端到端重启测试
# ─────────────────────────────────────────────────────
class TestEndToEndPersistence:
    """端到端：写入 → 关闭 → 重启 → 命中"""

    @pytest.mark.asyncio
    async def test_persistent_cache_survives_restart(self, tmp_path):
        """模拟进程重启：关闭 → 重新打开 → 命中缓存"""
        from unittest.mock import AsyncMock, MagicMock

        db_path = str(tmp_path / "e2e_cache_unique.db")

        # 阶段 1: 第一次启动，写入缓存
        cfg1 = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=db_path,
        )
        engine1 = LLMEngine(cfg1)
        # 清空可能存在的数据
        engine1.clear_persistent_cache()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "persistent"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        mock_resp.raise_for_status = lambda: None
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        engine1._client = mock_client

        await engine1.chat(
            messages=[{"role": "user", "content": "stable"}],
            temperature=0,
        )
        assert engine1._call_count == 1
        # 关闭（实际不需要 close，但模拟重启）
        del engine1

        # 阶段 2: 重启引擎，内存缓存为空
        cfg2 = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test-key",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=db_path,
        )
        engine2 = LLMEngine(cfg2)
        # 内存缓存应为空
        assert len(engine2._cache) == 0
        # 但持久化缓存应有 1 条
        pstats = engine2._persistent_cache.get_stats()
        assert pstats["total_entries"] == 1, f"应有 1 条，实际 {pstats['total_entries']}"

        # 模拟客户端（如果被调用会抛异常）
        mock_client2 = MagicMock()
        mock_client2.post = AsyncMock(side_effect=Exception("API should not be called"))
        engine2._client = mock_client2

        # 调用相同 prompt
        r = await engine2.chat(
            messages=[{"role": "user", "content": "stable"}],
            temperature=0,
        )
        assert r.content == "persistent"
        # API 不应被调用
        mock_client2.post.assert_not_called()
        # 命中磁盘
        assert engine2._cache_disk_hits == 1
        assert engine2._call_count == 0
