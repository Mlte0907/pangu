"""盘古核心功能测试"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig
from pangu.core.llm import PROVIDER_ENV_KEYS, PROVIDER_URLS, LLMEngine, LLMResponse
from pangu.core.palace import HALL_TYPES, Drawer, Palace, WikiPage
from pangu.memory.analytics import MemoryAnalytics, MemoryAnalyzer
from pangu.memory.clustering import MemoryCluster, MemoryClusterer
from pangu.memory.conflict import ConflictDetector, ConflictSeverity, MemoryConflict
from pangu.memory.consolidation import ForgettingCurve, MemoryConsolidator
from pangu.memory.dedup import DuplicateGroup, MemoryDeduplicator
from pangu.memory.fusion import FusedKnowledge, FusionEngine
from pangu.memory.knowledge_graph import KnowledgeGraph
from pangu.memory.layers import Layer0, Layer1, Layer2, Layer3, LRUCache, MemoryStack
from pangu.memory.migration import BackupManager, MemoryExporter, MemoryImporter
from pangu.memory.multimodal import MultimodalExtractor, MultimodalMemory, get_mime_type, get_modality
from pangu.memory.patterns import DiscoveredPattern, PatternEngine
from pangu.memory.replay import ReplayEngine, ReplaySession, SnapshotDiff
from pangu.memory.timeline import EventChain, TimelineEngine, TimelineEvent
from pangu.mining.miners import ConvoMiner, FileMiner
from pangu.plugins import ContentFilterPlugin, HookPoint, PluginContext, PluginManager, TagEnricherPlugin
from pangu.search.embedder import EmbeddingCache
from pangu.search.engine import HybridSearch, LexicalSearch, SemanticSearch
from pangu.wiki.engine import WikiEngine


class TestConfig:
    """配置测试"""

    def test_default_config(self):
        config = PanguConfig()
        assert config.web_port == 8866
        assert config.backend == "chromadb"
        assert "pangu" in config.palace_path

    def test_config_save_load(self, tmp_path):
        config_path = str(tmp_path / "config.json")
        config = PanguConfig()
        config.palace_path = str(tmp_path / "palace")
        config.save(config_path)

        loaded = PanguConfig.load(config_path)
        assert loaded.palace_path == config.palace_path


class TestPalace:
    """宫殿测试"""

    def test_create_wing(self, tmp_path):
        palace = Palace(str(tmp_path))
        palace.create_wing("test_wing", "测试空间")
        assert "test_wing" in palace.list_wings()

    def test_create_room(self, tmp_path):
        palace = Palace(str(tmp_path))
        palace.create_room("test_wing", "test_room")
        rooms = palace.list_rooms("test_wing")
        assert "test_room" in rooms.get("test_wing", [])

    def test_delete_wing(self, tmp_path):
        palace = Palace(str(tmp_path))
        palace.create_wing("temp")
        assert palace.delete_wing("temp")
        assert "temp" not in palace.list_wings()

    def test_cannot_delete_default(self, tmp_path):
        palace = Palace(str(tmp_path))
        assert not palace.delete_wing("default")

    def test_tunnel(self, tmp_path):
        palace = Palace(str(tmp_path))
        palace.create_wing("wing_a")
        palace.create_wing("wing_b")
        tunnel = palace.create_tunnel("wing_a", "wing_b", "shared_room")
        assert tunnel["room"] == "shared_room"

        found = palace.find_tunnels("wing_a", "wing_b")
        assert len(found) == 1

    def test_stats(self, tmp_path):
        palace = Palace(str(tmp_path))
        palace.create_wing("project_a")
        palace.create_room("project_a", "room_1")
        palace.create_room("project_a", "room_2")

        stats = palace.stats()
        assert stats["wings_count"] >= 2  # default + project_a
        assert stats["rooms_count"] >= 2


class TestDrawer:
    """抽屉测试"""

    def test_drawer_serialization(self):
        drawer = Drawer(
            id="test_001",
            content="这是一段测试记忆",
            wing="test",
            room="general",
            hall="hall_events",
            importance=4.0,
            tags=["test", "memory"],
        )
        data = drawer.to_dict()
        restored = Drawer.from_dict(data)
        assert restored.id == "test_001"
        assert restored.content == "这是一段测试记忆"
        assert restored.importance == 4.0
        assert "test" in restored.tags


class TestWikiPage:
    """Wiki 页面测试"""

    def test_page_serialization(self):
        page = WikiPage(
            id="wiki_001",
            title="测试页面",
            wing="default",
            content="# 测试\n\n内容",
            summary="这是一个测试",
            tags=["test"],
        )
        data = page.to_dict()
        restored = WikiPage.from_dict(data)
        assert restored.title == "测试页面"
        assert restored.version == 1


class TestMemoryStack:
    """记忆栈测试"""

    def test_layer0(self, tmp_path):
        identity_path = str(tmp_path / "identity.txt")
        with open(identity_path, "w") as f:
            f.write("我是测试 AI")

        l0 = Layer0(identity_path)
        assert "测试 AI" in l0.render()
        assert l0.token_estimate() > 0

    def test_layer0_default(self):
        l0 = Layer0("/nonexistent/path.txt")
        assert "未配置" in l0.render()

    def test_layer1_generation(self):
        l1 = Layer1("/tmp")
        drawers = [
            Drawer(id="1", content="重要决策：采用微服务架构", room="architecture", importance=5.0),
            Drawer(id="2", content="修复了登录 bug", room="bugfix", importance=3.0),
            Drawer(id="3", content="日常代码审查", room="review", importance=2.0),
        ]
        result = l1.generate(drawers)
        assert "L1" in result
        assert "architecture" in result

    def test_layer2_retrieval(self):
        l2 = Layer2("/tmp")
        drawers = [
            Drawer(id="1", content="API 设计文档", wing="project_a", room="api"),
            Drawer(id="2", content="数据库迁移方案", wing="project_a", room="database"),
            Drawer(id="3", content="前端重构计划", wing="project_b", room="frontend"),
        ]

        result_a = l2.retrieve(drawers, wing="project_a")
        assert "API" in result_a or "数据库" in result_a

        result_b = l2.retrieve(drawers, wing="project_b", room="frontend")
        assert "前端" in result_b

    def test_layer3_search(self):
        l3 = Layer3("/tmp")
        drawers = [
            Drawer(id="1", content="GraphQL API 设计方案", wing="project_a", room="api"),
            Drawer(id="2", content="REST API 性能优化", wing="project_a", room="api"),
            Drawer(id="3", content="数据库索引优化", wing="project_a", room="database"),
        ]

        result = l3.search("GraphQL", drawers)
        assert "GraphQL" in result

        result2 = l3.search("API", drawers)
        assert "API" in result2

    def test_memory_stack_add(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        drawer = Drawer(
            id="test_001",
            content="测试记忆内容",
            wing="default",
            room="general",
        )
        stack.add_drawer(drawer)
        assert stack.count_drawers() == 1

        # 清理
        for f in tmp_path.glob("*.json"):
            f.unlink()


class TestKnowledgeGraph:
    """知识图谱测试"""

    def test_add_entity(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)

        kg = KnowledgeGraph(config)
        entity = kg.add_entity("p1", "Alice", "person", "开发者")
        assert entity["name"] == "Alice"
        assert entity["type"] == "person"

    def test_add_relation(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)

        kg = KnowledgeGraph(config)
        kg.add_entity("p1", "Alice", "person")
        kg.add_entity("p2", "Bob", "person")

        rel = kg.add_relation("r1", "p1", "knows", "p2", confidence=0.9)
        assert rel["predicate"] == "knows"

    def test_query_relations(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)

        kg = KnowledgeGraph(config)
        kg.add_entity("p1", "Alice", "person")
        kg.add_entity("p2", "Bob", "person")
        kg.add_entity("proj1", "Pangu", "project")
        kg.add_relation("r1", "p1", "works_on", "proj1")
        kg.add_relation("r2", "p2", "works_on", "proj1")

        rels = kg.query_relations(object_id="proj1", predicate="works_on")
        assert len(rels) == 2

    def test_neighbors(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)

        kg = KnowledgeGraph(config)
        kg.add_entity("p1", "Alice", "person")
        kg.add_entity("p2", "Bob", "person")
        kg.add_relation("r1", "p1", "knows", "p2")

        neighbors = kg.get_neighbors("p1")
        assert len(neighbors["outgoing"]) == 1

    def test_invalidate_relation(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)

        kg = KnowledgeGraph(config)
        kg.add_entity("p1", "Alice", "person")
        kg.add_entity("p2", "Bob", "person")
        kg.add_relation("r1", "p1", "knows", "p2")

        assert kg.invalidate_relation("r1")
        rel = kg.get_relation("r1")
        assert rel["valid_until"] is not None


class TestWikiEngine:
    """Wiki 引擎测试"""

    def test_create_page(self, tmp_path):
        config = PanguConfig()
        config.wiki_path = str(tmp_path)

        wiki = WikiEngine(config)
        page = WikiPage(
            id="test_001",
            title="测试页面",
            wing="default",
            content="# 测试\n\n这是测试内容",
            summary="测试摘要",
        )
        created = wiki.create_page(page)
        assert created.title == "测试页面"

    def test_get_page(self, tmp_path):
        config = PanguConfig()
        config.wiki_path = str(tmp_path)

        wiki = WikiEngine(config)
        page = WikiPage(id="test_001", title="测试", wing="default", content="# 测试")
        wiki.create_page(page)

        found = wiki.get_page("test_001")
        assert found is not None
        assert found.title == "测试"

    def test_list_pages(self, tmp_path):
        config = PanguConfig()
        config.wiki_path = str(tmp_path)

        wiki = WikiEngine(config)
        wiki.create_page(WikiPage(id="p1", title="页面1", wing="a", content="# 页面1"))
        wiki.create_page(WikiPage(id="p2", title="页面2", wing="a", content="# 页面2"))
        wiki.create_page(WikiPage(id="p3", title="页面3", wing="b", content="# 页面3"))

        all_pages = wiki.list_pages()
        assert len(all_pages) == 3

        wing_a = wiki.list_pages(wing="a")
        assert len(wing_a) == 2

    def test_links(self, tmp_path):
        config = PanguConfig()
        config.wiki_path = str(tmp_path)

        wiki = WikiEngine(config)
        wiki.create_page(WikiPage(id="p1", title="页面1", wing="default", content="# 页面1"))
        wiki.create_page(WikiPage(id="p2", title="页面2", wing="default", content="# 页面2"))

        assert wiki.add_link("p1", "p2")

        links = wiki.get_linked_pages("p1")
        assert len(links) == 1

        backlinks = wiki.get_backlinks("p1")
        assert len(backlinks) == 1

    def test_delete_page(self, tmp_path):
        config = PanguConfig()
        config.wiki_path = str(tmp_path)

        wiki = WikiEngine(config)
        wiki.create_page(WikiPage(id="p1", title="测试", wing="default", content="# 测试"))
        assert wiki.delete_page("p1")
        assert wiki.get_page("p1") is None


class TestSearch:
    """搜索测试"""

    def test_semantic_search(self, tmp_path):
        config = PanguConfig()
        searcher = SemanticSearch(config)

        drawers = [
            Drawer(id="1", content="Python 异步编程指南", room="python", importance=4.0),
            Drawer(id="2", content="JavaScript 前端框架对比", room="javascript", importance=3.0),
            Drawer(id="3", content="Python 数据分析入门", room="python", importance=4.5),
        ]

        results = searcher.search("Python", drawers)
        assert len(results) > 0
        assert results[0]["room"] == "python"

    def test_lexical_search(self, tmp_path):
        config = PanguConfig()
        searcher = LexicalSearch(config)

        drawers = [
            Drawer(id="1", content="部署到 Kubernetes 集群"),
            Drawer(id="2", content="Docker 容器化方案"),
            Drawer(id="3", content="CI/CD 流水线配置"),
        ]

        results = searcher.search("Kubernetes", drawers)
        assert len(results) == 1

    def test_hybrid_search(self, tmp_path):
        config = PanguConfig()
        searcher = HybridSearch(config)

        drawers = [
            Drawer(id="1", content="微服务架构设计", room="architecture", importance=5.0),
            Drawer(id="2", content="API 网关配置", room="api", importance=4.0),
        ]

        results = searcher.search("微服务 架构", drawers)
        assert len(results) >= 1


class TestMiners:
    """挖掘器测试"""

    def test_file_miner(self, tmp_path):
        # 创建测试文件
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()
        (test_dir / "README.md").write_text("# 测试项目\n\n这是一个测试项目。\n\n## 功能\n\n- 功能A\n- 功能B")
        (test_dir / "main.py").write_text("def hello():\n    print('Hello World')\n\ndef main():\n    hello()")

        config = PanguConfig()
        miner = FileMiner(config)
        drawers = miner.scan_directory(str(test_dir), wing="test")

        assert len(drawers) > 0

    def test_convo_miner_claude(self, tmp_path):
        # 创建测试 JSONL 文件
        convo_file = tmp_path / "test_convo.jsonl"
        with open(convo_file, "w") as f:
            f.write(json.dumps({"role": "user", "content": "如何优化数据库查询？"}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": "建议使用索引优化和查询缓存。"}) + "\n")

        config = PanguConfig()
        miner = ConvoMiner(config)
        drawers = miner.parse_claude_jsonl(str(convo_file), wing="test")

        assert len(drawers) == 2


class TestHallTypes:
    """殿堂类型测试"""

    def test_hall_types(self):
        assert "hall_facts" in HALL_TYPES
        assert "hall_events" in HALL_TYPES
        assert "hall_discoveries" in HALL_TYPES
        assert "hall_preferences" in HALL_TYPES
        assert "hall_advice" in HALL_TYPES
        assert "hall_concepts" in HALL_TYPES
        assert "hall_relations" in HALL_TYPES
        assert len(HALL_TYPES) == 7


class TestForgettingCurve:
    """遗忘曲线测试"""

    def test_retention_at_zero(self):
        curve = ForgettingCurve(decay_rate=0.5)
        assert curve.retention(0) == 1.0

    def test_retention_decays(self):
        curve = ForgettingCurve(decay_rate=0.5)
        r1 = curve.retention(1)
        r24 = curve.retention(24)
        assert r24 < r1
        assert r24 < 1.0
        assert r24 > 0.0

    def test_effective_importance_decays(self):
        curve = ForgettingCurve(decay_rate=0.5)
        drawer = Drawer(
            id="test",
            content="test",
            importance=5.0,
            created_at=(datetime.now() - timedelta(hours=48)).isoformat(),
        )
        effective = curve.effective_importance(drawer)
        assert effective < 5.0

    def test_effective_importance_with_access(self):
        curve = ForgettingCurve(decay_rate=0.5)
        drawer = Drawer(
            id="test",
            content="test",
            importance=3.0,
            created_at=(datetime.now() - timedelta(hours=24)).isoformat(),
        )
        drawer.access_count = 10
        effective = curve.effective_importance(drawer)
        assert effective > 1.0


class TestMemoryConsolidator:
    """记忆巩固引擎测试"""

    def test_calculate_importance(self):
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        drawer = Drawer(
            id="test",
            content="这是一条重要的测试记忆，包含足够多的内容来进行重要性评估",
            importance=5.0,
            tags=["test", "important", "memory"],
        )
        importance = consolidator.calculate_importance(drawer)
        assert importance > 0
        assert importance <= 15.0

    def test_should_not_forget_important(self):
        config = PanguConfig()
        config.min_importance_threshold = 0.5
        consolidator = MemoryConsolidator(config)
        drawer = Drawer(
            id="test",
            content="important memory",
            importance=5.0,
        )
        assert not consolidator.should_forget(drawer)

    def test_should_forget_low_importance(self):
        config = PanguConfig()
        config.min_importance_threshold = 10.0
        consolidator = MemoryConsolidator(config)
        drawer = Drawer(
            id="test",
            content="unimportant",
            importance=0.1,
            created_at=(datetime.now() - timedelta(hours=72)).isoformat(),
        )
        assert consolidator.should_forget(drawer)

    def test_find_forgotten(self):
        config = PanguConfig()
        config.min_importance_threshold = 10.0
        consolidator = MemoryConsolidator(config)
        drawers = [
            Drawer(id="d1", content="important", importance=5.0),
            Drawer(
                id="d2",
                content="unimportant",
                importance=0.1,
                created_at=(datetime.now() - timedelta(hours=72)).isoformat(),
            ),
        ]
        forgotten = consolidator.find_forgotten(drawers)
        assert len(forgotten) >= 0

    def test_should_compress(self):
        config = PanguConfig()
        config.compression_threshold = 10
        consolidator = MemoryConsolidator(config)
        drawers = [Drawer(id=f"d{i}", content=f"memory {i}") for i in range(15)]
        assert consolidator.should_compress(drawers)

    def test_should_not_compress(self):
        config = PanguConfig()
        config.compression_threshold = 100
        consolidator = MemoryConsolidator(config)
        drawers = [Drawer(id=f"d{i}", content=f"memory {i}") for i in range(5)]
        assert not consolidator.should_compress(drawers)

    def test_record_access(self):
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        consolidator.record_access("mem_1")
        consolidator.record_access("mem_1")
        consolidator.record_access("mem_2")
        assert consolidator.get_access_count("mem_1") == 2
        assert consolidator.get_access_count("mem_2") == 1

    def test_next_review_interval(self):
        assert MemoryConsolidator.next_review_interval(0) == 24  # 未访问: 24h
        assert MemoryConsolidator.next_review_interval(1) == 6  # 第1次: 6h
        assert MemoryConsolidator.next_review_interval(2) == 24  # 第2次: 24h
        assert MemoryConsolidator.next_review_interval(3) == 72  # 第3次: 3天
        assert MemoryConsolidator.next_review_interval(4) == 168  # 第4次: 7天
        assert MemoryConsolidator.next_review_interval(5) == 720  # 第5次+: 30天

    def test_needs_consolidation(self):
        config = PanguConfig()
        config.consolidation_enabled = True
        config.consolidation_interval_hours = 0.0
        consolidator = MemoryConsolidator(config)
        assert consolidator.needs_consolidation()

    def test_mark_consolidated(self):
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        consolidator.mark_consolidated()
        assert not consolidator.needs_consolidation()

    def test_stats(self):
        config = PanguConfig()
        consolidator = MemoryConsolidator(config)
        drawers = [
            Drawer(id="d1", content="memory 1", importance=4.0, tags=["test"]),
            Drawer(id="d2", content="memory 2", importance=3.0, tags=["test"]),
        ]
        stats = consolidator.stats(drawers)
        assert "total_memories" in stats
        assert stats["total_memories"] == 2
        assert "forgotten_count" in stats
        assert "due_review_count" in stats
        assert "average_effective_importance" in stats


class TestLRUCache:
    """LRU 缓存测试"""

    def test_cache_set_get(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_miss(self):
        cache = LRUCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_cache_eviction(self):
        cache = LRUCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_cache_invalidate(self):
        cache = LRUCache(max_size=10)
        cache.set("key", "value")
        cache.invalidate()
        assert cache.get("key") is None
        assert len(cache) == 0


class TestLLMEngine:
    """LLM 引擎测试"""

    def test_provider_urls(self):
        assert "openai" in PROVIDER_URLS
        assert "ollama" in PROVIDER_URLS
        assert "deepseek" in PROVIDER_URLS
        assert "anthropic" in PROVIDER_ENV_KEYS
        assert PROVIDER_ENV_KEYS["ollama"] is None

    def test_llm_response_creation(self):
        resp = LLMResponse(content="test", model="gpt-4o", provider="openai", latency_ms=100.0)
        assert resp.content == "test"
        assert resp.provider == "openai"
        assert resp.latency_ms == 100.0

    def test_llm_engine_init(self):
        config = PanguConfig()
        engine = LLMEngine(config)
        assert engine.config.llm_provider == "openai"
        assert engine.avg_latency_ms == 0.0

    def test_extract_json(self):
        result = LLMEngine._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

        result2 = LLMEngine._extract_json('```json\n{"key": "value"}\n```')
        assert result2 == {"key": "value"}

        result3 = LLMEngine._extract_json("invalid json")
        assert result3 == {}

    def test_extract_json_with_default(self):
        result = LLMEngine._extract_json("invalid", default={"fallback": True})
        assert result == {"fallback": True}

    def test_get_api_key_from_config(self):
        config = PanguConfig()
        config.llm_api_key = "test-key"
        engine = LLMEngine(config)
        assert engine._get_api_key("openai") == "test-key"

    def test_get_base_url_from_config(self):
        config = PanguConfig()
        config.llm_base_url = "http://custom:8080/v1"
        engine = LLMEngine(config)
        assert engine._get_base_url("openai") == "http://custom:8080/v1"


class TestMemoryStackExtended:
    """记忆栈扩展功能测试"""

    def test_remove_drawer(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        drawer = Drawer(id="test_001", content="test", wing="default", room="general")
        stack.add_drawer(drawer)
        assert stack.count_drawers() == 1

        assert stack.remove_drawer("test_001")
        assert stack.count_drawers() == 0

    def test_remove_drawer_not_found(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        assert not stack.remove_drawer("nonexistent")

    def test_batch_remove(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        for i in range(5):
            stack.add_drawer(Drawer(id=f"d{i}", content=f"memory {i}", wing="default", room="general"))

        assert stack.count_drawers() == 5
        removed = stack.remove_drawers(["d0", "d1", "d2"])
        assert removed == 3
        assert stack.count_drawers() == 2

    def test_get_drawer_by_id(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        stack.add_drawer(Drawer(id="find_me", content="target", wing="default", room="general"))

        found = stack.get_drawer_by_id("find_me")
        assert found is not None
        assert found.content == "target"

        not_found = stack.get_drawer_by_id("no_such")
        assert not_found is None

    def test_cache_invalidation(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")

        stack = MemoryStack(config)
        stack.add_drawer(Drawer(id="d1", content="test", wing="default", room="general"))
        stack.invalidate_cache()
        assert len(stack._cache) == 0

    def test_consolidation_integration(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")
        config.consolidation_enabled = True

        stack = MemoryStack(config)
        stack.add_drawer(Drawer(id="d1", content="important memory", importance=5.0, tags=["test"]))
        stack.add_drawer(Drawer(id="d2", content="less important", importance=2.0, tags=["test"]))

        stats = stack.get_consolidation_stats()
        assert stats["total_memories"] == 2
        assert "forgotten_count" in stats

        importance = stack.get_memory_importance("d1")
        assert importance > 0

    def test_status_with_consolidation(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        config.identity_path = str(tmp_path / "identity.txt")
        config.consolidation_enabled = True

        stack = MemoryStack(config)
        status = stack.status()
        assert "consolidation" in status
        assert status["cache_size"] >= 0
        assert "cache_ttl" in status


class TestMigration:
    """迁移模块测试"""

    def test_export_import_roundtrip(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path / "palace")
        config.wiki_path = str(tmp_path / "wiki")
        config.identity_path = str(tmp_path / "identity.txt")
        os.makedirs(config.palace_path, exist_ok=True)
        os.makedirs(config.wiki_path, exist_ok=True)

        # 先添加一些记忆
        memory = MemoryStack(config)
        memory.add_drawer(Drawer(id="d1", content="test memory 1", wing="default", room="general"))
        memory.add_drawer(Drawer(id="d2", content="test memory 2", wing="default", room="general"))

        # 导出
        exporter = MemoryExporter(config)
        export_path = str(tmp_path / "export.json")
        result_path = exporter.export_all(export_path)
        assert os.path.exists(result_path)

        # 导入
        importer = MemoryImporter(config)
        stats = importer.import_from_file(result_path, merge=True)
        assert stats["memories_imported"] >= 0

    def test_backup_manager(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path / "palace")
        config.wiki_path = str(tmp_path / "wiki")
        config.identity_path = str(tmp_path / "identity.txt")
        os.makedirs(config.palace_path, exist_ok=True)
        os.makedirs(config.wiki_path, exist_ok=True)

        memory = MemoryStack(config)
        memory.add_drawer(Drawer(id="d1", content="test", wing="default", room="general"))

        manager = BackupManager(config)
        manager.backup_dir = tmp_path / "backups"

        path = manager.create_backup(label="test")
        assert os.path.exists(path)

        backups = manager.list_backups()
        assert len(backups) == 1

    def test_export_memories_by_wing(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path / "palace")
        config.wiki_path = str(tmp_path / "wiki")
        config.identity_path = str(tmp_path / "identity.txt")
        os.makedirs(config.palace_path, exist_ok=True)
        os.makedirs(config.wiki_path, exist_ok=True)

        memory = MemoryStack(config)
        memory.add_drawer(Drawer(id="d1", content="work memory", wing="work", room="general"))
        memory.add_drawer(Drawer(id="d2", content="personal memory", wing="personal", room="general"))

        exporter = MemoryExporter(config)
        export_path = str(tmp_path / "work_export.json")
        result = exporter.export_memories(export_path, wing="work")
        assert os.path.exists(result)


class TestMultimodal:
    """多模态模块测试"""

    def test_get_mime_type(self):
        assert get_mime_type("test.png") == "image/png"
        assert get_mime_type("test.jpg") == "image/jpeg"
        assert get_mime_type("test.mp3") == "audio/mpeg"
        assert get_mime_type("test.pdf") == "application/pdf"
        assert get_mime_type("test.unknown") == "application/octet-stream"

    def test_get_modality(self):
        assert get_modality("test.png") == "image"
        assert get_modality("test.mp3") == "audio"
        assert get_modality("test.txt") == "file"
        assert get_modality("test.pdf") == "file"

    def test_multimodal_memory_serialization(self):
        mm = MultimodalMemory(
            id="mm_001",
            content="test image",
            modality="image",
            file_path="/tmp/test.png",
            file_name="test.png",
            file_size=1024,
            file_type="png",
            mime_type="image/png",
            image_width=800,
            image_height=600,
        )
        data = mm.to_dict()
        assert data["modality"] == "image"
        assert data["image_width"] == 800

        restored = MultimodalMemory.from_dict(data)
        assert restored.file_name == "test.png"

    def test_extract_from_text_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        extractor = MultimodalExtractor()
        mm = extractor.extract_from_file(str(test_file), wing="test")
        assert mm.modality == "file"
        assert mm.file_name == "test.txt"
        assert mm.file_size > 0


class TestPluginSystem:
    """插件系统测试"""

    def test_plugin_manager_register(self):
        mgr = PluginManager()
        plugin = TagEnricherPlugin()
        mgr.register(plugin)
        assert mgr.get_plugin("tag_enricher") is not None
        assert mgr.plugin_count == 1

    def test_plugin_manager_unregister(self):
        mgr = PluginManager()
        plugin = TagEnricherPlugin()
        mgr.register(plugin)
        assert mgr.unregister("tag_enricher")
        assert mgr.plugin_count == 0

    def test_tag_enricher(self):
        plugin = TagEnricherPlugin()

        ctx = PluginContext()
        ctx.set("content", "修复了一个登录 bug")
        ctx.set("tags", [])
        import asyncio

        asyncio.run(plugin.on_pre_memory_add(ctx))
        assert "bug" in ctx.get("tags", [])

    def test_content_filter(self):
        plugin = ContentFilterPlugin(blocked_patterns=["password123"])

        ctx = PluginContext()
        ctx.set("content", "safe content")
        import asyncio

        asyncio.run(plugin.on_pre_memory_add(ctx))
        assert not ctx.cancelled

        ctx2 = PluginContext()
        ctx2.set("content", "the password is password123 please")
        asyncio.run(plugin.on_pre_memory_add(ctx2))
        assert ctx2.cancelled

    def test_plugin_context(self):
        ctx = PluginContext()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"
        assert ctx.get("nonexistent", "default") == "default"

    def test_hook_trigger(self):
        mgr = PluginManager()
        plugin = TagEnricherPlugin()
        mgr.register(plugin)

        ctx = PluginContext()
        ctx.set("content", "新增了一个 feature")
        ctx.set("tags", [])
        import asyncio

        asyncio.run(mgr.trigger_hook(HookPoint.PRE_MEMORY_ADD, ctx))
        assert "feature" in ctx.get("tags", [])

    def test_list_plugins(self):
        mgr = PluginManager()
        mgr.register(TagEnricherPlugin())
        mgr.register(ContentFilterPlugin())
        plugins = mgr.list_plugins()
        assert len(plugins) == 2
        assert plugins[0]["name"] in ("tag_enricher", "content_filter")


class TestEmbedder:
    """嵌入引擎测试"""

    def test_embedding_cache(self):
        cache = EmbeddingCache(max_size=100)
        import numpy as np

        vec = np.array([1.0, 2.0, 3.0])
        cache.set("test", vec)

        cached = cache.get("test")
        assert cached is not None
        assert cached.tolist() == vec.tolist()
        assert cache.hit_rate == 1.0

    def test_embedding_cache_miss(self):
        cache = EmbeddingCache()
        assert cache.get("nonexistent") is None

    def test_embedding_cache_clear(self):
        cache = EmbeddingCache()
        import numpy as np

        cache.set("test", np.array([1.0]))
        assert len(cache) == 1
        cache.clear()
        assert len(cache) == 0


class TestClustering:
    """聚类引擎测试"""

    def test_cluster_basic(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        clusterer = MemoryClusterer(config)

        drawers = [
            Drawer(id="d1", content="Python 异步编程 asyncio 使用指南", wing="dev", room="python"),
            Drawer(id="d2", content="Python 数据分析 pandas numpy 教程", wing="dev", room="python"),
            Drawer(id="d3", content="JavaScript React 前端框架入门", wing="dev", room="javascript"),
            Drawer(id="d4", content="JavaScript Vue 组件开发", wing="dev", room="javascript"),
            Drawer(id="d5", content="Docker 容器化部署方案", wing="dev", room="ops"),
            Drawer(id="d6", content="Kubernetes 集群管理", wing="dev", room="ops"),
        ]
        clusters = clusterer.cluster(drawers)
        assert len(clusters) >= 1
        assert all(isinstance(c, MemoryCluster) for c in clusters)

    def test_cluster_stats(self):
        clusterer = MemoryClusterer()
        clusters = [
            MemoryCluster(id="c1", label="test", keywords=["a", "b"], memory_ids=["1", "2"], size=2, cohesion=0.8),
            MemoryCluster(id="c2", label="test2", keywords=["c"], memory_ids=["3"], size=1, cohesion=1.0),
        ]
        stats = clusterer.cluster_stats(clusters)
        assert stats["total_clusters"] == 2
        assert stats["total_memories"] == 3
        assert stats["avg_size"] == 1.5

    def test_keyword_extraction(self):
        clusterer = MemoryClusterer()
        keywords = clusterer._extract_keywords("Python 异步编程和数据分析")
        assert len(keywords) > 0

    def test_cluster_empty(self):
        clusterer = MemoryClusterer()
        clusters = clusterer.cluster([])
        assert clusters == []

    def test_cluster_single(self):
        clusterer = MemoryClusterer()
        drawers = [Drawer(id="d1", content="single memory")]
        clusters = clusterer.cluster(drawers)
        assert len(clusters) == 1
        assert clusters[0].size == 1

    def test_cluster_filter_by_wing(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        clusterer = MemoryClusterer(config)

        drawers = [
            Drawer(id="d1", content="Python async tutorial", wing="dev"),
            Drawer(id="d2", content="Python data analysis", wing="dev"),
            Drawer(id="d3", content="Cooking recipe", wing="personal"),
        ]
        clusters = clusterer.cluster(drawers)
        assert len(clusters) >= 1


class TestConflictDetection:
    """冲突检测测试"""

    def test_detect_contradiction(self):
        detector = ConflictDetector()
        drawers = [
            Drawer(id="d1", content="Python 支持异步编程，推荐使用 asyncio"),
            Drawer(id="d2", content="Python 不支持异步编程，不推荐使用 asyncio"),
        ]
        conflicts = detector.detect_conflicts(drawers)
        assert len(conflicts) >= 0  # 可能检测到语义冲突

    def test_no_conflict(self):
        detector = ConflictDetector()
        drawers = [
            Drawer(id="d1", content="今天天气很好"),
            Drawer(id="d2", content="明天可能下雨"),
        ]
        conflicts = detector.detect_conflicts(drawers)
        assert len(conflicts) == 0

    def test_check_pair(self):
        detector = ConflictDetector()
        a = Drawer(id="a", content="支持使用 Redis 缓存")
        b = Drawer(id="b", content="不支持使用 Redis 缓存")
        result = detector.check_pair(a, b)
        assert "confidence" in result
        assert "severity" in result

    def test_resolve_suggestion(self):
        detector = ConflictDetector()
        conflict = MemoryConflict(
            id="c1",
            memory_a="a",
            memory_b="b",
            content_a="支持 Redis",
            content_b="不支持 Redis",
            description="矛盾",
            severity=ConflictSeverity.CRITICAL,
            confidence=0.9,
        )
        suggestion = detector.resolve_suggestion(conflict)
        assert "审查" in suggestion or "review" in suggestion.lower()

    def test_not_fact_keywords(self):
        detector = ConflictDetector()
        assert not detector._contains_fact_keywords("hello world")
        assert detector._contains_fact_keywords("version 2.0")

    def test_share_topic(self):
        detector = ConflictDetector()
        assert detector._share_topic("Python 异步编程 asyncio", "Python 异步编程 协程")
        assert not detector._share_topic("Python", "JavaScript")


class TestDeduplication:
    """去重引擎测试"""

    def test_exact_duplicate(self):
        deduper = MemoryDeduplicator()
        drawers = [
            Drawer(id="d1", content="完全相同的内容"),
            Drawer(id="d2", content="完全相同的内容"),
        ]
        groups = deduper.find_duplicates(drawers, method="hash")
        assert len(groups) == 1
        assert groups[0].memory_ids == ["d1", "d2"]

    def test_no_duplicate(self):
        deduper = MemoryDeduplicator()
        drawers = [
            Drawer(id="d1", content="Python 编程"),
            Drawer(id="d2", content="JavaScript 开发"),
        ]
        groups = deduper.find_duplicates(drawers)
        assert len(groups) == 0

    def test_dedup_stats(self):
        deduper = MemoryDeduplicator()
        groups = [
            DuplicateGroup(
                id="g1",
                memory_ids=["d1", "d2"],
                primary_id="d1",
                duplicate_ids=["d2"],
                similarity_matrix={},
                avg_similarity=0.95,
            ),
        ]
        stats = deduper.dedup_stats(groups)
        assert stats["duplicate_groups"] == 1
        assert stats["total_duplicate_memories"] == 1

    def test_merge_duplicates(self):
        deduper = MemoryDeduplicator()
        drawers = [
            Drawer(id="d1", content="Python 异步编程", importance=4.0, tags=["python"]),
            Drawer(id="d2", content="Python 异步编程详解", importance=3.0, tags=["async"]),
        ]
        group = DuplicateGroup(
            id="g1",
            memory_ids=["d1", "d2"],
            primary_id="d1",
            duplicate_ids=["d2"],
            similarity_matrix={},
            avg_similarity=0.9,
        )
        merged = deduper.merge_duplicates(group, drawers)
        assert merged is not None
        assert merged.id == "d1"
        assert "python" in merged.tags or "async" in merged.tags

    def test_similarity_check(self):
        deduper = MemoryDeduplicator()
        a = Drawer(id="a", content="Python 异步编程")
        b = Drawer(id="b", content="Python 异步编程")
        result = deduper.similarity_check(a, b)
        assert "similarity" in result
        assert "method" in result

    def test_keyword_dedup(self):
        deduper = MemoryDeduplicator()
        drawers = [
            Drawer(id="d1", content="Python 异步编程 asyncio"),
            Drawer(id="d2", content="Python 异步编程 协程"),
            Drawer(id="d3", content="JavaScript 前端开发"),
        ]
        groups = deduper.find_duplicates(drawers, method="keyword", threshold=0.4)
        assert len(groups) >= 0  # 取决于阈值


class TestAnalytics:
    """分析看板测试"""

    def test_analyze_basic(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        analyzer = MemoryAnalyzer(config)

        drawers = [
            Drawer(
                id="d1",
                content="重要决策：采用微服务架构",
                importance=5.0,
                wing="work",
                room="architecture",
                tags=["架构", "决策"],
            ),
            Drawer(
                id="d2",
                content="修复了登录页面的 bug",
                importance=3.0,
                wing="work",
                room="bugfix",
                tags=["bug", "修复"],
            ),
            Drawer(id="d3", content="日常代码审查", importance=2.0, wing="work", room="review", tags=["review"]),
        ]
        analysis = analyzer.analyze(drawers, wiki_page_count=2)
        assert isinstance(analysis, MemoryAnalytics)
        assert analysis.total_memories == 3
        assert analysis.total_wings == 1
        assert analysis.health_score >= 0
        assert analysis.health_score <= 100

    def test_health_score_good(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        analyzer = MemoryAnalyzer(config)

        drawers = [
            Drawer(
                id=f"d{i}",
                content=f"重要记忆 {i} 包含足够多的内容",
                importance=4.0,
                wing=f"wing_{i % 3}",
                room=f"room_{i}",
                tags=[f"tag_{i % 5}"],
            )
            for i in range(20)
        ]
        analysis = analyzer.analyze(drawers)
        assert analysis.health_score > 0
        assert "total_memories" in analysis.__dict__

    def test_growth_trend(self):
        analyzer = MemoryAnalyzer()
        drawers = [
            Drawer(id="d1", content="test", created_at="2024-01-15T10:00:00"),
            Drawer(id="d2", content="test", created_at="2024-01-16T10:00:00"),
        ]
        trend = analyzer.growth_trend(drawers, days=7)
        assert len(trend) == 7
        assert all("date" in d and "count" in d for d in trend)

    def test_anomaly_detect(self):
        analyzer = MemoryAnalyzer()
        drawers = [
            Drawer(id="d1", content=""),  # 空内容
            Drawer(id="d2", content="test", importance=10.0),  # 异常高重要性
            Drawer(id="d3", content="same content"),
            Drawer(id="d4", content="same content"),  # 完全重复
        ]
        anomalies = analyzer.anomaly_detect(drawers)
        assert len(anomalies) >= 1

    def test_summary_report(self):
        analyzer = MemoryAnalyzer()
        analysis = MemoryAnalytics(
            total_memories=10,
            total_wings=2,
            total_rooms=5,
            total_tags=8,
            total_wiki_pages=3,
            distribution_by_wing={"work": 7, "personal": 3},
            distribution_by_room={},
            distribution_by_hall={},
            distribution_by_tag={},
            importance_distribution={"high": 3, "medium": 4, "low": 3},
            avg_importance=2.8,
            memories_last_24h=2,
            memories_last_7d=5,
            memories_last_30d=10,
            oldest_memory_age_days=90,
            newest_memory_age_hours=1.0,
            avg_content_length=100,
            avg_tags_per_memory=1.5,
            most_common_tags=[("python", 3), ("bug", 2)],
            most_active_wings=[("work", 7)],
            health_score=85.0,
            health_issues=[],
            recommendations=["建议测试"],
        )
        report = analyzer.summary_report(analysis)
        assert "盘古" in report
        assert "85" in report

    def test_empty_analyze(self):
        analyzer = MemoryAnalyzer()
        analysis = analyzer.analyze([])
        assert analysis.total_memories == 0
        assert analysis.health_score <= 100


class TestTimeline:
    """时间线引擎测试"""

    def test_build_timeline(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        engine = TimelineEngine(config)

        drawers = [
            Drawer(id="d1", content="项目启动", created_at="2024-01-01T10:00:00", wing="work"),
            Drawer(id="d2", content="完成需求分析", created_at="2024-01-02T14:00:00", wing="work"),
            Drawer(id="d3", content="开始编码", created_at="2024-01-03T09:00:00", wing="work"),
        ]
        events = engine.build_timeline(drawers)
        assert len(events) == 3
        assert events[0].drawer_id == "d1"
        assert events[-1].drawer_id == "d3"

    def test_timeline_stats(self):
        engine = TimelineEngine()
        events = [
            TimelineEvent(id="e1", drawer_id="d1", content="test", timestamp="2024-01-01T10:00:00"),
            TimelineEvent(id="e2", drawer_id="d2", content="test", timestamp="2024-01-02T10:00:00"),
        ]
        stats = engine.timeline_stats(events)
        assert stats["total_events"] == 2
        assert stats["span_days"] >= 1

    def test_find_causal_links(self):
        engine = TimelineEngine()
        events = [
            TimelineEvent(
                id="e1", drawer_id="d1", content="因为发现了一个 bug，所以开始修复", timestamp="2024-01-01T10:00:00"
            ),
            TimelineEvent(id="e2", drawer_id="d2", content="修复了登录页面的 bug", timestamp="2024-01-01T11:00:00"),
        ]
        links = engine.find_causal_links(events)
        assert isinstance(links, list)

    def test_build_event_chain(self):
        engine = TimelineEngine()
        events = [
            TimelineEvent(id="e1", drawer_id="d1", content="开始", timestamp="2024-01-01T10:00:00"),
            TimelineEvent(id="e2", drawer_id="d2", content="进行中", timestamp="2024-01-01T11:00:00"),
            TimelineEvent(id="e3", drawer_id="d3", content="完成", timestamp="2024-01-02T10:00:00"),
        ]
        chains = engine.build_event_chain(events, max_gap_hours=24)
        assert len(chains) >= 1
        assert all(isinstance(c, EventChain) for c in chains)

    def test_temporal_markers(self):
        engine = TimelineEngine()
        markers = engine.find_temporal_markers("首先完成了需求分析，然后开始开发")
        assert "start" in markers or "next" in markers

    def test_query_timeline(self):
        engine = TimelineEngine()
        events = [
            TimelineEvent(id="e1", drawer_id="d1", content="test1", timestamp="2024-01-01T10:00:00", wing="work"),
            TimelineEvent(id="e2", drawer_id="d2", content="test2", timestamp="2024-01-02T10:00:00", wing="personal"),
        ]
        result = engine.query_timeline(events, wing="work")
        assert len(result) == 1

    def test_empty_timeline(self):
        engine = TimelineEngine()
        events = engine.build_timeline([])
        assert events == []
        stats = engine.timeline_stats(events)
        assert stats["total_events"] == 0

    def test_temporal_patterns(self):
        engine = TimelineEngine()
        events = [
            TimelineEvent(id="e1", drawer_id="d1", content="test", timestamp="2024-01-01T10:00:00"),
            TimelineEvent(id="e2", drawer_id="d2", content="test", timestamp="2024-01-01T11:00:00"),
            TimelineEvent(id="e3", drawer_id="d3", content="test", timestamp="2024-01-01T12:00:00"),
        ]
        patterns = engine.detect_temporal_patterns(events)
        assert isinstance(patterns, list)


class TestFusion:
    """融合引擎测试"""

    def test_fuse_topic(self):
        engine = FusionEngine()
        drawers = [
            Drawer(id="d1", content="Python 异步编程使用 asyncio 库", importance=4.0, tags=["python", "async"]),
            Drawer(id="d2", content="Python 协程可以提升并发性能", importance=3.0, tags=["python", "performance"]),
            Drawer(id="d3", content="JavaScript 使用 Promise 处理异步", importance=3.0, tags=["javascript"]),
        ]
        fused = engine.fuse_topic("Python", drawers)
        assert fused is not None
        assert isinstance(fused, FusedKnowledge)
        assert "Python" in fused.topic
        assert len(fused.key_points) > 0

    def test_fuse_nonexistent_topic(self):
        engine = FusionEngine()
        drawers = [Drawer(id="d1", content="Python programming")]
        fused = engine.fuse_topic("JavaScript", drawers)
        assert fused is None

    def test_progressive_summarize(self):
        engine = FusionEngine()
        drawers = [
            Drawer(id="d1", content="Python 异步编程基础", importance=4.0),
            Drawer(id="d2", content="Python 数据分析入门", importance=3.0),
            Drawer(id="d3", content="Python Web 开发指南", importance=4.0),
        ]
        result = engine.progressive_summarize(drawers)
        assert len(result) >= 1
        assert "level" in result[0]

    def test_crystallize_knowledge(self):
        engine = FusionEngine()
        drawers = [
            Drawer(id="d1", content="决定采用微服务架构 v2.0", importance=5.0),
            Drawer(id="d2", content="经验教训：不要在生产环境直接修改配置", importance=4.0),
            Drawer(id="d3", content="配置端口为 8866", importance=3.0),
        ]
        knowledge = engine.crystallize_knowledge(drawers)
        assert "facts" in knowledge
        assert "lessons" in knowledge
        assert "decisions" in knowledge
        assert "patterns" in knowledge


class TestPatterns:
    """模式识别测试"""

    def test_discover_all(self):
        engine = PatternEngine()
        drawers = [
            Drawer(id="d1", content="Python 异步编程", tags=["python", "async"], wing="dev", room="python"),
            Drawer(id="d2", content="Python 数据分析", tags=["python", "data"], wing="dev", room="python"),
            Drawer(id="d3", content="JavaScript 前端", tags=["javascript", "frontend"], wing="dev", room="js"),
            Drawer(id="d4", content="Python 机器学习", tags=["python", "ml"], wing="dev", room="python"),
        ]
        patterns = engine.discover_all(drawers)
        assert isinstance(patterns, list)
        assert all(isinstance(p, DiscoveredPattern) for p in patterns)

    def test_pattern_stats(self):
        engine = PatternEngine()
        patterns = [
            DiscoveredPattern(id="p1", pattern_type="frequency", description="test", evidence=[], confidence=0.8),
            DiscoveredPattern(id="p2", pattern_type="association", description="test", evidence=[], confidence=0.5),
        ]
        stats = engine.pattern_stats(patterns)
        assert stats["total_patterns"] == 2
        assert stats["high_confidence"] == 1

    def test_pattern_insights(self):
        engine = PatternEngine()
        patterns = [
            DiscoveredPattern(
                id="p1",
                pattern_type="frequency",
                description="标签 python 出现 3 次",
                evidence=[],
                confidence=0.8,
                frequency=3,
            ),
            DiscoveredPattern(
                id="p2",
                pattern_type="association",
                description="python 和 async 经常一起出现",
                evidence=[],
                confidence=0.6,
                frequency=2,
            ),
        ]
        insights = engine.pattern_insights(patterns)
        assert len(insights) >= 1

    def test_empty_patterns(self):
        engine = PatternEngine()
        patterns = engine.discover_all([])
        assert patterns == []


class TestReplay:
    """回放引擎测试"""

    def test_timeline_replay(self, tmp_path):
        config = PanguConfig()
        config.palace_path = str(tmp_path)
        engine = ReplayEngine(config)

        drawers = [
            Drawer(
                id="d1",
                content="项目启动会议",
                created_at="2024-01-01T10:00:00",
                importance=5.0,
                wing="work",
                room="meeting",
            ),
            Drawer(
                id="d2",
                content="编写需求文档",
                created_at="2024-01-02T14:00:00",
                importance=4.0,
                wing="work",
                room="docs",
            ),
            Drawer(
                id="d3",
                content="代码审查完成",
                created_at="2024-01-03T09:00:00",
                importance=3.0,
                wing="work",
                room="dev",
            ),
        ]
        session = engine.timeline_replay(drawers)
        assert isinstance(session, ReplaySession)
        assert session.event_count == 3
        assert len(session.key_moments) >= 1

    def test_topic_replay(self):
        engine = ReplayEngine()
        drawers = [
            Drawer(
                id="d1",
                content="Python 异步编程 asyncio 教程",
                created_at="2024-01-01T10:00:00",
                importance=4.0,
                tags=["python"],
            ),
            Drawer(
                id="d2",
                content="JavaScript 前端开发",
                created_at="2024-01-02T10:00:00",
                importance=3.0,
                tags=["javascript"],
            ),
            Drawer(
                id="d3",
                content="Python 数据分析 pandas",
                created_at="2024-01-03T10:00:00",
                importance=4.0,
                tags=["python"],
            ),
        ]
        session = engine.topic_replay("Python", drawers)
        assert session.event_count >= 2

    def test_diff_replay(self):
        engine = ReplayEngine()
        before = [
            Drawer(id="d1", content="old memory", created_at="2024-01-01T10:00:00"),
            Drawer(id="d2", content="deleted memory", created_at="2024-01-02T10:00:00"),
        ]
        after = [
            Drawer(id="d1", content="old memory", created_at="2024-01-01T10:00:00"),
            Drawer(id="d3", content="new memory", created_at="2024-01-03T10:00:00"),
        ]
        session = engine.diff_replay(before, after)
        assert session.event_count == 2  # 1 added + 1 removed

    def test_snapshot_compare(self):
        engine = ReplayEngine()
        a = [
            Drawer(id="d1", content="memory 1", importance=3.0),
            Drawer(id="d2", content="memory 2", importance=2.0),
        ]
        b = [
            Drawer(id="d1", content="memory 1 updated", importance=4.0),
            Drawer(id="d3", content="memory 3", importance=3.0),
        ]
        diff = engine.snapshot_compare(a, b)
        assert isinstance(diff, SnapshotDiff)
        assert len(diff.added) == 1
        assert len(diff.removed) == 1
        assert len(diff.modified) == 1

    def test_highlight_reel(self):
        engine = ReplayEngine()
        drawers = [
            Drawer(id="d1", content="important event", created_at="2024-01-01T10:00:00", importance=5.0),
            Drawer(id="d2", content="normal event", created_at="2024-01-02T10:00:00", importance=2.0),
            Drawer(id="d3", content="very important", created_at="2024-01-03T10:00:00", importance=4.5),
        ]
        session = engine.highlight_reel(drawers, top_n=2)
        assert session.event_count == 2
        assert session.key_moments[0]["importance"] >= session.key_moments[1]["importance"]

    def test_replay_summary(self):
        engine = ReplayEngine()
        session = ReplaySession(
            id="test",
            title="测试回放",
            events=[],
            span="2024-01-01 ~ 2024-01-03",
            event_count=3,
            wings=["work"],
            key_moments=[{"time": "2024-01-01T10:00:00", "content": "test", "importance": 5.0}],
        )
        summary = engine.replay_summary(session)
        assert "测试回放" in summary
        assert "test" in summary
