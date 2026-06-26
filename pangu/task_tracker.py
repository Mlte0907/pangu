#!/usr/bin/env python3
"""任务进度追踪器 — 在工具执行后自动保存任务状态（伏羲移植）

工作流程：
1. PostToolUse Hook 调用此脚本
2. 检测当前会话是否有活跃任务
3. 将任务状态序列化到持久化文件
4. 新会话启动时，SessionStart Hook 读取并恢复上下文

会话隔离：
- 每个会话使用独立的任务文件（基于会话 ID）
- 避免跨会话状态污染
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PANGU_BASE = os.environ.get("PANGU_BASE_URL", "http://127.0.0.1:8866")
API_KEY = os.environ.get("PANGU_API_KEY", "")
SESSION_DIR = Path.home() / ".pangu" / "sessions"
TASK_STATE_FILE = SESSION_DIR / "task_state.json"


def _read_stdin() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _get_session_id() -> str:
    """从环境变量获取当前会话 ID"""
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def _load_task_state() -> dict:
    """加载当前会话的任务状态"""
    if not TASK_STATE_FILE.exists():
        return {}
    try:
        return json.loads(TASK_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_task_state(state: dict) -> None:
    """保存任务状态到持久化文件"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    TASK_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _extract_task_from_context(messages: list) -> dict | None:
    """从消息历史中提取活跃任务信息"""
    if not messages:
        return None

    task_info = {
        "task": "",
        "steps": [],
        "progress": 0.0,
        "last_update": datetime.now().isoformat(),
        "tool_count": 0,
        "messages_count": len(messages),
    }

    # 从最近的 user 消息提取任务
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            if content and len(content) > 5:
                task_info["task"] = content[:500] if len(content) > 500 else content
                break

    # 检测步骤进度
    for msg in messages:
        if msg.get("role") == "assistant":
            tools = msg.get("tool_calls", []) or msg.get("tools", [])
            if tools:
                task_info["tool_count"] = len(tools)

    return task_info


def _save_to_pangu_memory(task_info: dict) -> bool:
    """将任务状态保存到盘古记忆系统"""
    import requests

    try:
        if task_info.get("progress", 0) < 0.3:
            return False

        resp = requests.post(
            f"{PANGU_BASE}/api/v2/memories",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={
                "text": f"[任务快照] {task_info.get('task', '')[:200]}",
                "wing": "default",
                "room": "tasks",
                "importance": 0.9,
                "tags": ["task-progress", "session-snapshot"],
            },
            timeout=2,
        )
        return resp.status_code == 200
    except Exception:
        return False


def main():
    event = _read_stdin()

    tool_name = event.get("tool", "")
    messages = event.get("messages", [])

    session_id = _get_session_id()

    # 从最近的消息中提取任务
    task_info = _extract_task_from_context(messages)

    if task_info and task_info.get("task"):
        state = _load_task_state()

        if state.get("session_id") != session_id:
            state = {"session_id": session_id}

        state["current_task"] = task_info
        state["last_activity"] = datetime.now().isoformat()
        state["last_tool"] = tool_name

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _save_task_state(state)

        if task_info.get("progress", 0) >= 0.3 or task_info.get("tool_count", 0) >= 5:
            _save_to_pangu_memory(task_info)


if __name__ == "__main__":
    main()
