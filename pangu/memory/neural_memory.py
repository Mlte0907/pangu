"""盘古类人记忆神经网络 — 海马体-新皮层双系统
===============================================
模拟人类大脑记忆处理的神经网络机制：
1. 海马体短期记忆 → 新皮层长期记忆的转化
2. 睡眠记忆巩固（离线批处理）
3. 情感标记记忆（情感值影响记忆强度）
4. 个性化遗忘曲线（不同记忆类型不同衰减率）
5. 记忆激活扩散（相关记忆联动增强）
6. 记忆竞争抑制（相似记忆互相抑制）

神经科学基础：
- 海马体负责快速编码短期记忆（容量有限、易丢失）
- 新皮层存储经过巩固的长期记忆（容量大、稳定）
- 睡眠期间海马体向新皮层重播记忆片段
- 情感杏仁核调制记忆强度（强烈情感 → 更深编码）
- 语义网络中的激活扩散（相关概念联动激活）
"""
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ..core.config import PanguConfig
from ..core.palace import Drawer


# ── 记忆类型枚举 ──

class MemoryType(Enum):
    """记忆分类 — 决定遗忘曲线和巩固策略"""
    EPISODIC = "episodic"           # 情景记忆：具体事件、经历
    SEMANTIC = "semantic"           # 语义记忆：事实、知识
    PROCEDURAL = "procedural"       # 程序记忆：操作方法、技能
    EMOTIONAL = "emotional"         # 情感记忆：情绪体验


class MemoryState(Enum):
    """记忆状态 — 海马体/新皮层生命周期"""
    ENCODED = "encoded"             # 新编码，尚未巩固
    CONSOLIDATING = "consolidating" # 巩固中（重播/强化）
    CONSOLIDATED = "consolidated"   # 已巩固至长期存储
    DECAYING = "decaying"           # 正在衰减
    FORGOTTEN = "forgotten"         # 已遗忘


# ── 记忆单元 ──

@dataclass
class NeuralMemory:
    """记忆神经元 — 记忆在网络中的基本单元"""
    id: str
    content: str
    memory_type: MemoryType = MemoryType.EPISODIC
    state: MemoryState = MemoryState.ENCODED
    strength: float = 1.0                    # 记忆强度 0-1
    emotional_valence: float = 0.0           # 情感效价 -1(负面) ~ +1(正面)
    arousal: float = 0.0                     # 情感唤醒度 0(平静) ~ 1(激动)
    consolidation_count: int = 0             # 巩固次数
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    source_drawer_id: str = ""               # 关联的 Drawer ID
    related_ids: list[str] = field(default_factory=list)  # 语义关联的记忆 ID
    tags: list[str] = field(default_factory=list)

    def emotional_weight(self) -> float:
        """计算情感权重：唤醒度越高，情感对记忆强度的影响越大"""
        return abs(self.emotional_valence) * self.arousal


# ── 个性化遗忘曲线 ──

