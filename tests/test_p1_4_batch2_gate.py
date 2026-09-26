"""第 2 批（门 + 功能空转）的回归测试（2026-09-20）。

覆盖：
1. `/api/v2/graph` 不再匿名可读（此前无凭据即可拉全图）
2. `verify_credentials` 在 require_auth 且无凭据时拒绝（此前恒 anonymous 放行）
3. `pangu_config_get(key=...)` 对密钥字段脱敏（此前明文返回 LLM/API Key）
4. `/memories/context`、`/memories/export` 不再被 `{memory_id}` 遮蔽
"""

import json

import inspect

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pangu.api.auth import verify_credentials

# ── 2：require_auth 不再被"未配置密钥"短路 ──


def test_require_auth_without_credentials_is_rejected():
    res = verify_credentials(headers={}, api_key="", secret="", require_auth=True)
    assert not res.ok, "require_auth=true 且无任何凭据时应拒绝，而不是匿名放行"
    assert res.method != "anonymous"


def test_require_auth_with_credentials_still_works():
    res = verify_credentials(
        headers={"x-api-key": "K"},
        api_key="K",
        secret="",
        require_auth=True,
    )
    assert res.ok
    assert res.method == "api_key"


def test_no_require_auth_still_allows_anonymous():
    """向后兼容：未启用 require_auth 的本地部署仍可匿名访问（默认行为不变）。"""
    res = verify_credentials(headers={}, api_key="", secret="", require_auth=False)
    assert res.ok
    assert res.method == "anonymous"


def test_require_auth_with_invalid_credentials_is_rejected():
    res = verify_credentials(
        headers={"x-api-key": "wrong"},
        api_key="right",
        secret="",
        require_auth=True,
    )
    assert not res.ok


# ── 3：config_get 密钥脱敏 ──


def test_config_get_redacts_secrets():
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.server.handlers.system import handle_config_get

    class _Server:
        config = PanguConfig.load()

    _Server.config.llm_api_key = "rc-super-secret"
    _Server.config.api_key = "pgk_super_secret"
    _Server.config.jwt_secret = "jwt-super-secret"
    _Server.config.siliconflow_key = "sf-super-secret"

    for field in ("llm_api_key", "api_key", "jwt_secret", "siliconflow_key"):
        out = json.loads(asyncio.run(handle_config_get(_Server(), [], {"key": field})))
        assert out[field] == "****", f"{field} 必须脱敏，实得 {out[field]!r}"


def test_config_get_non_secret_key_still_readable():
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.server.handlers.system import handle_config_get

    class _Server:
        config = PanguConfig.load()

    out = json.loads(asyncio.run(handle_config_get(_Server(), [], {"key": "llm_model"})))
    assert out["llm_model"] == _Server.config.llm_model


def test_config_get_full_dump_excludes_secrets():
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.server.handlers.system import handle_config_get

    class _Server:
        config = PanguConfig.load()

    out = json.loads(asyncio.run(handle_config_get(_Server(), [], {})))
    for field in ("llm_api_key", "api_key", "jwt_secret"):
        assert field not in out


# ── 4：路由遮蔽 ──


def _memory_router_client():
    from pangu.api.routes_memory import router as mem_router

    app = FastAPI()
    app.include_router(mem_router, prefix="/api/v2")
    return TestClient(app, raise_server_exceptions=False)


def test_literal_memory_routes_are_not_shadowed():
    client = _memory_router_client()
    for url in ("/api/v2/memories/context", "/api/v2/memories/export"):
        r = client.get(url)
        assert r.status_code == 200, f"{url} 不应被 {{memory_id}} 遮蔽"
        body = r.json()
        assert body.get("code") == 0, f"{url} 返回业务错误: {body}"
        assert "Memory not found" not in str(body)


