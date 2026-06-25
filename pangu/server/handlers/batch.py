"""盘古 MCP Handler — batch (3 tools)"""
import json

TOOLS = [
    {"name": "pangu_batch_scan", "description": "\u626b\u63cf\u76ee\u5f55\uff0c\u7edf\u8ba1\u5404\u7c7b\u578b\u6587\u4ef6\u6570\u91cf"},
    {"name": "pangu_batch_import", "description": "\u6279\u91cf\u5bfc\u5165\u76ee\u5f55\uff08\u81ea\u52a8\u68c0\u6d4b\u7c7b\u578b+\u53bb\u91cd+\u5165\u5e93\uff09"},
    {"name": "pangu_batch_stats", "description": "\u67e5\u770b\u6279\u91cf\u5bfc\u5165\u7edf\u8ba1"},
]

HANDLERS = {}

async def handle_batch_scan(server, drawers, arguments):
    """扫描目录，统计各类型文件数量"""
    from ..memory.batch_import import get_batch_importer
    importer = get_batch_importer(server.config)
    result = importer.scan_directory(arguments["dir_path"], recursive=arguments.get("recursive", True))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_batch_scan"] = handle_batch_scan

async def handle_batch_import(server, drawers, arguments):
    """批量导入目录（自动检测类型+去重+入库）"""
    from ..memory.batch_import import get_batch_importer
    importer = get_batch_importer(server.config)
    result = importer.import_directory(
        arguments["dir_path"],
        wing=arguments.get("wing", "default"),
        max_files=arguments.get("max_files", 100),
        tags=arguments.get("tags", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_batch_import"] = handle_batch_import

async def handle_batch_stats(server, drawers, arguments):
    """查看批量导入统计"""
    from ..memory.batch_import import get_batch_importer
    importer = get_batch_importer(server.config)
    return json.dumps(importer.get_stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_batch_stats"] = handle_batch_stats