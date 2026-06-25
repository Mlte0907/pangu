"""盘古 MCP Handler — session (28 tools)"""
import json

TOOLS = [
    {"name": "pangu_cross_session_links", "description": "\u53d1\u73b0\u8de8\u4f1a\u8bdd\u8bb0\u5fc6\u5173\u8054"},
    {"name": "pangu_auto_compress", "description": "\u89e6\u53d1\u81ea\u52a8\u8bb0\u5fc6\u538b\u7f29\uff08\u957f\u8bb0\u5fc6\u2192\u7cbe\u7b80\u6458\u8981\uff09"},
    {"name": "pangu_sync_record", "description": "\u8bb0\u5f55\u53d8\u66f4"},
    {"name": "pangu_sync_pending", "description": "\u83b7\u53d6\u5f85\u540c\u6b65\u53d8\u66f4"},
    {"name": "pangu_sync_incremental", "description": "\u589e\u91cf\u540c\u6b65"},
    {"name": "pangu_sync_apply", "description": "\u5e94\u7528\u589e\u91cf\u53d8\u66f4"},
    {"name": "pangu_sync_auto_resolve", "description": "\u81ea\u52a8\u89e3\u51b3\u51b2\u7a81"},
    {"name": "pangu_sync_state", "description": "\u540c\u6b65\u72b6\u6001"},
    {"name": "pangu_sync_stats", "description": "\u540c\u6b65\u7edf\u8ba1"},
    {"name": "pangu_portal_write", "description": "\u667a\u80fd\u5199\u5165\uff08\u81ea\u52a8\u6807\u7b7e+\u7d22\u5f15+\u4e8b\u4ef6\uff09"},
    {"name": "pangu_portal_search", "description": "\u667a\u80fd\u641c\u7d22\uff08\u81ea\u52a8\u91cd\u5199+\u7d22\u5f15+\u6392\u5e8f\uff09"},
    {"name": "pangu_portal_panorama", "description": "\u7cfb\u7edf\u5168\u666f"},
    {"name": "pangu_portal_maintain", "description": "\u4e00\u952e\u7ef4\u62a4"},
    {"name": "pangu_portal_summary", "description": "\u667a\u80fd\u6458\u8981"},
    {"name": "pangu_session_summary", "description": "\u751f\u6210\u4f1a\u8bdd\u6458\u8981"},
    {"name": "pangu_session_bridge", "description": "\u6784\u5efa\u4e0a\u4e0b\u6587\u6865\u63a5"},
    {"name": "pangu_session_stats", "description": "\u4f1a\u8bdd\u7edf\u8ba1"},
    {"name": "pangu_session_inject", "description": "\u8de8\u4f1a\u8bdd\u4e0a\u4e0b\u6587\u6ce8\u5165"},
    {"name": "pangu_session_start", "description": "\u8bb0\u5f55\u4f1a\u8bdd\u5f00\u59cb"},
    {"name": "pangu_session_end", "description": "\u8bb0\u5f55\u4f1a\u8bdd\u7ed3\u675f\u5e76\u751f\u6210\u6458\u8981"},
    {"name": "pangu_session_resume", "description": "\u83b7\u53d6\u4e0a\u4e00\u4e2a\u4f1a\u8bdd\u7684\u6062\u590d\u4e0a\u4e0b\u6587"},
    {"name": "pangu_session_record", "description": "\u8bb0\u5f55\u4f1a\u8bdd\u4e2d\u7684\u4e8b\u4ef6"},
    {"name": "pangu_session_stats", "description": "\u83b7\u53d6\u4f1a\u8bdd\u7edf\u8ba1"},
    {"name": "pangu_autopilot_activate", "description": "\u6fc0\u6d3b\u81ea\u52a8\u9a7e\u9a76\u6a21\u5f0f\uff08\u81ea\u52a8\u7ba1\u7406\u8bb0\u5fc6\uff09"},
    {"name": "pangu_autopilot_deactivate", "description": "\u505c\u7528\u81ea\u52a8\u9a7e\u9a76\u6a21\u5f0f"},
    {"name": "pangu_autopilot_tick", "description": "\u8fd0\u884c\u4e00\u6b21\u81ea\u52a8\u9a7e\u9a76\u68c0\u67e5\uff08\u81ea\u52a8\u7ec4\u7ec7/\u7ef4\u62a4/\u62a5\u544a\uff09"},
    {"name": "pangu_autopilot_suggest", "description": "\u57fa\u4e8e\u5f53\u524d\u4efb\u52a1\u4e3b\u52a8\u63a8\u8350\u76f8\u5173\u8bb0\u5fc6"},
    {"name": "pangu_autopilot_status", "description": "\u67e5\u770b\u81ea\u52a8\u9a7e\u9a76\u72b6\u6001"},
]

