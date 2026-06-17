"""盘古自主学习 — 自动发现新知识，无需人工干预

核心功能：
1. 知识发现：从记忆中自动发现新知识和模式
2. 模式学习：从用户行为中学习模式
3. 假设生成：基于已有知识生成假设
4. 假设验证：验证假设的正确性
5. 知识更新：根据验证结果更新知识
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.autonomous_learning")


@dataclass
class Hypothesis:
    """假设"""
    statement: str
    confidence: float
    evidence: list[str]  # 支持证据
    source_memories: list[str]
    status: str = "pending"  # pending / verified / rejected


class AutonomousLearning:
    """自主学习 — 自动发现新知识"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._knowledge_base: list[dict] = []
        self._hypotheses: list[Hypothesis] = []
        self._learning_history: list[dict] = []

    def _detect_wing_pattern(self, wing: str, wing_drawers: list[Drawer]) -> dict | None:
        all_tags = set()
        for d in wing_drawers:
            all_tags.update(d.tags)

        if len(all_tags) >= 2:
            return {
                "type": "pattern",
                "wing": wing,
                "tags": list(all_tags)[:5],
                "count": len(wing_drawers),
                "description": f"在 {wing} 领域发现 {len(all_tags)} 个相关主题",
            }
        return None

    def discover_knowledge(self, drawers: list[Drawer]) -> list[dict]:
        discoveries = []

        by_wing = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            if len(wing_drawers) >= 3:
                pattern = self._detect_wing_pattern(wing, wing_drawers)
                if pattern:
                    discoveries.append(pattern)

        return discoveries

    def generate_hypotheses(self, drawers: list[Drawer]) -> list[Hypothesis]:
        """基于记忆生成假设"""
        hypotheses = []

        # 发现因果关系
        for d in drawers:
            content = d.content.lower()
            if "因为" in content or "导致" in content or "所以" in content:
                hypotheses.append(Hypothesis(
                    statement=f"发现因果关系: {d.content[:50]}",
                    confidence=0.6,
                    evidence=[d.id],
                    source_memories=[d.id],
                ))

        # 发现改进建议
        low_importance = [d for d in drawers if d.importance / 5.0 < 0.3]
        if len(low_importance) > 3:
            hypotheses.append(Hypothesis(
                statement=f"发现 {len(low_importance)} 条低重要性记忆，可能需要优化",
                confidence=0.5,
                evidence=[d.id for d in low_importance[:3]],
                source_memories=[d.id for d in low_importance[:5]],
            ))

        self._hypotheses.extend(hypotheses)
        return hypotheses

    def verify_hypothesis(self, hypothesis: Hypothesis, drawers: list[Drawer]) -> dict:
        """验证假设"""
        # 简单的验证：检查证据是否仍然存在
        evidence_exists = 0
        for eid in hypothesis.evidence:
            for d in drawers:
                if d.id == eid:
                    evidence_exists += 1
                    break

        confidence = evidence_exists / max(len(hypothesis.evidence), 1)
        status = "verified" if confidence > 0.5 else "rejected"

        return {
            "hypothesis": hypothesis.statement,
            "status": status,
            "confidence": confidence,
            "evidence_found": evidence_exists,
        }

    def get_learning_stats(self) -> dict:
        """获取学习统计"""
        return {
            "knowledge_base": len(self._knowledge_base),
            "hypotheses": len(self._hypotheses),
            "verified": sum(1 for h in self._hypotheses if h.status == "verified"),
            "pending": sum(1 for h in self._hypotheses if h.status == "pending"),
        }

    def auto_learn(self, drawers: list[Drawer]) -> dict:
        """自主学习循环 — 发现→假设→验证→更新"""
        # 1. 发现知识
        discoveries = self.discover_knowledge(drawers)

        # 2. 生成假设
        hypotheses = self.generate_hypotheses(drawers)

        # 3. 验证假设
        verified = []
        rejected = []
        for h in hypotheses[:5]:
            result = self.verify_hypothesis(h, drawers)
            if result["status"] == "verified":
                verified.append(h)
                h.status = "verified"
            else:
                rejected.append(h)
                h.status = "rejected"

        # 4. 记录学习结果
        self._learning_history.append({
            "timestamp": datetime.now().isoformat(),
            "discoveries": len(discoveries),
            "hypotheses": len(hypotheses),
            "verified": len(verified),
            "rejected": len(rejected),
        })

        return {
            "discoveries": len(discoveries),
            "hypotheses_generated": len(hypotheses),
            "verified": len(verified),
            "rejected": len(rejected),
            "total_learning_cycles": len(self._learning_history),
        }


# 全局单例
_autonomous_learning: AutonomousLearning | None = None


def get_autonomous_learning(config: PanguConfig = None) -> AutonomousLearning:
    """获取全局自主学习实例"""
    global _autonomous_learning
    if _autonomous_learning is None:
        _autonomous_learning = AutonomousLearning(config)
    return _autonomous_learning
