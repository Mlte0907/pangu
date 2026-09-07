"""盘古安全测试 — 危险 API、SQL 注入、secret 扫描、越权"""

import json
import os
import pathlib
import re
import tempfile

os.environ.setdefault("PANGU_DATA_DIR", "/home/xiaoxin/pangu/.test_data")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

results = {"secret_scan": {}, "dangerous_api": {}, "sql_injection": {}, "auth_bypass": {}, "path_traversal": {}}
ROOT = pathlib.Path("/home/xiaoxin/pangu")

# ── 1. Secret 扫描（仓库代码 / 配置） ──
print("== Secret Scan ==")
secret_patterns = {
    "openai_key": r"sk-[A-Za-z0-9]{20,}",
    "anthropic_key": r"sk-ant-[A-Za-z0-9-]{20,}",
    "deepseek_key": r"sk-[a-f0-9]{32,}",
    "zhipu_key": r"[0-9a-f]{32}\.[A-Za-z0-9]{16,}",
    "dashscope_key": r"sk-[a-f0-9]{32}",
    "generic_bearer": r"Bearer\s+[A-Za-z0-9._-]{30,}",
    "private_key": r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----",
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"ghp_[A-Za-z0-9]{36}",
    "wechat_work": r"ww[0-9a-f]{32}",
}
findings = []
# 扫描 .py 文件，跳过 .venv/ / tests/ / reports/
for py in ROOT.rglob("*.py"):
    if any(p in py.parts for p in (".venv", "tests", "reports", "__pycache__", ".git", "node_modules")):
        continue
    try:
        text = py.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for name, pat in secret_patterns.items():
        m = re.findall(pat, text)
        if m:
            # 排除占位符/示例
            m_filtered = [
                s
                for s in m
                if not re.search(r"(?:example|placeholder|TODO|FAKE|xxxxx|sample)", s, re.I)
                and "YOUR_KEY" not in s
                and "your_key" not in s
            ]
            if m_filtered:
                findings.append({"file": str(py.relative_to(ROOT)), "type": name, "samples": m_filtered[:2]})
# 扫描环境文件
for env in [".env", ".env.example", ".env.local"]:
    p = ROOT / env
    if p.exists():
        for name, pat in secret_patterns.items():
            m = re.findall(pat, p.read_text(encoding="utf-8", errors="ignore"))
            if m:
                findings.append({"file": str(p.relative_to(ROOT)), "type": name, "samples": m[:2]})
results["secret_scan"] = {"patterns": list(secret_patterns.keys()), "findings": findings}
print(f"  scanned {len(list(ROOT.rglob('*.py')))} .py files")
print(f"  secret findings: {len(findings)}")
for f in findings:
    print(f"   - {f['file']}: {f['type']} ({len(f['samples'])})")

# ── 2. 危险 API 使用 ──
print("\n== Dangerous API Usage ==")
dangerous = {
    "subprocess_shell": r"subprocess\.(?:call|run|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True",
    "os_system": r"os\.(?:system|popen)",
    "eval_exec": r"^\s*(?:eval|exec)\s*\(",
    "pickle_loads": r"pickle\.loads?",
    "yaml_load": r"yaml\.(?:unsafe_load|load)\s*\(",
    "shell_injection": r"shell\s*=\s*True",
    "md5_insecure": r"hashlib\.(?:md5|sha1)\s*\(",
    "random_for_crypto": r"random\.(?:random|randint|choice)\s*\(",
    "verify_disabled": r"verify\s*=\s*False",
    "ssl_disabled": r"ssl\._create_unverified|ssl\.OP_NO_TLS",
}
api_findings = []
for py in ROOT.rglob("*.py"):
    if any(p in py.parts for p in (".venv", "tests", "reports", "__pycache__", ".git")):
        continue
    try:
        text = py.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for name, pat in dangerous.items():
        for m in re.finditer(pat, text, re.M):
            line = text[: m.start()].count("\n") + 1
            api_findings.append({"file": str(py.relative_to(ROOT)), "type": name, "line": line})
