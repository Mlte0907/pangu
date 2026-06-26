"""盘古多策略辩论引擎 — 并行推理 + 裁判评分选最优

核心功能：
1. 多策略并行推理 — 分析型/创意型/保守型三种策略
2. 四维度评分 — 逻辑性/可行性/创新性/完整性
3. 加权总分选优 — 按维度权重计算胜出策略
"""

import logging
import time
from dataclasses import dataclass, field

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.debate")

MIN_STRATEGIES = 2
MAX_STRATEGIES = 3
MONTHLY_QUOTA = 50

DEBATE_DIMENSIONS = ["logic", "feasibility", "innovation", "completeness"]
DIMENSION_WEIGHTS = {"logic": 0.30, "feasibility": 0.30, "innovation": 0.20, "completeness": 0.20}

STRATEGY_TEMPLATES = [
    {"name": "analytical", "description": "分析型策略 — 逻辑推演、因果分析、数据驱动"},
    {"name": "creative", "description": "创意型策略 — 跳跃思维、类比推理、非常规方案"},
    {"name": "conservative", "description": "保守型策略 — 风险规避、渐进方案、经验复用"},
]

LOGIC_KEYWORDS = ["因为", "因此", "所以", "由于", "从而", "导致", "推论", "证明", "根据", "基于"]
FEASIBILITY_KEYWORDS = ["实现", "可行", "步骤", "方案", "执行", "部署", "落地", "操作", "流程", "工具"]
INNOVATION_KEYWORDS = ["创新", "突破", "新颖", "独特", "颠覆", "重新定义", "前所未有", "跨界", "融合", "范式"]
COMPLETENESS_KEYWORDS = ["首先", "其次", "最后", "此外", "另外", "同时", "包括", "涵盖", "全面", "整体"]


def _clamp_score(value: int) -> int:
    return max(0, min(5, value))


def _count_keywords(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


@dataclass
class DebateStrategy:
    name: str = ""
    description: str = ""
    answer: str = ""
    scores: dict[str, int] = field(
        default_factory=lambda: {"logic": 0, "feasibility": 0, "innovation": 0, "completeness": 0}
    )

    @property
    def weighted_total(self) -> float:
        return sum(self.scores.get(d, 0) * DIMENSION_WEIGHTS.get(d, 0.25) for d in DEBATE_DIMENSIONS)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "answer": self.answer[:200],
            "scores": self.scores,
            "weighted_total": round(self.weighted_total, 2),
        }


def _generate_strategy_answer(strategy: dict, question: str, context: str) -> str:
    name = strategy["name"]
    desc = strategy["description"]
    parts = [f"[{name}策略] {desc}", f"问题：{question}"]
    if context:
        parts.append(f"上下文：{context}")

    if name == "analytical":
        parts.append("分析路径：分解问题 → 识别因果 → 逻辑推演 → 验证结论")
        parts.append("基于逻辑推演，逐步分解问题核心要素，建立因果链条，推导出严谨结论。")
    elif name == "creative":
        parts.append("分析路径：类比联想 → 跨域借鉴 → 重组创新 → 突破常规")
        parts.append("跳出常规思维框架，通过类比和跨界借鉴，探索非传统解决方案。")
    elif name == "conservative":
        parts.append("分析路径：风险评估 → 经验复用 → 渐进方案 → 安全验证")
        parts.append("基于已有经验和最佳实践，选择风险可控的渐进式方案，确保稳定性。")

    return "\n".join(parts)


def _score_strategy(strategy: DebateStrategy, question: str) -> DebateStrategy:
    answer = strategy.answer

    if len(answer) < 20:
        strategy.scores = {"logic": 1, "feasibility": 1, "innovation": 1, "completeness": 1}
        return strategy

    logic_score = min(5, 2 + _count_keywords(answer, LOGIC_KEYWORDS))
    feasibility_score = min(5, 2 + _count_keywords(answer, FEASIBILITY_KEYWORDS))
    innovation_score = min(5, 2 + _count_keywords(answer, INNOVATION_KEYWORDS))
    completeness_score = min(5, 2 + _count_keywords(answer, COMPLETENESS_KEYWORDS))

    sentences = [
        s.strip()
        for s in answer.replace("。", ".\n").replace("！", "!\n").replace("？", "?\n").split("\n")
        if s.strip()
    ]
    if len(sentences) >= 5:
        completeness_score = min(5, completeness_score + 1)
    elif len(sentences) < 3:
        completeness_score = max(1, completeness_score - 1)

    if len(answer) > 100:
        logic_score = min(5, logic_score + 1)

    if strategy.name == "analytical":
        logic_score = min(5, logic_score + 1)
    elif strategy.name == "creative":
        innovation_score = min(5, innovation_score + 1)
    elif strategy.name == "conservative":
        feasibility_score = min(5, feasibility_score + 1)

    if question:
        question_chars = set(question.replace("？", "").replace("?", "").replace("的", "").replace("了", ""))
        answer_chars = set(answer)
        overlap = len(question_chars & answer_chars)
        if overlap > 3:
            logic_score = min(5, logic_score + 1)
            completeness_score = min(5, completeness_score + 1)

    strategy.scores = {
        "logic": _clamp_score(logic_score),
        "feasibility": _clamp_score(feasibility_score),
        "innovation": _clamp_score(innovation_score),
        "completeness": _clamp_score(completeness_score),
    }
    return strategy


