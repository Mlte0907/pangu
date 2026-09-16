"""MCP 工具面健康探测：只调只读工具，按 schema 必填字段构造合法参数。

用法：
    PANGU_KEY=$(cat ~/.pangu/.mcp_key) python scripts/probe_mcp_tools.py [--include-mutating]

设计原则：
- 只读工具直接调，记录 ok/错误码/耗时；
- 写入/破坏性工具默认**不调**（会改数据）；加 --include-mutating 时也只在
  明确标注可逆的工具上调用（当前：全部跳过，仅报告名称与 schema 必填项）。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:19529/mcp"
KEY = os.environ.get("PANGU_KEY", "")

SAFE_READONLY = [
    "pangu_search_memories", "pangu_recall", "pangu_find_related", "pangu_search_stats",
    "pangu_health_report", "pangu_stats", "pangu_list_wings", "pangu_list_rooms",
    "pangu_analyze", "pangu_health_check", "pangu_analyze_emotion", "pangu_health_trend",
    "pangu_health_stats", "pangu_knowledge_get", "pangu_knowledge_list",
    "pangu_knowledge_search", "pangu_knowledge_related", "pangu_knowledge_stats",
    "pangu_get_supersede_chain",
]

# 按字段名给的保守假值，尽量让只读工具走到"正常空结果"而不是参数错误
DUMMY = {
    "query": "测试", "text": "测试", "content": "测试", "keyword": "测试", "q": "测试",
    "wing": "default", "room": "general", "id": "nonexistent-id", "drawer_id": "nonexistent-id",
    "key": "nonexistent-key", "topic": "test", "tag": "test", "limit": 1, "n": 1,
    "n_results": 1, "top_k": 1, "depth": 1, "days": 1, "since": "2026-09-01",
    "start": "2026-09-01", "end": "2026-09-16", "window": "1d", "entity": "test",
}


def rpc(method: str, params: dict, timeout: float = 60) -> tuple[dict | None, float]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(BASE, data=body, headers={
        "content-type": "application/json", "X-API-Key": KEY,
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), (time.time() - t0) * 1000
    except Exception as e:  # noqa: BLE001
        return {"__transport_error__": str(e)}, (time.time() - t0) * 1000


def build_args(schema: dict) -> dict:
    props = (schema or {}).get("properties", {}) or {}
    required = (schema or {}).get("required", []) or []
    args = {}
    for name in required:
        spec = props.get(name, {}) or {}
        if name in DUMMY:
            args[name] = DUMMY[name]
        elif spec.get("type") == "integer" or spec.get("type") == "number":
            args[name] = 1
        elif spec.get("type") == "boolean":
            args[name] = False
        elif spec.get("type") == "array":
            args[name] = []
        else:
            args[name] = "test"
    return args


def main() -> int:
    listing, _ = rpc("tools/list", {})
    tools = {t["name"]: t for t in (listing or {}).get("result", {}).get("tools", [])}
    if not tools:
        print("tools/list 失败：", listing)
        return 1

    print(f"工具总数 {len(tools)}；本次探测 {len(SAFE_READONLY)} 个只读工具\n")
    ok, err, missing = [], [], []
    for name in SAFE_READONLY:
        tool = tools.get(name)
        if tool is None:
            missing.append(name)
            print(f"  ✗ {name:<34} 不在暴露面内")
            continue
        args = build_args(tool.get("inputSchema"))
        resp, ms = rpc("tools/call", {"name": name, "arguments": args})
        result = (resp or {}).get("result", {})
        text = json.dumps(result, ensure_ascii=False)[:400]

        if "__transport_error__" in (resp or {}):
            err.append((name, "transport", resp["__transport_error__"]))
            print(f"  ✗ {name:<34} 传输失败 {resp['__transport_error__'][:60]}")
            continue

        if result.get("isError") or '"code"' in text and '"error"' in text:
            # MCP 层错误与工具自身的业务错误分开看
            code = None
            try:
                payload = json.loads(result["content"][0]["text"])
                code = payload.get("code")
            except Exception:  # noqa: BLE001
                pass
            err.append((name, code, text[:180]))
            print(f"  ⚠ {name:<34} code={code} {ms:.0f}ms {text[:110]}")
        else:
            ok.append(name)
            print(f"  ✓ {name:<34} {ms:6.0f}ms {text[:90]}")

    print(f"\n结果：正常 {len(ok)} · 异常 {len(err)} · 不在暴露面 {len(missing)}")
    if err:
        print("\n异常明细：")
        for name, code, text in err:
            print(f"  - {name} (code={code}): {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
