"""盘古 MCP Handler — consolidation (32 tools)"""

import json

from ...memory.distill_enhanced import DistillationTower

TOOLS = [
    {
        "name": "pangu_consolidation_stats",
        "description": "\u83b7\u53d6\u8bb0\u5fc6\u5de9\u56fa\u7edf\u8ba1\uff08\u9057\u5fd8/\u590d\u4e60/\u538b\u7f29\u72b6\u6001\uff09",
    },
    {
        "name": "pangu_find_forgotten",
        "description": "\u627e\u51fa\u5e94\u88ab\u9057\u5fd8\u7684\u4f4e\u91cd\u8981\u6027\u8bb0\u5fc6",
    },
    {
        "name": "pangu_compress_memories",
        "description": "\u4f7f\u7528 LMM \u538b\u7f29\u65e7\u8bb0\u5fc6\u4e3a\u7cbe\u7b80\u6458\u8981",
    },
    {
        "name": "pangu_detect_associations",
        "description": "LMM \u81ea\u52a8\u68c0\u6d4b\u8bb0\u5fc6\u7247\u6bb5\u4e4b\u95f4\u7684\u5173\u8054",
    },
    {
        "name": "pangu_memory_importance",
        "description": "\u8ba1\u7b97\u6307\u5b9a\u8bb0\u5fc6\u7684\u7efc\u5408\u91cd\u8981\u6027\u8bc4\u5206",
    },
    {
        "name": "pangu_fuse_topic",
        "description": "\u878d\u5408\u540c\u4e00\u4e3b\u9898\u7684\u8bb0\u5fc6\u4e3a\u7ed3\u6784\u5316\u7406\u89e3",
    },
    {
        "name": "pangu_progressive_summarize",
        "description": "\u6e10\u8fdb\u5f0f\u6458\u8981\uff08\u4ece\u7ec6\u8282\u5230\u62bd\u8c61\uff09",
    },
    {
        "name": "pangu_crystallize_knowledge",
        "description": "\u4ece\u8bb0\u5fc6\u4e2d\u7ed3\u6676\u53ef\u590d\u7528\u77e5\u8bc6",
    },
    {
        "name": "pangu_distill_knowledge",
        "description": "\u4ece\u8bb0\u5fc6\u4e2d\u84b8\u998f\u7ed3\u6784\u5316\u77e5\u8bc6\u5361\u7247",
    },
    {"name": "pangu_distill_causal_chains", "description": "\u63d0\u53d6\u6240\u6709\u56e0\u679c\u94fe"},
    {"name": "pangu_distill_graph", "description": "\u83b7\u53d6\u77e5\u8bc6\u5173\u8054\u56fe"},
    {"name": "pangu_distill_stats", "description": "\u83b7\u53d6\u84b8\u998f\u7edf\u8ba1"},
    {
        "name": "pangu_importance_feedback",
        "description": "\u6839\u636e\u53cd\u9988\u4fe1\u53f7\u52a8\u6001\u8c03\u6574\u8bb0\u5fc6\u91cd\u8981\u6027",
    },
    {
        "name": "pangu_auto_fusion",
        "description": "\u89e6\u53d1\u81ea\u52a8\u8bb0\u5fc6\u878d\u5408\uff08\u540c\u4e3b\u9898>=3\u6761\uff09",
    },
    {
        "name": "pangu_validate_memories",
        "description": "\u9a8c\u8bc1\u6240\u6709\u8bb0\u5fc6\u7684\u51c6\u786e\u6027\u548c\u65f6\u6548\u6027",
    },
    {
        "name": "pangu_proactive_predict",
        "description": "\u57fa\u4e8e\u4e0a\u4e0b\u6587\u9884\u6d4b\u76f8\u5173\u8bb0\u5fc6",
    },
    {
        "name": "pangu_proactive_suggest",
        "description": "\u57fa\u4e8e\u5f53\u524d\u4e0a\u4e0b\u6587\u4e3b\u52a8\u63a8\u8350\u8bb0\u5fc6",
    },
    {"name": "pangu_context_status", "description": "\u83b7\u53d6\u5f53\u524d\u4e0a\u4e0b\u6587\u72b6\u6001"},
    {
        "name": "pangu_resonance_find",
        "description": "\u53d1\u73b0\u60c5\u611f/\u8bed\u4e49\u5171\u9e23\u7684\u8bb0\u5fc6\u5bf9\u5e76\u6784\u5efa\u56fe\u8c31\u8fb9",
    },
    {"name": "pangu_resonance_edges", "description": "\u4e3a\u5171\u9e23\u5339\u914d\u5efa\u7acb\u56fe\u8c31\u8fb9"},
    {"name": "pangu_resonance_stats", "description": "\u83b7\u53d6\u5171\u9e23\u5339\u914d\u7edf\u8ba1"},
    {
        "name": "pangu_intent_predict",
        "description": "\u4ece\u8bb0\u5fc6\u884c\u4e3a\u5e8f\u5217\u63a8\u65ad\u5f53\u524d\u7528\u6237\u610f\u56fe",
    },
    {
        "name": "pangu_intent_tasks",
        "description": "\u4efb\u52a1\u94fe\u8ffd\u8e2a \u2014 \u8ddf\u8e2a\u591a\u6b65\u9aa4\u4efb\u52a1\u8fdb\u5ea6",
    },
    {"name": "pangu_intent_stats", "description": "\u83b7\u53d6\u610f\u56fe\u9884\u6d4b\u7edf\u8ba1"},
    {
        "name": "pangu_synthesis_cross_cluster",
        "description": "\u8de8\u96c6\u7fa4\u8054\u60f3 \u2014 \u53d1\u73b0\u4e0d\u540cWing\u95f4\u7684\u77e5\u8bc6\u5173\u8054",
    },
    {
        "name": "pangu_synthesis_gaps",
        "description": "\u77e5\u8bc6\u7f3a\u53e3\u8bc6\u522b \u2014 \u627e\u51fa\u7f3a\u5c11\u6df1\u5ea6\u5206\u6790\u7684\u4e3b\u9898",
    },
    {"name": "pangu_forget_stats", "description": "\u9057\u5fd8\u7edf\u8ba1"},
    {"name": "pangu_consolidation_stats", "description": "\u5de9\u56fa\u7edf\u8ba1"},
    {"name": "pangu_distill", "description": "\u84b8\u998f\u6240\u6709\u8bb0\u5fc6\u4e3a\u7cbe\u70bc\u77e5\u8bc6"},
    {"name": "pangu_distill_by_wing", "description": "\u6309\u9886\u57df\u84b8\u998f"},
    {"name": "pangu_distillation_stats", "description": "\u84b8\u998f\u7edf\u8ba1"},
    {
        "name": "pangu_auto_inject",
        "description": "\u57fa\u4e8e\u5f53\u524d\u4e0a\u4e0b\u6587\u81ea\u52a8\u6ce8\u5165\u6700\u76f8\u5173\u7684\u8bb0\u5fc6",
    },
]

