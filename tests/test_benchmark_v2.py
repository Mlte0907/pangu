"""盘古 v2.0 综合性能基准测试"""
import time
import statistics
import numpy as np
from pangu.memory.layers import MemoryStack, _estimate_tokens
from pangu.memory.ingestion import remember, _embed_text, _cosine_similarity
from pangu.memory.retrieval import recall, clear_recall_cache
from pangu.memory.hybrid_search import hybrid_search
from pangu.memory.vector_index import get_vector_index
from pangu.memory.onnx_embedder import get_onnx_embedder
from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer


def run_benchmark():
    """运行综合性能基准测试"""
    config = PanguConfig.load()
    stack = MemoryStack(config)
    drawers = stack.get_drawers()

    print('=' * 60)
    print('  盘古 v2.0 综合性能基准测试')
    print('=' * 60)

    # 基本信息
    idx = get_vector_index()
    print(f'\n系统状态:')
    print(f'  记忆数: {len(drawers)}')
    print(f'  向量数: {idx.size}')
    print(f'  后端: {"hnswlib" if idx._use_hnsw else ("FAISS" if idx._use_faiss else "numpy")}')

    # 1. ONNX 嵌入性能
    print('\n[1] ONNX 嵌入性能')
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        _embed_text('测试嵌入性能')
        times.append((time.perf_counter() - t0) * 1000)
    print(f'  单条: median={statistics.median(times):.2f}ms')

    # 2. VectorIndex 搜索性能
    print('\n[2] VectorIndex 搜索性能')
    query = np.random.randn(384).tolist()
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        idx.search(query, top_k=10)
        times.append((time.perf_counter() - t0) * 1000)
    print(f'  {idx.size}v: median={statistics.median(times):.2f}ms')

    # 3. recall() 性能
    print('\n[3] recall() 性能')
    times = []
    for _ in range(10):
        clear_recall_cache()
        t0 = time.perf_counter()
        recall(query='Python', limit=10, drawers=drawers)
        times.append((time.perf_counter() - t0) * 1000)
    print(f'  首次: {times[0]:.1f}ms')
    print(f'  缓存后: median={statistics.median(times[1:]):.1f}ms')

    # 4. cosine similarity 性能
    print('\n[4] cosine similarity 性能')
    a = np.random.randn(384).tolist()
    b = np.random.randn(384).tolist()
    times = []
    for _ in range(1000):
        t0 = time.perf_counter()
        _cosine_similarity(a, b)
        times.append((time.perf_counter() - t0) * 1000)
    print(f'  单次: median={statistics.median(times):.4f}ms')

    # 5. Token 统计
    print('\n[5] Token 统计')
    total_tokens = sum(_estimate_tokens(d.content) for d in drawers)
    print(f'  总计: {total_tokens}')
    print(f'  平均: {total_tokens // len(drawers)} tokens/memory')

    print('\n' + '=' * 60)
    print('  性能基准测试完成')
    print('=' * 60)


if __name__ == '__main__':
    run_benchmark()
