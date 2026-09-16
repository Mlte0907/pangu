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
    """列出所有 Wing（空间）

    以**权威记忆库**（drawer.wing）为准，并集上 Palace 索引里额外登记的 wing。
    此前只读 Palace：而 Palace 索引不参与 v2 写入路径（`palace_meta.json` 从未生成），
    于是在 125 条记忆 / 6 个 wing 的库上返回 `["default"]`，与 dashboard 的知识翼分布、
    检索看到的世界完全不一致 —— 属 P0-0 同类的路径分叉。
    """
    wings = {(d.wing or "default") for d in drawers}
    try:
        wings.update(server.palace.list_wings() or [])
    except Exception:
        pass
    return json.dumps(sorted(wings), ensure_ascii=False)


HANDLERS["pangu_list_wings"] = handle_list_wings


async def handle_create_wing(server, drawers, arguments):
    """创建新 Wing"""
    name = arguments.get("name", "")
    desc = arguments.get("description", "")
    return json.dumps({"wing": server.palace.create_wing(name, desc)}, ensure_ascii=False)


HANDLERS["pangu_create_wing"] = handle_create_wing


async def handle_list_rooms(server, drawers, arguments):
    """列出 Wing 下的所有 Room（返回 {wing: [room]}，与 Palace 原形状一致）

    同 handle_list_wings：以权威记忆库为准，并集 Palace 索引登记的 room。
    此前只读 Palace，实测在 20 个 room 的库上返回 `{}`。
    """
    wing = arguments.get("wing")
    result: dict[str, list[str]] = {}
    for d in drawers:
        w = d.wing or "default"
        if wing and w != wing:
            continue
        bucket = result.setdefault(w, [])
        r = d.room or "general"
        if r not in bucket:
            bucket.append(r)
    try:
        for w, rooms in (server.palace.list_rooms(wing) or {}).items():
            bucket = result.setdefault(w, [])
            for r in rooms or []:
                if r not in bucket:
                    bucket.append(r)
    except Exception:
        pass
    return json.dumps(
        {w: sorted(rooms) for w, rooms in sorted(result.items())}, ensure_ascii=False
    )


HANDLERS["pangu_list_rooms"] = handle_list_rooms


async def handle_create_room(server, drawers, arguments):
    """在 Wing 下创建 Room"""
    wing = arguments.get("wing", "default")
    room = arguments.get("room", "")
    desc = arguments.get("description", "")
    return json.dumps({"room": server.palace.create_room(wing, room, desc)}, ensure_ascii=False)


HANDLERS["pangu_create_room"] = handle_create_room
