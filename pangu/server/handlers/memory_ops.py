"""盘古 MCP Handler — memory_ops (4 tools)"""

import json
import uuid

from ...core.palace import Drawer

TOOLS = [
    {
        "name": "pangu_add_memory",
        "description": "添加记忆片段。⚠️ 强制：完成有意义的工作后必须调用此工具记录学到了什么、踩了什么坑、下次怎么做。不记录 = 白做。",
    },
    {
        "name": "pangu_search_memories",
        "description": "搜索记忆。⚠️ 强制：每次收到用户消息后必须先调用此工具搜索相关历史，再执行任务。不搜索 = 可能重复踩坑。",
    },
    {"name": "pangu_recall", "description": "按 Wing/Room 回忆记忆"},
    {"name": "pangu_wake_up", "description": "获取 L0+L1 唤醒上下文"},
    {
        "name": "pangu_delete_memory",
        "description": "按 memory_id 硬删除记忆（不可逆，本地自动备份）",
    },
    {
        "name": "pangu_archive_memory",
        "description": "按 memory_id 归档记忆（移出正常搜索/recall，可经 pangu_get_archive 查看）",
    },
]

HANDLERS = {}


async def handle_add_memory(server, drawers, arguments):
    """添加记忆片段（P0-1 缺口 2：接入 remember() 管道）

    修复前：直接创建 Drawer + add_drawer()，绕过脱敏/去重/冲突检测。
    修复后：走 remember() 全管道，与 REST 通道行为一致。
    """
    from ...memory.ingestion import remember

    # remember() 的契约是 0.0–1.0（旧默认 3.0 属 1–5 量纲，会让写入 100% 失败）
    importance = arguments.get("importance", 0.5)
    if not isinstance(importance, (int, float)):
        importance = Drawer._coerce_float(importance, 0.5)

    # 走 remember() 全管道（脱敏 → 去重 → 冲突检测 → supersede → 版本链）
    item_id, drawer = remember(
        raw_text=arguments.get("content", ""),
        wing=arguments.get("wing", "default"),
        room=arguments.get("room", "general"),
        importance=importance,
        tags=arguments.get("tags", []),
        source="mcp",
        created_by="mcp",
        source_session=arguments.get("source_session", ""),
    )

    # 设置 MCP 特有的 metadata（owner_id / tenant_id 等）
    if drawer is not None:
        drawer.metadata = dict(drawer.metadata or {})
        drawer.metadata["owner_id"] = arguments.get("owner_id", "mcp_user")
        # P1-3 阶段 1.4：身份优先于参数
        identity = arguments.get("_identity", {})
        drawer.metadata["tenant_id"] = identity.get("room", arguments.get("tenant_id", "default"))
        drawer.metadata["classification"] = arguments.get("classification", "normal")
        # P1-3 收尾：用 setdefault 语义，门禁已决定 visibility 时以门禁为准
        drawer.metadata.setdefault("visibility", arguments.get("visibility", "tenant"))
        # P1-3：remember() 不落盘（只创建 Drawer 对象），handler 的 add_drawer 才是唯一落盘点
        server.memory.add_drawer(drawer)

    try:
        from ...memory.autonomous import on_memory_written

        on_memory_written()
    except Exception:
        pass
    try:
        from ...memory.memory_events import get_event_stream

        get_event_stream(server.config).emit_memory_write(item_id, drawer.content, drawer.wing)
    except Exception:
        pass

    return json.dumps(
        {
            "drawer_id": item_id,
            "wing": drawer.wing,
            "room": drawer.room,
            "supersedes": drawer.metadata.get("supersedes", []),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_add_memory"] = handle_add_memory


async def handle_search_memories(server, drawers, arguments):
    """搜索记忆（P1-3 阶段 2.2：按 metadata.tenant_id 过滤 + public 毕业区）"""
    query = arguments.get("query", "")
    wing = arguments.get("wing")
    room = arguments.get("room")

    # P1-3 阶段 2.2：有身份时预过滤 drawers（隔离轴是 metadata.tenant_id，不是 Drawer.room）
    identity = arguments.get("_identity", {})
    if identity:
        identity_room = identity.get("room", "")
        filtered = [
            d for d in drawers
            if ((d.metadata or {}).get("tenant_id", "") == identity_room
                or (d.metadata or {}).get("visibility", "") == "public")
        ]
        drawers = filtered

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
    # 统一返回格式：{"results": [...], "total": N}
    if isinstance(results, list):
        return json.dumps({"results": results, "total": len(results), "query": query}, ensure_ascii=False, default=str)
    return json.dumps(results, ensure_ascii=False, default=str)


HANDLERS["pangu_search_memories"] = handle_search_memories


async def handle_recall(server, drawers, arguments):
    """按 Wing/Room 回忆记忆（P1-3 阶段 2.2：按 metadata.tenant_id 过滤）"""
    wing = arguments.get("wing")
    room = arguments.get("room")

    # P1-3 阶段 2.2：有身份时预过滤 drawers
    identity = arguments.get("_identity", {})
    if identity:
        identity_room = identity.get("room", "")
        filtered = [
            d for d in drawers
            if ((d.metadata or {}).get("tenant_id", "") == identity_room
                or (d.metadata or {}).get("visibility", "") == "public")
        ]
        drawers = filtered

    # 必须把过滤后的集合传进去：recall 默认只读自身存储，不传等于隔离空转
    result = server.memory.recall(wing=wing, room=room, drawers=drawers)

    # 记忆内容在盘上是加密的（Fernet，密文以 gAAAAAB 开头）。search 路径会逐条解密，
    # 而 recall 直接把这些密文拼进 Markdown 返回 —— 调用方拿到的是不可读的乱码
    # （实测 dsh 钥匙 recall 出 [general] gAAAAABqqp5v4dO3…）。这里做同样的解密。
    try:
        import re as _re

        from ...memory.encryption import decrypt

        def _decrypt_match(m: "_re.Match[str]") -> str:
            try:
                return decrypt(m.group(0))
            except Exception:
                return m.group(0)

        result = _re.sub(r"gAAAAAB[\w\-=]+", _decrypt_match, result)
    except Exception:
        pass

    return result


HANDLERS["pangu_recall"] = handle_recall


async def handle_wake_up(server, drawers, arguments):
    """获取 L0+L1 唤醒上下文"""
    wing = arguments.get("wing")
    return server.memory.wake_up(wing=wing)


HANDLERS["pangu_wake_up"] = handle_wake_up


async def handle_delete_memory(server, drawers, arguments):
    """硬删除记忆（按 memory_id，自动备份 + 向量索引同步，R4-B）"""
    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "参数缺失: memory_id 为必填"}, ensure_ascii=False)
    drawer = server.memory.get_drawer_by_id(memory_id)
    if not drawer:
        return json.dumps({"code": 2001, "error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)
    removed = server.memory.remove_drawer(memory_id)
    if not removed:
        return json.dumps({"code": 2004, "error": f"删除失败: {memory_id}"}, ensure_ascii=False)
    return json.dumps({"status": "removed", "memory_id": memory_id, "removed": True}, ensure_ascii=False)


HANDLERS["pangu_delete_memory"] = handle_delete_memory


async def handle_archive_memory(server, drawers, arguments):
    """归档记忆（按 memory_id：持久化归档 → 从正常搜索/recall 排除，R4-C）"""
    from ...memory.adaptive_forgetting import get_forgetting

    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "参数缺失: memory_id 为必填"}, ensure_ascii=False)
    drawer = server.memory.get_drawer_by_id(memory_id)
    if not drawer:
        return json.dumps({"code": 2001, "error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)

    af = get_forgetting(server.config)
    entry = af.archive_memory(drawer)
    removed = server.memory.remove_drawer(memory_id)
    if not removed:
        return json.dumps({"code": 2004, "error": f"归档失败: {memory_id}"}, ensure_ascii=False)

    return json.dumps(
        {
            "status": "archived",
            "memory_id": memory_id,
            "archived_at": entry["archived_at"],
            "wing": entry["wing"],
            "room": entry["room"],
            "archive_count": af.get_forgetting_stats().get("archive_size", len(af.get_archive(limit=10**6))),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_archive_memory"] = handle_archive_memory
