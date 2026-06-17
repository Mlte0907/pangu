"""盘古流式索引 — 增量索引 + WAL 日志 + 断点续传

从伏羲移植：流式增量索引引擎，支持大规模记忆的高效索引更新。
- WAL（Write-Ahead Log）日志保证崩溃恢复
- 增量索引避免全量重建
- 断点续传支持故障恢复

纯大脑能力：只做索引管理，不执行搜索任务。
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger("pangu.memory.streaming_index")


class StreamingIndexer:
    """流式索引引擎 — 增量索引 + WAL 日志

    工作流程:
    1. 扫描未索引的新记忆
    2. 将增量写入 WAL 文件
    3. 后台合并 WAL 到主索引
    4. 支持断点续传和故障恢复
    """

    def __init__(self, config=None, index_dir: str = "~/.pangu/index"):
        self.config = config
        self.index_dir = os.path.expanduser(index_dir)
        os.makedirs(self.index_dir, exist_ok=True)
        self._wal_path = os.path.join(self.index_dir, "index_wal.jsonl")
        self._checkpoint_path = os.path.join(self.index_dir, "index_checkpoint.json")
        self._indexed_ids: set[str] = set()
        self._last_indexed_id: str = ""
        self._total_indexed: int = 0
        self._restore_checkpoint()

    def scan_new(self, drawers: list) -> list:
        """扫描未索引的新记忆"""
        new_items = []
        for d in drawers:
            if d.id not in self._indexed_ids:
                new_items.append(d)
        return new_items

    def index(self, drawers: list, embedder=None) -> dict:
        """增量索引主入口

        Returns:
            {"status": "completed", "scanned": int, "indexed": int, ...}
        """
        new_items = self.scan_new(drawers)
        if not new_items:
            return {"status": "idle", "scanned": 0, "indexed": 0,
                    "timestamp": datetime.now().isoformat()}

        # 写入 WAL
        wal_entries = self._write_wal(new_items, embedder)

        # 更新 checkpoint
        if new_items:
            self._last_indexed_id = new_items[-1].id
            self._total_indexed += len(new_items)
            for item in new_items:
                self._indexed_ids.add(item.id)
            self._save_checkpoint()

        return {
            "status": "completed",
            "scanned": len(new_items),
            "indexed": wal_entries,
            "total_indexed": self._total_indexed,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_wal_entry(self, item, embedder=None) -> dict:
        """构建单条 WAL 条目"""
        now = datetime.now().isoformat()
        entry = {
            "id": item.id,
            "content": item.content[:500],
            "wing": item.wing,
            "room": item.room,
            "importance": item.importance,
            "tags": item.tags,
            "created_at": item.created_at,
            "indexed_at": now,
        }
        self._try_embed_item(entry, item, embedder)
        return entry

    def _write_wal(self, items: list, embedder=None) -> int:
        """写入 WAL 日志"""
        entries = 0

        try:
            with open(self._wal_path, "a", encoding="utf-8") as f:
                for item in items:
                    entry = self._build_wal_entry(item, embedder)
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    entries += 1
        except OSError as e:
            logger.warning(f"WAL write error: {e}")

        return entries

    def merge_wal(self) -> int:
        """合并 WAL 到主索引（清理旧日志）"""
        if not os.path.exists(self._wal_path):
            return 0

        try:
            # 读取 WAL 行数
            with open(self._wal_path, encoding="utf-8") as f:
                lines = f.readlines()
            count = len(lines)

            # 备份后清空 WAL
            backup_path = self._wal_path + ".bak"
            os.rename(self._wal_path, backup_path)
            logger.info(f"WAL merged: {count} entries backed up to {backup_path}")
            return count
        except OSError as e:
            logger.warning(f"WAL merge error: {e}")
            return 0

    def rebuild_from_wal(self) -> int:
        """从 WAL 重建索引（用于故障恢复）"""
        backup_path = self._wal_path + ".bak"
        paths = [p for p in [backup_path, self._wal_path] if os.path.exists(p)]

        if not paths:
            return 0

        restored = 0
        for path in paths:
            restored += self._restore_from_file(path)

        self._total_indexed = restored
        logger.info(f"Index rebuilt from WAL: {restored} entries")
        return restored

    def _save_checkpoint(self):
        """保存索引断点"""
        try:
            checkpoint = {
                "last_indexed_id": self._last_indexed_id,
                "total_indexed": self._total_indexed,
                "indexed_count": len(self._indexed_ids),
                "timestamp": datetime.now().isoformat(),
            }
            with open(self._checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning(f"Checkpoint save error: {e}")

    def _restore_checkpoint(self):
        """从断点恢复"""
        if not os.path.exists(self._checkpoint_path):
            return

        try:
            with open(self._checkpoint_path, encoding="utf-8") as f:
                checkpoint = json.load(f)
            self._last_indexed_id = checkpoint.get("last_indexed_id", "")
            self._total_indexed = checkpoint.get("total_indexed", 0)
            logger.info(f"Checkpoint restored: {self._total_indexed} items indexed")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Checkpoint restore error: {e}")

    def _try_embed_item(self, entry, item, embedder):
        if embedder:
            try:
                emb = embedder.embed(item.content)
                if emb:
                    entry["embedding"] = emb
            except Exception:
                pass

    def _restore_from_file(self, path):
        count = 0
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        self._indexed_ids.add(entry["id"])
                        count += 1
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return count

    def stats(self) -> dict:
        """索引统计"""
        wal_size = 0
        if os.path.exists(self._wal_path):
            wal_size = os.path.getsize(self._wal_path)

        return {
            "indexed_ids": len(self._indexed_ids),
            "total_indexed": self._total_indexed,
            "last_indexed_id": self._last_indexed_id[:8] if self._last_indexed_id else None,
            "wal_size_bytes": wal_size,
            "wal_size_mb": round(wal_size / 1024 / 1024, 2),
        }
