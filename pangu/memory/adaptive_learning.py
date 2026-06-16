"""盘古自适应学习系统 — 从用户行为中学习

核心功能：
1. 搜索模式学习：记录用户搜索的查询、点击的结果
2. 记忆访问学习：记录哪些记忆被频繁访问
3. 反馈学习：从用户反馈（点赞/踩/评论）中学习
4. 权重自适应：根据学习结果动态调整评分权重
5. 预测优化：基于历史行为优化预测模型
"""
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.adaptive_learning")


@dataclass
class LearningEvent:
    """学习事件"""
    event_type: str  # search / access / feedback / prediction
    query: str = ""
    memory_id: str = ""
    score: float = 0.0
    feedback: str = ""  # positive / negative
    timestamp: float = field(default_factory=time.time)


class AdaptiveLearningSystem:
    """自适应学习系统 — 从用户行为中学习

    学习内容：
    1. 搜索模式：哪些查询产生高点击率
    2. 记忆访问：哪些记忆被频繁访问
    3. 反馈信号：哪些记忆被点赞/踩
    4. 权重调整：根据学习结果优化评分权重
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._events: list[LearningEvent] = []
        self._search_patterns: dict[str, dict] = {}  # query -> {count, avg_score, last_used}
        self._memory_access: dict[str, dict] = {}  # memory_id -> {count, last_access, avg_score}
        self._weight_adjustments: dict[str, float] = {}  # factor -> adjustment
        self._learning_rate = 0.1
        self._max_events = 1000

    def record_search(self, query: str, results: list[dict], clicked_ids: list[str] = None) -> None:
        """记录搜索事件"""
        event = LearningEvent(
            event_type="search",
            query=query,
            score=len(results) / 10.0 if results else 0.0,
        )
        self._events.append(event)
        self._trim_events()

        # 更新搜索模式
        if query not in self._search_patterns:
            self._search_patterns[query] = {"count": 0, "total_score": 0.0, "last_used": 0.0}

        pattern = self._search_patterns[query]
        pattern["count"] += 1
        pattern["total_score"] += len(results)
        pattern["last_used"] = time.time()

        # 记录点击的记忆
        if clicked_ids:
            for mid in clicked_ids:
                self._record_memory_access(mid, "click")

    def record_memory_access(self, memory_id: str, access_type: str = "view") -> None:
        """记录记忆访问"""
        self._record_memory_access(memory_id, access_type)

    def _record_memory_access(self, memory_id: str, access_type: str) -> None:
        """内部记录记忆访问"""
        if memory_id not in self._memory_access:
            self._memory_access[memory_id] = {"count": 0, "last_access": 0.0, "total_score": 0.0}

        access = self._memory_access[memory_id]
        access["count"] += 1
        access["last_access"] = time.time()
        access["total_score"] += 1.0 if access_type == "click" else 0.5

    def record_feedback(self, memory_id: str, feedback: str) -> None:
        """记录用户反馈"""
        event = LearningEvent(
            event_type="feedback",
            memory_id=memory_id,
            feedback=feedback,
        )
        self._events.append(event)
        self._trim_events()

        # 更新记忆访问
        self._record_memory_access(memory_id, "feedback")

        # 调整权重
        if feedback == "positive":
            self._adjust_weights(memory_id, 0.05)
        elif feedback == "negative":
            self._adjust_weights(memory_id, -0.05)

    def _adjust_weights(self, memory_id: str, delta: float) -> None:
        """调整评分权重"""
        # 简单的在线学习：根据反馈调整相关因子的权重
        self._weight_adjustments["importance"] = self._weight_adjustments.get("importance", 0.0) + delta
        self._weight_adjustments["frequency"] = self._weight_adjustments.get("frequency", 0.0) + delta * 0.5

    def predict_relevance(self, query: str, memory_id: str, context: str = "") -> float:
        """预测记忆与查询的相关性（支持上下文感知）"""
        score = 0.5  # 基础分数

        # 搜索模式加成
        if query in self._search_patterns:
            pattern = self._search_patterns[query]
            if pattern["count"] > 0:
                avg_score = pattern["total_score"] / pattern["count"]
                score += min(avg_score / 10.0, 0.3)

        # 记忆访问加成
        if memory_id in self._memory_access:
            access = self._memory_access[memory_id]
            if access["count"] > 0:
                score += min(access["count"] / 100.0, 0.2)

        # 上下文感知加成
        if context:
            # 检查查询词是否在上下文中出现
            query_words = set(query.lower().split())
            context_words = set(context.lower().split())
            overlap = len(query_words & context_words)
            if overlap > 0:
                score += min(overlap * 0.05, 0.15)

        return min(1.0, max(0.0, score))

    def detect_patterns(self) -> list[dict]:
        """检测用户行为模式"""
        patterns = []

        # 检测重复查询模式
        if len(self._search_patterns) > 5:
            sorted_queries = sorted(self._search_patterns.items(), key=lambda x: x[1]["count"], reverse=True)
            top_queries = sorted_queries[:3]
            if top_queries[0][1]["count"] > 5:
                patterns.append({
                    "type": "frequent_query",
                    "query": top_queries[0][0],
                    "count": top_queries[0][1]["count"],
                    "suggestion": f"用户经常搜索 \"{top_queries[0][0]}\"，建议将其设为快捷查询",
                })

        # 检测记忆访问模式
        if len(self._memory_access) > 10:
            sorted_memories = sorted(self._memory_access.items(), key=lambda x: x[1]["count"], reverse=True)
            top_memory = sorted_memories[0]
            if top_memory[1]["count"] > 10:
                patterns.append({
                    "type": "frequent_memory",
                    "memory_id": top_memory[0],
                    "count": top_memory[1]["count"],
                    "suggestion": f"记忆 {top_memory[0][:8]} 被频繁访问，建议提升重要性",
                })

        return patterns

    def get_popular_queries(self, limit: int = 10) -> list[dict]:
        """获取热门查询"""
        sorted_queries = sorted(
            self._search_patterns.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        return [
            {"query": q, "count": p["count"], "avg_score": round(p["total_score"] / max(p["count"], 1), 2)}
            for q, p in sorted_queries[:limit]
        ]

    def get_frequent_memories(self, limit: int = 10) -> list[dict]:
        """获取频繁访问的记忆"""
        sorted_memories = sorted(
            self._memory_access.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        return [
            {"memory_id": mid, "count": a["count"], "last_access": datetime.fromtimestamp(a["last_access"]).isoformat()}
            for mid, a in sorted_memories[:limit]
        ]

    def get_learning_stats(self) -> dict:
        """获取学习统计"""
        return {
            "total_events": len(self._events),
            "unique_queries": len(self._search_patterns),
            "unique_memories": len(self._memory_access),
            "weight_adjustments": dict(self._weight_adjustments),
        }

    def _trim_events(self) -> None:
        """修剪事件列表"""
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]


# 全局单例
_adaptive_learning: AdaptiveLearningSystem | None = None


def get_adaptive_learning(config: PanguConfig = None) -> AdaptiveLearningSystem:
    """获取全局自适应学习系统"""
    global _adaptive_learning
    if _adaptive_learning is None:
        _adaptive_learning = AdaptiveLearningSystem(config)
    return _adaptive_learning
