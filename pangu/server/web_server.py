"""盘古 Web 服务器 — 提供记忆管理 Web UI 和 REST API
=====================================================
盘古定位为专业的记忆系统，API 只提供记忆管理功能。
不包含 Agent 执行功能（问答、对话、任务执行等）。
上层 Agent 框架应通过 MCP 接口调用记忆检索结果后自行实现推理。"""
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ..core.config import PanguConfig
from ..core.llm import LLMEngine
from ..core.palace import Drawer, Palace, WikiPage
from ..memory.knowledge_graph import KnowledgeGraph
from ..memory.layers import MemoryStack
from ..mining.miners import ConvoMiner, FileMiner
from ..search.engine import HybridSearch
from ..wiki.engine import WikiEngine

# ── Pydantic 模型 ──

class MemoryCreate(BaseModel):
    content: str
    wing: str = "default"
    room: str = "general"
    hall: str = "hall_events"
    importance: float = 3.0
    tags: list[str] = []

class WikiPageCreate(BaseModel):
    title: str
    wing: str = "default"
    content: str = ""
    summary: str = ""
    tags: list[str] = []

class SearchQuery(BaseModel):
    query: str
    wing: str = None
    room: str = None
    n_results: int = 10

class EntityCreate(BaseModel):
    id: str
    name: str
    type: str = "concept"
    description: str = ""

class RelationCreate(BaseModel):
    id: str
    subject_id: str
    predicate: str
    object_id: str
    valid_from: str = None
    valid_until: str = None
    confidence: float = 1.0


# ── 创建应用 ──

