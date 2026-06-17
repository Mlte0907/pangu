"""盘古 V3.0 模块测试 C — 7 个记忆引擎"""
import pytest
from pangu.core.palace import Drawer
from pangu.memory.quality_scorer import QualityScorer
from pangu.memory.meta_learning import MetaLearningEngine
from pangu.memory.distillation import DistillationEngine
from pangu.memory.query_rewriter import QueryRewriter
from pangu.memory.graph_builder import GraphBuilder
from pangu.memory.health_monitor import HealthMonitor
from pangu.memory.backup_restore import BackupRestoreEngine


def _drawer(id: str = "t1", content: str = "test content", wing: str = "test",
            importance: float = 3.0, tags: list = None) -> Drawer:
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or [])


# ── QualityScorer ──

class TestQualityScorer:
    def setup_method(self):
        self.scorer = QualityScorer()

    def test_batch_assess_empty(self):
        result = self.scorer.batch_assess([])
        assert result["total_assessed"] == 0
        assert result["avg_score"] == 0.0

    def test_batch_assess_single(self):
        d = _drawer(content="Python is a programming language", tags=["python", "lang"])
        result = self.scorer.batch_assess([d])
        assert result["total_assessed"] == 1
        assert 0.0 <= result["avg_score"] <= 1.0
        assert "A" in result["grade_distribution"]

    def test_batch_assess_multiple(self):
        drawers = [
            _drawer(id="a", content="short", tags=[], importance=1.0),
            _drawer(id="b", content="A longer content with enough text for scoring purposes here", tags=["t1", "t2"], importance=4.0),
        ]
        result = self.scorer.batch_assess(drawers)
        assert result["total_assessed"] == 2
        assert len(result["best_memories"]) <= 2
        assert len(result["worst_memories"]) <= 2

    def test_batch_assess_grades(self):
        d = _drawer(content="x" * 200, tags=["a", "b", "c"], importance=5.0)
        result = self.scorer.batch_assess([d])
        total = sum(result["grade_distribution"].values())
        assert total == 1

    def test_get_quality_stats_empty(self):
        stats = self.scorer.get_quality_stats()
        assert stats["total_assessments"] == 0

    def test_get_quality_stats_after_assess(self):
        self.scorer.batch_assess([_drawer()])
        stats = self.scorer.get_quality_stats()
        assert stats["total_assessments"] == 1
        assert "latest_avg_score" in stats
        assert "latest_grades" in stats


# ── MetaLearningEngine ──

class TestMetaLearningEngine:
    def setup_method(self):
        self.engine = MetaLearningEngine()

    def test_observe(self):
        self.engine.observe("search", "latency", 45.0, context="test")
        stats = self.engine.get_meta_stats()
        assert stats["observations"] == 1

    def test_observe_overflow(self):
        for i in range(600):
            self.engine.observe("m", "v", float(i))
        stats = self.engine.get_meta_stats()
        assert stats["observations"] == 500

    def test_recommend_strategy_default(self):
        result = self.engine.recommend_strategy("search")
        assert "strategy" in result
        assert "params" in result
        assert result["strategy"].startswith("search")

    def test_recommend_strategy_nonexistent(self):
        result = self.engine.recommend_strategy("nonexistent_task")
        assert "strategy" in result

    def test_auto_tune_no_data(self):
        result = self.engine.auto_tune()
        assert result["status"] == "no_data"

    def test_auto_tune_with_data(self):
        for i in range(10):
            self.engine.observe("search", "search_score", 0.2)
        result = self.engine.auto_tune()
        assert result["adjusted"] >= 0

    def test_get_meta_stats_empty(self):
        stats = self.engine.get_meta_stats()
        assert stats["strategies"] > 0
        assert stats["total_uses"] == 0
        assert stats["observations"] == 0

    def test_get_meta_stats_after_use(self):
        self.engine.record_strategy_result("search_balanced", True)
        stats = self.engine.get_meta_stats()
        assert stats["total_uses"] == 1


# ── DistillationEngine ──

