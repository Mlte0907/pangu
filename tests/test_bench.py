"""盘古性能基准测试 — 搜索/检索/索引速度、并发压测、内存分析

使用 pytest-benchmark 提供一致的基准报告。
模块未安装时整体跳过。
"""

import asyncio
import gc
import os
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta

import pytest

# ── 模块缺失检查（放在最前） ──
pytest.importorskip("pytest_benchmark", reason="需要安装 pytest-benchmark")

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.decay import decay_batch, get_decay_stats
from pangu.memory.fts_search import FTS5SearchEngine
from pangu.memory.knowledge_graph import KnowledgeGraph
from pangu.memory.vector_index import VectorIndex
from pangu.memory.working_memory import WMItem, get_working_memory

# ── Fixtures ──


def _gen_drawers(n: int) -> list[Drawer]:
    """生成测试用的 Drawer 列表"""
    import random

    random.seed(42)
    wings = ["tech", "life", "work", "study", "default"]
    rooms = ["general", "important", "daily", "code", "design"]
    keywords = [
        "python",
        "fastapi",
        "memory",
        "neural",
        "transformer",
        "graph",
        "database",
        "indexing",
        "search",
        "vector",
        "embedding",
        "retrieval",
        "decay",
        "consolidation",
        "knowledge",
        "wiki",
        "agent",
        "llm",
        "context",
        "attention",
        "transformer",
    ]
    drawers = []
    base = datetime.now() - timedelta(days=30)
    for i in range(n):
        text = f"Memory {i}: " + " ".join(random.choices(keywords, k=random.randint(3, 8)))
        d = Drawer(
            id=f"drawer_{i:06d}",
            content=text,
            wing=random.choice(wings),
            room=random.choice(rooms),
            importance=random.random(),
            created_at=(base + timedelta(hours=i)).isoformat(),
            tags=random.sample(["python", "llm", "memory", "agent"], k=2),
        )
        drawers.append(d)
    return drawers


@pytest.fixture
def small_drawers():
    return _gen_drawers(100)


@pytest.fixture
def medium_drawers():
    return _gen_drawers(1000)


@pytest.fixture
def large_drawers():
    return _gen_drawers(5000)


# ── 1. 搜索性能 ──


class TestSearchBench:
    """搜索性能基准"""

    def test_bench_fts_search_small(self, small_drawers, benchmark):
        """FTS 搜索 100 条记忆"""
        engine = FTS5SearchEngine(PanguConfig())
        engine.build_index(small_drawers)
        result = benchmark(engine.search, "python memory", small_drawers, limit=10)
        assert isinstance(result, dict)
        assert "results" in result

    def test_bench_fts_search_medium(self, medium_drawers, benchmark):
        """FTS 搜索 1000 条记忆"""
        engine = FTS5SearchEngine(PanguConfig())
        engine.build_index(medium_drawers)
        result = benchmark(engine.search, "neural network", medium_drawers, limit=10)
        assert isinstance(result, dict)

    def test_bench_fts_search_large(self, large_drawers, benchmark):
        """FTS 搜索 5000 条记忆"""
        engine = FTS5SearchEngine(PanguConfig())
        engine.build_index(large_drawers)
        result = benchmark(engine.search, "vector embedding", large_drawers, limit=10)
        assert isinstance(result, dict)


# ── 2. 索引构建性能 ──


class TestIndexBench:
    """索引构建性能基准"""

    def test_bench_fts_build_small(self, small_drawers, benchmark):
        """FTS 索引构建 100 条"""
        engine = FTS5SearchEngine(PanguConfig())
        benchmark(engine.build_index, small_drawers)

    def test_bench_fts_build_medium(self, medium_drawers, benchmark):
        """FTS 索引构建 1000 条"""
        engine = FTS5SearchEngine(PanguConfig())
        benchmark(engine.build_index, medium_drawers)

    def test_bench_fts_build_large(self, large_drawers, benchmark):
        """FTS 索引构建 5000 条"""
        engine = FTS5SearchEngine(PanguConfig())
        benchmark(engine.build_index, large_drawers)

    def test_bench_vector_build_medium(self, medium_drawers, benchmark):
        """向量索引构建 1000 条 (dim=128)"""
        idx = VectorIndex(dim=128)

        def _build():
            vectors = []
            for d in medium_drawers:
                v = [float((hash(d.content) >> (j * 4)) & 0xFF) / 255.0 for j in range(128)]
                vectors.append(v)
            return idx.build(vectors, [d.id for d in medium_drawers])

        benchmark(_build)


# ── 3. 检索性能 ──


class TestRetrievalBench:
    """记忆检索性能"""

    def test_bench_recall_simple(self, small_drawers, benchmark):
        """简单 recall 性能"""

        def _recall():
            return [d for d in small_drawers if "python" in d.content][:10]

        result = benchmark(_recall)
        assert isinstance(result, list)

    def test_bench_recall_with_filter(self, medium_drawers, benchmark):
        """带过滤的 recall 性能"""

        def _recall_filtered():
            return [d for d in medium_drawers if "neural" in d.content and d.wing == "tech"][:10]

        result = benchmark(_recall_filtered)
        assert isinstance(result, list)


# ── 4. 衰减性能 ──


