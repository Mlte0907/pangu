"""盘古多项目支持 — 不同项目独立记忆空间

核心能力：
1. 项目隔离：每个项目拥有独立的记忆空间
2. 项目切换：在不同项目间快速切换
3. 跨项目搜索：跨项目搜索记忆
4. 项目统计：查看各项目的记忆状态
5. 项目合并：将一个项目的记忆合并到另一个项目
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.project_manager")


@dataclass
class ProjectInfo:
    """项目信息"""
    project_id: str
    name: str
    description: str
    created_at: str
    memory_count: int = 0
    last_active: str = ""


class ProjectManager:
    """多项目管理引擎"""

    def __init__(self, config=None):
        self.config = config
        self._projects_dir = Path.home() / ".pangu" / "projects"
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._projects_dir / "index.json"
        self._projects: dict[str, ProjectInfo] = {}
        self._active_project: str = "default"
        self._load_index()

        if "default" not in self._projects:
            self._projects["default"] = ProjectInfo(
                project_id="default",
                name="Default",
                description="默认项目",
                created_at=datetime.now().isoformat(),
            )
            self._save_index()

    def _load_index(self) -> None:
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text())
                for pid, info in data.items():
                    self._projects[pid] = ProjectInfo(**info)
                if self._projects:
                    self._active_project = list(self._projects.keys())[-1]
            except Exception:
                self._projects = {}

    def _save_index(self) -> None:
        data = {
            pid: {
                "project_id": p.project_id, "name": p.name,
                "description": p.description, "created_at": p.created_at,
                "memory_count": p.memory_count, "last_active": p.last_active,
            }
            for pid, p in self._projects.items()
        }
        self._index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _project_dir(self, project_id: str) -> Path:
        d = self._projects_dir / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_project(self, project_id: str, name: str, description: str = "") -> dict:
        """创建项目"""
        if project_id in self._projects:
            return {"error": f"项目 '{project_id}' 已存在"}

        self._projects[project_id] = ProjectInfo(
            project_id=project_id,
            name=name,
            description=description,
            created_at=datetime.now().isoformat(),
        )
        self._project_dir(project_id)
        self._save_index()
        return {"status": "created", "project_id": project_id, "name": name}

    def switch_project(self, project_id: str) -> dict:
        """切换项目"""
        if project_id not in self._projects:
            return {"error": f"项目 '{project_id}' 不存在"}

        old = self._active_project
        self._active_project = project_id
        self._projects[project_id].last_active = datetime.now().isoformat()
        self._save_index()
        return {"switched_from": old, "switched_to": project_id}

    def get_active_project(self) -> dict:
        """获取当前活跃项目"""
        p = self._projects.get(self._active_project)
        if not p:
            return {"error": "无活跃项目"}
        return {
            "project_id": p.project_id, "name": p.name,
            "description": p.description, "memory_count": p.memory_count,
        }

    def list_projects(self) -> list[dict]:
        """列出所有项目"""
        return [
            {"id": p.project_id, "name": p.name, "description": p.description,
             "memories": p.memory_count, "active": p.project_id == self._active_project,
             "created": p.created_at}
            for p in self._projects.values()
        ]

    def save_memories(self, drawers: list) -> dict:
        """保存记忆到当前项目"""
        project_dir = self._project_dir(self._active_project)
        drawers_file = project_dir / "drawers.json"

        data = []
        for d in drawers:
            data.append({
                "id": d.id, "content": d.content, "wing": d.wing,
                "importance": d.importance, "tags": d.tags,
                "created_at": getattr(d, "created_at", ""),
                "updated_at": getattr(d, "updated_at", ""),
            })

        drawers_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        if self._active_project in self._projects:
            self._projects[self._active_project].memory_count = len(drawers)
            self._projects[self._active_project].last_active = datetime.now().isoformat()
            self._save_index()

        return {"saved": len(drawers), "project": self._active_project}

    def load_memories(self, project_id: str = None) -> list[dict]:
        """加载项目记忆"""
        pid = project_id or self._active_project
        project_dir = self._project_dir(pid)
        drawers_file = project_dir / "drawers.json"

        if not drawers_file.exists():
            return []

        try:
            return json.loads(drawers_file.read_text())
        except Exception:
            return []

    def search_cross_project(self, query: str, limit: int = 10) -> list[dict]:
        """跨项目搜索"""
        results = []
        for pid in self._projects:
            memories = self.load_memories(pid)
            for m in memories:
                score = 0
                q_lower = query.lower()
                c_lower = m.get("content", "").lower()
                for word in q_lower.split():
                    if len(word) >= 2 and word in c_lower:
                        score += 2
                for tag in m.get("tags", []):
                    for word in q_lower.split():
                        if word in tag.lower():
                            score += 3

                if score > 0:
                    results.append({
                        "project": pid,
                        "id": m.get("id", ""),
                        "content": m.get("content", "")[:80],
                        "score": score,
                    })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def merge_project(self, source_id: str, target_id: str = None) -> dict:
        """合并项目"""
        target = target_id or self._active_project
        if source_id not in self._projects:
            return {"error": f"源项目 '{source_id}' 不存在"}
        if target not in self._projects:
            return {"error": f"目标项目 '{target}' 不存在"}

        source_memories = self.load_memories(source_id)
        target_memories = self.load_memories(target)

        existing_ids = {m.get("id") for m in target_memories}
        merged = 0
        for m in source_memories:
            if m.get("id") not in existing_ids:
                target_memories.append(m)
                existing_ids.add(m.get("id"))
                merged += 1

        project_dir = self._project_dir(target)
        (project_dir / "drawers.json").write_text(
            json.dumps(target_memories, ensure_ascii=False, indent=2))

        self._projects[target].memory_count = len(target_memories)
        self._save_index()

        return {"merged": merged, "source": source_id, "target": target,
                "target_total": len(target_memories)}

    def delete_project(self, project_id: str) -> dict:
        """删除项目"""
        if project_id == "default":
            return {"error": "不能删除默认项目"}
        if project_id not in self._projects:
            return {"error": f"项目 '{project_id}' 不存在"}

        import shutil
        project_dir = self._projects_dir / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)

        del self._projects[project_id]
        if self._active_project == project_id:
            self._active_project = "default"
        self._save_index()

        return {"deleted": project_id}

    def get_project_stats(self) -> dict:
        """获取项目统计"""
        total_memories = sum(p.memory_count for p in self._projects.values())
        return {
            "total_projects": len(self._projects),
            "total_memories": total_memories,
            "active_project": self._active_project,
        }


_project_manager: ProjectManager | None = None


def get_project_manager(config=None) -> ProjectManager:
    """获取全局项目管理器实例"""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager(config)
    return _project_manager
