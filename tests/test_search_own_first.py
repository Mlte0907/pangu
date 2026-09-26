"""搜索「本平台优先」的两个模式（2026-09-26）。

用户诉求：搜记忆时先推本平台存的，再推别平台存的 —— 理由是「别的平台遇到过的坑，
我搜到可以拿来鉴别是否有用」。

两个模式（env PANGU_OWN_FIRST_MODE 切换）：
  split = 硬分两档（A）。本平台整块前置。实测代价：「浏览器 自动化 点击 失败」这条查询
          把改前第 1 名（importance 5.0 的「避免死循环验证」教训）整体挤出了前 10。
  boost = 位次加权（B，默认）。本平台每条提前 N 位，强相关的别平台记忆仍留在前面。
  off   = 不干预（= 改造前原始行为）。

本测试锁：
  1. split 必须稳定分档（档内保序），不能按平台排序；
  2. boost 要在「保住强相关」与「本平台确实上浮」之间取得平衡；
  3. 两者都在 room 为空（api_key 身份）时**完全不重排** —— 宁可不给优先，也不给错优先；
  4. 超额取（overfetch）—— engine 内部 `merged[:n_results]` 会截断；
  5. total 契约 —— total == len(results)，否则会污染 record_search 的搜索次数统计。
"""

import inspect

import pytest

from pangu.core.palace import Drawer
from pangu.server.handlers.memory_ops import (
    _OWN_FIRST_BOOST_POSITIONS,
    _OWN_FIRST_MAX_POOL,
    _OWN_FIRST_OVERFETCH,
    _apply_own_first,
    _boost_own,
    _own_first_mode,
    _partition_own_first,
)


@pytest.fixture(autouse=True)
def _clean_mode_env():
    """每个用例都从干净的环境变量出发，避免相互污染。"""
    import os

    os.environ.pop("PANGU_OWN_FIRST_MODE", None)
    os.environ.pop("PANGU_OWN_FIRST_BOOST", None)
    yield
    os.environ.pop("PANGU_OWN_FIRST_MODE", None)
    os.environ.pop("PANGU_OWN_FIRST_BOOST", None)


def _items(*ids):
    return [{"id": i, "content": f"c-{i}"} for i in ids]


def test_own_platform_goes_first():
    items = _items("a", "b", "c", "d")
    owner = {"a": "other", "b": "mine", "c": "other", "d": "mine"}
    out = _partition_own_first(items, owner, "mine")
    assert [i["id"] for i in out] == ["b", "d", "a", "c"]


def test_relevance_order_preserved_within_each_tier():
    """档内不能被重排 —— 这是本实现最容易写错的地方。

    直接 sort(key=is_own) 会把同档内的相关性顺序打乱：这里 own 段是 b、d，
    other 段是 a、c，重排后必须仍然是 b,d,a,c。
    """
    items = _items("a", "b", "c", "d", "e")
    owner = {"a": "o", "b": "m", "c": "o", "d": "m", "e": "o"}
    out = [i["id"] for i in _partition_own_first(items, owner, "m")]
    assert out == ["b", "d", "a", "c", "e"]


def test_no_platform_identity_means_no_reordering():
    """room 为空串 ⇒ 原样返回。

    云端实测 46 条记忆 metadata.tenant_id 为空（api_key 身份写入）。若把空串当
    平台名，这批会被误判成「本平台的」顶到最前。
    """
    items = _items("a", "b", "c")
    owner = {"a": "", "b": "other", "c": ""}
    assert _partition_own_first(items, owner, "") is items


def test_missing_owner_map_means_no_reordering():
    items = _items("a", "b")
    assert _partition_own_first(items, {}, "mine") is items
    assert _partition_own_first(items, None, "mine") is items


def test_non_dict_items_are_treated_as_other_not_crashed():
    """脏数据不能让搜索整个抛异常。"""
    items = [{"id": "a", "content": "x"}, "垃圾数据", None]
    owner = {"a": "mine"}
    out = _partition_own_first(items, owner, "mine")
    assert out[0] == {"id": "a", "content": "x"}
    assert len(out) == 3


def test_graduated_own_rows_still_count_as_own():
    """已毕业（visibility=public）但归属仍是本平台的记忆，算「本平台写的」。

    毕业只改可见性、不改归属，所以本平台写的毕业记忆仍应排在本平台档里 ——
    这符合用户「自己平台存的」这个说法。
    """
    items = [{"id": "g", "content": "graduated"}, {"id": "o", "content": "other"}]
    owner = {"g": "mine", "o": "other"}  # g 的 visibility 是 public，不影响归属判断
    out = [i["id"] for i in _partition_own_first(items, owner, "mine")]
    assert out == ["g", "o"]


# ── boost（默认模式，B）──


