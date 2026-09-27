"""`/api/v2/memories/lifecycle` 读取端点的回归（2026-09-27）。

缺陷：该端点直接回传 `[e.__dict__ for e in events]`，而 `TimelineEvent.content`
来自 `d.content` —— **落库时已按 `is_enabled()` 加密**。列表 / 搜索 / 详情 / 导出
这些读取端点都过了 `_plain_content()`，唯独生命周期页漏了，于是 dsh-pangu
仪表盘「生命周期」标签把 `gAAAAAB…` Fernet 密文原样渲染给用户看
（实测云端 `curl -H 'X-API-Key: …' /api/v2/memories/lifecycle` 返回的
content 全是密文）。

顺带锁鉴权通道：该端点属**数据面**，只认 `X-API-Key`，`X-Admin-Key` 恒 401。
dsh-pangu 侧曾用 `adminFetch`（发 X-Admin-Key）打它，401 的 error body 又被
压成一句 "lifecycle error"，真正的原因（鉴权头用错）就此消失。
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pangu.core.config import PanguConfig
from pangu.memory import encryption as enc
from tests.test_p0_0_authoritative_path import (  # noqa: F401 — fixture 经模块命名空间解析
    _write_drawers_raw,
    clean_home,
)


def _client() -> TestClient:
    """挂 memories 路由 + 注入已认证身份（等价 AuthMiddleware 产物）。

    cf131d7 起读取端点对匿名返回 401，bare 测试 App 没有 AuthMiddleware
    ⇒ `get_principal()` 拿到 anonymous ⇒ 响应体 `{"code":401,"data":null}`。
    这里考的是解密，不是鉴权，给个身份即可。
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
                    "user_id": "lc-user",
                    "method": "platform_token",
                    "tenant": "lc-platform",
                }
            await self.app(scope, receive, send)

    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(router, prefix="/api/v2")
    return TestClient(app)


def _seed_encrypted(cfg: PanguConfig, plaintexts: list[str]) -> str:
    """按写入方的真实行为落库：content 加密后写权威库，返回密钥。"""
    key = Fernet.generate_key().decode()
    for attr, val in (
        ("_fernet", None),
        ("_enabled", False),
        ("_key_count", 0),
        ("_decrypt_failed_warned", False),
        ("_encrypt_disabled_warned", False),
    ):
        setattr(enc, attr, val)
    import os

    os.environ["PANGU_ENCRYPTION_KEY"] = key
    enc._enabled = True  # 直接置位，绕开 self_check 的单例缓存

    items = []
    for i, text in enumerate(plaintexts):
        items.append(
            {
                "id": f"lce{i}",
                "content": enc.encrypt(text),
                "wing": "lcw",
                "room": "lcr",
                "tags": [],
                "metadata": {"tenant_id": "lc-platform"},
                "created_at": f"2026-09-2{i}T00:00:00",
            }
        )
    _write_drawers_raw(cfg.authoritative_drawers_path, items)
    return key


class TestLifecycleDecryptsContent:
    def test_content_is_plaintext_not_fernet(self, clean_home, monkeypatch):
        """★ 核心回归：生命周期 events 的 content 必须是可读正文。

        修复前 `e.__dict__` 原样回传 ⇒ 客户端拿到 `gAAAAAB…` 并直接渲染。
        """
        cfg = PanguConfig.load()
        _seed_encrypted(cfg, ["盘古生命周期页回归 A", "盘古生命周期页回归 B"])

        r = _client().get("/api/v2/memories/lifecycle", params={"limit": 10})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0, body

        events = body["data"]["events"]
        assert events, "种子数据没进时间线，断言无意义"
        for e in events:
            c = e["content"]
            assert not str(c).startswith("gAAAAA"), f"回传了密文：{c[:60]}"
            assert "回归" in c, f"没解出可读正文：{c[:60]}"

    def test_stats_still_present(self, clean_home):
        """解密改造不得碰掉 stats（前端读 stats.total / stats.events）。"""
        cfg = PanguConfig.load()
        _seed_encrypted(cfg, ["仅用于计数"])

        body = _client().get("/api/v2/memories/lifecycle").json()
        stats = body["data"]["stats"]
        assert stats["total"] >= 1
        assert stats["events"] == len(body["data"]["events"])

    def test_plain_content_is_passthrough(self, clean_home):
        """加密关闭时 decrypt 是三态的：明文原样返回，不能被这步改坏。"""
        cfg = PanguConfig.load()
        _write_drawers_raw(
            cfg.authoritative_drawers_path,
            [
                {
                    "id": "lcplain",
                    "content": "从未加密的正文",
                    "wing": "lcw",
                    "room": "lcr",
                    "tags": [],
                    "metadata": {"tenant_id": "lc-platform"},
                    "created_at": "2026-09-20T00:00:00",
                }
            ],
        )

        body = _client().get("/api/v2/memories/lifecycle").json()
        contents = [e["content"] for e in body["data"]["events"]]
        assert "从未加密的正文" in contents
        assert not any(str(c).startswith("gAAAAA") for c in contents)
