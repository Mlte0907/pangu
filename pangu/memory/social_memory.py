"""盘古记忆社交化模块 — 记忆评论、投票与共享
============================================
赋予记忆社交属性：支持评论讨论、投票评分、专家推荐和权限管理。

支持：
- 记忆评论和讨论（嵌套回复）
- 记忆投票和评分（有用性评分）
- 记忆专家推荐（基于使用频率和评分）
- 记忆共享权限管理（private / team / public）
"""
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.social_memory")


class ShareLevel(str, Enum):
    """共享级别"""
    PRIVATE = "private"    # 仅自己可见
    TEAM = "team"          # 团队可见
    PUBLIC = "public"      # 公开


class VoteType(str, Enum):
    """投票类型"""
    UP = "up"       # 有用
    DOWN = "down"   # 无用
    BOOKMARK = "bookmark"  # 收藏


@dataclass
class Comment:
    """记忆评论"""
    id: str
    memory_id: str
    author_id: str
    content: str
    parent_id: str | None = None  # 回复的评论 ID（支持嵌套）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    likes: int = 0
    replies: list[str] = field(default_factory=list)  # 子评论 ID 列表


@dataclass
class Vote:
    """投票记录"""
    user_id: str
    memory_id: str
    vote_type: VoteType
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    weight: float = 1.0  # 投票权重（专家权重更高）


@dataclass
class ExpertProfile:
    """专家档案"""
    user_id: str
    name: str
    expertise_tags: list[str] = field(default_factory=list)  # 擅长领域
    total_votes: int = 0  # 总投票数
    helpful_votes: int = 0  # 有用投票数
    accuracy: float = 0.0  # 投票准确率
    memories_used: list[str] = field(default_factory=list)  # 使用过的记忆


