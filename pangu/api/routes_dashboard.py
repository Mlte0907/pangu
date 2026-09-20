"""盘古 REST API 路由 — /api/v2/dashboard（仪表盘）

提供统计面板、平台管理、知识库浏览、快照管理等功能。
"""

import logging
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pangu.api.admin_auth import verify_admin as _verify_admin

logger = logging.getLogger("pangu.api.routes_dashboard")

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats")
async def get_stats(request: Request):
    """获取系统统计信息"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.core.config import PanguConfig
    from pangu.memory.drawer_storage import JsonDrawerStorage
    from pangu.memory.knowledge import get_knowledge_engine
    from pangu.memory.evolution import get_memory_evolution

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers = JsonDrawerStorage(str(cfg.authoritative_drawers_path)).load()

    # 记忆统计
    total_memories = len(drawers)
    sources = Counter()
    wings = Counter()
    for d in drawers:
        source = d.source or d.room or "unknown"
        sources[source] += 1
        wings[d.wing] += 1

    # 知识库统计
    knowledge_engine = get_knowledge_engine()
    knowledge_stats = knowledge_engine.get_stats()

    # 快照统计
    evolution = get_memory_evolution()
    snapshots = evolution.get_snapshots()
    total_snapshots = len(snapshots)

    return {
        "memories": {
            "total": total_memories,
            "by_source": dict(sources.most_common()),
            "by_wing": dict(wings.most_common()),
        },
        "knowledge": knowledge_stats,
        "snapshots": {
            "total": total_snapshots,
        },
    }


@router.get("/dashboard/platforms")
async def list_platforms(request: Request):
    """获取已接入平台列表"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.api.platform_tokens import get_platform_token_manager

    manager = get_platform_token_manager()
    platforms = manager.list_tokens(include_revoked=False)

    return {"platforms": platforms, "count": len(platforms)}


@router.get("/dashboard/knowledge")
async def list_knowledge(request: Request, category: str = None):
    """获取知识库列表"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.memory.knowledge import get_knowledge_engine

    engine = get_knowledge_engine()
    entries = engine.list_knowledge(category=category)

    return {
        "knowledge": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.get("/dashboard/knowledge/search")
async def search_knowledge(request: Request, query: str = ""):
    """搜索知识库"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.memory.knowledge import get_knowledge_engine

    engine = get_knowledge_engine()
    entries = engine.search_knowledge(query)

    return {
        "knowledge": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.get("/dashboard/snapshots")
async def list_snapshots(request: Request, memory_id: str = None):
    """获取记忆快照列表"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.memory.evolution import get_memory_evolution

    evolution = get_memory_evolution()
    snapshots = evolution.get_snapshots(memory_id=memory_id)

    return {
        "snapshots": [s.to_dict() for s in snapshots],
        "count": len(snapshots),
    }


@router.get("/dashboard/memories")
async def list_memories(request: Request, source: str = None, limit: int = 50):
    """获取记忆列表"""
    if not _verify_admin(request):
        return {"error": "需要 admin 凭据", "code": 401}

    from pangu.core.config import PanguConfig
    from pangu.memory.drawer_storage import JsonDrawerStorage

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers = JsonDrawerStorage(str(cfg.authoritative_drawers_path)).load()

    if source:
        drawers = [d for d in drawers if (d.source or d.room) == source]

    # 按创建时间排序，取最新的
    drawers.sort(key=lambda d: d.created_at or "", reverse=True)
    drawers = drawers[:limit]

    return {
        "memories": [
            {
                "id": d.id,
                "content": d.content[:200] + "..." if len(d.content) > 200 else d.content,
                "wing": d.wing,
                "room": d.room,
                "source": d.source,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": d.created_at,
            }
            for d in drawers
        ],
        "count": len(drawers),
    }
