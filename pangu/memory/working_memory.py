"""盘古工作记忆 — Miller 定律 7±2 槽位 + 注意力衰减 + Checkpoint

从伏羲移植：工作记忆是短期记忆缓冲区，模拟人类意识焦点。
- Miller 定律：容量 7±2 个槽位
- 注意力衰减：未被访问的项逐渐失去激活度
- 情感保护：高情感值项更难被驱逐
- Checkpoint：定期持久化，崩溃恢复

纯大脑能力：只做短期记忆管理，不执行任务。
"""

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger("pangu.memory.working_memory")

WM_CHECKPOINT_INTERVAL = 300  # 5分钟
WM_CHECKPOINT_MAX_ITEMS = 20
WM_DEFAULT_CAPACITY = 7  # Miller 定律
WM_DEFAULT_TOKEN_BUDGET = 2048


@dataclass
class WMItem:
    """工作记忆项"""
    id: str
    content: str
    source: str = "unknown"
    emotional_valence: float = 0.0  # -1.0 ~ 1.0
    urgency: float = 0.0            # 0.0 ~ 1.0
    tokens: int = 0
    activation: float = 1.0         # 0.0 ~ 1.0，越高越活跃
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0

    def touch(self):
        """访问时刷新激活度"""
        self.last_access = time.time()
        self.access_count += 1
        self.activation = min(1.0, self.activation + 0.1)


