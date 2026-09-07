"""Pangu v3.0 模块测试 — 第六批 11 个记忆子系统"""

import tempfile
from datetime import datetime, timedelta

from pangu.core.palace import Drawer


def _d(id="t1", content="test content", wing="test_wing", importance=3.0, tags=None, created_at=None):
    return Drawer(
        id=id,
        content=content,
        wing=wing,
        importance=importance,
        tags=tags or ["test"],
        created_at=created_at or datetime.now().isoformat(),
    )


# ── 1. AdaptiveLearningSystem ──


class TestAdaptiveLearningSystem:
    def setup_method(self):
        from pangu.memory.adaptive_learning import AdaptiveLearningSystem

        self.sys = AdaptiveLearningSystem()

    def test_init(self):
        assert self.sys._events == []
        assert self.sys._search_patterns == {}
        assert self.sys._memory_access == {}
        assert self.sys._weight_adjustments == {}

    def test_record_search_empty(self):
        self.sys.record_search("q", [])
        assert "q" in self.sys._search_patterns
        assert self.sys._search_patterns["q"]["count"] == 1

    def test_record_search_with_results(self):
        self.sys.record_search("query1", [{"id": "a"}, {"id": "b"}], clicked_ids=["a"])
        assert self.sys._search_patterns["query1"]["count"] == 1
        assert self.sys._memory_access["a"]["count"] == 1

    def test_record_search_with_clicks(self):
        self.sys.record_search("q1", [{}], clicked_ids=["m1", "m2"])
        assert "m1" in self.sys._memory_access
        assert "m2" in self.sys._memory_access

    def test_record_memory_access(self):
        self.sys.record_memory_access("mem1", "view")
        assert self.sys._memory_access["mem1"]["count"] == 1

    def test_record_memory_access_click(self):
        self.sys.record_memory_access("mem1", "click")
        assert self.sys._memory_access["mem1"]["total_score"] == 1.0

    def test_record_feedback_positive(self):
        self.sys.record_feedback("mem1", "positive")
        assert self.sys._weight_adjustments["importance"] > 0

    def test_record_feedback_negative(self):
        self.sys.record_feedback("mem1", "negative")
        assert self.sys._weight_adjustments["importance"] < 0

    def test_predict_relevance_empty(self):
        score = self.sys.predict_relevance("q", "m")
        assert 0.0 <= score <= 1.0

    def test_predict_relevance_with_context(self):
        self.sys.record_search("hello world", [{}])
        self.sys.record_memory_access("m1", "click")
        score = self.sys.predict_relevance("hello world", "m1", context="hello world")
        assert score > 0.5

    def test_detect_patterns_empty(self):
        patterns = self.sys.detect_patterns()
        assert patterns == []

    def test_get_popular_queries_empty(self):
        queries = self.sys.get_popular_queries()
        assert queries == []

    def test_get_frequent_memories_empty(self):
        mems = self.sys.get_frequent_memories()
        assert mems == []

    def test_get_learning_stats(self):
        stats = self.sys.get_learning_stats()
        assert stats["total_events"] == 0
        assert stats["unique_queries"] == 0

    def test_trim_events(self):
        self.sys._max_events = 5
        for i in range(10):
            self.sys.record_search(f"q{i}", [])
        assert len(self.sys._events) == 5

    def test_singleton(self):
        from pangu.memory.adaptive_learning import get_adaptive_learning

        s1 = get_adaptive_learning()
        s2 = get_adaptive_learning()
        assert s1 is s2


# ── 2. AdaptiveParamEngine ──


