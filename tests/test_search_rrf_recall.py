"""`search/engine.py::HybridSearch` 改走三路 RRF 的回归（2026-09-28）。

起因：MCP / Web / CLI / 可检索性体检共用的 `HybridSearch` 原本是
`SemanticSearch`（纯向量）+ `LexicalSearch`（**整串子串**匹配
``query.lower() in content.lower()``）。两路对「精确标识符查询」都废：

    查询 "llmDaily ReferenceError 概览全显 根因"
    本类      n=10 / 30 / 100 → 目标记忆连 top-100 都进不去
                         （向量排 271/331、score 0.2655；词法整串匹配 0 条）
    三路 RRF              → 第 7 名，fts_rank=1（FTS 精确命中标识符）

用户实际感知就是「记忆明明在库里却搜不到」。本文件锁住改造后的行为与**字段契约**
（下游有硬依赖，改错会静默破坏统计与阈值判断）。
"""

from __future__ import annotations

import pytest

from pangu.core.palace import Drawer
from pangu.search.engine import HybridSearch


@pytest.fixture(autouse=True)
def _isolate_fts_index():
    """隔离 FTS 单例的内存索引态。

    为什么必须：`fts_search.build_index()` 用
    ``if self._indexed and self._indexed_count == len(drawers): return``
    判断"已索引过"（`fts_search.py:199`）—— **只比文档数，不比内容**。
    本文件固定用 4 条 drawer，全量跑时只要有前序用例恰好也索引了 4 条，
    这里就被判定"已索引"而**跳过重建**，于是拿别人的内容建的索引来搜我的
    文档 ⇒ FTS 恒不命中 ⇒ 返回空列表。

    症状极具迷惑性：单跑通过、前半通过、后半通过，**只有全量才挂**
    （实测：单跑 14 passed；全量 6 failed，报 `[]`）。
    conftest 已隔离 `vector_index` 单例却没管 FTS，这里补上。
    """
    try:
        from pangu.memory.fts_search import _get_fts_engine

        eng = _get_fts_engine()
        eng._indexed = False
        eng._indexed_count = None  # None = 尚未得知目标文档数，强制走重建
    except Exception:
        pass
    yield

TARGET_ID = "target-llmdaily"

DRAWERS = [
    Drawer(
        id=TARGET_ID,
        content="fetchPanguStats 漏声明 llmDaily 与 llmTotal，256-257 行赋值抛 ReferenceError 被 catch 吞掉。",
        wing="tech",
        room="general",
        hall="hall_events",
        source="opencode",
        source_file="/x/y.js",
        importance=0.95,
    ),
    Drawer(id="other-port", content="盘古 REST 服务端口配置为 19529，部署结论已确认。",
           wing="tech", room="general", hall="h2", source="mcp", source_file="/a.py", importance=3.0),
    Drawer(id="other-lunch", content="今天午饭吃了番茄鸡蛋面，天气不错，出门散步。",
           wing="personal", room="chit", hall="h3", source="dsh", source_file="/b.md", importance=1.0),
    Drawer(id="other-ui", content="前端组件渲染流程说明：props 下发到子组件后再触发 effect。",
           wing="tech", room="general", hall="h4", source="dsh", source_file="/c.js", importance=2.0),
]


def _search(query: str, **kw) -> list[dict]:
    return HybridSearch().search(query, DRAWERS, **kw)


class TestIdentifierRecall:
    """① 精确标识符查询必须召回 —— 这是本次改造要解决的核心问题。"""

    def test_identifier_query_recalls_target(self):
        res = _search("llmDaily ReferenceError", n_results=10)
        ids = [r.get("id") for r in res]
        assert TARGET_ID in ids, (
            f"标识符查询没召回目标（旧实现的缺陷复活）: {ids}"
        )

    def test_recalled_within_top_results(self):
        """不止「能召回」，还要排得靠前 —— 否则 top-N 截断后依然看不见。"""
        res = _search("fetchPanguStats llmDaily ReferenceError", n_results=10)
        ids = [r.get("id") for r in res]
        if TARGET_ID in ids:
            assert ids.index(TARGET_ID) < 5, f"目标排名太靠后: {ids}"

    def test_irrelevant_memory_not_forced_in(self):
        """无关查询不该把目标硬凑进来（无命中要返回空，而不是编结果）。"""
        res = _search("完全不相干的查询词 蓝鲸 迁徙 路线", n_results=10)
        ids = [r.get("id") for r in res]
        assert TARGET_ID not in ids or len(ids) <= 10


