"""`/api/v2/memories/lifecycle` 读取端点的回归（2026-09-27）。

ROADMAP P2-4.4 的验收标准是「dashboard 展示记忆**从入库到遗忘的全轨迹**」
（docs/ROADMAP.md:167）。初版实现（commit e76e5b6）只调了
`TimelineEngine.build_timeline`，交付出来的是「活跃记忆按 created_at 排序的
清单」，与验收标准差了整整一段功能。本文件锁住第二次实现：

  1. **内容不得回传密文** —— 落库按 `is_enabled()` 加密，读取端点须过
     `_plain_content`。归档表（forgetting_archive.json）里的 content 同样是密文。
  2. **必须带上生命周期状态** —— 活跃记忆要有 `status` + `next_action`
     (keep/compress/archive/forget) + `status_reason` + `status_score`，
     数据源是 `AdaptiveForgetting.evaluate_all`；否则无从知道一条记忆在生命周期
     的哪一格。
  3. **已归档/已遗忘的记忆必须出现** —— 它们被 `remove_drawer` 移出 drawers.json
     （见 handlers/memory_ops.py handle_archive_memory），只活在冷存储里。
     不合并进来就永远展示不了「到遗忘」，尾巴是缺的。
  4. **倒序 + 取最新** —— 初版是升序且 `drawers[:limit]` 取的是文件头部，
     实测把全库最旧的 50 条当成"最近 50 条"展示。
  5. **stats 反映全库** —— 初版 `stats.total = len(drawers[:limit])`，
     恒等于 limit，被 UI 当成"全库只有 50 条"。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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

# 状态动作的全集（与 adaptive_forgetting._compute_decision 对齐）
ACTIONS = {"keep", "archive", "compress", "forget"}


def _client() -> TestClient:
    """挂 memories 路由 + 注入已认证身份（等价 AuthMiddleware 产物）。

    cf131d7 起读取端点对匿名返回 401，bare 测试 App 没有 AuthMiddleware
    ⇒ `get_principal()` 拿到 anonymous ⇒ 响应体 `{"code":401,"data":null}`。
    这里考的是解密与状态装配，不是鉴权，给个身份即可。
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


def _reset_crypto(monkeypatch) -> str:
    """重置加密单例并设置一把新钥（模拟进程重启 / 密钥变更）。"""
    for attr, val in (
        ("_fernet", None),
        ("_enabled", False),
        ("_key_count", 0),
        ("_decrypt_failed_warned", False),
        ("_encrypt_disabled_warned", False),
    ):
        setattr(enc, attr, val)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("PANGU_ENCRYPTION_KEY", key)
    enc._enabled = True  # 直接置位，绕开 self_check 的单例缓存
    return key


@pytest.fixture(autouse=True)
def _reset_forgetting_singleton(monkeypatch):
    """重置 `get_forgetting` 的进程级单例。

    它把 AdaptiveForgetting 缓存在模块变量 `_forgetting` 里、归档文件路径在
    **首次构造**时定死。`clean_home` 每个用例换一个 HOME，不重置的话单例会一直
    指向上一个用例的 tmp 目录 —— 本用例种的归档读不到，断言随机失败。
    """
    from pangu.memory import adaptive_forgetting as af_mod

    monkeypatch.setattr(af_mod, "_forgetting", None)
    yield


def _drawer(i: int, content: str, *, created: str, importance: float = 3.0) -> dict:
    return {
        "id": f"lce{i}",
        "content": content,
        "wing": "lcw",
        "room": "lcr",
        "tags": [],
        "importance": importance,
        "metadata": {"tenant_id": "lc-platform"},
        "created_at": created,
    }


def _seed_active(cfg: PanguConfig, specs: list[dict], monkeypatch, encrypt: bool = True) -> None:
    """写活跃库（drawers.json）。encrypt=True 时按写入方真实行为先加密 content。"""
    if encrypt:
        _reset_crypto(monkeypatch)
    items = []
    for i, s in enumerate(specs):
        content = enc.encrypt(s["content"]) if encrypt else s["content"]
        items.append(_drawer(i, content, created=s["created"], importance=s.get("importance", 3.0)))
    _write_drawers_raw(cfg.authoritative_drawers_path, items)


