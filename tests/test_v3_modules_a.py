"""盘古 V3.0 模块测试 — 7 个记忆引擎"""
import pytest
from pangu.core.palace import Drawer
from pangu.memory.self_evolution import SelfEvolutionEngine
from pangu.memory.temporal_reasoning import TemporalReasoning
from pangu.memory.semantic_compression import SemanticCompressor
from pangu.memory.collaborative_intelligence import CollaborativeIntelligence
from pangu.memory.causal_reasoning import CausalReasoningEngine
from pangu.memory.explainable_search import ExplainableSearchEngine
from pangu.memory.anomaly_detection import AnomalyDetector


def _drawer(id: str = "t1", content: str = "test content", wing: str = "test",
            importance: float = 3.0, tags: list = None) -> Drawer:
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or [])


# ── SelfEvolutionEngine ──

class TestSelfEvolutionEngine:
    def setup_method(self):
        self.engine = SelfEvolutionEngine()

    def test_diagnose_empty(self):
        results = self.engine.diagnose([])
        assert len(results) == 1
        assert results[0].severity == "critical"
        assert "没有记忆" in results[0].description

    def test_diagnose_low_count(self):
        drawers = [_drawer(id=f"d{i}") for i in range(5)]
        results = self.engine.diagnose(drawers)
        assert any(r.category == "memory" and r.severity == "warning" for r in results)

    def test_diagnose_healthy(self):
        drawers = [_drawer(id=f"d{i}", importance=3.0, tags=["a", "b", "c"]) for i in range(30)]
        results = self.engine.diagnose(drawers)
        critical = [r for r in results if r.severity == "critical"]
        assert len(critical) == 0

    def test_diagnose_with_search_stats(self):
        results = self.engine.diagnose([], search_stats={"avg_score": 0.1, "hit_rate": 0.1})
        assert any(r.category == "search" for r in results)

    def test_generate_evolution_plan_empty(self):
        plan = self.engine.generate_evolution_plan([])
        assert plan.priority == 3
        assert "常规优化" in plan.expected_improvement

    def test_generate_evolution_plan_critical(self):
        from pangu.memory.self_evolution import DiagnosisResult
        diag = [DiagnosisResult(category="mem", severity="critical",
                                description="bad", recommendation="fix it")]
        plan = self.engine.generate_evolution_plan(diag)
        assert plan.priority == 1
        assert len(plan.actions) == 1

    def test_get_evolution_stats_empty(self):
        stats = self.engine.get_evolution_stats()
        assert stats["diagnosis_count"] == 0
        assert stats["plans_count"] == 0

    def test_get_evolution_stats_after_diagnose(self):
        self.engine.diagnose([_drawer()])
        stats = self.engine.get_evolution_stats()
        assert stats["diagnosis_count"] == 1


# ── TemporalReasoning ──

class TestTemporalReasoning:
    def setup_method(self):
        self.engine = TemporalReasoning()

    def test_build_timeline_empty(self):
        assert self.engine.build_timeline([]) == []

    def test_build_timeline_with_dates(self):
        drawers = [
            _drawer(id="d1", content="2024-01-15 讨论项目进度"),
            _drawer(id="d2", content="2024-03-20 完成部署"),
        ]
        events = self.engine.build_timeline(drawers)
        assert len(events) == 2
        assert events[0].memory_id == "d1"

    def test_build_timeline_relative(self):
        drawers = [_drawer(id="d1", content="昨天开了一天会")]
        events = self.engine.build_timeline(drawers)
        assert len(events) == 1

    def test_find_temporal_relations_empty(self):
        assert self.engine.find_temporal_relations([]) == []

    def test_find_temporal_relations_with_cause(self):
        drawers = [
            _drawer(id="d1", content="因为代码有bug导致系统崩溃"),
            _drawer(id="d2", content="所以系统重启了"),
        ]
        relations = self.engine.find_temporal_relations(drawers)
        assert any(r.relation == "caused_by" for r in relations)

    def test_get_temporal_stats_empty(self):
        stats = self.engine.get_temporal_stats([])
        assert stats["total_memories"] == 0
        assert stats["with_time"] == 0

    def test_get_temporal_stats_with_dates(self):
        drawers = [_drawer(id="d1", content="2024-06-01 重要会议")]
        stats = self.engine.get_temporal_stats(drawers)
        assert stats["with_time"] == 1


