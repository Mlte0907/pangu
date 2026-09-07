"""因果发现实验工具 — causal 组"""

from __future__ import annotations

TOOLS = [
    {"name": "pangu_find_causal_links", "description": "发现记忆间的因果关联"},
]

HANDLERS: dict[str, callable] = {}