def _archive_path(cfg=None) -> Path:
    """归档表落盘路径。

    ⚠ 必须用 **authoritative** config 算，不能用 `PanguConfig.load()`：
    后者 palace_path 是 `~/.pangu/palace`，而服务端（MCPServer.__init__ 显式
    `.authoritative_memory_config()`、lifecycle 端点的 `_authoritative_cfg()`）
    用的是 `~/.pangu/pangu.db` —— 两条路会读写**两个不同的归档文件**。
    云端实测归档落在 `/root/.pangu/pangu.db/forgetting_archive.json`，即权威侧。
    """
    from pangu.api.routes_memory import _authoritative_cfg

    base = cfg or _authoritative_cfg()
    return Path(base.palace_path).parent / "forgetting_archive.json"


def _seed_archive(cfg: PanguConfig, entries: list[dict]) -> None:
    """写归档表。路径一律走 authoritative（见 `_archive_path`）。

    ``cfg`` 参数保留只是为了与 ``_seed_active`` 的调用形态对称，实际不参与
    路径计算 —— 传 `PanguConfig.load()` 会指到另一个文件，那正是本用例要避开的坑。
    """
    p = _archive_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


SPECS = [
    {"content": "最早的一条 LC-EARLY", "created": "2026-09-20T01:00:00", "importance": 5.0},
    {"content": "中间的一条 LC-MIDDLE", "created": "2026-09-24T01:00:00", "importance": 1.0},
    {"content": "最新的一条 LC-LATEST", "created": "2026-09-27T01:00:00", "importance": 3.0},
]


