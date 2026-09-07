"""元认知实验工具 — meta 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_metacognition_monitor", "description": "系统级健康监测"},
    {"name": "pangu_metacognition_reconfig", "description": "自重构检测"},
    {"name": "pangu_meta_observe", "description": "记录性能观察"},
    {"name": "pangu_meta_recommend", "description": "推荐最优策略"},
    {"name": "pangu_meta_tune", "description": "自动调优参数"},
    {"name": "pangu_meta_insights", "description": "获取学习洞察"},
    {"name": "pangu_meta_stats", "description": "元学习统计"},
]

HANDLERS: dict[str, callable] = {}