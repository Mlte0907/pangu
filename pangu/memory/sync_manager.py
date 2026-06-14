"""盘古跨平台同步管理器 — 增量同步与冲突解决
============================================
支持多设备间记忆的增量同步，采用离线优先设计。
联网时自动同步本地变更，离线操作会在联网后自动合并。

支持：
- 基于时间戳和哈希的增量同步协议
- 冲突自动解决策略（last-write-wins / merge / manual）
- 离线优先设计（本地优先，联网时同步）
- 同步状态追踪和日志记录
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


class SyncStrategy(str, Enum):
    """同步冲突解决策略"""
    LAST_WRITE_WINS = "last_write_wins"  # 最后写入者获胜
    MERGE = "merge"                       # 自动合并
    MANUAL = "manual"                     # 手动解决


class SyncState(str, Enum):
    """同步状态"""
    IDLE = "idle"                 # 空闲
    SYNCING = "syncing"           # 同步中
    CONFLICT = "conflict"         # 存在冲突
    OFFLINE = "offline"           # 离线
    ERROR = "error"               # 错误


@dataclass
class MemoryRecord:
    """同步记录条目"""
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    hash: str = ""  # 内容哈希
    version: int = 1  # 版本号
    device_id: str = ""  # 设备标识

    def compute_hash(self) -> str:
        """计算内容哈希"""
        self.hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        return self.hash


@dataclass
class SyncConflict:
    """同步冲突"""
    id: str
    local_record: MemoryRecord
    remote_record: MemoryRecord
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved: bool = False
    resolution: str = ""  # 解决方式


@dataclass
class SyncLog:
    """同步日志"""
    timestamp: str
    direction: str  # "push" / "pull" / "conflict"
    record_id: str
    status: str  # "success" / "failed" / "pending"
    message: str = ""


class SyncManager:
    """跨平台同步管理器

    实现增量同步协议，支持离线优先设计。
    本地操作立即生效，联网时批量同步远程变更。
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.state = SyncState.IDLE
        self.strategy = SyncStrategy.LAST_WRITE_WINS
        self.device_id = self._generate_device_id()
        self._local_store: dict[str, MemoryRecord] = {}
        self._remote_store: dict[str, MemoryRecord] = {}
        self._conflicts: list[SyncConflict] = []
        self._log: list[SyncLog] = []
        self._pending_changes: list[MemoryRecord] = []
        self._is_online = False

    def _generate_device_id(self) -> str:
        """生成唯一设备标识"""
        import platform
        node = platform.node()
        return hex_digest(node)[:8]

    def set_online(self, online: bool) -> None:
        """设置在线状态"""
        self._is_online = online
        if online and self.state == SyncState.OFFLINE:
            self.state = SyncState.IDLE
        elif not online:
            self.state = SyncState.OFFLINE

    def add_memory(self, memory: MemoryRecord) -> None:
        """添加记忆到本地存储（立即生效）"""
        memory.device_id = self.device_id
        memory.compute_hash()
        self._local_store[memory.id] = memory
        self._pending_changes.append(memory)

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        """获取记忆"""
        return self._local_store.get(memory_id)

    def sync(self) -> dict[str, Any]:
        """执行同步操作

        Returns:
            同步结果摘要
        """
        if not self._is_online:
            self.state = SyncState.OFFLINE
            return {"status": "offline", "pending": len(self._pending_changes)}

        self.state = SyncState.SYNCING
        result = {
            "pushed": 0,
            "pulled": 0,
            "conflicts": 0,
            "total": 0
        }

        try:
            # 推送本地变更
            for record in self._pending_changes:
                remote = self._remote_store.get(record.id)
                if remote is None:
                    self._remote_store[record.id] = record
                    result["pushed"] += 1
                    self._log_sync("push", record.id, "success", "新增记录")
                elif self._detect_conflict(record, remote):
                    result["conflicts"] += 1
                    self._log_sync("conflict", record.id, "pending", "检测到冲突")
                else:
                    self._remote_store[record.id] = record
                    result["pushed"] += 1
                    self._log_sync("push", record.id, "success", "更新记录")

            # 拉取远程变更（模拟）
            for rid, remote in self._remote_store.items():
                local = self._local_store.get(rid)
                if local is None:
                    self._local_store[rid] = remote
                    result["pulled"] += 1
                    self._log_sync("pull", rid, "success", "拉取新记录")
                elif local.hash != remote.hash and remote.timestamp > local.timestamp:
                    self._local_store[rid] = remote
                    result["pulled"] += 1
                    self._log_sync("pull", rid, "success", "拉取更新")

            result["total"] = len(self._local_store)
            self._pending_changes.clear()
            self.state = SyncState.IDLE

        except Exception as e:
            self.state = SyncState.ERROR
            result["error"] = str(e)

        return result

    def _detect_conflict(self, local: MemoryRecord, remote: MemoryRecord) -> bool:
        """检测冲突：内容不同且都有更新"""
        if local.hash == remote.hash:
            return False
        # 如果远端比本地新，视为冲突（需要策略决定）
        if remote.timestamp > local.timestamp and remote.version >= local.version:
            conflict = SyncConflict(
                id=hex_digest(f"{local.id}-{remote.id}")[:8],
                local_record=local,
                remote_record=remote
            )
            self._conflicts.append(conflict)
            return True
        return False

    def resolve_conflict(self, conflict_id: str, resolution: str = "") -> bool:
        """解决冲突

        Args:
            conflict_id: 冲突 ID
            resolution: 解决内容（manual 模式下使用）
        """
        for conflict in self._conflicts:
            if conflict.id == conflict_id and not conflict.resolved:
                if self.strategy == SyncStrategy.LAST_WRITE_WINS:
                    # 选择较新的记录
                    winner = (conflict.local_record
                              if conflict.local_record.timestamp > conflict.remote_record.timestamp
                              else conflict.remote_record)
                    self._local_store[winner.id] = winner
                    conflict.resolved = True
                    conflict.resolution = "last_write_wins"
                elif self.strategy == SyncStrategy.MERGE:
                    # 简单合并：保留两者内容
                    merged_content = (
                        f"{conflict.local_record.content}\n---\n{conflict.remote_record.content}"
                    )
                    merged = MemoryRecord(
                        id=conflict.local_record.id,
                        content=merged_content,
                        metadata={**conflict.local_record.metadata, **conflict.remote_record.metadata},
                        timestamp=datetime.now().isoformat(),
                        version=max(conflict.local_record.version, conflict.remote_record.version) + 1
                    )
                    merged.compute_hash()
                    self._local_store[merged.id] = merged
                    conflict.resolved = True
                    conflict.resolution = "merged"
                elif self.strategy == SyncStrategy.MANUAL:
                    if resolution:
                        merged = MemoryRecord(
                            id=conflict.local_record.id,
                            content=resolution,
                            timestamp=datetime.now().isoformat(),
                            version=max(conflict.local_record.version, conflict.remote_record.version) + 1
                        )
                        merged.compute_hash()
                        self._local_store[merged.id] = merged
                        conflict.resolved = True
                        conflict.resolution = "manual"
                    else:
                        return False  # 需要手动提供内容
                return True
        return False

    def _log_sync(self, direction: str, record_id: str, status: str, message: str) -> None:
        """记录同步日志"""
        log = SyncLog(
            timestamp=datetime.now().isoformat(),
            direction=direction,
            record_id=record_id,
            status=status,
            message=message
        )
        self._log.append(log)

    def get_pending_conflicts(self) -> list[SyncConflict]:
        """获取未解决的冲突"""
        return [c for c in self._conflicts if not c.resolved]

    def get_sync_history(self, limit: int = 50) -> list[SyncLog]:
        """获取同步历史"""
        return self._log[-limit:]

    def get_status(self) -> dict[str, Any]:
        """获取同步状态"""
        return {
            "state": self.state.value,
            "strategy": self.strategy.value,
            "device_id": self.device_id,
            "is_online": self._is_online,
            "local_count": len(self._local_store),
            "pending_changes": len(self._pending_changes),
            "pending_conflicts": len(self.get_pending_conflicts()),
            "total_synced": len(self._log)
        }

    def set_strategy(self, strategy: SyncStrategy) -> None:
        """设置冲突解决策略"""
        self.strategy = strategy
        Drawer.info(f"同步策略已切换为: {strategy.value}")

    def export_snapshot(self) -> dict[str, Any]:
        """导出同步快照（用于备份）"""
        return {
            "device_id": self.device_id,
            "timestamp": datetime.now().isoformat(),
            "records": {rid: {"content": r.content, "hash": r.hash, "version": r.version}
                       for rid, r in self._local_store.items()},
            "conflicts": len(self.get_pending_conflicts())
        }

    def import_snapshot(self, snapshot: dict[str, Any]) -> int:
        """导入同步快照

        Returns:
            导入的记录数
        """
        count = 0
        for rid, data in snapshot.get("records", {}).items():
            record = MemoryRecord(
                id=rid,
                content=data["content"],
                hash=data["hash"],
                version=data["version"]
            )
            self._local_store[rid] = record
            count += 1
        Drawer.info(f"导入快照: {count} 条记录")
        return count
