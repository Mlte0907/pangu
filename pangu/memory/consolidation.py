"""盘古记忆巩固引擎 — 类人记忆特征实现
============================================
实现类人记忆的三大核心特征：
1. 遗忘曲线 — 基于艾宾浩斯遗忘曲线的记忆衰减
2. 记忆巩固 — 通过重复访问强化记忆，间隔重复
3. 记忆压缩 — 将旧记忆自动压缩为精简摘要

这些机制使盘古的记忆系统具备类人特征：
- 不重要的记忆会随时间淡化
- 频繁访问的记忆会被强化
- 旧记忆自动浓缩为知识结晶
"""
import math
import time
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer


class ForgettingCurve:
    """艾宾浩斯遗忘曲线 — 模拟人类记忆衰减规律"""

    def __init__(self, decay_rate: float = 0.5):
        """
        Args:
            decay_rate: 衰减率，0.5 表示约 1 天后记忆强度减半
        """
        self.decay_rate = decay_rate

    def retention(self, elapsed_hours: float) -> float:
        """计算记忆保留率 R = e^(-decay_rate * hours / 24)

        Args:
            elapsed_hours: 自记忆创建以来经过的小时数

        Returns:
            0.0-1.0 之间的保留率
        """
        if elapsed_hours <= 0:
            return 1.0
        return math.exp(-self.decay_rate * elapsed_hours / 24.0)

    def effective_importance(self, drawer: Drawer, current_time: float = None) -> float:
        """计算记忆的有效重要性（考虑时间衰减）

        effective_importance = importance * retention * reinforcement_boost
        """
        if current_time is None:
            current_time = time.time()

        created = drawer.created_at
        if isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created)
                created = created_dt.timestamp()
            except (ValueError, TypeError):
                created = current_time - 3600

        elapsed_hours = (current_time - created) / 3600.0
        retention = self.retention(elapsed_hours)

        # 强化加成：每次访问提升 5%
        access_count = getattr(drawer, 'access_count', 0)
        reinforcement = 1.0 + access_count * 0.05

        return drawer.importance * retention * reinforcement


