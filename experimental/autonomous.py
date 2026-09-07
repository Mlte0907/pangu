"""自主循环实验工具 — autonomous 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_autonomous_analyze", "description": "分析任务复杂度并推荐能力"},
    {"name": "pangu_autonomous_tick", "description": "检查是否需要运行自主维护周期"},
    {"name": "pangu_autonomous_run", "description": "运行一次自主记忆管理周期"},
    {"name": "pangu_autonomous_status", "description": "查看自主引擎状态和任务调度"},
]

HANDLERS: dict[str, callable] = {}