HANDLERS = {}

async def handle_cross_session_links(server, drawers, arguments):
    """发现跨会话记忆关联"""
    from ...memory.cross_session import CrossSessionIntegrator
    integrator = CrossSessionIntegrator(server.config)
    min_sim = arguments.get("min_similarity", 0.4)
    max_links = arguments.get("max_links", 10)
    links = integrator.find_cross_session_links(drawers[-10:], drawers, min_sim, max_links)
    return json.dumps({"links": links, "count": len(links)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_cross_session_links"] = handle_cross_session_links

async def handle_auto_compress(server, drawers, arguments):
    """触发自动记忆压缩（长记忆→精简摘要）"""
    from ...lifecycle import LifecycleManager
    mgr = LifecycleManager(server.config)
    result = mgr.run_auto_compress()
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_auto_compress"] = handle_auto_compress

async def handle_sync_record(server, drawers, arguments):
    """记录变更"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    entry = sm.record_change(
        arguments["memory_id"], arguments["operation"],
        arguments.get("content", ""),
    )
    return json.dumps({"change_id": entry.change_id, "timestamp": entry.timestamp}, ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_record"] = handle_sync_record

async def handle_sync_pending(server, drawers, arguments):
    """获取待同步变更"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    pending = sm.get_pending_changes(arguments.get("since"))
    return json.dumps({"pending": pending, "count": len(pending)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_pending"] = handle_sync_pending

async def handle_sync_incremental(server, drawers, arguments):
    """增量同步"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    changes = sm.get_incremental_changes(
        arguments.get("since_timestamp"),
        arguments.get("source"),
    )
    return json.dumps({"changes": changes, "count": len(changes)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_incremental"] = handle_sync_incremental

async def handle_sync_apply(server, drawers, arguments):
    """应用增量变更"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    result = sm.apply_incremental(arguments.get("remote_changes", []))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_apply"] = handle_sync_apply

async def handle_sync_auto_resolve(server, drawers, arguments):
    """自动解决冲突"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    result = sm.auto_resolve_conflicts(arguments.get("strategy", "keep_latest"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_auto_resolve"] = handle_sync_auto_resolve

async def handle_sync_state(server, drawers, arguments):
    """同步状态"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    return json.dumps(sm.get_sync_state(), ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_state"] = handle_sync_state

async def handle_sync_stats(server, drawers, arguments):
    """同步统计"""
    from ...memory.sync_manager import get_sync
    sm = get_sync(server.config)
    return json.dumps(sm.get_sync_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_sync_stats"] = handle_sync_stats

async def handle_portal_write(server, drawers, arguments):
    """智能写入（自动标签+索引+事件）"""
    from ...memory.portal import get_portal
    portal = get_portal(server.config)
    result = portal.smart_write(
        drawers, arguments["content"],
        arguments.get("wing", "default"),
        arguments.get("tags", []),
        arguments.get("importance", 3.0),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_portal_write"] = handle_portal_write

async def handle_portal_search(server, drawers, arguments):
    """智能搜索（自动重写+索引+排序）"""
    from ...memory.portal import get_portal
    portal = get_portal(server.config)
    result = portal.smart_search(drawers, arguments["query"], arguments.get("limit", 5))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_portal_search"] = handle_portal_search

async def handle_portal_panorama(server, drawers, arguments):
    """系统全景"""
    from ...memory.portal import get_portal
    portal = get_portal(server.config)
    return json.dumps(portal.system_panorama(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_portal_panorama"] = handle_portal_panorama

async def handle_portal_maintain(server, drawers, arguments):
    """一键维护"""
    from ...memory.portal import get_portal
    portal = get_portal(server.config)
    return json.dumps(portal.one_click_maintenance(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_portal_maintain"] = handle_portal_maintain

async def handle_portal_summary(server, drawers, arguments):
    """智能摘要"""
    from ...memory.portal import get_portal
    portal = get_portal(server.config)
    summary = portal.get_smart_summary(drawers)
    return json.dumps({"summary": summary}, ensure_ascii=False, indent=2)

HANDLERS["pangu_portal_summary"] = handle_portal_summary

async def handle_session_summary(server, drawers, arguments):
    """生成会话摘要"""
    from ...memory.cross_session import CrossSessionIntegrator
    cs = CrossSessionIntegrator(server.config)
    summary = cs.generate_session_summary(drawers)
    return json.dumps(summary, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_summary"] = handle_session_summary

async def handle_session_bridge(server, drawers, arguments):
    """构建上下文桥接"""
    from ...memory.cross_session import CrossSessionIntegrator
    cs = CrossSessionIntegrator(server.config)
    bridge = cs.build_context_bridge(drawers)
    return json.dumps(bridge, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_bridge"] = handle_session_bridge

async def handle_session_stats(server, drawers, arguments):
    """会话统计"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    return json.dumps(bridge.get_session_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_session_stats"] = handle_session_stats

async def handle_session_inject(server, drawers, arguments):
    """跨会话上下文注入"""
    from ...memory.cross_session import CrossSessionIntegrator
    cs = CrossSessionIntegrator(server.config)
    result = cs.inject_session_context(arguments.get("query", ""), drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_inject"] = handle_session_inject

async def handle_session_start(server, drawers, arguments):
    """记录会话开始"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    result = bridge.start_session(
        arguments["session_id"],
        agent=arguments.get("agent", "claude"),
        description=arguments.get("description", ""),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_start"] = handle_session_start

async def handle_session_end(server, drawers, arguments):
    """记录会话结束并生成摘要"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    result = bridge.end_session(
        arguments["session_id"],
        summary=arguments.get("summary", ""),
        key_events=arguments.get("key_events"),
        files_modified=arguments.get("files_modified"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_end"] = handle_session_end

async def handle_session_resume(server, drawers, arguments):
    """获取上一个会话的恢复上下文"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    result = bridge.get_resume_context(
        agent=arguments.get("agent", "claude"),
        limit=arguments.get("limit", 3),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_resume"] = handle_session_resume

async def handle_session_record(server, drawers, arguments):
    """记录会话中的事件"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    result = bridge.record_event(
        arguments["session_id"],
        arguments["event_type"],
        arguments["detail"],
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_session_record"] = handle_session_record

async def handle_session_stats(server, drawers, arguments):
    """获取会话统计"""
    from ...memory.session_bridge import get_session_bridge
    bridge = get_session_bridge(server.config)
    return json.dumps(bridge.get_session_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_session_stats"] = handle_session_stats

async def handle_autopilot_activate(server, drawers, arguments):
    """激活自动驾驶模式（自动管理记忆）"""
    from ...memory.auto_pilot import get_auto_pilot
    pilot = get_auto_pilot(server.config)
    result = pilot.activate()
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_autopilot_activate"] = handle_autopilot_activate

async def handle_autopilot_deactivate(server, drawers, arguments):
    """停用自动驾驶模式"""
    from ...memory.auto_pilot import get_auto_pilot
    pilot = get_auto_pilot(server.config)
    result = pilot.deactivate()
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_autopilot_deactivate"] = handle_autopilot_deactivate

async def handle_autopilot_tick(server, drawers, arguments):
    """运行一次自动驾驶检查（自动组织/维护/报告）"""
    from ...memory.auto_pilot import get_auto_pilot
    pilot = get_auto_pilot(server.config)
    result = pilot.tick(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_autopilot_tick"] = handle_autopilot_tick

async def handle_autopilot_suggest(server, drawers, arguments):
    """基于当前任务主动推荐相关记忆"""
    from ...memory.auto_pilot import get_auto_pilot
    pilot = get_auto_pilot(server.config)
    result = pilot.auto_suggest(
        context=arguments.get("context", ""),
        drawers=drawers,
        limit=arguments.get("limit", 5),
    )
    try:
        from ...memory.encryption import decrypt
        for s in result.get("suggestions", []):
            c = s.get("content", "")
            if c and c.startswith("gAAAAAB"):
                try:
                    s["content"] = decrypt(c)
                except Exception:
                    pass
    except Exception:
        pass
    return json.dumps(result, ensure_ascii=False, default=str)
HANDLERS["pangu_autopilot_suggest"] = handle_autopilot_suggest

async def handle_autopilot_status(server, drawers, arguments):
    """查看自动驾驶状态"""
    from ...memory.auto_pilot import get_auto_pilot
    pilot = get_auto_pilot(server.config)
    return json.dumps(pilot.get_status(), ensure_ascii=False, indent=2)

HANDLERS["pangu_autopilot_status"] = handle_autopilot_status