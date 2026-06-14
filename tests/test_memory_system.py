"""盘古记忆系统综合测试 — 覆盖存储/检索/遗忘曲线/巩固/自然语言查询/多Agent协作

使用 pytest 框架，测试核心功能模块：
- 记忆存储与检索（Drawer CRUD + 向量搜索）
- 遗忘曲线与巩固机制（ForgettingCurve + MemoryConsolidator）
- 自然语言查询（NaturalLanguageQuery + MemoryRecommender）
- 多Agent协作（MultiAgentMemory + 权限隔离 + 同步）
- 性能优化模块（HNSW + ARC 缓存 + 对象池 + 批量操作）
"""

import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.consolidation import ForgettingCurve, MemoryConsolidator
from pangu.memory.decay import decay_batch, get_decay_stats, get_purge_candidates
from pangu.memory.multi_agent import (
    ConflictResolution,
    MemoryScope,
    MultiAgentMemory,
    SyncStrategy,
)
from pangu.memory.natural_query import (
    MemoryRecommender,
    NaturalLanguageQuery,
    natural_language_search,
)
from pangu.memory.performance import (
    ARCCache,
    BatchProcessor,
    HNSWVectorIndex,
    ObjectPool,
    PerformanceOptimizer,
)
from pangu.memory.retrieval import recall, recall_by_ids, recall_context


# ══════════════════════════════════════════════════════════════════════
# 辅助工厂
# ══════════════════════════════════════════════════════════════════════


def _make_drawer(
    id: str = "d1",
    content: str = "测试记忆内容",
    wing: str = "default",
    room: str = "general",
    importance: float = 3.0,
    tags: list[str] | None = None,
    created_at: str | None = None,
) -> Drawer:
    """快速构造 Drawer 对象"""
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
    )


def _make_drawers(n: int = 10, prefix: str = "mem") -> list[Drawer]:
    """批量构造 Drawer"""
    return [
        _make_drawer(
            id=f"{prefix}_{i}",
            content=f"记忆内容 {i}：关于 {'技术' if i % 2 == 0 else '生活'} 的记录",
            wing="work" if i % 2 == 0 else "personal",
            room=f"room_{i % 5}",
            importance=float(1 + i % 5),
            tags=[f"tag_{i % 3}", "test"],
        )
        for i in range(n)
    ]


def _make_vector(dim: int = 384, seed: int = 0) -> list[float]:
    """生成确定性向量"""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


# ══════════════════════════════════════════════════════════════════════
# 1. 记忆存储与检索
# ══════════════════════════════════════════════════════════════════════


class TestMemoryStorage:
    """记忆存储测试"""

    def test_drawer_create(self):
        """测试 Drawer 创建与属性"""
        drawer = _make_drawer(id="test_001", content="测试内容", importance=4.0)
        assert drawer.id == "test_001"
        assert drawer.content == "测试内容"
        assert drawer.importance == 4.0

    def test_drawer_serialization(self):
        """测试 Drawer 序列化/反序列化"""
        drawer = _make_drawer(id="s001", content="序列化测试", tags=["a", "b"])
        data = drawer.to_dict()
        restored = Drawer.from_dict(data)
        assert restored.id == "s001"
        assert restored.content == "序列化测试"
        assert "a" in restored.tags

    def test_drawer_metadata(self):
        """测试 Drawer 元数据"""
        drawer = _make_drawer()
        drawer.metadata["decay_score"] = 0.85
        drawer.metadata["embedding"] = [0.1] * 10
        assert drawer.metadata["decay_score"] == 0.85
        assert len(drawer.metadata["embedding"]) == 10


