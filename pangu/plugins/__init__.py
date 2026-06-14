"""盘古插件系统 — 可扩展的记忆处理器
==========================================
提供钩子机制，允许用户注册自定义的记忆处理器，
在记忆生命周期的各个阶段执行自定义逻辑。

钩子类型：
- on_memory_add: 记忆添加前/后处理
- on_memory_recall: 记忆检索前/后处理
- on_memory_forget: 记忆遗忘前/后处理
- on_memory_compress: 记忆压缩前/后处理
- on_wiki_generate: Wiki 生成前/后处理
- on_consolidation: 记忆巩固时触发

插件可以：
- 自动翻译记忆内容
- 过滤敏感信息
- 添加自定义标签
- 发送通知
- 触发外部工作流
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("pangu.plugins")


class HookPoint(str, Enum):
    """钩子触发点"""
    PRE_MEMORY_ADD = "pre_memory_add"
    POST_MEMORY_ADD = "post_memory_add"
    PRE_MEMORY_RECALL = "pre_memory_recall"
    POST_MEMORY_RECALL = "post_memory_recall"
    PRE_MEMORY_FORGET = "pre_memory_forget"
    POST_MEMORY_FORGET = "post_memory_forget"
    PRE_MEMORY_COMPRESS = "pre_memory_compress"
    POST_MEMORY_COMPRESS = "post_memory_compress"
    PRE_WIKI_GENERATE = "pre_wiki_generate"
    POST_WIKI_GENERATE = "post_wiki_generate"
    ON_CONSOLIDATION = "on_consolidation"


@dataclass
class PluginInfo:
    """插件元信息"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    hooks: list[HookPoint] = field(default_factory=list)
    priority: int = 100  # 数字越小优先级越高


@dataclass
class PluginContext:
    """插件上下文 — 在钩子间传递数据"""
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    cancelled: bool = False  # 设置为 True 可取消后续操作

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value


class Plugin:
    """插件基类"""

    def __init__(self, info: PluginInfo = None):
        self.info = info or PluginInfo(name=self.__class__.__name__)
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    # 钩子方法（子类覆写）
    async def on_pre_memory_add(self, ctx: PluginContext) -> None:
        """记忆添加前钩子"""
        pass

    async def on_post_memory_add(self, ctx: PluginContext) -> None:
        """记忆添加后钩子"""
        pass

    async def on_pre_memory_recall(self, ctx: PluginContext) -> None:
        """记忆检索前钩子"""
        pass

    async def on_post_memory_recall(self, ctx: PluginContext) -> None:
        """记忆检索后钩子"""
        pass

    async def on_pre_memory_forget(self, ctx: PluginContext) -> None:
        """记忆遗忘前钩子"""
        pass

    async def on_post_memory_forget(self, ctx: PluginContext) -> None:
        """记忆遗忘后钩子"""
        pass

    async def on_pre_memory_compress(self, ctx: PluginContext) -> None:
        """记忆压缩前钩子"""
        pass

    async def on_post_memory_compress(self, ctx: PluginContext) -> None:
        """记忆压缩后钩子"""
        pass

    async def on_pre_wiki_generate(self, ctx: PluginContext) -> None:
        """Wiki 生成前钩子"""
        pass

    async def on_post_wiki_generate(self, ctx: PluginContext) -> None:
        """Wiki 生成后钩子"""
        pass

    async def on_consolidation(self, ctx: PluginContext) -> None:
        """记忆巩固时钩子"""
        pass


# ── 内置插件 ──

