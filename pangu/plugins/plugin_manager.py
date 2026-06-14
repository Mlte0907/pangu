"""盘古插件管理器 — 插件化架构核心
====================================
管理插件生命周期、支持自定义 Mining/存储/分析器插件、
插件注册/卸载/配置、插件钩子系统。

插件类型：
- MiningPlugin: 从外部数据源挖掘记忆
- StoragePlugin: 自定义记忆存储后端
- AnalyzerPlugin: 记忆分析与洞察
"""
import importlib
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import HookPoint, Plugin, PluginContext, PluginInfo

logger = logging.getLogger("pangu.plugins.manager")


# ── 插件类型枚举 ──

class PluginType(str, Enum):
    """插件类型"""
    MINING = "mining"
    STORAGE = "storage"
    ANALYZER = "analyzer"
    HOOK = "hook"


# ── 插件基类 ──

class MiningPlugin(Plugin, ABC):
    """挖掘插件基类 — 从外部数据源挖掘记忆"""

    def __init__(self, info: PluginInfo, config: dict = None):
        super().__init__(info)
        self.config = config or {}

    @abstractmethod
    async def mine(self, source: str, **kwargs) -> list[dict]:
        """执行挖掘

        Args:
            source: 数据源路径或 URL
            **kwargs: 额外参数

        Returns:
            挖掘结果列表，每项为 {content, wing, room, tags, importance}
        """
        ...

    async def on_pre_mine(self, ctx: PluginContext) -> None:
        """挖掘前钩子"""
        pass

    async def on_post_mine(self, ctx: PluginContext) -> None:
        """挖掘后钩子"""
        pass


class StoragePlugin(Plugin, ABC):
    """存储后端插件基类 — 自定义记忆存储"""

    def __init__(self, info: PluginInfo, config: dict = None):
        super().__init__(info)
        self.config = config or {}

    @abstractmethod
    async def store(self, memory_id: str, data: dict) -> bool:
        """存储记忆"""
        ...

    @abstractmethod
    async def retrieve(self, memory_id: str) -> dict | None:
        """检索记忆"""
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        ...

    @abstractmethod
    async def search(self, query: str, **kwargs) -> list[dict]:
        """搜索记忆"""
        ...

    async def on_store(self, ctx: PluginContext) -> None:
        """存储钩子"""
        pass


class AnalyzerPlugin(Plugin, ABC):
    """分析器插件基类 — 记忆分析与洞察"""

    def __init__(self, info: PluginInfo, config: dict = None):
        super().__init__(info)
        self.config = config or {}

    @abstractmethod
    async def analyze(self, memories: list[dict], **kwargs) -> dict:
        """分析记忆列表

        Args:
            memories: 记忆列表

        Returns:
            分析结果
        """
        ...

    @abstractmethod
    async def get_insight(self, topic: str, memories: list[dict]) -> str:
        """生成主题洞察"""
        ...

    async def on_analyze(self, ctx: PluginContext) -> None:
        """分析钩子"""
        pass


# ── 插件配置 ──

@dataclass
class PluginConfig:
    """单个插件配置"""
    name: str
    enabled: bool = True
    priority: int = 100
    settings: dict = field(default_factory=dict)


@dataclass
class PluginRegistryEntry:
    """插件注册表条目"""
    plugin: Plugin
    plugin_type: PluginType
    config: PluginConfig
    loaded: bool = False


# ── 插件管理器 ──