results["dangerous_api"] = {"findings": api_findings}
print(f"  dangerous API usages: {len(api_findings)}")
# 统计
from collections import Counter

ctr = Counter(f["type"] for f in api_findings)
for t, c in ctr.most_common():
    print(f"   {t}: {c}")

# ── 3. SQL 注入测试 ──
print("\n== SQL Injection Test ==")
sql_test_results = []
# 测试 KnowledgeGraph 的查询方法是否参数化
try:
    import tempfile

    from pangu.core.config import PanguConfig
    from pangu.memory.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.db_path = pathlib.Path(td)
        cfg.base_dir = pathlib.Path(td)
        cfg.palace_path = str(pathlib.Path(td) / "palace.json")
        cfg.ensure_dirs()
        kg = KnowledgeGraph(cfg)
        # 尝试 SQL 注入
        malicious = "a'); DROP TABLE entities; --"
        try:
            r = kg.list_entities(entity_type=malicious)
            sql_test_results.append(
                {
                    "input": malicious,
                    "output_type": type(r).__name__,
                    "count": len(r) if hasattr(r, "__len__") else -1,
                    "error": None,
                }
            )
        except Exception as e:
            sql_test_results.append({"input": malicious, "error": f"{type(e).__name__}: {e}"})
        # 验证表还在
        try:
            r2 = kg.list_entities()
            sql_test_results.append({"verify": "table exists", "ok": True, "count": len(r2)})
        except Exception as e:
            sql_test_results.append({"verify": "table exists", "ok": False, "error": str(e)})
except Exception as e:
    sql_test_results.append({"setup_error": f"{type(e).__name__}: {e}"})
results["sql_injection"] = sql_test_results
print(f"  tested: {sql_test_results}")

# ── 4. 路径穿越 ──
print("\n== Path Traversal Test ==")
pt_results = []
try:
    from fastapi.testclient import TestClient

    from pangu.api.server import create_app

    app = create_app()
    client = TestClient(app)
    # 尝试在已知 API 路径穿越
    payloads = [
        "/api/v2/../../../../etc/passwd",
        "/api/v2/memory/../../../etc/shadow",
        "/api/v2/drawer/../../../../etc/passwd",
        "//etc/passwd",
    ]
    for p in payloads:
        try:
            r = client.get(p)
            content = r.text[:200]
            if "root:" in content or "PASSWD" in content.upper():
                pt_results.append({"payload": p, "LEAKED": True, "status": r.status_code})
            else:
                pt_results.append({"payload": p, "leaked": False, "status": r.status_code})
        except Exception as e:
            pt_results.append({"payload": p, "error": f"{type(e).__name__}: {e}"})
except Exception as e:
    pt_results.append({"setup_error": f"{type(e).__name__}: {e}"})
results["path_traversal"] = pt_results
print(f"  tested: {len(pt_results)} payloads")
for r in pt_results:
    print(f"   {r}")

# ── 5. 鉴权 / 越权 ──
print("\n== Auth Bypass Test ==")
auth_results = []
try:
    from fastapi.testclient import TestClient

    from pangu.api.server import create_app

    app = create_app()
    client = TestClient(app)
    # 假设存在 X-API-Key 头
    endpoints = ["/health", "/api/v2/system/info", "/api/v2/memory/search?q=test", "/api/v2/drawer/list"]
    for ep in endpoints:
        # 无头
        r1 = client.get(ep)
        # 假头
        r2 = client.get(ep, headers={"X-API-Key": "fake_key_test_12345"})
        # 错误头
        r3 = client.get(ep, headers={"X-API-Key": ""})
        auth_results.append(
            {
                "endpoint": ep,
                "no_auth": r1.status_code,
                "fake_key": r2.status_code,
                "empty_key": r3.status_code,
                "passes_through": r1.status_code == r2.status_code == r3.status_code,  # 没有差分 = 没鉴权
            }
        )
except Exception as e:
    auth_results.append({"error": f"{type(e).__name__}: {e}"})
results["auth_bypass"] = auth_results
print(f"  results: {auth_results}")

# 写报告
out = ROOT / "reports" / "security.json"
out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(f"\nsaved {out}")
