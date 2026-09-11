"""盘古向量嵌入引擎 — 真正的语义搜索
==========================================
向量嵌入后端，支持两种实现：

1. **ONNX（默认，推荐）**：基于 onnxruntime + tokenizers 的本地推理，
   模型 all-MiniLM-L6-v2（INT8 量化，384 维）。轻量、无 torch 依赖，
   启动即可用。这是 `onnx_enabled=True`（默认）时的首选路径。
2. **sentence-transformers（回退）**：仅在 ONNX 不可用时才尝试导入。
   需要额外安装 `sentence-transformers`（会传递引入 torch，约数百 MB）。

对外接口保持不变：始终返回 `numpy.ndarray`，调用方无需感知后端差异。

支持：
- 嵌入缓存（避免重复计算）
- 批量处理（提升吞吐量）
- 多模型支持（可切换嵌入模型）
"""

import logging
import time
from collections import OrderedDict

import numpy as np

from ..core.config import PanguConfig

logger = logging.getLogger(__name__)


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
    """向量嵌入引擎

    优先使用 ONNX 本地推理（默认，无 torch 依赖）；若 ONNX 不可用或
    被显式关闭，则回退到 sentence-transformers。两者对外都产出
    `numpy.ndarray`（384 维），调用方无需感知差异。
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._model = None
        self._onnx = None
        self._backend: str | None = None  # 'onnx' | 'st' | 'unavailable'
        self._cache = EmbeddingCache()
        self._embed_time_total: float = 0.0
        self._embed_count: int = 0

    # ── 后端选择 ──────────────────────────────────────────────

    def _init_onnx(self) -> bool:
        """尝试初始化 ONNX 后端。返回是否可用。"""
        if self._onnx is not None:
            return True
        if not getattr(self.config, "onnx_enabled", True):
            return False
        try:
            from ..memory.onnx_embedder import get_onnx_embedder

            self._onnx = get_onnx_embedder(
                model_id=self.config.onnx_model_id,
                quantized=self.config.onnx_quantized,
                max_length=self.config.onnx_max_length,
                cache_dir=self.config.onnx_cache_dir or None,
                mirror_base=self.config.onnx_mirror_base,
                embedding_dim=self.config.embedding_dim,
            )
            return True
        except Exception as e:  # noqa: BLE001 — 任何失败都只降级，不阻断
            logger.debug(f"ONNX embedder 初始化失败, 将回退: {e}")
            self._onnx = None
            return False

    def _init_sentence_transformers(self) -> bool:
        """尝试初始化 sentence-transformers 后端。返回是否可用。"""
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.config.embedding_model)
            return True
        except ImportError:
            return False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"sentence-transformers 模型加载失败: {e}")
            return False

    def _resolve_backend(self) -> str:
        """确定可用后端并缓存结果。"""
        if self._backend is not None:
            return self._backend

        # 首选 ONNX
        if self._init_onnx():
            self._backend = "onnx"
            logger.debug("VectorEmbedder 使用 ONNX 后端")
            return self._backend

        # 回退 sentence-transformers
        if self._init_sentence_transformers():
            self._backend = "st"
            logger.info("VectorEmbedder 回退到 sentence-transformers 后端")
            return self._backend

        self._backend = "unavailable"
        return self._backend

    @property
    def backend(self) -> str:
        """当前使用的嵌入后端：'onnx' / 'st' / 'unavailable'"""
        return self._resolve_backend()

    def _unavailable_error(self) -> RuntimeError:
        return RuntimeError(
            "无可用的嵌入后端：ONNX（onnxruntime + tokenizers）初始化失败，"
            "且 sentence-transformers 未安装。\n"
            "请任选其一：\n"
            "  1) 安装 ONNX 依赖（推荐，轻量）：pip install onnxruntime tokenizers\n"
            "  2) 安装 sentence-transformers（体积大，会引入 torch）："
            'pip install -e ".[multimodal]"'
        )

    # ── 嵌入实现 ──────────────────────────────────────────────

    def _embed_one(self, text: str) -> np.ndarray:
        if self._resolve_backend() == "onnx":
            vec = self._onnx.embed(text)
            if vec is None:
                raise RuntimeError("ONNX 嵌入返回空结果（模型可能下载失败）")
            return np.asarray(vec, dtype=np.float32)
        if self._backend == "st":
            return self.model.encode(text, convert_to_numpy=True)
        raise self._unavailable_error()

    def _embed_many(self, texts: list[str]) -> list[np.ndarray]:
        if self._resolve_backend() == "onnx":
            vecs = self._onnx.embed_batch(texts)
            out: list[np.ndarray] = []
            for i, v in enumerate(vecs):
                if v is None:
                    raise RuntimeError(f"ONNX 批量嵌入第 {i} 条返回空结果")
                out.append(np.asarray(v, dtype=np.float32))
            return out
        if self._backend == "st":
            arr = self.model.encode(texts, convert_to_numpy=True)
            return [arr[i] for i in range(len(texts))]
        raise self._unavailable_error()

    @property
    def model(self):
        """懒加载嵌入模型（sentence-transformers 后端专用）。

        仅为向后兼容保留。新代码请直接使用 embed() / embed_batch()。
        """
        if not self._init_sentence_transformers():
            raise ImportError(
                "sentence-transformers 未安装。默认的 ONNX 后端无需它；"
                '如确需此后端请运行: pip install -e ".[multimodal]"'
            )
        self._backend = self._backend or "st"
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
        embedding = self._embed_one(text)
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
            embeddings = self._embed_many(uncached_texts)
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