class TestMemoryRetrieval:
    """记忆检索测试"""

    def test_recall_basic(self):
        """测试基础检索"""
        drawers = _make_drawers(5)
        results = recall(query=None, drawers=drawers, limit=5)
        assert len(results) <= 5
        assert all("id" in r for r in results)

    def test_recall_by_wing(self):
        """测试按 Wing 过滤"""
        drawers = _make_drawers(20)
        results = recall(wing="work", drawers=drawers, limit=10)
        for r in results:
            assert r["wing"] == "work"

    def test_recall_by_importance(self):
        """测试按重要性过滤"""
        drawers = _make_drawers(10)
        results = recall(min_importance=4.0, drawers=drawers, limit=10)
        for r in results:
            assert r["importance"] >= 4.0

    def test_recall_by_ids(self):
        """测试按 ID 批量检索"""
        drawers = _make_drawers(10)
        results = recall_by_ids(["mem_0", "mem_3", "mem_7"], drawers)
        assert len(results) == 3
        ids = {r["id"] for r in results}
        assert "mem_0" in ids
        assert "mem_3" in ids

    def test_recall_context(self):
        """测试上下文窗口检索"""
        drawers = _make_drawers(20)
        results = recall_context(budget=5, drawers=drawers)
        assert len(results) <= 5
        # 上下文检索应按综合评分排序
        if len(results) >= 2:
            scores = [r.get("search_score", 0) for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_recall_empty(self):
        """测试空列表检索"""
        results = recall(drawers=[])
        assert results == []

    def test_recall_sort_by_importance(self):
        """测试按重要性排序"""
        drawers = [
            _make_drawer(id="low", content="低重要性", importance=1.0),
            _make_drawer(id="high", content="高重要性", importance=5.0),
        ]
        results = recall(drawers=drawers, sort_by="importance")
        assert results[0]["id"] == "high"

    def test_recall_sort_by_time(self):
        """测试按时间排序"""
        now = datetime.now()
        drawers = [
            _make_drawer(id="old", content="旧记忆",
                         created_at=(now - timedelta(days=7)).isoformat()),
            _make_drawer(id="new", content="新记忆",
                         created_at=now.isoformat()),
        ]
        results = recall(drawers=drawers, sort_by="time")
        assert results[0]["id"] == "new"


# ══════════════════════════════════════════════════════════════════════
# 2. 遗忘曲线与巩固机制
# ══════════════════════════════════════════════════════════════════════


class TestForgettingCurve:
    """遗忘曲线测试"""

    def test_retention_at_zero(self):
        """零时刻保留率应为 1.0"""
        curve = ForgettingCurve(decay_rate=0.5)
        assert curve.retention(0) == 1.0

    def test_retention_monotonic_decay(self):
        """保留率随时间单调递减"""
        curve = ForgettingCurve(decay_rate=0.5)
        prev = 1.0
        for hours in [1, 6, 12, 24, 48, 72, 168]:
            r = curve.retention(hours)
            assert r < prev, f"保留率未递减: {hours}h -> {r}"
            prev = r

    def test_retention_positive(self):
        """保留率始终为正"""
        curve = ForgettingCurve(decay_rate=0.5)
        for h in [0, 1, 24, 168, 720]:
            assert curve.retention(h) > 0

    def test_different_decay_rates(self):
        """不同衰减率的保留率差异"""
        slow = ForgettingCurve(decay_rate=0.3)
        fast = ForgettingCurve(decay_rate=0.7)
        assert slow.retention(24) > fast.retention(24)


class TestMemoryConsolidation:
    """记忆巩固测试"""

    def test_calculate_importance(self):
        """综合重要性评分应为正值"""
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        drawer = _make_drawer(
            content="重要记忆，包含丰富内容和多个标签",
            importance=5.0,
            tags=["important", "test", "memory"],
        )
        score = consolidator.calculate_importance(drawer)
        assert score > 0

    def test_importance_with_tags(self):
        """多标签记忆重要性应更高"""
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)

        d_no_tags = _make_drawer(id="no_tags", content="无标签记忆", importance=3.0)
        d_with_tags = _make_drawer(id="tags", content="有标签记忆",
                                    importance=3.0, tags=["a", "b", "c"])

        s1 = consolidator.calculate_importance(d_no_tags)
        s2 = consolidator.calculate_importance(d_with_tags)
        assert s2 >= s1

    def test_should_not_forget_important(self):
        """重要记忆不应被遗忘"""
        config = PanguConfig()
        config.min_importance_threshold = 10.0
        consolidator = MemoryConsolidator(config)
        drawer = _make_drawer(content="非常重要", importance=5.0)
        assert not consolidator.should_forget(drawer)

    def test_should_forget_low_importance(self):
        """低重要性记忆应被遗忘"""
        config = PanguConfig()
        config.min_importance_threshold = 5.0
        consolidator = MemoryConsolidator(config)
        drawer = _make_drawer(
            content="不重要",
            importance=0.1,
            created_at=(datetime.now() - timedelta(hours=72)).isoformat(),
        )
        assert consolidator.should_forget(drawer)

    def test_access_tracking(self):
        """访问计数应正确递增"""
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        consolidator.record_access("mem_1")
        consolidator.record_access("mem_1")
        consolidator.record_access("mem_2")
        assert consolidator.get_access_count("mem_1") == 2
        assert consolidator.get_access_count("mem_2") == 1

    def test_next_review_interval(self):
        """间隔重复间隔应递增"""
        intervals = [
            MemoryConsolidator.next_review_interval(i)
            for i in range(6)
        ]
        for i in range(len(intervals) - 1):
            assert intervals[i] < intervals[i + 1]

    def test_compressible_detection(self):
        """超过阈值应触发压缩"""
        config = PanguConfig()
        config.compression_threshold = 10
        consolidator = MemoryConsolidator(config)
        drawers = _make_drawers(15)
        assert consolidator.should_compress(drawers)

    def test_consolidation_stats(self):
        """巩固统计应包含所有关键字段"""
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        drawers = _make_drawers(5)
        stats = consolidator.stats(drawers)
        assert "total_memories" in stats
        assert "forgotten_count" in stats
        assert "due_review_count" in stats
        assert "average_effective_importance" in stats


