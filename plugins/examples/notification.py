"""通知插件 — 记忆变更时发送通知"""
from pangu.plugins import Plugin, PluginInfo, HookPoint, PluginContext
import logging

logger = logging.getLogger("pangu.plugins.notification")


class NotificationPlugin(Plugin):
    """通知插件 — 记忆变更时记录日志"""

    def __init__(self):
        super().__init__(PluginInfo(
            name="notification",
            version="1.0.0",
            description="记忆变更通知",
            hooks=[HookPoint.POST_MEMORY_ADD, HookPoint.POST_MEMORY_FORGET],
        ))

    async def on_post_memory_add(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "")[:50]
        logger.info(f"新记忆已添加: {content}")

    async def on_post_memory_forget(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "")[:50]
        logger.info(f"记忆已遗忘: {content}")
