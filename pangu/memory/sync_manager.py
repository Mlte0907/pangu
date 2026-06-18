"""盘古多端同步 — 支持多设备/多进程间记忆同步

核心能力：
1. 冲突检测：检测多端写入冲突
2. 冲突解决：自动解决合并冲突
3. 变更追踪：追踪记忆变更日志
4. 增量同步：只同步变更部分
5. 同步状态：追踪同步状态
"""
import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.sync_manager")


@dataclass
class ChangeEntry:
    """变更条目"""
    change_id: str
    memory_id: str
    operation: str  # create / update / delete
    timestamp: str
    source: str  # 设备/进程标识
    content_hash: str
    old_content_hash: str = ""
    resolved: bool = False


@dataclass
class SyncState:
    """同步状态"""
    device_id: str
    last_sync: str
    pending_changes: int
    synced_count: int
    conflict_count: int


class SyncManager:
    """多端同步引擎"""

    def __init__(self, config=None):
        self.config = config
        self._sync_dir = Path.home() / ".pangu" / "sync"
        self._sync_dir.mkdir(parents=True, exist_ok=True)
        self._changes: list[ChangeEntry] = []
        self._device_id = self._get_device_id()
        self._load_changes()

    def _get_device_id(self) -> str:
        """获取设备标识"""
        import platform
        import socket
        hostname = socket.gethostname()
        system = platform.system().lower()
        return f"{system}_{hostname}"

    def _load_changes(self) -> None:
        changes_file = self._sync_dir / "changes.json"
        if changes_file.exists():
            try:
                data = json.loads(changes_file.read_text())
                self._changes = [ChangeEntry(**c) for c in data]
            except Exception:
                self._changes = []

    def _save_changes(self) -> None:
        changes_file = self._sync_dir / "changes.json"
        data = [
            {"change_id": c.change_id, "memory_id": c.memory_id,
             "operation": c.operation, "timestamp": c.timestamp,
             "source": c.source, "content_hash": c.content_hash,
             "old_content_hash": c.old_content_hash, "resolved": c.resolved}
            for c in self._changes[-5000:]
        ]
        changes_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def record_change(self, memory_id: str, operation: str,
                      content: str = "", old_content: str = "") -> ChangeEntry:
        """记录变更"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16] if content else ""
        old_hash = hashlib.sha256(old_content.encode()).hexdigest()[:16] if old_content else ""

        entry = ChangeEntry(
            change_id=f"chg_{len(self._changes)}_{int(datetime.now().timestamp())}",
            memory_id=memory_id,
            operation=operation,
            timestamp=datetime.now().isoformat(),
            source=self._device_id,
            content_hash=content_hash,
            old_content_hash=old_hash,
        )
        self._changes.append(entry)
        self._save_changes()
        return entry

    def get_pending_changes(self, since: str = None) -> list[dict]:
        """获取待同步变更"""
        pending = [c for c in self._changes if not c.resolved]
        if since:
            pending = [c for c in pending if c.timestamp > since]

        return [
            {"id": c.change_id, "memory_id": c.memory_id,
             "operation": c.operation, "timestamp": c.timestamp,
             "source": c.source}
            for c in pending[-200:]
        ]

    def _check_single_remote_conflict(self, rc: dict,
                                       local_entries: list[ChangeEntry]) -> dict | None:
        """检查单个远程变更是否与本地存在冲突"""
        mem_id = rc.get("memory_id", "")
        for lc in local_entries:
            if self._is_update_conflict(lc, rc):
                return self._build_conflict_dict(mem_id, lc, rc)
        return None

    @staticmethod
    def _is_update_conflict(lc: ChangeEntry, rc: dict) -> bool:
        return (not lc.resolved and
                lc.operation == "update" and
                rc.get("operation") == "update" and
                lc.content_hash != rc.get("content_hash", ""))

    @staticmethod
    def _build_conflict_dict(mem_id: str, lc: ChangeEntry, rc: dict) -> dict:
        return {
            "memory_id": mem_id,
            "local_change": lc.change_id,
            "remote_change": rc.get("id", ""),
            "local_time": lc.timestamp,
            "remote_time": rc.get("timestamp", ""),
            "local_source": lc.source,
            "remote_source": rc.get("source", ""),
        }

    def detect_conflicts(self, remote_changes: list[dict]) -> list[dict]:
        """检测冲突"""
        conflicts = []
        local_by_memory: dict[str, list[ChangeEntry]] = {}
        for c in self._changes:
            local_by_memory.setdefault(c.memory_id, []).append(c)

        for rc in remote_changes:
            mem_id = rc.get("memory_id", "")
            local_entries = local_by_memory.get(mem_id, [])
            conflict = self._check_single_remote_conflict(rc, local_entries)
            if conflict:
                conflicts.append(conflict)

        return conflicts

    def resolve_conflict(self, change_id: str, resolution: str = "keep_latest") -> dict:
        """解决冲突"""
        for c in self._changes:
            if c.change_id == change_id:
                c.resolved = True
                self._save_changes()
                return {
                    "change_id": change_id,
                    "resolution": resolution,
                    "resolved_at": datetime.now().isoformat(),
                }

        return {"error": f"Change {change_id} not found"}

    def mark_synced(self, change_ids: list[str]) -> int:
        """标记已同步"""
        count = 0
        for c in self._changes:
            if c.change_id in change_ids:
                c.resolved = True
                count += 1
        self._save_changes()
        return count

    def get_sync_state(self) -> dict:
        """获取同步状态"""
        pending = sum(1 for c in self._changes if not c.resolved)
        synced = sum(1 for c in self._changes if c.resolved)

        sources = set(c.source for c in self._changes)
        return {
            "device_id": self._device_id,
            "total_changes": len(self._changes),
            "pending": pending,
            "synced": synced,
            "known_devices": list(sources),
        }

    def get_change_history(self, memory_id: str = None, limit: int = 20) -> list[dict]:
        """获取变更历史"""
        entries = self._changes
        if memory_id:
            entries = [c for c in entries if c.memory_id == memory_id]

        return [
            {"id": c.change_id, "memory_id": c.memory_id,
             "operation": c.operation, "timestamp": c.timestamp,
             "source": c.source, "resolved": c.resolved}
            for c in entries[-limit:]
        ]

    def get_sync_stats(self) -> dict:
        """获取同步统计"""
        return {
            "total_changes": len(self._changes),
            "pending": sum(1 for c in self._changes if not c.resolved),
            "synced": sum(1 for c in self._changes if c.resolved),
            "conflicts": sum(1 for c in self._changes if c.resolved and c.old_content_hash),
        }

    # ── 增量同步 ──

    def get_incremental_changes(self, since_timestamp: str = None, source: str = None) -> list[dict]:
        """获取增量变更 — 只返回指定时间后的未同步变更"""
        changes = [c for c in self._changes if not c.resolved]

        if since_timestamp:
            changes = [c for c in changes if c.timestamp > since_timestamp]

        if source:
            changes = [c for c in changes if c.source != source]

        return [
            {"id": c.change_id, "memory_id": c.memory_id,
             "operation": c.operation, "content_hash": c.content_hash,
             "timestamp": c.timestamp, "source": c.source}
            for c in changes
        ]

    def apply_incremental(self, remote_changes: list[dict]) -> dict:
        """应用增量变更 — 从远程设备接收变更"""
        applied = 0
        conflicts = 0
        skipped = 0

        for rc in remote_changes:
            mem_id = rc.get("memory_id", "")
            op = rc.get("operation", "")
            content_hash = rc.get("content_hash", "")

            existing = [c for c in self._changes if c.memory_id == mem_id and not c.resolved]

            if existing:
                latest = existing[-1]
                if latest.content_hash != content_hash:
                    conflicts += 1
                    continue

            entry = self.record_change(mem_id, op, content=rc.get("content", ""))
            applied += 1

        self._save_changes()
        return {"applied": applied, "conflicts": conflicts, "skipped": skipped}

    def auto_resolve_conflicts(self, strategy: str = "keep_latest") -> dict:
        """自动解决冲突"""
        unresolved = [c for c in self._changes if not c.resolved and c.old_content_hash]
        resolved = 0

        for c in unresolved:
            conflicts = [x for x in self._changes if x.memory_id == c.memory_id and x != c]
            if conflicts:
                latest = max(conflicts + [c], key=lambda x: x.timestamp)
                for other in conflicts:
                    if other != latest:
                        other.resolved = True
                latest.resolved = True
                resolved += 1

        self._save_changes()
        return {"resolved": resolved, "total_unresolved": len(unresolved)}


_sync: SyncManager | None = None


def get_sync(config=None) -> SyncManager:
    """获取全局同步管理器实例"""
    global _sync
    if _sync is None:
        _sync = SyncManager(config)
    return _sync
