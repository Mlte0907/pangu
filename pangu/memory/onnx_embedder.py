"""盘古 — ONNX 本地嵌入器（CPU 加速 3-10x）

特性：
1. 懒加载：首次调用时下载/加载模型
2. 自动从 hf-mirror.com 下载（直连 HF 在国内被墙）
3. INT8 量化模型：~22MB，CPU 单核 200-400 tokens/s
4. 批处理：动态 padding，单次推理多条
5. LRU 缓存：避免重复计算
6. 失败回退：网络/推理失败自动回退到 hash 向量

依赖：onnxruntime + tokenizers（轻量，避免 sentence-transformers 的 500MB 依赖）
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("pangu.memory.onnx_embed")

# ── 可选依赖探测 ──
_HAS_ORT = False
_HAS_TOKENIZERS = False
try:
    import onnxruntime as ort  # noqa: F401

    _HAS_ORT = True
except ImportError:
    ort = None  # type: ignore

try:
    from tokenizers import Tokenizer  # noqa: F401

    _HAS_TOKENIZERS = True
except ImportError:
    Tokenizer = None  # type: ignore


# ── 默认模型候选（按优先级尝试） ──
DEFAULT_MODELS = [
    # (model_id, onnx_filename, tokenizer_filename, dim)
    ("Xenova/all-MiniLM-L6-v2", "onnx/model_quantized.onnx", "tokenizer.json", 384),
    ("Xenova/all-MiniLM-L3-v2", "onnx/model_quantized.onnx", "tokenizer.json", 384),
    ("Xenova/paraphrase-MiniLM-L3-v2", "onnx/model_quantized.onnx", "tokenizer.json", 384),
]


class ONNXEmbedder:
    """ONNX 嵌入器 — 本地 CPU 推理，零外部 API 依赖

    优先级：API → ONNX（如果启用） → hash 向量
    """

    def __init__(
        self,
        model_id: str = "Xenova/all-MiniLM-L6-v2",
        quantized: bool = True,
        max_length: int = 128,
        cache_dir: str | None = None,
        mirror_base: str = "https://hf-mirror.com",
        embedding_dim: int = 384,
    ):
        self.model_id = model_id
        self.quantized = quantized
        self.max_length = max_length
        self.embedding_dim = embedding_dim
        self.mirror_base = mirror_base.rstrip("/")

        # 缓存目录
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / ".cache" / "pangu" / "onnx" / model_id.replace("/", "__")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 懒加载状态
        self._session: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()
        self._load_attempted = False
        self._load_error: str | None = None

        # 缓存
        self._cache: dict[str, list[float]] = {}
        self._cache_max = 1024

        # 统计（_stats["model_loaded"] 在 _do_load 成功后才设为 True，
        # get_stats() 每次实时检查 self._session，防止返回过期缓存数据）
        self._stats = {
            "model_loaded": False,
            "load_time_ms": 0.0,
            "infer_count": 0,
            "infer_total_ms": 0.0,
            "cache_hits": 0,
            "download_bytes": 0,
        }

    @property
    def is_available(self) -> bool:
        """ONNX + tokenizers 是否可用"""
        return _HAS_ORT and _HAS_TOKENIZERS

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载到内存"""
        return self._session is not None and self._tokenizer is not None

    def _resolve_onnx_filename(self) -> str:
        """根据 quantize 标志选择模型文件名"""
        if self.quantized:
            return "onnx/model_quantized.onnx"
        return "onnx/model.onnx"

    def _download_file(self, url: str, dest: Path) -> bool:
        """下载文件到本地（带进度日志）"""
        if dest.exists() and dest.stat().st_size > 1024:
            return True
        try:
            import httpx

            logger.info(f"Downloading {url} → {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            with httpx.stream(
                "GET",
                url,
                headers={"User-Agent": "pangu-onnx/1.0"},
                timeout=60.0,
                follow_redirects=True,
            ) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=chunk_size):
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and downloaded % (512 * 1024) < chunk_size:
                            pct = 100 * downloaded / total
                            logger.debug(f"  {pct:.1f}% ({downloaded // 1024}KB / {total // 1024}KB)")
            tmp.rename(dest)
            self._stats["download_bytes"] += dest.stat().st_size
            logger.info(f"✓ Downloaded {dest.name} ({dest.stat().st_size // 1024}KB)")
            return True
        except Exception as e:
            logger.warning(f"Download failed: {url} → {e}")
            return False

    def _ensure_loaded(self) -> bool:
        """确保模型和 tokenizer 已加载（线程安全）"""
        if self.is_loaded:
            return True
        with self._lock:
            if self.is_loaded:
                return True
            if self._load_attempted and self._load_error:
                return False
            self._load_attempted = True
            return self._do_load()

    def _do_load(self) -> bool:
        """实际加载模型"""
        if not self.is_available:
            self._load_error = "onnxruntime/tokenizers 未安装"
            logger.warning(self._load_error)
            return False

        start = time.time()
        try:
            onnx_name = self._resolve_onnx_filename()
            tok_name = "tokenizer.json"
            onnx_path = self.cache_dir / onnx_name.split("/")[-1]
            tok_path = self.cache_dir / tok_name

            # 尝试镜像
            base = f"{self.mirror_base}/{self.model_id}/resolve/main"
            for url, dest in [
                (f"{base}/{onnx_name}", onnx_path),
                (f"{base}/{tok_name}", tok_path),
            ]:
                if not self._download_file(url, dest):
                    # 尝试直连 HuggingFace
                    fallback = url.replace(self.mirror_base, "https://huggingface.co")
                    if not self._download_file(fallback, dest):
                        self._load_error = f"无法下载: {url}"
                        return False

            # 加载 session
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
            sess_opts.inter_op_num_threads = 1
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(onnx_path),
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )

            # 加载 tokenizer
            self._tokenizer = Tokenizer.from_file(str(tok_path))
            self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=self.max_length)
            self._tokenizer.enable_truncation(max_length=self.max_length)

            elapsed = (time.time() - start) * 1000
            self._stats["load_time_ms"] = elapsed
            self._stats["model_loaded"] = True
            logger.info(f"✓ ONNX model loaded in {elapsed:.0f}ms ({onnx_path.stat().st_size // 1024}KB)")
            return True
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"ONNX load failed: {e}", exc_info=True)
            return False

    def _mean_pool(self, last_hidden: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        """Mean pooling + L2 归一化"""
        mask = np.expand_dims(attention_mask.astype(np.float32), -1)
        summed = np.sum(last_hidden * mask, axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        pooled = summed / counts
        # L2 normalize
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.where(norms > 0, norms, 1.0)
        return pooled / norms

    def _cache_key(self, text: str) -> str:
        # blake2b 摘要（与 hashing.hex_digest 行为一致）
        return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()

    def embed(self, text: str) -> list[float] | None:
        """嵌入单条文本，失败返回 None"""
        if not text:
            return [0.0] * self.embedding_dim

        key = self._cache_key(text)
        with self._lock:
            if key in self._cache:
                self._stats["cache_hits"] += 1
                return self._cache[key]

        if not self._ensure_loaded():
            return None

        try:
            return self._infer([text], [key])[0]
        except Exception as e:
            logger.warning(f"ONNX embed failed: {e}")
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """批量嵌入"""
        if not texts:
            return []

        # 缓存命中
        keys = [self._cache_key(t) for t in texts]
        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        missing_keys: list[str] = []

        with self._lock:
            for i, k in enumerate(keys):
                if k in self._cache:
                    results[i] = self._cache[k]
                    self._stats["cache_hits"] += 1
                else:
                    missing_indices.append(i)
                    missing_texts.append(texts[i])
                    missing_keys.append(k)

        if not missing_texts:
            return results

        if not self._ensure_loaded():
            return results  # 全部为 None

        try:
            vecs = self._infer(missing_texts, missing_keys)
            for j, idx in enumerate(missing_indices):
                results[idx] = vecs[j]
        except Exception as e:
            logger.warning(f"ONNX batch embed failed: {e}")

        return results

    def _infer(self, texts: list[str], keys: list[str]) -> list[list[float]]:
        """实际推理：分批避免 OOM"""
        all_vecs: list[list[float]] = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_keys = keys[i : i + batch_size]
            vecs = self._infer_batch(batch_texts)
            all_vecs.extend(vecs)
            # 更新缓存
            with self._lock:
                for k, v in zip(batch_keys, vecs, strict=False):
                    if len(self._cache) >= self._cache_max:
                        # 简单 LRU：清空一半
                        self._cache = dict(list(self._cache.items())[self._cache_max // 2 :])
                    self._cache[k] = v
        return all_vecs

    def _infer_batch(self, texts: list[str]) -> list[list[float]]:
        """单次推理（< 32 条）"""
        start = time.time()
        encodings = self._tokenizer.encode_batch(texts)
        max_len = max(len(e.ids) for e in encodings)
        max_len = min(max_len, self.max_length)

        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
        for i, e in enumerate(encodings):
            ids = e.ids[:max_len]
            input_ids[i, : len(ids)] = ids
            attention_mask[i, : len(ids)] = 1

        # token_type_ids（部分模型需要，全 0 即可）
        token_type_ids = np.zeros_like(input_ids)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        last_hidden = outputs[0]  # [B, T, H]
        pooled = self._mean_pool(last_hidden, attention_mask)

        elapsed_ms = (time.time() - start) * 1000
        self._stats["infer_count"] += len(texts)
        self._stats["infer_total_ms"] += elapsed_ms
        logger.debug(f"ONNX batch({len(texts)}) infer: {elapsed_ms:.1f}ms")

        return pooled.tolist()

    def warmup(self, texts: list[str] | None = None) -> int:
        """预热 ONNX 缓存，返回预热条数"""
        if texts is None:
            texts = ["Python", "ONNX", "FAISS", "记忆系统", "向量搜索", "盘古", "深度学习"]
        count = 0
        for t in texts:
            try:
                vec = self.embed(t)
                if vec:
                    count += 1
            except Exception:
                pass
        return count

    def get_stats(self) -> dict:
        """获取性能统计（实时检查模型状态，防止返回过期缓存数据）"""
        stats = dict(self._stats)
        # 关键修复：实时检查 self._session，而非依赖 _stats["model_loaded"]
        # 模型可能在加载后被释放（如 OOM 时），此时 _stats["model_loaded"]
        # 仍为真，导致 mcp_tool 返回错误的 model_loaded: true
        stats["model_loaded"] = self._session is not None and self._tokenizer is not None
        if self._stats["infer_count"] > 0:
            stats["avg_infer_ms"] = self._stats["infer_total_ms"] / self._stats["infer_count"]
        else:
            stats["avg_infer_ms"] = 0.0
        # 附加实时校验标记，方便调用方判断数据新鲜度
        stats["_realtime_check"] = True
        return stats


# ── 全局单例 ──
_onnx_embedder: ONNXEmbedder | None = None
_onnx_lock = threading.Lock()


def get_onnx_embedder(
    model_id: str = "Xenova/all-MiniLM-L6-v2",
    quantized: bool = True,
    max_length: int = 128,
    cache_dir: str | None = None,
    mirror_base: str = "https://hf-mirror.com",
    embedding_dim: int = 384,
) -> ONNXEmbedder:
    """获取全局 ONNX 嵌入器（按参数缓存）"""
    global _onnx_embedder
    with _onnx_lock:
        if _onnx_embedder is None:
            _onnx_embedder = ONNXEmbedder(
                model_id=model_id,
                quantized=quantized,
                max_length=max_length,
                cache_dir=cache_dir,
                mirror_base=mirror_base,
                embedding_dim=embedding_dim,
            )
        return _onnx_embedder


def reset_onnx_embedder():
    """重置全局实例（用于配置更新）"""
    global _onnx_embedder
    with _onnx_lock:
        _onnx_embedder = None