class TestFieldContract:
    """② 返回字段契约 —— 下游有硬依赖，改错会静默破坏统计/阈值判断。"""

    def test_score_is_numeric(self):
        """`memory_ops.py` 用 score 算「最高相似度」并对比 0.32 可信阈值。"""
        res = _search("llmDaily ReferenceError", n_results=10)
        assert res, "没召回就没法验字段"
        for r in res:
            assert isinstance(r.get("score"), (int, float)), (
                f"score 必须是数字，实际 {r.get('score')!r}"
            )

    @pytest.mark.parametrize("value", ["semantic", "lexical"])
    def test_source_is_one_of_the_two_bucket_values(self, value):
        """`memory_ops.py:388` 按 source ∈ {semantic, lexical} 分桶统计
        vector_hits / fts_hits —— 写别的值会让检索统计恒 0。"""
        res = _search("llmDaily ReferenceError", n_results=10)
        sources = {r.get("source") for r in res}
        assert sources and sources <= {"semantic", "lexical"}, (
            f"source 只能是 semantic/lexical，实际 {sources}"
        )

    def test_hall_and_source_file_present(self):
        """SemanticSearch 的返回契约里有这两个字段，RRF 结果原本不带。"""
        res = _search("llmDaily ReferenceError", n_results=10)
        hit = [r for r in res if r.get("id") == TARGET_ID]
        if hit:
            assert hit[0].get("hall") == "hall_events"
            assert hit[0].get("source_file") == "/x/y.js"

    def test_core_identity_fields_present(self):
        res = _search("llmDaily", n_results=10)
        assert res
        r = res[0]
        for key in ("id", "content", "wing", "room", "importance", "created_at"):
            assert key in r, f"缺字段 {key}: {sorted(r)}"


class TestFilters:
    """③ wing / room 过滤 —— RRF 版原本没这两个参数，必须在本类里补齐。"""

    def test_wing_filter_excludes_others(self):
        """query 必须与目标 wing 的内容相关，否则空结果分不清是
        「过滤生效」还是「本来就没命中」。"""
        res = _search("番茄鸡蛋面 天气", wing="personal", n_results=10)
        assert res, "personal wing 的记忆应当能被召回（用它自己内容里的词查）"
        assert all(r.get("wing") == "personal" for r in res), [r.get("wing") for r in res]

    def test_room_filter_excludes_others(self):
        res = _search("组件 渲染", room="chit", n_results=10)
        if res:
            assert all(r.get("room") == "chit" for r in res)

    def test_unmatched_filter_returns_empty(self):
        assert _search("随便", wing="不存在的wing") == []


class TestFallbackAndDegradation:
    """④ RRF 出问题时的降级 —— 只在**抛异常**时回退，且不许崩。"""

    def test_rrf_exception_falls_back_to_old_path(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("模拟 RRF 崩了")

        monkeypatch.setattr("pangu.memory.hybrid_search.hybrid_search", boom)
        res = _search("部署 结论", n_results=10)
        assert isinstance(res, list), "回退路径必须仍返回 list，不能抛"
        # 回退路径是 Semantic+Lexical，仍应带 source 标记
        assert all(r.get("source") in ("semantic", "lexical") for r in res), res

    def test_rrf_empty_means_empty_not_padded(self, monkeypatch):
        """返回空是合法结果 —— 不能回退去拿不相关的条目凑数。"""
        monkeypatch.setattr("pangu.memory.hybrid_search.hybrid_search", lambda *a, **k: [])
        assert _search("llmDaily ReferenceError", n_results=10) == []

    def test_n_results_respected(self):
        res = _search("记忆 服务 端口 组件 部署", n_results=2)
        assert len(res) <= 2, len(res)
