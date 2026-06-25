"""盘古 MCP Handler — io_tools (30 tools)"""
import json

TOOLS = [
    {"name": "pangu_export", "description": "\u5bfc\u51fa\u8bb0\u5fc6\u6570\u636e\u4e3a JSON/ZIP"},
    {"name": "pangu_import", "description": "\u4ece\u6587\u4ef6\u5bfc\u5165\u8bb0\u5fc6\u6570\u636e"},
    {"name": "pangu_backup", "description": "\u521b\u5efa\u5907\u4efd\u5feb\u7167"},
    {"name": "pangu_list_backups", "description": "\u5217\u51fa\u6240\u6709\u5907\u4efd"},
    {"name": "pangu_restore_backup", "description": "\u4ece\u5907\u4efd\u6062\u590d"},
    {"name": "pangu_backup", "description": "\u5168\u91cf\u5907\u4efd\u8bb0\u5fc6"},
    {"name": "pangu_list_backups", "description": "\u5217\u51fa\u6240\u6709\u5907\u4efd"},
    {"name": "pangu_restore_backup", "description": "\u6062\u590d\u5907\u4efd"},
    {"name": "pangu_backup_stats", "description": "\u5907\u4efd\u7edf\u8ba1"},
    {"name": "pangu_export_json", "description": "JSON\u683c\u5f0f\u5bfc\u51fa"},
    {"name": "pangu_export_markdown", "description": "Markdown\u683c\u5f0f\u5bfc\u51fa"},
    {"name": "pangu_export_csv", "description": "CSV\u683c\u5f0f\u5bfc\u51fa"},
    {"name": "pangu_export_yaml", "description": "YAML\u683c\u5f0f\u5bfc\u51fa"},
    {"name": "pangu_export_obsidian", "description": "Obsidian\u683c\u5f0f\u5bfc\u51fa\uff08\u5e26WikiLink\uff09"},
    {"name": "pangu_import_smart", "description": "\u667a\u80fd\u5bfc\u5165\uff08\u81ea\u52a8\u68c0\u6d4b\u683c\u5f0f\uff09"},
    {"name": "pangu_list_exports", "description": "\u5217\u51fa\u6240\u6709\u5bfc\u51fa\u6587\u4ef6"},
    {"name": "pangu_export_stats", "description": "\u5bfc\u51fa\u5bfc\u5165\u7edf\u8ba1"},
    {"name": "pangu_env_check", "description": "\u8fd0\u884c\u73af\u5883\u68c0\u67e5"},
    {"name": "pangu_startup_validate", "description": "\u542f\u52a8\u6821\u9a8c"},
    {"name": "pangu_importance_score", "description": "\u8ba1\u7b97\u8bb0\u5fc6\u91cd\u8981\u6027\u8bc4\u5206"},
    {"name": "pangu_auto_collect", "description": "\u4ece\u4f1a\u8bdd\u6587\u4ef6\u81ea\u52a8\u63d0\u53d6\u8bb0\u5fc6"},
    {"name": "pangu_collect_file", "description": "\u4ece\u6307\u5b9a\u6587\u4ef6\u91c7\u96c6\u8bb0\u5fc6"},
    {"name": "pangu_collect_dir", "description": "\u4ece\u76ee\u5f55\u6279\u91cf\u91c7\u96c6\u8bb0\u5fc6"},
    {"name": "pangu_collect_all", "description": "\u626b\u63cf\u6240\u6709\u914d\u7f6e\u6e90\u81ea\u52a8\u91c7\u96c6"},
    {"name": "pangu_collect_stats", "description": "\u67e5\u770b\u91c7\u96c6\u7edf\u8ba1"},
    {"name": "pangu_feishu_send", "description": "\u53d1\u9001\u98de\u4e66\u901a\u77e5\uff08\u6587\u672c\u6d88\u606f\uff09"},
    {"name": "pangu_feishu_card", "description": "\u53d1\u9001\u98de\u4e66\u5361\u7247\u901a\u77e5"},
    {"name": "pangu_feishu_status", "description": "\u67e5\u770b\u98de\u4e66 Webhook \u72b6\u6001"},
    {"name": "pangu_watch_directory", "description": "\u76d1\u63a7\u76ee\u5f55\u53d8\u66f4\u5e76\u81ea\u52a8\u63d0\u53d6\u8bb0\u5fc6"},
    {"name": "pangu_watch_status", "description": "\u67e5\u770b\u6587\u4ef6\u76d1\u63a7\u72b6\u6001"},
]

HANDLERS = {}

async def handle_export(server, drawers, arguments):
    """导出记忆数据为 JSON/ZIP"""
    from ..memory.migration import MemoryExporter
    exporter = MemoryExporter(server.config)
    output = arguments.get("output_path", "/tmp/pangu_export.json")
    fmt = arguments.get("format", "json")
    result_path = exporter.export_all(output, format=fmt)
    return json.dumps({"status": "exported", "path": result_path}, ensure_ascii=False)

