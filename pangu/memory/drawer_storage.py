"""抽屉存储后端 — SQLite 并发安全存储

提供 JSON 和 SQLite 两种存储后端，支持自动迁移。
SQLite 后端提供：
- WAL 模式支持并发读写
- 事务性写入保证数据一致性
- 自动备份和恢复机制
"""

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.drawer_storage")

# SQLite 存储的【数据格式】版本，写入 storage_info 表。
# 与软件版本无关：软件版本是 pangu.__version__（唯一事实源为
# pangu/__init__.py + pyproject.toml）。发版时不要改这个值，
# 只有 storage_info / drawers 表结构发生不兼容变更时才调整。
_STORAGE_FORMAT_VERSION = "0.1.0"


class DrawerStorage:
    """抽屉存储抽象基类"""

    def load(self) -> list[Drawer]:
        """加载所有抽屉"""
        raise NotImplementedError

    def save(self, drawers: list[Drawer]) -> None:
        """保存所有抽屉"""
        raise NotImplementedError

    def close(self) -> None:
        """关闭存储"""
        pass


class JsonDrawerStorage(DrawerStorage):
    """JSON 文件存储（现有实现）"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._cache = {}
        self._cache_ttl = 30.0
        self._last_cache_time = 0.0

    def load(self) -> list[Drawer]:
        """从 JSON 文件加载抽屉"""
        cache_key = f"drawers_{self.file_path}"
        now = time.time()

        if self._cache_ttl > 0 and (now - self._last_cache_time) < self._cache_ttl:
            if cache_key in self._cache:
                return self._cache[cache_key]

        drawers = []
        if self.file_path.exists():
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    drawers.append(Drawer.from_dict(d))
            except Exception as e:
                logger.warning(f"JSON 文件读取失败: {e}")

        self._cache[cache_key] = drawers
        self._last_cache_time = now
        return drawers

    def save(self, drawers: list[Drawer]) -> None:
        """保存抽屉到 JSON 文件（原子写入）"""
        tmp_file = self.file_path.with_suffix(".json.tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, self.file_path)

            # 清除缓存
            cache_key = f"drawers_{self.file_path}"
            self._cache.pop(cache_key, None)

        except Exception as e:
            logger.error(f"JSON 文件写入失败: {e}")
            # 清理临时文件
            if tmp_file.exists():
                tmp_file.unlink()
            raise

    def close(self) -> None:
        """关闭存储"""
        self._cache.clear()


class SqliteDrawerStorage(DrawerStorage):
    """SQLite 存储后端（支持并发读写）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn_pool = threading.local()
        self._lock = threading.RLock()

        # 初始化数据库
        self._init_db()

    def _create_connection(self) -> sqlite3.Connection:
        """创建 SQLite 连接并设置性能优化 PRAGMA"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None,  # 自动提交模式
            check_same_thread=False,
        )

        # 性能优化 PRAGMA
        conn.execute("PRAGMA journal_mode=WAL")  # WAL 模式支持并发读写
        conn.execute("PRAGMA synchronous=NORMAL")  # 平衡性能和安全性
        conn.execute("PRAGMA cache_size=-64000")  # 64MB 缓存
        conn.execute("PRAGMA temp_store=MEMORY")  # 临时表存储在内存

        # 尝试启用内存映射（如果支持）
        try:
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        except sqlite3.DatabaseError:
            pass

        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接"""
        conn = getattr(self._conn_pool, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._conn_pool.conn = conn
        return conn

    @contextmanager
    def _connect(self):
        """连接上下文管理器"""
        conn = self._get_conn()
        try:
            yield conn
        except Exception as e:
            logger.error(f"SQLite 操作失败: {e}")
            raise

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        with self._connect() as conn:
            conn.executescript("""
                -- 抽屉主表
                CREATE TABLE IF NOT EXISTS drawers (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    wing TEXT DEFAULT 'default',
                    room TEXT DEFAULT 'general',
                    hall TEXT DEFAULT 'hall_events',
                    importance REAL DEFAULT 3.0,
                    emotional_weight REAL DEFAULT 0.0,
                    source_file TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',  -- JSON 数组
                    author TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',  -- JSON 对象
                    updated_at REAL NOT NULL,
                    created_timestamp REAL NOT NULL
                );

                -- 索引优化查询性能
                CREATE INDEX IF NOT EXISTS idx_drawers_wing ON drawers(wing);
                CREATE INDEX IF NOT EXISTS idx_drawers_room ON drawers(room);
                CREATE INDEX IF NOT EXISTS idx_drawers_importance ON drawers(importance DESC);
                CREATE INDEX IF NOT EXISTS idx_drawers_created_at ON drawers(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_drawers_updated_at ON drawers(updated_at DESC);

                -- 版本信息表
                CREATE TABLE IF NOT EXISTS storage_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 记录存储【格式】版本 —— 不是软件版本。
            # 软件版本见 pangu.__version__（唯一事实源：pangu/__init__.py
            # 与 pyproject.toml）。此处的值描述 storage_info 表所承载的
            # 数据布局，仅在表结构变更时才应调整，发版时不要跟着改。
            conn.execute(
                "INSERT OR REPLACE INTO storage_info (key, value, updated_at) VALUES (?, ?, ?)",
                ("version", _STORAGE_FORMAT_VERSION, time.time()),
            )

    def load(self) -> list[Drawer]:
        """从 SQLite 加载所有抽屉"""
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM drawers")
            rows = cursor.fetchall()

            drawers = []
            for row in rows:
                drawer_dict = {
                    "id": row[0],
                    "content": row[1],
                    "wing": row[2],
                    "room": row[3],
                    "hall": row[4],
                    "importance": row[5],
                    "emotional_weight": row[6],
                    "source_file": row[7],
                    "tags": json.loads(row[8]) if row[8] else [],
                    "author": row[9],
                    "created_at": row[10],
                    "metadata": json.loads(row[11]) if row[11] else {},
                }
                drawers.append(Drawer.from_dict(drawer_dict))

            return drawers

    def save(self, drawers: list[Drawer]) -> None:
        """保存所有抽屉到 SQLite（事务性写入）"""
        with self._lock:  # 确保线程安全
            with self._connect() as conn:
                try:
                    # 开始事务
                    conn.execute("BEGIN IMMEDIATE")

                    # 清空现有数据
                    conn.execute("DELETE FROM drawers")

                    # 批量插入
                    insert_data = []
                    current_time = time.time()

                    for drawer in drawers:
                        insert_data.append(
                            (
                                drawer.id,
                                drawer.content,
                                drawer.wing,
                                drawer.room,
                                drawer.hall,
                                drawer.importance,
                                drawer.emotional_weight,
                                drawer.source_file,
                                json.dumps(drawer.tags, ensure_ascii=False),
                                drawer.author,
                                drawer.created_at,
                                json.dumps(drawer.metadata, ensure_ascii=False),
                                current_time,  # updated_at
                                current_time,  # created_timestamp
                            )
                        )

                    conn.executemany(
                        """INSERT INTO drawers
                           (id, content, wing, room, hall, importance, emotional_weight,
                            source_file, tags, author, created_at, metadata, updated_at, created_timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        insert_data,
                    )

                    # 提交事务
                    conn.execute("COMMIT")

                    logger.info(f"成功保存 {len(drawers)} 个抽屉到 SQLite")

                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"SQLite 保存失败: {e}")
                    raise

    def save_incremental(self, drawers: list[Drawer], drawer_ids: set) -> None:
        """增量保存指定 ID 的抽屉（优化性能）"""
        with self._lock:
            with self._connect() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")

                    # 删除指定 ID 的抽屉
                    if drawer_ids:
                        placeholders = ",".join(["?" for _ in drawer_ids])
                        conn.execute(f"DELETE FROM drawers WHERE id IN ({placeholders})", list(drawer_ids))

                    # 插入新数据
                    insert_data = []
                    current_time = time.time()

                    for drawer in drawers:
                        if drawer.id in drawer_ids:
                            insert_data.append(
                                (
                                    drawer.id,
                                    drawer.content,
                                    drawer.wing,
                                    drawer.room,
                                    drawer.hall,
                                    drawer.importance,
                                    drawer.emotional_weight,
                                    drawer.source_file,
                                    json.dumps(drawer.tags, ensure_ascii=False),
                                    drawer.author,
                                    drawer.created_at,
                                    json.dumps(drawer.metadata, ensure_ascii=False),
                                    current_time,
                                    current_time,
                                )
                            )

                    if insert_data:
                        conn.executemany(
                            """INSERT INTO drawers
                               (id, content, wing, room, hall, importance, emotional_weight,
                                source_file, tags, author, created_at, metadata, updated_at, created_timestamp)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            insert_data,
                        )

                    conn.execute("COMMIT")

                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"SQLite 增量保存失败: {e}")
                    raise

    def close(self) -> None:
        """关闭 SQLite 连接"""
        conn = getattr(self._conn_pool, "conn", None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._conn_pool.conn = None

    def backup(self, backup_path: str) -> bool:
        """备份数据库"""
        try:
            with self._connect() as conn:
                conn.execute(f"VACUUM INTO '{backup_path}'")
            logger.info(f"数据库备份到: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return False

    def get_stats(self) -> dict:
        """获取存储统计信息"""
        with self._connect() as conn:
            # 记录数
            cursor = conn.execute("SELECT COUNT(*) FROM drawers")
            count = cursor.fetchone()[0]

            # 数据库大小
            cursor = conn.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            size_bytes = cursor.fetchone()[0]

            # 最后更新时间
            cursor = conn.execute("SELECT MAX(updated_at) FROM drawers")
            last_updated = cursor.fetchone()[0]

            return {
                "backend": "sqlite",
                "count": count,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "last_updated": last_updated,
                "db_path": self.db_path,
            }


class StorageFactory:
    """存储工厂 — 根据配置创建合适的存储后端"""

    @staticmethod
    def create(palace_path: str, use_sqlite: bool = False) -> DrawerStorage:
        """创建存储实例

        Args:
            palace_path: 宫殿路径
            use_sqlite: 是否使用 SQLite 存储

        Returns:
            存储实例
        """
        if use_sqlite:
            db_path = os.path.join(palace_path, "drawers.db")
            return SqliteDrawerStorage(db_path)
        else:
            file_path = os.path.join(palace_path, "drawers.json")
            return JsonDrawerStorage(file_path)

    @staticmethod
    def migrate_json_to_sqlite(json_path: str, db_path: str) -> bool:
        """将 JSON 文件迁移到 SQLite

        Args:
            json_path: JSON 文件路径
            db_path: SQLite 数据库路径

        Returns:
            是否迁移成功
        """
        try:
            # 读取 JSON 文件
            json_storage = JsonDrawerStorage(json_path)
            drawers = json_storage.load()

            if not drawers:
                logger.warning(f"JSON 文件为空或不存在: {json_path}")
                return False

            # 创建 SQLite 存储
            sqlite_storage = SqliteDrawerStorage(db_path)

            # 保存数据
            sqlite_storage.save(drawers)

            # 验证迁移结果
            loaded_drawers = sqlite_storage.load()
            if len(loaded_drawers) != len(drawers):
                logger.error(f"迁移验证失败：期望 {len(drawers)} 条，实际 {len(loaded_drawers)} 条")
                return False

            # 备份原 JSON 文件
            backup_path = f"{json_path}.bak"
            if os.path.exists(json_path):
                os.rename(json_path, backup_path)
                logger.info(f"原 JSON 文件备份到: {backup_path}")

            sqlite_storage.close()
            logger.info(f"成功迁移 {len(drawers)} 条记忆到 SQLite")
            return True

        except Exception as e:
            logger.error(f"迁移失败: {e}")
            return False
