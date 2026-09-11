"""模块注册表 — 盘古工具暴露面的单一事实源

本模块定义 17 个 handler 模块的元数据（模块名 → 工具名集合 → 层级 → 默认开关），
作为白名单与可选模块清单的唯一事实源，消除 spec 4.4.2 禁止的"代码与文档各自硬编码导致漂移"。

设计决策（design 2.2）：
- 17 个 handler 模块天然作为启用单元
- 层级：core（默认暴露）/ optional（按需启用）/ experimental（实验隔离）
- 白名单 28 个工具横跨 6 个 core 模块，过滤必须做到工具名级而非模块级

约束：
- 白名单与模块映射漂移时启动期 fail-fast（见 _validate_whitelist_coverage）
- 实验工具按前缀从所有模块中提取，归入 experimental 层级
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── 实验工具前缀映射（design 4.3 / spec 6.2）──

EXPERIMENTAL_PREFIXES: dict[str, list[str]] = {
    "autonomous": ["autonomous"],
    "autopilot": ["autopilot"],
    "causal": ["causal"],
    "cognitive": ["cognitive"],
    "worldmodel": ["worldmodel"],
    "neural": ["neural"],
    "dream": ["dream"],
    "evolution": ["evolution"],
    "meta": ["meta"],
    "self_aware": ["self_aware", "self_reflect", "self_evolve"],
}


def _is_experimental(tool_name: str) -> bool:
    """判断工具名是否属于实验工具（前缀匹配）

    实验工具名格式：pangu_<group>_<action>，如 pangu_autonomous_run
    前缀匹配：检查 pangu_ 后的第一个单词是否在实验前缀列表中
    """
    if not tool_name.startswith("pangu_"):
        return False
    # 提取 pangu_ 后的第一个单词
    suffix = tool_name[6:]  # 去掉 "pangu_"
    first_word = suffix.split("_")[0] if "_" in suffix else suffix

    for prefixes in EXPERIMENTAL_PREFIXES.values():
        for prefix in prefixes:
            if first_word == prefix:
                return True
    return False


def _extract_experimental_from_tools(tools: list[dict]) -> list[str]:
    """从 TOOLS 列表中提取实验工具名"""
    return [t["name"] for t in tools if _is_experimental(t["name"])]


# ── 白名单清单（单一事实源，spec 6.1）──

CORE_WHITELIST: frozenset[str] = frozenset(
    {
        # 记忆 CRUD 与召回 (7)
        "pangu_add_memory",
        "pangu_recall",
        "pangu_search_memories",
        "pangu_hybrid_search",
        "pangu_delete_memory",
        "pangu_archive_memory",
        "pangu_wake_up",
        # 关联与统计 (5)
        "pangu_find_related",
        "pangu_stats",
        "pangu_search_stats",
        "pangu_system_health",
        "pangu_backup_stats",
        # 备份与迁移 (6)
        "pangu_backup",
        "pangu_restore_backup",
        "pangu_list_backups",
        "pangu_export",
        "pangu_import",
        "pangu_list_exports",
        # 项目与配置 (4)
        "pangu_project_list",
        "pangu_project_switch",
        "pangu_config_get",
        "pangu_config_set",
        # 内容采集 (2)
        "pangu_collect_file",
        "pangu_collect_dir",
        # 宫殿浏览 (2)
        "pangu_list_wings",
        "pangu_list_rooms",
        # 批量导入 (2)
        "pangu_batch_import",
        "pangu_batch_stats",
    }
)  # 共 28 个


# ── 模块注册表 ──


@dataclass(frozen=True)
class ModuleEntry:
    """Handler 模块元数据条目

    Attributes:
        name: 模块名（与 handlers/ 下文件名一致，不含 .py 后缀）
        level: 层级 — "core"（默认暴露）/ "optional"（按需启用）/ "experimental"（实验隔离）
        tool_names: 该模块的全部工具名集合（实验工具已被提取移除）
        default_enabled: 默认是否启用（core=True, optional=False, experimental=False）
    """

    name: str
    level: Literal["core", "optional", "experimental"]
    tool_names: frozenset[str]
    default_enabled: bool


def _load_module_tools(module_name: str) -> list[dict]:
    """动态加载指定模块的 TOOLS 列表

    注意：此函数仅在模块注册表初始化时调用一次，
    后续通过 MODULE_REGISTRY 缓存工具名集合，不做运行时热加载。
    """
    import sys
    from importlib import import_module

    # 从 pangu.server.handlers 包中导入
    pkg = "pangu.server.handlers"
    try:
        mod = import_module(f".{module_name}", package=pkg)
        return getattr(mod, "TOOLS", [])
    except Exception:
        # 模块不存在或加载失败，返回空列表
        return []


def _build_module_registry() -> list[ModuleEntry]:
    """构建模块注册表（17 个模块）

    构建逻辑：
    1. 加载每个模块的 TOOLS 列表
    2. 提取实验工具（前缀匹配），从原模块中移除
    3. 根据层级分类分配 default_enabled
    4. 白名单交叉校验（见 _validate_whitelist_coverage）
    """

    # 17 个 handler 模块及其层级分类（design 2.2 表）
    module_levels: dict[str, Literal["core", "optional", "experimental"]] = {
        # core（6 个）：默认暴露，含白名单工具
        "memory_ops": "core",
        "search": "core",
        "system": "core",
        "io_tools": "core",
        "palace": "core",
        "batch": "core",
        # optional（10 个）：长尾模块，默认关闭
        "multimodal": "optional",
        "timeline": "optional",
        "analytics": "optional",
        "quality": "optional",
        "consolidation": "optional",
        "embed": "optional",
        "knowledge_graph": "optional",
        "wiki": "optional",
        "llm_tools": "optional",
        "session": "optional",
        # experimental（1 个）：实验工具容器，默认关闭
        "advanced": "experimental",
    }

    registry: list[ModuleEntry] = []
    all_experimental: set[str] = set()

    for module_name, level in module_levels.items():
        tools = _load_module_tools(module_name)
        tool_names = {t["name"] for t in tools if "name" in t}

        # 提取实验工具（前缀匹配）
        # 注意：experimental 层级的模块不移除实验工具
        experimental_in_module = {name for name in tool_names if _is_experimental(name)}
        all_experimental.update(experimental_in_module)

        # 从原模块中移除实验工具（experimental 层级除外）
        if level == "experimental":
            core_tool_names = tool_names
        else:
            core_tool_names = tool_names - experimental_in_module

        default_enabled = level == "core"

        registry.append(
            ModuleEntry(
                name=module_name,
                level=level,
                tool_names=frozenset(core_tool_names),
                default_enabled=default_enabled,
            )
        )

    # 白名单交叉校验
    _validate_whitelist_coverage(registry)

    return registry


def _validate_whitelist_coverage(registry: list[ModuleEntry]) -> None:
    """白名单交叉校验：断言 CORE_WHITELIST 全部属于 core 模块的工具集

    若漂移则启动期 fail-fast，不静默通过。
    """
    core_tool_names: set[str] = set()
    for entry in registry:
        if entry.level == "core":
            core_tool_names.update(entry.tool_names)

    missing = CORE_WHITELIST - core_tool_names
    if missing:
        raise RuntimeError(
            f"白名单交叉校验失败：以下白名单工具不在 core 模块工具集中：{missing}。"
            f"请检查 MODULE_REGISTRY 中 core 模块的工具名映射。"
        )


# ── 模块级单例（服务装配期初始化）──

MODULE_REGISTRY: list[ModuleEntry] = _build_module_registry()


# ── 派生查询函数 ──


def core_tool_names() -> frozenset[str]:
    """返回所有 core 模块的工具名集合"""
    result: set[str] = set()
    for entry in MODULE_REGISTRY:
        if entry.level == "core":
            result.update(entry.tool_names)
    return frozenset(result)


def optional_module_names() -> list[str]:
    """返回所有 optional 模块的模块名列表"""
    return [entry.name for entry in MODULE_REGISTRY if entry.level == "optional"]


def experimental_group_names() -> list[str]:
    """返回所有实验组的组名列表（基于 EXPERIMENTAL_PREFIXES 的键）"""
    return list(EXPERIMENTAL_PREFIXES.keys())


def tools_of_module(module_name: str) -> frozenset[str]:
    """返回指定模块的工具名集合"""
    for entry in MODULE_REGISTRY:
        if entry.name == module_name:
            return entry.tool_names
    return frozenset()


def module_of_tool(tool_name: str) -> str | None:
    """返回指定工具所属的模块名，未找到返回 None"""
    for entry in MODULE_REGISTRY:
        if tool_name in entry.tool_names:
            return entry.name
    return None


def level_of_module(module_name: str) -> Literal["core", "optional", "experimental"] | None:
    """返回指定模块的层级，未找到返回 None"""
    for entry in MODULE_REGISTRY:
        if entry.name == module_name:
            return entry.level
    return None


def is_experimental_tool(tool_name: str) -> bool:
    """判断工具名是否属于实验工具"""
    return _is_experimental(tool_name)


def get_experimental_group(tool_name: str) -> str | None:
    """返回实验工具所属的组名，非实验工具返回 None"""
    if not tool_name.startswith("pangu_"):
        return None
    suffix = tool_name[6:]
    first_word = suffix.split("_")[0] if "_" in suffix else suffix

    for group_name, prefixes in EXPERIMENTAL_PREFIXES.items():
        for prefix in prefixes:
            if first_word == prefix:
                return group_name
    return None
