"""盘古记忆可视化 — 文本化展示记忆连接关系

核心功能：
1. 图谱可视化：文本化展示知识图谱
2. 记忆网络：展示记忆间的连接关系
3. 时间线可视化：展示记忆的时间演变
4. 统计可视化：展示记忆分布统计
"""
import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.visualization")


class MemoryVisualizer:
    """记忆可视化 — 文本化展示"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def visualize_graph(self, entities: list[dict], relations: list[dict]) -> str:
        """可视化知识图谱"""
        lines = ["=== 知识图谱 ==="]

        # 实体统计
        entity_types = Counter(e.get("type", "unknown") for e in entities)
        lines.append(f"\n实体: {len(entities)} 个")
        for etype, count in entity_types.most_common(5):
            lines.append(f"  {etype}: {count}")

        # 关系统计
        relation_types = Counter(r.get("predicate", "unknown") for r in relations)
        lines.append(f"\n关系: {len(relations)} 条")
        for rtype, count in relation_types.most_common(5):
            lines.append(f"  {rtype}: {count}")

        # 图谱结构
        lines.append(f"\n图谱结构:")
        entity_map = {e["id"]: e for e in entities}
        for rel in relations[:10]:  # 只显示前10条
            subject = entity_map.get(rel.get("subject_id", ""), {}).get("name", "?")
            obj = entity_map.get(rel.get("object_id", ""), {}).get("name", "?")
            pred = rel.get("predicate", "?")
            lines.append(f"  {subject} --[{pred}]--> {obj}")

        if len(relations) > 10:
            lines.append(f"  ... 还有 {len(relations) - 10} 条关系")

        return "\n".join(lines)

    def visualize_memory_network(self, drawers: list[Drawer]) -> str:
        """可视化记忆网络"""
        lines = ["=== 记忆网络 ==="]

        # 按 Wing 分组
        by_wing = defaultdict(list)
        for d in drawers:
            by_wing[d.wing].append(d)

        lines.append(f"\n记忆分布: {len(drawers)} 条")
        for wing, items in sorted(by_wing.items(), key=lambda x: -len(x[1])):
            lines.append(f"  {wing}: {len(items)} 条")

        # 标签统计
        all_tags = []
        for d in drawers:
            all_tags.extend(d.tags)
        tag_counts = Counter(all_tags).most_common(10)
        if tag_counts:
            lines.append(f"\n热门标签:")
            for tag, count in tag_counts:
                lines.append(f"  {tag}: {count}")

        # 重要性分布
        importance_dist = {"高(≥4)": 0, "中(2-4)": 0, "低(<2)": 0}
        for d in drawers:
            if d.importance >= 4.0:
                importance_dist["高(≥4)"] += 1
            elif d.importance >= 2.0:
                importance_dist["中(2-4)"] += 1
            else:
                importance_dist["低(<2)"] += 1

        lines.append(f"\n重要性分布:")
        for level, count in importance_dist.items():
            lines.append(f"  {level}: {count}")

        return "\n".join(lines)

    def visualize_timeline(self, drawers: list[Drawer]) -> str:
        """可视化时间线"""
        lines = ["=== 记忆时间线 ==="]

        # 按时间分组
        by_date = defaultdict(list)
        for d in drawers:
            try:
                date = datetime.fromisoformat(d.created_at).strftime("%Y-%m-%d")
                by_date[date].append(d)
            except (ValueError, TypeError):
                by_date["未知日期"].append(d)

        # 显示最近7天
        sorted_dates = sorted(by_date.keys(), reverse=True)[:7]
        for date in sorted_dates:
            items = by_date[date]
            lines.append(f"\n{date} ({len(items)} 条):")
            for d in items[:3]:
                lines.append(f"  - {d.content[:40]}")
            if len(items) > 3:
                lines.append(f"  ... 还有 {len(items) - 3} 条")

        return "\n".join(lines)

    def visualize_stats(self, drawers: list[Drawer]) -> str:
        """可视化统计信息"""
        lines = ["=== 记忆统计 ==="]

        total = len(drawers)
        lines.append(f"总记忆数: {total}")

        # 按 Wing 统计
        by_wing = Counter(d.wing for d in drawers)
        lines.append(f"\n按 Wing 分布:")
        for wing, count in by_wing.most_common(5):
            lines.append(f"  {wing}: {count} ({count/total*100:.1f}%)")

        # 重要性统计
        avg_importance = sum(d.importance for d in drawers) / max(total, 1)
        lines.append(f"\n平均重要性: {avg_importance:.2f}")

        # 时间范围
        dates = []
        for d in drawers:
            try:
                dates.append(datetime.fromisoformat(d.created_at))
            except (ValueError, TypeError):
                pass
        if dates:
            oldest = min(dates)
            newest = max(dates)
            days_span = (newest - oldest).days
            lines.append(f"时间跨度: {days_span} 天")

        return "\n".join(lines)


# 全局单例
_visualizer: MemoryVisualizer | None = None


def get_visualizer(config: PanguConfig = None) -> MemoryVisualizer:
    """获取全局可视化实例"""
    global _visualizer
    if _visualizer is None:
        _visualizer = MemoryVisualizer(config)
    return _visualizer
