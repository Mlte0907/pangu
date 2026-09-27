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

    CRITICAL = "critical"  # 严重矛盾（如事实完全相反）
    MAJOR = "major"  # 重要矛盾
    MINOR = "minor"  # 轻微不一致
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
        "版本",
        "version",
        "数量",
        "number",
        "日期",
        "date",
        "大小",
        "size",
        "状态",
        "status",
        "结果",
        "result",
        "决定",
        "decision",
        "结论",
        "conclusion",
        "配置",
        "config",
    ]

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
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
        from .utils import cosine_similarity

        return cosine_similarity(a, b)

    def detect_conflicts(
        self, drawers: list[Drawer], min_similarity: float = 0.5, min_confidence: float = 0.3
    ) -> list[MemoryConflict]:
        """检测记忆列表中的冲突

        Args:
            drawers: 记忆列表
            min_similarity: 语义相似度阈值（高于此值才可能冲突）
            min_confidence: 最小冲突置信度

        Returns:
            冲突列表

        ⚠ 2026-09-27：**两路检测共用同一把相似度尺子**。此前关键词路
        （``_keyword_conflict_detect``）调 ``_contradiction_score`` 时不传
        ``semantic_sim``，等于**完全不看语义**——实测一对相似度仅 0.4724 的记忆
        被向量路挡下、却从关键词路判成冲突并触发静默 supersede。语义不像的两条
        不可能是「同一事实的矛盾」，这条闸门必须对两路同时生效。
        """
        if len(drawers) < 2:
            return []

        # 全量算一次 embedding，两路共用（比各算各的省，且保证尺子一致）
        embeddings: list | None = None
        if self.embedder:
            try:
                embeddings = self.embedder.embed_batch([d.content for d in drawers])
            except Exception:
                embeddings = None

        conflicts = []

        # 向量方法
        if embeddings is not None:
            try:
                conflicts = self._vector_conflict_detect(
                    drawers, min_similarity, min_confidence, embeddings=embeddings
                )
            except Exception:
                conflicts = []

        # 关键词方法（补充检测）—— 同样受 min_similarity 约束
        keyword_conflicts = self._keyword_conflict_detect(
            drawers, min_confidence, embeddings=embeddings, min_similarity=min_similarity
        )
        existing_pairs = {(c.memory_a, c.memory_b) for c in conflicts}
        existing_pairs.update((c.memory_b, c.memory_a) for c in conflicts)
        for c in keyword_conflicts:
            if (c.memory_a, c.memory_b) not in existing_pairs:
                conflicts.append(c)

        conflicts.sort(key=lambda c: c.confidence, reverse=True)
        return conflicts

    def _vector_conflict_detect(
        self,
        drawers: list[Drawer],
        min_similarity: float,
        min_confidence: float,
        embeddings: list | None = None,
    ) -> list[MemoryConflict]:
        """基于向量的冲突检测"""
        has_fact = [self._contains_fact_keywords(d.content) for d in drawers]

        # 只对包含事实关键词的记忆进行检测
        candidates = [(i, d) for i, d in enumerate(drawers) if has_fact[i]]
        if len(candidates) < 2:
            return []

        if embeddings is None:
            texts = [d.content for _, d in candidates]
            embeddings = self.embedder.embed_batch(texts)
            # 走这条分支时 embeddings 与 candidates 一一对应，用候选索引
            index_map = {ci: k for k, (ci, _) in enumerate(candidates)}
        else:
            # 传入的是全量 embeddings，用 drawer 在 drawers 中的原索引
            index_map = None

        conflicts = []
        for a in range(len(candidates)):
            for b in range(a + 1, len(candidates)):
                ia, ib = candidates[a][0], candidates[b][0]
                if index_map is None:
                    ea, eb = embeddings[ia], embeddings[ib]
                else:
                    ea, eb = embeddings[index_map[ia]], embeddings[index_map[ib]]
                conflict = self._check_vector_conflict_pair(
                    candidates, a, b, (ea, eb), min_similarity, min_confidence
                )
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _check_vector_conflict_pair(
        self,
        candidates: list,
        a: int,
        b: int,
        embeddings: tuple,
        min_similarity: float,
        min_confidence: float,
    ) -> MemoryConflict | None:
        """判定一对候选是否冲突。``embeddings`` 是 (emb_a, emb_b) 二元组。"""
        sim = self._cosine_sim(embeddings[0], embeddings[1])
        if sim < min_similarity:
            return None
        conf = self._contradiction_score(candidates[a][1].content, candidates[b][1].content, sim)
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

    def _keyword_conflict_detect(
        self,
        drawers: list[Drawer],
        min_confidence: float,
        embeddings: list | None = None,
        min_similarity: float | None = None,
    ) -> list[MemoryConflict]:
        """基于关键词的冲突检测。

        2026-09-27 起也校验语义相似度：关键词法原本**只看反义词是否同现**，
        于是一篇长文里的「于是/不是」「有/没有」「pass/error」这类**子串巧合**
        就能把毫无关系的两条记忆判成冲突。相似度不够 ⇒ 直接跳过该对。
        未提供 embeddings（无 embedder 或算失败）时保持旧口径，不做误杀。
        """
        conflicts = []
        texts = [d.content for d in drawers]

        for i in range(len(drawers)):
            for j in range(i + 1, len(drawers)):
                a = drawers[i]
                b = drawers[j]

                # 快速跳过无关记忆
                if not self._share_topic(a.content, b.content):
                    continue

                sim = 0.0
                if embeddings is not None and min_similarity is not None:
                    try:
                        sim = self._cosine_sim(embeddings[i], embeddings[j])
                    except Exception:
                        sim = 0.0
                    if sim < min_similarity:
                        # 语义不像 ⇒ 不是「同一事实的矛盾」，只是各说各事
                        continue

                conf = self._contradiction_score(a.content, b.content, sim)
                if conf["confidence"] >= min_confidence:
                    conflicts.append(
                        MemoryConflict(
                            id=f"conflict_{hex_digest(a.id + b.id)[:12]}",
                            memory_a=a.id,
                            memory_b=b.id,
                            content_a=a.content[:200],
                            content_b=b.content[:200],
                            description=conf["description"],
                            severity=conf["severity"],
                            confidence=round(conf["confidence"], 4),
                        )
                    )

        return conflicts

    def _polarity(self, text: str) -> tuple[bool, bool]:
        """文本在矛盾词表上的极性 `(含正词, 含负词)`。

        **同位置长词优先（最长匹配）** —— 裸子串匹配是 2026-09-27 三处假阳性的
        来源之一：

            「于是 gAAAAAB… 直出」含子串「是」  → 被当成正词「是」
            「当前目录不是 git」含子串「是」    → 也含正词「是」（而「不是」是负词）
            「455 passed」含子串「pass」        → 被当成正词

        长词先占位后，「不是」会覆盖其内部的「是」、「没有」覆盖「有」，于是
        「不是 git」只记负、不记正。这**不能**单独解决全部误报（长文常常两边
        同时有正负词），但能让极性如实反映文本，是相似度闸门之外的第二道网。
        """
        t = (text or "").lower()
        entries: list[tuple[str, bool]] = []
        for positive_words, negative_words in self.CONTRADICTION_PATTERNS:
            entries.extend((w, True) for w in positive_words)
            entries.extend((w, False) for w in negative_words)
        entries.sort(key=lambda e: -len(e[0]))  # 长的先占位

        occupied: list[tuple[int, int]] = []
        has_pos = has_neg = False
        for word, is_positive in entries:
            if not word:
                continue
            start = 0
            while True:
                i = t.find(word, start)
                if i < 0:
                    break
                j = i + len(word)
                start = j
                if any(i >= a and j <= b for a, b in occupied):
                    continue  # 已被同位置更长的词覆盖
                occupied.append((i, j))
                if is_positive:
                    has_pos = True
                else:
                    has_neg = True
        return has_pos, has_neg

    def _contradiction_score(self, text_a: str, text_b: str, semantic_sim: float = 0.0) -> dict:
        """计算两个文本的矛盾程度"""
        # 极性判定改走 _polarity（最长匹配），不再用 `w in text` 裸子串
        a_pos, a_neg = self._polarity(text_a)
        b_pos, b_neg = self._polarity(text_b)

        contradictions_found = []
        max_severity = ConflictSeverity.POTENTIAL

        # A 说正面，B 说反面
        if a_pos and b_neg:
            contradictions_found.append(("positive_vs_negative", 0.8))
            if max_severity in (ConflictSeverity.POTENTIAL, ConflictSeverity.MINOR):
                max_severity = ConflictSeverity.MAJOR
        # A 说反面，B 说正面
        if a_neg and b_pos:
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
            return {"confidence": 0.0, "severity": ConflictSeverity.POTENTIAL, "description": ""}

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

        words_a = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_a.lower()))
        words_b = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text_b.lower()))
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