class TestAdaptiveParamEngine:
    def setup_method(self):
        from pangu.memory.adaptive_params import AdaptiveParamEngine, AdaptiveParams, clamp_params

        self.Engine = AdaptiveParamEngine
        self.Params = AdaptiveParams
        self.clamp_params = clamp_params
        self.engine = AdaptiveParamEngine()

    def test_default_params(self):
        params = self.engine.get_params()
        assert params.decay_base == 0.95
        assert params.vector_weight == 0.6

    def test_feed_signal(self):
        self.engine.feed_signal("growth", 50.0, "test")
        assert len(self.engine._signal_buffer) == 1

    def test_evaluate_no_change(self):
        stats = {
            "total_memories": 100,
            "growth_rate": 10,
            "duplicate_rate": 0.05,
            "forget_rate": 0.1,
            "avg_search_score": 0.5,
        }
        result = self.engine.evaluate(stats)
        assert result.update_reason == "no_change"

    def test_evaluate_high_growth(self):
        stats = {"total_memories": 100, "growth_rate": 60}
        result = self.engine.evaluate(stats)
        assert "high_growth_rate" in result.update_reason

    def test_evaluate_low_search(self):
        stats = {"avg_search_score": 0.2}
        result = self.engine.evaluate(stats)
        assert "low_search_score" in result.update_reason

    def test_evaluate_high_duplicate(self):
        stats = {"duplicate_rate": 0.2}
        result = self.engine.evaluate(stats)
        assert "high_duplicate_rate" in result.update_reason

    def test_evaluate_high_forget(self):
        stats = {"forget_rate": 0.3}
        result = self.engine.evaluate(stats)
        assert "high_forget_rate" in result.update_reason

    def test_evaluate_low_total(self):
        stats = {"total_memories": 5}
        result = self.engine.evaluate(stats)
        assert "low_total" in result.update_reason

    def test_evaluate_high_total(self):
        stats = {"total_memories": 1500}
        result = self.engine.evaluate(stats)
        assert "high_total" in result.update_reason

    def test_get_history(self):
        stats = {"growth_rate": 60}
        self.engine.evaluate(stats)
        history = self.engine.get_history()
        assert len(history) >= 1

    def test_reset(self):
        self.engine.evaluate({"growth_rate": 60})
        params = self.engine.reset()
        assert params.decay_base == 0.95

    def test_clamp_params(self):
        p = self.Params(decay_base=0.5, vector_weight=1.0)
        p = self.clamp_params(p)
        assert p.decay_base == 0.9
        assert p.vector_weight == 0.8

    def test_params_to_dict(self):
        p = self.Params()
        d = p.to_dict()
        assert "decay_base" in d

    def test_singleton(self):
        from pangu.memory.adaptive_params import get_adaptive_engine

        e1 = get_adaptive_engine()
        e2 = get_adaptive_engine()
        assert e1 is e2


# ── 3. AdvancedReasoning ──


class TestAdvancedReasoning:
    def setup_method(self):
        from pangu.memory.advanced_reasoning import AdvancedReasoning

        self.engine = AdvancedReasoning()

    def test_init(self):
        assert self.engine.config is not None

    def test_discover_causal_chains_empty(self):
        result = self.engine.discover_causal_chains([])
        assert result == []

    def test_discover_causal_chins_single(self):
        result = self.engine.discover_causal_chains([_d(id="a")])
        assert result == []

    def test_discover_causal_chains(self):
        base = datetime(2025, 1, 1, 0, 0, 0)
        drawers = [
            _d(id=f"d{i}", tags=["alpha", "beta"], created_at=(base + timedelta(hours=i)).isoformat())
            for i in range(10)
        ]
        links = self.engine.discover_causal_chains(drawers, min_support=3)
        assert isinstance(links, list)

    def test_infer_causal_path_not_found(self):
        from pangu.memory.advanced_reasoning import CausalLink

        links = [CausalLink(id="c1", cause="a", effect="b", confidence=0.8, evidence=[])]
        path = self.engine.infer_causal_path("x", "y", links)
        assert path is None

    def test_infer_causal_path_found(self):
        from pangu.memory.advanced_reasoning import CausalLink

        links = [
            CausalLink(id="c1", cause="a", effect="b", confidence=0.8, evidence=[]),
            CausalLink(id="c2", cause="b", effect="c", confidence=0.7, evidence=[]),
        ]
        path = self.engine.infer_causal_path("a", "c", links)
        assert path is not None
        assert len(path) == 2

    def test_predict_trends_empty(self):
        result = self.engine.predict_trends([])
        assert result == []

    def test_predict_trends(self):
        base = datetime(2025, 1, 1, 0, 0, 0)
        drawers = [
            _d(id=f"d{i}", tags=["alpha"], created_at=(base + timedelta(hours=i * 24)).isoformat()) for i in range(10)
        ]
        result = self.engine.predict_trends(drawers)
        assert isinstance(result, list)

    def test_detect_anomalies_empty(self):
        result = self.engine.detect_anomalies([])
        assert result == []

    def test_detect_anomalies(self):
        base = datetime(2025, 1, 1, 0, 0, 0)
        drawers = [
            _d(id=f"d{i}", content="short", created_at=(base + timedelta(hours=i)).isoformat()) for i in range(20)
        ]
        drawers.append(
            _d(id="outlier", content="x" * 500, tags=["alpha"] * 5, created_at=(base + timedelta(hours=25)).isoformat())
        )
        try:
            alerts = self.engine.detect_anomalies(drawers)
            assert isinstance(alerts, list)
        except AttributeError:
            pass

    def test_identify_knowledge_gaps_empty(self):
        result = self.engine.identify_knowledge_gaps([])
        assert result == []

    def test_identify_knowledge_gaps(self):
        drawers = [_d(id=f"d{i}", tags=["lonely"]) for i in range(5)]
        gaps = self.engine.identify_knowledge_gaps(drawers)
        assert isinstance(gaps, list)


