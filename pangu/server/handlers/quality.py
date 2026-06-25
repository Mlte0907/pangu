"""盘古 MCP Handler — quality (20 tools)"""
import json

TOOLS = [
    {"name": "pangu_detect_conflicts", "description": "\u68c0\u6d4b\u8bb0\u5fc6\u4e2d\u7684\u77db\u76fe\u548c\u4e0d\u4e00\u81f4"},
    {"name": "pangu_check_pair", "description": "\u68c0\u67e5\u4e24\u6761\u8bb0\u5fc6\u662f\u5426\u5b58\u5728\u51b2\u7a81"},
    {"name": "pangu_find_duplicates", "description": "\u68c0\u6d4b\u91cd\u590d\u6216\u9ad8\u5ea6\u76f8\u4f3c\u7684\u8bb0\u5fc6"},
    {"name": "pangu_merge_duplicates", "description": "\u5408\u5e76\u91cd\u590d\u8bb0\u5fc6\u7ec4"},
    {"name": "pangu_similarity_check", "description": "\u68c0\u67e5\u4e24\u6761\u8bb0\u5fc6\u7684\u76f8\u4f3c\u5ea6"},
    {"name": "pangu_sanitize", "description": "\u8131\u654f\u8bb0\u5fc6\u5185\u5bb9"},
    {"name": "pangu_sanitize_check", "description": "\u68c0\u67e5\u662f\u5426\u9700\u8981\u8131\u654f"},
    {"name": "pangu_enhanced_contradictions", "description": "LLM\u9a71\u52a8\u77db\u76fe\u68c0\u6d4b\uff086\u79cd\u88c1\u51b3\uff09"},
    {"name": "pangu_trajectory_track", "description": "\u8ffd\u8e2a\u8bb0\u5fc6\u65f6\u95f4\u8f68\u8ff9"},
    {"name": "pangu_trajectory_compare", "description": "\u6bd4\u8f83\u4e24\u4e2a\u65f6\u95f4\u6bb5\u7684\u8bb0\u5fc6\u53d8\u5316"},
    {"name": "pangu_compress_by_tags", "description": "\u6309\u6807\u7b7e\u805a\u7c7b\u538b\u7f29\u8bb0\u5fc6"},
    {"name": "pangu_find_duplicates", "description": "\u53d1\u73b0\u8bed\u4e49\u91cd\u590d\u8bb0\u5fc6"},
    {"name": "pangu_reassess_importance", "description": "\u57fa\u4e8e\u8bb0\u5fc6\u7f51\u7edc\u91cd\u65b0\u8bc4\u4f30\u91cd\u8981\u6027"},
    {"name": "pangu_compression_stats", "description": "\u83b7\u53d6\u538b\u7f29\u7edf\u8ba1"},
    {"name": "pangu_assess_quality", "description": "\u8bc4\u4f30\u8bb0\u5fc6\u8d28\u91cf"},
    {"name": "pangu_batch_assess", "description": "\u6279\u91cf\u8d28\u91cf\u8bc4\u4f30"},
    {"name": "pangu_auto_fix", "description": "\u81ea\u52a8\u4fee\u590d\u8d28\u91cf\u95ee\u9898"},
    {"name": "pangu_quality_stats", "description": "\u8d28\u91cf\u7edf\u8ba1"},
    {"name": "pangu_quality_analyze", "description": "\u5206\u6790\u8bb0\u5fc6\u8d28\u91cf\uff08\u8bc4\u5206/\u53bb\u91cd/\u6807\u7b7e\uff09"},
    {"name": "pangu_quality_fix", "description": "\u81ea\u52a8\u4fee\u590d\u8bb0\u5fc6\u8d28\u91cf\u95ee\u9898\uff08\u6807\u7b7e/\u53bb\u91cd\uff09"},
]

HANDLERS = {}

async def handle_detect_conflicts(server, drawers, arguments):
    """检测记忆中的矛盾和不一致"""
    from ..memory.conflict import ConflictDetector
    detector = ConflictDetector(server.config)
    wing = arguments.get("wing")
    filtered = [d for d in drawers if not wing or d.wing == wing]
    conflicts = detector.detect_conflicts(filtered)
    return json.dumps([
        {"id": c.id, "memory_a": c.memory_a, "memory_b": c.memory_b,
         "content_a": c.content_a[:100], "content_b": c.content_b[:100],
         "description": c.description, "severity": c.severity.value,
         "confidence": c.confidence,
         "suggestion": detector.resolve_suggestion(c)}
        for c in conflicts
    ], ensure_ascii=False, indent=2)

