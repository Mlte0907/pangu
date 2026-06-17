"""盘古记忆融合引擎 — 高层抽象理解
==========================================
将多条相关记忆融合为更高层次的抽象理解。

支持：
- 主题融合：将同一主题的多条记忆合并为结构化理解
- 渐进式摘要：从细节到概括的层级抽象
- 知识结晶：从记忆中提取可复用的知识
- 跨时间融合：融合不同时间点的记忆形成观点演变
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from pangu.core.hashing import hex_digest

from ..core.config import PanguConfig
from ..core.palace import Drawer


@dataclass
class FusedKnowledge:
    """融合知识"""
    id: str
    topic: str  # 主题
    summary: str  # 摘要
    key_points: list[str]  # 关键要点
    source_memories: list[str]  # 源记忆 ID
    confidence: float  # 融合置信度
    contradictions: list[str] = field(default_factory=list)  # 发现的矛盾
    evolution: list[dict] = field(default_factory=list)  # 观点演变
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class FusionEngine:
    """记忆融合引擎"""

    @staticmethod
    def _cosine_sim(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
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

    def fuse_topic(self, topic: str, drawers: list[Drawer],
                   min_similarity: float = 0.99) -> FusedKnowledge | None:
        """融合同一主题的记忆

        Args:
            topic: 主题关键词
            drawers: 记忆列表
            min_similarity: 最小相似度

        Returns:
            融合知识，或 None
        """
        # 筛选相关记忆
        topic_lower = topic.lower()
        relevant = []
        for d in drawers:
            content_lower = d.content.lower()
            if topic_lower in content_lower:
                relevant.append((d, 1.0))  # 精确匹配
            elif self.embedder:
                try:
                    topic_emb = self.embedder.embed(topic)
                    content_emb = self.embedder.embed(d.content)
                    sim = self._cosine_sim(topic_emb, content_emb)
                    if sim >= min_similarity:
                        relevant.append((d, sim))
                except Exception:
                    pass

        if not relevant:
            return None

        relevant.sort(key=lambda x: (x[1], x[0].importance), reverse=True)
        top_drawers = [d for d, _ in relevant[:20]]

        # 提取关键要点
        key_points = self._extract_key_points(top_drawers)

        # 生成摘要
        summary = self._generate_summary(topic, top_drawers)

        # 检测矛盾
        contradictions = self._detect_internal_contradictions(top_drawers)

        # 分析观点演变
        evolution = self._analyze_evolution(top_drawers)

        avg_importance = sum(d.importance for d in top_drawers) / len(top_drawers)
        confidence = min(1.0, 0.5 + (avg_importance / 10) + (len(top_drawers) / 50))

        fusion_id = hex_digest(
            topic + "".join(d.id for d in top_drawers[:5])
        )[:12]

        return FusedKnowledge(
            id=fusion_id,
            topic=topic,
            summary=summary,
            key_points=key_points,
            source_memories=[d.id for d in top_drawers],
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evolution=evolution,
        )

    def _extract_key_points(self, drawers: list[Drawer]) -> list[str]:
        """从记忆中提取关键要点"""
        import re

        # 提取所有句子
        all_sentences = []
        for d in drawers:
            # 按句号/分号/换行分句
            sentences = re.split(r'[。；;！!？?\n]+', d.content)
            for s in sentences:
                s = s.strip()
                if len(s) > 10 and len(s) < 200:
                    all_sentences.append((s, d.importance))

        if not all_sentences:
            return [d.content[:100] for d in drawers[:3]]

        # 按重要性排序
        all_sentences.sort(key=lambda x: x[1], reverse=True)

        # 去重（简单余弦相似度对句子太慢，用关键词去重）
        seen_keywords = set()
        key_points = []
        for sentence, _imp in all_sentences:
            words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                    sentence.lower()))
            overlap = len(words & seen_keywords) / max(len(words), 1)
            if overlap < 0.5 and words:
                key_points.append(sentence)
                seen_keywords.update(words)
            if len(key_points) >= 10:
                break

        return key_points

    def _generate_summary(self, topic: str, drawers: list[Drawer]) -> str:
        """生成主题摘要"""
        if not drawers:
            return f"关于 '{topic}' 暂无记忆"

        # 提取最频繁的关键词
        all_words = []
        for d in drawers:
            import re
            words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                d.content.lower())
            all_words.extend(words)

        word_freq = Counter(all_words)
        top_words = [w for w, _ in word_freq.most_common(10)
                     if w.lower() != topic.lower()]

        # 按重要性排序
        sorted_drawers = sorted(drawers, key=lambda d: d.importance, reverse=True)
        key_contents = [d.content[:150] for d in sorted_drawers[:3]]

        num_memories = len(drawers)
        time_range = ""
        try:
            dates = [datetime.fromisoformat(d.created_at)
                     for d in drawers if d.created_at]
            if dates:
                earliest = min(dates).strftime("%Y-%m-%d")
                latest = max(dates).strftime("%Y-%m-%d")
                time_range = f"（时间跨度: {earliest} ~ {latest}）"
        except (ValueError, TypeError):
            pass

        return (
            f"关于「{topic}」的融合理解：共涉及 {num_memories} 条记忆{time_range}。\n"
            f"核心关键词：{'、'.join(top_words[:8])}。\n"
            f"关键内容：\n" +
            "\n".join(f"  - {c}" for c in key_contents)
        )

    def _detect_internal_contradictions(self, drawers: list[Drawer]) -> list[str]:
        """检测记忆内部的矛盾"""
        contradictions = []

        # 简单矛盾检测
        positive = {"支持", "推荐", "建议", "应该", "是", "正确", "好", "成功",
                     "support", "recommend", "yes", "true", "good", "success"}
        negative = {"不支持", "不推荐", "不建议", "不应该", "不是", "错误", "不好",
                     "失败", "not support", "not recommend", "no", "false", "bad", "fail"}

        for i in range(len(drawers)):
            for j in range(i + 1, len(drawers)):
                a = drawers[i].content.lower()
                b = drawers[j].content.lower()
                a_pos = any(w in a for w in positive)
                a_neg = any(w in a for w in negative)
                b_pos = any(w in b for w in positive)
                b_neg = any(w in b for w in negative)

                if (a_pos and b_neg) or (a_neg and b_pos):
                    contradictions.append(
                        f"'{drawers[i].content[:50]}...' ↔ '{drawers[j].content[:50]}...'"
                    )

        return contradictions[:5]

    def _analyze_evolution(self, drawers: list[Drawer]) -> list[dict]:
        """分析观点演变"""
        if len(drawers) < 2:
            return []

        # 按时间排序
        sorted_drawers = sorted(drawers, key=lambda d: d.created_at or "")

        evolution = []
        for i, d in enumerate(sorted_drawers):
            evolution.append({
                "stage": f"阶段{i + 1}",
                "time": d.created_at[:10] if d.created_at else "未知",
                "content": d.content[:100],
                "importance": d.importance,
            })

        return evolution

    def progressive_summarize(self, drawers: list[Drawer],
                              levels: int = 3) -> list[dict]:
        """渐进式摘要：从细节到概括的层级抽象

        Args:
            drawers: 记忆列表
            levels: 抽象层级数

        Returns:
            [层级1: 细节, 层级2: 概括, 层级3: 高度抽象]
        """
        if not drawers:
            return []

        result = []

        # 层级 1: 原始细节（按重要性排序）
        sorted_drawers = sorted(drawers, key=lambda d: d.importance, reverse=True)
        level1 = [
            {"id": d.id, "content": d.content[:200], "importance": d.importance}
            for d in sorted_drawers[:10]
        ]
        result.append({"level": 1, "label": "原始细节", "items": level1})

        # 层级 2: 主题分组
        groups = self._group_by_keywords(sorted_drawers)
        level2 = []
        for group_topic, group_drawers in groups.items():
            avg_imp = sum(d.importance for d in group_drawers) / len(group_drawers)
            level2.append({
                "topic": group_topic,
                "count": len(group_drawers),
                "avg_importance": round(avg_imp, 2),
                "sample": group_drawers[0].content[:100] if group_drawers else "",
            })
        result.append({"level": 2, "label": "主题分组", "items": level2[:10]})

        # 层级 3: 高度抽象
        if len(drawers) >= 3:
            all_keywords = Counter()
            for d in drawers:
                import re
                words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                    d.content.lower())
                all_keywords.update(words)
            top_abstract = [w for w, _ in all_keywords.most_common(15)]
            level3 = {
                "total_memories": len(drawers),
                "date_range": self._get_date_range(drawers),
                "primary_topics": top_abstract[:8],
                "avg_importance": round(
                    sum(d.importance for d in drawers) / len(drawers), 2),
                "dominant_wing": Counter(d.wing for d in drawers).most_common(1)[0][0],
            }
            result.append({"level": 3, "label": "高度抽象", "items": level3})

        return result

    def _group_by_keywords(self, drawers: list[Drawer]) -> dict[str, list[Drawer]]:
        """按关键词分组"""
        import re
        groups = {}

        for d in drawers:
            keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}',
                                   d.content.lower())
            # 取第一个有意义的词作为分组
            topic = keywords[0] if keywords else "其他"
            if topic not in groups:
                groups[topic] = []
            groups[topic].append(d)

        return groups

    def _get_date_range(self, drawers: list[Drawer]) -> str:
        """获取日期范围"""
        try:
            dates = [datetime.fromisoformat(d.created_at)
                     for d in drawers if d.created_at]
            if not dates:
                return "未知"
            return f"{min(dates).strftime('%Y-%m-%d')} ~ {max(dates).strftime('%Y-%m-%d')}"
        except (ValueError, TypeError):
            return "未知"

    def crystallize_knowledge(self, drawers: list[Drawer],
                              topic: str = "") -> dict:
        """知识结晶：从记忆中提取可复用的知识

        Returns:
            {"facts": [...], "lessons": [...], "decisions": [...], "patterns": [...]}
        """
        knowledge = {
            "facts": [],      # 事实性知识
            "lessons": [],    # 经验教训
            "decisions": [],  # 决策记录
            "patterns": [],   # 发现的模式
        }

        fact_keywords = ["版本", "version", "配置", "config", "地址", "url",
                         "端口", "port", "密钥", "key"]
        lesson_keywords = ["教训", "lesson", "经验", "experience", "不要",
                           "don't", "避免", "avoid", "注意", "小心"]
        decision_keywords = ["决定", "decision", "选择", "choose", "采用",
                             "adopt", "方案", "计划", "plan"]
        pattern_keywords = ["模式", "pattern", "规律", "规则", "rule",
                            "总是", "always", "通常", "usually", "习惯"]

        for d in drawers:
            content_lower = d.content.lower()
            if topic and topic.lower() not in content_lower:
                continue
            self._classify_drawer(d, content_lower, fact_keywords, lesson_keywords,
                                  decision_keywords, pattern_keywords, knowledge)

        return knowledge

    def _classify_drawer(self, d, content_lower, fact_keywords, lesson_keywords,
                         decision_keywords, pattern_keywords, knowledge):
        entry = {"content": d.content[:200], "importance": d.importance}
        if any(kw in content_lower for kw in fact_keywords):
            knowledge["facts"].append(entry)
        if any(kw in content_lower for kw in lesson_keywords):
            knowledge["lessons"].append(entry)
        if any(kw in content_lower for kw in decision_keywords):
            knowledge["decisions"].append(entry)
        if any(kw in content_lower for kw in pattern_keywords):
            knowledge["patterns"].append(entry)
