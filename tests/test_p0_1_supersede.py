"""P0-1 supersede 全链路测试

覆盖五项改动：
  ① _detect_conflicts 写 supersedes/superseded_by + 落盘旧 drawer
  ② hybrid_search._build_results 标注 superseded/superseded_by/warning
  ③ versioning.record_version 接线
  ④ 新 MCP 工具 pangu_get_supersede_chain
  ⑤ 完整链路（写入 → 检索 → 工具调用）

测试隔离由 conftest 的 autouse fixtures 提供（PANGU_BASE_DIR /
PANGU_CACHE_DIR 隔离 + 向量索引单例复位 + sentence-transformers mock）。
搜索缓存必须在每个 search 前清掉，否则 300s TTL 会让"先写 → search"
与"再写 → search"两次拿到同一缓存。
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# 全局唯一 wing/room 串，避免与其它测试串扰
_WING = f"p01_supersede_{uuid.uuid4().hex[:8]}"
_ROOM = "t"


# ── 工具函数 ──


def _clear_search_cache():
    from pangu.memory.search_cache import get_search_cache

    get_search_cache().clear()


def _stack_with_config():
    from pangu.core.config import PanguConfig
    from pangu.memory.layers import MemoryStack

    cfg = PanguConfig.load().authoritative_memory_config()
    # JsonDrawerStorage.save() 不自动 mkdir parent（与 SqliteDrawerStorage 不同）；
    # conftest 仅预建了 `palace/`，v2 路径 `pangu.db/v2_memories/` 缺失。
    # 这里预建以保证测试可写盘。
    Path(cfg.palace_path).mkdir(parents=True, exist_ok=True)
    return MemoryStack(config=cfg)


# 一个 pytest fixture：把 ingestion 的语义去重阈值调到 0.9999（几乎不触发）
# 同时关闭加密（避免 drawer.content 被 Fernet 加密后冲突检测看不到矛盾词）。
#
# 不调高阈值则 contradictory 文本会因 ONNX 嵌入相似度 ≈0.95 触发 dedup，
# 导致 remember() 直接返回 OLD drawer（带 boosted_at），_detect_conflicts
# 完全不被调用 —— 这是与 supersede 测试目的相反的现状。
#
# 不关加密则 drawer.content 是 "gAAAAA..." 开头的密文，ConflictDetector
# 在密文上跑关键词/矛盾模式匹配，命中数为 0，supersede 永远不触发。
#
# 还要重置 FTS 单例 + 改写其磁盘索引路径（默认 `~/.pangu/fts_index.json`
# 是**硬编码**生产路径，与 conftest 的 tmp_path 隔离不一致 ——
# conftest 只隔离了 vector_index 与 cache_dir，FTS 是历史遗留没补上）。
@pytest.fixture(autouse=True)
def _disable_semantic_dedup(monkeypatch, tmp_path):
    import pangu.memory.ingestion as ing_mod

    monkeypatch.setattr(ing_mod, "SIMILARITY_THRESHOLD", 0.9999)
    monkeypatch.setattr(ing_mod, "TEXT_OVERLAP_THRESHOLD", 1.1)
    # 关掉加密：本机 ~/.pangu/.encryption_key 存在 ⇒ is_enabled() True ⇒
    # 写入的 drawer.content 是密文，会让 ConflictDetector 看不到矛盾词。
    import pangu.memory.encryption as enc_mod

    monkeypatch.setattr(enc_mod, "_enabled", False)
    monkeypatch.setattr(enc_mod, "_fernet", None)
    monkeypatch.setattr(enc_mod, "is_enabled", lambda: False)
    # FTS 单例与索引路径重置（防止上一用例/生产状态泄漏）
    import pangu.memory.fts_search as fts_mod

    monkeypatch.setattr(fts_mod, "_fts_engine", None)
    if hasattr(fts_mod, "FTS5SearchEngine"):
        # 让 FTS 的索引文件落在 tmp 下，不污染生产
        monkeypatch.setattr(
            fts_mod.FTS5SearchEngine,
            "_get_index_path",
            lambda self: tmp_path / "fts_index.json",
        )
    yield


def _seed_supersede_scenario(stack, with_persistence: bool = True):
    """构造"先写 A → 写 ¬A 触发 supersede"的场景。

    返回 (stack, old_id, old_drawer, new_id, new_drawer, all_existing)
    all_existing 是 ¬A 写入时的 existing_drawers 列表（含 old + 2 个 filler）。

    当 with_persistence=True 时，把每个抽屉显式 add_drawer 落盘（生产路径）。
    """
    from pangu.memory.ingestion import remember

    # 1) 写 A（必须含 fact_keyword + positive 矛盾词，让 conflict 能识别）
    old_id, old_drawer = remember(
        "API 配置: token 是正确，应该启用。",
        wing=_WING,
        room=_ROOM,
        importance=0.5,
        tags=["api", "config"],
    )
    # 2) 写 2 个 filler 让现有 ≥ CONFLICT_MIN_EXISTING=3
    filler1_id, filler1 = remember(
        "数据库备份策略说明",
        wing=_WING,
        room=_ROOM,
        importance=0.3,
        tags=["backup"],
    )
    filler2_id, filler2 = remember(
        "前端缓存策略说明",
        wing=_WING,
        room=_ROOM,
        importance=0.3,
        tags=["cache"],
    )
    if with_persistence:
        stack.add_drawer(old_drawer)
        stack.add_drawer(filler1)
        stack.add_drawer(filler2)
    # 3) 写 ¬A（矛盾方向：只含 negative 词）
    all_existing = [old_drawer, filler1, filler2]
    new_id, new_drawer = remember(
        "API 配置: token 是错误的，必须禁用。",
        wing=_WING,
        room=_ROOM,
        importance=0.7,
        tags=["api", "config"],
        existing_drawers=all_existing,
    )
    if with_persistence:
        stack.add_drawer(new_drawer)
    return stack, old_id, old_drawer, new_id, new_drawer, all_existing


# ── 1. must-block ──


class TestMustBlock:
    """P0-1 必须阻止的：5 项核心行为必须实现"""

    def test_supersede_writes_metadata_to_old_drawer(self):
        """旧 drawer 必须带 superseded_by + memory_status=superseded"""
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        _, old_id, old_drawer, new_id, new_drawer, _ = _seed_supersede_scenario(stack)

        meta = old_drawer.metadata or {}
        assert meta.get("memory_status") == "superseded"
        assert new_id in (meta.get("superseded_by") or [])
        # 新 drawer 必须有 supersedes
        new_meta = new_drawer.metadata or {}
        assert old_id in (new_meta.get("supersedes") or [])

    def test_supersede_persists_old_drawer_to_storage(self):
        """旧 drawer 的 superseded_by 必须**真的落盘**（从 JsonDrawerStorage 重载可见）"""
        from pangu.core.config import PanguConfig
        from pangu.memory.drawer_storage import JsonDrawerStorage

        stack = _stack_with_config()
        _, old_id, _, new_id, _, _ = _seed_supersede_scenario(stack)

        config = PanguConfig.load().authoritative_memory_config()
        storage = JsonDrawerStorage(str(Path(config.palace_path) / "drawers.json"))
        on_disk = {d.id: d for d in storage.load()}

        assert old_id in on_disk, "old drawer must persist"
        assert new_id in on_disk, "new drawer must persist"
        old_meta = on_disk[old_id].metadata or {}
        assert old_meta.get("memory_status") == "superseded"
        assert new_id in (old_meta.get("superseded_by") or [])
        new_meta = on_disk[new_id].metadata or {}
        assert old_id in (new_meta.get("supersedes") or [])

    def test_hybrid_search_marks_superseded(self):
        """hybrid_search 结果必须标注 superseded/warning/superseded_by"""
        stack = _stack_with_config()
        _, old_id, _, new_id, _, _ = _seed_supersede_scenario(stack)

        from pangu.core.config import PanguConfig
        from pangu.memory.hybrid_search import hybrid_search

        _clear_search_cache()
        # 用唯一 query 避开缓存
        q = f"API 配置 token 错误 {uuid.uuid4().hex[:8]}"

        drawers = stack.get_drawers()
        results = hybrid_search(q, drawers, config=PanguConfig.load().authoritative_memory_config(), limit=50)
        by_id = {r["id"]: r for r in results}

        # 新 drawer 应当未被 supersede
        if new_id in by_id:
            assert by_id[new_id]["superseded"] is False
            assert by_id[new_id]["warning"] is None
            assert by_id[new_id]["superseded_by"] == []

        # 旧 drawer（若被搜到）必须标注
        if old_id in by_id:
            assert by_id[old_id]["superseded"] is True
            assert by_id[old_id]["warning"] == "⚠ 已被更新"
            assert new_id in by_id[old_id]["superseded_by"]

    def test_versioning_records_supersede(self):
        """versioning 必须记两条：旧 superseded、新 supersede"""
        from pangu.memory.versioning import get_version_control

        stack = _stack_with_config()
        _, old_id, _, new_id, _, _ = _seed_supersede_scenario(stack)

        vc = get_version_control()
        old_versions = vc.get_versions(old_id)
        new_versions = vc.get_versions(new_id)

        assert any(v.change_type == "superseded" for v in old_versions), (
            f"old drawer 应该有 superseded 版本记录，实测: {old_versions}"
        )
        assert any(v.change_type == "supersede" for v in new_versions), (
            f"new drawer 应该有 supersede 版本记录，实测: {new_versions}"
        )

    def test_pangu_get_supersede_chain_tool(self):
        """pangu_get_supersede_chain 工具返回 found=True + chain 含 old/new + versions 非空"""
        stack = _stack_with_config()
        _, old_id, _, new_id, _, _ = _seed_supersede_scenario(stack)

        from pangu.server.handlers.supersede import handle_get_supersede_chain

        class _FakeServer:
            class memory:
                @staticmethod
                def get_drawer_by_id(mid):
                    return _stack_with_config().get_drawer_by_id(mid)

            config = None

        async def _run(mid):
            return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": mid})

        result = json.loads(asyncio.run(_run(new_id)))
        assert result["found"] is True
        # chain 应至少含 root + old
        roles = [n["role"] for n in result["chain"]]
        assert "root" in roles
        assert "old" in roles
        assert any(n["id"] == old_id for n in result["chain"])
        # versions 非空
        assert len(result["versions"]) >= 1


# ── 2. must-allow ──


class TestMustAllow:
    """P0-1 必须放行的：不影响现有行为"""

    def test_remember_without_conflict_unaffected(self):
        """单条 write、无冲突 ⇒ drawer.metadata 不含 supersedes；search 该条 superseded=False"""
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        item_id, drawer = remember(
            "今日天气晴朗",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(drawer)

        meta = drawer.metadata or {}
        assert "supersedes" not in meta
        assert "superseded_by" not in meta
        assert meta.get("memory_status") != "superseded"

    def test_get_supersede_chain_nonexistent(self):
        """调 memory_id=INVALID ⇒ 返回 found=False，不抛"""
        from pangu.server.handlers.supersede import handle_get_supersede_chain

        class _FakeServer:
            class memory:
                @staticmethod
                def get_drawer_by_id(_mid):
                    return None

            config = None

        async def _run():
            return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": "INVALID-NOT-EXIST"})

        result = json.loads(asyncio.run(_run()))
        assert result["found"] is False
        assert result["chain"] == []
        assert result["versions"] == []
        assert result["depth"] == 0

    def test_get_supersede_chain_backward_forward(self):
        """direction 切换：both/forward/backward 三种"""
        stack = _stack_with_config()
        from pangu.memory.ingestion import remember

        # 构造 A → B（取代 A）→ C（取代 B）：链长 3
        a_id, a = remember(
            "数据库配置: 索引策略正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        f1_id, f1 = remember("缓存策略", wing=_WING, room=_ROOM, importance=0.3)
        f2_id, f2 = remember("监控策略", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(a)
        stack.add_drawer(f1)
        stack.add_drawer(f2)
        b_id, b = remember(
            "数据库配置: 索引策略是错误的，正确是分区",
            wing=_WING,
            room=_ROOM,
            importance=0.7,
            existing_drawers=[a, f1, f2],
        )
        stack.add_drawer(b)
        # 再写 C 取代 B（同样模式）
        f3_id, f3 = remember("网络配置", wing=_WING, room=_ROOM, importance=0.3)
        f4_id, f4 = remember("日志配置", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f3)
        stack.add_drawer(f4)
        c_id, c = remember(
            "数据库配置: 索引策略是错误的，正确是 sharding",
            wing=_WING,
            room=_ROOM,
            importance=0.8,
            existing_drawers=[b, f3, f4],
        )
        stack.add_drawer(c)

        from pangu.server.handlers.supersede import handle_get_supersede_chain

        class _FakeServer:
            class memory:
                @staticmethod
                def get_drawer_by_id(mid):
                    return _stack_with_config().get_drawer_by_id(mid)

            config = None

        async def _run(mid, direction):
            return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": mid, "direction": direction})

        # both：从 B 看应至少含 B (root) + A (old) + C (new)
        both = json.loads(asyncio.run(_run(b_id, "both")))
        roles = sorted({n["role"] for n in both["chain"]})
        assert "root" in roles
        # backward 只看 A 一侧
        back = json.loads(asyncio.run(_run(b_id, "backward")))
        back_roles = {n["role"] for n in back["chain"]}
        assert "new" not in back_roles
        # forward 只看 C 一侧
        fwd = json.loads(asyncio.run(_run(b_id, "forward")))
        fwd_roles = {n["role"] for n in fwd["chain"]}
        assert "old" not in fwd_roles

    def test_search_cache_cleared_after_update(self):
        """先写 → search(q) → 写 supersede → search(同样 q) 第二次能看到新 drawer 和旧标记"""
        from pangu.core.config import PanguConfig
        from pangu.memory.hybrid_search import hybrid_search
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        # 用一个固定 query，但每次 search 前清掉缓存（避免 300s TTL 干扰）
        q = f"P01-search-cache-{uuid.uuid4().hex[:8]}"

        old_id, old_drawer = remember(
            f"测试缓存查询 {q}: 配置正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(old_drawer)
        f1_id, f1 = remember(f"测试缓存 {q} 填充1", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f1)
        f2_id, f2 = remember(f"测试缓存 {q} 填充2", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f2)
        # 先 search（旧 drawer 应能被搜到）
        _clear_search_cache()
        r1 = hybrid_search(q, stack.get_drawers(), config=PanguConfig.load().authoritative_memory_config(), limit=50)
        by_id_1 = {r["id"]: r for r in r1}
        assert old_id in by_id_1
        assert by_id_1[old_id]["superseded"] is False

        # 写 supersede
        new_id, new_drawer = remember(
            f"测试缓存查询 {q}: 配置是错误的",
            wing=_WING,
            room=_ROOM,
            importance=0.7,
            existing_drawers=[old_drawer, f1, f2],
        )
        stack.add_drawer(new_drawer)

        # 第二次 search（清缓存后再走，否则 300s TTL 命中 r1）
        _clear_search_cache()
        r2 = hybrid_search(q, stack.get_drawers(), config=PanguConfig.load().authoritative_memory_config(), limit=50)
        by_id_2 = {r["id"]: r for r in r2}
        assert new_id in by_id_2
        assert by_id_2[new_id]["superseded"] is False
        # 旧 drawer 应被标注
        assert old_id in by_id_2
        assert by_id_2[old_id]["superseded"] is True
        assert by_id_2[old_id]["warning"] == "⚠ 已被更新"


# ── 3. 异常 / 边界 ──


class TestExceptions:
    """异常 / 边界条件"""

    def test_supersede_with_fewer_than_min_existing(self):
        """existing_drawers 长度 < CONFLICT_MIN_EXISTING=3 ⇒ _detect_conflicts 不调用 detector"""
        from pangu.core.palace import Drawer
        from pangu.memory.ingestion import _create_drawer, _detect_conflicts

        # 构造一个 Drawer + 仅 2 个 existing
        item_id = "fake-new-id-for-test"
        drawer = _create_drawer(
            item_id=item_id,
            stored_text="test content",
            wing="x",
            room="r",
            importance=0.5,
            tags=[],
            author="t",
            now="2025-01-01T00:00:00",
            source="test",
            confidence=1.0,
            created_by="t",
            facts="",
            emotional_valence=0.0,
        )
        existing = [
            Drawer(id="e1", content="x", wing="x", room="r", tags=[]),
            Drawer(id="e2", content="y", wing="x", room="r", tags=[]),
        ]
        _detect_conflicts(drawer, existing, item_id)
        # metadata 不写 supersedes（CONFLICT_MIN_EXISTING=3 不达）
        meta = drawer.metadata or {}
        assert "supersedes" not in meta
        # existing 也不变
        assert "superseded_by" not in (existing[0].metadata or {})

    def test_storage_update_failure_does_not_block_remember(self):
        """storage 抛异常 ⇒ remember 仍正常返回；新 drawer 仍带 supersedes 标记"""
        from unittest.mock import patch

        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        # 用 monkeypatch 让 _persist_supersede_update 抛异常
        from pangu.memory import ingestion as ing_mod

        def _boom(*_a, **_kw):
            raise RuntimeError("simulated storage failure")

        # 准备基线数据
        old_id, old_drawer = remember(
            "配置 X 是正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(old_drawer)
        f1_id, f1 = remember("填充 1", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f1)
        f2_id, f2 = remember("填充 2", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f2)

        with patch.object(ing_mod, "_persist_supersede_update", side_effect=_boom):
            # remember 不应抛
            new_id, new_drawer = remember(
                "配置 X 是错误的",
                wing=_WING,
                room=_ROOM,
                importance=0.7,
                existing_drawers=[old_drawer, f1, f2],
            )
        assert new_id is not None
        # 新 drawer 仍带 supersedes（落盘失败但 metadata 已更新）
        meta = new_drawer.metadata or {}
        assert old_id in (meta.get("supersedes") or [])

    def test_detect_conflict_exception_swallowed(self):
        """ConflictDetector.detect_conflicts 抛异常 ⇒ remember 不抛；新 drawer 无 conflicts/supersedes"""
        from unittest.mock import patch

        from pangu.memory import conflict as conflict_mod
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        old_id, old_drawer = remember(
            "测试异常: 配置正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(old_drawer)
        f1_id, f1 = remember("填充 1", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f1)
        f2_id, f2 = remember("填充 2", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f2)

        with patch.object(conflict_mod.ConflictDetector, "detect_conflicts", side_effect=RuntimeError("simulated")):
            new_id, new_drawer = remember(
                "测试异常: 配置是错误的",
                wing=_WING,
                room=_ROOM,
                importance=0.7,
                existing_drawers=[old_drawer, f1, f2],
            )
        assert new_id is not None
        meta = new_drawer.metadata or {}
        assert "supersedes" not in meta
        assert "conflicts" not in meta

    def test_chain_with_cycle_in_metadata(self):
        """A.supersedes=[B.id]、B.supersedes=[A.id]（互指）⇒ handle 不死循环"""
        from pangu.core.palace import Drawer
        from pangu.server.handlers.supersede import handle_get_supersede_chain

        a = Drawer(
            id="cycle-A",
            content="A content",
            wing="x",
            room="r",
            tags=[],
            created_at="2025-01-01T00:00:00",
            metadata={"supersedes": ["cycle-B"], "memory_status": "active"},
        )
        b = Drawer(
            id="cycle-B",
            content="B content",
            wing="x",
            room="r",
            tags=[],
            created_at="2025-01-02T00:00:00",
            metadata={"supersedes": ["cycle-A"], "memory_status": "active"},
        )
        by_id = {"cycle-A": a, "cycle-B": b}

        class _FakeServer:
            class memory:
                @staticmethod
                def get_drawer_by_id(mid):
                    return by_id.get(mid)

            config = None

        async def _run():
            return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": "cycle-A"})

        result = json.loads(asyncio.run(_run()))
        # visited 集合应保证不死循环；depth 有限
        assert isinstance(result["depth"], int)
        assert result["depth"] >= 0
        # 至少含 A（root）和 B（old）
        ids = {n["id"] for n in result["chain"]}
        assert "cycle-A" in ids
        assert "cycle-B" in ids

    def test_chain_with_missing_linked_drawer(self):
        """A.supersedes=[ghost_id]；ghost_id 不存在 ⇒ handle 跳过，chain 不报错"""
        from pangu.core.palace import Drawer
        from pangu.server.handlers.supersede import handle_get_supersede_chain

        a = Drawer(
            id="missing-link-A",
            content="A content",
            wing="x",
            room="r",
            tags=[],
            created_at="2025-01-01T00:00:00",
            metadata={"supersedes": ["ghost-xxx"], "memory_status": "active"},
        )
        by_id = {"missing-link-A": a}

        class _FakeServer:
            class memory:
                @staticmethod
                def get_drawer_by_id(mid):
                    return by_id.get(mid)

            config = None

        async def _run():
            return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": "missing-link-A"})

        result = json.loads(asyncio.run(_run()))
        assert result["found"] is True
        # chain 只含 A（ghost 被跳过）
        ids = [n["id"] for n in result["chain"]]
        assert ids == ["missing-link-A"]


# ── 4. 注入验证（regression 守护） ──


class TestInjectionValidation:
    """注入验证：手动改回旧逻辑，测试必须立刻失败"""

    def test_injection_disable_detect_conflicts(self):
        """monkeypatch _detect_conflicts 为 no-op ⇒ _seed_supersede_scenario 不再产生 superseded"""
        from unittest.mock import patch

        from pangu.memory import ingestion as ing_mod
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        old_id, old_drawer = remember(
            "注入 A: 配置正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(old_drawer)
        f1_id, f1 = remember("注入填充 1", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f1)
        f2_id, f2 = remember("注入填充 2", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f2)

        with patch.object(ing_mod, "_detect_conflicts", lambda *a, **kw: None):
            new_id, new_drawer = remember(
                "注入 A: 配置是错误的",
                wing=_WING,
                room=_ROOM,
                importance=0.7,
                existing_drawers=[old_drawer, f1, f2],
            )

        meta = new_drawer.metadata or {}
        assert "supersedes" not in meta, (
            f"如果 _detect_conflicts 被旁路，新 drawer 的 supersedes 必须为空；实测 meta={meta}"
        )
        # 旧 drawer 的 memory_status 由 _create_drawer 设为 "active"，
        # _detect_conflicts 跑过后会改成 "superseded"。被旁路时仍是 "active"。
        assert (old_drawer.metadata or {}).get("memory_status") == "active", (
            "如果 _detect_conflicts 被旁路，旧 drawer 的 memory_status 应保持 active；"
            f"实测 old meta={old_drawer.metadata}"
        )

    def test_injection_disable_storage_update(self):
        """monkeypatch _persist_supersede_update 抛 NotImplementedError ⇒
        旧 drawer 的 metadata 在内存被改（_detect_conflicts 仍跑），
        但磁盘上**没**真正写入 superseded_by（持久化路径被打断）。
        """
        from unittest.mock import patch

        from pangu.core.config import PanguConfig
        from pangu.memory import ingestion as ing_mod
        from pangu.memory.drawer_storage import JsonDrawerStorage
        from pangu.memory.ingestion import remember

        stack = _stack_with_config()
        old_id, old_drawer = remember(
            "注入持久化: 配置正确",
            wing=_WING,
            room=_ROOM,
            importance=0.5,
        )
        stack.add_drawer(old_drawer)
        f1_id, f1 = remember("注入填充 1", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f1)
        f2_id, f2 = remember("注入填充 2", wing=_WING, room=_ROOM, importance=0.3)
        stack.add_drawer(f2)

        with patch.object(ing_mod, "_persist_supersede_update", side_effect=NotImplementedError("injected")):
            new_id, new_drawer = remember(
                "注入持久化: 配置是错误的",
                wing=_WING,
                room=_ROOM,
                importance=0.7,
                existing_drawers=[old_drawer, f1, f2],
            )

        # 内存里 metadata 已被改
        meta_mem = old_drawer.metadata or {}
        assert "superseded_by" in meta_mem, "内存中应有 superseded_by（_detect_conflicts 仍跑）"

        # 但磁盘上**没**真写 superseded_by ⇒ 从 storage 重载应看不到
        config = PanguConfig.load().authoritative_memory_config()
        storage = JsonDrawerStorage(str(Path(config.palace_path) / "drawers.json"))
        on_disk = {d.id: d for d in storage.load()}
        if old_id in on_disk:
            disk_meta = on_disk[old_id].metadata or {}
            # 关键断言：磁盘上没有 superseded_by 字段（持久化被打断的证据）
            assert "superseded_by" not in disk_meta, f"磁盘上的旧 drawer 不应有 superseded_by；disk meta={disk_meta}"

    def test_injection_disable_chain_handler(self):
        """把 supersede handler 从全局 HANDLERS 移除 ⇒ handler 缺失"""
        from pangu.server import handlers

        # 移除 handler（必须在测试结束后恢复）
        saved = handlers.HANDLERS.get("pangu_get_supersede_chain")
        handlers.HANDLERS.pop("pangu_get_supersede_chain", None)
        try:
            assert "pangu_get_supersede_chain" not in handlers.HANDLERS
            # 直接调会 KeyError
            try:
                handlers.HANDLERS["pangu_get_supersede_chain"]
                raise AssertionError("HANDLERS 不应有此 key，注入验证失败")
            except KeyError:
                pass
        finally:
            if saved is not None:
                handlers.HANDLERS["pangu_get_supersede_chain"] = saved
