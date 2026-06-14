"""盘古领域知识库 — 软件工程、项目管理、团队协作知识管理
============================================================
结构化管理多领域知识，支持 CRUD、检索、关联和演进。

支持：
- 软件工程知识库（设计模式、架构决策、技术债）
- 项目管理知识库（任务、进度、风险、里程碑）
- 团队协作知识库（沟通模式、反馈、成长轨迹）
- 知识条目的 CRUD 和关联管理
"""
import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..core.config import PanguConfig


class DomainType(str, Enum):
    """领域类型"""
    SOFTWARE_ENGINEERING = "software_engineering"
    PROJECT_MANAGEMENT = "project_management"
    TEAM_COLLABORATION = "team_collaboration"
    CUSTOM = "custom"


class KnowledgeCategory(str, Enum):
    """知识分类"""
    # 软件工程
    DESIGN_PATTERN = "design_pattern"
    ARCHITECTURE_DECISION = "architecture_decision"
    TECH_DEBT = "tech_debt"
    BEST_PRACTICE = "best_practice"
    LESSON_LEARNED = "lesson_learned"
    # 项目管理
    TASK = "task"
    MILESTONE = "milestone"
    RISK = "risk"
    DECISION = "decision"
    PROGRESS = "progress"
    # 团队协作
    COMMUNICATION = "communication"
    FEEDBACK = "feedback"
    GROWTH = "growth"
    RETROSPECTIVE = "retrospective"
    # 通用
    REFERENCE = "reference"
    GUIDE = "guide"


class KnowledgeStatus(str, Enum):
    """知识状态"""
    DRAFT = "draft"
    ACTIVE = "active"
    REVIEW = "review"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    domain: DomainType
    category: KnowledgeCategory
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    confidence: float = 1.0          # 置信度 [0,1]
    importance: float = 0.5          # 重要性 [0,1]
    related_ids: list[str] = field(default_factory=list)  # 关联条目
    source: str = ""                 # 来源
    author: str = ""                 # 作者
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class KnowledgeStats:
    """知识库统计"""
    total_entries: int
    by_domain: dict[str, int]
    by_category: dict[str, int]
    by_status: dict[str, int]
    avg_confidence: float
    avg_importance: float
    top_tags: list[tuple[str, int]]


