"""盘古 REST API 路由 — /api/v2/memories（伏羲移植）"""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from pangu.api.abac import (
    Environment as AbacEnvironment,
)
from pangu.api.abac import (
    RequestContext as AbacRequestContext,
)
from pangu.api.abac import (
    Resource as AbacResource,
)
from pangu.api.abac import (
    Subject as AbacSubject,
)
from pangu.api.abac import (
    authorize as abac_authorize,
)
from pangu.api.abac import (
    evaluate as abac_evaluate,
)
from pangu.api.rbac import get_principal
from pangu.core.config import config
from pangu.core.palace import Drawer, Palace
from pangu.memory.decay import purge_below_floor
from pangu.memory.fts_search import FTS5SearchEngine
from pangu.memory.ingestion import remember
from pangu.memory.layers import MemoryStack
from pangu.memory.retrieval import recall, recall_context

logger = logging.getLogger("pangu.api.memories")
router = APIRouter(tags=["memories"])


# ── 请求/响应模型 ──

class MemoryCreateRequest(BaseModel):
    text: str = Field(..., description="记忆文本内容")
    wing: str = Field(default="default", description="Wing 名称")
    room: str = Field(default="general", description="Room 名称")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="重要性 (0-1)")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    source: str = Field(default="direct", description="来源类型")
    author: str = Field(default="", description="写入者 agent_id")
    created_by: str = Field(default="system", description="创建者")
    # ABAC 字段
    classification: int = Field(default=1, ge=0, le=3, description="密级 0=public,1=internal,2=confidential,3=top_secret")
    visibility: str = Field(default="tenant", description="public|tenant|private")


class MemoryUpdateRequest(BaseModel):
    text: str | None = Field(default=None, description="更新后的文本")
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = Field(default=None)
    facts: str | None = Field(default=None, description="提取的事实")


class MemoryResponse(BaseModel):
    id: str
    content: str
    wing: str
    room: str
    importance: float
    tags: list[str]
    created_at: str
    metadata: dict = Field(default_factory=dict)


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: dict | list | None = None

    @classmethod
    def ok(cls, data=None) -> dict:
        return {"code": 0, "message": "ok", "data": data}

    @classmethod
    def error(cls, code: int, message: str) -> dict:
        return {"code": code, "message": message, "data": None}


# ── ABAC 辅助函数 ──

def _memory_stack(request: Request) -> MemoryStack:
    """从 app.state 拿 MemoryStack 实例。"""
    stack = getattr(request.app.state, "memory", None)
    if stack is None:
        # 兜底新建（兜底可能没有 v2_db_path 配置）
        from pangu.core.config import PanguConfig
        cfg = PanguConfig()
        stack = MemoryStack(config=cfg)
    return stack


def _resolve_tenant_id(request: Request) -> str:
    """从 header / JWT claim 取 tenant_id。"""
    hdr = request.headers.get(config.abac_tenant_header, "")
    if hdr:
        return hdr
    principal = get_principal(request)
    if principal.method == "jwt" and principal.claims is not None:
        extra = getattr(principal.claims, "extra", {}) or {}
        return extra.get("tenant_id", config.abac_default_tenant)
    return config.abac_default_tenant


def _drawer_to_resource(d) -> AbacResource:
    """从记忆抽屉抽取 ABAC Resource 字段。"""
    md = getattr(d, "metadata", None) or {}
    if isinstance(md, dict) is False:
        md = {}
    return AbacResource(
        type="memories",
        id=getattr(d, "id", ""),
        owner_id=md.get("owner_id", "") if isinstance(md.get("owner_id", ""), str) else "",
        tenant_id=md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default",
        classification=int(md.get("classification", 0) or 0),
        visibility=md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private",
    )


def _dict_to_resource(d: dict) -> AbacResource:
    """从 dict 形式（recall_by_ids 返回）构造 ABAC Resource。"""
    md = d.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    return AbacResource(
        type="memories",
        id=d.get("id", ""),
        owner_id=md.get("owner_id", "") if isinstance(md.get("owner_id", ""), str) else "",
        tenant_id=md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default",
        classification=int(md.get("classification", 0) or 0),
        visibility=md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private",
    )


def _abac_evaluate_subject(request: Request, action: str, resource: AbacResource):
    """按当前 principal + tenant 构造 ctx 并 evaluate。"""
    principal = get_principal(request)
    tid = _resolve_tenant_id(request)
    subject = AbacSubject.from_principal(principal, tenant_id=tid)
    if request.headers.get(config.abac_tenant_header):
        subject.tenant_id = request.headers.get(config.abac_tenant_header)
    env = AbacEnvironment(
        client_ip=request.client.host if request.client else "",
        method=request.method,
        path=str(request.url.path),
    )
    ctx = AbacRequestContext(subject=subject, action=action, resource=resource, environment=env)
    return abac_evaluate(ctx), subject


# ── 路由 ──

