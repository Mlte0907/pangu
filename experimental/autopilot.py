"""自动驾驶实验工具 — autopilot 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_autopilot_status", "description": "获取自动驾驶状态"},
    {"name": "pangu_autopilot_enable", "description": "启用自动驾驶"},
    {"name": "pangu_autopilot_disable", "description": "禁用自动驾驶"},
]

HANDLERS: dict[str, callable] = {}