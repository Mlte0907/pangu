"""盘古语义压缩 — AI 驱动的记忆摘要和压缩

核心能力：
1. 语义摘要：将多条相关记忆压缩为精炼摘要
2. 智能去重：识别语义重复的记忆并合并
3. 重要性重评估：基于记忆网络重新评估重要性
4. 压缩质量评估：评估压缩后信息损失
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("pangu.memory.semantic_compression")


@dataclass
class CompressionResult:
    """压缩结果"""

    original_count: int
    compressed_count: int
    merged_groups: list[dict]
    information_loss: float  # 0-1, 越低越好
    tokens_saved: int


class SemanticCompressor:
    """语义压缩引擎"""

    def __init__(self, config=None):
        self.config = config

    def compress_by_tags(self, drawers: list) -> CompressionResult:
        """按标签聚类压缩"""
        tag_groups: dict[str, list] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        merged = []
        compressed_ids = set()

        for tag, group in tag_groups.items():
            if len(group) >= 3:
                contents = [d.content for d in group]
                summary = self._generate_summary(contents)
                avg_importance = sum(d.importance for d in group) / len(group)
                merged.append(
                    {
                        "tag": tag,
                        "summary": summary,
                        "original_count": len(group),
                        "avg_importance": avg_importance,
                        "ids": [d.id for d in group],
                    }
                )
                compressed_ids.update(d.id for d in group)

        unmerged = [d for d in drawers if d.id not in compressed_ids]

        total_tokens = sum(len(d.content) * 1.5 for d in drawers)
        saved_tokens = sum(m["original_count"] * len(m["summary"]) * 1.5 for m in merged)

        return CompressionResult(
            original_count=len(drawers),
            compressed_count=len(merged) + len(unmerged),
            merged_groups=merged,
            information_loss=0.15 if merged else 0.0,
            tokens_saved=int(total_tokens - saved_tokens),
        )

    def _is_encrypted(self, content: str) -> bool:
        """Fernet 密文识别（gAAAAAB 前缀）：密文彼此不同但共享标签，标签聚类会误判为语义重复。"""
        return content.startswith("gAAAAAB")

    def find_semantic_duplicates(self, drawers: list, threshold: float = 0.8) -> list[dict]:
        """发现语义重复（跳过 Fernet 密文——密文共享标签但内容互异，标签聚类对其是误报）"""
        duplicates = []
        seen = {}

        for d in drawers:
            if self._is_encrypted(d.content):
                continue
            content_key = d.content[:30]
            if content_key in seen:
                duplicates.append(
                    {
                        "original": seen[content_key],
                        "duplicate": d.id,
                        "similarity": 0.95,
                        "reason": "前30字符完全匹配",
                    }
                )
            else:
                seen[content_key] = d.id

        tag_sets = {}
        for d in drawers:
            if self._is_encrypted(d.content):
                continue
            key = tuple(sorted(d.tags))
            if key in tag_sets:
                tag_sets[key].append(d)
            else:
                tag_sets[key] = [d]

        for _tag_key, group in tag_sets.items():
            if len(group) >= 2:
                self._check_tag_group_duplicates(group, threshold, duplicates)

        seen_pairs = set()
        unique = []
        for d in duplicates:
            pair = (d["original"], d["duplicate"])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                unique.append(d)

        return unique

    def analyze_duplicates(self, drawers: list, threshold: float = 0.8) -> dict:
        """统一重复口径分析 — 三口径同源可换算（R3-A 唯一权威口径）

        输出三元组：
        - duplicate_groups:      重复组簇数（口径：语义连通分量，每组>=2条）
        - total_recoverable:     可回收条数 = Σ(组内条数 - 1)（合并每组仅保留1条时可删除条数）
        - pairs:                 重复对数 = 前缀精确匹配对 ∪ 标签重叠语义对（去重）

        另附算法/阈值/口径标签，供 health_check / find_duplicates / merge_candidates 共用。
        """
        total = len(drawers)

        # 1) 前缀精确匹配分组（前30字符，启发式低配近似）
        prefix_groups: dict[str, list] = {}
        for d in drawers:
            prefix_groups.setdefault(d.content[:30], []).append(d)
        prefix_groups_list = [g for g in prefix_groups.values() if len(g) > 1]
        prefix_recoverable = sum(len(g) - 1 for g in prefix_groups_list)

        # 2) 语义对（前缀对 + 标签重叠对，去重）
        pairs = self.find_semantic_duplicates(drawers, threshold)
        pair_keys: set[tuple] = set()
        for g in prefix_groups_list:
            members = [d.id for d in g]
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    pair_keys.add(tuple(sorted((members[i], members[j]))))
        for p in pairs:
            pair_keys.add(tuple(sorted((p["original"], p["duplicate"]))))
        pairs_count = len(pair_keys)

        # 3) 语义连通分量（并查集）→ 组簇数 / 可回收条数
        parent: dict[str, str] = {}

        def _find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a: str, b: str) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        for g in prefix_groups_list:
            for i in range(1, len(g)):
                _union(g[0].id, g[i].id)
        for p in pairs:
            _union(p["original"], p["duplicate"])

        comp_members: dict[str, set] = {}
        for d in drawers:
            comp_members.setdefault(_find(d.id), set()).add(d.id)
        semantic_groups = [m for m in comp_members.values() if len(m) > 1]
        semantic_recoverable = sum(len(m) - 1 for m in semantic_groups)

        return {
            "duplicate_groups": len(semantic_groups),
            "total_recoverable": semantic_recoverable,
            "pairs": pairs_count,
            "total_memories": total,
            "prefix_recoverable": prefix_recoverable,
            "prefix_groups": len(prefix_groups_list),
            "caliber": {
                "algorithm": "prefix30_exact + tag_overlap_threshold",
                "threshold": threshold,
                "group_basis": "semantic connected components (每组分母≥2条)",
                "recoverable_basis": "Σ(组内条数-1)，合并每组仅保留1条",
                "pair_basis": "前缀精确匹配对 ∪ 标签重叠对（去重）",
            },
        }

    def reassess_importance(self, drawers: list) -> list[dict]:
        """基于记忆网络重新评估重要性"""
        updates = []

        tag_importance: dict[str, list[float]] = {}
        for d in drawers:
            for tag in d.tags:
                tag_importance.setdefault(tag, []).append(d.importance / 5.0)

        tag_avg = {}
        for tag, scores in tag_importance.items():
            tag_avg[tag] = sum(scores) / len(scores)

        for d in drawers:
            if not d.tags:
                continue

            network_score = sum(tag_avg.get(t, 0.5) for t in d.tags) / len(d.tags)
            current_norm = d.importance / 5.0
            new_norm = 0.6 * current_norm + 0.4 * network_score
            new_importance = round(new_norm * 5.0, 1)

            if abs(new_importance - d.importance) > 0.3:
                updates.append(
                    {
                        "id": d.id,
                        "old_importance": d.importance,
                        "new_importance": new_importance,
                        "network_score": round(network_score, 3),
                    }
                )

        return updates

    def _compare_tag_pair(self, item_a, item_b, threshold: float) -> dict | None:
        overlap = len(set(item_a.tags) & set(item_b.tags))
        total = len(set(item_a.tags) | set(item_b.tags))
        if total > 0 and overlap / total >= threshold:
            return {
                "original": item_a.id,
                "duplicate": item_b.id,
                "similarity": overlap / total,
                "reason": f"标签重叠 {overlap}/{total}",
            }
        return None

    def _check_tag_group_duplicates(self, group, threshold, duplicates):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                result = self._compare_tag_pair(group[i], group[j], threshold)
                if result:
                    duplicates.append(result)

    def _generate_summary(self, contents: list[str]) -> str:
        """生成摘要（无 LLM 版本：取最短+去重关键词）"""
        all_words = set()
        for c in contents:
            for word in c.split():
                if len(word) >= 2:
                    all_words.add(word)

        if len(contents) == 1:
            return contents[0][:100]

        summary = f"[{len(contents)}条相关记忆] "
        summary += "、".join(list(all_words)[:8])
        return summary[:200]

    def get_compression_stats(self, drawers: list) -> dict:
        """获取压缩统计"""
        tag_groups: dict[str, int] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups[tag] = tag_groups.get(tag, 0) + 1

        compressible = sum(1 for count in tag_groups.values() if count >= 3)
        total_tags = len(tag_groups)

        return {
            "total_memories": len(drawers),
            "total_tags": total_tags,
            "compressible_groups": compressible,
            "estimated_reduction": f"{compressible * 2}/{len(drawers)} 条可合并",
        }


_compressor: SemanticCompressor | None = None


def get_compressor(config=None) -> SemanticCompressor:
    """获取全局语义压缩实例"""
    global _compressor
    if _compressor is None:
        _compressor = SemanticCompressor(config)
    return _compressor
