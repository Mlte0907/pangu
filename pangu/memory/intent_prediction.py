"""盘古用户意图预测 — 时序意图建模 / 任务链追踪 / 上下文感知建议

从伏羲移植并适配盘古架构：
1. 从 Drawer 行为序列推断当前意图
2. 跟踪多步骤任务进度
3. 基于上下文生成智能建议
"""

import logging
from datetime import datetime, timedelta

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.intent_prediction")

# 意图模式 → 关键词映射
_INTENT_PATTERNS = {
    "information_seeking": ["search", "find", "query", "recall", "look", "find"],
    "content_creation": ["write", "edit", "create", "add", "draft", "compose"],
    "consuming_content": ["read", "review", "browse", "list", "get"],
    "analysis": ["analyze", "compare", "evaluate", "detect", "discover"],
    "organization": ["organize", "cluster", "merge", "compress", "clean"],
}


class IntentPredictor:
    """用户意图预测器 — 时序意图建模、任务链追踪、上下文感知建议"""

    def __init__(self, config: PanguConfig | None = None):
        self.config = config
        self._action_history: list[dict] = []
        self._last_prediction: dict = {}
        self._predictions_count: int = 0

    def predict_intent(self, drawers: list[Drawer], context: str = "") -> dict:
        """从记忆行为序列推断当前意图

        Args:
            drawers: 记忆列表（按时间排序）
            context: 额外上下文文本
        """
        model = {"intent": "unknown", "confidence": 0.0, "evidence": [], "context": context}

        if not drawers:
            return model

        recent = drawers[-20:]
        content_lower = " ".join(d.content.lower() for d in recent)
        tag_lower = " ".join(t.lower() for d in recent for t in d.tags)

        best_intent = "unknown"
        best_score = 0.0

        for intent, keywords in _INTENT_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in content_lower or kw in tag_lower)
            if score > best_score:
                best_score = score
                best_intent = intent

        if best_score > 0:
            model["intent"] = best_intent
            model["confidence"] = min(0.9, 0.3 + best_score * 0.1)
            model["evidence"] = [d.content[:60] for d in recent[-3:]]

        self._last_prediction = model
        self._predictions_count += 1
        return model

    def track_task_chain(self, drawers: list[Drawer]) -> dict:
        """任务链追踪 — 跟踪多步骤任务的进度

        Args:
            drawers: 记忆列表
        """
        tracker: dict = {"active_tasks": [], "completed_steps": 0, "total_steps": 0}

        task_keywords = ["任务", "task", "todo", "待办", "计划", "plan"]
        tasks = [
            d for d in drawers
            if any(kw in d.content.lower() or kw in " ".join(t.lower() for t in d.tags)
                   for kw in task_keywords)
        ]

        for task in tasks[-5:]:
            tracker["active_tasks"].append({
                "id": task.id[:8],
                "preview": task.content[:50],
                "wing": task.wing,
                "importance": task.importance,
                "created_at": task.created_at,
            })

        total = len(tasks)
        completed = min(total, len(drawers) // 3)
        tracker["completed_steps"] = completed
        tracker["total_steps"] = total + completed

        return tracker

    def suggest_next(self, drawers: list[Drawer], intent_model: dict,
                     task_chain: dict) -> list[dict]:
        """上下文感知建议 — 基于当前上下文生成智能建议

        Args:
            drawers: 记忆列表
            intent_model: predict_intent 返回的意图模型
            task_chain: track_task_chain 返回的任务链
        """
        suggestions = []

        intent = intent_model.get("intent", "unknown")
        if intent == "information_seeking":
            suggestions.append({
                "type": "next_action",
                "content": "考虑深入探索相关主题",
                "confidence": 0.6,
            })
        elif intent == "content_creation":
            suggestions.append({
                "type": "next_action",
                "content": "建议保存当前进度并记录灵感",
                "confidence": 0.5,
            })
        elif intent == "analysis":
            suggestions.append({
                "type": "next_action",
                "content": "可以运行知识综合发现更多洞察",
                "confidence": 0.55,
            })

        active = task_chain.get("active_tasks", [])
        if len(active) > 3:
            suggestions.append({
                "type": "task_overload",
                "content": "当前有较多进行中任务，建议专注完成其一",
                "confidence": 0.7,
            })

        if not suggestions:
            suggestions.append({
                "type": "general",
                "content": "没有明显的行为模式，建议浏览最近记忆",
                "confidence": 0.3,
            })

        return suggestions

    def stats(self) -> dict:
        return {
            "predictions_count": self._predictions_count,
            "last_prediction": self._last_prediction,
            "history_size": len(self._action_history),
        }


_intent_predictor: IntentPredictor | None = None


def get_intent_predictor(config: PanguConfig | None = None) -> IntentPredictor:
    global _intent_predictor
    if _intent_predictor is None:
        _intent_predictor = IntentPredictor(config)
    return _intent_predictor
