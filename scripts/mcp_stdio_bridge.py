#!/usr/bin/env python3
"""盘古 MCP 的 stdio ↔ HTTP 桥。

为什么需要它：CodeBuddy IDE 的 MCP 配置文档只给了 `type: "stdio"`（官方《使用指南 › MCP》
的示例字段只有 type/command/args/env/description），而盘古的 MCP 端点是 streamable-HTTP
的 `/mcp` + `X-API-Key` 头。这个桥把 stdin 上的 JSON-RPC 逐行转发到盘古，再把应答写回
stdout —— 两端都是标准 MCP，桥本身不做业务解释（唯一例外是丢弃通知的应答，见下）。

在 MCP 客户端里配置为 stdio server：

    {
      "mcpServers": {
        "pangu": {
          "type": "stdio",
          "command": "/home/xiaoxin/pangu/.venv/bin/python",
          "args": ["/home/xiaoxin/pangu/scripts/mcp_stdio_bridge.py"],
          "env": {
            "PANGU_MCP_URL": "http://127.0.0.1:19529/mcp",
            "PANGU_API_KEY_FILE": "/home/xiaoxin/.pangu/.mcp_key_codebuddy"
          }
        }
      }
    }

环境变量：
    PANGU_MCP_URL        默认 http://127.0.0.1:19529/mcp
    PANGU_API_KEY        直接给凭据明文（优先于文件）
    PANGU_API_KEY_FILE   从文件读凭据，默认 ~/.pangu/.mcp_key_codebuddy
    PANGU_TIMEOUT        单次请求超时秒数，默认 120

协议约束（踩过的坑，改这个文件前先读）：
  * stdout 只能出现 JSON-RPC 消息 —— 任何调试输出都必须走 stderr，否则客户端解析失败。
  * 无 id 的消息是**通知**，MCP 规定不得应答；盘古的 HTTP 端点会回
    `{"jsonrpc":"2.0","id":null,"result":{}}`，原样透传会让部分客户端报
    「收到未知 id 的应答」，所以这里丢弃。
  * 出错时返回 JSON-RPC error（而不是静默），否则客户端会一直等下去。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("PANGU_MCP_URL", "http://127.0.0.1:19529/mcp")
TIMEOUT = float(os.environ.get("PANGU_TIMEOUT", "120"))
KEY_FILE = os.environ.get("PANGU_API_KEY_FILE", str(Path.home() / ".pangu" / ".mcp_key_codebuddy"))


def log(msg: str) -> None:
    """调试输出**只能**走 stderr（stdout 是协议通道）。"""
    print(f"[pangu-bridge] {msg}", file=sys.stderr, flush=True)


def write(msg: object) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read_key() -> str:
    env = (os.environ.get("PANGU_API_KEY") or "").strip()
    if env:
        return env
    try:
        return Path(os.path.expanduser(KEY_FILE)).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def forward(payload: object, key: str) -> object | None:
    """把一条（或一批）JSON-RPC 消息转发到盘古，返回解析后的应答；空应答返回 None。"""
    headers = {"content-type": "application/json"}
    if key:
        headers["x-api-key"] = key
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
    if not raw.strip():
        return None
    return json.loads(raw)


def main() -> int:
    key = read_key()
    log(f"就绪 url={URL} 凭据={'已加载' if key else f'缺失({KEY_FILE})，将以匿名身份请求'}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            log(f"丢弃非 JSON 输入: {exc}")
            continue

        is_batch = isinstance(payload, list)
        is_notification = (not is_batch) and isinstance(payload, dict) and "id" not in payload
        msg_id = None if (is_batch or is_notification) else payload.get("id")

        try:
            result = forward(payload, key)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            log(f"HTTP {exc.code}: {detail}")
            if not is_notification:
                write({"jsonrpc": "2.0", "id": msg_id, "error": {
                    "code": -32000, "message": f"pangu MCP HTTP {exc.code}", "data": detail}})
            continue
        except Exception as exc:  # noqa: BLE001 — 桥要保住协议通道，任何异常都转成 JSON-RPC error
            log(f"转发失败: {exc!r}")
            if not is_notification:
                write({"jsonrpc": "2.0", "id": msg_id, "error": {
                    "code": -32000, "message": f"pangu MCP unreachable: {exc}"}})
            continue

        if is_notification or result is None:
            continue  # 通知不得应答（盘古会回 id:null，透传会触发客户端协议告警）
        write(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