class TestDistillationEngine:
    def setup_method(self):
        self.engine = DistillationEngine()

    def test_extract_keywords_empty(self):
        result = self.engine.extract_keywords("")
        assert result == []

    def test_extract_keywords(self):
        result = self.engine.extract_keywords("Python Python Python Java Java Go")
        assert "python" in result
        assert "java" in result

    def test_extract_keywords_chinese(self):
        result = self.engine.extract_keywords("搜索引擎 向量搜索 搜索优化 搜索性能")
        assert len(result) > 0

    def test_distill_all_empty(self):
        report = self.engine.distill_all([])
        assert report.input_count == 0
        assert report.output_count == 0

    def test_distill_all_single_tag_group(self):
        drawers = [
            _drawer(id="a", content="Python is great for AI", tags=["python"]),
            _drawer(id="b", content="Python is used everywhere", tags=["python"]),
        ]
        report = self.engine.distill_all(drawers, min_group_size=2)
        assert report.input_count == 2
        assert report.output_count >= 1

    def test_distill_all_no_groups(self):
        drawers = [_drawer(id=f"d{i}", tags=[f"unique_{i}"]) for i in range(5)]
        report = self.engine.distill_all(drawers, min_group_size=2)
        assert report.output_count == 0

    def test_get_distillation_stats_empty(self):
        stats = self.engine.get_distillation_stats()
        assert stats["total_runs"] == 0

    def test_get_distillation_stats_after_run(self):
        drawers = [
            _drawer(id="a", content="test content A", tags=["t"]),
            _drawer(id="b", content="test content B", tags=["t"]),
        ]
        self.engine.distill_all(drawers)
        stats = self.engine.get_distillation_stats()
        assert stats["total_runs"] == 1
        assert "total_tokens_saved" in stats


# ── QueryRewriter ──

class TestQueryRewriter:
    def setup_method(self):
        self.rewriter = QueryRewriter()

    def test_rewrite_empty(self):
        result = self.rewriter.rewrite("")
        assert result.original == ""
        assert result.strategy == "expand_synonym"

    def test_rewrite_simple(self):
        result = self.rewriter.rewrite("记忆系统搜索优化")
        assert result.original == "记忆系统搜索优化"
        assert len(result.rewritten) > 0
        assert result.confidence > 0

    def test_rewrite_expand_synonym(self):
        result = self.rewriter.rewrite("记忆优化", strategy="expand_synonym")
        assert result.strategy == "expand_synonym"
        assert len(result.expanded_terms) > 0

    def test_rewrite_decompose(self):
        result = self.rewriter.rewrite("搜索引擎 和 向量索引", strategy="decompose")
        assert "OR" in result.rewritten

    def test_suggest_queries_empty(self):
        result = self.rewriter.suggest_queries("test", [])
        assert isinstance(result, list)

    def test_suggest_queries_with_drawers(self):
        drawers = [
            _drawer(tags=["memory", "search"]),
            _drawer(tags=["memory", "vector"]),
        ]
        result = self.rewriter.suggest_queries("mem", drawers)
        assert len(result) > 0

    def test_get_rewrite_stats_empty(self):
        stats = self.rewriter.get_rewrite_stats()
        assert stats["total_rewrites"] == 0

    def test_get_rewrite_stats_after_rewrite(self):
        self.rewriter.rewrite("test query")
        stats = self.rewriter.get_rewrite_stats()
        assert stats["total_rewrites"] == 1
        assert "strategy_distribution" in stats
        assert "intent_distribution" in stats


# ── GraphBuilder ──

class TestGraphBuilder:
    def setup_method(self):
        self.builder = GraphBuilder()

    def test_build_from_drawers_empty(self):
        result = self.builder.build_from_drawers([])
        assert result["entities_added"] == 0
        assert result["relations_added"] == 0

    def test_build_from_drawers_with_entities(self):
        drawers = [
            _drawer(content="Python使用FAISS进行向量检索，提升搜索引擎性能"),
        ]
        result = self.builder.build_from_drawers(drawers)
        assert result["entities_added"] > 0
        assert result["total_entities"] > 0

    def test_build_from_drawers_with_relations(self):
        drawers = [
            _drawer(content="Python使用FAISS进行检索"),
        ]
        result = self.builder.build_from_drawers(drawers)
        assert result["relations_added"] >= 0

    def test_assess_quality_empty(self):
        result = self.builder.assess_quality()
        assert result["quality"] == 0
        assert result["status"] == "empty"

    def test_assess_quality_with_data(self):
        drawers = [
            _drawer(content="Python使用FAISS进行向量检索优化搜索引擎"),
        ]
        self.builder.build_from_drawers(drawers)
        result = self.builder.assess_quality()
        assert result["quality"] > 0
        assert result["total_entities"] > 0

    def test_get_graph_stats_empty(self):
        stats = self.builder.get_graph_stats()
        assert stats["entities"] == 0
        assert stats["relations"] == 0
        assert stats["build_count"] == 0

    def test_get_graph_stats_after_build(self):
        self.builder.build_from_drawers([_drawer(content="Python使用FAISS")])
        stats = self.builder.get_graph_stats()
        assert stats["build_count"] == 1
        assert stats["latest_build"] is not None