class TestDecayBench:
    """衰减处理性能"""

    def test_bench_decay_batch_small(self, small_drawers, benchmark):
        """批量衰减 100 条"""
        benchmark(decay_batch, small_drawers)

    def test_bench_decay_batch_medium(self, medium_drawers, benchmark):
        """批量衰减 1000 条"""
        benchmark(decay_batch, medium_drawers)

    def test_bench_decay_stats(self, small_drawers, benchmark):
        """decay 统计性能"""
        benchmark(get_decay_stats, small_drawers)


# ── 5. 工作记忆性能 ──


class TestWorkingMemoryBench:
    """工作记忆性能"""

    def test_bench_wm_push_get(self, benchmark):
        """WM push+get 性能"""
        wm = get_working_memory()
        wm.clear()

        def _push_get():
            item = WMItem(
                id=f"bench_{os.urandom(4).hex()}",
                content="benchmark content for working memory test",
                tokens=10,
            )
            wm.push(item)
            return wm.get(item.id)

        result = benchmark(_push_get)
        assert result is not None
        wm.clear()


# ── 6. 知识图谱性能 ──


class TestKnowledgeGraphBench:
    """知识图谱性能"""

    def test_bench_kg_add_entities(self, benchmark):
        """添加实体性能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = PanguConfig(palace_path=tmpdir)
            kg = KnowledgeGraph(cfg)

            def _add():
                for i in range(100):
                    kg.add_entity(
                        f"entity_{i}",
                        f"entity_{i}",
                        "concept",
                        description=f"weight={i}",
                    )

            benchmark(_add)

    def test_bench_kg_query(self, benchmark):
        """图谱查询性能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = PanguConfig(palace_path=tmpdir)
            kg = KnowledgeGraph(cfg)
            for i in range(100):
                kg.add_entity(f"entity_{i}", f"entity_{i}", "concept")
                if i > 0:
                    kg.add_relation(
                        f"rel_{i}",
                        f"entity_{i - 1}",
                        "follows",
                        f"entity_{i}",
                    )

            result = benchmark(kg.find_path, "entity_0", "entity_99", max_depth=10)
            assert isinstance(result, list)


# ── 7. 并发压测 ──


class TestConcurrencyBench:
    """并发压测"""

    @pytest.mark.asyncio
    async def test_concurrent_search(self, medium_drawers):
        """100 并发搜索"""
        engine = FTS5SearchEngine(PanguConfig())
        engine.build_index(medium_drawers)

        async def _search(query: str) -> int:
            return len(engine.search(query, medium_drawers, limit=5)["results"])

        queries = [f"term_{i}" for i in range(100)]
        start = time.time()
        results = await asyncio.gather(*[_search(q) for q in queries])
        elapsed = time.time() - start

        assert len(results) == 100
        # 平均每次 < 50ms
        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 50, f"平均搜索耗时 {avg_ms:.1f}ms 超过 50ms"

    @pytest.mark.asyncio
    async def test_concurrent_wm_ops(self):
        """50 并发 WM 操作"""
        wm = get_working_memory()
        wm.clear()

        async def _op(i: int) -> str:
            item = WMItem(
                id=f"concurrent_{i}",
                content=f"concurrent content {i}",
                tokens=5,
            )
            wm.push(item)
            return item.id

        start = time.time()
        ids = await asyncio.gather(*[_op(i) for i in range(50)])
        elapsed = time.time() - start

        assert len(ids) == 50
        # 总耗时 < 1s
        assert elapsed < 1.0, f"50 并发 WM 操作耗时 {elapsed:.2f}s 超过 1s"
        wm.clear()


# ── 8. 内存分析 ──


class TestMemoryBench:
    """内存占用分析"""

    def test_fts_engine_memory(self, large_drawers):
        """FTS 引擎内存占用"""
        gc.collect()
        tracemalloc.start()

        engine = FTS5SearchEngine(PanguConfig())
        engine.build_index(large_drawers)
        for _ in range(10):
            engine.search("test query", large_drawers, limit=5)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 5000 条记忆峰值内存应 < 100MB
        assert peak < 100 * 1024 * 1024, f"峰值内存 {peak / 1024 / 1024:.1f}MB 超过 100MB"

    def test_wm_memory(self):
        """工作记忆内存"""
        gc.collect()
        tracemalloc.start()

        wm = get_working_memory()
        wm.clear()
        for i in range(100):
            wm.push(WMItem(id=f"mem_{i}", content="x" * 200, tokens=50))

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 100 条工作记忆应 < 5MB
        assert peak < 5 * 1024 * 1024
        wm.clear()

    def test_vector_index_memory(self, medium_drawers):
        """向量索引内存占用"""
        gc.collect()
        tracemalloc.start()

        idx = VectorIndex(dim=384)
        vectors = [[float((hash(d.content) >> (j * 4)) & 0xFF) / 255.0 for j in range(384)] for d in medium_drawers]
        idx.build(vectors, [d.id for d in medium_drawers])

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 1000 条 384 维向量应 < 50MB
        assert peak < 50 * 1024 * 1024


# ── 9. 端到端性能 ──


class TestE2EBench:
    """端到端性能"""

    def test_bench_full_pipeline_small(self, small_drawers, benchmark):
        """完整流程：索引 + 多次搜索"""
        engine = FTS5SearchEngine(PanguConfig())

        def _full_pipeline():
            engine.build_index(small_drawers)
            for q in ["python", "memory", "agent", "neural", "vector"]:
                engine.search(q, small_drawers, limit=5)

        benchmark(_full_pipeline)
