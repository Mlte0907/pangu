"""盘古上下文注入引擎 — 自动为对话注入相关记忆上下文

核心能力：
1. 上下文感知：感知当前对话主题和上下文
2. 自动注入：自动从记忆库中检索并注入最相关的记忆
3. 优先级排序：根据重要性、时效性、相关性排序
4. Token 预算管理：在 token 限制内最大化上下文价值
5. 增量更新：对话进行中持续更新上下文
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("pangu.memory.context_injection")


@dataclass
class InjectedContext:
    """注入的上下文"""
    memory_id: str
    content: str
    wing: str
    relevance_score: float
    importance_score: float
    recency_score: float
    final_score: float
    injection_position: str  # prefix / inline / suffix


@dataclass
class InjectionResult:
    """注入结果"""
    original_text: str
    injected_text: str
    context_count: int
    tokens_used: int
    token_budget: int
    injection_positions: list[dict]


class ContextInjectionEngine:
    """上下文注入引擎"""

    RELEVANCE_KEYWORDS = {
        "code": ["代码", "函数", "实现", "API", "模块", "类"],
        "config": ["配置", "设置", "参数", "config", "环境"],
        "debug": ["错误", "bug", "修复", "问题", "异常", "失败"],
        "design": ["设计", "架构", "方案", "规划", "结构"],
        "deploy": ["部署", "上线", "发布", "服务", "端口"],
        "test": ["测试", "验证", "检查", "测试用例"],
        "memory": ["记忆", "存储", "检索", "搜索", "回忆"],
        "ai": ["AI", "模型", "推理", "嵌入", "向量", "ONNX"],
    }

    def __init__(self, config=None):
        self.config = config
        self._injection_history: list[dict] = []
        self._context_buffer: list[InjectedContext] = []

    def detect_context_topics(self, text: str) -> list[str]:
        """检测文本中的上下文主题"""
        topics = []
        text_lower = text.lower()
        for topic, keywords in self.RELEVANCE_KEYWORDS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                topics.append(topic)
        return topics if topics else ["general"]

    def score_relevance(self, drawer, topics: list[str]) -> float:
        """计算记忆与当前上下文的相关性分数"""
        score = 0.0
        content_lower = drawer.content.lower()
        tags_lower = [t.lower() for t in drawer.tags]

        for topic in topics:
            keywords = self.RELEVANCE_KEYWORDS.get(topic, [])
            for kw in keywords:
                if kw.lower() in content_lower:
                    score += 0.15
                if any(kw.lower() in t for t in tags_lower):
                    score += 0.25

        for tag in drawer.tags:
            for topic in topics:
                if topic in tag.lower():
                    score += 0.2

        return min(1.0, score)

    def score_recency(self, drawer) -> float:
        """计算记忆的新鲜度分数"""
        if hasattr(drawer, 'updated_at') and drawer.updated_at:
            try:
                updated = datetime.fromisoformat(drawer.updated_at)
                days_old = (datetime.now() - updated).days
                if days_old < 7:
                    return 1.0
                elif days_old < 30:
                    return 0.8
                elif days_old < 90:
                    return 0.5
                else:
                    return 0.3
            except (ValueError, TypeError):
                pass
        return 0.5

    def _inject_single(self, d, final, relevance, importance, recency,
                       tokens_used: int, token_budget: int,
                       injected: list) -> int:
        est_tokens = int(len(d.content) * 1.5)
        if tokens_used + est_tokens > token_budget:
            remaining = token_budget - tokens_used
            truncated_len = int(remaining / 1.5)
            if truncated_len > 20:
                content = d.content[:truncated_len] + "..."
                injected.append(InjectedContext(
                    memory_id=d.id, content=content, wing=d.wing,
                    relevance_score=relevance, importance_score=importance,
                    recency_score=recency, final_score=final,
                    injection_position="prefix",
                ))
                return remaining
            return 0
        injected.append(InjectedContext(
            memory_id=d.id, content=d.content, wing=d.wing,
            relevance_score=relevance, importance_score=importance,
            recency_score=recency, final_score=final,
            injection_position="prefix",
        ))
        return est_tokens

    def inject_context(self, text: str, drawers: list,
                       token_budget: int = 500, max_memories: int = 5) -> InjectionResult:
        topics = self.detect_context_topics(text)

        scored = []
        for d in drawers:
            relevance = self.score_relevance(d, topics)
            importance = d.importance / 5.0
            recency = self.score_recency(d)

            final = 0.5 * relevance + 0.3 * importance + 0.2 * recency
            if final > 0.2:
                scored.append((d, final, relevance, importance, recency))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:max_memories]

        injected = []
        tokens_used = 0
        for d, final, relevance, importance, recency in top:
            used = self._inject_single(d, final, relevance, importance, recency,
                                       tokens_used, token_budget, injected)
            if used == 0:
                break
            tokens_used += used

        if injected:
            context_block = "[相关记忆上下文]\n"
            for ctx in injected:
                context_block += f"- [{ctx.wing}] {ctx.content[:150]}\n"
            context_block += "[/相关记忆上下文]\n\n"
            injected_text = context_block + text
        else:
            injected_text = text

        self._context_buffer = injected
        self._injection_history.append({
            "topics": topics,
            "injected_count": len(injected),
            "tokens_used": tokens_used,
            "timestamp": datetime.now().isoformat(),
        })

        return InjectionResult(
            original_text=text,
            injected_text=injected_text,
            context_count=len(injected),
            tokens_used=tokens_used,
            token_budget=token_budget,
            injection_positions=[
                {"id": c.memory_id, "wing": c.wing, "score": round(c.final_score, 3)}
                for c in injected
            ],
        )

    def get_current_context(self) -> list[dict]:
        """获取当前上下文缓冲"""
        return [
            {"id": c.memory_id, "content": c.content[:100], "wing": c.wing,
             "score": round(c.final_score, 3)}
            for c in self._context_buffer
        ]

    def update_context(self, new_text: str, drawers: list) -> InjectionResult:
        """增量更新上下文"""
        combined = " ".join(c.content for c in self._context_buffer[:3]) + " " + new_text
        return self.inject_context(combined, drawers)

    def get_injection_stats(self) -> dict:
        """获取注入统计"""
        if not self._injection_history:
            return {"total_injections": 0, "avg_tokens": 0}

        avg_tokens = sum(h["tokens_used"] for h in self._injection_history) / len(self._injection_history)
        return {
            "total_injections": len(self._injection_history),
            "avg_tokens_used": round(avg_tokens),
            "avg_context_count": round(
                sum(h["injected_count"] for h in self._injection_history) / len(self._injection_history), 1
            ),
        }


_injection_engine: ContextInjectionEngine | None = None


def get_injection_engine(config=None) -> ContextInjectionEngine:
    """获取全局上下文注入引擎实例"""
    global _injection_engine
    if _injection_engine is None:
        _injection_engine = ContextInjectionEngine(config)
    return _injection_engine
