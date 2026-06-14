"""盘古 API 服务器 + MCP 集成测试"""
import json
import os
import tempfile


class TestApiServer:
    """测试 FastAPI 应用工厂"""

    def test_create_app(self):
        """测试应用创建"""
        from pangu.api.server import create_app
        app = create_app()
        assert app.title == "盘古 v0.1.0"
        assert app.version == "0.1.0"

    def test_app_has_routes(self):
        """测试应用注册了路由"""
        from pangu.api.server import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        # 应包含 health, metrics, memories
        assert any("/health" in p for p in paths)
        assert any("/api/v2" in p for p in paths)

    def test_app_cors_middleware(self):
        """测试 CORS 中间件"""
        from pangu.api.server import create_app
        app = create_app()
        # 检查中间件
        assert any("CORS" in str(m.cls) for m in app.user_middleware)


class TestMcpServerTools:
    """测试 MCP 服务器工具注册"""

    def test_tools_list_not_empty(self):
        """测试工具列表非空"""
        from pangu.server.mcp_server import MCPServer
        server = MCPServer()
        tools = server.tools
        assert len(tools) >= 50  # 至少 50 个工具

    def test_fuxi_tools_registered(self):
        """测试伏羲移植工具已注册"""
        from pangu.server.mcp_server import MCPServer
        server = MCPServer()
        tool_names = {t["name"] for t in server.tools}

        # 核心伏羲移植工具
        assert "pangu_fts_search" in tool_names
        assert "pangu_holographic_encode" in tool_names
        assert "pangu_holographic_search" in tool_names
        assert "pangu_judge_memory" in tool_names
        assert "pangu_adaptive_params" in tool_names
        assert "pangu_wm_push" in tool_names
        assert "pangu_sanitize" in tool_names
        assert "pangu_reconsolidate" in tool_names
        assert "pangu_distill_knowledge" in tool_names
        assert "pangu_attention_state" in tool_names
        assert "pangu_enhanced_contradictions" in tool_names
        assert "pangu_streaming_index" in tool_names
        assert "pangu_verify" in tool_names
        assert "pangu_privacy_stats" in tool_names

    def test_base_tools_registered(self):
        """测试基础工具已注册"""
        from pangu.server.mcp_server import MCPServer
        server = MCPServer()
        tool_names = {t["name"] for t in server.tools}

        assert "pangu_list_wings" in tool_names
        assert "pangu_add_memory" in tool_names
        assert "pangu_search_memories" in tool_names
        assert "pangu_stats" in tool_names


