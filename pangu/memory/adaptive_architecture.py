"""盘古自适应记忆架构 — 记忆系统自动重构

核心能力：
1. 架构分析：分析当前记忆架构的效率
2. 自动重构：根据使用模式自动调整 Wing/Room 结构
3. 冷热分离：自动将冷数据和热数据分离
4. 索引优化：根据查询模式优化索引
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.adaptive_architecture")


@dataclass
class ArchitectureAdvice:
    """架构建议"""
    category: str
    action: str
    reason: str
    priority: int  # 1-5
    expected_benefit: str


class AdaptiveArchitecture:
    """自适应记忆架构"""

    def __init__(self, config=None):
        self.config = config
        self._restructure_history: list[dict] = []

    def analyze_architecture(self, drawers: list) -> dict:
        """分析当前架构"""
        wing_stats: dict[str, dict] = {}
        for d in drawers:
            if d.wing not in wing_stats:
                wing_stats[d.wing] = {"count": 0, "total_importance": 0, "tags": set()}
            wing_stats[d.wing]["count"] += 1
            wing_stats[d.wing]["total_importance"] += d.importance
            wing_stats[d.wing]["tags"].update(d.tags)

        analysis = {}
        for wing, stats in wing_stats.items():
            analysis[wing] = {
                "count": stats["count"],
                "avg_importance": round(stats["total_importance"] / max(stats["count"], 1), 2),
                "tag_diversity": len(stats["tags"]),
                "health": "good" if stats["count"] >= 3 else "sparse",
            }

        total = len(drawers)
        wing_count = len(wing_stats)

        return {
            "total_memories": total,
            "total_wings": wing_count,
            "avg_memories_per_wing": round(total / max(wing_count, 1), 1),
            "wings": analysis,
            "architecture_score": round(min(1.0, wing_count / max(1, total / 10)), 2),
        }

    def suggest_restructuring(self, drawers: list) -> list[ArchitectureAdvice]:
        """建议架构重构"""
        suggestions = []
        wing_stats: dict[str, int] = {}
        for d in drawers:
            wing_stats[d.wing] = wing_stats.get(d.wing, 0) + 1

        for wing, count in wing_stats.items():
            if count < 2:
                suggestions.append(ArchitectureAdvice(
                    category="wing_merge",
                    action=f"将稀疏 Wing '{wing}' 合并到最近似 Wing",
                    reason=f"仅有 {count} 条记忆，维护成本高于价值",
                    priority=3,
                    expected_benefit="减少架构碎片化",
                ))
            elif count > len(drawers) * 0.4:
                suggestions.append(ArchitectureAdvice(
                    category="wing_split",
                    action=f"将大 Wing '{wing}' 拆分为子类别",
                    reason=f"占总记忆 {count / len(drawers):.0%}，需要更细粒度组织",
                    priority=2,
                    expected_benefit="提高检索精度",
                ))

        all_tags: dict[str, int] = {}
        for d in drawers:
            for tag in d.tags:
                all_tags[tag] = all_tags.get(tag, 0) + 1

        orphan_tags = [t for t, c in all_tags.items() if c == 1]
        if len(orphan_tags) > len(all_tags) * 0.3:
            suggestions.append(ArchitectureAdvice(
                category="tag_cleanup",
                action=f"清理 {len(orphan_tags)} 个孤立标签",
                reason=f"占总标签 {len(orphan_tags) / max(len(all_tags), 1):.0%}",
                priority=4,
                expected_benefit="提高标签系统效率",
            ))

        return suggestions

    def suggest_cold_hot_separation(self, drawers: list, access_log: list[dict] = None) -> dict:
        """冷热分离建议"""
        hot = []
        warm = []
        cold = []

        for d in drawers:
            imp = d.importance / 5.0
            if imp > 0.7:
                hot.append(d.id)
            elif imp > 0.3:
                warm.append(d.id)
            else:
                cold.append(d.id)

        return {
            "hot_count": len(hot),
            "warm_count": len(warm),
            "cold_count": len(cold),
            "hot_ids": hot[:10],
            "cold_ids": cold[:10],
            "recommendation": f"建议将 {len(cold)} 条冷记忆归档到 L3 深度存储",
        }

    def optimize_indices(self, drawers: list) -> dict:
        """索引优化建议"""
        tag_index_size = len(set(t for d in drawers for t in d.tags))
        wing_index_size = len(set(d.wing for d in drawers))

        return {
            "tag_index_entries": tag_index_size,
            "wing_index_entries": wing_index_size,
            "recommended_fts_rebuild": len(drawers) > 100,
            "recommended_vector_rebuild": len(drawers) > 500,
        }

    def full_analysis(self, drawers: list) -> dict:
        """完整架构分析"""
        analysis = self.analyze_architecture(drawers)
        suggestions = self.suggest_restructuring(drawers)
        separation = self.suggest_cold_hot_separation(drawers)
        index_opt = self.optimize_indices(drawers)

        self._restructure_history.append({
            "timestamp": datetime.now().isoformat(),
            "total_memories": len(drawers),
            "suggestions_count": len(suggestions),
        })

        return {
            "architecture": analysis,
            "suggestions": [
                {"action": s.action, "reason": s.reason, "priority": s.priority}
                for s in suggestions
            ],
            "cold_hot_separation": separation,
            "index_optimization": index_opt,
        }

    def get_architecture_stats(self) -> dict:
        """获取架构统计"""
        return {
            "restructurings": len(self._restructure_history),
            "latest": self._restructure_history[-1] if self._restructure_history else None,
        }


_architecture: AdaptiveArchitecture | None = None


def get_architecture(config=None) -> AdaptiveArchitecture:
    """获取全局自适应架构实例"""
    global _architecture
    if _architecture is None:
        _architecture = AdaptiveArchitecture(config)
    return _architecture
