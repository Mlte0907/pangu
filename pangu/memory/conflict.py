"""盘古冲突检测引擎 — 发现矛盾记忆
==========================================
自动检测记忆中相互矛盾的信息，帮助维护记忆一致性。

支持：
- 基于嵌入向量的语义冲突检测
- 基于关键词的事实冲突检测
- 冲突严重度评分
- 冲突解决建议
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


class ConflictSeverity(str, Enum):
    """冲突严重度"""
    CRITICAL = "critical"    # 严重矛盾（如事实完全相反）
    MAJOR = "major"          # 重要矛盾
    MINOR = "minor"          # 轻微不一致
    POTENTIAL = "potential"  # 潜在冲突


@dataclass
class MemoryConflict:
    """记忆冲突"""
    id: str
    memory_a: str  # 记忆 A ID
    memory_b: str  # 记忆 B ID
    content_a: str  # 记忆 A 摘要
    content_b: str  # 记忆 B 摘要
    description: str  # 冲突描述
    severity: ConflictSeverity
    confidence: float  # 冲突置信度 [0,1]
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())


class ConflictDetector:
    """冲突检测引擎"""

    # 矛盾词对（A 与 B 语义相反）
    CONTRADICTION_PATTERNS = [
        # 中文矛盾词
        (["是", "正确", "对的", "✓"], ["不是", "错误", "不对", "✗", "否"]),
        (["成功", "通过", "完成"], ["失败", "未通过", "中断"]),
        (["支持", "启用", "开启"], ["不支持", "禁用", "关闭"]),
        (["增加", "上升", "提升"], ["减少", "下降", "降低"]),
        (["推荐", "建议", "应该"], ["不推荐", "避免", "不应该"]),
        (["存在", "有"], ["不存在", "没有", "无"]),
        (["简单", "容易", "方便"], ["复杂", "困难", "麻烦"]),
        (["快", "迅速", "高效"], ["慢", "缓慢", "低效"]),
        (["安全", "可靠"], ["不安全", "危险", "不可靠"]),
        # 英文矛盾词
        (["yes", "true", "correct"], ["no", "false", "incorrect"]),
        (["success", "pass", "work"], ["fail", "error", "broken"]),
        (["support", "enable"], ["not support", "disable"]),
        (["increase", "up"], ["decrease", "down"]),
        (["good", "great", "excellent"], ["bad", "poor", "terrible"]),
        (["fast", "quick"], ["slow"]),
        (["safe", "secure"], ["unsafe", "dangerous", "insecure"]),
    ]

    # 事实类关键词
    FACT_KEYWORDS = [
        "版本", "version", "数量", "number", "日期", "date",
        "大小", "size", "状态", "status", "结果", "result",
        "决定", "decision", "结论", "conclusion", "配置", "config",
    ]

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._embedder = None

    @property
    def embedder(self):
        if self._embedder is None:
            try:
                from pangu.memory.embedding import EmbeddingService
                self._embedder = EmbeddingService(self.config)
            except ImportError:
                self._embedder = None
        return self._embedder

    @staticmethod
    def _cosine_sim(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def detect_conflicts(self, drawers: list[Drawer],
                         min_similarity: float = 0.5,
                         min_confidence: float = 0.3) -> list[MemoryConflict]:
        """检测记忆列表中的冲突

        Args:
            drawers: 记忆列表
            min_similarity: 语义相似度阈值（高于此值才可能冲突）
            min_confidence: 最小冲突置信度

        Returns:
            冲突列表
        """
        if len(drawers) < 2:
            return []

        conflicts = []

        # 尝试向量方法
        if self.embedder:
            try:
                conflicts = self._vector_conflict_detect(
                    drawers, min_similarity, min_confidence)
            except Exception:
                conflicts = []

        # 关键词方法（补充检测）
        keyword_conflicts = self._keyword_conflict_detect(
            drawers, min_confidence)
        existing_pairs = {(c.memory_a, c.memory_b) for c in conflicts}
        existing_pairs.update((c.memory_b, c.memory_a) for c in conflicts)
        for c in keyword_conflicts:
            if (c.memory_a, c.memory_b) not in existing_pairs:
                conflicts.append(c)

        conflicts.sort(key=lambda c: c.confidence, reverse=True)
        return conflicts

    def _vector_conflict_detect(self, drawers: list[Drawer],
                                min_similarity: float,
                                min_confidence: float) -> list[MemoryConflict]:
        """基于向量的冲突检测"""
        has_fact = [self._contains_fact_keywords(d.content) for d in drawers]

        # 只对包含事实关键词的记忆进行检测
        candidates = [(i, d) for i, d in enumerate(drawers) if has_fact[i]]
        if len(candidates) < 2:
            return []

        texts = [d.content for _, d in candidates]
        embeddings = self.embedder.embed_batch(texts)

        conflicts = []
        for a in range(len(candidates)):
            for b in range(a + 1, len(candidates)):
                conflict = self._check_vector_conflict_pair(
                    candidates, a, b, embeddings, min_similarity, min_confidence)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _check_vector_conflict_pair(self, candidates: list, a: int, b: int,
                                    embeddings: list, min_similarity: float,
                                    min_confidence: float) -> MemoryConflict | None:
        sim = self._cosine_sim(embeddings[a], embeddings[b])
        if sim < min_similarity:
            return None
        conf = self._contradiction_score(
            candidates[a][1].content, candidates[b][1].content, sim)
        if conf["confidence"] >= min_confidence:
            return MemoryConflict(
                id=f"conflict_{hex_digest(candidates[a][1].id + candidates[b][1].id)[:12]}",
                memory_a=candidates[a][1].id,
                memory_b=candidates[b][1].id,
                content_a=candidates[a][1].content[:200],
                content_b=candidates[b][1].content[:200],
                description=conf["description"],
                severity=conf["severity"],
                confidence=round(conf["confidence"], 4),
            )
        return None

    def _keyword_conflict_detect(self, drawers: list[Drawer],
                                 min_confidence: float) -> list[MemoryConflict]:
        """基于关键词的冲突检测"""
        conflicts = []

        for i in range(len(drawers)):
            for j in range(i + 1, len(drawers)):
                a = drawers[i]
                b = drawers[j]

                # 快速跳过无关记忆
                if not self._share_topic(a.content, b.content):
                    continue

                conf = self._contradiction_score(a.content, b.content)
                if conf["confidence"] >= min_confidence:
                    conflicts.append(MemoryConflict(
                        id=f"conflict_{hex_digest(a.id + b.id)[:12]}",
                        memory_a=a.id,
                        memory_b=b.id,
                        content_a=a.content[:200],
                        content_b=b.content[:200],
                        description=conf["description"],
                        severity=conf["severity"],
                        confidence=round(conf["confidence"], 4),
                    ))

        return conflicts

    def _contradiction_score(self, text_a: str, text_b: str,
                             semantic_sim: float = 0.0) -> dict:
        """计算两个文本的矛盾程度"""
        text_a_lower = text_a.lower()
        text_b_lower = text_b.lower()

        contradictions_found = []
        max_severity = ConflictSeverity.POTENTIAL

        for positive_words, negative_words in self.CONTRADICTION_PATTERNS:
            a_pos = any(w in text_a_lower for w in positive_words)
            a_neg = any(w in text_a_lower for w in negative_words)
            b_pos = any(w in text_b_lower for w in positive_words)
            b_neg = any(w in text_b_lower for w in negative_words)

            # A 说正面，B 说反面
            if a_pos and b_neg:
                contradictions_found.append(("positive_vs_negative", 0.8))
                if max_severity in (ConflictSeverity.POTENTIAL, ConflictSeverity.MINOR):
                    max_severity = ConflictSeverity.MAJOR
            # A 说反面，B 说正面
            elif a_neg and b_pos:
                contradictions_found.append(("negative_vs_positive", 0.8))
                if max_severity in (ConflictSeverity.POTENTIAL, ConflictSeverity.MINOR):
                    max_severity = ConflictSeverity.MAJOR

        # 综合置信度
        if not contradictions_found:
            # 仅靠语义相似度判断潜在冲突
            if semantic_sim > 0.7:
                return {
                    "confidence": round(semantic_sim * 0.3, 4),
                    "severity": ConflictSeverity.POTENTIAL,
                    "description": "两条记忆语义高度相似，但可能存在不一致",
                }
            return {"confidence": 0.0, "severity": ConflictSeverity.POTENTIAL,
                    "description": ""}

        # 加权计算
        avg_contra_score = sum(s for _, s in contradictions_found) / len(contradictions_found)
        base_conf = avg_contra_score

        if semantic_sim > 0.5:
            base_conf *= 1.5  # 相似但矛盾 => 更可能是真正冲突

        confidence = min(1.0, base_conf)

        if confidence > 0.8:
            severity = ConflictSeverity.CRITICAL
        elif confidence > 0.6:
            severity = ConflictSeverity.MAJOR
        elif confidence > 0.3:
            severity = ConflictSeverity.MINOR
        else:
            severity = max_severity

        return {
            "confidence": round(confidence, 4),
            "severity": severity,
            "description": f"发现 {len(contradictions_found)} 处矛盾表述",
        }

    def _contains_fact_keywords(self, text: str) -> bool:
        """检查文本是否包含事实类关键词"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.FACT_KEYWORDS)

    def _share_topic(self, text_a: str, text_b: str) -> bool:
        """检查两个文本是否共享话题"""
        # 提取名词
        import re
        words_a = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                  text_a.lower()))
        words_b = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                  text_b.lower()))
        if not words_a or not words_b:
            return False

        overlap = words_a & words_b
        return len(overlap) >= 2

    def check_pair(self, drawer_a: Drawer, drawer_b: Drawer) -> dict:
        """检查两条记忆是否存在冲突"""
        sim = 0.0
        if self.embedder:
            try:
                emb_a = self.embedder.embed(drawer_a.content)
                emb_b = self.embedder.embed(drawer_b.content)
                sim = self._cosine_sim(emb_a, emb_b)
            except Exception:
                pass

        return self._contradiction_score(drawer_a.content, drawer_b.content, sim)

    def resolve_suggestion(self, conflict: MemoryConflict) -> str:
        """生成冲突解决建议"""
        if conflict.severity == ConflictSeverity.CRITICAL:
            return "严重冲突：建议人工审查两条记忆，删除或修正其中一条。"
        elif conflict.severity == ConflictSeverity.MAJOR:
            return "重要冲突：请核实两条记忆的正确性，更新较旧的一条。"
        elif conflict.severity == ConflictSeverity.MINOR:
            return "轻微不一致：可能是表述差异，建议统一用词。"
        else:
            return "潜在冲突：两条记忆语义相似，建议确认是否存在矛盾。"
