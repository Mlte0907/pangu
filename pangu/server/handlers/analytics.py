"""盘古 MCP Handler — analytics (37 tools)"""

import json

TOOLS = [
    {"name": "pangu_analyze", "description": "\u751f\u6210\u5168\u9762\u8bb0\u5fc6\u5206\u6790\u62a5\u544a"},
    {"name": "pangu_health_check", "description": "\u68c0\u67e5\u8bb0\u5fc6\u7cfb\u7edf\u5065\u5eb7\u5ea6"},
    {"name": "pangu_anomaly_detect", "description": "\u68c0\u6d4b\u8bb0\u5fc6\u7cfb\u7edf\u5f02\u5e38"},
    {"name": "pangu_growth_trend", "description": "\u5206\u6790\u8bb0\u5fc6\u589e\u957f\u8d8b\u52bf"},
    {
        "name": "pangu_discover_patterns",
        "description": "\u53d1\u73b0\u8bb0\u5fc6\u4e2d\u7684\u9690\u85cf\u6a21\u5f0f\u548c\u89c4\u5f8b",
    },
    {"name": "pangu_pattern_insights", "description": "\u4ece\u6a21\u5f0f\u4e2d\u63d0\u53d6\u6d1e\u5bdf"},
    {"name": "pangu_analyze_emotion", "description": "\u5206\u6790\u6587\u672c\u60c5\u7eea"},
    {"name": "pangu_emotion_stats", "description": "\u83b7\u53d6\u60c5\u611f\u7edf\u8ba1"},
    {"name": "pangu_predict_emotion", "description": "\u9884\u6d4b\u7528\u6237\u60c5\u7eea"},
    {"name": "pangu_discover_patterns", "description": "\u53d1\u73b0\u8bb0\u5fc6\u4e2d\u7684\u6a21\u5f0f"},
    {
        "name": "pangu_discover_knowledge",
        "description": "\u4ece\u8bb0\u5fc6\u4e2d\u81ea\u52a8\u53d1\u73b0\u65b0\u77e5\u8bc6",
    },
    {"name": "pangu_generate_hypotheses", "description": "\u57fa\u4e8e\u8bb0\u5fc6\u751f\u6210\u5047\u8bbe"},
    {"name": "pangu_learning_stats", "description": "\u83b7\u53d6\u81ea\u4e3b\u5b66\u4e60\u7edf\u8ba1"},
    {"name": "pangu_self_diagnose", "description": "\u7cfb\u7edf\u81ea\u6211\u8bca\u65ad"},
    {"name": "pangu_evolution_plan", "description": "\u751f\u6210\u8fdb\u5316\u8ba1\u5212"},
    {"name": "pangu_performance_trend", "description": "\u67e5\u770b\u6027\u80fd\u8d8b\u52bf"},
    {"name": "pangu_evolution_stats", "description": "\u83b7\u53d6\u8fdb\u5316\u7edf\u8ba1"},
    {"name": "pangu_anomaly_scan", "description": "\u5168\u9762\u5f02\u5e38\u626b\u63cf"},
    {"name": "pangu_anomaly_content", "description": "\u5185\u5bb9\u5f02\u5e38\u68c0\u6d4b"},
    {"name": "pangu_anomaly_stats", "description": "\u5f02\u5e38\u68c0\u6d4b\u7edf\u8ba1"},
    {"name": "pangu_predict_queries", "description": "\u9884\u6d4b\u7528\u6237\u4e0b\u4e00\u6b65\u67e5\u8be2"},
    {"name": "pangu_predict_forgetting", "description": "\u9884\u6d4b\u5373\u5c06\u9057\u5fd8\u7684\u8bb0\u5fc6"},
    {"name": "pangu_growth_trend", "description": "\u5206\u6790\u589e\u957f\u8d8b\u52bf"},
    {"name": "pangu_hot_topics", "description": "\u9884\u6d4b\u70ed\u70b9\u4e3b\u9898"},
    {"name": "pangu_predictive_stats", "description": "\u9884\u6d4b\u5206\u6790\u7edf\u8ba1"},
    {"name": "pangu_meta_observe", "description": "\u8bb0\u5f55\u6027\u80fd\u89c2\u5bdf"},
    {"name": "pangu_meta_recommend", "description": "\u63a8\u8350\u6700\u4f18\u7b56\u7565"},
    {"name": "pangu_meta_tune", "description": "\u81ea\u52a8\u8c03\u4f18\u53c2\u6570"},
    {"name": "pangu_meta_insights", "description": "\u83b7\u53d6\u5b66\u4e60\u6d1e\u5bdf"},
    {"name": "pangu_meta_stats", "description": "\u5143\u5b66\u4e60\u7edf\u8ba1"},
    {"name": "pangu_health_check", "description": "\u5168\u9762\u5065\u5eb7\u68c0\u67e5"},
    {"name": "pangu_health_trend", "description": "\u5065\u5eb7\u8d8b\u52bf"},
    {"name": "pangu_health_stats", "description": "\u5065\u5eb7\u7edf\u8ba1"},
    {"name": "pangu_learning_stats", "description": "\u83b7\u53d6\u81ea\u9002\u5e94\u5b66\u4e60\u7edf\u8ba1"},
    {"name": "pangu_benchmark", "description": "\u8fd0\u884c\u6027\u80fd\u57fa\u51c6\u6d4b\u8bd5"},
    {
        "name": "pangu_error_stats",
        "description": "\u67e5\u770b\u9519\u8bef\u7edf\u8ba1\uff08\u9519\u8bef\u7387/\u8d8b\u52bf/\u4e25\u91cd\u9519\u8bef\uff09",
    },
    {
        "name": "pangu_health_report",
        "description": "\u751f\u6210\u7efc\u5408\u5065\u5eb7\u62a5\u544a\uff08\u8bc4\u5206+\u5efa\u8bae\uff09",
    },
    # ── P2-1 Step 2：高级推理（advanced_reasoning）接入 ──
    # 命名一律带 advanced_ 前缀，避开既有的 pangu_growth_trend /
    # pangu_anomaly_detect / pangu_anomaly_scan（同层已有，不可重名）。
    {
        "name": "pangu_advanced_causal_chains",
        "description": "\u53d1\u73b0\u8bb0\u5fc6\u95f4\u7684\u65f6\u5e8f\u56e0\u679c\u94fe\uff08\u652f\u6301 min_support/limit\uff09",
    },
    {
        "name": "pangu_advanced_trends",
        "description": "\u9884\u6d4b\u6807\u7b7e\u70ed\u5ea6\u8d8b\u52bf\uff08\u652f\u6301\u7a97\u53e3/\u9884\u6d4b\u6b65\u957f\uff09",
    },
    {
        "name": "pangu_advanced_anomalies",
        "description": "\u68c0\u6d4b\u8bb0\u5fc6\u5f02\u5e38\uff08\u9891\u7387/\u5185\u5bb9/\u6807\u7b7e/\u95f4\u9694\uff09",
    },
    {
        "name": "pangu_advanced_knowledge_gaps",
        "description": "\u8bc6\u522b\u77e5\u8bc6\u7f3a\u53e3\uff08\u5b64\u7acb\u4e3b\u9898/\u8584\u5f31\u4e3b\u9898\uff0c\u6309\u4f18\u5148\u7ea7\u8fc7\u6ee4\uff09",
    },
]

