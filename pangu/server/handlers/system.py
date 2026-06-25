"""盘古 MCP Handler — system (44 tools)"""
import json

TOOLS = [
    {"name": "pangu_stats", "description": "\u83b7\u53d6\u7cfb\u7edf\u7edf\u8ba1"},
    {"name": "pangu_graph", "description": "\u5bfc\u51fa\u77e5\u8bc6\u56fe\u8c31"},
    {"name": "pangu_identity", "description": "\u83b7\u53d6/\u8bbe\u7f6e AI \u8eab\u4efd"},
    {"name": "pangu_system_health", "description": "\u6df1\u5ea6\u7cfb\u7edf\u5065\u5eb7\u68c0\u67e5\uff08DB/\u7ed3\u6784/\u5d4c\u5165/\u7edf\u8ba1\uff09"},
    {"name": "pangu_system_metrics", "description": "\u83b7\u53d6 Prometheus \u683c\u5f0f\u7cfb\u7edf\u6307\u6807"},
    {"name": "pangu_config_get", "description": "\u83b7\u53d6\u5f53\u524d\u914d\u7f6e"},
    {"name": "pangu_config_set", "description": "\u66f4\u65b0\u914d\u7f6e\u9879"},
    {"name": "pangu_config_reload", "description": "\u70ed\u66f4\u65b0\u914d\u7f6e"},
    {"name": "pangu_schema_version", "description": "\u83b7\u53d6\u6570\u636e\u5e93 schema \u7248\u672c"},
    {"name": "pangu_schema_migrations", "description": "\u5217\u51fa\u6240\u6709\u8fc1\u79fb\u7248\u672c"},
    {"name": "pangu_api_server_start", "description": "\u542f\u52a8 REST API \u670d\u52a1\u5668"},
    {"name": "pangu_graph_infer", "description": "\u57fa\u4e8e\u77e5\u8bc6\u56fe\u8c31\u63a8\u7406"},
    {"name": "pangu_graph_contradictions", "description": "\u68c0\u6d4b\u56fe\u4e2d\u7684\u77db\u76fe\u5173\u7cfb"},
    {"name": "pangu_graph_causal_chain", "description": "\u56e0\u679c\u94fe\u5206\u6790"},
    {"name": "pangu_graph_temporal", "description": "\u65f6\u5e8f\u63a8\u7406"},
    {"name": "pangu_graph_analogy", "description": "\u7c7b\u6bd4\u68c0\u6d4b"},
    {"name": "pangu_graph_visualize", "description": "\u63a8\u7406\u8fc7\u7a0b\u53ef\u89c6\u5316"},
    {"name": "pangu_graph_entity", "description": "\u83b7\u53d6\u5b9e\u4f53\u4fe1\u606f"},
    {"name": "pangu_graph_path", "description": "\u67e5\u627e\u5b9e\u4f53\u95f4\u8def\u5f84"},
    {"name": "pangu_graph_quality", "description": "\u8bc4\u4f30\u56fe\u8c31\u8d28\u91cf"},
    {"name": "pangu_graph_stats", "description": "\u56fe\u8c31\u7edf\u8ba1"},
    {"name": "pangu_project_create", "description": "\u521b\u5efa\u9879\u76ee"},
    {"name": "pangu_project_switch", "description": "\u5207\u6362\u9879\u76ee"},
    {"name": "pangu_project_list", "description": "\u5217\u51fa\u6240\u6709\u9879\u76ee"},
    {"name": "pangu_project_active", "description": "\u83b7\u53d6\u5f53\u524d\u9879\u76ee"},
    {"name": "pangu_project_save", "description": "\u4fdd\u5b58\u8bb0\u5fc6\u5230\u5f53\u524d\u9879\u76ee"},
    {"name": "pangu_project_load", "description": "\u52a0\u8f7d\u9879\u76ee\u8bb0\u5fc6"},
    {"name": "pangu_project_search", "description": "\u8de8\u9879\u76ee\u641c\u7d22"},
    {"name": "pangu_project_merge", "description": "\u5408\u5e76\u9879\u76ee"},
    {"name": "pangu_project_delete", "description": "\u5220\u9664\u9879\u76ee"},
    {"name": "pangu_project_stats", "description": "\u9879\u76ee\u7edf\u8ba1"},
    {"name": "pangu_audit_log", "description": "\u8bb0\u5f55\u5ba1\u8ba1\u65e5\u5fd7"},
    {"name": "pangu_audit_query", "description": "\u67e5\u8be2\u5ba1\u8ba1\u65e5\u5fd7"},
    {"name": "pangu_audit_stats", "description": "\u64cd\u4f5c\u7edf\u8ba1"},
    {"name": "pangu_access_patterns", "description": "\u8bbf\u95ee\u6a21\u5f0f\u5206\u6790"},
    {"name": "pangu_security_summary", "description": "\u5b89\u5168\u6458\u8981"},
    {"name": "pangu_plugin_list", "description": "\u5217\u51fa\u6240\u6709\u63d2\u4ef6"},
    {"name": "pangu_plugin_enable", "description": "\u542f\u7528\u63d2\u4ef6"},
    {"name": "pangu_plugin_disable", "description": "\u7981\u7528\u63d2\u4ef6"},
    {"name": "pangu_plugin_config", "description": "\u83b7\u53d6\u63d2\u4ef6\u914d\u7f6e"},
    {"name": "pangu_plugin_discover", "description": "\u53d1\u73b0\u5e76\u52a0\u8f7d\u81ea\u5b9a\u4e49\u63d2\u4ef6"},
    {"name": "pangu_version_history", "description": "\u83b7\u53d6\u8bb0\u5fc6\u53d8\u66f4\u5386\u53f2"},
    {"name": "pangu_version_compare", "description": "\u6bd4\u8f83\u4e24\u4e2a\u7248\u672c\u7684\u5dee\u5f02"},
    {"name": "pangu_graph_visualize_web", "description": "\u751f\u6210\u77e5\u8bc6\u56fe\u8c31\u53ef\u89c6\u5316\u9875\u9762URL"},
]