@dataclass
class SharePermission:
    """共享权限"""
    memory_id: str
    owner_id: str
    share_level: ShareLevel = ShareLevel.PRIVATE
    shared_with: list[str] = field(default_factory=list)  # 共享的用户 ID 列表
    allow_comment: bool = True
    allow_vote: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SocialMemory:
    """记忆社交化管理器（SQLite 持久化）

    管理记忆的社交属性：评论、投票、推荐和权限。
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._comments: dict[str, Comment] = {}
        self._votes: dict[str, list[Vote]] = {}
        self._experts: dict[str, ExpertProfile] = {}
        self._permissions: dict[str, SharePermission] = {}

        # SQLite 持久化
        from pangu.core.config import config as pangu_config
        self._db_path = Path(pangu_config.palace_path) / "social.db"
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        """初始化社交数据表"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY, memory_id TEXT, author_id TEXT, content TEXT,
                parent_id TEXT, created_at TEXT, likes INTEGER DEFAULT 0, replies TEXT DEFAULT '[]'
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT, user_id TEXT,
                vote_type TEXT, timestamp TEXT, weight REAL DEFAULT 1.0
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS experts (
                user_id TEXT PRIMARY KEY, name TEXT, expertise_tags TEXT DEFAULT '[]',
                total_votes INTEGER DEFAULT 0, helpful_votes INTEGER DEFAULT 0,
                accuracy REAL DEFAULT 0.0, memories_used TEXT DEFAULT '[]'
            )""")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
        finally:
            conn.close()

    def _load_from_db(self) -> None:
        """从数据库加载数据"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                # 加载评论
                rows = conn.execute("SELECT * FROM comments").fetchall()
                for row in rows:
                    comment = Comment(
                        id=row[0], memory_id=row[1], author_id=row[2],
                        content=row[3], parent_id=row[4], created_at=row[5],
                        likes=row[6], replies=json.loads(row[7])
                    )
                    self._comments[comment.id] = comment

                # 加载投票
                rows = conn.execute("SELECT * FROM votes").fetchall()
                for row in rows:
                    vote = Vote(
                        user_id=row[2], memory_id=row[1],
                        vote_type=VoteType(row[3]), timestamp=row[4], weight=row[5]
                    )
                    self._votes.setdefault(vote.memory_id, []).append(vote)

                # 加载专家
                rows = conn.execute("SELECT * FROM experts").fetchall()
                for row in rows:
                    expert = ExpertProfile(
                        user_id=row[0], name=row[1],
                        expertise_tags=json.loads(row[2]),
                        total_votes=row[3], helpful_votes=row[4],
                        accuracy=row[5], memories_used=json.loads(row[6])
                    )
                    self._experts[expert.user_id] = expert
            finally:
                conn.close()
        except Exception:
            pass

    def _save_comment(self, comment: Comment) -> None:
        """保存评论到数据库"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO comments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (comment.id, comment.memory_id, comment.author_id, comment.content,
                     comment.parent_id, comment.created_at, comment.likes, json.dumps(comment.replies))
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def _save_vote(self, vote: Vote) -> None:
        """保存投票到数据库"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                conn.execute(
                    "INSERT INTO votes (memory_id, user_id, vote_type, timestamp, weight) VALUES (?, ?, ?, ?, ?)",
                    (vote.memory_id, vote.user_id, vote.vote_type.value, vote.timestamp, vote.weight)
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def _save_expert(self, expert: ExpertProfile) -> None:
        """保存专家到数据库"""
        try:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO experts VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (expert.user_id, expert.name, json.dumps(expert.expertise_tags),
                     expert.total_votes, expert.helpful_votes, expert.accuracy,
                     json.dumps(expert.memories_used))
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    # ---- 评论管理 ----

    def add_comment(self, memory_id: str, author_id: str, content: str,
                    parent_id: str | None = None) -> Comment:
        """添加评论"""
        comment_id = hex_digest(f"{memory_id}-{author_id}-{time.time()}")[:8]
        comment = Comment(
            id=comment_id,
            memory_id=memory_id,
            author_id=author_id,
            content=content,
            parent_id=parent_id
        )
        self._comments[comment_id] = comment
        self._save_comment(comment)

        # 如果是回复，添加到父评论的 replies 列表
        if parent_id and parent_id in self._comments:
            self._comments[parent_id].replies.append(comment_id)
            self._save_comment(self._comments[parent_id])

        logger.info(f"评论已添加: {comment_id} (记忆: {memory_id})")
        return comment

    def get_comments(self, memory_id: str, top_level_only: bool = True) -> list[Comment]:
        """获取记忆的评论列表"""
        comments = [c for c in self._comments.values() if c.memory_id == memory_id]
        if top_level_only:
            return [c for c in comments if c.parent_id is None]
        return sorted(comments, key=lambda c: c.created_at)

    def get_comment_thread(self, comment_id: str) -> dict[str, Any]:
        """获取评论线程（递归）"""
        comment = self._comments.get(comment_id)
        if not comment:
            return {}
        return {
            "comment": comment,
            "replies": [self.get_comment_thread(rid) for rid in comment.replies]
        }

    def like_comment(self, comment_id: str) -> bool:
        """点赞评论"""
        if comment_id in self._comments:
            self._comments[comment_id].likes += 1
            return True
        return False

    def delete_comment(self, comment_id: str) -> bool:
        """删除评论"""
        comment = self._comments.pop(comment_id, None)
        if comment and comment.parent_id:
            parent = self._comments.get(comment.parent_id)
            if parent and comment_id in parent.replies:
                parent.replies.remove(comment_id)
        return comment is not None

    # ---- 投票与评分 ----

    def vote(self, memory_id: str, user_id: str, vote_type: VoteType) -> Vote:
        """对记忆投票"""
        # 检查是否已投票，如果是则更新
        if memory_id not in self._votes:
            self._votes[memory_id] = []

        # 移除该用户之前的投票
        self._votes[memory_id] = [
            v for v in self._votes[memory_id] if v.user_id != user_id
        ]

        # 确定权重（专家权重更高）
        weight = 1.0
        if user_id in self._experts:
            weight = 1.5

        vote = Vote(
            user_id=user_id,
            memory_id=memory_id,
            vote_type=vote_type,
            weight=weight
        )
        self._votes[memory_id].append(vote)
        self._save_vote(vote)

        # 更新专家统计
        self._update_expert_stats(user_id, memory_id, vote_type)

        return vote

    def get_votes(self, memory_id: str) -> dict[str, Any]:
        """获取记忆的投票统计"""
        votes = self._votes.get(memory_id, [])
        up_count = sum(1 for v in votes if v.vote_type == VoteType.UP)
        down_count = sum(1 for v in votes if v.vote_type == VoteType.DOWN)
        bookmark_count = sum(1 for v in votes if v.vote_type == VoteType.BOOKMARK)

        # 加权评分
        weighted_score = sum(
            v.weight if v.vote_type == VoteType.UP else -v.weight
            for v in votes
            if v.vote_type in (VoteType.UP, VoteType.DOWN)
        )

        return {
            "up": up_count,
            "down": down_count,
            "bookmarks": bookmark_count,
            "total": len(votes),
            "weighted_score": weighted_score,
            "score": up_count - down_count  # 简单评分
        }

    def get_top_memories(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取评分最高的记忆"""
        rankings = []
        for memory_id, votes in self._votes.items():
            stats = self.get_votes(memory_id)
            if stats["total"] > 0:
                rankings.append({
                    "memory_id": memory_id,
                    **stats
                })
        rankings.sort(key=lambda x: x["weighted_score"], reverse=True)
        return rankings[:limit]

    def _update_expert_stats(self, user_id: str, memory_id: str, vote_type: VoteType) -> None:
        """更新专家统计"""
        if user_id not in self._experts:
            self._experts[user_id] = ExpertProfile(
                user_id=user_id,
                name=user_id
            )
        expert = self._experts[user_id]
        expert.total_votes += 1
        if vote_type == VoteType.UP:
            expert.helpful_votes += 1
        if memory_id not in expert.memories_used:
            expert.memories_used.append(memory_id)
        if expert.total_votes > 0:
            expert.accuracy = expert.helpful_votes / expert.total_votes
        self._save_expert(expert)

    # ---- 专家推荐 ----

    def get_experts(self, limit: int = 10) -> list[ExpertProfile]:
        """获取顶级专家列表"""
        experts = sorted(
            self._experts.values(),
            key=lambda e: (e.accuracy, e.total_votes),
            reverse=True
        )
        return experts[:limit]

    def get_expert_recommendations(self, memory_id: str) -> list[dict[str, Any]]:
        """获取专家对该记忆的推荐情况"""
        votes = self._votes.get(memory_id, [])
        expert_votes = []
        for vote in votes:
            if vote.user_id in self._experts:
                expert = self._experts[vote.user_id]
                expert_votes.append({
                    "expert": expert.name,
                    "vote": vote.vote_type.value,
                    "accuracy": expert.accuracy,
                    "expertise": expert.expertise_tags
                })
        return expert_votes

    def register_expert(self, user_id: str, name: str, tags: list[str] | None = None) -> ExpertProfile:
        """注册专家"""
        if user_id not in self._experts:
            self._experts[user_id] = ExpertProfile(
                user_id=user_id,
                name=name,
                expertise_tags=tags or []
            )
        return self._experts[user_id]

    # ---- 权限管理 ----

    def set_permission(self, memory_id: str, owner_id: str,
                       share_level: ShareLevel = ShareLevel.PRIVATE,
                       shared_with: list[str] | None = None) -> SharePermission:
        """设置记忆共享权限"""
        permission = SharePermission(
            memory_id=memory_id,
            owner_id=owner_id,
            share_level=share_level,
            shared_with=shared_with or []
        )
        self._permissions[memory_id] = permission
        return permission

    def check_access(self, memory_id: str, user_id: str) -> dict[str, bool]:
        """检查用户对记忆的访问权限"""
        perm = self._permissions.get(memory_id)
        if not perm:
            return {"read": False, "comment": False, "vote": False}

        # 所有者拥有全部权限
        if user_id == perm.owner_id:
            return {"read": True, "comment": True, "vote": True}

        # 根据共享级别判断
        if perm.share_level == ShareLevel.PUBLIC:
            return {
                "read": True,
                "comment": perm.allow_comment,
                "vote": perm.allow_vote
            }
        elif perm.share_level == ShareLevel.TEAM:
            if user_id in perm.shared_with:
                return {
                    "read": True,
                    "comment": perm.allow_comment,
                    "vote": perm.allow_vote
                }
        elif perm.share_level == ShareLevel.PRIVATE:
            if user_id in perm.shared_with:
                return {"read": True, "comment": False, "vote": False}

        return {"read": False, "comment": False, "vote": False}

    def share_with(self, memory_id: str, user_id: str, level: ShareLevel = ShareLevel.TEAM) -> bool:
        """将记忆分享给指定用户"""
        if memory_id not in self._permissions:
            return False
        perm = self._permissions[memory_id]
        perm.share_level = level
        if user_id not in perm.shared_with:
            perm.shared_with.append(user_id)
        return True

    def revoke_access(self, memory_id: str, user_id: str) -> bool:
        """撤销用户访问权限"""
        if memory_id not in self._permissions:
            return False
        perm = self._permissions[memory_id]
        if user_id in perm.shared_with:
            perm.shared_with.remove(user_id)
            return True
        return False

    # ---- 统计 ----

    def get_stats(self) -> dict[str, Any]:
        """获取社交模块统计"""
        total_votes = sum(len(v) for v in self._votes.values())
        return {
            "total_comments": len(self._comments),
            "total_votes": total_votes,
            "total_experts": len(self._experts),
            "total_shared": len(self._permissions),
            "top_memory": self.get_top_memories(1)[0] if self._votes else None
        }