# ── SemanticCompressor ──

class TestSemanticCompressor:
    def setup_method(self):
        self.compressor = SemanticCompressor()

    def test_compress_by_tags_empty(self):
        result = self.compressor.compress_by_tags([])
        assert result.original_count == 0
        assert result.compressed_count == 0

    def test_compress_by_tags_groups(self):
        drawers = [_drawer(id=f"d{i}", tags=["alpha"], content=f"alpha item {i}") for i in range(4)]
        result = self.compressor.compress_by_tags(drawers)
        assert len(result.merged_groups) == 1
        assert result.merged_groups[0]["original_count"] == 4

    def test_compress_by_tags_no_group(self):
        drawers = [_drawer(id=f"d{i}", tags=[f"tag{i}"], content=f"content {i}") for i in range(3)]
        result = self.compressor.compress_by_tags(drawers)
        assert len(result.merged_groups) == 0

    def test_find_semantic_duplicates_empty(self):
        assert self.compressor.find_semantic_duplicates([]) == []

    def test_find_semantic_duplicates_exact_prefix(self):
        drawers = [
            _drawer(id="d1", content="这是一段很长的测试内容用来验证去重"),
            _drawer(id="d2", content="这是一段很长的测试内容用来验证去重"),
        ]
        dups = self.compressor.find_semantic_duplicates(drawers)
        assert len(dups) == 1

    def test_find_semantic_duplicates_no_match(self):
        drawers = [
            _drawer(id="d1", content="alpha beta"),
            _drawer(id="d2", content="gamma delta"),
        ]
        dups = self.compressor.find_semantic_duplicates(drawers)
        assert len(dups) == 0

    def test_get_compression_stats_empty(self):
        stats = self.compressor.get_compression_stats([])
        assert stats["total_memories"] == 0


# ── CollaborativeIntelligence ──

class TestCollaborativeIntelligence:
    def setup_method(self):
        self.ci = CollaborativeIntelligence()

    def test_register_agent(self):
        result = self.ci.register_agent("a1", "Alice", ["math", "physics"])
        assert result["status"] == "registered"
        assert self.ci._agents["a1"].name == "Alice"

    def test_share_knowledge(self):
        self.ci.register_agent("a1", "A")
        self.ci.register_agent("a2", "B")
        result = self.ci.share_knowledge("a1", "a2", ["k1", "k2"])
        assert result["shared"] == 2

    def test_share_knowledge_unknown_agent(self):
        self.ci.register_agent("a1", "A")
        result = self.ci.share_knowledge("a1", "unknown", ["k1"])
        assert "error" in result

    def test_collaborative_reasoning(self):
        self.ci.register_agent("a1", "A", ["coding"])
        self.ci.register_agent("a2", "B", ["testing"])
        result = self.ci.collaborative_reasoning("task: review code")
        assert len(result.participants) == 2
        assert result.confidence > 0.5

    def test_collaborative_reasoning_empty(self):
        result = self.ci.collaborative_reasoning("task: nothing")
        assert result.confidence == 0.5

    def test_get_agent_stats_empty(self):
        stats = self.ci.get_agent_stats()
        assert stats["total_agents"] == 0

    def test_get_agent_stats_after_register(self):
        self.ci.register_agent("a1", "A")
        stats = self.ci.get_agent_stats()
        assert stats["total_agents"] == 1


# ── CausalReasoningEngine ──

