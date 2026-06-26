"""盘古宫殿核心 — Wings/Rooms/Drawers/Halls/Tunnels 管理"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Drawer:
    """记忆抽屉 — 存储原始记忆片段"""

    id: str
    content: str
    wing: str = "default"
    room: str = "general"
    hall: str = "hall_events"
    importance: float = 3.0
    emotional_weight: float = 0.0
    source_file: str = ""
    tags: list = field(default_factory=list)
    author: str = ""  # 新增：记录写入者 agent_id
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "wing": self.wing,
            "room": self.room,
            "hall": self.hall,
            "importance": self.importance,
            "emotional_weight": self.emotional_weight,
            "source_file": self.source_file,
            "tags": self.tags,
            "author": self.author,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Drawer":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            content=data.get("content", ""),
            wing=data.get("wing", "default"),
            room=data.get("room", "general"),
            hall=data.get("hall", "hall_events"),
            importance=data.get("importance", 3.0),
            emotional_weight=data.get("emotional_weight", 0.0),
            source_file=data.get("source_file", ""),
            tags=data.get("tags", []),
            author=data.get("author", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class WikiPage:
    """Wiki 页面 — 由 LMM 从记忆中自动生成的知识页面"""

    id: str
    title: str
    wing: str
    content: str  # Markdown 内容
    summary: str = ""  # LMM 生成的摘要
    linked_pages: list = field(default_factory=list)  # 关联页面 ID
    linked_drawers: list = field(default_factory=list)  # 关联记忆片段 ID
    tags: list = field(default_factory=list)
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "wing": self.wing,
            "content": self.content,
            "summary": self.summary,
            "linked_pages": self.linked_pages,
            "linked_drawers": self.linked_drawers,
            "tags": self.tags,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WikiPage":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data.get("title", ""),
            wing=data.get("wing", "default"),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            linked_pages=data.get("linked_pages", []),
            linked_drawers=data.get("linked_drawers", []),
            tags=data.get("tags", []),
            version=data.get("version", 1),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


# 殿堂分类体系
HALL_TYPES = {
    "hall_facts": "事实与决策 — 已做出的决定和锁定的选择",
    "hall_events": "事件与里程碑 — 会话、调试过程、重要节点",
    "hall_discoveries": "发现与洞察 — 突破性发现、新认知",
    "hall_preferences": "偏好与习惯 — 个人喜好、工作习惯、观点",
    "hall_advice": "建议与方案 — 推荐方案和解决思路",
    "hall_concepts": "概念与理论 — 核心概念、理论框架",
    "hall_relations": "关系与网络 — 人物关系、项目关联",
}


class Palace:
    """宫殿 — 记忆系统的核心容器"""

    def __init__(self, palace_path: str):
        self.path = Path(palace_path)
        self.path.mkdir(parents=True, exist_ok=True)

        # 元数据文件
        self.meta_file = self.path / "palace_meta.json"
        self.wings_file = self.path / "wings.json"
        self.rooms_file = self.path / "rooms.json"

        self._load_meta()

    def _load_meta(self) -> None:
        """加载宫殿元数据"""
        if self.meta_file.exists():
            with open(self.meta_file, encoding="utf-8") as f:
                self.meta = json.load(f)
        else:
            self.meta = {
                "name": "盘古记忆宫殿",
                "version": "0.1.0",
                "created_at": datetime.now().isoformat(),
                "wings": ["default"],
                "rooms": {},
                "tunnels": [],
            }
            self._save_meta()

    def _save_meta(self) -> None:
        """保存宫殿元数据"""
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)

    # ── Wing 管理 ──

    def list_wings(self) -> list[str]:
        """列出所有 Wing"""
        return self.meta.get("wings", ["default"])

    def create_wing(self, name: str, description: str = "") -> str:
        """创建新 Wing"""
        if name not in self.meta["wings"]:
            self.meta["wings"].append(name)
            self.meta.setdefault("rooms", {})[name] = []
            self.meta.setdefault("wing_descriptions", {})[name] = description
            self._save_meta()
        return name

    def delete_wing(self, name: str) -> bool:
        """删除 Wing"""
        if name == "default":
            return False
        if name in self.meta["wings"]:
            self.meta["wings"].remove(name)
            self.meta["rooms"].pop(name, None)
            self.meta.get("wing_descriptions", {}).pop(name, None)
            self._save_meta()
            return True
        return False

    # ── Room 管理 ──

    def list_rooms(self, wing: str = None) -> dict[str, list[str]]:
        """列出 Wing 下的所有 Room"""
        rooms = self.meta.get("rooms", {})
        if wing:
            return {wing: rooms.get(wing, [])}
        return rooms

    def create_room(self, wing: str, room: str, description: str = "") -> str:
        """在指定 Wing 下创建 Room"""
        self.create_wing(wing)  # 确保 wing 存在
        rooms = self.meta.setdefault("rooms", {})
        wing_rooms = rooms.setdefault(wing, [])
        if room not in wing_rooms:
            wing_rooms.append(room)
            self.meta.setdefault("room_descriptions", {}).setdefault(wing, {})[room] = description
            self._save_meta()
        return room

    def delete_room(self, wing: str, room: str) -> bool:
        """删除 Room"""
        rooms = self.meta.get("rooms", {})
        if wing in rooms and room in rooms[wing]:
            rooms[wing].remove(room)
            self.meta.get("room_descriptions", {}).get(wing, {}).pop(room, None)
            self._save_meta()
            return True
        return False

    # ── Tunnel 管理 (跨 Wing 连接) ──

    def create_tunnel(self, wing_a: str, wing_b: str, room: str) -> dict:
        """创建跨 Wing 隧道"""
        tunnel = {
            "id": str(uuid.uuid4())[:8],
            "wing_a": wing_a,
            "wing_b": wing_b,
            "room": room,
            "created_at": datetime.now().isoformat(),
        }
        self.meta.setdefault("tunnels", []).append(tunnel)
        self._save_meta()
        return tunnel

    def list_tunnels(self) -> list[dict]:
        """列出所有隧道"""
        return self.meta.get("tunnels", [])

    def find_tunnels(self, wing_a: str, wing_b: str) -> list[dict]:
        """查找两个 Wing 之间的隧道"""
        tunnels = self.meta.get("tunnels", [])
        return [
            t
            for t in tunnels
            if (t["wing_a"] == wing_a and t["wing_b"] == wing_b) or (t["wing_a"] == wing_b and t["wing_b"] == wing_a)
        ]

    # ── 统计 ──

    def stats(self) -> dict:
        """获取宫殿统计信息"""
        return {
            "name": self.meta.get("name", ""),
            "wings_count": len(self.meta.get("wings", [])),
            "rooms_count": sum(len(v) for v in self.meta.get("rooms", {}).values()),
            "tunnels_count": len(self.meta.get("tunnels", [])),
            "created_at": self.meta.get("created_at", ""),
        }

    def export_structure(self) -> dict:
        """导出宫殿结构（用于可视化）"""
        nodes = []
        edges = []

        for wing in self.meta.get("wings", []):
            nodes.append({"id": wing, "type": "wing", "label": wing})
            for room in self.meta.get("rooms", {}).get(wing, []):
                room_id = f"{wing}/{room}"
                nodes.append({"id": room_id, "type": "room", "label": room, "wing": wing})
                edges.append({"from": wing, "to": room_id, "type": "contains"})

        for tunnel in self.meta.get("tunnels", []):
            edges.append(
                {
                    "from": tunnel["wing_a"],
                    "to": tunnel["wing_b"],
                    "type": "tunnel",
                    "room": tunnel["room"],
                }
            )

        return {"nodes": nodes, "edges": edges}