class TestLifecycleStatus:
    """状态装配：页面必须能看出每条记忆在生命周期的哪一格。"""

    def test_active_events_carry_status_and_next_action(self, clean_home, monkeypatch):
        """活跃记忆要有 status/next_action/status_reason/status_score。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)

        body = _client().get("/api/v2/memories/lifecycle").json()
        assert body["code"] == 0, body
        actives = [e for e in body["data"]["events"] if e["status"] == "active"]
        assert actives, "没有任何活跃事件，状态装配没生效"

        for e in actives:
            assert e["next_action"] in ACTIONS, f"next_action 不合法: {e['next_action']!r}"
            assert isinstance(e["status_reason"], str)
            assert isinstance(e["status_score"], (int, float))
            # 状态是评估出来的，不是硬编码：低重要性应被判到更激进的去向
            assert 0.0 <= e["status_score"] <= 1.0

    def test_score_reflects_importance(self, clean_home, monkeypatch):
        """低重要性记忆的遗忘分应高于高重要性记忆 —— 否则状态是假的。

        公式（adaptive_forgetting.evaluate_memory）：
            forget_score = (1-imp/5)*0.4 + (1-freq)*0.3 + (1-recency)*0.3
        两条的 freq/recency 相同 ⇒ 分数差只由 importance 决定。
        """
        cfg = PanguConfig.load()
        _seed_active(
            cfg,
            [
                {"content": "高价值 HIGH-IMP", "created": "2026-09-20T01:00:00", "importance": 5.0},
                {"content": "低价值 LOW-IMP", "created": "2026-09-20T01:00:00", "importance": 1.0},
            ],
            monkeypatch,
        )

        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        by_content = {e["content"]: e for e in ev}
        hi = by_content["高价值 HIGH-IMP"]
        lo = by_content["低价值 LOW-IMP"]
        assert lo["status_score"] > hi["status_score"], (
            f"低重要性分应更高: low={lo['status_score']} high={hi['status_score']}"
        )


class TestLifecycleArchivedVisible:
    """已归档/已遗忘的记忆必须出现在时间线上 —— 否则「到遗忘」永远缺尾。

    背景：handle_archive_memory 会 archive_memory() 存冷存储后再
    remove_drawer() 从 drawers.json 删掉，所以它们只存在于
    forgetting_archive.json。初版端点只读 get_drawers()，必然看不到。
    """

    def test_archived_entry_appears(self, clean_home, monkeypatch):
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch, encrypt=False)
        _seed_archive(
            cfg,
            [
                {
                    "id": "arch-1",
                    "content": "已归档的 LC-ARCHIVED",
                    "wing": "lcw",
                    "room": "lcr",
                    "importance": 2.0,
                    "archived_at": "2026-09-25T02:00:00",
                    "created_at": "2026-09-21T02:00:00",
                    "action": "archive",
                    "reason": "低活跃",
                }
            ],
        )

        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        archived = [e for e in ev if e["status"] in ("archived", "forgotten")]
        assert archived, "归档记忆没出现在时间线上，「到遗忘」是缺尾的"
        a = archived[0]
        assert a["content"] == "已归档的 LC-ARCHIVED"
        assert a["archived_at"] == "2026-09-25T02:00:00"
        # 有 created_at 就该用入库时刻定位，而不是归档时刻
        assert a["timestamp"] == "2026-09-21T02:00:00"

    def test_archived_content_is_decrypted(self, clean_home, monkeypatch):
        """归档表里的 content 也是 Fernet 密文（实测云端 n=16 全是 gAAAAA…）。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch)  # 顺带设好密钥
        _seed_archive(
            cfg,
            [
                {
                    "id": "arch-ct",
                    "content": enc.encrypt("归档密文应解开"),
                    "wing": "lcw",
                    "room": "lcr",
                    "importance": 2.0,
                    "archived_at": "2026-09-25T02:00:00",
                }
            ],
        )

        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        got = [e for e in ev if e["drawer_id"] == "arch-ct"][0]
        assert not got["content"].startswith("gAAAAA"), got["content"][:60]
        assert got["content"] == "归档密文应解开"

    def test_legacy_archive_without_created_at_falls_back(self, clean_home, monkeypatch):
        """老归档条目没有 created_at（初版就没存）—— 不能让时间线整体崩掉。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch, encrypt=False)
        _seed_archive(
            cfg,
            [{"id": "legacy-1", "content": "老数据", "wing": "lcw", "room": "lcr",
              "importance": 3.0, "archived_at": "2026-09-23T03:47:13"}],
        )

        body = _client().get("/api/v2/memories/lifecycle").json()
        assert body["code"] == 0
        legacy = [e for e in body["data"]["events"] if e["drawer_id"] == "legacy-1"]
        assert legacy, "缺 created_at 的老归档条目丢了"
        assert legacy[0]["timestamp"], "缺 created_at 时应回退到 archived_at"


class TestLifecycleOrderAndStats:
    """顺序与统计：初版两处都反了，实测把最旧的 50 条当成「最近 50 条」。"""

    def test_events_are_newest_first(self, clean_home, monkeypatch):
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)
        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        ts = [e["timestamp"] for e in ev]
        assert ts == sorted(ts, reverse=True), f"应为倒序（最新在前）: {ts}"

    def test_latest_memories_are_the_ones_returned(self, clean_home, monkeypatch):
        """limit 截断要落在**最新**的条目上，而不是文件头部（初版 bug）。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)
        ev = _client().get("/api/v2/memories/lifecycle", params={"limit": 2}).json()["data"]["events"]
        assert len(ev) == 2
        contents = [e["content"] for e in ev]
        assert "最新的一条 LC-LATEST" in contents, f"limit=2 没拿到最新的: {contents}"
        assert "最早的一条 LC-EARLY" not in contents

    def test_stats_total_is_whole_library_not_limit(self, clean_home, monkeypatch):
        """初版 stats.total = len(drawers[:limit]) ≡ limit，被 UI 读成全库规模。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)
        _seed_archive(
            cfg,
            [{"id": "a1", "content": "x", "wing": "lcw", "room": "lcr",
              "importance": 3.0, "archived_at": "2026-09-25T00:00:00"}],
        )

        stats = _client().get("/api/v2/memories/lifecycle", params={"limit": 2}).json()["data"]["stats"]
        assert stats["total"] == 4, f"total 应是全库(3 活跃+1 归档)而非 limit: {stats}"
        assert stats["events"] == 2, "events 是本次返回条数，应受 limit 约束"
        assert stats["total"] >= stats["events"]

    def test_stats_breaks_down_by_status(self, clean_home, monkeypatch):
        """状态分布是「生命周期」这页的核心读数，必须给。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)
        _seed_archive(
            cfg,
            [{"id": "a1", "content": "x", "wing": "lcw", "room": "lcr",
              "importance": 3.0, "archived_at": "2026-09-25T00:00:00"}],
        )

        stats = _client().get("/api/v2/memories/lifecycle").json()["data"]["stats"]
        for key in ("active", "archived", "keep", "compress", "archive", "forget"):
            assert key in stats, f"stats 缺 {key}: {sorted(stats)}"
        assert stats["active"] == 3
        assert stats["archived"] >= 1


