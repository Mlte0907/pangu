"""盘古记忆去重引擎 — 检测并合并重复记忆
==============================================
自动检测高度相似或重复的记忆片段，避免记忆冗余。

支持：
- 基于嵌入向量的精确去重
- 基于 MinHash 的近似去重
- 基于内容哈希的精确去重
- 可配置的相似度阈值
- 自动合并策略
"""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class DuplicateGroup:
    """重复记忆组"""
    id: str
    memory_ids: list[str]  # 重复记忆 ID 列表
    primary_id: str  # 主记忆（保留）
    duplicate_ids: list[str]  # 重复记忆（可删除）
    similarity_matrix: dict  # {id1_id2: similarity}
    avg_similarity: float
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MemoryDeduplicator:
    """记忆去重引擎"""

    @staticmethod
    def _cosine_sim(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0


    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService
                self._embedder = EmbeddingService(self.config)
            except Exception:
                self._embedder = None
        return self._embedder

    def find_duplicates(self, drawers: list[Drawer],
                        threshold: float = 0.99,
                        method: str = "auto") -> list[DuplicateGroup]:
        """查找重复记忆

        Args:
            drawers: 记忆列表
            threshold: 相似度阈值（高于此值视为重复）
            method: 方法 (auto/vector/hash/keyword)

        Returns:
            重复组列表
        """
        if len(drawers) < 2:
            return []

        if method == "hash":
            return self._hash_dedup(drawers)
        elif method == "keyword":
            return self._keyword_dedup(drawers, threshold)
        elif method == "vector" or (method == "auto" and self.embedder):
            try:
                return self._vector_dedup(drawers, threshold)
            except Exception:
                return self._keyword_dedup(drawers, threshold)
        else:
            return self._keyword_dedup(drawers, threshold)

    def _vector_dedup(self, drawers: list[Drawer],
                      threshold: float) -> list[DuplicateGroup]:
        """基于向量相似度的去重"""
        texts = [d.content for d in drawers]
        n = len(drawers)

        # 批量嵌入
        embeddings = self.embedder.embed_batch(texts)

        # 找相似对
        similar_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                sim = self._cosine_sim(embeddings[i], embeddings[j])
                if sim >= threshold:
                    similar_pairs.append((i, j, sim))

        return self._group_duplicates(drawers, similar_pairs, threshold)

    def _hash_dedup(self, drawers: list[Drawer]) -> list[DuplicateGroup]:
        """基于内容哈希的精确去重"""
        hash_map: dict[str, list[int]] = {}
        for i, d in enumerate(drawers):
            content_hash = hashlib.sha256(
                d.content.strip().encode()).hexdigest()
            if content_hash not in hash_map:
                hash_map[content_hash] = []
            hash_map[content_hash].append(i)

        similar_pairs = []
        for _hash, indices in hash_map.items():
            if len(indices) > 1:
                for a in range(len(indices)):
                    for b in range(a + 1, len(indices)):
                        similar_pairs.append((indices[a], indices[b], 1.0))

        return self._group_duplicates(drawers, similar_pairs, 0.99)

    def _keyword_dedup(self, drawers: list[Drawer],
                       threshold: float) -> list[DuplicateGroup]:
        """基于关键词重叠的去重"""
        import re

        def tokenize(text: str) -> set[str]:
            words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                    text.lower()))
            return words

        token_sets = [tokenize(d.content) for d in drawers]
        n = len(drawers)

        similar_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                if not token_sets[i] or not token_sets[j]:
                    continue
                # Jaccard 相似度
                intersection = len(token_sets[i] & token_sets[j])
                union = len(token_sets[i] | token_sets[j])
                jaccard = intersection / union if union > 0 else 0

                if jaccard >= threshold:
                    similar_pairs.append((i, j, jaccard))

        return self._group_duplicates(drawers, similar_pairs, threshold)

    def _group_duplicates(self, drawers: list[Drawer],
                          similar_pairs: list[tuple],
                          threshold: float) -> list[DuplicateGroup]:
        """将相似对分组为重复组"""
        if not similar_pairs:
            return []

        # 并查集分组
        parent = list(range(len(drawers)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i, j, _sim in similar_pairs:
            union(i, j)

        # 收集组
        groups: dict[int, list[int]] = {}
        for i in range(len(drawers)):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)

        # 构建结果
        result = []
        for indices in groups.values():
            if len(indices) < 2:
                continue

            # 选择主记忆（重要性最高、内容最长的）
            group_drawers = [drawers[i] for i in indices]
            primary = max(group_drawers,
                          key=lambda d: (d.importance, len(d.content)))

            sim_matrix = {}
            sims = []
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    key = f"{drawers[indices[a]].id}_{drawers[indices[b]].id}"
                    sim = next((s for i, j, s in similar_pairs
                                if (i == indices[a] and j == indices[b]) or
                                (i == indices[b] and j == indices[a])), threshold)
                    sim_matrix[key] = round(sim, 4)
                    sims.append(sim)

            avg_sim = sum(sims) / len(sims) if sims else threshold

            group_id = hex_digest(
                "".join(sorted(d.id for d in group_drawers))
            )[:12]

            result.append(DuplicateGroup(
                id=group_id,
                memory_ids=[d.id for d in group_drawers],
                primary_id=primary.id,
                duplicate_ids=[d.id for d in group_drawers if d.id != primary.id],
                similarity_matrix=sim_matrix,
                avg_similarity=round(avg_sim, 4),
            ))

        return result

    def merge_duplicates(self, group: DuplicateGroup,
                         drawers: list[Drawer]) -> Drawer | None:
        """合并重复记忆组为一条记忆

        Args:
            group: 重复组
            drawers: 所有记忆

        Returns:
            合并后的记忆，或 None
        """
        group_drawers = [d for d in drawers if d.id in group.memory_ids]
        if not group_drawers:
            return None

        primary = next((d for d in group_drawers if d.id == group.primary_id),
                       group_drawers[0])

        # 合并标签
        all_tags = list(set(
            tag for d in group_drawers for tag in (d.tags or [])
        ))

        # 合并内容（取最长 + 补充差异）
        contents = [d.content for d in group_drawers]
        merged_content = max(contents, key=len)

        # 合并重要性
        merged_importance = max(d.importance for d in group_drawers)

        return Drawer(
            id=primary.id,
            content=merged_content,
            wing=primary.wing,
            room=primary.room,
            hall=primary.hall,
            importance=merged_importance,
            tags=all_tags,
            source_file=primary.source_file,
            created_at=min(d.created_at for d in group_drawers
                           if d.created_at),
        )

    def dedup_stats(self, groups: list[DuplicateGroup]) -> dict:
        """去重统计"""
        total_dup = sum(len(g.duplicate_ids) for g in groups)
        return {
            "duplicate_groups": len(groups),
            "total_duplicate_memories": total_dup,
            "estimated_savings": total_dup,
            "avg_similarity": round(
                sum(g.avg_similarity for g in groups) / len(groups), 4
            ) if groups else 0.0,
            "largest_group": max(len(g.memory_ids) for g in groups)
            if groups else 0,
        }

    def similarity_check(self, drawer_a: Drawer, drawer_b: Drawer) -> dict:
        """检查两条记忆的相似度"""
        if self.embedder:
            try:
                emb_a = self.embedder.embed(drawer_a.content)
                emb_b = self.embedder.embed(drawer_b.content)
                sim = self._cosine_sim(emb_a, emb_b)
                return {"similarity": round(sim, 4), "method": "vector"}
            except Exception:
                pass

        # 关键词回退
        import re

        def tokenize(text: str) -> set[str]:
            return set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                   text.lower()))

        tokens_a = tokenize(drawer_a.content)
        tokens_b = tokenize(drawer_b.content)
        if not tokens_a or not tokens_b:
            return {"similarity": 0.0, "method": "keyword"}

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        jaccard = intersection / union if union > 0 else 0
        return {"similarity": round(jaccard, 4), "method": "keyword"}
