"""盘古时间线引擎 — 事件链构建与因果推理
==============================================
构建记忆之间的时间线关系，支持：
- 事件链构建：按时间顺序串联记忆
- 因果推理：基于时间先后推断因果关系
- 时序查询：查询某时间点前后的记忆
- 事件跨度分析：计算事件持续时间
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class TimelineEvent:
    """时间线事件"""

    id: str
    drawer_id: str
    content: str
    timestamp: str
    wing: str = ""
    room: str = ""
    importance: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class EventChain:
    """事件链"""

    id: str
    events: list[TimelineEvent]
    span: str  # 时间跨度描述
    summary: str  # 事件链摘要
    causal_links: list[dict] = field(default_factory=list)  # [{from, to, confidence}]


@dataclass
class CausalLink:
    """因果关联"""

    source_id: str
    target_id: str
    confidence: float
    reason: str
    source_content: str = ""
    target_content: str = ""


class TimelineEngine:
    """时间线引擎"""

    # 因果关键词（A 导致 B）
    CAUSAL_PATTERNS = [
        # 显式因果
        (r"(?:因为|由于|因为|由于)\s*(.+?)(?:所以|因此|导致|于是|造成|引起)", 0.9),
        (r"(.+?)(?:导致|造成了|引起了|触发了)\s*(.+)", 0.85),
        (r"(.+?)(?:结果|最终|后来)\s*(.+)", 0.5),
        (r"(.+?)(?:修复了|解决了|处理了)\s*(.+)", 0.7),
        (r"(.+?)(?:升级|迁移|重构).+?(?:到|为|至)\s*(.+)", 0.6),
        # 英文
        (r"(.+?)(?:because|since|due to)\s*(.+?)(?:,|\.|so|therefore|thus|hence)", 0.9),
        (r"(.+?)(?:caused|led to|resulted in|triggered)\s*(.+)", 0.85),
        (r"(.+?)(?:fixed|resolved|patched)\s*(.+)", 0.7),
        (r"(.+?)(?:upgraded|migrated|refactored).+?(?:to|into)\s*(.+)", 0.6),
    ]

    # 时序标记词
    TEMPORAL_MARKERS = [
        (r"(?:首先|起初|最初|一开始|开始)", "start"),
        (r"(?:然后|接着|随后|之后|接下来|此后)", "next"),
        (r"(?:最后|最终|终于|到此|结束|完成)", "end"),
        (r"(?:之前|以前|此前|在此之前)", "before"),
        (r"(?:之后|之后|此后|后来|此后)", "after"),
        (r"(?:同时|与此同时|同时|与此同时)", "concurrent"),
        (r"(?:第[一二三四五六七八九十\d]+天|第[一二三四五六七八九十\d]+周|第[一二三四五六七八九十\d]+月)", "phase"),
        # 英文
        (r"(?:first|initially|at first|to start)", "start"),
        (r"(?:then|next|after that|subsequently|following)", "next"),
        (r"(?:finally|at last|in the end|completed)", "end"),
        (r"(?:before|prior to|previously)", "before"),
        (r"(?:after|afterwards|later|since)", "after"),
        (r"(?:meanwhile|simultaneously|at the same time)", "concurrent"),
    ]

    @staticmethod
    def _cosine_sim(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService

                self._embedder = EmbeddingService(self.config)
            except Exception:
                self._embedder = None
        return self._embedder

    def build_timeline(self, drawers: list[Drawer], wing: str = None) -> list[TimelineEvent]:
        """构建时间线

        Args:
            drawers: 记忆列表
            wing: 限定 Wing

        Returns:
            按时间排序的事件列表
        """
        events = []
        for d in drawers:
            if wing and d.wing != wing:
                continue

            try:
                ts = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                ts = datetime.now()

            events.append(
                TimelineEvent(
                    id=f"evt_{d.id}",
                    drawer_id=d.id,
                    content=d.content,
                    timestamp=ts.isoformat(),
                    wing=d.wing,
                    room=d.room,
                    importance=d.importance,
                    tags=d.tags or [],
                )
            )

        events.sort(key=lambda e: e.timestamp)
        return events

    def _check_event_pair_causal(self, a: TimelineEvent, b: TimelineEvent, min_confidence: float) -> CausalLink | None:
        """检查两个事件对之间的因果关系"""
        try:
            ta = datetime.fromisoformat(a.timestamp)
            tb = datetime.fromisoformat(b.timestamp)
            delta_hours = (tb - ta).total_seconds() / 3600
        except (ValueError, TypeError):
            delta_hours = 0

        confidence = self._check_causal_pattern(a.content, b.content)
        if confidence > 0:
            time_factor = 1.0 if delta_hours <= 24 else max(0.3, 1.0 - delta_hours / 720)
            confidence *= time_factor

        if confidence == 0 and self.embedder:
            confidence = self._check_semantic_similarity(a.content, b.content, confidence)

        if confidence >= min_confidence:
            return CausalLink(
                source_id=a.drawer_id,
                target_id=b.drawer_id,
                confidence=round(confidence, 4),
                reason=self._describe_causal(a, b, confidence),
                source_content=a.content[:100],
                target_content=b.content[:100],
            )
        return None

    def find_causal_links(self, events: list[TimelineEvent], min_confidence: float = 0.5) -> list[CausalLink]:
        """发现事件间的因果关系

        Args:
            events: 按时间排序的事件列表
            min_confidence: 最小置信度

        Returns:
            因果关联列表
        """
        links = []

        for i in range(len(events)):
            for j in range(i + 1, min(i + 10, len(events))):
                link = self._check_event_pair_causal(events[i], events[j], min_confidence)
                if link:
                    links.append(link)

        links.sort(key=lambda link: link.confidence, reverse=True)
        return links

    def _check_causal_pattern(self, text_a: str, text_b: str) -> float:
        """检查是否存在因果模式"""
        text_a_lower = text_a.lower()
        text_b_lower = text_b.lower()
        combined = text_a_lower + " " + text_b_lower

        max_conf = 0.0
        for pattern, base_conf in self.CAUSAL_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                max_conf = max(max_conf, base_conf)

        return max_conf

    def _describe_causal(self, a: TimelineEvent, b: TimelineEvent, confidence: float) -> str:
        """描述因果关系"""
        if confidence >= 0.8:
            return f"强烈因果：'{a.content[:30]}...' 很可能导致了 '{b.content[:30]}...'"
        elif confidence >= 0.6:
            return f"可能因果：'{a.content[:30]}...' 与 '{b.content[:30]}...' 存在时序关联"
        else:
            return f"潜在关联：'{a.content[:30]}...' 和 '{b.content[:30]}...' 话题相关"

    def _check_semantic_similarity(self, content_a: str, content_b: str, current_confidence: float) -> float:
        try:
            emb_a = self.embedder.embed(content_a)
            emb_b = self.embedder.embed(content_b)
            sim = self._cosine_sim(emb_a, emb_b)
            if sim > 0.5:
                return min(0.4, sim * 0.5)
        except Exception:
            pass
        return current_confidence

    def build_event_chain(self, events: list[TimelineEvent], max_gap_hours: float = 72) -> list[EventChain]:
        """构建事件链（将时间相近的事件分组）

        Args:
            events: 时间线事件
            max_gap_hours: 最大时间间隔（小时），超过则视为新链

        Returns:
            事件链列表
        """
        if not events:
            return []

        chains = []
        current_chain = [events[0]]

        for i in range(1, len(events)):
            try:
                prev_ts = datetime.fromisoformat(current_chain[-1].timestamp)
                curr_ts = datetime.fromisoformat(events[i].timestamp)
                gap = (curr_ts - prev_ts).total_seconds() / 3600
            except (ValueError, TypeError):
                gap = 0

            # 同一 Wing 且时间间隔小 → 同一链
            same_wing = current_chain[-1].wing == events[i].wing
            if same_wing and gap <= max_gap_hours:
                current_chain.append(events[i])
            else:
                chains.append(self._finalize_chain(current_chain))
                current_chain = [events[i]]

        chains.append(self._finalize_chain(current_chain))
        return chains

    def _finalize_chain(self, events: list[TimelineEvent]) -> EventChain:
        """完成事件链"""
        if not events:
            return EventChain(id="empty", events=[], span="", summary="")

        start = events[0].timestamp[:10]
        end = events[-1].timestamp[:10]
        span = f"{start} ~ {end}"

        # 生成摘要
        contents = [e.content[:80] for e in events[:5]]
        summary = " → ".join(contents)
        if len(events) > 5:
            summary += f" ... (共 {len(events)} 个事件)"

        chain_id = hex_digest("".join(e.drawer_id for e in events))[:12]

        return EventChain(
            id=chain_id,
            events=events,
            span=span,
            summary=summary,
        )

    def query_timeline(
        self,
        events: list[TimelineEvent],
        start: str = None,
        end: str = None,
        wing: str = None,
        room: str = None,
        tags: list[str] = None,
    ) -> list[TimelineEvent]:
        """时序查询

        Args:
            events: 事件列表
            start: 开始时间 (ISO 格式)
            end: 结束时间 (ISO 格式)
            wing: 限定 Wing
            room: 限定 Room
            tags: 限定标签

        Returns:
            匹配的事件列表
        """
        result = []

        for e in events:
            if wing and e.wing != wing:
                continue
            if room and e.room != room:
                continue
            if tags:
                if not any(t in (e.tags or []) for t in tags):
                    continue

            if start:
                try:
                    s = datetime.fromisoformat(start)
                    if datetime.fromisoformat(e.timestamp) < s:
                        continue
                except (ValueError, TypeError):
                    pass

            if end:
                try:
                    ed = datetime.fromisoformat(end)
                    if datetime.fromisoformat(e.timestamp) > ed:
                        continue
                except (ValueError, TypeError):
                    pass

            result.append(e)

        return result

    def find_temporal_markers(self, text: str) -> list[str]:
        """在文本中找时序标记"""
        markers = []
        for pattern, marker_type in self.TEMPORAL_MARKERS:
            if re.search(pattern, text, re.IGNORECASE):
                if marker_type not in markers:
                    markers.append(marker_type)
        return markers

    def timeline_stats(self, events: list[TimelineEvent]) -> dict:
        """时间线统计"""
        if not events:
            return {"total_events": 0, "span_days": 0, "events_per_day": 0}

        try:
            first = datetime.fromisoformat(events[0].timestamp)
            last = datetime.fromisoformat(events[-1].timestamp)
            span_days = max(1, (last - first).days)
        except (ValueError, TypeError):
            span_days = 1

        return {
            "total_events": len(events),
            "span_days": span_days,
            "events_per_day": round(len(events) / span_days, 1),
            "first_event": events[0].timestamp[:10],
            "last_event": events[-1].timestamp[:10],
            "wings": len(set(e.wing for e in events)),
            "rooms": len(set((e.wing, e.room) for e in events)),
        }

    def detect_temporal_patterns(self, events: list[TimelineEvent]) -> list[dict]:
        """检测时序模式（周期性、突发等）"""
        patterns = []
        if len(events) < 3:
            return patterns

        # 按天聚合
        daily_counts = defaultdict(int)
        for e in events:
            try:
                day = datetime.fromisoformat(e.timestamp).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
            daily_counts[day] += 1

        if not daily_counts:
            return patterns

        avg_per_day = sum(daily_counts.values()) / len(daily_counts)

        # 检测突发日
        burst_days = []
        for day, count in daily_counts.items():
            if count >= avg_per_day * 3 and count >= 3:
                burst_days.append({"date": day, "count": count})

        if burst_days:
            patterns.append(
                {
                    "type": "burst",
                    "description": f"发现 {len(burst_days)} 个突发日（事件数远超平均）",
                    "details": burst_days[:5],
                }
            )

        # 检测活跃时段
        hour_counts = defaultdict(int)
        for e in events:
            try:
                hour = datetime.fromisoformat(e.timestamp).hour
            except (ValueError, TypeError):
                continue
            hour_counts[hour] += 1

        if hour_counts:
            active_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            patterns.append(
                {
                    "type": "active_hours",
                    "description": "最活跃时段",
                    "details": [{"hour": h, "count": c} for h, c in active_hours],
                }
            )

        return patterns