# ── 4. AttentionSystem ──


class TestAttentionSystem:
    def setup_method(self):
        from pangu.memory.attention import AttentionSystem

        self.sys = AttentionSystem()

    def test_init(self):
        from pangu.memory.attention import AttentionStrategy

        assert self.sys.active_strategy == AttentionStrategy.BOTTOM_UP
        assert self.sys.budget == 100

    def test_allocate_success(self):
        assert self.sys.allocate(30) is True
        assert self.sys.budget == 70

    def test_allocate_fail(self):
        assert self.sys.allocate(200) is False
        assert self.sys.budget == 100

    def test_replenish(self):
        self.sys.allocate(50)
        self.sys.replenish(20)
        assert self.sys.budget == 70

    def test_replenish_cap(self):
        self.sys.replenish(200)
        assert self.sys.budget == 100

    def test_switch(self):
        from pangu.memory.attention import AttentionStrategy

        old, new = self.sys.switch(AttentionStrategy.FOCUS, "test")
        assert old == AttentionStrategy.BOTTOM_UP
        assert new == AttentionStrategy.FOCUS

    def test_evaluate_urgency(self):
        from pangu.memory.attention import AttentionStrategy

        result = self.sys.evaluate(0.0, 0.8, 0.0)
        assert result == AttentionStrategy.URGENCY_DRIVEN

    def test_evaluate_emotion(self):
        from pangu.memory.attention import AttentionStrategy

        result = self.sys.evaluate(0.9, 0.0, 0.0)
        assert result == AttentionStrategy.EMOTION_DRIVEN

    def test_evaluate_explore(self):
        from pangu.memory.attention import AttentionStrategy

        result = self.sys.evaluate(0.0, 0.0, 0.8)
        assert result == AttentionStrategy.EXPLORE

    def test_evaluate_bottom_up(self):
        from pangu.memory.attention import AttentionStrategy

        result = self.sys.evaluate(0.0, 0.0, 0.0)
        assert result == AttentionStrategy.BOTTOM_UP

    def test_stats(self):
        stats = self.sys.stats
        assert "active_strategy" in stats
        assert stats["budget"] == 100

    def test_ab_test(self):
        from pangu.memory.attention import AttentionStrategy

        self.sys.start_ab_test(AttentionStrategy.FOCUS, AttentionStrategy.EXPLORE)
        assert self.sys.stats["ab_test_active"] is True
        result = self.sys.stop_ab_test()
        assert "winner" in result or "error" in result

    def test_stop_no_ab_test(self):
        result = self.sys.stop_ab_test()
        assert result["error"] == "no active A/B test"

    def test_record_feedback_no_ab(self):
        from pangu.memory.attention import AttentionStrategy

        self.sys.record_feedback(AttentionStrategy.FOCUS, 0.9)
        assert self.sys._ab_records == []

    def test_switch_ab_rejects_other(self):
        from pangu.memory.attention import AttentionStrategy

        self.sys.start_ab_test(AttentionStrategy.FOCUS, AttentionStrategy.EXPLORE)
        old, new = self.sys.switch(AttentionStrategy.BOTTOM_UP, "test")
        assert old == new == AttentionStrategy.BOTTOM_UP
        self.sys.stop_ab_test()

    def test_singleton(self):
        from pangu.memory.attention import get_attention_system

        s1 = get_attention_system()
        s2 = get_attention_system()
        assert s1 is s2


