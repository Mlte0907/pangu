"""盘古智能问答引擎 — 基于记忆的智能问答

核心能力：
1. 上下文理解：理解问题的上下文和意图
2. 记忆检索：从记忆库中检索相关知识
3. 推理综合：综合多条记忆生成答案
4. 置信度评估：评估答案的可信度
5. 追问生成：生成有价值的追问
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("pangu.memory.qa_engine")


@dataclass
class QAResult:
    """问答结果"""
    question: str
    answer: str
    confidence: float
    source_memories: list[dict]
    follow_up_questions: list[str]
    reasoning_steps: list[str]


class QAEngine:
    """智能问答引擎"""

    INTENT_PATTERNS = {
        "what": ["什么", "哪些", "哪些", "是什么", "什么是"],
        "how": ["如何", "怎么", "怎样", "方法"],
        "why": ["为什么", "原因", "为何"],
        "when": ["什么时候", "何时", "时间"],
        "who": ["谁", "哪个", "哪些人"],
    }

    def __init__(self, config=None):
        self.config = config
        self._qa_history: list[dict] = []

    def detect_intent(self, question: str) -> str:
        """检测问题意图"""
        q_lower = question.lower()
        for intent, keywords in self.INTENT_PATTERNS.items():
            if any(kw in q_lower for kw in keywords):
                return intent
        return "general"

    def answer(self, question: str, drawers: list, recall_fn=None) -> QAResult:
        """回答问题"""
        import re
        intent = self.detect_intent(question)
        reasoning = [f"检测到意图: {intent}"]

        # 1. 检索相关记忆
        relevant = []
        # 提取问题关键词（中文2字+，英文整体）
        q_keywords = set()
        for segment in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', question):
            q_keywords.add(segment.lower())

        q_lower = question.lower()
        for d in drawers:
            score = self._score_memory(d, q_keywords, q_lower)

            if score > 0:
                relevant.append((d, score))

        relevant.sort(key=lambda x: x[1], reverse=True)
        top_memories = relevant[:5]
        reasoning.append(f"检索到 {len(relevant)} 条相关记忆，取 Top 5")

        # 2. 综合答案
        if not top_memories:
            answer = f"未找到与'{question}'相关的记忆。建议提供更多上下文。"
            confidence = 0.1
        else:
            sources = []
            fragments = []
            for d, score in top_memories:
                sources.append({"id": d.id, "content": d.content[:80], "score": score})
                fragments.append(d.content[:100])

            if intent == "what":
                answer = "根据记忆：" + "；".join(fragments[:3])
            elif intent == "how":
                answer = "方法/经验：" + "；".join(fragments[:3])
            elif intent == "why":
                answer = "原因分析：" + "；".join(fragments[:3])
            else:
                answer = "相关信息：" + "；".join(fragments[:3])

            confidence = min(0.9, 0.3 + len(top_memories) * 0.1 + top_memories[0][1] * 0.05)
            reasoning.append(f"综合 {len(top_memories)} 条记忆生成答案")

        # 3. 生成追问
        follow_up = self._generate_follow_up(question, top_memories, intent)
        reasoning.append(f"生成 {len(follow_up)} 个追问")

        result = QAResult(
            question=question,
            answer=answer[:500],
            confidence=confidence,
            source_memories=[{"id": d.id, "content": d.content[:80]} for d, _ in top_memories[:3]],
            follow_up_questions=follow_up,
            reasoning_steps=reasoning,
        )

        self._qa_history.append({
            "question": question,
            "intent": intent,
            "confidence": confidence,
            "source_count": len(top_memories),
        })

        return result

    def _generate_follow_up(self, question: str, memories: list, intent: str) -> list[str]:
        """生成追问"""
        follow_ups = []

        if intent == "what":
            follow_ups.append(f"关于 {question} 的更多细节是什么？")
        elif intent == "how":
            follow_ups.append("这个方法有什么注意事项？")
        elif intent == "why":
            follow_ups.append("有其他可能的原因吗？")
        else:
            follow_ups.append(f"关于这个话题，还有什么值得了解的？")

        if memories:
            tags = set()
            for d, _ in memories[:3]:
                tags.update(d.tags)
            if tags:
                tag_list = list(tags)[:3]
                follow_ups.append(f"想了解更多关于 {'/'.join(tag_list)} 的内容吗？")

        return follow_ups

    def _score_memory(self, d, q_keywords: set, q_lower: str) -> float:
        score = 0
        d_lower = d.content.lower()
        for kw in q_keywords:
            if kw in d_lower:
                score += 2
        if d.tags:
            for tag in d.tags:
                tag_l = tag.lower()
                for kw in q_keywords:
                    if kw in tag_l or tag_l in kw:
                        score += 3
        for i in range(len(q_lower) - 1):
            bigram = q_lower[i:i+2]
            if bigram in d_lower:
                score += 0.5
        return score

    def batch_answer(self, questions: list[str], drawers: list) -> list[QAResult]:
        """批量问答"""
        return [self.answer(q, drawers) for q in questions]

    def get_qa_stats(self) -> dict:
        """获取问答统计"""
        if not self._qa_history:
            return {"total_questions": 0, "avg_confidence": 0}

        avg_conf = sum(q["confidence"] for q in self._qa_history) / len(self._qa_history)
        return {
            "total_questions": len(self._qa_history),
            "avg_confidence": round(avg_conf, 3),
            "intent_distribution": {},
        }


_qa_engine: QAEngine | None = None


def get_qa_engine(config=None) -> QAEngine:
    """获取全局问答引擎实例"""
    global _qa_engine
    if _qa_engine is None:
        _qa_engine = QAEngine(config)
    return _qa_engine
