"""盘古智能自动索引 — 根据使用模式自动创建和优化索引

核心能力：
1. 热词索引：自动为高频查询词建立索引
2. 标签索引：自动优化标签索引结构
3. 索引推荐：根据查询模式推荐新索引
4. 索引健康：监控索引健康状态
5. 索引优化：自动清理无效索引
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.smart_indexing")


@dataclass
class IndexEntry:
    """索引条目"""
    key: str
    index_type: str  # hot_word / tag / wing / temporal
    memory_ids: list[str]
    hit_count: int = 0
    created_at: str = ""
    last_hit: str = ""


@dataclass
class IndexRecommendation:
    """索引推荐"""
    index_type: str
    key: str
    reason: str
    expected_benefit: str
    priority: int


class SmartIndexingEngine:
    """智能自动索引引擎"""

    def __init__(self, config=None):
        self.config = config
        self._indexes: dict[str, IndexEntry] = {}
        self._query_log: list[dict] = []
        self._max_query_log = 5000

    def log_query(self, query: str, result_ids: list[str] = None) -> None:
        """记录查询"""
        self._query_log.append({
            "query": query,
            "result_ids": result_ids or [],
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._query_log) > self._max_query_log:
            self._query_log = self._query_log[-self._max_query_log:]

    def build_hot_word_index(self, drawers: list) -> dict:
        """构建热词索引"""
        word_freq: dict[str, int] = defaultdict(int)
        word_memories: dict[str, list[str]] = defaultdict(list)

        for d in drawers:
            words = set()
            for word in d.content.split():
                if len(word) >= 2:
                    words.add(word.lower())
            for tag in d.tags:
                words.add(tag.lower())

            for w in words:
                word_freq[w] += 1
                if d.id not in word_memories[w]:
                    word_memories[w].append(d.id)

        indexed = 0
        for word, freq in sorted(word_freq.items(), key=lambda x: -x[1])[:200]:
            key = f"hot:{word}"
            if key not in self._indexes or freq > self._indexes[key].hit_count:
                self._indexes[key] = IndexEntry(
                    key=key, index_type="hot_word",
                    memory_ids=word_memories[word][:50],
                    hit_count=freq,
                    created_at=datetime.now().isoformat(),
                )
                indexed += 1

        return {"hot_words_indexed": indexed, "total_words": len(word_freq)}

    def build_tag_index(self, drawers: list) -> dict:
        """构建标签索引"""
        tag_memories: dict[str, list[str]] = defaultdict(list)
        for d in drawers:
            for tag in d.tags:
                tag_memories[tag.lower()].append(d.id)

        indexed = 0
        for tag, mem_ids in tag_memories.items():
            key = f"tag:{tag}"
            self._indexes[key] = IndexEntry(
                key=key, index_type="tag",
                memory_ids=mem_ids,
                hit_count=len(mem_ids),
                created_at=datetime.now().isoformat(),
            )
            indexed += 1

        return {"tag_indexes": indexed, "unique_tags": len(tag_memories)}

    def build_wing_index(self, drawers: list) -> dict:
        """构建 Wing 索引"""
        wing_memories: dict[str, list[str]] = defaultdict(list)
        for d in drawers:
            wing_memories[d.wing].append(d.id)

        for wing, mem_ids in wing_memories.items():
            key = f"wing:{wing}"
            self._indexes[key] = IndexEntry(
                key=key, index_type="wing",
                memory_ids=mem_ids,
                hit_count=len(mem_ids),
                created_at=datetime.now().isoformat(),
            )

        return {"wing_indexes": len(wing_memories)}

    def build_all_indexes(self, drawers: list) -> dict:
        """构建所有索引"""
        hot = self.build_hot_word_index(drawers)
        tags = self.build_tag_index(drawers)
        wings = self.build_wing_index(drawers)

        return {
            "hot_words": hot,
            "tags": tags,
            "wings": wings,
            "total_indexes": len(self._indexes),
        }

    def search_index(self, query: str) -> list[str]:
        """通过索引搜索"""
        q_lower = query.lower()
        result_ids: dict[str, int] = defaultdict(int)

        for key, entry in self._indexes.items():
            if q_lower in key:
                for mid in entry.memory_ids:
                    result_ids[mid] += 1
                entry.hit_count += 1
                entry.last_hit = datetime.now().isoformat()

        sorted_ids = sorted(result_ids.items(), key=lambda x: -x[1])
        return [mid for mid, _ in sorted_ids[:20]]

    def recommend_indexes(self, drawers: list) -> list[IndexRecommendation]:
        """推荐新索引"""
        recommendations = []

        query_words: dict[str, int] = defaultdict(int)
        for log_entry in self._query_log:
            for word in log_entry["query"].split():
                if len(word) >= 2:
                    query_words[word.lower()] += 1

        for word, freq in sorted(query_words.items(), key=lambda x: -x[1])[:10]:
            key = f"hot:{word}"
            if key not in self._indexes:
                recommendations.append(IndexRecommendation(
                    index_type="hot_word",
                    key=word,
                    reason=f"高频查询词（{freq}次）但无索引",
                    expected_benefit=f"预计提升 {freq} 次查询的检索速度",
                    priority=1 if freq > 5 else 2,
                ))

        tag_counts: dict[str, int] = defaultdict(int)
        for d in drawers:
            for tag in d.tags:
                tag_counts[tag] += 1

        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:5]:
            key = f"tag:{tag}"
            if key not in self._indexes:
                recommendations.append(IndexRecommendation(
                    index_type="tag",
                    key=tag,
                    reason=f"标签 {tag} 关联 {count} 条记忆但无索引",
                    expected_benefit="加速按标签检索",
                    priority=2,
                ))

        return recommendations

    def get_index_health(self) -> dict:
        """索引健康检查"""
        total = len(self._indexes)
        by_type: dict[str, int] = defaultdict(int)
        zero_hit = 0

        for entry in self._indexes.values():
            by_type[entry.index_type] += 1
            if entry.hit_count == 0:
                zero_hit += 1

        return {
            "total_indexes": total,
            "by_type": dict(by_type),
            "zero_hit_indexes": zero_hit,
            "health": "good" if zero_hit < total * 0.3 else "needs_cleanup",
        }

    def cleanup_indexes(self) -> int:
        """清理无效索引"""
        to_remove = []
        for key, entry in self._indexes.items():
            if entry.hit_count == 0 and entry.index_type == "hot_word":
                to_remove.append(key)

        for key in to_remove:
            del self._indexes[key]

        return len(to_remove)

    def get_smart_index_stats(self) -> dict:
        """获取智能索引统计"""
        return {
            "total_indexes": len(self._indexes),
            "query_log_size": len(self._query_log),
            "types": dict(defaultdict(int, {
                it: sum(1 for e in self._indexes.values() if e.index_type == it)
                for e in self._indexes.values()
            })),
        }


_smart_indexing: SmartIndexingEngine | None = None


def get_smart_indexing(config=None) -> SmartIndexingEngine:
    """获取全局智能索引引擎实例"""
    global _smart_indexing
    if _smart_indexing is None:
        _smart_indexing = SmartIndexingEngine(config)
    return _smart_indexing
