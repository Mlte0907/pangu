"""实验模块目录 — 承载"类人大脑"愿景的研究性功能

设计决策（design 2.3）：
- 实验工具物理隔离于核心引擎，核心不 import experimental
- 默认关闭，显式开关启用时动态装配
- 实验工具经暴露面过滤器的第三层暴露

约束：
- 实验工具前缀：autonomous/autopilot/causal/cognitive/worldmodel/neural/dream/evolution/meta/self_*
- 核心包对实验目录不存在反向依赖（见 test_core_not_import_experimental）
"""

from __future__ import annotations

from typing import Any

# ── 实验组定义（与 module_registry.EXPERIMENTAL_PREFIXES 一致）──

EXPERIMENTAL_GROUPS: dict[str, list[str]] = {
    "cognitive": [],
    "worldmodel": [],
    "causal": [],
    "autonomous": [],
    "autopilot": [],
    "neural": [],
    "dream": [],
    "evolution": [],
    "meta": [],
    "self_aware": [],
}

# ── 动态加载的 TOOLS/HANDLERS（仅在启用时填充）──

EXPERIMENTAL_TOOLS: list[dict] = []
EXPERIMENTAL_HANDLERS: dict[str, Any] = {}


def load_group(group_name: str) -> None:
    """动态加载某实验组的 TOOLS/HANDLERS

    Args:
        group_name: 实验组名，如 "cognitive"、"worldmodel"

    Raises:
        ImportError: 实验组模块不存在
    """
    global EXPERIMENTAL_TOOLS, EXPERIMENTAL_HANDLERS

    # 映射组名到模块名
    module_map = {
        "cognitive": "cognitive",
        "worldmodel": "worldmodel",
        "causal": "causal",
        "autonomous": "autonomous",
        "autopilot": "autopilot",
        "neural": "neural",
        "dream": "dream",
        "evolution": "evolution",
        "meta": "meta",
        "self_aware": "self_aware",
    }

    module_name = module_map.get(group_name)
    if not module_name:
        raise ImportError(f"未知实验组: {group_name}")

    try:
        mod = __import__(
            f".{module_name}",
            globals(),
            locals(),
            fromlist=["TOOLS", "HANDLERS"],
            package="experimental",
        )
        EXPERIMENTAL_TOOLS.extend(getattr(mod, "TOOLS", []))
        EXPERIMENTAL_HANDLERS.update(getattr(mod, "HANDLERS", {}))
    except Exception as e:
        raise ImportError(f"加载实验组 {group_name} 失败: {e}")


def unload_group(group_name: str) -> None:
    """卸载某实验组的 TOOLS/HANDLERS

    注意：此操作不可逆，仅用于测试清理。
    """
    global EXPERIMENTAL_TOOLS, EXPERIMENTAL_HANDLERS

    # 重新加载实验组定义（简化处理）
    EXPERIMENTAL_TOOLS = []
    EXPERIMENTAL_HANDLERS = {}


def is_group_loaded(group_name: str) -> bool:
    """检查某实验组是否已加载"""
    return group_name in EXPERIMENTAL_GROUPS and len(EXPERIMENTAL_TOOLS) > 0