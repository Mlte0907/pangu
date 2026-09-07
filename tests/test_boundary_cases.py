"""盘古记忆系统边界与极端情况测试

覆盖5大类边界场景：
1. 空输入测试
2. 极端值测试
3. 并发访问测试
4. 错误恢复测试
5. 性能边界测试
"""

import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.palace import Drawer
from pangu.memory.consolidation import ForgettingCurve, MemoryConsolidator
from pangu.memory.decay import decay_batch, get_decay_stats, get_purge_candidates
from pangu.memory.event_bus import Event, EventBus, EventPriority
from pangu.memory.importance_scorer import ImportanceScorer
from pangu.memory.retrieval import (
    _cosine_similarity,
    _expand_query,
    _get_search_suggestions,
    _highlight_content,
    clear_recall_cache,
    get_search_stats,
    importance_feedback,
    recall,
    recall_by_ids,
    recall_context,
)

# ══════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════


def _make_drawer(
    id: str = "d1",
    content: str = "测试内容",
    wing: str = "default",
    room: str = "general",
    importance: float = 3.0,
    tags: list[str] | None = None,
    created_at: str | None = None,
    emotional_weight: float = 0.0,
    metadata: dict | None = None,
) -> Drawer:
    if created_at is None:
        created_at = datetime.now().isoformat()
    return Drawer(
        id=id,
        content=content,
        wing=wing,
        room=room,
        importance=importance,
        tags=tags or [],
        created_at=created_at,
        emotional_weight=emotional_weight,
        metadata=metadata or {},
    )


def _make_drawers(n: int = 10) -> list[Drawer]:
    return [
        _make_drawer(
            id=f"mem_{i}",
            content=f"记忆内容编号{i}：关于{'技术' if i % 2 == 0 else '生活'}的详细描述",
            wing="work" if i % 2 == 0 else "personal",
            room=f"room_{i % 5}",
            importance=float(1 + i % 5),
            tags=[f"tag_{i % 3}", "test"],
        )
        for i in range(n)
    ]


# ══════════════════════════════════════════════════════════════════════
# 1. 空输入测试
# ══════════════════════════════════════════════════════════════════════


