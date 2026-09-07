"""去重守卫插件 — 防止重复记忆写入"""
from pangu.plugins import Plugin, PluginInfo, HookPoint, PluginContext


class DedupGuardPlugin(Plugin):
    """去重守卫插件 — 写入前检查是否已存在相同内容"""

    def __init__(self, threshold: float = 0.95):
        super().__init__(PluginInfo(
            name="dedup_guard",
            version="1.0.0",
            description="写入前检查重复内容",
            hooks=[HookPoint.PRE_MEMORY_ADD],
        ))
        self.threshold = threshold
        self._seen: dict[str, str] = {}

    async def on_pre_memory_add(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "")
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]

        # 精确去重
        if content_hash in self._seen:
            ctx.set("cancel_reason", f"重复内容 (hash: {content_hash})")
            return

        self._seen[content_hash] = content[:50]

import hashlib