class TestMcpToolCalls:
    """测试 MCP 工具调用（不依赖 LLM）"""

    def test_sanitize_call(self):
        """测试脱敏工具"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_sanitize", {
            "text": "联系邮箱 test@example.com，电话 13800138000",
            "level": "standard",
        }))
        data = json.loads(result)
        assert "sanitized" in data
        assert "[EMAIL]" in data["sanitized"] or "[PHONE]" in data["sanitized"]

    def test_sanitize_check_call(self):
        """测试脱敏检查工具"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_sanitize_check", {
            "text": "<script>alert(1)</script>",
            "level": "standard",
        }))
        data = json.loads(result)
        assert data["has_xss"] is True

    def test_adaptive_params_get(self):
        """测试自适应参数获取"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_adaptive_params", {"action": "get"}))
        data = json.loads(result)
        assert "decay_base" in data
        assert "vector_weight" in data

    def test_wm_push_and_get(self):
        """测试工作记忆推入和获取"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        # 推入
        result = asyncio.run(server.call_tool("pangu_wm_push", {
            "item_id": "test_wm_001",
            "content": "测试工作记忆内容",
            "emotional_valence": 0.5,
        }))
        data = json.loads(result)
        assert data["status"] == "pushed"
        assert data["item_id"] == "test_wm_001"

        # 获取
        result = asyncio.run(server.call_tool("pangu_wm_get", {"item_id": "test_wm_001"}))
        data = json.loads(result)
        assert data["id"] == "test_wm_001"

    def test_wm_stats(self):
        """测试工作记忆统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_wm_stats", {}))
        data = json.loads(result)
        assert "capacity" in data
        assert "slots_used" in data

    def test_wm_clear(self):
        """测试工作记忆清空"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_wm_clear", {}))
        data = json.loads(result)
        assert data["status"] == "cleared"

    def test_attention_state(self):
        """测试注意力状态"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_attention_state", {}))
        data = json.loads(result)
        assert "active_strategy" in data
        assert "budget" in data

    def test_attention_switch(self):
        """测试注意力策略切换"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_attention_switch", {
            "strategy": "focus",
            "reason": "test",
        }))
        data = json.loads(result)
        assert data["new"] == "focus"

    def test_privacy_stats(self):
        """测试差分隐私统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_privacy_stats", {}))
        data = json.loads(result)
        assert "epsilon" in data
        assert "remaining_budget" in data

    def test_privatize_count(self):
        """测试隐私化计数"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_privatize_count", {"count": 100}))
        data = json.loads(result)
        assert "original" in data
        assert data["original"] == 100
        assert "privatized" in data

    def test_judge_stats(self):
        """测试记忆法官统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_judge_stats", {}))
        data = json.loads(result)
        assert "total" in data

    def test_fts_search_stats(self):
        """测试 FTS 搜索统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_fts_search_stats", {}))
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_distill_stats(self):
        """测试蒸馏统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_distill_stats", {}))
        data = json.loads(result)
        assert "total_cards" in data

    def test_vector_index_stats(self):
        """测试向量索引统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_vector_index_stats", {}))
        data = json.loads(result)
        assert "is_built" in data

    def test_streaming_stats(self):
        """测试流式索引统计"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_streaming_stats", {}))
        data = json.loads(result)
        assert "total_indexed" in data

    def test_unknown_tool(self):
        """测试未知工具返回错误"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_nonexistent_tool", {}))
        data = json.loads(result)
        assert "error" in data

    def test_config_get(self):
        """测试配置获取"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_config_get", {"key": "llm_provider"}))
        data = json.loads(result)
        assert "llm_provider" in data

    def test_schema_migrations(self):
        """测试迁移列表"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_schema_migrations", {}))
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 8

    def test_autonomous_analyze(self):
        """测试自主分析"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        result = asyncio.run(server.call_tool("pangu_autonomous_analyze", {
            "task": "帮我检索之前的记忆",
        }))
        data = json.loads(result)
        assert data["needs_memory"] is True


class TestMcpJsonRpcProtocol:
    """测试 MCP JSON-RPC 协议处理"""

    def test_initialize_method(self):
        """测试 initialize 方法"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        request = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
        }
        response = asyncio.run(server.handle_request(request))
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "protocolVersion" in response["result"]
        assert response["result"]["serverInfo"]["name"] == "pangu"

    def test_tools_list_method(self):
        """测试 tools/list 方法"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        response = asyncio.run(server.handle_request(request))
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) >= 50

    def test_tools_call_method(self):
        """测试 tools/call 方法"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        request = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "pangu_wm_clear", "arguments": {}},
        }
        response = asyncio.run(server.handle_request(request))
        assert "content" in response["result"]
        assert response["result"]["content"][0]["type"] == "text"

    def test_unknown_method(self):
        """测试未知方法返回错误"""
        import asyncio

        from pangu.server.mcp_server import MCPServer
        server = MCPServer()

        request = {"jsonrpc": "2.0", "id": 4, "method": "unknown/method"}
        response = asyncio.run(server.handle_request(request))
        assert "error" in response
        assert response["error"]["code"] == -32601


