"""Pangu v3.0 模块测试 — 第五批 3 个记忆子系统"""
import pytest
from pangu.core.palace import Drawer


def _d(id="t1", content="test content", wing="test_wing", importance=3.0, tags=None):
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or ["test"])


# ── 1. MemoryDiffEngine ──

class TestMemoryDiffEngine:
    def setup_method(self):
        from pangu.memory.memory_diff import MemoryDiffEngine
        self.engine = MemoryDiffEngine()

    def test_diff_content_empty(self):
        result = self.engine.diff_content("", "")
        assert result.similarity == 1.0
        assert result.added == 0
        assert result.removed == 0
        assert result.unchanged == 1

    def test_diff_content_identical(self):
        result = self.engine.diff_content("hello\nworld", "hello\nworld")
        assert result.similarity == 1.0
        assert result.added == 0
        assert result.removed == 0
        assert result.unchanged == 2

    def test_diff_content_added(self):
        result = self.engine.diff_content("a", "a\nb")
        assert result.added == 1
        assert result.unchanged == 1
        assert result.similarity > 0

    def test_diff_content_removed(self):
        result = self.engine.diff_content("a\nb", "a")
        assert result.removed == 1
        assert result.unchanged == 1

    def test_diff_content_modified(self):
        result = self.engine.diff_content("old", "new")
        assert result.modified == 1
        assert result.unchanged == 0

    def test_diff_content_custom_ids(self):
        result = self.engine.diff_content("x", "y", id_a="mem_a", id_b="mem_b")
        assert result.memory_id_a == "mem_a"
        assert result.memory_id_b == "mem_b"

    def test_diff_content_lines_populated(self):
        result = self.engine.diff_content("a\nb\nc", "a\nx\nc")
        assert len(result.lines) == 3
        assert result.lines[0].type == "unchanged"
        assert result.lines[1].type == "modified"
        assert result.lines[2].type == "unchanged"

    def test_diff_drawers(self):
        d1 = _d("m1", "line one\nline two")
        d2 = _d("m2", "line one\nline three")
        result = self.engine.diff_drawers(d1, d2)
        assert result.memory_id_a == "m1"
        assert result.memory_id_b == "m2"
        assert result.modified == 1

    def test_diff_stats_empty(self):
        stats = self.engine.get_diff_stats()
        assert stats["total_diffs"] == 0

    def test_diff_stats_after_diffs(self):
        self.engine.diff_content("a", "b")
        self.engine.diff_content("x", "x")
        stats = self.engine.get_diff_stats()
        assert stats["total_diffs"] == 2
        assert 0 <= stats["avg_similarity"] <= 1

    def test_batch_diff(self):
        d1 = _d("m1", "alpha beta")
        d2 = _d("m2", "alpha gamma")
        d3 = _d("m3", "alpha beta")
        results = self.engine.batch_diff([d1, d2, d3], reference_id="m1")
        assert len(results) == 2
        assert all("similarity" in r for r in results)

    def test_batch_diff_empty(self):
        results = self.engine.batch_diff([])
        assert results == []

    def test_similarity_matrix(self):
        d1 = _d("m1", "aaa")
        d2 = _d("m2", "aaa")
        matrix = self.engine.similarity_matrix([d1, d2])
        assert matrix["matrix"]["m1"]["m1"] == 1.0
        assert matrix["matrix"]["m1"]["m2"] == 1.0
        assert matrix["size"] == 2

    def test_generate_change_summary(self):
        diff = self.engine.diff_content("a\nb", "a\nc\nd")
        summary = self.engine.generate_change_summary(diff)
        assert "差异:" in summary
        assert "相似度" in summary

    def test_get_diff_engine_singleton(self):
        from pangu.memory.memory_diff import get_diff_engine
        e1 = get_diff_engine()
        e2 = get_diff_engine()
        assert e1 is e2


# ── 2. MetricsCollector & StartupValidator ──

