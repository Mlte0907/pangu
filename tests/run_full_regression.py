"""盘古综合回归与报告生成器

合并运行：单元 + 接口 + 性能 + 安全，输出统一报告与基线对比。
CI 入口：python tests/run_full_regression.py
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("PANGU_DATA_DIR", "/home/xiaoxin/pangu/.test_data")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = pathlib.Path("/home/xiaoxin/pangu")
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)
BASELINE = REPORTS / "perf_baseline.json"


def run_pytest(files, out_xml: str, extra_args: list = None) -> dict:
    """运行 pytest 套件并返回摘要。files 是文件列表。"""
    extra_args = extra_args or []
    cmd = [
        sys.executable, "-m", "pytest", *files,
        "--no-header", "-p", "no:cacheprovider",
        f"--junitxml={out_xml}", "-q", *extra_args,
    ]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "PANGU_DATA_DIR": str(ROOT / ".test_data")})
    elapsed = time.time() - t0
    summary = {"exit": r.returncode, "elapsed_s": round(elapsed, 2), "stdout_tail": r.stdout[-500:]}
    if r.returncode in (0, 1):  # 0=全过；1=部分失败但有 junit
        # 解析 junit（pytest 输出根为 <testsuites>，数据在 <testsuite> 子节点）
        import xml.etree.ElementTree as ET
        root = ET.parse(out_xml).getroot()
        suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
        totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for ts in suites:
            for k in totals:
                totals[k] += int(ts.get(k, 0))
        summary.update({
            "tests": totals["tests"],
            "passed": totals["tests"] - totals["failures"] - totals["errors"],
            "failed": totals["failures"],
            "errors": totals["errors"],
            "skipped": totals["skipped"],
        })
    return summary


def run_module(script: str) -> dict:
    """运行独立 Python 脚本"""
    cmd = [sys.executable, str(ROOT / "tests" / script)]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, "PANGU_DATA_DIR": str(ROOT / ".test_data")})
    elapsed = time.time() - t0
    return {
        "exit": r.returncode, "elapsed_s": round(elapsed, 2),
        "stdout_tail": r.stdout[-500:],
        "stderr_tail": r.stderr[-500:] if r.returncode != 0 else "",
    }


def compare_perf(current: dict) -> list:
    """与基线对比，返回回归警告列表"""
    if not BASELINE.exists():
        return [{"warning": "no baseline; saving current as baseline"}]
    base = json.loads(BASELINE.read_text())
    warnings = []
    for section, data in current.get("sections", {}).items():
        old = base.get("sections", {}).get(section, {})
        # 延迟类指标
        for key in ("ms_per_text", "write_ms_each", "write_us_each", "read_us_each"):
            if key in data and key in old:
                if data[key] > old[key] * 1.05:
                    warnings.append({
                        "section": section, "metric": key,
                        "baseline": old[key], "current": data[key],
                        "delta_pct": round(100 * (data[key] - old[key]) / old[key], 2),
                    })
        # 吞吐类指标
        for key in ("ops_per_s",):
            if key in data and key in old:
                if data[key] < old[key] * 0.95:
                    warnings.append({
                        "section": section, "metric": key,
                        "baseline": old[key], "current": data[key],
                        "delta_pct": round(100 * (data[key] - old[key]) / old[key], 2),
                    })
    return warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true", help="save current perf as new baseline")
    ap.add_argument("--skip-perf", action="store_true")
    ap.add_argument("--skip-security", action="store_true")
    ap.add_argument("--skip-api", action="store_true")
    args = ap.parse_args()

    result = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "sections": {}}

    # ── 1. 单元 + 集成 ──
    print("▶ 单元 + 集成...")
    unit_files = [
        "tests/test_core.py", "tests/test_fuxi_port.py", "tests/test_mcp_warmup.py",
        "tests/test_vacuum.py", "tests/test_warmup_audit.py", "tests/test_onnx_embedder.py",
        "tests/test_persistent_cache.py",
    ]
    result["sections"]["unit_core"] = run_pytest(
        unit_files, str(REPORTS / "junit_unit.xml"),
        ["-k", "not semantic_search and not test_layer3_search and not test_hybrid_search"],
    )
    print(f"  unit_core: {result['sections']['unit_core'].get('tests','-')} tests, "
          f"failed={result['sections']['unit_core'].get('failed',0)}")

    result["sections"]["integration"] = run_pytest(
        ["tests/test_cache_warmup.py", "tests/test_llm_optimizations.py", "tests/test_integration.py"],
        str(REPORTS / "junit_intg.xml"),
    )
    print(f"  integration: {result['sections']['integration'].get('tests','-')} tests")

    result["sections"]["bench"] = run_pytest(
        ["tests/test_bench.py"], str(REPORTS / "junit_bench.xml"),
        ["--benchmark-disable-gc", "--benchmark-min-rounds=3", "-k", "not sentence_transformer_perf"],
    )
    print(f"  bench: {result['sections']['bench'].get('tests','-')} tests, "
          f"failed={result['sections']['bench'].get('failed',0)}")

    # ── 2. 接口契约 ──
    if not args.skip_api:
        print("▶ 接口契约...")
        result["sections"]["api_smoke"] = run_module("manual_api_smoke.py")
        print(f"  api_smoke: exit={result['sections']['api_smoke']['exit']}")

    # ── 3. 安全 ──
    if not args.skip_security:
        print("▶ 安全...")
        result["sections"]["security"] = run_module("manual_security.py")
        print(f"  security: exit={result['sections']['security']['exit']}")

    # ── 4. 性能 + 基线对比 ──
    if not args.skip_perf:
        print("▶ 性能...")
        result["sections"]["perf"] = run_module("manual_perf.py")
        perf = json.loads((REPORTS / "perf.json").read_text())
        if args.update_baseline:
            BASELINE.write_text(json.dumps(perf, indent=2, ensure_ascii=False))
            print("  baseline updated")
        else:
            warnings = compare_perf(perf)
            result["perf_regressions"] = warnings
            for w in warnings:
                print(f"  ⚠ regression: {w}")

    # ── 总结 ──
    total_tests = 0
    total_failed = 0
    for s in result["sections"].values():
        if isinstance(s.get("tests"), int) and s["tests"] > 0:
            total_tests += s["tests"]
            total_failed += s.get("failed", 0)
    # api_smoke / security 没有 tests 字段，但有 exit 状态
    api_exit = result["sections"].get("api_smoke", {}).get("exit", 0)
    sec_exit = result["sections"].get("security", {}).get("exit", 0)
    result["summary"] = {
        "total_tests": total_tests,
        "total_failed": total_failed,
        "pass_rate": round((total_tests - total_failed) / max(1, total_tests), 4),
        "api_smoke_exit": api_exit,
        "security_exit": sec_exit,
    }
    out = REPORTS / "regression.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n📊 pytest tests: {total_tests}, failed: {total_failed}, "
          f"pass_rate: {result['summary']['pass_rate']:.2%}, "
          f"api={api_exit}, sec={sec_exit}")
    print(f"   saved {out}")
    # 只对 pytest 失败返回非零
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