class PluginManager:
    """插件管理器 — 管理插件生命周期、配置和钩子

    功能：
    - 插件注册/卸载/启用/禁用
    - 按类型管理插件（Mining/Storage/Analyzer/Hook）
    - 插件配置持久化
    - 钩子触发与分发
    - 插件发现（自动扫描目录）
    """

    def __init__(self, config_dir: str = None):
        """
        Args:
            config_dir: 插件配置目录，默认 ~/.pangu/plugins/
        """
        self._plugins: dict[str, PluginRegistryEntry] = {}
        self._hook_map: dict[HookPoint, list[Plugin]] = {}
        self._config_dir = Path(config_dir or os.path.expanduser("~/.pangu/plugins"))
        self._config_file = self._config_dir / "plugins.json"
        self._configs: dict[str, PluginConfig] = {}
        self._load_configs()

    # ── 注册与卸载 ──

    def register(self, plugin: Plugin, plugin_type: PluginType = PluginType.HOOK,
                 config: PluginConfig = None) -> None:
        """注册插件

        Args:
            plugin: 插件实例
            plugin_type: 插件类型
            config: 插件配置，留空自动生成
        """
        name = plugin.info.name
        if not config:
            config = PluginConfig(name=name, priority=plugin.info.priority)

        entry = PluginRegistryEntry(plugin=plugin, plugin_type=plugin_type, config=config)
        self._plugins[name] = entry
        self._configs[name] = config

        # 注册钩子
        for hook in plugin.info.hooks:
            if hook not in self._hook_map:
                self._hook_map[hook] = []
            self._hook_map[hook].append(plugin)
            self._hook_map[hook].sort(key=lambda p: p.info.priority)

        logger.info(f"插件已注册: {name} ({plugin_type.value}) v{plugin.info.version}")

    def unregister(self, name: str) -> bool:
        """卸载插件

        Args:
            name: 插件名称

        Returns:
            是否卸载成功
        """
        entry = self._plugins.pop(name, None)
        if not entry:
            return False

        # 移除钩子
        for _hook, plugins in self._hook_map.items():
            if entry.plugin in plugins:
                plugins.remove(entry.plugin)

        self._configs.pop(name, None)
        logger.info(f"插件已卸载: {name}")
        return True

    def enable(self, name: str) -> bool:
        """启用插件"""
        entry = self._plugins.get(name)
        if not entry:
            return False
        entry.plugin.enable()
        entry.config.enabled = True
        self._save_configs()
        return True

    def disable(self, name: str) -> bool:
        """禁用插件"""
        entry = self._plugins.get(name)
        if not entry:
            return False
        entry.plugin.disable()
        entry.config.enabled = False
        self._save_configs()
        return True

    # ── 按类型获取 ──

    def get_mining_plugins(self) -> list[MiningPlugin]:
        """获取所有已启用的挖掘插件"""
        return [
            e.plugin for e in self._plugins.values()
            if e.plugin_type == PluginType.MINING and e.plugin.enabled and isinstance(e.plugin, MiningPlugin)
        ]

    def get_storage_plugins(self) -> list[StoragePlugin]:
        """获取所有已启用的存储插件"""
        return [
            e.plugin for e in self._plugins.values()
            if e.plugin_type == PluginType.STORAGE and e.plugin.enabled and isinstance(e.plugin, StoragePlugin)
        ]

    def get_analyzer_plugins(self) -> list[AnalyzerPlugin]:
        """获取所有已启用的分析器插件"""
        return [
            e.plugin for e in self._plugins.values()
            if e.plugin_type == PluginType.ANALYZER and e.plugin.enabled and isinstance(e.plugin, AnalyzerPlugin)
        ]

    def get_plugin(self, name: str) -> Plugin | None:
        """获取指定插件"""
        entry = self._plugins.get(name)
        return entry.plugin if entry else None

    def get_plugin_type(self, name: str) -> PluginType | None:
        """获取插件类型"""
        entry = self._plugins.get(name)
        return entry.plugin_type if entry else None

    # ── 配置管理 ──

    def update_config(self, name: str, settings: dict) -> bool:
        """更新插件配置

        Args:
            name: 插件名称
            settings: 配置项（合并到现有配置）

        Returns:
            是否更新成功
        """
        config = self._configs.get(name)
        if not config:
            return False
        config.settings.update(settings)
        self._save_configs()
        logger.info(f"插件配置已更新: {name}")
        return True

    def get_config(self, name: str) -> dict:
        """获取插件配置"""
        config = self._configs.get(name)
        return config.settings if config else {}

    def _load_configs(self) -> None:
        """从文件加载插件配置"""
        import json
        if not self._config_file.exists():
            return
        try:
            with open(self._config_file, encoding="utf-8") as f:
                data = json.load(f)
            for name, cfg in data.items():
                self._configs[name] = PluginConfig(
                    name=name,
                    enabled=cfg.get("enabled", True),
                    priority=cfg.get("priority", 100),
                    settings=cfg.get("settings", {}),
                )
        except Exception as e:
            logger.warning(f"加载插件配置失败: {e}")

    def _save_configs(self) -> None:
        """保存插件配置到文件"""
        import json
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = {}
        for name, config in self._configs.items():
            data[name] = {
                "enabled": config.enabled,
                "priority": config.priority,
                "settings": config.settings,
            }
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 钩子系统 ──

    async def trigger_hook(self, hook: HookPoint, ctx: PluginContext = None) -> PluginContext:
        """触发钩子

        Args:
            hook: 钩子点
            ctx: 插件上下文，留空自动创建

        Returns:
            处理后的上下文
        """
        if ctx is None:
            ctx = PluginContext()

        plugins = self._hook_map.get(hook, [])
        for plugin in plugins:
            if not plugin.enabled:
                continue
            if ctx.cancelled:
                break

            method_name = f"on_{hook.value}"
            handler = getattr(plugin, method_name, None)
            if handler:
                try:
                    await handler(ctx)
                except Exception as e:
                    logger.error(f"插件 {plugin.info.name} 钩子 {hook.value} 异常: {e}")

        return ctx

    # ── 插件发现 ──

    def discover_plugins(self, plugin_dir: str = None) -> int:
        """从目录自动发现并加载插件

        Args:
            plugin_dir: 插件目录，默认 ~/.pangu/plugins/custom/

        Returns:
            发现的插件数量
        """
        plugin_path = Path(plugin_dir or self._config_dir / "custom")
        if not plugin_path.exists():
            return 0

        count = 0
        for py_file in plugin_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, str(py_file))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 查找 Plugin 子类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                            and attr is not MiningPlugin
                            and attr is not StoragePlugin
                            and attr is not AnalyzerPlugin):
                        instance = attr()
                        self.register(instance)
                        count += 1
            except Exception as e:
                logger.error(f"加载插件 {py_file.name} 失败: {e}")

        logger.info(f"发现 {count} 个插件")
        return count

    # ── 列表与状态 ──

    def list_plugins(self) -> list[dict]:
        """列出所有插件"""
        return [
            {
                "name": e.plugin.info.name,
                "version": e.plugin.info.version,
                "description": e.plugin.info.description,
                "type": e.plugin_type.value,
                "enabled": e.plugin.enabled,
                "hooks": [h.value for h in e.plugin.info.hooks],
                "priority": e.config.priority,
            }
            for e in self._plugins.values()
        ]

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def enabled_count(self) -> int:
        return sum(1 for e in self._plugins.values() if e.plugin.enabled)


# ── 全局单例 ──

_manager: PluginManager | None = None


def get_plugin_manager(config_dir: str = None) -> PluginManager:
    """获取全局插件管理器实例"""
    global _manager
    if _manager is None:
        _manager = PluginManager(config_dir)
    return _manager