class TestDecayBatch:
    """批量衰减测试"""

    def test_decay_batch_basic(self):
        """批量衰减基本流程"""
        drawers = _make_drawers(10)
        for d in drawers:
            d.metadata["decay_score"] = 1.0
            d.created_at = (datetime.now() - timedelta(days=7)).isoformat()
        stats = decay_batch(drawers, min_idle_hours=0, dry_run=True)
        assert stats["total"] == 10
        assert stats["dry_run"] is True

    def test_decay_stats(self):
        """衰减统计"""
        drawers = _make_drawers(5)
        for d in drawers:
            d.metadata["decay_score"] = 0.8
        stats = get_decay_stats(drawers)
        assert stats["total"] == 5
        assert stats["avg_decay_score"] > 0

    def test_purge_candidates(self):
        """清除候选检测"""
        drawers = _make_drawers(5)
        drawers[0].metadata["decay_score"] = 0.1  # 低于阈值
        drawers[1].metadata["decay_score"] = 0.9
        candidates = get_purge_candidates(drawers, decay_floor=0.15)
        assert len(candidates) == 1
        assert candidates[0].id == drawers[0].id


# ══════════════════════════════════════════════════════════════════════
# 3. 自然语言查询
# ══════════════════════════════════════════════════════════════════════


class TestNaturalLanguageQuery:
    """自然语言查询解析测试"""

    def test_parse_search_intent(self):
        """搜索意图检测"""
        parser = NaturalLanguageQuery()
        result = parser.parse("帮我找一下 Python 相关的记忆")
        assert result["intent"] == "search"
        assert len(result["keywords"]) > 0

    def test_parse_summary_intent(self):
        """总结意图检测"""
        parser = NaturalLanguageQuery()
        result = parser.parse("总结一下最近的工作记忆")
        assert result["intent"] == "summary"

    def test_parse_analysis_intent(self):
        """分析意图检测"""
        parser = NaturalLanguageQuery()
        result = parser.parse("统计一下我有多少条记忆")
        assert result["intent"] == "analysis"

    def test_parse_timeline_intent(self):
        """时间线意图检测"""
        parser = NaturalLanguageQuery()
        result = parser.parse("什么时候创建的记忆")
        assert result["intent"] == "timeline"

    def test_extract_time_range_today(self):
        """提取时间范围 — 今天"""
        parser = NaturalLanguageQuery()
        result = parser.parse("看看今天的记忆")
        assert result["time_range"] == timedelta(days=0)

    def test_extract_time_range_week(self):
        """提取时间范围 — 最近一周"""
        parser = NaturalLanguageQuery()
        result = parser.parse("最近一周的技术记忆")
        assert result["time_range"] == timedelta(days=7)

    def test_extract_wing(self):
        """提取空间"""
        parser = NaturalLanguageQuery()
        result = parser.parse("技术相关的记忆")
        assert result["wing"] == "tech"

    def test_extract_importance(self):
        """提取重要性"""
        parser = NaturalLanguageQuery()
        result = parser.parse("重要的决策记忆")
        assert result["importance_threshold"] > 0

    def test_natural_language_search(self):
        """自然语言搜索集成"""
        drawers = _make_drawers(10)
        results = natural_language_search("总结工作空间的记忆", drawers, limit=5)
        assert isinstance(results, list)