def test_boost_lifts_own_but_keeps_strong_other_at_top():
    """boost 的核心价值：**强相关的别平台记忆仍留在第 1 位**。

    这是 split 做不到的：split 会把别平台那条整块挤到本平台那批之后，
    实测「浏览器 自动化 点击 失败」因此丢掉了改前第 1 名。

    构造：a/b/c 是别平台，d 是本平台且原第 4 位。提前 3 位后 d 的有效位次为 0，
    与 a 的 0 并列、按原位次 a 仍居首 —— 这正是「加权」相对「分档」的价值：
    本平台的确实上浮了（4 → 2），但别平台第 1 名没被挤掉（split 会把它压到第 5）。
    """
    items = _items("a", "b", "c", "d")
    owner = {"a": "o", "b": "o", "c": "o", "d": "m"}
    out = [i["id"] for i in _boost_own(items, owner, "m", positions=3)]
    assert out == ["a", "d", "b", "c"], out
    assert out[0] == "a", "别平台第 1 名必须保住"
    assert out.index("d") < out.index("b"), "本平台的 d 应升到别平台 b 之前"


def test_boost_equals_ties_are_broken_by_original_position():
    """同一位次按原始顺序 —— 否则同一查询每次结果顺序可能不同。"""
    # a 与 d 上浮后有效位次都是 0，按原位次 a 先
    items = _items("a", "b", "c", "d")
    owner = {"a": "o", "b": "o", "c": "o", "d": "m"}
    out = [i["id"] for i in _boost_own(items, owner, "m", positions=3)]
    assert out.index("a") < out.index("d")


def test_boost_is_deterministic():
    items = _items("a", "b", "c", "d", "e", "f")
    owner = {"a": "m", "b": "o", "c": "m", "d": "o", "e": "m", "f": "o"}
    runs = [[i["id"] for i in _boost_own(items, owner, "m", positions=2)] for _ in range(5)]
    assert all(r == runs[0] for r in runs), f"结果不稳定：{runs}"


def test_boost_with_zero_positions_is_noop():
    items = _items("a", "b", "c")
    assert _boost_own(items, {"a": "m"}, "m", positions=0) is items


def test_boost_default_positions_are_sane():
    assert _OWN_FIRST_BOOST_POSITIONS == 4, "4 是实测拐点，改动前请重跑 scripts/ab_own_first.py 的位次扫描"
    assert 1 <= _OWN_FIRST_BOOST_POSITIONS <= 10, "提前位次过小没效果，过大会退化成 split"


def test_positions_overridable_by_env():
    """调参是运维动作，不该每次都改代码重新部署。"""
    import os

    from pangu.server.handlers.memory_ops import _own_first_positions

    os.environ.pop("PANGU_OWN_FIRST_BOOST", None)
    assert _own_first_positions() == _OWN_FIRST_BOOST_POSITIONS
    os.environ["PANGU_OWN_FIRST_BOOST"] = "7"
    assert _own_first_positions() == 7
    os.environ["PANGU_OWN_FIRST_BOOST"] = "-3"
    assert _own_first_positions() == 0, "负数应被夹到 0（等于不干预），不能变负数"
    os.environ["PANGU_OWN_FIRST_BOOST"] = "999"
    assert _own_first_positions() == 50, "上限 50 防呆：过大就退化成 split 行为了"
    os.environ["PANGU_OWN_FIRST_BOOST"] = "乱写"
    assert _own_first_positions() == _OWN_FIRST_BOOST_POSITIONS, "非法值回落默认值"


def test_boost_uses_env_positions_when_not_given():
    import os

    os.environ["PANGU_OWN_FIRST_BOOST"] = "2"
    items = _items("a", "b", "c", "d")
    owner = {"a": "o", "b": "o", "c": "o", "d": "m"}
    out = [i["id"] for i in _boost_own(items, owner, "m")]
    # d 原在第 4 位（index 3），提前 2 位 → 第 3 位（index 2）
    assert out.index("d") == 2, f"提前 2 位应从第 4 升到第 3：{out}"


def test_boost_respects_empty_tenant():
    items = _items("a", "b", "c")
    owner = {"a": "", "b": "o", "c": ""}
    assert _boost_own(items, owner, "") is items
    assert _boost_own(items, {}, "m") is items
    assert _boost_own(["x"], {"x": "m"}, "m") == ["x"], "单条无需重排"


def test_boost_tolerates_dirty_items():
    items = [{"id": "a", "content": "x"}, "垃圾", None, {"id": "b"}]
    out = _boost_own(items, {"a": "m"}, "m", positions=1)
    assert len(out) == 4, "脏数据不能让搜索抛异常"


# ── 模式切换 ──


def test_default_mode_is_boost():
    """默认必须是 boost（用户 2026-09-26 的决定：换加权）。"""
    assert _own_first_mode() == "boost"


def test_mode_switch_via_env():
    import os

    for m, expect in (("split", "split"), ("off", "off"), ("BOOST", "boost"), ("  off  ", "off")):
        os.environ["PANGU_OWN_FIRST_MODE"] = m
        assert _own_first_mode() == expect, m