class WorkingMemory:
    """工作记忆 — 短期记忆缓冲区

    核心特性：
    1. Miller 定律：7±2 槽位容量
    2. 注意力衰减：每 tick 衰减激活度
    3. 情感保护：高情感值项更难驱逐
    4. 自适应容量：根据驱逐率自动调整
    5. Checkpoint：定期持久化到数据库
    """

    # 驱逐保护阈值
    EVICT_PROTECTION_VALENCE = 0.7
    EVICT_P1_ACTIVATION = 0.3
    EVICT_P1_VALENCE = 0.3
    EVICT_P2_ACTIVATION = 0.5
    DECAY_EXTREME_THRESHOLD = 0.1
    EMOTIONAL_COMPENSATION_VALENCE = 0.5

    def __init__(self, capacity: int = None, token_budget: int = WM_DEFAULT_TOKEN_BUDGET):
        self.capacity = capacity or WM_DEFAULT_CAPACITY
        self.token_budget = token_budget
        self._buffer: OrderedDict = OrderedDict()
        self._decay_rate = 0.02
        self._emotional_boost = 0.1
        self._lock = threading.Lock()
        self._total_pushed = 0
        self._evictions = 0
        self._token_evictions = 0
        self._total_tokens = 0
        self._last_checkpoint = time.time()
        self._checkpoint_thread: threading.Thread | None = None
        self._checkpoint_stop = threading.Event()

    @property
    def slots(self) -> list[WMItem]:
        """当前所有槽位"""
        return list(self._buffer.values())

    @property
    def focus(self) -> WMItem | None:
        """焦点项（激活度最高的项）"""
        if not self._buffer:
            return None
        return max(self._buffer.values(), key=lambda item: item.activation)

    @property
    def current_tokens(self) -> int:
        return self._total_tokens

    def usage(self) -> float:
        """使用率 0.0 ~ 1.0"""
        if self.capacity == 0:
            return 0.0
        return len(self._buffer) / self.capacity

    def _evict_to_token_budget(self) -> WMItem | None:
        """Token 预算驱逐，返回第一个被驱逐的项"""
        first_evicted = None
        while self._total_tokens > self.token_budget:
            token_evicted = self._evict_by_token()
            if first_evicted is None:
                first_evicted = token_evicted
        return first_evicted

    def push(self, item: WMItem) -> WMItem | None:
        """推入一个工作记忆项，返回被驱逐的项（如果有）"""
        with self._lock:
            self._total_pushed += 1
            self._total_tokens += item.tokens
            item.touch()
            evicted = None

            if item.id in self._buffer:
                self._buffer.move_to_end(item.id)
            else:
                while len(self._buffer) >= self.capacity:
                    evicted = self._evict()
                token_evicted = self._evict_to_token_budget()
                if evicted is None:
                    evicted = token_evicted

            self._buffer[item.id] = item

        self.adapt_capacity()
        return evicted

    def _evict(self) -> WMItem | None:
        """驱逐策略：优先驱逐低激活度+低情感值项"""
        if not self._buffer:
            return None

        candidates = list(self._buffer.items())

        # 优先级1: 低激活 + 低情感
        low_act_low_val = [
            (k, v) for k, v in candidates
            if v.activation < self.EVICT_P1_ACTIVATION
            and v.emotional_valence < self.EVICT_P1_VALENCE
        ]
        if low_act_low_val:
            victim_id, victim = min(low_act_low_val, key=lambda x: x[1].activation + x[1].emotional_valence)
            reason = "low_activation_low_valence"
        else:
            # 优先级2: 低激活
            low_act = [(k, v) for k, v in candidates if v.activation < self.EVICT_P2_ACTIVATION]
            if low_act:
                victim_id, victim = min(low_act, key=lambda x: x[1].activation)
                reason = "low_activation"
            else:
                # 溢出：保护高激活项（>=0.8），在 0.5-0.8 范围内驱逐
                unprotected = [(k, v) for k, v in candidates if v.activation < 0.8]
                if unprotected:
                    victim_id, victim = min(unprotected, key=lambda x: x[1].activation)
                else:
                    victim_id, victim = min(candidates, key=lambda x: x[1].activation)
                reason = "overflow"

        evicted = self._buffer.pop(victim_id)
        self._evictions += 1
        self._token_evictions += 1
        self._total_tokens = max(0, self._total_tokens - evicted.tokens)
        logger.debug(f"WM evicted: {victim_id[:8]} (reason={reason}, activation={evicted.activation:.4f})")
        return evicted

    def _select_eviction_candidate(self, candidates: list) -> tuple:
        """从候选列表中选择驱逐目标"""
        low_act_low_val = [(k, v) for k, v in candidates
                           if v.activation < 0.3 and v.emotional_valence < 0.3]
        if low_act_low_val:
            return min(low_act_low_val, key=lambda x: x[1].activation + x[1].emotional_valence)

        low_act = [(k, v) for k, v in candidates if v.activation < 0.5]
        if low_act:
            return min(low_act, key=lambda x: x[1].activation)

        return min(candidates, key=lambda x: x[1].activation)

    def _evict_by_token(self) -> WMItem | None:
        """Token 预算驱逐"""
        if not self._buffer:
            return None

        candidates = list(self._buffer.items())
        victim_id, victim = self._select_eviction_candidate(candidates)

        evicted = self._buffer.pop(victim_id)
        self._evictions += 1
        self._token_evictions += 1
        self._total_tokens = max(0, self._total_tokens - evicted.tokens)
        return evicted

    def get(self, item_id: str) -> WMItem | None:
        """获取工作记忆项（触达刷新）"""
        with self._lock:
            item = self._buffer.get(item_id)
            if item:
                item.last_access = time.time()
                item.access_count += 1
                self._buffer.move_to_end(item_id)
            return item

    def decay_tick(self, dt: float = 1.0):
        """注意力衰减一次 tick"""
        dt = max(0.01, min(dt, 10.0))

        with self._lock:
            to_remove = []
            for item_id, item in self._buffer.items():
                item.activation = max(0.0, item.activation * (1.0 - self._decay_rate * dt))
                # 情感补偿
                if item.emotional_valence > self.EMOTIONAL_COMPENSATION_VALENCE:
                    item.activation = min(1.0, item.activation + self._emotional_boost * item.emotional_valence * dt)
                if item.activation < self.DECAY_EXTREME_THRESHOLD:
                    to_remove.append(item_id)

            for item_id in to_remove:
                evicted = self._buffer.pop(item_id, None)
                if evicted:
                    self._evictions += 1
                    self._total_tokens = max(0, self._total_tokens - evicted.tokens)

    def clear(self):
        """清空工作记忆"""
        with self._lock:
            self._buffer.clear()
            self._total_tokens = 0

    @property
    def context(self) -> str:
        """获取当前上下文摘要"""
        parts = []
        for item in list(self._buffer.values())[-3:]:
            prefix = "[焦点]" if item is self.focus else ""
            parts.append(f"{prefix} {item.content[:50]}")
        return "\n".join(parts)

    @property
    def token_usage(self) -> float:
        if self.token_budget == 0:
            return 0.0
        return self._total_tokens / self.token_budget

    def adapt_capacity(self):
        """根据驱逐率自适应调整容量"""
        if self._total_pushed < 100:
            return

        eviction_rate = self._evictions / self._total_pushed
        old_cap = self.capacity
        if eviction_rate > 0.3 and self.capacity < 15:
            self.capacity = min(15, self.capacity + 2)
            logger.info(f"WM capacity: {old_cap} → {self.capacity} (eviction_rate={eviction_rate:.2f})")
        elif eviction_rate < 0.05 and self.capacity > 3:
            self.capacity = max(3, self.capacity - 1)
            logger.info(f"WM capacity: {old_cap} → {self.capacity} (eviction_rate={eviction_rate:.2f})")

    @property
    def stats(self) -> dict:
        """工作记忆统计"""
        return {
            "capacity": self.capacity,
            "slots_used": len(self._buffer),
            "total_pushed": self._total_pushed,
            "evictions": self._evictions,
            "token_budget": self.token_budget,
            "tokens_used": self._total_tokens,
            "token_usage_pct": round(self.token_usage * 100, 1),
            "token_evictions": self._token_evictions,
            "focus_id": self.focus.id[:8] if self.focus else None,
            "last_checkpoint": self._last_checkpoint,
        }

    def checkpoint(self) -> int:
        """将工作记忆持久化（用于崩溃恢复）"""
        from ..core.config import PanguConfig
        config = PanguConfig()
        checkpoint_path = os.path.join(config.palace_path, "wm_checkpoint.json")

        with self._lock:
            items = list(self._buffer.values())
        if not items:
            return 0

        items.sort(key=lambda x: x.activation, reverse=True)
        top_items = items[:WM_CHECKPOINT_MAX_ITEMS]

        try:
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            data = {
                "ts": time.time(),
                "count": len(top_items),
                "items": [
                    {
                        "id": item.id,
                        "content": item.content[:1000],
                        "source": item.source,
                        "activation": item.activation,
                        "emotional_valence": item.emotional_valence,
                        "created_at": item.created_at,
                    }
                    for item in top_items
                ],
            }
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._last_checkpoint = time.time()
            logger.info(f"WM checkpoint saved: {len(top_items)} items")
            return len(top_items)
        except Exception as e:
            logger.warning(f"WM checkpoint failed: {e}")
            return 0

    def restore_checkpoint(self) -> int:
        """从持久化恢复工作记忆"""
        from ..core.config import PanguConfig
        config = PanguConfig()
        checkpoint_path = os.path.join(config.palace_path, "wm_checkpoint.json")

        try:
            if not os.path.exists(checkpoint_path):
                return 0
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0

        restored = 0
        with self._lock:
            for item_data in data.get("items", []):
                try:
                    item = WMItem(
                        id=item_data["id"],
                        content=item_data["content"],
                        source=item_data.get("source", "checkpoint"),
                        activation=float(item_data.get("activation", 0.5)),
                        emotional_valence=float(item_data.get("emotional_valence", 0.0)),
                        created_at=float(item_data.get("created_at", time.time())),
                    )
                    self._buffer[item.id] = item
                    restored += 1
                except Exception as e:
                    logger.warning(f"WM restore item failed: {e}")

        if restored:
            logger.info(f"WM checkpoint restored: {restored} items")
        return restored

    def start_auto_checkpoint(self):
        """启动定期 Checkpoint 线程"""
        if self._checkpoint_thread and self._checkpoint_thread.is_alive():
            return
        self._checkpoint_stop.clear()
        self._checkpoint_thread = threading.Thread(
            target=self._auto_checkpoint_loop, daemon=True, name="wm-checkpoint"
        )
        self._checkpoint_thread.start()
        logger.info(f"WM auto-checkpoint started (interval={WM_CHECKPOINT_INTERVAL}s)")

    def stop_auto_checkpoint(self):
        """停止 Checkpoint 线程"""
        self._checkpoint_stop.set()
        if self._checkpoint_thread:
            self._checkpoint_thread.join(timeout=5)

    def _auto_checkpoint_loop(self):
        while not self._checkpoint_stop.wait(timeout=WM_CHECKPOINT_INTERVAL):
            try:
                self.checkpoint()
            except Exception as e:
                logger.warning(f"WM auto-checkpoint failed: {e}")


_wm_instance: WorkingMemory | None = None


def get_working_memory(capacity: int = None) -> WorkingMemory:
    """获取工作记忆单例"""
    global _wm_instance
    if _wm_instance is None:
        _wm_instance = WorkingMemory(capacity=capacity)
    return _wm_instance
