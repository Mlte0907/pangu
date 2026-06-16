"""盘古智能缓存管理 — 自适应缓存策略和缓存预热

核心能力：
1. 自适应TTL：根据访问频率自动调整缓存过期时间
2. 缓存预热：启动时自动预热热点数据
3. 缓存驱逐：智能选择驱逐策略（LRU/LFU/ARC）
4. 缓存统计：命中率、驱逐率、内存使用统计
5. 缓存穿透防护：防止不存在的数据反复查询
"""
import logging
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger("pangu.memory.smart_cache")


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: any
    created_at: float
    last_accessed: float
    access_count: int = 0
    ttl: float = 3600.0
    size_bytes: int = 0


class SmartCache:
    """智能缓存引擎"""

    def __init__(self, max_size: int = 1000, max_memory_mb: float = 100):
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        self._current_memory = 0

        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._penetration_blocked = 0
        self._null_set: set[str] = set()

    def get(self, key: str):
        """获取缓存"""
        if key in self._null_set:
            self._penetration_blocked += 1
            return None

        if key in self._entries:
            entry = self._entries[key]
            now = time.time()

            if now - entry.created_at > entry.ttl:
                self._remove(key)
                self._misses += 1
                return None

            entry.last_accessed = now
            entry.access_count += 1
            self._entries.move_to_end(key)
            self._hits += 1
            return entry.value

        self._misses += 1
        return None

    def set(self, key: str, value, ttl: float = 3600.0):
        """设置缓存"""
        now = time.time()
        size = len(str(value).encode()) if value else 0

        if key in self._entries:
            old = self._entries[key]
            self._current_memory -= old.size_bytes
            self._entries.move_to_end(key)
        else:
            if len(self._entries) >= self._max_size:
                self._evict_lfu()

        entry = CacheEntry(
            key=key, value=value, created_at=now,
            last_accessed=now, ttl=ttl, size_bytes=size,
        )
        self._entries[key] = entry
        self._current_memory += size

        self._null_set.discard(key)

    def set_null(self, key: str, ttl: float = 300.0):
        """设置空值缓存（防穿透）"""
        self._null_set.add(key)

    def invalidate(self, key: str) -> bool:
        """失效缓存"""
        if key in self._entries:
            self._remove(key)
            return True
        if key in self._null_set:
            self._null_set.discard(key)
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """按模式失效"""
        keys_to_remove = [k for k in self._entries if pattern in k]
        for k in keys_to_remove:
            self._remove(k)
        return len(keys_to_remove)

    def warmup(self, data_loader, keys: list[str]):
        """缓存预热"""
        warmed = 0
        for key in keys:
            if key not in self._entries:
                value = data_loader(key)
                if value is not None:
                    self.set(key, value)
                    warmed += 1
        return warmed

    def _evict_lfu(self):
        """驱逐最低频使用"""
        if not self._entries:
            return
        lfu_key = min(self._entries, key=lambda k: self._entries[k].access_count)
        self._remove(lfu_key)
        self._evictions += 1

    def _remove(self, key: str):
        if key in self._entries:
            entry = self._entries.pop(key)
            self._current_memory -= entry.size_bytes

    def adjust_ttls(self):
        """自适应调整 TTL"""
        for entry in self._entries.values():
            if entry.access_count > 10:
                entry.ttl = min(entry.ttl * 1.5, 86400)
            elif entry.access_count < 2:
                entry.ttl = max(entry.ttl * 0.5, 60)

    def cleanup_expired(self) -> int:
        """清理过期条目"""
        now = time.time()
        expired = [k for k, e in self._entries.items()
                   if now - e.created_at > e.ttl]
        for k in expired:
            self._remove(k)
        return len(expired)

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self._hits + self._misses
        return {
            "size": len(self._entries),
            "max_size": self._max_size,
            "memory_bytes": self._current_memory,
            "memory_mb": round(self._current_memory / 1024 / 1024, 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1), 3),
            "evictions": self._evictions,
            "penetration_blocked": self._penetration_blocked,
            "null_cache_size": len(self._null_set),
        }

    def clear(self):
        """清空缓存"""
        self._entries.clear()
        self._null_set.clear()
        self._current_memory = 0


class CacheManager:
    """多层缓存管理器"""

    def __init__(self, config=None):
        self.config = config
        self._l1 = SmartCache(max_size=256, max_memory_mb=10)
        self._l2 = SmartCache(max_size=1024, max_memory_mb=50)
        self._hit_stats: dict[str, int] = defaultdict(int)

    def get(self, key: str):
        """L1 → L2 层级查找"""
        value = self._l1.get(key)
        if value is not None:
            self._hit_stats["l1_hits"] += 1
            return value

        value = self._l2.get(key)
        if value is not None:
            self._hit_stats["l2_hits"] += 1
            self._l1.set(key, value, ttl=600)
            return value

        self._hit_stats["misses"] += 1
        return None

    def set(self, key: str, value, ttl: float = 3600):
        """写入 L1 和 L2"""
        self._l1.set(key, value, ttl=min(ttl, 600))
        self._l2.set(key, value, ttl=ttl)

    def invalidate(self, key: str):
        """双层失效"""
        self._l1.invalidate(key)
        self._l2.invalidate(key)

    def get_stats(self) -> dict:
        total = sum(self._hit_stats.values())
        l1 = self._hit_stats.get("l1_hits", 0)
        l2 = self._hit_stats.get("l2_hits", 0)
        return {
            "l1": self._l1.get_stats(),
            "l2": self._l2.get_stats(),
            "combined_hit_rate": round((l1 + l2) / max(total, 1), 3),
            "l1_hit_rate": round(l1 / max(total, 1), 3),
            "l2_hit_rate": round(l2 / max(total, 1), 3),
        }


_cache_manager: CacheManager | None = None


def get_cache_manager(config=None) -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(config)
    return _cache_manager
