"""召回补全（2026-10-01）—— 搜索命中旧版时把它的后继带回来。

病史：`supersede` 链完整可查（`pangu_get_supersede_chain` found=true, depth=18），
但**检索阶段从不解引用 `superseded_by`**。实测真实历史对 `04538e81`（22 个后继）
在查询"错误 之前是错的"下同批召回 **0/22**，换成旧记忆原文也只有 **2/22**；
只有当天新写、关键词高度重合的那条更正是 3/3 —— 那是样本偏差，不是机制。

本文件锁五件事：
  1. **只插入、不重排** —— 已有条目相对顺序必须原样（这是它区别于"改排序"的风险面）；
  2. 补入项**紧随其对应旧版**，且带 `recalled_via` 指明来路；
  3. **封顶** —— 22 后继不能把 10 条搜索撑成 30 条；
  4. **两条检索路径都能工作** —— 回退路径的结果项不带 `superseded` 键，要从 drawer 现算；
  5. **不越租户** —— 补全只能在调用方已可见的 `drawers` 里找。
"""

from __future__ import annotations

import pytest

from pangu.core.palace import Drawer
from pangu.server.handlers.memory_ops import (
    MAX_SUCC_PER_ITEM,
    MAX_SUPERSEDE_COMPLETIONS,
    _complete_superseded,
)


def _drawer(
    i: int,
    content: str,
    *,
    superseded_by=None,
    status: str | None = None,
    did: str | None = None,
    **kw,
) -> Drawer:
    """造一个 Drawer。`did` 显式指定 id —— 后继 id 必须与 `superseded_by`
    里的字符串**逐字对上**，否则补全查不到人，测试会假通过（added 恒 0）。

    `status` 缺省时按 `ingestion.py:561-567` 的真实写法推：那里**同时**写
    `superseded_by` 和 `memory_status="superseded"`，所以带 `superseded_by`
    就该是 superseded —— 夹具不这么默认就会测出假阴性。
    """
    d = Drawer(id=did or f"d{i}", content=content, wing="技术", room="general", **kw)
    md = dict(d.metadata or {})
    if status is None:
        status = "superseded" if superseded_by is not None else "active"
    md["memory_status"] = status
    if superseded_by is not None:
        md["superseded_by"] = list(superseded_by)
    d.metadata = md
    return d


def _result(i: int, **extra) -> dict:
    """RRF 路径形状：**带** supersede 三件套。"""
    base = {
        "id": f"d{i}",
        "content": f"旧内容 {i}",
        "wing": "技术",
        "room": "general",
        "importance": 3.0,
        "tags": [],
        "created_at": "2026-09-01T00:00:00",
        "superseded": False,
        "superseded_by": [],
        "warning": None,
    }
    base.update(extra)
    return base


def _bare_result(i: int) -> dict:
    """回退路径形状：**不带** supersede 键（search/engine.py 非 RRF 分支）。"""
    return {
        "id": f"d{i}",
        "content": f"旧内容 {i}",
        "wing": "技术",
        "room": "general",
        "importance": 3.0,
        "tags": [],
        "created_at": "2026-09-01T00:00:00",
    }


# ── ① 只插入、不重排 ─────────────────────────────────────────────


class TestOrderPreserved:
    def test_no_superseded_returns_the_same_object(self):
        """无事可做时必须**原样返回入参**，调用方靠身份判断有没有变化。"""
        items = [_result(1), _result(2)]
        out, added = _complete_superseded(items, [])
        assert out is items, "没补东西就不该换一个列表对象"
        assert added == 0

    def test_unrelated_items_keep_their_relative_order(self):
        """补入会把后续条目**顶后一位**（它紧随旧版），但**已有条目之间**的
        相对次序必须原样 —— 这才是「只插入、不重排」的准确含义。"""
        old = _drawer(1, "旧", superseded_by=["d9"])
        other = _drawer(2, "无关")
        new = _drawer(9, "新版")
        drawers = [old, other, new]

        items = [_result(1, superseded=True, superseded_by=["d9"]), _result(2)]
        out, added = _complete_superseded(items, drawers)

        assert added == 1
        ids = [r["id"] for r in out]
        assert ids[0] == "d1", "旧版本身位置不能动"
        assert ids.index("d1") < ids.index("d2"), "已有条目相对次序必须原样"
        assert ids == ["d1", "d9", "d2"], "补入项紧随其旧版"

    def test_successor_lands_immediately_after_its_old_version(self):
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        items = [
            _result(1, superseded=True, superseded_by=["d9"]),
            _result(2),
            _result(3),
        ]
        out, _ = _complete_superseded(items, [old, new])
        ids = [r["id"] for r in out]
        assert ids == ["d1", "d9", "d2", "d3"]

    def test_idempotent_second_pass_adds_nothing(self):
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        drawers = [old, new]
        items = [_result(1, superseded=True, superseded_by=["d9"])]
        out, added = _complete_superseded(items, drawers)
        assert added == 1
        out2, added2 = _complete_superseded(out, drawers)
        assert added2 == 0, "已在结果里的后继不得重复补"
        assert [r["id"] for r in out2] == [r["id"] for r in out]


# ── ② 补入项的自述 ───────────────────────────────────────────────


