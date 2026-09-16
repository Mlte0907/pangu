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
    stack.add_drawers([_drawer("pub", "dsh", 0), _drawer("secret", "dsh", 3)])
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


def test_write_clamps_classification_to_clearance():
    """★ 写入方标定的密级不得超过自己的 clearance（否则低密级调用方能自锁数据）。"""
    from pangu.memory.layers import clamp_classification

    # 密级 0 的调用方想标 3 → 只能标 0
    token = set_tenant_scope("dsh", "k", 0)
    try:
        assert clamp_classification(3) == 0
        assert clamp_classification(1) == 0
        assert clamp_classification(0) == 0
    finally:
        reset_tenant_scope(token)

    # 密级 3 的调用方可以标到 3
    token = set_tenant_scope("dsh", "k", 3)
    try:
        assert clamp_classification(3) == 3
        assert clamp_classification(2) == 2
        assert clamp_classification("normal") == 0, "非法/字符串值按 0 处理"
    finally:
        reset_tenant_scope(token)


def test_stats_reports_classification_breakdown(stack):
    """管理/租户统计里带密级分布，便于审计"库里有没有高密级数据"。"""
    from pangu.server.handlers.system import collect_stats

    class _Stub:
        """collect_stats 用到 palace / memory / wiki / knowledge_graph 的 stats()。"""

        class memory:
            @staticmethod
            def status():
                return {"total_memories": 0, "by_wing": {}}

            @staticmethod
            def get_drawers():
                return []

        class palace:
            @staticmethod
            def stats():
                return {"wings_count": 0, "rooms_count": 0}

        class wiki:
            @staticmethod
            def stats():
                return {"total_pages": 0}

        class knowledge_graph:
            @staticmethod
            def stats():
                return {"entities": 0, "relations": 0}

    stack.add_drawers([_drawer("a", "dsh", 0), _drawer("b", "dsh", 3)])
    token = set_tenant_scope("dsh", "k", 3)
    try:
        stats = collect_stats(_Stub(), stack.get_drawers())
    finally:
        reset_tenant_scope(token)
    assert stats["classification"] == {"0": 1, "1": 0, "2": 0, "3": 1}


# ── 密级变更通道：pangu_set_classification ──


@pytest.fixture
def srv(tmp_path):
    """最小 server 桩 —— handler 只用到 server.memory 与 server.config。"""
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


def _call(srv, **args):
    import asyncio
    import json

    from pangu.server.handlers.memory_ops import handle_set_classification

    return json.loads(asyncio.run(handle_set_classification(srv, [], args)))


def _cls_of(srv, mid, tenant="dsh", clearance=3):
    tok = set_tenant_scope(tenant, "k", clearance)
    try:
        d = srv.memory.get_drawer_by_id(mid)
        return _coerce_classification((d.metadata or {}).get("classification")) if d else None
    finally:
        reset_tenant_scope(tok)


def test_declassify_own_memory(srv):
    """本工具存在的理由：所有者把自己的高密级记忆解密级。"""
    srv.memory.add_drawers([_drawer("m1", "dsh", 3)])
    tok = set_tenant_scope("dsh", "k3", 3)
    try:
        r = _call(srv, memory_id="m1", classification=0)
    finally:
        reset_tenant_scope(tok)
    assert r.get("status") == "updated", r
    assert r["previous"] == 3 and r["classification"] == 0
    assert r["direction"] == "declassify", r
    assert _cls_of(srv, "m1") == 0, "必须真的落库，不能只在返回值里说改了"


def test_low_clearance_cannot_declassify_what_it_cannot_see(srv):
    """低密级调用方够不着高密级记忆 —— 不能解密级自己看不见的东西。"""
    srv.memory.add_drawers([_drawer("m1", "dsh", 3)])
    tok = set_tenant_scope("dsh", "k0", 0)  # 同租户，但 clearance=0
    try:
        r = _call(srv, memory_id="m1", classification=0)
    finally:
        reset_tenant_scope(tok)
    assert r.get("code") == 2001, r  # 记忆不存在（不泄露存在性）
    assert _cls_of(srv, "m1") == 3, "密级必须纹丝不动"


def test_cannot_change_others_memory(srv):
    """A 能读到 B 的 public 记忆，但不能改它的密级 —— 可读 ≠ 可改。"""
    d = _drawer("b1", "other", 3)
    d.metadata["visibility"] = "public"
    srv.memory.add_drawers([d])
    tok = set_tenant_scope("dsh", "k3", 3)
    try:
        assert srv.memory.get_drawer_by_id("b1") is not None, "public 记忆本应可读"
        r = _call(srv, memory_id="b1", classification=0)
    finally:
        reset_tenant_scope(tok)
    assert r.get("code") == 2003, r
    assert _cls_of(srv, "b1", tenant="other") == 3, "别人的密级不能被改"


def test_escalate_clamped_to_caller_clearance(srv):
    """升级方向：钳到自身 clearance（与写入同策略，不能一步标成绝密）。"""
    srv.memory.add_drawers([_drawer("m1", "dsh", 0)])
    tok = set_tenant_scope("dsh", "k1", 1)
    try:
        r = _call(srv, memory_id="m1", classification=3)
    finally:
        reset_tenant_scope(tok)
    assert r["classification"] == 1 and r["clamped"] is True, r
    assert _cls_of(srv, "m1") == 1


def test_system_view_can_declassify(srv):
    """全库视角（CLI/后台/admin）不受限 —— 后台维护需要这条通道。"""
    srv.memory.add_drawers([_drawer("m1", "dsh", 3)])
    r = _call(srv, memory_id="m1", classification=0)  # 无作用域
    assert r.get("status") == "updated", r
    assert _cls_of(srv, "m1") == 0
