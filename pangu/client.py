#!/usr/bin/env python3
"""盘古记忆客户端 — 外部系统交互封装（伏羲移植）"""

import hashlib
import hmac
import json
import os
import sys
import time

import requests

AGENT_ID = "pangu_client"
API_KEY = os.environ.get("PANGU_API_KEY", "")
BASE = os.environ.get("PANGU_BASE_URL", "http://127.0.0.1:8866")


def _headers():
    ts = str(int(time.time()))
    msg = f"{AGENT_ID}:{ts}"
    sig = hmac.new(API_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest() if API_KEY else ""
    return {
        "X-API-Key": API_KEY,
        "X-Agent-ID": AGENT_ID,
        "X-Agent-Signature": sig,
        "X-Timestamp": ts,
    }


def pangu_get(path, params=None):
    r = requests.get(f"{BASE}{path}", params=params, headers=_headers(), timeout=15)
    try:
        return r.json()
    except Exception:
        return r.text


def pangu_post(path, data=None):
    r = requests.post(f"{BASE}{path}", json=data or {}, headers=_headers(), timeout=15)
    try:
        return r.json()
    except Exception:
        return r.text


def pangu_put(path, data=None):
    r = requests.put(f"{BASE}{path}", json=data or {}, headers=_headers(), timeout=15)
    try:
        return r.json()
    except Exception:
        return r.text


def pangu_delete(path):
    r = requests.delete(f"{BASE}{path}", headers=_headers(), timeout=15)
    try:
        return r.json()
    except Exception:
        return r.text


def cmd_memory(args):
    sub = args[0] if args else "help"

    if sub == "recent":
        limit = int(args[1]) if args[1:2] else 10
        result = pangu_get("/api/v2/memories", {"limit": limit})
        items = result.get("data", {}).get("items", [])
        for i, item in enumerate(items, 1):
            text = (item.get("content") or item.get("raw_text", ""))[:120]
            imp = item.get("importance", "?")
            tags = item.get("tags", [])
            created = (item.get("created_at") or "?")[:16]
            print(f"  {i}. [{created}] imp={imp} tags={tags}")
            print(f"     {text}")

    elif sub == "search":
        q = " ".join(args[1:])
        result = pangu_get("/api/v2/memories/search", {"q": q, "limit": 10})
        data = result.get("data", {})
        results = data.get("results", []) if isinstance(data, dict) else []
        print(f"  搜索 '{q}' -> {len(results)} 条结果")
        for i, item in enumerate(results[:5], 1):
            text = (item.get("content") or item.get("raw_text", ""))[:120]
            print(f"  {i}. {text}")

    elif sub == "remember":
        text = " ".join(args[1:]) if len(args) > 1 else ""
        if not text:
            print("用法: memory remember <文本> [重要度] [标签...]")
            return
        # 简单解析：如果下一个参数是数字，则为重要度
        parts = args[1:]
        imp = 0.5
        tags = []
        text_parts = []
        for p in parts:
            try:
                imp = float(p)
            except ValueError:
                if p.startswith("#"):
                    tags.append(p[1:])
                else:
                    text_parts.append(p)

        result = pangu_post(
            "/api/v2/memories",
            {
                "text": " ".join(text_parts) if text_parts else text,
                "importance": imp,
                "tags": tags,
                "wing": "default",
                "room": "general",
            },
        )
        print(f"  已写入: {json.dumps(result, ensure_ascii=False)[:200]}")

    elif sub == "context":
        budget = int(args[1]) if args[1:2] else 2000
        result = pangu_get("/api/v2/memories/context", {"budget": budget})
        items = result.get("data", {}).get("context", [])
        print(f"  上下文 (budget={budget}): {len(items)} 条记忆")
        for i, item in enumerate(items[:5], 1):
            text = (item.get("content") or item.get("raw_text", ""))[:80]
            imp = item.get("importance", "?")
            print(f"  {i}. [imp={imp}] {text}")

    elif sub == "delete":
        if len(args) < 2:
            print("用法: memory delete <记忆ID>")
            return
        mid = args[1]
        result = pangu_delete(f"/api/v2/memories/{mid}")
        print(f"  删除 {mid}: {json.dumps(result, ensure_ascii=False)[:200]}")

    elif sub == "stats":
        result = pangu_get("/api/v2/memories/stats")
        stats = result.get("data", {})
        print("  盘古记忆统计:")
        print(f"    Wings: {stats.get('wings_count', '?')}")
        print(f"    Rooms: {stats.get('rooms_count', '?')}")
        print(f"    Tunnels: {stats.get('tunnels_count', '?')}")

    elif sub == "health":
        result = pangu_get("/health")
        health = result.get("data", {})
        print(f"  状态: {health.get('status', 'unknown')}")
        print(f"  版本: {health.get('version', '?')}")
        print(f"  运行时间: {health.get('uptime_seconds', 0)}s")

    else:
        print("用法: memory <recent|search|remember|context|delete|stats|health> [args...]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 pangu_client.py memory <recent|search|remember|context|delete|stats|health> [args...]")
    else:
        cmd = sys.argv[1]
        if cmd == "memory":
            cmd_memory(sys.argv[2:])
        else:
            print(f"未知命令: {cmd}")
