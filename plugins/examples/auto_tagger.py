"""自动标签插件 — 根据内容自动添加标签"""
from pangu.plugins import Plugin, PluginInfo, HookPoint, PluginContext


class AutoTaggerPlugin(Plugin):
    """自动标签插件 — 根据关键词自动为记忆添加标签"""

    def __init__(self):
        super().__init__(PluginInfo(
            name="auto_tagger",
            version="1.0.0",
            description="根据内容自动添加标签",
            hooks=[HookPoint.PRE_MEMORY_ADD],
        ))
        self.rules = {
            "ai": ["AI", "人工智能", "机器学习", "深度学习"],
            "database": ["数据库", "SQL", "SQLite", "MySQL"],
            "web": ["HTTP", "API", "REST", "Web"],
            "devops": ["Docker", "Kubernetes", "部署", "CI/CD"],
            "security": ["密码", "加密", "安全", "权限"],
        }

    async def on_pre_memory_add(self, ctx: PluginContext) -> None:
        content = ctx.get("content", "").lower()
        tags = list(ctx.get("tags", []))
        added = []

        for tag, keywords in self.rules.items():
            if any(kw.lower() in content for kw in keywords):
                if tag not in tags:
                    tags.append(tag)
                    added.append(tag)

        if added:
            ctx.set("tags", tags)
            ctx.set("auto_tags", added)
