"""盘古任务状态同步 API — 跨 Agent 任务追踪"""
import logging
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger("pangu.api.tasks")
router = APIRouter(tags=["tasks"])


class TaskStatus(str, Enum):
    """任务状态"""
    received = "received"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    verified = "verified"


# ── 请求/响应模型 ──

class TaskCreateRequest(BaseModel):
    task_id: str = Field(..., description="任务 ID")
    title: str = Field(..., description="任务标题")
    description: str = Field(default="", description="任务描述")
    agent_id: str = Field(..., description="负责 Agent ID")
    status: TaskStatus = Field(default=TaskStatus.received, description="任务状态")
    parent_task_id: str | None = Field(default=None, description="父任务 ID")


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    status: TaskStatus | None = Field(default=None)
    blocker: str | None = Field(default=None, description="阻碍原因")


class TaskResponse(BaseModel):
    task_id: str
    title: str
    description: str
    agent_id: str
    status: str
    parent_task_id: str | None
    created_at: str
    updated_at: str
    blocker: str | None = None


# 内存存储（生产环境应持久化到 SQLite）
_tasks: dict[str, dict] = {}


# ── 路由 ──

@router.post("/tasks")
async def create_task(req: TaskCreateRequest, request: Request) -> dict:
    """创建任务"""
    now = datetime.now().isoformat()
    task = {
        "task_id": req.task_id,
        "title": req.title,
        "description": req.description,
        "agent_id": req.agent_id,
        "status": req.status.value,
        "parent_task_id": req.parent_task_id,
        "created_at": now,
        "updated_at": now,
        "blocker": None,
    }
    _tasks[req.task_id] = task
    logger.info(f"Task created: {req.task_id} by {req.agent_id}")
    return {"code": 0, "message": "ok", "data": task}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """获取任务详情"""
    task = _tasks.get(task_id)
    if not task:
        return {"code": 404, "message": f"Task not found: {task_id}", "data": None}
    return {"code": 0, "message": "ok", "data": task}


@router.get("/tasks")
async def list_tasks(
    agent_id: str | None = Query(default=None, description="按 agent_id 筛选"),
    status: str | None = Query(default=None, description="按状态筛选"),
) -> dict:
    """列出任务（支持按 agent_id 和 status 筛选）"""
    tasks = list(_tasks.values())
    
    if agent_id:
        tasks = [t for t in tasks if t.get("agent_id") == agent_id]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    
    # 按 updated_at 降序
    tasks.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    
    return {"code": 0, "message": "ok", "data": {"items": tasks, "total": len(tasks)}}


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest) -> dict:
    """更新任务状态"""
    task = _tasks.get(task_id)
    if not task:
        return {"code": 404, "message": f"Task not found: {task_id}", "data": None}
    
    if req.title is not None:
        task["title"] = req.title
    if req.description is not None:
        task["description"] = req.description
    if req.status is not None:
        task["status"] = req.status.value
    if req.blocker is not None:
        task["blocker"] = req.blocker
    
    task["updated_at"] = datetime.now().isoformat()
    _tasks[task_id] = task
    
    logger.info(f"Task updated: {task_id} -> {task.get('status')}")
    return {"code": 0, "message": "ok", "data": task}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    """删除任务"""
    if task_id in _tasks:
        del _tasks[task_id]
        logger.info(f"Task deleted: {task_id}")
        return {"code": 0, "message": "ok", "data": {"deleted": True}}
    return {"code": 404, "message": f"Task not found: {task_id}", "data": None}


@router.get("/tasks/agent/{agent_id}")
async def get_agent_tasks(agent_id: str) -> dict:
    """获取指定 Agent 的所有任务"""
    tasks = [t for t in _tasks.values() if t.get("agent_id") == agent_id]
    tasks.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"code": 0, "message": "ok", "data": {"items": tasks, "total": len(tasks)}}