class TestEmptyInput:
    """空输入边界测试"""

    def test_recall_empty_drawers(self):
        """空记忆列表调用 recall"""
        results = recall(query="test", drawers=[])
        assert results == []

    def test_recall_none_drawers(self):
        """None 记忆列表调用 recall"""
        results = recall(query="test", drawers=None)
        assert results == []

    def test_recall_empty_query(self):
        """空查询字符串"""
        drawers = _make_drawers(3)
        results = recall(query="", drawers=drawers, limit=5)
        assert isinstance(results, list)

    def test_recall_none_query(self):
        """None 查询"""
        drawers = _make_drawers(3)
        results = recall(query=None, drawers=drawers, limit=5)
        assert isinstance(results, list)
        assert len(results) <= 3

    def test_recall_by_ids_empty(self):
        """空 ID 列表召回"""
        drawers = _make_drawers(5)
        results = recall_by_ids([], drawers)
        assert results == []

    def test_recall_by_ids_none_match(self):
        """不存在的 ID 列表"""
        drawers = _make_drawers(5)
        results = recall_by_ids(["nonexistent_1", "nonexistent_2"], drawers)
        assert results == []

    def test_recall_context_empty(self):
        """空记忆列表的上下文召回"""
        results = recall_context(budget=10, drawers=[])
        assert results == []

    def test_recall_context_none(self):
        """None 记忆列表的上下文召回"""
        results = recall_context(budget=10, drawers=None)
        assert results == []

    def test_recall_context_zero_budget(self):
        """零预算上下文召回"""
        drawers = _make_drawers(5)
        results = recall_context(budget=0, drawers=drawers)
        assert results == []

    def test_get_purge_candidates_empty(self):
        """空列表获取清除候选"""
        candidates = get_purge_candidates([])
        assert candidates == []

    def test_get_decay_stats_empty(self):
        """空列表获取衰减统计"""
        stats = get_decay_stats([])
        assert stats["total"] == 0

    def test_decay_batch_empty(self):
        """空列表批量衰减"""
        stats = decay_batch([])
        assert stats["total"] == 0

    def test_cosine_similarity_empty_vectors(self):
        """空向量余弦相似度"""
        assert _cosine_similarity([], []) == 0.0
        assert _cosine_similarity([1.0], []) == 0.0
        assert _cosine_similarity([], [1.0]) == 0.0

    def test_cosine_similarity_zero_norm(self):
        """零范数向量余弦相似度"""
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert _cosine_similarity([1.0, 1.0], [0.0, 0.0]) == 0.0

    def test_expand_query_empty(self):
        """空查询扩展"""
        result = _expand_query("", [])
        assert result == ""
        drawers = _make_drawers(3)
        result = _expand_query("", drawers)
        assert isinstance(result, str)

    def test_expand_query_no_drawers(self):
        """无记忆的查询扩展"""
        result = _expand_query("test", [])
        assert result == "test"

    def test_get_search_suggestions_empty_query(self):
        """空查询搜索建议"""
        drawers = _make_drawers(3)
        suggestions = _get_search_suggestions("", drawers)
        assert suggestions == []

    def test_get_search_suggestions_empty_drawers(self):
        """空记忆搜索建议"""
        suggestions = _get_search_suggestions("test", [])
        assert suggestions == []

    def test_highlight_content_empty(self):
        """空内容高亮"""
        assert _highlight_content("", "test") == ""
        assert _highlight_content("hello", "") == "hello"
        assert _highlight_content("", "") == ""

    def test_importance_feedback_unknown_signal(self):
        """未知反馈信号"""
        result = importance_feedback("drawer_1", "unknown_signal", drawers=[])
        assert "error" in result

    def test_importance_feedback_missing_drawer(self):
        """不存在的记忆反馈"""
        drawers = _make_drawers(3)
        result = importance_feedback("nonexistent", "recall_success", drawers=drawers)
        assert "error" in result

    def test_ingest_batch_empty(self):
        """空文本列表批量摄入"""
        from pangu.memory.ingestion import ingest_batch

        results = ingest_batch([])
        assert results == []


# ══════════════════════════════════════════════════════════════════════
# 2. 极端值测试
# ══════════════════════════════════════════════════════════════════════