class TagEnricherPlugin(Plugin):
    """标签增强插件 — 自动为记忆添加标签"""

    def __init__(self, auto_tags: dict[str, list[str]] = None):
        super().__init__(PluginInfo(
            name="tag_enricher",
            description="根据关键词自动添加标签",
            hooks=[HookPoint.PRE_MEMORY_ADD],
        ))
        self.auto_tags = auto_tags or {
            "bug": ["bug", "缺陷", "修复"],
            "feature": ["feature", "功能", "新增"],
            "docs": ["文档", "doc", "README"],
            "performance": ["性能", "优化", "perf"],
            "security": ["安全", "漏洞", "security"],
        }

    async def on_pre_memory_add(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "").lower()
        tags = list(ctx.get("tags", []))

        for tag, keywords in self.auto_tags.items():
            if any(kw in content for kw in keywords):
                if tag not in tags:
                    tags.append(tag)

        ctx.set("tags", tags)


class ContentFilterPlugin(Plugin):
    """内容过滤器插件 — 过滤或修改记忆内容"""

    def __init__(self, blocked_patterns: list[str] = None, max_length: int = 10000):
        super().__init__(PluginInfo(
            name="content_filter",
            description="过滤敏感内容，限制长度",
            hooks=[HookPoint.PRE_MEMORY_ADD],
        ))
        self.blocked_patterns = blocked_patterns or []
        self.max_length = max_length

    async def on_pre_memory_add(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "")

        # 检查敏感内容
        for pattern in self.blocked_patterns:
            if pattern in content:
                ctx.cancelled = True
                ctx.set("cancel_reason", f"内容包含敏感模式: {pattern}")
                logger.warning(f"记忆被过滤: 包含 {pattern}")
                return

        # 截断过长内容
        if len(content) > self.max_length:
            ctx.set("content", content[:self.max_length] + "...[已截断]")


class TranslationPlugin(Plugin):
    """翻译插件 — 自动翻译记忆内容"""

    def __init__(self, target_lang: str = "zh", llm_engine=None):
        super().__init__(PluginInfo(
            name="translator",
            description="自动翻译记忆内容",
            hooks=[HookPoint.POST_MEMORY_ADD],
        ))
        self.target_lang = target_lang
        self.llm = llm_engine

    async def on_post_memory_add(self, ctx: PluginContext) -> None:
        if not self.llm:
            return
        content = ctx.get("content", "")
        if len(content) < 50:
            return

        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": f"请将以下内容翻译为中文：\n\n{content[:500]}"}],
                system="你是翻译助手，请准确翻译。",
                max_tokens=500,
            )
            ctx.set("translation", response.content)
        except Exception:
            pass


# ── 插件管理器 ──

class PluginManager:
    """插件管理器 — 注册、调度插件钩子"""

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._hook_map: dict[HookPoint, list[Plugin]] = {}

    def register(self, plugin: Plugin) -> None:
        """注册插件"""
        self._plugins[plugin.info.name] = plugin

        for hook in plugin.info.hooks:
            if hook not in self._hook_map:
                self._hook_map[hook] = []
            self._hook_map[hook].append(plugin)
            # 按优先级排序
            self._hook_map[hook].sort(key=lambda p: p.info.priority)

        logger.info(f"插件已注册: {plugin.info.name} v{plugin.info.version}")

    def unregister(self, plugin_name: str) -> bool:
        """注销插件"""
        if plugin_name not in self._plugins:
            return False

        plugin = self._plugins.pop(plugin_name)
        for _hook, plugins in self._hook_map.items():
            if plugin in plugins:
                plugins.remove(plugin)
        return True

    def get_plugin(self, name: str) -> Plugin | None:
        """获取插件"""
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict]:
        """列出所有插件"""
        return [
            {
                "name": p.info.name,
                "version": p.info.version,
                "description": p.info.description,
                "enabled": p.enabled,
                "hooks": [h.value for h in p.info.hooks],
                "priority": p.info.priority,
            }
            for p in self._plugins.values()
        ]

    async def trigger_hook(self, hook: HookPoint, ctx: PluginContext = None) -> PluginContext:
        """触发钩子"""
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

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)


# ── 从 plugin_manager.py 导入增强类型 ──
from .plugin_manager import (
    MiningPlugin,
    StoragePlugin,
    AnalyzerPlugin,
    PluginType,
    PluginManager as EnhancedPluginManager,
    get_plugin_manager,
)