# ── HealthMonitor ──

class TestHealthMonitor:
    def setup_method(self):
        self.monitor = HealthMonitor()

    def test_full_check_empty(self):
        result = self.monitor.full_check([])
        assert result["overall_status"] == "critical"
        assert result["critical_count"] > 0
        assert len(result["checks"]) == 6

    def test_full_check_healthy(self):
        drawers = [_drawer(id=f"d{i}", importance=3.0, tags=["a", "b", "c"],
                           wing=f"wing_{i % 3}", content="A" * 50)
                   for i in range(20)]
        result = self.monitor.full_check(drawers)
        assert result["overall_status"] in ("healthy", "warning")
        assert result["overall_score"] > 0.3

    def test_full_check_low_importance(self):
        drawers = [_drawer(id=f"d{i}", importance=0.5) for i in range(10)]
        result = self.monitor.full_check(drawers)
        checks = {c["component"]: c for c in result["checks"]}
        assert checks["importance"]["status"] == "warning"

    def test_full_check_single_wing(self):
        drawers = [_drawer(id=f"d{i}", wing="same", tags=["t1", "t2"]) for i in range(15)]
        result = self.monitor.full_check(drawers)
        checks = {c["component"]: c for c in result["checks"]}
        assert checks["distribution"]["status"] == "warning"

    def test_full_check_duplicates(self):
        drawers = [_drawer(id=f"d{i}", content="same content here for all") for i in range(10)]
        result = self.monitor.full_check(drawers)
        checks = {c["component"]: c for c in result["checks"]}
        assert checks["duplicates"]["status"] == "warning"

    def test_get_health_stats_empty(self):
        stats = self.monitor.get_health_stats()
        assert stats["total_checks"] == 0
        assert stats["total_alerts"] == 0

    def test_get_health_stats_after_check(self):
        self.monitor.full_check([])
        stats = self.monitor.get_health_stats()
        assert stats["total_checks"] == 1
        assert stats["total_alerts"] > 0


# ── BackupRestoreEngine ──

class TestBackupRestoreEngine:
    def setup_method(self):
        self.engine = BackupRestoreEngine()
        self.engine._backup_index.clear()
        self.engine._save_index()

    def test_backup_empty(self):
        info = self.engine.backup([])
        assert info.memory_count == 0
        assert info.size_bytes >= 0
        assert info.checksum

    def test_backup_with_data(self):
        drawers = [_drawer(id=f"d{i}", content=f"content {i}") for i in range(5)]
        info = self.engine.backup(drawers, description="test backup")
        assert info.memory_count == 5
        assert info.description == "test backup"

    def test_list_backups_empty(self):
        result = self.engine.list_backups()
        assert isinstance(result, list)

    def test_list_backups_after_backup(self):
        self.engine.backup([_drawer()])
        result = self.engine.list_backups()
        assert len(result) >= 1
        assert "id" in result[-1]

    def test_verify_backup(self):
        info = self.engine.backup([_drawer(content="verify me")])
        result = self.engine.verify_backup(info.backup_id)
        assert result["valid"] is True
        assert result["memory_count"] == 1

    def test_verify_nonexistent(self):
        result = self.engine.verify_backup("nonexistent_backup_id")
        assert result["valid"] is False

    def test_restore(self):
        info = self.engine.backup([_drawer(id="r1", content="restore test")])
        result = self.engine.restore(info.backup_id)
        assert result["success"] is True
        assert result["restored_count"] == 1

    def test_restore_nonexistent(self):
        result = self.engine.restore("nonexistent")
        assert result["success"] is False

    def test_get_backup_stats_empty(self):
        stats = self.engine.get_backup_stats()
        assert stats["total_backups"] == 0

    def test_get_backup_stats_after_backup(self):
        self.engine.backup([_drawer()])
        stats = self.engine.get_backup_stats()
        assert stats["total_backups"] >= 1
        assert stats["total_memories_backed"] >= 1
        assert stats["total_size_mb"] >= 0