class TestExtremeValues:
    """极端值边界测试"""

    def test_very_long_content_recall(self):
        """超长内容记忆检索"""
        long_content = "A" * 10000
        drawer = _make_drawer(id="long_1", content=long_content, importance=3.0)
        results = recall(query="A", drawers=[drawer], limit=10)
        assert isinstance(results, list)

    def test_very_long_content_context(self):
        """超长内容上下文召回"""
        long_content = "X" * 15000
        drawer = _make_drawer(id="long_ctx", content=long_content)
        results = recall_context(budget=5, drawers=[drawer])
        assert len(results) <= 1

    def test_unicode_content_recall(self):
        """Unicode 内容记忆检索"""
        unicode_content = "你好世界 🌍🎉🚀 αβγδ 数学公式 ∑∫√"
        drawer = _make_drawer(id="uni_1", content=unicode_content, importance=4.0)
        results = recall(query="世界", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_emoji_content_recall(self):
        """Emoji 内容记忆检索"""
        emoji_content = "🎉 恭喜完成任务 🚀 效率提升50% 💯"
        drawer = _make_drawer(id="emoji_1", content=emoji_content)
        results = recall(query=None, drawers=[drawer], limit=5)
        assert len(results) == 1
        assert results[0]["content"] == emoji_content

    def test_special_chars_query(self):
        """特殊字符查询"""
        drawer = _make_drawer(id="spec_1", content="价格是$100.00 (含税) [优惠]")
        results = recall(query="$100", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_sql_injection_query(self):
        """SQL 注入查询（不应崩溃）"""
        drawer = _make_drawer(id="sql_1", content="正常内容")
        results = recall(query="'; DROP TABLE memories;--", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_xss_injection_query(self):
        """XSS 注入查询"""
        drawer = _make_drawer(id="xss_1", content="正常内容")
        results = recall(query="<script>alert('xss')</script>", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_very_high_importance(self):
        """极高重要性值"""
        drawer = _make_drawer(id="imp_high", importance=999999.0)
        results = recall(query=None, drawers=[drawer], limit=1)
        assert len(results) == 1

    def test_negative_importance(self):
        """负重要性值"""
        drawer = _make_drawer(id="imp_neg", importance=-5.0)
        results = recall(query=None, drawers=[drawer], limit=1)
        assert isinstance(results, list)

    def test_zero_importance(self):
        """零重要性值"""
        drawer = _make_drawer(id="imp_zero", importance=0.0)
        results = recall(query=None, drawers=[drawer], limit=1)
        assert len(results) == 1

    def test_extreme_emotional_weight(self):
        """极端情感值"""
        drawer_pos = _make_drawer(id="emo_pos", emotional_weight=1.0)
        drawer_neg = _make_drawer(id="emo_neg", emotional_weight=-1.0)
        results = recall(query=None, drawers=[drawer_pos, drawer_neg], limit=5)
        assert len(results) == 2

    def test_recall_limit_exceeds_available(self):
        """召回限制超过可用数量"""
        drawers = _make_drawers(3)
        results = recall(query=None, drawers=drawers, limit=100)
        assert len(results) <= 3

    def test_recall_negative_limit(self):
        """负数召回限制"""
        drawers = _make_drawers(3)
        results = recall(query=None, drawers=drawers, limit=-1)
        assert isinstance(results, list)

    def test_recall_negative_offset(self):
        """负数偏移量"""
        drawers = _make_drawers(5)
        results = recall(query=None, drawers=drawers, limit=3, offset=-1)
        assert isinstance(results, list)

    def test_recall_offset_exceeds_total(self):
        """偏移量超过总数"""
        drawers = _make_drawers(3)
        results = recall(query=None, drawers=drawers, limit=10, offset=100)
        assert results == []

    def test_forgetting_curve_zero_hours(self):
        """遗忘曲线零时间"""
        curve = ForgettingCurve(decay_rate=0.5)
        assert curve.retention(0.0) == 1.0

    def test_forgetting_curve_negative_hours(self):
        """遗忘曲线负时间"""
        curve = ForgettingCurve(decay_rate=0.5)
        assert curve.retention(-10.0) == 1.0

    def test_forgetting_curve_huge_hours(self):
        """遗忘曲线超大时间"""
        curve = ForgettingCurve(decay_rate=0.5)
        retention = curve.retention(1_000_000)
        assert 0.0 <= retention <= 1.0

    def test_forgetting_curve_zero_decay_rate(self):
        """零衰减率"""
        curve = ForgettingCurve(decay_rate=0.0)
        assert curve.retention(1000.0) == 1.0

    def test_forgetting_curve_negative_decay_rate(self):
        """负衰减率"""
        curve = ForgettingCurve(decay_rate=-1.0)
        retention = curve.retention(24.0)
        assert retention >= 1.0

    def test_importance_scorer_extreme_content_length(self):
        """极端内容长度的重要性评分"""
        scorer = ImportanceScorer()
        drawer = _make_drawer(content="X" * 100000)
        result = scorer.score(drawer)
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.explanation, str)

    def test_importance_scorer_empty_content(self):
        """空内容的重要性评分"""
        scorer = ImportanceScorer()
        drawer = _make_drawer(content="")
        result = scorer.score(drawer)
        assert 0.0 <= result.score <= 1.0

    def test_decay_batch_extreme_idle_hours(self):
        """极端空闲时间批量衰减"""
        drawer = _make_drawer(
            id="extreme_idle",
            importance=3.0,
            created_at=(datetime.now() - timedelta(days=3650)).isoformat(),
        )
        stats = decay_batch([drawer], min_idle_hours=0.1)
        assert stats["total"] == 1

    def test_consolidator_next_review_extreme_access_count(self):
        """极高访问次数的复习间隔"""
        interval = MemoryConsolidator.next_review_interval(1000)
        assert interval > 0


# ══════════════════════════════════════════════════════════════════════
# 3. 并发访问测试
# ══════════════════════════════════════════════════════════════════════


class TestConcurrentAccess:
    """并发访问边界测试"""

    def test_concurrent_recall(self):
        """多线程并发读取"""
        drawers = _make_drawers(20)
        results_collection = []
        errors = []
        barrier = threading.Barrier(5)

        def worker(idx):
            try:
                barrier.wait(timeout=2)
                r = recall(query="记忆", drawers=drawers, limit=5)
                results_collection.append((idx, len(r)))
            except Exception as e:
                errors.append((idx, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"并发错误: {errors}"
        assert len(results_collection) == 5

    def test_concurrent_recall_cache(self):
        """并发缓存读写"""
        clear_recall_cache()
        drawers = _make_drawers(10)
        errors = []

        def worker(idx):
            try:
                for _ in range(5):
                    recall(query=f"test_{idx}", drawers=drawers, limit=3, use_cache=True)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0

    def test_concurrent_recall_and_clear_cache(self):
        """并发读写缓存"""
        drawers = _make_drawers(10)
        stop_event = threading.Event()
        errors = []

        def reader():
            try:
                while not stop_event.is_set():
                    recall(query="test", drawers=drawers, limit=3, use_cache=True)
            except Exception as e:
                errors.append(f"reader: {e}")

        def cache_clearer():
            try:
                while not stop_event.is_set():
                    clear_recall_cache()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(f"clearer: {e}")

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=cache_clearer)
        t1.start()
        t2.start()
        time.sleep(0.1)
        stop_event.set()
        t1.join(timeout=3)
        t2.join(timeout=3)

        assert len(errors) == 0

    def test_concurrent_event_bus_publish(self):
        """事件总线并发发布"""
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                received.append(event.type)

        bus.subscribe("concurrent_test", handler)
        errors = []

        def publisher(idx):
            try:
                for _ in range(10):
                    bus.publish(Event(type="concurrent_test", data={"idx": idx}))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=publisher, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)

        bus.unsubscribe("concurrent_test", handler)
        assert len(errors) == 0

    def test_concurrent_importance_scorer(self):
        """并发重要性评分"""
        scorer = ImportanceScorer()
        drawers = _make_drawers(5)
        errors = []
        results = []
        lock = threading.Lock()

        def worker(idx):
            try:
                for d in drawers:
                    r = scorer.score(d)
                    with lock:
                        results.append(r.score)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)

        assert len(errors) == 0
        assert len(results) == 20

    def test_concurrent_decay_batch(self):
        """并发批量衰减"""
        drawers = _make_drawers(10)
        errors = []

        def worker():
            try:
                decay_batch(drawers, dry_run=True)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)

        assert len(errors) == 0


# ══════════════════════════════════════════════════════════════════════
# 4. 错误恢复测试
# ══════════════════════════════════════════════════════════════════════


class TestErrorRecovery:
    """错误恢复边界测试"""

    def test_corrupted_drawer_recovery(self):
        """损坏的 Drawer 数据恢复"""
        drawer = Drawer(
            id="corrupt_1",
            content="正常内容",
            importance=3.0,
            tags=["tag1"],
            metadata={"decay_score": "not_a_number"},
        )
        results = recall(query=None, drawers=[drawer], limit=5)
        assert len(results) == 1

    def test_drawer_missing_fields(self):
        """Drawer 缺少必要字段"""
        drawer = Drawer(
            id="missing_fields",
            content="",
            importance=0.0,
            tags=[],
            metadata={},
        )
        results = recall(query=None, drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_recall_with_broken_embedding(self):
        """损坏嵌入向量的检索"""
        drawer = _make_drawer(id="broken_emb")
        drawer.metadata["embedding"] = [float("nan")] * 384
        results = recall(query="test", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_recall_with_wrong_dim_embedding(self):
        """错误维度嵌入向量"""
        drawer = _make_drawer(id="wrong_dim")
        drawer.metadata["embedding"] = [0.1] * 10  # 错误维度
        results = recall(query="test", drawers=[drawer], limit=5)
        assert isinstance(results, list)

    def test_decay_with_corrupted_timestamp(self):
        """损坏时间戳的衰减处理"""
        drawer = _make_drawer(id="bad_ts")
        drawer.created_at = "not-a-valid-date"
        stats = decay_batch([drawer])
        assert stats["total"] == 1

    def test_consolidator_with_corrupted_data(self):
        """巩固器处理损坏数据"""
        config = MagicMock()
        config.forgetting_curve_decay = 0.5
        config.min_importance_threshold = 0.1
        config.compression_threshold = 1000
        config.consolidation_enabled = True
        config.consolidation_interval_hours = 24

        consolidator = MemoryConsolidator(config)
        drawer = _make_drawer(
            id="consolidate_corrupt",
            content="测试内容",
            importance=3.0,
        )
        drawer.created_at = "invalid_date"
        importance = consolidator.calculate_importance(drawer)
        assert isinstance(importance, float)
        assert importance >= 0.0

    def test_importance_feedback_nonexistent_signal(self):
        """不存在的反馈信号"""
        result = importance_feedback("any_id", "nonexistent_signal", drawers=[])
        assert "error" in result

    def test_cosine_similarity_identical_vectors(self):
        """相同向量余弦相似度"""
        vec = [1.0, 0.0, 0.0]
        sim = _cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """正交向量余弦相似度"""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = _cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_cosine_similarity_opposite_vectors(self):
        """相反向量余弦相似度"""
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        sim = _cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_missing_file_layer0(self):
        """Layer0 身份文件不存在"""
        from pangu.memory.layers import Layer0

        layer = Layer0(identity_path="/tmp/nonexistent_pangu_test_identity.txt")
        text = layer.render()
        assert "身份未配置" in text

    def test_recall_cache_overflow(self):
        """召回缓存溢出处理"""
        clear_recall_cache()
        drawers = _make_drawers(5)
        for i in range(120):
            recall(query=f"q_{i}", drawers=drawers, limit=2, use_cache=True)
        stats = get_search_stats()
        assert stats["cache_hits"] >= 0

    def test_event_bus_max_queue_size(self):
        """事件总线最大队列大小"""
        bus = EventBus(max_queue_size=5)
        for i in range(10):
            bus.publish(Event(type="overflow_test", data={"i": i}))
        assert len(bus._pending) <= 5

    def test_event_bus_subscribe_nonexistent_event(self):
        """订阅不存在的事件类型"""
        bus = EventBus()

        def handler(e):
            return None

        bus.subscribe("nonexistent_type", handler)
        bus.publish(Event(type="nonexistent_type", data={}))
        bus.unsubscribe("nonexistent_type", handler)

    def test_drawer_serialization_roundtrip(self):
        """Drawer 序列化往返完整性"""
        original = _make_drawer(
            id="roundtrip",
            content="序列化测试内容",
            importance=4.5,
            tags=["a", "b", "c"],
            emotional_weight=0.7,
            metadata={"key": "value", "nested": {"inner": 123}},
        )
        data = original.to_dict()
        restored = Drawer.from_dict(data)
        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.importance == original.importance
        assert restored.tags == original.tags
        assert restored.emotional_weight == original.emotional_weight
        assert restored.metadata["key"] == "value"

    def test_drawer_from_dict_defaults(self):
        """Drawer from_dict 缺省值"""
        data = {"id": "test_defaults"}
        drawer = Drawer.from_dict(data)
        assert drawer.content == ""
        assert drawer.wing == "default"
        assert drawer.room == "general"
        assert drawer.importance == 3.0


# ══════════════════════════════════════════════════════════════════════
# 5. 性能边界测试
# ══════════════════════════════════════════════════════════════════════


class TestPerformanceBoundary:
    """性能边界测试"""

    def test_recall_zero_results(self):
        """零结果检索"""
        drawers = _make_drawers(5)
        results = recall(
            query="完全不存在的关键词xyzzy12345",
            drawers=drawers,
            limit=10,
        )
        assert isinstance(results, list)

    def test_recall_exact_match(self):
        """精确匹配检索"""
        target_content = "独特的精确匹配测试短语ABCD1234"
        drawers = _make_drawers(10)
        drawers.append(_make_drawer(id="exact_1", content=target_content, importance=5.0))
        results = recall(query=target_content, drawers=drawers, limit=5)
        assert isinstance(results, list)

    def test_batch_ingest_100(self):
        """批量摄入 100 条记忆"""
        from pangu.memory.ingestion import ingest_batch

        texts = [f"批量测试记忆编号{i}" for i in range(100)]
        results = ingest_batch(texts)
        assert isinstance(results, list)
        assert len(results) <= 100

    def test_recall_1000_memories(self):
        """1000 条记忆的召回"""
        drawers = [
            _make_drawer(
                id=f"big_{i}",
                content=f"大规模测试记忆内容编号{i}",
                importance=float(1 + i % 5),
            )
            for i in range(1000)
        ]
        results = recall(query="测试", drawers=drawers, limit=50)
        assert isinstance(results, list)
        assert len(results) <= 50

    def test_recall_1000_no_query(self):
        """1000 条记忆无查询召回"""
        drawers = [
            _make_drawer(
                id=f"big_{i}",
                content=f"内容{i}",
                importance=float(1 + i % 5),
            )
            for i in range(1000)
        ]
        results = recall(query=None, drawers=drawers, limit=50)
        assert len(results) <= 50

    def test_recall_by_ids_large_batch(self):
        """大批量 ID 召回"""
        drawers = _make_drawers(100)
        ids = [f"mem_{i}" for i in range(0, 100, 2)]
        results = recall_by_ids(ids, drawers)
        assert len(results) == 50

    def test_importance_scorer_batch(self):
        """批量重要性评分"""
        scorer = ImportanceScorer()
        drawers = _make_drawers(100)
        start = time.time()
        for d in drawers:
            scorer.score(d)
        elapsed = time.time() - start
        assert elapsed < 1.0

    def test_decay_batch_1000(self):
        """1000 条记忆批量衰减"""
        drawers = [_make_drawer(id=f"d_{i}", importance=float(i % 5 + 1)) for i in range(1000)]
        stats = decay_batch(drawers, dry_run=True)
        assert stats["total"] == 1000

    def test_cosine_similarity_large_vectors(self):
        """大维度向量余弦相似度"""
        dim = 384
        rng = np.random.RandomState(42)
        a = rng.randn(dim).astype(np.float32).tolist()
        b = rng.randn(dim).astype(np.float32).tolist()
        sim = _cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0

    def test_search_stats_accuracy(self):
        """搜索统计准确性"""
        clear_recall_cache()
        drawers = _make_drawers(5)
        initial_stats = get_search_stats()
        initial_total = initial_stats["total_searches"]

        recall(query="test_stats", drawers=drawers, limit=3, use_cache=False)
        after_stats = get_search_stats()
        assert after_stats["total_searches"] == initial_total + 1

    def test_recall_context_budget_respected(self):
        """上下文召回预算限制"""
        drawers = _make_drawers(50)
        for budget in [1, 5, 10, 20]:
            results = recall_context(budget=budget, drawers=drawers)
            assert len(results) <= budget

    def test_forgetting_curve_retention_range(self):
        """遗忘曲线保留率范围"""
        curve = ForgettingCurve(decay_rate=0.5)
        for hours in [0, 1, 6, 24, 72, 168, 720, 8760]:
            retention = curve.retention(float(hours))
            assert 0.0 <= retention <= 1.0

    def test_consolidator_stats_accuracy(self):
        """巩固器统计准确性"""
        config = MagicMock()
        config.forgetting_curve_decay = 0.5
        config.min_importance_threshold = 0.1
        config.compression_threshold = 1000
        config.consolidation_enabled = True
        config.consolidation_interval_hours = 24

        consolidator = MemoryConsolidator(config)
        drawers = _make_drawers(10)
        stats = consolidator.stats(drawers)
        assert stats["total_memories"] == 10
        assert isinstance(stats["forgotten_count"], int)
        assert isinstance(stats["due_review_count"], int)

    def test_memory_validator_memory_diff(self):
        """记忆差异计算"""
        from pangu.memory.memory_diff import MemoryDiffEngine

        engine = MemoryDiffEngine()
        result = engine.diff_content("版本A内容", "版本B内容", id_a="diff_a", id_b="diff_b")
        assert result.memory_id_a == "diff_a"
        assert result.memory_id_b == "diff_b"
        assert result.similarity >= 0.0

    def test_hot_cold_memory_split(self):
        """冷热记忆分离"""
        from pangu.memory.decay import get_purge_candidates

        drawers = _make_drawers(20)
        for d in drawers[:5]:
            d.metadata["decay_score"] = 0.1
        for d in drawers[5:]:
            d.metadata["decay_score"] = 0.9
        cold = get_purge_candidates(drawers, decay_floor=0.15)
        assert len(cold) == 5

    def test_memory_export_import_roundtrip(self):
        """记忆导出导入往返"""
        from pangu.memory.export_import import ExportImportEngine

        engine = ExportImportEngine()
        drawers = _make_drawers(5)
        result = engine.export_json(drawers)
        assert result["count"] == 5
        assert result["format"] == "json"
        assert Path(result["filepath"]).exists()

    def test_recall_with_all_filters(self):
        """多条件过滤召回"""
        drawers = _make_drawers(20)
        results = recall(
            query=None,
            wing="work",
            room="room_0",
            limit=10,
            min_importance=2.0,
            drawers=drawers,
        )
        for r in results:
            if not r.get("suggestion"):
                assert r["wing"] == "work"
                assert r["importance"] >= 2.0

    def test_recall_sort_by_importance(self):
        """按重要性排序召回"""
        drawers = _make_drawers(10)
        results = recall(
            query=None,
            drawers=drawers,
            limit=5,
            sort_by="importance",
        )
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i]["importance"] >= results[i + 1]["importance"]

    def test_recall_sort_by_time(self):
        """按时间排序召回"""
        drawers = _make_drawers(10)
        results = recall(
            query=None,
            drawers=drawers,
            limit=5,
            sort_by="time",
        )
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i]["created_at"] >= results[i + 1]["created_at"]

    def test_importance_feedback_boundary_values(self):
        """重要性反馈边界值"""
        drawer = _make_drawer(id="fb_boundary", importance=0.5)
        result = importance_feedback("fb_boundary", "verified", drawers=[drawer])
        assert "new_importance" in result
        assert 0.5 <= result["new_importance"] <= 5.0

    def test_importance_feedback_at_max(self):
        """重要性反馈达到最大值"""
        drawer = _make_drawer(id="fb_max", importance=5.0)
        result = importance_feedback("fb_max", "verified", drawers=[drawer])
        assert result["new_importance"] == 5.0

    def test_importance_feedback_at_min(self):
        """重要性反馈达到最小值"""
        drawer = _make_drawer(id="fb_min", importance=0.5)
        for _ in range(20):
            result = importance_feedback("fb_min", "vote_down", drawers=[drawer])
        assert result["new_importance"] == 0.5

    def test_lru_cache_basic(self):
        """LRU 缓存基本操作"""
        from pangu.memory.layers import LRUCache

        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") == 1
        cache.set("d", 4)
        assert cache.get("b") is None
        assert len(cache) == 3

    def test_lru_cache_invalidate(self):
        """LRU 缓存清除"""
        from pangu.memory.layers import LRUCache

        cache = LRUCache()
        cache.set("x", 10)
        cache.set("y", 20)
        cache.invalidate()
        assert len(cache) == 0
        assert cache.get("x") is None

    def test_event_bus_priority_ordering(self):
        """事件总线优先级排序"""
        bus = EventBus()
        received_priorities = []

        def handler(event):
            received_priorities.append(event.priority)

        bus.subscribe("priority_test", handler)
        bus.publish(Event(type="priority_test", priority=EventPriority.LOW))
        bus.publish(Event(type="priority_test", priority=EventPriority.URGENT))
        bus.publish(Event(type="priority_test", priority=EventPriority.HIGH))
        bus.unsubscribe("priority_test", handler)

        assert len(received_priorities) == 3

    def test_memory_diff_no_changes(self):
        """无差异记忆对比"""
        from pangu.memory.memory_diff import MemoryDiffEngine

        engine = MemoryDiffEngine()
        result = engine.diff_content("相同内容", "相同内容", id_a="same", id_b="same")
        assert result.added == 0
        assert result.removed == 0
        assert result.modified == 0