class MemoryConsolidator:
    """记忆巩固引擎 — 管理记忆的生命周期

    核心功能：
    1. 重要性衰减 — 随时间降低未访问记忆的重要性
    2. 记忆强化 — 通过访问提升记忆重要性
    3. 记忆压缩 — 将旧记忆压缩为摘要
    4. 遗忘判定 — 删除重要性过低的记忆
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.curve = ForgettingCurve(decay_rate=self.config.forgetting_curve_decay)
        self._access_tracker: dict[str, int] = {}  # 记忆 ID -> 访问次数
        self._last_consolidation: float = 0.0

    # ── 访问追踪 ──

    def record_access(self, drawer_id: str) -> None:
        """记录一次记忆访问"""
        self._access_tracker[drawer_id] = self._access_tracker.get(drawer_id, 0) + 1

    def get_access_count(self, drawer_id: str) -> int:
        """获取记忆访问次数"""
        return self._access_tracker.get(drawer_id, 0)

    # ── 重要性计算 ──

    def calculate_importance(self, drawer: Drawer) -> float:
        """计算记忆的综合重要性评分

        考虑因素：
        - 初始重要性 (1-5)
        - 时间衰减 (艾宾浩斯曲线)
        - 访问强化 (每次访问 +5%)
        - 标签密度 (标签越多越重要)
        - 内容长度 (内容越丰富越重要)
        """
        current_time = time.time()

        # 时间衰减
        created = drawer.created_at
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created).timestamp()
            except (ValueError, TypeError):
                created = current_time - 3600

        elapsed_hours = (current_time - created) / 3600.0
        retention = self.curve.retention(elapsed_hours)

        # 访问强化
        access_count = self._access_tracker.get(drawer.id, 0)
        reinforcement = 1.0 + min(access_count * 0.05, 1.0)  # 最多翻倍

        # 标签加成
        tag_bonus = 1.0 + min(len(drawer.tags) * 0.05, 0.3)  # 最多 +30%

        # 内容长度加成
        content_len = len(drawer.content)
        if content_len > 200:
            content_bonus = 1.1
        elif content_len > 50:
            content_bonus = 1.05
        else:
            content_bonus = 0.9  # 太短的内容略降权重

        return drawer.importance * retention * reinforcement * tag_bonus * content_bonus

    # ── 遗忘判定 ──

    def should_forget(self, drawer: Drawer) -> bool:
        """判断一条记忆是否应该被遗忘"""
        effective = self.calculate_importance(drawer)
        return effective < self.config.min_importance_threshold

    def find_forgotten(self, drawers: list[Drawer]) -> list[Drawer]:
        """找出所有应该被遗忘的记忆"""
        return [d for d in drawers if self.should_forget(d)]

    # ── 压缩判定 ──

    def should_compress(self, drawers: list[Drawer]) -> bool:
        """判断是否需要压缩记忆"""
        return len(drawers) > self.config.compression_threshold

    def find_compressible(self, drawers: list[Drawer]) -> list[Drawer]:
        """找出可以压缩的旧记忆（低重要性、长时间未访问）"""
        if not drawers:
            return []

        # 按有效重要性排序
        scored = [(self.calculate_importance(d), d) for d in drawers]
        scored.sort(key=lambda x: x[0])

        # 返回最不重要的 30%
        cutoff = max(1, len(drawers) // 3)
        return [d for _, d in scored[:cutoff]]

    def compress_memory(self, drawer: Drawer) -> str:
        """将长记忆压缩为精简摘要

        策略：
        - >500字 → 保留前100字 + 关键句提取
        - >200字 → 保留前80字
        - 其他 → 保留前50字
        """
        content = drawer.content
        if len(content) <= 200:
            return content[:50] + ("..." if len(content) > 50 else "")

        # 尝试提取关键句（包含标签词或重要性关键词的句子）
        sentences = content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
        key_sentences = []
        important_words = set(drawer.tags) | {"重要", "关键", "决定", "结论", "注意", "总结"}
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if any(w in s for w in important_words):
                key_sentences.append(s)

        if key_sentences:
            summary = "。".join(key_sentences[:3])
            if len(summary) > 150:
                summary = summary[:150] + "..."
            return summary

        # 降级：保留前100字
        return content[:100] + "..."

    # ── 巩固检查 ──

    def needs_consolidation(self) -> bool:
        """检查是否需要进行记忆巩固"""
        if not self.config.consolidation_enabled:
            return False

        now = time.time()
        interval = self.config.consolidation_interval_hours * 3600
        return (now - self._last_consolidation) > interval

    def mark_consolidated(self) -> None:
        """标记已完成巩固"""
        self._last_consolidation = time.time()

    # ── 间隔重复 ──

    @staticmethod
    def next_review_interval(access_count: int) -> float:
        """计算下次复习间隔（小时间隔）

        基于间隔重复算法：
        - 第 0 次（未访问）: 24 小时
        - 第 1 次: 6 小时
        - 第 2 次: 24 小时
        - 第 3 次: 3 天
        - 第 4 次: 7 天
        - 第 5 次+: 30 天
        """
        intervals = [24, 6, 24, 72, 168, 720]
        if access_count < len(intervals):
            return intervals[access_count]
        return intervals[-1] * (1.5 ** (access_count - len(intervals) + 1))

    def needs_review(self, drawer: Drawer) -> bool:
        """判断记忆是否需要复习"""
        access_count = self._access_tracker.get(drawer.id, 0)
        interval_hours = self.next_review_interval(access_count)

        created = drawer.created_at
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created).timestamp()
            except (ValueError, TypeError):
                return False

        elapsed_hours = (time.time() - created) / 3600.0
        return elapsed_hours > interval_hours

    def find_due_reviews(self, drawers: list[Drawer]) -> list[Drawer]:
        """找出需要复习的记忆"""
        return [d for d in drawers if self.needs_review(d)]

    # ── 统计 ──

    def stats(self, drawers: list[Drawer]) -> dict:
        """巩固统计信息"""
        forgotten = self.find_forgotten(drawers)
        due_reviews = self.find_due_reviews(drawers)

        effective_importances = [self.calculate_importance(d) for d in drawers]
        avg_importance = sum(effective_importances) / max(len(effective_importances), 1)

        return {
            "total_memories": len(drawers),
            "forgotten_count": len(forgotten),
            "due_review_count": len(due_reviews),
            "average_effective_importance": round(avg_importance, 2),
            "needs_compression": self.should_compress(drawers),
            "total_accesses": sum(self._access_tracker.values()),
            "last_consolidation": datetime.fromtimestamp(self._last_consolidation).isoformat() if self._last_consolidation else None,
        }