class PersonalizedDecay:
    """个性化遗忘曲线 — 不同记忆类型使用不同的衰减参数"""

    # 默认衰减率：不同类型记忆的半衰期差异
    DEFAULT_DECAY_RATES: dict[MemoryType, float] = {
        MemoryType.EPISODIC: 0.6,      # 情景记忆衰减较快
        MemoryType.SEMANTIC: 0.15,     # 语义记忆衰减很慢（知识长期保持）
        MemoryType.PROCEDURAL: 0.08,   # 程序记忆几乎不衰减（肌肉记忆）
        MemoryType.EMOTIONAL: 0.3,     # 情感记忆中等衰减（情绪淡化）
    }

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        # 可覆盖每种类型的衰减率
        self.decay_rates: dict[MemoryType, float] = dict(self.DEFAULT_DECAY_RATES)

    def retention(self, memory: NeuralMemory, current_time: float = None) -> float:
        """计算个性化保留率

        不同记忆类型有不同的衰减曲线：
        - 语义记忆：R = e^(-0.15 * t / 24)  半衰期约 4.6 天
        - 情景记忆：R = e^(-0.60 * t / 24)  半衰期约 1.2 天
        - 程序记忆：R = e^(-0.08 * t / 24)  半衰期约 8.7 天
        - 情感记忆：R = e^(-0.30 * t / 24)  半衰期约 2.3 天

        附加修正：
        - 高情感唤醒度 → 衰减速率降低（更难忘记）
        - 多次巩固 → 衰减速率降低（更稳定）
        - 频繁访问 → 衰减速率降低（间隔重复效应）
        """
        if current_time is None:
            current_time = time.time()

        elapsed_hours = (current_time - memory.created_at) / 3600.0
        if elapsed_hours <= 0:
            return 1.0

        base_rate = self.decay_rates.get(memory.memory_type, 0.5)

        # 情感修正：高唤醒度记忆更难遗忘
        emotional_correction = 1.0 - memory.emotional_weight() * 0.4

        # 巩固修正：每次巩固降低衰减率 8%（最多降低 60%）
        consolidation_correction = max(0.4, 1.0 - memory.consolidation_count * 0.08)

        # 访问修正：频繁访问的记忆衰减更慢
        access_correction = 1.0 / (1.0 + math.log1p(memory.access_count) * 0.1)

        effective_rate = base_rate * emotional_correction * consolidation_correction * access_correction
        return math.exp(-effective_rate * elapsed_hours / 24.0)

    def should_forget(self, memory: NeuralMemory) -> bool:
        """判断记忆是否应被遗忘"""
        retention = self.retention(memory)
        return retention < self.config.min_importance_threshold


# ── 海马体短期记忆缓冲 ──

