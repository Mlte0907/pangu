"""盘古实时事件通知 — WebSocket 实时推送记忆变更"""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger("pangu.memory.realtime")


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._connections: dict[str, object] = {}
        self._subscriptions: dict[str, set[str]] = defaultdict(set)
        self._message_history: list[dict] = []
        self._max_history = 500

    def connect(self, client_id: str, websocket) -> None:
        self._connections[client_id] = websocket
        logger.info(f"WebSocket connected: {client_id}")

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        for topic_subs in self._subscriptions.values():
            topic_subs.discard(client_id)
        logger.info(f"WebSocket disconnected: {client_id}")

    def subscribe(self, client_id: str, topic: str) -> None:
        self._subscriptions[topic].add(client_id)

    def unsubscribe(self, client_id: str, topic: str = None) -> None:
        if topic:
            self._subscriptions[topic].discard(client_id)
        else:
            for subs in self._subscriptions.values():
                subs.discard(client_id)

    async def emit(self, event_type: str, data: dict) -> int:
        """推送事件到所有订阅者"""
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)

        self._message_history.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history:]

        sent = 0
        target_clients = self._subscriptions.get(event_type, set()) | self._subscriptions.get("*", set())

        for client_id in list(target_clients):
            ws = self._connections.get(client_id)
            if ws:
                try:
                    await ws.send_text(message)
                    sent += 1
                except Exception:
                    self.disconnect(client_id)

        return sent

    def get_history(self, event_type: str = None, limit: int = 50) -> list[dict]:
        history = self._message_history
        if event_type:
            history = [m for m in history if m["type"] == event_type]
        return history[-limit:]

    def get_stats(self) -> dict:
        return {
            "connected_clients": len(self._connections),
            "subscriptions": {topic: len(clients) for topic, clients in self._subscriptions.items()},
            "total_messages": len(self._message_history),
        }


_manager: ConnectionManager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    return _manager
