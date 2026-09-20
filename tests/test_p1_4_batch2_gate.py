"""第 2 批（门 + 功能空转）的回归测试（2026-09-20）。

覆盖：
1. `/api/v2/graph` 不再匿名可读（此前无凭据即可拉全图）
2. `verify_credentials` 在 require_auth 且无凭据时拒绝（此前恒 anonymous 放行）
3. `pangu_config_get(key=...)` 对密钥字段脱敏（此前明文返回 LLM/API Key）
4. `/memories/context`、`/memories/export` 不再被 `{memory_id}` 遮蔽
"""

import json

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


def test_graph_route_requires_auth(monkeypatch):
    """`/api/v2/graph` 必须在鉴权网关之内（不再进 _EXEMPT_PREFIXES）。"""
    from pangu.api import server as server_mod

    src_app = server_mod.create_app()
    # 断言路由存在且不在豁免前缀里（豁免表在 _AuthMiddleware 内部，改为
    # 直接断言中间件行为：无凭据访问应 401 而不是 200 + 数据）。
    client = TestClient(src_app, raise_server_exceptions=False)
    r = client.get("/api/v2/graph")
    assert r.status_code == 401, f"graph 无凭据应 401，实得 {r.status_code}: {r.text[:120]}"