def create_app(config: PanguConfig = None) -> FastAPI:
    config = config or PanguConfig.load()
    config.ensure_dirs()

    app = FastAPI(title="盘古 — 专业记忆系统", version="0.1.0")

    # 静态文件路径
    static_dir = Path(__file__).parent.parent / "ui" / "static"
    templates_dir = Path(__file__).parent.parent / "ui" / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(templates_dir)) if templates_dir.exists() else None

    # 初始化核心组件
    palace = Palace(config.palace_path)
    memory = MemoryStack(config)
    wiki = WikiEngine(config)
    kg = KnowledgeGraph(config)
    search = HybridSearch(config)
    llm = LLMEngine(config)

    # ── 页面路由 ──

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """主页面"""
        if templates:
            return templates.TemplateResponse("index.html", {"request": request})
        return HTMLResponse("<h1>盘古记忆系统</h1><p>Web UI 模板未找到，请使用 API 接口。</p>")

    # ── API 路由 ──

    # Palace
    @app.get("/api/wings")
    async def list_wings():
        return {"wings": palace.list_wings()}

    @app.post("/api/wings")
    async def create_wing(name: str = Form(...), description: str = Form("")):
        return {"wing": palace.create_wing(name, description)}

    @app.get("/api/wings/{wing}/rooms")
    async def list_rooms(wing: str):
        return palace.list_rooms(wing)

    @app.post("/api/wings/{wing}/rooms")
    async def create_room(wing: str, room: str = Form(...), description: str = Form("")):
        return {"room": palace.create_room(wing, room, description)}

    @app.delete("/api/wings/{wing}")
    async def delete_wing(wing: str):
        if palace.delete_wing(wing):
            return {"status": "deleted"}
        raise HTTPException(400, "无法删除 default wing")

    @app.delete("/api/wings/{wing}/rooms/{room}")
    async def delete_room(wing: str, room: str):
        if palace.delete_room(wing, room):
            return {"status": "deleted"}
        raise HTTPException(404, "Room 不存在")

    # 记忆
    @app.get("/api/memories")
    async def list_memories(wing: str = None, room: str = None, limit: int = 50):
        drawers = memory.get_drawers()
        if wing:
            drawers = [d for d in drawers if d.wing == wing]
        if room:
            drawers = [d for d in drawers if d.room == room]
        return {"memories": [d.to_dict() for d in drawers[-limit:]], "total": len(drawers)}

    @app.post("/api/memories")
    async def add_memory(data: MemoryCreate):
        drawer = Drawer(
            id=f"mem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            content=data.content,
            wing=data.wing,
            room=data.room,
            hall=data.hall,
            importance=data.importance,
            tags=data.tags,
        )
        memory.add_drawer(drawer)
        return {"status": "added", "memory": drawer.to_dict()}

    @app.delete("/api/memories/{memory_id}")
    async def delete_memory(memory_id: str):
        drawers = memory.get_drawers()
        drawers = [d for d in drawers if d.id != memory_id]
        # 重新保存
        memory._drawers = drawers
        memory._save_drawers()
        return {"status": "deleted"}

    @app.post("/api/memories/search")
    async def search_memories(data: SearchQuery):
        drawers = memory.get_drawers()
        results = search.search(data.query, drawers, wing=data.wing, room=data.room, n_results=data.n_results)
        return {"results": results, "query": data.query}

    @app.get("/api/memories/wake-up")
    async def wake_up(wing: str = None):
        return {"context": memory.wake_up(wing=wing)}

    # Wiki
    @app.get("/api/wiki/pages")
    async def list_wiki_pages(wing: str = None, tag: str = None):
        pages = wiki.list_pages(wing=wing, tag=tag)
        return {"pages": [p.to_dict() for p in pages]}

    @app.get("/api/wiki/pages/{page_id}")
    async def get_wiki_page(page_id: str):
        page = wiki.get_page(page_id)
        if page:
            linked = wiki.get_linked_pages(page_id)
            backlinks = wiki.get_backlinks(page_id)
            return {
                "page": page.to_dict(),
                "linked": [p.to_dict() for p in linked],
                "backlinks": [p.to_dict() for p in backlinks],
            }
        raise HTTPException(404, "页面不存在")

    @app.post("/api/wiki/pages")
    async def create_wiki_page(data: WikiPageCreate):
        page = WikiPage(
            id=f"wiki_{datetime.now().strftime('%Y%m%d%H%M%S')}_{data.title[:20]}",
            title=data.title,
            wing=data.wing,
            content=data.content or f"# {data.title}\n\n待完善...",
            summary=data.summary,
            tags=data.tags,
        )
        wiki.create_page(page)
        return {"status": "created", "page": page.to_dict()}

    @app.put("/api/wiki/pages/{page_id}")
    async def update_wiki_page(page_id: str, data: WikiPageCreate):
        page = wiki.get_page(page_id)
        if not page:
            raise HTTPException(404, "页面不存在")
        page.title = data.title
        page.content = data.content
        page.summary = data.summary
        page.tags = data.tags
        wiki.update_page(page)
        return {"status": "updated", "page": page.to_dict()}

    @app.delete("/api/wiki/pages/{page_id}")
    async def delete_wiki_page(page_id: str):
        if wiki.delete_page(page_id):
            return {"status": "deleted"}
        raise HTTPException(404, "页面不存在")

    @app.post("/api/wiki/generate")
    async def auto_generate_wiki(title: str = Form(...), wing: str = Form("default")):
        drawers = memory.get_drawers()
        memories = [
            {"content": d.content, "wing": d.wing, "room": d.room}
            for d in drawers if d.wing == wing
        ]
        page = await wiki.auto_generate_page(llm, title, wing, memories)
        return {"status": "generated", "page": page.to_dict()}

    # LMM 记忆处理
    @app.post("/api/llm/classify")
    async def classify_content(content: str = Form(...)):
        result = await llm.classify_memory(content)
        return {"result": result}

    @app.post("/api/llm/summarize")
    async def summarize_memories(wing: str = Form(None)):
        drawers = memory.get_drawers()
        if wing:
            drawers = [d for d in drawers if d.wing == wing]
        memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:20]]
        summary = await llm.summarize_memories(memories)
        return {"summary": summary}

    @app.post("/api/llm/insight")
    async def get_insight(topic: str = Form("")):
        drawers = memory.get_drawers()
        if topic:
            related = search.search(topic, drawers)
        else:
            related = [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:5]]
        insight = await llm.generate_insight(related)
        return {"insight": insight}

    # 记忆巩固
    @app.get("/api/consolidation/stats")
    async def get_consolidation_stats():
        return memory.get_consolidation_stats()

    @app.get("/api/consolidation/forgotten")
    async def find_forgotten():
        forgotten = memory.find_forgotten()
        return {"forgotten": [d.to_dict() for d in forgotten], "count": len(forgotten)}

    @app.post("/api/consolidation/compress")
    async def compress_memories(target_count: int = Form(5)):
        compressible = memory.find_compressible()
        if not compressible:
            return {"status": "nothing to compress"}
        memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in compressible]
        result = await llm.compress_memories(memories, target_count=target_count)
        return {"status": "compressed", "result": result}

    @app.post("/api/llm/detect-associations")
    async def detect_associations(wing: str = Form(None)):
        drawers = memory.get_drawers()
        if wing:
            drawers = [d for d in drawers if d.wing == wing]
        memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:20]]
        result = await llm.detect_associations(memories)
        return result

    @app.get("/api/memories/{memory_id}/importance")
    async def get_memory_importance(memory_id: str):
        importance = memory.get_memory_importance(memory_id)
        return {"memory_id": memory_id, "importance": importance}

    # 迁移与备份
    @app.post("/api/export")
    async def export_data(format: str = Form("json"), wing: str = Form(None)):
        from ..memory.migration import MemoryExporter
        exporter = MemoryExporter(config)
        output = f"/tmp/pangu_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}" if format != "zip" else f"/tmp/pangu_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        result = exporter.export_all(output, format)
        return {"status": "exported", "path": result}

    @app.post("/api/import")
    async def import_data(file_path: str = Form(...), merge: bool = Form(True)):
        from ..memory.migration import MemoryImporter
        importer = MemoryImporter(config)
        stats = importer.import_from_file(file_path, merge=merge)
        return stats

    @app.get("/api/backups")
    async def list_backups():
        from ..memory.migration import BackupManager
        manager = BackupManager(config)
        return {"backups": manager.list_backups()}

    @app.post("/api/backups")
    async def create_backup(label: str = Form(None)):
        from ..memory.migration import BackupManager
        manager = BackupManager(config)
        path = manager.create_backup(label=label)
        return {"status": "backup_created", "path": path}

    @app.post("/api/backups/{backup_name}/restore")
    async def restore_backup(backup_name: str, merge: bool = Form(False)):
        from ..memory.migration import BackupManager
        manager = BackupManager(config)
        result = manager.restore_backup(backup_name, merge=merge)
        return result

    # 多模态
    @app.post("/api/multimodal/extract-file")
    async def extract_multimodal(file_path: str = Form(...), wing: str = Form("default"), room: str = Form(None), tags: str = Form("")):
        from ..memory.multimodal import MultimodalExtractor
        extractor = MultimodalExtractor()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        mm = extractor.extract_from_file(file_path, wing=wing, room=room, tags=tag_list)
        return mm.to_dict()

    @app.get("/api/search/cache-stats")
    async def get_search_cache_stats():
        embedder = getattr(search.semantic, '_embedder', None)
        if embedder:
            return embedder.cache_stats()
        return {"status": "embedder not initialized"}

    # 插件
    @app.get("/api/plugins")
    async def list_plugins():
        from ..plugins import PluginManager
        mgr = PluginManager()
        return {"plugins": mgr.list_plugins()}

    # 知识图谱
    @app.get("/api/kg/entities")
    async def list_entities(type: str = None):
        return {"entities": kg.list_entities(entity_type=type)}

    @app.post("/api/kg/entities")
    async def add_entity(data: EntityCreate):
        entity = kg.add_entity(data.id, data.name, data.type, data.description)
        return {"entity": entity}

    @app.get("/api/kg/entities/{entity_id}")
    async def get_entity(entity_id: str):
        entity = kg.get_entity(entity_id)
        if entity:
            return {"entity": entity}
        raise HTTPException(404, "实体不存在")

    @app.get("/api/kg/entities/{entity_id}/neighbors")
    async def get_neighbors(entity_id: str):
        return kg.get_neighbors(entity_id)

    @app.post("/api/kg/relations")
    async def add_relation(data: RelationCreate):
        rel = kg.add_relation(
            id=data.id, subject_id=data.subject_id,
            predicate=data.predicate, object_id=data.object_id,
            valid_from=data.valid_from, valid_until=data.valid_until,
            confidence=data.confidence,
        )
        return {"relation": rel}

    @app.get("/api/kg/relations")
    async def query_relations(
        subject_id: str = None, object_id: str = None,
        predicate: str = None, at_time: str = None,
    ):
        relations = kg.query_relations(
            subject_id=subject_id, object_id=object_id,
            predicate=predicate, at_time=at_time,
        )
        return {"relations": relations}

    # 隧道
    @app.get("/api/tunnels")
    async def list_tunnels():
        return {"tunnels": palace.list_tunnels()}

    @app.post("/api/tunnels")
    async def create_tunnel(wing_a: str = Form(...), wing_b: str = Form(...), room: str = Form(...)):
        tunnel = palace.create_tunnel(wing_a, wing_b, room)
        return {"tunnel": tunnel}

    # 挖掘
    @app.post("/api/mine/files")
    async def mine_files(directory: str = Form(...), wing: str = Form(None)):
        miner = FileMiner(config)
        drawers = miner.scan_directory(directory, wing=wing)
        memory.add_drawers(drawers)
        return {"status": "mined", "count": len(drawers)}

    @app.post("/api/mine/convos")
    async def mine_convos(file_path: str = Form(...), wing: str = Form(None), format: str = Form("jsonl")):
        miner = ConvoMiner(config)
        if format == "chatgpt":
            drawers = miner.parse_chatgpt_json(file_path, wing=wing)
        else:
            drawers = miner.parse_claude_jsonl(file_path, wing=wing)
        memory.add_drawers(drawers)
        return {"status": "mined", "count": len(drawers)}

    # 统计
    @app.get("/api/stats")
    async def get_stats():
        return {
            "palace": palace.stats(),
            "memory": memory.status(),
            "wiki": wiki.stats(),
            "knowledge_graph": kg.stats(),
        }

    @app.get("/api/graph")
    async def get_graph():
        return {
            "palace": palace.export_structure(),
            "wiki": wiki.export_graph(),
            "knowledge_graph": kg.export_graph(),
        }

    @app.get("/api/identity")
    async def get_identity():
        return {"identity": memory.l0.render()}

    @app.post("/api/identity")
    async def set_identity(text: str = Form(...)):
        memory.l0.set_identity(text)
        return {"status": "identity set"}

    @app.on_event("shutdown")
    async def shutdown():
        await llm.close()

    return app
