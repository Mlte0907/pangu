"""盘古记忆版本控制 — 跟踪记忆如何演变

核心功能：
1. 版本记录：记录每次记忆变更
2. 版本对比：比较不同版本的差异
3. 版本回滚：恢复到之前的版本
4. 变更历史：完整的变更轨迹
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.versioning")


@dataclass
class MemoryVersion:
    """记忆版本"""

    version: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    change_type: str = "update"  # create / update / compress / merge


class MemoryVersionControl:
    """记忆版本控制 — 跟踪记忆演变"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._versions: dict[str, list[MemoryVersion]] = {}  # memory_id -> [versions]
        self._max_versions: int = 10

    def record_version(
        self, memory_id: str, content: str, change_type: str = "update", metadata: dict[str, Any] | None = None
    ) -> MemoryVersion:
        """记录记忆版本"""
        if memory_id not in self._versions:
            self._versions[memory_id] = []

        version_num = len(self._versions[memory_id]) + 1
        version = MemoryVersion(
            version=version_num,
            content=content,
            metadata=metadata or {},
            timestamp=time.time(),
            change_type=change_type,
        )

        self._versions[memory_id].append(version)

        # 限制版本数量
        if len(self._versions[memory_id]) > self._max_versions:
            self._versions[memory_id] = self._versions[memory_id][-self._max_versions :]

        return version

    def get_versions(self, memory_id: str) -> list[MemoryVersion]:
        """获取记忆的所有版本"""
        return self._versions.get(memory_id, [])

    def get_latest_version(self, memory_id: str) -> MemoryVersion | None:
        """获取最新版本"""
        versions = self._versions.get(memory_id, [])
        return versions[-1] if versions else None

    def get_version(self, memory_id: str, version: int) -> MemoryVersion | None:
        """获取指定版本"""
        versions = self._versions.get(memory_id, [])
        for v in versions:
            if v.version == version:
                return v
        return None

    def compare_versions(self, memory_id: str, v1: int, v2: int) -> dict:
        """比较两个版本的差异"""
        ver1 = self.get_version(memory_id, v1)
        ver2 = self.get_version(memory_id, v2)

        if not ver1 or not ver2:
            return {"error": "Version not found"}

        # 简单的文本差异
        content_changed = ver1.content != ver2.content
        metadata_changed = ver1.metadata != ver2.metadata

        # 计算相似度
        if ver1.content and ver2.content:
            common = set(ver1.content) & set(ver2.content)
            total = set(ver1.content) | set(ver2.content)
            similarity = len(common) / max(len(total), 1)
        else:
            similarity = 0.0

        return {
            "v1": v1,
            "v2": v2,
            "content_changed": content_changed,
            "metadata_changed": metadata_changed,
            "similarity": round(similarity, 3),
            "time_diff_hours": round((ver2.timestamp - ver1.timestamp) / 3600, 1),
        }

    def rollback(self, memory_id: str, version: int) -> MemoryVersion | None:
        """回滚到指定版本"""
        ver = self.get_version(memory_id, version)
        if not ver:
            return None

        # 记录回滚操作
        new_version = self.record_version(
            memory_id,
            ver.content,
            change_type="rollback",
            metadata={"rollback_to": version, "original_content": ver.content},
        )

        return new_version

    def get_change_history(self, memory_id: str) -> list[dict]:
        """获取记忆变更历史"""
        versions = self._versions.get(memory_id, [])
        history = []
        for v in versions:
            history.append(
                {
                    "version": v.version,
                    "change_type": v.change_type,
                    "timestamp": datetime.fromtimestamp(v.timestamp).isoformat(),
                    "content_preview": v.content[:50] + "..." if len(v.content) > 50 else v.content,
                }
            )
        return history


# 全局单例
_version_control: MemoryVersionControl | None = None


def get_version_control(config: PanguConfig = None) -> MemoryVersionControl:
    """获取全局版本控制实例"""
    global _version_control
    if _version_control is None:
        _version_control = MemoryVersionControl(config)
    return _version_control
