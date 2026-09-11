"""盘古主动提醒引擎 — 检测重复问题，推送相关记忆

核心能力：
1. 问题追踪：记录用户问过的所有问题
2. 重复检测：识别相似问题被反复询问
3. 主动推送：在用户提问时自动推送相关记忆
4. 模式发现：发现用户关注的主题模式

使用方式：
    engine = ProactiveReminderEngine()
    # 检测到新问题时
    reminders = engine.on_new_question("盘古的状态怎么样")
    # 获取用户关注模式
    patterns = get_user_interest_patterns()
"""

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.proactive_reminder")


@dataclass
class Reminder:
    """主动提醒"""

    memory_id: str
    content: str
    relevance_score: float
    reason: str
    reminder_type: str  # repeated_question, related_topic, fresh_knowledge
    tags: list[str] = field(default_factory=list)


@dataclass
class QuestionRecord:
    """问题记录"""

    question: str
    timestamp: str
    topic: str
    keywords: list[str]


class ProactiveReminderEngine:
    """主动提醒引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._history_file = Path(self.config.palace_path) / "question_history.json"
        self._history: list[dict] = self._load_history()
        self._topic_stats: dict[str, int] = self._compute_topic_stats()

    def _load_history(self) -> list[dict]:
        """加载问题历史"""
        if self._history_file.exists():
            try:
                with open(self._history_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        """保存问题历史"""
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save question history: {e}")

    def _compute_topic_stats(self) -> dict[str, int]:
        """计算主题频率"""
        stats = Counter()
        for record in self._history:
            topic = record.get("topic", "")
            if topic:
                stats[topic] += 1
        return dict(stats)

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        # 简单分词 + 过滤
        stop_words = {
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
        }

        # 提取中文词和英文词
        words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", text)
        return [w for w in words if len(w) >= 2 and w not in stop_words]

    def _extract_topic(self, question: str) -> str:
        """提取问题主题"""
        keywords = self._extract_keywords(question)
        if keywords:
            return keywords[0]  # 取第一个关键词作为主题
        return question[:10]

    def _calculate_similarity(self, q1: str, q2: str) -> float:
        """计算两个问题的相似度"""
        kw1 = set(self._extract_keywords(q1))
        kw2 = set(self._extract_keywords(q2))

        if not kw1 or not kw2:
            return 0.0

        intersection = kw1 & kw2
        union = kw1 | kw2

        return len(intersection) / len(union) if union else 0.0

    def _find_similar_questions(self, question: str, threshold: float = 0.5) -> list[dict]:
        """查找相似的历史问题"""
        similar = []

        for record in self._history[-100:]:  # 只看最近100条
            history_q = record.get("question", "")
            similarity = self._calculate_similarity(question, history_q)

            if similarity >= threshold:
                similar.append(
                    {
                        "question": history_q,
                        "timestamp": record.get("timestamp", ""),
                        "similarity": similarity,
                        "topic": record.get("topic", ""),
                    }
                )

        return sorted(similar, key=lambda x: x["similarity"], reverse=True)

    def on_new_question(self, question: str) -> list[Reminder]:
        """处理新问题，返回主动提醒"""
        reminders = []

        # 记录问题
        keywords = self._extract_keywords(question)
        topic = self._extract_topic(question)

        record = {
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "keywords": keywords,
        }
        self._history.append(record)

        # 更新主题统计
        self._topic_stats[topic] = self._topic_stats.get(topic, 0) + 1

        # 保存历史
        self._save_history()

        # 检测重复问题
        similar = self._find_similar_questions(question)
        if len(similar) >= 2:
            # 发现重复提问模式
            reminders.append(
                Reminder(
                    memory_id="pattern_repeat",
                    content=f"你之前问过 {len(similar)} 次类似问题：{similar[0]['question']}",
                    relevance_score=0.9,
                    reason=f"检测到重复提问模式（{len(similar)}次）",
                    reminder_type="repeated_question",
                    tags=["pattern", "repeat"],
                )
            )

        # 搜索相关记忆
        related_memories = self._search_related_memories(question)
        for mem in related_memories[:3]:  # 最多推送3条
            reminders.append(
                Reminder(
                    memory_id=mem["id"],
                    content=mem["content"],
                    relevance_score=mem["score"],
                    reason=f"与当前问题相关（{mem['match_type']}）",
                    reminder_type="related_topic",
                    tags=mem.get("tags", []),
                )
            )

        # 检查是否有新知识
        fresh = self._find_fresh_knowledge(keywords)
        if fresh:
            reminders.append(
                Reminder(
                    memory_id=fresh["id"],
                    content=fresh["content"],
                    relevance_score=0.7,
                    reason="最近提取的新知识",
                    reminder_type="fresh_knowledge",
                    tags=fresh.get("tags", []),
                )
            )

        return reminders

    def _search_related_memories(self, question: str) -> list[dict]:
        """搜索相关记忆"""
        try:
            from pangu.core.palace import Drawer
            from pangu.memory.fts_search import FTS5SearchEngine

            # 加载记忆
            drawers_file = Path(self.config.palace_path) / "drawers.json"
            if not drawers_file.exists():
                return []

            with open(drawers_file, encoding="utf-8") as f:
                data = json.load(f)
            drawers = [Drawer.from_dict(d) for d in data]

            # 搜索
            engine = FTS5SearchEngine()
            engine.build_index(drawers)

            scores = engine._fts_search(question, drawers, limit=5)

            results = []
            drawer_map = {d.id: d for d in drawers}
            for did, score in sorted(scores.items(), key=lambda x: -x[1])[:5]:
                d = drawer_map.get(did)
                if d and score > 0.3:
                    results.append(
                        {
                            "id": did,
                            "content": d.content[:200],
                            "score": score,
                            "tags": d.tags,
                            "match_type": "fts",
                        }
                    )

            return results
        except Exception as e:
            logger.error(f"Search related memories failed: {e}")
            return []

    def _find_fresh_knowledge(self, keywords: list[str]) -> dict | None:
        """查找最近提取的新知识"""
        try:
            drawers_file = Path(self.config.palace_path) / "drawers.json"
            if not drawers_file.exists():
                return None

            with open(drawers_file, encoding="utf-8") as f:
                data = json.load(f)

            # 查找最近24小时内提取的知识
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

            for d in reversed(data):  # 从最新开始
                if "auto_extracted" not in d.get("tags", []):
                    continue
                created = d.get("created_at", "")
                if created < cutoff:
                    break

                # 检查关键词匹配
                content = d.get("content", "").lower()
                for kw in keywords:
                    if kw.lower() in content:
                        return {
                            "id": d.get("id", ""),
                            "content": d.get("content", "")[:200],
                            "tags": d.get("tags", []),
                        }

            return None
        except Exception as e:
            logger.error(f"Find fresh knowledge failed: {e}")
            return None

    def get_user_interest_patterns(self) -> dict:
        """获取用户关注模式"""
        if not self._history:
            return {"total_questions": 0, "top_topics": [], "frequency": {}}

        # 主题频率
        topic_counts = Counter(r.get("topic", "") for r in self._history)
        top_topics = topic_counts.most_common(10)

        # 时间频率
        hourly = defaultdict(int)
        for r in self._history:
            ts = r.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    hourly[dt.hour] += 1
                except Exception:
                    pass

        return {
            "total_questions": len(self._history),
            "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
            "hourly_frequency": dict(hourly),
            "unique_topics": len(topic_counts),
        }

    def get_repeated_questions(self, min_count: int = 2) -> list[dict]:
        """获取重复提问的问题"""
        question_counts = Counter(r.get("question", "") for r in self._history)

        repeated = []
        for q, count in question_counts.most_common():
            if count >= min_count:
                repeated.append(
                    {
                        "question": q,
                        "count": count,
                        "last_asked": next(
                            (r.get("timestamp", "") for r in reversed(self._history) if r.get("question") == q), ""
                        ),
                    }
                )

        return repeated


# 单例
_engine: ProactiveReminderEngine | None = None


def get_proactive_engine() -> ProactiveReminderEngine:
    """获取单例引擎"""
    global _engine
    if _engine is None:
        _engine = ProactiveReminderEngine()
    return _engine
