"""衰减幂等性（2026-09-19 修复回归）。

修复前：`_calculate_decay_v2` 的 base_decay 用距创建的**总年龄**、又乘在
current_score 上 —— 每次跑都重复应用同一段年龄的衰减（不幂等）。实测生产库
171 条里 129 条（75%）已被打到 floor 0.15。
`decay_updated_at`（上次衰减时刻）一直只写不读，正是这里该读的增量基准。

修复后：base_decay 只对"距上次衰减的新增时长"生效 → 连跑两次，第二次不变。
"""

from datetime import datetime, timedelta

from pangu.core.palace import Drawer
from pangu.memory.decay import _calculate_decay_v2, decay_batch

NOW = datetime(2026, 9, 19, 12, 0, 0)


def _aged_drawer(days: float, importance: float = 2.5, decay_score: float | None = None) -> Drawer:
    d = Drawer(id=f"age{days}", content="内容", wing="w", room="r")
    d.created_at = (NOW - timedelta(days=days)).isoformat()
    d.importance = importance
    if decay_score is not None:
        d.metadata["decay_score"] = decay_score
    return d


def test_decay_is_idempotent(monkeypatch):
    """★ 核心修复：连跑两次，第二次必须纹丝不动（此前每次都再乘一遍全年龄衰减）。"""
    import pangu.memory.decay as decay_mod

    # 固定 now，排除夜间因子随时钟漂移的干扰
    class _FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(decay_mod, "datetime", _FixedDT)

    d = _aged_drawer(30)
    s0 = d.metadata.get("decay_score", 1.0)
    decay_batch([d], dry_run=False)
    s1 = d.metadata["decay_score"]
    assert s1 < s0, "首次应衰减（全年龄）"
    assert d.metadata.get("decay_updated_at"), "应记录上次衰减时刻"

    decay_batch([d], dry_run=False)
    s2 = d.metadata["decay_score"]
    assert s2 == s1, f"第二次必须不变（幂等）：{s1} → {s2}"

    decay_batch([d], dry_run=False)
    assert d.metadata["decay_score"] == s1, "第三次同样不变"


def test_first_run_decays_by_full_age():
    """首次衰减（无 decay_updated_at）按全年龄：30 天 ≈ 0.95^(720/168)。"""
    score, action = _calculate_decay_v2(
        current_score=1.0,
        importance=0.5,
        updated_at=(NOW - timedelta(days=30)).isoformat(),
        now=NOW,
        basis_at=None,
    )
    # 精确核对公式：base=0.95^(720/168) × importance(1-0.5*0.4) × night(正午≈1) × touch
    # （idle=720h 不满足 >720 → touch=1.0；若把边界写成 >720 的下一条会差 6%）
    expected = (0.95 ** (720 / 168)) * (1 - 0.5 * 0.4)
    assert abs(score - expected) < 0.005, (score, expected)
    assert action == "decayed"


def test_incremental_basis_changes_decay():
    """同一 current_score：距上次衰减 1 天 vs 30 天，衰减幅度必须不同（增量语义）。"""
    s_fresh, _ = _calculate_decay_v2(
        current_score=0.8,
        importance=0.5,
        updated_at=(NOW - timedelta(days=60)).isoformat(),
        now=NOW,
        basis_at=(NOW - timedelta(days=1)).isoformat(),  # 昨天刚衰减过
    )
    s_stale, _ = _calculate_decay_v2(
        current_score=0.8,
        importance=0.5,
        updated_at=(NOW - timedelta(days=60)).isoformat(),
        now=NOW,
        basis_at=(NOW - timedelta(days=30)).isoformat(),  # 30 天没衰减
    )
    assert s_fresh > s_stale, f"刚衰减过的应几乎不变（{s_fresh}），久未衰减的应更低（{s_stale}）"


def test_floor_respected():
    """极限老记忆不跌破 floor。"""
    score, _ = _calculate_decay_v2(
        current_score=0.2,
        importance=0.0,
        updated_at=(NOW - timedelta(days=3650)).isoformat(),
        now=NOW,
        basis_at=None,
        touch_boost_long=1.0,
        touch_boost_short=1.0,
    )
    assert score >= 0.15, score
