"""盘古实时推送桥接 — 事件总线 → WebSocket + 飞书 自动推送

跨线程投递（2026-09-19 修）：`stream.emit` 会被后台维护线程调用（BackgroundScheduler
的维护任务，例如 portal 的 system.maintenance 事件）。旧实现是在 emit **所在线程**里
`asyncio.get_event_loop()`：
  - 无 loop 的后台线程上，Python 3.12 直接抛
    RuntimeError("There is no current event loop in thread ...")（实测复现），
    随后被 `except Exception: pass` 静默吞掉 —— 后台事件永远推不到 WebSocket，
    而且没有任何日志线索。
现在：启动时捕获主事件循环与主线程 id；同线程走 ensure_future，跨线程走
run_coroutine_threadsafe。
"""

import asyncio
import logging
import threading

logger = logging.getLogger("pangu.memory.realtime_bridge")

_bridge_active = False
_main_loop: asyncio.AbstractEventLoop | None = None
_main_thread_id: int | None = None


def _schedule(coro) -> bool:
    """把协程投递到主循环执行，返回是否成功投递。

    - 同线程（主循环内）：ensure_future
    - 跨线程（维护线程）：run_coroutine_threadsafe
    - 没有运行中的主循环（测试 / CLI 直调）：丢弃并关闭协程（防 "never awaited" 警告）
    """
    loop = _main_loop
    if loop is None or loop.is_closed() or not loop.is_running():
        coro.close()
        return False
    if threading.get_ident() == _main_thread_id:
        asyncio.ensure_future(coro)
    else:
        asyncio.run_coroutine_threadsafe(coro, loop)
    return True


def setup_bridge():
    """将 MemoryEventStream 的事件桥接到 WebSocket + 飞书"""
    global _bridge_active, _main_loop, _main_thread_id
    if _bridge_active:
        return

    # 捕获主循环（lifespan 是协程，这里能拿到 running loop）；测试直调时可能没有
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = None
    _main_thread_id = threading.get_ident()

    try:
        from ..core.config import PanguConfig
        from .memory_events import get_event_stream
        from .realtime import get_connection_manager

        stream = get_event_stream()
        mgr = get_connection_manager()
        _original_emit = stream.emit

        config = PanguConfig.load().authoritative_memory_config()

        feishu = None
        try:
            if config.feishu_webhook_url:
                from .feishu_webhook import get_feishu_webhook

                feishu = get_feishu_webhook(config.feishu_webhook_url)
        except Exception:
            pass

        def bridge_emit(event_type: str, memory_id: str = "", data: dict = None, source: str = "pangu"):
            event = _original_emit(event_type, memory_id, data, source)

            payload = {"event_id": event.event_id, "memory_id": memory_id, "data": data or {}, "source": source}

            # 跨线程安全投递（后台维护线程调用 emit 是常态）
            if not _schedule(mgr.emit(event_type, payload)):
                logger.debug("WebSocket bridge: 无运行中的主循环，事件仅记录在事件流里")

            if feishu and feishu.is_configured():
                try:
                    feishu.push_event(event_type, memory_id, data or {})
                except Exception as e:
                    logger.warning(f"Feishu push failed [{event_type}]: {e}")

            return event

        stream.emit = bridge_emit
        _bridge_active = True
        logger.info("Event stream → WebSocket + Feishu bridge activated")
    except Exception as e:
        logger.error(f"Failed to setup bridge: {e}")
