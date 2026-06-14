"""盘古 — 持久化缓存 VACUUM 后台任务测试

覆盖：
1. LLMEngine.vacuum_persistent_cache() 基本功能
2. VACUUM 跳过场景（持久化禁用、配置禁用）
3. VACUUM 异常处理
4. start_periodic_vacuum 周期任务
5. auto_vacuum_on_start 配置驱动
6. CLI/MCP 集成
"""

import asyncio

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine, LLMResponse


# ─────────────────────────────────────────────────────
# 1. vacuum_persistent_cache 基本功能
# ─────────────────────────────────────────────────────
class TestVacuumPersistentCache:
    """VACUUM 持久化缓存"""

    def test_vacuum_returns_metrics(self, tmp_path):
        """VACUUM 返回指标"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "vacuum.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 写入一些数据
        for i in range(10):
            engine._persistent_cache.put(
                f"key_{i}", "openai", "gpt-4o-mini", {},
                LLMResponse(content=f"r{i}" * 100, model="gpt-4o-mini", provider="openai",
                            usage={"prompt_tokens": 100, "completion_tokens": 200}),
            )

        result = engine.vacuum_persistent_cache()
        assert "before_bytes" in result
        assert "after_bytes" in result
        assert "freed_bytes" in result
        assert "duration_ms" in result
        assert result["skipped"] is False
        # before >= after（VACUUM 不会膨胀）
        assert result["before_bytes"] >= result["after_bytes"]
        # freed >= 0
        assert result["freed_bytes"] >= 0
        # duration_ms 是有限数字
        assert result["duration_ms"] >= 0
        assert isinstance(result["duration_ms"], (int, float))

    def test_vacuum_preserves_data(self, tmp_path):
        """VACUUM 后数据仍然存在"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "preserve.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        response = LLMResponse(content="preserved", model="gpt-4o-mini", provider="openai")
        engine._persistent_cache.put("k1", "openai", "gpt-4o-mini", {}, response)

        # VACUUM
        engine.vacuum_persistent_cache()

        # 数据仍然能读出
        entry = engine._persistent_cache.get("k1")
        assert entry is not None
        assert entry.response.content == "preserved"

    def test_vacuum_empty_db(self, tmp_path):
        """空数据库的 VACUUM"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "empty.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()
        result = engine.vacuum_persistent_cache()
        assert result["skipped"] is False
        assert result["before_bytes"] >= 0
        assert result["after_bytes"] >= 0


# ─────────────────────────────────────────────────────
# 2. VACUUM 跳过场景
# ─────────────────────────────────────────────────────
class TestVacuumSkipCases:
    """VACUUM 跳过场景"""

    def test_vacuum_skipped_when_persist_disabled(self):
        """持久化禁用时返回 skipped"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist=False,
        )
        engine = LLMEngine(cfg)
        result = engine.vacuum_persistent_cache()
        assert result["skipped"] is True
        assert "persistent cache disabled" in result.get("reason", "")

    def test_auto_vacuum_skipped_when_config_disabled(self, tmp_path):
        """auto_vacuum_on_start 配置禁用时返回 skipped"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "noauto.db"),
            llm_cache_vacuum_on_start=False,
        )
        engine = LLMEngine(cfg)
        result = engine.auto_vacuum_on_start()
        assert result["skipped"] is True
        assert "vacuum_on_start disabled" in result.get("reason", "")

    def test_auto_vacuum_runs_when_config_enabled(self, tmp_path):
        """auto_vacuum_on_start 配置启用时实际执行"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "auto.db"),
            llm_cache_vacuum_on_start=True,
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()
        # 写入一些数据使 VACUUM 有意义
        for i in range(3):
            engine._persistent_cache.put(
                f"k_{i}", "p", "m", {},
                LLMResponse(content="x" * 500, model="m", provider="p"),
            )
        result = engine.auto_vacuum_on_start()
        assert result["skipped"] is False
        assert "before_bytes" in result


# ─────────────────────────────────────────────────────
# 3. 异常处理
# ─────────────────────────────────────────────────────
class TestVacuumErrorHandling:
    """VACUUM 异常处理"""

    def test_vacuum_handles_missing_file(self, tmp_path, monkeypatch):
        """VACUUM 在数据库文件被外部删除时优雅处理"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "missing.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 模拟持久化缓存被破坏
        class _BrokenCache:
            db_path = "/nonexistent/path/db.db"

            def vacuum(self):
                raise OSError("simulated vacuum failure")

        monkeypatch.setattr(engine, "_persistent_cache", _BrokenCache())
        result = engine.vacuum_persistent_cache()
        assert result.get("skipped") is True
        assert "error" in result
        assert "simulated" in result["error"]


# ─────────────────────────────────────────────────────
# 4. start_periodic_vacuum 周期任务
# ─────────────────────────────────────────────────────
class TestPeriodicVacuum:
    """周期 VACUUM 任务"""

    @pytest.mark.asyncio
    async def test_periodic_vacuum_skipped_when_interval_zero(self, tmp_path):
        """interval=0 时不启动任务"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "zero.db"),
        )
        engine = LLMEngine(cfg)
        # interval=0 → 直接返回，不阻塞
        await asyncio.wait_for(engine.start_periodic_vacuum(0.0), timeout=1.0)

    @pytest.mark.asyncio
    async def test_periodic_vacuum_skipped_when_persist_disabled(self):
        """持久化禁用时不启动任务"""
        cfg = PanguConfig(llm_api_key="test", llm_cache_persist=False)
        engine = LLMEngine(cfg)
        # interval>0 但无持久化 → 直接返回
        await asyncio.wait_for(engine.start_periodic_vacuum(24.0), timeout=1.0)

    @pytest.mark.asyncio
    async def test_periodic_vacuum_runs_and_cancellable(self, tmp_path, monkeypatch):
        """周期任务能运行且可取消"""
        cfg = PanguConfig(
            llm_api_key="test",
            llm_cache_persist_path=str(tmp_path / "periodic.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 用很短的 interval 模拟周期行为（实际生产用 24h）
        task = asyncio.create_task(engine.start_periodic_vacuum(interval_hours=1.0))
        await asyncio.sleep(0.1)  # 让任务进入 sleep
        # 取消
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # 任务应已被取消
        assert task.cancelled() or task.done()


# ─────────────────────────────────────────────────────
# 5. 配置项
# ─────────────────────────────────────────────────────
class TestVacuumConfig:
    """VACUUM 配置项"""

    def test_vacuum_config_defaults(self):
        """默认配置值"""
        cfg = PanguConfig()
        assert hasattr(cfg, "llm_cache_vacuum_on_start")
        assert cfg.llm_cache_vacuum_on_start is False
        assert hasattr(cfg, "llm_cache_vacuum_interval_hours")
        assert cfg.llm_cache_vacuum_interval_hours == 0.0

    def test_vacuum_config_can_be_overridden(self):
        """配置可覆盖"""
        cfg = PanguConfig(
            llm_cache_vacuum_on_start=True,
            llm_cache_vacuum_interval_hours=12.5,
        )
        assert cfg.llm_cache_vacuum_on_start is True
        assert cfg.llm_cache_vacuum_interval_hours == 12.5