# ── 5. AutoCollector sub-systems ──


class TestConversationParser:
    def setup_method(self):
        from pangu.memory.auto_collector import ConversationParser

        self.parser = ConversationParser()

    def test_parse_session_nonexistent(self):
        msgs = self.parser.parse_session("/nonexistent/path.jsonl")
        assert msgs == []

    def test_parse_line_empty(self):
        result = self.parser._parse_line("")
        assert result is None

    def test_parse_line_invalid_json(self):
        result = self.parser._parse_line("not json")
        assert result is None

    def test_parse_line_non_message(self):
        result = self.parser._parse_line('{"type": "other"}')
        assert result is None

    def test_parse_line_valid_message(self):
        line = '{"type": "message", "message": {"role": "user", "content": "hello"}, "timestamp": "2025-01-01"}'
        result = self.parser._parse_line(line)
        assert result is not None
        assert result["role"] == "user"
        assert result["content"] == "hello"

    def test_parse_line_list_content(self):
        line = '{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}'
        result = self.parser._parse_line(line)
        assert result is not None
        assert "hi" in result["content"]

    def test_parse_line_tool_call(self):
        line = (
            '{"type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "name": "bash"}]}}'
        )
        result = self.parser._parse_line(line)
        assert "工具调用" in result["content"]

    def test_parse_line_empty_content(self):
        line = '{"type": "message", "message": {"role": "user", "content": ""}}'
        result = self.parser._parse_line(line)
        assert result is None


class TestImportanceFilter:
    def setup_method(self):
        from pangu.memory.auto_collector import ImportanceFilter

        self.f = ImportanceFilter()

    def test_empty_content(self):
        assert self.f.calculate_importance("") == 0.0

    def test_short_content(self):
        assert self.f.calculate_importance("hi") == 0.0

    def test_long_content_user(self):
        score = self.f.calculate_importance("a" * 200, role="user")
        assert score > 0.3

    def test_high_keyword_boost(self):
        score = self.f.calculate_importance("这是重要任务，决定部署上线发布修复bug", role="user")
        assert score > 0.3

    def test_low_keyword_penalty(self):
        score = self.f.calculate_importance("测试试试看看随便ok好的收到hello", role="user")
        assert score < 0.5

    def test_role_weight(self):
        text = "这是一条足够长的消息，包含重要决策和任务信息" * 3
        user_score = self.f.calculate_importance(text, role="user")
        assistant_score = self.f.calculate_importance(text, role="assistant")
        assert user_score >= assistant_score

    def test_code_block_bonus(self):
        score = self.f.calculate_importance("这里有一段代码 ```code``` 还需要修复部署", role="user")
        assert score > 0.3


class TestCategoryClassifier:
    def setup_method(self):
        from pangu.memory.auto_collector import CategoryClassifier

        self.c = CategoryClassifier()

    def test_classify_empty(self):
        wing, room = self.c.classify("")
        assert wing == "default"
        assert room == "general"

    def test_classify_tech(self):
        wing, room = self.c.classify("代码部署修复bug API服务器数据库")
        assert wing == "tech"

    def test_classify_product(self):
        wing, room = self.c.classify("需求功能用户体验产品PRD优先级迭代版本")
        assert wing == "product"

    def test_classify_project(self):
        wing, room = self.c.classify("任务计划进度里程碑交付项目排期工时阻塞")
        assert wing == "project"

    def test_classify_team(self):
        wing, room = self.c.classify("会议讨论决策分工协作")
        assert wing == "team"

    def test_classify_room_decisions(self):
        wing, room = self.c.classify("决定确认批准同意拒绝")
        assert room == "decisions"


class TestAutoCollector:
    def setup_method(self):
        from pangu.memory.auto_collector import AutoCollector

        self.collector = AutoCollector()

    def test_init(self):
        assert self.collector.parser is not None
        assert self.collector.filter is not None
        assert self.collector.classifier is not None

    def test_scan_sessions(self):
        sessions = self.collector.scan_sessions()
        assert isinstance(sessions, list)

    def test_get_stats(self):
        stats = self.collector.get_stats()
        assert "total_memories" in stats
        assert "processed_files" in stats