@router.get("/memories")
async def list_memories(
    request: Request,
    wing: str = Query(default="default", description="Wing 名称"),
    room: str = Query(default=None, description="Room 名称"),
    author: str = Query(default=None, description="按 author 筛选"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at", description="排序字段"),
):
    """列出记忆（ABAC：按 tenant 隔离 + 公开资源可跨租户）。从 MemoryStack 读取。"""
    try:
        stack = _memory_stack(request)
        drawers = stack.get_drawers() or []
        if room:
            drawers = [d for d in drawers if getattr(d, "room", "") == room]
        # author 过滤
        if author:
            drawers = [d for d in drawers if getattr(d, "author", "") == author]
        # tenant 隔离
        tid = _resolve_tenant_id(request)
        principal = get_principal(request)
        subject = AbacSubject.from_principal(principal, tenant_id=tid)
        if request.headers.get(config.abac_tenant_header):
            subject.tenant_id = request.headers.get(config.abac_tenant_header)
        if not subject.is_admin:
            filtered = []
            for d in drawers:
                md = getattr(d, "metadata", None) or {}
                if not isinstance(md, dict):
                    md = {}
                vis = md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private"
                d_tid = md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default"
                if vis == "public" or d_tid == subject.tenant_id:
                    filtered.append(d)
            drawers = filtered
        total = len(drawers)
        drawers = drawers[offset:offset + limit]
        items = []
        for d in drawers:
            md = getattr(d, "metadata", None) or {}
            items.append({
                "id": getattr(d, "id", ""),
                "content": getattr(d, "content", ""),
                "wing": getattr(d, "wing", ""),
                "room": getattr(d, "room", ""),
                "importance": getattr(d, "importance", 0.5),
                "tags": getattr(d, "tags", []),
                "metadata": md if isinstance(md, dict) else {},
                "created_at": getattr(d, "created_at", ""),
            })
        return ApiResponse.ok({
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "tenant_id": subject.tenant_id,
        })
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories")
async def create_memory(req: MemoryCreateRequest, request: Request):
    """创建记忆（ABAC：tenant 隔离 + 密级 + 所有权 + 公开可访问性）。"""
    tid = _resolve_tenant_id(request)
    principal = get_principal(request)
    if principal.method == "anonymous":
        return ApiResponse.error(401, "Authentication required")
    resource = AbacResource(
        type="memories",
        id="",
        owner_id=principal.user_id,
        tenant_id=tid,
        classification=req.classification,
        visibility=req.visibility,
    )
    decision, subject = _abac_evaluate_subject(request, "write", resource)
    if not decision.allowed:
        return ApiResponse.error(403, f"ABAC deny: {decision.reason}")

    item_id, drawer = remember(
        raw_text=req.text,
        wing=req.wing,
        room=req.room,
        importance=req.importance,
        tags=req.tags,
        source=req.source,
        author=req.author,
        created_by=req.created_by,
    )
    if drawer is not None:
        drawer.metadata = dict(drawer.metadata or {})
        drawer.metadata.update({
            "owner_id": principal.user_id,
            "tenant_id": subject.tenant_id,
            "classification": req.classification,
            "visibility": req.visibility,
        })
        try:
            stack = _memory_stack(request)
            stack.add_drawer(drawer)
        except Exception as e:
            logger.warning(f"add_drawer failed: {e}")
    return ApiResponse.ok({
        "id": item_id,
        "content": drawer.content if drawer else req.text,
        "wing": req.wing,
        "room": req.room,
        "tenant_id": subject.tenant_id,
        "owner_id": principal.user_id,
        "policy": decision.policy,
    })


@router.get("/memories/search")
async def search_memories(
    q: str = Query(..., description="搜索关键词"),
    wing: str = Query(default=None, description="限定 Wing"),
    limit: int = Query(default=10, ge=1, le=50),
    search_type: str = Query(default="fts", description="搜索类型: fts/hybrid/vector"),
):
    """搜索记忆"""
    import json as _json
    from pathlib import Path as _Path

    def _do_search():
        drawers_file = _Path(config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return []
        with open(drawers_file, encoding="utf-8") as f:
            raw = _json.load(f)
        from pangu.core.palace import Drawer as _Drawer
        all_drawers = [_Drawer.from_dict(d) for d in raw]

        if wing:
            all_drawers = [d for d in all_drawers if d.wing == wing]

        fts_engine = FTS5SearchEngine(config)
        fts_engine.build_index(all_drawers)
        fts_results = fts_engine._fts_search(q, all_drawers, limit=limit)
        drawer_map = {d.id: d for d in all_drawers}
        results = []
        for did, score in sorted(fts_results.items(), key=lambda x: x[1], reverse=True)[:limit]:
            d = drawer_map.get(did)
            if not d:
                continue
            results.append({
                "id": d.id,
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags,
                "search_score": round(score, 4),
            })
        return results

    try:
        results = await asyncio.to_thread(_do_search)
        return ApiResponse.ok({
            "query": q,
            "results": results,
            "total": len(results) if results else 0,
        })
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    """获取单条记忆（ABAC：按 mid 加载资源，authorize 后返回）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    md = getattr(drawer, "metadata", None) or {}
    if not isinstance(md, dict):
        md = {}
    res = _drawer_to_resource(drawer)
    decision = abac_authorize(
        "memories", "read",
        resource_loader=lambda ctx: res,
    )(request)
    return ApiResponse.ok({
        "id": drawer.id,
        "content": drawer.content,
        "wing": drawer.wing,
        "room": drawer.room,
        "importance": drawer.importance,
        "tags": drawer.tags,
        "metadata": md,
        "created_at": getattr(drawer, "created_at", ""),
        "_policy": decision.policy,
    })


@router.put("/memories/{memory_id}")
async def update_memory(memory_id: str, req: MemoryUpdateRequest, request: Request):
    """更新记忆（ABAC：owner_or_admin / admin_full）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    res = _drawer_to_resource(drawer)
    abac_authorize(
        "memories", "write",
        resource_loader=lambda ctx: res,
    )(request)

    drawer.content = req.text if req.text is not None else drawer.content
    if req.importance is not None:
        drawer.importance = req.importance
    if req.tags is not None:
        drawer.tags = req.tags
    if req.facts is not None:
        drawer.metadata["facts"] = req.facts
    drawer.metadata["updated_at"] = datetime.now().isoformat()
    stack.add_drawer(drawer)
    return ApiResponse.ok({
        "id": drawer.id,
        "content": drawer.content,
        "wing": drawer.wing,
        "room": drawer.room,
        "importance": drawer.importance,
        "tags": drawer.tags,
        "metadata": drawer.metadata,
    })


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    """删除记忆（ABAC：owner_or_admin / admin_full）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    res = _drawer_to_resource(drawer)
    decision = abac_authorize(
        "memories", "delete",
        resource_loader=lambda ctx: res,
    )(request)
    stack.remove_drawer(memory_id)
    return ApiResponse.ok({"id": memory_id, "deleted": True, "policy": decision.policy})


@router.get("/memories/context")
async def get_context(
    drawer_id: str = Query(default="default", description="抽屉 ID"),
    budget: int = Query(default=2000, ge=100, le=10000),
):
    """获取上下文记忆"""
    try:
        context = recall_context(budget=budget)
        return ApiResponse.ok({
            "context": context,
            "budget": budget,
            "item_count": len(context) if context else 0,
        })
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/stats")
async def get_stats():
    """获取记忆统计（含搜索、健康、token）"""
    try:
        palace = Palace(config.palace_path)
        stats = palace.stats()

        # 搜索统计
        try:
            from pangu.memory.retrieval import get_search_stats, get_search_history
            stats["search"] = get_search_stats()
            stats["search"]["recent_history"] = get_search_history(limit=5)
        except Exception:
            pass

        # 健康检查
        try:
            from pangu.memory.layers import MemoryStack
            stack = MemoryStack(config)
            stats["health"] = stack.health_check()
        except Exception:
            pass

        # Token 统计
        try:
            from pangu.memory.layers import MemoryStack, _estimate_tokens
            stack = MemoryStack(config)
            drawers_file = Path(config.palace_path) / "drawers.json"
            if drawers_file.exists():
                import json
                with open(drawers_file) as f:
                    drawers = json.load(f)
                total_tokens = sum(_estimate_tokens(d.get("content", "")) for d in drawers)
                stats["tokens"] = {"total": total_tokens, "avg_per_memory": round(total_tokens / max(len(drawers), 1))}
        except Exception:
            pass

        return ApiResponse.ok(stats)
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories/decay")
async def trigger_decay():
    """触发记忆衰减"""
    try:
        from pangu.memory.decay import decay_batch
        all_drawers = recall()
        if all_drawers:
            drawers = [Drawer.from_dict(d) for d in all_drawers]
            result = decay_batch(drawers)
            return ApiResponse.ok(result)
        return ApiResponse.ok({"decayed": 0, "message": "no memories to decay"})
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories/purge")
async def purge_low_memories(threshold: float = Query(default=0.15, ge=0.0, le=1.0)):
    """清除低于阈值的记忆"""
    try:
        all_drawers = recall()
        if all_drawers:
            drawers = [Drawer.from_dict(d) for d in all_drawers]
            result = purge_below_floor(drawers, threshold)
            return ApiResponse.ok(result)
        return ApiResponse.ok({"purged": 0})
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/export")
async def export_memories(
    wing: str = Query(default=None),
    format: str = Query(default="json"),
):
    """导出记忆数据"""
    try:
        results = recall(wing=wing)
        return ApiResponse.ok({
            "format": format,
            "items": results,
            "total": len(results) if results else 0,
            "exported_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return ApiResponse.error(500, str(e))
