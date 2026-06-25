"""盘古 MCP Handler — search (33 tools)"""
import json
from ...memory.fts_search import FTS5SearchEngine

TOOLS = [
    {"name": "pangu_cluster_memories", "description": "\u5c06\u8bb0\u5fc6\u81ea\u52a8\u805a\u7c7b\u4e3a\u4e3b\u9898\u5206\u7ec4"},
    {"name": "pangu_find_related", "description": "\u627e\u5230\u4e0e\u6307\u5b9a\u8bb0\u5fc6\u6700\u76f8\u5173\u7684\u5176\u4ed6\u8bb0\u5fc6"},
    {"name": "pangu_fts_search", "description": "FTS5\u5168\u6587+\u5411\u91cf\u6df7\u5408\u641c\u7d22(RRF\u878d\u5408)"},
    {"name": "pangu_fts_search_stats", "description": "\u83b7\u53d6\u641c\u7d22\u5f15\u64ce\u7edf\u8ba1"},
    {"name": "pangu_natural_query", "description": "\u81ea\u7136\u8bed\u8a00\u67e5\u8be2\u8bb0\u5fc6\uff08\u652f\u6301\u65f6\u95f4\u3001\u7a7a\u95f4\u3001\u91cd\u8981\u6027\u7b49\u8bed\u4e49\u7406\u89e3\uff09"},
    {"name": "pangu_recommend", "description": "\u57fa\u4e8e\u4e0a\u4e0b\u6587\u667a\u80fd\u63a8\u8350\u76f8\u5173\u8bb0\u5fc6"},
    {"name": "pangu_conversational_search", "description": "\u5bf9\u8bdd\u5f0f\u8bb0\u5fc6\u641c\u7d22\uff08\u652f\u6301\u591a\u8f6e\u6f84\u6e05\uff09"},
    {"name": "pangu_memory_insights", "description": "\u4ece\u8bb0\u5fc6\u4e2d\u63d0\u53d6\u6d1e\u5bdf\u548c\u6a21\u5f0f"},
    {"name": "pangu_hybrid_search", "description": "FTS+\u5411\u91cf+KG\u4e09\u8def\u53ec\u56de RRF\u878d\u5408\u68c0\u7d22"},
    {"name": "pangu_cluster_by_tags", "description": "\u6309\u6807\u7b7e\u805a\u7c7b\u641c\u7d22\u7ed3\u679c"},
    {"name": "pangu_cluster_by_time", "description": "\u6309\u65f6\u95f4\u805a\u7c7b\u641c\u7d22\u7ed3\u679c"},
    {"name": "pangu_hierarchical_cluster", "description": "\u5c42\u6b21\u805a\u7c7b\uff08\u57fa\u4e8e\u5411\u91cf\u76f8\u4f3c\u5ea6\uff09"},
    {"name": "pangu_dedup_results", "description": "\u53bb\u91cd\u641c\u7d22\u7ed3\u679c"},
    {"name": "pangu_recommend_interaction", "description": "\u63a8\u8350\u4ea4\u4e92\u7b56\u7565"},
    {"name": "pangu_explain_search", "description": "\u89e3\u91ca\u641c\u7d22\u7ed3\u679c"},
    {"name": "pangu_search_suggestions", "description": "\u641c\u7d22\u6539\u8fdb\u5efa\u8bae"},
    {"name": "pangu_recommend", "description": "\u7efc\u5408\u8bb0\u5fc6\u63a8\u8350"},
    {"name": "pangu_recommend_similar", "description": "\u63a8\u8350\u76f8\u4f3c\u8bb0\u5fc6"},
    {"name": "pangu_recommend_timely", "description": "\u63a8\u8350\u65f6\u6548\u6027\u8bb0\u5fc6"},
    {"name": "pangu_recommend_feedback", "description": "\u8bb0\u5f55\u63a8\u8350\u53cd\u9988"},
    {"name": "pangu_recommendation_stats", "description": "\u63a8\u8350\u7edf\u8ba1"},
    {"name": "pangu_rewrite_query", "description": "\u91cd\u5199\u641c\u7d22\u67e5\u8be2"},
    {"name": "pangu_suggest_queries", "description": "\u67e5\u8be2\u5efa\u8bae"},
    {"name": "pangu_rewrite_stats", "description": "\u91cd\u5199\u7edf\u8ba1"},
    {"name": "pangu_search_analytics_summary", "description": "\u641c\u7d22\u5206\u6790\u6458\u8981"},
    {"name": "pangu_search_analytics_top", "description": "\u70ed\u95e8\u67e5\u8be2"},
    {"name": "pangu_search_analytics_empty", "description": "\u65e0\u7ed3\u679c\u641c\u7d22"},
    {"name": "pangu_search_analytics_slow", "description": "\u6162\u641c\u7d22"},
    {"name": "pangu_realtime_stats", "description": "\u5b9e\u65f6\u901a\u77e5\u7edf\u8ba1"},
    {"name": "pangu_realtime_history", "description": "\u4e8b\u4ef6\u5386\u53f2"},
    {"name": "pangu_search_stats", "description": "\u83b7\u53d6\u641c\u7d22\u547d\u4e2d\u7387\u7edf\u8ba1"},
    {"name": "pangu_rerank", "description": "\u8bed\u4e49\u91cd\u6392\u5e8f\u641c\u7d22\u7ed3\u679c\uff08\u4e0a\u4e0b\u6587+\u65f6\u6548+\u91cd\u8981\u6027+\u8d28\u91cf\uff09"},
    {"name": "pangu_search_explain", "description": "\u641c\u7d22\u7ed3\u679c\u89e3\u91ca\uff08\u6bcf\u6761\u7ed3\u679c\u9644\u5e26\u4e3a\u4ec0\u4e48\u5339\u914d\uff09"},
]

