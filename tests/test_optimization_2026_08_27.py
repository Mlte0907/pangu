"""PANGU 优化改进项 2026-08-27 实现验证（R1-R4 盘古侧）

覆盖：
- R1-A：cluster_by_tags / cluster_by_time / hierarchical_cluster / dedup_results 不再 NameError
- R1-B：pangu_memory_insights 不再 AttributeError（接入 PatternEngine）
- R1-C：工具级异常被 ErrorMonitor 捕获（error_stats/recent 可见），成功调用只增 total_events
- R2：未配 key 时 llm_base_url 非空 → 本地路由允许无 key 调用；两缺时保留明确提示
- R3：统一重复口径（组簇/可回收/对）同源可换算；TTL 字段语义化命名
- R4：ingest_text 兼容 content/text；delete_memory / archive_memory 行为与留痕
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer


@pytest.fixture(autouse=True)
def _reset_global_singletons():
    """每个用例前后重置按配置缓存的全局单例。

    暴露过滤器（exposure）与多模态流水线（multimodal_pipeline）都是
    模块级单例，首次使用后绑定当时的 config。本文件的用例各自用
    tmp_path 隔离配置，若不重置，第一个用例的 config 会泄漏到后续
    用例——表现为「写入成功但立刻查不到」或工具莫名 code=1002。
    """
    from pangu.memory.multimodal_pipeline import reset_multimodal_pipeline
    from pangu.server.exposure import reset_exposure_filter

    reset_exposure_filter()
    reset_multimodal_pipeline()
    yield
    reset_exposure_filter()
    reset_multimodal_pipeline()


def _make_config(tmp_path, **overrides) -> PanguConfig:
    """隔离配置：临时 palace / 关闭 LLM 缓存持久化，避免触碰 ~/.pangu 现网数据

    同时启用本文件涉及的工具所属模块。v1.0.0 引入三级工具暴露后，缺省
    只暴露 28 个核心白名单工具，其余工具在 tools/call 时返回 code=1002。
    本文件验证的是工具**功能**，故显式启用承载它们的模块。
    """
    from pangu.server.module_registry import EXPERIMENTAL_PREFIXES, MODULE_REGISTRY

    cfg = PanguConfig(
        palace_path=str(tmp_path / "palace"),
        config_path=str(tmp_path / "config.json"),
        identity_path=str(tmp_path / "identity.txt"),
        llm_cache_enabled=False,
        llm_cache_persist=False,
        llm_cache_warmup_on_start=False,
    )
    cfg.exposure.enabled_core_modules = [e.name for e in MODULE_REGISTRY if e.level == "core"]
    cfg.exposure.enabled_optional_modules = [e.name for e in MODULE_REGISTRY if e.level == "optional"]
    cfg.exposure.enabled_experiments = list(EXPERIMENTAL_PREFIXES.keys()) + ["advanced"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    cfg.ensure_dirs()
    return cfg


def _drawer(mid: str, content: str, tags=None, wing="test", room="general", importance=3.0) -> Drawer:
    return Drawer(
        id=mid,
        content=content,
        wing=wing,
        room=room,
        importance=importance,
        tags=tags or [],
        created_at="2026-01-01T00:00:00",
    )


class FakeServer:
    """handler 直接调用所需的最小子集"""

    def __init__(self, config, memory=None):
        self.config = config
        self.memory = memory if memory is not None else _FakeMemory()

    @property
    def search(self):
        return _FakeSearch()

    @property
    def llm(self):
        return _FakeLLM()


class _FakeMemory:
    def get_drawers(self):
        return []

    def get_drawer_by_id(self, drawer_id):
        return None


class _FakeSearch:
    def search(self, query, drawers, **kwargs):
        return {"results": []}


class _FakeLLM:
    async def generate_insight(self, memories):
        return "[mock insight]"

    async def summarize_memories(self, memories):
        return "[mock summary]"


# ────────────────────────────────────────────────────────────────
# R1-A：4 个受影响工具不再 NameError（真实 handler 调用 + 真实 hybrid_search）
# ────────────────────────────────────────────────────────────────


class TestR1SearchHandlers:
    @pytest.fixture(autouse=True)
    def _isolate_fts_disk(self, monkeypatch, tmp_path):
        """R1-A 用例会触发真实 hybrid_search → FTS 索引落盘；将索引路径隔离到临时目录，
        避免覆写现网 ~/.pangu/fts_index.json 缓存。"""
        from pangu.memory import fts_search

        monkeypatch.setattr(fts_search.FTS5SearchEngine, "_get_index_path", lambda self: tmp_path / "fts_index.json")

    async def _run(self, handler, cfg, drawers):
        return json.loads(await handler(FakeServer(cfg), drawers, {"query": "DSH", "limit": 5}))

    @pytest.mark.asyncio
    async def test_cluster_by_tags_ok(self, tmp_path):
        from pangu.server.handlers.search import handle_cluster_by_tags

        cfg = _make_config(tmp_path)
        drawers = [
            _drawer("a", "DSH 集成测试记忆", tags=["ds"]),
            _drawer("b", "DSH 集成测试记忆", tags=["ds"]),
            _drawer("c", "盘古记忆系统", tags=["pangu"]),
        ]
        out = await self._run(handle_cluster_by_tags, cfg, drawers)
        assert "clusters" in out
        assert isinstance(out["clusters"], list)
        assert "total_clusters" in out

    @pytest.mark.asyncio
    async def test_cluster_by_time_ok(self, tmp_path):
        from pangu.server.handlers.search import handle_cluster_by_time

        cfg = _make_config(tmp_path)
        drawers = [_drawer("a", "记忆1"), _drawer("b", "记忆2")]
        out = await self._run(handle_cluster_by_time, cfg, drawers)
        assert "clusters" in out
        assert "total_clusters" in out

    @pytest.mark.asyncio
    async def test_hierarchical_cluster_ok(self, tmp_path):
        from pangu.server.handlers.search import handle_hierarchical_cluster

        cfg = _make_config(tmp_path)
        drawers = [_drawer("a", "记忆1"), _drawer("b", "记忆2"), _drawer("c", "记忆3")]
        out = await self._run(handle_hierarchical_cluster, cfg, drawers)
        assert "clusters" in out

    @pytest.mark.asyncio
    async def test_dedup_results_ok(self, tmp_path):
        from pangu.server.handlers.search import handle_dedup_results

        cfg = _make_config(tmp_path)
        drawers = [_drawer("a", "DSH 集成测试记忆"), _drawer("b", "DSH 集成测试记忆")]
        out = await self._run(handle_dedup_results, cfg, drawers)
        assert "results" in out
        assert "removed" in out

    @pytest.mark.asyncio
    async def test_hybrid_search_importable_at_module_top(self):
        from pangu.server.handlers import search as search_mod

        assert hasattr(search_mod, "hybrid_search")


# ────────────────────────────────────────────────────────────────
# R1-B：memory_insights 返回完整结果（analysis/top_memories/patterns）
# ────────────────────────────────────────────────────────────────


class TestR1MemoryInsights:
    @pytest.mark.asyncio
    async def test_memory_insights_full_result(self, tmp_path):
        from pangu.server.handlers.search import handle_memory_insights

        cfg = _make_config(tmp_path)
        drawers = [
            _drawer("a", "DSH 集成测试记忆", tags=["dsh"]),
            _drawer("b", "盘古记忆系统", tags=["pangu"]),
        ]
        raw = await handle_memory_insights(FakeServer(cfg), drawers, {})
        out = json.loads(raw)
        assert "analysis" in out
        assert "top_memories" in out
        assert "patterns" in out
        assert "total" in out["patterns"]
        assert "items" in out["patterns"]


# ────────────────────────────────────────────────────────────────
# R1-C：工具级异常被 ErrorMonitor 捕获；成功调用不增 total_errors
# ────────────────────────────────────────────────────────────────


class TestR1ErrorStats:
    @pytest.mark.asyncio
    async def test_tool_exception_recorded(self, tmp_path, monkeypatch):
        import pangu.memory.error_monitor as emod
        import pangu.server.handlers as handlers_mod
        from pangu.server.mcp_server import MCPServer

        cfg = _make_config(tmp_path)
        # 全新 ErrorMonitor，隔离现网状态
        fresh = emod.ErrorMonitor(cfg)
        fresh._errors = []
        fresh._stats.clear()
        monkeypatch.setattr(emod, "_monitor", fresh)

        server = MCPServer(cfg)
        server._memory = _FakeMemory()
        server._ensure_initialized = lambda: None

        async def _boom(server_, drawers, arguments):
            raise RuntimeError("boom-tool-error")

        monkeypatch.setitem(handlers_mod.HANDLERS, "zz_boom_test", _boom)

        req = {
            "method": "tools/call",
            "id": 1,
            "params": {"name": "zz_boom_test", "arguments": {}},
        }
        resp = await server.handle_request(req)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert data["code"] == 5000
        assert "boom-tool-error" in data["error"]

        stats = fresh.get_stats()
        assert stats["total_errors"] >= 1
        assert "zz_boom_test" in stats["top_error_tools"]
        recent = fresh.get_recent(limit=5)
        assert any(e["tool"] == "zz_boom_test" for e in recent)


# ────────────────────────────────────────────────────────────────
# R1 e2e：真实 MCP tools/call 复现用例（对应验收「复现用例通过」）
# ────────────────────────────────────────────────────────────────


class TestR1E2EToolsCall:
    @pytest.mark.asyncio
    async def test_tools_call_cluster_by_tags_ok(self, tmp_path, monkeypatch):
        from pangu.memory import fts_search
        from pangu.memory.layers import MemoryStack
        from pangu.server.mcp_server import MCPServer

        monkeypatch.setattr(fts_search.FTS5SearchEngine, "_get_index_path", lambda self: tmp_path / "fts_index.json")
        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        stack.add_drawers(
            [_drawer("a", "DSH 集成测试记忆", tags=["ds"]), _drawer("b", "DSH 集成测试记忆", tags=["ds"])]
        )
        server = MCPServer(cfg)
        server._memory = stack
        server._ensure_initialized = lambda: None

        req = {
            "method": "tools/call",
            "id": 7,
            "params": {"name": "pangu_cluster_by_tags", "arguments": {"query": "DSH", "limit": 5}},
        }
        resp = await server.handle_request(req)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "clusters" in data
        assert "total_clusters" in data

    @pytest.mark.asyncio
    async def test_tools_call_memory_insights_ok(self, tmp_path, monkeypatch):
        from pangu.memory.layers import MemoryStack
        from pangu.server.mcp_server import MCPServer

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        stack.add_drawers([_drawer("a", "DSH 集成测试记忆", tags=["ds"])])
        server = MCPServer(cfg)
        server._memory = stack
        server._ensure_initialized = lambda: None

        req = {
            "method": "tools/call",
            "id": 8,
            "params": {"name": "pangu_memory_insights", "arguments": {}},
        }
        resp = await server.handle_request(req)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert "analysis" in data
        assert "top_memories" in data
        assert "patterns" in data

    @pytest.mark.asyncio
    async def test_success_call_grows_events_only(self, tmp_path, monkeypatch):
        import pangu.memory.error_monitor as emod
        from pangu.server.mcp_server import MCPServer

        cfg = _make_config(tmp_path)
        fresh = emod.ErrorMonitor(cfg)
        fresh._errors = []
        fresh._stats.clear()
        monkeypatch.setattr(emod, "_monitor", fresh)

        server = MCPServer(cfg)
        server._memory = _FakeMemory()
        server._ensure_initialized = lambda: None

        req = {
            "method": "tools/call",
            "id": 1,
            "params": {"name": "pangu_schema_version", "arguments": {}},
        }
        resp = await server.handle_request(req)
        assert "error" not in resp
        stats = fresh.get_stats()
        assert stats["total_errors"] == 0
        # 成功调用通过 record_success 计入 total_events（不经过 record_error）
        assert fresh._stats.get("total_events", 0) == 1
        assert stats["total_events"] == 1


# ────────────────────────────────────────────────────────────────
# R2：LLM 路由 fallback（无 key + llm_base_url 允许本地端点；两缺提示）
# ────────────────────────────────────────────────────────────────


class TestR2LLMRouting:
    @pytest.mark.asyncio
    async def test_no_key_no_base_url_keeps_missing_prompt(self, tmp_path):
        from pangu.core.llm import LLMEngine

        cfg = _make_config(tmp_path, llm_provider="openai", llm_model="gpt-4o", llm_base_url="", llm_api_key="")
        engine = LLMEngine(cfg)
        resp = await engine._call_openai_compatible("openai", [{"role": "user", "content": "hi"}])
        assert "未配置 API Key" in resp.content
        assert "llm_base_url" in resp.content  # 错误信息注明需要哪一个配置项（R2-C）

    @pytest.mark.asyncio
    async def test_no_key_with_base_url_routes_and_omits_auth_header(self, tmp_path, monkeypatch):
        from pangu.core.llm import LLMEngine

        cfg = _make_config(
            tmp_path, llm_provider="openai", llm_model="gpt-4o", llm_base_url="http://127.0.0.1:9999/v1", llm_api_key=""
        )
        engine = LLMEngine(cfg)

        captured = {}

        class _FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "本地路由内容"}}], "usage": {}}

        class _FakeClient:
            async def post(self, url, json=None, headers=None):
                captured["url"] = url
                captured["headers"] = headers
                return _FakeResp()

        engine._client = _FakeClient()
        resp = await engine._call_openai_compatible("openai", [{"role": "user", "content": "hi"}])
        assert "未配置 API Key" not in resp.content
        assert resp.content == "本地路由内容"
        assert "Authorization" not in captured["headers"]
        assert captured["url"] == "http://127.0.0.1:9999/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_env_check_reports_route(self, tmp_path, monkeypatch):
        import pangu.core.config as cmod
        import pangu.memory.production as production

        cfg = _make_config(tmp_path, llm_provider="openai", llm_base_url="http://127.0.0.1:9999/v1", llm_api_key="")
        monkeypatch.setattr(cmod.PanguConfig, "load", staticmethod(lambda: cfg))
        checks = production.check_environment()
        assert checks["llm"]["route"] == "local_base_url_no_key"
        assert checks["llm"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_config_set_accepts_llm_route_keys(self, tmp_path):
        from pangu.server.handlers.system import handle_config_set

        cfg = _make_config(tmp_path)
        server = FakeServer(cfg)
        out = json.loads(
            await handle_config_set(server, [], {"key": "llm_base_url", "value": "http://127.0.0.1:9999/v1"})
        )
        assert out["status"] == "updated"
        assert cfg.llm_base_url == "http://127.0.0.1:9999/v1"
        out2 = json.loads(await handle_config_set(server, [], {"key": "llm_api_key", "value": "sk-local"}))
        assert out2["status"] == "updated"
        assert cfg.llm_api_key == "sk-local"


# ────────────────────────────────────────────────────────────────
# R3-A：统一重复口径（组簇/可回收/对）同源可换算 + health 带标签
# ────────────────────────────────────────────────────────────────


class TestR3Duplicates:
    def test_analyze_duplicates_three_calibers_consistent(self, tmp_path):
        from pangu.memory.semantic_compression import SemanticCompressor

        cfg = _make_config(tmp_path)
        comp = SemanticCompressor(cfg)
        drawers = [
            _drawer("a", "完全相同的记忆内容", tags=["x"]),
            _drawer("b", "完全相同的记忆内容", tags=["x"]),
            _drawer("c", "完全相同的记忆内容", tags=["x"]),
            _drawer("d", "另一条完全不同的记忆", tags=["y"]),
        ]
        analysis = comp.analyze_duplicates(drawers, threshold=0.8)
        # 3 条同前缀 → 1 组，可回收 2
        assert analysis["duplicate_groups"] == 1
        assert analysis["total_recoverable"] == 2
        # 对数 = C(3,2) = 3
        assert analysis["pairs"] == 3
        assert analysis["total_memories"] == 4
        assert "algorithm" in analysis["caliber"]
        assert "threshold" in analysis["caliber"]

    def test_health_check_duplicates_labeled(self, tmp_path):
        from pangu.memory.health_monitor import HealthMonitor

        cfg = _make_config(tmp_path)
        hm = HealthMonitor(cfg)
        drawers = [
            _drawer("a", "完全相同的记忆内容", tags=["x"]),
            _drawer("b", "完全相同的记忆内容", tags=["x"]),
        ]
        check = hm.check_duplicates(drawers)
        assert "可回收条数" in check.detail
        assert "组簇" in check.detail
        assert "对数" in check.detail
        assert "口径" in check.detail

    def test_find_duplicates_output_has_caliber(self, tmp_path):
        import asyncio

        from pangu.server.handlers.quality import handle_find_duplicates as h

        cfg = _make_config(tmp_path)
        drawers = [
            _drawer("a", "完全相同的记忆内容", tags=["x"]),
            _drawer("b", "完全相同的记忆内容", tags=["x"]),
        ]
        raw = asyncio.run(h(FakeServer(cfg), drawers, {}))
        out = json.loads(raw)
        assert out["pairs"] == 1
        assert out["duplicate_groups"] == 1
        assert out["total_recoverable"] == 1
        assert "caliber" in out


# ────────────────────────────────────────────────────────────────
# R3-B：TTL 字段语义化命名
# ────────────────────────────────────────────────────────────────


class TestR3TTLNames:
    def test_memory_stack_ttl_semantic_field(self, tmp_path):
        from pangu.memory.search_cache import SearchCache

        cfg = _make_config(tmp_path)
        from pangu.memory.layers import MemoryStack

        stack = MemoryStack(cfg)
        status = stack.status()
        assert status["memory_stack_cache_ttl_seconds"] == 30.0
        assert status["cache_ttl"] == 30.0  # 兼容旧字段

        cache = SearchCache(ttl_seconds=300)
        stats = cache.get_stats()
        assert stats["search_cache_ttl_seconds"] == 300
        assert stats["ttl_seconds"] == 300


# ────────────────────────────────────────────────────────────────
# R4-A：ingest_text 兼容 content / text，缺参报明确错误
# ────────────────────────────────────────────────────────────────


class TestR4IngestText:
    """ingest_text 参数兼容 + F1 真实落库回归（检索可见、立即可删，不再假落库）"""

    @pytest.fixture(autouse=True)
    def _reset_pipeline_singleton(self, monkeypatch):
        """隔离 get_multimodal_pipeline 全局单例：每次测试重建并绑定当前 tmp 配置，
        避免跨测试的单例配置耦合导致落库位置错乱。"""
        import pangu.memory.multimodal_pipeline as pmod

        monkeypatch.setattr(pmod, "_pipeline", None)

    @pytest.mark.asyncio
    async def test_ingest_text_content_persists_and_searchable(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.multimodal import handle_ingest_text

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = FakeServer(cfg, stack)
        raw = await handle_ingest_text(
            server, stack.get_drawers(), {"content": "F1 落库验证记忆", "wing": "test", "room": "dshbench"}
        )
        out = json.loads(raw)
        assert out.get("stored") is True
        drawer_id = out.get("drawer_id") or out.get("memory_id")
        assert drawer_id
        # F1：真正落库——抽屉可检索、recall 可见（ingest_text 存储 room=modality="text"；
        # 内容可能被加密渲染，按抽屉存在性 + recall 非空判定）
        assert stack.get_drawer_by_id(drawer_id) is not None
        assert any(d.id == drawer_id for d in stack.get_drawers())
        recall_text = stack.recall(wing="test")
        assert "暂无" not in recall_text

    @pytest.mark.asyncio
    async def test_ingest_text_then_delete_immediately(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.memory_ops import handle_delete_memory
        from pangu.server.handlers.multimodal import handle_ingest_text

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = FakeServer(cfg, stack)
        raw = await handle_ingest_text(server, stack.get_drawers(), {"content": "F1 三连验证记忆", "wing": "test"})
        out = json.loads(raw)
        drawer_id = out.get("drawer_id") or out.get("memory_id")
        assert drawer_id
        # F1：立即 delete 不得再报「记忆不存在」
        del_raw = await handle_delete_memory(server, stack.get_drawers(), {"memory_id": drawer_id})
        del_out = json.loads(del_raw)
        assert del_out.get("status") == "removed", del_out
        assert stack.get_drawer_by_id(drawer_id) is None

    @pytest.mark.asyncio
    async def test_ingest_text_text_backward_compat(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.multimodal import handle_ingest_text

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = FakeServer(cfg, stack)
        raw = await handle_ingest_text(server, stack.get_drawers(), {"text": "旧参数名写入"})
        out = json.loads(raw)
        assert out.get("stored") is True
        drawer_id = out.get("drawer_id") or out.get("memory_id")
        assert drawer_id and stack.get_drawer_by_id(drawer_id) is not None

    @pytest.mark.asyncio
    async def test_ingest_text_echo_triple_via_mcp(self, tmp_path, monkeypatch):
        """t9 回声三连：ingest_text → search_memories → delete_memory（MCP tools/call 协议路径）"""
        import pangu.memory.multimodal_pipeline as pmod
        from pangu.memory.layers import MemoryStack
        from pangu.server.mcp_server import MCPServer

        monkeypatch.setattr(pmod, "_pipeline", None)
        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = MCPServer(cfg)
        server._memory = stack
        server._ensure_initialized = lambda: None

        async def call(name, args):
            resp = await server.handle_request(
                {"method": "tools/call", "id": 1, "params": {"name": name, "arguments": args}}
            )
            return json.loads(resp["result"]["content"][0]["text"])

        # 1) ingest_text 落库
        r1 = await call("pangu_ingest_text", {"content": "t9 回声三连验证记忆", "wing": "tech", "tags": ["t9"]})
        did = r1.get("drawer_id") or r1.get("memory_id")
        assert r1.get("stored") is True and did
        # 2) search_memories 可检索
        r2 = json.dumps(await call("pangu_search_memories", {"query": "t9 回声三连", "wing": "tech"}))
        assert did in r2 or "t9 回声三连" in r2
        # 3) delete_memory 立即可删（不得「记忆不存在」）
        r3 = await call("pangu_delete_memory", {"memory_id": did})
        assert r3.get("status") == "removed", r3
        assert stack.get_drawer_by_id(did) is None

    @pytest.mark.asyncio
    async def test_ingest_text_missing_arg_error(self, tmp_path):
        from pangu.server.handlers.multimodal import handle_ingest_text

        cfg = _make_config(tmp_path)
        raw = await handle_ingest_text(FakeServer(cfg), [], {})
        out = json.loads(raw)
        assert "error" in out
        assert "content" in out["error"]

    def test_ingest_text_schema_registered(self):
        from pangu.server.handlers import _TOOL_SCHEMAS

        schema = _TOOL_SCHEMAS["pangu_ingest_text"]
        assert "content" in schema["required"]
        assert "text" in schema["properties"]


# ────────────────────────────────────────────────────────────────
# R4-B/C：delete_memory / archive_memory 行为与留痕
# ────────────────────────────────────────────────────────────────


class TestR4DeleteArchive:
    @pytest.mark.asyncio
    async def test_delete_memory_removes(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.memory_ops import handle_delete_memory

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        d = _drawer("mem_del_1", "待删除记忆", wing="test", room="dshbench")
        stack.add_drawer(d)
        assert stack.get_drawer_by_id("mem_del_1") is not None

        server = FakeServer(cfg, stack)
        raw = await handle_delete_memory(server, stack.get_drawers(), {"memory_id": "mem_del_1"})
        out = json.loads(raw)
        assert out["status"] == "removed"
        assert out["removed"] is True
        # 删除后 recall/search 不再可见
        assert stack.get_drawer_by_id("mem_del_1") is None
        assert "mem_del_1" not in stack.recall(wing="test")

    @pytest.mark.asyncio
    async def test_delete_memory_missing_id_error(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.memory_ops import handle_delete_memory

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = FakeServer(cfg, stack)
        raw = await handle_delete_memory(server, stack.get_drawers(), {"memory_id": "no_such_id"})
        out = json.loads(raw)
        assert out["code"] == 2001
        assert "不存在" in out["error"]

    @pytest.mark.asyncio
    async def test_archive_memory_excludes_and_visible_in_archive(self, tmp_path):
        from pangu.memory.adaptive_forgetting import get_forgetting
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.memory_ops import handle_archive_memory

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        d = _drawer("mem_arc_1", "待归档记忆", wing="test", room="dshbench", tags=["t"])
        stack.add_drawer(d)

        server = FakeServer(cfg, stack)
        raw = await handle_archive_memory(server, stack.get_drawers(), {"memory_id": "mem_arc_1"})
        out = json.loads(raw)
        assert out["status"] == "archived"

        # 移出正常搜索/recall
        assert stack.get_drawer_by_id("mem_arc_1") is None
        # pangu_get_archive 可见（同一持久化归档单例）
        af = get_forgetting(cfg)
        archive = af.get_archive(limit=100)
        assert any(e["id"] == "mem_arc_1" for e in archive)
        # 持久化文件存在（跨重启不丢）；路径以归档单例实际绑定为准
        assert af._archive_file is not None and af._archive_file.exists()
        saved = json.loads(af._archive_file.read_text(encoding="utf-8"))
        assert any(e["id"] == "mem_arc_1" for e in saved)

    @pytest.mark.asyncio
    async def test_archive_memory_missing_id_error(self, tmp_path):
        from pangu.memory.layers import MemoryStack
        from pangu.server.handlers.memory_ops import handle_archive_memory

        cfg = _make_config(tmp_path)
        stack = MemoryStack(cfg)
        server = FakeServer(cfg, stack)
        raw = await handle_archive_memory(server, stack.get_drawers(), {"memory_id": "no_such_id"})
        out = json.loads(raw)
        assert out["code"] == 2001

    def test_new_tools_schema_and_registration(self):
        from pangu.server.handlers import _TOOL_SCHEMAS, HANDLERS, TOOLS

        names = {t["name"] for t in TOOLS}
        assert "pangu_delete_memory" in names
        assert "pangu_archive_memory" in names
        assert "pangu_delete_memory" in HANDLERS
        assert "pangu_archive_memory" in HANDLERS
        for tool in ("pangu_delete_memory", "pangu_archive_memory"):
            schema = _TOOL_SCHEMAS[tool]
            assert schema["required"] == ["memory_id"]
        # 不破坏既有 421+2 结构（无重名、schema 合规）
        assert len(names) == len(TOOLS)


def test_semantic_duplicates_skip_encrypted():
    """Fernet 密文共享标签不应被聚类为语义重复（遗留项修复：加密误报）"""
    from pangu.memory.layers import Drawer
    from pangu.memory.semantic_compression import SemanticCompressor

    comp = SemanticCompressor()
    # 5 条加密内容 + 共享 self_improve/tool_usage 标签
    encrypted = [
        Drawer(
            id=f"enc{i}",
            content=f"gAAAAAB{i:032d}encryptedblob{i}",
            tags=["self_improve", "tool_usage"],
            importance=1,
            wing="default",
            room="general",
        )
        for i in range(5)
    ]
    dups = comp.find_semantic_duplicates(encrypted, threshold=0.8)
    assert dups == [], f"encrypted memories must not be flagged: {dups}"

    # 明文相同前缀仍应被检出
    plain = [
        Drawer(
            id=f"p{i}",
            content="這是一段完全相同的記憶內容 test abc",
            tags=["x"],
            importance=1,
            wing="default",
            room="general",
        )
        for i in range(2)
    ]
    dups2 = comp.find_semantic_duplicates(plain)
    assert len(dups2) == 1, f"plain prefix dup should be found: {dups2}"