class TestMemoryRecommender:
    """记忆推荐测试"""

    def test_empty_recommend(self):
        """空列表推荐应返回空"""
        rec = MemoryRecommender([])
        results = rec.recommend("Python 编程")
        assert results == []

    def test_fallback_recommend(self):
        """降级推荐（无嵌入时基于重要性）"""
        drawers = _make_drawers(5)
        rec = MemoryRecommender(drawers)
        # 使用不存在的嵌入服务触发降级
        results = rec._fallback_recommend(limit=3)
        assert len(results) <= 3
        assert all("score" in r for r in results)

    def test_score_calculation(self):
        """综合评分计算"""
        rec = MemoryRecommender()
        drawer = _make_drawer(importance=5.0)
        score = rec._calculate_score(drawer, similarity=0.8)
        assert 0 < score <= 1.0

    def test_time_decay_score(self):
        """时间衰减评分"""
        rec = MemoryRecommender()

        # 新记忆
        new_drawer = _make_drawer(
            created_at=datetime.now().isoformat()
        )
        assert rec._time_decay_score(new_drawer) == 1.0

        # 旧记忆
        old_drawer = _make_drawer(
            created_at=(datetime.now() - timedelta(days=60)).isoformat()
        )
        assert rec._time_decay_score(old_drawer) < 1.0


# ══════════════════════════════════════════════════════════════════════
# 4. 多Agent协作
# ══════════════════════════════════════════════════════════════════════


