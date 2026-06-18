"""盘古搜索模式分析 — 跟踪搜索行为，提供优化建议"""
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pangu.core.config import PanguConfig


class SearchAnalytics:
    """搜索分析引擎"""

    def __init__(self, config=None):
        self.config = config or PanguConfig.load()
        self._log_file = Path.home() / ".pangu" / "search_analytics.json"
        self._queries: list[dict] = []
        self._load()

    def _load(self):
        if self._log_file.exists():
            try:
                self._queries = json.loads(self._log_file.read_text())
            except Exception:
                self._queries = []

    def _save(self):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log_file.write_text(json.dumps(self._queries[-1000:], ensure_ascii=False))

    def log_search(self, query: str, result_count: int, duration_ms: float,
                   user_id: str = "default") -> None:
        """记录搜索行为"""
        self._queries.append({
            "query": query,
            "result_count": result_count,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._queries) > 1000:
            self._queries = self._queries[-1000:]
        self._save()

    def get_top_queries(self, top_k: int = 10) -> list[dict]:
        """获取热门查询"""
        counts = defaultdict(int)
        for q in self._queries:
            counts[q["query"]] += 1
        sorted_q = sorted(counts.items(), key=lambda x: -x[1])
        return [{"query": q, "count": c} for q, c in sorted_q[:top_k]]

    def get_empty_searches(self) -> list[dict]:
        """获取无结果的搜索"""
        return [q for q in self._queries if q["result_count"] == 0][-20:]

    def get_slow_searches(self, threshold_ms: float = 1000) -> list[dict]:
        """获取慢搜索"""
        return [q for q in self._queries if q["duration_ms"] > threshold_ms][-20:]

    def get_hourly_distribution(self) -> dict:
        """获取每小时搜索分布"""
        hourly = defaultdict(int)
        for q in self._queries:
            try:
                dt = datetime.fromisoformat(q["timestamp"])
                hourly[dt.hour] += 1
            except Exception:
                pass
        return dict(sorted(hourly.items()))

    def get_summary(self) -> dict:
        """获取搜索分析摘要"""
        if not self._queries:
            return {"total_searches": 0}

        durations = [q["duration_ms"] for q in self._queries]
        result_counts = [q["result_count"] for q in self._queries]

        return {
            "total_searches": len(self._queries),
            "avg_duration_ms": round(statistics.mean(durations), 2) if durations else 0,
            "avg_results": round(statistics.mean(result_counts), 1) if result_counts else 0,
            "empty_search_rate": round(sum(1 for r in result_counts if r == 0) / max(len(result_counts), 1), 3),
            "top_queries": self.get_top_queries(5),
            "unique_queries": len(set(q["query"] for q in self._queries)),
        }


import statistics

_analytics: SearchAnalytics | None = None


def get_search_analytics(config=None) -> SearchAnalytics:
    global _analytics
    if _analytics is None:
        _analytics = SearchAnalytics(config)
    return _analytics
