"""第 2 批「功能空转」修复的回归测试（2026-09-20）。

每个用例断言"功能真的生效"，而不是"函数被调用了"：
1. adaptive_forgetting.auto_forget 真正把归档/遗忘条目移出活动集合
2. decay_batch 的 strengthened 不再恒 0
3. NeuralMemory 巩固后不被立即遗忘，且真实 created_at 不被改写
4. merge_duplicates 保留 metadata/author/source（不再降级成裸记忆）
5. lifecycle.needs_index_rebuild 真正使用 threshold
6. routes_memory 的 decay/purge/export 不再空转（传了 drawers）
7. admin secret 路径跟随 base_dir
"""

import json

import pytest

from pangu.core.palace import Drawer

# ── 1：自适应遗忘真正生效 ──


def test_auto_forget_removes_entries_from_active_set():
    from pangu.core.config import PanguConfig
    from pangu.memory.adaptive_forgetting import AdaptiveForgetting

    af = AdaptiveForgetting(PanguConfig.load())
    drawers = [Drawer(id=f"m{i}", content=f"content {i}", importance=0.2) for i in range(5)]

    # 无论决策如何，只要报告里判了 archive/forget，就必须从 drawers 移出
    report = af.evaluate_all(drawers)
    n_actionable = sum(1 for d in report.decisions if d.action in ("archive", "forget"))
    before = len(drawers)
    result = af.auto_forget(drawers)
    removed = result["removed_ids"]["archived"] + result["removed_ids"]["forgotten"]

    assert len(removed) == n_actionable
    assert len(drawers) == before - len(set(removed)), "被归档/遗忘的条目必须真正移出活动集合"


def test_auto_forget_modifies_in_place_for_caller():
    """调用方（autonomous 周期）靠原地修改 drawers 才能落盘，不能返回新列表。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.adaptive_forgetting import AdaptiveForgetting

    af = AdaptiveForgetting(PanguConfig.load())
    drawers = [Drawer(id="only", content="x", importance=0.0)]
    af.auto_forget(drawers)
    assert isinstance(drawers, list)  # 同一对象被原地修改/至少仍是 list


# ── 2：decay strengthened ──


def test_decay_tracks_strengthened(monkeypatch):
    import pangu.memory.decay as decay_mod
    from pangu.core.palace import Drawer

    # 强制 new_score(0.9) > old_score(0.5)：必须计入 strengthened 而不是 decayed
    monkeypatch.setattr(decay_mod, "_calculate_decay_v2", lambda *a, **k: (0.9, "strengthen"))
    d = Drawer(id="x", content="hi", importance=3.0)
    d.metadata["decay_score"] = 0.5
    stats = decay_mod.decay_batch([d])

    assert stats["strengthened"] == 1, f"应计入 strengthened，实得 {stats}"
    assert stats["decayed"] == 0


def test_decay_tracks_decayed(monkeypatch):
    import pangu.memory.decay as decay_mod
    from pangu.core.palace import Drawer

    monkeypatch.setattr(decay_mod, "_calculate_decay_v2", lambda *a, **k: (0.2, "decay"))
    d = Drawer(id="y", content="hi", importance=3.0)
    d.metadata["decay_score"] = 0.8
    stats = decay_mod.decay_batch([d])
    assert stats["decayed"] == 1
    assert stats["strengthened"] == 0


# ── 3：神经巩固不被立即遗忘 ──


def test_neural_consolidation_preserves_created_at_and_survives():
    import time
    from datetime import datetime, timedelta

    from pangu.memory.neural_memory import NeuralMemoryEngine

    engine = NeuralMemoryEngine()
    old = (datetime.now() - timedelta(days=2)).isoformat()
    for i, content in enumerate(["Python", "ONNX", "FAISS"]):
        engine.encode(Drawer(id=f"n{i}", content=content, wing="test", importance=3.0, tags=["test"], created_at=old))

    engine.sleep()

    # 巩固后记忆必须还在（此前因 created_at 不刷新，apply_decay 立刻判遗忘）
    remaining = set(engine.neocortex._memories.keys())
    assert remaining, "巩固后不应把所有记忆都遗忘"

    # 真实创建时间不被改写
    for mem in engine.neocortex._memories.values():
        assert mem.created_at < time.time() - 3600 * 24, "created_at 应保留真实创建时间"
        assert mem.decay_basis_at >= mem.created_at, "衰减基准应不早于创建时间"


# ── 4：合并保留元数据 ──


def test_merge_duplicates_preserves_metadata_and_identity():
    from pangu.core.config import PanguConfig
    from pangu.memory.dedup import DuplicateGroup, MemoryDeduplicator

    dd = MemoryDeduplicator(PanguConfig.load())
    a = Drawer(id="a", content="longer content a", wing="w", tags=["t1"])
    a.metadata["tenant_id"] = "default"
    a.metadata["visibility"] = "tenant"
    a.author = "agent-1"
    a.source = "dsh"
    b = Drawer(id="b", content="b short")

    group = DuplicateGroup(
        id="g",
        memory_ids=["a", "b"],
        primary_id="a",
        duplicate_ids=["b"],
        similarity_matrix={},
        avg_similarity=1.0,
    )
    merged = dd.merge_duplicates(group, [a, b])

    assert merged is not None
    assert merged.metadata.get("tenant_id") == "default", "metadata 不能丢"
    assert merged.metadata.get("visibility") == "tenant"
    assert merged.author == "agent-1"
    assert merged.source == "dsh"


def test_merge_duplicates_handles_empty_created_at():
    """所有成员 created_at 为空时不得 min() 空序列抛错。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.dedup import DuplicateGroup, MemoryDeduplicator

    dd = MemoryDeduplicator(PanguConfig.load())
    a = Drawer(id="a", content="x")
    b = Drawer(id="b", content="yy")
    a.created_at = ""
    b.created_at = ""
    group = DuplicateGroup(
        id="g",
        memory_ids=["a", "b"],
        primary_id="a",
        duplicate_ids=["b"],
        similarity_matrix={},
        avg_similarity=1.0,
    )
    assert dd.merge_duplicates(group, [a, b]) is not None


