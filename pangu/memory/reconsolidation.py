"""盘古记忆巩固增强 — 再巩固引擎 + 共鸣匹配

从伏羲移植：
1. 再巩固引擎 — 定期刷新重要记忆的衰减分数，模拟睡眠记忆巩固
2. 共鸣匹配 — 发现情感/语义共鸣的记忆对，建立关联

纯大脑能力：只做记忆维护和关联发现，不执行任务。
"""

import logging
from datetime import datetime

logger = logging.getLogger("pangu.memory.reconsolidation")


class ReconsolidationEngine:
    """再巩固引擎 — 定期刷新重要记忆的衰减分数

    模拟人类睡眠中的记忆巩固过程：
    - 选择中等重要性且衰减中的记忆
    - 基于重要性给予衰减分数提升
    - 避免重要记忆被过早遗忘
    """

    def __init__(self, config=None):
        self.config = config
        self._last_run: float = 0.0
        self._runs: int = 0
        self._total_boosted: int = 0

    def run(self, drawers: list, min_importance: float = 0.3,
            max_importance: float = 0.7, limit: int = 20) -> dict:
        """执行再巩固

        Args:
            drawers: 记忆列表
            min_importance: 最低重要性
            max_importance: 最高重要性
            limit: 每次处理上限
        """
        # 选择中等重要性且一段时间未更新的记忆
        candidates = []
        for d in drawers:
            if min_importance <= d.importance <= max_importance:
                try:
                    dt = datetime.fromisoformat(d.created_at)
                    days_old = (datetime.now() - dt).days
                    if days_old > 1:  # 至少存在1天
                        candidates.append(d)
                except (ValueError, TypeError):
                    pass

        candidates.sort(key=lambda d: d.importance)
        candidates = candidates[:limit]

        boosted = 0
        for d in candidates:
            boost = (d.importance * 0.2) + 0.05  # 基于重要性提升
            old_importance = d.importance
            d.importance = min(5.0, old_importance + boost)
            boosted += 1

        self._runs += 1
        self._total_boosted += boosted
        self._last_run = datetime.now().timestamp()

        state = {
            "candidates": len(candidates),
            "boosted": boosted,
            "avg_boost": round((0.3 * 0.2 + 0.05 + 0.7 * 0.2 + 0.05) / 2, 3),
            "timestamp": datetime.now().isoformat(),
            "total_runs": self._runs,
            "total_boosted": self._total_boosted,
        }
        logger.info(f"Reconsolidation: {boosted}/{len(candidates)} boosted")
        return state

    def stats(self) -> dict:
        return {
            "runs": self._runs,
            "total_boosted": self._total_boosted,
            "last_run": datetime.fromtimestamp(self._last_run).isoformat() if self._last_run else None,
        }


