"""盘古 — 统一嵌入服务（API → ONNX → hash 三级降级）

从伏羲 v1.5.6 移植，适配盘古架构。

核心特性：
1. 优先外部API，失败降级到 ONNX 本地推理
2. ONNX 不可用时进一步降级到 hash 向量
   ⚠ hash 向量**没有任何语义能力**（字符 trigram 哈希），它合法、非零、
   维度正确，因此无法通过"看向量是否有效"来发现降级。
   实际后端由 `active_backend` / `is_degraded` 如实上报，见 `_mark_backend`。
3. 电路断路器（circuit breaker）防雪崩
4. 批量嵌入（batch API + 并发本地）
5. blake2b 缓存避免重复计算
6. 异步/同步双模式
"""

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
        self._onnx = None
        # 实际生效的嵌入后端。"hash" 意味着检索结果**没有语义能力**，
        # 与 "onnx"/"api" 完全不是一个东西（实测 cos(猫,dog)=0.0000）。
        # 此前没有任何地方记录这个事实，导致服务静默地给出无意义结果。
        self._active_backend: str = "unknown"
        self._degraded_reason: str | None = None
        self._degraded_warned = False
        self._partial_hash_count = 0
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

    def _mark_backend(self, backend: str, reason: str | None = None):
        """记录实际生效的后端。

        `hash` 是**语义能力为零**的降级后端，必须让它可见而不是静默生效。
        """
        if backend == self._active_backend:
            return
        self._active_backend = backend
        if backend == "hash":
            self._degraded_reason = reason or "ONNX 与远程 API 均不可用"
            # 只告警一次，避免刷屏掩盖其它日志
            if not self._degraded_warned:
                self._degraded_warned = True
                logger.error(
                    "嵌入服务已降级为 hash 向量 —— 检索结果将**没有语义能力**"
                    "（相同含义的文本不会相近）。原因: %s。"
                    "修复：安装 ONNX 模型（./install.sh 会预下载）或配置 embed_api_url。"
                    "若确需在此环境运行，设 PANGU_ALLOW_HASH_FALLBACK=1 显式接受降级。",
                    self._degraded_reason,
                )
        else:
            self._degraded_reason = None

    @property
    def active_backend(self) -> str:
        """实际生效的后端：api / onnx / hash / unknown"""
        return self._active_backend

    @property
    def is_degraded(self) -> bool:
        """是否已降级到无语义的 hash 向量"""
        return self._active_backend == "hash"

    @property
    def partial_hash_vectors(self) -> int:
        """批量嵌入中被 hash 补位的向量条数。

        为什么单独计数：整批失败会被 `_mark_backend("hash")` 记下，但**部分**
        补位时后端仍是 `onnx`——若只看后端，这种情况不可见。它同样让返回的
        向量**部分无语义**，属于同一类"静默错误"，故必须能被观测。
        """
        return self._partial_hash_count

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
            if vec is not None:
                self._mark_backend("api")

        if vec is None:
            # API 失败/未配置，降级到 ONNX 本地推理
            vec = self._onnx_embed(text)
            if vec is not None:
                self._mark_backend("onnx")

        if vec is None:
            # ONNX 不可用，最终降级到 hash 向量。
            # 这是**语义能力为零**的后端，必须显式记录，让 /health 能发现。
            vec = self._local_embed(text)
            reason = None
            if self._onnx is not None:
                reason = getattr(self._onnx, "_load_error", None) or "ONNX 模型未加载"
            elif not getattr(self.config, "onnx_enabled", True):
                reason = "onnx_enabled=False"
            else:
                reason = "ONNX 嵌入器初始化失败"
            self._mark_backend("hash", reason)

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

        # 未配置 API URL 时不要走 API 分支：`_embed_batch_api` 会返回 None，
        # 让 `return` 直接把 None 交给调用方（调用方需自行判空），
        # 同时避免下面那条误导性的 "Batch API failed" WARNING。
        if not self.config.embed_api_url:
            use_api = False

        if use_api and self.config.embedding_model:
            try:
                result = self._embed_batch_api(texts)
                if result is not None:
                    self._mark_backend("api")
                    return result
            except Exception as e:
                logger.warning(f"Batch API failed, falling back to ONNX: {e}")

        # ONNX 批量（高效的本地方案）
        if self._onnx is not None and self._onnx.is_available:
            try:
                onnx_results = self._onnx.embed_batch(texts)
                # 补齐 ONNX 返回 None 的位置。
                # 注意：这些补位是 hash 向量，与其余位置**性质不同**。
                # 若整批都补位（ONNX 实际失败），那就是彻底降级，必须如实上报，
                # 否则 /health 会看到一个"onnx"后端却全是无语义向量。
                filled = 0
                for i, r in enumerate(onnx_results):
                    if r is None:
                        onnx_results[i] = self._local_embed(texts[i])
                        filled += 1
                if filled == len(texts):
                    self._mark_backend("hash", "ONNX 批量嵌入全部返回 None")
                else:
                    if filled:
                        self._partial_hash_count += filled
                        logger.warning("ONNX 批量嵌入有 %d/%d 条降级为 hash 向量", filled, len(texts))
                    self._mark_backend("onnx")
                return onnx_results
            except Exception as e:
                logger.warning(f"ONNX batch failed, falling back to hash: {e}")

        # 最终降级：并发 hash
        self._mark_backend("hash", "ONNX 嵌入器不可用（批量）")
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
            # `_call_api_batch` 在未配置 `embed_api_url` 时返回 None（见其
            # 首行守卫）。此前这里直接 `enumerate(vecs)`，于是**任何没配
            # API URL 的部署**（默认就是空字符串）每次批量嵌入都抛
            # TypeError: 'NoneType' object is not iterable，被 embed_batch
            # 的 except 吞掉后打一条 WARNING 再回退 ONNX。
            # 功能侥幸正确（有回退），但每次都在做无用功并刷警告，
            # 掩盖了真正需要关注的 API 故障。未配置是正常状态，直接返回 None。
            if vecs is None:
                return None
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
            import httpx

            from pangu.memory.sanitizer import MemorySanitizer

            safe_texts = [MemorySanitizer.sanitize(t)[0] for t in texts]
            data = {"model": self.config.embedding_model, "input": safe_texts, "encoding_format": "float"}
            headers = {"Authorization": f"Bearer {self.config.llm_api_key}"} if self.config.llm_api_key else {}
            # 此前这里用的是 aiohttp，但它**未被声明为依赖**（三份依赖清单均无），
            # 于是该分支在任何标准安装下都必然抛 ImportError，被下面 except 吞掉，
            # 表现为"配了 embed_api_url 却永远不生效"，且无任何提示。
            # httpx 已是正式依赖（pyproject.toml:25），同仓库 onnx_embedder.py:140
            # 也用它下载模型，统一到一个客户端可少一份依赖。
            resp = httpx.post(self.config.embed_api_url, json=data, headers=headers, timeout=30.0)
            resp.raise_for_status()
            result = resp.json()
            embeddings = [item["embedding"] for item in result["data"]]
            self._fail_count = 0
            if self._circuit_open:
                self._circuit_open = False
                self._half_open_until = 0.0
                logger.info("Circuit breaker CLOSED — API recovered (batch)")
            return embeddings
        except Exception as e:
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
            import httpx

            from pangu.memory.sanitizer import MemorySanitizer

            safe_text = MemorySanitizer.sanitize(text)[0]
            data = {"model": self.config.embedding_model, "input": safe_text, "encoding_format": "float"}
            headers = {"Authorization": f"Bearer {self.config.llm_api_key}"} if self.config.llm_api_key else {}
            # 同 _call_api_batch：改用已声明的 httpx，见该处注释。
            resp = httpx.post(self.config.embed_api_url, json=data, headers=headers, timeout=10.0)
            resp.raise_for_status()
            result = resp.json()
            vec = result["data"][0]["embedding"]
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
            # 后端可见性：让调用方无需猜测"结果是否可信"
            "active_backend": self._active_backend,
            "degraded": self.is_degraded,
        }
        if self._degraded_reason:
            result["degraded_reason"] = self._degraded_reason
        if self._partial_hash_count:
            # 部分降级：后端仍是 onnx，但确有向量是 hash 补位的
            result["partial_hash_vectors"] = self._partial_hash_count
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
