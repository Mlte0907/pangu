"""盘古实时推送桥接 — 事件总线 → WebSocket + 飞书 自动推送"""

import asyncio
import logging

logger = logging.getLogger("pangu.memory.realtime_bridge")

_bridge_active = False


def setup_bridge():
    """将 MemoryEventStream 的事件桥接到 WebSocket + 飞书"""
    global _bridge_active
    if _bridge_active:
        return

    try:
        from ..core.config import PanguConfig
        from .memory_events import get_event_stream
        from .realtime import get_connection_manager

        stream = get_event_stream()
        mgr = get_connection_manager()
        _original_emit = stream.emit

        config = PanguConfig.load()

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

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(mgr.emit(event_type, payload))
                else:
                    loop.run_until_complete(mgr.emit(event_type, payload))
            except Exception:
                pass

            if feishu and feishu.is_configured():
                try:
                    feishu.push_event(event_type, memory_id, data or {})
                except Exception:
                    pass

            return event

        stream.emit = bridge_emit
        _bridge_active = True
        logger.info("Event stream → WebSocket + Feishu bridge activated")

    except Exception as e:
        logger.error(f"Failed to setup bridge: {e}")