def test_dynamic_memory_route_still_registered():
    from pangu.api.routes_memory import router as mem_router

    paths = [r.path for r in mem_router.routes]
    assert "/memories/{memory_id}" in paths
    # 动态路由必须在字面路径之后
    assert paths.index("/memories/{memory_id}") > paths.index("/memories/context")
    assert paths.index("/memories/{memory_id}") > paths.index("/memories/export")


# ── 1：graph 不匿名 ──


def _auth_client(tmp_path, monkeypatch):
    """构造一个**网关鉴权已启用**的 TestClient。

    两个坑，缺一个就会假绿：
    1) 必须 patch 全局单例 `pangu.core.config.config` 的字段，而不是 `PanguConfig.load`
       —— create_app 会用 config.json 的显式字段覆盖单例（见 server.py:116-129）。
    2) 必须把 base_dir 指到 tmp，否则读到的是真实的 ~/.pangu/config.json。
    """
    from fastapi.testclient import TestClient

    from pangu.api import server as srv_mod
    from pangu.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.config, "base_dir", tmp_path, raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_secret_file", str(tmp_path / ".jwt"), raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_default_user", "admin", raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_default_password", "test-pass-123", raising=False)
    monkeypatch.setattr(cfg_mod.config, "jwt_users", {}, raising=False)
    monkeypatch.setattr(cfg_mod.config, "api_key", "TEST_API_KEY_42", raising=False)
    monkeypatch.setattr(cfg_mod.config, "mcp_require_auth", True, raising=False)
    return TestClient(srv_mod.create_app(), raise_server_exceptions=False)


def test_graph_route_requires_credentials(tmp_path, monkeypatch):
    """`/api/v2/graph` 必须凭据才能读。

    2026-09-26 翻转：此前这条测试断言「无凭据应 200」，把漏洞当成了预期行为 ——
    `/api/v2/graph` 一直留在网关的 `_EXEMPT_PREFIXES` 里，而路由自身也没有任何校验，
    两层都不设卡，实测匿名可拉走全量图谱。那同时破坏了用户的两条设定：
    FastAPI 只给仪表盘/管理员，以及平台无法用 token 走 FastAPI 取数据。
    现在它已从豁免前缀摘掉，由网关鉴权兜住。
    """
    r = _auth_client(tmp_path, monkeypatch).get("/api/v2/graph")
    assert r.status_code in (401, 403), f"graph 无凭据必须被拒，实得 {r.status_code}: {r.text[:120]}"


def test_graph_route_rejects_platform_token(tmp_path, monkeypatch):
    """平台 token（pgp_*）同样不得走 FastAPI 取图谱 —— 用户设定的第二条边界。"""
    r = _auth_client(tmp_path, monkeypatch).get(
        "/api/v2/graph", headers={"Authorization": "Bearer pgp_not_a_real_token"}
    )
    assert r.status_code in (401, 403), f"平台 token 必须被拒，实得 {r.status_code}: {r.text[:120]}"


def test_graph_route_accepts_admin_key(tmp_path, monkeypatch):
    """摘掉豁免不能误伤仪表盘：带 admin api_key 时仍须能读。"""
    r = _auth_client(tmp_path, monkeypatch).get("/api/v2/graph", headers={"X-API-Key": "TEST_API_KEY_42"})
    assert r.status_code == 200, f"带 api_key 应放行，实得 {r.status_code}: {r.text[:120]}"


def test_graph_route_absent_from_exempt_prefixes():
    """回归锁定：`/api/v2/graph` 不得再回到网关豁免名单里（它是唯一无自保护的豁免路由）。"""
    from pangu.api import server as server_mod

    src = inspect.getsource(server_mod)
    block = src.split("_EXEMPT_PREFIXES = (", 1)[1].split(")", 1)[0]
    assert '"/api/v2/graph"' not in block, "/api/v2/graph 又被加回豁免前缀了"
    # 同名单里这几个是安全的 —— 它们在路由内自己校验 admin
    for safe in ('"/api/v2/admin"', '"/api/v2/dashboard"'):
        assert safe in block, f"{safe} 应仍在豁免名单（路由内有 admin 自校验）"
