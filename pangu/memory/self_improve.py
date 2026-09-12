"""盘古自我提升工作器 — 服务端透明采集与记忆自我增强

设计：无论任何 MCP 客户端调用盘古，盘古服务端自动捕获有价值的交互，
经规则提炼后写入自身记忆库（self_improvement wing）。客户端无需配合。

关键决策：
- 单点挂钩：所有 MCP 调用汇合于 MCPServer.handle_request 的 tools/call 分支
- 写入侧独立：通过 HTTP 调自身的 /api/v2/memories，绕过 MCP，避免递归
- 提炼规则保守：长度阈值 + 关键词 + 工具排除白名单，控制噪声
- 非阻塞设计：handler 只做 queue.put_nowait（O(1)），Worker 线程后台消费
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field

import requests

from pangu.memory.event_bus import Event, EventPriority, get_event_bus

logger = logging.getLogger("pangu.memory.self_improve")

# 工具调用事件的盘古事件类型（与 memory_events.MEMORY_EVENT_TYPES 区分）
MCP_TOOL_INVOCATION_EVENT = "mcp.tool_invocation"

# 不值得采集的工具名（噪声工具 / 元查询 / 本身即写记忆的工具）
EXCLUDED_TOOLS = frozenset(
    {
        "ping",
        "health_check",
        "list_tools",
        "get_tool_info",
        "stats",
        "metrics",
        "pangu_add_memory",
        "pangu_update_memory",
        "pangu_delete_memory",
        "pangu_export_memories",
        "pangu_purge_memories",
    }
)

# 触发采集的最低有效字符数
MIN_CONTENT_CHARS = 60

# 队列上限（避免内存爆炸）
QUEUE_MAX = 5000


@dataclass
class _BufferedInvocation:
    tool: str
    args_text: str
    result_text: str
    success: bool
    ts: float = field(default_factory=time.time)


class SelfImproveWorker:
    """订阅 mcp.tool_invocation 事件，按规则提炼后写入盘古自身记忆。

    非阻塞：handler 仅做 O(1) 的 queue.put_nowait，Worker 后台线程消费。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        flush_interval: float = 30.0,
        batch_size: int = 5,
    ):
        if base_url is None:
            # 统一走 PanguConfig，不要自己 json.load config.json：
            #  1) 配置模型里没有 server_url 字段，config.json 也从不写它，
            #     原先的 cfg.get("server_url", "http://127.0.0.1:19529")
            #     永远取默认值——那段读取是装饰性的死代码；
            #  2) api_key 被 PanguConfig.save() 的 exclude 排除，从不落在
            #     config.json（改存环境变量），直接读 json 永远拿到空串，
            #     导致 X-API-Key 认证失效。
            # PanguConfig 用 env_prefix="PANGU_"，故 PANGU_HOST/PANGU_PORT
            # 会正确映射到 host/port。
            from pangu.core.config import PanguConfig

            cfg = PanguConfig.load()
            # host 是【监听】地址，0.0.0.0 表示监听所有网卡，
            # 不能直接当连接目标用，需换成环回地址。
            host = "127.0.0.1" if cfg.host in ("0.0.0.0", "::", "") else cfg.host
            base_url = f"http://{host}:{cfg.port}"
            api_key = api_key or cfg.api_key

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._flush_interval = flush_interval
        self._batch_size = batch_size

        self._queue: queue.Queue[_BufferedInvocation] = queue.Queue(maxsize=QUEUE_MAX)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._drop_count = 0
        self._written_count = 0
        # 近期去重：缓存最近写入的 (tool, args_hash)，避免同类调用反复沉淀
        self._recent_hashes: dict[str, float] = {}
        self._dedup_window: float = 300.0  # 5 分钟内相同 tool+args 不重复写入

        # 订阅事件总线（handler 只入队立即返回，不阻塞 publish）
        get_event_bus().subscribe(MCP_TOOL_INVOCATION_EVENT, self._on_event, async_mode=False)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._consume_loop, name="pangu-self-improve", daemon=True)
        self._thread.start()
        logger.info(
            f"SelfImproveWorker 已启动 (base={self._base_url}, interval={self._flush_interval}s, batch={self._batch_size})"
        )

    def stop(self) -> None:
        self._stop.set()

    # ── 事件回调（非阻塞） ──────────────────────────────────────

    def _on_event(self, event: Event) -> None:
        """Handler 仅做解析+O(1) 入队，立即返回。绝不阻塞 publish。"""
        try:
            inv = self._extract(event)
            if inv is None:
                return
            try:
                self._queue.put_nowait(inv)
            except queue.Full:
                self._drop_count += 1
                logger.debug("self_improve queue full, dropped event")
        except Exception as e:
            logger.debug(f"self_improve _on_event 解析失败: {e}")

    def _extract(self, event: Event) -> _BufferedInvocation | None:
        data = event.data or {}
        tool = data.get("tool_name", "") or ""
        if tool in EXCLUDED_TOOLS:
            return None
        args_text = self._flatten_text(data.get("arguments"))
        result_text = self._flatten_text(data.get("result"))
        if len(args_text) + len(result_text) < MIN_CONTENT_CHARS:
            return None
        # 近期去重：相同 tool + 相同参数，5 分钟内只记一次
        try:
            key = f"{tool}\x00{hash(args_text)}"
            now = time.time()
            self._recent_hashes = {k: v for k, v in self._recent_hashes.items() if now - v < self._dedup_window}
            if key in self._recent_hashes:
                return None
            self._recent_hashes[key] = now
        except Exception:
            pass
        return _BufferedInvocation(
            tool=tool,
            args_text=args_text[:500],
            result_text=result_text[:800],
            success=data.get("success", True),
        )

    @staticmethod
    def _flatten_text(obj: object) -> str:
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            for k in ("text", "content", "data", "message", "preview"):
                v = obj.get(k)
                if isinstance(v, str):
                    return v
            try:
                return json.dumps(obj, ensure_ascii=False)
            except Exception:
                return str(obj)
        if isinstance(obj, list):
            parts = [SelfImproveWorker._flatten_text(x) for x in obj[:5]]
            return "\n".join(p for p in parts if p)
        return str(obj)

    # ── 后台消费 ─────────────────────────────────────────────

    def _consume_loop(self) -> None:
        """批量消费队列中的事件，周期性 flush。"""
        buffer: list[_BufferedInvocation] = []
        next_flush = time.monotonic() + self._flush_interval
        while not self._stop.is_set():
            # 批量收集（非阻塞）
            try:
                inv = self._queue.get_nowait()
                buffer.append(inv)
                # 满批立即 flush
                while len(buffer) < self._batch_size:
                    try:
                        buffer.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
                self._flush_batch(buffer)
                buffer = []
                next_flush = time.monotonic() + self._flush_interval
            except queue.Empty:
                pass

            # 到时间也 flush
            if buffer and time.monotonic() >= next_flush:
                self._flush_batch(buffer)
                buffer = []
                next_flush = time.monotonic() + self._flush_interval

            # 短暂 sleep 让出 CPU
            time.sleep(0.5)

        # 退出前最后一次 flush
        if buffer:
            self._flush_batch(buffer)

    def _flush_batch(self, batch: list[_BufferedInvocation]) -> None:
        for inv in batch:
            try:
                self._write_memory(inv)
                self._written_count += 1
            except Exception as e:
                self._drop_count += 1
                logger.debug(f"self_improve 写入失败 ({inv.tool}): {e}")

    def _write_memory(self, inv: _BufferedInvocation) -> None:
        text = (
            f"[服务端透明采集] 工具 `{inv.tool}` 被调用。\n"
            f"参数摘要：{inv.args_text[:300]}\n"
            f"结果摘要：{inv.result_text[:500]}"
        )
        payload = {
            "text": text,
            "importance": 0.5,
            "tags": ["self_improve", "tool_usage", inv.tool],
            "source": "self_improve",
            "wing": "self_improvement",
            "room": "tool_usage",
            "classification": 0,
            "visibility": "public",
        }
        r = requests.post(
            f"{self._base_url}/api/v2/memories",
            json=payload,
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
            timeout=3,
        )
        r.raise_for_status()


# 便捷发布函数（供钩子点调用）
def emit_tool_invocation(
    tool_name: str,
    arguments: dict | None,
    result: object,
    success: bool = True,
    source: str = "mcp",
    extra: dict | None = None,
) -> None:
    data = {
        "tool_name": tool_name,
        "arguments": arguments or {},
        "result": result,
        "success": success,
        "source": source,
    }
    if extra:
        data.update(extra)
    get_event_bus().publish(
        Event(
            type=MCP_TOOL_INVOCATION_EVENT,
            data=data,
            priority=EventPriority.LOW,
        )
    )


def start_self_improver(**kwargs) -> SelfImproveWorker:
    """便捷启动入口（在 server lifespan 中调用）。"""
    worker = SelfImproveWorker(**kwargs)
    worker.start()
    return worker