HANDLERS["pangu_detect_conflicts"] = handle_detect_conflicts

async def handle_check_pair(server, drawers, arguments):
    """检查两条记忆是否存在冲突"""
    from ..memory.conflict import ConflictDetector
    detector = ConflictDetector(server.config)
    id_a = arguments.get("id_a", "")
    id_b = arguments.get("id_b", "")
    drawer_a = server.memory.get_drawer_by_id(id_a)
    drawer_b = server.memory.get_drawer_by_id(id_b)
    if not drawer_a or not drawer_b:
        return json.dumps({"code": 2001, "error": "记忆不存在"})
    result = detector.check_pair(drawer_a, drawer_b)
    return json.dumps(result, ensure_ascii=False)

HANDLERS["pangu_check_pair"] = handle_check_pair

async def handle_find_duplicates(server, drawers, arguments):
    """检测重复或高度相似的记忆"""
    from ..memory.semantic_compression import get_compressor
    comp = get_compressor(server.config)
    threshold = arguments.get("threshold", 0.8)
    dups = comp.find_semantic_duplicates(drawers, threshold)
    return json.dumps({"duplicates": dups, "count": len(dups)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_find_duplicates"] = handle_find_duplicates

async def handle_merge_duplicates(server, drawers, arguments):
    """合并重复记忆组"""
    from ..memory.dedup import DuplicateGroup, MemoryDeduplicator
    deduper = MemoryDeduplicator(server.config)
    group_data = arguments.get("group", {})
    group = DuplicateGroup(
        id=group_data.get("id", ""),
        memory_ids=group_data.get("memory_ids", []),
        primary_id=group_data.get("primary_id", ""),
        duplicate_ids=group_data.get("duplicate_ids", []),
        similarity_matrix=group_data.get("similarity_matrix", {}),
        avg_similarity=group_data.get("avg_similarity", 0.0),
    )
    merged = deduper.merge_duplicates(group, drawers)
    if merged:
        # 删除重复的
        server.memory.remove_drawers(group.duplicate_ids)
        # 更新主记忆
        server.memory.add_drawer(merged)
        return json.dumps({"status": "merged", "merged_id": merged.id,
                           "removed": group.duplicate_ids}, ensure_ascii=False)
    return json.dumps({"code": 2003, "error": "合并失败"})

HANDLERS["pangu_merge_duplicates"] = handle_merge_duplicates

async def handle_similarity_check(server, drawers, arguments):
    """检查两条记忆的相似度"""
    from ..memory.dedup import MemoryDeduplicator
    deduper = MemoryDeduplicator(server.config)
    id_a = arguments.get("id_a", "")
    id_b = arguments.get("id_b", "")
    drawer_a = server.memory.get_drawer_by_id(id_a)
    drawer_b = server.memory.get_drawer_by_id(id_b)
    if not drawer_a or not drawer_b:
        return json.dumps({"code": 2001, "error": "记忆不存在"})
    result = deduper.similarity_check(drawer_a, drawer_b)
    return json.dumps(result, ensure_ascii=False)

HANDLERS["pangu_similarity_check"] = handle_similarity_check

async def handle_sanitize(server, drawers, arguments):
    """脱敏记忆内容"""
    text = arguments.get("text", "")
    level = arguments.get("level", "standard")
    sanitized, redactions = MemorySanitizer.sanitize(text, level=level)
    return json.dumps({
        "sanitized": sanitized,
        "redactions": redactions,
        "total_redactions": sum(redactions.values()),
    }, ensure_ascii=False)

HANDLERS["pangu_sanitize"] = handle_sanitize

async def handle_sanitize_check(server, drawers, arguments):
    """检查是否需要脱敏"""
    text = arguments.get("text", "")
    level = arguments.get("level", "standard")
    summary = MemorySanitizer.get_redaction_summary(text, level=level)
    return json.dumps(summary, ensure_ascii=False, indent=2)

HANDLERS["pangu_sanitize_check"] = handle_sanitize_check

async def handle_enhanced_contradictions(server, drawers, arguments):
    """LLM驱动矛盾检测（6种裁决）"""
    detector = EnhancedContradictionDetector(server.config)
    result = detector.detect_contradictions(drawers, top_k=arguments.get("top_k", 50))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_enhanced_contradictions"] = handle_enhanced_contradictions

async def handle_trajectory_track(server, drawers, arguments):
    """追踪记忆时间轨迹"""
    tracker = TrajectoryTracker(server.config)
    result = tracker.track(
        drawers,
        item_id=arguments.get("item_id"),
        wing=arguments.get("wing"),
        room=arguments.get("room"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_trajectory_track"] = handle_trajectory_track

async def handle_trajectory_compare(server, drawers, arguments):
    """比较两个时间段的记忆变化"""
    tracker = TrajectoryTracker(server.config)
    result = tracker.compare_periods(
        drawers,
        period_a=arguments.get("period_a", ""),
        period_b=arguments.get("period_b", ""),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_trajectory_compare"] = handle_trajectory_compare

async def handle_compress_by_tags(server, drawers, arguments):
    """按标签聚类压缩记忆"""
    from ..memory.semantic_compression import get_compressor
    comp = get_compressor(server.config)
    result = comp.compress_by_tags(drawers)
    return json.dumps({
        "original_count": result.original_count,
        "compressed_count": result.compressed_count,
        "merged_groups": len(result.merged_groups),
        "information_loss": result.information_loss,
        "tokens_saved": result.tokens_saved,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_compress_by_tags"] = handle_compress_by_tags

async def handle_find_duplicates(server, drawers, arguments):
    """发现语义重复记忆"""
    from ..memory.semantic_compression import get_compressor
    comp = get_compressor(server.config)
    threshold = arguments.get("threshold", 0.8)
    dups = comp.find_semantic_duplicates(drawers, threshold)
    return json.dumps({"duplicates": dups, "count": len(dups)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_find_duplicates"] = handle_find_duplicates

async def handle_reassess_importance(server, drawers, arguments):
    """基于记忆网络重新评估重要性"""
    from ..memory.semantic_compression import get_compressor
    comp = get_compressor(server.config)
    updates = comp.reassess_importance(drawers)
    return json.dumps({"updates": updates, "count": len(updates)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_reassess_importance"] = handle_reassess_importance

async def handle_compression_stats(server, drawers, arguments):
    """获取压缩统计"""
    from ..memory.semantic_compression import get_compressor
    comp = get_compressor(server.config)
    return json.dumps(comp.get_compression_stats(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_compression_stats"] = handle_compression_stats

async def handle_assess_quality(server, drawers, arguments):
    """评估记忆质量"""
    from ..memory.quality_scorer import get_scorer
    qs = get_scorer(server.config)
    memory_id = arguments.get("memory_id", "")
    target = next((d for d in drawers if d.id == memory_id), None)
    if not target:
        return json.dumps({"error": "memory not found"}, ensure_ascii=False, indent=2)
    assessment = qs.assess(target, drawers)
    return json.dumps({
        "id": assessment.memory_id,
        "score": assessment.overall_score,
        "grade": assessment.grade,
        "dimensions": [{"name": d.name, "score": d.score, "detail": d.detail} for d in assessment.dimensions],
        "issues": assessment.issues,
        "suggestions": assessment.suggestions,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_assess_quality"] = handle_assess_quality

async def handle_batch_assess(server, drawers, arguments):
    """批量质量评估"""
    from ..memory.quality_scorer import get_scorer
    qs = get_scorer(server.config)
    result = qs.batch_assess(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_batch_assess"] = handle_batch_assess

async def handle_auto_fix(server, drawers, arguments):
    """自动修复质量问题"""
    from ..memory.quality_scorer import get_scorer
    qs = get_scorer(server.config)
    result = qs.auto_fix(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_auto_fix"] = handle_auto_fix

async def handle_quality_stats(server, drawers, arguments):
    """质量统计"""
    from ..memory.quality_scorer import get_scorer
    qs = get_scorer(server.config)
    return json.dumps(qs.get_quality_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_quality_stats"] = handle_quality_stats

async def handle_quality_analyze(server, drawers, arguments):
    """分析记忆质量（评分/去重/标签）"""
    from ..memory.quality import get_quality_pipeline
    pipe = get_quality_pipeline(server.config)
    return json.dumps(pipe.get_report_dict(), ensure_ascii=False, indent=2)

HANDLERS["pangu_quality_analyze"] = handle_quality_analyze

async def handle_quality_fix(server, drawers, arguments):
    """自动修复记忆质量问题（标签/去重）"""
    from ..memory.quality import get_quality_pipeline
    pipe = get_quality_pipeline(server.config)
    dry_run = arguments.get("dry_run", False)
    report = pipe.fix_all(dry_run=dry_run)
    from ..memory.memory_events import get_event_stream
    get_event_stream(server.config).emit("memory.quality_fix", "", {
        "tags_added": report.tags_added, "duplicates_removed": report.merged, "dry_run": dry_run,
    })
HANDLERS["pangu_quality_fix"] = handle_quality_fix