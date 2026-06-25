"""盘古 MCP Handler — palace (4 tools)"""
import json

TOOLS = [
    {"name": "pangu_list_wings", "description": "\u5217\u51fa\u6240\u6709 Wing\uff08\u7a7a\u95f4\uff09"},
    {"name": "pangu_create_wing", "description": "\u521b\u5efa\u65b0 Wing"},
    {"name": "pangu_list_rooms", "description": "\u5217\u51fa Wing \u4e0b\u7684\u6240\u6709 Room"},
    {"name": "pangu_create_room", "description": "\u5728 Wing \u4e0b\u521b\u5efa Room"},
]

HANDLERS = {}

async def handle_list_wings(server, drawers, arguments):
    """列出所有 Wing（空间）"""
    return json.dumps(server.palace.list_wings(), ensure_ascii=False)

HANDLERS["pangu_list_wings"] = handle_list_wings

async def handle_create_wing(server, drawers, arguments):
    """创建新 Wing"""
    name = arguments.get("name", "")
    desc = arguments.get("description", "")
    return json.dumps({"wing": server.palace.create_wing(name, desc)}, ensure_ascii=False)

HANDLERS["pangu_create_wing"] = handle_create_wing

async def handle_list_rooms(server, drawers, arguments):
    """列出 Wing 下的所有 Room"""
    wing = arguments.get("wing")
    return json.dumps(server.palace.list_rooms(wing), ensure_ascii=False)

HANDLERS["pangu_list_rooms"] = handle_list_rooms

async def handle_create_room(server, drawers, arguments):
    """在 Wing 下创建 Room"""
    wing = arguments.get("wing", "default")
    room = arguments.get("room", "")
    desc = arguments.get("description", "")
    return json.dumps({"room": server.palace.create_room(wing, room, desc)}, ensure_ascii=False)

HANDLERS["pangu_create_room"] = handle_create_room