class ResonanceEngine:
    """共鸣匹配引擎 — 发现情感/语义共鸣的记忆对

    纯大脑能力：通过向量相似度+情感同向性发现记忆间的共鸣关系。
    共鸣是指两条记忆在语义上相似且情感倾向一致，形成"情感共鸣"。
    """

    def __init__(self, config=None):
        self.config = config
        self._embedder = None
        self._last_run: float = 0.0
        self._matches_found: int = 0

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService
                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    def find_resonance(self, drawers: list, limit: int = 30,
                       sim_threshold: float = 0.99) -> list[dict]:
        """发现共鸣记忆对

        Args:
            drawers: 记忆列表
            limit: 扫描数量上限
            sim_threshold: 相似度阈值
        """
        if not self.embedder:
            return []

        from .fts_search import cosine_similarity

        # 取有情感标记的记忆（或全部记忆）
        candidates = drawers[:limit]

        if len(candidates) < 2:
            return []

        # 编码所有候选记忆
        try:
            _ids = [d.id for d in candidates]
            texts = [d.content for d in candidates]
            embeddings = self.embedder.embed_batch(texts)
            if not embeddings:
                return []
        except Exception:
            return []

        matches = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                self._try_resonance_match(
                    candidates, embeddings, i, j, sim_threshold, matches
                )

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        top_matches = matches[:10]

        self._matches_found += len(top_matches)
        self._last_run = datetime.now().timestamp()

        return top_matches

    def _try_resonance_match(self, candidates, embeddings, i, j,
                             sim_threshold: float, matches: list):
        try:
            if embeddings[i] and embeddings[j]:
                self._compute_and_append_match(
                    candidates[i], candidates[j], embeddings[i], embeddings[j],
                    sim_threshold, matches
                )
        except Exception:
            pass

    def _build_match_result(self, cand_a, cand_b, sim: float) -> dict:
        return {
            "source_id": cand_a.id,
            "target_id": cand_b.id,
            "source_content": cand_a.content[:100],
            "target_content": cand_b.content[:100],
            "similarity": round(sim, 3),
            "source_wing": cand_a.wing,
            "target_wing": cand_b.wing,
        }

    def _compute_and_append_match(self, cand_a, cand_b, emb_a, emb_b,
                                   sim_threshold: float, matches: list):
        from .fts_search import cosine_similarity
        sim = cosine_similarity(emb_a, emb_b)
        if sim >= sim_threshold:
            matches.append(self._build_match_result(cand_a, cand_b, sim))

    def _find_cross_matches(self, wings: list, wing_groups: dict,
                            sim_threshold: float) -> list[dict]:
        cross_matches = []
        for a_idx in range(len(wings)):
            for b_idx in range(a_idx + 1, len(wings)):
                wing_a = wings[a_idx]
                wing_b = wings[b_idx]
                self._match_wing_pair(
                    wing_groups[wing_a][:5], wing_groups[wing_b][:5],
                    wing_a, wing_b, sim_threshold, cross_matches
                )
        return cross_matches

    def _match_wing_pair(self, drawables_a: list, drawables_b: list,
                         wing_a: str, wing_b: str,
                         sim_threshold: float, cross_matches: list):
        for da in drawables_a:
            for db in drawables_b:
                self._try_cross_match(
                    da, db, wing_a, wing_b, sim_threshold, cross_matches
                )

    def _try_cross_match(self, da, db, wing_a: str, wing_b: str,
                         sim_threshold: float, cross_matches: list):
        try:
            emb_a = self.embedder.embed(da.content)
            emb_b = self.embedder.embed(db.content)
            if not (emb_a and emb_b):
                return
            from .fts_search import cosine_similarity
            sim = cosine_similarity(emb_a, emb_b)
            if sim >= sim_threshold:
                cross_matches.append({
                    "source_id": da.id,
                    "target_id": db.id,
                    "source_wing": wing_a,
                    "target_wing": wing_b,
                    "source_content": da.content[:100],
                    "target_content": db.content[:100],
                    "similarity": round(sim, 3),
                })
        except Exception:
            pass

    def find_cross_wing_resonance(self, drawers: list, sim_threshold: float = 0.99) -> list[dict]:
        """发现跨 Wing 的共鸣关系 — 不同领域间的知识迁移

        只考虑不同 Wing 之间的记忆对，发现潜在的知识关联。
        """
        if not self.embedder:
            return []

        # 按 Wing 分组
        wing_groups: dict[str, list] = {}
        for d in drawers:
            wing_groups.setdefault(d.wing, []).append(d)

        wings = list(wing_groups.keys())
        if len(wings) < 2:
            return []

        cross_matches = self._find_cross_matches(wings, wing_groups, sim_threshold)
        cross_matches.sort(key=lambda x: x["similarity"], reverse=True)
        return cross_matches[:10]

    def stats(self) -> dict:
        return {
            "matches_found": self._matches_found,
            "last_run": datetime.fromtimestamp(self._last_run).isoformat() if self._last_run else None,
        }
