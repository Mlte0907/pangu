"""盘古预测性记忆 — 基于上下文预加载相关记忆

核心功能：
1. 上下文感知：分析当前对话上下文
2. 记忆预测：预测 Agent 可能需要的记忆
3. 主动推送：在 Agent 询问前预加载相关记忆
4. 学习优化：根据使用反馈优化预测模型
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.proactive")


@dataclass
class ProactiveMemory:
    """主动推送的记忆"""

    memory_id: str
    content: str
    relevance_score: float
    reason: str  # 推荐原因
    wing: str = ""
    tags: list[str] = field(default_factory=list)


class ProactiveEngine:
    """预测性记忆引擎 — 基于上下文预加载相关记忆"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._context_history: list[str] = []  # 上下文历史
        self._prediction_stats: dict = {"hits": 0, "misses": 0}
        self._context_window: int = 10  # 上下文窗口大小

    def get_context(self) -> str:
        """获取当前上下文（从 working_memory）"""
        try:
            from pangu.memory.working_memory import get_working_memory

            wm = get_working_memory()
            # 从工作记忆中提取上下文
            context_items = []
            for item in wm._buffer[-5:]:  # 最近 5 条
                if hasattr(item, "content"):
                    context_items.append(item.content)
            return " ".join(context_items)
        except Exception:
            return " ".join(self._context_history[-5:])

    def update_context(self, text: str) -> None:
        """更新上下文历史"""
        self._context_history.append(text)
        if len(self._context_history) > self._context_window:
            self._context_history = self._context_history[-self._context_window :]

    def predict(self, context: str, drawers: list[Drawer], limit: int = 5) -> list[ProactiveMemory]:
        """基于上下文预测相关记忆

        Args:
            context: 当前上下文（对话内容、任务描述等）
            drawers: 所有记忆列表
            limit: 推荐数量

        Returns:
            推荐的记忆列表
        """
        if not context or not drawers:
            return []

        # 更新上下文历史
        self._context_history.append(context)
        if len(self._context_history) > 10:
            self._context_history.pop(0)

        # 提取关键词
        keywords = self._extract_keywords(context)

        # 计算每条记忆的相关性
        scored = []
        for d in drawers:
            score = self._calculate_relevance(d, keywords, context)
            if score > 0.1:
                scored.append((d, score))

        # 按相关性排序
        scored.sort(key=lambda x: -x[1])

        # 构建结果
        results = []
        for drawer, score in scored[:limit]:
            reason = self._generate_reason(drawer, keywords, context)
            results.append(
                ProactiveMemory(
                    memory_id=drawer.id,
                    content=drawer.content[:100],
                    relevance_score=round(score, 3),
                    reason=reason,
                    wing=drawer.wing,
                    tags=drawer.tags,
                )
            )

        return results

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        # 简单分词
        words = text.lower().split()
        # 过滤停用词
        stopwords = {
            "的",
            "了",
            "是",
            "在",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
        }
        keywords = [w for w in words if len(w) >= 2 and w not in stopwords]
        return keywords[:10]

    def _calculate_relevance(self, drawer: Drawer, keywords: list[str], context: str) -> float:
        """计算记忆与上下文的相关性"""
        score = 0.0
        content_lower = drawer.content.lower()

        # 关键词匹配
        for kw in keywords:
            if kw in content_lower:
                score += 0.3

        # 标签匹配
        for tag in drawer.tags:
            if tag.lower() in context.lower():
                score += 0.2

        # 内容相似度（简单字符重叠）
        context_chars = set(context.lower())
        content_chars = set(content_lower)
        if context_chars and content_chars:
            overlap = len(context_chars & content_chars) / max(len(context_chars), 1)
            score += overlap * 0.2

        # 重要性加成
        score += (drawer.importance / 5.0) * 0.1

        # 时间衰减（新记忆优先）
        try:
            days_old = (datetime.now() - datetime.fromisoformat(drawer.created_at)).total_seconds() / 86400
            recency = max(0.0, 1.0 - days_old / 30)
            score += recency * 0.2
        except Exception:
            pass

        return min(score, 1.0)

    def _generate_reason(self, drawer: Drawer, keywords: list[str], context: str) -> str:
        """生成推荐原因"""
        matched_keywords = [kw for kw in keywords if kw in drawer.content.lower()]
        if matched_keywords:
            return f"包含关键词: {', '.join(matched_keywords[:3])}"

        matched_tags = [t for t in drawer.tags if t.lower() in context.lower()]
        if matched_tags:
            return f"匹配标签: {', '.join(matched_tags[:3])}"

        return "与当前上下文相关"

    def get_stats(self) -> dict:
        """获取预测统计"""
        total = self._prediction_stats["hits"] + self._prediction_stats["misses"]
        hit_rate = self._prediction_stats["hits"] / total if total > 0 else 0.0
        return {
            "hits": self._prediction_stats["hits"],
            "misses": self._prediction_stats["misses"],
            "hit_rate": round(hit_rate, 3),
            "context_history_size": len(self._context_history),
        }


# 全局单例
_proactive_engine: ProactiveEngine | None = None


def get_proactive_engine(config: PanguConfig = None) -> ProactiveEngine:
    """获取全局预测性记忆引擎"""
    global _proactive_engine
    if _proactive_engine is None:
        _proactive_engine = ProactiveEngine(config)
    return _proactive_engine