HANDLERS = {}


async def handle_consolidation_stats(server, drawers, arguments):
    """获取记忆巩固统计（遗忘/复习/压缩状态）"""
    from ...memory.consolidation_intelligence import get_consolidation_intel
    from ...memory.lifecycle import LifecycleManager

    ci = get_consolidation_intel(server.config)
    stats = ci.get_consolidation_stats()
    # 同时从 LifecycleManager 读取 last_consolidation
    lifecycle = LifecycleManager(server.config)
    stats["last_consolidation"] = lifecycle._last_consolidation if lifecycle._last_consolidation else None
    return json.dumps(stats, ensure_ascii=False, indent=2)


HANDLERS["pangu_consolidation_stats"] = handle_consolidation_stats


async def handle_find_forgotten(server, drawers, arguments):
    """找出应被遗忘的低重要性记忆"""
    forgotten = server.memory.find_forgotten()
    return json.dumps([d.to_dict() for d in forgotten], ensure_ascii=False, indent=2)


HANDLERS["pangu_find_forgotten"] = handle_find_forgotten


async def handle_compress_memories(server, drawers, arguments):
    """使用 LMM 压缩旧记忆为精简摘要"""
    compressible = server.memory.find_compressible()
    if not compressible:
        return json.dumps({"status": "nothing to compress"})
    memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in compressible]
    result = await server.llm.compress_memories(memories, target_count=arguments.get("target_count", 5))
    return json.dumps({"status": "compressed", "result": result}, ensure_ascii=False)


