"""盘古叙事引擎 — 将碎片化记忆串成连贯叙事 + 主题提取 + 身份连续性

核心功能：
1. 叙事生成 — 按 Wing/Room 将记忆串成连贯叙事线
2. 主题提取 — 从记忆片段中提取主题聚类
3. 身份连续性 — 从自省记忆生成连续身份叙事
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.narrative")


@dataclass
class Narrative:
    drawer: str
    thread_length: int
    narrative: str
    avg_importance: float


@dataclass
class ThemeSummary:
    drawer: str
    memory_count: int
    sample: str


def _extract_themes(drawers: list[Drawer]) -> list[dict]:
    """从记忆片段中提取主题聚类"""
    themes: dict[str, dict] = {}
    for d in drawers:
        if not d.content:
            continue
        key = d.wing
        if key not in themes:
            themes[key] = {"drawer": d.wing, "count": 0, "previews": []}
        themes[key]["count"] += 1
        preview = d.content[:100].replace("\n", " ")
        themes[key]["previews"].append(preview)

    return sorted(themes.values(), key=lambda t: t["count"], reverse=True)


def _generate_identity_statement(identity_drawers: list[Drawer]) -> str | None:
    """从自省记忆生成连续身份叙事"""
    if not identity_drawers:
        return None
    sorted_drawers = sorted(identity_drawers, key=lambda d: d.created_at)
    timeline = [d.content[:80].replace("\n", " ") for d in sorted_drawers if d.content]
    if not timeline:
        return None
    return " → ".join(timeline[-5:])


class NarrativeEngine:
    """叙事引擎 — 将碎片化记忆串成连贯叙事 + 主题提取 + 身份连续性"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def generate_narrative(self, drawers: list[Drawer]) -> dict:
        """生成叙事 — 按 Wing 聚合记忆为连贯叙事线"""
        timeline = [d for d in drawers if d.importance > 3.0 and d.content]
        timeline.sort(key=lambda d: d.created_at, reverse=True)
        timeline = timeline[:30]

        if not timeline:
            return {"narratives": 0, "message": "Not enough material"}

        by_wing: dict[str, list[Drawer]] = {}
        for d in timeline:
            if d.wing not in by_wing:
                by_wing[d.wing] = []
            by_wing[d.wing].append(d)

        narratives = []
        for wing, wing_drawers in by_wing.items():
            if len(wing_drawers) >= 3:
                previews = [d.content[:80].replace("\n", " ") for d in wing_drawers[:5]]
                avg_importance = sum(d.importance for d in wing_drawers) / len(wing_drawers)
                narrative_text = f"In wing '{wing}' ({len(wing_drawers)} memories, avg importance {avg_importance:.2f}): {' → '.join(previews)}"
                narratives.append(Narrative(
                    drawer=wing,
                    thread_length=len(wing_drawers),
                    narrative=narrative_text[:500],
                    avg_importance=round(avg_importance, 2),
                ).__dict__)

        identity_items = [d for d in drawers if d.importance > 4.0 and any(
            t in d.tags for t in ["自省", "反思", "身份", "soul", "identity"]
        )]
        identity_statement = _generate_identity_statement(identity_items[:10])

        themes = _extract_themes(timeline)
        theme_summaries = [
            ThemeSummary(
                drawer=theme["drawer"],
                memory_count=theme["count"],
                sample=theme["previews"][0][:80] if theme["previews"] else "",
            ).__dict__
            for theme in themes if theme["count"] >= 2
        ]

        return {
            "narratives": len(narratives),
            "samples": narratives[:3],
            "themes": theme_summaries,
            "total_items_in_window": len(timeline),
            "identity_continuity": identity_statement,
            "timestamp": datetime.now().isoformat(),
        }

    def extract_themes(self, drawers: list[Drawer]) -> dict:
        """提取主题"""
        themes = _extract_themes(drawers[:30])
        theme_summaries = [
            {"drawer": t["drawer"], "memory_count": t["count"], "sample": t["previews"][0][:80] if t["previews"] else ""}
            for t in themes if t["count"] >= 2
        ]
        return {"themes": theme_summaries, "count": len(theme_summaries)}

    def identity_statement(self, drawers: list[Drawer]) -> dict:
        """生成身份连续性叙事"""
        identity_items = [d for d in drawers if d.importance > 4.0 and any(
            t in d.tags for t in ["自省", "反思", "身份", "soul", "identity"]
        )]
        statement = _generate_identity_statement(identity_items[:10])
        return {
            "identity": statement,
            "source_count": len(identity_items),
            "has_continuity": bool(statement and len(statement) > 30),
        }

    def get_stats(self, drawers: list[Drawer]) -> dict:
        """获取叙事统计"""
        wings = set(d.wing for d in drawers)
        high_importance = sum(1 for d in drawers if d.importance > 3.0)
        identity_tagged = sum(1 for d in drawers if any(
            t in d.tags for t in ["自省", "反思", "身份", "soul", "identity"]
        ))
        return {
            "total_memories": len(drawers),
            "wings": len(wings),
            "high_importance": high_importance,
            "identity_tagged": identity_tagged,
        }


_engine: NarrativeEngine | None = None


def get_narrative_engine(config: PanguConfig = None) -> NarrativeEngine:
    global _engine
    if _engine is None:
        _engine = NarrativeEngine(config)
    return _engine
