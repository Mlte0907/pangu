"""盘古多Agent协作记忆 — 共享记忆空间 + 权限隔离 + 跨Agent同步

多Agent（羲和/玄女/轩辕等）共享记忆池，同时保持权限隔离：
- private：仅创建者可见
- shared：指定Agent组可见
- public：所有Agent可见

核心特性：
1. 三级权限隔离（private/shared/public）
2. 跨Agent记忆同步（事件驱动）
3. 冲突检测与解决策略（last-write-wins / manual / merge）
4. 记忆引用与追溯（谁写了什么、谁引用了谁）
"""

import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .conflict import ConflictDetector

logger = logging.getLogger("pangu.memory.multi_agent")


class MemoryScope(str, Enum):
    """记忆权限范围"""

    PRIVATE = "private"  # 仅创建者可见
    SHARED = "shared"  # 指定Agent组可见
    PUBLIC = "public"  # 所有Agent可见


class SyncStrategy(str, Enum):
    """跨Agent同步策略"""

    IMMEDIATE = "immediate"  # 实时同步
    BATCH = "batch"  # 批量同步
    ON_DEMAND = "on_demand"  # 按需同步


class ConflictResolution(str, Enum):
    """冲突解决策略"""

    LAST_WRITE_WINS = "last_write_wins"  # 最后写入者胜出
    HIGHEST_PRIORITY = "highest_priority"  # 高优先级Agent胜出
    MANUAL = "manual"  # 人工介入
    MERGE = "merge"  # 合并


@dataclass
class AgentMemory:
    """Agent记忆项"""

    id: str
    content: str
    owner: str  # 创建者Agent ID
    scope: MemoryScope = MemoryScope.PRIVATE
    shared_with: list[str] = field(default_factory=list)  # shared范围下的可见Agent
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    references: list[str] = field(default_factory=list)  # 引用的其他记忆ID
    ref_count: int = 0  # 被引用次数


@dataclass
class MemoryReference:
    """记忆引用关系"""

    referrer: str  # 引用者Agent ID
    reference_id: str  # 被引用的记忆ID
    referrer_id: str  # 引用者记忆ID
    created_at: float = field(default_factory=time.time)


