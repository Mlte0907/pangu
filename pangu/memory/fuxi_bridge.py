"""盘古-Fuxi 桥接引擎 — 调用 Fuxi 认知能力做深度分析

核心能力：
1. 知识发现：从记忆中发现知识空白和关联
2. 模式分析：识别用户行为模式和偏好
3. 质量评估：深度评估记忆质量
4. 洞察生成：从多条记忆中生成深层洞察

不直接依赖 Fuxi，而是复用其核心算法逻辑。
"""

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.fuxi_bridge")


@dataclass
class Insight:
    """洞察"""

    insight_type: str  # pattern, gap, connection, suggestion
    content: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    related_memories: list[str] = field(default_factory=list)


class FuxiBridge:
    """Fuxi 桥接引擎 — 复用 Fuxi 核心算法"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._drawers_file = Path(self.config.palace_path) / "drawers.json"

    def _load_drawers(self) -> list[dict]:
        """加载记忆"""
        if self._drawers_file.exists():
            with open(self._drawers_file, encoding="utf-8") as f:
                return json.load(f)
        return []

    def discover_knowledge_gaps(self, drawers: list[dict] = None) -> list[Insight]:
        """发现知识空白"""
        if drawers is None:
            drawers = self._load_drawers()

        insights = []

        # 1. 检查主题覆盖度
        topics = defaultdict(int)
        for d in drawers:
            tags = d.get("tags", [])
            for tag in tags:
                topics[tag] += 1

        # 找出低频主题
        low_freq = {t: c for t, c in topics.items() if c <= 2 and t not in ["general", "auto_extracted"]}
        if low_freq:
            insights.append(
                Insight(
                    insight_type="gap",
                    content=f"以下主题知识较少：{', '.join(list(low_freq.keys())[:5])}",
                    confidence=0.7,
                    evidence=[f"{t}: {c}条" for t, c in low_freq.items()],
                )
            )

        # 2. 检查时间覆盖
        dates = set()
        for d in drawers:
            created = d.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    dates.add(dt.date().isoformat())
                except Exception:
                    pass

        if len(dates) < 7:
            insights.append(
                Insight(
                    insight_type="gap",
                    content=f"知识时间跨度较短（{len(dates)}天），建议增加历史知识",
                    confidence=0.6,
                )
            )

        return insights

    def analyze_user_patterns(self, drawers: list[dict] = None) -> list[Insight]:
        """分析用户行为模式"""
        if drawers is None:
            drawers = self._load_drawers()

        insights = []

        # 1. 决策模式
        decisions = [d for d in drawers if "decision" in d.get("tags", [])]
        if len(decisions) > 5:
            # 分析决策主题
            decision_topics = []
            for d in decisions:
                content = d.get("content", "")
                # 提取决策对象
                match = re.search(r"(?:决定|确认|选择|采用|切换到|改为|使用)\s*(.{2,20})", content)
                if match:
                    decision_topics.append(match.group(1))

            if decision_topics:
                topic_counts = Counter(decision_topics).most_common(3)
                insights.append(
                    Insight(
                        insight_type="pattern",
                        content=f"用户频繁决策的主题：{', '.join([t for t, _ in topic_counts])}",
                        confidence=0.8,
                        evidence=[f"{t}: {c}次" for t, c in topic_counts],
                    )
                )

        # 2. 关注领域
        tag_counts = Counter()
        for d in drawers:
            for tag in d.get("tags", []):
                if tag not in ["auto_extracted", "auto_collected", "fused"]:
                    tag_counts[tag] += 1

        top_tags = tag_counts.most_common(5)
        if top_tags:
            insights.append(
                Insight(
                    insight_type="pattern",
                    content=f"用户关注领域：{', '.join([t for t, _ in top_tags])}",
                    confidence=0.9,
                    evidence=[f"{t}: {c}条" for t, c in top_tags],
                )
            )

        return insights

    def generate_insights(self, drawers: list[dict] = None) -> list[Insight]:
        """生成深层洞察"""
        if drawers is None:
            drawers = self._load_drawers()

        insights = []

        # 1. 知识关联
        insights.extend(self._find_connections(drawers))

        # 2. 改进建议
        insights.extend(self._generate_suggestions(drawers))

        return insights

    def _find_connections(self, drawers: list[dict]) -> list[Insight]:
        """发现记忆之间的关联"""
        insights = []

        # 按标签分组
        tag_groups = defaultdict(list)
        for d in drawers:
            for tag in d.get("tags", []):
                if tag not in ["auto_extracted", "auto_collected"]:
                    tag_groups[tag].append(d)

        # 找出有重叠的主题
        for tag1, group1 in tag_groups.items():
            for tag2, group2 in tag_groups.items():
                if tag1 >= tag2:
                    continue
                # 检查内容重叠
                overlap = 0
                for d1 in group1[:5]:
                    content1 = set(d1.get("content", "").split())
                    for d2 in group2[:5]:
                        content2 = set(d2.get("content", "").split())
                        overlap += len(content1 & content2)

                if overlap > 10:
                    insights.append(
                        Insight(
                            insight_type="connection",
                            content=f"主题 '{tag1}' 和 '{tag2}' 有较强关联",
                            confidence=0.7,
                            evidence=[f"内容重叠词数: {overlap}"],
                        )
                    )

        return insights[:3]  # 最多返回3条

    def _generate_suggestions(self, drawers: list[dict]) -> list[Insight]:
        """生成改进建议"""
        insights = []

        # 1. 检查记忆质量分布
        scores = []
        for d in drawers:
            content = d.get("content", "")
            score = 0
            if len(content) > 100:
                score += 30
            if len(content) > 50:
                score += 20
            if len(d.get("tags", [])) >= 2:
                score += 20
            if re.search(r"[：:]", content):
                score += 10
            scores.append(score)

        avg_score = sum(scores) / len(scores) if scores else 0
        if avg_score < 50:
            insights.append(
                Insight(
                    insight_type="suggestion",
                    content=f"平均记忆质量分偏低（{avg_score:.0f}/100），建议补充更多高质量内容",
                    confidence=0.8,
                )
            )

        # 2. 检查知识新鲜度
        recent_count = 0
        cutoff = datetime.now().isoformat()[:10]
        for d in drawers:
            created = d.get("created_at", "")[:10]
            if created >= cutoff:
                recent_count += 1

        if recent_count < 5:
            insights.append(
                Insight(
                    insight_type="suggestion",
                    content="最近新增知识较少，建议增加知识提取频率",
                    confidence=0.7,
                )
            )

        return insights

    def get_comprehensive_report(self) -> dict:
        """获取综合分析报告"""
        drawers = self._load_drawers()

        all_insights = []
        all_insights.extend(self.discover_knowledge_gaps(drawers))
        all_insights.extend(self.analyze_user_patterns(drawers))
        all_insights.extend(self.generate_insights(drawers))

        # 按类型分组
        by_type = defaultdict(list)
        for insight in all_insights:
            by_type[insight.insight_type].append(insight)

        return {
            "total_memories": len(drawers),
            "total_insights": len(all_insights),
            "insights_by_type": {
                k: [{"content": i.content, "confidence": i.confidence} for i in v] for k, v in by_type.items()
            },
            "timestamp": datetime.now().isoformat(),
        }


# 单例
_bridge: FuxiBridge | None = None


def get_fuxi_bridge() -> FuxiBridge:
    """获取单例桥接"""
    global _bridge
    if _bridge is None:
        _bridge = FuxiBridge()
    return _bridge
