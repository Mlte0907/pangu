"""盘古 MCP Handler — llm_tools (19 tools)"""
import json
from ...core.llm import LLMEngine

TOOLS = [
    {"name": "pangu_summarize", "description": "\u603b\u7ed3\u8bb0\u5fc6"},
    {"name": "pangu_classify", "description": "LMM \u5206\u7c7b\u8bb0\u5fc6"},
    {"name": "pangu_insight", "description": "\u4ece\u8bb0\u5fc6\u4e2d\u63d0\u53d6\u6d1e\u5bdf"},
    {"name": "pangu_deep_emotion_trajectory", "description": "\u60c5\u7eea\u8f68\u8ff9\u8ffd\u8e2a\uff08\u901f\u5ea6/\u52a0\u901f\u5ea6/\u8d8b\u52bf\uff09"},
    {"name": "pangu_deep_emotion_decompose", "description": "\u6df7\u5408\u60c5\u7eea\u89e3\u8026\uff08\u8bc6\u522b\u590d\u6742\u60c5\u7eea\u4e2d\u7684\u591a\u4e2a\u6210\u5206\uff09"},
    {"name": "pangu_deep_emotion_stats", "description": "\u83b7\u53d6\u6df1\u5ea6\u60c5\u7eea\u7edf\u8ba1"},
    {"name": "pangu_debate_run", "description": "\u8fd0\u884c\u591a\u7b56\u7565\u8fa9\u8bba\uff08\u5206\u6790/\u521b\u610f/\u4fdd\u5b88\u4e09\u7b56\u7565\u8bc4\u5206\u9009\u4f18\uff09"},
    {"name": "pangu_debate_stats", "description": "\u83b7\u53d6\u8fa9\u8bba\u7edf\u8ba1"},
    {"name": "pangu_narrative_generate", "description": "\u751f\u6210\u8bb0\u5fc6\u53d9\u4e8b\uff08\u6309Wing\u805a\u5408\u4e3a\u8fde\u8d2f\u53d9\u4e8b\u7ebf\uff09"},
    {"name": "pangu_narrative_themes", "description": "\u63d0\u53d6\u8bb0\u5fc6\u4e3b\u9898"},
    {"name": "pangu_narrative_identity", "description": "\u751f\u6210\u8eab\u4efd\u8fde\u7eed\u6027\u53d9\u4e8b"},
    {"name": "pangu_llm_cache_stats", "description": "\u83b7\u53d6 LLM \u7f13\u5b58\u7edf\u8ba1\uff08\u547d\u4e2d\u3001token\u3001\u6210\u672c\u3001\u78c1\u76d8\uff09"},
    {"name": "pangu_llm_cache_top", "description": "\u83b7\u53d6\u8bbf\u95ee\u6700\u9891\u7e41\u7684\u7f13\u5b58\u952e"},
    {"name": "pangu_llm_cache_clear", "description": "\u6e05\u7a7a LLM \u7f13\u5b58\uff08\u5185\u5b58/\u78c1\u76d8\uff09"},
    {"name": "pangu_llm_cache_metrics", "description": "\u5bfc\u51fa Prometheus \u683c\u5f0f LLM \u7f13\u5b58\u6307\u6807"},
    {"name": "pangu_llm_cache_warmup", "description": "\u9884\u70ed LLM \u7f13\u5b58\uff08\u6309 prompt \u5217\u8868\u6279\u91cf\u586b\u5145\uff09"},
    {"name": "pangu_llm_cache_warmup_log", "description": "\u67e5\u770b LLM \u7f13\u5b58\u9884\u70ed\u5ba1\u8ba1\u65e5\u5fd7"},
    {"name": "pangu_llm_cache_vacuum", "description": "\u5bf9\u6301\u4e45\u5316\u7f13\u5b58\u6267\u884c VACUUM\uff0c\u91ca\u653e SQLite \u788e\u7247\u7a7a\u95f4"},
    {"name": "pangu_llm_cache_config", "description": "\u67e5\u770b\u5f53\u524d LLM \u7f13\u5b58\u76f8\u5173\u914d\u7f6e"},
]

HANDLERS = {}

async def handle_summarize(server, drawers, arguments):
    """总结记忆"""
    memories = [
        {"content": d.content, "wing": d.wing, "room": d.room}
        for d in drawers[:20]
    ]
    return await server.llm.summarize_memories(memories)

HANDLERS["pangu_summarize"] = handle_summarize

async def handle_classify(server, drawers, arguments):
    """LMM 分类记忆"""
    content = arguments.get("content", "")
    result = await server.llm.classify_memory(content)
    return json.dumps(result, ensure_ascii=False)

HANDLERS["pangu_classify"] = handle_classify

async def handle_insight(server, drawers, arguments):
    """从记忆中提取洞察"""
    related = server.search.search(
        arguments.get("topic", ""), drawers
    ) if arguments.get("topic") else [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:5]]
    return await server.llm.generate_insight(related)

HANDLERS["pangu_insight"] = handle_insight

