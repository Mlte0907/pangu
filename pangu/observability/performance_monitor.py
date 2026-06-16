"""盘古性能基准监控 — 持续监控性能变化"""

import time
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    timestamp: str
    total_memories: int
    vector_count: int
    embed_latency_ms: float
    search_latency_ms: float
    hybrid_latency_ms: float
    token_count: int
    token_per_memory: int


class PerformanceMonitor:
    """性能基准监控"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._history: list[BenchmarkResult] = []

    def run_benchmark(self) -> BenchmarkResult:
        """运行性能基准测试"""
        from ..memory.layers import MemoryStack, _estimate_tokens
        from ..memory.retrieval import recall, clear_recall_cache
        from ..memory.hybrid_search import hybrid_search
        from ..memory.vector_index import get_vector_index

        stack = MemoryStack(config=self.config)
        drawers = stack.get_drawers()

        # 向量索引状态
        idx = get_vector_index()
        vector_count = idx.size

        # ONNX 嵌入延迟
        from ..memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        t0 = time.perf_counter()
        onnx.embed("benchmark test")
        embed_latency = (time.perf_counter() - t0) * 1000

        # recall() 搜索延迟
        times = []
        for _ in range(5):
            clear_recall_cache()
            t0 = time.perf_counter()
            recall(query="Python", limit=5, drawers=drawers)
            times.append((time.perf_counter() - t0) * 1000)
        search_latency = statistics.median(times)

        # hybrid_search 延迟
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            hybrid_search("Python", drawers, config=self.config, limit=5)
            times.append((time.perf_counter() - t0) * 1000)
        hybrid_latency = statistics.median(times)

        # Token 统计
        total_tokens = sum(_estimate_tokens(d.content) for d in drawers)
        token_per_memory = total_tokens // max(len(drawers), 1)

        result = BenchmarkResult(
            timestamp=datetime.now().isoformat(),
            total_memories=len(drawers),
            vector_count=vector_count,
            embed_latency_ms=round(embed_latency, 2),
            search_latency_ms=round(search_latency, 2),
            hybrid_latency_ms=round(hybrid_latency, 2),
            token_count=total_tokens,
            token_per_memory=token_per_memory,
        )

        self._history.append(result)
        return result

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取历史基准结果"""
        return [
            {
                "timestamp": r.timestamp,
                "total_memories": r.total_memories,
                "vector_count": r.vector_count,
                "embed_latency_ms": r.embed_latency_ms,
                "search_latency_ms": r.search_latency_ms,
                "hybrid_latency_ms": r.hybrid_latency_ms,
                "token_count": r.token_count,
                "token_per_memory": r.token_per_memory,
            }
            for r in self._history[-limit:]
        ]

    def get_summary(self) -> dict:
        """获取性能摘要"""
        if not self._history:
            return {"status": "no_data"}

        latest = self._history[-1]
        return {
            "total_memories": latest.total_memories,
            "vector_count": latest.vector_count,
            "embed_latency_ms": latest.embed_latency_ms,
            "search_latency_ms": latest.search_latency_ms,
            "hybrid_latency_ms": latest.hybrid_latency_ms,
            "token_count": latest.token_count,
            "token_per_memory": latest.token_per_memory,
        }
