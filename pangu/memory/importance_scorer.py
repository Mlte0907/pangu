"""盘古记忆重要性评分 — 基于多维度特征的智能评分

核心功能：
1. 多维度特征提取：内容、时间、访问、标签、情感
2. 自适应权重：根据使用反馈动态调整权重
3. 重要性预测：预测记忆的长期价值
4. 评分解释：解释为什么给这个分数
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.importance_scorer")


@dataclass
class ImportanceScore:
    """重要性评分结果"""
    score: float  # 0.0 - 1.0
    factors: dict[str, float]  # 各维度得分
    explanation: str  # 评分解释


class ImportanceScorer:
    """记忆重要性评分 — 基于多维度特征"""

    # 默认权重
    DEFAULT_WEIGHTS = {
        "content": 0.25,      # 内容质量
        "recency": 0.20,      # 时效性
        "frequency": 0.20,    # 访问频率
        "importance": 0.15,   # 原始重要性
        "tags": 0.10,         # 标签丰富度
        "emotional": 0.10,    # 情感强度
    }

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._weights = dict(self.DEFAULT_WEIGHTS)
        self._feedback_history: list[dict] = []

    def score(self, drawer: Drawer, context: str = "") -> ImportanceScore:
        """计算记忆重要性评分

        Args:
            drawer: 记忆对象
            context: 当前上下文（可选）

        Returns:
            ImportanceScore 包含分数、因素和解释
        """
        factors = {}

        # 内容质量：长度、关键词密度
        content_len = len(drawer.content)
        if content_len > 200:
            factors["content"] = 1.0
        elif content_len > 100:
            factors["content"] = 0.8
        elif content_len > 50:
            factors["content"] = 0.6
        else:
            factors["content"] = 0.4

        # 时效性：新记忆得分更高
        try:
            days_old = (datetime.now() - datetime.fromisoformat(drawer.created_at)).total_seconds() / 86400
            factors["recency"] = max(0.0, 1.0 - days_old / 30)
        except Exception:
            factors["recency"] = 0.5

        # 访问频率（从 metadata 获取）
        access_count = drawer.metadata.get("access_count", 0)
        factors["frequency"] = min(access_count / 10, 1.0)

        # 原始重要性
        factors["importance"] = drawer.importance / 5.0

        # 标签丰富度
        factors["tags"] = min(len(drawer.tags) / 5, 1.0)

        # 情感强度
        factors["emotional"] = abs(drawer.emotional_weight) if drawer.emotional_weight else 0.0

        # 加权求和
        score = sum(factors.get(k, 0) * v for k, v in self._weights.items())

        # 上下文加成
        if context:
            context_lower = context.lower()
            content_lower = drawer.content.lower()
            if any(kw in content_lower for kw in context_lower.split() if len(kw) >= 2):
                score = min(1.0, score * 1.2)

        # 生成解释
        explanation = self._generate_explanation(factors, score)

        return ImportanceScore(
            score=round(min(1.0, max(0.0, score)), 3),
            factors=factors,
            explanation=explanation,
        )

    def _generate_explanation(self, factors: dict[str, float], score: float) -> str:
        """生成评分解释"""
        top_factors = sorted(factors.items(), key=lambda x: -x[1])[:3]
        explanations = []
        for factor, value in top_factors:
            if value >= 0.8:
                explanations.append(f"{factor}优秀")
            elif value >= 0.5:
                explanations.append(f"{factor}良好")
            else:
                explanations.append(f"{factor}一般")

        return f"综合评分 {score:.1%}，主要因素: {', '.join(explanations)}"

    def update_weights(self, feedback: dict[str, float]) -> None:
        """根据反馈更新权重"""
        self._feedback_history.append(feedback)
        if len(self._feedback_history) > 100:
            self._feedback_history = self._feedback_history[-100:]

        # 简单的在线学习：如果反馈积极，增加相关特征的权重
        for factor, delta in feedback.items():
            if factor in self._weights:
                self._weights[factor] = max(0.05, min(0.5, self._weights[factor] + delta))

        # 归一化权重
        total = sum(self._weights.values())
        if total > 0:
            for k in self._weights:
                self._weights[k] /= total

    def get_weights(self) -> dict[str, float]:
        """获取当前权重"""
        return dict(self._weights)


# 全局单例
_importance_scorer: ImportanceScorer | None = None


def get_importance_scorer(config: PanguConfig = None) -> ImportanceScorer:
    """获取全局重要性评分器"""
    global _importance_scorer
    if _importance_scorer is None:
        _importance_scorer = ImportanceScorer(config)
    return _importance_scorer
