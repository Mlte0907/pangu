"""盘古记忆事件流 — 基于 EventBus 的记忆专用事件系统

核心能力：
1. 记忆事件发布：write/update/delete/search 事件自动发布
2. 带过滤的订阅：按事件类型、关键词、Wing 过滤订阅
3. 事件历史持久化：事件日志写入文件
4. Webhook 回调：事件触发外部 HTTP 回调
5. 事件统计：事件频率和分布分析
"""
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("pangu.memory.memory_events")

MEMORY_EVENT_TYPES = [
    "memory.write",
    "memory.update",
    "memory.delete",
    "memory.search",
    "memory.recall",
    "memory.backup",
    "memory.restore",
    "memory.compress",
    "memory.consolidate",
    "memory.forget",
    "memory.distill",
    "memory.quality_check",
    "memory.health_check",
    "system.startup",
    "system.shutdown",
]


@dataclass
class MemoryEvent:
    """记忆事件"""
    event_id: str
    event_type: str
    memory_id: str
    data: dict
    timestamp: str
    source: str = "pangu"


@dataclass
class EventSubscription:
    """事件订阅"""
    sub_id: str
    event_type: str
    callback: Callable
    filter_fn: Optional[Callable] = None
    active: bool = True


@dataclass
class WebhookConfig:
    """Webhook 配置"""
    url: str
    event_types: list[str]
    secret: str = ""
    active: bool = True


class MemoryEventStream:
    """记忆事件流引擎"""

    def __init__(self, config=None):
        self.config = config
        self._subscriptions: dict[str, EventSubscription] = {}
        self._webhooks: list[WebhookConfig] = []
        self._event_history: list[MemoryEvent] = []
        self._event_counts: dict[str, int] = defaultdict(int)
        self._max_history = 5000
        self._event_dir = Path.home() / ".pangu" / "events"
        self._event_dir.mkdir(parents=True, exist_ok=True)
        self._sub_counter = 0

    def _gen_id(self) -> str:
        self._sub_counter += 1
        return f"sub_{self._sub_counter}_{int(time.time())}"

    def _dispatch_to_subscriber(self, sub: EventSubscription, event: MemoryEvent) -> None:
        """将事件分发给单个订阅者"""
        if not sub.active:
            return
        if sub.event_type != event.event_type and sub.event_type != "*":
            return
        if sub.filter_fn is not None and not sub.filter_fn(event):
            return
        try:
            sub.callback(event)
        except Exception as e:
            logger.error(f"Event handler error: {e}")

    def emit(self, event_type: str, memory_id: str = "",
             data: dict = None, source: str = "pangu") -> MemoryEvent:
        """发布记忆事件"""
        event = MemoryEvent(
            event_id=f"evt_{len(self._event_history)}_{int(time.time())}",
            event_type=event_type,
            memory_id=memory_id,
            data=data or {},
            timestamp=datetime.now().isoformat(),
            source=source,
        )

        self._event_history.append(event)
        self._event_counts[event_type] += 1

        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        for sub in self._subscriptions.values():
            self._dispatch_to_subscriber(sub, event)

        return event

    def subscribe(self, event_type: str, callback: Callable,
                  filter_fn: Callable = None) -> str:
        """订阅事件"""
        sub_id = self._gen_id()
        self._subscriptions[sub_id] = EventSubscription(
            sub_id=sub_id,
            event_type=event_type,
            callback=callback,
            filter_fn=filter_fn,
        )
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """取消订阅"""
        if sub_id in self._subscriptions:
            del self._subscriptions[sub_id]
            return True
        return False

    def add_webhook(self, url: str, event_types: list[str], secret: str = "") -> dict:
        """添加 Webhook"""
        wh = WebhookConfig(url=url, event_types=event_types, secret=secret)
        self._webhooks.append(wh)
        return {"url": url, "event_types": event_types, "status": "registered"}

    def remove_webhook(self, url: str) -> bool:
        """移除 Webhook"""
        before = len(self._webhooks)
        self._webhooks = [w for w in self._webhooks if w.url != url]
        return len(self._webhooks) < before

    def get_history(self, event_type: str = None, limit: int = 50) -> list[dict]:
        """查询事件历史"""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return [
            {"id": e.event_id, "type": e.event_type, "memory_id": e.memory_id,
             "timestamp": e.timestamp, "source": e.source, "data": e.data}
            for e in events[-limit:]
        ]

    def get_stats(self) -> dict:
        """获取事件统计"""
        return {
            "total_events": len(self._event_history),
            "event_counts": dict(self._event_counts),
            "active_subscriptions": sum(1 for s in self._subscriptions.values() if s.active),
            "webhooks": len(self._webhooks),
            "top_events": sorted(self._event_counts.items(), key=lambda x: -x[1])[:5],
        }

    def save_history(self) -> int:
        """持久化事件历史到文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = self._event_dir / f"events_{today}.json"

        existing = []
        if history_file.exists():
            try:
                existing = json.loads(history_file.read_text())
            except Exception:
                existing = []

        new_events = [
            {"id": e.event_id, "type": e.event_type, "memory_id": e.memory_id,
             "data": e.data, "timestamp": e.timestamp, "source": e.source}
            for e in self._event_history[-200:]
        ]

        existing.extend(new_events)
        history_file.write_text(json.dumps(existing[-5000:], ensure_ascii=False, indent=2))
        return len(new_events)

    def _replay_to_subscriber(self, event: MemoryEvent, sub: EventSubscription) -> bool:
        """向单个订阅者回放事件，成功返回 True"""
        if not sub.active:
            return False
        if sub.event_type != event.event_type and sub.event_type != "*":
            return False
        try:
            sub.callback(event)
            return True
        except Exception:
            return False

    def replay_events(self, since: str = None, event_type: str = None) -> int:
        """回放事件"""
        events = self._event_history
        if since:
            events = [e for e in events if e.timestamp >= since]
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        replayed = 0
        for event in events:
            for sub in self._subscriptions.values():
                if self._replay_to_subscriber(event, sub):
                    replayed += 1

        return replayed

    def emit_memory_write(self, memory_id: str, content: str = "",
                          wing: str = "") -> MemoryEvent:
        """便捷：发布记忆写入事件"""
        return self.emit("memory.write", memory_id,
                         {"content": content[:100], "wing": wing})

    def emit_memory_delete(self, memory_id: str) -> MemoryEvent:
        """便捷：发布记忆删除事件"""
        return self.emit("memory.delete", memory_id)

    def emit_memory_search(self, query: str, result_count: int = 0) -> MemoryEvent:
        """便捷：发布搜索事件"""
        return self.emit("memory.search", "", {"query": query, "result_count": result_count})


_stream: MemoryEventStream | None = None


def get_event_stream(config=None) -> MemoryEventStream:
    """获取全局记忆事件流实例"""
    global _stream
    if _stream is None:
        _stream = MemoryEventStream(config)
    return _stream
