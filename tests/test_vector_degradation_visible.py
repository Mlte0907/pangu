"""向量路径的降级必须**看得见**。

2026-09-26 修的问题：`FTS5SearchEngine` 的向量路径有两层 `except Exception` 静默吞异常
（批量失败降级逐条、逐条失败 continue），导致嵌入器一坏，搜索就悄悄退化成纯 FTS ——
结果变差，但**没有日志、没有异常、返回值也看不出区别**。

同一个模块的 `hybrid_search.py` 早就有 `logger.debug`，这里 lacked 对应物。

这些测试锁三件事：
1. 降级会打 warning（不是静默）
2. 返回值里 `degraded=True`，能把它和「没有文档达阈值」区分开
3. **降级前后搜索结果完全一致** —— 加可观测性不许动行为
"""

import logging

import pytest

from pangu.core.palace import Drawer
from pangu.memory.fts_search import FTS5SearchEngine

WORDS = ["memory", "wiki", "graph", "retrieval", "decay", "python", "agent", "tenant"]


def _drawers(n: int = 30) -> list[Drawer]:
    return [
        Drawer(
            id=f"d{i:04d}",
            content=f"Memory {i}: " + " ".join(WORDS[i % len(WORDS) : i % len(WORDS) + 4]),
            wing="tech",
            room="general",
            hall="main",
            importance=3.0,
            tags=["python"],
            author="",
            source="",
            source_file="",
            created_at="2026-08-28T01:04:34",
            metadata={},
        )
        for i in range(n)
    ]


class _Boom(Exception):
    pass


class _StubEmbedder:
    """可控的嵌入器：能整体抛异常，也能逐条抛。"""

    def __init__(self, batch_raises=False, item_raises_at=None, dim=8):
        self.batch_raises = batch_raises
        self.item_raises_at = item_raises_at
        self.dim = dim
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        if self.item_raises_at is not None and self.calls >= self.item_raises_at:
            raise _Boom("item embed failed")
        # 让不同文本有不同向量，便于相似度有区分度
        return [((hash(text) >> (i * 3)) % 97) / 97.0 for i in range(self.dim)]

    def embed_batch(self, texts, max_workers=4):
        if self.batch_raises:
            raise _Boom("batch embed failed")
        return [self.embed(t) for t in texts]


# 注意：这里所有 search 都必须传 use_cache=False。
# `_SEARCH_CACHE` 是**模块级全局 LRU**（fts_search.py 顶部），key 只由
# (query, wing, room, limit, offset, min_importance, vector_weight) 组成 ——
# 与嵌入器状态无关。所以同一 query 的第二次调用会直接拿到上一次的响应，
# `degraded` 标志读到的是别人的结果。这既是本测试的坑，也是线上排查时的坑。
def _engine(embedder) -> FTS5SearchEngine:
    e = FTS5SearchEngine()
    e._embedder = embedder
    e.build_index(_drawers())
    return e


def test_batch_failure_logs_and_marks_degraded(caplog):
    """批量嵌入抛异常 → 必须打 warning，且 degraded=True。"""
    e = _engine(_StubEmbedder(batch_raises=True, item_raises_at=None))
    with caplog.at_level(logging.WARNING, logger="pangu.memory.fts_search"):
        r = e.search(query="memory", drawers=_drawers(), limit=5, use_cache=False)

    warns = [r_.message for r_ in caplog.records if r_.levelno >= logging.WARNING]
    assert warns, "批量嵌入失败却没有打任何 warning —— 这就是那个静默降级"
    assert any("批量嵌入失败" in m for m in warns), f"warning 文案没提批量失败：{warns}"
    assert r["degraded"] is True, "降级了但 degraded=False，等于没报"
    # 注意：降级 ≠ 向量不可用。逐条路径仍能产出结果，所以 `vector_used` 可以是 True
    #（代价是慢一个数量级）。早先我在这里断言 `vector_used is False`，那是**错的** ——
    #  降级路径存在的意义就是「慢但能用」，把它断言成不可用等于要求它别救场。
    assert r["vector_used"] is True, "逐条降级路径应仍能产出向量结果"