HANDLERS = {}

async def handle_stats(server, drawers, arguments):
    """获取系统统计"""
    stats = {
        "palace": server.palace.stats(),
        "memory": server.memory.status(),
        "wiki": server.wiki.stats(),
        "knowledge_graph": server.knowledge_graph.stats(),
    }
    return json.dumps(stats, ensure_ascii=False, indent=2)

HANDLERS["pangu_stats"] = handle_stats

async def handle_graph(server, drawers, arguments):
    """导出知识图谱"""
    graph = {
        "palace": server.palace.export_structure(),
        "wiki": server.wiki.export_graph(),
        "knowledge_graph": server.knowledge_graph.export_graph(),
    }
    return json.dumps(graph, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph"] = handle_graph

async def handle_identity(server, drawers, arguments):
    """获取/设置 AI 身份"""
    action = arguments.get("action", "get")
    if action == "set":
        server.memory.l0.set_identity(arguments.get("text", ""))
        return json.dumps({"status": "identity set"})
    return json.dumps({"identity": server.memory.l0.render()}, ensure_ascii=False)

HANDLERS["pangu_identity"] = handle_identity

async def handle_system_health(server, drawers, arguments):
    """深度系统健康检查（DB/结构/嵌入/统计）"""
    from ...observability.health import deep_health_check
    return json.dumps(deep_health_check(), ensure_ascii=False, indent=2)

HANDLERS["pangu_system_health"] = handle_system_health

async def handle_system_metrics(server, drawers, arguments):
    """获取 Prometheus 格式系统指标"""
    from ...observability.metrics import get_metrics_response
    content, _ = get_metrics_response()
    if isinstance(content, bytes):
        content = content.decode()
    return content

HANDLERS["pangu_system_metrics"] = handle_system_metrics

async def handle_config_get(server, drawers, arguments):
    """获取当前配置"""
    key = arguments.get("key")
    cfg = server.config
    if key:
        val = getattr(cfg, key, None)
        return json.dumps({key: str(val) if val is not None else None}, ensure_ascii=False)
    # 返回所有非敏感配置
    safe = cfg.model_dump(exclude={"api_key", "llm_api_key", "siliconflow_key"})
    return json.dumps(safe, ensure_ascii=False, indent=2, default=str)

HANDLERS["pangu_config_get"] = handle_config_get

async def handle_config_set(server, drawers, arguments):
    """更新配置项"""
    key = arguments.get("key", "")
    value = arguments.get("value")
    if key and hasattr(server.config, key):
        setattr(server.config, key, value)
        return json.dumps({"status": "updated", "key": key, "value": str(value)}, ensure_ascii=False)
    return json.dumps({"error": f"unknown config key: {key}"})

HANDLERS["pangu_config_set"] = handle_config_set

async def handle_config_reload(server, drawers, arguments):
    """热更新配置"""
    from ...core.config import PanguConfig
    new_cfg = PanguConfig.reload()
    server.config = new_cfg
    return json.dumps({"status": "reloaded", "llm_provider": new_cfg.llm_provider}, ensure_ascii=False)

HANDLERS["pangu_config_reload"] = handle_config_reload

async def handle_schema_version(server, drawers, arguments):
    """获取数据库 schema 版本"""
    from ...store.migrations import get_schema_version
    version = get_schema_version()
    return json.dumps({"schema_version": version}, ensure_ascii=False)

HANDLERS["pangu_schema_version"] = handle_schema_version

async def handle_schema_migrations(server, drawers, arguments):
    """列出所有迁移版本"""
    from ...store.migrations import get_available_migrations
    migrations = get_available_migrations()
    return json.dumps(migrations, ensure_ascii=False, indent=2)

HANDLERS["pangu_schema_migrations"] = handle_schema_migrations

async def handle_api_server_start(server, drawers, arguments):
    """启动 REST API 服务器"""
    import uvicorn

    from ...api.server import create_app
    host = arguments.get("host", server.config.host)
    port = arguments.get("port", server.config.port)
    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    # 在后台启动
    import asyncio as _asyncio
    _asyncio.create_task(server.serve())
    return json.dumps({
        "status": "starting",
        "host": host,
        "port": port,
        "health_url": f"http://{host}:{port}/health",
    }, ensure_ascii=False)

HANDLERS["pangu_api_server_start"] = handle_api_server_start

async def handle_graph_infer(server, drawers, arguments):
    """基于知识图谱推理"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.infer(query)
    summary = gr.get_reasoning_summary(result)
    return json.dumps({
        "entities": len(result.entities),
        "paths": len(result.paths),
        "inferences": len(result.inferences),
        "confidence": result.confidence,
        "summary": summary,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_infer"] = handle_graph_infer

async def handle_graph_contradictions(server, drawers, arguments):
    """检测图中的矛盾关系"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    contradictions = gr.detect_contradictions()
    return json.dumps({
        "contradictions": contradictions,
        "count": len(contradictions),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_contradictions"] = handle_graph_contradictions

async def handle_graph_causal_chain(server, drawers, arguments):
    """因果链分析"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    entity_id = arguments.get("entity_id", "")
    max_depth = arguments.get("max_depth", 5)
    chain = gr.causal_chain_analysis(entity_id, max_depth)
    return json.dumps({"chain": chain, "length": len(chain)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_causal_chain"] = handle_graph_causal_chain

async def handle_graph_temporal(server, drawers, arguments):
    """时序推理"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.temporal_reasoning(query)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_temporal"] = handle_graph_temporal

async def handle_graph_analogy(server, drawers, arguments):
    """类比检测"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.analogy_detection(query)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_analogy"] = handle_graph_analogy

async def handle_graph_visualize(server, drawers, arguments):
    """推理过程可视化"""
    from ...memory.graph_reasoning import GraphReasoning
    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.infer(query)
    visualization = gr.visualize_reasoning(result)
    return json.dumps(visualization, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_visualize"] = handle_graph_visualize

async def handle_graph_entity(server, drawers, arguments):
    """获取实体信息"""
    from ...memory.graph_builder import get_builder
    gb = get_builder(server.config)
    name = arguments.get("name", "")
    entity = gb.get_entity(name)
    if not entity:
        return json.dumps({"error": f"Entity '{name}' not found"}, ensure_ascii=False, indent=2)
    rels = gb.get_entity_relations(name)
    return json.dumps({
        "name": entity.name, "type": entity.entity_type,
        "confidence": entity.confidence,
        "relations": rels, "relation_count": len(rels),
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_entity"] = handle_graph_entity

async def handle_graph_path(server, drawers, arguments):
    """查找实体间路径"""
    from ...memory.graph_builder import get_builder
    gb = get_builder(server.config)
    path = gb.find_path(arguments["from_name"], arguments["to_name"])
    return json.dumps({
        "from": arguments["from_name"], "to": arguments["to_name"],
        "path": path, "found": len(path) > 0,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_path"] = handle_graph_path

async def handle_graph_quality(server, drawers, arguments):
    """评估图谱质量"""
    from ...memory.graph_builder import get_builder
    gb = get_builder(server.config)
    return json.dumps(gb.assess_quality(), ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_quality"] = handle_graph_quality

async def handle_graph_stats(server, drawers, arguments):
    """图谱统计"""
    from ...memory.graph_builder import get_builder
    gb = get_builder(server.config)
    return json.dumps(gb.get_graph_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_stats"] = handle_graph_stats

async def handle_project_create(server, drawers, arguments):
    """创建项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.create_project(
        arguments["project_id"], arguments["name"],
        arguments.get("description", ""),
    ), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_create"] = handle_project_create

async def handle_project_switch(server, drawers, arguments):
    """切换项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.switch_project(arguments["project_id"]), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_switch"] = handle_project_switch

async def handle_project_list(server, drawers, arguments):
    """列出所有项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps({"projects": pm.list_projects()}, ensure_ascii=False, indent=2)

HANDLERS["pangu_project_list"] = handle_project_list

async def handle_project_active(server, drawers, arguments):
    """获取当前项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.get_active_project(), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_active"] = handle_project_active

async def handle_project_save(server, drawers, arguments):
    """保存记忆到当前项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.save_memories(drawers), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_save"] = handle_project_save

async def handle_project_load(server, drawers, arguments):
    """加载项目记忆"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    pid = arguments.get("project_id")
    memories = pm.load_memories(pid)
    return json.dumps({"memories": len(memories), "project": pid or pm._active_project}, ensure_ascii=False, indent=2)

HANDLERS["pangu_project_load"] = handle_project_load

async def handle_project_search(server, drawers, arguments):
    """跨项目搜索"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    results = pm.search_cross_project(arguments["query"], arguments.get("limit", 10))
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_project_search"] = handle_project_search

async def handle_project_merge(server, drawers, arguments):
    """合并项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.merge_project(
        arguments["source_id"], arguments.get("target_id"),
    ), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_merge"] = handle_project_merge

async def handle_project_delete(server, drawers, arguments):
    """删除项目"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.delete_project(arguments["project_id"]), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_delete"] = handle_project_delete

async def handle_project_stats(server, drawers, arguments):
    """项目统计"""
    from ...memory.project_manager import get_project_manager
    pm = get_project_manager(server.config)
    return json.dumps(pm.get_project_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_project_stats"] = handle_project_stats

async def handle_audit_log(server, drawers, arguments):
    """记录审计日志"""
    from ...memory.audit_analytics import get_audit
    audit = get_audit(server.config)
    entry = audit.log(arguments["operation"], arguments.get("target_id", ""))
    return json.dumps({"entry_id": entry.entry_id, "timestamp": entry.timestamp}, ensure_ascii=False, indent=2)

HANDLERS["pangu_audit_log"] = handle_audit_log

async def handle_audit_query(server, drawers, arguments):
    """查询审计日志"""
    from ...memory.audit_analytics import get_audit
    audit = get_audit(server.config)
    entries = audit.get_entries(
        arguments.get("operation"), arguments.get("user_id"),
        arguments.get("limit", 50),
    )
    return json.dumps({"entries": entries, "count": len(entries)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_audit_query"] = handle_audit_query

async def handle_audit_stats(server, drawers, arguments):
    """操作统计"""
    from ...memory.audit_analytics import get_audit
    audit = get_audit(server.config)
    return json.dumps(audit.get_operation_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_audit_stats"] = handle_audit_stats

async def handle_access_patterns(server, drawers, arguments):
    """访问模式分析"""
    from ...memory.audit_analytics import get_audit
    audit = get_audit(server.config)
    return json.dumps(audit.get_access_patterns(), ensure_ascii=False, indent=2)

HANDLERS["pangu_access_patterns"] = handle_access_patterns

async def handle_security_summary(server, drawers, arguments):
    """安全摘要"""
    from ...memory.audit_analytics import get_audit
    audit = get_audit(server.config)
    return json.dumps(audit.get_security_summary(), ensure_ascii=False, indent=2)

HANDLERS["pangu_security_summary"] = handle_security_summary

async def handle_plugin_list(server, drawers, arguments):
    """列出所有插件"""
    from ...plugins import get_plugin_manager
    pm = get_plugin_manager()
    return json.dumps({"plugins": pm.list_plugins(), "count": pm.plugin_count}, ensure_ascii=False, indent=2)

HANDLERS["pangu_plugin_list"] = handle_plugin_list

async def handle_plugin_enable(server, drawers, arguments):
    """启用插件"""
    from ...plugins import get_plugin_manager
    pm = get_plugin_manager()
    ok = pm.enable(arguments["name"])
    return json.dumps({"status": "enabled" if ok else "not_found"}, ensure_ascii=False, indent=2)

HANDLERS["pangu_plugin_enable"] = handle_plugin_enable

async def handle_plugin_disable(server, drawers, arguments):
    """禁用插件"""
    from ...plugins import get_plugin_manager
    pm = get_plugin_manager()
    ok = pm.disable(arguments["name"])
    return json.dumps({"status": "disabled" if ok else "not_found"}, ensure_ascii=False, indent=2)

HANDLERS["pangu_plugin_disable"] = handle_plugin_disable

async def handle_plugin_config(server, drawers, arguments):
    """获取插件配置"""
    from ...plugins import get_plugin_manager
    pm = get_plugin_manager()
    config = pm.get_config(arguments["name"])
    return json.dumps({"name": arguments["name"], "config": config}, ensure_ascii=False, indent=2)

HANDLERS["pangu_plugin_config"] = handle_plugin_config

async def handle_plugin_discover(server, drawers, arguments):
    """发现并加载自定义插件"""
    from ...plugins import get_plugin_manager
    pm = get_plugin_manager()
    path = arguments.get("path")
    count = pm.discover_plugins(path)
    return json.dumps({"discovered": count}, ensure_ascii=False, indent=2)

HANDLERS["pangu_plugin_discover"] = handle_plugin_discover

async def handle_version_history(server, drawers, arguments):
    """获取记忆变更历史"""
    from ...memory.versioning import get_version_control
    vc = get_version_control(server.config)
    memory_id = arguments.get("memory_id", "")
    history = vc.get_change_history(memory_id)
    return json.dumps({"history": history, "count": len(history)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_version_history"] = handle_version_history

async def handle_version_compare(server, drawers, arguments):
    """比较两个版本的差异"""
    from ...memory.versioning import get_version_control
    vc = get_version_control(server.config)
    memory_id = arguments.get("memory_id", "")
    v1 = arguments.get("v1", 1)
    v2 = arguments.get("v2", 2)
    diff = vc.compare_versions(memory_id, v1, v2)
    return json.dumps(diff, ensure_ascii=False, indent=2)

HANDLERS["pangu_version_compare"] = handle_version_compare

async def handle_graph_visualize_web(server, drawers, arguments):
    """生成知识图谱可视化页面URL"""
    from ...core.config import PanguConfig as _Cfg
    cfg = _Cfg.load()
    host = cfg.host if cfg.host != "0.0.0.0" else "127.0.0.1"
    url = f"http://{host}:{cfg.port}/graph"
    return json.dumps({"url": url, "description": "在浏览器中打开此URL查看交互式知识图谱"}, ensure_ascii=False, indent=2)

HANDLERS["pangu_graph_visualize_web"] = handle_graph_visualize_web