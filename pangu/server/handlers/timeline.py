"""盘古 MCP Handler — timeline (16 tools)"""
import json

TOOLS = [
    {"name": "pangu_build_timeline", "description": "\u6784\u5efa\u8bb0\u5fc6\u65f6\u95f4\u7ebf"},
    {"name": "pangu_find_causal_links", "description": "\u53d1\u73b0\u8bb0\u5fc6\u95f4\u7684\u56e0\u679c\u5173\u7cfb"},
    {"name": "pangu_event_chains", "description": "\u6784\u5efa\u4e8b\u4ef6\u94fe\uff08\u65f6\u95f4\u76f8\u8fd1\u7684\u4e8b\u4ef6\u5206\u7ec4\uff09"},
    {"name": "pangu_timeline_query", "description": "\u6309\u65f6\u95f4\u8303\u56f4\u67e5\u8be2\u8bb0\u5fc6"},
    {"name": "pangu_timeline_replay", "description": "\u6309\u65f6\u95f4\u7ebf\u56de\u653e\u8bb0\u5fc6"},
    {"name": "pangu_topic_replay", "description": "\u56f4\u7ed5\u4e3b\u9898\u56de\u653e\u76f8\u5173\u8bb0\u5fc6"},
    {"name": "pangu_highlight_reel", "description": "\u63d0\u53d6\u6700\u91cd\u8981\u7684\u8bb0\u5fc6\u65f6\u523b\uff08\u7cbe\u5f69\u96c6\u9526\uff09"},
    {"name": "pangu_temporal_timeline", "description": "\u6784\u5efa\u65f6\u95f4\u7ebf"},
    {"name": "pangu_temporal_relations", "description": "\u53d1\u73b0\u65f6\u95f4\u5173\u7cfb"},
    {"name": "pangu_temporal_query", "description": "\u6309\u65f6\u95f4\u8303\u56f4\u67e5\u8be2"},
    {"name": "pangu_temporal_stats", "description": "\u83b7\u53d6\u65f6\u95f4\u7edf\u8ba1"},
    {"name": "pangu_causal_discover", "description": "\u53d1\u73b0\u56e0\u679c\u94fe\u63a5"},
    {"name": "pangu_causal_chains", "description": "\u6784\u5efa\u56e0\u679c\u94fe"},
    {"name": "pangu_counterfactual", "description": "\u53cd\u4e8b\u5b9e\u63a8\u7406"},
    {"name": "pangu_root_cause", "description": "\u6839\u56e0\u5206\u6790"},
    {"name": "pangu_causal_stats", "description": "\u56e0\u679c\u63a8\u7406\u7edf\u8ba1"},
]

HANDLERS = {}