class TestCausalReasoningEngine:
    def setup_method(self):
        self.engine = CausalReasoningEngine()

    def test_discover_causal_links_empty(self):
        assert self.engine.discover_causal_links([]) == []

    def test_discover_causal_links_with_cause_effect(self):
        drawers = [
            _drawer(id="d1", content="因为服务器过载导致请求超时", tags=["server", "perf"]),
            _drawer(id="d2", content="所以系统响应变慢了", tags=["server", "perf"]),
        ]
        links = self.engine.discover_causal_links(drawers)
        assert len(links) >= 1
        assert links[0].cause_id == "d1"

    def test_discover_causal_links_no_match(self):
        drawers = [
            _drawer(id="d1", content="今天天气不错", tags=["weather"]),
            _drawer(id="d2", content="去公园散步了", tags=["outdoor"]),
        ]
        links = self.engine.discover_causal_links(drawers)
        assert len(links) == 0

    def test_build_causal_chains_empty(self):
        assert self.engine.build_causal_chains([]) == []

    def test_get_causal_stats_empty(self):
        stats = self.engine.get_causal_stats()
        assert stats["total_links"] == 0
        assert stats["total_chains"] == 0


# ── ExplainableSearchEngine ──

class TestExplainableSearchEngine:
    def setup_method(self):
        self.engine = ExplainableSearchEngine()

    def test_explain_results_empty(self):
        assert self.engine.explain_results("query", [], []) == []

    def test_explain_results_with_match(self):
        drawer = _drawer(id="d1", content="python programming tutorial", tags=["python"], importance=4.0)
        results = [{"id": "d1", "score": 0.8}]
        explanations = self.engine.explain_results("python", results, [drawer])
        assert len(explanations) == 1
        assert explanations[0].memory_id == "d1"
        assert len(explanations[0].factors) > 0

    def test_explain_results_no_match_drawer(self):
        results = [{"id": "missing", "score": 0.5}]
        explanations = self.engine.explain_results("x", results, [_drawer(id="other")])
        assert len(explanations) == 0

    def test_suggest_improvement_empty(self):
        suggestions = self.engine.suggest_improvement("query", [])
        assert len(suggestions) >= 2

    def test_suggest_improvement_with_explanations(self):
        from pangu.memory.explainable_search import SearchExplanation
        exp = SearchExplanation(memory_id="d1", content_preview="x", score=0.1,
                                factors={"partial_match": 0.1}, primary_reason="weak",
                                matched_terms=[])
        suggestions = self.engine.suggest_improvement("python test", [exp])
        assert isinstance(suggestions, list)

    def test_get_explanation_stats_empty(self):
        stats = self.engine.get_explanation_stats()
        assert stats["total_explanations"] == 0


# ── AnomalyDetector ──

class TestAnomalyDetector:
    def setup_method(self):
        self.detector = AnomalyDetector()

    def test_full_scan_empty(self):
        result = self.detector.full_scan([])
        assert result["total"] == 0
        assert result["healthy"] is True

    def test_full_scan_healthy(self):
        drawers = [_drawer(id=f"d{i}", tags=["ok"]) for i in range(10)]
        result = self.detector.full_scan(drawers)
        assert isinstance(result["anomalies"], list)

    def test_detect_content_anomalies_empty(self):
        assert self.detector.detect_content_anomalies([]) == []

    def test_detect_content_anomalies_empty_content(self):
        drawer = _drawer(id="d1", content="  ")
        anomalies = self.detector.detect_content_anomalies([drawer])
        assert any(a.anomaly_type == "empty_content" for a in anomalies)

    def test_detect_content_anomalies_oversized(self):
        drawer = _drawer(id="d1", content="x" * 15000)
        anomalies = self.detector.detect_content_anomalies([drawer])
        assert any(a.anomaly_type == "oversized_content" for a in anomalies)

    def test_detect_content_anomalies_duplicates(self):
        drawers = [_drawer(id="d1", content="same"), _drawer(id="d2", content="same")]
        anomalies = self.detector.detect_content_anomalies(drawers)
        assert any(a.anomaly_type == "exact_duplicates" for a in anomalies)

    def test_detect_behavior_anomalies_empty(self):
        assert self.detector.detect_behavior_anomalies() == []

    def test_detect_behavior_anomalies_under_threshold(self):
        log = [{"query": "q"} for _ in range(10)]
        assert self.detector.detect_behavior_anomalies(log) == []

    def test_get_anomaly_stats_empty(self):
        stats = self.detector.get_anomaly_stats()
        assert stats["scans_count"] == 0
