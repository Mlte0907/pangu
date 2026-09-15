"""盘古 MCP Handler — knowledge (8 tools, P2-1 Step 1)

领域知识库工具（独立 SQLite DB）。所有工具通过 `server.domain_knowledge` 访问。
该 DB 路径由 `PanguConfig.domain_knowledge_db_path` 控制（不走 drawers.json）。

⚠️ 注意：本模块使用**绝对导入**（`from pangu.memory...`）而非相对导入
（`from ...memory...`），原因是 service 模式下 `sys.path.insert(0, '.')`
让 `pangu` 成为顶层包，`...` 三级相对导入会触发
"attempted relative import beyond top-level package"。
"""

import json

from pangu.memory.domain_knowledge import DomainType, KnowledgeCategory, KnowledgeEntry

TOOLS = [
    {"name": "pangu_knowledge_create", "description": "\u521b\u5efa\u9886\u57df\u77e5\u8bc6\u6761\u76ee"},
    {"name": "pangu_knowledge_get", "description": "\u83b7\u53d6\u77e5\u8bc6\u6761\u76ee"},
    {"name": "pangu_knowledge_update", "description": "\u66f4\u65b0\u77e5\u8bc6\u6761\u76ee"},
    {"name": "pangu_knowledge_delete", "description": "\u5220\u9664\u77e5\u8bc6\u6761\u76ee"},
    {"name": "pangu_knowledge_list", "description": "\u5217\u51fa\u77e5\u8bc6\u6761\u76ee"},
    {"name": "pangu_knowledge_search", "description": "\u5173\u952e\u8bcd\u68c0\u7d22\u77e5\u8bc6"},
    {"name": "pangu_knowledge_related", "description": "\u83b7\u53d6\u5173\u8054\u6761\u76ee"},
    {"name": "pangu_knowledge_stats", "description": "\u83b7\u53d6\u77e5\u8bc6\u5e93\u7edf\u8ba1"},
]

HANDLERS = {}


def _entry_to_dict(entry) -> dict:
    """KnowledgeEntry → JSON dict（dataclass 友好序列化）"""
    return {
        "id": entry.id,
        "domain": entry.domain.value,
        "category": entry.category.value,
        "title": entry.title,
        "content": entry.content,
        "tags": list(entry.tags),
        "status": entry.status.value,
        "confidence": entry.confidence,
        "importance": entry.importance,
        "related_ids": list(entry.related_ids),
        "source": entry.source,
        "author": entry.author,
    }


async def handle_knowledge_create(server, drawers, arguments):
    """创建领域知识条目"""
    domain = DomainType(arguments.get("domain", "software_engineering"))
    category = KnowledgeCategory(arguments.get("category", "best_practice"))
    entry = KnowledgeEntry(
        id=arguments.get("id", ""),
        domain=domain,
        category=category,
        title=arguments.get("title", ""),
        content=arguments.get("content", ""),
        tags=arguments.get("tags", []),
        confidence=arguments.get("confidence", 1.0),
        importance=arguments.get("importance", 0.5),
        source=arguments.get("source", ""),
        author=arguments.get("author", ""),
    )
    created = server.domain_knowledge.create_entry(entry)
    return json.dumps(_entry_to_dict(created), ensure_ascii=False)


HANDLERS["pangu_knowledge_create"] = handle_knowledge_create


async def handle_knowledge_get(server, drawers, arguments):
    """获取知识条目"""
    entry = server.domain_knowledge.get_entry(arguments.get("entry_id", ""))
    if entry is None:
        return json.dumps({"error": "not_found", "entry_id": arguments.get("entry_id", "")})
    return json.dumps(_entry_to_dict(entry), ensure_ascii=False)


HANDLERS["pangu_knowledge_get"] = handle_knowledge_get


async def handle_knowledge_update(server, drawers, arguments):
    """更新知识条目（kwargs 透传到 update_entry）"""
    entry_id = arguments.get("entry_id", "")
    kwargs = {k: v for k, v in arguments.items() if k != "entry_id"}
    updated = server.domain_knowledge.update_entry(entry_id, **kwargs)
    if updated is None:
        return json.dumps({"error": "not_found", "entry_id": entry_id})
    return json.dumps(_entry_to_dict(updated), ensure_ascii=False)


HANDLERS["pangu_knowledge_update"] = handle_knowledge_update


async def handle_knowledge_delete(server, drawers, arguments):
    """删除知识条目"""
    entry_id = arguments.get("entry_id", "")
    ok = server.domain_knowledge.delete_entry(entry_id)
    return json.dumps({"entry_id": entry_id, "deleted": ok})


HANDLERS["pangu_knowledge_delete"] = handle_knowledge_delete


async def handle_knowledge_list(server, drawers, arguments):
    """列出知识条目（按 domain/category 过滤）

    domain/category 是枚举字符串，handler 内做转换。
    status 是字符串字段（active/deprecated/merged），直接传。
    """
    domain_str = arguments.get("domain")
    category_str = arguments.get("category")
    try:
        domain = DomainType(domain_str) if domain_str else None
        category = KnowledgeCategory(category_str) if category_str else None
    except ValueError as e:
        return json.dumps({"code": 4000, "error": f"枚举值非法: {e}"})
    entries = server.domain_knowledge.list_entries(
        domain=domain,
        category=category,
        status=arguments.get("status"),
        limit=arguments.get("limit", 100),
    )
    return json.dumps(
        {"total": len(entries), "entries": [_entry_to_dict(e) for e in entries]},
        ensure_ascii=False,
    )


HANDLERS["pangu_knowledge_list"] = handle_knowledge_list


async def handle_knowledge_search(server, drawers, arguments):
    """关键词检索知识库"""
    keywords = arguments.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keywords]
    entries = server.domain_knowledge.search_by_keywords(keywords)
    return json.dumps(
        {"total": len(entries), "entries": [_entry_to_dict(e) for e in entries]},
        ensure_ascii=False,
    )


HANDLERS["pangu_knowledge_search"] = handle_knowledge_search


async def handle_knowledge_related(server, drawers, arguments):
    """获取关联条目"""
    entry_id = arguments.get("entry_id", "")
    entries = server.domain_knowledge.get_related(entry_id)
    return json.dumps(
        {"total": len(entries), "entries": [_entry_to_dict(e) for e in entries]},
        ensure_ascii=False,
    )


HANDLERS["pangu_knowledge_related"] = handle_knowledge_related


async def handle_knowledge_stats(server, drawers, arguments):
    """获取知识库统计"""
    stats = server.domain_knowledge.get_stats()
    return json.dumps(
        {
            "total_entries": stats.total_entries,
            "by_domain": stats.by_domain,
            "by_category": stats.by_category,
            "by_status": stats.by_status,
            "avg_confidence": stats.avg_confidence,
            "avg_importance": stats.avg_importance,
            "top_tags": stats.top_tags,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_knowledge_stats"] = handle_knowledge_stats
