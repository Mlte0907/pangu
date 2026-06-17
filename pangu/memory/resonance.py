"""盘古共鸣匹配 — 发现情感/语义共鸣的记忆对，构建图谱边

从伏羲移植并适配盘古架构：
1. 向量相似度 + 情感同向性发现共鸣对
2. 高共鸣对自动建立图谱边
3. 跨 Wing 知识迁移发现
"""

import logging
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.resonance")


class ResonanceEngine:
    """共鸣匹配引擎 — 发现情感/语义共鸣的记忆对并构建图谱边"""

    def __init__(self, config: PanguConfig | None = None):
        self.config = config
        self._embedder = None
        self._last_run: float = 0.0
        self._matches_found: int = 0
        self._edges_created: int = 0

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from .embedding import EmbeddingService
                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    def find_resonance(self, drawers: list[Drawer], limit: int = 30,
                       sim_threshold: float = 0.7) -> list[dict]:
        """发现共鸣记忆对

        Args:
            drawers: 记忆列表
            limit: 扫描数量上限
            sim_threshold: 相似度阈值
        """
        if not self.embedder or len(drawers) < 2:
            return []

        candidates = drawers[:limit]

        try:
            texts = [d.content for d in candidates]
            embeddings = self.embedder.embed_batch(texts)
            if not embeddings:
                return []
        except Exception:
            return []

        matches = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                try:
                    if not (embeddings[i] and embeddings[j]):
                        continue
                    from .fts_search import cosine_similarity
                    sim = cosine_similarity(embeddings[i], embeddings[j])
                    same_dir = candidates[i].emotional_weight * candidates[j].emotional_weight > 0
                    if sim >= sim_threshold and same_dir:
                        matches.append({
                            "source_id": candidates[i].id,
                            "target_id": candidates[j].id,
                            "source_preview": candidates[i].content[:80],
                            "target_preview": candidates[j].content[:80],
                            "similarity": round(sim, 3),
                            "source_wing": candidates[i].wing,
                            "target_wing": candidates[j].wing,
                        })
                except Exception:
                    continue

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        top_matches = matches[:10]

        self._matches_found += len(top_matches)
        self._last_run = datetime.now().timestamp()

        return top_matches

    def build_edges(self, matches: list[dict], drawers: list[Drawer],
                    max_edges: int = 5) -> list[dict]:
        """为高共鸣匹配建立图谱边

        Args:
            matches: find_resonance 返回的匹配列表
            drawers: 记忆列表（用于更新 importance）
            max_edges: 最多建立边数
        """
        created = []
        for m in matches[:max_edges]:
            try:
                src = next((d for d in drawers if d.id == m["source_id"]), None)
                tgt = next((d for d in drawers if d.id == m["target_id"]), None)
                if not src or not tgt:
                    continue

                edge = {
                    "source_id": m["source_id"],
                    "target_id": m["target_id"],
                    "edge_type": "related_to",
                    "weight": m["similarity"],
                    "created_at": datetime.now().isoformat(),
                }

                src.metadata.setdefault("edges", []).append(edge)
                tgt.metadata.setdefault("edges", []).append(edge)
                created.append(edge)
            except Exception:
                continue

        self._edges_created += len(created)
        return created

    def compute_similarity(self, drawer_a: Drawer, drawer_b: Drawer) -> float:
        """计算两条记忆的语义相似度"""
        if not self.embedder:
            return 0.0
        try:
            from .fts_search import cosine_similarity
            emb_a = self.embedder.embed(drawer_a.content)
            emb_b = self.embedder.embed(drawer_b.content)
            if not (emb_a and emb_b):
                return 0.0
            return cosine_similarity(emb_a, emb_b)
        except Exception:
            return 0.0

    def stats(self) -> dict:
        return {
            "matches_found": self._matches_found,
            "edges_created": self._edges_created,
            "last_run": datetime.fromtimestamp(self._last_run).isoformat() if self._last_run else None,
        }


_resonance_engine: ResonanceEngine | None = None


def get_resonance_engine(config: PanguConfig | None = None) -> ResonanceEngine:
    global _resonance_engine
    if _resonance_engine is None:
        _resonance_engine = ResonanceEngine(config)
    return _resonance_engine