class DomainKnowledge:
    """领域知识库"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        db_path = Path.home() / ".pangu" / "domain_knowledge.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._init_db()
        self._seed_defaults()

    @contextmanager
    def _conn(self):
        """SQLite 连接"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_entries (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'active',
                    confidence REAL DEFAULT 1.0,
                    importance REAL DEFAULT 0.5,
                    related_ids TEXT DEFAULT '[]',
                    source TEXT DEFAULT '',
                    author TEXT DEFAULT '',
                    version INTEGER DEFAULT 1,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_domain
                ON knowledge_entries(domain)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_category
                ON knowledge_entries(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_status
                ON knowledge_entries(status)
            """)

    def _seed_defaults(self) -> None:
        """填充默认知识条目"""
        existing = self.list_entries(limit=1)
        if existing:
            return

        defaults = [
            # 软件工程 - 设计模式
            KnowledgeEntry(
                id="se_pattern_singleton",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.DESIGN_PATTERN,
                title="单例模式",
                content="确保一个类只有一个实例，并提供全局访问点。"
                        "适用场景：配置管理、日志、连接池。"
                        "注意：避免过度使用，会增加耦合度。",
                tags=["设计模式", "创建型"],
                importance=0.7,
                source="GoF Design Patterns",
            ),
            KnowledgeEntry(
                id="se_pattern_observer",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.DESIGN_PATTERN,
                title="观察者模式",
                content="定义对象间的一对多依赖，当一个对象状态改变时，"
                        "所有依赖它的对象都会收到通知。"
                        "适用场景：事件系统、消息队列、UI 响应式更新。",
                tags=["设计模式", "行为型"],
                importance=0.8,
                source="GoF Design Patterns",
            ),
            KnowledgeEntry(
                id="se_pattern_strategy",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.DESIGN_PATTERN,
                title="策略模式",
                content="定义一系列算法，将每个算法封装起来，使它们可互换。"
                        "适用场景：支付方式、排序算法、验证规则。",
                tags=["设计模式", "行为型"],
                importance=0.7,
            ),
            # 软件工程 - 架构决策
            KnowledgeEntry(
                id="se_arch_clean",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.ARCHITECTURE_DECISION,
                title="整洁架构",
                content="依赖规则：源码依赖只能向内。外层知道内层，内层不知道外层。"
                        "层次：实体 → 用例 → 接口适配器 → 框架和驱动。",
                tags=["架构", "整洁架构", "SOLID"],
                importance=0.9,
            ),
            KnowledgeEntry(
                id="se_arch_hexagonal",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.ARCHITECTURE_DECISION,
                title="六边形架构（端口适配器）",
                content="应用核心通过端口与外部交互，适配器实现端口接口。"
                        "优势：可测试性高、技术栈可替换。",
                tags=["架构", "六边形"],
                importance=0.8,
            ),
            # 软件工程 - 最佳实践
            KnowledgeEntry(
                id="se_practice_code_review",
                domain=DomainType.SOFTWARE_ENGINEERING,
                category=KnowledgeCategory.BEST_PRACTICE,
                title="代码审查最佳实践",
                content="1. 每次 PR 不超过 400 行。"
                        "2. 关注逻辑错误而非代码风格。"
                        "3. 提出建设性建议而非命令。"
                        "4. 至少一人批准后合并。",
                tags=["代码审查", "团队规范"],
                importance=0.8,
            ),
            # 项目管理 - 风险
            KnowledgeEntry(
                id="pm_risk_scope_creep",
                domain=DomainType.PROJECT_MANAGEMENT,
                category=KnowledgeCategory.RISK,
                title="范围蔓延风险",
                content="项目需求不断膨胀，超出原始范围。"
                        "应对：明确需求基线，建立变更控制流程。",
                tags=["风险管理", "范围"],
                importance=0.9,
            ),
            KnowledgeEntry(
                id="pm_risk_bus_factor",
                domain=DomainType.PROJECT_MANAGEMENT,
                category=KnowledgeCategory.RISK,
                title="巴士因子风险",
                content="关键知识集中在少数人身上，一旦离开项目就无法继续。"
                        "应对：知识共享、文档化、交叉培训。",
                tags=["风险管理", "人员"],
                importance=0.85,
            ),
            # 团队协作 - 沟通
            KnowledgeEntry(
                id="tc_comm_async",
                domain=DomainType.TEAM_COLLABORATION,
                category=KnowledgeCategory.COMMUNICATION,
                title="异步沟通原则",
                content="1. 文字优于语音（可搜索、可引用）。"
                        "2. 明确期望回复时间。"
                        "3. 写清楚上下文，减少来回。"
                        "4. 重要决策形成文档。",
                tags=["沟通", "远程协作"],
                importance=0.8,
            ),
            KnowledgeEntry(
                id="tc_feedback_sbi",
                domain=DomainType.TEAM_COLLABORATION,
                category=KnowledgeCategory.FEEDBACK,
                title="SBI 反馈模型",
                content="Situation（情境）→ Behavior（行为）→ Impact（影响）。"
                        "描述具体情境，指出具体行为，说明产生的影响。"
                        "避免评判人格，聚焦可观察行为。",
                tags=["反馈", "沟通技巧"],
                importance=0.75,
            ),
        ]

        for entry in defaults:
            self.create_entry(entry)

    # ── CRUD 操作 ──────────────────────────────────────────────

    def create_entry(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """创建知识条目"""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO knowledge_entries
                   (id, domain, category, title, content, tags, status,
                    confidence, importance, related_ids, source, author,
                    version, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.domain.value,
                    entry.category.value,
                    entry.title,
                    entry.content,
                    json.dumps(entry.tags, ensure_ascii=False),
                    entry.status.value,
                    entry.confidence,
                    entry.importance,
                    json.dumps(entry.related_ids),
                    entry.source,
                    entry.author,
                    entry.version,
                    json.dumps(entry.metadata, ensure_ascii=False),
                    entry.created_at,
                    entry.updated_at,
                ),
            )
        return entry

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """获取知识条目"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row)

    def update_entry(self, entry_id: str, **kwargs) -> KnowledgeEntry | None:
        """更新知识条目

        Args:
            entry_id: 条目 ID
            **kwargs: 要更新的字段

        Returns:
            更新后的条目，不存在返回 None
        """
        allowed = {
            "title", "content", "tags", "status", "confidence",
            "importance", "related_ids", "source", "author",
            "metadata", "category", "domain",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_entry(entry_id)

        # 序列化特殊字段
        if "tags" in updates and isinstance(updates["tags"], list):
            updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)
        if "related_ids" in updates and isinstance(updates["related_ids"], list):
            updates["related_ids"] = json.dumps(updates["related_ids"])
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata"] = json.dumps(updates["metadata"], ensure_ascii=False)
        if "status" in updates and isinstance(updates["status"], KnowledgeStatus):
            updates["status"] = updates["status"].value
        if "category" in updates and isinstance(updates["category"], KnowledgeCategory):
            updates["category"] = updates["category"].value
        if "domain" in updates and isinstance(updates["domain"], DomainType):
            updates["domain"] = updates["domain"].value

        updates["updated_at"] = datetime.now().isoformat()
        updates["version"] = None  # 需要先查询再 +1

        # 查询当前版本
        current = self.get_entry(entry_id)
        if not current:
            return None
        updates["version"] = current.version + 1

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entry_id]

        with self._conn() as conn:
            conn.execute(
                f"UPDATE knowledge_entries SET {set_clause} WHERE id = ?",
                values,
            )

        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: str) -> bool:
        """删除知识条目"""
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM knowledge_entries WHERE id = ?", (entry_id,)
            )
        return cursor.rowcount > 0

    def list_entries(
        self,
        domain: DomainType | None = None,
        category: KnowledgeCategory | None = None,
        status: KnowledgeStatus | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeEntry]:
        """查询知识条目

        Args:
            domain: 按领域过滤
            category: 按分类过滤
            status: 按状态过滤
            tags: 按标签过滤（AND）
            search: 搜索标题和内容
            limit: 返回数量上限
            offset: 分页偏移

        Returns:
            匹配的条目列表
        """
        conditions: list[str] = []
        params: list[Any] = []

        if domain:
            conditions.append("domain = ?")
            params.append(domain.value)
        if category:
            conditions.append("category = ?")
            params.append(category.value)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if search:
            conditions.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM knowledge_entries {where} ORDER BY importance DESC, updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        entries = [self._row_to_entry(row) for row in rows]

        # 标签过滤（需要后过滤，因为标签是 JSON）
        if tags:
            entries = [
                e for e in entries
                if all(t in e.tags for t in tags)
            ]

        return entries

    def _row_to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        """将数据库行转换为 KnowledgeEntry"""
        return KnowledgeEntry(
            id=row["id"],
            domain=DomainType(row["domain"]),
            category=KnowledgeCategory(row["category"]),
            title=row["title"],
            content=row["content"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            status=KnowledgeStatus(row["status"]),
            confidence=row["confidence"],
            importance=row["importance"],
            related_ids=json.loads(row["related_ids"]) if row["related_ids"] else [],
            source=row["source"] or "",
            author=row["author"] or "",
            version=row["version"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── 查询与分析 ──────────────────────────────────────────────

    def search_by_keywords(self, keywords: list[str]) -> list[KnowledgeEntry]:
        """关键词搜索（OR 匹配）"""
        if not keywords:
            return []

        conditions = []
        params: list[Any] = []
        for kw in keywords:
            conditions.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

        where = " OR ".join(conditions)
        query = f"SELECT * FROM knowledge_entries WHERE {where} ORDER BY importance DESC"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_entry(row) for row in rows]

    def get_related(self, entry_id: str) -> list[KnowledgeEntry]:
        """获取关联条目"""
        entry = self.get_entry(entry_id)
        if not entry:
            return []

        related = []
        for rid in entry.related_ids:
            related_entry = self.get_entry(rid)
            if related_entry:
                related.append(related_entry)
        return related

    def add_relation(self, entry_id: str, related_id: str) -> bool:
        """添加双向关联"""
        entry = self.get_entry(entry_id)
        related = self.get_entry(related_id)
        if not entry or not related:
            return False

        # 添加正向关联
        if related_id not in entry.related_ids:
            self.update_entry(entry_id, related_ids=entry.related_ids + [related_id])

        # 添加反向关联
        if entry_id not in related.related_ids:
            self.update_entry(related_id, related_ids=related.related_ids + [entry_id])

        return True

    def remove_relation(self, entry_id: str, related_id: str) -> bool:
        """移除双向关联"""
        entry = self.get_entry(entry_id)
        related = self.get_entry(related_id)
        if not entry or not related:
            return False

        if related_id in entry.related_ids:
            self.update_entry(entry_id, related_ids=[r for r in entry.related_ids if r != related_id])
        if entry_id in related.related_ids:
            self.update_entry(related_id, related_ids=[r for r in related.related_ids if r != entry_id])

        return True

    def get_stats(self) -> KnowledgeStats:
        """获取知识库统计"""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0]

            domain_rows = conn.execute(
                "SELECT domain, COUNT(*) FROM knowledge_entries GROUP BY domain"
            ).fetchall()
            by_domain = {row[0]: row[1] for row in domain_rows}

            cat_rows = conn.execute(
                "SELECT category, COUNT(*) FROM knowledge_entries GROUP BY category"
            ).fetchall()
            by_category = {row[0]: row[1] for row in cat_rows}

            status_rows = conn.execute(
                "SELECT status, COUNT(*) FROM knowledge_entries GROUP BY status"
            ).fetchall()
            by_status = {row[0]: row[1] for row in status_rows}

            avg_conf = conn.execute(
                "SELECT AVG(confidence) FROM knowledge_entries"
            ).fetchone()[0] or 0.0

            avg_imp = conn.execute(
                "SELECT AVG(importance) FROM knowledge_entries"
            ).fetchone()[0] or 0.0

        # 统计标签
        all_tags: list[str] = []
        with self._conn() as conn:
            rows = conn.execute("SELECT tags FROM knowledge_entries").fetchall()
            for row in rows:
                all_tags.extend(json.loads(row[0]) if row[0] else [])
        tag_counts = Counter(all_tags).most_common(10)

        return KnowledgeStats(
            total_entries=total,
            by_domain=by_domain,
            by_category=by_category,
            by_status=by_status,
            avg_confidence=round(avg_conf, 3),
            avg_importance=round(avg_imp, 3),
            top_tags=tag_counts,
        )

    def deprecate_entry(self, entry_id: str, reason: str = "") -> KnowledgeEntry | None:
        """废弃条目"""
        metadata_update = {}
        if reason:
            entry = self.get_entry(entry_id)
            if entry:
                metadata_update = entry.metadata.copy()
                metadata_update["deprecation_reason"] = reason

        return self.update_entry(
            entry_id,
            status=KnowledgeStatus.DEPRECATED,
            metadata=metadata_update if metadata_update else None,
        )

    def merge_entries(self, source_id: str, target_id: str) -> KnowledgeEntry | None:
        """合并两个条目（source 合并到 target）"""
        source = self.get_entry(source_id)
        target = self.get_entry(target_id)
        if not source or not target:
            return None

        # 合并内容
        merged_content = f"{target.content}\n\n--- 合并自 {source.title} ---\n{source.content}"

        # 合并标签
        merged_tags = list(set(source.tags + target.tags))

        # 合并关联（排除自己）
        merged_related = list(set(
            r for r in (source.related_ids + target.related_ids)
            if r not in (source_id, target_id)
        ))

        # 更新 target
        updated = self.update_entry(
            target_id,
            content=merged_content,
            tags=merged_tags,
            related_ids=merged_related,
            confidence=max(source.confidence, target.confidence),
            importance=max(source.importance, target.importance),
        )

        # 废弃 source 并关联到 target
        self.update_entry(
            source_id,
            status=KnowledgeStatus.ARCHIVED,
            related_ids=[target_id],
            metadata={"merged_into": target_id, "merge_time": datetime.now().isoformat()},
        )

        return updated