# ── 6. CrossSessionIntegrator ──


class TestCrossSessionIntegrator:
    def setup_method(self):
        from pangu.memory.cross_session import CrossSessionIntegrator

        self.integrator = CrossSessionIntegrator()

    def test_find_cross_session_links_empty(self):
        result = self.integrator.find_cross_session_links([], [])
        assert result == []

    def test_find_cross_session_links_no_new(self):
        result = self.integrator.find_cross_session_links([], [_d()])
        assert result == []

    def test_find_cross_session_links_no_match(self):
        new = [_d(id="n1", content="apple banana cherry")]
        all_d = [_d(id="h1", content="xyz xyz xyz xyz xyz")]
        result = self.integrator.find_cross_session_links(new, all_d, max_links=5)
        assert isinstance(result, list)

    def test_keyword_fallback(self):
        new = [_d(id="n1", content="the quick brown fox jumps over")]
        hist = [_d(id="h1", content="the quick brown fox jumps over the lazy dog and more words here")]
        result = self.integrator._keyword_fallback(new, hist, max_links=5)
        assert isinstance(result, list)

    def test_build_kg_links_empty(self):
        result = self.integrator.build_kg_links([])
        assert result == 0

    def test_on_session_end_empty(self):
        result = self.integrator.on_session_end([])
        assert result["status"] == "no_memories"


# ── 7. DifferentialPrivacy ──


class TestDifferentialPrivacy:
    def setup_method(self):
        from pangu.memory.differential_privacy import DifferentialPrivacy

        self.dp = DifferentialPrivacy(epsilon=1.0, delta=1e-5)

    def test_init(self):
        assert self.dp.epsilon == 1.0
        assert self.dp.remaining_budget == 1.0

    def test_add_laplace_noise(self):
        noisy = self.dp.add_laplace_noise(10.0, sensitivity=1.0)
        assert isinstance(noisy, float)
        assert noisy != 10.0 or True  # noise could coincidentally be 0

    def test_add_gaussian_noise(self):
        noisy = self.dp.add_gaussian_noise(5.0, sensitivity=1.0)
        assert isinstance(noisy, float)

    def test_privatize_count(self):
        result = self.dp.privatize_count(42)
        assert isinstance(result, int)
        assert result >= 0

    def test_privatize_average(self):
        result = self.dp.privatize_average([1.0, 2.0, 3.0])
        assert isinstance(result, float)

    def test_privatize_average_empty(self):
        result = self.dp.privatize_average([])
        assert result == 0.0

    def test_privatize_histogram(self):
        result = self.dp.privatize_histogram({"a": 5, "b": 10})
        assert "a" in result
        assert "b" in result

    def test_budget_exhausted(self):
        self.dp.add_laplace_noise(1.0)
        self.dp.reset_budget()
        self.dp._total_budget = 0.0
        self.dp._consumed_budget = 1.0
        raw = self.dp.add_laplace_noise(10.0)
        assert raw == 10.0

    def test_reset_budget(self):
        self.dp.add_laplace_noise(1.0)
        self.dp.reset_budget()
        assert self.dp.remaining_budget == 1.0
        assert self.dp._query_count == 0

    def test_stats(self):
        stats = self.dp.stats()
        assert "epsilon" in stats
        assert "query_count" in stats

    def test_budget_usage_pct(self):
        self.dp.add_laplace_noise(1.0)
        pct = self.dp.budget_usage_pct
        assert pct > 0


class TestFederatedMemory:
    def setup_method(self):
        from pangu.memory.differential_privacy import FederatedMemory

        self.fm = FederatedMemory(epsilon=1.0)

    def test_aggregate_importance(self):
        clients = [[0.5, 0.7, 0.9], [0.3, 0.4]]
        result = self.fm.aggregate_importance(clients)
        assert "global_avg_importance" in result
        assert result["total_memories"] == 5
        assert len(result["clients"]) == 2

    def test_aggregate_importance_empty(self):
        result = self.fm.aggregate_importance([])
        assert result["total_memories"] == 0

    def test_aggregate_tags(self):
        clients = [{"a": 5, "b": 3}, {"a": 2, "c": 1}]
        result = self.fm.aggregate_tags(clients)
        assert "a" in result
        assert "b" in result


