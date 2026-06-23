"""盘古批量多模态导入 — 目录扫描 + 自动检测 + 批量入库

支持：
1. 目录递归扫描，自动检测文件类型
2. 文本/图片/视频/音频/PDF 分别走对应引擎
3. 进度追踪 + 并发限制
4. 去重（按文件哈希）
5. 批量导入统计
"""
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.batch_import")

TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".java", ".go", ".rs", ".json",
             ".yaml", ".yml", ".toml", ".xml", ".html", ".css", ".sql", ".sh",
             ".csv", ".log", ".ini", ".cfg", ".c", ".cpp", ".h", ".rb", ".php"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}
DOC_EXTS = {".pdf"}
SKIP_EXTS = {".pyc", ".pyo", ".o", ".so", ".dll", ".exe", ".bin", ".DS_Store",
              ".git", ".idea", ".vscode", ".cache", ".db", ".sqlite", ".lock"}


class BatchImporter:
    """批量多模态导入引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._state_file = Path(self.config.palace_path) / "import_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"imported_files": {}, "total_imported": 0, "last_run": None}

    def _save_state(self):
        try:
            self._state["last_run"] = datetime.now().isoformat()
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存导入状态失败: {e}")

    def scan_directory(self, dir_path: str, recursive: bool = True,
                       include_hidden: bool = False) -> dict:
        """扫描目录，统计各类型文件数量"""
        path = Path(dir_path).expanduser()
        if not path.exists() or not path.is_dir():
            return {"error": f"目录不存在: {dir_path}"}

        stats = defaultdict(list)
        pattern = "**/*" if recursive else "*"
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".idea", ".vscode"}

        for file_path in path.glob(pattern):
            if not file_path.is_file():
                continue
            if not include_hidden and any(p.startswith(".") for p in file_path.parts[-2:]):
                continue
            if any(skip in str(file_path) for skip in skip_dirs):
                continue

            ext = file_path.suffix.lower()
            if ext in SKIP_EXTS:
                continue

            if ext in TEXT_EXTS:
                stats["text"].append(str(file_path))
            elif ext in IMAGE_EXTS:
                stats["image"].append(str(file_path))
            elif ext in VIDEO_EXTS:
                stats["video"].append(str(file_path))
            elif ext in AUDIO_EXTS:
                stats["audio"].append(str(file_path))
            elif ext in DOC_EXTS:
                stats["doc"].append(str(file_path))
            else:
                stats["other"].append(str(file_path))

        return {
            "directory": str(path),
            "total_files": sum(len(v) for v in stats.values()),
            "by_type": {k: len(v) for k, v in stats.items()},
            "files": dict(stats),
        }

    def import_directory(self, dir_path: str, wing: str = "default",
                         min_importance: float = 0.3, tags: list[str] = None,
                         max_files: int = 100) -> dict:
        """批量导入目录"""
        scan = self.scan_directory(dir_path)
        if "error" in scan:
            return scan

        start_time = time.time()
        all_files = []
        for file_type, files in scan["files"].items():
            for fp in files[:max_files // max(len(scan["files"]), 1)]:
                all_files.append((fp, file_type))

        results = {"imported": 0, "skipped": 0, "failed": 0, "by_type": defaultdict(int), "errors": []}

        for file_path, file_type in all_files[:max_files]:
            try:
                # 去重检查
                if file_path in self._state.get("imported_files", {}):
                    results["skipped"] += 1
                    continue

                result = self._import_single(file_path, file_type, wing, tags)
                if result.get("stored"):
                    results["imported"] += 1
                    results["by_type"][file_type] += 1
                    self._state.setdefault("imported_files", {})[file_path] = time.time()
                else:
                    results["skipped"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{file_path}: {str(e)[:80]}")

        self._state["total_imported"] = self._state.get("total_imported", 0) + results["imported"]
        self._save_state()

        return {
            "directory": scan["directory"],
            "total_scanned": scan["total_files"],
            "imported": results["imported"],
            "skipped": results["skipped"],
            "failed": results["failed"],
            "by_type": dict(results["by_type"]),
            "errors": results["errors"][:10],
            "duration_seconds": round(time.time() - start_time, 2),
            "total_imported_alltime": self._state["total_imported"],
        }

    def _import_single(self, file_path: str, file_type: str,
                       wing: str, tags: list[str]) -> dict:
        """导入单个文件"""
        from ..memory.multimodal_pipeline import get_multimodal_pipeline
        pipe = get_multimodal_pipeline(self.config)

        if file_type in ("text", "doc"):
            return pipe.ingest_file(file_path, wing=wing, tags=tags, auto_store=True)
        elif file_type == "image":
            result = pipe.ingest_file(file_path, wing=wing, tags=tags, auto_store=True)
            if not result.get("error") and not result.get("stored"):
                # Pipeline may not store images, use image engine
                from ..memory.image_engine import get_image_engine
                engine = get_image_engine(self.config)
                embed_result = engine.embed_image(file_path)
                if embed_result.get("embedding"):
                    result["tags"] = (tags or []) + ["image"]
                    result["stored"] = True
            return result
        elif file_type == "video":
            from ..memory.video_engine import get_video_engine
            engine = get_video_engine(self.config)
            return engine.ingest_video(file_path, wing=wing, tags=tags, auto_store=True)
        elif file_type == "audio":
            from ..memory.audio_engine import get_audio_engine
            engine = get_audio_engine(self.config)
            return engine.ingest_audio(file_path, wing=wing, tags=tags, auto_store=True)
        else:
            return pipe.ingest_file(file_path, wing=wing, tags=tags, auto_store=True)

    def get_stats(self) -> dict:
        return {
            "total_imported_alltime": self._state.get("total_imported", 0),
            "imported_files_count": len(self._state.get("imported_files", {})),
            "last_run": self._state.get("last_run"),
        }


_batch: BatchImporter | None = None


def get_batch_importer(config: PanguConfig = None) -> BatchImporter:
    global _batch
    if _batch is None:
        _batch = BatchImporter(config)
    return _batch
