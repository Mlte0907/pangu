"""世界模型实验工具 — worldmodel 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_worldmodel_forecast", "description": "基于当前状态预测未来情景"},
    {"name": "pangu_worldmodel_plan", "description": "为指定情景生成应对计划"},
    {"name": "pangu_worldmodel_match", "description": "将事件与预测情景匹配"},
    {"name": "pangu_worldmodel_stats", "description": "获取世界模型统计"},
]

HANDLERS: dict[str, callable] = {}