HANDLERS = {}

async def handle_cluster_memories(server, drawers, arguments):
    """将记忆自动聚类为主题分组"""
    from ...memory.clustering import MemoryClusterer
    clusterer = MemoryClusterer(server.config)
    n_clusters = arguments.get("n_clusters", 0)
    min_sim = arguments.get("min_similarity", 0.3)
    wing = arguments.get("wing")
    filtered = [d for d in drawers if not wing or d.wing == wing]
    clusters = clusterer.cluster(filtered, n_clusters=n_clusters, min_similarity=min_sim)
    stats = clusterer.cluster_stats(clusters)
    result = {
        "stats": stats,
        "clusters": [
            {"id": c.id, "label": c.label, "keywords": c.keywords,
             "size": c.size, "cohesion": c.cohesion,
             "memory_ids": c.memory_ids[:5]}
            for c in clusters
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_cluster_memories"] = handle_cluster_memories

async def handle_find_related(server, drawers, arguments):
    """找到与指定记忆最相关的其他记忆"""
    from ...memory.clustering import MemoryClusterer
    clusterer = MemoryClusterer(server.config)
    drawer_id = arguments.get("drawer_id", "")
    target = server.memory.get_drawer_by_id(drawer_id)
    if not target:
        return json.dumps({"code": 2001, "error": "记忆不存在"})
    related = clusterer.find_related(target, drawers)
    return json.dumps(related, ensure_ascii=False, indent=2)

HANDLERS["pangu_find_related"] = handle_find_related

async def handle_fts_search(server, drawers, arguments):
    """FTS5全文+向量混合搜索(RRF融合)"""
    engine = FTS5SearchEngine(server.config)
    engine.build_index(drawers)
    result = engine.search(
        query=arguments.get("query", ""),
        drawers=drawers,
        wing=arguments.get("wing"),
        room=arguments.get("room"),
        limit=arguments.get("limit", 10),
        offset=arguments.get("offset", 0),
        min_importance=arguments.get("min_importance", 0.0),
        vector_weight=arguments.get("vector_weight"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_fts_search"] = handle_fts_search

async def handle_fts_search_stats(server, drawers, arguments):
    """获取搜索引擎统计"""
    return json.dumps(get_search_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_fts_search_stats"] = handle_fts_search_stats

async def handle_natural_query(server, drawers, arguments):
    """自然语言查询记忆（支持时间、空间、重要性等语义理解）"""
    from ...memory.natural_query import natural_language_search
    query = arguments.get("query", "")
    limit = int(arguments.get("limit", 10))
    results = natural_language_search(query, drawers, limit)
    return json.dumps(results, ensure_ascii=False, indent=2)

HANDLERS["pangu_natural_query"] = handle_natural_query

async def handle_recommend(server, drawers, arguments):
    """基于上下文智能推荐相关记忆"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    context = arguments.get("context", "")
    memory_id = arguments.get("memory_id", "")
    top_k = arguments.get("top_k", 5)
    result = rec.get_full_recommendations(context, memory_id, drawers, top_k)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend"] = handle_recommend

async def handle_conversational_search(server, drawers, arguments):
    """对话式记忆搜索（支持多轮澄清）"""
    from ...memory.natural_query import natural_language_search
    query = arguments.get("query", "")
    session_id = arguments.get("session_id", "")
    clarify = arguments.get("clarify", False)

    # 简单的对话式搜索
    results = natural_language_search(query, drawers, limit=10)

    # 如果需要澄清，添加提示
    if clarify and len(results) > 5:
        results.append({
            "type": "clarification",
            "message": f"找到 {len(results)} 条相关记忆，是否需要更精确的搜索？",
            "suggestions": [
                "缩小时间范围",
                "指定空间(Wing)",
                "提高重要性阈值"
            ]
        })

    return json.dumps(results, ensure_ascii=False, indent=2)

HANDLERS["pangu_conversational_search"] = handle_conversational_search

async def handle_memory_insights(server, drawers, arguments):
    """从记忆中提取洞察和模式"""
    from ...memory.natural_query import _analyze_memories, _timeline_query
    from datetime import timedelta

    topic = arguments.get("topic", "")
    time_range = arguments.get("time_range", "")

    # 过滤记忆
    filtered = drawers
    if topic:
        filtered = [d for d in filtered if topic.lower() in d.content.lower()]

    if time_range:
        days = int(time_range.replace('d', ''))
        cutoff = datetime.now() - timedelta(days=days)
        filtered = [d for d in filtered if datetime.fromisoformat(d.created_at) >= cutoff]

    # 分析
    analysis = _analyze_memories(filtered, {"wing": None})
    insights = {
        "analysis": analysis[0] if analysis else {},
        "top_memories": [
            {"content": d.content[:100], "importance": d.importance}
            for d in sorted(filtered, key=lambda x: x.importance, reverse=True)[:5]
        ],
        "patterns": server._discover_simple_patterns(filtered),
    }

    return json.dumps(insights, ensure_ascii=False, indent=2)

HANDLERS["pangu_memory_insights"] = handle_memory_insights

async def handle_hybrid_search(server, drawers, arguments):
    """FTS+向量+KG三路召回 RRF融合检索"""
    from ...memory.hybrid_search import hybrid_search
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)
    results = hybrid_search(query, drawers, server.config, limit)
    return json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_hybrid_search"] = handle_hybrid_search

async def handle_cluster_by_tags(server, drawers, arguments):
    """按标签聚类搜索结果"""
    from ...memory.cluster import cluster_by_tags, get_cluster_summary
    query = arguments.get("query", "")
    limit = arguments.get("limit", 20)
    results = hybrid_search(query, drawers, server.config, limit)
    clusters = cluster_by_tags(results)
    summary = get_cluster_summary(clusters)
    return json.dumps({"clusters": summary, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_cluster_by_tags"] = handle_cluster_by_tags

async def handle_cluster_by_time(server, drawers, arguments):
    """按时间聚类搜索结果"""
    from ...memory.cluster import cluster_by_time, get_cluster_summary
    query = arguments.get("query", "")
    buckets = arguments.get("buckets", 3)
    results = hybrid_search(query, drawers, server.config, 20)
    clusters = cluster_by_time(results, buckets)
    summary = get_cluster_summary(clusters)
    return json.dumps({"clusters": summary, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_cluster_by_time"] = handle_cluster_by_time

async def handle_hierarchical_cluster(server, drawers, arguments):
    """层次聚类（基于向量相似度）"""
    from ...memory.cluster import hierarchical_cluster
    query = arguments.get("query", "")
    max_clusters = arguments.get("max_clusters", 5)
    results = hybrid_search(query, drawers, server.config, limit=20)
    clusters = hierarchical_cluster(results, max_clusters=max_clusters)
    return json.dumps({"clusters": clusters, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_hierarchical_cluster"] = handle_hierarchical_cluster

async def handle_dedup_results(server, drawers, arguments):
    """去重搜索结果"""
    from ...memory.cluster import deduplicate_results
    query = arguments.get("query", "")
    limit = arguments.get("limit", 10)
    results = hybrid_search(query, drawers, server.config, limit=limit)
    deduped = deduplicate_results(results)
    return json.dumps({"results": deduped, "total": len(deduped), "removed": len(results) - len(deduped)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_dedup_results"] = handle_dedup_results

async def handle_recommend_interaction(server, drawers, arguments):
    """推荐交互策略"""
    from ...memory.emotional_intelligence import get_emotional_intelligence
    ei = get_emotional_intelligence(server.config)
    emotion_state = arguments.get("emotion_state", {})
    result = ei.recommend_interaction(emotion_state)
    return json.dumps({"recommendation": result}, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend_interaction"] = handle_recommend_interaction

async def handle_explain_search(server, drawers, arguments):
    """解释搜索结果"""
    from ...memory.explainable_search import get_explainable_engine
    ee = get_explainable_engine(server.config)
    query = arguments.get("query", "")
    result_ids = arguments.get("result_ids", [])
    mock_results = [{"id": rid, "score": 0.5} for rid in result_ids]
    explanations = ee.explain_results(query, mock_results, drawers)
    return json.dumps({
        "explanations": [
            {"id": e.memory_id, "preview": e.content_preview,
             "score": e.score, "factors": e.factors,
             "reason": e.primary_reason}
            for e in explanations
        ],
        "count": len(explanations),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_explain_search"] = handle_explain_search

async def handle_search_suggestions(server, drawers, arguments):
    """搜索改进建议"""
    from ...memory.explainable_search import get_explainable_engine
    ee = get_explainable_engine(server.config)
    query = arguments.get("query", "")
    suggestions = ee.suggest_improvement(query, [])
    return json.dumps({"suggestions": suggestions}, ensure_ascii=False, indent=2)

HANDLERS["pangu_search_suggestions"] = handle_search_suggestions

async def handle_recommend(server, drawers, arguments):
    """综合记忆推荐"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    context = arguments.get("context", "")
    memory_id = arguments.get("memory_id", "")
    top_k = arguments.get("top_k", 5)
    result = rec.get_full_recommendations(context, memory_id, drawers, top_k)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend"] = handle_recommend

async def handle_recommend_similar(server, drawers, arguments):
    """推荐相似记忆"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    memory_id = arguments.get("memory_id", "")
    top_k = arguments.get("top_k", 5)
    results = rec.recommend_similar(memory_id, drawers, top_k)
    return json.dumps({
        "recommendations": [
            {"id": r.memory_id, "preview": r.content_preview,
             "score": r.score, "reason": r.reason}
            for r in results
        ],
        "count": len(results),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend_similar"] = handle_recommend_similar

async def handle_recommend_timely(server, drawers, arguments):
    """推荐时效性记忆"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    top_k = arguments.get("top_k", 5)
    results = rec.recommend_timely(drawers, top_k)
    return json.dumps({
        "recommendations": [
            {"id": r.memory_id, "preview": r.content_preview,
             "wing": r.wing, "score": r.score, "reason": r.reason}
            for r in results
        ],
        "count": len(results),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend_timely"] = handle_recommend_timely

async def handle_recommend_feedback(server, drawers, arguments):
    """记录推荐反馈"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    memory_id = arguments.get("memory_id", "")
    liked = arguments.get("liked", True)
    rec.record_feedback("default", memory_id, liked)
    return json.dumps({"status": "recorded", "memory_id": memory_id, "liked": liked}, ensure_ascii=False, indent=2)

HANDLERS["pangu_recommend_feedback"] = handle_recommend_feedback

async def handle_recommendation_stats(server, drawers, arguments):
    """推荐统计"""
    from ...memory.recommendation import get_recommendation
    rec = get_recommendation(server.config)
    return json.dumps(rec.get_recommendation_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_recommendation_stats"] = handle_recommendation_stats

async def handle_rewrite_query(server, drawers, arguments):
    """重写搜索查询"""
    from ...memory.query_rewriter import get_rewriter
    rw = get_rewriter(server.config)
    query = arguments.get("query", "")
    strategy = arguments.get("strategy", "auto")
    result = rw.rewrite(query, strategy)
    return json.dumps({
        "original": result.original,
        "rewritten": result.rewritten,
        "strategy": result.strategy,
        "expanded_terms": result.expanded_terms,
        "confidence": result.confidence,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_rewrite_query"] = handle_rewrite_query

async def handle_suggest_queries(server, drawers, arguments):
    """查询建议"""
    from ...memory.query_rewriter import get_rewriter
    rw = get_rewriter(server.config)
    partial = arguments.get("partial", "")
    top_k = arguments.get("top_k", 5)
    suggestions = rw.suggest_queries(partial, drawers, top_k)
    return json.dumps({"suggestions": suggestions, "count": len(suggestions)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_suggest_queries"] = handle_suggest_queries

async def handle_rewrite_stats(server, drawers, arguments):
    """重写统计"""
    from ...memory.query_rewriter import get_rewriter
    rw = get_rewriter(server.config)
    return json.dumps(rw.get_rewrite_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_rewrite_stats"] = handle_rewrite_stats

async def handle_search_analytics_summary(server, drawers, arguments):
    """搜索分析摘要"""
    from ...memory.search_analytics import get_search_analytics
    sa = get_search_analytics(server.config)
    return json.dumps(sa.get_summary(), ensure_ascii=False, indent=2)

HANDLERS["pangu_search_analytics_summary"] = handle_search_analytics_summary

async def handle_search_analytics_top(server, drawers, arguments):
    """热门查询"""
    from ...memory.search_analytics import get_search_analytics
    sa = get_search_analytics(server.config)
    top = sa.get_top_queries(arguments.get("top_k", 10))
    return json.dumps({"queries": top, "count": len(top)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_search_analytics_top"] = handle_search_analytics_top

async def handle_search_analytics_empty(server, drawers, arguments):
    """无结果搜索"""
    from ...memory.search_analytics import get_search_analytics
    sa = get_search_analytics(server.config)
    empty = sa.get_empty_searches()
    return json.dumps({"searches": empty, "count": len(empty)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_search_analytics_empty"] = handle_search_analytics_empty

async def handle_search_analytics_slow(server, drawers, arguments):
    """慢搜索"""
    from ...memory.search_analytics import get_search_analytics
    sa = get_search_analytics(server.config)
    slow = sa.get_slow_searches(arguments.get("threshold_ms", 1000))
    return json.dumps({"searches": slow, "count": len(slow)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_search_analytics_slow"] = handle_search_analytics_slow

async def handle_realtime_stats(server, drawers, arguments):
    """实时通知统计"""
    from ...memory.realtime import get_connection_manager
    mgr = get_connection_manager()
    return json.dumps(mgr.get_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_realtime_stats"] = handle_realtime_stats

async def handle_realtime_history(server, drawers, arguments):
    """事件历史"""
    from ...memory.realtime import get_connection_manager
    mgr = get_connection_manager()
    history = mgr.get_history(arguments.get("event_type"), arguments.get("limit", 50))
    return json.dumps({"history": history, "count": len(history)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_realtime_history"] = handle_realtime_history

async def handle_search_stats(server, drawers, arguments):
    """获取搜索命中率统计"""
    from ...memory.retrieval import get_search_stats as _get_search_stats
    return json.dumps(_get_search_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_search_stats"] = handle_search_stats

async def handle_rerank(server, drawers, arguments):
    """语义重排序搜索结果（上下文+时效+重要性+质量）"""
    from ...memory.reranker import rerank_search_results
    from ...memory.hybrid_search import hybrid_search
    query = arguments["query"]
    context = arguments.get("context", "")
    limit = arguments.get("limit", 10)
    rrf_results = hybrid_search(query, drawers, config=server.config, limit=limit * 2)
    reranked = rerank_search_results(query, rrf_results, context=context, drawers=drawers, limit=limit)
    return json.dumps({
        "count": len(reranked),
        "results": [{
            "id": r["id"], "content": r["content"][:100], "wing": r.get("wing"),
            "rerank_score": r.get("rerank_score", 0),
            "breakdown": r.get("rerank_breakdown", {}),
            "explanation": r.get("explanation", ""),
            "match_reasons": r.get("match_reasons", []),
        } for r in reranked]
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_rerank"] = handle_rerank

async def handle_search_explain(server, drawers, arguments):
    """搜索结果解释（每条结果附带为什么匹配）"""
    from ...memory.hybrid_search import hybrid_search
    query = arguments["query"]
    limit = arguments.get("limit", 5)
    results = hybrid_search(query, drawers, config=server.config, limit=limit)
    output = []
    for r in results:
        output.append({
            "id": r["id"],
            "content": r["content"][:100],
            "wing": r.get("wing"),
            "importance": r.get("importance"),
            "explanation": r.get("explanation", "语义匹配"),
            "match_reasons": r.get("match_reasons", []),
            "match_type": r.get("match_type", "keyword"),
            "rrf_score": r.get("rrf_score", 0),
            "rerank_score": r.get("rerank_score", 0),
        })
    return json.dumps({"count": len(output), "results": output}, ensure_ascii=False, indent=2)

HANDLERS["pangu_search_explain"] = handle_search_explain