"""盘古 MCP Handler — analytics (37 tools)"""
import json

TOOLS = [
    {"name": "pangu_analyze", "description": "\u751f\u6210\u5168\u9762\u8bb0\u5fc6\u5206\u6790\u62a5\u544a"},
    {"name": "pangu_health_check", "description": "\u68c0\u67e5\u8bb0\u5fc6\u7cfb\u7edf\u5065\u5eb7\u5ea6"},
    {"name": "pangu_anomaly_detect", "description": "\u68c0\u6d4b\u8bb0\u5fc6\u7cfb\u7edf\u5f02\u5e38"},
    {"name": "pangu_growth_trend", "description": "\u5206\u6790\u8bb0\u5fc6\u589e\u957f\u8d8b\u52bf"},
    {"name": "pangu_discover_patterns", "description": "\u53d1\u73b0\u8bb0\u5fc6\u4e2d\u7684\u9690\u85cf\u6a21\u5f0f\u548c\u89c4\u5f8b"},
    {"name": "pangu_pattern_insights", "description": "\u4ece\u6a21\u5f0f\u4e2d\u63d0\u53d6\u6d1e\u5bdf"},
    {"name": "pangu_analyze_emotion", "description": "\u5206\u6790\u6587\u672c\u60c5\u7eea"},
    {"name": "pangu_emotion_stats", "description": "\u83b7\u53d6\u60c5\u611f\u7edf\u8ba1"},
    {"name": "pangu_predict_emotion", "description": "\u9884\u6d4b\u7528\u6237\u60c5\u7eea"},
    {"name": "pangu_discover_patterns", "description": "\u53d1\u73b0\u8bb0\u5fc6\u4e2d\u7684\u6a21\u5f0f"},
    {"name": "pangu_discover_knowledge", "description": "\u4ece\u8bb0\u5fc6\u4e2d\u81ea\u52a8\u53d1\u73b0\u65b0\u77e5\u8bc6"},
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
    {"name": "pangu_error_stats", "description": "\u67e5\u770b\u9519\u8bef\u7edf\u8ba1\uff08\u9519\u8bef\u7387/\u8d8b\u52bf/\u4e25\u91cd\u9519\u8bef\uff09"},
    {"name": "pangu_health_report", "description": "\u751f\u6210\u7efc\u5408\u5065\u5eb7\u62a5\u544a\uff08\u8bc4\u5206+\u5efa\u8bae\uff09"},
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
    return json.dumps({
        "emotion": result.emotion.value,
        "intensity": result.intensity,
        "keywords": result.keywords,
        "confidence": result.confidence,
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "hypotheses": [
            {"statement": h.statement, "confidence": h.confidence, "status": h.status}
            for h in hypotheses[:limit]
        ],
        "count": len(hypotheses),
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "issues": [
            {"category": d.category, "severity": d.severity,
             "description": d.description, "recommendation": d.recommendation}
            for d in diagnosis
        ],
        "total_issues": len(diagnosis),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_self_diagnose"] = handle_self_diagnose

async def handle_evolution_plan(server, drawers, arguments):
    """生成进化计划"""
    from ...memory.self_evolution import get_evolution_engine
    se = get_evolution_engine(server.config)
    diagnosis = se.diagnose(drawers)
    plan = se.generate_evolution_plan(diagnosis)
    return json.dumps({
        "name": plan.name,
        "actions": plan.actions,
        "expected_improvement": plan.expected_improvement,
        "priority": plan.priority,
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "anomalies": [{"type": a.anomaly_type, "severity": a.severity,
                       "description": a.description} for a in anomalies],
        "count": len(anomalies),
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
        "count": len(predictions),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_predict_queries"] = handle_predict_queries

async def handle_predict_forgetting(server, drawers, arguments):
    """预测即将遗忘的记忆"""
    from ...memory.predictive_analytics import get_analytics
    pa = get_analytics(server.config)
    threshold = arguments.get("days_threshold", 30)
    predictions = pa.predict_forgetting(drawers, threshold)
    return json.dumps({
        "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
        "count": len(predictions),
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
        "count": len(predictions),
    }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "timestamp": result.timestamp,
        "total_memories": result.total_memories,
        "vector_count": result.vector_count,
        "embed_latency_ms": result.embed_latency_ms,
        "search_latency_ms": result.search_latency_ms,
        "hybrid_latency_ms": result.hybrid_latency_ms,
        "token_count": result.token_count,
        "token_per_memory": result.token_per_memory,
    }, ensure_ascii=False, indent=2)

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