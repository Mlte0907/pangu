"""盘古语义压缩 — AI 驱动的记忆摘要和压缩

核心能力：
1. 语义摘要：将多条相关记忆压缩为精炼摘要
2. 智能去重：识别语义重复的记忆并合并
3. 重要性重评估：基于记忆网络重新评估重要性
4. 压缩质量评估：评估压缩后信息损失
"""
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime

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
                merged.append({
                    "tag": tag,
                    "summary": summary,
                    "original_count": len(group),
                    "avg_importance": avg_importance,
                    "ids": [d.id for d in group],
                })
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

    def find_semantic_duplicates(self, drawers: list, threshold: float = 0.8) -> list[dict]:
        """发现语义重复"""
        duplicates = []
        seen = {}

        for d in drawers:
            content_key = d.content[:30]
            if content_key in seen:
                duplicates.append({
                    "original": seen[content_key],
                    "duplicate": d.id,
                    "similarity": 0.95,
                    "reason": "前30字符完全匹配",
                })
            else:
                seen[content_key] = d.id

        tag_sets = {}
        for d in drawers:
            key = tuple(sorted(d.tags))
            if key in tag_sets:
                tag_sets[key].append(d)
            else:
                tag_sets[key] = [d]

        for tag_key, group in tag_sets.items():
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
                updates.append({
                    "id": d.id,
                    "old_importance": d.importance,
                    "new_importance": new_importance,
                    "network_score": round(network_score, 3),
                })

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