def test_invalid_mode_falls_back_to_boost():
    import os

    os.environ["PANGU_OWN_FIRST_MODE"] = "乱写"
    assert _own_first_mode() == "boost", "非法值必须回落到安全默认，不能变成静默关闭"


def test_off_mode_returns_items_untouched():
    import os

    os.environ["PANGU_OWN_FIRST_MODE"] = "off"
    items = _items("a", "b", "c")
    assert _apply_own_first(items, {"a": "m", "b": "m"}, "m") is items


def test_off_mode_gives_exact_pre_change_behaviour():
    """off 模式 = 改造前的原始行为，这是回退手段，必须真的等于「什么都不做」。"""
    import os

    os.environ["PANGU_OWN_FIRST_MODE"] = "off"
    items = _items("a", "b", "c", "d", "e")
    owner = {"a": "m", "b": "o", "c": "m", "d": "m", "e": "o"}
    assert [i["id"] for i in _apply_own_first(items, owner, "m")] == ["a", "b", "c", "d", "e"]


def test_handler_dispatches_through_apply_own_first():
    from pangu.server.handlers import memory_ops

    src = inspect.getsource(memory_ops.handle_search_memories)
    assert "_apply_own_first(" in src, "handler 必须走分派函数，否则切模式不起作用"
    assert "_partition_own_first(_items" not in src, "handler 还在绕过分派直接调 split"


def test_handler_uses_rank_boost_not_score_weight():
    """加固：加权必须是位次而非分数。

    引擎两种来源的量纲完全不同（semantic 余弦 0.33~0.76 vs lexical 关键词计数
    engine.py:102，量级个位数到几十）。若有人改成按 score 加权，会随「碰巧命中哪种
    来源」剧烈漂移。本测试从签名上把它挡住。
    """
    from pangu.server.handlers import memory_ops

    sig = inspect.signature(memory_ops._boost_own)
    assert "score" not in " ".join(sig.parameters), "boost 不应接收 score 参数"
    src = inspect.getsource(memory_ops._boost_own)
    assert '"score"' not in src and "'score'" not in src, "boost 里出现 score 即危险"


# ── 超额取 ──


def test_overfetch_is_configured_and_bounded():
    assert _OWN_FIRST_OVERFETCH >= 2, "至少要 2 倍，否则排在 limit 之后的本平台记忆捞不上来"
    assert _OWN_FIRST_MAX_POOL >= 30, "池子上限太小会把超额取压回 limit，等于没超额"


def test_handler_requests_overfetch_and_passes_n_results():
    """handler 必须真的把 n_results 传下去，否则超额取形同虚设。"""
    from pangu.server.handlers import memory_ops

    src = inspect.getsource(memory_ops.handle_search_memories)
    assert "n_results=" in src, "engine.search 的 n_results 没传 —— 超额取没生效"
    assert "_OWN_FIRST_OVERFETCH" in src, "超额取倍数没用上"


def test_handler_accepts_limit_argument():
    from pangu.server.handlers import memory_ops

    src = inspect.getsource(memory_ops.handle_search_memories)
    assert 'arguments.get("limit"' in src, "应支持 limit 参数并在分档后截断"


def test_handler_docstring_mentions_own_first():
    """把意图钉在 docstring 里，避免后人以为那几行是无用排序。"""
    from pangu.server.handlers import memory_ops

    assert "本平台" in inspect.getsource(memory_ops.handle_search_memories)


# ── 对照：确认现网确实没有平台加权（若哪天引擎自己加了，这里会失败并提示可简化）──


def test_total_must_follow_returned_count_not_overfetch_pool():
    """total 必须是**返回条数**，不能是超额取出来的池子大小。

    这条是我自己踩的坑：引擎的 total 是「截断前那一批」的条数，为分档超额取 3 倍后
    它就变成池子大小（limit=30 → total 报 90、实际返回 30）。而 record_search 直接拿
    total 当搜索次数记，放大的数字会污染 pangu_search_stats。
    """
    from pangu.server.handlers import memory_ops

    src = inspect.getsource(memory_ops.handle_search_memories)
    assert 'payload["total"] = len(payload["results"])' in src, "total 必须等于返回条数"
    assert 'max(payload.get("total"' not in src, "total 又开始沿用引擎给的池子大小了"


def test_engine_has_no_platform_boost_yet():
    """记录现状：engine.py 里 source 只是精确过滤，没有平台加权。

    哪天引擎自己实现了平台加权，本实现就可以简化掉 —— 这个测试是提醒，不是阻拦。
    """
    import inspect as _i

    from pangu.search.engine import HybridSearch

    src = _i.getsource(HybridSearch)
    assert "tenant" not in src, "引擎里已出现 tenant 相关逻辑，本 handler 的分档可能已冗余，请复核"
