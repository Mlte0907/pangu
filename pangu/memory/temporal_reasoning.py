"""盘古时间推理 — 时间感知记忆，理解事件时间线

核心能力：
1. 时间线构建：从记忆中提取时间信息，构建事件时间线
2. 时序推理：基于时间顺序推断因果关系
3. 时间查询：按时间范围查询记忆
4. 时效性评估：评估记忆的时效性和新鲜度
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger("pangu.memory.temporal_reasoning")


@dataclass
class TimeEvent:
    """时间事件"""
    memory_id: str
    content: str
    timestamp: str
    wing: str
    importance: float
    time_parsed: datetime | None = None


@dataclass
class TemporalRelation:
    """时间关系"""
    before_id: str
    after_id: str
    relation: str  # before / after / during / caused_by
    confidence: float


class TemporalReasoning:
    """时间推理引擎"""

    TIME_PATTERNS = [
        (r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日]?', "%Y-%m-%d"),
        (r'(\d{1,2})[月/-](\d{1,2})[日]?', None),
        (r'(\d{4})年(\d{1,2})月', "%Y-%m"),
        (r'(昨天|今天|前天|明天|后天)', None),
        (r'(\d+)(天|周|月|年)(前|后)', None),
    ]

    TEMPORAL_WORDS = {
        "before": ["之前", "以前", "先前", "之前"],
        "after": ["之后", "以后", "随后", "然后"],
        "cause": ["因为", "由于", "导致", "所以", "因此"],
        "concurrent": ["同时", "一起", "一块", "一同"],
    }

    def __init__(self, config=None):
        self.config = config

    def build_timeline(self, drawers: list) -> list[TimeEvent]:
        """构建时间线"""
        events = []

        for d in drawers:
            ts = self._parse_time(d.content)
            if ts:
                events.append(TimeEvent(
                    memory_id=d.id,
                    content=d.content[:100],
                    timestamp=ts.isoformat(),
                    wing=d.wing,
                    importance=d.importance,
                    time_parsed=ts,
                ))

        events.sort(key=lambda e: e.time_parsed or datetime.min)
        return events

    def find_temporal_relations(self, drawers: list) -> list[TemporalRelation]:
        """发现时间关系"""
        relations = []

        for i, d1 in enumerate(drawers):
            for j, d2 in enumerate(drawers):
                if i >= j:
                    continue

                # 检查因果关系
                c1 = d1.content.lower()
                c2 = d2.content.lower()

                for cause_word in self.TEMPORAL_WORDS["cause"]:
                    if cause_word in c1 and any(w in c2 for w in ["所以", "因此", "导致"]):
                        relations.append(TemporalRelation(
                            before_id=d1.id,
                            after_id=d2.id,
                            relation="caused_by",
                            confidence=0.7,
                        ))

                # 检查先后关系
                for before_word in self.TEMPORAL_WORDS["before"]:
                    if before_word in c2 and d1.content[:20] in c2:
                        relations.append(TemporalRelation(
                            before_id=d1.id,
                            after_id=d2.id,
                            relation="before",
                            confidence=0.6,
                        ))

        return relations

    def query_by_time_range(self, drawers: list, start: str = None,
                            end: str = None) -> list:
        """按时间范围查询记忆"""
        start_dt = self._parse_time_string(start) if start else None
        end_dt = self._parse_time_string(end) if end else None

        results = []
        for d in drawers:
            ts = self._parse_time(d.content)
            if ts is None:
                continue
            if start_dt and ts < start_dt:
                continue
            if end_dt and ts > end_dt:
                continue
            results.append(d)

        return results

    def evaluate_freshness(self, drawer) -> dict:
        """评估记忆时效性"""
        ts = self._parse_time(drawer.content)
        now = datetime.now()

        if ts is None:
            return {
                "freshness": "unknown",
                "age_days": None,
                "recommendation": "无法确定时间，建议保留",
            }

        age = (now - ts).days

        if age < 7:
            freshness = "fresh"
            recommendation = "新记忆，保持活跃"
        elif age < 30:
            freshness = "recent"
            recommendation = "近期记忆，适度关注"
        elif age < 90:
            freshness = "aging"
            recommendation = "较旧记忆，考虑巩固"
        else:
            freshness = "old"
            recommendation = "老旧记忆，考虑归档或压缩"

        return {
            "freshness": freshness,
            "age_days": age,
            "timestamp": ts.isoformat(),
            "recommendation": recommendation,
        }

    def _parse_time(self, text: str) -> datetime | None:
        """从文本中解析时间"""
        now = datetime.now()

        # 相对时间
        m = re.search(r'(\d+)(天|周|月|年)(前|后)', text)
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            direction = m.group(3)
            delta_map = {"天": timedelta(days=num), "周": timedelta(weeks=num),
                         "月": timedelta(days=num * 30), "年": timedelta(days=num * 365)}
            delta = delta_map.get(unit, timedelta())
            return now - delta if direction == "前" else now + delta

        # 今天/昨天/前天
        if "前天" in text:
            return now - timedelta(days=2)
        if "昨天" in text:
            return now - timedelta(days=1)
        if "今天" in text:
            return now
        if "明天" in text:
            return now + timedelta(days=1)

        # 绝对日期
        m = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        return None

    def _parse_time_string(self, s: str) -> datetime | None:
        """解析时间字符串"""
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return self._parse_time(s)

    def get_temporal_stats(self, drawers: list) -> dict:
        """获取时间统计"""
        total = len(drawers)
        time_found = 0
        by_month: dict[str, int] = {}

        for d in drawers:
            ts = self._parse_time(d.content)
            if ts:
                time_found += 1
                key = ts.strftime("%Y-%m")
                by_month[key] = by_month.get(key, 0) + 1

        return {
            "total_memories": total,
            "with_time": time_found,
            "time_coverage": time_found / max(total, 1),
            "by_month": dict(sorted(by_month.items())[-12:]),
        }


_temporal_engine: TemporalReasoning | None = None


def get_temporal_engine(config=None) -> TemporalReasoning:
    """获取全局时间推理实例"""
    global _temporal_engine
    if _temporal_engine is None:
        _temporal_engine = TemporalReasoning(config)
    return _temporal_engine
