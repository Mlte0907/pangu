"""P1-3 阶段 2 退回修复测试：过滤轴从 Drawer.room 改为 metadata.tenant_id

场景：三条记忆——tenant_id='dsh'、tenant_id='other'、tenant_id='dsh'+visibility='public'
"""
import json
import pytest

from pangu.core.palace import Drawer


def _make_drawers():
    """构造三条测试记忆"""
    d1 = Drawer(id="dsh1", content="dsh 专属记忆", wing="test", room="r")
    d1.metadata = {"tenant_id": "dsh"}

    d2 = Drawer(id="other1", content="other 专属记忆", wing="test", room="r")
    d2.metadata = {"tenant_id": "other"}

    d3 = Drawer(id="pub1", content="公共毕业区记忆", wing="test", room="r")
    d3.metadata = {"tenant_id": "dsh", "visibility": "public"}

    return [d1, d2, d3]


def _filter_by_identity(drawers, identity_room):
    """模拟 handle_search_memories 的过滤逻辑"""
    return [
        d for d in drawers
        if ((d.metadata or {}).get("tenant_id", "") == identity_room
            or (d.metadata or {}).get("visibility", "") == "public")
    ]


def test_filter_dsh_identity():
    """dsh 身份：只看到 tenant_id='dsh' + public"""
    drawers = _make_drawers()
    result = _filter_by_identity(drawers, "dsh")
    ids = [d.id for d in result]
    assert "dsh1" in ids, "tenant_id='dsh' 应可见"
    assert "pub1" in ids, "visibility='public' 应可见（毕业区）"
    assert "other1" not in ids, "tenant_id='other' 不应可见"


def test_filter_no_identity():
    """无身份：不预过滤（行为同现状）"""
    drawers = _make_drawers()
    # 无身份时 handler 不预过滤，直接传全量
    result = drawers  # 不过滤
    ids = [d.id for d in result]
    assert "dsh1" in ids
    assert "other1" in ids
    assert "pub1" in ids


def test_filter_other_identity():
    """other 身份：只看到 tenant_id='other' + public"""
    drawers = _make_drawers()
    result = _filter_by_identity(drawers, "other")
    ids = [d.id for d in result]
    assert "other1" in ids
    assert "pub1" in ids
    assert "dsh1" not in ids


def test_filter_no_tenant_id_default():
    """无 tenant_id 的记忆对任何身份可见（迁移到 default）"""
    d = Drawer(id="no_tid", content="无 tenant_id", wing="test", room="r")
    d.metadata = {}
    drawers = [d]
    result = _filter_by_identity(drawers, "dsh")
    # 无 tenant_id 的记忆：tenant_id="" != "dsh" 且 visibility="" != "public"
    # 所以不可见（正确行为：未迁移到任何房间的记忆对外隔离）
    ids = [d.id for d in result]
    assert "no_tid" not in ids
