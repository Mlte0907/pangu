"""盘古 — 统一嵌入服务（API → ONNX → hash 三级降级）

从伏羲 v1.5.6 移植，适配盘古架构。

核心特性：
1. 优先外部API，失败降级到 ONNX 本地推理
2. ONNX 不可用时进一步降级到 hash 向量
3. 电路断路器（circuit breaker）防雪崩
4. 批量嵌入（batch API + 并发本地）
5. 批量嵌入（batch API + 并发本地）
6. blake2b 缓存避免重复计算
7. 异步/同步双模式
"""

import asyncio
import concurrent.futures
import hashlib  # noqa: F401  # 仅供 blake2b fallback 使用
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from pangu.core.config import PanguConfig
from pangu.core.hashing import hex_digest, int_hash

logger = logging.getLogger("pangu.memory.embed")


class EmbeddingService:
    """统一嵌入服务：优先外部API，失败降级为本地hash向量"""

    CIRCUIT_COOLDOWN = 600  # 电路断路器冷却时间（秒）

    def _init_onnx_embedder(self):
        """初始化 ONNX 嵌入器"""
        if not getattr(self.config, "onnx_enabled", True):
            return
        try:
            from pangu.memory.onnx_embedder import get_onnx_embedder

            if get_onnx_embedder.__module__:
                self._onnx = get_onnx_embedder(
                    model_id=self.config.onnx_model_id,
                    quantized=self.config.onnx_quantized,
                    max_length=self.config.onnx_max_length,
                    cache_dir=self.config.onnx_cache_dir or None,
                    mirror_base=self.config.onnx_mirror_base,
                    embedding_dim=self.config.embedding_dim,
                )
        except Exception as e:
            logger.debug(f"ONNX embedder init deferred: {e}")

    def __init__(self, config: PanguConfig | None = None):
        self.config = config or PanguConfig()
        self._cache: dict = {}
        self._cache_lock = threading.Lock()
        self._fail_count = 0
        self._last_fail_time = 0.0
        self._circuit_open = False
        self._half_open_until = 0.0  # timestamp until which half-open probe is allowed
        self._embed_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed_async")
        self._onnx = None
        self._init_onnx_embedder()

    def reset_circuit(self):
        """手动重置电路断路器"""
        self._fail_count = 0
        self._last_fail_time = 0.0
        self._circuit_open = False
        self._half_open_until = 0.0
        logger.info("Circuit breaker MANUALLY RESET — API calls re-enabled")

    def _maybe_reset_circuit(self):
        if self._circuit_open:
            if self._last_fail_time == 0 or time.time() - self._last_fail_time >= self.CIRCUIT_COOLDOWN:
                self._fail_count = 0
                self._circuit_open = False
                self._half_open_until = 0.0
                logger.info("Circuit breaker COOLDOWN RESET — retrying API after cooldown")

    def embed(self, text: str) -> list[float] | None:
        """嵌入单条文本"""
        self._maybe_reset_circuit()
        if not text:
            return [0.0] * self.config.embedding_dim

        cache_key = hex_digest(text)
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        # 电路断路器 + half-open 恢复
        use_api = False
        if self._circuit_open:
            if time.time() >= self._half_open_until:
                use_api = True  # half-open: 允许一次探测
        else:
            use_api = True

        vec = None
        if use_api:
            vec = self._call_api(text)

        if vec is None:
            # API 失败/未配置，降级到 ONNX 本地推理
            vec = self._onnx_embed(text)

        if vec is None:
            # ONNX 不可用，最终降级到 hash 向量
            vec = self._local_embed(text)

        if vec:
            with self._cache_lock:
                if len(self._cache) >= 10000:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                self._cache[cache_key] = vec

        return vec

    def embed_batch(self, texts: list[str], max_workers: int = 4) -> list[list[float] | None]:
        """批量嵌入

        优先级：API → ONNX（批量） → hash 并发
        """
        self._maybe_reset_circuit()
        if len(texts) <= 1:
            return [self.embed(t) for t in texts]

        use_api = False
        if self._circuit_open:
            if time.time() >= self._half_open_until:
                use_api = True
        else:
            use_api = True

        if use_api and self.config.embedding_model:
            try:
                return self._embed_batch_api(texts)
            except Exception as e:
                logger.warning(f"Batch API failed, falling back to ONNX: {e}")

        # ONNX 批量（高效的本地方案）
        if self._onnx is not None and self._onnx.is_available:
            try:
                onnx_results = self._onnx.embed_batch(texts)
                # 补齐 ONNX 返回 None 的位置
                for i, r in enumerate(onnx_results):
                    if r is None:
                        onnx_results[i] = self._local_embed(texts[i])
                return onnx_results
            except Exception as e:
                logger.warning(f"ONNX batch failed, falling back to hash: {e}")

        # 最终降级：并发 hash
        results: list[list[float] | None] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(texts))) as ex:
            futures = {ex.submit(self.embed, t): i for i, t in enumerate(texts)}
            for f in as_completed(futures):
                i = futures[f]
                try:
                    results[i] = f.result()
                except Exception as e:
                    logger.warning(f"Batch embed failed for index {i}: {e}")
        return results

    def _embed_batch_api(self, texts: list[str]) -> list[list[float] | None]:
        """批量API嵌入"""
        cache_keys = [hex_digest(t) for t in texts]
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        with self._cache_lock:
            for i, key in enumerate(cache_keys):
                if key in self._cache:
                    results[i] = self._cache[key]
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(texts[i])

        if uncached_texts:
            vecs = self._call_api_batch(uncached_texts)
            for j, vec in enumerate(vecs):
                idx = uncached_indices[j]
                resolved_vec = vec if vec else self._local_embed(uncached_texts[j])
                results[idx] = resolved_vec
                self._cache_embedding(cache_keys[idx], resolved_vec)

        return results

    def _cache_embedding(self, key: str, vec: list[float] | None):
        if vec:
            with self._cache_lock:
                if len(self._cache) >= 10000:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                self._cache[key] = vec

    def _call_api_batch(self, texts: list[str]) -> list[list[float] | None]:
        """调用批量API"""
        if not self.config.embed_api_url:
            return None  # 未配置 API URL，跳过 API 直接走 ONNX
        try:
            import aiohttp

            from pangu.memory.sanitizer import MemorySanitizer

            safe_texts = [MemorySanitizer.sanitize(t)[0] for t in texts]
            data = {"model": self.config.embedding_model, "input": safe_texts, "encoding_format": "float"}
            timeout = aiohttp.ClientTimeout(total=30)

            async def _fetch():
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.post(
                        self.config.embed_api_url,
                        json=data,
                        headers={"Authorization": f"Bearer {self.config.llm_api_key}"}
                        if self.config.llm_api_key
                        else {},
                    ) as resp,
                ):
                    resp.raise_for_status()
                    result = await resp.json()
                    return [item["embedding"] for item in result["data"]]

            future = self._embed_executor.submit(asyncio.run, _fetch())
            embeddings = future.result(timeout=45)
            self._fail_count = 0
            if self._circuit_open:
                self._circuit_open = False
                self._half_open_until = 0.0
                logger.info("Circuit breaker CLOSED — API recovered (batch)")
            return embeddings
        except (concurrent.futures.TimeoutError, Exception) as e:
            self._fail_count += 1
            self._last_fail_time = time.time()
            logger.warning(f"Embed batch API failed ({self._fail_count}): {e}")
            if self._fail_count >= 5:
                self._circuit_open = True
                self._half_open_until = time.time() + 60
                logger.warning("Circuit breaker OPEN — using local fallback, half-open in 60s")
            return [None] * len(texts)

    def _call_api(self, text: str) -> list[float] | None:
        """同步调用API"""
        if not self.config.embed_api_url:
            return None  # 未配置 API URL，跳过 API 直接走 ONNX
        try:
            import aiohttp

            from pangu.memory.sanitizer import MemorySanitizer

            safe_text = MemorySanitizer.sanitize(text)[0]
            data = {"model": self.config.embedding_model, "input": safe_text, "encoding_format": "float"}
            timeout = aiohttp.ClientTimeout(total=10)

            async def _fetch():
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.post(
                        self.config.embed_api_url,
                        json=data,
                        headers={"Authorization": f"Bearer {self.config.llm_api_key}"}
                        if self.config.llm_api_key
                        else {},
                    ) as resp,
                ):
                    resp.raise_for_status()
                    result = await resp.json()
                    return result["data"][0]["embedding"]

            future = self._embed_executor.submit(asyncio.run, _fetch())
            vec = future.result(timeout=15)
            self._fail_count = 0
            if self._circuit_open:
                self._circuit_open = False
                self._half_open_until = 0.0
                logger.info("Circuit breaker CLOSED — API recovered")
            return vec
        except Exception as e:
            self._fail_count += 1
            self._last_fail_time = time.time()
            logger.warning(f"Embed API failed ({self._fail_count}): {e}")
            if self._fail_count >= 5:
                self._circuit_open = True
                self._half_open_until = time.time() + 60
                logger.warning("Circuit breaker OPEN — using local fallback, half-open in 60s")
            return None

    def _onnx_embed(self, text: str) -> list[float] | None:
        """ONNX 本地嵌入（API 失败后的第一级降级）

        Returns:
            向量，失败时返回 None
        """
        if self._onnx is None:
            return None
        return self._onnx.embed(text)

    def _local_embed(self, text: str) -> list[float]:
        """基于hash的本地向量生成（无需外部模型，确定性降级方案）"""
        vec = np.zeros(self.config.embedding_dim, dtype=np.float32)
        if len(text) <= 2:
            # 短文本：使用字符级 unigram
            for ch in text:
                idx = int_hash(ch, mod=self.config.embedding_dim)
                vec[idx] += 1.0
        else:
            # 正常文本：使用字符级 trigram
            for i in range(len(text) - 2):
                ngram = text[i : i + 3]
                idx = int_hash(ngram, mod=self.config.embedding_dim)
                vec[idx] += 1.0

        # L2归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def warmup(self, queries: list[str] | None = None) -> int:
        """预热 embedding 缓存，返回预热条数"""
        if queries is None:
            queries = self.config.embed_warmup_queries
        if not queries:
            return 0

        count = 0
        for q in queries:
            try:
                vec = self.embed(q)
                if vec:
                    count += 1
            except Exception:
                pass
        logger.info(f"Embedding cache warmed: {count}/{len(queries)} queries")
        return count

    @property
    def stats(self) -> dict:
        result = {
            "cache_size": len(self._cache),
            "fail_count": self._fail_count,
            "circuit_open": self._circuit_open,
        }
        if self._onnx is not None:
            result["onnx"] = self._onnx.get_stats()
        return result


_embed_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取全局嵌入服务单例"""
    global _embed_service
    if _embed_service is None:
        _embed_service = EmbeddingService()
    return _embed_service