class Hippocampus:
    """海马体 — 短期记忆编码器

    职责：
    1. 接收新输入，快速编码为短期记忆
    2. 维护有限容量的工作缓冲（容量瓶颈）
    3. 在巩固周期向新皮层传输重要记忆
    """
    CAPACITY: int = 40    # 海马体容量上限

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._buffer: list[NeuralMemory] = []
        self._encoding_queue: list[NeuralMemory] = []

    @property
    def capacity(self) -> int:
        return self.config.wm_capacity or self.CAPACITY

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def load_factor(self) -> float:
        """海马体负载率"""
        return len(self._buffer) / self.capacity

    def encode(self, drawer: Drawer) -> NeuralMemory:
        """编码新记忆进入海马体

        将 Drawer 转化为 NeuralMemory，赋予初始情感标记。
        如果海马体已满，触发竞争抑制淘汰最弱记忆。
        """
        # 根据 Drawer 内容推断记忆类型
        memory_type = self._infer_type(drawer)

        # 从 Drawer 提取情感信号
        emotional_valence = drawer.emotional_weight
        arousal = min(abs(emotional_valence), 1.0)

        # 解析 Drawer 的创建时间
        try:
            created_ts = datetime.fromisoformat(drawer.created_at).timestamp()
        except (ValueError, TypeError, AttributeError):
            created_ts = time.time()

        memory = NeuralMemory(
            id=drawer.id,
            content=drawer.content,
            memory_type=memory_type,
            state=MemoryState.ENCODED,
            strength=drawer.importance / 5.0,  # 归一化到 0-1
            emotional_valence=emotional_valence,
            arousal=arousal,
            source_drawer_id=drawer.id,
            tags=list(drawer.tags),
            created_at=created_ts,
        )

        # 容量检查：超出时触发竞争抑制
        if len(self._buffer) >= self.capacity:
            self._competitive_inhibition(memory)

        self._buffer.append(memory)
        return memory

    def _infer_type(self, drawer: Drawer) -> MemoryType:
        """从 Drawer 元数据推断记忆类型"""
        hall = drawer.hall.lower()
        if "fact" in hall or "decision" in hall:
            return MemoryType.SEMANTIC
        elif "discovery" in hall or "concept" in hall:
            return MemoryType.SEMANTIC
        elif "event" in hall or "milestone" in hall:
            return MemoryType.EPISODIC
        elif "preference" in hall or "advice" in hall:
            return MemoryType.PROCEDURAL
        elif "relation" in hall:
            return MemoryType.EMOTIONAL
        # 有显著情感标记的记忆归类为情感记忆
        if abs(drawer.emotional_weight) > 0.5:
            return MemoryType.EMOTIONAL
        return MemoryType.EPISODIC

    def _competitive_inhibition(self, new_memory: NeuralMemory) -> Optional[NeuralMemory]:
        """记忆竞争抑制：新记忆进入时与现有记忆竞争

        最终会淘汰最弱的记忆，让出位置给新记忆。
        返回被淘汰的记忆（需要转移或丢弃）。
        """
        if not self._buffer:
            return None

        # 计算每个记忆的竞争力分数
        candidates = []
        for mem in self._buffer:
            score = self._competition_score(mem)
            candidates.append((score, mem))

        # 加入新记忆的竞争
        new_score = self._competition_score(new_memory)
        candidates.append((new_score, new_memory))

        # 按竞争力排序，最弱的被淘汰
        candidates.sort(key=lambda x: x[0])
        weakest_score, weakest = candidates[0]

        # 如果新记忆不如最弱的旧记忆，新记忆不进入
        if weakest.id == new_memory.id:
            return None

        # 淘汰最弱的记忆
        self._buffer = [m for m in self._buffer if m.id != weakest.id]
        weakest.state = MemoryState.DECAYING
        return weakest

    def _competition_score(self, memory: NeuralMemory) -> float:
        """计算记忆的竞争竞争力

        综合考虑：强度 × 情感权重 × 巩固次数 × 访问频率
        """
        emotional_bonus = 1.0 + memory.emotional_weight() * 0.5
        consolidation_bonus = 1.0 + math.log1p(memory.consolidation_count) * 0.2
        recency_bonus = 1.0 / (1.0 + (time.time() - memory.last_access) / 3600.0)
        return memory.strength * emotional_bonus * consolidation_bonus * recency_bonus

    def get_candidates_for_consolidation(self) -> list[NeuralMemory]:
        """获取可送往新皮层巩固的记忆候选

        选择标准：
        - 强度足够高（>0.3）
        - 满足以下任一条件：
          - 高情感唤醒度（>0.4）
          - 已巩固过（consolidation_count > 0）
          - 高访问量（>3）
          - 在海马体停留超过 1 小时（自动晋升）
        """
        now = time.time()
        candidates = []
        for mem in self._buffer:
            if mem.strength < 0.3:
                continue
            age_hours = (now - mem.created_at) / 3600.0
            if (mem.arousal > 0.4
                    or mem.consolidation_count > 0
                    or mem.access_count > 3
                    or age_hours > 1.0):
                candidates.append(mem)
        return candidates

    def flush(self, candidates: list[NeuralMemory]) -> list[NeuralMemory]:
        """清空海马体缓冲，返回被巩固的记忆列表"""
        consolidated = [m for m in self._buffer if m.id in {c.id for c in candidates}]
        remaining = [m for m in self._buffer if m.id not in {c.id for c in candidates}]
        self._buffer = remaining
        return consolidated


# ── 新皮层长期记忆存储 ──

