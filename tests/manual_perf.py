"""盘古性能基准 — ONNX 嵌入 / SQLite 缓存 / 记忆读写（修正 API 签名）"""

import json
import os
import pathlib
import tempfile
import time

os.environ.setdefault("PANGU_DATA_DIR", "/home/xiaoxin/pangu/.test_data")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

results = {"env": {}, "sections": {}}
import multiprocessing
import platform
import sys

results["env"] = {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "machine": platform.machine(),
    "cpu_count": multiprocessing.cpu_count(),
}

# ── 1. ONNX 嵌入器 ──
print("== ONNX Embedder ==")
try:
    from pangu.memory.onnx_embedder import get_onnx_embedder

    emb = get_onnx_embedder()
    _ = emb.embed("warmup text for jit")
    samples = [
        "盘古是专业的记忆系统",
        "Python 异步编程指南",
        "Kubernetes 集群部署",
        "深度学习与自然语言处理",
        "RESTful API 设计原则",
    ]
    n_iters = 30
    start = time.perf_counter()
    for _ in range(n_iters):
        for s in samples:
            emb.embed(s)
    elapsed = time.perf_counter() - start
    n_total = n_iters * len(samples)
    stats = emb.get_stats()
    results["sections"]["onnx"] = {
        "n_total": n_total,
        "elapsed_s": round(elapsed, 3),
        "ms_per_text": round(1000 * elapsed / n_total, 3),
        "reported_avg_ms": round(stats.get("avg_infer_ms", -1), 3),
        "model_loaded": stats.get("model_loaded"),
    }
    print(
        f"  text={n_total}, mean_ms={results['sections']['onnx']['ms_per_text']}, reported_avg={stats.get('avg_infer_ms')}"
    )
    start = time.perf_counter()
    vecs = emb.embed_batch(samples * 4)
    elapsed_b = time.perf_counter() - start
    results["sections"]["onnx_batch"] = {
        "n_texts": len(samples * 4),
        "elapsed_s": round(elapsed_b, 3),
        "ms_per_text": round(1000 * elapsed_b / len(samples * 4), 3),
        "dim": len(vecs[0]) if vecs else 0,
    }
    print(
        f"  batch n={len(samples * 4)}, ms/text={results['sections']['onnx_batch']['ms_per_text']}, dim={len(vecs[0])}"
    )
except Exception as e:
    import traceback

    traceback.print_exc()
    results["sections"]["onnx"] = {"error": f"{type(e).__name__}: {e}"}

# ── 2. SQLite 持久化缓存 ──
print("== SQLite Persistent Cache ==")
try:
    from pangu.core.cache import PersistentCache
    from pangu.core.llm import LLMResponse

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "cache.db")
        cache = PersistentCache(db_path=db, max_disk_mb=50.0, write_throttle=1)
        n_writes = 200
        start = time.perf_counter()
        for i in range(n_writes):
            cache.put(f"key_{i:04d}", "mock", "mock", {"i": i}, LLMResponse(content=f"v{i}", model="m", provider="p"))
        write_t = time.perf_counter() - start
        start = time.perf_counter()
        hits = 0
        for i in range(n_writes):
            v = cache.get(f"key_{i:04d}")
            if v:
                hits += 1
        read_t = time.perf_counter() - start
        stats = cache.get_stats()
        cache.close()
        results["sections"]["sqlite_cache"] = {
            "n_writes": n_writes,
            "write_s": round(write_t, 3),
            "write_us_each": round(1e6 * write_t / n_writes, 1),
            "n_reads": n_writes,
            "read_s": round(read_t, 3),
            "read_us_each": round(1e6 * read_t / n_writes, 1),
            "hits": hits,
            "hit_rate": round(hits / n_writes, 4),
            "total_entries": stats.get("total_entries"),
        }
        print(
            f"  write_us={results['sections']['sqlite_cache']['write_us_each']}, "
            f"read_us={results['sections']['sqlite_cache']['read_us_each']}, entries={stats.get('total_entries')}"
        )
except Exception as e:
    import traceback

    traceback.print_exc()
    results["sections"]["sqlite_cache"] = {"error": f"{type(e).__name__}: {e}"}

