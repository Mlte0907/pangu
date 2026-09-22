"""REST v2 契约回归（2026-09-22 mimo-desktop-agent 接入实测报告）。

把报告暴露的三个行为面锁进测试：

1. importance 标度：PUT 与 POST 同契约（输入 0–1、服务端 ×5 存 0–5）。
   修复前 PUT 直存 0–1，同一字段两条写路径分裂（POST 0.5→2.5、PUT 0.5→0.5）。
2. 单条 GET/PUT 默认剔除 metadata.embedding（数百维内部检索向量不随响应
   外带），`?include_embedding=true` 才取回。
3. search 分层与过滤：本平台租户命中（own）排前、其他平台（recommend）
   随后，每条带 scope/tenant_id；支持 offset/tag/owner_id/scope；空 q 与
   缺省 q 同为分层 top-N（不再 422/0 条分裂）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pangu.core.config import PanguConfig
from tests.test_p0_0_authoritative_path import _write_drawers_raw, clean_home  # noqa: F401 — fixture 经模块命名空间解析

OWN = "tc-platform"
OTHER = "tc-other"


def _client(tenant: str = OWN) -> TestClient:
    """挂 memories 路由 + 注入已认证的平台身份（等价 AuthMiddleware 产物）。

    内置 ABAC 策略只在真实 server 启动时注册（server.py），bare 测试 App
    不注册会在 authorize 处 403 "ABAC not initialized"；注册同名覆盖、幂等。
    """
    from pangu.api.abac import register_builtin_policies
    from pangu.api.routes_memory import router

    register_builtin_policies()
    app = FastAPI()

    class _FakeAuthMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["auth"] = {
                    "user_id": "tc-user",
                    "method": "platform_token",
                    "tenant": tenant,
                }
            await self.app(scope, receive, send)

    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(router, prefix="/api/v2")
    return TestClient(app)


def _drawer(i, content, tenant, tags=None, owner=None, created=None, importance=None, embedding=None):
    meta = {"tenant_id": tenant}
    if owner:
        meta["owner_id"] = owner
    if embedding is not None:
        meta["embedding"] = embedding
    item = {
        "id": f"tcr{i}",
        "content": content,
        "wing": "tcw",
        "room": "tcr",
        "tags": tags or [],
        "metadata": meta,
    }
    if created:
        item["created_at"] = created
    if importance is not None:
        item["importance"] = importance
    return item


# ── 1. importance 标度：PUT 对齐 POST ─────────────────────────


class TestImportanceScale:
    def test_put_scales_input_to_storage_range(self, clean_home):
        """PUT 输入 0–1 → 存 0–5（与 POST 同标度）；0–5 值回填被 422 拒。"""
        cfg = PanguConfig.load()
        _write_drawers_raw(
            cfg.authoritative_drawers_path,
            [_drawer(0, "tc-scale", OWN, importance=2.5)],
        )
        client = _client()

        r = client.put("/api/v2/memories/tcr0", json={"importance": 0.4})
        assert r.status_code == 200

        g = client.get("/api/v2/memories/tcr0").json()["data"]
        assert g["importance"] == pytest.approx(2.0), "PUT 应 ×5 与 POST 同标度（0.4 → 2.0）"

        # GET 读回的 0–5 值直接回填：仍是 422（输入契约 0–1，需除以 5）
        p = client.put("/api/v2/memories/tcr0", json={"importance": 2.0})
        assert p.status_code == 422


# ── 2. GET/PUT 不外带 embedding ──────────────────────────────


class TestEmbeddingNotExposedByDefault:
    def test_get_strips_unless_explicitly_requested(self, clean_home):
        cfg = PanguConfig.load()
        _write_drawers_raw(
            cfg.authoritative_drawers_path,
            [_drawer(1, "tc-embed", OWN, embedding=[0.1, 0.2])],
        )
        client = _client()

        g = client.get("/api/v2/memories/tcr1").json()["data"]
        assert "embedding" not in g["metadata"], "默认响应不得携带内部 embedding"

        g2 = client.get("/api/v2/memories/tcr1", params={"include_embedding": "true"}).json()["data"]
        assert g2["metadata"].get("embedding") == [0.1, 0.2]

    def test_put_response_strips_embedding(self, clean_home):
        cfg = PanguConfig.load()
        _write_drawers_raw(
            cfg.authoritative_drawers_path,
            [_drawer(2, "tc-embed-put", OWN, embedding=[0.3])],
        )
        client = _client()

        r = client.put("/api/v2/memories/tcr2", json={"tags": ["tc"]})
        assert r.status_code == 200
        assert "embedding" not in r.json()["data"]["metadata"]
        # 存储不丢：显式请求仍能取回
        g = client.get("/api/v2/memories/tcr2", params={"include_embedding": "true"}).json()["data"]
        assert g["metadata"].get("embedding") == [0.3]


# ── 3. search 分层 / 过滤 / 分页 / 空 q ──────────────────────


def _seed_layered(cfg):
    """2 条 own + 1 条 recommend，同一命中词 tclayer；created_at 显式定序。"""
    _write_drawers_raw(
        cfg.authoritative_drawers_path,
        [
            _drawer(3, "tclayer own-new", OWN, created="2026-09-22T10:00:00"),
            _drawer(4, "tclayer own-old", OWN, created="2026-09-22T09:00:00"),
            _drawer(5, "tclayer recommend", OTHER, created="2026-09-22T11:00:00"),
        ],
    )


class TestSearchLayering:
    def test_own_before_recommend_with_scope_fields(self, clean_home):
        cfg = PanguConfig.load()
        _seed_layered(cfg)
        client = _client()

        body = client.get("/api/v2/memories/search", params={"q": "tclayer"}).json()["data"]
        assert body["total"] == 3
        assert body["own_total"] == 2
        assert body["recommend_total"] == 1
        scopes = [r["scope"] for r in body["results"]]
        assert scopes == ["own", "own", "recommend"], "own 必须整体排在 recommend 之前"
        assert body["results"][0]["tenant_id"] == OWN
        assert body["results"][2]["tenant_id"] == OTHER
        # own 组内按写入时间倒序（新 → 旧）
        assert [r["id"] for r in body["results"][:2]] == ["tcr3", "tcr4"]

    def test_scope_param_selects_layer(self, clean_home):
        cfg = PanguConfig.load()
        _seed_layered(cfg)
        client = _client()

        own = client.get("/api/v2/memories/search", params={"q": "tclayer", "scope": "own"}).json()["data"]
        assert own["total"] == 2
        assert all(r["scope"] == "own" for r in own["results"])

        rec = client.get(
            "/api/v2/memories/search", params={"q": "tclayer", "scope": "recommend"}
        ).json()["data"]
        assert rec["total"] == 1
        assert rec["results"][0]["tenant_id"] == OTHER

    def test_offset_pages_across_layers(self, clean_home):
        cfg = PanguConfig.load()
        _seed_layered(cfg)
        client = _client()

        first = client.get("/api/v2/memories/search", params={"q": "tclayer", "limit": 1}).json()["data"]
        second = client.get(
            "/api/v2/memories/search", params={"q": "tclayer", "limit": 1, "offset": 1}
        ).json()["data"]
        assert first["offset"] == 0 and second["offset"] == 1
        assert first["results"][0]["id"] != second["results"][0]["id"]
        # 分页不重不漏
        ids = set()
        for off in range(3):
            page = client.get(
                "/api/v2/memories/search", params={"q": "tclayer", "limit": 1, "offset": off}
            ).json()["data"]
            ids.update(r["id"] for r in page["results"])
        assert ids == {"tcr3", "tcr4", "tcr5"}

    def test_tag_and_owner_filters(self, clean_home):
        cfg = PanguConfig.load()
        _write_drawers_raw(
            cfg.authoritative_drawers_path,
            [
                _drawer(6, "tcfilter alpha", OWN, tags=["a", "b"], owner="u1"),
                _drawer(7, "tcfilter beta", OWN, tags=["a"], owner="u2"),
                _drawer(8, "tcfilter gamma", OWN, tags=["b"], owner="u2"),
            ],
        )
        client = _client()

        both = client.get("/api/v2/memories/search", params={"q": "tcfilter", "tag": ["a", "b"]}).json()["data"]
        assert [r["id"] for r in both["results"]] == ["tcr6"], "多 tag 为 AND 语义"

        by_owner = client.get(
            "/api/v2/memories/search", params={"q": "tcfilter", "owner_id": "u2"}
        ).json()["data"]
        assert {r["id"] for r in by_owner["results"]} == {"tcr7", "tcr8"}

    def test_empty_and_missing_q_are_same_topn(self, clean_home):
        """空 q 与缺省 q 同为分层 top-N（此前空 q=0 条、缺 q=422）。"""
        cfg = PanguConfig.load()
        _seed_layered(cfg)
        client = _client()

        empty = client.get("/api/v2/memories/search", params={"q": ""}).json()["data"]
        missing = client.get("/api/v2/memories/search").json()["data"]
        assert empty["total"] == 3 and missing["total"] == 3
        assert [r["scope"] for r in empty["results"]] == ["own", "own", "recommend"]
        # 分层 top-N 不是检索：分数为 0，不误打召回反馈亦不改写内容
        assert all(r["search_score"] == 0 for r in empty["results"])
