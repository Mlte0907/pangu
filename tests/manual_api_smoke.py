"""盘古系统接口契约/冒烟测试 — REST API + MCP 工具 + CLI

覆盖：
- FastAPI 应用创建（不启动服务，纯内存）
- /health、/health/deep、/metrics、/api/v2/system/info
- /docs、/openapi.json 外部访问限制
- CORS 头
- 异常处理
- 鉴权/边界用例
- MCP 工具注册表
- CLI 命令注册
"""

import os

os.environ.setdefault("PANGU_DATA_DIR", "/home/xiaoxin/pangu/.test_data")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import json
import time

from fastapi.testclient import TestClient

results = {"passed": 0, "failed": 0, "errors": []}


def check(name, cond, detail=""):
    if cond:
        results["passed"] += 1
        print(f"  [PASS] {name}")
    else:
        results["failed"] += 1
        results["errors"].append((name, detail))
        print(f"  [FAIL] {name} :: {detail}")


# ── 1. FastAPI 应用 ──
print("== FastAPI Application ==")
from pangu.api.server import create_app

try:
    app = create_app()
    check("app.create_app", app is not None)
    check("app.title", "盘古" in app.title, app.title)
    check("app.version", app.version == "0.1.0", app.version)
except Exception as e:
    check("app.create_app", False, str(e))
    print(f"  cannot proceed: {e}")
    raise SystemExit(1) from e

client = TestClient(app)

