"""P1-3 阶段 4：classification（密级）轴 —— 与租户**正交**的第二条可读判据。

规则：可读 = 租户轴成立 ∧ 密级轴成立（clearance >= classification）
  0=public / 1=internal / 2=confidential / 3=secret

密级是**凭据属性**：盘古钥匙记录带 clearance，JWT 用户用 claim（claim 优先）。默认 0
＝失败关闭（需要时由管理员在建钥匙时显式授予）。

全库视角（作用域为空：CLI / 后台维护 / admin）＝系统自身，两条轴都不拦 —— 否则后台
巩固/备份会因为 clearance=0 而漏掉高密级记忆（"系统看不见自己的数据"更危险）。

同时锁定一个类型坑：记忆写入路径曾把 classification 写成字符串（"normal"，存量 13 条），
而 REST/ABAC 侧按 int 读 → ValueError。现在两侧都用 _coerce_classification 归一化。
"""

import pytest

from pangu.core.palace import Drawer
from pangu.keys import KeyManager
from pangu.memory.layers import (
    _coerce_classification,
    current_clearance,
    metadata_readable,
    reset_tenant_scope,
    set_tenant_scope,
)


def test_coerce_classification():
    """字符串/越界/空值都要安全地归一成 0..3。"""
    assert _coerce_classification("normal") == 0, "历史数据的字符串值不能再让 int() 抛异常"
    assert _coerce_classification(None) == 0
    assert _coerce_classification(0) == 0
    assert _coerce_classification(2) == 2
    assert _coerce_classification(99) == 3
    assert _coerce_classification(-5) == 0
    assert _coerce_classification(True) == 0


@pytest.fixture
def stack():
    import pathlib
    import tempfile

    from pangu.core.config import PanguConfig
    from pangu.memory.layers import MemoryStack

    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td)
        cfg.db_path = pathlib.Path(td)
        cfg.palace_path = str(pathlib.Path(td) / "palace")
        cfg.ensure_dirs()
        yield MemoryStack(cfg)


def _drawer(did, tenant, classification):
    d = Drawer(id=did, content=f"{did} 的内容", wing="w", room="r")
    d.metadata = {"tenant_id": tenant, "classification": classification}
    return d


def test_secret_memory_needs_matching_clearance(stack):
    """★ 密级不足 → 即使同租户也读不到。"""
    stack.add_drawers(
        [_drawer("pub", "dsh", 0), _drawer("secret", "dsh", 3)]
    )
    token = set_tenant_scope("dsh", "k", 0)
    try:
        assert stack.get_drawer_by_id("pub") is not None
        assert stack.get_drawer_by_id("secret") is None, "密级 0 不应读到 secret"
        assert [d.id for d in stack.get_drawers()] == ["pub"]
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh", "k", 3)
    try:
        assert current_clearance() == 3
        assert stack.get_drawer_by_id("secret") is not None, "密级 3 应能读到 secret"
    finally:
        reset_tenant_scope(token)


def test_classification_respects_tenancy_first(stack):
    """租户不对，密级再高也读不到（两条轴是合取，不能互相替代）。"""
    stack.add_drawers([_drawer("other-secret", "other", 1)])
    token = set_tenant_scope("dsh", "k", 3)
    try:
        assert stack.get_drawer_by_id("other-secret") is None
    finally:
        reset_tenant_scope(token)


def test_full_view_ignores_both_axes(stack):
    """全库视角＝系统自身：租户与密级都不拦（后台维护不能漏数据）。"""
    stack.add_drawers([_drawer("other-secret", "other", 3)])
    assert stack.get_drawer_by_id("other-secret") is not None
    assert metadata_readable({"tenant_id": "other", "classification": 3}, "", "", 0) is True


def test_key_carries_clearance():
    """钥匙记录带密级，verify 之后要能带出来（MCP/REST 都据此判定）。"""
    km = KeyManager()
    created = km.create(room="room-cls", scope="readonly", clearance=2)
    plain = created.get("key") or ""
    assert plain
    ident = km.verify(plain)
    assert ident and ident["clearance"] == 2
    listed = km.list_keys()
    assert any(k["key_id"] == created["key_id"] and k["clearance"] == 2 for k in listed)


def test_rest_resource_builder_survives_string_classification():
    """REST 资源构造遇到历史字符串值不能抛异常。"""
    from pangu.api.routes_memory import _drawer_to_resource

    d = Drawer(id="x", content="", wing="w", room="r")
    d.metadata = {"tenant_id": "dsh", "classification": "normal"}
    assert _drawer_to_resource(d).classification == 0
