"""盘古记忆聚类引擎 — 自动主题发现与分组
==============================================
将记忆按语义相似度自动聚类，发现隐藏的主题模式。
支持：
- 基于嵌入向量的层次聚类
- 关键词共现聚类（轻量回退）
- 主题标签自动生成
- 聚类质量评估
"""
from collections import Counter
from dataclasses import dataclass

import numpy as np

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class MemoryCluster:
    """记忆聚类"""
    id: str
    label: str  # 聚类标签
    keywords: list[str]  # 关键词
    memory_ids: list[str]  # 记忆 ID 列表
    centroid: list[float] | None = None  # 聚类中心向量
    cohesion: float = 0.0  # 内聚度 [0,1]
    size: int = 0
    summary: str = ""  # 聚类摘要


class MemoryClusterer:
    """记忆聚类引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._embedder = None

    @property
    def embedder(self):
        """懒加载向量嵌入器"""
        if self._embedder is None:
            try:
                from ..search.embedder import VectorEmbedder
                self._embedder = VectorEmbedder(self.config)
            except Exception:
                self._embedder = None
        return self._embedder

    def cluster(self, drawers: list[Drawer], n_clusters: int = 0,
                min_similarity: float = 0.3) -> list[MemoryCluster]:
        """将记忆聚类为分组

        Args:
            drawers: 记忆列表
            n_clusters: 目标聚类数（0=自动）
            min_similarity: 最小相似度阈值

        Returns:
            聚类列表
        """
        if len(drawers) < 3:
            return [self._single_cluster(drawers)] if drawers else []

        # 尝试向量聚类
        if self.embedder:
            try:
                return self._vector_cluster(drawers, n_clusters, min_similarity)
            except Exception:
                pass

        # 回退到关键词聚类
        return self._keyword_cluster(drawers, n_clusters)

    def _vector_cluster(self, drawers: list[Drawer], n_clusters: int,
                        min_similarity: float) -> list[MemoryCluster]:
        """基于嵌入向量的层次聚类"""
        texts = [d.content for d in drawers]
        embeddings = self.embedder.embed_batch(texts)

        # 计算相似度矩阵
        n = len(drawers)
        sim_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.embedder.similarity(embeddings[i], embeddings[j])
                sim_matrix[i][j] = sim
                sim_matrix[j][i] = sim

        # 自动确定聚类数
        if n_clusters <= 0:
            n_clusters = max(2, min(n // 3, 15))

        # 简单层次聚类：贪心合并
        groups = {i: [i] for i in range(n)}
        merged = set()

        # 按相似度排序
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((sim_matrix[i][j], i, j))
        pairs.sort(reverse=True)

        for sim, i, j in pairs:
            if sim < min_similarity:
                break
            if i in merged or j in merged:
                continue
            # 合并两个组
            gi = self._find_group(groups, i)
            gj = self._find_group(groups, j)
            if gi == gj:
                continue
            if len(groups[gi]) + len(groups[gj]) > n // n_clusters + 1:
                continue
            groups[gi].extend(groups[gj])
            del groups[gj]
            merged.add(i)
            merged.add(j)

        # 构建聚类结果
        clusters = []
        for group_indices in groups.values():
            group_drawers = [drawers[i] for i in group_indices]
            cluster = self._build_cluster(group_drawers, group_indices, embeddings)
            clusters.append(cluster)

        clusters.sort(key=lambda c: c.size, reverse=True)
        return clusters

    def _find_group(self, groups: dict, idx: int) -> int:
        """找到 idx 所属的组"""
        for gid, members in groups.items():
            if idx in members:
                return gid
        return -1

    def _keyword_cluster(self, drawers: list[Drawer],
                         n_clusters: int = 0) -> list[MemoryCluster]:
        """基于关键词共现的聚类"""
        # 提取关键词
        all_keywords = []
        for d in drawers:
            words = self._extract_keywords(d.content)
            all_keywords.append(words)

        # 构建关键词共现矩阵
        keyword_docs = {}
        for i, keywords in enumerate(all_keywords):
            for kw in keywords:
                if kw not in keyword_docs:
                    keyword_docs[kw] = set()
                keyword_docs[kw].add(i)

        # 分组
        assigned = set()
        clusters = []

        if n_clusters <= 0:
            n_clusters = max(2, min(len(drawers) // 3, 10))

        for _kw, doc_ids in sorted(keyword_docs.items(),
                                  key=lambda x: len(x[1]), reverse=True):
            unassigned = doc_ids - assigned
            if len(unassigned) < 2:
                continue
            if len(clusters) >= n_clusters:
                break

            group_drawers = [drawers[i] for i in unassigned]
            group_indices = list(unassigned)
            cluster = self._build_cluster(group_drawers, group_indices)
            clusters.append(cluster)
            assigned.update(unassigned)

        # 剩余未分配的
        unassigned = [i for i in range(len(drawers)) if i not in assigned]
        if unassigned:
            clusters.append(self._build_cluster(
                [drawers[i] for i in unassigned], unassigned))

        clusters.sort(key=lambda c: c.size, reverse=True)
        return clusters

    def _build_cluster(self, drawers: list[Drawer], indices: list[int],
                       embeddings: np.ndarray = None) -> MemoryCluster:
        """构建聚类对象"""
        if not drawers:
            return MemoryCluster(id="empty", label="空", keywords=[],
                                 memory_ids=[], size=0)

        # 提取关键词
        keyword_counter = Counter()
        for d in drawers:
            for kw in self._extract_keywords(d.content):
                keyword_counter[kw] += 1
        top_keywords = [kw for kw, _ in keyword_counter.most_common(5)]

        # 生成标签
        label = top_keywords[0] if top_keywords else "未分类"

        # 计算内聚度
        if embeddings is not None and len(indices) > 1:
            group_embs = embeddings[indices]
            centroid = np.mean(group_embs, axis=0)
            cohesion = float(np.mean([
                float(np.dot(emb, centroid) / (
                    np.linalg.norm(emb) * np.linalg.norm(centroid) + 1e-8))
                for emb in group_embs
            ]))
            centroid_list = centroid.tolist()
        else:
            cohesion = 1.0
            centroid_list = None

        cluster_id = hex_digest(
            "".join(sorted(d.id for d in drawers))
        )[:12]

        return MemoryCluster(
            id=cluster_id,
            label=label,
            keywords=top_keywords,
            memory_ids=[d.id for d in drawers],
            centroid=centroid_list,
            cohesion=round(cohesion, 4),
            size=len(drawers),
        )

    def _single_cluster(self, drawers: list[Drawer]) -> MemoryCluster:
        """单记忆聚类"""
        keyword_counter = Counter()
        for d in drawers:
            for kw in self._extract_keywords(d.content):
                keyword_counter[kw] += 1
        top_keywords = [kw for kw, _ in keyword_counter.most_common(3)]

        return MemoryCluster(
            id=hex_digest(drawers[0].id)[:12],
            label=top_keywords[0] if top_keywords else "单条记忆",
            keywords=top_keywords,
            memory_ids=[d.id for d in drawers],
            size=len(drawers),
        )

    def _extract_keywords(self, text: str, max_len: int = 8) -> list[str]:
        """从文本中提取关键词"""
        # 中文分词简单实现
        import re
        # 匹配中文词（2-4字）和英文词
        words = []
        # 英文词
        eng_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_]{2,}', text)
        words.extend(w.lower() for w in eng_words)

        # 中文词（2-4字组合）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        for window in [4, 3, 2]:
            for i in range(len(chinese_chars) - window + 1):
                words.append("".join(chinese_chars[i:i + window]))

        # 去重并过滤停用词
        stopwords = {"这个", "一个", "可以", "没有", "什么", "怎么", "如何",
                     "我们", "他们", "因为", "所以", "但是", "而且", "或者",
                     "the", "and", "for", "that", "this", "with", "from"}
        filtered = [w for w in words if w.lower() not in stopwords]

        # 按频率排序
        counter = Counter(filtered)
        return [kw for kw, _ in counter.most_common(max_len)]

    def find_related(self, drawer: Drawer, all_drawers: list[Drawer],
                     top_k: int = 5, min_similarity: float = 0.3) -> list[dict]:
        """找到与指定记忆最相关的其他记忆"""
        if not self.embedder:
            return []

        query_emb = self.embedder.embed(drawer.content)
        texts = [d.content for d in all_drawers if d.id != drawer.id]
        if not texts:
            return []

        item_embs = self.embedder.embed_batch(texts)
        scored = []
        for i, d in enumerate([d for d in all_drawers if d.id != drawer.id]):
            sim = self.embedder.similarity(query_emb, item_embs[i])
            if sim >= min_similarity:
                scored.append((sim, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": d.id, "content": d.content[:200],
                 "similarity": round(sim, 4)} for sim, d in scored[:top_k]]

    def cluster_stats(self, clusters: list[MemoryCluster]) -> dict:
        """聚类统计"""
        if not clusters:
            return {"total_clusters": 0, "total_memories": 0,
                    "avg_cohesion": 0.0, "avg_size": 0.0}

        total_mems = sum(c.size for c in clusters)
        return {
            "total_clusters": len(clusters),
            "total_memories": total_mems,
            "avg_cohesion": round(
                sum(c.cohesion for c in clusters) / len(clusters), 4),
            "avg_size": round(total_mems / len(clusters), 1),
            "largest_cluster": max(c.size for c in clusters),
            "smallest_cluster": min(c.size for c in clusters),
        }