class TestCompletedItemSelfDescribe:
    def test_carries_recalled_via_pointing_at_the_old_version(self):
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        items = [_result(1, superseded=True, superseded_by=["d9"])]
        out, _ = _complete_superseded(items, [old, new])
        assert out[1]["recalled_via"] == "d1", "必须能说清「我是被谁带进来的」"

    def test_shape_matches_the_ranked_items(self):
        """补入项要与同行条目同形，调用方不用写两套解析。"""
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        items = [_result(1, superseded=True, superseded_by=["d9"])]
        out, _ = _complete_superseded(items, [old, new])
        ranked_keys = {k for k in out[0] if k != "recalled_via"}
        assert ranked_keys <= set(out[1].keys()), f"补入项缺字段: {ranked_keys - set(out[1].keys())}"

    def test_no_fabricated_ranks(self):
        """没参与本次排序就不许有 rank —— 伪造会污染按通道的判定。"""
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        items = [_result(1, superseded=True, superseded_by=["d9"])]
        out, _ = _complete_superseded(items, [old, new])
        added = out[1]
        for key in ("rrf_score", "fts_rank", "vector_rank", "kg_rank", "relevance", "score"):
            assert key not in added, f"补入项不该伪造 {key}"

    def test_drawer_source_not_leaked_as_retrieval_channel(self):
        """`Drawer.source` 是来源平台（mcp/dsh），结果项 `source` 是召回通道
        （semantic/lexical）—— 同名不同义，写进去会污染通道分桶。"""
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版", source="mcp")
        items = [_result(1, superseded=True, superseded_by=["d9"])]
        out, _ = _complete_superseded(items, [old, new])
        assert "source" not in out[1]

    def test_successor_that_is_itself_superseded_says_so(self):
        """A→B→C：补进来的 B 若自己也被取代，必须自述，否则等于又给了个旧的。"""
        old = _drawer(1, "A", superseded_by=["d2"])
        mid = _drawer(2, "B", superseded_by=["d3"], status="superseded")
        items = [_result(1, superseded=True, superseded_by=["d2"])]
        out, _ = _complete_superseded(items, [old, mid])
        assert out[1]["id"] == "d2"
        assert out[1]["superseded"] is True
        assert out[1]["warning"] == "⚠ 已被更新"


# ── ③ 封顶 ───────────────────────────────────────────────────────


class TestBounds:
    def test_total_cap_holds_with_many_successors(self):
        """真实场景：一条记忆有 22 个后继，不能把 10 条搜索撑成 30 条。"""
        succ = [f"s{i}" for i in range(22)]
        old = _drawer(1, "旧", superseded_by=succ)
        drawers = [old] + [_drawer(i, f"后继{i}", did=f"s{i}") for i in range(22)]
        items = [_result(1, superseded=True, superseded_by=succ), _result(2)]

        out, added = _complete_superseded(items, drawers)
        assert added > 0, "夹具的后继 id 必须与 superseded_by 对上，否则这条是假通过"
        assert added <= MAX_SUPERSEDE_COMPLETIONS
        assert len(out) == len(items) + added

    def test_takes_the_newest_successors(self):
        """`superseded_by` 按取代顺序 append（ingestion.py:561）→ 末尾最新。
        封顶时该给**最新**的，不是最老的。"""
        succ = [f"s{i}" for i in range(10)]
        old = _drawer(1, "旧", superseded_by=succ)
        drawers = [old] + [_drawer(i, f"后继{i}", did=f"s{i}") for i in range(10)]
        items = [_result(1, superseded=True, superseded_by=succ)]

        out, added = _complete_superseded(items, drawers, max_total=2)
        assert added == min(MAX_SUCC_PER_ITEM, 2)
        picked = [r["id"] for r in out[1:]]
        assert picked == [f"s{i}" for i in range(10 - len(picked), 10)], f"应取末尾最新的，实际 {picked}"

    def test_missing_successor_is_skipped_not_invented(self):
        """后继 id 指向的 drawer 不可见（被租户过滤掉）时必须跳过，不许凭空造。"""
        old = _drawer(1, "旧", superseded_by=["dX"])
        items = [_result(1, superseded=True, superseded_by=["dX"])]
        out, added = _complete_superseded(items, [old])
        assert added == 0
        assert [r["id"] for r in out] == ["d1"]


# ── ④ 两条检索路径 ───────────────────────────────────────────────


class TestBothSearchPaths:
    def test_fallback_path_without_supersede_keys_still_completes(self):
        """回退路径（search/engine.py 非 RRF 分支）的结果项**不带** supersede 键。
        只认结果键的话，这条路径上补全等于没上。"""
        old = _drawer(1, "旧", superseded_by=["d9"], status="superseded")
        new = _drawer(9, "新版")
        items = [_bare_result(1), _bare_result(2)]

        out, added = _complete_superseded(items, [old, new])
        assert added == 1, "回退路径必须同样生效"
        assert out[1]["id"] == "d9"
        assert out[1]["recalled_via"] == "d1"
        assert out[0]["id"] == "d1"

    def test_non_superseded_drawer_never_triggers(self):
        """memory_status 不是 superseded 就不补 —— 别把「活跃」当成「被取代」。"""
        active = _drawer(1, "活跃", status="active")
        other = _drawer(2, "别的")
        items = [_result(1), _result(2)]
        out, added = _complete_superseded(items, [active, other])
        assert added == 0
        assert out is items

    def test_empty_and_non_list_inputs_are_tolerated(self):
        assert _complete_superseded([], [_drawer(1, "x")]) == ([], 0)
        assert _complete_superseded(None, []) == (None, 0)


# ── ⑤ 非 dict 项不崩 ─────────────────────────────────────────────


class TestRobustness:
    def test_non_dict_items_pass_through(self):
        items = ["not-a-dict", _result(1, superseded=True, superseded_by=["d9"])]
        old = _drawer(1, "旧", superseded_by=["d9"])
        new = _drawer(9, "新版")
        out, added = _complete_superseded(items, [old, new])
        assert out[0] == "not-a-dict"
        assert added == 1

    def test_drawer_without_metadata_does_not_crash(self):
        d = Drawer(id="d1", content="无 metadata")
        d.metadata = None
        old = _result(1)
        out, added = _complete_superseded([old], [d])
        assert added == 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
