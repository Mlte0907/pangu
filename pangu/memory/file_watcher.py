"""盘古文件监控 — 监控目录变更自动提取记忆

核心能力：
1. 目录监控：定时扫描指定目录的文件变更
2. 变更检测：基于 mtime 变化检测文件修改
3. 自动提取：新修改的文件自动提取内容存入记忆
4. 状态管理：记录已监控的目录和处理进度
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.file_watcher")

WATCH_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".sql",
    ".html",
    ".css",
    ".go",
    ".rs",
    ".java",
}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".idea", ".vscode", ".cache", "dist", "build"}


class FileWatcher:
    """文件监控引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._state_file = Path(self.config.palace_path) / "file_watcher_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"watched_dirs": {}, "total_files_processed": 0, "last_scan": None}

    def _save_state(self):
        try:
            self._state["last_scan"] = datetime.now().isoformat()
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存监控状态失败: {e}")

    def watch_directory(
        self, dir_path: str, pattern: str = "*.md", recursive: bool = True, auto_store: bool = True
    ) -> dict:
        """扫描目录变更并提取记忆"""
        path = Path(dir_path).expanduser()
        if not path.exists() or not path.is_dir():
            return {"error": f"目录不存在: {dir_path}"}

        # 获取文件列表
        glob_pattern = f"**/{pattern}" if recursive else pattern
        files = []
        for f in path.glob(glob_pattern):
            if not f.is_file():
                continue
            if any(skip in str(f) for skip in SKIP_DIRS):
                continue
            files.append(f)

        # 检测变更
        dir_key = str(path)
        last_scan = self._state.get("watched_dirs", {}).get(dir_key, {}).get("last_scan", 0)
        changed_files = []
        for f in files:
            try:
                mtime = f.stat().st_mtime
                if mtime > last_scan:
                    changed_files.append(f)
            except Exception:
                continue

        if not changed_files:
            return {
                "directory": str(path),
                "total_files": len(files),
                "changed": 0,
                "message": "无新变更",
            }

        # 提取变更文件的内容
        results = {"imported": 0, "skipped": 0, "files": []}
        for f in changed_files[:50]:
            try:
                if auto_store:
                    from ..memory.multimodal_pipeline import get_multimodal_pipeline

                    pipe = get_multimodal_pipeline(self.config)
                    result = pipe.ingest_file(
                        str(f),
                        wing="default",
                        description=f"文件变更监控: {f.name}",
                        tags=["file_watcher", "auto"],
                    )
                    if result.get("stored"):
                        results["imported"] += 1
                        results["files"].append(str(f.name))
                    else:
                        results["skipped"] += 1
            except Exception as e:
                logger.debug(f"处理文件失败 {f}: {e}")

        # 更新状态
        self._state.setdefault("watched_dirs", {})[dir_key] = {
            "pattern": pattern,
            "recursive": recursive,
            "last_scan": time.time(),
            "total_files": len(files),
        }
        self._state["total_files_processed"] += results["imported"]
        self._save_state()

        return {
            "directory": str(path),
            "total_files": len(files),
            "changed": len(changed_files),
            "imported": results["imported"],
            "files": results["files"][:10],
        }

    def get_watched_dirs(self) -> list[dict]:
        """获取所有监控的目录"""
        dirs = []
        for dir_path, info in self._state.get("watched_dirs", {}).items():
            dirs.append(
                {
                    "directory": dir_path,
                    "pattern": info.get("pattern", "*"),
                    "total_files": info.get("total_files", 0),
                    "last_scan": info.get("last_scan"),
                }
            )
        return dirs

    def get_stats(self) -> dict:
        return {
            "watched_dirs": len(self._state.get("watched_dirs", {})),
            "total_files_processed": self._state.get("total_files_processed", 0),
            "last_scan": self._state.get("last_scan"),
        }


_watcher: FileWatcher | None = None


def get_file_watcher(config: PanguConfig = None) -> FileWatcher:
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher(config)
    return _watcher
