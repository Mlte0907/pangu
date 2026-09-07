"""盘古搜索缓存 — 相同查询 5 分钟内直接返回缓存结果

核心能力：
1. 内存缓存：LRU + TTL 过期
2. 命中率统计：追踪缓存命中/未命中
3. 自动失效：5 分钟后自动清除
4. 可配置：TTL 和缓存大小可调
"""

import hashlib
import logging
import time
from collections import OrderedDict

logger = logging.getLogger("pangu.memory.search_cache")


class SearchCache:
    """搜索结果缓存"""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 200):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._stats = {"hits": 0, "misses": 0}

    def _make_key(self, query: str, modalities: list = None, limit: int = 10) -> str:
        raw = f"{query}|{sorted(modalities or [])}|{limit}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, query: str, modalities: list = None, limit: int = 10) -> dict | None:
        """获取缓存"""
        key = self._make_key(query, modalities, limit)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["time"] < self._ttl:
                self._cache.move_to_end(key)
                self._stats["hits"] += 1
                return entry["data"]
            else:
                del self._cache[key]
        self._stats["misses"] += 1
        return None

    def set(self, query: str, data: dict, modalities: list = None, limit: int = 10):
        """设置缓存"""
        key = self._make_key(query, modalities, limit)
        self._cache[key] = {"data": data, "time": time.time()}
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0}

    def get_stats(self) -> dict:
        """缓存统计"""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": round(self._stats["hits"] / total, 3) if total > 0 else 0,
        }


_cache: SearchCache | None = None


def get_search_cache() -> SearchCache:
    global _cache
    if _cache is None:
        _cache = SearchCache()
    return _cache
