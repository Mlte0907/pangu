"""盘古向量索引加速 — 加速大规模向量相似度搜索

从伏羲移植：基于 numpy 的向量索引，支持快速近似最近邻搜索。
当记忆数量超过阈值时自动构建索引，大幅提升搜索速度。

性能优化：
1. 写入缓冲：批量写入减少磁盘 I/O
2. FAISS/hnswlib 增量更新：无需重建索引
3. 线程安全：并发读写保护
"""

import json
import logging
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger("pangu.memory.vector_index")


FAISS_THRESHOLD = 1000  # 超过此数量自动切换 FAISS
AUTO_FLUSH_THRESHOLD = 100  # 写入缓冲自动刷新阈值


class VectorIndex:
    """向量索引加速器 — 加速大规模向量相似度搜索

    核心特性：
    1. <1000 条: numpy brute-force（预归一化，0.1ms）
    2. >=1000 条: FAISS IVFFlat（近似最近邻，O(log n)）
    3. 自动切换，对调用方透明
    4. 增量更新 + 磁盘持久化
    """

    def __init__(self, dim: int = 384, persist: bool = False):
        import os
        from pathlib import Path

        self.dim = dim
        # 是否持久化到全局缓存目录。
        #
        # 默认 False：`build()` / `add_batch()` 会调 `_save()`，而缓存文件名
        # 只由维度决定，于是任何**临时实例**（测试、多模型并存的调用方）
        # 构建索引时都会覆盖全局单例的索引文件。之后单例从磁盘加载到别人
        # 的数据——`size` 凭空变大、`np.vstack` 维度不符被吞成"加了 0 条"、
        # 搜索返回错误结果。只有真正的进程级单例（get_vector_index）才该
        # 写入共享缓存，构造函数直接使用时应显式传 persist=True。
        self._persist = persist
        self._index: np.ndarray | None = None  # numpy 模式
        self._faiss_index = None  # FAISS 模式
        self._hnsw_index = None  # hnswlib 模式
        self._ids: list[str] = []
        self._is_built: bool = False
        self._size: int = 0
        self._use_faiss: bool = False
        self._use_hnsw: bool = False
        self._cache_dir = Path(os.environ.get("PANGU_CACHE_DIR", str(Path.home() / ".cache" / "pangu")))
        # 按维度区分文件名。
        #
        # 此前所有维度的实例共用 `vector_index.npz`：一个 dim=4 的实例
        # （测试、或多模型混用场景）构建索引时会**覆盖** dim=384 的主索引，
        # 之后主索引从磁盘加载到 4 维数据，`np.vstack` 与 384 维新向量不
        # 匹配 → add_batch 静默失败 → 搜索恒为空。维度是索引身份的一部分。
        suffix = "" if dim == 384 else f".d{dim}"
        self._index_file = self._cache_dir / f"vector_index{suffix}.npz"
        self._faiss_file = self._cache_dir / f"vector_index{suffix}.faiss"
        self._faiss_ids_file = self._cache_dir / f"vector_index_ids{suffix}.json"
        self._hnsw_file = self._cache_dir / f"vector_index{suffix}.hnsw"
        self._hnsw_ids_file = self._cache_dir / f"vector_index_hnsw_ids{suffix}.json"
        # 写入缓冲
        self._pending_vectors: list[np.ndarray] = []
        self._pending_ids: list[str] = []
        self._pending_count: int = 0
        # 线程安全
        self._lock = threading.RLock()
        self._load()  # 启动时自动加载

    def _save(self) -> None:
        """保存索引到磁盘（仅当实例声明持久化）"""
        if not self._persist:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            if self._use_hnsw and self._hnsw_index is not None:
                self._hnsw_index.save_index(str(self._hnsw_file))
                with open(self._hnsw_ids_file, "w") as f:
                    json.dump(self._ids, f)
                logger.debug("hnswlib index saved")
            elif self._use_faiss and self._faiss_index is not None:
                import faiss

                faiss.write_index(self._faiss_index, str(self._faiss_file))
                with open(self._faiss_ids_file, "w") as f:
                    json.dump(self._ids, f)
                logger.debug("FAISS index saved")
            elif self._is_built and self._index is not None:
                np.savez_compressed(self._index_file, vectors=self._index, ids=self._ids, dim=self.dim)
                logger.debug(f"Vector index saved to {self._index_file}")
        except Exception as e:
            logger.warning(f"Vector index save failed: {e}")

    def _load(self) -> None:
        """从磁盘加载索引（仅当实例声明持久化）"""
        if not self._persist:
            return
        try:
            # 尝试加载 hnswlib
            if self._hnsw_file.exists() and self._hnsw_ids_file.exists():
                import hnswlib

                self._hnsw_index = hnswlib.Index(space="cosine", dim=self.dim)
                self._hnsw_index.load_index(str(self._hnsw_file))
                with open(self._hnsw_ids_file) as f:
                    self._ids = json.load(f)
                self._is_built = True
                self._use_hnsw = True
                self._size = len(self._ids)
                logger.info(f"hnswlib index loaded: {self._size} vectors")
                return
            # 尝试加载 FAISS
            if self._faiss_file.exists() and self._faiss_ids_file.exists():
                import faiss

                self._faiss_index = faiss.read_index(str(self._faiss_file))
                with open(self._faiss_ids_file) as f:
                    self._ids = json.load(f)
                self._is_built = True
                self._use_faiss = True
                self._size = len(self._ids)
                logger.info(f"FAISS index loaded: {self._size} vectors")
                return
            # 降级到 numpy
            if self._index_file.exists():
                data = np.load(self._index_file)
                loaded = data["vectors"]
                # 维度自检：拒绝加载与实例维度不符的索引。
                # 读到不匹配的数据会让后续 add_batch 的 np.vstack 抛错，
                # 而错误被吞成"加了 0 条"，表现为搜索永远为空——
                # 在这里直接跳过并告警，让问题在加载点可见。
                if loaded.ndim != 2 or loaded.shape[1] != self.dim:
                    logger.warning(
                        f"忽略维度不匹配的索引缓存 {self._index_file}: "
                        f"文件 {getattr(loaded, 'shape', None)} vs 期望 dim={self.dim}"
                    )
                    return
                self._index = loaded
                self._ids = list(data["ids"])
                self._is_built = True
                self._size = len(self._ids)
                logger.info(f"Vector index loaded: {self._size} vectors from {self._index_file}")
        except Exception as e:
            logger.debug(f"Vector index load failed: {e}")

    @property
    def is_built(self) -> bool:
        return self._is_built

    @property
    def size(self) -> int:
        return self._size

    def build(self, vectors: list[list[float]], ids: list[str]) -> bool:
        """构建向量索引（自动选择 numpy 或 FAISS）

        Args:
            vectors: 向量列表
            ids: 对应的 ID 列表
        """
        if len(vectors) != len(ids):
            return False
        if not vectors:
            return False

        try:
            arr = np.array(vectors, dtype=np.float32)
            # 预归一化
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            arr = arr / norms
            self._ids = list(ids)
            self._is_built = True
            self._size = len(vectors)

            # 自动选择后端：hnswlib > FAISS > numpy
            if self._size >= FAISS_THRESHOLD:
                try:
                    import hnswlib

                    self._build_hnsw(arr)
                except ImportError:
                    self._build_faiss(arr)
            else:
                self._index = arr
                self._use_faiss = False
                self._use_hnsw = False

            self._save()
            backend = "hnswlib" if self._use_hnsw else ("FAISS" if self._use_faiss else "numpy")
            logger.info(f"Vector index built: {self._size} vectors, dim={self.dim}, backend={backend}")
            return True
        except Exception as e:
            logger.warning(f"Vector index build failed: {e}")
            return False

    def _build_faiss(self, arr: np.ndarray) -> None:
        """构建 FAISS 索引"""
        try:
            import faiss

            nlist = min(int(np.sqrt(len(arr))), 256)  # 聚类中心数
            quantizer = faiss.IndexFlatIP(self.dim)  # 内积 = 余弦（已归一化）
            self._faiss_index = faiss.IndexIVFFlat(quantizer, self.dim, nlist, faiss.METRIC_INNER_PRODUCT)
            self._faiss_index.train(arr.astype(np.float32))
            self._faiss_index.add(arr.astype(np.float32))
            self._faiss_index.nprobe = min(nlist, 16)  # 搜索时检查的聚类数
            self._use_faiss = True
            self._index = None  # 释放 numpy 内存
            logger.info(f"FAISS index built: {self._size} vectors, nlist={nlist}")
        except ImportError:
            logger.warning("FAISS not available, falling back to numpy")
            self._index = arr
            self._use_faiss = False

    def _build_hnsw(self, arr: np.ndarray) -> None:
        """构建 hnswlib 索引"""
        try:
            import hnswlib

            self._hnsw_index = hnswlib.Index(space="cosine", dim=self.dim)
            self._hnsw_index.init_index(max_elements=self._size, ef_construction=200, M=16)
            self._hnsw_index.add_items(arr.astype(np.float32), list(range(self._size)))
            self._hnsw_index.set_ef(50)  # 搜索时的 ef 参数
            self._use_hnsw = True
            self._index = None  # 释放 numpy 内存
            logger.info(f"hnswlib index built: {self._size} vectors")
        except ImportError:
            logger.warning("hnswlib not available, falling back to numpy")
            self._index = arr
            self._use_hnsw = False

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        """归一化向量"""
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else vec

    def add(self, vector: list[float], item_id: str) -> bool:
        """增量添加单个向量（写入缓冲 + 线程安全）"""
        with self._lock:
            try:
                vec = self._normalize(np.array([vector], dtype=np.float32))
                self._pending_vectors.append(vec)
                self._pending_ids.append(item_id)
                self._pending_count += 1
                self._size += 1

                # 自动刷新缓冲
                if self._pending_count >= AUTO_FLUSH_THRESHOLD:
                    self._flush_pending()
                return True
            except Exception as e:
                logger.debug(f"Vector index add failed: {e}")
                return False

    def _flush_pending(self) -> None:
        """刷新写入缓冲到索引"""
        if not self._pending_vectors:
            return

        batch = np.array(self._pending_vectors, dtype=np.float32)
        batch = self._normalize(batch)

        if self._use_hnsw and self._hnsw_index is not None:
            # hnswlib 增量添加
            self._hnsw_index.add_items(batch, list(range(self._size - len(self._pending_vectors), self._size)))
            self._ids.extend(self._pending_ids)
        elif self._use_faiss and self._faiss_index is not None:
            # FAISS 增量添加（无需重建）
            self._faiss_index.add(batch.astype(np.float32))
            self._ids.extend(self._pending_ids)
        elif self._is_built and self._index is not None:
            self._index = np.vstack([self._index, batch])
            self._ids.extend(self._pending_ids)
        else:
            self._index = batch
            self._ids = list(self._pending_ids)
            self._is_built = True

        self._pending_vectors.clear()
        self._pending_ids.clear()
        self._pending_count = 0

        # 跨过阈值时重建
        if not self._use_faiss and not self._use_hnsw and self._size >= FAISS_THRESHOLD:
            try:
                import hnswlib

                self._build_hnsw(self._index)
            except ImportError:
                self._build_faiss(self._index)

        self._save()

    def _add_to_backend(self, batch: np.ndarray, ids: list[str]) -> None:
        """将批次添加到当前后端索引"""
        if self._use_hnsw and self._hnsw_index is not None:
            self._hnsw_index.add_items(batch, list(range(self._size, self._size + len(ids))))
            self._ids.extend(ids)
        elif self._use_faiss and self._faiss_index is not None:
            self._faiss_index.add(batch.astype(np.float32))
            self._ids.extend(ids)
        elif self._is_built and self._index is not None:
            self._index = np.vstack([self._index, batch])
            self._ids.extend(ids)
        else:
            self._index = batch
            self._ids = list(ids)
            self._is_built = True

    def _maybe_rebuild_index(self) -> None:
        """跨越阈值时尝试重建索引"""
        if not self._use_faiss and not self._use_hnsw and self._size >= FAISS_THRESHOLD:
            try:
                import hnswlib

                self._build_hnsw(self._index)
            except ImportError:
                self._build_faiss(self._index)

    def add_batch(self, vectors: list[list[float]], ids: list[str]) -> int:
        """批量添加向量（线程安全）

        返回**实际加入**的条数。维度与已有索引不一致时抛 ValueError：
        此前这里 `except Exception: return 0`，把「维度不匹配」和
        「什么都没加」混成同一个返回值 0，调用方只看到「加了 0 条」，
        既不知道失败也不知道为什么——索引里 4 维数据与 384 维调用方
        共存时会永久静默失效。
        """
        if len(vectors) != len(ids):
            return 0

        with self._lock:
            batch = np.array(vectors, dtype=np.float32)
            # 维度自检：与已有索引不一致必须显式报错，不能静默丢弃
            if self._is_built and self._index is not None and self._index.size:
                existing_dim = self._index.shape[1] if self._index.ndim == 2 else None
                if existing_dim is not None and existing_dim != batch.shape[1]:
                    raise ValueError(
                        f"向量维度不匹配: 索引已存 {existing_dim} 维，"
                        f"本次传入 {batch.shape[1]} 维。索引可能来自其他"
                        f"模型或陈旧缓存（{self._index_file}），"
                        f"请清理缓存或重建索引。"
                    )
            try:
                batch = self._normalize(batch)

                self._add_to_backend(batch, ids)
                self._size += len(ids)
                self._maybe_rebuild_index()
                self._save()
                return len(ids)
            except Exception as e:
                logger.debug(f"Vector index batch add failed: {e}")
                return 0

    def search(self, query_vec: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """搜索最相似的 top_k 个向量（线程安全）

        自动选择后端：hnswlib > FAISS > numpy brute-force。
        """
        with self._lock:
            if not self._is_built:
                return []

            # 刷新待写入数据
            self._flush_pending()

            try:
                query = np.array([query_vec], dtype=np.float32)
                qnorm = np.linalg.norm(query)
                if qnorm > 1e-8:
                    query = query / qnorm

                if self._use_hnsw and self._hnsw_index is not None:
                    return self._search_hnsw(query, top_k)
                elif self._use_faiss and self._faiss_index is not None:
                    return self._search_faiss(query[0], top_k)
                elif self._index is not None:
                    return self._search_numpy(query[0], top_k)
                else:
                    return []
            except Exception as e:
                logger.debug(f"Vector index search failed: {e}")
                return []

    def _search_hnsw(self, query: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """hnswlib 近似最近邻搜索"""
        indices, distances = self._hnsw_index.knn_query(query.reshape(1, -1), k=top_k)
        results = []
        for idx, dist in zip(indices[0], distances[0], strict=False):
            if idx < len(self._ids):
                # hnswlib 返回距离，转换为相似度
                similarity = 1.0 - dist
                if similarity > 0:
                    results.append((self._ids[idx], float(similarity)))
        return results

    def _search_faiss(self, query: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """FAISS 近似最近邻搜索"""
        distances, indices = self._faiss_index.search(query.reshape(1, -1), top_k)
        results = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx >= 0 and idx < len(self._ids) and dist > 0:
                results.append((self._ids[idx], float(dist)))
        return results

    def _search_numpy(self, query: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """numpy brute-force 搜索（预归一化，直接 dot product）"""
        similarities = np.dot(self._index, query)

        if len(similarities) <= top_k:
            top_indices = np.argsort(similarities)[::-1]
        else:
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])][::-1]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim > 0:
                results.append((self._ids[idx], sim))
        return results

    def search_batch(self, query_vecs: list[list[float]], top_k: int = 10) -> list[list[tuple[str, float]]]:
        """批量搜索"""
        return [self.search(qv, top_k) for qv in query_vecs]

    def build_from_drawers(self, drawers: list, embedder=None, min_count: int = 100) -> bool:
        """从 Drawer 列表构建索引

        Args:
            drawers: 记忆列表
            embedder: 向量嵌入器
            min_count: 最少需要多少条记忆才构建索引
        """
        if len(drawers) < min_count:
            logger.debug(f"Not enough drawers for index: {len(drawers)} < {min_count}")
            return False

        if embedder is None:
            return False

        vectors = []
        ids = []
        try:
            for d in drawers:
                emb = embedder.embed(d.content)
                if emb:
                    vectors.append(emb)
                    ids.append(d.id)
        except Exception as e:
            logger.warning(f"Failed to encode drawers: {e}")
            return False

        return self.build(vectors, ids)

    def clear(self):
        """清空索引（线程安全）"""
        with self._lock:
            self._index = None
            self._faiss_index = None
            self._hnsw_index = None
            self._ids = []
            self._is_built = False
            self._size = 0
            self._use_faiss = False
            self._use_hnsw = False
            self._pending_vectors.clear()
            self._pending_ids.clear()
            self._pending_count = 0

    def stats(self) -> dict:
        """索引统计"""
        if self._use_faiss:
            mem_mb = 0
            try:
                import faiss

                mem_mb = faiss.index_memory(self._faiss_index) / 1024 / 1024
            except Exception:
                pass
            return {
                "backend": "faiss",
                "is_built": self._is_built,
                "size": self._size,
                "dim": self.dim,
                "memory_mb": round(mem_mb, 2),
            }
        return {
            "backend": "numpy",
            "is_built": self._is_built,
            "size": self._size,
            "dim": self.dim,
            "memory_mb": round(self._index.nbytes / 1024 / 1024, 2) if self._index is not None else 0,
        }


class HolographicIndex:
    """全息索引 — 多维度向量索引

    为全息记忆的每个维度维护独立索引，支持跨维度融合搜索。
    """

    def __init__(self):
        self._indices: dict[str, VectorIndex] = {}
        self._is_built: bool = False
        self._hologram_count: int = 0

    @property
    def is_built(self) -> bool:
        return self._is_built and len(self._indices) > 0

    def build(self, holograms: list) -> bool:
        """从全息记忆列表构建多维度索引"""
        from .hologram import FUSION_ORDER, PROJECTION_DIMS

        if not holograms:
            return False

        # 按维度分组构建
        for dim in FUSION_ORDER:
            vectors = []
            ids = []
            for holo in holograms:
                proj = holo.get(dim)
                if proj is not None:
                    vectors.append(proj.tolist())
                    ids.append(holo.item_id)

            if vectors:
                # 全息子索引按维度落盘（文件名含维度，彼此不冲突），
                # 归全息单例所有，因此声明持久化。
                idx = VectorIndex(dim=PROJECTION_DIMS.get(dim, 384), persist=True)
                idx.build(vectors, ids)
                self._indices[dim] = idx

        self._is_built = len(self._indices) > 0
        self._hologram_count = len(holograms)
        logger.info(f"Holographic index built: {len(self._indices)} dimensions, {self._hologram_count} holograms")
        return self._is_built

    def fused_search(self, query_projections: dict, weights: dict, top_k: int = 10) -> list[tuple[str, float]]:
        """跨维度融合搜索

        Args:
            query_projections: 查询的维度投影 {dim: vector}
            weights: 各维度权重 {dim: weight}
            top_k: 返回数量

        Returns:
            [(item_id, fused_score), ...]
        """
        from .hologram import FUSION_ORDER

        fused_scores: dict[str, float] = {}

        for dim in FUSION_ORDER:
            weight = weights.get(dim, 0)
            if weight <= 0 or dim not in query_projections:
                continue

            idx = self._indices.get(dim)
            if idx is None:
                continue

            qv = query_projections[dim]
            if isinstance(qv, np.ndarray):
                qv = qv.tolist()

            dim_results = idx.search(qv, top_k=top_k * 3)
            for item_id, sim in dim_results:
                fused_scores[item_id] = fused_scores.get(item_id, 0) + sim * weight

        return sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def stats(self) -> dict:
        return {
            "is_built": self._is_built,
            "hologram_count": self._hologram_count,
            "dimensions": list(self._indices.keys()),
            "dim_sizes": {dim: idx.size for dim, idx in self._indices.items()},
        }


_vector_index: VectorIndex | None = None
_holographic_index: HolographicIndex | None = None
_vector_index_lock = threading.Lock()
_holographic_index_lock = threading.Lock()
_vector_index_key: tuple | None = None


def _vector_index_fingerprint(dim: int) -> tuple:
    """索引身份指纹：缓存目录 + 维度

    两者任一变化都必须换新实例——缓存目录决定落盘/加载位置，维度决定
    `_index` 的形状。指纹相同但实例为 None 时才复用，避免把 A 目录的
    索引当成 B 目录的数据继续用。
    """
    import os
    from pathlib import Path

    cache_dir = os.environ.get("PANGU_CACHE_DIR", str(Path.home() / ".cache" / "pangu"))
    return (cache_dir, dim)


def get_vector_index(dim: int = 384) -> VectorIndex:
    global _vector_index, _vector_index_key
    key = _vector_index_fingerprint(dim)
    if _vector_index is None or _vector_index_key != key:
        with _vector_index_lock:
            if _vector_index is None or _vector_index_key != key:
                _vector_index = VectorIndex(dim=dim, persist=True)
                _vector_index_key = key
    return _vector_index


def reset_vector_index() -> None:
    """丢弃向量索引单例，下次获取时按当前缓存目录重新加载。

    单例一旦建立就长期持有已加载的 `_index` 数据与后端句柄。缓存目录被
    切换（测试隔离）或索引数据被外部替换后，旧单例会把**陈旧数据**当作
    "已有向量"继续使用——维度不符时 `add_batch` 抛错并被吞，搜索恒为空。
    与 `reset_multimodal_pipeline()` / `reset_exposure_filter()` 同一类
    重置入口：持有持久化状态或 config 的单例都必须能被显式复位。
    """
    global _vector_index, _vector_index_key
    with _vector_index_lock:
        _vector_index = None
        _vector_index_key = None


def reset_holographic_index() -> None:
    """丢弃全息索引单例（理由同 reset_vector_index）"""
    global _holographic_index
    with _holographic_index_lock:
        _holographic_index = None


def get_holographic_index() -> HolographicIndex:
    global _holographic_index
    if _holographic_index is None:
        with _holographic_index_lock:
            if _holographic_index is None:
                _holographic_index = HolographicIndex()
    return _holographic_index
