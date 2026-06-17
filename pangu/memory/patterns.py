"""盘古模式识别引擎 — 发现记忆中的重复模式和规律
====================================================
从记忆数据中自动发现隐藏的模式和规律。

支持：
- 频率模式：发现频繁出现的主题/标签组合
- 序列模式：发现事件发生的先后顺序规律
- 关联模式：发现经常一起出现的记忆主题
- 异常模式：发现偏离常规的记忆行为
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class DiscoveredPattern:
    """发现的模式"""
    id: str
    pattern_type: str  # frequency, sequence, association, anomaly
    description: str
    evidence: list[str]  # 证据（记忆 ID 列表）
    confidence: float
    frequency: int = 0
    metadata: dict = field(default_factory=dict)


class PatternEngine:
    """模式识别引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def discover_all(self, drawers: list[Drawer]) -> list[DiscoveredPattern]:
        """发现所有模式"""
        patterns = []
        patterns.extend(self.find_frequency_patterns(drawers))
        patterns.extend(self.find_association_patterns(drawers))
        patterns.extend(self.find_sequence_patterns(drawers))
        patterns.extend(self.find_anomaly_patterns(drawers))
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def find_frequency_patterns(self, drawers: list[Drawer],
                                min_count: int = 3) -> list[DiscoveredPattern]:
        """发现频率模式：频繁出现的标签/主题组合"""
        patterns = []

        # 标签频率
        tag_counter = Counter()
        for d in drawers:
            for tag in (d.tags or []):
                tag_counter[tag] += 1

        for tag, count in tag_counter.most_common():
            if count >= min_count:
                evidence = [d.id for d in drawers if tag in (d.tags or [])]
                patterns.append(DiscoveredPattern(
                    id=f"freq_tag_{tag}",
                    pattern_type="frequency",
                    description=f"标签 '{tag}' 出现 {count} 次（{count/len(drawers)*100:.1f}%）",
                    evidence=evidence[:5],
                    confidence=min(1.0, count / 10),
                    frequency=count,
                    metadata={"tag": tag, "percentage": round(count/len(drawers)*100, 1)},
                ))

        # Wing/Room 频率
        room_counter = Counter(f"{d.wing}/{d.room}" for d in drawers)
        for room, count in room_counter.most_common(5):
            if count >= min_count:
                evidence = [d.id for d in drawers
                            if f"{d.wing}/{d.room}" == room]
                patterns.append(DiscoveredPattern(
                    id=f"freq_room_{room.replace('/', '_')}",
                    pattern_type="frequency",
                    description=f"Room '{room}' 聚集了 {count} 条记忆",
                    evidence=evidence[:5],
                    confidence=min(1.0, count / max(10, len(drawers))),
                    frequency=count,
                ))

        return patterns

    def find_association_patterns(self, drawers: list[Drawer],
                                  min_cooccurrence: int = 2,
                                  min_confidence: float = 0.3) -> list[DiscoveredPattern]:
        """发现关联模式：经常一起出现的标签/主题"""
        patterns = []

        # 标签共现
        tag_cooccur = Counter()
        tag_memories = defaultdict(set)
        for d in drawers:
            tags = d.tags or []
            for tag in tags:
                tag_memories[tag].add(d.id)
            for t1, t2 in combinations(sorted(tags), 2):
                tag_cooccur[(t1, t2)] += 1

        for (t1, t2), count in tag_cooccur.most_common(10):
            if count >= min_cooccurrence:
                support = count / len(drawers)
                confidence = min(1.0, support * 5)
                if confidence >= min_confidence:
                    patterns.append(DiscoveredPattern(
                        id=f"assoc_{t1}_{t2}",
                        pattern_type="association",
                        description=f"标签 '{t1}' 和 '{t2}' 经常一起出现（{count} 次）",
                        evidence=list(tag_memories[t1] & tag_memories[t2])[:5],
                        confidence=round(confidence, 4),
                        frequency=count,
                        metadata={"tags": [t1, t2], "cooccurrence": count},
                    ))

        # Wing 跨空间关联
        if len(set(d.wing for d in drawers)) > 1:
            import re
            wing_pairs, wing_evidence = self._find_wing_cross_pairs(drawers)

            for (w1, w2), count in wing_pairs.most_common(5):
                if count >= min_cooccurrence:
                    patterns.append(DiscoveredPattern(
                        id=f"cross_wing_{w1}_{w2}",
                        pattern_type="association",
                        description=f"Wing '{w1}' 和 '{w2}' 存在 {count} 次内容关联",
                        evidence=list(set(wing_evidence[(w1, w2)]))[:5],
                        confidence=min(1.0, count / 20),
                        frequency=count,
                    ))

        return patterns

    def find_sequence_patterns(self, drawers: list[Drawer],
                               min_sequence: int = 2) -> list[DiscoveredPattern]:
        """发现序列模式：事件发生的先后顺序规律"""
        patterns = []

        # 按时间排序
        sorted_drawers = sorted(drawers, key=lambda d: d.created_at or "")

        # 统计相邻标签序列
        tag_sequences = self._count_tag_sequences(sorted_drawers)

        for (t1, t2), count in tag_sequences.most_common(10):
            if count >= min_sequence:
                patterns.append(DiscoveredPattern(
                    id=f"seq_{t1}_{t2}",
                    pattern_type="sequence",
                    description=f"标签 '{t1}' 后经常出现 '{t2}'（{count} 次）",
                    evidence=[],
                    confidence=min(1.0, count / 5),
                    frequency=count,
                    metadata={"from": t1, "to": t2},
                ))

        # 统计相邻 Room 序列
        room_sequences = Counter()
        for i in range(len(sorted_drawers) - 1):
            r1 = f"{sorted_drawers[i].wing}/{sorted_drawers[i].room}"
            r2 = f"{sorted_drawers[i+1].wing}/{sorted_drawers[i+1].room}"
            if r1 != r2:
                room_sequences[(r1, r2)] += 1

        for (r1, r2), count in room_sequences.most_common(5):
            if count >= min_sequence:
                patterns.append(DiscoveredPattern(
                    id=f"seq_room_{r1}_{r2}".replace("/", "_"),
                    pattern_type="sequence",
                    description=f"Room '{r1}' 后常跟随 '{r2}'（{count} 次）",
                    evidence=[],
                    confidence=min(1.0, count / 5),
                    frequency=count,
                ))

        return patterns

    def find_anomaly_patterns(self, drawers: list[Drawer]) -> list[DiscoveredPattern]:
        """发现异常模式：偏离常规的记忆行为"""
        patterns = []

        if len(drawers) < 5:
            return patterns

        # 内容长度异常
        lengths = [len(d.content) for d in drawers]
        avg_len = sum(lengths) / len(lengths)
        std_len = (sum((len_val - avg_len) ** 2 for len_val in lengths) / len(lengths)) ** 0.5

        for d in drawers:
            if abs(len(d.content) - avg_len) > 3 * std_len:
                patterns.append(DiscoveredPattern(
                    id=f"anomaly_len_{d.id}",
                    pattern_type="anomaly",
                    description=f"记忆 '{d.id}' 内容长度异常（{len(d.content)} 字符，"
                                f"平均 {avg_len:.0f}±{std_len:.0f}）",
                    evidence=[d.id],
                    confidence=0.6,
                    metadata={"memory_id": d.id, "length": len(d.content),
                              "avg": round(avg_len), "std": round(std_len)},
                ))

        # 重要性异常
        importances = [d.importance for d in drawers]
        avg_imp = sum(importances) / len(importances)
        std_imp = (sum((i - avg_imp) ** 2 for i in importances) / len(importances)) ** 0.5
        patterns.extend(self._detect_importance_anomalies(drawers, avg_imp, std_imp))

        # 时间分布异常
        try:
            dates = [datetime.fromisoformat(d.created_at)
                     for d in drawers if d.created_at]
            if dates:
                day_counts = defaultdict(int)
                for dt in dates:
                    day_counts[dt.strftime("%Y-%m-%d")] += 1

                avg_per_day = sum(day_counts.values()) / len(day_counts)
                for day, count in day_counts.items():
                    if count >= avg_per_day * 3 and count >= 3:
                        patterns.append(DiscoveredPattern(
                            id=f"anomaly_burst_{day}",
                            pattern_type="anomaly",
                            description=f"日期 {day} 出现记忆爆发（{count} 条，日均 {avg_per_day:.1f}）",
                            evidence=[],
                            confidence=0.7,
                            metadata={"date": day, "count": count,
                                      "avg": round(avg_per_day, 1)},
                        ))
        except (ValueError, TypeError):
            pass

        return patterns

    def _detect_importance_anomalies(self, drawers: list[Drawer], avg_imp: float,
                                     std_imp: float) -> list[DiscoveredPattern]:
        patterns = []
        if std_imp <= 0:
            return patterns
        for d in drawers:
            z_score = (d.importance - avg_imp) / std_imp
            if abs(z_score) > 2.5:
                direction = "高" if z_score > 0 else "低"
                patterns.append(DiscoveredPattern(
                    id=f"anomaly_imp_{d.id}",
                    pattern_type="anomaly",
                    description=f"记忆 '{d.id}' 重要性异常偏{direction}"
                                f"（{d.importance}，平均 {avg_imp:.1f}±{std_imp:.1f}）",
                    evidence=[d.id],
                    confidence=0.5,
                    metadata={"memory_id": d.id, "importance": d.importance,
                              "z_score": round(z_score, 2)},
                ))
        return patterns

    def pattern_stats(self, patterns: list[DiscoveredPattern]) -> dict:
        """模式统计"""
        type_counts = Counter(p.pattern_type for p in patterns)
        return {
            "total_patterns": len(patterns),
            "by_type": dict(type_counts),
            "avg_confidence": round(
                sum(p.confidence for p in patterns) / len(patterns), 4
            ) if patterns else 0.0,
            "high_confidence": sum(1 for p in patterns if p.confidence >= 0.7),
            "medium_confidence": sum(1 for p in patterns if 0.3 <= p.confidence < 0.7),
            "low_confidence": sum(1 for p in patterns if p.confidence < 0.3),
        }

    def pattern_insights(self, patterns: list[DiscoveredPattern]) -> list[str]:
        """从模式中提取洞察"""
        insights = []

        frequency_patterns = [p for p in patterns if p.pattern_type == "frequency"]
        if frequency_patterns:
            top = frequency_patterns[0]
            insights.append(f"最频繁主题：{top.description}")

        association_patterns = [p for p in patterns if p.pattern_type == "association"]
        if association_patterns:
            top = association_patterns[0]
            insights.append(f"最强关联：{top.description}")

        sequence_patterns = [p for p in patterns if p.pattern_type == "sequence"]
        if sequence_patterns:
            top = sequence_patterns[0]
            insights.append(f"常见序列：{top.description}")

        anomaly_patterns = [p for p in patterns if p.pattern_type == "anomaly"]
        if anomaly_patterns:
            insights.append(f"发现 {len(anomaly_patterns)} 个异常模式")

        return insights

    def _find_wing_cross_pairs(self, drawers):
        import re
        wing_pairs = Counter()
        wing_evidence = defaultdict(list)
        for i in range(len(drawers)):
            for j in range(i + 1, len(drawers)):
                if drawers[i].wing != drawers[j].wing:
                    self._check_wing_pair(drawers, i, j, wing_pairs, wing_evidence)
        return wing_pairs, wing_evidence

    def _check_wing_pair(self, drawers, i, j, wing_pairs, wing_evidence):
        import re
        words_i = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                  drawers[i].content.lower()))
        words_j = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                  drawers[j].content.lower()))
        overlap = len(words_i & words_j)
        if overlap >= 2:
            key = tuple(sorted([drawers[i].wing, drawers[j].wing]))
            wing_pairs[key] += 1
            wing_evidence[key].extend([drawers[i].id, drawers[j].id])

    def _count_tag_sequences(self, sorted_drawers):
        tag_sequences = Counter()
        for i in range(len(sorted_drawers) - 1):
            tags_i = sorted_drawers[i].tags or []
            tags_j = sorted_drawers[i + 1].tags or []
            for t1 in tags_i:
                for t2 in tags_j:
                    if t1 != t2:
                        tag_sequences[(t1, t2)] += 1
        return tag_sequences
