"""盘古梦境巩固 — 5步睡眠整理周期

移植自伏羲 dream.py，适配盘古架构：
- 使用 PanguConfig + Drawer 替代 Fuxi 的 CognitiveEngine
- 5步流程：fetch → dedup → link → decay → distill
- 纯记忆层编排，操作 Drawer 列表
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.dream")


class DreamConsolidation:
    """梦境记忆巩固 — 5步睡眠整理流程"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._last_state: dict = {}
        self._cycle_count = 0

    def run_dream_cycle(self, drawers: list) -> dict:
        """运行一次完整的梦境巩固周期"""
        steps_log: list[str] = []
        stats: dict[str, int] = {
            "consolidated": 0,
            "linked": 0,
            "pruned": 0,
            "distilled": 0,
        }

        if not drawers:
            return {"status": "empty", "steps": [], "stats": stats}

        recent = self._step_fetch_recent(drawers, limit=50)
        steps_log.append(f"fetch: {len(recent)} items")

        merged = self._step_dedup(recent)
        steps_log.append(f"dedup: {merged} merged")
        stats["consolidated"] = merged

        linked = self._step_link(recent)
        steps_log.append(f"link: {linked} edges")
        stats["linked"] = linked

        pruned = self._step_decay(drawers)
        steps_log.append(f"decay: {pruned} pruned")
        stats["pruned"] = pruned

        distilled = self._step_distill(recent)
        steps_log.append(f"distill: {distilled} candidates")
        stats["distilled"] = distilled

        self._cycle_count += 1
        state = {
            "status": "completed",
            "stats": stats,
            "steps": steps_log,
            "cycle": self._cycle_count,
            "timestamp": datetime.now().isoformat(),
        }
        self._last_state = state
        return state

    def deduplicate(self, drawers: list) -> dict:
        """去重检查：基于 Jaccard(3-gram) 相似度"""
        merged = self._step_dedup(drawers)
        return {"merged": merged, "timestamp": datetime.now().isoformat()}

    def link_memories(self, drawers: list) -> dict:
        """建立关联：发现记忆间的语义关联"""
        linked = self._step_link(drawers)
        return {
            "linked": linked,
            "pairs": self._link_pairs[-10:] if hasattr(self, "_link_pairs") else [],
            "timestamp": datetime.now().isoformat(),
        }

    def distill(self, drawers: list) -> dict:
        """蒸馏总结：标记高价值记忆作为知识蒸馏候选"""
        candidates = self._step_distill(drawers)
        return {
            "distilled": candidates,
            "timestamp": datetime.now().isoformat(),
        }

    def dream_stats(self) -> dict:
        """获取梦境统计"""
        return {
            "cycle_count": self._cycle_count,
            "last_state": self._last_state,
        }

    # ── 内部步骤 ──

    def _step_fetch_recent(self, drawers: list, limit: int = 50) -> list:
        """检索近期记忆（按重要性 + 时间排序）"""
        sorted_d = sorted(
            drawers,
            key=lambda d: (d.importance, d.created_at),
            reverse=True,
        )
        return sorted_d[:limit]

    def _step_dedup(self, items: list) -> int:
        """去重：Jaccard(3-gram) 相似度 > 0.85 的合并较旧的"""
        merged = 0
        merged_ids: set[str] = set()

        for i in range(len(items)):
            if items[i].id in merged_ids:
                continue
            for j in range(i + 1, len(items)):
                if items[j].id in merged_ids:
                    continue
                sim = self._jaccard_similarity(items[i].content, items[j].content)
                if sim > 0.85:
                    older = (
                        items[j]
                        if items[i].created_at > items[j].created_at
                        else items[i]
                    )
                    merged_ids.add(older.id)
                    merged += 1
                if merged >= 20:
                    break

        return merged

    def _step_link(self, items: list) -> int:
        """建立关联：3-gram Jaccard 在 (0.3, 0.85) 之间建立 related_to 边"""
        self._link_pairs = []
        linked = 0

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                sim = self._jaccard_similarity(items[i].content, items[j].content)
                if 0.3 < sim < 0.85:
                    self._link_pairs.append({
                        "source": items[i].id,
                        "target": items[j].id,
                        "weight": round(sim, 3),
                    })
                    linked += 1
                if linked >= 50:
                    break
            if linked >= 50:
                break

        return linked

    def _step_decay(self, drawers: list) -> int:
        """衰减修剪：标记低重要性记忆"""
        return sum(
            1 for d in drawers
            if d.importance < 2.0
        )

    def _step_distill(self, items: list) -> int:
        """蒸馏候选：高重要性记忆作为知识蒸馏候选"""
        return sum(
            1 for d in items
            if d.importance >= 4.0
        )

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        """3-gram Jaccard 相似度"""
        if not a or not b:
            return 0.0
        a_grams = {a[i:i + 3] for i in range(max(0, len(a) - 2))}
        b_grams = {b[i:i + 3] for i in range(max(0, len(b) - 2))}
        if not a_grams or not b_grams:
            return 0.0
        intersection = len(a_grams & b_grams)
        union = len(a_grams | b_grams)
        return intersection / union if union > 0 else 0.0


_instance: DreamConsolidation | None = None


def get_dream_engine(config: PanguConfig = None) -> DreamConsolidation:
    global _instance
    if _instance is None:
        _instance = DreamConsolidation(config)
    return _instance
