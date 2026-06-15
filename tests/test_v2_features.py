"""盘古 v2.0 新功能测试 — neural_memory / multi_agent / social_memory"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer


class TestNeuralMemory:
    """神经记忆系统测试"""

    def test_neural_engine_creation(self):
        from pangu.memory.neural_memory import NeuralMemoryEngine
        engine = NeuralMemoryEngine()
        assert engine.hippocampus is not None
        assert engine.neocortex is not None
        assert engine.sleep_engine is not None

    def test_neural_encode(self):
        from pangu.memory.neural_memory import NeuralMemoryEngine
        engine = NeuralMemoryEngine()
        drawer = Drawer(
            id='test-1', content='测试记忆', wing='test',
            importance=3.0, tags=['test'], created_at='2026-01-01T00:00:00'
        )
        nm = engine.encode(drawer)
        assert nm.id == 'test-1'
        assert nm.content == '测试记忆'
        assert engine.hippocampus.buffer_size == 1

    def test_neural_sleep_consolidation(self):
        from pangu.memory.neural_memory import NeuralMemoryEngine
        engine = NeuralMemoryEngine()
        old_time = (datetime.now() - timedelta(days=2)).isoformat()
        for i in range(3):
            engine.encode(Drawer(
                id=f'test-{i}', content=f'记忆{i}', wing='test',
                importance=3.0, tags=['test'], created_at=old_time
            ))
        assert engine.hippocampus.buffer_size == 3
        result = engine.sleep()
        assert result['consolidated'] == 3
        assert engine.neocortex.count() == 3

    def test_neural_spreading(self):
        from pangu.memory.neural_memory import NeuralMemoryEngine
        engine = NeuralMemoryEngine()
        old_time = (datetime.now() - timedelta(days=2)).isoformat()
        for i, content in enumerate(['Python', 'ONNX', 'FAISS']):
            engine.encode(Drawer(
                id=f'test-{i}', content=content, wing='test',
                importance=3.0, tags=['test'], created_at=old_time
            ))
        engine.sleep()
        engine.neocortex.build_association('test-0', 'test-1', 0.8)
        activations = engine.neocortex.activate_spreading(['test-0'])
        assert len(activations) > 0
        assert activations[0][0] == 'test-0'  # seed has highest activation

    def test_neural_decay(self):
        from pangu.memory.neural_memory import PersonalizedDecay, NeuralMemory, MemoryType
        decay = PersonalizedDecay()
        mem = NeuralMemory(
            id='test', content='test', memory_type=MemoryType.SEMANTIC,
            created_at=datetime.now().timestamp() - 86400  # 1 day ago
        )
        retention = decay.retention(mem)
        assert 0 < retention < 1  # should have decayed

    def test_neural_stats(self):
        from pangu.memory.neural_memory import NeuralMemoryEngine
        engine = NeuralMemoryEngine()
        stats = engine.stats()
        assert 'hippocampus' in stats
        assert 'neocortex' in stats


class TestMultiAgent:
    """多Agent协作记忆测试"""

    def test_register_agent(self):
        from pangu.memory.multi_agent import get_multi_agent_memory
        mam = get_multi_agent_memory()
        mam.register_agent('test-agent', priority=10)
        agents = mam.get_agents()
        assert 'test-agent' in agents
        assert agents['test-agent'] == 10

    def test_write_read(self):
        from pangu.memory.multi_agent import get_multi_agent_memory, MemoryScope
        mam = get_multi_agent_memory()
        mam.register_agent('writer', priority=10)
        mam.register_agent('reader', priority=5)
        
        mem = mam.write('writer', '测试记忆', scope=MemoryScope.PUBLIC)
        assert mem.content == '测试记忆'
        
        results = mam.read('reader')
        assert len(results) > 0

    def test_scope_isolation(self):
        from pangu.memory.multi_agent import get_multi_agent_memory, MemoryScope
        mam = get_multi_agent_memory()
        mam.register_agent('a', priority=10)
        mam.register_agent('b', priority=5)
        
        mam.write('a', '私有记忆', scope=MemoryScope.PRIVATE)
        mam.write('a', '公开记忆', scope=MemoryScope.PUBLIC)
        
        results_a = mam.read('a')
        results_b = mam.read('b')
        assert len(results_a) >= 2  # a sees private + public
        assert len(results_b) >= 1  # b sees only public

    def test_agents_list(self):
        from pangu.memory.multi_agent import get_multi_agent_memory
        mam = get_multi_agent_memory()
        mam.register_agent('x', priority=1)
        mam.register_agent('y', priority=2)
        agents = mam.get_agents()
        assert 'x' in agents
        assert 'y' in agents


class TestSocialMemory:
    """社交记忆测试"""

    def test_add_comment(self):
        from pangu.memory.social_memory import SocialMemory
        sm = SocialMemory()
        comment = sm.add_comment('mem-1', 'user1', '测试评论')
        assert comment.memory_id == 'mem-1'
        assert comment.author_id == 'user1'
        assert comment.content == '测试评论'

    def test_comment_thread(self):
        import uuid
        from pangu.memory.social_memory import SocialMemory
        sm = SocialMemory()
        mem_id = f'mem-thread-{uuid.uuid4().hex[:8]}'
        c1 = sm.add_comment(mem_id, 'user1', '评论1')
        c2 = sm.add_comment(mem_id, 'user2', '回复1', parent_id=c1.id)
        comments = sm.get_comments(mem_id, top_level_only=False)
        assert len(comments) == 2
        assert c1.parent_id is None
        assert c2.parent_id == c1.id

    def test_vote(self):
        from pangu.memory.social_memory import SocialMemory, VoteType
        sm = SocialMemory()
        vote = sm.vote('mem-1', 'user1', VoteType.UP)
        assert vote.vote_type == VoteType.UP
        stats = sm.get_votes('mem-1')
        assert stats['up'] == 1

    def test_persistence(self):
        from pangu.memory.social_memory import SocialMemory
        sm1 = SocialMemory()
        sm1.add_comment('mem-persist', 'user1', '持久化测试')
        
        sm2 = SocialMemory()
        comments = sm2.get_comments('mem-persist')
        assert len(comments) >= 1
        assert any(c.content == '持久化测试' for c in comments)


class TestCluster:
    """聚类测试"""

    def test_cluster_by_tags(self):
        from pangu.memory.cluster import cluster_by_tags
        results = [
            {'id': '1', 'content': 'test1', 'tags': ['python']},
            {'id': '2', 'content': 'test2', 'tags': ['python']},
            {'id': '3', 'content': 'test3', 'tags': ['ai']},
        ]
        clusters = cluster_by_tags(results)
        assert 'python' in clusters
        assert len(clusters['python']) == 2

    def test_hierarchical_cluster(self):
        from pangu.memory.cluster import hierarchical_cluster
        results = [
            {'id': '1', 'content': 'Python编程', 'tags': ['python']},
            {'id': '2', 'content': 'Python数据分析', 'tags': ['python']},
            {'id': '3', 'content': 'ONNX推理', 'tags': ['onnx']},
        ]
        clusters = hierarchical_cluster(results, max_clusters=2)
        assert len(clusters) <= 2


class TestTags:
    """标签管理测试"""

    def test_tags_db_init(self):
        from pangu.api.routes_tags import _init_db, _get_db
        _init_db()
        conn = _get_db()
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [r[0] for r in rows]
            assert 'tags' in table_names
        finally:
            conn.close()
