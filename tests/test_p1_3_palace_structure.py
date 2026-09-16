"""P1-3 阶段 3：Palace 骨架（翼/房间/隧道）的租户归属与删除授权。

**为什么这里的规则和其它三个域不同**：骨架是"有哪些翼、有哪些房间、房间之间怎么连"的
**共享硬件**（全局唯一的结构表，里面没有记忆内容）。所以：

  * 读**不裁剪** —— 目录信息是共享的（谁都能看到有哪些房间，否则连去哪儿放记忆都不知道）
  * 创建**不限制**（房间名全局唯一），但记下 `created_by`
  * 删除/改名：只有 `created_by` 相同，或 `requester` 为空（＝全库视角：CLI / 后台 / admin）

如果像记忆那样按租户裁剪骨架再写回，会把别的租户建的翼/房间从结构里抹掉 —— 这是本仓
反复强调的"写路径必须用全库快照"原则在结构表上的体现。
"""

import pathlib
import tempfile

import pytest

from pangu.core.palace import Palace
from pangu.memory.layers import reset_tenant_scope, set_tenant_scope


@pytest.fixture
def palace():
    with tempfile.TemporaryDirectory() as td:
        yield Palace(str(pathlib.Path(td) / "palace"))


def test_create_records_creator(palace):
    """创建记下 created_by（handler 传 current_tenant()）。"""
    token = set_tenant_scope("dsh")
    try:
        palace.create_wing("tech", "技术翼", created_by="dsh")
        palace.create_room("tech", "api", "接口", created_by="dsh")
    finally:
        reset_tenant_scope(token)
    assert palace.meta["wing_owners"]["tech"] == "dsh"
    assert palace.meta["room_owners"]["tech"]["api"] == "dsh"


def test_reads_are_not_scoped(palace):
    """读不裁剪：骨架是共享目录，别的租户也能看到有哪些翼/房间。"""
    palace.create_wing("other-wing", created_by="other")
    palace.create_room("other-wing", "r1", created_by="other")
    token = set_tenant_scope("dsh")
    try:
        assert "other-wing" in palace.list_wings()
        assert palace.list_rooms("other-wing")["other-wing"] == ["r1"]
    finally:
        reset_tenant_scope(token)


def test_delete_requires_ownership(palace):
    """★ 删除授权：只能删自己建的；别人的拒绝，管理员（requester 为空）放行。"""
    palace.create_wing("mine", created_by="dsh")
    palace.create_room("mine", "myroom", created_by="dsh")
    palace.create_wing("theirs", created_by="other")
    palace.create_room("theirs", "theirroom", created_by="other")

    assert palace.delete_wing("theirs", requester="dsh") is False, "别租户不得删我的翼"
    assert palace.delete_room("theirs", "theirroom", requester="dsh") is False
    assert "theirs" in palace.list_wings(), "拒绝后结构必须原样保留"

    assert palace.delete_room("mine", "myroom", requester="dsh") is True, "自己的可以删"
    assert palace.delete_wing("mine", requester="dsh") is True

    assert palace.delete_wing("theirs", requester="") is True, "空 requester＝管理员/CLI，放行"


def test_legacy_structure_without_owner_is_deletable(palace):
    """历史结构没有 created_by：不因为"没记归属"就锁死（仍按共享硬件处理）。"""
    palace.create_wing("legacy")  # 不带 created_by
    assert palace.delete_wing("legacy", requester="dsh") is True


def test_tunnel_records_creator(palace):
    t = palace.create_tunnel("a", "b", "r", created_by="dsh")
    assert t["created_by"] == "dsh"
    assert palace.list_tunnels()[0]["created_by"] == "dsh"


def test_write_uses_full_snapshot(palace):
    """★ 作用域内创建不得抹掉别人的结构（写路径永远是全库快照）。"""
    palace.create_wing("theirs", created_by="other")
    palace.create_room("theirs", "r", created_by="other")
    token = set_tenant_scope("dsh")
    try:
        palace.create_wing("mine2", created_by="dsh")
        palace.create_room("mine2", "r2", created_by="dsh")
    finally:
        reset_tenant_scope(token)
    assert "theirs" in palace.list_wings(), "别人的翼不得因我的写入而消失"
    assert palace.list_rooms("theirs")["theirs"] == ["r"]
    assert "mine2" in palace.list_wings()