class TestMetricsCollector:
    def setup_method(self):
        from pangu.memory.production import MetricsCollector
        self.mc = MetricsCollector()

    def test_record_request(self):
        self.mc.record_request("/api/test", "GET", 200, 15.0)
        summary = self.mc.get_summary()
        assert summary["counters"]["requests_200"] == 1
        assert summary["counters"]["requests_GET"] == 1

    def test_record_request_multiple(self):
        self.mc.record_request("/a", "GET", 200, 10.0)
        self.mc.record_request("/b", "POST", 500, 50.0)
        summary = self.mc.get_summary()
        assert summary["counters"]["requests_200"] == 1
        assert summary["counters"]["requests_500"] == 1
        assert summary["error_requests"] == 1
        assert summary["error_rate"] > 0

    def test_get_summary_empty(self):
        summary = self.mc.get_summary()
        assert summary["total_requests"] == 0
        assert summary["error_rate"] == 0
        assert summary["avg_response_ms"] == 0
        assert summary["uptime_seconds"] >= 0

    def test_get_summary_includes_counters(self):
        self.mc.record_request("/x", "GET", 200, 5.0)
        summary = self.mc.get_summary()
        assert "counters" in summary
        assert summary["counters"]["requests_GET"] == 1

    def test_get_summary_includes_gauges(self):
        self.mc.set_gauge("cpu_usage", 75.5)
        summary = self.mc.get_summary()
        assert summary["gauges"]["cpu_usage"] == 75.5

    def test_get_prometheus_format_empty(self):
        output = self.mc.get_prometheus_format()
        assert "pangu_uptime_seconds" in output

    def test_get_prometheus_format(self):
        self.mc.record_request("/test", "GET", 200, 10.0)
        output = self.mc.get_prometheus_format()
        assert "pangu_requests_GET 1" in output
        assert "pangu_requests_200 1" in output
        assert "pangu_uptime_seconds" in output

    def test_increment(self):
        self.mc.increment("custom_counter")
        self.mc.increment("custom_counter", 5)
        summary = self.mc.get_summary()
        assert summary["counters"]["custom_counter"] == 6

    def test_set_gauge(self):
        self.mc.set_gauge("memory_mb", 1024)
        summary = self.mc.get_summary()
        assert summary["gauges"]["memory_mb"] == 1024

    def test_user_agent_recorded(self):
        self.mc.record_request("/api", "GET", 200, 10.0, user_agent="test-agent")
        summary = self.mc.get_summary()
        assert summary["counters"]["requests_200"] == 1


class TestStartupValidator:
    def test_validate_empty(self):
        from pangu.memory.production import StartupValidator
        sv = StartupValidator()
        all_ok, results = sv.validate()
        assert all_ok is True
        assert results == []

    def test_validate_passing_check(self):
        from pangu.memory.production import StartupValidator
        sv = StartupValidator()
        sv.check("always_pass", lambda: True, "should pass")
        all_ok, results = sv.validate()
        assert all_ok is True
        assert results[0]["status"] == "ok"

    def test_validate_failing_check(self):
        from pangu.memory.production import StartupValidator
        sv = StartupValidator()
        sv.check("always_fail", lambda: False, "should fail")
        all_ok, results = sv.validate()
        assert all_ok is False
        assert results[0]["status"] == "fail"

    def test_validate_error_in_check(self):
        from pangu.memory.production import StartupValidator
        sv = StartupValidator()
        sv.check("raises", lambda: (_ for _ in ()).throw(ValueError("boom")), "will error")
        all_ok, results = sv.validate()
        assert all_ok is False
        assert results[0]["status"] == "error"

    def test_default_startup_checks(self):
        from pangu.memory.production import default_startup_checks
        sv = default_startup_checks()
        all_ok, results = sv.validate()
        assert len(results) >= 3
        names = [r["check"] for r in results]
        assert "python_version" in names

    def test_check_environment(self):
        from pangu.memory.production import check_environment
        env = check_environment()
        assert "python" in env
        assert "version" in env["python"]
        assert "memory" in env
        assert "disk" in env
        assert "pangu" in env


# ── 3. ContextInjectionEngine ──

