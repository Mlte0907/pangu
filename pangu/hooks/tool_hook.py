#!/usr/bin/env python3
"""PostToolUse Hook — 工具调用结果自动沉淀到盘古记忆（伏羲移植）

ECC 协议：
- stdin: {"session_id": "...", "tool_name": "Write", "tool_input": {...}, "tool_output": "..."}
- stdout: {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}

自动过滤低价值调用，提取文件变更和关键信息，上传到盘古记忆。
"""
import json
import os
import re
import sys
from datetime import datetime

PANGU_BASE = os.environ.get("PANGU_BASE_URL", "http://127.0.0.1:8866")
API_KEY = os.environ.get("PANGU_API_KEY")
if not API_KEY:
    sys.exit(0)

IMPORTANT_TOOLS = {"Write", "Edit", "Bash", "Agent", "TodoWrite", "TaskCreate", "TaskUpdate"}
FILE_TOOLS = {"Write", "Edit", "Bash"}

HIGH_IMPORTANCE_KEYWORDS = [
    "修复", "fix", "bug", "BUG", "错误", "问题",
    "安全", "security", "漏洞", "vulnerability",
    "重构", "refactor", "优化", "performance",
    "新增", "create", "删除", "delete",
]

BASH_BLACKLIST = {
    "ls", "pwd", "cd", "echo", "cat", "head", "tail",
    "grep", "find", "which", "whoami", "date", "uptime",
    "df", "du", "free", "uname", "arch", "id", "env",
    "kill", "ps", "top", "htop",
}
BASH_WHITELIST = {
    "git", "npm", "pip", "pip3", "python", "python3",
    "make", "docker", "docker-compose", "kubectl",
    "curl", "wget", "ssh", "scp", "rsync",
    "bash", "sh", "zsh",
}

SENSITIVE_PATTERNS = [
    r'api_key["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'password["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'token["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'secret["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'private_key["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'Authorization["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'Bearer\s+[^\s"\'`]+',
    r'access_token["\']?\s*[:=]\s*["\'][^"\']*["\']',
    r'refresh_token["\']?\s*[:=]\s*["\'][^"\']*["\']',
]


def _read_stdin() -> dict:
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}


def _extract_bash_command(tool_input) -> list:
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command", "") or tool_input.get("input", "")
    else:
        cmd = str(tool_input)
    stripped = cmd.strip()
    if not stripped:
        return []
    parts = re.split(r'&&|\|\||;|\|', stripped)
    commands = []
    for part in parts:
        part = part.strip()
        if part:
            commands.append(part.split()[0] if ' ' in part else part)
    return commands


def _should_remember(tool_name: str, tool_input, tool_output: str) -> bool:
    if tool_name == "Bash":
        cmds = _extract_bash_command(tool_input)
        if not cmds:
            return False
        has_whitelist = any(c in BASH_WHITELIST for c in cmds)
        if has_whitelist:
            return True
        if all(c in BASH_BLACKLIST for c in cmds):
            return False
    if tool_name in IMPORTANT_TOOLS:
        return True
    combined = f"{tool_input} {tool_output}"
    for kw in HIGH_IMPORTANCE_KEYWORDS:
        if kw.lower() in combined.lower():
            return True
    if tool_name in FILE_TOOLS:
        inp = str(tool_input)
        return ".py" in inp or ".sh" in inp or ".md" in inp
    return False


def _extract_file_changes(tool_name: str, tool_input) -> list:
    changes = []
    inp = tool_input if isinstance(tool_input, dict) else {}
    if isinstance(tool_input, str):
        try:
            inp = json.loads(tool_input)
        except Exception:
            inp = {}

    if tool_name == "Write":
        fp = inp.get("file_path", "")
        if fp:
            changes.append(f"创建: {fp}")
    elif tool_name == "Edit":
        fp = inp.get("file_path", "")
        if fp:
            changes.append(f"修改: {fp}")
    elif tool_name == "Bash":
        cmd = str(tool_input)
        if "git commit" in cmd:
            changes.append("git commit")
        elif "git push" in cmd:
            changes.append("git push")
        elif re.search(r'\b(pip install|npm install|brew install)\b', cmd):
            changes.append("依赖安装")
    return changes


def _sanitize(text: str) -> str:
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, '***', text)
    return text


def _upload_to_pangu(text: str, importance: float, tags: list, source: str = "claude_code_hook") -> bool:
    import threading

    import requests

    def _do_upload():
        try:
            requests.post(
                f"{PANGU_BASE}/api/v2/memories",
                json={
                    "text": text,
                    "importance": importance,
                    "tags": tags,
                    "source": source,
                    "wing": "default",
                    "room": "general",
                },
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                timeout=2,
            )
        except Exception:
            pass

    try:
        t = threading.Thread(target=_do_upload, daemon=True)
        t.start()
        return True
    except Exception:
        return False


def main():
    event = _read_stdin()

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", "")
    tool_output = event.get("tool_output", "")

    if not tool_name:
        sys.exit(0)

    tool_input_str = json.dumps(tool_input) if isinstance(tool_input, dict) else str(tool_input)
    tool_input_str = _sanitize(tool_input_str)
    tool_output_str = _sanitize(str(tool_output)[:2000])

    if not _should_remember(tool_name, tool_input, tool_output_str):
        sys.exit(0)

    tags = ["tool", "auto"]
    if tool_name in FILE_TOOLS:
        tags.append("file_change")
    if "error" in tool_output_str.lower():
        tags.append("error")

    importance = 0.5
    combined = f"{tool_input_str} {tool_output_str}"
    for kw in HIGH_IMPORTANCE_KEYWORDS:
        if kw.lower() in combined.lower():
            importance = 0.8
            break

    changes = _extract_file_changes(tool_name, tool_input)
    summary_parts = [f"[{tool_name}]"]
    if changes:
        summary_parts.extend(changes[:3])

    text = f"""[工具调用] {datetime.now().strftime('%H:%M:%S')}

{' | '.join(summary_parts)}

输入: {tool_input_str[:500]}
输出: {tool_output_str[:1000]}"""

    _upload_to_pangu(text, importance, tags)
    sys.exit(0)


if __name__ == "__main__":
    main()