def test_degraded_flag_not_sticky_across_searches(caplog):
    """降级标志**不能**粘住：下一次正常搜索必须是 False。

    这是加 thread-local 标志时最容易写错的地方 —— 上一��降级泄漏到下一请求，
    就会长期误报降级，比不报还糟。
    """
    bad = _engine(_StubEmbedder(batch_raises=True))
    with caplog.at_level(logging.WARNING, logger="pangu.memory.fts_search"):
        first = bad.search(query="memory", drawers=_drawers(), limit=5, use_cache=False)
    assert first["degraded"] is True

    good = _engine(_StubEmbedder())
    second = good.search(query="memory", drawers=_drawers(), limit=5, use_cache=False)
    assert second["degraded"] is False, "降级标志粘住了：正常搜索被误报成降级"


def test_low_similarity_is_not_reported_as_degraded():
    """没有文档相似度达阈值 = 正常，不该被当成故障。

    这是加 degraded 字段的**主要动机**：此前 `method` 在「向量坏了」和
    「向量正常但没匹配上」两种情况下都是 "fts"，故障因此隐形。
    """
    e = _engine(_StubEmbedder())
    r = e.search(query="完全不存在的词zzzz", drawers=_drawers(), limit=5, use_cache=False)
    assert r["degraded"] is False, "没匹配上是正常结果，不该报降级"


def test_per_item_failure_is_aggregated_not_flooded(caplog):
    """逐条嵌入失败要聚合成一条日志，不能刷屏。

    1000 条全失败时刷 1000 行会把真正的日志淹掉。
    """
    e = _engine(_StubEmbedder(item_raises_at=3))
    with caplog.at_level(logging.WARNING, logger="pangu.memory.fts_search"):
        e.search(query="memory", drawers=_drawers(), limit=5, use_cache=False)

    warns = [r_ for r_ in caplog.records if r_.levelno >= logging.WARNING]
    per_item = [r_ for r_ in warns if "向量降级路径" in r_.message]
    assert per_item, "逐条嵌入全失败却没有任何日志"
    assert len(per_item) == 1, f"逐条失败被刷成 {len(per_item)} 条日志，应该聚合成 1 条"
    assert "27/30" in per_item[0].message or "/30" in per_item[0].message, (
        f"汇总日志应写明失败条数：{per_item[0].message}"
    )


def test_degradation_does_not_change_results(caplog):
    """**降级前后返回的结果必须完全一致** —— 加可观测性不许动行为。"""
    drawers = _drawers()

    ok = _engine(_StubEmbedder())
    r_ok = ok.search(query="memory wiki", drawers=drawers, limit=5, use_cache=False)
    assert r_ok["degraded"] is False

    with caplog.at_level(logging.WARNING, logger="pangu.memory.fts_search"):
        deg = _engine(_StubEmbedder(batch_raises=True, item_raises_at=None))
        r_deg = deg.search(query="memory wiki", drawers=drawers, limit=5, use_cache=False)
    assert r_deg["degraded"] is True

    assert [x["id"] for x in r_ok["results"]] == [x["id"] for x in r_deg["results"]], (
        "降级路径给出了不同的结果 id 序列 —— 可观测性改动影响了行为"
    )


def test_empty_result_also_carries_degraded_key(caplog):
    """空结果分支也要带 degraded，否则调用方按 key 取会 KeyError。"""
    e = _engine(_StubEmbedder(batch_raises=True))
    with caplog.at_level(logging.WARNING, logger="pangu.memory.fts_search"):
        r = e.search(query="memory", drawers=[], limit=5, use_cache=False)
    assert "degraded" in r, "空结果分支漏了 degraded 键"