HANDLERS = {}


async def handle_analyze(server, drawers, arguments):
    """生成全面记忆分析报告"""
    from ...memory.analytics import MemoryAnalyzer

    analyzer = MemoryAnalyzer(server.config)
    wiki_count = server.wiki.stats().get("total_pages", 0)
    analysis = analyzer.analyze(drawers, wiki_page_count=wiki_count)
    return json.dumps(analysis.__dict__, ensure_ascii=False, indent=2)


HANDLERS["pangu_analyze"] = handle_analyze


async def handle_health_check(server, drawers, arguments):
    """检查记忆系统健康度"""
    from ...memory.health_monitor import get_monitor

    hm = get_monitor(server.config)
    return json.dumps(hm.full_check(drawers), ensure_ascii=False, indent=2)


HANDLERS["pangu_health_check"] = handle_health_check


async def handle_anomaly_detect(server, drawers, arguments):
    """检测记忆系统异常"""
    from ...memory.analytics import MemoryAnalyzer

    analyzer = MemoryAnalyzer(server.config)
    anomalies = analyzer.anomaly_detect(drawers)
    return json.dumps(anomalies, ensure_ascii=False, indent=2)


HANDLERS["pangu_anomaly_detect"] = handle_anomaly_detect


async def handle_growth_trend(server, drawers, arguments):
    """分析记忆增长趋势"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    trend = pa.analyze_growth_trend(drawers)
    return json.dumps(trend, ensure_ascii=False, indent=2)


HANDLERS["pangu_growth_trend"] = handle_growth_trend


async def handle_discover_patterns(server, drawers, arguments):
    """发现记忆中的隐藏模式和规律"""
    from ...memory.creative_thinking import get_creative_thinking

    ct = get_creative_thinking(server.config)
    patterns = ct.discover_patterns(drawers)
    return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_discover_patterns"] = handle_discover_patterns


async def handle_pattern_insights(server, drawers, arguments):
    """从模式中提取洞察"""
    from ...memory.patterns import PatternEngine

    engine = PatternEngine(server.config)
    patterns = engine.discover_all(drawers)
    insights = engine.pattern_insights(patterns)
    return json.dumps(insights, ensure_ascii=False, indent=2)


HANDLERS["pangu_pattern_insights"] = handle_pattern_insights


async def handle_analyze_emotion(server, drawers, arguments):
    """分析文本情绪"""
    from ...memory.emotional_intelligence import get_emotional_intelligence

    ei = get_emotional_intelligence(server.config)
    text = arguments.get("text", "")
    result = ei.analyze_emotion(text)
    ei.record_emotion(text, result)
    return json.dumps(
        {
            "emotion": result.emotion.value,
            "intensity": result.intensity,
            "keywords": result.keywords,
            "confidence": result.confidence,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_analyze_emotion"] = handle_analyze_emotion


async def handle_emotion_stats(server, drawers, arguments):
    """获取情感统计"""
    from ...memory.emotional_intelligence import get_emotional_intelligence

    ei = get_emotional_intelligence(server.config)
    return json.dumps(ei.get_emotion_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_emotion_stats"] = handle_emotion_stats


async def handle_predict_emotion(server, drawers, arguments):
    """预测用户情绪"""
    from ...memory.emotional_intelligence import get_emotional_intelligence

    ei = get_emotional_intelligence(server.config)
    context = arguments.get("context", "")
    result = ei.predict_emotion(context)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_predict_emotion"] = handle_predict_emotion


async def handle_discover_patterns(server, drawers, arguments):
    """发现记忆中的模式"""
    from ...memory.creative_thinking import get_creative_thinking

    ct = get_creative_thinking(server.config)
    patterns = ct.discover_patterns(drawers)
    return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_discover_patterns"] = handle_discover_patterns


async def handle_discover_knowledge(server, drawers, arguments):
    """从记忆中自动发现新知识"""
    from ...memory.autonomous_learning import get_autonomous_learning

    al = get_autonomous_learning(server.config)
    discoveries = al.discover_knowledge(drawers)
    return json.dumps({"discoveries": discoveries, "count": len(discoveries)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_discover_knowledge"] = handle_discover_knowledge


async def handle_generate_hypotheses(server, drawers, arguments):
    """基于记忆生成假设"""
    from ...memory.autonomous_learning import get_autonomous_learning

    al = get_autonomous_learning(server.config)
    limit = arguments.get("limit", 5)
    hypotheses = al.generate_hypotheses(drawers)
    return json.dumps(
        {
            "hypotheses": [
                {"statement": h.statement, "confidence": h.confidence, "status": h.status} for h in hypotheses[:limit]
            ],
            "count": len(hypotheses),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_generate_hypotheses"] = handle_generate_hypotheses


async def handle_learning_stats(server, drawers, arguments):
    """获取自主学习统计"""
    from ...memory.adaptive_learning import get_adaptive_learning

    al = get_adaptive_learning(server.config)
    return json.dumps(al.get_learning_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_learning_stats"] = handle_learning_stats


async def handle_self_diagnose(server, drawers, arguments):
    """系统自我诊断"""
    from ...memory.self_evolution import get_evolution_engine

    se = get_evolution_engine(server.config)
    diagnosis = se.diagnose(drawers)
    return json.dumps(
        {
            "issues": [
                {
                    "category": d.category,
                    "severity": d.severity,
                    "description": d.description,
                    "recommendation": d.recommendation,
                }
                for d in diagnosis
            ],
            "total_issues": len(diagnosis),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_self_diagnose"] = handle_self_diagnose


async def handle_evolution_plan(server, drawers, arguments):
    """生成进化计划"""
    from ...memory.self_evolution import get_evolution_engine

    se = get_evolution_engine(server.config)
    diagnosis = se.diagnose(drawers)
    plan = se.generate_evolution_plan(diagnosis)
    return json.dumps(
        {
            "name": plan.name,
            "actions": plan.actions,
            "expected_improvement": plan.expected_improvement,
            "priority": plan.priority,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_evolution_plan"] = handle_evolution_plan


async def handle_performance_trend(server, drawers, arguments):
    """查看性能趋势"""
    from ...memory.self_evolution import get_evolution_engine

    se = get_evolution_engine(server.config)
    metric = arguments.get("metric", "search_score")
    trend = se.get_performance_trend(metric)
    return json.dumps(trend, ensure_ascii=False, indent=2)


HANDLERS["pangu_performance_trend"] = handle_performance_trend


async def handle_evolution_stats(server, drawers, arguments):
    """获取进化统计"""
    from ...memory.self_evolution import get_evolution_engine

    se = get_evolution_engine(server.config)
    return json.dumps(se.get_evolution_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_evolution_stats"] = handle_evolution_stats


async def handle_anomaly_scan(server, drawers, arguments):
    """全面异常扫描"""
    from ...memory.anomaly_detection import get_detector

    det = get_detector(server.config)
    result = det.full_scan(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_anomaly_scan"] = handle_anomaly_scan


async def handle_anomaly_content(server, drawers, arguments):
    """内容异常检测"""
    from ...memory.anomaly_detection import get_detector

    det = get_detector(server.config)
    anomalies = det.detect_content_anomalies(drawers)
    return json.dumps(
        {
            "anomalies": [
                {"type": a.anomaly_type, "severity": a.severity, "description": a.description} for a in anomalies
            ],
            "count": len(anomalies),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_anomaly_content"] = handle_anomaly_content


async def handle_anomaly_stats(server, drawers, arguments):
    """异常检测统计"""
    from ...memory.anomaly_detection import get_detector

    det = get_detector(server.config)
    return json.dumps(det.get_anomaly_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_anomaly_stats"] = handle_anomaly_stats


async def handle_predict_queries(server, drawers, arguments):
    """预测用户下一步查询"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    top_k = arguments.get("top_k", 5)
    predictions = pa.predict_next_queries([], top_k)
    return json.dumps(
        {
            "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
            "count": len(predictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_predict_queries"] = handle_predict_queries


async def handle_predict_forgetting(server, drawers, arguments):
    """预测即将遗忘的记忆"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    threshold = arguments.get("days_threshold", 30)
    predictions = pa.predict_forgetting(drawers, threshold)
    return json.dumps(
        {
            "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
            "count": len(predictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_predict_forgetting"] = handle_predict_forgetting


async def handle_growth_trend(server, drawers, arguments):
    """分析增长趋势"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    trend = pa.analyze_growth_trend(drawers)
    return json.dumps(trend, ensure_ascii=False, indent=2)


HANDLERS["pangu_growth_trend"] = handle_growth_trend


async def handle_hot_topics(server, drawers, arguments):
    """预测热点主题"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    top_k = arguments.get("top_k", 5)
    predictions = pa.predict_hot_topics(drawers, top_k)
    return json.dumps(
        {
            "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
            "count": len(predictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_hot_topics"] = handle_hot_topics


async def handle_predictive_stats(server, drawers, arguments):
    """预测分析统计"""
    from ...memory.predictive_analytics import get_analytics

    pa = get_analytics(server.config)
    return json.dumps(pa.get_prediction_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_predictive_stats"] = handle_predictive_stats


async def handle_meta_observe(server, drawers, arguments):
    """记录性能观察"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    ml.observe(arguments["module"], arguments["metric"], arguments["value"])
    return json.dumps({"status": "recorded"}, ensure_ascii=False, indent=2)


HANDLERS["pangu_meta_observe"] = handle_meta_observe


async def handle_meta_recommend(server, drawers, arguments):
    """推荐最优策略"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    task_type = arguments.get("task_type", "search")
    result = ml.recommend_strategy(task_type)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_meta_recommend"] = handle_meta_recommend


async def handle_meta_tune(server, drawers, arguments):
    """自动调优参数"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    result = ml.auto_tune()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_meta_tune"] = handle_meta_tune


async def handle_meta_insights(server, drawers, arguments):
    """获取学习洞察"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    return json.dumps(ml.get_learning_insights(), ensure_ascii=False, indent=2)


HANDLERS["pangu_meta_insights"] = handle_meta_insights


async def handle_meta_stats(server, drawers, arguments):
    """元学习统计"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    return json.dumps(ml.get_meta_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_meta_stats"] = handle_meta_stats


async def handle_health_check(server, drawers, arguments):
    """全面健康检查"""
    from ...memory.health_monitor import get_monitor

    hm = get_monitor(server.config)
    return json.dumps(hm.full_check(drawers), ensure_ascii=False, indent=2)


HANDLERS["pangu_health_check"] = handle_health_check


async def handle_health_trend(server, drawers, arguments):
    """健康趋势"""
    from ...memory.health_monitor import get_monitor

    hm = get_monitor(server.config)
    return json.dumps(hm.get_trend(), ensure_ascii=False, indent=2)


HANDLERS["pangu_health_trend"] = handle_health_trend


async def handle_health_stats(server, drawers, arguments):
    """健康统计"""
    from ...memory.health_monitor import get_monitor

    hm = get_monitor(server.config)
    return json.dumps(hm.get_health_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_health_stats"] = handle_health_stats


async def handle_learning_stats(server, drawers, arguments):
    """获取自适应学习统计"""
    from ...memory.adaptive_learning import get_adaptive_learning

    al = get_adaptive_learning(server.config)
    return json.dumps(al.get_learning_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_learning_stats"] = handle_learning_stats


async def handle_benchmark(server, drawers, arguments):
    """运行性能基准测试"""
    from ...observability.performance_monitor import PerformanceMonitor

    monitor = PerformanceMonitor(server.config)
    result = monitor.run_benchmark()
    return json.dumps(
        {
            "timestamp": result.timestamp,
            "total_memories": result.total_memories,
            "vector_count": result.vector_count,
            "embed_latency_ms": result.embed_latency_ms,
            "search_latency_ms": result.search_latency_ms,
            "hybrid_latency_ms": result.hybrid_latency_ms,
            "token_count": result.token_count,
            "token_per_memory": result.token_per_memory,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_benchmark"] = handle_benchmark


async def handle_error_stats(server, drawers, arguments):
    """查看错误统计（错误率/趋势/严重错误）"""
    from ...memory.error_monitor import get_error_monitor

    monitor = get_error_monitor(server.config)
    return json.dumps(monitor.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_error_stats"] = handle_error_stats


async def handle_health_report(server, drawers, arguments):
    """生成综合健康报告（评分+建议）"""
    from ...memory.error_monitor import get_error_monitor

    monitor = get_error_monitor(server.config)
    return json.dumps(monitor.get_health_report(), ensure_ascii=False, indent=2)


HANDLERS["pangu_health_report"] = handle_health_report


# ══════════════════════════════════════════════════════════════════════
# P2-1 Step 2：高级推理（memory/advanced_reasoning.py）接入
#
# 为什么每个工具都有 limit：
#   勘察实测（84 条生产记忆 / 301 个唯一标签）——
#     discover_causal_chains(min_support=3) → **8674 条链接**（O(T²) 标签对爆炸）
#     identify_knowledge_gaps             → **2881 个缺口**（单点主题刷屏）
#   不加限制会把 5MB+ JSON 直接返回给调用方。故一律带 limit 且给保守默认值。
# ══════════════════════════════════════════════════════════════════════


def _causal_link_to_dict(link) -> dict:
    return {
        "id": link.id,
        "cause": link.cause,
        "effect": link.effect,
        "confidence": link.confidence,
        "mechanism": link.mechanism,
        "temporal_lag_hours": link.temporal_lag,
        "evidence": list(link.evidence),
    }


def _trend_to_dict(t) -> dict:
    return {
        "id": t.id,
        "subject": t.subject,
        "direction": t.direction.value,
        "confidence": t.confidence,
        "historical_values": list(t.historical_values),
        "predicted_values": list(t.predicted_values),
        "time_horizon_hours": t.time_horizon_hours,
        "factors": list(t.factors),
    }


def _anomaly_to_dict(a) -> dict:
    return {
        "id": a.id,
        "anomaly_type": a.anomaly_type,
        "description": a.description,
        "severity": a.severity.value,
        "evidence": list(a.evidence),
        "expected_value": a.expected_value,
        "actual_value": a.actual_value,
        "deviation": a.deviation,
    }


def _gap_to_dict(g) -> dict:
    return {
        "id": g.id,
        "topic": g.topic,
        "description": g.description,
        "related_knowledge": list(g.related_knowledge),
        "missing_links": list(g.missing_links),
        "priority": g.priority,
        "suggested_actions": list(g.suggested_actions),
    }


async def handle_advanced_causal_chains(server, drawers, arguments):
    """发现记忆间的时序因果链。

    min_support 默认 **5**（不是模块默认的 3）：勘察实测 min_support=3 时
    84 条记忆会产出 8674 条链接，几乎全是置信度 <0.1 的噪声；提到 5 后
    降到约 3475 条，再经 limit 截断才可读。
    """
    from ...memory.advanced_reasoning import AdvancedReasoning

    engine = AdvancedReasoning(server.config)
    links = engine.discover_causal_chains(
        drawers,
        min_support=int(arguments.get("min_support", 5)),
        max_lag_hours=float(arguments.get("max_lag_hours", 48.0)),
    )
    limit = int(arguments.get("limit", 20))
    # 按置信度降序取 top-K（raw 输出未排序时也保证可读）
    # ⚠ total 必须在**切片前**记录，否则它等于 min(len, limit)，看不出被截断
    total = len(links)
    links = sorted(links, key=lambda x: -x.confidence)[:limit]
    return json.dumps(
        {
            "total_before_limit": total,
            "limit": limit,
            "links": [_causal_link_to_dict(x) for x in links],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_advanced_causal_chains"] = handle_advanced_causal_chains


async def handle_advanced_trends(server, drawers, arguments):
    """预测标签热度趋势。"""
    from ...memory.advanced_reasoning import AdvancedReasoning

    engine = AdvancedReasoning(server.config)
    trends = engine.predict_trends(
        drawers,
        window_hours=float(arguments.get("window_hours", 168.0)),
        prediction_hours=float(arguments.get("prediction_hours", 72.0)),
    )
    limit = int(arguments.get("limit", 20))
    total = len(trends)  # 切片前记录，否则看不出被截断
    trends = sorted(trends, key=lambda x: -x.confidence)[:limit]
    return json.dumps(
        {
            "total_before_limit": total,
            "limit": limit,
            "trends": [_trend_to_dict(x) for x in trends],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_advanced_trends"] = handle_advanced_trends


async def handle_advanced_anomalies(server, drawers, arguments):
    """检测记忆异常（频率/内容/标签集中度/创建间隔四通道）。"""
    from ...memory.advanced_reasoning import AdvancedReasoning

    engine = AdvancedReasoning(server.config)
    alerts = engine.detect_anomalies(
        drawers,
        z_threshold=float(arguments.get("z_threshold", 2.0)),
    )
    limit = int(arguments.get("limit", 30))
    total = len(alerts)  # 切片前记录，否则看不出被截断
    # 严重度排序：critical > high > medium > low，同 severity 按偏差降序
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts = sorted(alerts, key=lambda a: (_order.get(a.severity.value, 9), -abs(a.deviation)))[:limit]
    return json.dumps(
        {
            "total_before_limit": total,
            "limit": limit,
            "alerts": [_anomaly_to_dict(a) for a in alerts],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_advanced_anomalies"] = handle_advanced_anomalies


async def handle_advanced_knowledge_gaps(server, drawers, arguments):
    """识别知识缺口。

    ⚠ min_priority 默认 **0.0（不过滤）**，而不是某个"看起来合理"的高阈值。
    原因（实测，92 条生产记忆）：priority 只有 3 个固定档位 ——
        0.4 = 薄弱主题（标签仅出现 1 次）
        0.6 = 孤立主题（出现 ≥3 次但只与 1 个其他主题关联）
        0.7 = 因果缺口
    生产数据 264 个缺口**全部是 0.4**，若默认 0.6 则工具永远返回空数组，
    调用方会误以为"没有缺口"而不是"阈值把结果滤光了"。
    故默认不过滤、按优先级降序 + limit 截断，并在返回里给出 by_priority
    分布，让调用方自己决定要不要抬高阈值。
    """
    from ...memory.advanced_reasoning import AdvancedReasoning

    engine = AdvancedReasoning(server.config)
    all_gaps = engine.identify_knowledge_gaps(drawers)
    min_priority = float(arguments.get("min_priority", 0.0))
    gaps = [g for g in all_gaps if g.priority >= min_priority]

    by_priority: dict[str, int] = {}
    for g in all_gaps:
        key = f"{g.priority:.1f}"
        by_priority[key] = by_priority.get(key, 0) + 1

    limit = int(arguments.get("limit", 20))
    top = sorted(gaps, key=lambda g: -g.priority)[:limit]
    return json.dumps(
        {
            "total_gaps": len(all_gaps),
            "after_min_priority": len(gaps),
            "by_priority": by_priority,
            "min_priority": min_priority,
            "limit": limit,
            "gaps": [_gap_to_dict(g) for g in top],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_advanced_knowledge_gaps"] = handle_advanced_knowledge_gaps
