"""暴露面过滤器 — MCP/REST 双通道单一拦截点

设计决策（design 2.1）：
- 在 handler 聚合层输出与 McpServer 消费之间插入单一过滤拦截点
- MCP 与 REST 两条通道同时生效，不重复实现
- 过滤器从 config 单例读取 exposure 段，服务装配期一次性计算暴露集合，运行时不做热加载

约束：
- 过滤额外耗时 ≤ 10ms（spec 4.1.2）
- 白名单 28 个工具必须全部保留（spec 5.1.1.1）
- 未暴露工具调用返回 code=1002 结构化错误（spec 5.1.3 场景 3）
"""

from __future__ import annotations

import json
from typing import Any

from pangu.core.config import PanguConfig
from pangu.server.module_registry import (
    CORE_WHITELIST,
    MODULE_REGISTRY,
    ModuleEntry,
    get_experimental_group,
)


class ExposureFilter:
    """工具暴露面过滤器

    在 MCP tools/list 与 tools/call 之间插入单一拦截点，
    使 MCP 与 REST 两条通道同时生效。
    """

    def __init__(self, config: PanguConfig):
        """初始化过滤器，计算暴露集合

        Args:
            config: PanguConfig 实例，从中读取 exposure 配置
        """
        self._config = config
        self._exposed_set: set[str] = self._compute_exposed_set(config)

    def _compute_exposed_set(self, config: PanguConfig) -> set[str]:
        """计算暴露集合

        暴露集合 = 白名单 ∪ 已启用可选模块工具集 ∪ 已启用实验组工具集

        复杂度：O(|白名单| + |已启用模块工具| + |已启用实验工具|) ≤ O(423)
        """
        exposed: set[str] = set(CORE_WHITELIST)

        exposure = config.exposure
        enabled_optional = exposure.enabled_optional_modules
        enabled_experiments = exposure.enabled_experiments

        # 添加已启用可选模块的工具
        for entry in MODULE_REGISTRY:
            if entry.level == "optional" and entry.name in enabled_optional:
                exposed.update(entry.tool_names)

        # 添加已启用实验组的工具
        # 实验工具在 module_registry 中已被提取归入 experimental 层级
        # 这里通过 EXPERIMENTAL_PREFIXES 从所有模块中重新提取
        if enabled_experiments:
            from pangu.server.module_registry import EXPERIMENTAL_PREFIXES

            for group_name in enabled_experiments:
                prefixes = EXPERIMENTAL_PREFIXES.get(group_name, [])
                if not prefixes:
                    continue
                # 从所有模块中匹配实验工具
                for entry in MODULE_REGISTRY:
                    for tool_name in entry.tool_names:
                        for prefix in prefixes:
                            if tool_name.startswith(prefix):
                                exposed.add(tool_name)
                                break

        return exposed

    def apply(self, tools: list[dict]) -> list[dict]:
        """过滤 tools/list 输出

        Args:
            tools: 完整的 TOOLS 列表（423 个）

        Returns:
            过滤后的工具列表，仅包含暴露集合中的工具

        复杂度：O(|TOOLS|) = O(423)，线性扫描，耗时 < 1ms
        """
        return [t for t in tools if t.get("name") in self._exposed_set]

    def check_callable(self, tool_name: str) -> tuple[bool, str | None]:
        """tools/call 前置校验

        Args:
            tool_name: 工具名

        Returns:
            (True, None) 如果工具可调用
            (False, error_json) 如果工具不可调用，error_json 含 code=1002 与可操作错误信息
        """
        if tool_name in self._exposed_set:
            return True, None

        # 判断被过滤原因，给出可操作错误信息
        error_msg = self._build_error_message(tool_name)
        error_json = json.dumps({"code": 1002, "error": error_msg}, ensure_ascii=False)
        return False, error_json

    def _build_error_message(self, tool_name: str) -> str:
        """构建错误消息

        根据工具是否存在、属于哪个层级，给出可操作错误信息。
        """
        # 查找工具所属模块
        for entry in MODULE_REGISTRY:
            if tool_name in entry.tool_names:
                if entry.level == "optional":
                    return (
                        f"模块 {entry.name} 未启用，"
                        f"请在配置 exposure.enabled_optional_modules 中添加 '{entry.name}'"
                    )
                elif entry.level == "experimental":
                    group = get_experimental_group(tool_name)
                    return (
                        f"实验模块 {group} 未启用，"
                        f"请在配置 exposure.enabled_experiments 中添加 '{group}'"
                    )
                else:
                    return f"工具 {tool_name} 不在当前暴露面中"

        # 工具不在注册表中，可能是实验工具（前缀匹配）
        from pangu.server.module_registry import EXPERIMENTAL_PREFIXES

        for group_name, prefixes in EXPERIMENTAL_PREFIXES.items():
            for prefix in prefixes:
                if tool_name.startswith(prefix):
                    return (
                        f"实验模块 {group_name} 未启用，"
                        f"请在配置 exposure.enabled_experiments 中添加 '{group_name}'"
                    )

        # 工具不存在
        return f"未知工具: {tool_name}"

    @property
    def exposed_set(self) -> frozenset[str]:
        """返回当前暴露集合（只读）"""
        return frozenset(self._exposed_set)

    @property
    def exposed_count(self) -> int:
        """返回当前暴露工具数量"""
        return len(self._exposed_set)


# ── 模块级单例（服务装配期初始化）──

_exposure_filter: ExposureFilter | None = None


def get_exposure_filter(config: PanguConfig) -> ExposureFilter:
    """获取暴露面过滤器单例

    首次调用时初始化，后续调用返回缓存实例。
    注意：运行时不做热加载，与既有配置语义一致。
    """
    global _exposure_filter
    if _exposure_filter is None:
        _exposure_filter = ExposureFilter(config)
    return _exposure_filter


def reset_exposure_filter() -> None:
    """重置暴露面过滤器（测试用）"""
    global _exposure_filter
    _exposure_filter = None


# 向后兼容：模块级单例
exposure_filter: ExposureFilter | None = None


def init_exposure_filter(config: PanguConfig) -> None:
    """初始化模块级单例（服务启动时调用）

    Args:
        config: PanguConfig 实例
    """
    global exposure_filter
    exposure_filter = ExposureFilter(config)