class DebateEngine:
    """多策略辩论引擎 — 并行推理 + 裁判评分选最优"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._quota: dict = {}
        self._cache: dict = {}

    def _check_quota(self) -> bool:
        current_month = time.strftime("%Y-%m")
        used = self._quota.get(current_month, 0)
        return used < MONTHLY_QUOTA

    def _increment_quota(self):
        current_month = time.strftime("%Y-%m")
        self._quota[current_month] = self._quota.get(current_month, 0) + 1

    def run_debate(self, question: str, strategies_count: int = 2, context: str = "") -> dict:
        """运行辩论 — 多策略并行推理 + 评分选优"""
        if not question:
            return {"status": "error", "reason": "question is required"}

        if not self._check_quota():
            return {"status": "error", "reason": "monthly quota exceeded"}

        strategies_count = max(MIN_STRATEGIES, min(MAX_STRATEGIES, strategies_count))

        cache_key = f"{hash(question)}_{strategies_count}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached.get("ts", 0) < 3600:
            return cached["result"]

        selected_templates = STRATEGY_TEMPLATES[:strategies_count]
        strategies: list[DebateStrategy] = []

        for template in selected_templates:
            answer = _generate_strategy_answer(template, question, context)
            strategy = DebateStrategy(
                name=template["name"],
                description=template["description"],
                answer=answer,
            )
            strategy = _score_strategy(strategy, question)
            strategies.append(strategy)

        total_scores = {s.name: round(s.weighted_total, 2) for s in strategies}
        winner_strategy = max(strategies, key=lambda s: s.weighted_total)

        reasoning_parts = []
        for s in strategies:
            reasoning_parts.append(
                f"{s.name}: L={s.scores['logic']} F={s.scores['feasibility']} "
                f"I={s.scores['innovation']} C={s.scores['completeness']} "
                f"加权={s.weighted_total:.2f}"
            )
        reasoning_parts.append(f"胜出策略: {winner_strategy.name} (加权总分最高)")

        result = {
            "question": question[:200],
            "strategies": [s.to_dict() for s in strategies],
            "winner": winner_strategy.name,
            "total_scores": total_scores,
            "reasoning": "; ".join(reasoning_parts),
        }

        self._increment_quota()
        self._cache[cache_key] = {"result": result, "ts": time.time()}
        return result

    def score_strategies(self, question: str, strategies_count: int = 2, context: str = "") -> dict:
        """对策略进行评分（不缓存，用于外部策略）"""
        if not question:
            return {"status": "error", "reason": "question is required"}

        strategies_count = max(MIN_STRATEGIES, min(MAX_STRATEGIES, strategies_count))
        selected_templates = STRATEGY_TEMPLATES[:strategies_count]
        strategies = []

        for template in selected_templates:
            answer = _generate_strategy_answer(template, question, context)
            strategy = DebateStrategy(
                name=template["name"],
                description=template["description"],
                answer=answer,
            )
            strategy = _score_strategy(strategy, question)
            strategies.append(strategy)

        return {
            "strategies": [s.to_dict() for s in strategies],
            "total_scores": {s.name: round(s.weighted_total, 2) for s in strategies},
        }

    def select_winner(self, strategies: list[dict]) -> dict:
        """从已评分策略中选择胜者"""
        if not strategies:
            return {"error": "no strategies provided"}

        best = max(strategies, key=lambda s: s.get("weighted_total", 0))
        return {"winner": best.get("name", ""), "score": best.get("weighted_total", 0)}

    def get_stats(self) -> dict:
        """获取辩论统计"""
        current_month = time.strftime("%Y-%m")
        used = self._quota.get(current_month, 0)
        return {
            "monthly_quota": MONTHLY_QUOTA,
            "monthly_used": used,
            "monthly_remaining": MONTHLY_QUOTA - used,
            "cache_size": len(self._cache),
        }


_engine: DebateEngine | None = None


def get_debate_engine(config: PanguConfig = None) -> DebateEngine:
    global _engine
    if _engine is None:
        _engine = DebateEngine(config)
    return _engine
