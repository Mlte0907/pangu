"""盘古高级推理引擎 — 因果推断、趋势预测与异常检测
====================================================
从记忆数据中自动发现因果关系、预测发展趋势、检测异常模式。

支持：
- 因果链自动发现（基于时序关联和共现分析）
- 趋势预测（基于历史模式的外推）
- 异常检测和预警（统计偏差 + 语义漂移）
- 知识缺口识别（发现推理链中的缺失环节）
"""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from itertools import combinations

from ..core.config import PanguConfig
from ..core.palace import Drawer


class ReasoningType(str, Enum):
    """推理类型"""
    CAUSAL = "causal"          # 因果推理
    TREND = "trend"            # 趋势预测
    ANOMALY = "anomaly"        # 异常检测
    GAP = "gap"                # 知识缺口


class AnomalySeverity(str, Enum):
    """异常严重度"""
    CRITICAL = "critical"      # 严重异常
    HIGH = "high"              # 高风险
    MEDIUM = "medium"          # 中等
    LOW = "low"                # 低风险


class TrendDirection(str, Enum):
    """趋势方向"""
    RISING = "rising"          # 上升
    FALLING = "falling"        # 下降
    STABLE = "stable"          # 平稳
    VOLATILE = "volatile"      # 波动


@dataclass
class CausalLink:
    """因果链"""
    id: str
    cause: str                 # 原因（记忆 ID 或主题）
    effect: str                # 结果（记忆 ID 或主题）
    confidence: float          # 因果置信度 [0,1]
    evidence: list[str]        # 支撑证据
    mechanism: str = ""        # 推断的因果机制
    temporal_lag: float = 0.0  # 时间延迟（小时）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TrendPrediction:
    """趋势预测"""
    id: str
    subject: str               # 预测对象
    direction: TrendDirection
    confidence: float          # 预测置信度 [0,1]
    historical_values: list[float]  # 历史值
    predicted_values: list[float]   # 预测值
    time_horizon_hours: float  # 预测时间窗口
    factors: list[str]         # 影响因素
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AnomalyAlert:
    """异常预警"""
    id: str
    anomaly_type: str          # 异常类型
    description: str
    severity: AnomalySeverity
    evidence: list[str]        # 相关记忆 ID
    expected_value: float      # 期望值
    actual_value: float        # 实际值
    deviation: float           # 偏差度
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class KnowledgeGap:
    """知识缺口"""
    id: str
    topic: str                 # 缺口主题
    description: str           # 缺口描述
    related_knowledge: list[str]  # 已有相关知识
    missing_links: list[str]   # 缺失的连接
    priority: float            # 优先级 [0,1]
    suggested_actions: list[str]  # 建议行动
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AdvancedReasoning:
    """高级推理引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    # ── 因果链发现 ──────────────────────────────────────────────

    def discover_causal_chains(
        self,
        drawers: list[Drawer],
        min_support: int = 3,
        max_lag_hours: float = 48.0,
    ) -> list[CausalLink]:
        """自动发现因果链

        基于以下信号推断因果关系：
        1. 时序先后：A 总是在 B 之前出现
        2. 共现频率：A 和 B 同时出现的频率
        3. 标签关联：A 和 B 共享关键标签

        Args:
            drawers: 记忆列表
            min_support: 最小支撑度（同时出现次数）
            max_lag_hours: 最大允许时间延迟（小时）

        Returns:
            因果链列表，按置信度降序
        """
        if len(drawers) < 2:
            return []

        # 按时间排序
        sorted_drawers = sorted(drawers, key=lambda d: d.created_at)
        causal_links: list[CausalLink] = []

        # 构建标签索引
        tag_index: dict[str, list[int]] = defaultdict(list)
        for i, d in enumerate(sorted_drawers):
            for tag in (d.tags or []):
                tag_index[tag].append(i)

        # 分析标签对的时序关联
        tag_pairs = list(combinations(tag_index.keys(), 2))
        for tag_a, tag_b in tag_pairs:
            indices_a = tag_index[tag_a]
            indices_b = tag_index[tag_b]

            # 统计 A→B 的先后出现次数
            forward_count = 0
            lags: list[float] = []
            for i_a in indices_a:
                for i_b in indices_b:
                    if i_b <= i_a:
                        continue
                    # 计算时间差
                    try:
                        t_a = datetime.fromisoformat(sorted_drawers[i_a].created_at)
                        t_b = datetime.fromisoformat(sorted_drawers[i_b].created_at)
                        lag = (t_b - t_a).total_seconds() / 3600
                        if 0 < lag <= max_lag_hours:
                            forward_count += 1
                            lags.append(lag)
                    except (ValueError, TypeError):
                        continue

            if forward_count >= min_support:
                # 计算因果置信度
                total_pairs = len(indices_a) * len(indices_b) or 1
                confidence = min(1.0, forward_count / max(total_pairs * 0.3, 1))
                avg_lag = sum(lags) / len(lags) if lags else 0.0

                # 收集证据
                evidence_ids = []
                for i_a in indices_a[:3]:
                    evidence_ids.append(sorted_drawers[i_a].id)
                for i_b in indices_b[:3]:
                    if sorted_drawers[i_b].id not in evidence_ids:
                        evidence_ids.append(sorted_drawers[i_b].id)

                causal_links.append(CausalLink(
                    id=f"causal_{tag_a}_{tag_b}",
                    cause=tag_a,
                    effect=tag_b,
                    confidence=round(confidence, 3),
                    evidence=evidence_ids[:6],
                    mechanism=f"标签 '{tag_a}' 后倾向于出现 '{tag_b}'（{forward_count}次，平均延迟{avg_lag:.1f}h）",
                    temporal_lag=round(avg_lag, 1),
                ))

        # 按置信度排序
        causal_links.sort(key=lambda c: c.confidence, reverse=True)
        return causal_links

    def infer_causal_path(
        self,
        cause: str,
        effect: str,
        causal_chains: list[CausalLink],
    ) -> list[CausalLink] | None:
        """推理从 cause 到 effect 的因果路径

        使用 BFS 在因果图中搜索最短路径。

        Args:
            cause: 起始节点（主题/标签）
            effect: 目标节点（主题/标签）
            causal_chains: 已发现的因果链

        Returns:
            因果路径（因果链列表），未找到返回 None
        """
        # 构建邻接表
        graph: dict[str, list[CausalLink]] = defaultdict(list)
        for link in causal_chains:
            graph[link.cause].append(link)

        # BFS 搜索
        visited: set[str] = set()
        queue: list[list[CausalLink]] = [[link] for link in graph.get(cause, [])]

        while queue:
            path = queue.pop(0)
            current = path[-1].effect

            if current == effect:
                return path

            if current in visited:
                continue
            visited.add(current)

            for link in graph.get(current, []):
                if link.effect not in visited:
                    queue.append(path + [link])

        return None

    # ── 趋势预测 ──────────────────────────────────────────────

    def predict_trends(
        self,
        drawers: list[Drawer],
        window_hours: float = 168.0,  # 7 天
        prediction_hours: float = 72.0,  # 预测未来 3 天
    ) -> list[TrendPrediction]:
        """基于历史模式预测趋势

        分析记忆的创建频率、标签热度、活跃度变化。

        Args:
            drawers: 记忆列表
            window_hours: 历史分析窗口（小时）
            prediction_hours: 预测时间窗口（小时）

        Returns:
            趋势预测列表
        """
        if not drawers:
            return []

        now = datetime.now()
        predictions: list[TrendPrediction] = []

        # 按时间窗口分桶统计
        buckets = self._time_bucket(drawers, bucket_hours=24.0)
        if len(buckets) < 3:
            return []

        # 每日记忆数趋势
        daily_counts = [len(b) for b in buckets]
        direction, confidence = self._analyze_direction(daily_counts)

        # 线性外推预测
        predicted = self._linear_extrapolate(daily_counts, steps=int(prediction_hours / 24))

        predictions.append(TrendPrediction(
            id="trend_daily_volume",
            subject="每日记忆创建量",
            direction=direction,
            confidence=confidence,
            historical_values=[float(c) for c in daily_counts],
            predicted_values=predicted,
            time_horizon_hours=prediction_hours,
            factors=["时间窗口活跃度"],
        ))

        # 标签热度趋势
        tag_trends = self._tag_heat_trends(drawers, buckets)
        predictions.extend(tag_trends)

        return predictions

    def _time_bucket(
        self, drawers: list[Drawer], bucket_hours: float = 24.0
    ) -> list[list[Drawer]]:
        """将记忆按时间窗口分桶"""
        if not drawers:
            return []

        sorted_drawers = sorted(drawers, key=lambda d: d.created_at)
        buckets: list[list[Drawer]] = [[]]
        try:
            base = datetime.fromisoformat(sorted_drawers[0].created_at)
        except (ValueError, TypeError):
            return [sorted_drawers]

        for d in sorted_drawers:
            try:
                t = datetime.fromisoformat(d.created_at)
                elapsed = (t - base).total_seconds() / 3600
                bucket_idx = int(elapsed / bucket_hours)
                while len(buckets) <= bucket_idx:
                    buckets.append([])
                buckets[bucket_idx].append(d)
            except (ValueError, TypeError):
                buckets[-1].append(d)

        return buckets

    def _analyze_direction(self, values: list[float]) -> tuple[TrendDirection, float]:
        """分析数值序列的趋势方向"""
        if len(values) < 2:
            return TrendDirection.STABLE, 0.0

        n = len(values)
        # 简单线性回归斜率
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n)) or 1
        slope = numerator / denominator

        # 标准差
        variance = sum((v - y_mean) ** 2 for v in values) / n or 1
        std = math.sqrt(variance)

        # 归一化斜率
        norm_slope = slope / (std or 1)

        # 判断方向和置信度
        if abs(norm_slope) < 0.1:
            return TrendDirection.STABLE, 0.5
        elif abs(norm_slope) > 1.0:
            # 高波动
            diffs = [values[i] - values[i - 1] for i in range(1, n)]
            sign_changes = sum(1 for i in range(1, len(diffs)) if diffs[i] * diffs[i - 1] < 0)
            if sign_changes > n * 0.4:
                return TrendDirection.VOLATILE, min(1.0, 0.3 + sign_changes / n)

        if norm_slope > 0:
            return TrendDirection.RISING, min(1.0, 0.5 + abs(norm_slope) * 0.2)
        else:
            return TrendDirection.FALLING, min(1.0, 0.5 + abs(norm_slope) * 0.2)

    def _linear_extrapolate(self, values: list[float], steps: int) -> list[float]:
        """线性外推"""
        if len(values) < 2:
            return [values[-1]] * steps if values else [0.0] * steps

        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n)) or 1
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        return [max(0.0, slope * (n + i) + intercept) for i in range(steps)]

    def _tag_heat_trends(
        self, drawers: list[Drawer], buckets: list[list[Drawer]]
    ) -> list[TrendPrediction]:
        """分析标签热度趋势"""
        predictions: list[TrendPrediction] = []

        # 统计每个桶中标签出现次数
        tag_per_bucket: list[Counter] = []
        for bucket in buckets:
            counter: Counter = Counter()
            for d in bucket:
                for tag in (d.tags or []):
                    counter[tag] += 1
            tag_per_bucket.append(counter)

        if len(tag_per_bucket) < 3:
            return predictions

        # 找出热门标签（在至少 2 个桶中出现）
        all_tags = set()
        for c in tag_per_bucket:
            all_tags.update(c.keys())

        for tag in all_tags:
            values = [c.get(tag, 0) for c in tag_per_bucket]
            if sum(values) < 3:
                continue

            direction, confidence = self._analyze_direction(values)
            if direction == TrendDirection.STABLE:
                continue

            predicted = self._linear_extrapolate(values, steps=3)
            predictions.append(TrendPrediction(
                id=f"trend_tag_{tag}",
                subject=f"标签 '{tag}' 热度",
                direction=direction,
                confidence=confidence,
                historical_values=values,
                predicted_values=predicted,
                time_horizon_hours=72.0,
                factors=[f"标签在 {sum(values)} 条记忆中出现"],
            ))

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions[:5]

    # ── 异常检测 ──────────────────────────────────────────────

    def detect_anomalies(
        self,
        drawers: list[Drawer],
        z_threshold: float = 2.0,
    ) -> list[AnomalyAlert]:
        """检测记忆系统中的异常

        检测维度：
        1. 创建频率异常（突然暴增或骤降）
        2. 内容长度异常（异常长或短）
        3. 标签分布异常（某个标签突然集中出现）
        4. 时间间隔异常（创建间隔异常）

        Args:
            drawers: 记忆列表
            z_threshold: Z-score 阈值

        Returns:
            异常预警列表
        """
        alerts: list[AnomalyAlert] = []

        # 频率异常
        alerts.extend(self._detect_frequency_anomalies(drawers, z_threshold))
        # 内容异常
        alerts.extend(self._detect_content_anomalies(drawers, z_threshold))
        # 标签集中度异常
        alerts.extend(self._detect_tag_concentration(drawers, z_threshold))
        # 时间间隔异常
        alerts.extend(self._detect_interval_anomalies(drawers, z_threshold))

        alerts.sort(key=lambda a: a.severity.value, reverse=True)
        return alerts

    def _z_score(self, values: list[float], value: float) -> float:
        """计算 Z-score"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (value - mean) / std

    def _detect_frequency_anomalies(
        self, drawers: list[Drawer], z_threshold: float
    ) -> list[AnomalyAlert]:
        """检测频率异常"""
        alerts: list[AnomalyAlert] = []
        buckets = self._time_bucket(drawers, bucket_hours=6.0)
        if len(buckets) < 4:
            return alerts

        counts = [len(b) for b in buckets]
        for i, count in enumerate(counts):
            z = self._z_score(counts, count)
            if abs(z) > z_threshold:
                direction = "暴增" if z > 0 else "骤降"
                alerts.append(AnomalyAlert(
                    id=f"anomaly_freq_{i}",
                    anomaly_type="frequency",
                    description=f"6小时窗口内记忆创建量{direction}（Z={z:.2f}）",
                    severity=AnomalySeverity.HIGH if abs(z) > 3 else AnomalySeverity.MEDIUM,
                    evidence=[d.id for d in buckets[i][:5]],
                    expected_value=round(sum(counts) / len(counts), 1),
                    actual_value=float(count),
                    deviation=round(z, 2),
                ))

        return alerts

    def _detect_content_anomalies(
        self, drawers: list[Drawer], z_threshold: float
    ) -> list[AnomalyAlert]:
        """检测内容长度异常"""
        alerts: list[AnomalyAlert] = []
        if len(drawers) < 5:
            return alerts

        lengths = [len(d.content or "") for d in drawers]
        for d in drawers:
            content_len = len(d.content or "")
            z = self._z_score(lengths, content_len)
            if abs(z) > z_threshold:
                direction = "异常长" if z > 0 else "异常短"
                alerts.append(AnomalyAlert(
                    id=f"anomaly_content_{d.id}",
                    anomaly_type="content_length",
                    description=f"记忆 '{d.title}' 内容{direction}（{content_len}字符，Z={z:.2f}）",
                    severity=AnomalySeverity.LOW if abs(z) < 3 else AnomalySeverity.MEDIUM,
                    evidence=[d.id],
                    expected_value=round(sum(lengths) / len(lengths), 1),
                    actual_value=float(content_len),
                    deviation=round(z, 2),
                ))

        return alerts

    def _detect_tag_concentration(
        self, drawers: list[Drawer], z_threshold: float
    ) -> list[AnomalyAlert]:
        """检测标签集中度异常"""
        alerts: list[AnomalyAlert] = []
        buckets = self._time_bucket(drawers, bucket_hours=24.0)
        if len(buckets) < 3:
            return alerts

        for tag in set().union(*(d.tags or [] for d in drawers)):
            tag_counts = [
                sum(1 for d in b if tag in (d.tags or []))
                for b in buckets
            ]
            if sum(tag_counts) < 3:
                continue

            for i, count in enumerate(tag_counts):
                z = self._z_score(tag_counts, count)
                if abs(z) > z_threshold:
                    alerts.append(AnomalyAlert(
                        id=f"anomaly_tag_{tag}_{i}",
                        anomaly_type="tag_concentration",
                        description=f"标签 '{tag}' 在某天集中出现（{count}次，Z={z:.2f}）",
                        severity=AnomalySeverity.MEDIUM,
                        evidence=[d.id for d in buckets[i] if tag in (d.tags or [])][:5],
                        expected_value=round(sum(tag_counts) / len(tag_counts), 1),
                        actual_value=float(count),
                        deviation=round(z, 2),
                    ))

        return alerts

    def _detect_interval_anomalies(
        self, drawers: list[Drawer], z_threshold: float
    ) -> list[AnomalyAlert]:
        """检测时间间隔异常"""
        alerts: list[AnomalyAlert] = []
        sorted_drawers = sorted(drawers, key=lambda d: d.created_at)
        if len(sorted_drawers) < 5:
            return alerts

        intervals: list[float] = []
        for i in range(1, len(sorted_drawers)):
            try:
                t_prev = datetime.fromisoformat(sorted_drawers[i - 1].created_at)
                t_curr = datetime.fromisoformat(sorted_drawers[i].created_at)
                hours = (t_curr - t_prev).total_seconds() / 3600
                intervals.append(hours)
            except (ValueError, TypeError):
                continue

        if len(intervals) < 3:
            return alerts

        for i, interval in enumerate(intervals):
            z = self._z_score(intervals, interval)
            if abs(z) > z_threshold:
                direction = "异常长" if z > 0 else "异常短"
                alerts.append(AnomalyAlert(
                    id=f"anomaly_interval_{i}",
                    anomaly_type="interval",
                    description=f"记忆创建间隔{direction}（{interval:.1f}小时，Z={z:.2f}）",
                    severity=AnomalySeverity.MEDIUM,
                    evidence=[
                        sorted_drawers[i].id,
                        sorted_drawers[i + 1].id,
                    ],
                    expected_value=round(sum(intervals) / len(intervals), 1),
                    actual_value=round(interval, 1),
                    deviation=round(z, 2),
                ))

        return alerts

    # ── 知识缺口识别 ──────────────────────────────────────────

    def identify_knowledge_gaps(
        self,
        drawers: list[Drawer],
        causal_chains: list[CausalLink] | None = None,
    ) -> list[KnowledgeGap]:
        """识别知识缺口

        检测维度：
        1. 主题孤立：某主题与其他主题缺乏连接
        2. 因果断裂：因果链中缺少中间环节
        3. 信息不足：某主题的记忆太少
        4. 矛盾未解：存在冲突但未解决

        Args:
            drawers: 记忆列表
            causal_chains: 已发现的因果链（可选）

        Returns:
            知识缺口列表，按优先级降序
        """
        gaps: list[KnowledgeGap] = []

        # 主题孤立检测
        gaps.extend(self._detect_orphan_topics(drawers))

        # 因果断裂检测
        if causal_chains:
            gaps.extend(self._detect_causal_gaps(causal_chains))

        # 信息不足检测
        gaps.extend(self._detect_thin_topics(drawers))

        gaps.sort(key=lambda g: g.priority, reverse=True)
        return gaps

    def _detect_orphan_topics(self, drawers: list[Drawer]) -> list[KnowledgeGap]:
        """检测孤立主题"""
        gaps: list[KnowledgeGap] = []

        # 构建标签共现图
        tag_connections: dict[str, set[str]] = defaultdict(set)
        tag_counts: Counter = Counter()

        for d in drawers:
            tags = d.tags or []
            for tag in tags:
                tag_counts[tag] += 1
            for t1, t2 in combinations(tags, 2):
                tag_connections[t1].add(t2)
                tag_connections[t2].add(t1)

        # 找出连接数少的主题
        for tag, count in tag_counts.items():
            connections = tag_connections.get(tag, set())
            if count >= 3 and len(connections) <= 1:
                gaps.append(KnowledgeGap(
                    id=f"gap_orphan_{tag}",
                    topic=tag,
                    description=f"主题 '{tag}' 有 {count} 条记忆但仅与 {len(connections)} 个其他主题关联，知识较孤立",
                    related_knowledge=list(connections),
                    missing_links=["更多跨主题连接"],
                    priority=0.6,
                    suggested_actions=[
                        f"探索 '{tag}' 与其他主题的关系",
                        f"补充 '{tag}' 的应用场景或案例",
                    ],
                ))

        return gaps

    def _detect_causal_gaps(
        self, causal_chains: list[CausalLink]
    ) -> list[KnowledgeGap]:
        """检测因果断裂"""
        gaps: list[KnowledgeGap] = []

        # 构建因果图
        graph: dict[str, list[str]] = defaultdict(list)
        for link in causal_chains:
            graph[link.cause].append(link.effect)

        # 检测长链中的薄弱环节
        visited: set[str] = set()

        for start in graph:
            if start in visited:
                continue

            # BFS 找最长链
            chain: list[str] = [start]
            queue = [start]
            while queue:
                current = queue.pop(0)
                for next_node in graph.get(current, []):
                    if next_node not in chain:
                        chain.append(next_node)
                        queue.append(next_node)

            if len(chain) >= 3:
                for i in range(len(chain) - 2):
                    # 检查是否有直接连接
                    if chain[i + 2] not in graph.get(chain[i], []):
                        gaps.append(KnowledgeGap(
                            id=f"gap_causal_{chain[i]}_{chain[i+2]}",
                            topic=f"{chain[i]} → {chain[i+2]}",
                            description=(
                                f"因果链 {chain[i]} → ... → {chain[i+2]} "
                                f"中间可能缺少直接关联"
                            ),
                            related_knowledge=[chain[i], chain[i + 1], chain[i + 2]],
                            missing_links=[f"{chain[i]} 与 {chain[i+2]} 的直接因果关系"],
                            priority=0.7,
                            suggested_actions=[
                                f"验证 '{chain[i]}' 是否直接导致 '{chain[i+2]}'",
                                f"探索 '{chain[i+1]}' 在其中的中介作用",
                            ],
                        ))

            visited.update(chain)

        return gaps

    def _detect_thin_topics(self, drawers: list[Drawer]) -> list[KnowledgeGap]:
        """检测信息薄弱的主题"""
        gaps: list[KnowledgeGap] = []
        tag_counts: Counter = Counter()

        for d in drawers:
            for tag in (d.tags or []):
                tag_counts[tag] += 1

        # 找出出现次数恰好为 1 的主题
        for tag, count in tag_counts.items():
            if count == 1:
                gaps.append(KnowledgeGap(
                    id=f"gap_thin_{tag}",
                    topic=tag,
                    description=f"主题 '{tag}' 仅有 1 条记忆，信息严重不足",
                    related_knowledge=[],
                    missing_links=["更多相关记忆"],
                    priority=0.4,
                    suggested_actions=[
                        f"补充 '{tag}' 相关的记忆",
                        f"记录 '{tag}' 的使用经验和教训",
                    ],
                ))

        return gaps