class TestContextInjectionEngine:
    def setup_method(self):
        from pangu.memory.context_injection import ContextInjectionEngine
        self.engine = ContextInjectionEngine()

    def test_inject_context_empty_drawers(self):
        result = self.engine.inject_context("hello", [])
        assert result.original_text == "hello"
        assert result.injected_text == "hello"
        assert result.context_count == 0
        assert result.tokens_used == 0

    def test_inject_context_no_match(self):
        d = _d("m1", "unrelated content", tags=["irrelevant"])
        result = self.engine.inject_context("hello world", [d])
        assert result.original_text == "hello world"

    def test_inject_context_with_code_topic(self):
        d = _d("m1", "这段代码的函数实现了API", tags=["code", "api"])
        result = self.engine.inject_context("请帮我写代码", [d])
        assert result.context_count >= 1
        assert "[相关记忆上下文]" in result.injected_text

    def test_inject_context_token_budget(self):
        drawers = [_d(f"m{i}", f"内容{i} " * 50, tags=["code"]) for i in range(10)]
        result = self.engine.inject_context("请帮我写代码", drawers, token_budget=100)
        assert result.tokens_used <= 100
        assert result.context_count >= 0

    def test_inject_context_max_memories(self):
        drawers = [_d(f"m{i}", f"关于代码的函数{i}", tags=["code"]) for i in range(10)]
        result = self.engine.inject_context("请帮我写代码", drawers, max_memories=3)
        assert result.context_count <= 3

    def test_get_current_context_empty(self):
        ctx = self.engine.get_current_context()
        assert ctx == []

    def test_get_current_context_after_inject(self):
        d = _d("m1", "代码函数实现", tags=["code"])
        self.engine.inject_context("请帮我写代码", [d])
        ctx = self.engine.get_current_context()
        assert len(ctx) >= 1
        assert ctx[0]["id"] == "m1"

    def test_get_injection_stats_empty(self):
        stats = self.engine.get_injection_stats()
        assert stats["total_injections"] == 0

    def test_get_injection_stats_after_inject(self):
        self.engine.inject_context("请帮我写代码", [_d("m1", "代码实现", tags=["code"])])
        self.engine.inject_context("配置参数", [_d("m2", "配置设置", tags=["config"])])
        stats = self.engine.get_injection_stats()
        assert stats["total_injections"] == 2
        assert stats["avg_tokens_used"] > 0
        assert stats["avg_context_count"] >= 1

    def test_detect_context_topics_code(self):
        topics = self.engine.detect_context_topics("请帮我写代码函数")
        assert "code" in topics

    def test_detect_context_topics_config(self):
        topics = self.engine.detect_context_topics("修改配置参数")
        assert "config" in topics

    def test_detect_context_topics_general(self):
        topics = self.engine.detect_context_topics("今天天气不错")
        assert topics == ["general"]

    def test_detect_context_topics_multiple(self):
        topics = self.engine.detect_context_topics("写代码修bug测试")
        assert "code" in topics
        assert "debug" in topics
        assert "test" in topics

    def test_score_relevance(self):
        d = _d("m1", "代码函数实现", tags=["code"])
        score = self.engine.score_relevance(d, ["code"])
        assert score > 0

    def test_score_relevance_no_match(self):
        d = _d("m1", "无关内容", tags=["unrelated"])
        score = self.engine.score_relevance(d, ["code"])
        assert score == 0

    def test_score_recency_no_timestamp(self):
        d = _d("m1", "test")
        score = self.engine.score_recency(d)
        assert score == 0.5

    def test_score_recency_recent(self):
        from datetime import datetime, timedelta
        d = _d("m1", "test")
        d.updated_at = (datetime.now() - timedelta(days=1)).isoformat()
        score = self.engine.score_recency(d)
        assert score == 1.0

    def test_update_context(self):
        d1 = _d("m1", "代码函数", tags=["code"])
        d2 = _d("m2", "配置参数", tags=["config"])
        result = self.engine.update_context("继续讨论代码", [d1, d2])
        assert result.original_text or result.injected_text

    def test_multiple_wings_ranking(self):
        d1 = _d("m1", "测试函数验证", wing="test", importance=2.0, tags=["test"])
        d2 = _d("m2", "测试用例检查", wing="qa", importance=4.0, tags=["test"])
        result = self.engine.inject_context("请运行测试", [d1, d2])
        assert result.context_count <= 2
        if result.context_count == 2:
            assert result.injection_positions[0]["score"] >= result.injection_positions[1]["score"]
