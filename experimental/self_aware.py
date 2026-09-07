"""自我感知实验工具 — self_aware 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_persona_identity", "description": "获取系统身份和人格特质"},
    {"name": "pangu_persona_values", "description": "获取系统价值观和原则"},
    {"name": "pangu_persona_health", "description": "系统综合健康度检查"},
]

HANDLERS: dict[str, callable] = {}