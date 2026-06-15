"""盘古任务状态同步 API — 跨 Agent 任务追踪（SQLite 持久化）"""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from typing import Optional

from pangu.core.config import config

logger = logging.getLogger("pangu.api.tasks")
router = APIRouter(tags=["tasks"])

# ── SQLite 持久化 ──

_db_lock = threading.Lock()
_db_path = Path(config.palace_path) / "tasks.db"


def _get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db():
    """初始化任务表"""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    agent_id TEXT NOT NULL,
                    status TEXT DEFAULT 'received',
                    parent_task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    blocker TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.commit()
        finally:
            conn.close()


def _task_to_dict(row: sqlite3.Row) -> dict:
    """将 Row 转换为字典"""
    return dict(row)


# 启动时初始化数据库
_init_db()


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


# ── 路由 ──

@router.post("/tasks")
async def create_task(req: TaskCreateRequest, request: Request) -> dict:
    """创建任务"""
    now = datetime.now().isoformat()
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO tasks (task_id, title, description, agent_id, status, parent_task_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (req.task_id, req.title, req.description, req.agent_id, req.status.value, req.parent_task_id, now, now)
            )
            conn.commit()
        finally:
            conn.close()
    logger.info(f"Task created: {req.task_id} by {req.agent_id}")
    return {"code": 0, "message": "ok", "data": {"task_id": req.task_id, "title": req.title, "agent_id": req.agent_id, "status": req.status.value, "created_at": now}}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """获取任务详情"""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return {"code": 404, "message": f"Task not found: {task_id}", "data": None}
            return {"code": 0, "message": "ok", "data": _task_to_dict(row)}
        finally:
            conn.close()


@router.get("/tasks")
async def list_tasks(
    agent_id: str | None = Query(default=None, description="按 agent_id 筛选"),
    status: str | None = Query(default=None, description="按状态筛选"),
) -> dict:
    """列出任务（支持按 agent_id 和 status 筛选）"""
    with _db_lock:
        conn = _get_db()
        try:
            query = "SELECT * FROM tasks"
            params = []
            conditions = []
            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            if status:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY updated_at DESC"
            rows = conn.execute(query, params).fetchall()
            tasks = [_task_to_dict(row) for row in rows]
            return {"code": 0, "message": "ok", "data": {"items": tasks, "total": len(tasks)}}
        finally:
            conn.close()


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest) -> dict:
    """更新任务状态"""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return {"code": 404, "message": f"Task not found: {task_id}", "data": None}
            
            updates = []
            params = []
            if req.title is not None:
                updates.append("title = ?")
                params.append(req.title)
            if req.description is not None:
                updates.append("description = ?")
                params.append(req.description)
            if req.status is not None:
                updates.append("status = ?")
                params.append(req.status.value)
            if req.blocker is not None:
                updates.append("blocker = ?")
                params.append(req.blocker)
            
            if updates:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(task_id)
                conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", params)
                conn.commit()
            
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            logger.info(f"Task updated: {task_id} -> {row['status'] if row else 'unknown'}")
            return {"code": 0, "message": "ok", "data": _task_to_dict(row)}
        finally:
            conn.close()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    """删除任务"""
    with _db_lock:
        conn = _get_db()
        try:
            cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Task deleted: {task_id}")
                return {"code": 0, "message": "ok", "data": {"deleted": True}}
            return {"code": 404, "message": f"Task not found: {task_id}", "data": None}
        finally:
            conn.close()


@router.get("/tasks/agent/{agent_id}")
async def get_agent_tasks(agent_id: str) -> dict:
    """获取指定 Agent 的所有任务"""
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute("SELECT * FROM tasks WHERE agent_id = ? ORDER BY updated_at DESC", (agent_id,)).fetchall()
            tasks = [_task_to_dict(row) for row in rows]
            return {"code": 0, "message": "ok", "data": {"items": tasks, "total": len(tasks)}}
        finally:
            conn.close()