"""盘古记忆进化模块

提供记忆质量评估、相关记忆匹配、记忆替换、快照保存功能。
每次写入记忆时，自动匹配相关记忆，如果新记忆比旧记忆更优，则自动替换。
旧版本保留为快照，方便复查。
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pangu.memory.evolution")


@dataclass
class MemorySnapshot:
    """记忆快照 — 被替换的旧版本记忆"""

    snapshot_id: str
    memory_id: str  # 关联的记忆ID
    version: int  # 版本号
    content: str  # 旧版本内容
    quality_score: float  # 旧版本质量分数
    created_at: str  # 原记忆创建时间
    replaced_at: str  # 替换时间
    replaced_by: str = ""  # 替换它的记忆ID
    reason: str = ""  # 替换原因

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "memory_id": self.memory_id,
            "version": self.version,
            "content": self.content,
            "quality_score": self.quality_score,
            "created_at": self.created_at,
            "replaced_at": self.replaced_at,
            "replaced_by": self.replaced_by,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemorySnapshot":
        return cls(
            snapshot_id=data.get("snapshot_id", ""),
            memory_id=data.get("memory_id", ""),
            version=data.get("version", 1),
            content=data.get("content", ""),
            quality_score=data.get("quality_score", 0.0),
            created_at=data.get("created_at", ""),
            replaced_at=data.get("replaced_at", ""),
            replaced_by=data.get("replaced_by", ""),
            reason=data.get("reason", ""),
        )


class MemoryEvolution:
    """记忆进化引擎"""

    def __init__(self, snapshots_path: str = None):
        if snapshots_path is None:
            try:
                from pangu.core.config import PanguConfig

                self.snapshots_path = Path(PanguConfig.load().base_dir) / "memory_snapshots.json"
            except Exception:
                self.snapshots_path = Path.home() / ".pangu" / "memory_snapshots.json"
        else:
            self.snapshots_path = Path(snapshots_path)
        self._ensure_file()

    def _ensure_file(self):
        """确保 snapshots.json 存在且权限正确"""
        if not self.snapshots_path.exists():
            self.snapshots_path.parent.mkdir(parents=True, exist_ok=True)
            self._write([])
        else:
            current = oct(self.snapshots_path.stat().st_mode)[-3:]
            if current != "600":
                self.snapshots_path.chmod(0o600)

    def _read(self) -> list[dict]:
        try:
            with open(self.snapshots_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, snapshots: list[dict]):
        tmp = self.snapshots_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshots, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.snapshots_path)
        self.snapshots_path.chmod(0o600)

    def evaluate_memory_quality(self, memory: dict) -> float:
        """评估记忆质量

        从四个维度评估：
        1. 内容完整性（0-0.3）：内容长度
        2. 信息密度（0-0.3）：是否包含步骤、代码、错误处理等
        3. 时效性（0-0.2）：创建时间越新分数越高
        4. 使用频率（0-0.2）：被访问次数
        """
        score = 0.0

        # 1. 内容完整性（0-0.3）
        content_length = len(memory.get("content", ""))
        if content_length > 500:
            score += 0.3
        elif content_length > 200:
            score += 0.2
        elif content_length > 50:
            score += 0.1

        # 2. 信息密度（0-0.3）
        content = memory.get("content", "")
        # 包含具体步骤
        if "步骤" in content or "1." in content or "2." in content:
            score += 0.1
        # 包含代码示例
        if "```" in content or "代码" in content or "命令" in content:
            score += 0.1
        # 包含错误处理
        if "错误" in content or "解决" in content or "修复" in content:
            score += 0.1

        # 3. 时效性（0-0.2）
        created_at = memory.get("created_at", "")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                days_old = (datetime.now() - created.replace(tzinfo=None)).days
                if days_old < 7:
                    score += 0.2
                elif days_old < 30:
                    score += 0.15
                elif days_old < 90:
                    score += 0.1
            except (ValueError, TypeError):
                pass

        # 4. 使用频率（0-0.2）
        access_count = memory.get("access_count", 0)
        if isinstance(access_count, (int, float)):
            if access_count > 10:
                score += 0.2
            elif access_count > 5:
                score += 0.15
            elif access_count > 0:
                score += 0.1

        return min(score, 1.0)

    def find_related_memories(self, new_memory: dict, all_memories: list[dict], threshold: float = 0.3) -> list[dict]:
        """查找相关记忆

        使用简单的文本相似度匹配，找到与新记忆相关的旧记忆。
        """
        new_content = new_memory.get("content", "").lower()
        new_tags = set(new_memory.get("tags", []))

        related = []
        for mem in all_memories:
            # 跳过自身
            if mem.get("id") == new_memory.get("id"):
                continue

            old_content = mem.get("content", "").lower()
            old_tags = set(mem.get("tags", []))

            # 计算相似度
            score = 0.0

            # 标签重叠
            if new_tags and old_tags:
                tag_overlap = len(new_tags & old_tags) / max(len(new_tags | old_tags), 1)
                score += tag_overlap * 0.4

            # 内容关键词重叠
            new_words = set(new_content.split())
            old_words = set(old_content.split())
            if new_words and old_words:
                word_overlap = len(new_words & old_words) / max(len(new_words | old_words), 1)
                score += word_overlap * 0.6

            if score >= threshold:
                related.append({"memory": mem, "similarity": score})

        # 按相似度排序
        related.sort(key=lambda x: x["similarity"], reverse=True)
        return [r["memory"] for r in related[:5]]  # 最多返回5个相关记忆

    def should_replace(self, new_quality: float, old_quality: float) -> bool:
        """判断是否应该替换旧记忆

        新记忆质量高出10%以上时替换。
        """
        return new_quality > old_quality * 1.1

    def save_snapshot(self, memory: dict, replaced_by: str = "", reason: str = "") -> MemorySnapshot:
        """保存记忆快照"""
        import secrets

        snapshot = MemorySnapshot(
            snapshot_id=f"snap_{secrets.token_hex(8)}",
            memory_id=memory.get("id", ""),
            version=memory.get("version", 1),
            content=memory.get("content", ""),
            quality_score=memory.get("quality_score", 0.0),
            created_at=memory.get("created_at", ""),
            replaced_at=datetime.now().isoformat(),
            replaced_by=replaced_by,
            reason=reason or "被更优记忆替换",
        )

        # 保存到快照表
        snapshots = self._read()
        snapshots.append(snapshot.to_dict())
        self._write(snapshots)

        logger.info(f"保存记忆快照: {snapshot.snapshot_id} (记忆 {snapshot.memory_id} v{snapshot.version})")
        return snapshot

    def get_snapshots(self, memory_id: str = None) -> list[MemorySnapshot]:
        """获取记忆快照列表"""
        snapshots = self._read()
        result = []
        for s in snapshots:
            if memory_id and s.get("memory_id") != memory_id:
                continue
            result.append(MemorySnapshot.from_dict(s))
        return result

    def get_snapshot_count(self, memory_id: str) -> int:
        """获取某条记忆的快照数量"""
        snapshots = self._read()
        return sum(1 for s in snapshots if s.get("memory_id") == memory_id)

    def get_latest_snapshot(self, memory_id: str) -> MemorySnapshot | None:
        """获取某条记忆的最新快照"""
        snapshots = self.get_snapshots(memory_id)
        if not snapshots:
            return None
        return max(snapshots, key=lambda s: s.replaced_at)


# 全局实例
_evolution: MemoryEvolution | None = None


def get_memory_evolution() -> MemoryEvolution:
    """获取全局 MemoryEvolution 实例"""
    global _evolution
    if _evolution is None:
        _evolution = MemoryEvolution()
    return _evolution