class TestMultiAgentMemory:
    """多Agent协作记忆测试"""

    def test_register_agents(self):
        """注册多个Agent"""
        mam = MultiAgentMemory()
        mam.register_agent("xihe", priority=10)
        mam.register_agent("xuannv", priority=5)
        agents = mam.get_agents()
        assert "xihe" in agents
        assert "xuannv" in agents
        assert agents["xihe"] == 10

    def test_private_memory(self):
        """私有记忆仅创建者可见"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mem = mam.write("agent_a", "这是私有记忆", scope=MemoryScope.PRIVATE)
        assert mem.owner == "agent_a"

        # agent_a 可见
        results_a = mam.read("agent_a")
        assert any(m.id == mem.id for m in results_a)

        # agent_b 不可见
        results_b = mam.read("agent_b")
        assert not any(m.id == mem.id for m in results_b)

    def test_shared_memory(self):
        """共享记忆对指定Agent可见"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mem = mam.write(
            "agent_a", "这是共享记忆",
            scope=MemoryScope.SHARED,
            shared_with=["agent_b"],
        )

        results_b = mam.read("agent_b")
        assert any(m.id == mem.id for m in results_b)

    def test_public_memory(self):
        """公开记忆对所有Agent可见"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")
        mam.register_agent("agent_c")

        mem = mam.write("agent_a", "这是公开记忆", scope=MemoryScope.PUBLIC)

        for agent_id in ["agent_a", "agent_b", "agent_c"]:
            results = mam.read(agent_id)
            assert any(m.id == mem.id for m in results)

    def test_memory_update(self):
        """更新记忆（仅创建者）"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mem = mam.write("agent_a", "原始内容")

        updated = mam.update("agent_a", mem.id, content="更新后内容")
        assert updated.content == "更新后内容"
        assert updated.version == 2

    def test_memory_delete(self):
        """删除记忆（仅创建者）"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mem = mam.write("agent_a", "待删除记忆")

        assert mam.delete("agent_a", mem.id)
        assert mam.get("agent_a", mem.id) is None

    def test_permission_error(self):
        """无权更新/删除应报错"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")
        mem = mam.write("agent_a", "私有记忆")

        with pytest.raises(PermissionError):
            mam.update("agent_b", mem.id, content="非法修改")
        with pytest.raises(PermissionError):
            mam.delete("agent_b", mem.id)

    def test_share_memory(self):
        """分享记忆给其他Agent"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mem = mam.write("agent_a", "分享记忆", scope=MemoryScope.PRIVATE)
        assert mam.share("agent_a", mem.id, ["agent_b"])

        results_b = mam.read("agent_b")
        assert any(m.id == mem.id for m in results_b)

    def test_revoke_access(self):
        """撤销访问权"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mem = mam.write(
            "agent_a", "记忆",
            scope=MemoryScope.SHARED,
            shared_with=["agent_b"],
        )
        mam.revoke_access("agent_a", mem.id, ["agent_b"])

        results_b = mam.read("agent_b")
        assert not any(m.id == mem.id for m in results_b)

    def test_memory_reference(self):
        """记忆引用与追溯"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")

        mem1 = mam.write("agent_a", "基础记忆")
        mem2 = mam.write("agent_a", "引用记忆", references=[mem1.id])

        refs = mam.get_references_to(mem1.id)
        assert len(refs) == 1
        assert refs[0].referrer_id == mem2.id

    def test_lineage_trace(self):
        """血缘追溯"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")

        mem1 = mam.write("agent_a", "根记忆")
        mem2 = mam.write("agent_a", "子记忆", references=[mem1.id])
        mem3 = mam.write("agent_a", "孙记忆", references=[mem2.id])

        lineage = mam.trace_lineage(mem3.id)
        assert len(lineage) >= 2

    def test_search_in_memories(self):
        """Agent内搜索"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.write("agent_a", "Python 异步编程")
        mam.write("agent_a", "JavaScript 前端开发")

        results = mam.search("agent_a", "Python")
        assert len(results) == 1
        assert "Python" in results[0].content

    def test_sync_events(self):
        """同步事件生成"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mam.write("agent_a", "新记忆", scope=MemoryScope.PUBLIC)
        pending = mam.get_pending_syncs("agent_b")
        assert len(pending) >= 1

    def test_stats(self):
        """协作统计"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")
        mam.write("agent_a", "记忆1", scope=MemoryScope.PUBLIC)
        mam.write("agent_b", "记忆2", scope=MemoryScope.PRIVATE)

        stats = mam.stats
        assert stats["total_agents"] == 2
        assert stats["total_memories"] == 2

    def test_conflict_detection(self):
        """冲突检测"""
        mam = MultiAgentMemory()
        mam.register_agent("agent_a")
        mam.register_agent("agent_b")

        mam.write("agent_a", "Python 支持异步编程，推荐使用 asyncio")
        mam.write("agent_b", "Python 不支持异步编程，不推荐使用 asyncio")

        conflicts = mam.detect_conflicts()
        assert isinstance(conflicts, list)

    def test_unregistered_agent(self):
        """未注册Agent无法写入"""
        mam = MultiAgentMemory()
        with pytest.raises(ValueError):
            mam.write("unknown_agent", "test")


# ══════════════════════════════════════════════════════════════════════
# 5. 性能优化模块
# ══════════════════════════════════════════════════════════════════════


class TestHNSWVectorIndex:
    """HNSW向量索引测试"""

    def test_add_and_search(self):
        """添加并搜索"""
        idx = HNSWVectorIndex(dim=8, max_connections=4, ef_construction=10, ef_search=10)
        vecs = [_make_vector(dim=8, seed=i) for i in range(20)]
        for i, v in enumerate(vecs):
            idx.add(f"v_{i}", v)

        results = idx.search(vecs[0], top_k=5)
        assert len(results) > 0
        assert results[0][0] == "v_0"  # 最相似的应是自身

    def test_search_empty(self):
        """空索引搜索"""
        idx = HNSWVectorIndex(dim=8)
        results = idx.search([0.0] * 8, top_k=5)
        assert results == []

    def test_add_batch(self):
        """批量添加"""
        idx = HNSWVectorIndex(dim=8, max_connections=4, ef_construction=10, ef_search=10)
        ids = [f"b_{i}" for i in range(30)]
        vecs = [_make_vector(dim=8, seed=i + 100) for i in range(30)]
        count = idx.add_batch(ids, vecs)
        assert count == 30
        assert idx.size == 30

    def test_remove(self):
        """删除节点"""
        idx = HNSWVectorIndex(dim=8, max_connections=4, ef_construction=10)
        idx.add("v1", _make_vector(dim=8, seed=1))
        idx.add("v2", _make_vector(dim=8, seed=2))
        assert idx.remove("v1")
        assert idx.size == 1
        assert not idx.remove("nonexistent")

    def test_stats(self):
        """索引统计"""
        idx = HNSWVectorIndex(dim=8, max_connections=4, ef_construction=10)
        for i in range(10):
            idx.add(f"v_{i}", _make_vector(dim=8, seed=i))
        stats = idx.stats()
        assert stats["size"] == 10
        assert stats["dim"] == 8
        assert "layers" in stats

    def test_dimension_mismatch(self):
        """维度不匹配应报错"""
        idx = HNSWVectorIndex(dim=8)
        with pytest.raises(ValueError):
            idx.add("bad", [0.0] * 16)

    def test_high_dimensional(self):
        """高维向量"""
        idx = HNSWVectorIndex(dim=384, max_connections=8, ef_construction=20, ef_search=10)
        vecs = [_make_vector(dim=384, seed=i) for i in range(50)]
        for i, v in enumerate(vecs):
            idx.add(f"hd_{i}", v)
        results = idx.search(vecs[0], top_k=5)
        assert len(results) > 0


class TestARCCache:
    """ARC缓存测试"""

    def test_basic_put_get(self):
        """基础存取"""
        cache = ARCCache[str](capacity=10)
        cache.put("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_cache_miss(self):
        """缓存未命中"""
        cache = ARCCache[str](capacity=10)
        assert cache.get("missing") is None

    def test_capacity_limit(self):
        """容量限制"""
        cache = ARCCache[str](capacity=5)
        for i in range(10):
            cache.put(f"k{i}", f"v{i}")
        assert cache.size <= 5

    def test_hit_rate(self):
        """命中率统计"""
        cache = ARCCache[str](capacity=10)
        cache.put("k1", "v1")
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        assert cache.hit_rate == 0.5

    def test_ghost_list_adaptation(self):
        """Ghost list 自适应"""
        cache = ARCCache[str](capacity=5)
        # 填满缓存
        for i in range(5):
            cache.put(f"k{i}", f"v{i}")
        # 淘汰部分
        for i in range(5):
            cache.get(f"k{i}")
        for i in range(5):
            cache.put(f"new_{i}", f"v_{i}")
        # ghost list 命中应调整 p
        for i in range(5):
            cache.get(f"k{i}")
        stats = cache.stats()
        assert stats["p"] > 0

    def test_invalidate(self):
        """清空缓存"""
        cache = ARCCache[str](capacity=10)
        cache.put("k1", "v1")
        cache.invalidate()
        assert cache.size == 0
        assert cache.get("k1") is None

    def test_update_existing(self):
        """更新已有键"""
        cache = ARCCache[str](capacity=10)
        cache.put("k1", "v1")
        cache.put("k1", "v2")
        assert cache.get("k1") == "v2"
        assert cache.size == 1


class TestObjectPool:
    """对象池测试"""

    def test_acquire_release(self):
        """获取和归还"""
        pool = ObjectPool[int](factory=lambda: 0, max_size=5)
        obj = pool.acquire()
        assert obj == 0
        pool.release(obj)
        assert pool.size == 1

    def test_reuse(self):
        """对象复用"""
        pool = ObjectPool[str](factory=lambda: "new", max_size=5)
        obj1 = pool.acquire()
        pool.release(obj1)
        obj2 = pool.acquire()
        assert obj1 is obj2  # 同一对象被复用

    def test_pool_max_size(self):
        """池容量限制"""
        pool = ObjectPool[int](factory=lambda: 0, max_size=3)
        for i in range(10):
            pool.release(i)
        assert pool.size <= 3

    def test_reset_callback(self):
        """归还时重置"""
        class Box:
            def __init__(self):
                self.value = 0
        pool = ObjectPool[Box](
            factory=Box,
            reset=lambda b: setattr(b, "value", 0),
            max_size=5,
        )
        box = pool.acquire()
        box.value = 42
        pool.release(box)
        box2 = pool.acquire()
        assert box2.value == 0

    def test_stats(self):
        """池统计"""
        pool = ObjectPool[int](factory=lambda: 0, max_size=5)
        pool.acquire()
        pool.acquire()
        stats = pool.stats()
        assert stats["created"] == 2
        assert stats["reused"] == 0

    def test_clear(self):
        """清空池"""
        pool = ObjectPool[int](factory=lambda: 0, max_size=5)
        pool.release(1)
        pool.release(2)
        pool.clear()
        assert pool.size == 0


class TestBatchProcessor:
    """批量操作优化器测试"""

    def test_add_write_triggers_flush(self):
        """缓冲区满触发刷新"""
        bp = BatchProcessor(batch_size=3)
        flushed = []
        bp.on_flush(lambda batch: flushed.extend(batch))

        bp.add_write("k1", "v1")
        bp.add_write("k2", "v2")
        triggered = bp.add_write("k3", "v3")
        assert triggered
        assert len(flushed) == 3

    def test_force_flush(self):
        """强制刷新"""
        bp = BatchProcessor(batch_size=100)
        bp.add_write("k1", "v1")
        bp.add_write("k2", "v2")
        batch = bp.force_flush()
        assert len(batch) == 2
        assert bp.batch.stats()["buffer_size"] == 0

    def test_batch_encode(self):
        """批量向量编码"""
        texts = ["文本1", "文本2", "文本3"]
        results = BatchProcessor.batch_encode(
            texts, embed_fn=lambda t: [0.1, 0.2, 0.3], batch_size=2
        )
        assert len(results) == 3

    def test_merge_search_results(self):
        """RRF 搜索结果合并"""
        r1 = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
        r2 = [("b", 0.85), ("a", 0.75), ("d", 0.6)]
        merged = BatchProcessor.merge_search_results([r1, r2], top_k=3)
        assert len(merged) == 3
        # "a" 和 "b" 同时出现在两组中，应排名靠前
        ids = [m[0] for m in merged]
        assert "a" in ids
        assert "b" in ids

    def test_empty_batch_encode(self):
        """空文本编码"""
        results = BatchProcessor.batch_encode([], embed_fn=lambda t: [])
        assert results == []

    def test_stats(self):
        """统计信息"""
        bp = BatchProcessor(batch_size=5)
        bp.add_write("k1", "v1")
        bp.force_flush()
        stats = bp.stats()
        assert stats["total_flushed"] == 1
        assert stats["total_flush_calls"] == 1


class TestPerformanceOptimizer:
    """性能优化器集成测试"""

    def test_init(self):
        """初始化"""
        optimizer = PerformanceOptimizer(dim=32)
        assert optimizer.dim == 32
        assert optimizer.hnsw.dim == 32

    def test_combined_search(self):
        """组合搜索（缓存 + HNSW）"""
        optimizer = PerformanceOptimizer(dim=8, hnsw_m=4, hnsw_ef_construction=10, hnsw_ef_search=10)
        for i in range(20):
            optimizer.hnsw.add(f"item_{i}", _make_vector(dim=8, seed=i))

        query = _make_vector(dim=8, seed=0)
        r1 = optimizer.combined_search(query, top_k=5)
        assert len(r1) > 0
        # 第二次应从缓存命中
        r2 = optimizer.combined_search(query, top_k=5)
        assert r1 == r2

    def test_combined_search_no_cache(self):
        """禁用缓存的组合搜索"""
        optimizer = PerformanceOptimizer(dim=8, hnsw_m=4, hnsw_ef_construction=10)
        for i in range(10):
            optimizer.hnsw.add(f"i_{i}", _make_vector(dim=8, seed=i))

        query = _make_vector(dim=8, seed=0)
        results = optimizer.combined_search(query, top_k=3, use_arc_cache=False)
        assert len(results) > 0

    def test_drawer_pool(self):
        """Drawer 对象池"""
        optimizer = PerformanceOptimizer()
        pool = optimizer.init_drawer_pool(max_size=10)
        assert pool is not None

        obj = pool.acquire()
        assert obj is not None
        pool.release(obj)
        stats = pool.stats()
        assert stats["pool_size"] == 1

    def test_stats(self):
        """综合统计"""
        optimizer = PerformanceOptimizer(dim=8)
        stats = optimizer.stats()
        assert "uptime_sec" in stats
        assert "hnsw" in stats
        assert "arc_cache" in stats
        assert "batch" in stats

    def test_arc_cache_in_optimizer(self):
        """优化器中的ARC缓存"""
        optimizer = PerformanceOptimizer()
        optimizer.arc_cache.put("key", [1, 2, 3])
        assert optimizer.arc_cache.get("key") == [1, 2, 3]