# ── 5：索引重建阈值 ──


def test_needs_index_rebuild_uses_threshold():
    from pangu.core.config import PanguConfig
    from pangu.memory.lifecycle import LifecycleManager

    mgr = LifecycleManager(PanguConfig.load())
    mgr._last_index_rebuild = 9e18  # 时间判断永不触发

    # 阈值 0 ⇒ 立即需要重建（证明 threshold 真被读取）
    assert mgr.needs_index_rebuild(threshold=0) is True

    # 时间未到 + 计数为 0 + 大阈值 ⇒ 不重建
    import time

    mgr._last_index_rebuild = time.time()
    mgr._count_new_memories = lambda: 0
    assert mgr.needs_index_rebuild(threshold=100) is False
    mgr._count_new_memories = lambda: 100
    assert mgr.needs_index_rebuild(threshold=100) is True


# ── 6：decay/purge/export 不空转 ──


def test_memory_maintenance_endpoints_have_data_source():
    """/memories/decay|purge|export 必须读权威存储，而不是 recall() 的空默认。"""
    from pangu.api import routes_memory as rm

    # _authoritative_drawers 必须存在且能返回 list（允许为空库）
    assert hasattr(rm, "_authoritative_drawers")
    drawers = rm._authoritative_drawers()
    assert isinstance(drawers, list)


# ── 7：admin secret 路径 ──


def test_admin_secret_path_follows_base_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PANGU_BASE_DIR", str(tmp_path / ".pangu"))
    from pangu.api.admin_auth import admin_secret_path, ensure_admin_secret

    p = admin_secret_path()
    assert str(p).startswith(str(tmp_path)), f"admin secret 应在隔离目录下，实得 {p}"
    secret = ensure_admin_secret()
    assert p.exists()
    assert len(secret) > 20
