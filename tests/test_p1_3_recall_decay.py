"""recall 排序并入衰减分（2026-09-19）。

背景：L2.retrieve 此前只按静态 importance 排序，无视 metadata.decay_score ——
库里 101/165 条已低于遗忘线（中位数 0.21），陈旧记忆照样霸占召回前排，污染
插件注入的上下文。现用与 retrieval.py 一致的合成口径：(imp/5)*0.4 + decay*0.6。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pangu.core.palace import Drawer
from pangu.memory.layers import Layer2


def _l2(tmp_path):
    p = tmp_path / "palace"
    p.mkdir(parents=True, exist_ok=True)
    return Layer2(str(p))


def test_decayed_high_importance_loses_to_fresh(tmp_path):
    """importance 5.0 但衰减 0.1 的陈旧记忆，应排在 importance 3.0 新鲜记忆之后。"""
    l2 = _l2(tmp_path)
    stale = Drawer(
        id="old",
        content="陈旧但重要分高",
        wing="w",
        room="r",
        importance=5.0,
        metadata={"decay_score": 0.1},
    )
    fresh = Drawer(
        id="new",
        content="新鲜但重要分低",
        wing="w",
        room="r",
        importance=3.0,
        metadata={"decay_score": 1.0},
    )
    out = l2.retrieve([stale, fresh], wing="w", room="r", n_results=10)
    assert out.index("新鲜但重要分低") < out.index("陈旧但重要分高")


def test_missing_decay_treated_as_fresh(tmp_path):
    """没有 decay_score 的老数据按 1.0 处理，不被惩罚。"""
    l2 = _l2(tmp_path)
    no_decay = Drawer(id="a", content="无衰减数据", wing="w", room="r", importance=3.0)
    decayed = Drawer(
        id="b",
        content="已衰减",
        wing="w",
        room="r",
        importance=3.0,
        metadata={"decay_score": 0.2},
    )
    out = l2.retrieve([no_decay, decayed], wing="w", room="r", n_results=10)
    assert out.index("无衰减数据") < out.index("已衰减")


def test_same_decay_importance_still_wins(tmp_path):
    """衰减相同时 importance 高者在前（不改变原有相对序）。"""
    l2 = _l2(tmp_path)
    hi = Drawer(id="hi", content="重要", wing="w", room="r", importance=5.0, metadata={"decay_score": 0.8})
    lo = Drawer(id="lo", content="次要", wing="w", room="r", importance=2.0, metadata={"decay_score": 0.8})
    out = l2.retrieve([lo, hi], wing="w", room="r", n_results=10)
    assert out.index("重要") < out.index("次要")


def test_rank_formula_matches_retrieval_convention(tmp_path):
    """权重口径与 retrieval.py 一致：(imp/5)*0.4 + decay*0.6。"""
    l2 = _l2(tmp_path)
    a = Drawer(id="a", content="A", wing="w", room="r", importance=5.0, metadata={"decay_score": 0.5})
    b = Drawer(id="b", content="B", wing="w", room="r", importance=0.0, metadata={"decay_score": 0.8})
    # a: 1.0*0.4 + 0.5*0.6 = 0.70 ; b: 0 + 0.8*0.6 = 0.48 → a 在前
    out = l2.retrieve([b, a], wing="w", room="r", n_results=10)
    assert out.index("A") < out.index("B")