async def handle_build_timeline(server, drawers, arguments):
    """构建记忆时间线"""
    from ...memory.timeline import TimelineEngine
    engine = TimelineEngine(server.config)
    wing = arguments.get("wing")
    events = engine.build_timeline(drawers, wing=wing)
    stats = engine.timeline_stats(events)
    return json.dumps({
        "stats": stats,
        "events": [{"id": e.drawer_id, "content": e.content[:150],
                    "timestamp": e.timestamp, "wing": e.wing,
                    "room": e.room, "importance": e.importance}
                   for e in events[:30]],
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_build_timeline"] = handle_build_timeline

async def handle_find_causal_links(server, drawers, arguments):
    """发现记忆间的因果关系"""
    from ...memory.timeline import TimelineEngine
    engine = TimelineEngine(server.config)
    events = engine.build_timeline(drawers)
    links = engine.find_causal_links(events)
    return json.dumps([
        {"source_id": link.source_id, "target_id": link.target_id,
         "confidence": link.confidence, "reason": link.reason,
         "source": link.source_content, "target": link.target_content}
        for link in links[:20]
    ], ensure_ascii=False, indent=2)

HANDLERS["pangu_find_causal_links"] = handle_find_causal_links

async def handle_event_chains(server, drawers, arguments):
    """构建事件链（时间相近的事件分组）"""
    from ...memory.timeline import TimelineEngine
    engine = TimelineEngine(server.config)
    events = engine.build_timeline(drawers)
    chains = engine.build_event_chain(events)
    return json.dumps({
        "total_chains": len(chains),
        "chains": [
            {"id": c.id, "span": c.span, "summary": c.summary,
             "event_count": len(c.events)}
            for c in chains[:10]
        ],
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_event_chains"] = handle_event_chains

async def handle_timeline_query(server, drawers, arguments):
    """按时间范围查询记忆"""
    from ...memory.timeline import TimelineEngine
    engine = TimelineEngine(server.config)
    events = engine.build_timeline(drawers)
    result = engine.query_timeline(
        events,
        start=arguments.get("start"),
        end=arguments.get("end"),
        wing=arguments.get("wing"),
        room=arguments.get("room"),
    )
    return json.dumps([
        {"id": e.drawer_id, "content": e.content[:150],
         "timestamp": e.timestamp, "wing": e.wing, "room": e.room}
        for e in result[:30]
    ], ensure_ascii=False, indent=2)

HANDLERS["pangu_timeline_query"] = handle_timeline_query

async def handle_timeline_replay(server, drawers, arguments):
    """按时间线回放记忆"""
    from ...memory.replay import ReplayEngine
    engine = ReplayEngine(server.config)
    session = engine.timeline_replay(
        drawers,
        start=arguments.get("start"),
        end=arguments.get("end"),
        wing=arguments.get("wing"),
        room=arguments.get("room"),
    )
    return json.dumps({
        "id": session.id, "title": session.title,
        "span": session.span, "event_count": session.event_count,
        "wings": session.wings,
        "key_moments": [
            {"time": m["time"][:16], "content": m["content"][:100],
             "importance": m["importance"]}
            for m in session.key_moments[:5]
        ],
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_timeline_replay"] = handle_timeline_replay

async def handle_topic_replay(server, drawers, arguments):
    """围绕主题回放相关记忆"""
    from ...memory.replay import ReplayEngine
    engine = ReplayEngine(server.config)
    topic = arguments.get("topic", "")
    session = engine.topic_replay(topic, drawers)
    return json.dumps({
        "id": session.id, "title": session.title,
        "span": session.span, "event_count": session.event_count,
        "key_moments": [
            {"time": m["time"][:16], "content": m["content"][:100],
             "importance": m["importance"]}
            for m in session.key_moments[:5]
        ],
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_topic_replay"] = handle_topic_replay

async def handle_highlight_reel(server, drawers, arguments):
    """提取最重要的记忆时刻（精彩集锦）"""
    from ...memory.replay import ReplayEngine
    engine = ReplayEngine(server.config)
    session = engine.highlight_reel(drawers)
    return json.dumps({
        "id": session.id, "title": session.title,
        "event_count": session.event_count,
        "highlights": [
            {"time": m["time"][:16], "content": m["content"][:100],
             "importance": m["importance"]}
            for m in session.key_moments
        ],
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_highlight_reel"] = handle_highlight_reel

async def handle_temporal_timeline(server, drawers, arguments):
    """构建时间线"""
    from ...memory.temporal_reasoning import get_temporal_engine
    te = get_temporal_engine(server.config)
    events = te.build_timeline(drawers)
    return json.dumps({
        "events": [
            {"id": e.memory_id, "content": e.content,
             "timestamp": e.timestamp, "wing": e.wing}
            for e in events
        ],
        "count": len(events),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_temporal_timeline"] = handle_temporal_timeline

async def handle_temporal_relations(server, drawers, arguments):
    """发现时间关系"""
    from ...memory.temporal_reasoning import get_temporal_engine
    te = get_temporal_engine(server.config)
    rels = te.find_temporal_relations(drawers)
    return json.dumps({
        "relations": [
            {"before": r.before_id, "after": r.after_id,
             "relation": r.relation, "confidence": r.confidence}
            for r in rels
        ],
        "count": len(rels),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_temporal_relations"] = handle_temporal_relations

async def handle_temporal_query(server, drawers, arguments):
    """按时间范围查询"""
    from ...memory.temporal_reasoning import get_temporal_engine
    te = get_temporal_engine(server.config)
    start = arguments.get("start")
    end = arguments.get("end")
    results = te.query_by_time_range(drawers, start, end)
    return json.dumps({
        "results": [{"id": d.id, "content": d.content[:80]} for d in results],
        "count": len(results),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_temporal_query"] = handle_temporal_query

async def handle_temporal_stats(server, drawers, arguments):
    """获取时间统计"""
    from ...memory.temporal_reasoning import get_temporal_engine
    te = get_temporal_engine(server.config)
    return json.dumps(te.get_temporal_stats(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_temporal_stats"] = handle_temporal_stats

async def handle_causal_discover(server, drawers, arguments):
    """发现因果链接"""
    from ...memory.causal_reasoning import get_causal_engine
    cr = get_causal_engine(server.config)
    links = cr.discover_causal_links(drawers)
    return json.dumps({
        "links": [
            {"cause": l.cause_text[:50], "effect": l.effect_text[:50],
             "type": l.relation_type, "confidence": l.confidence}
            for l in links
        ],
        "count": len(links),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_causal_discover"] = handle_causal_discover

async def handle_causal_chains(server, drawers, arguments):
    """构建因果链"""
    from ...memory.causal_reasoning import get_causal_engine
    cr = get_causal_engine(server.config)
    cr.discover_causal_links(drawers)
    chains = cr.build_causal_chains()
    return json.dumps({
        "chains": [
            {"id": c.chain_id, "root": c.root_cause[:50],
             "effect": c.final_effect[:50], "length": c.chain_length,
             "confidence": c.overall_confidence}
            for c in chains
        ],
        "count": len(chains),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_causal_chains"] = handle_causal_chains

async def handle_counterfactual(server, drawers, arguments):
    """反事实推理"""
    from ...memory.causal_reasoning import get_causal_engine
    cr = get_causal_engine(server.config)
    cr.discover_causal_links(drawers)
    result = cr.counterfactual_reasoning(
        arguments["cause_id"], arguments["counterfactual"], drawers,
    )
    return json.dumps({
        "original": result.original_cause,
        "counterfactual": result.counterfactual,
        "predicted_effect": result.predicted_effect,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_counterfactual"] = handle_counterfactual

async def handle_root_cause(server, drawers, arguments):
    """根因分析"""
    from ...memory.causal_reasoning import get_causal_engine
    cr = get_causal_engine(server.config)
    cr.discover_causal_links(drawers)
    result = cr.root_cause_analysis(arguments["effect_text"], drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_root_cause"] = handle_root_cause

async def handle_causal_stats(server, drawers, arguments):
    """因果推理统计"""
    from ...memory.causal_reasoning import get_causal_engine
    cr = get_causal_engine(server.config)
    return json.dumps(cr.get_causal_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_causal_stats"] = handle_causal_stats