"""盘古通用自动记忆采集器 — 从任意来源采集记忆

扩展 OpenClaw 会话采集，支持：
- 任意文件（.md/.txt/.log/.json）
- 目录监控（自动发现新文件）
- 日志文件（提取有价值信息）
- Claude Code 会话历史
- 接入自主调度器自动运行
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.collector")

# 采集源配置
COLLECT_SOURCES = {
    "pangu_sessions": {
        "path": "~/.local/share/mimocode/memory/sessions",
        "pattern": "*.md",
        "description": "Claude Code 会话记录",
        "enabled": True,
    },
    "pangu_projects": {
        "path": "~/.local/share/mimocode/memory/projects",
        "pattern": "**/*.md",
        "description": "项目记忆",
        "enabled": True,
    },
    "logs": {
        "path": "/tmp",
        "pattern": "pangu_*.log",
        "description": "盘古日志",
        "enabled": True,
    },
}


class FileCollector:
    """文件采集器 — 从任意文件提取记忆"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._state_file = Path(self.config.palace_path) / "collector_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"processed": {}, "total_collected": 0, "last_run": None}

    def _save_state(self):
        try:
            self._state["last_run"] = datetime.now().isoformat()
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存采集状态失败: {e}")

    def collect_from_file(self, file_path: str, source: str = "file", min_importance: float = 0.3) -> list[dict]:
        """从单个文件采集记忆"""
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            return []

        mtime = path.stat().st_mtime
        key = str(path)
        if self._state["processed"].get(key, 0) >= mtime:
            return []

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"读取文件失败 {path}: {e}")
            return []

        if not content or len(content.strip()) < 50:
            return []

        results = []
        chunks = self._chunk_content(content, max_chars=800)

        from ..memory.ingestion import remember
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        existing = self._load_existing()

        for i, chunk in enumerate(chunks):
            importance = self._assess_importance(chunk)
            if importance < min_importance:
                continue

            wing, room = self._classify(chunk)
            tags = ["auto_collect", source, path.suffix.lstrip(".")]

            item_id, drawer = remember(
                raw_text=chunk,
                wing=wing,
                room=room,
                importance=importance,
                tags=tags,
                source=f"collector:{source}:{path.name}",
                existing_drawers=existing,
            )
            existing.append(drawer)
            results.append({
                "id": item_id,
                "wing": wing,
                "importance": round(importance, 2),
                "preview": chunk[:80],
            })

        if results:
            self._save_drawers(existing)

        self._state["processed"][key] = mtime
        self._state["total_collected"] += len(results)
        self._save_state()
        return results

    def collect_from_dir(self, dir_path: str, pattern: str = "*.md", source: str = "dir",
                         min_importance: float = 0.3, max_files: int = 20) -> dict:
        """从目录批量采集"""
        path = Path(dir_path).expanduser()
        if not path.exists() or not path.is_dir():
            return {"error": f"目录不存在: {dir_path}"}

        files = sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
        total = 0
        by_file = {}
        for f in files:
            results = self.collect_from_file(str(f), source=source, min_importance=min_importance)
            if results:
                by_file[f.name] = len(results)
                total += len(results)

        return {
            "dir": str(path),
            "files_scanned": len(files),
            "memories_collected": total,
            "by_file": by_file,
        }

    def collect_all_sources(self, min_importance: float = 0.3) -> dict:
        """扫描所有配置的采集源"""
        stats = {"sources": {}, "total": 0}
        for name, src in COLLECT_SOURCES.items():
            if not src.get("enabled", True):
                continue
            path = Path(src["path"]).expanduser()
            if not path.exists():
                continue
            result = self.collect_from_dir(
                str(path), pattern=src["pattern"], source=name, min_importance=min_importance,
            )
            stats["sources"][name] = result
            stats["total"] += result.get("memories_collected", 0)
        return stats

    def _chunk_content(self, content: str, max_chars: int = 800) -> list[str]:
        """按段落/标题分块"""
        sections = []
        current = []
        for line in content.split("\n"):
            if line.startswith("#") and current:
                sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
                if len("\n".join(current)) > max_chars:
                    sections.append("\n".join(current).strip())
                    current = []
        if current:
            sections.append("\n".join(current).strip())
        return [s for s in sections if len(s) > 50]

    def _assess_importance(self, text: str) -> float:
        score = 0.3
        if len(text) > 100: score += 0.1
        if len(text) > 300: score += 0.1
        text_lower = text.lower()
        high_kw = ["决定", "修复", "bug", "部署", "必须", "规则", "P0", "架构", "完成", "失败"]
        score += min(sum(0.08 for kw in high_kw if kw in text_lower), 0.3)
        if "```" in text: score += 0.05
        if "http" in text: score += 0.05
        return min(1.0, score)

    def _classify(self, text: str) -> tuple[str, str]:
        text_lower = text.lower()
        wing = "default"
        for w, kws in {"tech": ["代码", "bug", "修复", "api", "python", "docker", "git"],
                        "project": ["任务", "计划", "进度", "交付"],
                        "team": ["会议", "讨论", "决策"]}.items():
            if any(k in text_lower for k in kws):
                wing = w
                break
        room = "general"
        for r, kws in {"decisions": ["决定", "确认"], "tasks": ["任务", "完成"],
                        "issues": ["bug", "问题"]}.items():
            if any(k in text_lower for k in kws):
                room = r
                break
        return wing, room

    def _load_existing(self, _=None) -> list:
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if drawers_file.exists():
            try:
                with open(drawers_file, encoding="utf-8") as f:
                    return [Drawer.from_dict(d) for d in json.load(f)]
            except Exception:
                pass
        return []

    def _save_drawers(self, drawers: list):
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        try:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    def get_stats(self) -> dict:
        return {
            "total_collected": self._state.get("total_collected", 0),
            "processed_files": len(self._state.get("processed", {})),
            "last_run": self._state.get("last_run"),
            "sources": {name: src["description"] for name, src in COLLECT_SOURCES.items()},
        }


_collector: FileCollector | None = None


def get_collector(config: PanguConfig = None) -> FileCollector:
    global _collector
    if _collector is None:
        _collector = FileCollector(config)
    return _collector
