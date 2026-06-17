"""盘古记忆分析看板 — 全面统计与健康监控
==============================================
提供记忆系统的全面分析、趋势洞察和健康监控。

支持：
- 记忆增长趋势分析
- 活跃度分析（读写频率）
- 存储分布分析（按 Wing/Room/Hall/Tag）
- 重要性分布分析
- 健康评分
- 异常检测
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class MemoryAnalytics:
    """记忆分析报告"""
    # 基本统计
    total_memories: int
    total_wings: int
    total_rooms: int
    total_tags: int
    total_wiki_pages: int

    # 存储分布
    distribution_by_wing: dict[str, int]
    distribution_by_room: dict[str, int]
    distribution_by_hall: dict[str, int]
    distribution_by_tag: dict[str, int]

    # 重要性分布
    importance_distribution: dict[str, int]  # {high/medium/low: count}
    avg_importance: float

    # 时间分析
    memories_last_24h: int
    memories_last_7d: int
    memories_last_30d: int
    oldest_memory_age_days: int
    newest_memory_age_hours: float

    # 内容分析
    avg_content_length: int
    avg_tags_per_memory: float
    most_common_tags: list[tuple[str, int]]
    most_active_wings: list[tuple[str, int]]

    # 健康评分
    health_score: float  # 0-100
    health_issues: list[str]
    recommendations: list[str]

    # 元数据
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MemoryAnalyzer:
    """记忆分析引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def _analyze_time_ranges(self, drawers: list, now: datetime) -> tuple[int, int, int, int, float]:
        counts_24h = 0
        counts_7d = 0
        counts_30d = 0
        oldest = now
        newest = datetime(2000, 1, 1)

        for d in drawers:
            try:
                created = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                created = now

            if created > newest:
                newest = created
            if created < oldest:
                oldest = created

            age_hours = (now - created).total_seconds() / 3600
            if age_hours <= 24:
                counts_24h += 1
            if age_hours <= 24 * 7:
                counts_7d += 1
            if age_hours <= 24 * 30:
                counts_30d += 1

        oldest_days = (now - oldest).days if drawers else 0
        newest_hours = (now - newest).total_seconds() / 3600 if drawers else 0
        return counts_24h, counts_7d, counts_30d, oldest_days, newest_hours

    def analyze(self, drawers: list[Drawer],
                wiki_page_count: int = 0,
                access_data: dict[str, int] = None) -> MemoryAnalytics:
        now = datetime.now()

        wings = set(d.wing for d in drawers)
        rooms = set((d.wing, d.room) for d in drawers)
        all_tags = set()
        for d in drawers:
            all_tags.update(d.tags or [])

        wing_dist = dict(Counter(d.wing for d in drawers))
        room_dist = dict(Counter(f"{d.wing}/{d.room}" for d in drawers))
        hall_dist = dict(Counter(d.hall for d in drawers))
        tag_dist = dict(Counter(
            tag for d in drawers for tag in (d.tags or [])
        ))

        high = sum(1 for d in drawers if d.importance >= 4.0)
        medium = sum(1 for d in drawers if 2.0 <= d.importance < 4.0)
        low = sum(1 for d in drawers if d.importance < 2.0)
        avg_imp = (sum(d.importance for d in drawers) / len(drawers)
                   if drawers else 0.0)

        counts_24h, counts_7d, counts_30d, oldest_days, newest_hours = (
            self._analyze_time_ranges(drawers, now)
        )

        content_lengths = [len(d.content) for d in drawers]
        avg_content_len = (sum(content_lengths) // len(content_lengths)
                           if content_lengths else 0)
        avg_tags = (sum(len(d.tags or []) for d in drawers) / len(drawers)
                    if drawers else 0.0)

        top_tags = sorted(tag_dist.items(), key=lambda x: x[1], reverse=True)[:10]
        top_wings = sorted(wing_dist.items(), key=lambda x: x[1], reverse=True)[:5]

        health = self._health_assessment(
            drawers, wing_dist, access_data, avg_imp,
            oldest_days, newest_hours, avg_tags)

        return MemoryAnalytics(
            total_memories=len(drawers),
            total_wings=len(wings),
            total_rooms=len(rooms),
            total_tags=len(all_tags),
            total_wiki_pages=wiki_page_count,
            distribution_by_wing=wing_dist,
            distribution_by_room=room_dist,
            distribution_by_hall=hall_dist,
            distribution_by_tag=tag_dist,
            importance_distribution={"high": high, "medium": medium, "low": low},
            avg_importance=round(avg_imp, 2),
            memories_last_24h=counts_24h,
            memories_last_7d=counts_7d,
            memories_last_30d=counts_30d,
            oldest_memory_age_days=oldest_days,
            newest_memory_age_hours=round(newest_hours, 1),
            avg_content_length=avg_content_len,
            avg_tags_per_memory=round(avg_tags, 2),
            most_common_tags=top_tags,
            most_active_wings=top_wings,
            health_score=health["score"],
            health_issues=health["issues"],
            recommendations=health["recommendations"],
        )

    def _health_assessment(self, drawers: list[Drawer],
                           wing_dist: dict, access_data: dict,
                           avg_imp: float, oldest_days: int,
                           newest_hours: float, avg_tags: float) -> dict:
        """评估记忆系统健康度"""
        score = 100.0
        issues = []
        recommendations = []

        # 1. 记忆数量检查
        if len(drawers) == 0:
            score -= 30
            issues.append("记忆系统为空，没有任何记忆")
            recommendations.append("建议开始添加记忆内容")
        elif len(drawers) < 5:
            score -= 10
            issues.append("记忆数量较少（< 5 条）")
            recommendations.append("建议持续积累记忆")

        # 2. 重要性分布检查
        if avg_imp < 2.0:
            score -= 15
            issues.append("平均重要性过低（< 2.0），记忆质量可能偏低")
            recommendations.append("建议提高记忆的质量标准")
        elif avg_imp > 4.0:
            score -= 5
            issues.append("平均重要性过高（> 4.0），可能存在过度标记")
            recommendations.append("建议合理区分记忆的重要性等级")

        # 3. Wing 分布检查
        if len(wing_dist) == 1 and wing_dist.get("default", 0) == len(drawers):
            score -= 10
            issues.append("所有记忆都在默认空间，缺乏分类组织")
            recommendations.append("建议创建多个 Wing 来组织不同类型的记忆")

        # 4. 标签检查
        if avg_tags < 0.5:
            score -= 10
            issues.append("平均标签数过低（< 0.5），记忆缺乏分类标签")
            recommendations.append("建议为记忆添加更多标签以便检索")

        # 5. 时效性检查
        if newest_hours > 24 * 7:
            score -= 10
            issues.append("超过 7 天没有新记忆，系统可能处于停滞状态")
            recommendations.append("建议检查记忆采集流程是否正常")

        if oldest_days > 365:
            score -= 5
            issues.append(f"存在超过 1 年的旧记忆（{oldest_days}天），未进行压缩")
            recommendations.append("建议运行记忆压缩以精简旧记忆")

        # 6. 访问频率检查
        if access_data:
            total_accesses = sum(access_data.values())
            avg_access = total_accesses / len(drawers) if drawers else 0
            if avg_access < 0.1:
                score -= 10
                issues.append("记忆访问率极低，系统可能未被充分利用")
                recommendations.append("建议检查上层 Agent 是否正确调用记忆接口")

        # 7. 数据一致性
        content_too_short = sum(1 for d in drawers if len(d.content) < 10)
        if content_too_short > len(drawers) * 0.3:
            score -= 10
            issues.append("超过 30% 的记忆内容过短（< 10 字符）")
            recommendations.append("建议清理或合并过短的记忆片段")

        # 8. 冗余检查
        if len(drawers) > 100:
            score -= 5
            issues.append("记忆数量超过 100，建议进行去重和压缩")
            recommendations.append("建议运行去重检查，合并相似记忆")

        score = max(0.0, min(100.0, score))

        return {
            "score": round(score, 1),
            "issues": issues,
            "recommendations": recommendations,
        }

    def growth_trend(self, drawers: list[Drawer],
                     days: int = 30) -> list[dict]:
        """分析记忆增长趋势"""
        now = datetime.now()
        daily_counts = defaultdict(int)

        for d in drawers:
            try:
                created = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                continue
            day_key = created.strftime("%Y-%m-%d")
            daily_counts[day_key] += 1

        trend = []
        for i in range(days - 1, -1, -1):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            trend.append({
                "date": day,
                "count": daily_counts.get(day, 0),
            })

        return trend

    def activity_heatmap(self, drawers: list[Drawer],
                         access_data: dict[str, int]) -> dict:
        """生成活跃度热力图数据"""
        hour_counts = defaultdict(int)
        weekday_counts = defaultdict(int)

        for d in drawers:
            count = access_data.get(d.id, 0)
            if count == 0:
                continue
            try:
                created = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                continue
            hour_counts[created.hour] += count
            weekday_counts[created.weekday()] += count

        return {
            "by_hour": {str(h): hour_counts.get(h, 0) for h in range(24)},
            "by_weekday": {
                "周一": weekday_counts.get(0, 0),
                "周二": weekday_counts.get(1, 0),
                "周三": weekday_counts.get(2, 0),
                "周四": weekday_counts.get(3, 0),
                "周五": weekday_counts.get(4, 0),
                "周六": weekday_counts.get(5, 0),
                "周日": weekday_counts.get(6, 0),
            },
        }

    def anomaly_detect(self, drawers: list[Drawer]) -> list[dict]:
        """异常检测"""
        anomalies = []
        now = datetime.now()

        # 检测突然大量记忆涌入
        recent_24h = 0
        for d in drawers:
            try:
                created = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                continue
            if (now - created).total_seconds() / 3600 <= 24:
                recent_24h += 1

        if len(drawers) > 10 and recent_24h > len(drawers) * 0.5:
            anomalies.append({
                "type": "surge",
                "description": f"过去 24 小时新增 {recent_24h} 条记忆，占总量的 {recent_24h/len(drawers)*100:.0f}%",
                "severity": "warning",
            })

        # 检测内容完全相同的记忆
        content_map = defaultdict(list)
        for d in drawers:
            content_map[d.content.strip()].append(d.id)
        exact_dups = {k: v for k, v in content_map.items() if len(v) > 1}
        if exact_dups:
            anomalies.append({
                "type": "exact_duplicate",
                "description": f"发现 {len(exact_dups)} 组完全相同的记忆",
                "severity": "warning",
                "details": {k: v for k, v in list(exact_dups.items())[:5]},
            })

        # 检测异常高重要性
        very_high = [d.id for d in drawers if d.importance > 9.0]
        if very_high:
            anomalies.append({
                "type": "high_importance",
                "description": f"发现 {len(very_high)} 条异常高重要性记忆（> 9.0）",
                "severity": "info",
            })

        # 检测空洞
        empty_content = [d.id for d in drawers if not d.content.strip()]
        if empty_content:
            anomalies.append({
                "type": "empty_content",
                "description": f"发现 {len(empty_content)} 条空内容记忆",
                "severity": "warning",
                "details": empty_content[:10],
            })

        return anomalies

    def summary_report(self, analytics: MemoryAnalytics) -> str:
        """生成人类可读的摘要报告"""
        lines = [
            "=" * 50,
            "盘古记忆系统分析报告",
            "=" * 50,
            f"生成时间: {analytics.generated_at}",
            "",
            "[基本统计]",
            f"  总记忆数: {analytics.total_memories}",
            f"  空间数: {analytics.total_wings}",
            f"  房间数: {analytics.total_rooms}",
            f"  标签数: {analytics.total_tags}",
            f"  Wiki 页面数: {analytics.total_wiki_pages}",
            "",
            "[重要性分布]",
            f"  高 (>4.0): {analytics.importance_distribution.get('high', 0)}",
            f"  中 (2.0-4.0): {analytics.importance_distribution.get('medium', 0)}",
            f"  低 (<2.0): {analytics.importance_distribution.get('low', 0)}",
            f"  平均重要性: {analytics.avg_importance}",
            "",
            "[时间分析]",
            f"  最近 24h 新增: {analytics.memories_last_24h}",
            f"  最近 7d 新增: {analytics.memories_last_7d}",
            f"  最近 30d 新增: {analytics.memories_last_30d}",
            f"  最旧记忆: {analytics.oldest_memory_age_days} 天前",
            f"  最新记忆: {analytics.newest_memory_age_hours} 小时前",
            "",
            "[内容分析]",
            f"  平均内容长度: {analytics.avg_content_length} 字符",
            f"  平均标签数: {analytics.avg_tags_per_memory}",
            "",
            "[健康评分]",
            f"  健康度: {analytics.health_score}/100",
        ]

        if analytics.health_issues:
            lines.append("")
            lines.append("[问题]")
            for issue in analytics.health_issues:
                lines.append(f"  - {issue}")

        if analytics.recommendations:
            lines.append("")
            lines.append("[建议]")
            for rec in analytics.recommendations:
                lines.append(f"  - {rec}")

        if analytics.most_common_tags:
            lines.append("")
            lines.append("[热门标签]")
            for tag, count in analytics.most_common_tags[:5]:
                lines.append(f"  {tag}: {count}")

        if analytics.most_active_wings:
            lines.append("")
            lines.append("[活跃空间]")
            for wing, count in analytics.most_active_wings:
                lines.append(f"  {wing}: {count}")

        lines.append("")
        lines.append("=" * 50)

        return "\n".join(lines)