HANDLERS["pangu_compress_memories"] = handle_compress_memories


async def handle_detect_associations(server, drawers, arguments):
    """LMM 自动检测记忆片段之间的关联"""
    memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:20]]
    result = await server.llm.detect_associations(memories)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_detect_associations"] = handle_detect_associations


async def handle_memory_importance(server, drawers, arguments):
    """计算指定记忆的综合重要性评分"""
    drawer_id = arguments.get("drawer_id", "")
    importance = server.memory.get_memory_importance(drawer_id)
    return json.dumps({"drawer_id": drawer_id, "importance": importance}, ensure_ascii=False)


HANDLERS["pangu_memory_importance"] = handle_memory_importance


async def handle_fuse_topic(server, drawers, arguments):
    """融合同一主题的记忆为结构化理解"""
    from ...memory.fusion import FusionEngine

    engine = FusionEngine(server.config)
    topic = arguments.get("topic", "")
    fused = engine.fuse_topic(topic, drawers)
    if fused:
        return json.dumps(
            {
                "id": fused.id,
                "topic": fused.topic,
                "summary": fused.summary,
                "key_points": fused.key_points,
                "confidence": fused.confidence,
                "contradictions": fused.contradictions,
                "source_count": len(fused.source_memories),
            },
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps({"status": "no relevant memories found"})


HANDLERS["pangu_fuse_topic"] = handle_fuse_topic


async def handle_progressive_summarize(server, drawers, arguments):
    """渐进式摘要（从细节到抽象）"""
    from ...memory.fusion import FusionEngine

    engine = FusionEngine(server.config)
    result = engine.progressive_summarize(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_progressive_summarize"] = handle_progressive_summarize


async def handle_crystallize_knowledge(server, drawers, arguments):
    """从记忆中结晶可复用知识"""
    from ...memory.fusion import FusionEngine

    engine = FusionEngine(server.config)
    topic = arguments.get("topic", "")
    knowledge = engine.crystallize_knowledge(drawers, topic=topic)
    return json.dumps({k: len(v) for k, v in knowledge.items()}, ensure_ascii=False, indent=2)


HANDLERS["pangu_crystallize_knowledge"] = handle_crystallize_knowledge


async def handle_distill_knowledge(server, drawers, arguments):
    """从记忆中蒸馏结构化知识卡片"""
    tower = DistillationTower(server.config)
    texts = arguments.get("texts", [])
    source_ids = arguments.get("source_ids", [])
    if not texts:
        texts = [d.content for d in drawers[:10]]
    card = tower.distill(texts, source_ids=source_ids)
    return json.dumps(card, ensure_ascii=False, indent=2)


HANDLERS["pangu_distill_knowledge"] = handle_distill_knowledge


async def handle_distill_causal_chains(server, drawers, arguments):
    """提取所有因果链"""
    tower = DistillationTower(server.config)
    chains = tower.get_causal_chains()
    return json.dumps(chains, ensure_ascii=False, indent=2)


HANDLERS["pangu_distill_causal_chains"] = handle_distill_causal_chains


async def handle_distill_graph(server, drawers, arguments):
    """获取知识关联图"""
    tower = DistillationTower(server.config)
    graph = tower.get_knowledge_graph()
    return json.dumps(graph, ensure_ascii=False, indent=2)


HANDLERS["pangu_distill_graph"] = handle_distill_graph


async def handle_distill_stats(server, drawers, arguments):
    """获取蒸馏统计"""
    tower = DistillationTower(server.config)
    return json.dumps(tower.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_distill_stats"] = handle_distill_stats


async def handle_importance_feedback(server, drawers, arguments):
    """根据反馈信号动态调整记忆重要性"""
    from ...memory.retrieval import importance_feedback

    result = importance_feedback(
        arguments["drawer_id"],
        arguments["signal"],
        drawers,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_importance_feedback"] = handle_importance_feedback


async def handle_auto_fusion(server, drawers, arguments):
    """触发自动记忆融合（同主题>=3条）"""
    from ...lifecycle import LifecycleManager

    mgr = LifecycleManager(server.config)
    result = mgr.run_auto_fusion()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_auto_fusion"] = handle_auto_fusion


async def handle_validate_memories(server, drawers, arguments):
    """验证所有记忆的准确性和时效性"""
    from ...memory.memory_validator import MemoryValidator

    validator = MemoryValidator(server.config)
    result = validator.validate_all(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_validate_memories"] = handle_validate_memories


async def handle_proactive_predict(server, drawers, arguments):
    """基于上下文预测相关记忆"""
    from ...memory.proactive import get_proactive_engine

    engine = get_proactive_engine(server.config)
    context = arguments.get("context", "")
    limit = arguments.get("limit", 5)
    predictions = engine.predict(context, drawers, limit)
    return json.dumps(
        {
            "predictions": [
                {"id": p.memory_id, "content": p.content, "score": p.relevance_score, "reason": p.reason}
                for p in predictions
            ],
            "count": len(predictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_proactive_predict"] = handle_proactive_predict


async def handle_proactive_suggest(server, drawers, arguments):
    """基于当前上下文主动推荐记忆"""
    from ...memory.proactive import get_proactive_engine

    engine = get_proactive_engine(server.config)
    context = engine.get_context()
    limit = arguments.get("limit", 5)
    predictions = engine.predict(context, drawers, limit)
    return json.dumps(
        {
            "context": context[:100] if context else "",
            "predictions": [
                {"id": p.memory_id, "content": p.content, "score": p.relevance_score, "reason": p.reason}
                for p in predictions
            ],
            "count": len(predictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_proactive_suggest"] = handle_proactive_suggest


async def handle_context_status(server, drawers, arguments):
    """获取当前上下文状态"""
    from ...memory.proactive import get_proactive_engine

    engine = get_proactive_engine(server.config)
    context = engine.get_context()
    return json.dumps(
        {
            "context": context[:200] if context else "",
            "context_length": len(context),
            "history_size": len(engine._context_history),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_context_status"] = handle_context_status


async def handle_resonance_find(server, drawers, arguments):
    """发现情感/语义共鸣的记忆对并构建图谱边"""
    from ...memory.resonance import get_resonance_engine

    engine = get_resonance_engine(server.config)
    matches = engine.find_resonance(
        drawers,
        limit=arguments.get("limit", 30),
        sim_threshold=arguments.get("sim_threshold", 0.7),
    )
    edges = engine.build_edges(matches, drawers)
    return json.dumps(
        {
            "matches": matches,
            "edges_created": len(edges),
            "total_matches": len(matches),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_resonance_find"] = handle_resonance_find


async def handle_resonance_edges(server, drawers, arguments):
    """为共鸣匹配建立图谱边"""
    from ...memory.resonance import get_resonance_engine

    engine = get_resonance_engine(server.config)
    matches = arguments.get("matches", [])
    edges = engine.build_edges(
        matches,
        drawers,
        max_edges=arguments.get("max_edges", 5),
    )
    return json.dumps({"edges": edges, "count": len(edges)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_resonance_edges"] = handle_resonance_edges


async def handle_resonance_stats(server, drawers, arguments):
    """获取共鸣匹配统计"""
    from ...memory.resonance import get_resonance_engine

    engine = get_resonance_engine(server.config)
    return json.dumps(engine.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_resonance_stats"] = handle_resonance_stats


async def handle_intent_predict(server, drawers, arguments):
    """从记忆行为序列推断当前用户意图"""
    from ...memory.intent_prediction import get_intent_predictor

    predictor = get_intent_predictor(server.config)
    intent = predictor.predict_intent(drawers, arguments.get("context", ""))
    task_chain = predictor.track_task_chain(drawers)
    suggestions = predictor.suggest_next(drawers, intent, task_chain)
    return json.dumps(
        {
            "intent": intent,
            "task_chain": task_chain,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_intent_predict"] = handle_intent_predict


async def handle_intent_tasks(server, drawers, arguments):
    """任务链追踪 — 跟踪多步骤任务进度"""
    from ...memory.intent_prediction import get_intent_predictor

    predictor = get_intent_predictor(server.config)
    task_chain = predictor.track_task_chain(drawers)
    return json.dumps(task_chain, ensure_ascii=False, indent=2)


HANDLERS["pangu_intent_tasks"] = handle_intent_tasks


async def handle_intent_stats(server, drawers, arguments):
    """获取意图预测统计"""
    from ...memory.intent_prediction import get_intent_predictor

    predictor = get_intent_predictor(server.config)
    return json.dumps(predictor.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_intent_stats"] = handle_intent_stats


async def handle_synthesis_cross_cluster(server, drawers, arguments):
    """跨集群联想 — 发现不同Wing间的知识关联"""
    from ...memory.knowledge_synthesis import get_synthesizer

    ks = get_synthesizer(server.config)
    insights = ks.cross_cluster_association(drawers)
    return json.dumps({"insights": insights, "count": len(insights)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_synthesis_cross_cluster"] = handle_synthesis_cross_cluster


async def handle_synthesis_gaps(server, drawers, arguments):
    """知识缺口识别 — 找出缺少深度分析的主题"""
    from ...memory.knowledge_synthesis import get_synthesizer

    ks = get_synthesizer(server.config)
    gaps = ks.knowledge_gap_detection(drawers)
    return json.dumps({"gaps": gaps, "count": len(gaps)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_synthesis_gaps"] = handle_synthesis_gaps


async def handle_forget_stats(server, drawers, arguments):
    """遗忘统计"""
    from ...memory.adaptive_forgetting import get_forgetting

    af = get_forgetting(server.config)
    return json.dumps(af.get_forgetting_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_forget_stats"] = handle_forget_stats


async def handle_consolidation_stats(server, drawers, arguments):
    """巩固统计"""
    from ...memory.consolidation_intelligence import get_consolidation_intel
    from ...memory.lifecycle import LifecycleManager

    ci = get_consolidation_intel(server.config)
    stats = ci.get_consolidation_stats()
    # 同时从 LifecycleManager 读取 last_consolidation
    lifecycle = LifecycleManager(server.config)
    stats["last_consolidation"] = lifecycle._last_consolidation if lifecycle._last_consolidation else None
    return json.dumps(stats, ensure_ascii=False, indent=2)


HANDLERS["pangu_consolidation_stats"] = handle_consolidation_stats


async def handle_distill(server, drawers, arguments):
    """蒸馏所有记忆为精炼知识"""
    from ...memory.distillation import get_distiller

    d = get_distiller(server.config)
    min_size = arguments.get("min_group_size", 2)
    report = d.distill_all(drawers, min_size)
    return json.dumps(
        {
            "input": report.input_count,
            "output": report.output_count,
            "tokens_saved": report.tokens_saved,
            "avg_confidence": report.avg_confidence,
            "distilled": [
                {"summary": dk.summary[:100], "keywords": dk.keywords, "wing": dk.wing, "confidence": dk.confidence}
                for dk in report.distilled[:10]
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_distill"] = handle_distill


async def handle_distill_by_wing(server, drawers, arguments):
    """按领域蒸馏"""
    from ...memory.distillation import get_distiller

    d = get_distiller(server.config)
    result = d.distill_by_wing(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_distill_by_wing"] = handle_distill_by_wing


async def handle_distillation_stats(server, drawers, arguments):
    """蒸馏统计"""
    from ...memory.distillation import get_distiller

    d = get_distiller(server.config)
    return json.dumps(d.get_distillation_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_distillation_stats"] = handle_distillation_stats


async def handle_auto_inject(server, drawers, arguments):
    """基于当前上下文自动注入最相关的记忆"""
    from ...memory.context_injector import get_context_injector

    injector = get_context_injector(server.config)
    result = injector.auto_inject(
        context=arguments.get("context", ""),
        drawers=drawers,
        limit=arguments.get("limit", 5),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_auto_inject"] = handle_auto_inject
