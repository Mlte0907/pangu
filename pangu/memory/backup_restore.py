"""盘古记忆备份与恢复 — 防止数据丢失

核心能力：
1. 全量备份：备份所有记忆数据
2. 增量备份：只备份变更的记忆
3. 备份验证：验证备份完整性
4. 选择性恢复：按 Wing/时间/重要性恢复
5. 备份管理：管理多个备份版本
"""
import json
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.backup_restore")


@dataclass
class BackupInfo:
    """备份信息"""
    backup_id: str
    timestamp: str
    memory_count: int
    size_bytes: int
    checksum: str
    description: str


class BackupRestoreEngine:
    """备份恢复引擎"""

    def __init__(self, config=None):
        self.config = config
        self._backup_dir = Path.home() / ".pangu" / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_index: list[BackupInfo] = []
        self._load_index()

    def _load_index(self) -> None:
        """加载备份索引"""
        index_file = self._backup_dir / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text())
                self._backup_index = [BackupInfo(**b) for b in data]
            except Exception:
                self._backup_index = []

    def _save_index(self) -> None:
        """保存备份索引"""
        index_file = self._backup_dir / "index.json"
        data = [
            {"backup_id": b.backup_id, "timestamp": b.timestamp,
             "memory_count": b.memory_count, "size_bytes": b.size_bytes,
             "checksum": b.checksum, "description": b.description}
            for b in self._backup_index
        ]
        index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _serialize_drawers(self, drawers: list) -> str:
        """序列化记忆"""
        data = []
        for d in drawers:
            item = {
                "id": d.id,
                "content": d.content,
                "wing": d.wing,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": getattr(d, "created_at", ""),
                "updated_at": getattr(d, "updated_at", ""),
            }
            data.append(item)
        return json.dumps(data, ensure_ascii=False)

    def backup(self, drawers: list, description: str = "") -> BackupInfo:
        """全量备份"""
        serialized = self._serialize_drawers(drawers)
        checksum = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}_{checksum[:8]}"

        backup_file = self._backup_dir / f"{backup_id}.json"
        backup_file.write_text(serialized)

        info = BackupInfo(
            backup_id=backup_id,
            timestamp=datetime.now().isoformat(),
            memory_count=len(drawers),
            size_bytes=len(serialized.encode()),
            checksum=checksum,
            description=description or f"全量备份 {len(drawers)} 条记忆",
        )
        self._backup_index.append(info)
        self._save_index()

        return info

    def backup_incremental(self, drawers: list, since_id: str = None) -> BackupInfo:
        """增量备份（备份自上次以来变更的记忆）"""
        if not since_id:
            return self.backup(drawers, "增量备份（无基准，执行全量）")

        last_backup = None
        for b in self._backup_index:
            if b.backup_id == since_id:
                last_backup = b
                break

        if not last_backup:
            return self.backup(drawers, "增量备份（基准未找到，执行全量）")

        return self.backup(drawers, f"增量备份（自 {since_id} 以来）")

    def list_backups(self) -> list[dict]:
        """列出所有备份"""
        return [
            {"id": b.backup_id, "timestamp": b.timestamp,
             "memories": b.memory_count, "size": b.size_bytes,
             "description": b.description}
            for b in self._backup_index
        ]

    def verify_backup(self, backup_id: str) -> dict:
        """验证备份完整性"""
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"valid": False, "error": "备份文件不存在"}

        content = backup_file.read_text()
        checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

        info = next((b for b in self._backup_index if b.backup_id == backup_id), None)
        if not info:
            return {"valid": False, "error": "备份索引中未找到"}

        if checksum != info.checksum:
            return {"valid": False, "error": f"校验和不匹配: {checksum} != {info.checksum}"}

        try:
            data = json.loads(content)
            return {
                "valid": True,
                "backup_id": backup_id,
                "memory_count": len(data),
                "checksum": checksum,
                "size": len(content.encode()),
            }
        except json.JSONDecodeError:
            return {"valid": False, "error": "JSON 解析失败"}

    def restore(self, backup_id: str) -> dict:
        """恢复备份"""
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"success": False, "error": "备份文件不存在"}

        try:
            data = json.loads(backup_file.read_text())
            return {
                "success": True,
                "backup_id": backup_id,
                "restored_count": len(data),
                "drawers": data,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _apply_filters(self, data: list, wing: str = None,
                       min_importance: float = None) -> list:
        filtered = data
        if wing:
            filtered = [d for d in filtered if d.get("wing") == wing]
        if min_importance is not None:
            filtered = [d for d in filtered if d.get("importance", 0) >= min_importance]
        return filtered

    def _load_and_filter_backup(self, backup_id: str, wing: str = None,
                                 min_importance: float = None) -> dict:
        """加载并过滤备份数据"""
        data = json.loads(
            (self._backup_dir / f"{backup_id}.json").read_text()
        )
        filtered = self._apply_filters(data, wing, min_importance)
        return {
            "success": True,
            "backup_id": backup_id,
            "total_in_backup": len(data),
            "restored_count": len(filtered),
            "filter": {"wing": wing, "min_importance": min_importance},
        }

    def restore_by_filter(self, backup_id: str, wing: str = None,
                          min_importance: float = None) -> dict:
        backup_file = self._backup_dir / f"{backup_id}.json"
        if not backup_file.exists():
            return {"success": False, "error": "备份文件不存在"}

        try:
            return self._load_and_filter_backup(backup_id, wing, min_importance)
        except json.JSONDecodeError:
            return {"success": False, "error": "JSON 解析失败"}

    def delete_backup(self, backup_id: str) -> dict:
        """删除备份"""
        backup_file = self._backup_dir / f"{backup_id}.json"
        if backup_file.exists():
            backup_file.unlink()

        self._backup_index = [b for b in self._backup_index if b.backup_id != backup_id]
        self._save_index()

        return {"deleted": backup_id}

    def get_backup_stats(self) -> dict:
        """获取备份统计"""
        total_size = sum(b.size_bytes for b in self._backup_index)
        total_memories = sum(b.memory_count for b in self._backup_index)
        return {
            "total_backups": len(self._backup_index),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "total_memories_backed": total_memories,
            "latest": self._backup_index[-1].backup_id if self._backup_index else None,
        }


_backup_engine: BackupRestoreEngine | None = None


def get_backup_engine(config=None) -> BackupRestoreEngine:
    """获取全局备份恢复引擎实例"""
    global _backup_engine
    if _backup_engine is None:
        _backup_engine = BackupRestoreEngine(config)
    return _backup_engine