class Neocortex:
    """新皮层 — 长期记忆存储器

    职责：
    1. 存储经过海马体巩固的记忆
    2. 维护记忆间的语义关联网络
    3. 执行激活扩散和竞争抑制
    4. 周期性衰减和遗忘
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._memories: dict[str, NeuralMemory] = {}
        # 语义关联矩阵：记忆 ID 对 → 关联强度
        self._association_graph: dict[str, dict[str, float]] = {}
        self.decay = PersonalizedDecay(config)

    def store(self, memory: NeuralMemory) -> None:
        """存储记忆到新皮层"""
        memory.state = MemoryState.CONSOLIDATED
        self._memories[memory.id] = memory
        # 初始化关联节点
        if memory.id not in self._association_graph:
            self._association_graph[memory.id] = {}

    def get(self, memory_id: str) -> Optional[NeuralMemory]:
        """获取指定记忆"""
        return self._memories.get(memory_id)

    def all_memories(self) -> list[NeuralMemory]:
        """获取所有记忆"""
        return list(self._memories.values())

    def count(self) -> int:
        return len(self._memories)

    # ── 激活扩散 ──

    def build_association(self, id_a: str, id_b: str, strength: float = 0.5) -> None:
        """建立两个记忆之间的语义关联

        关联强度 0-1，越接近 1 表示语义越相关。
        """
        if id_a not in self._association_graph:
            self._association_graph[id_a] = {}
        if id_b not in self._association_graph:
            self._association_graph[id_b] = {}
        self._association_graph[id_a][id_b] = strength
        self._association_graph[id_b][id_a] = strength

    def activate_spreading(self, seed_ids: list[str], decay_factor: float = 0.6,
                           max_depth: int = 3) -> list[tuple[str, float]]:
        """激活扩散 — 模拟神经网络中的信号传播

        从种子记忆出发，沿关联网络扩散激活信号。
        每经过一跳，激活强度衰减 decay_factor 倍。

        Args:
            seed_ids: 初始激活的记忆 ID 列表
            decay_factor: 每跳衰减系数（0-1，越小衰减越快）
            max_depth: 最大传播深度

        Returns:
            按激活强度排序的 (memory_id, activation) 列表
        """
        activations: dict[str, float] = {}
        visited: set[str] = set()
        # BFS 队列：(memory_id, activation, depth)
        queue: list[tuple[str, float, int]] = []

        for mid in seed_ids:
            if mid in self._memories:
                activations[mid] = 1.0
                queue.append((mid, 1.0, 0))

        while queue:
            current, current_activation, depth = queue.pop(0)
            if current in visited or depth >= max_depth:
                continue
            visited.add(current)

            neighbors = self._association_graph.get(current, {})
            for neighbor_id, edge_strength in neighbors.items():
                # 扩散激活 = 当前激活 × 边权重 × 衰减系数
                spread_activation = current_activation * edge_strength * decay_factor
                if neighbor_id not in activations or activations[neighbor_id] < spread_activation:
                    activations[neighbor_id] = spread_activation
                    queue.append((neighbor_id, spread_activation, depth + 1))

        # 按激活强度降序排序
        result = sorted(activations.items(), key=lambda x: x[1], reverse=True)
        return result

    def mutual_inhibition(self, memory_ids: list[str]) -> dict[str, float]:
        """记忆竞争抑制 — 相似记忆互相抑制

        相似度越高的记忆，互相抑制越强。
        返回每个记忆的抑制后有效激活值。

        机制：Winner-Take-All with soft competition
        - 最强记忆不受抑制
        - 其他记忆被按相似度加权抑制
        """
        if not memory_ids:
            return {}

        memories = [self._memories[mid] for mid in memory_ids if mid in self._memories]
        if not memories:
            return {}

        # 计算初始激活值（基于记忆强度）
        activations: dict[str, float] = {m.id: m.strength for m in memories}

        # 迭代抑制（3轮收敛）
        for _ in range(3):
            new_activations = dict(activations)
            for i, mem_a in enumerate(memories):
                inhibition_total = 0.0
                for j, mem_b in enumerate(memories):
                    if i == j:
                        continue
                    # 相似度：类型相同 +0.3，内容重叠 +0.4，标签重叠 +0.3
                    similarity = self._similarity(mem_a, mem_b)
                    inhibitor_activation = activations.get(mem_b.id, 0.0)
                    inhibition_total += similarity * inhibitor_activation * 0.3
                # 抑制后的新激活
                new_activations[mem_a.id] = max(
                    0.01,
                    activations[mem_a.id] - inhibition_total
                )

            # 归一化：防止整体激活值漂移
            total = sum(new_activations.values())
            if total > 0:
                for mid in new_activations:
                    new_activations[mid] /= total
                    new_activations[mid] *= len(memories)  # 保持平均值为 1

            activations = new_activations

        return activations

    def _similarity(self, a: NeuralMemory, b: NeuralMemory) -> float:
        """计算两个记忆的相似度（0-1）"""
        score = 0.0

        # 类型相同
        if a.memory_type == b.memory_type:
            score += 0.3

        # 标签重叠
        common_tags = set(a.tags) & set(b.tags)
        all_tags = set(a.tags) | set(b.tags)
        if all_tags:
            score += 0.4 * (len(common_tags) / len(all_tags))

        # 情感相似（效价方向一致）
        if a.emotional_valence * b.emotional_valence > 0:
            score += 0.3 * (1.0 - abs(a.emotional_valence - b.emotional_valence) / 2.0)

        return min(score, 1.0)

    # ── 衰减与遗忘 ──

    def apply_decay(self) -> list[NeuralMemory]:
        """应用个性化衰减，返回被遗忘的记忆列表"""
        forgotten = []
        current_time = time.time()

        for memory in list(self._memories.values()):
            retention = self.decay.retention(memory, current_time)
            memory.strength = retention

            if retention < self.config.min_importance_threshold:
                memory.state = MemoryState.FORGOTTEN
                forgotten.append(memory)
                del self._memories[memory.id]
                self._association_graph.pop(memory.id, None)
                # 清理指向该记忆的关联
                for node in self._association_graph.values():
                    node.pop(memory.id, None)

        return forgotten

    def stats(self) -> dict:
        """新皮层统计信息"""
        by_type: dict[str, int] = {}
        by_state: dict[str, int] = {}
        strengths: list[float] = []

        for mem in self._memories.values():
            by_type[mem.memory_type.value] = by_type.get(mem.memory_type.value, 0) + 1
            by_state[mem.state.value] = by_state.get(mem.state.value, 0) + 1
            strengths.append(mem.strength)

        avg_strength = sum(strengths) / max(len(strengths), 1)
        total_edges = sum(len(v) for v in self._association_graph.values()) // 2

        return {
            "total_memories": len(self._memories),
            "by_type": by_type,
            "by_state": by_state,
            "average_strength": round(avg_strength, 3),
            "association_edges": total_edges,
        }


# ── 睡眠巩固引擎 ──

class SleepConsolidation:
    """睡眠巩固 — 模拟睡眠期间的记忆重播与整合

    神经科学基础：
    - 慢波睡眠（SWS）：海马体向新皮层重播情景记忆
    - REM 睡眠：情感记忆去标记化，语义记忆提取规律
    - 睡眠纺锤波：选择性巩固重要记忆，抑制噪声
    """

    def __init__(self, config: PanguConfig = None,
                 hippocampus: Hippocampus = None, neocortex: Neocortex = None):
        self.config = config or PanguConfig.load()
        self.hippocampus = hippocampus or Hippocampus(config)
        self.neocortex = neocortex or Neocortex(config)
        self._last_sleep: float = 0.0
        self._sleep_count: int = 0

    def enter_sleep(self) -> dict:
        """进入睡眠巩固周期 — 离线批处理

        处理流程：
        1. 海马体筛选巩固候选
        2. 情感记忆去标记化（降低情感唤醒度）
        3. 语义记忆提取规律（建立关联）
        4. 竞争抑制淘汰冗余记忆
        5. 激活扩散建立新关联
        6. 清空海马体，已巩固记忆转入新皮层

        Returns:
            本次睡眠的统计报告
        """
        self._last_sleep = time.time()
        self._sleep_count += 1

        stats = {
            "sleep_cycle": self._sleep_count,
            "timestamp": datetime.now().isoformat(),
            "candidates": 0,
            "consolidated": 0,
            "forgotten": 0,
            "associations_built": 0,
        }

        # 1. 获取海马体巩固候选
        candidates = self.hippocampus.get_candidates_for_consolidation()
        stats["candidates"] = len(candidates)

        if not candidates:
            return stats

        # 2. 情感记忆去标记化
        for mem in candidates:
            if mem.memory_type == MemoryType.EMOTIONAL:
                mem.arousal *= 0.7  # 降低唤醒度 30%
                mem.emotional_valence *= 0.8  # 降低情感强度 20%

        # 3. 语义记忆提取规律：建立关联
        semantic = [m for m in candidates if m.memory_type == MemoryType.SEMANTIC]
        associations = 0
        for i, mem_a in enumerate(semantic):
            for mem_b in semantic[i+1:]:
                sim = self.neocortex._similarity(mem_a, mem_b)
                if sim > 0.3:
                    self.neocortex.build_association(mem_a.id, mem_b.id, sim)
                    associations += 1
                    # 双向链接
                    mem_a.related_ids.append(mem_b.id)
                    mem_b.related_ids.append(mem_a.id)

        stats["associations_built"] = associations

        # 4. 竞争抑制：淘汰冗余
        if len(candidates) > 10:
            ids = [m.id for m in candidates]
            inhibitions = self.neocortex.mutual_inhibition(ids)
            # 移除被抑制到很低激活的记忆
            suppressed = [
                mid for mid, activation in inhibitions.items()
                if activation < 0.1
            ]
            candidates = [m for m in candidates if m.id not in suppressed]
            stats["forgotten"] += len(suppressed)

        # 5. 转移至新皮层（重置时间戳，避免立即衰减）
        for mem in candidates:
            mem.consolidation_count += 1
            mem.state = MemoryState.CONSOLIDATED
            mem.created_at = time.time()  # 巩固时重置为当前时间
            self.neocortex.store(mem)

        stats["consolidated"] = len(candidates)

        # 6. 清空海马体已巩固部分
        self.hippocampus.flush(candidates)

        # 7. 应用新皮层衰减
        forgotten = self.neocortex.apply_decay()
        stats["forgotten"] += len(forgotten)

        return stats

    def needs_sleep(self) -> bool:
        """检查是否需要进入睡眠巩固"""
        if not self.config.consolidation_enabled:
            return False

        # 海马体负载率超过 60% 时需要巩固
        if self.hippocampus.load_factor > 0.6:
            return True

        # 距离上次巩固超过配置间隔
        now = time.time()
        interval = self.config.consolidation_interval_hours * 3600
        return (now - self._last_sleep) > interval


# ── 情感调制器 ──

class EmotionalModulator:
    """情感调制 — 杏仁核对记忆编码的调制作用

    神经科学基础：
    - 高唤醒度事件触发杏仁核激活
    - 杏仁核增强海马体编码强度
    - 情感记忆更容易被长期保持
    - 时间推移导致情感去标记化
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def modulate_encoding(self, memory: NeuralMemory) -> NeuralMemory:
        """调制记忆编码：根据情感状态增强/减弱编码强度

        高情感唤醒度 → 增强记忆强度（类似肾上腺素效应）
        """
        emotional_boost = 1.0 + memory.emotional_weight() * 0.5
        memory.strength = min(1.0, memory.strength * emotional_boost)
        return memory

    def modulate_retrieval(self, memory: NeuralMemory, current_time: float = None) -> float:
        """调制记忆检索：情感记忆更容易被回忆

        情感记忆在回忆时有天然优势（情绪触发回忆）
        """
        if current_time is None:
            current_time = time.time()

        base_strength = memory.strength
        emotional_bonus = 1.0 + memory.emotional_weight() * 0.3
        return min(1.0, base_strength * emotional_bonus)

    def devaluation(self, memory: NeuralMemory, decay_cycles: int = 1) -> NeuralMemory:
        """情感去标记化：随时间降低情感标记强度

        模拟情感记忆的自然淡化过程。
        """
        for _ in range(decay_cycles):
            memory.arousal *= 0.9           # 唤醒度衰减 10%
            memory.emotional_valence *= 0.95  # 情感效价衰减 5%
        return memory


