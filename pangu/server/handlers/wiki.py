"""盘古 MCP Handler — wiki (4 tools)"""
import json

TOOLS = [
    {"name": "pangu_list_wiki_pages", "description": "\u5217\u51fa Wiki \u9875\u9762"},
    {"name": "pangu_get_wiki_page", "description": "\u83b7\u53d6 Wiki \u9875\u9762\u5185\u5bb9"},
    {"name": "pangu_create_wiki_page", "description": "\u521b\u5efa Wiki \u9875\u9762"},
    {"name": "pangu_auto_generate_wiki", "description": "LMM \u81ea\u52a8\u751f\u6210 Wiki \u9875\u9762"},
]

HANDLERS = {}

async def handle_list_wiki_pages(server, drawers, arguments):
    """列出 Wiki 页面"""
    wing = arguments.get("wing")
    tag = arguments.get("tag")
    pages = server.wiki.list_pages(wing=wing, tag=tag)
    return json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2)

HANDLERS["pangu_list_wiki_pages"] = handle_list_wiki_pages

async def handle_get_wiki_page(server, drawers, arguments):
    """获取 Wiki 页面内容"""
    page_id = arguments.get("page_id", "")
    page = server.wiki.get_page(page_id)
    if page:
        return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)
    return json.dumps({"code": 1002, "error": "页面不存在"})

HANDLERS["pangu_get_wiki_page"] = handle_get_wiki_page

async def handle_create_wiki_page(server, drawers, arguments):
    """创建 Wiki 页面"""
    from ...core.palace import WikiPage
    page = WikiPage(
        id=f"wiki_manual_{arguments.get('title', '')[:20]}",
        title=arguments.get("title", ""),
        wing=arguments.get("wing", "default"),
        content=arguments.get("content", ""),
        summary=arguments.get("summary", ""),
        tags=arguments.get("tags", []),
    )
    server.wiki.create_page(page)
    return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)

HANDLERS["pangu_create_wiki_page"] = handle_create_wiki_page

async def handle_auto_generate_wiki(server, drawers, arguments):
    """LMM 自动生成 Wiki 页面"""
    title = arguments.get("title", "")
    wing = arguments.get("wing", "default")
    memories = [
        {"content": d.content, "wing": d.wing, "room": d.room}
        for d in drawers if d.wing == wing
    ]
    page = await server.wiki.auto_generate_page(server.llm, title, wing, memories)
    return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)

HANDLERS["pangu_auto_generate_wiki"] = handle_auto_generate_wiki