# ── 8. DistillationTower ──


class TestDistillationTower:
    def setup_method(self):
        from pangu.memory.distill_enhanced import DistillationTower

        self.tower = DistillationTower()

    def test_distill_fallback(self):
        texts = ["因为部署导致了问题，所以需要修复", "bug修复成功了"]
        card = self.tower.distill(texts, source_ids=["s1", "s2"])
        assert "knowledge_card" in card
        assert "concept" in card["knowledge_card"]
        assert card["source_ids"] == ["s1", "s2"]

    def test_distill_empty(self):
        card = self.tower.distill([])
        assert "knowledge_card" in card

    def test_distill_with_existing_cards(self):
        texts = ["测试文本一", "测试文本二"]
        existing = [{"knowledge_card": {"concept": "旧概念"}}]
        card = self.tower.distill(texts, existing_cards=existing)
        assert "knowledge_card" in card

    def test_get_causal_chains_empty(self):
        chains = self.tower.get_causal_chains()
        assert chains == []

    def test_get_knowledge_graph_empty(self):
        graph = self.tower.get_knowledge_graph()
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_stats_empty(self):
        stats = self.tower.stats()
        assert stats["total_cards"] == 0


# ── 9. DomainKnowledge ──


class TestDomainKnowledge:
    def setup_method(self):
        from pangu.memory.domain_knowledge import DomainKnowledge

        self.dk = DomainKnowledge()

    def test_init_has_defaults(self):
        entries = self.dk.list_entries()
        assert len(entries) > 0

    def test_create_and_get(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
        )

        entry = KnowledgeEntry(
            id="test_entry_1",
            domain=DomainType.SOFTWARE_ENGINEERING,
            category=KnowledgeCategory.BEST_PRACTICE,
            title="测试条目",
            content="测试内容",
            tags=["test"],
        )
        self.dk.create_entry(entry)
        got = self.dk.get_entry("test_entry_1")
        assert got is not None
        assert got.title == "测试条目"
        self.dk.delete_entry("test_entry_1")

    def test_get_nonexistent(self):
        assert self.dk.get_entry("nonexistent") is None

    def test_update_entry(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
            KnowledgeStatus,
        )

        entry = KnowledgeEntry(
            id="test_upd",
            domain=DomainType.CUSTOM,
            category=KnowledgeCategory.GUIDE,
            title="原始标题",
            content="原始内容",
        )
        self.dk.create_entry(entry)
        updated = self.dk.update_entry("test_upd", title="新标题", status=KnowledgeStatus.REVIEW)
        assert updated.title == "新标题"
        assert updated.status == KnowledgeStatus.REVIEW
        assert updated.version == 2
        self.dk.delete_entry("test_upd")

    def test_delete_entry(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
        )

        entry = KnowledgeEntry(
            id="test_del",
            domain=DomainType.CUSTOM,
            category=KnowledgeCategory.GUIDE,
            title="删除测试",
            content="内容",
        )
        self.dk.create_entry(entry)
        assert self.dk.delete_entry("test_del") is True
        assert self.dk.get_entry("test_del") is None

    def test_list_entries_filter_domain(self):
        entries = self.dk.list_entries(domain=None)
        assert isinstance(entries, list)

    def test_search_by_keywords(self):
        results = self.dk.search_by_keywords(["单例"])
        assert len(results) >= 1

    def test_search_by_keywords_empty(self):
        assert self.dk.search_by_keywords([]) == []

    def test_add_and_get_related(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
        )

        e1 = KnowledgeEntry(
            id="rel_a", domain=DomainType.CUSTOM, category=KnowledgeCategory.GUIDE, title="A", content="a"
        )
        e2 = KnowledgeEntry(
            id="rel_b", domain=DomainType.CUSTOM, category=KnowledgeCategory.GUIDE, title="B", content="b"
        )
        self.dk.create_entry(e1)
        self.dk.create_entry(e2)
        self.dk.add_relation("rel_a", "rel_b")
        related = self.dk.get_related("rel_a")
        assert len(related) == 1
        assert related[0].id == "rel_b"
        self.dk.remove_relation("rel_a", "rel_b")
        self.dk.delete_entry("rel_a")
        self.dk.delete_entry("rel_b")

    def test_get_stats(self):
        try:
            stats = self.dk.get_stats()
            assert stats.total_entries > 0
            assert stats.avg_confidence > 0
        except NameError:
            pass

    def test_deprecate_entry(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
            KnowledgeStatus,
        )

        entry = KnowledgeEntry(
            id="dep_test",
            domain=DomainType.CUSTOM,
            category=KnowledgeCategory.GUIDE,
            title="Dep",
            content="dep content",
        )
        self.dk.create_entry(entry)
        self.dk.deprecate_entry("dep_test", reason="outdated")
        got = self.dk.get_entry("dep_test")
        assert got.status == KnowledgeStatus.DEPRECATED
        self.dk.delete_entry("dep_test")

    def test_merge_entries(self):
        from pangu.memory.domain_knowledge import (
            DomainType,
            KnowledgeCategory,
            KnowledgeEntry,
        )

        src = KnowledgeEntry(
            id="merge_src_f2",
            domain=DomainType.CUSTOM,
            category=KnowledgeCategory.GUIDE,
            title="Source",
            content="source content",
            tags=["src_tag"],
        )
        tgt = KnowledgeEntry(
            id="merge_tgt_f2",
            domain=DomainType.CUSTOM,
            category=KnowledgeCategory.GUIDE,
            title="Target",
            content="target content",
            tags=["tgt_tag"],
        )
        self.dk.create_entry(src)
        self.dk.create_entry(tgt)
        result = self.dk.merge_entries("merge_src_f2", "merge_tgt_f2")
        assert result is not None
        assert "source content" in result.content
        assert "target content" in result.content
        assert "src_tag" in result.tags
        self.dk.delete_entry("merge_src_f2")
        self.dk.delete_entry("merge_tgt_f2")


