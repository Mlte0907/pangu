"""盘古因果推理引擎 — 深度因果分析

核心能力：
1. 因果链发现：从记忆中提取因果关系链
2. 反事实推理：如果 X 没发生会怎样
3. 因果图构建：构建因果关系图
4. 根因分析：找到问题的根本原因
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("pangu.memory.causal_reasoning")

CAUSAL_MARKERS = {
    "cause": ["因为", "由于", "原因是", "根源是", "起因", "导致", "造成", "引发"],
    "effect": ["所以", "因此", "结果", "导致", "造成", "产生", "形成"],
    "prevent": ["如果", "假如", "要是", "万一"],
    "sequence": ["然后", "接着", "随后", "之后", "紧接着"],
}


@dataclass
class CausalLink:
    """因果链接"""
    cause_id: str
    effect_id: str
    cause_text: str
    effect_text: str
    relation_type: str  # direct / indirect / correlative
    confidence: float
    evidence: list[str]


@dataclass
class CausalChain:
    """因果链"""
    chain_id: str
    links: list[CausalLink]
    root_cause: str
    final_effect: str
    chain_length: int
    overall_confidence: float


@dataclass
class CounterfactualResult:
    """反事实推理结果"""
    original_cause: str
    counterfactual: str
    predicted_effect: str
    confidence: float
    reasoning: str


class CausalReasoningEngine:
    """因果推理引擎"""

    def __init__(self, config=None):
        self.config = config
        self._causal_links: list[CausalLink] = []
        self._causal_chains: list[CausalChain] = []

    def discover_causal_links(self, drawers: list) -> list[CausalLink]:
        """从记忆中发现因果链接"""
        links = []

        for i, d1 in enumerate(drawers):
            c1 = d1.content.lower()
            is_cause = any(m in c1 for m in CAUSAL_MARKERS["cause"])

            if not is_cause:
                continue

            for j, d2 in enumerate(drawers):
                if i == j:
                    continue

                c2 = d2.content.lower()
                is_effect = any(m in c2 for m in CAUSAL_MARKERS["effect"])

                if is_effect:
                    link = self._try_create_causal_link(d1, d2)
                    if link:
                        links.append(link)

        seen = set()
        unique = []
        for link in links:
            key = (link.cause_id, link.effect_id)
            if key not in seen:
                seen.add(key)
                unique.append(link)

        self._causal_links = unique
        return unique

    def _try_create_causal_link(self, d1, d2) -> CausalLink | None:
        tags1 = set(d1.tags)
        tags2 = set(d2.tags)
        overlap = len(tags1 & tags2) / max(len(tags1 | tags2), 1)
        if overlap > 0.2:
            return CausalLink(
                cause_id=d1.id,
                effect_id=d2.id,
                cause_text=d1.content[:80],
                effect_text=d2.content[:80],
                relation_type="direct" if overlap > 0.5 else "indirect",
                confidence=min(0.9, 0.4 + overlap),
                evidence=[d1.id, d2.id],
            )
        return None

    def build_causal_chains(self, links: list[CausalLink] = None) -> list[CausalChain]:
        """构建因果链"""
        if links is None:
            links = self._causal_links

        if not links:
            return []

        adjacency: dict[str, list[CausalLink]] = {}
        for link in links:
            adjacency.setdefault(link.cause_id, []).append(link)

        chains = []
        visited_chains: set[tuple] = set()

        for link in links:
            chain_links = [link]
            current = link.effect_id

            for _ in range(5):
                next_links = adjacency.get(current, [])
                if not next_links:
                    break
                chain_links.append(next_links[0])
                current = next_links[0].effect_id

            chain_key = tuple(l.cause_id for l in chain_links)
            if chain_key not in visited_chains and len(chain_links) >= 2:
                visited_chains.add(chain_key)
                confidences = [l.confidence for l in chain_links]
                chains.append(CausalChain(
                    chain_id=f"chain_{len(chains)}",
                    links=chain_links,
                    root_cause=chain_links[0].cause_text,
                    final_effect=chain_links[-1].effect_text,
                    chain_length=len(chain_links),
                    overall_confidence=sum(confidences) / len(confidences),
                ))

        self._causal_chains = chains
        return chains

    def counterfactual_reasoning(self, cause_id: str, counterfactual: str, drawers: list) -> CounterfactualResult:
        """反事实推理"""
        cause_drawer = None
        for d in drawers:
            if d.id == cause_id:
                cause_drawer = d
                break

        if not cause_drawer:
            return CounterfactualResult(
                original_cause="unknown",
                counterfactual=counterfactual,
                predicted_effect="无法推理：原始因果未找到",
                confidence=0.0,
                reasoning="缺少原始因果数据",
            )

        related_effects = []
        for link in self._causal_links:
            if link.cause_id == cause_id:
                related_effects.append(link.effect_text)

        if related_effects:
            predicted = f"如果'{counterfactual}'，则以下结果可能不会发生：" + "；".join(related_effects[:3])
            confidence = 0.6
        else:
            predicted = f"如果'{counterfactual}'，影响范围不确定"
            confidence = 0.3

        return CounterfactualResult(
            original_cause=cause_drawer.content[:80],
            counterfactual=counterfactual,
            predicted_effect=predicted,
            confidence=confidence,
            reasoning=f"基于 {len(related_effects)} 个已知因果关系推断",
        )

    def root_cause_analysis(self, effect_text: str, drawers: list) -> dict:
        """根因分析"""
        potential_causes = []

        for link in self._causal_links:
            if any(kw in effect_text for kw in link.effect_text.split()):
                potential_causes.append({
                    "cause": link.cause_text,
                    "confidence": link.confidence,
                    "relation": link.relation_type,
                    "id": link.cause_id,
                })

        potential_causes.sort(key=lambda x: x["confidence"], reverse=True)

        if potential_causes:
            return {
                "effect": effect_text[:80],
                "root_cause": potential_causes[0]["cause"],
                "all_causes": potential_causes[:5],
                "total_causes_found": len(potential_causes),
            }

        return {
            "effect": effect_text[:80],
            "root_cause": "未找到明确根因",
            "all_causes": [],
            "total_causes_found": 0,
        }

    def get_causal_stats(self) -> dict:
        """获取因果推理统计"""
        return {
            "total_links": len(self._causal_links),
            "total_chains": len(self._causal_chains),
            "avg_chain_length": (
                sum(c.chain_length for c in self._causal_chains) / len(self._causal_chains)
                if self._causal_chains else 0
            ),
            "avg_confidence": (
                sum(l.confidence for l in self._causal_links) / len(self._causal_links)
                if self._causal_links else 0
            ),
            "direct_relations": sum(1 for l in self._causal_links if l.relation_type == "direct"),
            "indirect_relations": sum(1 for l in self._causal_links if l.relation_type == "indirect"),
        }


_causal_engine: CausalReasoningEngine | None = None


def get_causal_engine(config=None) -> CausalReasoningEngine:
    """获取全局因果推理实例"""
    global _causal_engine
    if _causal_engine is None:
        _causal_engine = CausalReasoningEngine(config)
    return _causal_engine
