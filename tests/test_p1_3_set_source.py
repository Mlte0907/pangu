"""pangu_set_source：补来源指针 —— 解「缺来源」的准入死结。

背景（面板实测）：57 条待验证里 16 条缺来源指针。毕业判据
（_admission_gate 四问 + retrieval.py 毕业通路）要求
    has_source ∧ has_positive_feedback
同时成立 —— 缺来源的记忆即使被召回验证过也**永远毕不了业**（死结，
把"待验证"数字永远占住）。本工具补上来源并重新过准入门。

权限模型（与 pangu_set_classification 一致）：读得到 / 是自己的 / 只补不删。
"""

import asyncio
import json

import pytest

from pangu.core.palace import Drawer
from pangu.memory.layers import reset_tenant_scope, set_tenant_scope


@pytest.fixture
def srv(tmp_path):
    """最小 server 桩 —— handler 只用 server.memory 与 server.config。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.layers import MemoryStack

    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()

    class _S:
        pass

    s = _S()
    s.memory = MemoryStack(cfg)
    s.config = cfg
    return s


def _drawer(
    did,
    tenant="dsh",
    cls=0,
    source_file=None,
    source_session=None,
    last_feedback=None,
    admission="pending_review",
):
    d = Drawer(id=did, content=f"{did} 的内容", wing="w", room="r")
    d.metadata = {"tenant_id": tenant, "classification": cls, "admission": admission}
    if source_session:
        d.metadata["source_session"] = source_session
    if last_feedback:
        d.metadata["last_feedback"] = last_feedback
    if source_file:
        d.source_file = source_file
    return d


def _call(srv, **args):
    from pangu.server.handlers.memory_ops import handle_set_source

    return json.loads(asyncio.run(handle_set_source(srv, [], args)))


def _get(srv, mid, tenant="dsh", clearance=3):
    tok = set_tenant_scope(tenant, "k", clearance)
    try:
        return srv.memory.get_drawer_by_id(mid)
    finally:
        reset_tenant_scope(tok)


# ── 核心：补来源 + 已有反馈 → 直接毕业 ──


def test_fill_source_then_graduate(srv):
    """★ 本工具存在的理由：缺来源的死结 + 已被召回验证过 → 补上即毕业。"""
    srv.memory.add_drawers([_drawer("m1", last_feedback="recall_success")])  # 有反馈、缺来源
    r = _call(srv, memory_id="m1", source_session="session-abc")
    assert r["updated"] == 1 and r["graduated"] == 1, r
    d = _get(srv, "m1")
    assert d.metadata.get("source_session") == "session-abc"
    assert d.metadata.get("admission") == "graduated", "满足四问必须毕业"
    assert d.metadata.get("visibility") == "public", "毕业 → 进全平台只读区"
    assert d.metadata.get("graduated_at")


def test_fill_source_without_feedback_stays_pending(srv):
    """补了来源但还没被召回验证 → 保持 pending_review（等使用信号）。"""
    srv.memory.add_drawers([_drawer("m2")])  # 无反馈
    r = _call(srv, memory_id="m2", source_file="/tmp/x.log")
    assert r["updated"] == 1 and r["graduated"] == 0, r
    d = _get(srv, "m2")
    assert d.source_file == "/tmp/x.log"
    assert d.metadata.get("admission") == "pending_review"


def test_does_not_overwrite_existing_source(srv):
    """只补不删：已有来源不覆盖（防止借工具伪造来历）。"""
    srv.memory.add_drawers([_drawer("m3", source_file="/orig.log", last_feedback="verified")])
    r = _call(srv, memory_id="m3", source_file="/forged.log")
    res = r["results"][0]
    assert res["status"] == "unchanged" and "source_file" in res["skipped"], r
    assert _get(srv, "m3").source_file == "/orig.log", "原来源必须纹丝不动"


def test_low_clearance_cannot_touch_invisible(srv):
    """低密级读不到 → 不存在（不泄露存在性）→ 改不了。"""
    srv.memory.add_drawers([_drawer("m4", cls=3)])
    tok = set_tenant_scope("dsh", "k0", 0)
    try:
        r = _call(srv, memory_id="m4", source_session="s")
    finally:
        reset_tenant_scope(tok)
    assert r["results"][0].get("code") == 2001, r
    assert _get(srv, "m4").metadata.get("source_session") is None


def test_cannot_change_others(srv):
    """别人的记忆（public 可见）也不能补来源 —— 可读 ≠ 可改。"""
    d = _drawer("b1", tenant="other")
    d.metadata["visibility"] = "public"
    srv.memory.add_drawers([d])
    tok = set_tenant_scope("dsh", "k", 3)
    try:
        assert srv.memory.get_drawer_by_id("b1") is not None, "public 本应可读"
        r = _call(srv, memory_id="b1", source_session="s")
    finally:
        reset_tenant_scope(tok)
    assert r["results"][0].get("code") == 2003, r
    assert _get(srv, "b1", tenant="other").metadata.get("source_session") is None


def test_batch_fill(srv):
    """批量：一次给多条补；不可见的按条报错、可见的正常补。"""
    srv.memory.add_drawers(
        [
            _drawer("b_a", last_feedback="recall_success"),
            _drawer("b_b"),
        ]
    )
    r = _call(srv, memory_ids=["b_a", "b_b", "missing"], source_session="session-batch")
    assert r["total"] == 3 and r["updated"] == 2, r
    assert r["graduated"] == 1, "只有带反馈的那条毕业"
    assert _get(srv, "b_a").metadata.get("admission") == "graduated"
    assert _get(srv, "b_b").metadata.get("admission") == "pending_review"
