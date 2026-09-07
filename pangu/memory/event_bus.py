"""盘古 — 统一事件总线（从伏羲 v1.5.6 移植）

核心特性：
1. 发布/订阅模式，解耦模块间通信
2. 优先级队列（LOW/NORMAL/HIGH/URGENT）
3. 同步+异步双模式
4. 背压智能丢弃（优先丢弃低优先级旧事件）
5. 事件日志记录
"""

import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("pangu.kernel.event_bus")


class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    source: str = ""


class EventBus:
    """统一事件总线 — 同步和异步双模式"""

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __init__(self, max_queue_size: int = 10000):
        self._sync_handlers: dict[str, list[Callable]] = {}
        self._async_handlers: dict[str, list[Callable]] = {}
        self._event_log: deque = deque(maxlen=1000)
        self._pending: deque = deque(maxlen=max_queue_size)
        self._max_queue_size = max_queue_size
        self._dropped_count = 0
        self._running = False

    @classmethod
    def get(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（用于测试）"""
        with cls._lock:
            cls._instance = None

    def subscribe(self, event_type: str, handler: Callable, async_mode: bool = False):
        with self._lock:
            target = self._async_handlers if async_mode else self._sync_handlers
            target.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable):
        with self._lock:
            for handlers in [self._sync_handlers, self._async_handlers]:
                if event_type in handlers:
                    handlers[event_type] = [h for h in handlers[event_type] if h is not handler]

    def publish(self, event: Event):
        if len(self._pending) >= self._max_queue_size:
            # 基于优先级的智能丢弃：找到最低优先级的旧事件
            lowest_idx = 0
            lowest_priority = EventPriority.URGENT.value
            for i, e in enumerate(self._pending):
                if e.priority.value < lowest_priority:
                    lowest_priority = e.priority.value
                    lowest_idx = i
            if event.priority.value > lowest_priority:
                self._pending[lowest_idx] = event
                self._dropped_count += 1
                logger.warning(
                    f"EventBus backpressure: dropped low-priority event "
                    f"(priority={EventPriority(lowest_priority).name}, total_dropped={self._dropped_count})"
                )
            else:
                self._dropped_count += 1
                logger.debug(f"EventBus backpressure: dropped event (priority={event.priority.name})")
        else:
            self._pending.append(event)

        self._event_log.append(event)
        handlers = self._sync_handlers.get(event.type, []) + self._sync_handlers.get("*", [])
        for h in handlers:
            try:
                h(event)
            except Exception as e:
                logger.error(f"Event handler error [{event.type}]: {e}")

    async def publish_async(self, event: Event):
        if len(self._pending) >= self._max_queue_size:
            lowest_idx = 0
            lowest_priority = EventPriority.URGENT.value
            for i, e in enumerate(self._pending):
                if e.priority.value < lowest_priority:
                    lowest_priority = e.priority.value
                    lowest_idx = i
            if event.priority.value > lowest_priority:
                self._pending[lowest_idx] = event
                self._dropped_count += 1
                logger.warning(
                    f"EventBus backpressure: dropped low-priority event "
                    f"(priority={EventPriority(lowest_priority).name}, total_dropped={self._dropped_count})"
                )
            else:
                self._dropped_count += 1
        else:
            self._pending.append(event)

        self._event_log.append(event)
        async_handlers = self._async_handlers.get(event.type, [])
        sync_handlers = self._sync_handlers.get(event.type, [])
        for h in async_handlers + sync_handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    await h(event)
                else:
                    h(event)
            except Exception as e:
                logger.error(f"Async handler error [{event.type}]: {e}")

    def clear(self):
        with self._lock:
            self._sync_handlers.clear()
            self._async_handlers.clear()
            self._event_log.clear()
            self._pending.clear()

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def recent_events(self) -> list[Event]:
        return list(self._event_log)

    @property
    def stats(self) -> dict:
        return {
            "total_subscribers": sum(len(v) for v in self._sync_handlers.values())
            + sum(len(v) for v in self._async_handlers.values()),
            "event_types": len(set(list(self._sync_handlers.keys()) + list(self._async_handlers.keys()))),
            "recent_events": len(self._event_log),
            "pending_events": len(self._pending),
            "max_queue_size": self._max_queue_size,
            "dropped_count": self._dropped_count,
            "running": self._running,
        }


def get_event_bus() -> EventBus:
    return EventBus.get()