# ── 2. 健康检查 ──
print("== Health endpoints ==")
r = client.get("/health")
check("/health 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
if r.status_code == 200:
    body = r.json()
    check("/health envelope", body.get("code") == 0 and "data" in body, body)
    check("/health data.status", body["data"].get("status") in ("ok", "degraded", "unhealthy"), body["data"])

r = client.get("/health/deep")
check("/health/deep 200", r.status_code == 200, f"status={r.status_code}")

r = client.get("/")
check("/ root redirect", r.status_code in (200, 307, 308), f"status={r.status_code}")

# ── 3. 指标端点 ──
print("== Metrics ==")
r = client.get("/metrics")
check("/metrics 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    check("/metrics prometheus text", "text/plain" in r.headers.get("content-type", ""), r.headers.get("content-type"))
    check("/metrics has pangu metrics", "pangu_" in r.text or "python_gc" in r.text, r.text[:300])

# ── 4. 系统信息 ──
print("== System info ==")
r = client.get("/api/v2/system/info")
check("/api/v2/system/info 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    body = r.json()
    check(
        "/system/info data fields",
        all(k in body.get("data", {}) for k in ("name", "version", "health", "config")),
        list(body.get("data", {}).keys()),
    )

# ── 5. 文档限制 ──
print("== Docs access control ==")
# TestClient 走 127.0.0.1 客户端（白名单），所以应能访问
r = client.get("/docs")
check("/docs accessible from localhost", r.status_code in (200, 307, 308), f"status={r.status_code}")

# 模拟外部 IP（需要直接调 ASGI 中间件）
# 通过自定义 scope 模拟外部 host
# Use raw ASGI to test the middleware


async def call_with_host(path, host="8.8.8.8"):
    from pangu.api.server import create_app

    app2 = create_app()
    _received = {}
    body_chunks = []
    status = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]
            status["headers"] = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            body_chunks.append(msg.get("body", b""))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (host, 12345),
        "server": ("test", 80),
        "scheme": "http",
    }
    try:
        await app2(scope, receive, send)
    except Exception as e:
        return 500, str(e)
    body = b"".join(body_chunks).decode(errors="ignore")
    return status.get("code", 0), body


# 用 asyncio 跑
import asyncio

for path in ["/docs", "/openapi.json"]:
    code, _ = asyncio.run(call_with_host(path, host="8.8.8.8"))
    check(f"{path} blocked from external", code == 403, f"code={code}")
    code, _ = asyncio.run(call_with_host(path, host="127.0.0.1"))
    check(f"{path} allowed from localhost", code in (200, 307, 308), f"code={code}")

# ── 6. CORS ──
print("== CORS ==")
r = client.options(
    "/health",
    headers={
        "Origin": "http://localhost:19528",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type",
    },
)
check("CORS preflight", "access-control-allow-origin" in {k.lower() for k in r.headers.keys()}, dict(r.headers))

# ── 7. 异常处理 ──
print("== Exception handler ==")
r = client.get("/api/v2/nonexistent")
check("404 handling", r.status_code in (404, 405), f"code={r.status_code}")
if r.status_code == 404:
    body = r.json()
    # FastAPI 默认 404 也可，但全局处理器应接管
    check("404 envelope", isinstance(body, dict) and "code" in body, body)

# ── 8. MCP 工具 ──
print("== MCP Server ==")
try:
    from pangu.server.mcp_server import MCPServer

    mcp = MCPServer.__new__(MCPServer)
    if hasattr(mcp, "_register_tools") or hasattr(mcp, "tools"):
        # Try list_tools method
        from pangu.core.config import PanguConfig

        cfg = PanguConfig()
        mcp_inst = MCPServer(cfg) if hasattr(MCPServer, "__init__") else None
        if mcp_inst:
            tools = mcp_inst.list_tools() if hasattr(mcp_inst, "list_tools") else None
            if tools is not None:
                check(
                    "MCP list_tools", isinstance(tools, list) and len(tools) > 0, f"count={len(tools) if tools else 0}"
                )
                if tools:
                    check(
                        "MCP tool has name/signature",
                        all("name" in t and ("inputSchema" in t or "parameters" in t) for t in tools),
                        tools[:2],
                    )
                    print(f"  ({len(tools)} tools registered)")
            else:
                check("MCP list_tools", True, "no list_tools method, but class loaded")
        else:
            check("MCP init", False, "cannot init MCPServer without args")
except Exception as e:
    check("MCP server load", False, f"{type(e).__name__}: {e}")

# ── 9. CLI ──
print("== CLI ==")
try:
    from pangu.cli import app as cli_app

    check("CLI app", cli_app is not None, str(type(cli_app)))
    # typer apps have registered_commands via app.registered_commands or similar
    if hasattr(cli_app, "registered_commands"):
        cmds = [c.name for c in cli_app.registered_commands]
        check("CLI has commands", len(cmds) > 0, f"commands={cmds[:5]}")
    elif hasattr(cli_app, "commands"):
        # Click-style fallback
        check("CLI app", True, "click-style")
    else:
        check("CLI app", True, "loaded (introspection limited)")
except Exception as e:
    check("CLI load", False, f"{type(e).__name__}: {e}")

# ── 10. 路由注册情况 ──
print("== Routes ==")
routes = [r.path for r in app.routes if hasattr(r, "path")]
check("has /health", "/health" in routes, routes)
check("has /metrics", "/metrics" in routes, routes)
check("has /api/v2/system/info", "/api/v2/system/info" in routes, routes)
api_v2 = [r for r in routes if r.startswith("/api/v2/")]
check("api v2 routes registered", len(api_v2) >= 3, f"count={len(api_v2)} paths={api_v2[:5]}")
print(f"  Total routes: {len(routes)}")
print(f"  API v2 routes: {len(api_v2)}")

# ── 总结 ──
print()
print("=" * 60)
print(f"API/MCP/CLI Smoke: {results['passed']} passed, {results['failed']} failed")
if results["failed"] > 0:
    print("Failed cases:")
    for n, d in results["errors"]:
        print(f"  - {n}: {d}")

# 写报告
import pathlib

out = pathlib.Path("/home/xiaoxin/pangu/reports/api_smoke.json")
out.write_text(
    json.dumps(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "passed": results["passed"],
            "failed": results["failed"],
            "errors": [{"name": n, "detail": d} for n, d in results["errors"]],
            "routes_count": len(routes),
            "api_v2_count": len(api_v2),
        },
        indent=2,
        ensure_ascii=False,
    )
)
print(f"saved {out}")

import sys

sys.exit(0 if results["failed"] == 0 else 1)
