"""梦境实验工具 — dream 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_dream_cycle", "description": "运行一次梦境固化周期"},
    {"name": "pangu_dream_stats", "description": "获取梦境固化统计"},
]

HANDLERS: dict[str, callable] = {}