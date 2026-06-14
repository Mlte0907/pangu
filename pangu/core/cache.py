"""盘古 — 持久化 LLM 响应缓存

将 LLM 响应缓存到 SQLite，重启后仍然有效，避免重复消耗 token / 成本。

设计：
- 使用 SQLite 存储，无新增依赖
- 索引：hash_key (PRIMARY KEY), created_at, last_accessed
- 内存层 (LRU) + 磁盘层 (SQLite) 双层架构
- 写入节流：每 N 次写入才落盘一次
- TTL 过期清理
- 磁盘大小上限保护
- 线程级连接池：避免每次操作创建/关闭连接
"""

import collections
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .llm import LLMResponse


@dataclass
class CachedResponse:
    """缓存条目"""
    key: str
    provider: str
    model: str
    request: dict
    response: LLMResponse
    created_at: float
    last_accessed: float
    hit_count: int = 0
    disk_size: int = 0  # 字节


class PersistentCache:
    """SQLite 持久化缓存

    使用示例：
        cache = PersistentCache("/path/to/cache.db")
        cache.put("hash_key", request, response)
        cached = cache.get("hash_key")
        stats = cache.get_stats()
        cache.close()
    """

    def __init__(
        self,
        db_path: str = "",
        ttl_days: int = 7,
        max_disk_mb: float = 100.0,
        write_throttle: int = 10,
    ):
        self.db_path = db_path or self._default_db_path()
        self.ttl_seconds = ttl_days * 86400 if ttl_days > 0 else 0
        self.max_disk_bytes = int(max_disk_mb * 1024 * 1024) if max_disk_mb > 0 else 0
        self.write_throttle = max(1, write_throttle)

        # 写入节流计数器
        self._pending_writes = 0
        self._lock = threading.RLock()

        # 线程级连接池：每个线程持有自己的连接，避免频繁创建/销毁
        self._conn_pool = threading.local()

        # 性能指标
        self._get_latencies: collections.deque[float] = collections.deque(maxlen=1000)
        self._put_latencies: collections.deque[float] = collections.deque(maxlen=1000)

        # 初始化数据库
        self._init_db()
        # 启动时清理过期条目
        self._purge_expired()

    @staticmethod
    def _default_db_path() -> str:
        """默认数据库路径（与 fuxi.db 同目录）"""
        home = os.path.expanduser("~/.pangu")
        os.makedirs(home, exist_ok=True)
        return os.path.join(home, "llm_cache.db")

    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接并设置性能 PRAGMA"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            isolation_level=None,  # 自动提交
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB
        conn.execute("PRAGMA temp_store=MEMORY")
        try:
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        except sqlite3.DatabaseError:
            pass
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接（复用或创建）"""
        conn = getattr(self._conn_pool, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._conn_pool.conn = conn
        return conn

    @contextmanager
    def _connect(self):
        """兼容旧接口的上下文管理器（操作结束后不关闭连接）"""
        yield self._get_conn()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                request_json TEXT NOT NULL,
                content TEXT NOT NULL,
                usage_json TEXT NOT NULL DEFAULT '{}',
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                hit_count INTEGER DEFAULT 0,
                disk_size INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_last_accessed
                ON llm_cache(last_accessed DESC);
            CREATE INDEX IF NOT EXISTS idx_created_at
                ON llm_cache(created_at);
            CREATE INDEX IF NOT EXISTS idx_hit_count
                ON llm_cache(hit_count DESC);
        """)

    def _purge_expired(self) -> int:
        """清理过期条目，返回删除数量"""
        if self.ttl_seconds <= 0:
            return 0
        cutoff = time.time() - self.ttl_seconds
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM llm_cache WHERE created_at < ?", (cutoff,)
        )
        return cursor.rowcount

    def _check_disk_size(self) -> None:
        """检查并清理磁盘大小"""
        if self.max_disk_bytes <= 0:
            return
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COALESCE(SUM(disk_size), 0) FROM llm_cache"
        ).fetchone()[0]
        if total <= self.max_disk_bytes:
            return
        # 需要清理的字节数
        need_free = total - int(self.max_disk_bytes * 0.8)
        # 优先删除最少访问的（hit_count 最小，last_accessed 最早）
        freed = 0
        cursor = conn.execute(
            """SELECT key, disk_size FROM llm_cache
               ORDER BY hit_count ASC, last_accessed ASC"""
        )
        for key, size in cursor:
            if freed >= need_free:
                break
            conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
            freed += size

    def get(self, key: str) -> CachedResponse | None:
        """获取缓存条目（不存在返回 None）"""
        start = time.perf_counter()
        conn = self._get_conn()
        row = conn.execute(
            """SELECT key, provider, model, request_json, content,
                      usage_json, prompt_tokens, completion_tokens,
                      cost_usd, created_at, last_accessed, hit_count
               FROM llm_cache WHERE key = ?""",
            (key,),
        ).fetchone()
        elapsed = time.perf_counter() - start
        self._get_latencies.append(elapsed)

        if not row:
            return None

        # 检查过期
        if self.ttl_seconds > 0 and (time.time() - row[9]) > self.ttl_seconds:
            self.delete(key)
            return None

        # 异步更新访问时间 + 命中数（不阻塞读）
        with self._lock:
            self._pending_writes += 1
            if self._pending_writes >= self.write_throttle:
                self._pending_writes = 0
                self._flush_access_update(key)

        # 构造返回对象
        request = json.loads(row[3])
        usage = json.loads(row[5])
        response = LLMResponse(
            content=row[4],
            model=row[2],
            provider=row[1],
            latency_ms=0.0,  # 缓存命中不计延迟
            usage=usage,
        )
        return CachedResponse(
            key=row[0],
            provider=row[1],
            model=row[2],
            request=request,
            response=response,
            created_at=row[9],
            last_accessed=row[10],
            hit_count=row[11] + 1,  # 本次即将 +1
        )

    def _flush_access_update(self, key: str) -> None:
        """异步刷新访问更新（节流后批量）"""
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE llm_cache
                   SET last_accessed = ?, hit_count = hit_count + 1
                   WHERE key = ?""",
                (time.time(), key),
            )
        except Exception:
            pass

    def put(
        self,
        key: str,
        provider: str,
        model: str,
        request: dict,
        response: LLMResponse,
    ) -> None:
        """写入缓存"""
        start = time.perf_counter()
        request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
        content = response.content
        usage_json = json.dumps(response.usage or {}, ensure_ascii=False)
        prompt_tokens = (response.usage or {}).get("prompt_tokens", 0)
        completion_tokens = (response.usage or {}).get("completion_tokens", 0)

        # 估算磁盘占用
        size = len(content) + len(request_json) + len(usage_json) + 200

        now = time.time()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO llm_cache
               (key, provider, model, request_json, content, usage_json,
                prompt_tokens, completion_tokens, cost_usd,
                created_at, last_accessed, hit_count, disk_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, 0, ?)""",
            (
                key, provider, model, request_json, content, usage_json,
                prompt_tokens, completion_tokens,
                now, now, size,
            ),
        )

        elapsed = time.perf_counter() - start
        self._put_latencies.append(elapsed)

        # 检查磁盘大小
        self._check_disk_size()

    def delete(self, key: str) -> bool:
        """删除条目"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
        return cursor.rowcount > 0

    def clear(self) -> int:
        """清空所有缓存，返回删除数量"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM llm_cache")
        return cursor.rowcount

    def get_stats(self) -> dict:
        """获取缓存统计"""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*) as total_entries,
                   COALESCE(SUM(hit_count), 0) as total_hits,
                   COALESCE(SUM(disk_size), 0) as total_bytes,
                   COALESCE(SUM(prompt_tokens + completion_tokens), 0) as total_tokens,
                   COALESCE(MIN(created_at), 0) as oldest,
                   COALESCE(MAX(last_accessed), 0) as newest
               FROM llm_cache"""
        ).fetchone()

        total, hits, bytes_used, tokens, oldest, newest = row
        if total > 0 and oldest > 0:
            age_hours = (time.time() - oldest) / 3600
        else:
            age_hours = 0.0

        return {
            "backend": "sqlite",
            "db_path": self.db_path,
            "total_entries": total,
            "total_hits": hits,
            "total_bytes": bytes_used,
            "total_mb": round(bytes_used / 1024 / 1024, 3),
            "total_tokens_saved": tokens,
            "oldest_age_hours": round(age_hours, 2),
            "ttl_seconds": self.ttl_seconds,
            "max_disk_bytes": self.max_disk_bytes,
            "disk_usage_pct": (
                round(bytes_used / self.max_disk_bytes * 100, 2)
                if self.max_disk_bytes > 0 else 0.0
            ),
        }

    def metrics(self) -> dict[str, Any]:
        """返回性能指标

        包含：
        - get_latency: 读取延迟 (avg/p50/p95/p99, 秒)
        - put_latency: 写入延迟 (avg/p50/p95/p99, 秒)
        - connection_pool: 连接池状态
        - pending_writes: 待写入计数
        """
        latencies = list(self._get_latencies)
        put_lats = list(self._put_latencies)
        return {
            "backend": "sqlite_pool",
            "connections_active": 1 if getattr(self._conn_pool, "conn", None) else 0,
            "get_latency": {
                "count": len(latencies),
                "avg_ms": round(sum(latencies) / len(latencies) * 1000, 3) if latencies else 0,
                "p50_ms": round(_percentile(latencies, 50) * 1000, 3) if latencies else 0,
                "p95_ms": round(_percentile(latencies, 95) * 1000, 3) if latencies else 0,
                "p99_ms": round(_percentile(latencies, 99) * 1000, 3) if latencies else 0,
            },
            "put_latency": {
                "count": len(put_lats),
                "avg_ms": round(sum(put_lats) / len(put_lats) * 1000, 3) if put_lats else 0,
                "p50_ms": round(_percentile(put_lats, 50) * 1000, 3) if put_lats else 0,
                "p95_ms": round(_percentile(put_lats, 95) * 1000, 3) if put_lats else 0,
                "p99_ms": round(_percentile(put_lats, 99) * 1000, 3) if put_lats else 0,
            },
            "pending_writes": self._pending_writes,
            "write_throttle": self.write_throttle,
        }

    def get_top_keys(self, limit: int = 10) -> list[dict]:
        """获取访问最频繁的键（用于调试）"""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT key, provider, model, hit_count, last_accessed,
                      prompt_tokens + completion_tokens as tokens
               FROM llm_cache
               ORDER BY hit_count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "key": r[0][:16] + "...",
                "provider": r[1],
                "model": r[2],
                "hit_count": r[3],
                "last_accessed": r[4],
                "tokens": r[5],
            }
            for r in rows
        ]

    def vacuum(self) -> None:
        """整理数据库（释放空间）"""
        conn = self._get_conn()
        conn.execute("VACUUM")

    def close(self) -> None:
        """关闭当前线程的连接"""
        conn = getattr(self._conn_pool, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._conn_pool.conn = None

    def __del__(self):
        """析构时尝试关闭连接"""
        try:
            self.close()
        except Exception:
            pass

    def __len__(self) -> int:
        """返回条目数"""
        try:
            conn = self._get_conn()
            row = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()
            return row[0] if row else 0
        except Exception:
            return 0


def _percentile(data: list[float], pct: float) -> float:
    """计算百分位数（线性插值）"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    k = (pct / 100) * (n - 1)
    f = int(k)
    c = k - f
    if f + 1 < n:
        return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
    return sorted_data[f]
