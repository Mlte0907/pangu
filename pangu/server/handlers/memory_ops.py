"""盘古 MCP Handler — memory_ops (4 tools)"""

import json

from ...core.palace import Drawer

TOOLS = [
    {"name": "pangu_add_memory", "description": "\u6dfb\u52a0\u8bb0\u5fc6\u7247\u6bb5"},
    {"name": "pangu_search_memories", "description": "\u641c\u7d22\u8bb0\u5fc6"},
    {"name": "pangu_recall", "description": "\u6309 Wing/Room \u56de\u5fc6\u8bb0\u5fc6"},
    {"name": "pangu_wake_up", "description": "\u83b7\u53d6 L0+L1 \u5524\u9192\u4e0a\u4e0b\u6587"},
]

HANDLERS = {}


async def handle_add_memory(server, drawers, arguments):
    """添加记忆片段"""
    drawer = Drawer(
        id=f"mem_{arguments.get('wing', 'default')}_{arguments.get('content', '')[:20]}",
        content=arguments.get("content", ""),
        wing=arguments.get("wing", "default"),
        room=arguments.get("room", "general"),
        hall=arguments.get("hall", "hall_events"),
        importance=arguments.get("importance", 3.0),
        tags=arguments.get("tags", []),
    )
    server.memory.add_drawer(drawer)
    try:
        from ...memory.autonomous import on_memory_written

        on_memory_written()
    except Exception:
        pass
    try:
        from ...memory.memory_events import get_event_stream

        get_event_stream(server.config).emit_memory_write(drawer.id, drawer.content, drawer.wing)
    except Exception:
        pass
    return json.dumps({"drawer_id": drawer.id, "wing": drawer.wing, "room": drawer.room}, ensure_ascii=False)


HANDLERS["pangu_add_memory"] = handle_add_memory


async def handle_search_memories(server, drawers, arguments):
    """搜索记忆"""
    query = arguments.get("query", "")
    wing = arguments.get("wing")
    room = arguments.get("room")
    results = server.search.search(query, drawers, wing=wing, room=room)
    try:
        from ...memory.encryption import decrypt

        items = results.get("results", results) if isinstance(results, dict) else results
        if isinstance(items, list):
            for r in items:
                if isinstance(r, dict):
                    for key in ("content", "highlighted"):
                        c = r.get(key, "")
                        if c and c.startswith("gAAAAAB"):
                            try:
                                r[key] = decrypt(c)
                            except Exception:
                                pass
    except Exception:
        pass
    return json.dumps(results, ensure_ascii=False, default=str)


HANDLERS["pangu_search_memories"] = handle_search_memories


async def handle_recall(server, drawers, arguments):
    """按 Wing/Room 回忆记忆"""
    wing = arguments.get("wing")
    room = arguments.get("room")
    return server.memory.recall(wing=wing, room=room)


HANDLERS["pangu_recall"] = handle_recall


async def handle_wake_up(server, drawers, arguments):
    """获取 L0+L1 唤醒上下文"""
    wing = arguments.get("wing")
    return server.memory.wake_up(wing=wing)


HANDLERS["pangu_wake_up"] = handle_wake_up
