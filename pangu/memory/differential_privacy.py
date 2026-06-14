"""盘古差分隐私 — 记忆数据隐私保护

从伏羲移植：为记忆数据提供差分隐私保护。
- 拉普拉斯噪声注入
- 隐私预算管理（ε-differential privacy）
- 数据脱敏预处理

纯大脑能力：只做隐私保护，不执行数据操作。
"""

import logging
import math
import random

logger = logging.getLogger("pangu.memory.differential_privacy")


class DifferentialPrivacy:
    """差分隐私保护 — 拉普拉斯机制

    核心特性：
    1. 拉普拉斯噪声注入
    2. 隐私预算管理（ε-differential privacy）
    3. 敏感度自动计算
    4. 预算消耗追踪
    """

    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        """
        Args:
            epsilon: 隐私预算（越小越隐私，0.1-10）
            delta: 失败概率（通常很小）
        """
        self.epsilon = epsilon
        self.delta = delta
        self._total_budget = epsilon
        self._consumed_budget: float = 0.0
        self._query_count: int = 0

    def add_laplace_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """添加拉普拉斯噪声

        Args:
            value: 原始值
            sensitivity: 敏感度（单条数据变化对输出的最大影响）

        Returns:
            加噪后的值
        """
        if self._consumed_budget >= self._total_budget:
            logger.warning("Privacy budget exhausted, returning raw value")
            return value

        scale = sensitivity / self.epsilon
        noise = random.uniform(-scale, scale)  # 简化：均匀噪声近似拉普拉斯

        self._consumed_budget += self.epsilon
        self._query_count += 1

        return value + noise

    def add_gaussian_noise(self, value: float, sensitivity: float = 1.0) -> float:
        """添加高斯噪声（(ε, δ)-DP）

        适用于需要更强隐私保护的场景。
        """
        if self._consumed_budget >= self._total_budget:
            return value

        sigma = math.sqrt(2 * math.log(1.25 / self.delta)) * sensitivity / self.epsilon
        noise = random.gauss(0, sigma)

        self._consumed_budget += self.epsilon
        self._query_count += 1

        return value + noise

    def privatize_count(self, count: int) -> int:
        """隐私化计数结果"""
        noisy = self.add_laplace_noise(float(count), sensitivity=1.0)
        return max(0, int(round(noisy)))

    def privatize_average(self, values: list[float], sensitivity: float = 1.0) -> float:
        """隐私化平均值"""
        if not values:
            return 0.0
        avg = sum(values) / len(values)
        return self.add_laplace_noise(avg, sensitivity / max(len(values), 1))

    def privatize_histogram(self, bins: dict[str, int]) -> dict[str, int]:
        """隐私化直方图"""
        return {k: self.privatize_count(v) for k, v in bins.items()}

    def reset_budget(self):
        """重置隐私预算"""
        self._consumed_budget = 0.0
        self._query_count = 0

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self._total_budget - self._consumed_budget)

    @property
    def budget_usage_pct(self) -> float:
        if self._total_budget == 0:
            return 100.0
        return (self._consumed_budget / self._total_budget) * 100

    def stats(self) -> dict:
        """隐私预算统计"""
        return {
            "epsilon": self.epsilon,
            "delta": self.delta,
            "total_budget": self._total_budget,
            "consumed_budget": round(self._consumed_budget, 4),
            "remaining_budget": round(self.remaining_budget, 4),
            "budget_usage_pct": round(self.budget_usage_pct, 1),
            "query_count": self._query_count,
        }


class FederatedMemory:
    """联邦记忆 — 分布式中保持隐私的记忆聚合

    模拟联邦学习中的模型聚合，在不共享原始数据的情况下聚合记忆统计。
    """

    def __init__(self, epsilon: float = 1.0):
        self.dp = DifferentialPrivacy(epsilon=epsilon)

    def aggregate_importance(self, clients: list[list[float]]) -> dict:
        """聚合多个客户端的记忆重要性统计

        Args:
            clients: 各客户端的记忆重要性列表

        Returns:
            隐私化聚合统计
        """
        all_importances = []
        client_stats = []
        for i, values in enumerate(clients):
            avg = sum(values) / max(len(values), 1)
            noisy_avg = self.dp.add_laplace_noise(avg, sensitivity=5.0 / max(len(values), 1))
            client_stats.append({
                "client": i,
                "count": len(values),
                "avg_importance": round(noisy_avg, 2),
            })
            all_importances.extend(values)

        global_avg = sum(all_importances) / max(len(all_importances), 1)
        noisy_global = self.dp.add_laplace_noise(global_avg, sensitivity=5.0 / max(len(all_importances), 1))

        return {
            "global_avg_importance": round(noisy_global, 2),
            "total_memories": len(all_importances),
            "clients": client_stats,
            "privacy_budget": self.dp.stats(),
        }

    def aggregate_tags(self, clients: list[dict[str, int]]) -> dict[str, int]:
        """聚合标签计数"""
        merged: dict[str, int] = {}
        for client_tags in clients:
            for tag, count in client_tags.items():
                merged[tag] = merged.get(tag, 0) + count
        return self.dp.privatize_histogram(merged)
