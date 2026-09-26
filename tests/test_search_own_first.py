"""搜索「本平台优先」的稳定分档（2026-09-26）。

用户诉求：搜记忆时先推本平台存的，再推别平台存的 —— 理由是「我这个平台没遇到过的，
别的平台遇到过了，搜到可以拿来鉴别是否有用」。做法是**硬分两档**（非加权）。

本测试锁四件事：
  1. 本平台的确实排前面；
  2. **档内保持原有相关性顺序**（最容易写错的地方：直接 sort 会打乱相关性）；
  3. 调用方没有平台身份（api_key，room 为空串）时**完全不重排** —— 宁可不给优先，
     也不给错优先（云端有 46 条归属为空的记忆，拿空串当平台名会误判）；
  4. 超额取（overfetch）—— engine 内部 `merged[:n_results]` 会截断，只在截断后的
     集合里重排等于半残。
"""

import inspect

import pytest

from pangu.core.palace import Drawer
from pangu.server.handlers.memory_ops import (
    _OWN_FIRST_MAX_POOL,
    _OWN_FIRST_OVERFETCH,
    _partition_own_first,
)


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