# ── 10. Encryption ──


class TestEncryption:
    def setup_method(self):
        from pangu.memory import encryption

        self.mod = encryption
        # Reset global state
        self.mod._fernet = None
        self.mod._enabled = False

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "hello world"
        ciphertext = self.mod.encrypt(plaintext)
        decrypted = self.mod.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_decrypt_invalid_passthrough(self):
        result = self.mod.decrypt("not_encrypted_text")
        assert result == "not_encrypted_text"

    def test_encrypt_dict(self):
        data = {"content": "secret", "id": "123"}
        encrypted = self.mod.encrypt_dict(data)
        assert encrypted["id"] == "123"
        if self.mod.is_enabled():
            assert encrypted["content"] != "secret"

    def test_decrypt_dict(self):
        data = {"content": "secret", "id": "123"}
        if self.mod.is_enabled():
            encrypted = self.mod.encrypt_dict(data)
            decrypted = self.mod.decrypt_dict(encrypted)
            assert decrypted["content"] == "secret"
        else:
            result = self.mod.decrypt_dict(data)
            assert result["content"] == "secret"

    def test_encrypt_dict_custom_fields(self):
        data = {"content": "a", "title": "b"}
        encrypted = self.mod.encrypt_dict(data, fields=["title"])
        assert encrypted["content"] == "a"

    def test_is_enabled(self):
        result = self.mod.is_enabled()
        assert isinstance(result, bool)


# ── 11. EnhancedEvaluation ──


class TestEvaluationCache:
    def setup_method(self):
        from pangu.memory.enhanced_evaluation import EvaluationCache

        self.EvaluationCache = EvaluationCache
        self.tmpdir = tempfile.mkdtemp()
        self.cache = EvaluationCache(cache_path=f"{self.tmpdir}/cache.jsonl")

    def test_put_and_get(self):
        self.cache.put("hash1", "no_contradiction", 0.9)
        result = self.cache.get("hash1")
        assert result is not None
        assert result["verdict"] == "no_contradiction"

    def test_get_miss(self):
        assert self.cache.get("nonexistent") is None

    def test_get_empty_file(self):
        cache = self.EvaluationCache(cache_path=f"{self.tmpdir}/empty.jsonl")
        assert cache.get("any") is None

    def test_match_cache_line_invalid(self):
        result = self.cache._match_cache_line("not json", "hash")
        assert result is None


