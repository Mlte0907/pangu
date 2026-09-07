"""盘古记忆导出导入 — 多格式导出和跨系统导入

核心能力：
1. JSON 导出：标准 JSON 格式全量导出
2. Markdown 导出：可读 Markdown 格式导出
3. CSV 导出：表格格式导出
4. JSON 导入：标准格式导入
5. 格式检测：自动检测导入文件格式
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.export_import")


class ExportImportEngine:
    """导出导入引擎"""

    def __init__(self, config=None):
        self.config = config
        self._export_dir = Path.home() / ".pangu" / "exports"
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._history: list[dict] = []

    def export_json(self, drawers: list, filepath: str = None) -> dict:
        """JSON 格式导出"""
        data = []
        for d in drawers:
            data.append(
                {
                    "id": d.id,
                    "content": d.content,
                    "wing": d.wing,
                    "importance": d.importance,
                    "tags": d.tags,
                    "created_at": getattr(d, "created_at", ""),
                    "updated_at": getattr(d, "updated_at", ""),
                }
            )

        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._export_dir / f"export_{ts}.json")

        Path(filepath).write_text(json.dumps(data, ensure_ascii=False, indent=2))

        self._record_export("json", len(data), filepath)
        return {"format": "json", "count": len(data), "filepath": filepath}

    def export_markdown(self, drawers: list, filepath: str = None) -> dict:
        """Markdown 格式导出"""
        lines = ["# 盘古记忆导出\n"]
        lines.append(f"导出时间: {datetime.now().isoformat()}\n")
        lines.append(f"记忆总数: {len(drawers)}\n\n")

        by_wing: dict[str, list] = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            lines.append(f"## {wing} ({len(wing_drawers)} 条)\n\n")
            for d in wing_drawers:
                imp_bar = "★" * int(d.importance) + "☆" * (5 - int(d.importance))
                lines.append(f"### {d.id[:12]} {imp_bar}\n")
                lines.append(f"{d.content}\n")
                if d.tags:
                    lines.append(f"\n标签: {', '.join(d.tags)}\n")
                lines.append("\n---\n\n")

        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._export_dir / f"export_{ts}.md")

        Path(filepath).write_text("\n".join(lines))
        self._record_export("markdown", len(drawers), filepath)
        return {"format": "markdown", "count": len(drawers), "filepath": filepath}

    def export_csv(self, drawers: list, filepath: str = None) -> dict:
        """CSV 格式导出"""
        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._export_dir / f"export_{ts}.csv")

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "content", "wing", "importance", "tags", "created_at"])
            for d in drawers:
                writer.writerow(
                    [
                        d.id,
                        d.content[:200],
                        d.wing,
                        d.importance,
                        "|".join(d.tags),
                        getattr(d, "created_at", ""),
                    ]
                )

        self._record_export("csv", len(drawers), filepath)
        return {"format": "csv", "count": len(drawers), "filepath": filepath}

    def export_yaml(self, drawers: list, filepath: str = None) -> dict:
        """YAML 格式导出"""
        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._export_dir / f"export_{ts}.yaml")

        data = []
        for d in drawers:
            data.append(
                {
                    "id": d.id,
                    "content": d.content,
                    "wing": d.wing,
                    "importance": d.importance,
                    "tags": d.tags,
                    "created_at": getattr(d, "created_at", ""),
                }
            )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# 盘古记忆导出 - {datetime.now().isoformat()}\n")
            f.write(f"# 总计 {len(drawers)} 条记忆\n\n")
            f.write("memories:\n")
            for item in data:
                f.write(f"  - id: {item['id']}\n")
                f.write(f'    content: "{item["content"][:200]}"\n')
                f.write(f"    wing: {item['wing']}\n")
                f.write(f"    importance: {item['importance']}\n")
                f.write(f"    tags: {json.dumps(item['tags'], ensure_ascii=False)}\n")
                if item["created_at"]:
                    f.write(f"    created_at: {item['created_at']}\n")
                f.write("\n")

        self._record_export("yaml", len(drawers), filepath)
        return {"format": "yaml", "count": len(drawers), "filepath": filepath}

    def export_obsidian(self, drawers: list, filepath: str = None) -> dict:
        """Obsidian 格式导出（单文件，带 WikiLink）"""
        if not filepath:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._export_dir / f"export_{ts}_obsidian.md")

        lines = ["# 盘古记忆导出\n"]
        lines.append(f"导出时间: {datetime.now().isoformat()}\n")
        lines.append(f"总计: {len(drawers)} 条记忆\n\n")

        by_wing = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            lines.append(f"## {wing}\n")
            for d in wing_drawers:
                " ".join(f"#{t}" for t in d.tags)
                lines.append(f"### [{d.id[:8]}]\n")
                lines.append(f"{d.content[:300]}\n")
                lines.append(f"重要性: {'⭐' * int(d.importance)} | 标签: {', '.join(d.tags)}\n")
                if d.tags:
                    links = " ".join(f"[[{t}]]" for t in d.tags[:3])
                    lines.append(f"相关: {links}\n")
                lines.append("\n---\n\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._record_export("obsidian", len(drawers), filepath)
        return {"format": "obsidian", "count": len(drawers), "filepath": filepath}

    def import_json(self, filepath: str) -> dict:
        """JSON 格式导入"""
        content = Path(filepath).read_text()
        data = json.loads(content)

        imported = []
        for item in data:
            imported.append(
                {
                    "id": item.get("id", ""),
                    "content": item.get("content", ""),
                    "wing": item.get("wing", "imported"),
                    "importance": item.get("importance", 3.0),
                    "tags": item.get("tags", []),
                }
            )

        self._record_import("json", len(imported), filepath)
        return {"format": "json", "imported": len(imported), "data": imported}

    def import_markdown(self, filepath: str) -> dict:
        """Markdown 格式导入"""
        content = Path(filepath).read_text(encoding="utf-8")
        imported = []
        current_wing = "imported"
        current_content = ""

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_content:
                    imported.append(
                        {
                            "id": "",
                            "content": current_content.strip(),
                            "wing": current_wing,
                            "importance": 3.0,
                            "tags": [],
                        }
                    )
                current_wing = line[3:].strip()
                current_content = ""
            elif line.startswith("### "):
                if current_content:
                    imported.append(
                        {
                            "id": "",
                            "content": current_content.strip(),
                            "wing": current_wing,
                            "importance": 3.0,
                            "tags": [],
                        }
                    )
                current_content = ""
            elif line.strip() and not line.startswith("#") and not line.startswith("---"):
                current_content += line + "\n"

        if current_content.strip():
            imported.append(
                {
                    "id": "",
                    "content": current_content.strip(),
                    "wing": current_wing,
                    "importance": 3.0,
                    "tags": [],
                }
            )

        self._record_import("markdown", len(imported), filepath)
        return {"format": "markdown", "imported": len(imported), "data": imported}

    def import_csv(self, filepath: str) -> dict:
        """CSV 格式导入"""
        imported = []
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                imported.append(
                    {
                        "id": row.get("id", ""),
                        "content": row.get("content", ""),
                        "wing": row.get("wing", "imported"),
                        "importance": float(row.get("importance", 3.0)),
                        "tags": row.get("tags", "").split("|") if row.get("tags") else [],
                    }
                )

        self._record_import("csv", len(imported), filepath)
        return {"format": "csv", "imported": len(imported), "data": imported}

    def import_yaml(self, filepath: str) -> dict:
        """YAML 格式导入"""
        content = Path(filepath).read_text(encoding="utf-8")
        imported = []
        current_id = ""
        current_content = ""
        current_wing = "imported"
        current_importance = 3.0
        current_tags = []

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- id:"):
                if current_content:
                    imported.append(
                        {
                            "id": current_id,
                            "content": current_content,
                            "wing": current_wing,
                            "importance": current_importance,
                            "tags": current_tags,
                        }
                    )
                current_id = stripped.split(":", 1)[1].strip().strip('"')
                current_content = ""
                current_tags = []
            elif stripped.startswith("content:"):
                current_content = stripped.split(":", 1)[1].strip().strip('"')
            elif stripped.startswith("wing:"):
                current_wing = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("importance:"):
                try:
                    current_importance = float(stripped.split(":", 1)[1].strip())
                except:
                    pass
            elif stripped.startswith("tags:"):
                tag_str = stripped.split(":", 1)[1].strip()
                if tag_str.startswith("["):
                    try:
                        current_tags = json.loads(tag_str)
                    except:
                        current_tags = []
                elif tag_str:
                    current_tags = [tag_str]

        if current_content:
            imported.append(
                {
                    "id": current_id,
                    "content": current_content,
                    "wing": current_wing,
                    "importance": current_importance,
                    "tags": current_tags,
                }
            )

        self._record_import("yaml", len(imported), filepath)
        return {"format": "yaml", "imported": len(imported), "data": imported}

    def detect_format(self, filepath: str) -> str:
        """检测文件格式"""
        path = Path(filepath)
        ext = path.suffix.lower()
        if ext == ".json":
            return "json"
        elif ext == ".yaml" or ext == ".yml":
            return "yaml"
        elif ext == ".md":
            return "markdown"
        elif ext == ".csv":
            return "csv"
        elif "obsidian" in path.name:
            return "obsidian"
        return "unknown"

    def smart_import(self, filepath: str) -> dict:
        """智能导入（自动检测格式）"""
        fmt = self.detect_format(filepath)
        if fmt == "json":
            return self.import_json(filepath)
        elif fmt == "markdown":
            return self.import_markdown(filepath)
        elif fmt == "csv":
            return self.import_csv(filepath)
        elif fmt == "yaml":
            return self.import_yaml(filepath)
        else:
            return {"error": f"不支持的导入格式: {fmt}", "detected": fmt}

    def _record_export(self, format_name: str, count: int, filepath: str):
        self._history.append(
            {
                "operation": "export",
                "format": format_name,
                "count": count,
                "filepath": filepath,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _record_import(self, format_name: str, count: int, filepath: str):
        self._history.append(
            {
                "operation": "import",
                "format": format_name,
                "count": count,
                "filepath": filepath,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def list_exports(self) -> list[dict]:
        """列出所有导出文件"""
        exports = []
        for f in self._export_dir.iterdir():
            if f.suffix in (".json", ".md", ".csv", ".yaml", ".yml") or "obsidian" in f.name:
                exports.append(
                    {
                        "name": f.name,
                        "format": f.suffix[1:],
                        "size": f.stat().st_size,
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    }
                )
        exports.sort(key=lambda x: x["modified"], reverse=True)
        return exports

    def get_stats(self) -> dict:
        """获取统计"""
        exports = sum(1 for h in self._history if h["operation"] == "export")
        imports = sum(1 for h in self._history if h["operation"] == "import")
        return {"total_exports": exports, "total_imports": imports, "history": len(self._history)}


_engine: ExportImportEngine | None = None


def get_export_engine(config=None) -> ExportImportEngine:
    global _engine
    if _engine is None:
        _engine = ExportImportEngine(config)
    return _engine