@dataclass
class SyncEvent:
    """同步事件"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_id: str = ""
    memory_id: str = ""
    action: str = ""  # create / update / delete
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False


class MultiAgentMemory:
    """多Agent协作记忆 — 共享记忆空间

    核心职责：
    1. 管理多Agent共享记忆池
    2. 权限隔离：private/shared/public三级
    3. 跨Agent同步：事件驱动 + 冲突检测
    4. 记忆引用与追溯：记录Agent间的记忆关系

    典型用法：
        mam = MultiAgentMemory()
        mam.register_agent("xihe", priority=10)
        mam.register_agent("xuannv", priority=5)

        # 羲和写入私有记忆
        mem = mam.write("xihe", "盘古启动完成", scope=MemoryScope.PRIVATE)

        # 羲和写入共享记忆
        mem = mam.write("xihe", "训练进度80%", scope=MemoryScope.SHARED,
                        shared_with=["xuannv", "xuanyuan"])

        # 玄女读取（只能看到public + 自己被shared的）
        results = mam.read("xuannv")
    """

    # 默认Agent优先级
    DEFAULT_PRIORITY = 5

    def __init__(
        self,
        conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE_WINS,
    ):
        # 记忆池：memory_id -> AgentMemory
        self._memories: dict[str, AgentMemory] = {}
        # Agent注册表：agent_id -> priority
        self._agents: dict[str, int] = {}
        # 引用关系索引：memory_id -> list[MemoryReference]
        self._references: dict[str, list[MemoryReference]] = defaultdict(list)
        # 同步事件队列
        self._sync_events: list[SyncEvent] = []
        # 同步回调：agent_id -> handler
        self._sync_handlers: dict[str, Any] = {}
        # 冲突检测器
        self._conflict_detector = ConflictDetector()
        # 冲突解决策略
        self._conflict_resolution = conflict_resolution
        # 读写统计
        self._stats: dict[str, dict[str, int]] = defaultdict(lambda: {"reads": 0, "writes": 0})
        # 活动流
        self._activity_feed: list[dict] = []
        self._max_activity = 500
        # 锁
        self._lock = threading.RLock()

    # ── Agent管理 ──────────────────────────────────────────────

    def register_agent(self, agent_id: str, priority: int = None) -> None:
        """注册Agent到协作记忆空间"""
        with self._lock:
            self._agents[agent_id] = priority if priority is not None else self.DEFAULT_PRIORITY
            self._log_activity(agent_id, "register", f"Agent {agent_id} registered")
            logger.info(f"Agent registered: {agent_id} (priority={self._agents[agent_id]})")

    def ensure_agent(self, agent_id: str, priority: int = None) -> None:
        """自动注册Agent（已注册则跳过）"""
        if agent_id not in self._agents:
            self.register_agent(agent_id, priority)

    def _log_activity(self, agent_id: str, action: str, detail: str = ""):
        """记录活动流"""
        entry = {
            "agent": agent_id,
            "action": action,
            "detail": detail[:200],
            "timestamp": datetime.now().isoformat(),
        }
        self._activity_feed.append(entry)
        if len(self._activity_feed) > self._max_activity:
            self._activity_feed = self._activity_feed[-self._max_activity :]

    def get_activity_feed(self, agent_id: str = None, limit: int = 20) -> list[dict]:
        """获取活动流"""
        feed = self._activity_feed
        if agent_id:
            feed = [e for e in feed if e["agent"] == agent_id]
        return feed[-limit:]

    def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        with self._lock:
            self._agents.pop(agent_id, None)
            logger.info(f"Agent unregistered: {agent_id}")

    def get_agents(self) -> dict[str, int]:
        """获取所有已注册Agent及其优先级"""
        return dict(self._agents)

    # ── 记忆写入 ──────────────────────────────────────────────

    def write(
        self,
        agent_id: str,
        content: str,
        scope: MemoryScope = MemoryScope.PRIVATE,
        shared_with: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        references: list[str] | None = None,
    ) -> AgentMemory:
        """写入一条记忆

        Args:
            agent_id: 写入者Agent ID
            content: 记忆内容
            scope: 权限范围（private/shared/public）
            shared_with: shared范围下的可见Agent列表
            tags: 标签
            metadata: 附加元数据
            references: 引用的其他记忆ID列表
        """
        if agent_id not in self._agents:
            raise ValueError(f"Agent '{agent_id}' 未注册")

        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = time.time()

        memory = AgentMemory(
            id=memory_id,
            content=content,
            owner=agent_id,
            scope=scope,
            shared_with=shared_with or [],
            tags=tags or [],
            metadata=metadata or {},
            references=references or [],
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._memories[memory_id] = memory
            self._stats[agent_id]["writes"] += 1
            self._log_activity(
                agent_id, "write", f"Wrote {getattr(memory.scope, 'value', memory.scope)} memory: {content[:60]}"
            )

            # 记录引用关系
            for ref_id in references or []:
                if ref_id in self._memories:
                    self._references[ref_id].append(
                        MemoryReference(
                            referrer=agent_id,
                            reference_id=ref_id,
                            referrer_id=memory_id,
                        )
                    )
                    self._memories[ref_id].ref_count += 1

        # 发布同步事件
        self._emit_sync(agent_id, memory_id, "create")

        # 检测与已有记忆的冲突
        conflicts = self._detect_new_conflicts(memory)
        if conflicts:
            logger.warning(f"Memory {memory_id[:8]} has {len(conflicts)} conflicts")

        logger.debug(f"Memory written: {memory_id[:8]} by {agent_id} (scope={getattr(scope, 'value', scope)})")
        return memory

    def update(
        self,
        agent_id: str,
        memory_id: str,
        content: str | None = None,
        scope: MemoryScope | None = None,
        shared_with: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemory | None:
        """更新一条记忆（仅创建者可更新）"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if not memory:
                return None
            if memory.owner != agent_id:
                raise PermissionError(f"Agent '{agent_id}' 无权更新记忆 {memory_id[:8]}")

            if content is not None:
                memory.content = content
            if scope is not None:
                memory.scope = scope
            if shared_with is not None:
                memory.shared_with = shared_with
            if tags is not None:
                memory.tags = tags
            if metadata is not None:
                memory.metadata.update(metadata)

            memory.version += 1
            memory.updated_at = time.time()
            self._stats[agent_id]["writes"] += 1

        self._emit_sync(agent_id, memory_id, "update")
        return memory

    def delete(self, agent_id: str, memory_id: str) -> bool:
        """删除一条记忆（仅创建者可删除）"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if not memory:
                return False
            if memory.owner != agent_id:
                raise PermissionError(f"Agent '{agent_id}' 无权删除记忆 {memory_id[:8]}")
            del self._memories[memory_id]

        self._emit_sync(agent_id, memory_id, "delete")
        return True

    # ── 记忆读取 ──────────────────────────────────────────────

    def read(self, agent_id: str, tags: list[str] | None = None) -> list[AgentMemory]:
        """读取当前Agent可见的所有记忆（自动注册未注册的Agent）"""
        if agent_id not in self._agents:
            self.ensure_agent(agent_id)

        results = []
        with self._lock:
            for memory in self._memories.values():
                if not self._is_visible(memory, agent_id):
                    continue
                if tags and not any(t in memory.tags for t in tags):
                    continue
                results.append(memory)
                self._stats[agent_id]["reads"] += 1

        self._log_activity(agent_id, "read", f"Read {len(results)} memories" + (f" [tags={tags}]" if tags else ""))
        return results

    def get(self, agent_id: str, memory_id: str) -> AgentMemory | None:
        """获取单条记忆（需有可见权限）"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if not memory:
                return None
            if not self._is_visible(memory, agent_id):
                return None
            self._stats[agent_id]["reads"] += 1
            return memory

    def get_by_owner(self, agent_id: str) -> list[AgentMemory]:
        """获取指定Agent拥有的所有记忆"""
        with self._lock:
            return [m for m in self._memories.values() if m.owner == agent_id]

    def search(self, agent_id: str, query: str) -> list[AgentMemory]:
        """在可见记忆中搜索（简单关键词匹配）"""
        visible = self.read(agent_id)
        query_lower = query.lower()
        return [m for m in visible if query_lower in m.content.lower()]

    # ── 权限管理 ──────────────────────────────────────────────

    def share(self, owner: str, memory_id: str, target_agents: list[str]) -> bool:
        """将私有/共享记忆分享给指定Agent"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if not memory:
                return False
            if memory.owner != owner:
                raise PermissionError(f"Agent '{owner}' 无权分享记忆 {memory_id[:8]}")

            # 如果是私有记忆，先升级为shared
            if memory.scope == MemoryScope.PRIVATE:
                memory.scope = MemoryScope.SHARED

            for agent in target_agents:
                if agent not in memory.shared_with:
                    memory.shared_with.append(agent)

            memory.updated_at = time.time()
        return True

    def revoke_access(self, owner: str, memory_id: str, target_agents: list[str]) -> bool:
        """撤销指定Agent对记忆的访问权"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if not memory:
                return False
            if memory.owner != owner:
                raise PermissionError(f"Agent '{owner}' 无权操作记忆 {memory_id[:8]}")

            memory.shared_with = [a for a in memory.shared_with if a not in target_agents]
            memory.updated_at = time.time()
        return True

    # ── 引用与追溯 ────────────────────────────────────────────

    def add_reference(self, agent_id: str, memory_id: str, reference_id: str) -> bool:
        """为记忆添加引用"""
        with self._lock:
            memory = self._memories.get(memory_id)
            ref_target = self._memories.get(reference_id)
            if not memory or not ref_target:
                return False
            if not self._is_visible(ref_target, agent_id):
                raise PermissionError(f"Agent '{agent_id}' 无权引用记忆 {reference_id[:8]}")
            if reference_id not in memory.references:
                memory.references.append(reference_id)
                ref_target.ref_count += 1
                self._references[reference_id].append(
                    MemoryReference(
                        referrer=agent_id,
                        reference_id=reference_id,
                        referrer_id=memory_id,
                    )
                )
        return True

    def get_references_to(self, memory_id: str) -> list[MemoryReference]:
        """获取引用了指定记忆的所有关系"""
        return list(self._references.get(memory_id, []))

    def get_references_from(self, agent_id: str) -> list[MemoryReference]:
        """获取指定Agent的所有引用关系"""
        with self._lock:
            refs = []
            for memory in self._memories.values():
                if memory.owner == agent_id:
                    refs.extend(self._references.get(memory.id, []))
            return refs

    def trace_lineage(self, memory_id: str, depth: int = 5) -> list[dict[str, Any]]:
        """追溯记忆血缘链（引用链）"""
        result = []
        visited = set()
        queue = [(memory_id, 0)]

        while queue:
            mid, level = queue.pop(0)
            if mid in visited or level >= depth:
                continue
            visited.add(mid)

            with self._lock:
                memory = self._memories.get(mid)
                if not memory:
                    continue
                result.append(
                    {
                        "id": memory.id,
                        "owner": memory.owner,
                        "content_preview": memory.content[:60],
                        "version": memory.version,
                        "level": level,
                    }
                )
                # 向上追溯：谁引用了这条记忆
                for ref in self._references.get(mid, []):
                    queue.append((ref.referrer_id, level + 1))

        return result

    # ── 跨Agent同步 ──────────────────────────────────────────

    def register_sync_handler(self, agent_id: str, handler: Any) -> None:
        """注册Agent同步回调（收到新记忆时触发）"""
        self._sync_handlers[agent_id] = handler

    def get_pending_syncs(self, agent_id: str) -> list[SyncEvent]:
        """获取Agent的待同步事件"""
        with self._lock:
            return [e for e in self._sync_events if not e.resolved and e.agent_id != agent_id]

    def resolve_sync(self, event_id: str) -> None:
        """标记同步事件已处理"""
        with self._lock:
            for event in self._sync_events:
                if event.id == event_id:
                    event.resolved = True
                    break

    def sync_all(self, source_agent: str, strategy: SyncStrategy = SyncStrategy.IMMEDIATE) -> int:
        """将源Agent的public/shared记忆同步给所有其他Agent

        Returns:
            同步的记忆数量
        """
        source_memories = self.get_by_owner(source_agent)
        synced = 0

        with self._lock:
            targets = [a for a in self._agents if a != source_agent]

        for memory in source_memories:
            if memory.scope == MemoryScope.PRIVATE:
                continue
            synced += self._sync_memory_to_targets(memory, source_agent, targets, strategy)

        return synced

    # ── 冲突检测与解决 ────────────────────────────────────────

    def detect_conflicts(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """检测记忆间的冲突

        Args:
            agent_id: 仅检测指定Agent的记忆，None则检测全部
        """
        with self._lock:
            if agent_id:
                memories = [m for m in self._memories.values() if m.owner == agent_id and self._is_visible(m, agent_id)]
            else:
                memories = list(self._memories.values())

        if len(memories) < 2:
            return []

        conflicts = self._find_conflict_pairs(memories)
        conflicts.sort(key=lambda c: c["confidence"], reverse=True)
        return conflicts

    def resolve_conflict(
        self,
        memory_a_id: str,
        memory_b_id: str,
        strategy: ConflictResolution | None = None,
    ) -> str | None:
        """解决两个记忆间的冲突

        Returns:
            保留的记忆ID，或None（表示合并后生成新记忆）
        """
        strategy = strategy or self._conflict_resolution

        with self._lock:
            mem_a = self._memories.get(memory_a_id)
            mem_b = self._memories.get(memory_b_id)

        if not mem_a or not mem_b:
            return None

        if strategy == ConflictResolution.LAST_WRITE_WINS:
            winner = mem_a if mem_a.updated_at >= mem_b.updated_at else mem_b
            loser = mem_b if winner is mem_a else mem_a
            # 删除较旧的记忆
            self.delete(loser.owner, loser.id)
            logger.info(f"Conflict resolved (last_write_wins): kept {winner.id[:8]}")
            return winner.id

        elif strategy == ConflictResolution.HIGHEST_PRIORITY:
            with self._lock:
                pri_a = self._agents.get(mem_a.owner, 0)
                pri_b = self._agents.get(mem_b.owner, 0)
            if pri_a >= pri_b:
                self.delete(mem_b.owner, mem_b.id)
                logger.info(f"Conflict resolved (highest_priority): kept {mem_a.id[:8]}")
                return mem_a.id
            else:
                self.delete(mem_a.owner, mem_a.id)
                logger.info(f"Conflict resolved (highest_priority): kept {mem_b.id[:8]}")
                return mem_b.id

        elif strategy == ConflictResolution.MERGE:
            # 合并为新记忆
            merged_content = f"[合并] {mem_a.content}\n---\n{mem_b.content}"
            merged = self.write(
                agent_id="system",
                content=merged_content,
                scope=MemoryScope.PUBLIC,
                tags=list(set(mem_a.tags + mem_b.tags)),
                metadata={"merged_from": [mem_a.id, mem_b.id]},
            )
            # 删除原记忆
            self.delete(mem_a.owner, mem_a.id)
            self.delete(mem_b.owner, mem_b.id)
            logger.info(f"Conflict resolved (merge): new {merged.id[:8]}")
            return merged.id

        else:  # MANUAL
            logger.info(f"Conflict requires manual resolution: {memory_a_id[:8]} vs {memory_b_id[:8]}")
            return None

    # ── 统计与查询 ────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """协作记忆统计"""
        with self._lock:
            scope_counts = defaultdict(int)
            for m in self._memories.values():
                scope_counts[getattr(m.scope, "value", m.scope)] += 1

            return {
                "total_agents": len(self._agents),
                "total_memories": len(self._memories),
                "scope_distribution": dict(scope_counts),
                "total_references": sum(len(refs) for refs in self._references.values()),
                "pending_syncs": sum(1 for e in self._sync_events if not e.resolved),
                "agent_stats": dict(self._stats),
            }

    def get_agent_memory_map(self) -> dict[str, dict[str, int]]:
        """获取每个Agent的记忆分布"""
        with self._lock:
            result: dict[str, dict[str, int]] = {}
            for agent_id in self._agents:
                owned = sum(1 for m in self._memories.values() if m.owner == agent_id)
                visible = sum(1 for m in self._memories.values() if self._is_visible(m, agent_id))
                result[agent_id] = {
                    "owned": owned,
                    "visible": visible,
                    "writes": self._stats[agent_id]["writes"],
                    "reads": self._stats[agent_id]["reads"],
                }
            return result

    # ── 内部方法 ──────────────────────────────────────────────

    def _is_visible(self, memory: AgentMemory, agent_id: str) -> bool:
        """检查记忆对指定Agent是否可见"""
        if memory.scope == MemoryScope.PUBLIC:
            return True
        if memory.scope == MemoryScope.PRIVATE:
            return memory.owner == agent_id
        # SHARED
        return agent_id in memory.shared_with or memory.owner == agent_id

    def _emit_sync(self, agent_id: str, memory_id: str, action: str) -> None:
        """发射同步事件"""
        event = SyncEvent(
            agent_id=agent_id,
            memory_id=memory_id,
            action=action,
            timestamp=time.time(),
        )
        with self._lock:
            self._sync_events.append(event)

        self._trigger_sync_callbacks(agent_id, memory_id)

    def _sync_memory_to_targets(self, memory, source_agent, targets, strategy):
        synced = 0
        for target in targets:
            if memory.scope == MemoryScope.PUBLIC or target in memory.shared_with:
                event = SyncEvent(
                    agent_id=source_agent,
                    memory_id=memory.id,
                    action="sync",
                    timestamp=time.time(),
                )
                with self._lock:
                    self._sync_events.append(event)

                if strategy == SyncStrategy.IMMEDIATE and target in self._sync_handlers:
                    try:
                        self._sync_handlers[target](memory)
                    except Exception as e:
                        logger.error(f"Sync handler error for {target}: {e}")
                synced += 1
        return synced

    def _trigger_sync_callbacks(self, agent_id, memory_id):
        for target, handler in self._sync_handlers.items():
            if target != agent_id:
                try:
                    memory = self._memories.get(memory_id)
                    if memory and self._is_visible(memory, target):
                        handler(memory)
                except Exception as e:
                    logger.error(f"Sync callback error for {target}: {e}")

    def _try_find_conflict(self, a: AgentMemory, b: AgentMemory) -> dict | None:
        if not self._texts_may_conflict(a.content, b.content):
            return None
        conf = self._compute_conflict(a, b)
        if conf["confidence"] > 0.3:
            return {
                "memory_a": a.id,
                "memory_b": b.id,
                "agent_a": a.owner,
                "agent_b": b.owner,
                "description": conf["description"],
                "severity": conf["severity"],
                "confidence": conf["confidence"],
            }
        return None

    def _find_conflict_pairs(self, memories):
        conflicts = []
        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                conflict = self._try_find_conflict(memories[i], memories[j])
                if conflict:
                    conflicts.append(conflict)
        return conflicts

    def _detect_new_conflicts(self, new_memory: AgentMemory) -> list[dict[str, Any]]:
        """检测新记忆与已有记忆的冲突"""
        conflicts = []
        with self._lock:
            existing = [
                m for m in self._memories.values() if m.id != new_memory.id and self._is_visible(m, new_memory.owner)
            ]

        for mem in existing:
            if not self._texts_may_conflict(new_memory.content, mem.content):
                continue
            conf = self._compute_conflict(new_memory, mem)
            if conf["confidence"] > 0.3:
                conflicts.append(
                    {
                        "memory_a": new_memory.id,
                        "memory_b": mem.id,
                        "description": conf["description"],
                        "severity": conf["severity"],
                        "confidence": conf["confidence"],
                    }
                )
        return conflicts

    def _texts_may_conflict(self, text_a: str, text_b: str) -> bool:
        """快速判断两段文本是否可能冲突（基于关键词重叠）"""
        import re

        words_a = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_a.lower()))
        words_b = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_b.lower()))
        if not words_a or not words_b:
            return False
        return len(words_a & words_b) >= 2

    def _compute_conflict(self, mem_a: AgentMemory, mem_b: AgentMemory) -> dict[str, Any]:
        """计算两段内容的冲突程度"""
        import re

        # 矛盾词对
        contradiction_pairs = [
            (["是", "正确", "成功", "支持", "增加"], ["不是", "错误", "失败", "不支持", "减少"]),
            (["yes", "true", "success", "enable"], ["no", "false", "fail", "disable"]),
        ]

        text_a = mem_a.content.lower()
        text_b = mem_b.content.lower()
        contradictions = 0

        for pos_words, neg_words in contradiction_pairs:
            a_pos = any(w in text_a for w in pos_words)
            b_neg = any(w in text_b for w in neg_words)
            a_neg = any(w in text_a for w in neg_words)
            b_pos = any(w in text_b for w in pos_words)
            if (a_pos and b_neg) or (a_neg and b_pos):
                contradictions += 1

        # 主题重叠
        words_a = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_a))
        words_b = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_b))
        overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)

        if contradictions == 0:
            if overlap > 0.7:
                return {
                    "confidence": round(overlap * 0.3, 4),
                    "severity": "potential",
                    "description": "语义高度相似，可能存在不一致",
                }
            return {"confidence": 0.0, "severity": "none", "description": ""}

        confidence = min(1.0, contradictions * 0.4 + overlap * 0.2)
        if confidence > 0.8:
            severity = "critical"
        elif confidence > 0.6:
            severity = "major"
        elif confidence > 0.3:
            severity = "minor"
        else:
            severity = "potential"

        return {
            "confidence": round(confidence, 4),
            "severity": severity,
            "description": f"发现 {contradictions} 处矛盾表述",
        }


# 全局单例
_multi_agent_memory: MultiAgentMemory | None = None


def get_multi_agent_memory(**kwargs) -> MultiAgentMemory:
    """获取多Agent协作记忆单例"""
    global _multi_agent_memory
    if _multi_agent_memory is None:
        _multi_agent_memory = MultiAgentMemory(**kwargs)
    return _multi_agent_memory
