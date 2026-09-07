"""盘古伏羲移植模块测试"""

import os
import tempfile
from pathlib import Path

from pangu.core.config import PanguConfig, config


class TestPanguConfig:
    """测试增强版配置系统"""

    def test_config_defaults(self):
        """测试默认配置值"""
        cfg = PanguConfig()
        assert cfg.llm_provider == "openai"
        assert cfg.backend == "chromadb"
        assert cfg.embedding_dim == 384
        assert cfg.decay_base == 0.95
        assert cfg.wm_capacity == 40
        assert cfg.consolidation_enabled is True

    def test_config_env_override(self, monkeypatch):
        """测试环境变量覆盖"""
        monkeypatch.setenv("PANGU_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("PANGU_DECAY_BASE", "0.8")
        cfg = PanguConfig()
        assert cfg.llm_provider == "anthropic"
        assert cfg.decay_base == 0.8

    def test_config_load_save(self):
        """测试配置加载和保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            cfg = PanguConfig(llm_provider="ollama", embedding_dim=768)
            cfg.save(config_path)

            loaded = PanguConfig.load(config_path)
            assert loaded.llm_provider == "ollama"
            assert loaded.embedding_dim == 768

    def test_config_ensure_dirs(self):
        """测试目录创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = PanguConfig(base_dir=Path(tmpdir))
            cfg.ensure_dirs()
            assert os.path.isdir(cfg.palace_path)
            assert os.path.isdir(cfg.wiki_path)

    def test_config_edge_types(self):
        """测试知识图谱边类型"""
        cfg = PanguConfig()
        assert "causes" in cfg.edge_types
        assert "contradicts" in cfg.edge_types
        assert "wikilink" in cfg.edge_types

    def test_config_confidence_sources(self):
        """测试置信度来源"""
        cfg = PanguConfig()
        assert cfg.confidence_sources["direct"] == 1.0
        assert cfg.confidence_sources["inferred"] == 0.6

    def test_global_config_singleton(self):
        """测试全局配置单例"""
        assert isinstance(config, PanguConfig)
        assert config.llm_provider == "openai"


class TestMigrations:
    """测试数据库迁移系统"""

    def test_available_migrations(self):
        """测试迁移列表"""
        from pangu.store.migrations import get_available_migrations

        migrations = get_available_migrations()
        assert len(migrations) >= 8
        versions = [m["version"] for m in migrations]
        assert "v1" in versions
        assert "v8" in versions

    def test_get_schema_version(self):
        """测试获取 schema 版本"""
        from pangu.store.migrations import get_schema_version

        version = get_schema_version()
        assert version in ("none", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8")

    def test_migration_structure(self):
        """测试迁移结构完整性"""
        from pangu.store.migrations import MIGRATIONS

        for version, label, forward_op, _rollback in MIGRATIONS:
            assert isinstance(version, str)
            assert isinstance(label, str)
            assert isinstance(forward_op, dict)
            assert "action" in forward_op
            assert forward_op["action"] in ("ensure_schema", "add_field", "remove_field")


class TestHealthCheck:
    """测试健康检查系统"""

    def test_quick_health_check(self):
        """测试快速健康检查"""
        from pangu.observability.health import quick_health_check

        result = quick_health_check()
        assert result["status"] == "ok"
        assert "version" in result
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 0

    def test_deep_health_check(self):
        """测试深度健康检查"""
        from pangu.observability.health import deep_health_check

        result = deep_health_check()
        assert result["status"] in ("ok", "degraded")
        assert "checks" in result
        assert "uptime_seconds" in result


class TestMetrics:
    """测试 Prometheus 指标系统"""

    def test_metrics_response(self):
        """测试指标响应"""
        from pangu.observability.metrics import get_metrics_response

        content, media_type = get_metrics_response()
        assert isinstance(content, (str, bytes))
        assert len(content) > 0

    def test_update_memory_count(self):
        """测试更新记忆计数"""
        from pangu.observability.metrics import update_memory_count

        # 不应抛出异常
        update_memory_count(42)

    def test_record_api_request(self):
        """测试记录 API 请求"""
        from pangu.observability.metrics import record_api_request

        # 不应抛出异常
        record_api_request("GET", "/api/v2/memories", 200, 0.05)


class TestAutonomousEngine:
    """测试自主判断引擎"""

    def test_analyze_memory_task(self):
        """测试记忆类任务分析"""
        from pangu.autonomous import analyze_task

        result = analyze_task("帮我检索一下之前的记忆")
        assert result["needs_memory"] is True
        assert len(result["matched_scenarios"]) >= 1

    def test_analyze_reflection_task(self):
        """测试反思类任务分析"""
        from pangu.autonomous import analyze_task

        result = analyze_task("帮我复盘一下最近的工作")
        assert len(result["matched_scenarios"]) >= 1

    def test_analyze_complex_task(self):
        """测试复杂任务分析"""
        from pangu.autonomous import analyze_task

        result = analyze_task("重构整个项目的架构设计")
        assert result["complexity"] > 0
        assert isinstance(result["needs_deep_decision"], bool)

    def test_analyze_simple_task(self):
        """测试简单任务分析"""
        from pangu.autonomous import analyze_task

        result = analyze_task("hello world")
        assert result["complexity"] == 0
        assert result["needs_deep_decision"] is False


class TestConfigReload:
    """测试配置热更新"""

    def test_reload_method_exists(self):
        """测试 reload 方法存在"""
        assert hasattr(PanguConfig, "reload")
        assert callable(PanguConfig.reload)

    def test_model_post_init(self):
        """测试初始化后处理"""
        cfg = PanguConfig()
        assert cfg.palace_path
        assert cfg.wiki_path
        assert cfg.identity_path
        assert cfg.config_path
