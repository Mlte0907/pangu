"""盘古记忆回放引擎 — 按时间线重构事件全景
==============================================
从散落的记忆中重构完整的事件全景，就像电影回放。

支持：
- 时间线回放：按时间顺序重播记忆
- 主题回放：围绕特定主题重播相关记忆
- 差异回放：对比两个时间段的记忆变化
- 快照对比：比较不同时间点的记忆状态
"""
from dataclasses import dataclass, field
from datetime import datetime

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class ReplaySession:
    """回放会话"""
    id: str
    title: str
    events: list[dict]  # [{time, content, wing, room, importance, tags}]
    span: str  # 时间跨度
    event_count: int
    wings: list[str]
    key_moments: list[dict]  # 关键时刻
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SnapshotDiff:
    """快照差异"""
    added: list[dict]  # 新增的记忆
    removed: list[dict]  # 消失的记忆
    modified: list[dict]  # 变化的记忆
    unchanged: int  # 不变的记忆


class ReplayEngine:
    """记忆回放引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def _check_time_range(self, ts: datetime, start: str, end: str) -> bool:
        """检查时间戳是否在指定范围内，返回 True 表示通过"""
        if start:
            try:
                if ts < datetime.fromisoformat(start):
                    return False
            except (ValueError, TypeError):
                pass
        if end:
            try:
                if ts > datetime.fromisoformat(end):
                    return False
            except (ValueError, TypeError):
                pass
        return True

    def _filter_drawer(self, d: Drawer, wing: str, room: str,
                        start: str, end: str) -> bool:
        """判断 drawer 是否通过过滤条件，返回 True 表示保留"""
        if wing and d.wing != wing:
            return False
        if room and d.room != room:
            return False
        try:
            ts = datetime.fromisoformat(d.created_at)
        except (ValueError, TypeError):
            ts = datetime.now()
        return self._check_time_range(ts, start, end)

    def _drawer_to_event(self, d: Drawer) -> dict:
        """将 Drawer 转换为回放事件"""
        try:
            ts = datetime.fromisoformat(d.created_at)
        except (ValueError, TypeError):
            ts = datetime.now()
        return {
            "time": ts.isoformat(),
            "content": d.content,
            "wing": d.wing,
            "room": d.room,
            "importance": d.importance,
            "tags": d.tags or [],
            "id": d.id,
        }

    def timeline_replay(self, drawers: list[Drawer],
                        start: str = None, end: str = None,
                        wing: str = None, room: str = None,
                        limit: int = 50) -> ReplaySession:
        """时间线回放：按时间顺序重播记忆

        Args:
            drawers: 记忆列表
            start: 开始时间
            end: 结束时间
            wing: 限定 Wing
            room: 限定 Room
            limit: 最大事件数

        Returns:
            ReplaySession
        """
        events = []
        for d in drawers:
            if not self._filter_drawer(d, wing, room, start, end):
                continue
            events.append(self._drawer_to_event(d))

        events.sort(key=lambda e: e["time"])
        events = events[:limit]

        # 确定时间跨度
        if events:
            span = f"{events[0]['time'][:10]} ~ {events[-1]['time'][:10]}"
        else:
            span = "无事件"

        # 识别关键时刻（高重要性事件）
        key_moments = [e for e in events if e["importance"] >= 4.0]
        if not key_moments:
            key_moments = events[:5] if events else []

        wings_seen = list(set(e["wing"] for e in events))

        title = "记忆回放"
        if wing:
            title += f" [{wing}]"
        if room:
            title += f" / {room}"

        session_id = hex_digest(
            title + (events[0]["id"] if events else "")
        )[:12]

        return ReplaySession(
            id=session_id,
            title=title,
            events=events,
            span=span,
            event_count=len(events),
            wings=wings_seen,
            key_moments=key_moments[:10],
        )

    def topic_replay(self, topic: str, drawers: list[Drawer],
                     limit: int = 30) -> ReplaySession:
        """主题回放：围绕特定主题重播相关记忆

        Args:
            topic: 主题关键词
            drawers: 记忆列表
            limit: 最大事件数

        Returns:
            ReplaySession
        """
        topic_lower = topic.lower()

        # 按相关性排序
        scored = []
        for d in drawers:
            content_lower = d.content.lower()
            # 关键词匹配
            score = content_lower.count(topic_lower) * 2
            # 标签匹配
            if any(topic_lower in (t or "").lower() for t in (d.tags or [])):
                score += 3
            # 重要性加权
            score += d.importance / 5
            if score > 0:
                scored.append((score, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_drawers = [d for _, d in scored[:limit]]

        events = []
        for d in top_drawers:
            try:
                ts = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                ts = datetime.now()

            events.append({
                "time": ts.isoformat(),
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags or [],
                "id": d.id,
            })

        events.sort(key=lambda e: e["time"])

        span = f"{events[0]['time'][:10]} ~ {events[-1]['time'][:10]}" if events else ""

        key_moments = [e for e in events if e["importance"] >= 4.0][:10]

        return ReplaySession(
            id=hex_digest(topic)[:12],
            title=f"主题回放: {topic}",
            events=events,
            span=span,
            event_count=len(events),
            wings=list(set(e["wing"] for e in events)),
            key_moments=key_moments,
        )

    def diff_replay(self, before: list[Drawer], after: list[Drawer],
                    title: str = "差异回放") -> ReplaySession:
        """差异回放：对比两个时间段的记忆变化

        Args:
            before: 之前时间段的记忆
            after: 之后时间段的记忆
            title: 回放标题

        Returns:
            ReplaySession
        """
        before_ids = {d.id for d in before}
        after_ids = {d.id for d in after}

        # 新增的
        added_ids = after_ids - before_ids
        added = [
            {"time": d.created_at or "", "content": d.content,
             "wing": d.wing, "room": d.room, "importance": d.importance,
             "tags": d.tags or [], "id": d.id, "change": "新增"}
            for d in after if d.id in added_ids
        ]

        # 删除的
        removed_ids = before_ids - after_ids
        removed = [
            {"time": d.created_at or "", "content": d.content,
             "wing": d.wing, "room": d.room, "importance": d.importance,
             "tags": d.tags or [], "id": d.id, "change": "删除"}
            for d in before if d.id in removed_ids
        ]

        # 不变
        unchanged = len(before_ids & after_ids)

        # 合并
        all_events = added + removed
        all_events.sort(key=lambda e: e["time"])

        return ReplaySession(
            id=hex_digest(title)[:12],
            title=title,
            events=all_events[:50],
            span=f"新增 {len(added)} / 删除 {len(removed)} / 不变 {unchanged}",
            event_count=len(all_events),
            wings=list(set(e["wing"] for e in all_events)),
            key_moments=added[:5],
            created_at=datetime.now().isoformat(),
        )

    def snapshot_compare(self, drawers_a: list[Drawer],
                         drawers_b: list[Drawer]) -> SnapshotDiff:
        """快照对比：比较两个记忆集合的差异

        Args:
            drawers_a: 快照 A
            drawers_b: 快照 B

        Returns:
            SnapshotDiff
        """
        ids_a = {d.id: d for d in drawers_a}
        ids_b = {d.id: d for d in drawers_b}

        added_ids = set(ids_b.keys()) - set(ids_a.keys())
        removed_ids = set(ids_a.keys()) - set(ids_b.keys())
        common_ids = set(ids_a.keys()) & set(ids_b.keys())

        added = [
            {"id": d.id, "content": d.content[:100], "wing": d.wing,
             "room": d.room, "importance": d.importance}
            for d in drawers_b if d.id in added_ids
        ]

        removed = [
            {"id": d.id, "content": d.content[:100], "wing": d.wing,
             "room": d.room, "importance": d.importance}
            for d in drawers_a if d.id in removed_ids
        ]

        modified = []
        for mid in common_ids:
            a = ids_a[mid]
            b = ids_b[mid]
            if (a.content != b.content or a.importance != b.importance
                    or a.tags != b.tags):
                modified.append({
                    "id": mid,
                    "before": a.content[:100],
                    "after": b.content[:100],
                    "importance_change": b.importance - a.importance,
                })

        return SnapshotDiff(
            added=added,
            removed=removed,
            modified=modified,
            unchanged=len(common_ids) - len(modified),
        )

    def highlight_reel(self, drawers: list[Drawer],
                       top_n: int = 10) -> ReplaySession:
        """精彩集锦：提取最重要的记忆时刻

        Args:
            drawers: 记忆列表
            top_n: 返回事件数

        Returns:
            ReplaySession
        """
        sorted_drawers = sorted(drawers, key=lambda d: d.importance, reverse=True)
        top = sorted_drawers[:top_n]

        events = []
        for d in top:
            events.append({
                "time": d.created_at or "",
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags or [],
                "id": d.id,
            })

        events.sort(key=lambda e: e["time"])

        return ReplaySession(
            id=hex_digest("highlight")[:12],
            title="精彩集锦",
            events=events,
            span=f"共 {len(events)} 个高光时刻",
            event_count=len(events),
            wings=list(set(e["wing"] for e in events)),
            key_moments=events,
        )

    def replay_summary(self, session: ReplaySession) -> str:
        """生成回放摘要"""
        lines = [
            f"=== {session.title} ===",
            f"时间跨度: {session.span}",
            f"事件数: {session.event_count}",
            f"涉及空间: {', '.join(session.wings) if session.wings else '无'}",
            "",
            "--- 关键时刻 ---",
        ]

        for i, moment in enumerate(session.key_moments[:5], 1):
            lines.append(
                f"{i}. [{moment['time'][:10]}] {moment['content'][:100]}"
                f" (重要性: {moment['importance']})"
            )

        if session.event_count > 0:
            lines.append("")
            lines.append("--- 完整时间线 ---")
            for i, event in enumerate(session.events[:20], 1):
                change = event.get("change", "")
                marker = f"[{change}] " if change else ""
                lines.append(
                    f"{i}. [{event['time'][:16]}] {marker}{event['content'][:80]}"
                )

        return "\n".join(lines)
