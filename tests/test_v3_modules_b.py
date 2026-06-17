"""Pangu v3.0 模块测试 — 第二批 7 个记忆子系统"""
import pytest
from pangu.core.palace import Drawer


def _d(id="t1", content="test content", wing="test_wing", importance=3.0, tags=None):
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or ["test"])


def _drawers(n=5):
    return [
        _d(id=f"t{i}", content=f"memory item {i} 关于开发",
           wing="dev", importance=2.0 + i, tags=["code", f"tag{i}"])
        for i in range(n)
    ]


# ── 1. KnowledgeSynthesizer ──

class TestKnowledgeSynthesizer:
    def setup_method(self):
        from pangu.memory.knowledge_synthesis import KnowledgeSynthesizer
        self.synth = KnowledgeSynthesizer()

    def test_synthesize_by_topic_empty(self):
        result = self.synth.synthesize_by_topic([])
        assert result == []

    def test_synthesize_by_topic(self):
        drawers = _drawers(3)
        insights = self.synth.synthesize_by_topic(drawers)
        assert isinstance(insights, list)
        assert all(hasattr(i, "topic") for i in insights)

    def test_detect_contradictions_empty(self):
        assert self.synth.detect_contradictions([]) == []

    def test_detect_contradictions_with_conflict(self):
        pos = _d("p1", "测试通过成功", importance=4.0, tags=["status"])
        neg = _d("n1", "测试失败出错了", importance=4.0, tags=["status"])
        result = self.synth.detect_contradictions([pos, neg])
        assert isinstance(result, list)

    def test_extract_core_insights(self):
        drawers = _drawers(3)
        insights = self.synth.extract_core_insights(drawers, top_k=2)
        assert len(insights) <= 2
        assert all("id" in i for i in insights)

    def test_extract_core_insights_empty(self):
        assert self.synth.extract_core_insights([]) == []

    def test_get_synthesis_stats(self):
        stats = self.synth.get_synthesis_stats()
        assert "synthesis_count" in stats


# ── 2. PredictiveAnalytics ──

class TestPredictiveAnalytics:
    def setup_method(self):
        from pangu.memory.predictive_analytics import PredictiveAnalytics
        self.analytics = PredictiveAnalytics()

    def test_analyze_growth_trend_empty(self):
        result = self.analytics.analyze_growth_trend([])
        assert result["trend"] == "no_data"

    def test_analyze_growth_trend(self):
        result = self.analytics.analyze_growth_trend(_drawers(5))
        assert "total_memories" in result
        assert result["total_memories"] == 5

    def test_predict_hot_topics_empty(self):
        assert self.analytics.predict_hot_topics([]) == []

    def test_predict_hot_topics(self):
        result = self.analytics.predict_hot_topics(_drawers(5))
        assert isinstance(result, list)

    def test_get_prediction_stats(self):
        stats = self.analytics.get_prediction_stats()
        assert "predictions_count" in stats


# ── 3. AdaptiveArchitecture ──

class TestAdaptiveArchitecture:
    def setup_method(self):
        from pangu.memory.adaptive_architecture import AdaptiveArchitecture
        self.arch = AdaptiveArchitecture()

    def test_analyze_architecture_empty(self):
        result = self.arch.analyze_architecture([])
        assert result["total_memories"] == 0

    def test_analyze_architecture(self):
        result = self.arch.analyze_architecture(_drawers(5))
        assert "total_wings" in result
        assert "wings" in result

    def test_suggest_restructuring(self):
        result = self.arch.suggest_restructuring(_drawers(5))
        assert isinstance(result, list)

    def test_get_architecture_stats(self):
        stats = self.arch.get_architecture_stats()
        assert "restructurings" in stats


# ── 4. QAEngine ──

class TestQAEngine:
    def setup_method(self):
        from pangu.memory.qa_engine import QAEngine
        self.qa = QAEngine()

    def test_answer_no_match(self):
        result = self.qa.answer("something unrelated", [])
        assert result.confidence == 0.1
        assert result.answer

    def test_answer_with_drawers(self):
        drawers = _drawers(5)
        result = self.qa.answer("如何实现代码", drawers)
        assert result.confidence > 0
        assert isinstance(result.reasoning_steps, list)

    def test_batch_answer(self):
        results = self.qa.batch_answer(["问题一", "问题二"], _drawers(3))
        assert len(results) == 2

    def test_batch_answer_empty(self):
        results = self.qa.batch_answer([], [])
        assert results == []

    def test_get_qa_stats(self):
        stats = self.qa.get_qa_stats()
        assert "total_questions" in stats


# ── 5. ContextInjectionEngine ──

class TestContextInjectionEngine:
    def setup_method(self):
        from pangu.memory.context_injection import ContextInjectionEngine
        self.engine = ContextInjectionEngine()

    def test_inject_context_empty(self):
        result = self.engine.inject_context("hello", [])
        assert result.context_count == 0
        assert result.injected_text == "hello"

    def test_inject_context(self):
        drawers = _drawers(5)
        result = self.engine.inject_context("如何写代码", drawers, token_budget=500)
        assert result.token_budget == 500
        assert isinstance(result.injection_positions, list)

    def test_inject_context_token_budget(self):
        drawers = _drawers(10)
        result = self.engine.inject_context("测试", drawers, token_budget=10)
        assert result.tokens_used <= result.token_budget

    def test_get_injection_stats(self):
        stats = self.engine.get_injection_stats()
        assert "total_injections" in stats


# ── 6. AdaptiveForgetting ──

class TestAdaptiveForgetting:
    def setup_method(self):
        from pangu.memory.adaptive_forgetting import AdaptiveForgetting
        self.forgetting = AdaptiveForgetting()

    def test_evaluate_all_empty(self):
        report = self.forgetting.evaluate_all([])
        assert report.total_evaluated == 0
        assert report.forget_count == 0

    def test_evaluate_all(self):
        drawers = _drawers(5)
        report = self.forgetting.evaluate_all(drawers)
        assert report.total_evaluated == 5
        assert isinstance(report.decisions, list)

    def test_auto_forget(self):
        result = self.forgetting.auto_forget(_drawers(5))
        assert "evaluated" in result
        assert "forgotten" in result

    def test_auto_forget_empty(self):
        result = self.forgetting.auto_forget([])
        assert result["evaluated"] == 0

    def test_get_forgetting_stats(self):
        stats = self.forgetting.get_forgetting_stats()
        assert "total_cycles" in stats


# ── 7. ConsolidationIntelligence ──

class TestConsolidationIntelligence:
    def setup_method(self):
        from pangu.memory.consolidation_intelligence import ConsolidationIntelligence
        self.consolidator = ConsolidationIntelligence()

    def test_find_merge_candidates_empty(self):
        result = self.consolidator.find_merge_candidates([])
        assert result == []

    def test_find_merge_candidates(self):
        d1 = _d("m1", "content a", tags=["shared"])
        d2 = _d("m2", "content b", tags=["shared"])
        d3 = _d("m3", "content c", tags=["shared"])
        result = self.consolidator.find_merge_candidates([d1, d2, d3])
        assert isinstance(result, list)

    def test_run_consolidation(self):
        drawers = _drawers(5)
        report = self.consolidator.run_consolidation(drawers)
        assert report.total_actions >= 0
        assert report.avg_info_preserved > 0

    def test_run_consolidation_empty(self):
        report = self.consolidator.run_consolidation([])
        assert report.total_actions == 0

    def test_get_consolidation_stats(self):
        stats = self.consolidator.get_consolidation_stats()
        assert "total_runs" in stats
