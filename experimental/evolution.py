"""进化实验工具 — evolution 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_evolution_plan", "description": "生成进化计划"},
    {"name": "pangu_evolution_stats", "description": "获取进化统计"},
]

HANDLERS: dict[str, callable] = {}