class TestFuxiPortedModules:
    """测试伏羲移植模块的基本功能"""

    def test_fts_search_module(self):
        """测试 FTS 搜索模块导入"""
        from pangu.memory.fts_search import FTS5SearchEngine
        engine = FTS5SearchEngine()
        stats = engine.get_stats()
        assert "fts_index_size" in stats
        assert "cache_size" in stats

    def test_hologram_module(self):
        """测试全息模块导入"""
        from pangu.memory.hologram import (
            HolographicEncoder,
        )
        encoder = HolographicEncoder()
        holo = encoder.encode(item_id="test", raw_text="hello world")
        assert holo.item_id == "test"
        assert "semantic" in holo.all_dims() or "temporal" in holo.all_dims()

    def test_judge_module(self):
        """测试法官模块"""
        from pangu.memory.judge import JudgmentVerdict, MemoryJudge
        judge = MemoryJudge()
        # fallback 判定
        result = judge._fallback_judgment()
        assert result.verdict == JudgmentVerdict.B
        assert judge.stats()["total"] == 0

    def test_adaptive_params_module(self):
        """测试自适应参数模块"""
        from pangu.memory.adaptive_params import (
            AdaptiveParamEngine,
        )
        engine = AdaptiveParamEngine()
        params = engine.evaluate({"total_memories": 10, "growth_rate": 0})
        assert 0.9 <= params.decay_base <= 0.99

    def test_working_memory_module(self):
        """测试工作记忆模块"""
        from pangu.memory.working_memory import WMItem, get_working_memory
        wm = get_working_memory()
        item = WMItem(id="test_wm_x", content="test")
        wm.push(item)
        retrieved = wm.get("test_wm_x")
        assert retrieved is not None
        assert retrieved.content == "test"
        wm.clear()

    def test_sanitizer_module(self):
        """测试脱敏模块"""
        from pangu.memory.sanitizer import MemorySanitizer
        sanitized, redactions = MemorySanitizer.sanitize(
            "test@example.com, 13800138000", level="strict"
        )
        assert "[EMAIL]" in sanitized
        assert "[PHONE]" in sanitized
        assert redactions["email"] == 1
        assert redactions["phone"] == 1

    def test_reconsolidation_module(self):
        """测试再巩固模块"""
        from pangu.core.palace import Drawer
        from pangu.memory.reconsolidation import ReconsolidationEngine
        engine = ReconsolidationEngine()
        from datetime import datetime, timedelta
        drawers = [
            Drawer(id="d1", content="test 1", importance=0.5,
                   created_at=(datetime.now() - timedelta(days=2)).isoformat()),
        ]
        result = engine.run(drawers, limit=10)
        assert "boosted" in result

    def test_distill_module(self):
        """测试蒸馏模块"""
        from pangu.memory.distill_enhanced import DistillationTower
        tower = DistillationTower()
        card = tower.distill(["机器学习是AI的子领域", "深度学习基于神经网络"])
        assert "knowledge_card" in card
        assert "concept" in card["knowledge_card"]

    def test_vector_index_module(self):
        """测试向量索引模块"""
        from pangu.memory.vector_index import VectorIndex
        idx = VectorIndex(dim=4)
        # 简单测试
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        ids = ["a", "b"]
        success = idx.build(vectors, ids)
        assert success
        results = idx.search([0.1, 0.2, 0.3, 0.4], top_k=2)
        assert len(results) == 2

    def test_attention_module(self):
        """测试注意力模块"""
        from pangu.memory.attention import AttentionStrategy, AttentionSystem
        attn = AttentionSystem()
        attn.switch(AttentionStrategy.FOCUS)
        assert attn.active_strategy == AttentionStrategy.FOCUS
        # 评估
        strategy = attn.evaluate(0.8, 0.0, 0.0)  # 高情感
        assert strategy in AttentionStrategy

    def test_enhanced_evaluation_module(self):
        """测试增强评估模块"""
        from pangu.core.palace import Drawer
        from pangu.memory.enhanced_evaluation import EnhancedContradictionDetector
        detector = EnhancedContradictionDetector()
        from datetime import datetime
        drawers = [
            Drawer(id="d1", content="我每天跑步", importance=0.5,
                   created_at=datetime.now().isoformat()),
            Drawer(id="d2", content="我从不运动", importance=0.5,
                   created_at=datetime.now().isoformat()),
        ]
        result = detector.detect_contradictions(drawers, top_k=2)
        assert "verdicts" in result
        assert "stats" in result

    def test_streaming_index_module(self):
        """测试流式索引模块"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from pangu.memory.streaming_index import StreamingIndexer
            indexer = StreamingIndexer(index_dir=os.path.join(tmpdir, "index"))
            stats = indexer.stats()
            assert "total_indexed" in stats

    def test_verification_module(self):
        """测试验证模块"""
        from pangu.memory.verification import VerificationLoop
        loop = VerificationLoop()
        result = loop.run_diff_review()
        assert result.phase == "diff_review"

    def test_differential_privacy_module(self):
        """测试差分隐私模块"""
        from pangu.memory.differential_privacy import DifferentialPrivacy
        dp = DifferentialPrivacy(epsilon=1.0)
        noisy = dp.add_laplace_noise(100.0, sensitivity=1.0)
        assert isinstance(noisy, float)
        # 重置
        dp.reset_budget()
        assert dp.remaining_budget == 1.0


class TestCliCommandsRegistered:
    """测试 CLI 命令注册"""

    def test_cli_import(self):
        """测试 CLI 可正常导入"""
        from pangu.cli import app
        assert app is not None

    def test_cli_has_fuxi_commands(self):
        """测试 CLI 包含伏羲移植命令"""
        from pangu.cli import app
        # 收集所有命令名
        commands = set()
        for cmd_info in app.registered_commands:
            if cmd_info.name:
                commands.add(cmd_info.name)
            if cmd_info.callback and hasattr(cmd_info.callback, "__name__"):
                commands.add(cmd_info.callback.__name__)
        # 至少包含一些核心命令（用 callback 函数名或短横线名）
        expected_keywords = ["fts", "holo", "judge", "adaptive", "wm_", "sanitize",
                            "reconsolidate", "distill", "attention", "verify",
                            "privacy", "system_health"]
        for kw in expected_keywords:
            assert any(kw in c for c in commands), f"Missing command containing: {kw}"