async def handle_deep_emotion_trajectory(server, drawers, arguments):
    """情绪轨迹追踪（速度/加速度/趋势）"""
    from ...memory.deep_emotion import get_deep_emotion_engine
    engine = get_deep_emotion_engine(server.config)
    return json.dumps(engine.analyze_trajectory(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_deep_emotion_trajectory"] = handle_deep_emotion_trajectory

async def handle_deep_emotion_decompose(server, drawers, arguments):
    """混合情绪解耦（识别复杂情绪中的多个成分）"""
    from ...memory.deep_emotion import get_deep_emotion_engine
    engine = get_deep_emotion_engine(server.config)
    return json.dumps(engine.decompose_emotions(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_deep_emotion_decompose"] = handle_deep_emotion_decompose

async def handle_deep_emotion_stats(server, drawers, arguments):
    """获取深度情绪统计"""
    from ...memory.deep_emotion import get_deep_emotion_engine
    engine = get_deep_emotion_engine(server.config)
    return json.dumps(engine.get_stats(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_deep_emotion_stats"] = handle_deep_emotion_stats

async def handle_debate_run(server, drawers, arguments):
    """运行多策略辩论（分析/创意/保守三策略评分选优）"""
    from ...memory.debate import get_debate_engine
    engine = get_debate_engine(server.config)
    result = engine.run_debate(
        question=arguments.get("question", ""),
        strategies_count=arguments.get("strategies_count", 2),
        context=arguments.get("context", ""),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_debate_run"] = handle_debate_run

async def handle_debate_stats(server, drawers, arguments):
    """获取辩论统计"""
    from ...memory.debate import get_debate_engine
    engine = get_debate_engine(server.config)
    return json.dumps(engine.get_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_debate_stats"] = handle_debate_stats

async def handle_narrative_generate(server, drawers, arguments):
    """生成记忆叙事（按Wing聚合为连贯叙事线）"""
    from ...memory.narrative import get_narrative_engine
    engine = get_narrative_engine(server.config)
    return json.dumps(engine.generate_narrative(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_narrative_generate"] = handle_narrative_generate

async def handle_narrative_themes(server, drawers, arguments):
    """提取记忆主题"""
    from ...memory.narrative import get_narrative_engine
    engine = get_narrative_engine(server.config)
    return json.dumps(engine.extract_themes(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_narrative_themes"] = handle_narrative_themes

async def handle_narrative_identity(server, drawers, arguments):
    """生成身份连续性叙事"""
    from ...memory.narrative import get_narrative_engine
    engine = get_narrative_engine(server.config)
    return json.dumps(engine.identity_statement(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_narrative_identity"] = handle_narrative_identity

async def handle_llm_cache_stats(server, drawers, arguments):
    """获取 LLM 缓存统计（命中、token、成本、磁盘）"""
    return json.dumps(server.llm.get_stats(), ensure_ascii=False)

HANDLERS["pangu_llm_cache_stats"] = handle_llm_cache_stats

async def handle_llm_cache_top(server, drawers, arguments):
    """获取访问最频繁的缓存键"""
    limit = int(arguments.get("limit", 10))
    if server._persistent_cache is None:
        return json.dumps({"error": "persistent cache disabled"}, ensure_ascii=False)
    return json.dumps(
        server._persistent_cache.get_top_keys(limit),
        ensure_ascii=False,
    )

HANDLERS["pangu_llm_cache_top"] = handle_llm_cache_top

async def handle_llm_cache_clear(server, drawers, arguments):
    """清空 LLM 缓存（内存/磁盘）"""
    cleared = {"memory": 0, "persistent": 0}
    if arguments.get("memory", True):
        cleared["memory"] = server.llm.clear_cache()
    if arguments.get("persistent", False):
        cleared["persistent"] = server.llm.clear_persistent_cache()
    return json.dumps({"status": "cleared", **cleared}, ensure_ascii=False)

HANDLERS["pangu_llm_cache_clear"] = handle_llm_cache_clear

async def handle_llm_cache_metrics(server, drawers, arguments):
    """导出 Prometheus 格式 LLM 缓存指标"""
    return server.llm.export_prometheus_metrics()

HANDLERS["pangu_llm_cache_metrics"] = handle_llm_cache_metrics

async def handle_llm_cache_warmup(server, drawers, arguments):
    """预热 LLM 缓存（按 prompt 列表批量填充）"""
    prompts = arguments.get("prompts") or []
    concurrency = int(arguments.get("concurrency", 3))
    skip_existing = bool(arguments.get("skip_existing", True))
    result = await server.llm.warmup_cache(
        prompts, concurrency=concurrency, skip_existing=skip_existing
    )
    return json.dumps(result, ensure_ascii=False)

HANDLERS["pangu_llm_cache_warmup"] = handle_llm_cache_warmup

async def handle_llm_cache_warmup_log(server, drawers, arguments):
    """查看 LLM 缓存预热审计日志"""
    limit = int(arguments.get("limit", 20))
    log_path = arguments.get("log_path", "")
    records = LLMEngine.get_warmup_history(log_path=log_path, limit=limit)
    return json.dumps({"count": len(records), "records": records}, ensure_ascii=False)

HANDLERS["pangu_llm_cache_warmup_log"] = handle_llm_cache_warmup_log

async def handle_llm_cache_vacuum(server, drawers, arguments):
    """对持久化缓存执行 VACUUM，释放 SQLite 碎片空间"""
    return json.dumps(
        server.llm.vacuum_persistent_cache(), ensure_ascii=False
    )

HANDLERS["pangu_llm_cache_vacuum"] = handle_llm_cache_vacuum

async def handle_llm_cache_config(server, drawers, arguments):
    """查看当前 LLM 缓存相关配置"""
    cfg_keys = [
        "llm_cache_enabled", "llm_cache_max", "llm_cache_persist",
        "llm_cache_persist_path", "llm_cache_ttl_days", "llm_cache_max_disk_mb",
        "llm_cache_write_throttle", "llm_cache_warmup_on_start",
        "llm_cache_warmup_prompts", "llm_cache_vacuum_on_start",
        "llm_cache_vacuum_interval_hours",
    ]
    return json.dumps(
        {k: getattr(server.config, k, None) for k in cfg_keys},
        ensure_ascii=False,
    )

HANDLERS["pangu_llm_cache_config"] = handle_llm_cache_config