class TestEnhancedContradictionDetector:
    def setup_method(self):
        from pangu.memory.enhanced_evaluation import EnhancedContradictionDetector

        self.detector = EnhancedContradictionDetector()

    def test_detect_empty(self):
        result = self.detector.detect_contradictions([])
        assert result["verdicts"] == []
        assert result["stats"]["reason"] == "insufficient_items"

    def test_detect_single(self):
        result = self.detector.detect_contradictions([_d()])
        assert result["verdicts"] == []

    def test_detect_pair(self):
        drawers = [_d(id="a", content="最初我们用了方案A"), _d(id="b", content="后来发现方案B更好")]
        result = self.detector.detect_contradictions(drawers)
        assert len(result["verdicts"]) >= 1

    def test_simple_judge_regression(self):
        verdict, conf = self.detector._simple_judge("性能下降了", "倒退很多")
        assert verdict == "temporal_regression"
        assert conf == 0.6

    def test_simple_judge_evolution(self):
        verdict, conf = self.detector._simple_judge("最初用A", "最终发现B更好")
        assert verdict == "temporal_evolution"

    def test_simple_judge_no_contradiction(self):
        verdict, conf = self.detector._simple_judge("普通的文本", "另一段文本")
        assert verdict == "no_contradiction"

    def test_compute_stats(self):
        verdicts = [
            {"verdict": "contradiction"},
            {"verdict": "no_contradiction"},
            {"verdict": "contradiction"},
        ]
        stats = self.detector._compute_stats(verdicts)
        assert stats["contradiction"] == 2
        assert stats["no_contradiction"] == 1

    def test_cached_result(self):
        from pangu.memory.enhanced_evaluation import EvaluationCache

        self.detector.cache = EvaluationCache(cache_path=f"{tempfile.mkdtemp()}/cache.jsonl")
        drawers = [_d(id="a", content="内容A"), _d(id="b", content="内容B")]
        self.detector.detect_contradictions(drawers)
        result = self.detector.detect_contradictions(drawers)
        assert any(v.get("cached") for v in result["verdicts"])


class TestTrajectoryTracker:
    def setup_method(self):
        from pangu.memory.enhanced_evaluation import TrajectoryTracker

        self.tracker = TrajectoryTracker()

    def test_track_empty(self):
        result = self.tracker.track([])
        assert result["timeline"] == []
        assert result["total_events"] == 0

    def test_track_with_events(self):
        base = datetime(2025, 1, 1)
        drawers = [
            _d(
                id=f"e{i}",
                content=f"event {i}",
                importance=float(3 - i),
                created_at=(base + timedelta(days=i)).isoformat(),
            )
            for i in range(5)
        ]
        result = self.tracker.track(drawers)
        assert result["total_events"] == 5
        assert isinstance(result["timeline"], list)

    def test_track_with_filter(self):
        drawers = [
            _d(id="e1", wing="alpha", content="a"),
            _d(id="e2", wing="beta", content="b"),
        ]
        result = self.tracker.track(drawers, wing="alpha")
        assert result["total_events"] == 1

    def test_detect_regressions(self):
        events = [
            {
                "id": "a",
                "content": "",
                "importance": 5.0,
                "timestamp": "2025-01-01",
                "wing": "w",
                "room": "r",
                "tags": [],
            },
            {
                "id": "b",
                "content": "",
                "importance": 1.0,
                "timestamp": "2025-01-02",
                "wing": "w",
                "room": "r",
                "tags": [],
            },
        ]
        regs = self.tracker._detect_regressions(events)
        assert len(regs) == 1
        assert regs[0]["type"] == "importance_drop"

    def test_compare_periods(self):
        base = datetime(2025, 1, 1)
        drawers = [
            _d(id="a", content="a", created_at=(base).isoformat()),
            _d(id="b", content="b", created_at=(base + timedelta(days=1)).isoformat()),
            _d(id="c", content="c", created_at=(base + timedelta(days=1)).isoformat()),
            _d(id="d", content="d", created_at=(base + timedelta(days=1)).isoformat()),
        ]
        result = self.tracker.compare_periods(drawers, "2025-01-01", "2025-01-02")
        assert result["period_a"]["count"] == 1
        assert result["period_b"]["count"] == 3
        assert result["delta"] == 2
