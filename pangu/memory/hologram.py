"""盘古全息记忆编码 — 多维度投影 + 跨维度检索

从伏羲移植：将记忆分解为语义/时空/情感/因果/来源五维投影，
支持任一维度独立检索，跨维度加权融合重建完整记忆。

纯大脑能力：不执行任务，只做记忆编码和检索。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from pangu.core.hashing import int_hash

logger = logging.getLogger("pangu.memory.hologram")

PROJECTION_DIMS = {
    "semantic": 1024,
    "temporal": 256,
    "emotional": 128,
    "causal": 256,
    "source": 128,
}

FUSION_ORDER = ["semantic", "temporal", "emotional", "causal", "source"]

DEFAULT_FUSION_WEIGHTS = {
    "semantic": 0.40,
    "temporal": 0.15,
    "emotional": 0.15,
    "causal": 0.20,
    "source": 0.10,
}


@dataclass
class Hologram:
    """全息记忆投影 — 一条记忆的多维度编码"""

    item_id: str
    projections: dict[str, np.ndarray] = field(default_factory=dict)

    def get(self, dim: str) -> np.ndarray | None:
        return self.projections.get(dim)

    def all_dims(self) -> list[str]:
        return [d for d in FUSION_ORDER if d in self.projections]

    @property
    def byte_size(self) -> int:
        return sum(v.nbytes for v in self.projections.values())


class TemporalEncoder:
    """时空投影编码器 — 将时间+空间位置编码为256维向量"""

    def __init__(self, dim: int = 256):
        self._dim = dim
        self._rng = np.random.default_rng(42)

    def encode(self, created_at: str = "", wing: str = "", room: str = "", sequence_position: int = 0) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                vec[0] = np.sin(2 * np.pi * dt.hour / 24.0)
                vec[1] = np.cos(2 * np.pi * dt.hour / 24.0)
                vec[2] = np.sin(2 * np.pi * dt.weekday() / 7.0)
                vec[3] = np.cos(2 * np.pi * dt.weekday() / 7.0)
                vec[4] = np.sin(2 * np.pi * dt.month / 12.0)
                vec[5] = np.cos(2 * np.pi * dt.month / 12.0)

                ts_hash = int_hash(created_at)
                for i in range(6, min(38, self._dim)):
                    idx = (ts_hash + i * 31) % self._dim
                    vec[idx] += 0.5
            except Exception:
                pass

        # 空间编码（wing + room）
        location_str = f"{wing}/{room}"
        if location_str:
            lh = int_hash(location_str)
            for i in range(40, min(80, self._dim)):
                idx = (lh + i * 37) % self._dim
                vec[idx] += 0.3

        if sequence_position > 0:
            pos_signal = 1.0 / (1.0 + sequence_position)
            for i in range(80, min(120, self._dim)):
                vec[(sequence_position * 13 + i * 41) % self._dim] += pos_signal

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class EmotionalEncoder:
    """情感投影编码器 — 将 PAD 三维情感编码为 128 维向量

    PAD 模型:
    - Pleasure (愉悦度): -1.0 ~ 1.0
    - Arousal (唤醒度): 0.0 ~ 1.0
    - Dominance (支配度): 0.0 ~ 1.0
    """

    def __init__(self, dim: int = 128):
        self._dim = dim

    def encode(self, valence: float = 0.0, arousal: float = 0.0, dominance: float = 0.5) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        v = max(-1.0, min(1.0, valence))
        a = max(0.0, min(1.0, arousal))
        d = max(0.0, min(1.0, dominance))

        vec[0] = v
        vec[1] = a
        vec[2] = d

        for i in range(3, min(20, self._dim)):
            phase = (i - 3) * np.pi / 17
            vec[i] = v * np.sin(phase) + a * np.cos(phase)

        for i in range(20, min(50, self._dim)):
            idx = int(abs(v * 10 + a * 5) * (self._dim - 20))
            j = (idx + i * 7) % (self._dim - 20) + 20
            vec[j] += 0.3

        for i in range(50, min(90, self._dim)):
            if a > 0.3:
                vec[i] = a * 0.5 * (1.0 if v >= 0 else -1.0)

        for i in range(90, min(self._dim, 128)):
            vec[i] = d * 0.4

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class CausalEncoder:
    """因果投影编码器 — 将因果链摘要编码为 256 维向量"""

    def __init__(self, dim: int = 256):
        self._dim = dim
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService

                self._embedder = EmbeddingService()
            except ImportError:
                self._embedder = None
        return self._embedder

    def encode(self, causal_summary: str = "") -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        if not causal_summary:
            return vec

        try:
            if self.embedder:
                emb = self.embedder.embed(causal_summary)
                if emb:
                    for i, v in enumerate(emb[: min(len(emb), self._dim)]):
                        vec[i] = v
                    norm = np.linalg.norm(vec)
                    if norm > 1e-8:
                        vec /= norm
                    return vec
        except Exception as e:
            logger.debug(f"Causal encoding failed: {e}")

        # 降级到哈希编码
        h = int_hash(causal_summary)
        for i in range(self._dim):
            idx = (h + i * 67) % self._dim
            bit = (h >> (i % 64)) & 1
            vec[idx] += 0.3 if bit else -0.3
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class SourceEncoder:
    """来源投影编码器 — 将来源信息编码为 128 维向量"""

    def __init__(self, dim: int = 128):
        self._dim = dim

    def encode(self, source_type: str = "", agent_id: str = "", session_id: str = "") -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)

        parts = [source_type, agent_id, session_id]
        for part_idx, part in enumerate(parts):
            if not part:
                continue
            h = int_hash(part)
            offset = part_idx * 40
            for i in range(min(40, self._dim - offset)):
                idx = offset + (h + i * 43) % min(40, self._dim - offset)
                if 0 <= idx < self._dim:
                    bit = (h >> (i % 64)) & 1
                    vec[idx] += 0.4 if bit else -0.4

        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec /= norm
        return vec


class HolographicEncoder:
    """全息编码器 — 统一入口，将记忆编码为多维度投影 Hologram"""

    def __init__(self, config=None):
        self.config = config
        self.temporal = TemporalEncoder(dim=PROJECTION_DIMS["temporal"])
        self.emotional = EmotionalEncoder(dim=PROJECTION_DIMS["emotional"])
        self.causal = CausalEncoder(dim=PROJECTION_DIMS["causal"])
        self.source = SourceEncoder(dim=PROJECTION_DIMS["source"])
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService

                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    def _encode_semantic(self, raw_text: str) -> np.ndarray | None:
        try:
            semantic_vec = self.embedder.embed(raw_text)
            if semantic_vec:
                return np.array(semantic_vec, dtype=np.float32)
        except Exception as e:
            logger.debug(f"Semantic encoding failed: {e}")
        return None

    def _encode_semantic_projection(self, raw_text: str) -> dict[str, np.ndarray]:
        """编码语义投影"""
        projections = {}
        if self.embedder and raw_text:
            semantic = self._encode_semantic(raw_text)
            if semantic is not None:
                projections["semantic"] = semantic
        return projections

    def encode(
        self,
        item_id: str,
        raw_text: str,
        created_at: str = "",
        wing: str = "",
        room: str = "",
        sequence_position: int = 0,
        valence: float = 0.0,
        arousal: float = 0.0,
        dominance: float = 0.5,
        causal_summary: str = "",
        source_type: str = "",
        agent_id: str = "",
        session_id: str = "",
    ) -> Hologram:
        projections = self._encode_semantic_projection(raw_text)

        projections["temporal"] = self.temporal.encode(created_at, wing, room, sequence_position)
        projections["emotional"] = self.emotional.encode(valence, arousal, dominance)
        projections["causal"] = self.causal.encode(causal_summary)
        projections["source"] = self.source.encode(source_type, agent_id, session_id)

        return Hologram(item_id=item_id, projections=projections)

    def encode_from_drawer(
        self, drawer, causal_summary: str = "", source_type: str = "", agent_id: str = "", session_id: str = ""
    ) -> Hologram:
        """从 Drawer 对象编码"""
        return self.encode(
            item_id=drawer.id,
            raw_text=drawer.content,
            created_at=drawer.created_at,
            wing=drawer.wing,
            room=drawer.room,
            tags=drawer.tags,
            causal_summary=causal_summary,
            source_type=source_type or drawer.source_file or "",
            agent_id=agent_id,
            session_id=session_id,
        )


class HolographicSearch:
    """全息搜索 — 跨维度加权融合检索

    支持 "昨天下午让我焦虑的那件事" 这样的跨维度自然语言查询。
    """

    def __init__(self, encoder: HolographicEncoder = None):
        self.encoder = encoder or HolographicEncoder()

    def search(
        self,
        query: str,
        holograms: list[Hologram],
        weights: dict = None,
        top_k: int = 10,
    ) -> list[dict]:
        """全息搜索主入口

        Args:
            query: 自然语言查询
            holograms: 全息记忆列表
            weights: 各维度权重 {"semantic": 0.4, "temporal": 0.15, ...}
            top_k: 返回数量
        """
        if weights is None:
            weights = DEFAULT_FUSION_WEIGHTS

        # 编码查询投影
        query_holo = self.encoder.encode(
            item_id="__query__",
            raw_text=query,
            created_at=datetime.now().isoformat(),
        )

        scores = []
        for holo in holograms:
            dim_scores = {}
            for dim in FUSION_ORDER:
                weight = weights.get(dim, 0)
                if weight <= 0:
                    continue
                qv = query_holo.get(dim)
                hv = holo.get(dim)
                if qv is not None and hv is not None:
                    from .fts_search import cosine_similarity

                    dim_scores[dim] = cosine_similarity(qv.tolist(), hv.tolist()) * weight

            if dim_scores:
                fused = sum(dim_scores.values())
                scores.append((holo.item_id, fused, dim_scores))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [
            {"item_id": item_id, "score": round(score, 4), "dimensions": dims}
            for item_id, score, dims in scores[:top_k]
        ]


_holographic_encoder: HolographicEncoder | None = None


def get_holographic_encoder(config=None) -> HolographicEncoder:
    """获取全息编码器单例"""
    global _holographic_encoder
    if _holographic_encoder is None:
        _holographic_encoder = HolographicEncoder(config)
    return _holographic_encoder
