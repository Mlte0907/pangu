#!/usr/bin/env python3
"""OSV 漏洞审计脚本 — 查询 Google OSV 数据库"""
import json
import sys
import urllib.request
import urllib.parse


def query_osv(package: str) -> list:
    """查询单个包的已知漏洞"""
    url = "https://api.osv.dev/v1/query"
    payload = json.dumps({"package": {"name": package, "ecosystem": "PyPI"}}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("vulns", [])
    except Exception:
        return []


def main():
    if len(sys.argv) < 2:
        print("Usage: osv_audit.py <requirements.txt>")
        sys.exit(1)

    req_file = sys.argv[1]
    results = {}

    with open(req_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg = line.split(">=")[0].split("==")[0].split("<=")[0].split("!=")[0].strip()
            if not pkg:
                continue
            vulns = query_osv(pkg)
            if vulns:
                results[pkg] = []
                for v in vulns:
                    severity = "UNKNOWN"
                    for s in v.get("severity", []):
                        if s.get("type") == "CVSS_V3":
                            score = s.get("score", "")
                            if "CVSS:" in score:
                                parts = score.split("/")
                                for p in parts:
                                    if p.startswith("CVSS:3"):
                                        severity = "HIGH" if float(p.split(":")[-1]) >= 7.0 else "MEDIUM"
                    results[pkg].append({
                        "id": v.get("id", ""),
                        "summary": v.get("summary", "")[:100],
                        "severity": severity,
                    })

    print(json.dumps(results, indent=2))
    print(f"\n📊 Scanned packages with vulns: {len(results)}", file=sys.stderr)


if __name__ == "__main__":
    main()