# ── 3. MemoryStack 读写 ──
print("== MemoryStack Read/Write ==")
try:
    from pangu.core.config import PanguConfig
    from pangu.memory.layers import MemoryStack

    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td)
        cfg.palace_path = str(pathlib.Path(td) / "palace.json")
        cfg.db_path = pathlib.Path(td)
        cfg.ensure_dirs()
        stk = MemoryStack(cfg)
        from pangu.core.palace import Drawer

        n_drawers = 100
        start = time.perf_counter()
        for i in range(n_drawers):
            stk.add_drawer(Drawer(id=f"d{i}", content=f"content {i} " * 5, importance=3.0))
        w_t = time.perf_counter() - start
        start = time.perf_counter()
        ds = stk.get_drawers()
        l_t = time.perf_counter() - start
        results["sections"]["memory_stack"] = {
            "n_writes": n_drawers,
            "write_s": round(w_t, 3),
            "write_ms_each": round(1000 * w_t / n_drawers, 3),
            "list_s": round(l_t, 3),
            "list_count": len(ds),
        }
        print(f"  write_ms={results['sections']['memory_stack']['write_ms_each']}, list={len(ds)}")
except Exception as e:
    import traceback

    traceback.print_exc()
    results["sections"]["memory_stack"] = {"error": f"{type(e).__name__}: {e}"}

# ── 4. 并发读取 ──
print("== Concurrent reads ==")
try:
    import threading

    from pangu.core.cache import PersistentCache
    from pangu.core.llm import LLMResponse

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "cache.db")
        cache = PersistentCache(db_path=db, max_disk_mb=50.0, write_throttle=1)
        for i in range(100):
            cache.put(f"k{i}", "p", "m", {}, LLMResponse(content=f"v{i}", model="m", provider="p"))
        n_threads = 4
        n_per_thread = 200
        timings = []
        errors = []

        def worker():
            try:
                t = time.perf_counter()
                for i in range(n_per_thread):
                    cache.get(f"k{i % 100}")
                timings.append(time.perf_counter() - t)
            except Exception as e:
                errors.append(str(e))

        ts = [threading.Thread(target=worker) for _ in range(n_threads)]
        t0 = time.perf_counter()
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        total_t = time.perf_counter() - t0
        cache.close()
        results["sections"]["concurrency"] = {
            "n_threads": n_threads,
            "n_per_thread": n_per_thread,
            "total_s": round(total_t, 3),
            "ops_per_s": round(n_threads * n_per_thread / total_t, 1),
            "errors": len(errors),
        }
        print(
            f"  threads={n_threads}, ops={n_threads * n_per_thread}, "
            f"total_s={total_t:.2f}, ops/s={results['sections']['concurrency']['ops_per_s']}"
        )
except Exception as e:
    import traceback

    traceback.print_exc()
    results["sections"]["concurrency"] = {"error": f"{type(e).__name__}: {e}"}

# ── 5. 导入/导出 ──
print("== Import/Export ==")
try:
    from pangu.core.config import PanguConfig
    from pangu.memory.migration import MemoryExporter, MemoryImporter

    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td) / "src"
        cfg.palace_path = str(pathlib.Path(td) / "src" / "palace.json")
        cfg.db_path = pathlib.Path(td) / "src"
        cfg.ensure_dirs()
        from pangu.memory.layers import MemoryStack

        stk = MemoryStack(cfg)
        from pangu.core.palace import Drawer

        for i in range(50):
            stk.add_drawer(Drawer(id=f"x{i}", content=f"c{i} " * 8, importance=3.0))
        out = os.path.join(td, "export.json")
        t0 = time.perf_counter()
        rpath = MemoryExporter(cfg).export_all(out, format="json")
        export_t = time.perf_counter() - t0
        size = os.path.getsize(rpath)
        cfg2 = PanguConfig()
        cfg2.base_dir = pathlib.Path(td) / "dst"
        cfg2.palace_path = str(pathlib.Path(td) / "dst" / "palace.json")
        cfg2.db_path = pathlib.Path(td) / "dst"
        cfg2.ensure_dirs()
        t0 = time.perf_counter()
        MemoryImporter(cfg2).import_from_file(rpath, merge=True)
        import_t = time.perf_counter() - t0
        results["sections"]["io"] = {
            "export_s": round(export_t, 3),
            "import_s": round(import_t, 3),
            "size_bytes": size,
        }
        print(f"  export_s={export_t:.3f}, import_s={import_t:.3f}, size={size}")
except Exception as e:
    import traceback

    traceback.print_exc()
    results["sections"]["io"] = {"error": f"{type(e).__name__}: {e}"}

# 写报告
out = pathlib.Path("/home/xiaoxin/pangu/reports/perf.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(f"\nsaved {out}")
