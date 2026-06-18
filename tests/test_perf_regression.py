"""盘古性能回归检测 — 自动对比基准，检测性能退化"""
import json
import time
import statistics
from datetime import datetime
from pathlib import Path

from pangu.memory.layers import MemoryStack
from pangu.memory.retrieval import recall
from pangu.memory.onnx_embedder import ONNXEmbedder
from pangu.core.config import PanguConfig


class PerformanceRegression:
    """性能回归检测"""

    def __init__(self, baseline_file: str = None):
        self.config = PanguConfig.load()
        self.baseline_file = Path(baseline_file or Path.home() / ".pangu" / "perf_baseline.json")

    def run_benchmark(self, iterations: int = 100) -> dict:
        """运行基准测试"""
        stack = MemoryStack(self.config)
        drawers = stack.get_drawers()
        embedder = ONNXEmbedder()

        results = {}

        # 1. 搜索延迟
        search_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            recall("test", limit=5, drawers=drawers)
            search_times.append((time.perf_counter() - t0) * 1000)
        results["search_median_ms"] = round(statistics.median(search_times), 2)
        results["search_p95_ms"] = round(sorted(search_times)[int(len(search_times) * 0.95)], 2)

        # 2. 嵌入延迟
        embed_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            embedder.embed("test embedding")
            embed_times.append((time.perf_counter() - t0) * 1000)
        results["embed_median_ms"] = round(statistics.median(embed_times), 2)

        # 3. 写入延迟（模拟）
        write_times = []
        for _ in range(10):
            t0 = time.perf_counter()
            stack.get_drawers()
            write_times.append((time.perf_counter() - t0) * 1000)
        results["read_median_ms"] = round(statistics.median(write_times), 2)

        # 4. 记忆数
        results["memory_count"] = len(drawers)

        return results

    def save_baseline(self, results: dict) -> None:
        """保存基准"""
        self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
        results["timestamp"] = time.time()
        self.baseline_file.write_text(json.dumps(results, indent=2))

    def load_baseline(self) -> dict | None:
        """加载基准"""
        if self.baseline_file.exists():
            return json.loads(self.baseline_file.read_text())
        return None

    def detect_regression(self, current: dict, baseline: dict = None, threshold: float = 0.2) -> dict:
        """检测回归"""
        if baseline is None:
            baseline = self.load_baseline()
        if not baseline:
            return {"status": "no_baseline", "current": current}

        regressions = []
        improvements = []

        for key in current:
            if key == "timestamp" or key not in baseline:
                continue
            if not isinstance(current[key], (int, float)):
                continue
            if not isinstance(baseline[key], (int, float)):
                continue

            current_val = current[key]
            baseline_val = baseline[key]
            if baseline_val == 0:
                continue

            change = (current_val - baseline_val) / baseline_val

            if change > threshold:
                regressions.append({
                    "metric": key,
                    "baseline": baseline_val,
                    "current": current_val,
                    "change": f"+{change:.1%}",
                })
            elif change < -threshold:
                improvements.append({
                    "metric": key,
                    "baseline": baseline_val,
                    "current": current_val,
                    "change": f"{change:.1%}",
                })

        return {
            "status": "regression" if regressions else ("improvement" if improvements else "stable"),
            "regressions": regressions,
            "improvements": improvements,
            "current": current,
        }

    def generate_report(self, regression: dict) -> str:
        """生成报告"""
        lines = ["=== 性能回归检测报告 ===\n"]
        lines.append(f"状态: {regression['status']}")
        lines.append(f"时间: {datetime.now().isoformat()}\n")

        if regression["regressions"]:
            lines.append("⚠️ 性能退化:")
            for r in regression["regressions"]:
                lines.append(f"  {r['metric']}: {r['baseline']:.2f} → {r['current']:.2f} ({r['change']})")

        if regression["improvements"]:
            lines.append("✅ 性能提升:")
            for r in regression["improvements"]:
                lines.append(f"  {r['metric']}: {r['baseline']:.2f} → {r['current']:.2f} ({r['change']})")

        if not regression["regressions"] and not regression["improvements"]:
            lines.append("✅ 性能稳定，无回归")

        return "\n".join(lines)


def main():
    """命令行入口"""
    import sys

    pr = PerformanceRegression()

    if len(sys.argv) > 1 and sys.argv[1] == "save":
        print("运行基准测试...")
        results = pr.run_benchmark()
        pr.save_baseline(results)
        print(f"基准已保存: {pr.baseline_file}")
        print(json.dumps(results, indent=2))
    else:
        current = pr.run_benchmark()
        regression = pr.detect_regression(current)
        report = pr.generate_report(regression)
        print(report)


if __name__ == "__main__":
    main()
