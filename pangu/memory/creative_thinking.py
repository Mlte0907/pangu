"""盘古创造性思维 — 基于知识图谱生成新想法

核心功能：
1. 知识关联：发现不同领域知识的关联
2. 模式发现：从历史记忆中发现重复模式
3. 想法生成：基于已有知识生成新想法
4. 类比推理：将一个领域的解决方案迁移到另一个领域
"""

import logging
from dataclasses import dataclass

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.creative_thinking")


@dataclass
class Idea:
    """生成的想法"""

    title: str
    description: str
    source_memories: list[str]  # 来源记忆 ID
    confidence: float
    category: str  # innovation / improvement / solution


class CreativeThinking:
    """创造性思维 — 基于知识图谱生成新想法"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._idea_history: list[Idea] = []

    def _collect_wing_topics(self, wing_drawers: list[Drawer]) -> set[str]:
        topics = set()
        for d in wing_drawers:
            for tag in d.tags:
                topics.add(tag)
        return topics

    def _detect_wing_pattern(self, wing: str, wing_drawers: list[Drawer]) -> dict | None:
        """检测单个 Wing 中的重复主题模式"""
        if len(wing_drawers) < 3:
            return None
        topics = self._collect_wing_topics(wing_drawers)
        if len(topics) < 2:
            return None
        return {
            "type": "recurring_theme",
            "wing": wing,
            "topics": list(topics)[:5],
            "count": len(wing_drawers),
            "suggestion": f"在 {wing} 领域发现 {len(topics)} 个相关主题",
        }

    def discover_patterns(self, drawers: list[Drawer]) -> list[dict]:
        patterns = []

        by_wing = {}
        for d in drawers:
            wing = d.wing
            if wing not in by_wing:
                by_wing[wing] = []
            by_wing[wing].append(d)

        for wing, wing_drawers in by_wing.items():
            pattern = self._detect_wing_pattern(wing, wing_drawers)
            if pattern:
                patterns.append(pattern)

        return patterns

    def generate_ideas(self, drawers: list[Drawer], context: str = "") -> list[Idea]:
        """基于记忆生成新想法"""
        ideas = []

        # 发现跨领域关联
        cross_domain_ideas = self._find_cross_domain_links(drawers)
        ideas.extend(cross_domain_ideas)

        # 发现改进机会
        improvement_ideas = self._find_improvement_opportunities(drawers)
        ideas.extend(improvement_ideas)

        # 保存想法历史
        self._idea_history.extend(ideas)
        if len(self._idea_history) > 100:
            self._idea_history = self._idea_history[-100:]

        return ideas

    def _find_cross_domain_links(self, drawers: list[Drawer]) -> list[Idea]:
        """发现跨领域关联"""
        ideas = []

        # 按 wing 分组
        by_wing = {}
        for d in drawers:
            wing = d.wing
            if wing not in by_wing:
                by_wing[wing] = []
            by_wing[wing].append(d)

        # 查找不同 wing 间的标签重叠
        wings = list(by_wing.keys())
        for i in range(len(wings)):
            for j in range(i + 1, len(wings)):
                wing1_tags = set()
                wing2_tags = set()
                for d in by_wing[wings[i]]:
                    wing1_tags.update(d.tags)
                for d in by_wing[wings[j]]:
                    wing2_tags.update(d.tags)

                common = wing1_tags & wing2_tags
                if common:
                    ideas.append(
                        Idea(
                            title=f"{wings[i]} 与 {wings[j]} 的关联",
                            description=f"发现共同主题: {', '.join(list(common)[:3])}",
                            source_memories=[d.id for d in by_wing[wings[i]][:2]],
                            confidence=0.7,
                            category="innovation",
                        )
                    )

        return ideas

    def _find_improvement_opportunities(self, drawers: list[Drawer]) -> list[Idea]:
        """发现改进机会"""
        ideas = []

        # 查找低重要性记忆（可能是改进机会）
        low_importance = [d for d in drawers if d.importance / 5.0 < 0.3]
        if len(low_importance) > 5:
            ideas.append(
                Idea(
                    title="记忆优化机会",
                    description=f"发现 {len(low_importance)} 条低重要性记忆，可能需要压缩或归档",
                    source_memories=[d.id for d in low_importance[:3]],
                    confidence=0.6,
                    category="improvement",
                )
            )

        return ideas

    def get_idea_history(self, limit: int = 10) -> list[dict]:
        """获取想法历史"""
        return [
            {
                "title": idea.title,
                "description": idea.description,
                "category": idea.category,
                "confidence": idea.confidence,
            }
            for idea in self._idea_history[-limit:]
        ]

    def _generate_tag_pair_ideas(self, wing: str, tag_list: list[str]) -> list[dict]:
        ideas = []
        for i in range(min(3, len(tag_list))):
            for j in range(i + 1, min(5, len(tag_list))):
                if tag_list[i] != tag_list[j]:
                    ideas.append(
                        {
                            "title": f"跨领域创新: {tag_list[i]} + {tag_list[j]}",
                            "description": f"结合 {tag_list[i]} 和 {tag_list[j]} 可能产生创新",
                            "confidence": 0.7,
                            "category": "innovation",
                        }
                    )
        return ideas

    def generate_novel_ideas(self, domain: str, context: str, drawers: list[Drawer] = None) -> list[dict]:
        """生成原创想法 — 基于领域知识和上下文生成创新方案"""
        ideas = []
        if not drawers:
            return ideas

        # 分析上下文关键词
        context_keywords = set()
        for word in context.split():
            if len(word) >= 2:
                context_keywords.add(word.lower())

        # 基于领域发现创新机会
        by_wing: dict[str, list[Drawer]] = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            if wing == domain or not domain:
                all_tags = set()
                for d in wing_drawers:
                    all_tags.update(d.tags)

                if len(all_tags) >= 3:
                    tag_list = list(all_tags)
                    ideas.extend(self._generate_tag_pair_ideas(wing, tag_list))

        return ideas[:10]


# 全局单例
_creative_thinking: CreativeThinking | None = None


def get_creative_thinking(config: PanguConfig = None) -> CreativeThinking:
    """获取全局创造性思维实例"""
    global _creative_thinking
    if _creative_thinking is None:
        _creative_thinking = CreativeThinking(config)
    return _creative_thinking
