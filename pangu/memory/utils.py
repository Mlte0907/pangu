"""盘古记忆系统公共工具模块

提供统一的向量计算函数和线程安全工具，避免在多个模块中重复实现。
所有模块应从此处导入 cosine_similarity，不再各自实现。
"""

import threading
from collections.abc import Sequence

import numpy as np

# ── 线程安全单例工厂 ──


def make_singleton(factory, *args, **kwargs):
    """线程安全的单例创建（双重检查锁定模式）

    用法:
        _engine = None
        _engine_lock = threading.Lock()

        def get_engine(config=None):
            global _engine
            if _engine is None:
                _engine = make_singleton(_engine_lock, EngineClass, config)
            return _engine
    """
    if not isinstance(factory, type):
        # 已经是实例，直接返回
        return factory
    # 作为锁 + 创建器使用时的备选方案
    return factory(*args, **kwargs)


class ThreadSafeSingleton:
    """线程安全单例基类 — 子类继承即可获得 DCL 保护

    用法:
        class MyEngine(ThreadSafeSingleton):
            def __init__(self, config=None):
                self.config = config
                ...

        engine = MyEngine.get_instance(config)
    """

    _instances: dict = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, config=None):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = cls(config)
        return cls._instances[cls]


class LRUCache:
    """线程安全的 LRU 缓存（基于 OrderedDict）

    自动淘汰最久未访问的条目，支持 TTL 过期。

    用法:
        cache = LRUCache(max_size=100, ttl_seconds=300)
        cache.set("key", value)
        value = cache.get("key")  # None if missing/expired
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 300):
        from collections import OrderedDict

        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str):
        """获取缓存值，命中时刷新访问顺序"""
        with self._lock:
            if key not in self._cache:
                return None
            entry = self._cache[key]
            if self._ttl and (time.time() - entry["ts"]) > self._ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return entry["data"]

    def set(self, key: str, value):
        """设置缓存值，超容量时淘汰最久未访问的"""
        import time as _time

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = {"ts": _time.time(), "data": value}
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def __len__(self):
        return len(self._cache)


# ── 公共工具函数 ──

import time


def cosine_similarity(a: Sequence[float] | np.ndarray, b: Sequence[float] | np.ndarray) -> float:
    """计算两个向量的余弦相似度（统一实现）

    使用 numpy 向量化计算，比纯 Python 循环快 10-100 倍。
    支持不同长度的向量（截断到较短长度）。

    Args:
        a: 第一个向量（list、tuple 或 numpy array）
        b: 第二个向量（list、tuple 或 numpy array）

    Returns:
        余弦相似度，范围 [-1, 1]
    """
    # 判空：a / b 可能是 numpy 数组，不能用 `not a`——数组的真值判断会抛
    # ValueError: truth value of an array with more than one element is ambiguous。
    # 统一转成数组后按元素个数判断，同时兼容 list / tuple / ndarray。
    try:
        size_a = np.asarray(a).size
        size_b = np.asarray(b).size
    except Exception:
        return 0.0
    if size_a == 0 or size_b == 0:
        return 0.0

    # 转换为 numpy 数组
    vec_a = np.array(a, dtype=np.float32)
    vec_b = np.array(b, dtype=np.float32)

    # 截断到相同长度
    min_len = min(len(vec_a), len(vec_b))
    if min_len == 0:
        return 0.0

    vec_a = vec_a[:min_len]
    vec_b = vec_b[:min_len]

    # 计算余弦相似度
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)

    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0

    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def cosine_similarity_batch(
    query: Sequence[float] | np.ndarray, vectors: Sequence[Sequence[float]] | np.ndarray, threshold: float = 0.0
) -> list[tuple[int, float]]:
    """批量计算查询向量与多个向量的余弦相似度

    使用 numpy 向量化计算，避免 O(n²) 循环。

    Args:
        query: 查询向量
        vectors: 候选向量列表
        threshold: 相似度阈值，低于此值的结果不返回

    Returns:
        [(index, similarity), ...] 按相似度降序排列
    """
    if not query or not vectors:
        return []

    # 转换为 numpy 数组
    query_arr = np.array(query, dtype=np.float32)
    vectors_arr = np.array(vectors, dtype=np.float32)

    # 归一化查询向量
    query_norm = np.linalg.norm(query_arr)
    if query_norm < 1e-8:
        return []
    query_arr = query_arr / query_norm

    # 归一化所有候选向量
    vector_norms = np.linalg.norm(vectors_arr, axis=1, keepdims=True)
    vector_norms = np.where(vector_norms > 1e-8, vector_norms, 1.0)
    vectors_arr = vectors_arr / vector_norms

    # 向量化点积计算相似度
    similarities = np.dot(vectors_arr, query_arr)

    # 过滤并排序
    results = []
    for i, sim in enumerate(similarities):
        if sim > threshold:
            results.append((i, float(sim)))

    # 按相似度降序排列
    results.sort(key=lambda x: -x[1])

    return results


def batch_cosine_similarity(queries: list[list[float]], vectors: list[list[float]]) -> np.ndarray:
    """计算两组向量之间的余弦相似度矩阵

    Args:
        queries: 查询向量列表 (m x d)
        vectors: 候选向量列表 (n x d)

    Returns:
        相似度矩阵 (m x n)
    """
    if not queries or not vectors:
        return np.array([])

    # 转换为 numpy 数组
    queries_arr = np.array(queries, dtype=np.float32)
    vectors_arr = np.array(vectors, dtype=np.float32)

    # 归一化
    query_norms = np.linalg.norm(queries_arr, axis=1, keepdims=True)
    query_norms = np.where(query_norms > 1e-8, query_norms, 1.0)
    queries_arr = queries_arr / query_norms

    vector_norms = np.linalg.norm(vectors_arr, axis=1, keepdims=True)
    vector_norms = np.where(vector_norms > 1e-8, vector_norms, 1.0)
    vectors_arr = vectors_arr / vector_norms

    # 计算相似度矩阵
    return np.dot(queries_arr, vectors_arr.T)
