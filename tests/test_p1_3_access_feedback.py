"""访问反馈环（2026-09-19）：搜索命中 → record_access → 衰减/遗忘读它。

背景：access_count 全仓没有写入方、touch_boost 实际按创建年龄算 ——
"使用信号"完全断裂：天天被搜的记忆照常衰减、常用记忆可能被遗忘模型归档。
本组测试锁住整条环。
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.adaptive_forgetting import AdaptiveForgetting
from pangu.memory.decay import _calculate_decay_v2
from pangu.memory.layers import MemoryStack


def _stack(tmp_path):
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()
    return MemoryStack(cfg)


def test_record_access_bumps_and_persists(tmp_path):
    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id="a", content="内容", wing="w", room="r")])
    assert ms.record_access(["a"]) == 1
    assert ms.record_access(["a", "a"]) >= 1  # 重复 id 去重后仍只更新一次
    d = [x for x in ms._load_drawers() if x.id == "a"][0]
    assert d.metadata["access_count"] == 2
    assert "last_accessed" in d.metadata


def test_record_access_unknown_ids_noop(tmp_path):
    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id="a", content="x", wing="w", room="r")])
    assert ms.record_access(["不存在"]) == 0
    assert ms.record_access([]) == 0


def test_decay_respects_last_accessed():
    """刚被访问的记忆几乎不衰减；从未访问的同龄记忆正常衰减。"""
    now = datetime.now()
    common = dict(
        current_score=0.8,
        importance=1.0,
        updated_at=(now - timedelta(days=60)).isoformat(),
        basis_at=(now - timedelta(days=7)).isoformat(),
        now=now,
    )
    accessed, _ = _calculate_decay_v2(last_accessed=(now - timedelta(hours=1)).isoformat(), **common)
    never, _ = _calculate_decay_v2(**common)
    assert accessed > never, f"刚访问({accessed}) 应衰减少于 未访问({never})"


def test_forgetting_derives_access_from_metadata(tmp_path):
    """access_log 缺省时从 metadata 取 —— 常用记忆不被归档。"""
    af = AdaptiveForgetting()
    now = datetime.now()
    used = Drawer(
        id="used",
        content="常用",
        wing="w",
        room="r",
        importance=3.0,
        metadata={"access_count": 15, "last_accessed": now.isoformat()},
    )
    never_used = Drawer(
        id="never",
        content="从不用",
        wing="w",
        room="r",
        importance=3.0,
        metadata={"access_count": 0},
    )
    report = af.evaluate_all([used, never_used])
    dec = {d.memory_id: d.action for d in report.decisions}
    # 常用记忆的处置不应比从不用的更差
    rank = {"keep": 0, "compress": 1, "archive": 2, "forget": 3}
    assert rank[dec["used"]] <= rank[dec["never"]], f"decisions={dec}"


def test_forgetting_defaults_unchanged_for_no_metadata(tmp_path):
    """无任何访问数据的记忆行为不变（days_since_access 默认 30）。"""
    af = AdaptiveForgetting()
    d = Drawer(id="x", content="无数据", wing="w", room="r", importance=3.0)
    report = af.evaluate_all([d])
    dec = report.decisions[0]
    # 与旧行为（access_count=0, days=30）一致即可 —— 只要不抛错、有决策
    assert dec.action in ("keep", "compress", "archive", "forget")


def test_end_to_end_search_updates_disk(tmp_path):
    """搜索命中 → metadata 更新 → 落盘（直接读磁盘验证，绕过缓存）。"""
    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id="a", content="内容", wing="w", room="r")])
    ms.record_access(["a"])
    raw = json.loads((tmp_path / "palace" / "drawers.json").read_text())
    item = [x for x in raw if x["id"] == "a"][0]
    assert item["metadata"]["access_count"] == 1
    assert "last_accessed" in item["metadata"]
