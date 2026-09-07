"""盘古性能基准测试 — 延迟/吞吐量/并发/内存"""

import concurrent.futures
import statistics
import time

from pangu.core.config import PanguConfig
from pangu.memory.ingestion import remember
from pangu.memory.layers import MemoryStack
from pangu.memory.retrieval import recall


class Benchmark:
    """性能基准"""

    def __init__(self):
        self.config = PanguConfig.load()
        self.stack = MemoryStack(self.config)
        self.drawers = self.stack.get_drawers()
        self.results = {}

    def run_all(self):
        print("=" * 70)
        print("  盘古 v3.0 性能基准测试")
        print("=" * 70)

        self.benchmark_read()
        self.benchmark_search()
        self.benchmark_write()
        self.benchmark_embedding()
        self.benchmark_concurrent_search()
        self.benchmark_memory_overhead()
        self.benchmark_large_batch_search()

        self.print_summary()

    def _time_it(self, func, iterations=100):
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            func()
            times.append((time.perf_counter() - t0) * 1000)
        return {
            "median": round(statistics.median(times), 2),
            "p95": round(sorted(times)[int(len(times) * 0.95)], 2),
            "p99": round(sorted(times)[int(len(times) * 0.99)], 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
            "avg": round(statistics.mean(times), 2),
        }

    def benchmark_read(self):
        print("\n[1] 记忆读取性能")
        stats = self._time_it(lambda: self.stack.get_drawers(), iterations=50)
        self.results["read"] = stats
        print(f"   读取 {len(self.drawers)} 条记忆:")
        print(f"   median={stats['median']}ms, p95={stats['p95']}ms, p99={stats['p99']}ms")

    def benchmark_search(self):
        print("\n[2] 搜索性能")
        queries = ["Python", "ONNX", "记忆系统", "性能优化", "向量索引"]
        query_stats = []
        for q in queries:
            stats = self._time_it(lambda q=q: recall(q, limit=5, drawers=self.drawers), iterations=50)
            query_stats.append(stats)

        avg_median = statistics.mean([s["median"] for s in query_stats])
        avg_p95 = statistics.mean([s["p95"] for s in query_stats])
        self.results["search"] = {
            "avg_median": round(avg_median, 2),
            "avg_p95": round(avg_p95, 2),
            "queries": len(queries),
        }
        print(f"   {len(queries)} 个查询, 每个 50 次迭代:")
        print(f"   avg median={avg_median:.2f}ms, avg p95={avg_p95:.2f}ms")

    def benchmark_write(self):
        print("\n[3] 写入性能")
        write_times = []
        for i in range(20):
            t0 = time.perf_counter()
            item_id, drawer = remember(
                raw_text=f"性能测试记忆 #{i} — benchmark test memory",
                wing="benchmark",
                tags=["benchmark", "test"],
                importance=0.5,
                existing_drawers=self.drawers,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            write_times.append(elapsed)
            self.stack.add_drawer(drawer)

        avg = statistics.mean(write_times)
        self.results["write"] = {"avg_ms": round(avg, 2), "count": len(write_times)}
        print(f"   写入 {len(write_times)} 条:")
        print(f"   avg={avg:.2f}ms, median={statistics.median(write_times):.2f}ms")

        # 清理
        self.stack._drawers = [d for d in self.stack.get_drawers() if d.wing != "benchmark"]
        self.stack._save_drawers()

    def benchmark_embedding(self):
        print("\n[4] 嵌入性能")
        from pangu.memory.onnx_embedder import ONNXEmbedder

        embedder = ONNXEmbedder()
        texts = ["Python编程", "ONNX推理优化", "向量索引搜索", "记忆系统架构", "性能测试"]

        embed_times = []
        for text in texts:
            for _ in range(20):
                t0 = time.perf_counter()
                vec = embedder.embed(text)
                elapsed = (time.perf_counter() - t0) * 1000
                embed_times.append(elapsed)

        avg = statistics.mean(embed_times)
        self.results["embedding"] = {"avg_ms": round(avg, 2), "dim": len(vec) if vec else 0}
        print(f"   嵌入 {len(texts)} 个文本, 每个 20 次:")
        print(f"   avg={avg:.2f}ms, dim={len(vec)}")

    def benchmark_concurrent_search(self):
        print("\n[5] 并发搜索性能")
        queries = ["Python", "ONNX", "记忆", "向量", "优化", "搜索", "嵌入", "索引"]

        def search_task(q):
            t0 = time.perf_counter()
            recall(q, limit=3, drawers=self.drawers)
            return (time.perf_counter() - t0) * 1000

        # 串行
        serial_times = [search_task(q) for q in queries]

        # 并发
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            t0 = time.perf_counter()
            list(executor.map(search_task, queries))
            concurrent_total = (time.perf_counter() - t0) * 1000

        serial_total = sum(serial_times)
        speedup = serial_total / max(concurrent_total, 0.01)

        self.results["concurrent"] = {
            "serial_total_ms": round(serial_total, 2),
            "concurrent_total_ms": round(concurrent_total, 2),
            "speedup": round(speedup, 2),
        }
        print(f"   {len(queries)} 个查询:")
        print(f"   串行: {serial_total:.2f}ms")
        print(f"   并发(4线程): {concurrent_total:.2f}ms")
        print(f"   加速比: {speedup:.2f}x")

    def benchmark_memory_overhead(self):
        print("\n[6] 内存开销")
        import sys

        stack_size = sys.getsizeof(self.drawers)
        drawer_sample = self.drawers[0] if self.drawers else None
        drawer_size = sys.getsizeof(drawer_sample) if drawer_sample else 0

        self.results["memory"] = {
            "drawers_list_bytes": stack_size,
            "avg_drawer_bytes": drawer_size,
            "total_drawers": len(self.drawers),
        }
        print(f"   记忆列表: {stack_size:,} bytes")
        print(f"   单条记忆: ~{drawer_size:,} bytes")
        print(f"   总记忆数: {len(self.drawers)}")

    def benchmark_large_batch_search(self):
        print("\n[7] 大批量搜索性能")
        queries = [f"test_query_{i}" for i in range(100)]

        t0 = time.perf_counter()
        for q in queries:
            recall(q, limit=3, drawers=self.drawers)
        elapsed = (time.perf_counter() - t0) * 1000

        self.results["batch_search"] = {
            "queries": len(queries),
            "total_ms": round(elapsed, 2),
            "avg_per_query_ms": round(elapsed / len(queries), 2),
            "qps": round(len(queries) / (elapsed / 1000), 1),
        }
        print(f"   {len(queries)} 个查询:")
        print(f"   总耗时: {elapsed:.2f}ms")
        print(f"   平均: {elapsed / len(queries):.2f}ms/query")
        print(f"   QPS: {len(queries) / (elapsed / 1000):.1f}")

    def print_summary(self):
        print("\n" + "=" * 70)
        print("  性能基准总结")
        print("=" * 70)
        print(f"  记忆数: {len(self.drawers)}")
        print(f"  读取: {self.results.get('read', {}).get('median', '?')}ms median")
        print(f"  搜索: {self.results.get('search', {}).get('avg_median', '?')}ms avg median")
        print(f"  写入: {self.results.get('write', {}).get('avg_ms', '?')}ms avg")
        print(f"  嵌入: {self.results.get('embedding', {}).get('avg_ms', '?')}ms avg")
        print(f"  并发加速: {self.results.get('concurrent', {}).get('speedup', '?')}x")
        print(f"  批量QPS: {self.results.get('batch_search', {}).get('qps', '?')}")
        print(f"  单条记忆: ~{self.results.get('memory', {}).get('avg_drawer_bytes', '?')} bytes")
        print("=" * 70)


if __name__ == "__main__":
    bench = Benchmark()
    bench.run_all()
