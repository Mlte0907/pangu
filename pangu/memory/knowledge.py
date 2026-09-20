"""盘古知识生成模块

提供从记忆中自动提取知识、生成知识库的功能。
盘古不单单是记忆大脑，还把平台们写入的记忆生成知识存入知识库。
"""

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pangu.memory.knowledge")


@dataclass
class KnowledgeEntry:
    """知识条目 — 从记忆中提取的知识"""

    id: str
    title: str
    content: str
    category: str  # best_practice / solution / guide / insight
    source_memories: list[str] = field(default_factory=list)  # 来源记忆ID
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.8  # 知识置信度
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    usage_count: int = 0  # 被使用次数
    related_knowledge: list[str] = field(default_factory=list)  # 相关知识ID
    metadata: dict = field(default_factory=dict)  # 生成信息（模型/时间等，自动结晶用）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "source_memories": self.source_memories,
            "tags": self.tags,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
            "related_knowledge": self.related_knowledge,
            **({"metadata": self.metadata} if self.metadata else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            category=data.get("category", "insight"),
            source_memories=data.get("source_memories", []),
            tags=data.get("tags", []),
            confidence=data.get("confidence", 0.8),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            usage_count=data.get("usage_count", 0),
            related_knowledge=data.get("related_knowledge", []),
            metadata=data.get("metadata") or {},
        )


class KnowledgeEngine:
    """知识生成引擎"""

    def __init__(self, knowledge_path: str = None):
        if knowledge_path is None:
            try:
                from pangu.core.config import PanguConfig

                self.knowledge_path = Path(PanguConfig.load().base_dir) / "knowledge_base.json"
            except Exception:
                self.knowledge_path = Path.home() / ".pangu" / "knowledge_base.json"
        else:
            self.knowledge_path = Path(knowledge_path)
        self._ensure_file()

    def _ensure_file(self):
        """确保 knowledge_base.json 存在且权限正确"""
        if not self.knowledge_path.exists():
            self.knowledge_path.parent.mkdir(parents=True, exist_ok=True)
            self._write([])
        else:
            current = oct(self.knowledge_path.stat().st_mode)[-3:]
            if current != "600":
                self.knowledge_path.chmod(0o600)

    def _read(self) -> list[dict]:
        try:
            with open(self.knowledge_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, entries: list[dict]):
        tmp = self.knowledge_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.knowledge_path)
        self.knowledge_path.chmod(0o600)

    def create_knowledge(
        self,
        title: str,
        content: str,
        category: str,
        source_memories: list[str] = None,
        tags: list[str] = None,
        confidence: float = 0.8,
        metadata: dict = None,
    ) -> KnowledgeEntry:
        """创建知识条目"""
        entry = KnowledgeEntry(
            id=f"kb_{secrets.token_hex(8)}",
            title=title,
            content=content,
            category=category,
            source_memories=source_memories or [],
            tags=tags or [],
            confidence=confidence,
            metadata=metadata or {},
        )

        entries = self._read()
        entries.append(entry.to_dict())
        self._write(entries)

        logger.info(f"创建知识条目: {entry.title} ({entry.category})")
        return entry

    def update_knowledge(self, knowledge_id: str, **kwargs) -> KnowledgeEntry | None:
        """更新知识条目"""
        entries = self._read()
        for i, e in enumerate(entries):
            if e.get("id") == knowledge_id:
                for key, value in kwargs.items():
                    if key in ("title", "content", "category", "tags", "confidence"):
                        entries[i][key] = value
                entries[i]["updated_at"] = datetime.now().isoformat()
                self._write(entries)
                return KnowledgeEntry.from_dict(entries[i])
        return None

    def get_knowledge(self, knowledge_id: str) -> KnowledgeEntry | None:
        """获取知识条目"""
        entries = self._read()
        for e in entries:
            if e.get("id") == knowledge_id:
                return KnowledgeEntry.from_dict(e)
        return None

    def list_knowledge(self, category: str = None) -> list[KnowledgeEntry]:
        """列出知识条目"""
        entries = self._read()
        result = []
        for e in entries:
            if category and e.get("category") != category:
                continue
            result.append(KnowledgeEntry.from_dict(e))
        return result

    def search_knowledge(self, query: str) -> list[KnowledgeEntry]:
        """搜索知识条目"""
        entries = self._read()
        query_lower = query.lower()
        results = []
        for e in entries:
            score = 0
            if query_lower in e.get("title", "").lower():
                score += 2
            if query_lower in e.get("content", "").lower():
                score += 1
            for tag in e.get("tags", []):
                if query_lower in tag.lower():
                    score += 0.5
            if score > 0:
                result = KnowledgeEntry.from_dict(e)
                results.append((score, result))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:10]]

    def delete_knowledge(self, knowledge_id: str) -> bool:
        """删除知识条目"""
        entries = self._read()
        new_entries = [e for e in entries if e.get("id") != knowledge_id]
        if len(new_entries) < len(entries):
            self._write(new_entries)
            return True
        return False

    def get_stats(self) -> dict:
        """获取知识库统计"""
        entries = self._read()
        categories = {}
        for e in entries:
            cat = e.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "total": len(entries),
            "categories": categories,
        }


# 全局实例
_knowledge_engine: KnowledgeEngine | None = None


def get_knowledge_engine() -> KnowledgeEngine:
    """获取全局 KnowledgeEngine 实例"""
    global _knowledge_engine
    if _knowledge_engine is None:
        _knowledge_engine = KnowledgeEngine()
    return _knowledge_engine
