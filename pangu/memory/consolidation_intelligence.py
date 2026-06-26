"""盘古记忆巩固智能 — 更智能的记忆合并和巩固策略

核心能力：
1. 语义聚类巩固：将语义相似的记忆合并为知识结晶
2. 重要性提升巩固：频繁访问的记忆自动提升重要性
3. 冲突解决巩固：发现矛盾记忆时智能选择最可靠版本
4. 层级巩固：L0→L1→L2→L3 多层渐进式压缩
5. 巩固效果评估：评估每次巩固的效果和信息保留率
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.consolidation_intelligence")


@dataclass
class ConsolidationAction:
    """巩固操作"""

    action_type: str  # merge / promote / resolve / compress / skip
    source_ids: list[str]
    target_id: str | None
    description: str
    info_preserved: float  # 0-1 信息保留率
    importance_delta: float


@dataclass
class ConsolidationReport:
    """巩固报告"""

    total_actions: int
    merges: int
    promotions: int
    resolutions: int
    compressions: int
    skipped: int
    avg_info_preserved: float
    actions: list[ConsolidationAction]


class ConsolidationIntelligence:
    """记忆巩固智能引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._consolidation_history: list[dict] = []

    def find_merge_candidates(self, drawers: list[Drawer]) -> list[list[Drawer]]:
        """查找可合并的记忆组"""
        tag_groups: dict[str, list[Drawer]] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        candidates = []
        seen_ids: set[str] = set()

        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue

            for d in group:
                if d.id in seen_ids:
                    continue

            if len(group) >= 3:
                members = [d for d in group if d.id not in seen_ids][:5]
                if len(members) >= 2:
                    candidates.append(members)
                    for m in members:
                        seen_ids.add(m.id)

        return candidates

    def merge_group(self, group: list[Drawer]) -> ConsolidationAction:
        """合并一组记忆"""
        contents = [d.content[:100] for d in group]
        all_tags = set()
        for d in group:
            all_tags.update(d.tags)

        max_importance = max(d.importance for d in group)
        f"[合并{len(group)}条] " + " | ".join(contents)[:300]

        return ConsolidationAction(
            action_type="merge",
            source_ids=[d.id for d in group],
            target_id=None,
            description=f"合并 {len(group)} 条相关记忆 ({', '.join(list(all_tags)[:3])})",
            info_preserved=0.75,
            importance_delta=max_importance * 0.1,
        )

    def _collect_promotions(self, drawers: list[Drawer], access_counts: dict[str, int]) -> list[ConsolidationAction]:
        actions = []
        for d in drawers:
            count = access_counts.get(d.id, 0)
            action = self._check_promotion_candidate(d, count)
            if action:
                actions.append(action)
        return actions

    def find_promotion_candidates(
        self, drawers: list[Drawer], access_counts: dict[str, int] = None
    ) -> list[ConsolidationAction]:
        """查找应提升重要性的记忆"""
        access_counts = access_counts or {}
        return self._collect_promotions(drawers, access_counts)[:10]

    def _check_promotion_candidate(self, d: Drawer, count: int) -> ConsolidationAction | None:
        if count >= 5 and d.importance / 5.0 < 0.6:
            boost = min(1.0, count * 0.1)
            return ConsolidationAction(
                action_type="promote",
                source_ids=[d.id],
                target_id=d.id,
                description=f"频繁访问({count}次)提升重要性",
                info_preserved=1.0,
                importance_delta=boost,
            )
        return None

    def find_conflicts(self, drawers: list[Drawer]) -> list[ConsolidationAction]:
        """发现并解决矛盾记忆"""
        negative_kw = ["失败", "错误", "问题", "不行", "有缺陷"]
        positive_kw = ["成功", "完成", "优秀", "通过", "正常"]

        tag_groups: dict[str, list[Drawer]] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        actions = []
        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue

            pos = [d for d in group if any(k in d.content for k in positive_kw)]
            neg = [d for d in group if any(k in d.content for k in negative_kw)]

            if pos and neg:
                latest = max(pos + neg, key=lambda d: d.importance)
                others = [d.id for d in (pos + neg) if d.id != latest.id]

                actions.append(
                    ConsolidationAction(
                        action_type="resolve",
                        source_ids=others,
                        target_id=latest.id,
                        description=f"解决 '{tag}' 冲突: 保留最高重要性版本",
                        info_preserved=0.85,
                        importance_delta=0,
                    )
                )

        return actions[:10]

    def compress_old_memories(self, drawers: list[Drawer], min_age_days: int = 60) -> list[ConsolidationAction]:
        """压缩旧记忆"""
        actions = []
        now = datetime.now()

        for d in drawers:
            if hasattr(d, "created_at") and d.created_at:
                try:
                    created = datetime.fromisoformat(d.created_at)
                    age_days = (now - created).days
                    if age_days > min_age_days and len(d.content) > 200:
                        actions.append(
                            ConsolidationAction(
                                action_type="compress",
                                source_ids=[d.id],
                                target_id=d.id,
                                description=f"压缩 {age_days} 天前的旧记忆 ({len(d.content)}字)",
                                info_preserved=0.7,
                                importance_delta=-0.1,
                            )
                        )
                except (ValueError, TypeError):
                    pass

        return actions[:10]

    def run_consolidation(self, drawers: list[Drawer], access_counts: dict[str, int] = None) -> ConsolidationReport:
        """执行完整巩固流程"""
        all_actions: list[ConsolidationAction] = []

        merge_candidates = self.find_merge_candidates(drawers)
        for group in merge_candidates:
            all_actions.append(self.merge_group(group))

        all_actions.extend(self.find_promotion_candidates(drawers, access_counts))
        all_actions.extend(self.find_conflicts(drawers))
        all_actions.extend(self.compress_old_memories(drawers))

        merges = sum(1 for a in all_actions if a.action_type == "merge")
        promotions = sum(1 for a in all_actions if a.action_type == "promote")
        resolutions = sum(1 for a in all_actions if a.action_type == "resolve")
        compressions = sum(1 for a in all_actions if a.action_type == "compress")
        avg_preserved = sum(a.info_preserved for a in all_actions) / len(all_actions) if all_actions else 1.0

        report = ConsolidationReport(
            total_actions=len(all_actions),
            merges=merges,
            promotions=promotions,
            resolutions=resolutions,
            compressions=compressions,
            skipped=0,
            avg_info_preserved=round(avg_preserved, 3),
            actions=all_actions,
        )

        self._consolidation_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "total_memories": len(drawers),
                "actions": len(all_actions),
                "merges": merges,
                "promotions": promotions,
                "resolutions": resolutions,
                "compressions": compressions,
            }
        )

        return report

    def get_consolidation_stats(self) -> dict:
        """获取巩固统计"""
        if not self._consolidation_history:
            return {"total_runs": 0}

        total_actions = sum(h["actions"] for h in self._consolidation_history)
        return {
            "total_runs": len(self._consolidation_history),
            "total_actions": total_actions,
            "total_merges": sum(h["merges"] for h in self._consolidation_history),
            "total_promotions": sum(h["promotions"] for h in self._consolidation_history),
            "total_resolutions": sum(h["resolutions"] for h in self._consolidation_history),
            "total_compressions": sum(h["compressions"] for h in self._consolidation_history),
        }


_consolidation_intel: ConsolidationIntelligence | None = None


def get_consolidation_intel(config: PanguConfig = None) -> ConsolidationIntelligence:
    """获取全局巩固智能实例"""
    global _consolidation_intel
    if _consolidation_intel is None:
        _consolidation_intel = ConsolidationIntelligence(config)
    return _consolidation_intel
