"""盘古时间知识图谱 — 增强版（从伏羲 v1.5.6 移植增强功能）

新增功能：
1. BFS 遍历（含边类型过滤和权重阈值）
2. 因果链追溯
3. 自动关系发现（基于向量聚类）
4. 多视角图谱（coding/messaging/ide）
5. 边质量评分
6. 边类型自动推断
"""

import logging
import sqlite3
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from .layers import current_tenant

logger = logging.getLogger("pangu.memory.graph")


class KnowledgeGraph:
    """时间知识图谱 — 实体关系的时间维度管理"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        db_path = Path(self.config.palace_path) / "knowledge_graph.db"
        self.db_path = str(db_path)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的 SQLite 连接（线程本地复用）"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # 租户作用域的 SQL 侧入口：视图 entities/relations 靠它过滤（见 _init_db）。
            # UDF 是**连接级**的，必须每个新连接都注册；未注册的连接查视图会直接报
            # "no such function"（硬失败，不会静默漏数据 —— 这正是想要的）。
            conn.create_function(self._SCOPE_UDF, 0, lambda: current_tenant())
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-32000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def _conn(self):
        """知识图谱 SQLite 连接（线程本地复用 + 事务保护）"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _SCOPE_UDF = "current_tenant"

    def _init_db(self) -> None:
        """初始化数据库（含「基表 + 租户视图」多租户改造，幂等）

        多租户（P1-3 阶段 3）：
        - 物理表是 `entities_all` / `relations_all`，主键为 **(id, tenant_id)** —— 同名实体
          在不同租户下各有一份，`INSERT OR REPLACE` 天然只覆盖自己那份，踩不到别人
        - 对外暴露**同名视图** entities / relations，按 current_tenant() 过滤
          （我的 + visibility='public'；作用域为空＝全库视角，供 CLI/后台/admin）
        - 写路径一律显式打基表：SQLite 的 UPDATE/DELETE **不会**套用视图的 WHERE，
          直接写视图就是"删掉所有租户的关系"这类跨租户写

        为什么用视图而不是逐个改 SQL：本文件有 30+ 处 SQL，逐个加条件必然漏（记忆层的
        教训：287 个 handler 里 18 个漏了，靠人工扫描才发现）。视图把过滤收敛到唯一一处。
        """
        with self._conn() as conn:
            # 迁移期间关外键：旧库的 relations 表带 `REFERENCES entities(id)`，而我们要把
            # entities 改名、之后建同名**视图** —— SQLite 按名字解析外键，父表变成视图/不存在
            # 时插入会报 "FOREIGN KEY constraint failed"（实测：关系搬运卡住、legacy 表残留，
            # 库处于半迁移状态）。新 schema 已不含任何外键，故迁移后无需恢复语义，只恢复 pragma。
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                self._rename_legacy_tables(conn)
                self._create_tenant_tables(conn)
                self._copy_legacy_rows(conn)
                self._create_tenant_views(conn)
            finally:
                conn.execute("PRAGMA foreign_keys=ON")

    def _create_tenant_tables(self, conn) -> None:
        """建基表与索引（幂等）。"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entities_all (
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'private',
                PRIMARY KEY (id, tenant_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relations_all (
                id TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL,
                valid_from TEXT,
                valid_until TEXT,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'private',
                PRIMARY KEY (id, tenant_id)
            )
        """)
        # 不再声明 entity↔relation 外键：复合主键后 id 单独不再唯一，SQLite 要求外键指向
        # 唯一索引，按 (subject_id) 写会直接 "foreign key mismatch"。级联删除本来就是
        # delete_entity 里手工做的，去掉不丢语义。
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations_all(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_object ON relations_all(object_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_valid ON relations_all(valid_from, valid_until)",
            "CREATE INDEX IF NOT EXISTS idx_entities_tenant ON entities_all(tenant_id, visibility)",
            "CREATE INDEX IF NOT EXISTS idx_relations_tenant ON relations_all(tenant_id, visibility)",
        ):
            conn.execute(stmt)

    @staticmethod
    def _rename_legacy_tables(conn) -> None:
        """旧库的 entities / relations 表补列并改名，等新结构建好后搬运（幂等）。"""
        for table in ("entities", "relations"):
            row = conn.execute("SELECT type FROM sqlite_master WHERE name = ?", (table,)).fetchone()
            if row is None or row["type"] != "table":
                continue  # 不存在（新库）或已是视图（已迁移）
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "tenant_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT ''")
            if "visibility" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'")
            conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
            logger.warning(f"knowledge_graph: 旧表 {table} → {table}_legacy（等待搬入新基表）")

    @staticmethod
    def _copy_legacy_rows(conn) -> None:
        """把 _legacy 表的数据搬进新基表并删除旧表。

        列名显式写出（不用 SELECT *）—— 新旧列序不同，`SELECT *` 会错位。
        搬运后 tenant_id 保持 ''（无主）：**谁都读不到**，只有全库视角和后续的归属回填
        能处理它。这是安全默认 —— 漏填不会把历史数据暴露给某个租户。
        """
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='entities_legacy'").fetchone():
            conn.execute("""
                INSERT OR REPLACE INTO entities_all
                    (id, name, type, description, created_at, tenant_id, visibility)
                SELECT id, name, type, description, created_at, tenant_id, visibility
                FROM entities_legacy
            """)
            conn.execute("DROP TABLE entities_legacy")
            logger.warning("knowledge_graph: 实体已搬入 entities_all（tenant_id 为空＝无主，需一次性回填）")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='relations_legacy'").fetchone():
            conn.execute("""
                INSERT OR REPLACE INTO relations_all
                    (id, subject_id, predicate, object_id, valid_from, valid_until,
                     confidence, source, created_at, tenant_id, visibility)
                SELECT id, subject_id, predicate, object_id, valid_from, valid_until,
                       confidence, source, created_at, tenant_id, visibility
                FROM relations_legacy
            """)
            conn.execute("DROP TABLE relations_legacy")
            logger.warning("knowledge_graph: 关系已搬入 relations_all（tenant_id 为空＝无主，需一次性回填）")

    @staticmethod
    def _create_tenant_views(conn) -> None:
        """创建同名租户视图（读路径的唯一收口点）。

        ORDER BY 是"自己的行优先"—— 同名 id 在别的租户里也存在时（复合主键允许多份），
        by-id 查询应优先命中自己那份；SQLite 在带 JOIN 的外层查询里会忽略视图内的排序，
        所以这只是尽力而为，不影响正确性（两份都是当前租户**可见**的行）。
        """
        for table in ("entities", "relations"):
            conn.execute(f"""
                CREATE VIEW IF NOT EXISTS {table} AS
                SELECT * FROM {table}_all
                WHERE current_tenant() = ''
                   OR tenant_id = current_tenant()
                   OR visibility = 'public'
                ORDER BY (tenant_id = current_tenant()) DESC
            """)

    # ── 实体操作 ──

    def add_entity(
        self, id: str, name: str, entity_type: str, description: str = "", tenant_id: str | None = None
    ) -> dict:
        """添加实体（落当前租户归属）

        tenant_id 默认取请求作用域（无则 ''＝无主）；**自动抽取会显式传入来源记忆的租户**
        —— 图谱是记忆的衍生，归属必须跟着来源走，否则后台一跑就产生"无主知识"。
        """
        owner = current_tenant() if tenant_id is None else tenant_id
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO entities_all
                   (id, name, type, description, created_at, tenant_id, visibility)
                   VALUES (?, ?, ?, ?, ?, ?, 'private')""",
                (id, name, entity_type, description, datetime.now().isoformat(), owner),
            )
            # 回读走基表：抽取可能以来源租户落库（与当前作用域不同的公共记忆），
            # 走视图会因不可见而返回 None。
            row = conn.execute("SELECT * FROM entities_all WHERE id = ? AND tenant_id = ?", (id, owner)).fetchone()
        return dict(row) if row else None

    def get_entity(self, id: str) -> dict | None:
        """获取实体"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None

    def list_entities(self, entity_type: str = None) -> list[dict]:
        """列出实体"""
        with self._conn() as conn:
            if entity_type:
                rows = conn.execute("SELECT * FROM entities WHERE type = ? ORDER BY name", (entity_type,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM entities ORDER BY type, name").fetchall()
            return [dict(r) for r in rows]

    def delete_entity(self, id: str) -> bool:
        """删除实体及其所有关系（只动当前租户的行 —— 同名实体在别的租户下各有一份）"""
        owner = current_tenant()
        with self._conn() as conn:
            if owner:
                conn.execute(
                    "DELETE FROM relations_all WHERE (subject_id = ? OR object_id = ?) AND tenant_id = ?",
                    (id, id, owner),
                )
                cursor = conn.execute("DELETE FROM entities_all WHERE id = ? AND tenant_id = ?", (id, owner))
            else:
                conn.execute("DELETE FROM relations_all WHERE subject_id = ? OR object_id = ?", (id, id))
                cursor = conn.execute("DELETE FROM entities_all WHERE id = ?", (id,))
            return cursor.rowcount > 0

    # ── 关系操作 ──

    def add_relation(
        self,
        id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        valid_from: str = None,
        valid_until: str = None,
        confidence: float = 1.0,
        source: str = "",
        tenant_id: str | None = None,
    ) -> dict:
        """添加关系（落当前租户归属；tenant_id 语义同 add_entity）"""
        owner = current_tenant() if tenant_id is None else tenant_id
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO relations_all
                   (id, subject_id, predicate, object_id, valid_from, valid_until,
                    confidence, source, created_at, tenant_id, visibility)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'private')""",
                (
                    id,
                    subject_id,
                    predicate,
                    object_id,
                    valid_from,
                    valid_until,
                    confidence,
                    source,
                    datetime.now().isoformat(),
                    owner,
                ),
            )
            row = conn.execute("SELECT * FROM relations_all WHERE id = ? AND tenant_id = ?", (id, owner)).fetchone()
        return dict(row) if row else None

    def get_relation(self, id: str) -> dict | None:
        """获取关系"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM relations WHERE id = ?", (id,)).fetchone()
            return dict(row) if row else None

    def _build_relation_conditions(
        self, subject_id: str = None, object_id: str = None, predicate: str = None, at_time: str = None
    ) -> list:
        """构建关系查询条件"""
        conditions = []
        params = []

        if subject_id:
            conditions.append("subject_id = ?")
            params.append(subject_id)
        if object_id:
            conditions.append("object_id = ?")
            params.append(object_id)
        if predicate:
            conditions.append("predicate = ?")
            params.append(predicate)
        if at_time:
            self._add_time_conditions(conditions, params, at_time)

        return conditions, params

    def _add_time_conditions(self, conditions: list, params: list, at_time: str) -> None:
        conditions.append("(valid_from IS NULL OR valid_from <= ?)")
        params.append(at_time)
        conditions.append("(valid_until IS NULL OR valid_until >= ?)")
        params.append(at_time)

    def query_relations(
        self, subject_id: str = None, object_id: str = None, predicate: str = None, at_time: str = None
    ) -> list[dict]:
        """查询关系"""
        conditions, params = self._build_relation_conditions(subject_id, object_id, predicate, at_time)
        where = " AND ".join(conditions) if conditions else "1=1"

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM relations WHERE {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def invalidate_relation(self, id: str, invalidated_at: str = None) -> bool:
        """使关系失效"""
        invalidated_at = invalidated_at or datetime.now().isoformat()
        owner = current_tenant()
        with self._conn() as conn:
            if owner:
                cursor = conn.execute(
                    "UPDATE relations_all SET valid_until = ? WHERE id = ? AND tenant_id = ?",
                    (invalidated_at, id, owner),
                )
            else:
                cursor = conn.execute(
                    "UPDATE relations_all SET valid_until = ? WHERE id = ?",
                    (invalidated_at, id),
                )
            return cursor.rowcount > 0

    def delete_relation(self, id: str) -> bool:
        """删除关系（只动当前租户的行）"""
        owner = current_tenant()
        with self._conn() as conn:
            if owner:
                cursor = conn.execute("DELETE FROM relations_all WHERE id = ? AND tenant_id = ?", (id, owner))
            else:
                cursor = conn.execute("DELETE FROM relations_all WHERE id = ?", (id,))
            return cursor.rowcount > 0

    # ── 图查询 ──

    def get_neighbors(self, entity_id: str, at_time: str = None) -> dict:
        """获取实体的邻居"""
        outgoing = self.query_relations(subject_id=entity_id, at_time=at_time)
        incoming = self.query_relations(object_id=entity_id, at_time=at_time)

        return {
            "entity": self.get_entity(entity_id),
            "outgoing": outgoing,
            "incoming": incoming,
        }

    def find_path(self, from_id: str, to_id: str, max_depth: int = 3) -> list[list[dict]]:
        """查找两个实体之间的路径（BFS）"""
        if from_id == to_id:
            return []

        visited = {from_id}
        queue = [(from_id, [])]

        while queue:
            current_id, path = queue.pop(0)

            if len(path) >= max_depth:
                continue

            # 获取所有出边
            relations = self.query_relations(subject_id=current_id)

            for rel in relations:
                next_id = rel["object_id"]

                if next_id == to_id:
                    return [path + [rel]]

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, path + [rel]))

        return []

    def export_graph(self) -> dict:
        """导出知识图谱"""
        entities = self.list_entities()

        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM relations").fetchall()
            relations = [dict(r) for r in rows]

        return {
            "entities": entities,
            "relations": relations,
        }

    def stats(self) -> dict:
        """图谱统计"""
        with self._conn() as conn:
            entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            active_relations = conn.execute("SELECT COUNT(*) FROM relations WHERE valid_until IS NULL").fetchone()[0]

        return {
            "entities": entity_count,
            "relations": relation_count,
            "active_relations": active_relations,
            "db_path": self.db_path,
        }

    # ── 伏羲移植：增强功能 ──

    # Agent type -> relevant edge types
    PERSPECTIVE_EDGE_TYPES: dict = {
        "coding": ["causes", "depends_on", "enables", "refines", "hinders"],
        "messaging": ["temporal", "related_to", "contradicts"],
        "ide": ["refines", "supersedes", "depends_on", "related_to"],
        "custom": None,  # All edge types
    }

    _RELATION_PATTERNS = [
        (r"使用(\w+)", "uses"),
        (r"部署了?(\w+)", "deploys"),
        (r"集成了?(\w+)", "integrates"),
        (r"修复了?(\w+)", "fixes"),
        (r"基于(\w+)", "based_on"),
        (r"依赖(\w+)", "depends_on"),
    ]

    def bfs_traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_types: list[str] | None = None,
        min_weight: float = 0.3,
    ) -> list[dict]:
        """BFS遍历图谱（从伏羲移植）

        Args:
            start_id: 起始实体ID
            max_depth: 最大深度
            edge_types: 边类型过滤列表
            min_weight: 最小权重阈值

        Returns:
            遍历结果列表，含 depth 和 weight 字段
        """
        visited: set[str] = set()
        queue = deque([(start_id, 0)])
        visited.add(start_id)
        result = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # 获取出边和入边
            if edge_types:
                placeholders = ",".join("?" * len(edge_types))
                query = f"""SELECT DISTINCT e.*,
                    CASE WHEN e.subject_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction
                    FROM relations e
                    WHERE (e.subject_id = ? OR e.object_id = ?)
                    AND e.predicate IN ({placeholders})
                    AND e.confidence >= ?"""
                params = [current_id, current_id, current_id] + edge_types + [min_weight]
            else:
                query = """SELECT DISTINCT e.*,
                    CASE WHEN e.subject_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction
                    FROM relations e
                    WHERE (e.subject_id = ? OR e.object_id = ?)
                    AND e.confidence >= ?"""
                params = [current_id, current_id, current_id, min_weight]

            with self._conn() as conn:
                rows = conn.execute(query, params).fetchall()

            for r in rows:
                d = dict(r)
                peer_id = d["object_id"] if d["direction"] == "outgoing" else d["subject_id"]
                if peer_id not in visited:
                    visited.add(peer_id)
                    d["depth"] = depth + 1
                    result.append(d)
                    queue.append((peer_id, depth + 1))

        result.sort(key=lambda x: (x.get("depth", 0), -x.get("confidence", 0)))
        return result

    def causal_chain(self, item_id: str, max_length: int = 5) -> list[dict]:
        """追溯因果链（从伏羲移植）

        沿着 causes→enables→depends_on 边追溯因果链。
        """
        chain = []
        current = item_id
        visited = set()

        for _ in range(max_length):
            if current in visited:
                break
            visited.add(current)

            entity = self.get_entity(current)
            if not entity:
                break
            chain.append(entity)

            # 找下一个因果节点
            with self._conn() as conn:
                edge = conn.execute(
                    "SELECT subject_id FROM relations "
                    "WHERE object_id = ? AND predicate IN ('causes','enables','depends_on') "
                    "ORDER BY confidence DESC LIMIT 1",
                    (current,),
                ).fetchone()

            if not edge:
                break
            current = edge["subject_id"]

        return chain

    def discover_auto_relations(
        self,
        drawers: list,
        top_k: int = 50,
        similarity_threshold: float = 0.65,
    ) -> dict:
        """基于嵌入向量聚类自动发现新关系（从伏羲移植）

        Args:
            drawers: 记忆列表（需含 metadata.embedding）
            top_k: 最多发现的关系数
            similarity_threshold: 相似度阈值

        Returns:
            {"status": str, "found": int, "suggestions": list}
        """
        # 取有嵌入向量的活跃记忆
        items = [d for d in drawers if d.metadata.get("embedding")]
        if len(items) < 5:
            return {"status": "skip", "reason": "not enough items with embeddings", "found": 0}

        candidates = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i].wing == items[j].wing:
                    continue  # 同一 Wing 的可能已有关系，跳过
                try:
                    sim = self._cosine_sim(
                        items[i].metadata["embedding"],
                        items[j].metadata["embedding"],
                    )
                    if sim >= similarity_threshold:
                        candidates.append(
                            {
                                "source_id": items[i].id,
                                "target_id": items[j].id,
                                "similarity": sim,
                            }
                        )
                except Exception:
                    continue

        if not candidates:
            return {"status": "ok", "found": 0, "suggestions": []}

        # 去重（已存在的边）
        existing_pairs = set()
        with self._conn() as conn:
            rows = conn.execute("SELECT subject_id, object_id FROM relations").fetchall()
            for r in rows:
                existing_pairs.add((r["subject_id"], r["object_id"]))

        new_candidates = [
            c
            for c in candidates
            if (c["source_id"], c["target_id"]) not in existing_pairs
            and (c["target_id"], c["source_id"]) not in existing_pairs
        ]

        discovered = 0
        suggestions = []
        for cand in new_candidates[:top_k]:
            # 推断边类型
            source_content = ""
            target_content = ""
            for d in items:
                if d.id == cand["source_id"]:
                    source_content = d.content[:500]
                elif d.id == cand["target_id"]:
                    target_content = d.content[:500]

            edge_type = self._infer_edge_type(source_content, target_content)

            # 自动创建边
            rel_id = self.add_relation(
                id=f"auto_{cand['source_id'][:8]}_{cand['target_id'][:8]}",
                subject_id=cand["source_id"],
                predicate=edge_type,
                object_id=cand["target_id"],
                confidence=cand["similarity"],
                source="auto_discovery",
            )
            discovered += 1
            suggestions.append(
                {
                    "source": cand["source_id"][:8],
                    "target": cand["target_id"][:8],
                    "similarity": round(cand["similarity"], 3),
                    "edge_id": rel_id["id"][:8] if rel_id else "",
                }
            )

        logger.info(f"Auto-discovery: found {discovered} new relations")
        return {"status": "ok", "found": discovered, "suggestions": suggestions}

    def get_perspective_view(
        self,
        agent_type: str,
        focus_entity: str | None = None,
        max_depth: int = 2,
    ) -> dict:
        """获取多视角知识图谱（从伏羲移植）

        Args:
            agent_type: "coding" | "messaging" | "ide" | "custom"
            focus_entity: 可选的中心实体名
            max_depth: BFS 遍历深度

        Returns:
            视角视图字典
        """
        if agent_type not in self.PERSPECTIVE_EDGE_TYPES:
            return {
                "status": "error",
                "message": f"Unknown agent_type: {agent_type}. Valid: {list(self.PERSPECTIVE_EDGE_TYPES.keys())}",
            }

        edge_filter = self.PERSPECTIVE_EDGE_TYPES[agent_type]

        if focus_entity:
            # BFS from matching entities
            entities = self.list_entities()
            matching = [e for e in entities if focus_entity.lower() in e["name"].lower()]
            if not matching:
                return {"status": "not_found", "query": focus_entity, "agent_type": agent_type}

            all_results = []
            for entity in matching[:5]:
                bfs_results = self.bfs_traverse(
                    entity["id"],
                    max_depth=max_depth,
                    edge_types=edge_filter,
                    min_weight=0.1,
                )
                all_results.append(
                    {
                        "id": entity["id"][:8],
                        "name": entity["name"],
                        "type": entity["type"],
                        "connections": len(bfs_results),
                        "neighbors": [
                            {
                                "id": n.get("id", "")[:8],
                                "direction": n.get("direction", ""),
                                "predicate": n.get("predicate", ""),
                                "confidence": round(n.get("confidence", 0), 3),
                                "depth": n.get("depth", 0),
                            }
                            for n in bfs_results[:8]
                        ],
                    }
                )
            return {
                "status": "ok",
                "agent_type": agent_type,
                "perspective": agent_type,
                "query": focus_entity,
                "found": len(all_results),
                "results": all_results,
            }
        else:
            # 返回过滤后的高权重边
            if edge_filter:
                placeholders = ",".join("?" * len(edge_filter))
                with self._conn() as conn:
                    rows = conn.execute(
                        f"SELECT * FROM relations WHERE predicate IN ({placeholders}) "
                        f"ORDER BY confidence DESC LIMIT 50",
                        edge_filter,
                    ).fetchall()
            else:
                with self._conn() as conn:
                    rows = conn.execute("SELECT * FROM relations ORDER BY confidence DESC LIMIT 50").fetchall()

            edges = []
            for r in rows:
                d = dict(r)
                edges.append(
                    {
                        "id": d["id"][:8],
                        "predicate": d["predicate"],
                        "confidence": round(d.get("confidence", 0), 3),
                        "subject_id": d["subject_id"][:8],
                        "object_id": d["object_id"][:8],
                    }
                )

            return {
                "status": "ok",
                "agent_type": agent_type,
                "perspective": agent_type,
                "edge_count": len(edges),
                "edges": edges,
            }

    def score_depends_on_edge(self, source_id: str, target_id: str) -> float:
        """评分 depends_on 边质量（从伏羲移植）"""
        source = self.get_entity(source_id)
        target = self.get_entity(target_id)
        if not source or not target:
            return 0.0

        source_desc = source.get("description", "")
        target_desc = target.get("description", "")

        depend_keywords = [
            "依赖",
            "需要",
            "前提",
            "基于",
            "取决于",
            "必需",
            "必要条件",
            "依赖项",
            "所依赖",
            "的前提",
            "依赖关系",
            "前置条件",
            "先决条件",
            "所需",
            "必备",
            "requires",
            "depends",
            "based on",
            "prerequisite",
        ]

        kw_score = 0.0
        source_matched = sum(1 for kw in depend_keywords if kw in source_desc)
        target_matched = sum(1 for kw in depend_keywords if kw in target_desc)
        total_matched = source_matched + target_matched
        if total_matched > 0:
            kw_score = min(0.4, 0.12 + (total_matched - 1) * 0.06)

        overlap_score = 0.0
        source_words = set(source_desc.lower().split())
        target_words = set(target_desc.lower().split())
        if source_words and target_words:
            overlap = len(source_words & target_words)
            union = len(source_words | target_words)
            if union > 0:
                jaccard = overlap / union
                overlap_score = min(0.5, jaccard * 0.9)

        return round(min(1.0, kw_score + overlap_score), 3)

    def clean_depends_on_edges(self, dry_run: bool = True) -> dict:
        """清理低质量 depends_on 边（从伏羲移植）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, subject_id, object_id, confidence FROM relations WHERE predicate='depends_on'"
            ).fetchall()

        if not rows:
            return {"status": "ok", "total": 0, "high": 0, "medium": 0, "low": 0, "downgraded": 0}

        high = 0
        medium = 0
        low = 0
        downgraded = 0

        for row in rows:
            score = self.score_depends_on_edge(row["subject_id"], row["object_id"])
            if score >= 0.7:
                high += 1
            elif score >= 0.5:
                medium += 1
            else:
                low += 1
                if not dry_run:
                    self._downgrade_relation(row["id"], score)
                    downgraded += 1

        if dry_run:
            logger.info(f"[depends_on] dry run: high={high}, medium={medium}, low={low}")
        else:
            logger.info(f"[depends_on] cleaned: high={high}, medium={medium}, downgraded={downgraded}")

        return {
            "status": "dry_run" if dry_run else "cleaned",
            "total": len(rows),
            "high": high,
            "medium": medium,
            "low": low,
            "downgraded": downgraded if not dry_run else low,
        }

    def _downgrade_relation(self, row_id, score):
        owner = current_tenant()
        with self._conn() as c:
            if owner:
                c.execute(
                    "UPDATE relations_all SET predicate='related_to', confidence=? WHERE id=? AND tenant_id=?",
                    (score, row_id, owner),
                )
            else:
                c.execute(
                    "UPDATE relations_all SET predicate='related_to', confidence=? WHERE id=?",
                    (score, row_id),
                )

    def get_graph_quality_stats(self) -> dict:
        """获取图谱质量统计（从伏羲移植）"""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM relations").fetchone()
            total_cnt = total["cnt"] if total else 0

            if total_cnt == 0:
                return {"total_edges": 0, "by_type": {}, "related_to_pct": 0, "depends_on_quality": {}}

            by_type = {}
            rows = conn.execute("SELECT predicate, COUNT(*) AS cnt FROM relations GROUP BY predicate").fetchall()
            for r in rows:
                by_type[r["predicate"]] = r["cnt"]

            related_to_cnt = by_type.get("related_to", 0)
            related_to_pct = round(related_to_cnt / total_cnt * 100, 1) if total_cnt > 0 else 0

            depends_on_quality = {}
            dep_rows = conn.execute("SELECT confidence FROM relations WHERE predicate='depends_on'").fetchall()
            if dep_rows:
                high = sum(1 for r in dep_rows if r["confidence"] >= 0.7)
                medium = sum(1 for r in dep_rows if 0.5 <= r["confidence"] < 0.7)
                low = sum(1 for r in dep_rows if r["confidence"] < 0.5)
                depends_on_quality = {
                    "total": len(dep_rows),
                    "high": high,
                    "high_pct": round(high / len(dep_rows) * 100, 1),
                    "medium": medium,
                    "low": low,
                }

        return {
            "total_edges": total_cnt,
            "by_type": by_type,
            "related_to_pct": related_to_pct,
            "depends_on_quality": depends_on_quality,
        }

    @staticmethod
    def _cosine_sim(a: list, b: list) -> float:
        """余弦相似度（委托给统一实现）"""
        from .utils import cosine_similarity

        return cosine_similarity(a, b)

    @staticmethod
    def _infer_edge_type(
        source_text: str,
        target_text: str,
        source_time: str = "",
        target_time: str = "",
    ) -> str:
        """推断边类型（从伏羲移植）"""
        cause_keywords = [
            "因为",
            "导致",
            "造成",
            "原因",
            "所以",
            "因此",
            "结果",
            "引起",
            "致使",
            "由于",
            "使得",
            "结果是",
            "引发",
            "触发",
            "从而",
            "以致",
            "进而",
            "随之",
            "之所以",
            "是因为",
            "归因于",
            "源自",
            "源于",
            "究其原因",
            "thus",
            "because",
            "cause",
            "result",
            "lead to",
            "therefore",
        ]
        if any(kw in source_text for kw in cause_keywords):
            return "causes"

        if source_time and target_time and source_time < target_time:
            return "temporal"

        depend_keywords = [
            "依赖",
            "需要",
            "前提",
            "基于",
            "取决于",
            "必需",
            "必要条件",
            "依赖项",
            "所依赖",
            "的前提",
            "requires",
            "depends",
            "based on",
            "prerequisite",
        ]
        if any(kw in target_text for kw in depend_keywords):
            return "depends_on"

        enable_keywords = [
            "使得",
            "促成",
            "实现",
            "达到",
            "允许",
            "赋能",
            "enable",
            "achieve",
            "realize",
            "allow",
            "facilitate",
        ]
        if any(kw in source_text for kw in enable_keywords):
            return "enables"

        refine_keywords = [
            "进一步",
            "细化",
            "补充",
            "详细说明",
            "具体来说",
            "深入",
            "完善",
            "优化",
            "改进",
            "修正",
            "更新",
            "迭代",
            "深化",
            "扩展",
            "升级",
            "新版",
            "重写",
            "修订",
            "refine",
            "elaborate",
            "detail",
            "improve",
            "optimize",
            "revise",
            "enhance",
            "extend",
            "upgrade",
            "rewrite",
        ]
        if any(kw in source_text for kw in refine_keywords):
            return "refines"

        contradict_keywords = [
            "但是",
            "然而",
            "不过",
            "可是",
            "却",
            "but",
            "however",
            "yet",
            "though",
            "nevertheless",
        ]
        if any(kw in source_text + target_text for kw in contradict_keywords):
            return "contradicts"

        return "related_to"

    def auto_extract_entities(self, drawers: list, max_drawers: int = 50) -> dict:
        """从记忆中自动提取实体和关系，丰富知识图谱

        提取策略：
        - 技术名词（Python/ONNX/SQLite 等）→ technology
        - 系统名（盘古/伏羲/OpenClaw）→ system
        - 人名/代号（羲和/玄女/轩辕）→ agent
        - 动词关系（使用/部署/集成/修复）→ 对应关系类型
        """
        from pangu.core.hashing import hex_digest

        # 实体类型识别规则
        ENTITY_PATTERNS = {
            "technology": [
                "Python",
                "ONNX",
                "SQLite",
                "FastAPI",
                "uvicorn",
                "Docker",
                "Redis",
                "PostgreSQL",
                "MySQL",
                "MongoDB",
                "ChromaDB",
                "PyTorch",
                "TensorFlow",
                "HuggingFace",
                " sentence-transformers",
            ],
            "system": ["盘古", "伏羲", "OpenClaw", "Claude", "MCP"],
            "agent": ["羲和", "玄女", "轩辕", "主人"],
            "protocol": ["MCP", "REST", "WebSocket", "HTTP", "gRPC"],
        }

        entities_added = 0
        relations_added = 0

        for drawer in drawers[:max_drawers]:
            content = drawer.content
            # 归属继承：图谱条目是**这条记忆**的衍生，租户跟着来源记忆走。
            # 兜底用请求作用域（抽取若由租户调用，两者一致）。
            owner = (drawer.metadata or {}).get("tenant_id") or current_tenant()

            found_entities = []
            for etype, keywords in ENTITY_PATTERNS.items():
                for kw in keywords:
                    if kw.lower() in content.lower():
                        eid = f"entity-{hex_digest(kw)[:12]}"
                        self.add_entity(eid, kw, etype, f"从记忆 {drawer.id[:8]} 提取", tenant_id=owner)
                        found_entities.append((eid, kw))
                        entities_added += 1

            relations_added += self._find_and_create_relations(found_entities, content, drawer.id, owner)

        return {
            "entities_added": entities_added,
            "relations_added": relations_added,
        }

    def _find_and_create_relations(self, found_entities, content, drawer_id, tenant_id: str | None = None):
        import re

        from pangu.core.hashing import hex_digest

        count = 0
        for i, (eid_a, _name_a) in enumerate(found_entities):
            for eid_b, name_b in found_entities[i + 1 :]:
                for pattern, predicate in self._RELATION_PATTERNS:
                    if re.search(pattern.replace(r"(\w+)", f".*{re.escape(name_b)}.*"), content):
                        rid = f"rel-{hex_digest(f'{eid_a}-{eid_b}-{predicate}')[:12]}"
                        self.add_relation(rid, eid_a, predicate, eid_b, source=drawer_id[:8], tenant_id=tenant_id)
                        count += 1
                        break
        return count

    def cross_domain_transfer(self, source_domain: str, target_domain: str) -> dict:
        """跨领域知识迁移 — 将一个领域的知识迁移到另一个领域

        Args:
            source_domain: 源领域 (wing)
            target_domain: 目标领域 (wing)

        Returns:
            迁移结果
        """
        # 查找源领域的实体
        source_entities = self.list_entities(entity_type="technology") + self.list_entities(entity_type="concept")

        # 查找目标领域的实体
        target_entities = self.list_entities(entity_type="technology") + self.list_entities(entity_type="concept")

        # 查找跨领域关联
        transfers = []
        for se in source_entities:
            for te in target_entities:
                if se["id"] != te["id"]:
                    transfer = self._check_transfer_candidate(se, te)
                    if transfer:
                        transfers.append(transfer)

        return {
            "source_domain": source_domain,
            "target_domain": target_domain,
            "transfers": transfers[:10],
            "count": len(transfers),
        }

    def _check_transfer_candidate(self, source: dict, target: dict) -> dict | None:
        se_relations = set(r["predicate"] for r in self.query_relations(subject_id=source["id"]))
        te_relations = set(r["predicate"] for r in self.query_relations(subject_id=target["id"]))
        common = se_relations & te_relations
        if common:
            return {
                "source": source["name"],
                "target": target["name"],
                "common_relations": list(common),
                "confidence": 0.7,
            }
        return None

    def find_similar_patterns(self, entity_id: str) -> list[dict]:
        """查找相似模式 — 在不同领域中找到类似的实体关系"""
        entity = self.get_entity(entity_id)
        if not entity:
            return []

        # 获取实体的关系
        relations = self.query_relations(subject_id=entity_id)
        if not relations:
            return []

        # 查找具有相似关系的其他实体
        patterns = []
        for rel in relations:
            similar_rels = self.query_relations(predicate=rel["predicate"])
            patterns.extend(self._find_similar_entities(similar_rels, entity_id, rel))

        # 去重
        seen = set()
        unique_patterns = []
        for p in patterns:
            key = (p["entity"], p["relation"])
            if key not in seen:
                seen.add(key)
                unique_patterns.append(p)

        return unique_patterns[:10]

    def _find_similar_entities(self, similar_rels, entity_id, rel):
        results = []
        for sr in similar_rels:
            if sr["object_id"] != entity_id:
                similar_entity = self.get_entity(sr["object_id"])
                if similar_entity:
                    results.append(
                        {
                            "entity": similar_entity["name"],
                            "relation": rel["predicate"],
                            "confidence": rel.get("confidence", 1.0),
                        }
                    )
        return results
