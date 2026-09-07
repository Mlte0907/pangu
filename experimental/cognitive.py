"""认知循环实验工具 — cognitive 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_cognitive_loop", "description": "运行一次认知循环（observe→think→evaluate→act）"},
    {"name": "pangu_cognitive_stats", "description": "获取认知循环统计"},
]

HANDLERS: dict[str, callable] = {}