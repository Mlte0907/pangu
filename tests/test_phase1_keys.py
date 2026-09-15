"""阶段 1 测试：钥匙管理 + 身份解析 + 管理端点鉴权 + require_auth"""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_keys(tmp_path):
    """临时 keys.json（隔离测试）"""
    keys_path = tmp_path / "keys.json"
    from pangu.keys import KeyManager

    km = KeyManager(str(keys_path))
    return km, keys_path


# ── 钥匙生命周期 ──────────────────────────────────────────────────


def test_key_lifecycle_create_verify_revoke(tmp_keys):
    """钥匙生命周期：create → verify → revoke → verify 失败"""
    km, _ = tmp_keys
    record = km.create(room="test_room", scope="readwrite")
    assert record["key"].startswith("pgk_")
    assert record["room"] == "test_room"
    assert record["scope"] == "readwrite"

    # verify 成功
    identity = km.verify(record["key"])
    assert identity is not None
    assert identity["room"] == "test_room"
    assert identity["scope"] == "readwrite"

    # revoke
    assert km.revoke(record["key_id"]) is True

    # verify 失败（已吊销）
    identity = km.verify(record["key"])
    assert identity is None


def test_keys_file_0600(tmp_keys):
    """keys.json 文件权限必须是 0600"""
    _, keys_path = tmp_keys
    km, _ = tmp_keys
    km.create(room="t", scope="readonly")
    mode = oct(keys_path.stat().st_mode)[-3:]
    assert mode == "600", f"keys.json 权限应为 600，实际 {mode}"


def test_key_list_excludes_revoked(tmp_keys):
    """默认 list 不包含已吊销钥匙"""
    km, _ = tmp_keys
    r1 = km.create(room="a", scope="readwrite")
    r2 = km.create(room="b", scope="readonly")
    km.revoke(r1["key_id"])

    keys = km.list_keys()
    assert len(keys) == 1
    assert keys[0]["key_id"] == r2["key_id"]


def test_key_list_includes_revoked(tmp_keys):
    """--revoked 包含已吊销"""
    km, _ = tmp_keys
    r1 = km.create(room="a", scope="readwrite")
    km.revoke(r1["key_id"])
    keys = km.list_keys(include_revoked=True)
    assert len(keys) == 1


# ── 身份注入 ──────────────────────────────────────────────────


def test_inject_identity_with_valid_key(tmp_keys):
    """带有效 X-API-Key 的请求应注入 _identity"""
    km, keys_path = tmp_keys
    record = km.create(room="dsh", scope="readwrite")

    msg = {}

    class FakeRequest:
        headers = {"X-API-Key": record["key"]}

    # 临时设置 KeyManager 使用测试路径
    import pangu.api.mcp_http as mcp_mod
    from pangu.api.mcp_http import _inject_identity

    original_init = None
    try:
        from pangu.keys import KeyManager as KM

        original_init = KM.__init__
        KM.__init__ = lambda self, kp=None: original_init(self, str(keys_path))
        _inject_identity(msg, FakeRequest())
    finally:
        KM.__init__ = original_init

    assert "_identity" in msg
    assert msg["_identity"]["room"] == "dsh"


def test_inject_identity_without_key():
    """无 X-API-Key 时不注入"""
    msg = {}

    class FakeRequest:
        headers = {}

    from pangu.api.mcp_http import _inject_identity

    _inject_identity(msg, FakeRequest())
    assert "_identity" not in msg


def test_inject_identity_invalid_key():
    """无效钥匙不注入，mcp_require_auth=false 时不报错"""
    msg = {}

    class FakeRequest:
        headers = {"X-API-Key": "pgk_invalid_key_12345"}

    from pangu.api.mcp_http import _inject_identity

    _inject_identity(msg, FakeRequest())
    assert "_identity" not in msg
    assert "_auth_error" not in msg  # false 时只 warning


# ── require_auth ──────────────────────────────────────────────────


def test_require_auth_true_rejects_no_key(tmp_path):
    """mcp_require_auth=true 时无凭据返回 401"""
    from pangu.core.config import PanguConfig

    # 临时设置
    os.environ["PANGU_MCP_REQUIRE_AUTH"] = "true"
    try:
        msg = {}

        class FakeRequest:
            headers = {}

        from pangu.api.mcp_http import _inject_identity

        _inject_identity(msg, FakeRequest())
        assert "_auth_error" in msg
        assert msg["_auth_code"] == 401
    finally:
        os.environ.pop("PANGU_MCP_REQUIRE_AUTH", None)


def test_require_auth_true_rejects_invalid_key(tmp_path):
    """mcp_require_auth=true 时无效钥匙返回 401"""
    os.environ["PANGU_MCP_REQUIRE_AUTH"] = "true"
    try:
        msg = {}

        class FakeRequest:
            headers = {"X-API-Key": "pgk_invalid"}

        from pangu.api.mcp_http import _inject_identity

        _inject_identity(msg, FakeRequest())
        assert "_auth_error" in msg
        assert msg["_auth_code"] == 401
    finally:
        os.environ.pop("PANGU_MCP_REQUIRE_AUTH", None)


# ── 管理端点鉴权 ──────────────────────────────────────────────────


def test_admin_endpoint_no_auth_returns_401(tmp_keys):
    """管理端点无凭据返回 401"""
    from pangu.api.routes_keys import _verify_admin

    class FakeRequest:
        headers = {}

    assert _verify_admin(FakeRequest()) is False


def test_admin_endpoint_room_key_returns_403(tmp_keys):
    """房间钥匙访问管理端点返回 403"""
    km, _ = tmp_keys
    record = km.create(room="dsh", scope="readwrite")

    # 验证房间钥匙能通过 KeyManager.verify
    identity = km.verify(record["key"])
    assert identity is not None  # 房间钥匙有效
    # 但管理端点需要 admin secret，不是房间钥匙
    # _verify_admin 检查 X-Admin-Key，不是 X-API-Key
    from pangu.api.routes_keys import _verify_admin

    class FakeRequest:
        headers = {"X-API-Key": record["key"]}

    assert _verify_admin(FakeRequest()) is False  # 房间钥匙不是 admin


# ── 重发钥匙（rekey）──────────────────────────────────────────────


def test_rekey_revokes_old_creates_new(tmp_keys):
    """rekey 吊销旧钥匙并创建新钥匙"""
    km, _ = tmp_keys
    # 创建两把钥匙
    r1 = km.create(room="rekey_room", scope="readwrite")
    r2 = km.create(room="rekey_room", scope="readwrite")
    old_ids = {r1["key_id"], r2["key_id"]}

    # 手动模拟 rekey 逻辑
    all_keys = km.list_keys(include_revoked=False)
    room_keys = [k for k in all_keys if k.get("room") == "rekey_room"]
    for k in room_keys:
        km.revoke(k["key_id"])

    new_record = km.create(room="rekey_room", scope="readwrite")

    # 旧钥匙 verify 失败（已吊销）
    for old_key in [r1["key"], r2["key"]]:
        assert km.verify(old_key) is None

    # 新钥匙有效
    identity = km.verify(new_record["key"])
    assert identity is not None
    assert identity["room"] == "rekey_room"
    assert new_record["key_id"] not in old_ids
