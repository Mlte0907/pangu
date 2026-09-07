#!/usr/bin/env python3
"""盘古 Benchmark — 性能基准测试 + 竞品对比"""
import json
import sys
import time
from pathlib import Path
from pangu.core.config import PanguConfig
from pangu.core.palace import Palace, Drawer


def run_benchmark():
    config = PanguConfig.load()
    palace = Palace(config.palace_path)
    drawers_file = palace.drawers_file if hasattr(palace, 'drawers_file') else Path(config.palace_path) / "drawers.json"
    if drawers_file.exists():
        with open(drawers_file) as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]
    else:
        drawers = []

    print(f"盘古 v3.6.0 Benchmark")
    print(f"{'='*50}")
    print(f"记忆数: {len(drawers)}")

    # 1. 写入性能
    print(f"\n【写入性能】")
    from pangu.memory.ingestion import remember
    times = []
    for i in range(10):
        t0 = time.time()
        remember(raw_text=f"benchmark test memory {i}", wing="benchmark", tags=["test"])
        times.append((time.time() - t0) * 1000)
    avg = sum(times) / len(times)
    print(f"  10次写入平均: {avg:.1f}ms")
    print(f"  P50: {sorted(times)[5]:.1f}ms  P95: {sorted(times)[8]:.1f}ms  P99: {sorted(times)[9]:.1f}ms")

    # 2. 搜索性能
    print(f"\n【搜索性能】")
    from pangu.memory.hybrid_search import hybrid_search
    times = []
    for i in range(10):
        t0 = time.time()
        hybrid_search("Python", drawers, limit=10)
        times.append((time.time() - t0) * 1000)
    avg = sum(times) / len(times)
    print(f"  10次搜索平均: {avg:.1f}ms")
    print(f"  P50: {sorted(times)[5]:.1f}ms  P95: {sorted(times)[8]:.1f}ms")

    # 3. 嵌入性能
    print(f"\n【嵌入性能】")
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        if onnx.is_available:
            times = []
            for i in range(50):
                t0 = time.time()
                onnx.embed(f"benchmark test {i}")
                times.append((time.time() - t0) * 1000)
            avg = sum(times) / len(times)
            print(f"  50次嵌入平均: {avg:.2f}ms")
            print(f"  P50: {sorted(times)[25]:.2f}ms  P95: {sorted(times)[47]:.2f}ms")
        else:
            print("  ONNX 不可用")
    except Exception as e:
        print(f"  嵌入测试失败: {e}")

    # 4. 向量搜索性能
    print(f"\n【向量搜索性能】")
    from pangu.memory.vector_index import get_vector_index
    vi = get_vector_index()
    if vi.is_built:
        try:
            from pangu.memory.onnx_embedder import get_onnx_embedder
            onnx = get_onnx_embedder()
            if onnx.is_available:
                qvec = onnx.embed("Python optimization")
                times = []
                for _ in range(20):
                    t0 = time.time()
                    vi.search(qvec, k=10)
                    times.append((time.time() - t0) * 1000)
                avg = sum(times) / len(times)
                print(f"  20次向量搜索平均: {avg:.2f}ms")
                print(f"  P50: {sorted(times)[10]:.2f}ms")
        except Exception as e:
            print(f"  测试失败: {e}")

    # 5. MCP工具延迟
    print(f"\n【MCP工具延迟】")
    import httpx
    try:
        client = httpx.Client(verify=False)
        r = client.post("http://127.0.0.1:19529/api/v2/auth/login", json={"username":"admin","password":"pangu-admin-2026"})
        token = r.json()["data"]["access_token"]
        hdr = {"Content-Type":"application/json","Authorization":f"Bearer {token}"}

        tools = [
            ("pangu_stats", {}),
            ("pangu_wm_stats", {}),
            ("pangu_health_check", {}),
            ("pangu_autonomous_status", {}),
            ("pangu_error_stats", {}),
        ]
        for name, args in tools:
            t0 = time.time()
            client.post("http://127.0.0.1:19529/mcp", headers=hdr,
                json={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}, timeout=10)
            ms = (time.time() - t0) * 1000
            print(f"  {name}: {ms:.0f}ms")
    except Exception as e:
        print(f"  MCP测试失败: {e}")

    print(f"\n{'='*50}")
    print("Benchmark 完成")


if __name__ == "__main__":
    run_benchmark()
