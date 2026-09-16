"""P1-3 租户作用域（MemoryStack 读路径闸门）回归测试。

为什么闸门在这一层：租户隔离原先散在各个 handler 里各写一遍，实测漏了三处
（hybrid_search 完全不过滤、recall 算了 filtered 却没用、后续新增工具默认不带）；
把收口只做在 call_tool 的 drawers 参数上也不够 —— 静态扫描发现 287 个 handler 不使用
该参数，其中 18 个确实碰记忆数据（直接调 server.memory.*：by-id 查、聚合、wake_up）。

所以闸门下沉到 MemoryStack 的读路径（layers._read_drawers + contextvars 作用域）。
本测试锁定四件事：
  1. 读裁剪（get_drawers/count/wake_up/find_*）
  2. by-id 查：不可见等同不存在
  3. 删除越权保护
  4. **写路径绝不能被裁剪** —— _save_drawers 落的是全量快照，一旦写回裁剪后的列表
     就是把别的租户的数据删掉（这是本次改造最危险的一侧）
"""

import pathlib
import tempfile

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.layers import MemoryStack, reset_tenant_scope, set_tenant_scope


def _mk_drawer(did: str, tenant: str, content: str, visibility: str = "") -> Drawer:
    d = Drawer(id=did, content=content, wing="test", room="r")
    md = {"tenant_id": tenant}
    if visibility:
        md["visibility"] = visibility
    d.metadata = md
    return d


@pytest.fixture
def stack():
    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td)
        cfg.palace_path = str(pathlib.Path(td) / "palace.json")
        cfg.db_path = pathlib.Path(td)
        cfg.ensure_dirs()
        st = MemoryStack(cfg)
        st.add_drawers(
            [
                _mk_drawer("dsh1", "dsh", "dsh 专属记忆"),
                _mk_drawer("other1", "other", "other 专属记忆"),
                _mk_drawer("pub1", "other", "公共毕业区记忆", visibility="public"),
            ]
        )
        yield st


def test_full_view_without_scope(stack):
    """无作用域（CLI / 自主维护 / 后台任务）＝全库视角，行为不变。"""
    assert sorted(d.id for d in stack.get_drawers()) == ["dsh1", "other1", "pub1"]
    assert stack.count_drawers() == 3


def test_read_path_is_scoped(stack):
    """作用域内：只见本租户 + public。"""
    token = set_tenant_scope("dsh")
    try:
        assert sorted(d.id for d in stack.get_drawers()) == ["dsh1", "pub1"]
        assert stack.count_drawers() == 2
        assert "other 专属记忆" not in stack.wake_up()
        for d in stack.find_forgotten() + stack.find_compressible():
            assert (d.metadata or {}).get("tenant_id", "") in ("dsh", "") or (d.metadata or {}).get(
                "visibility"
            ) == "public", "聚合类读路径也必须在作用域内"
    finally:
        reset_tenant_scope(token)
    assert stack.count_drawers() == 3, "作用域复原后应回到全库视角"


def test_by_id_gate(stack):
    """不可见的 id 等同不存在 —— by-id 系工具（冲突检查/重要性/supersede/删除/归档）的闸门。"""
    token = set_tenant_scope("dsh")
    try:
        assert stack.get_drawer_by_id("dsh1") is not None
        assert stack.get_drawer_by_id("pub1") is not None
        assert stack.get_drawer_by_id("other1") is None
    finally:
        reset_tenant_scope(token)


def test_remove_drawer_refuses_cross_tenant(stack):
    """越权删除被拒，且磁盘上那条仍在。"""
    token = set_tenant_scope("dsh")
    try:
        assert stack.remove_drawer("other1") is False, "跨租户删除必须被拒"
        assert stack.remove_drawer("dsh1") is True, "本租户删除应正常"
    finally:
        reset_tenant_scope(token)
    ids = sorted(d.id for d in stack.get_drawers())
    assert ids == ["other1", "pub1"], f"写路径应保留其他租户数据，实际 {ids}"


def test_write_path_keeps_whole_store(stack):
    """★ 最危险的一侧：作用域内写入不得抹掉别的租户 —— _save_drawers 用全量快照。"""
    token = set_tenant_scope("dsh")
    try:
        stack.add_drawer(_mk_drawer("dsh2", "dsh", "写入的新记忆"))
    finally:
        reset_tenant_scope(token)
    ids = sorted(d.id for d in stack.get_drawers())
    assert ids == ["dsh1", "dsh2", "other1", "pub1"], f"其他租户数据不得丢失，实际 {ids}"


def test_public_visible_to_all_tenants(stack):
    """public 是跨租户可见的毕业区语义（不是泄漏）。"""
    for tenant in ("dsh", "other"):
        token = set_tenant_scope(tenant)
        try:
            assert stack.get_drawer_by_id("pub1") is not None, f"{tenant} 应能看到 public"
        finally:
            reset_tenant_scope(token)
