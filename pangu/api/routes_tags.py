"""盘古标签管理 API — CRUD + 统计 + 合并 + 推荐"""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Optional

from pangu.core.config import config

logger = logging.getLogger("pangu.api.tags")
router = APIRouter(tags=["tags"])

# ── SQLite 持久化 ──

_db_lock = threading.Lock()
_db_path = Path(config.palace_path) / "tags.db"


def _get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    """初始化标签表"""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT DEFAULT '',
                    color TEXT DEFAULT '#666666',
                    usage_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_relations (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT DEFAULT 'related',
                    PRIMARY KEY (source_id, target_id)
                )
            """)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
        finally:
            conn.close()


# 启动时初始化数据库
_init_db()


# ── 请求/响应模型 ──

class TagCreateRequest(BaseModel):
    name: str = Field(..., description="标签名称")
    description: str = Field(default="", description="标签描述")
    color: str = Field(default="#666666", description="标签颜色")


class TagUpdateRequest(BaseModel):
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    color: str | None = Field(default=None)


class TagMergeRequest(BaseModel):
    source_tags: list[str] = Field(..., description="要合并的标签列表")
    target_tag: str = Field(..., description="合并目标标签")


# ── CRUD 路由 ──

@router.post("/tags")
async def create_tag(req: TagCreateRequest) -> dict:
    """创建标签"""
    tag_id = f"tag-{req.name.lower().replace(' ', '-')}"
    now = datetime.now().isoformat()
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO tags (id, name, description, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (tag_id, req.name, req.description, req.color, now, now)
            )
            conn.commit()
        finally:
            conn.close()
    logger.info(f"Tag created: {tag_id}")
    return {"code": 0, "data": {"id": tag_id, "name": req.name, "color": req.color}}


@router.get("/tags")
async def list_tags(
    search: str | None = Query(default=None, description="搜索关键词"),
    limit: int = Query(default=50, description="返回数量"),
) -> dict:
    """列出标签"""
    with _db_lock:
        conn = _get_db()
        try:
            if search:
                rows = conn.execute(
                    "SELECT * FROM tags WHERE name LIKE ? ORDER BY usage_count DESC LIMIT ?",
                    (f"%{search}%", limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tags ORDER BY usage_count DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            tags = [dict(row) for row in rows]
            return {"code": 0, "data": {"items": tags, "total": len(tags)}}
        finally:
            conn.close()


@router.get("/tags/{tag_id}")
async def get_tag(tag_id: str) -> dict:
    """获取标签详情"""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            if not row:
                return {"code": 404, "message": f"Tag not found: {tag_id}"}
            return {"code": 0, "data": dict(row)}
        finally:
            conn.close()


@router.put("/tags/{tag_id}")
async def update_tag(tag_id: str, req: TagUpdateRequest) -> dict:
    """更新标签"""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            if not row:
                return {"code": 404, "message": f"Tag not found: {tag_id}"}
            updates = []
            params = []
            if req.name is not None:
                updates.append("name = ?")
                params.append(req.name)
            if req.description is not None:
                updates.append("description = ?")
                params.append(req.description)
            if req.color is not None:
                updates.append("color = ?")
                params.append(req.color)
            if updates:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                params.append(tag_id)
                conn.execute(f"UPDATE tags SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
            row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            return {"code": 0, "data": dict(row)}
        finally:
            conn.close()


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str) -> dict:
    """删除标签"""
    with _db_lock:
        conn = _get_db()
        try:
            cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            conn.execute("DELETE FROM tag_relations WHERE source_id = ? OR target_id = ?", (tag_id, tag_id))
            conn.commit()
            if cursor.rowcount > 0:
                return {"code": 0, "data": {"deleted": True}}
            return {"code": 404, "message": f"Tag not found: {tag_id}"}
        finally:
            conn.close()


# ── 统计 ──

@router.get("/tags/stats/summary")
async def get_tag_stats() -> dict:
    """获取标签统计"""
    with _db_lock:
        conn = _get_db()
        try:
            total = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            top_tags = conn.execute(
                "SELECT name, usage_count FROM tags ORDER BY usage_count DESC LIMIT 10"
            ).fetchall()
            return {
                "code": 0,
                "data": {
                    "total_tags": total,
                    "top_tags": [{"name": t[0], "count": t[1]} for t in top_tags],
                }
            }
        finally:
            conn.close()


@router.post("/tags/{tag_id}/increment")
async def increment_usage(tag_id: str) -> dict:
    """增加标签使用次数"""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE tags SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), tag_id)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
            if row:
                return {"code": 0, "data": {"id": tag_id, "usage_count": row["usage_count"]}}
            return {"code": 404, "message": f"Tag not found: {tag_id}"}
        finally:
            conn.close()


# ── 合并 ──

@router.post("/tags/merge")
async def merge_tags(req: TagMergeRequest) -> dict:
    """合并标签"""
    with _db_lock:
        conn = _get_db()
        try:
            # 确保目标标签存在
            target = conn.execute("SELECT * FROM tags WHERE name = ?", (req.target_tag,)).fetchone()
            if not target:
                now = datetime.now().isoformat()
                target_id = f"tag-{req.target_tag.lower().replace(' ', '-')}"
                conn.execute(
                    "INSERT OR REPLACE INTO tags (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (target_id, req.target_tag, now, now)
                )
            else:
                target_id = target["id"]

            # 合并使用次数
            total_usage = 0
            for source_name in req.source_tags:
                source = conn.execute("SELECT * FROM tags WHERE name = ?", (source_name,)).fetchone()
                if source:
                    total_usage += source["usage_count"]
                    conn.execute("DELETE FROM tags WHERE id = ?", (source["id"],))

            conn.execute(
                "UPDATE tags SET usage_count = usage_count + ?, updated_at = ? WHERE id = ?",
                (total_usage, datetime.now().isoformat(), target_id)
            )
            conn.commit()
            return {"code": 0, "data": {"merged": len(req.source_tags), "target": req.target_tag}}
        finally:
            conn.close()


# ── 推荐 ──

@router.get("/tags/suggest")
async def suggest_tags(
    content: str = Query(..., description="记忆内容"),
    limit: int = Query(default=5, description="推荐数量"),
) -> dict:
    """基于内容推荐标签"""
    with _db_lock:
        conn = _get_db()
        try:
            # 获取所有标签
            rows = conn.execute("SELECT name, usage_count FROM tags ORDER BY usage_count DESC").fetchall()
            content_lower = content.lower()

            # 简单关键词匹配
            suggestions = []
            for name, count in rows:
                if name.lower() in content_lower or any(kw in content_lower for kw in name.lower().split()):
                    suggestions.append({"name": name, "score": count, "reason": "keyword_match"})

            # 如果匹配不够，返回热门标签
            if len(suggestions) < limit:
                for name, count in rows:
                    if name not in [s["name"] for s in suggestions]:
                        suggestions.append({"name": name, "score": count, "reason": "popular"})
                    if len(suggestions) >= limit:
                        break

            return {"code": 0, "data": {"suggestions": suggestions[:limit]}}
        finally:
            conn.close()