# ── 统一接口：NeuralMemoryEngine ──

class NeuralMemoryEngine:
    """类人记忆神经网络引擎 — 统一管理所有子系统

    整合海马体、新皮层、睡眠巩固、情感调制为统一接口。
    提供与现有盘古记忆系统的对接能力。
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.hippocampus = Hippocampus(config)
        self.neocortex = Neocortex(config)
        self.sleep_engine = SleepConsolidation(config, self.hippocampus, self.neocortex)
        self.emotional = EmotionalModulator(config)
        self.decay = PersonalizedDecay(config)

    # ── 编码入口 ──

    def encode(self, drawer: Drawer) -> NeuralMemory:
        """编码新记忆 — 从 Drawer 到 NeuralMemory

        流程：
        1. 海马体快速编码
        2. 情感调制增强
        3. 如果海马体满载，触发巩固
        """
        memory = self.hippocampus.encode(drawer)
        memory = self.emotional.modulate_encoding(memory)
        return memory

    # ── 检索入口 ──

    def retrieve(self, query_ids: list[str] = None, top_k: int = 5) -> list[tuple[NeuralMemory, float]]:
        """检索记忆 — 支持激活扩散

        Args:
            query_ids: 种子记忆 ID 列表（用于激活扩散）
            top_k: 返回前 K 条结果

        Returns:
            (memory, effective_strength) 列表
        """
        results: list[tuple[NeuralMemory, float]] = []

        if query_ids:
            # 激活扩散检索
            activations = self.neocortex.activate_spreading(query_ids)
            for mid, activation in activations[:top_k]:
                mem = self.neocortex.get(mid)
                if mem:
                    effective = self.emotional.modulate_retrieval(mem)
                    effective *= activation  # 结合扩散激活
                    results.append((mem, effective))
        else:
            # 全量检索：按强度排序
            for mem in self.neocortex.all_memories():
                effective = self.emotional.modulate_retrieval(mem)
                results.append((mem, effective))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ── 睡眠巩固 ──

    def sleep(self) -> dict:
        """触发一次睡眠巩固周期"""
        return self.sleep_engine.enter_sleep()

    def needs_sleep(self) -> bool:
        """检查是否需要睡眠巩固"""
        return self.sleep_engine.needs_sleep()

    # ── 衰减 ──

    def apply_global_decay(self) -> list[NeuralMemory]:
        """全局衰减 — 对所有记忆应用个性化遗忘曲线"""
        # 新皮层衰减
        forgotten = self.neocortex.apply_decay()

        # 海马体衰减：清除过期缓冲
        hippocampus_forgotten = []
        for mem in list(self.hippocampus._buffer):
            if self.decay.should_forget(mem):
                hippocampus_forgotten.append(mem)
                self.hippocampus._buffer = [
                    m for m in self.hippocampus._buffer if m.id != mem.id
                ]

        return forgotten + hippocampus_forgotten

    # ── 统计 ──

    def stats(self) -> dict:
        """神经网络整体统计"""
        return {
            "hippocampus": {
                "buffer_size": self.hippocampus.buffer_size,
                "capacity": self.hippocampus.capacity,
                "load_factor": round(self.hippocampus.load_factor, 2),
            },
            "neocortex": self.neocortex.stats(),
            "sleep": {
                "sleep_count": self.sleep_engine._sleep_count,
                "last_sleep": datetime.fromtimestamp(
                    self.sleep_engine._last_sleep
                ).isoformat() if self.sleep_engine._last_sleep else None,
            },
        }


_neural_engine: NeuralMemoryEngine | None = None


def get_neural_engine(config: PanguConfig = None) -> NeuralMemoryEngine:
    """获取全局 NeuralMemoryEngine 单例"""
    global _neural_engine
    if _neural_engine is None:
        cfg = config or PanguConfig.load()
        if not cfg.neural_enabled:
            raise RuntimeError("Neural memory is disabled (neural_enabled=false)")
        _neural_engine = NeuralMemoryEngine(cfg)
    return _neural_engine
