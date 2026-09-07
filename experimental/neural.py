"""神经网络实验工具 — neural 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_neural_stats", "description": "获取海马体-新皮层双系统统计"},
    {"name": "pangu_neural_sleep", "description": "触发神经睡眠固化"},
    {"name": "pangu_neural_spreading", "description": "基于种子记忆执行扩散激活"},
    {"name": "pangu_neural_inhibition", "description": "对一组记忆执行竞争抑制"},
    {"name": "pangu_neural_decay", "description": "对所有记忆应用个性化衰减"},
]

HANDLERS: dict[str, callable] = {}