HANDLERS["pangu_export"] = handle_export

async def handle_import(server, drawers, arguments):
    """从文件导入记忆数据"""
    from ..memory.migration import MemoryImporter
    importer = MemoryImporter(server.config)
    file_path = arguments.get("file_path", "")
    merge = arguments.get("merge", True)
    stats = importer.import_from_file(file_path, merge=merge)
    return json.dumps(stats, ensure_ascii=False)

HANDLERS["pangu_import"] = handle_import

async def handle_backup(server, drawers, arguments):
    """创建备份快照"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    desc = arguments.get("description", "")
    info = be.backup(drawers, desc)
    return json.dumps({
        "backup_id": info.backup_id, "memories": info.memory_count,
        "size": info.size_bytes, "checksum": info.checksum,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_backup"] = handle_backup

async def handle_list_backups(server, drawers, arguments):
    """列出所有备份"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    return json.dumps({"backups": be.list_backups(), "count": len(be.list_backups())}, ensure_ascii=False, indent=2)

HANDLERS["pangu_list_backups"] = handle_list_backups

async def handle_restore_backup(server, drawers, arguments):
    """从备份恢复"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    result = be.restore(arguments["backup_id"])
    result.pop("drawers", None)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_restore_backup"] = handle_restore_backup

async def handle_backup(server, drawers, arguments):
    """全量备份记忆"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    desc = arguments.get("description", "")
    info = be.backup(drawers, desc)
    return json.dumps({
        "backup_id": info.backup_id, "memories": info.memory_count,
        "size": info.size_bytes, "checksum": info.checksum,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_backup"] = handle_backup

async def handle_list_backups(server, drawers, arguments):
    """列出所有备份"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    return json.dumps({"backups": be.list_backups(), "count": len(be.list_backups())}, ensure_ascii=False, indent=2)

HANDLERS["pangu_list_backups"] = handle_list_backups

async def handle_restore_backup(server, drawers, arguments):
    """恢复备份"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    result = be.restore(arguments["backup_id"])
    result.pop("drawers", None)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_restore_backup"] = handle_restore_backup

async def handle_backup_stats(server, drawers, arguments):
    """备份统计"""
    from ..memory.backup_restore import get_backup_engine
    be = get_backup_engine(server.config)
    return json.dumps(be.get_backup_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_backup_stats"] = handle_backup_stats

async def handle_export_json(server, drawers, arguments):
    """JSON格式导出"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.export_json(drawers, arguments.get("filepath"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_export_json"] = handle_export_json

async def handle_export_markdown(server, drawers, arguments):
    """Markdown格式导出"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.export_markdown(drawers, arguments.get("filepath"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_export_markdown"] = handle_export_markdown

async def handle_export_csv(server, drawers, arguments):
    """CSV格式导出"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.export_csv(drawers, arguments.get("filepath"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_export_csv"] = handle_export_csv

async def handle_export_yaml(server, drawers, arguments):
    """YAML格式导出"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.export_yaml(drawers, arguments.get("filepath"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_export_yaml"] = handle_export_yaml

async def handle_export_obsidian(server, drawers, arguments):
    """Obsidian格式导出（带WikiLink）"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.export_obsidian(drawers, arguments.get("filepath"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_export_obsidian"] = handle_export_obsidian

async def handle_import_smart(server, drawers, arguments):
    """智能导入（自动检测格式）"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    result = ee.smart_import(arguments["filepath"])
    result.pop("data", None)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_import_smart"] = handle_import_smart

async def handle_list_exports(server, drawers, arguments):
    """列出所有导出文件"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    return json.dumps({"exports": ee.list_exports()}, ensure_ascii=False, indent=2)

HANDLERS["pangu_list_exports"] = handle_list_exports

async def handle_export_stats(server, drawers, arguments):
    """导出导入统计"""
    from ..memory.export_import import get_export_engine
    ee = get_export_engine(server.config)
    return json.dumps(ee.get_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_export_stats"] = handle_export_stats

async def handle_env_check(server, drawers, arguments):
    """运行环境检查"""
    from ..memory.production import check_environment
    return json.dumps(check_environment(), ensure_ascii=False, indent=2)

HANDLERS["pangu_env_check"] = handle_env_check

async def handle_startup_validate(server, drawers, arguments):
    """启动校验"""
    from ..memory.production import default_startup_checks
    validator = default_startup_checks()
    ok, results = validator.validate()
    return json.dumps({"ok": ok, "checks": results}, ensure_ascii=False, indent=2)

HANDLERS["pangu_startup_validate"] = handle_startup_validate

async def handle_importance_score(server, drawers, arguments):
    """计算记忆重要性评分"""
    from ..memory.importance_scorer import get_importance_scorer
    scorer = get_importance_scorer(server.config)
    memory_id = arguments.get("memory_id", "")
    context = arguments.get("context", "")
    # 查找记忆
    drawer = next((d for d in drawers if d.id == memory_id), None)
    if not drawer:
        return json.dumps({"error": f"Memory not found: {memory_id}"})
    result = scorer.score(drawer, context)
    return json.dumps({
        "score": result.score,
        "factors": result.factors,
        "explanation": result.explanation,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_importance_score"] = handle_importance_score

async def handle_auto_collect(server, drawers, arguments):
    """从会话文件自动提取记忆"""
    from ..memory.auto_collector import AutoCollector
    collector = AutoCollector(server.config)
    session_file = arguments.get("session_file", "")
    min_importance = arguments.get("min_importance", 0.3)
    result = collector.collect_from_file(session_file, min_importance=min_importance)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_auto_collect"] = handle_auto_collect

async def handle_collect_file(server, drawers, arguments):
    """从指定文件采集记忆"""
    from ..memory.collector import get_collector
    collector = get_collector(server.config)
    results = collector.collect_from_file(
        arguments["file_path"],
        min_importance=arguments.get("min_importance", 0.3),
    )
    return json.dumps({"collected": len(results), "memories": results}, ensure_ascii=False, indent=2)

HANDLERS["pangu_collect_file"] = handle_collect_file

async def handle_collect_dir(server, drawers, arguments):
    """从目录批量采集记忆"""
    from ..memory.collector import get_collector
    collector = get_collector(server.config)
    result = collector.collect_from_dir(
        arguments["dir_path"],
        pattern=arguments.get("pattern", "*.md"),
        min_importance=arguments.get("min_importance", 0.3),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_collect_dir"] = handle_collect_dir

async def handle_collect_all(server, drawers, arguments):
    """扫描所有配置源自动采集"""
    from ..memory.collector import get_collector
    collector = get_collector(server.config)
    result = collector.collect_all_sources(
        min_importance=arguments.get("min_importance", 0.3),
    )
    from ..memory.memory_events import get_event_stream
    count = result.get("total", 0)
    if count > 0:
        get_event_stream(server.config).emit("memory.collect", "", {"count": count, "sources": result.get("sources", {})})
HANDLERS["pangu_collect_all"] = handle_collect_all

async def handle_collect_stats(server, drawers, arguments):
    """查看采集统计"""
    from ..memory.collector import get_collector
    collector = get_collector(server.config)
    return json.dumps(collector.get_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_collect_stats"] = handle_collect_stats

async def handle_feishu_send(server, drawers, arguments):
    """发送飞书通知（文本消息）"""
    from ..memory.feishu_webhook import get_feishu_webhook
    from ..core.config import PanguConfig as _Cfg
    cfg = _Cfg.load()
    wh = get_feishu_webhook(cfg.feishu_webhook_url)
    result = wh.send_text(arguments["text"])
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_feishu_send"] = handle_feishu_send

async def handle_feishu_card(server, drawers, arguments):
    """发送飞书卡片通知"""
    from ..memory.feishu_webhook import get_feishu_webhook
    from ..core.config import PanguConfig as _Cfg
    cfg = _Cfg.load()
    wh = get_feishu_webhook(cfg.feishu_webhook_url)
    lines = [l.strip() for l in arguments["content"].split("\n") if l.strip()]
    result = wh.send_card(arguments["title"], lines, arguments.get("color", "blue"))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_feishu_card"] = handle_feishu_card

async def handle_feishu_status(server, drawers, arguments):
    """查看飞书 Webhook 状态"""
    from ..core.config import PanguConfig as _Cfg
    cfg = _Cfg.load()
    configured = bool(cfg.feishu_webhook_url)
    return json.dumps({
        "configured": configured,
        "webhook_url": cfg.feishu_webhook_url[:50] + "..." if len(cfg.feishu_webhook_url) > 50 else cfg.feishu_webhook_url,
    }, ensure_ascii=False, indent=2)

HANDLERS["pangu_feishu_status"] = handle_feishu_status

async def handle_watch_directory(server, drawers, arguments):
    """监控目录变更并自动提取记忆"""
    from ..memory.file_watcher import get_file_watcher
    watcher = get_file_watcher(server.config)
    result = watcher.watch_directory(
        arguments["dir_path"],
        pattern=arguments.get("pattern", "*.md"),
        recursive=arguments.get("recursive", True),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_watch_directory"] = handle_watch_directory

async def handle_watch_status(server, drawers, arguments):
    """查看文件监控状态"""
    from ..memory.file_watcher import get_file_watcher
    watcher = get_file_watcher(server.config)
    stats = watcher.get_stats()
    dirs = watcher.get_watched_dirs()
    stats["directories"] = dirs
    return json.dumps(stats, ensure_ascii=False, indent=2)

HANDLERS["pangu_watch_status"] = handle_watch_status