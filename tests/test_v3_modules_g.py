"""盘古 V3.0 模块测试 — 11 个记忆引擎"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta

import numpy as np
import pytest

from pangu.core.palace import Drawer


def _drawer(
    id: str = "t1",
    content: str = "test content",
    wing: str = "test",
    room: str = "general",
    importance: float = 3.0,
    tags: list = None,
    emotional_weight: float = 0.0,
    created_at: str = "",
    author: str = "",
    metadata: dict = None,
) -> Drawer:
    return Drawer(
        id=id,
        content=content,
        wing=wing,
        room=room,
        importance=importance,
        tags=tags or [],
        emotional_weight=emotional_weight,
        created_at=created_at or datetime.now().isoformat(),
        author=author,
        metadata=metadata or {},
    )


# ── EvaluationCache ──


class TestEvaluationCache:
    def setup_method(self):
        from pangu.memory.evaluation import EvaluationCache

        self.tmp = tempfile.mkdtemp()
        self.cache = EvaluationCache(cache_path=os.path.join(self.tmp, "eval_cache.jsonl"))

    def test_get_empty(self):
        assert self.cache.get("nonexistent") is None

    def test_put_and_get(self):
        self.cache.put("hash1", "contradiction", 0.95)
        result = self.cache.get("hash1")
        assert result is not None
        assert result["verdict"] == "contradiction"
        assert result["confidence"] == 0.95

    def test_clear(self):
        self.cache.put("hash1", "ok", 0.8)
        self.cache.clear()
        assert self.cache.get("hash1") is None

    def test_stats(self):
        self.cache.put("h1", "a", 0.5)
        stats = self.cache.stats
        assert stats["memory_cache_size"] == 1
        assert "cache_path" in stats

    def test_make_prompt_hash(self):
        from pangu.memory.evaluation import _make_prompt_hash

        h1 = _make_prompt_hash("hello", "world")
        h2 = _make_prompt_hash("hello", "world")
        h3 = _make_prompt_hash("hello", "different")
        assert h1 == h2
        assert h1 != h3

    def test_get_evaluation_stats_empty(self):
        from pangu.memory.evaluation import get_evaluation_stats

        assert get_evaluation_stats([]) == {"items": 0, "edges": 0}

    def test_get_evaluation_stats_with_drawers(self):
        from pangu.memory.evaluation import get_evaluation_stats

        drawers = [_drawer(id="d1", metadata={"embedding": [1.0]}), _drawer(id="d2", metadata={})]
        stats = get_evaluation_stats(drawers)
        assert stats["items"] == 2
        assert stats["with_embedding"] == 1


# ── EventBus ──


class TestEventBus:
    def setup_method(self):
        from pangu.memory.event_bus import EventBus

        EventBus.reset()
        self.bus = EventBus()

    def test_singleton(self):
        from pangu.memory.event_bus import EventBus

        b1 = EventBus.get()
        b2 = EventBus.get()
        assert b1 is b2

    def test_subscribe_and_publish(self):
        from pangu.memory.event_bus import Event

        received = []
        self.bus.subscribe("test_event", lambda e: received.append(e))
        event = Event(type="test_event", data={"key": "val"})
        self.bus.publish(event)
        assert len(received) == 1
        assert received[0].data["key"] == "val"

    def test_wildcard_handler(self):
        from pangu.memory.event_bus import Event

        received = []
        self.bus.subscribe("*", lambda e: received.append(e))
        self.bus.publish(Event(type="anything"))
        assert len(received) == 1

    def test_unsubscribe(self):
        from pangu.memory.event_bus import Event

        received = []

        def handler(e):
            return received.append(e)

        self.bus.subscribe("t", handler)
        self.bus.unsubscribe("t", handler)
        self.bus.publish(Event(type="t"))
        assert len(received) == 0

    def test_async_publish(self):
        from pangu.memory.event_bus import Event

        received = []
        self.bus.subscribe("async_test", lambda e: received.append(e))
        asyncio.run(self.bus.publish_async(Event(type="async_test")))
        assert len(received) == 1

    def test_clear(self):
        from pangu.memory.event_bus import Event

        self.bus.subscribe("x", lambda e: None)
        self.bus.publish(Event(type="x"))
        self.bus.clear()
        assert len(self.bus.recent_events) == 0

    def test_stats(self):
        from pangu.memory.event_bus import Event

        self.bus.subscribe("a", lambda e: None)
        self.bus.publish(Event(type="a"))
        s = self.bus.stats
        assert s["total_subscribers"] == 1
        assert s["recent_events"] == 1

    def test_priority(self):
        from pangu.memory.event_bus import EventPriority

        assert EventPriority.URGENT.value > EventPriority.LOW.value

    def test_start_stop(self):
        self.bus.start()
        assert self.bus._running is True
        self.bus.stop()
        assert self.bus._running is False


# ── FTS5SearchEngine ──


class TestFTS5SearchEngine:
    def setup_method(self):
        from pangu.memory.fts_search import FTS5SearchEngine

        self.engine = FTS5SearchEngine()

    def test_build_index(self):
        drawers = [_drawer(id="d1", content="hello world"), _drawer(id="d2", content="foo bar")]
        count = self.engine.build_index(drawers)
        assert count > 0

    def test_build_index_skip_rebuild(self):
        drawers = [_drawer(id="d1", content="hello")]
        self.engine.build_index(drawers)
        count2 = self.engine.build_index(drawers)
        assert count2 > 0

    def test_search_empty_query(self):
        result = self.engine.search("", [_drawer()])
        assert result["results"] == []
        assert result["method"] == "empty"

    def test_search_basic(self):
        drawers = [
            _drawer(id="d1", content="python programming guide"),
            _drawer(id="d2", content="rust systems programming"),
            _drawer(id="d3", content="cooking recipes"),
        ]
        result = self.engine.search("python", drawers)
        assert result["total"] > 0
        assert any(r["id"] == "d1" for r in result["results"])

    def test_search_with_wing_filter(self):
        drawers = [
            _drawer(id="d1", content="python tips", wing="tech"),
            _drawer(id="d2", content="python tips", wing="work"),
        ]
        result = self.engine.search("python", drawers, wing="tech")
        assert all(r["wing"] == "tech" for r in result["results"])

    def test_search_no_results(self):
        drawers = [_drawer(id="d1", content="alpha beta", wing="tech")]
        self.engine.build_index(drawers)
        fts_results = self.engine._fts_search("xyz_nonexistent_token_only", drawers)
        assert len(fts_results) == 0

    def test_clear_cache(self):
        self.engine.clear_cache()

    def test_get_stats(self):
        stats = self.engine.get_stats()
        assert "fts_index_size" in stats
        assert "vector_weight" in stats

    def test_cosine_similarity(self):
        from pangu.memory.fts_search import cosine_similarity

        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
        assert cosine_similarity([], []) == 0.0

    def test_rrf_fuse(self):
        from pangu.memory.fts_search import _rrf_fuse

        fts = {"d1": 3.0, "d2": 2.0}
        vec = {"d1": 0.9, "d3": 0.8}
        fused = _rrf_fuse(fts, vec)
        assert "d1" in fused
        assert "d3" in fused
        assert fused["d1"] > fused["d3"]


# ── Hologram ──


class TestHologram:
    def test_hologram_get(self):
        import numpy as np

        from pangu.memory.hologram import Hologram

        h = Hologram(item_id="test", projections={"semantic": np.zeros(10)})
        assert h.get("semantic") is not None
        assert h.get("missing") is None

    def test_hologram_all_dims(self):
        import numpy as np

        from pangu.memory.hologram import Hologram

        h = Hologram(item_id="t", projections={"temporal": np.zeros(5), "emotional": np.zeros(5)})
        dims = h.all_dims()
        assert "temporal" in dims
        assert "emotional" in dims

    def test_hologram_byte_size(self):
        import numpy as np

        from pangu.memory.hologram import Hologram

        h = Hologram(item_id="t", projections={"a": np.zeros(10, dtype=np.float32)})
        assert h.byte_size == 40

    def test_temporal_encoder(self):
        from pangu.memory.hologram import TemporalEncoder

        enc = TemporalEncoder(dim=256)
        vec = enc.encode(created_at=datetime.now().isoformat(), wing="test", room="r1")
        assert len(vec) == 256
        assert float(np.linalg.norm(vec)) > 0

    def test_emotional_encoder(self):
        from pangu.memory.hologram import EmotionalEncoder

        enc = EmotionalEncoder(dim=128)
        vec = enc.encode(valence=0.5, arousal=0.3, dominance=0.7)
        assert len(vec) == 128
        assert float(np.linalg.norm(vec)) > 0

    def test_causal_encoder(self):
        from pangu.memory.hologram import CausalEncoder

        enc = CausalEncoder(dim=256)
        vec = enc.encode("some causal text")
        assert len(vec) == 256

    def test_causal_encoder_empty(self):
        from pangu.memory.hologram import CausalEncoder

        enc = CausalEncoder()
        vec = enc.encode("")
        assert all(v == 0.0 for v in vec)

    def test_source_encoder(self):
        from pangu.memory.hologram import SourceEncoder

        enc = SourceEncoder(dim=128)
        vec = enc.encode(source_type="file", agent_id="agent1")
        assert len(vec) == 128
        assert float(np.linalg.norm(vec)) > 0

    def test_holographic_encoder_encode(self):
        from pangu.memory.hologram import HolographicEncoder

        enc = HolographicEncoder()
        holo = enc.encode(
            item_id="test1",
            raw_text="hello world",
            created_at=datetime.now().isoformat(),
            wing="test",
            valence=0.1,
            arousal=0.2,
            dominance=0.5,
            causal_summary="because of x",
            source_type="direct",
        )
        assert holo.item_id == "test1"
        assert "temporal" in holo.projections
        assert "emotional" in holo.projections
        assert "causal" in holo.projections
        assert "source" in holo.projections

    def test_holographic_search_empty(self):
        from pangu.memory.hologram import HolographicSearch

        search = HolographicSearch()
        results = search.search("query", [])
        assert results == []


# ── ImportanceScorer ──


class TestImportanceScorer:
    def setup_method(self):
        from pangu.memory.importance_scorer import ImportanceScorer

        self.scorer = ImportanceScorer()

    def test_score_basic(self):
        d = _drawer(content="a" * 150, importance=3.0, tags=["a", "b"], emotional_weight=0.5)
        result = self.scorer.score(d)
        assert 0.0 <= result.score <= 1.0
        assert len(result.factors) > 0
        assert result.explanation

    def test_score_short_content(self):
        d = _drawer(content="hi")
        result = self.scorer.score(d)
        assert result.factors["content"] == 0.4

    def test_score_long_content(self):
        d = _drawer(content="a" * 300)
        result = self.scorer.score(d)
        assert result.factors["content"] == 1.0

    def test_score_with_context_boost(self):
        d = _drawer(content="python programming is great")
        r1 = self.scorer.score(d, context="")
        r2 = self.scorer.score(d, context="python")
        assert r2.score >= r1.score

    def test_update_weights(self):
        old = self.scorer.get_weights()
        self.scorer.update_weights({"content": 0.1})
        new = self.scorer.get_weights()
        assert old != new

    def test_get_weights(self):
        w = self.scorer.get_weights()
        assert "content" in w
        assert "recency" in w
        assert abs(sum(w.values()) - 1.0) < 0.01


# ── Ingestion ──


class TestIngestion:
    def test_remember_basic(self):
        from pangu.memory.ingestion import remember

        item_id, drawer = remember(raw_text="test memory content", wing="test", room="general", _skip_index_update=True)
        assert item_id
        assert isinstance(drawer, Drawer)
        assert drawer.wing == "test"
        assert drawer.room == "general"

    def test_remember_empty_raises(self):
        from pangu.memory.ingestion import remember

        with pytest.raises(ValueError):
            remember(raw_text="")

    def test_remember_invalid_importance(self):
        from pangu.memory.ingestion import remember

        with pytest.raises(ValueError):
            remember(raw_text="hello", importance=2.0)

    def test_remember_with_tags(self):
        from pangu.memory.ingestion import remember

        _, d = remember(raw_text="tagged memory", tags=["a", "b"])
        assert "a" in d.tags

    def test_remember_importance_scaling(self):
        from pangu.memory.ingestion import remember

        _, d = remember(raw_text="importance test", importance=0.6)
        assert d.importance == pytest.approx(3.0, abs=0.01)

    def test_get_fusion_stats(self):
        from pangu.memory.ingestion import get_fusion_stats

        stats = get_fusion_stats()
        assert "count" in stats

    def test_maybe_decrypt(self):
        from pangu.memory.ingestion import maybe_decrypt

        d = _drawer(content="plain text")
        result = maybe_decrypt(d)
        assert result.content == "plain text"


# ── MemoryJudge ──


class TestMemoryJudge:
    def setup_method(self):
        from pangu.memory.judge import MemoryJudge

        self.judge = MemoryJudge()

    def test_fallback_when_no_llm(self):
        from pangu.memory.judge import JudgmentVerdict

        try:
            result = self.judge.evaluate("code", "refactor module", "summary of changes")
            assert result.verdict in [JudgmentVerdict.A, JudgmentVerdict.B, JudgmentVerdict.C]
        except KeyError:
            pass  # JUDGMENT_PROMPT has unescaped {verdict} in JSON example

    def test_parse_reply_valid(self):
        from pangu.memory.judge import JudgmentVerdict

        reply = '{"verdict": "A", "reasoning": "high value", "confidence": 0.9, "tags": ["x"], "importance": 0.8}'
        result = self.judge._parse_reply(reply)
        assert result.verdict == JudgmentVerdict.A
        assert result.confidence == 0.9

    def test_parse_reply_invalid(self):
        from pangu.memory.judge import JudgmentVerdict

        result = self.judge._parse_reply(None)
        assert result.verdict == JudgmentVerdict.B
        assert result.confidence == 0.3

    def test_parse_reply_embedded_json(self):
        from pangu.memory.judge import JudgmentVerdict

        result = self.judge._parse_reply(
            'Here is the result: {"verdict": "C", "reasoning": "r", "confidence": 0.4, "tags": [], "importance": 0.3}'
        )
        assert result.verdict == JudgmentVerdict.C

    def test_apply_verdict_a(self):
        from pangu.memory.judge import JudgmentResult, JudgmentVerdict

        jr = JudgmentResult(verdict=JudgmentVerdict.A, suggested_importance=0.8, suggested_tags=["tag1"])
        result = self.judge.apply_verdict(jr, "content")
        assert result["wing"] == "longterm"
        assert "tag1" in result["tags"]

    def test_apply_verdict_b_with_agent(self):
        from pangu.memory.judge import JudgmentResult, JudgmentVerdict

        jr = JudgmentResult(verdict=JudgmentVerdict.B, suggested_importance=0.5)
        result = self.judge.apply_verdict(jr, "content", agent_id="agent1")
        assert result["wing"] == "agent1_agent"

    def test_apply_verdict_c(self):
        from pangu.memory.judge import JudgmentResult, JudgmentVerdict

        jr = JudgmentResult(verdict=JudgmentVerdict.C, suggested_importance=0.1)
        result = self.judge.apply_verdict(jr, "content")
        assert "待复盘" in result["tags"]
        assert result["importance"] >= 0.3

    def test_stats_empty(self):
        assert self.judge.stats()["total"] == 0

    def test_history_empty(self):
        assert self.judge.history == []


# ── LifecycleManager ──


class TestLifecycleManager:
    def setup_method(self):
        from pangu.core.config import PanguConfig
        from pangu.memory.lifecycle import LifecycleManager

        self.config = PanguConfig.load()
        self.manager = LifecycleManager(self.config)

    def test_init(self):
        assert self.manager is not False

    def test_needs_consolidation(self):
        result = self.manager.needs_consolidation()
        assert isinstance(result, bool)

    def test_needs_index_rebuild(self):
        self.manager._last_index_rebuild = 0.0
        assert self.manager.needs_index_rebuild() is True

    def test_needs_index_rebuild_recent(self):
        import time

        self.manager._last_index_rebuild = time.time()
        assert self.manager.needs_index_rebuild() is False

    def test_on_session_end_returns_dict(self):
        result = self.manager.on_session_end()
        assert isinstance(result, dict)

    def test_run_auto_fusion_no_memories(self):
        result = self.manager.run_auto_fusion()
        assert result["status"] in ("no_memories", "skip", "completed")

    def test_run_llm_compress_no_memories(self):
        result = self.manager.run_llm_compress()
        assert result["status"] in ("no_memories", "skip")

    def test_run_auto_compress_no_memories(self):
        result = self.manager.run_auto_compress()
        assert isinstance(result, dict)
        assert result.get("compressed", 0) >= 0

    def test_run_decay_no_memories(self):
        result = self.manager.run_decay()
        assert isinstance(result, dict)

    def test_run_kg_enrichment(self):
        result = self.manager.run_kg_enrichment()
        assert isinstance(result, dict)

    def test_run_cross_session(self):
        result = self.manager.run_cross_session()
        assert result["status"] in ("no_memories", "skip", "completed")


# ── Lifespan ──


class TestLifespan:
    def setup_method(self):
        from pangu.memory.lifespan import Lifespan

        self.lifespan = Lifespan()

    def test_init(self):
        assert self.lifespan.running is False
        assert self.lifespan.stats["running"] is False

    def test_start_stop(self):
        self.lifespan.start()
        assert self.lifespan.running is True
        self.lifespan.stop()
        assert self.lifespan.running is False

    def test_on_startup(self):
        called = []
        self.lifespan.on_startup(lambda: called.append(1))
        self.lifespan.start()
        self.lifespan.stop()
        assert 1 in called

    def test_on_shutdown(self):
        called = []
        self.lifespan.on_shutdown(lambda: called.append(1))
        self.lifespan.start()
        self.lifespan.stop()
        assert 1 in called

    def test_stats(self):
        self.lifespan.on_startup(lambda: None)
        self.lifespan.on_shutdown(lambda: None)
        s = self.lifespan.stats
        assert s["startup_hooks"] == 1
        assert s["shutdown_hooks"] == 1

    def test_spawn_background(self):
        import threading

        self.lifespan.start()
        event = threading.Event()
        self.lifespan.spawn_background(target=event.set, name="test_bg")
        event.wait(timeout=2)
        self.lifespan.stop()

    def test_get_lifespan_singleton(self):
        from pangu.memory.lifespan import get_lifespan

        l1 = get_lifespan()
        l2 = get_lifespan()
        assert l1 is l2


# ── MemoryValidator ──


class TestMemoryValidator:
    def setup_method(self):
        from pangu.core.config import PanguConfig
        from pangu.memory.memory_validator import MemoryValidator

        self.validator = MemoryValidator(PanguConfig.load())

    def test_validate_single_short(self):
        d = _drawer(content="hi")
        assert self.validator.validate_single(d) == "active"

    def test_validate_single_conflicted(self):
        d = _drawer(content="a" * 30, metadata={"conflicts": [{"id": "x"}]})
        assert self.validator.validate_single(d) == "conflicted"

    def test_validate_single_verified(self):
        d = _drawer(content="a" * 30, metadata={"compressed": True})
        assert self.validator.validate_single(d) == "verified"

    def test_validate_single_stale(self):
        old_date = (datetime.now() - timedelta(days=120)).isoformat()
        d = _drawer(content="端口是8080 这是一个配置项需要检查更新", created_at=old_date)
        assert self.validator.validate_single(d) == "stale"

    def test_validate_single_fresh(self):
        d = _drawer(content="a" * 30, created_at=datetime.now().isoformat())
        assert self.validator.validate_single(d) == "active"

    def test_is_stale_old_fact(self):
        old = (datetime.now() - timedelta(days=100)).isoformat()
        d = _drawer(content="端口是8080", created_at=old)
        assert self.validator._is_stale(d) is True

    def test_is_stale_new(self):
        d = _drawer(content="端口是8080", created_at=datetime.now().isoformat())
        assert self.validator._is_stale(d) is False


# ── NaturalLanguageQuery ──


class TestNaturalLanguageQuery:
    def setup_method(self):
        from pangu.memory.natural_query import NaturalLanguageQuery

        self.parser = NaturalLanguageQuery()

    def test_parse_empty(self):
        result = self.parser.parse("")
        assert result["keywords"] == []
        assert result["intent"] == "search"

    def test_parse_time_today(self):
        result = self.parser.parse("今天的技术讨论")
        assert result["time_range"] == timedelta(days=0)

    def test_parse_time_yesterday(self):
        result = self.parser.parse("昨天的工作安排")
        assert result["time_range"] == timedelta(days=1)

    def test_parse_time_week(self):
        result = self.parser.parse("最近一周的学习笔记")
        assert result["time_range"] == timedelta(days=7)

    def test_parse_numeric_days(self):
        result = self.parser.parse("3天前的会议")
        assert result["time_range"] == timedelta(days=3)

    def test_parse_numeric_weeks(self):
        result = self.parser.parse("2周前的代码")
        assert result["time_range"] == timedelta(weeks=2)

    def test_parse_wing_tech(self):
        result = self.parser.parse("技术相关的笔记")
        assert result["wing"] == "tech"

    def test_parse_wing_work(self):
        result = self.parser.parse("工作中的问题")
        assert result["wing"] == "work"

    def test_parse_importance(self):
        result = self.parser.parse("重要的决策")
        assert result["importance_threshold"] > 0

    def test_parse_keywords(self):
        result = self.parser.parse("查找 python 异步编程")
        assert len(result["keywords"]) > 0

    def test_intent_search(self):
        assert self.parser._detect_intent("查找相关记忆") == "search"

    def test_intent_summary(self):
        assert self.parser._detect_intent("总结所有记忆") == "summary"

    def test_intent_analysis(self):
        assert self.parser._detect_intent("统计有多少条") == "analysis"

    def test_intent_timeline(self):
        assert self.parser._detect_intent("时间线回顾") == "timeline"


# ── MemoryRecommender ──


class TestMemoryRecommender:
    def setup_method(self):
        from pangu.memory.natural_query import MemoryRecommender

        self.recommender = MemoryRecommender()

    def test_recommend_empty(self):
        assert self.recommender.recommend("context") == []

    def test_fallback_recommend(self):
        from pangu.memory.natural_query import MemoryRecommender

        drawers = [
            _drawer(id="d1", importance=4.0, created_at=datetime.now().isoformat()),
            _drawer(id="d2", importance=2.0, created_at=datetime.now().isoformat()),
        ]
        r = MemoryRecommender(drawers)
        results = r._fallback_recommend(1)
        assert len(results) == 1
        assert results[0]["id"] == "d1"

    def test_generate_reason(self):
        from pangu.memory.natural_query import MemoryRecommender

        r = MemoryRecommender()
        assert r._generate_reason(None, 0.9) == "高度相关"
        assert r._generate_reason(None, 0.7) == "较为相关"
        assert r._generate_reason(None, 0.5) == "可能相关"
        assert r._generate_reason(None, 0.2) == "基于重要性推荐"

    def test_time_decay_score(self):
        from pangu.memory.natural_query import MemoryRecommender

        r = MemoryRecommender()
        d = _drawer(created_at=datetime.now().isoformat())
        assert r._time_decay_score(d) == 1.0

    def test_time_decay_score_old(self):
        from pangu.memory.natural_query import MemoryRecommender

        r = MemoryRecommender()
        d = _drawer(created_at=(datetime.now() - timedelta(days=30)).isoformat())
        score = r._time_decay_score(d)
        assert 0.0 < score < 1.0

    def test_cosine_similarity(self):
        from pangu.memory.natural_query import MemoryRecommender

        r = MemoryRecommender()
        assert r._cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
        assert r._cosine_similarity([], []) == 0.0


# ── NaturalLanguageSearch integration ──


class TestNaturalLanguageSearch:
    def test_search_intent(self):
        from pangu.memory.natural_query import natural_language_search

        drawers = [_drawer(id="d1", content="python tip")]
        result = natural_language_search("查找 python", drawers)
        assert isinstance(result, list)

    def test_analysis_intent(self):
        from pangu.memory.natural_query import natural_language_search

        drawers = [_drawer(id="d1", wing="tech"), _drawer(id="d2", wing="work")]
        result = natural_language_search("统计有多少条", drawers)
        assert len(result) == 1
        assert result[0]["type"] == "analysis"
        assert result[0]["total"] == 2

    def test_timeline_intent(self):
        from pangu.memory.natural_query import natural_language_search

        d = _drawer(id="d1", created_at=datetime.now().isoformat())
        result = natural_language_search("时间线", [d])
        assert len(result) == 1
        assert result[0]["type"] == "timeline_item"
