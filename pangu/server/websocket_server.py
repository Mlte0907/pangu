"""盘古 WebSocket 服务器 — 实时记忆流推送
==========================================
提供 WebSocket 连接管理、实时记忆变更推送、
记忆事件流（create/update/delete）和心跳保活。
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("pangu.websocket")


class EventType(str, Enum):
    """记忆事件类型"""

    MEMORY_CREATE = "memory_create"
    MEMORY_UPDATE = "memory_update"
    MEMORY_DELETE = "memory_delete"
    MEMORY_RECALL = "memory_recall"
    WIKI_UPDATE = "wiki_update"
    KG_UPDATE = "kg_update"
    SYSTEM_STATUS = "system_status"
    HEARTBEAT = "heartbeat"


@dataclass
class ConnectionInfo:
    """WebSocket 连接信息"""

    conn_id: str
    ws: WebSocket
    client_id: str
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    subscriptions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryEvent:
    """记忆事件"""

    event_type: EventType
    data: dict
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class MemoryStreamServer:
    """记忆流 WebSocket 服务器

    功能：
    - 管理多个 WebSocket 连接
    - 按事件类型分发记忆变更
    - 支持按 wing/room 过滤订阅
    - 心跳保活机制
    """

    def __init__(self, heartbeat_interval: float = 30.0, heartbeat_timeout: float = 60.0):
        """
        Args:
            heartbeat_interval: 心跳发送间隔（秒）
            heartbeat_timeout: 心跳超时断开阈值（秒）
        """
        self._connections: dict[str, ConnectionInfo] = {}
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._heartbeat_task: asyncio.Task | None = None
        self._event_history: list[MemoryEvent] = []
        self._max_history = 100
        self._event_callbacks: dict[EventType, list[Callable]] = {}

    async def connect(self, ws: WebSocket, client_id: str = "") -> str:
        """接受 WebSocket 连接

        Args:
            ws: WebSocket 连接对象
            client_id: 客户端标识，留空自动生成

        Returns:
            分配的连接 ID
        """
        await ws.accept()
        conn_id = uuid.uuid4().hex[:8]
        if not client_id:
            client_id = f"client_{conn_id}"

        info = ConnectionInfo(conn_id=conn_id, ws=ws, client_id=client_id)
        self._connections[conn_id] = info
        logger.info(f"WebSocket 连接建立: {conn_id} ({client_id})")

        # 发送欢迎消息
        welcome = MemoryEvent(
            event_type=EventType.SYSTEM_STATUS,
            data={"status": "connected", "conn_id": conn_id, "heartbeat_interval": self._heartbeat_interval},
        )
        await ws.send_text(welcome.to_json())

        # 启动心跳检查（首次连接时）
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return conn_id

    async def disconnect(self, conn_id: str) -> None:
        """断开连接"""
        if conn_id in self._connections:
            info = self._connections.pop(conn_id)
            try:
                await info.ws.close()
            except Exception:
                pass
            logger.info(f"WebSocket 连接断开: {conn_id}")

    async def broadcast(self, event: MemoryEvent, wing: str = None, room: str = None) -> int:
        """广播记忆事件到所有订阅者

        Args:
            event: 记忆事件
            wing: 仅发送给订阅了该 wing 的客户端
            room: 仅发送给订阅了该 room 的客户端

        Returns:
            成功发送的连接数
        """
        # 记录事件历史
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history :]

        # 触发事件回调
        for cb in self._event_callbacks.get(event.event_type, []):
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"事件回调异常: {e}")

        message = event.to_json()
        sent_count = 0
        disconnected: list[str] = []

        for conn_id, info in self._connections.items():
            # 过滤订阅
            if info.subscriptions:
                matched = False
                for sub in info.subscriptions:
                    if wing and sub == f"wing:{wing}":
                        matched = True
                        break
                    if room and sub == f"room:{room}":
                        matched = True
                        break
                    if sub == "all":
                        matched = True
                        break
                if not matched:
                    continue

            try:
                await info.ws.send_text(message)
                sent_count += 1
            except Exception:
                disconnected.append(conn_id)

        # 清理断开的连接
        for conn_id in disconnected:
            await self.disconnect(conn_id)

        return sent_count

    def subscribe(self, conn_id: str, topics: list[str]) -> bool:
        """订阅事件主题

        Args:
            conn_id: 连接 ID
            topics: 订阅主题列表，支持格式：
                    - "all": 所有事件
                    - "wing:default": 特定 wing 的事件
                    - "room:general": 特定 room 的事件
                    - "event:memory_create": 特定事件类型

        Returns:
            是否订阅成功
        """
        info = self._connections.get(conn_id)
        if not info:
            return False
        for topic in topics:
            if topic not in info.subscriptions:
                info.subscriptions.append(topic)
        logger.info(f"连接 {conn_id} 订阅: {topics}")
        return True

    def unsubscribe(self, conn_id: str, topics: list[str]) -> bool:
        """取消订阅"""
        info = self._connections.get(conn_id)
        if not info:
            return False
        for topic in topics:
            if topic in info.subscriptions:
                info.subscriptions.remove(topic)
        return True

    def on_event(self, event_type: EventType, callback: Callable) -> None:
        """注册事件回调"""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self._connections)

    def get_event_history(self, event_type: EventType = None, limit: int = 20) -> list[dict]:
        """获取事件历史"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events[-limit:]]

    async def _heartbeat_loop(self) -> None:
        """心跳保活循环"""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            now = time.time()
            disconnected: list[str] = []

            for conn_id, info in self._connections.items():
                # 检查超时
                if now - info.last_heartbeat > self._heartbeat_timeout:
                    logger.warning(f"心跳超时，断开连接: {conn_id}")
                    disconnected.append(conn_id)
                    continue

                # 发送心跳
                try:
                    hb = MemoryEvent(
                        event_type=EventType.HEARTBEAT,
                        data={"server_time": now, "conn_id": conn_id},
                    )
                    await info.ws.send_text(hb.to_json())
                except Exception:
                    disconnected.append(conn_id)

            for conn_id in disconnected:
                await self.disconnect(conn_id)

    def handle_heartbeat(self, conn_id: str) -> None:
        """处理客户端心跳响应"""
        info = self._connections.get(conn_id)
        if info:
            info.last_heartbeat = time.time()

    async def close(self) -> None:
        """关闭所有连接并停止心跳"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        for conn_id in list(self._connections.keys()):
            await self.disconnect(conn_id)

        logger.info("WebSocket 服务器已关闭")


# ── 辅助工具函数 ──


def create_memory_event(event_type: str, data: dict) -> MemoryEvent:
    """快速创建记忆事件"""
    return MemoryEvent(event_type=EventType(event_type), data=data)


async def mount_websocket(app, ws: WebSocket, server: MemoryStreamServer) -> None:
    """FastAPI 路由处理：WebSocket 连接入口"""
    conn_id = await server.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = msg.get("action", "")

            if action == "heartbeat":
                server.handle_heartbeat(conn_id)
            elif action == "subscribe":
                topics = msg.get("topics", [])
                server.subscribe(conn_id, topics)
            elif action == "unsubscribe":
                topics = msg.get("topics", [])
                server.unsubscribe(conn_id, topics)
            elif action == "history":
                event_type = msg.get("event_type")
                limit = msg.get("limit", 20)
                et = EventType(event_type) if event_type else None
                history = server.get_event_history(et, limit)
                resp = MemoryEvent(
                    event_type=EventType.SYSTEM_STATUS,
                    data={"action": "history", "events": history},
                )
                await ws.send_text(resp.to_json())

    except WebSocketDisconnect:
        await server.disconnect(conn_id)
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
        await server.disconnect(conn_id)