class TestLifecycleContentDecryption:
    """读取端点必须解密（初版缺陷，2026-09-27 第一次修复）。"""

    def test_content_is_plaintext_not_fernet(self, clean_home, monkeypatch):
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS, monkeypatch)

        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        assert ev, "种子数据没进时间线，断言无意义"
        for e in ev:
            c = e["content"]
            assert not str(c).startswith("gAAAAA"), f"回传了密文：{c[:60]}"
            assert "LC-" in c, f"没解出可读正文：{c[:60]}"

    def test_plain_content_is_passthrough(self, clean_home, monkeypatch):
        """加密关闭时 decrypt 是三态的：明文原样返回，不能被这步改坏。"""
        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch, encrypt=False)

        ev = _client().get("/api/v2/memories/lifecycle").json()["data"]["events"]
        assert any(e["content"] == SPECS[0]["content"] for e in ev)


class TestArchiveWritePath:
    """归档写入端：不补 created_at/action，时间线永远没有「入库→遗忘」的跨度。"""

    def test_archive_memory_records_created_at(self, clean_home, monkeypatch):
        from pangu.memory.adaptive_forgetting import AdaptiveForgetting

        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch, encrypt=False)
        from pangu.core.palace import Drawer

        d = Drawer(id="w1", content="待归档", wing="lcw", room="lcr",
                   created_at="2026-09-21T05:00:00")
        entry = AdaptiveForgetting(cfg).archive_memory(d)

        assert entry.get("created_at") == "2026-09-21T05:00:00", (
            "归档条目没记 created_at ⇒ 时间线上定位不到入库时刻，"
            "「从入库到遗忘」的跨度无从表达"
        )
        assert entry.get("action") == "archive"
        assert entry.get("reason"), "归档要带原因，否则页面只能显示一个光秃秃的状态"

    def test_auto_forget_records_forgotten(self, clean_home, monkeypatch):
        """★ 彻底遗忘的条目必须留痕。

        初版 auto_forget 的 forget 分支只 `forgotten.append(id)`、把 id 从
        drawers 移除 —— 既不在 drawers.json 也不在归档表，只剩一个计数。
        「到遗忘」这一段因此在数据上根本不存在。
        """
        from pangu.core.palace import Drawer
        from pangu.memory.adaptive_forgetting import AdaptiveForgetting

        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch, encrypt=False)
        af = AdaptiveForgetting(cfg)
        drawers = [
            Drawer(id="keep-me", content="重要", wing="lcw", room="lcr", importance=5.0,
                   created_at="2026-09-26T00:00:00"),
            Drawer(id="forget-me", content="废弃", wing="lcw", room="lcr", importance=0.0,
                   created_at="2026-09-20T00:00:00"),
        ]
        af.auto_forget(drawers)

        assert not any(d.id == "forget-me" for d in drawers), "没真正移出活跃集合"
        kept = af.get_archive(limit=100)  # 默认口径：归档表（不含遗忘）
        forgotten = af.get_archive(limit=100, include_forgotten=True)
        f_ids = {e["id"] for e in forgotten}
        assert "forget-me" in f_ids, "彻底遗忘没留痕，时间线永远看不到遗忘段"

        # 既有契约不能被破坏：pangu_get_archive 默认仍只返回归档
        assert "forget-me" not in {e["id"] for e in kept}, (
            "默认 get_archive 混入 forgotten 会改变 pangu_get_archive 的既有契约"
        )

    def test_get_archive_default_excludes_forgotten(self, clean_home, monkeypatch):
        """get_archive 的默认口径必须与改动前一致（advanced.py:1351 依赖它）。"""
        from pangu.memory.adaptive_forgetting import AdaptiveForgetting

        cfg = PanguConfig.load()
        _seed_active(cfg, SPECS[:1], monkeypatch, encrypt=False)
        af = AdaptiveForgetting(cfg)
        assert af.get_archive(limit=100) == [], "空归档表默认应返回空"
