#!/usr/bin/env python3
"""SessionStart Hook — 自动从盘古记忆注入上下文到 Claude Code（伏羲移植）

在新会话开始时:
1. 查询盘古最近的记忆
2. 按 Wing/Room 分类整理
3. 输出格式化的上下文供 Claude Code 使用

用法（从 Claude Code settings.json 调用）:
  python3 /home/xiaoxin/pangu/pangu/hooks/session_hook.py
"""

import os
import sys
from datetime import datetime

import requests

PANGU_BASE = os.environ.get("PANGU_BASE_URL", "http://127.0.0.1:8866")
API_KEY = os.environ.get("PANGU_API_KEY")
if not API_KEY:
    print("⚠️ PANGU_API_KEY 环境变量未设置，跳过记忆注入", file=sys.stderr)
    sys.exit(0)

# 颜色
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def check_services() -> dict:
    """检查服务状态"""
    services = {
        "盘古 API": f"{PANGU_BASE}/health",
    }
    status = {}
    for name, url in services.items():
        try:
            resp = requests.get(url, timeout=2)
            status[name] = resp.status_code == 200
        except Exception:
            status[name] = False
    return status


def fetch_memories(limit: int = 10) -> list[dict]:
    """获取最近记忆"""
    url = f"{PANGU_BASE}/api/v2/memories"
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def fetch_memories_by_wing(wing: str, limit: int = 5) -> list[dict]:
    """按 Wing 获取记忆"""
    url = f"{PANGU_BASE}/api/v2/memories"
    headers = {"X-API-Key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, params={"wing": wing, "limit": limit}, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def format_memory(mem: dict, index: int) -> str:
    """格式化单条记忆"""
    content = (mem.get("content") or mem.get("raw_text", ""))[:200]
    wing = mem.get("wing", "unknown")
    importance = mem.get("importance", 0.5)
    tags = mem.get("tags", [])
    created_at = (mem.get("created_at") or "")[:10]

    if importance >= 0.8:
        imp_mark = "🔴"
    elif importance >= 0.6:
        imp_mark = "🟡"
    else:
        imp_mark = "🟢"

    tag_str = ", ".join(tags[:3]) if tags else ""

    lines = [f"  {imp_mark} [{wing}] {created_at}"]
    if tag_str:
        lines.append(f"     标签: {tag_str}")
    lines.append(f"     {content}")
    return "\n".join(lines)


def format_context_header():
    """打印上下文头部"""
    print()
    print(f"{CYAN}{BOLD}  ╔══════════════════════════════════════════════╗{RESET}")
    print(f"{CYAN}{BOLD}  ║   盘古 (Pangu) 记忆上下文注入               ║{RESET}")
    print(f"{CYAN}{BOLD}  ╚══════════════════════════════════════════════╝{RESET}")
    print()


def format_services(status: dict):
    """打印服务状态"""
    print(f"{DIM}{'─' * 50}{RESET}")
    print(f"  {CYAN}▸ 服务状态{RESET}")
    for name, ok in status.items():
        mark = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⚠{RESET}"
        print(f"    {mark} {name}")
    print()


def format_recent_memories(memories: list[dict], title: str = "最近记忆"):
    """打印最近记忆"""
    print(f"{DIM}{'─' * 50}{RESET}")
    print(f"  {CYAN}▸ {title}{RESET}")
    if not memories:
        print(f"    {DIM}无记忆{RESET}")
        return
    for i, mem in enumerate(memories[:8], 1):
        print(format_memory(mem, i))
        print()


def format_wing_summary():
    """打印各 Wing 摘要"""
    wings = ["default", "knowledge", "projects", "personal"]
    wing_names = {
        "default": "通用",
        "knowledge": "知识库",
        "projects": "项目",
        "personal": "个人",
    }

    print(f"{DIM}{'─' * 50}{RESET}")
    print(f"  {CYAN}▸ Wing 摘要{RESET}")
    for wing_id in wings:
        memories = fetch_memories_by_wing(wing_id, limit=2)
        if memories:
            name = wing_names.get(wing_id, wing_id)
            latest = (memories[0].get("created_at") or "")[:10]
            text = (memories[0].get("content") or memories[0].get("raw_text", ""))[:80]
            print(f"    {name}: {latest} — {text}...")
    print()


def main():
    format_context_header()

    # 1. 服务状态
    services = check_services()
    format_services(services)

    # 2. 最近记忆
    memories = fetch_memories(limit=10)
    if memories:
        format_recent_memories(memories)
    else:
        print(f"{DIM}{'─' * 50}{RESET}")
        print(f"  {CYAN}▸ 最近记忆{RESET}")
        print(f"    {DIM}无记忆{RESET}")
        print()

    # 3. 各 Wing 摘要
    format_wing_summary()

    # 4. 总结
    print(f"{DIM}{'─' * 50}{RESET}")
    print(f"{GREEN}✓ SessionStart 完成 · {datetime.now().strftime('%H:%M:%S')}{RESET}")
    print()


if __name__ == "__main__":
    main()
