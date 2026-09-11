"""测试性能优化效果"""

import time

import numpy as np
import pytest

from pangu.core.palace import Drawer
from pangu.memory.hybrid_search import hybrid_search
from pangu.memory.utils import cosine_similarity, cosine_similarity_batch


class TestCosineSimilarityOptimization:
    """测试余弦相似度优化"""

    def test_cosine_similarity_correctness(self):
        """测试余弦相似度正确性"""
        # 相同向量
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0)

        # 正交向量
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

        # 相反向量
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

        # 空向量
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], []) == 0.0
        assert cosine_similarity([], [1.0]) == 0.0

    def test_cosine_similarity_performance(self):
        """测试余弦相似度性能"""
        a = np.random.randn(384).tolist()
        b = np.random.randn(384).tolist()

        # 测试单次计算性能
        start = time.time()
        for _ in range(1000):
            cosine_similarity(a, b)
        end = time.time()
        avg_time = (end - start) * 1000 / 1000

        # 应该小于 0.1ms
        assert avg_time < 0.1, f"单次计算太慢: {avg_time:.4f}ms"

    def test_cosine_similarity_batch_performance(self):
        """测试批量余弦相似度性能"""
        query = np.random.randn(384).tolist()
        vectors = [np.random.randn(384).tolist() for _ in range(100)]

        start = time.time()
        for _ in range(100):
            results = cosine_similarity_batch(query, vectors, threshold=0.2)
        end = time.time()
        avg_time = (end - start) * 1000 / 100

        # 应该小于 2ms
        assert avg_time < 2, f"批量计算太慢: {avg_time:.4f}ms"

    def test_cosine_similarity_batch_correctness(self):
        """测试批量余弦相似度正确性"""
        query = [1.0, 0.0, 0.0]
        vectors = [
            [1.0, 0.0, 0.0],  # 完全相同
            [0.0, 1.0, 0.0],  # 正交
            [-1.0, 0.0, 0.0],  # 相反
            [0.5, 0.5, 0.0],  # 45度
        ]

        results = cosine_similarity_batch(query, vectors, threshold=0.1)

        # 应该找到索引0和3
        assert len(results) == 2
        assert results[0] == (0, 1.0)
        assert results[1][0] == 3
        assert results[1][1] == pytest.approx(0.707, abs=0.01)


class TestHybridSearchOptimization:
    """测试混合搜索优化"""

    def test_hybrid_search_with_embeddings(self):
        """测试带嵌入的混合搜索"""
        # 创建更现实的测试数据
        base_embedding = np.random.randn(384).tolist()
        drawers = []
        for i in range(50):
            # 创建与基础嵌入相似的向量
            noise = np.random.randn(384) * 0.1
            embedding = (np.array(base_embedding) + noise).tolist()

            drawer = Drawer(
                id=f"test_{i}",
                content=f"Test memory {i} about Python programming",
                wing="test",
                room="general",
                importance=float(i % 5),
                tags=["test"],
                created_at="2024-01-01T00:00:00",
                metadata={"embedding": embedding},
            )
            drawers.append(drawer)

        # 测试搜索性能
        start = time.time()
        for _ in range(10):
            results = hybrid_search("Python", drawers, limit=10)
        end = time.time()
        avg_time = (end - start) * 1000 / 10

        # 应该小于 50ms
        assert avg_time < 50, f"混合搜索太慢: {avg_time:.2f}ms"
        # 搜索可能返回空结果（如果所有相似度都低于阈值），但这不是性能问题
        # 我们主要测试性能，不是搜索质量

    def test_hybrid_search_without_embeddings(self):
        """测试无嵌入的混合搜索"""
        drawers = []
        for i in range(50):
            drawer = Drawer(
                id=f"test_{i}",
                content=f"Test memory {i} about Python programming",
                wing="test",
                room="general",
                importance=float(i % 5),
                tags=["test"],
                created_at="2024-01-01T00:00:00",
                metadata={},
            )
            drawers.append(drawer)

        # 测试搜索性能
        start = time.time()
        for _ in range(10):
            results = hybrid_search("Python", drawers, limit=10)
        end = time.time()
        avg_time = (end - start) * 1000 / 10

        # 应该小于 20ms
        assert avg_time < 20, f"混合搜索太慢: {avg_time:.2f}ms"
        # 搜索可能返回空结果（如果没有匹配），但这不是性能问题


class TestVectorIndexIntegration:
    """测试向量索引集成"""

    def test_vector_index_search(self):
        """测试向量索引搜索"""
        from pangu.memory.vector_index import get_vector_index

        vi = get_vector_index()

        # 添加测试向量
        vectors = [np.random.randn(384).tolist() for _ in range(100)]
        ids = [f"vec_{i}" for i in range(100)]

        start = time.time()
        vi.add_batch(vectors, ids)
        end = time.time()
        add_time = (end - start) * 1000

        # 测试搜索性能
        query = np.random.randn(384).tolist()
        start = time.time()
        results = vi.search(query, top_k=10)
        end = time.time()
        search_time = (end - start) * 1000

        assert add_time < 100, f"添加向量太慢: {add_time:.2f}ms"
        assert search_time < 1, f"搜索太慢: {search_time:.2f}ms"
        assert len(results) == 10
        assert vi.size == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
