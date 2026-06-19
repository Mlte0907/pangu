"""盘古实时推送桥接 — 事件总线 → WebSocket 自动推送

将 MemoryEventStream 的事件自动推送到所有 WebSocket 订阅者。
"""
import asyncio
import logging
import threading

logger = logging.getLogger("pangu.memory.realtime_bridge")

_bridge_active = False


def setup_bridge():
    """将 MemoryEventStream 的事件桥接到 WebSocket ConnectionManager"""
    global _bridge_active
    if _bridge_active:
        return

    try:
        from .memory_events import get_event_stream
        from .realtime import get_connection_manager

        stream = get_event_stream()
        mgr = get_connection_manager()

        _original_emit = stream.emit

        def bridge_emit(event_type: str, memory_id: str = "", data: dict = None, source: str = "pangu"):
            event = _original_emit(event_type, memory_id, data, source)

            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass

            if loop and loop.is_running():
                asyncio.ensure_future(mgr.emit(event_type, {
                    "event_id": event.event_id,
                    "memory_id": memory_id,
                    "data": data or {},
                    "source": source,
                }))
            else:
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(mgr.emit(event_type, {
                        "event_id": event.event_id,
                        "memory_id": memory_id,
                        "data": data or {},
                        "source": source,
                    }))
                    loop.close()
                except Exception:
                    pass

            return event

        stream.emit = bridge_emit
        _bridge_active = True
        logger.info("Event stream → WebSocket bridge activated")

    except Exception as e:
        logger.error(f"Failed to setup bridge: {e}")
