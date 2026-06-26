"""盘古向量嵌入引擎 — 真正的语义搜索
==========================================
基于 sentence-transformers 的向量嵌入，替换简单的关键词匹配，
实现真正的语义级搜索。

支持：
- 嵌入缓存（避免重复计算）
- 批量处理（提升吞吐量）
- 多模型支持（可切换嵌入模型）
"""

import time
from collections import OrderedDict

import numpy as np

from ..core.config import PanguConfig


class EmbeddingCache:
    """嵌入向量 LRU 缓存"""

    def __init__(self, max_size: int = 5000):
        self._cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> np.ndarray | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: np.ndarray):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def clear(self):
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def __len__(self):
        return len(self._cache)


class VectorEmbedder:
    """向量嵌入引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._model = None
        self._cache = EmbeddingCache()
        self._embed_time_total: float = 0.0
        self._embed_count: int = 0

    @property
    def model(self):
        """懒加载嵌入模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.config.embedding_model)
            except ImportError as e:
                raise ImportError("sentence-transformers 未安装，请运行: pip install sentence-transformers") from e
            except Exception as e:
                raise RuntimeError(f"加载嵌入模型失败: {e}") from e
        return self._model

    @property
    def avg_embed_time_ms(self) -> float:
        if self._embed_count == 0:
            return 0.0
        return (self._embed_time_total / self._embed_count) * 1000

    def embed(self, text: str) -> np.ndarray:
        """为单段文本生成嵌入向量"""
        cache_key = f"emb_{hash(text)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        start = time.time()
        embedding = self.model.encode(text, convert_to_numpy=True)
        self._embed_time_total += time.time() - start
        self._embed_count += 1

        self._cache.set(cache_key, embedding)
        return embedding

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """批量生成嵌入向量"""
        if not texts:
            return np.array([])

        results = []
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cache_key = f"emb_{hash(text)}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                results.append((i, cached))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        if uncached_texts:
            start = time.time()
            embeddings = self.model.encode(uncached_texts, convert_to_numpy=True)
            self._embed_time_total += time.time() - start
            self._embed_count += len(uncached_texts)

            for j, idx in enumerate(uncached_indices):
                emb = embeddings[j]
                cache_key = f"emb_{hash(uncached_texts[j])}"
                self._cache.set(cache_key, emb)
                results.append((idx, emb))

        results.sort(key=lambda x: x[0])
        return np.stack([r[1] for r in results])

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def search(self, query: str, items: list[dict], top_k: int = 10, content_key: str = "content") -> list[dict]:
        """语义搜索 — 基于向量相似度

        Args:
            query: 搜索查询
            items: 待搜索的项目列表，每个项目是 dict
            top_k: 返回结果数
            content_key: 用于生成嵌入的字段名

        Returns:
            按相似度排序的结果列表
        """
        if not items:
            return []

        query_emb = self.embed(query)

        texts = [item.get(content_key, "") for item in items]
        item_embs = self.embed_batch(texts)

        scored = []
        for i, item in enumerate(items):
            sim = self.similarity(query_emb, item_embs[i])
            scored.append((sim, item))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, item in scored[:top_k]:
            item_copy = dict(item)
            item_copy["score"] = round(float(sim), 4)
            item_copy["source"] = "semantic"
            results.append(item_copy)

        return results

    def cache_stats(self) -> dict:
        return {
            "size": len(self._cache),
            "hits": self._cache._hits,
            "misses": self._cache._misses,
            "hit_rate": round(self._cache.hit_rate, 4),
            "avg_embed_time_ms": round(self.avg_embed_time_ms, 2),
            "total_embeds": self._embed_count,
        }
