"""盘古记忆迁移引擎 — 导出/导入/备份恢复
==============================================
支持记忆数据的完整迁移：
- 导出为 JSON/ZIP 格式
- 从 JSON/ZIP 导入
- 增量备份与恢复
- 跨实例迁移
"""
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer, WikiPage
from ..memory.knowledge_graph import KnowledgeGraph
from ..memory.layers import MemoryStack
from ..wiki.engine import WikiEngine


class MemoryExporter:
    """记忆导出器"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def export_all(self, output_path: str, format: str = "json") -> str:
        """导出所有记忆数据

        Args:
            output_path: 输出路径（文件或目录）
            format: 导出格式 json / zip

        Returns:
            导出的文件路径
        """
        memory = MemoryStack(self.config)
        wiki = WikiEngine(self.config)
        kg = KnowledgeGraph(self.config)
        palace = None
        try:
            from ..core.palace import Palace
            palace = Palace(self.config.palace_path)
        except Exception:
            pass

        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "source": "pangu",
            "memories": [d.to_dict() for d in memory.get_drawers()],
            "wiki_pages": [p.to_dict() for p in wiki.list_pages()],
            "knowledge_graph": kg.export_graph() if kg else {},
            "identity": memory.l0.render(),
        }

        if palace:
            export_data["palace"] = palace.export_structure()

        if format == "zip":
            output_path = output_path.replace(".json", ".zip") if not output_path.endswith(".zip") else output_path
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("pangu_export.json", json.dumps(export_data, ensure_ascii=False, indent=2))
            return output_path

        if not output_path.endswith(".json"):
            output_path += ".json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return output_path

    def export_memories(self, output_path: str, wing: str = None, room: str = None) -> str:
        """导出指定范围的记忆"""
        memory = MemoryStack(self.config)
        drawers = memory.get_drawers()

        if wing:
            drawers = [d for d in drawers if d.wing == wing]
        if room:
            drawers = [d for d in drawers if d.room == room]

        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "memories": [d.to_dict() for d in drawers],
        }

        if not output_path.endswith(".json"):
            output_path += ".json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return output_path


class MemoryImporter:
    """记忆导入器"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def import_from_file(self, file_path: str, merge: bool = True) -> dict:
        """从文件导入记忆

        Args:
            file_path: JSON 或 ZIP 文件路径
            merge: 是否合并（True）还是替换（False）

        Returns:
            导入统计
        """
        data = self._load_file(file_path)
        if not data:
            return {"error": "无法读取文件"}

        stats = {"memories_imported": 0, "wiki_pages_imported": 0, "entities_imported": 0}

        # 导入记忆
        if "memories" in data:
            memory = MemoryStack(self.config)
            imported = [Drawer.from_dict(d) for d in data["memories"]]
            if not merge:
                # 清空现有记忆
                existing = memory.get_drawers()
                memory.remove_drawers([d.id for d in existing])
            memory.add_drawers(imported)
            stats["memories_imported"] = len(imported)

        # 导入 Wiki 页面
        if "wiki_pages" in data:
            wiki = WikiEngine(self.config)
            for page_dict in data["wiki_pages"]:
                page = WikiPage.from_dict(page_dict)
                wiki.create_page(page)
                stats["wiki_pages_imported"] += 1

        # 导入身份
        if "identity" in data:
            memory = MemoryStack(self.config)
            memory.l0.set_identity(data["identity"])

        return stats

    def _load_json_from_zip(self, file_path: str) -> dict:
        """从 ZIP 文件中加载 JSON"""
        with zipfile.ZipFile(file_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    return json.loads(zf.read(name).decode("utf-8"))
        return {}

    def _load_file(self, file_path: str) -> dict:
        """加载导入文件"""
        if file_path.endswith(".zip"):
            return self._load_json_from_zip(file_path)
        else:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)


class BackupManager:
    """备份管理器"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.backup_dir = Path(self.config.palace_path).parent / "backups"

    def create_backup(self, label: str = None) -> str:
        """创建备份快照"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"backup_{label}_{timestamp}" if label else f"backup_{timestamp}"
        path = str(self.backup_dir / f"{name}.zip")

        exporter = MemoryExporter(self.config)
        return exporter.export_all(path, format="zip")

    def list_backups(self) -> list[dict]:
        """列出所有备份"""
        if not self.backup_dir.exists():
            return []

        backups = []
        for f in sorted(self.backup_dir.glob("*.zip"), reverse=True):
            stat = f.stat()
            backups.append({
                "name": f.stem,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return backups

    def restore_backup(self, backup_name: str, merge: bool = False) -> dict:
        """恢复备份"""
        backup_path = self.backup_dir / f"{backup_name}.zip"
        if not backup_path.exists():
            return {"error": f"备份不存在: {backup_name}"}

        importer = MemoryImporter(self.config)
        return importer.import_from_file(str(backup_path), merge=merge)

    def clean_old_backups(self, keep_count: int = 5) -> int:
        """清理旧备份，保留最近 N 个"""
        backups = self.list_backups()
        if len(backups) <= keep_count:
            return 0

        removed = 0
        for old in backups[keep_count:]:
            os.remove(old["path"])
            removed += 1
        return removed
