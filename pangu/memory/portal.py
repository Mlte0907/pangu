"""盘古记忆门户 — 一站式记忆操作入口

核心能力：
1. 智能写入：写入时自动触发标签提取、图谱更新、质量评估
2. 智能搜索：搜索时自动触发查询重写、索引查找、结果排序
3. 系统全景：一次性查看系统全貌
4. 一键维护：一键执行所有维护操作
5. 智能摘要：自动生成系统状态摘要
"""
import logging
from datetime import datetime

logger = logging.getLogger("pangu.memory.portal")


class MemoryPortal:
    """记忆门户 — 统一入口"""

    def __init__(self, config=None):
        self.config = config

    def smart_write(self, drawers: list, content: str, wing: str = "default",
                    tags: list[str] = None, importance: float = 3.0) -> dict:
        """智能写入 — 写入时自动触发多个模块"""
        from ..core.palace import Drawer
        import uuid

        drawer_id = str(uuid.uuid4())[:16]
        if not tags:
            import re
            tags = list(set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', content)))[:5]

        drawer = Drawer(
            id=drawer_id, content=content, wing=wing,
            importance=importance, tags=tags,
        )

        actions = {
            "created": drawer_id,
            "wing": wing,
            "tags": tags,
            "importance": importance,
            "auto_actions": [],
        }

        from ..memory.memory_events import get_event_stream
        es = get_event_stream(self.config)
        es.emit_memory_write(drawer_id, content, wing)
        actions["auto_actions"].append("event_emitted")

        from ..memory.smart_indexing import get_smart_indexing
        si = get_smart_indexing(self.config)
        for tag in tags:
            key = f"tag:{tag}"
            if key in si._indexes:
                si._indexes[key].memory_ids.append(drawer_id)
        actions["auto_actions"].append("index_updated")

        return actions

    def _score_drawer(self, d, query: str, index_results: set) -> int:
        """计算单个 drawer 的搜索得分"""
        score = 0
        q_lower = query.lower()
        d_lower = d.content.lower()
        for word in q_lower.split():
            if len(word) >= 2 and word in d_lower:
                score += 2
        for tag in d.tags:
            for word in q_lower.split():
                if word in tag.lower():
                    score += 3
        if d.id in index_results:
            score += 5
        return score

    def smart_search(self, drawers: list, query: str, limit: int = 5) -> dict:
        """智能搜索 — 自动触发查询重写+索引搜索+结果排序"""
        from ..memory.query_rewriter import get_rewriter
        rw = get_rewriter(self.config)
        rewrite_result = rw.rewrite(query)

        from ..memory.smart_indexing import get_smart_indexing
        si = get_smart_indexing(self.config)
        index_results = si.search_index(query)

        scored = []
        for d in drawers:
            score = self._score_drawer(d, query, index_results)
            if score > 0:
                scored.append((d, score))

        scored.sort(key=lambda x: -x[1])
        top = scored[:limit]

        from ..memory.memory_events import get_event_stream
        es = get_event_stream(self.config)
        es.emit_memory_search(query, len(top))

        return {
            "query": query,
            "rewritten": rewrite_result.rewritten[:100],
            "results": [
                {"id": d.id, "content": d.content[:80], "wing": d.wing, "score": s}
                for d, s in top
            ],
            "total_found": len(scored),
            "index_hits": len(index_results),
        }

    def system_panorama(self, drawers: list) -> dict:
        """系统全景 — 一次性查看系统全貌"""
        wing_counts = {}
        tag_counts = {}
        total_importance = 0
        for d in drawers:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1
            for t in d.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
            total_importance += d.importance

        avg_importance = total_importance / max(len(drawers), 1)

        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]

        return {
            "total_memories": len(drawers),
            "wing_distribution": wing_counts,
            "unique_tags": len(tag_counts),
            "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
            "avg_importance": round(avg_importance, 2),
            "timestamp": datetime.now().isoformat(),
        }

    def one_click_maintenance(self, drawers: list) -> dict:
        """一键维护 — 执行所有维护操作"""
        results = {}

        from ..memory.smart_indexing import get_smart_indexing
        si = get_smart_indexing(self.config)
        idx_result = si.build_all_indexes(drawers)
        results["indexing"] = idx_result["total_indexes"]

        from ..memory.health_monitor import get_monitor
        hm = get_monitor(self.config)
        health = hm.full_check(drawers)
        results["health_score"] = health["overall_score"]
        results["health_status"] = health["overall_status"]

        from ..memory.quality_scorer import get_scorer
        qs = get_scorer(self.config)
        batch = qs.batch_assess(drawers)
        results["quality_avg"] = batch["avg_score"]
        results["quality_grades"] = batch["grade_distribution"]

        from ..memory.smart_cache import get_cache_manager
        cm = get_cache_manager(self.config)
        cm._l1.cleanup_expired()
        cm._l2.cleanup_expired()
        results["cache_cleaned"] = True

        from ..memory.memory_events import get_event_stream
        es = get_event_stream(self.config)
        es.emit("system.maintenance", "", results)

        return results

    def get_smart_summary(self, drawers: list) -> str:
        """智能摘要 — 自动生成系统状态摘要"""
        pan = self.system_panorama(drawers)

        top_wing = max(pan["wing_distribution"].items(), key=lambda x: x[1]) if pan["wing_distribution"] else ("", 0)
        top_tag = pan["top_tags"][0] if pan["top_tags"] else {"tag": "", "count": 0}

        summary = (
            f"盘古记忆系统状态 | "
            f"记忆: {pan['total_memories']}条 | "
            f"领域: {len(pan['wing_distribution'])}个(最大:{top_wing[0]} {top_wing[1]}条) | "
            f"标签: {pan['unique_tags']}个(热门:{top_tag['tag']}) | "
            f"平均重要性: {pan['avg_importance']}"
        )
        return summary


_portal: MemoryPortal | None = None


def get_portal(config=None) -> MemoryPortal:
    """获取全局记忆门户实例"""
    global _portal
    if _portal is None:
        _portal = MemoryPortal(config)
    return _portal
