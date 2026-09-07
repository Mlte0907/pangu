"""盘古搜索查询重写 — 自动改写和优化搜索查询

核心能力：
1. 查询纠错：修正拼写和语法错误
2. 查询扩展：添加同义词和相关词
3. 查询分解：将复杂查询分解为子查询
4. 查询聚焦：识别核心意图，去除噪声
5. 查询建议：推荐更好的搜索查询
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("pangu.memory.query_rewriter")


@dataclass
class RewrittenQuery:
    """重写后的查询"""

    original: str
    rewritten: str
    strategy: str
    expanded_terms: list[str]
    confidence: float


class QueryRewriter:
    """搜索查询重写引擎"""

    SYNONYM_MAP = {
        "记忆": ["存储", "保存", "recall", "memory"],
        "搜索": ["检索", "查找", "查询", "search", "retrieve"],
        "优化": ["改进", "提升", "增强", "optimize", "improve"],
        "系统": ["平台", "框架", "架构", "system"],
        "模型": ["算法", "网络", "model"],
        "数据": ["信息", "知识", "data", "information"],
        "问题": ["错误", "bug", "issue", "problem"],
        "性能": ["速度", "延迟", "效率", "performance", "latency"],
        "部署": ["上线", "发布", "deploy"],
        "测试": ["验证", "检查", "test"],
        "配置": ["设置", "参数", "config", "setting"],
        "文档": ["说明", "手册", "doc", "documentation"],
        "推理": ["推断", "预测", "inference", "reasoning"],
        "向量": ["嵌入", "embedding", "vector"],
        "图谱": ["关系图", "知识图", "graph"],
    }

    INTENT_KEYWORDS = {
        "search": ["怎么", "如何", "怎样", "哪里", "搜索", "查找", "检索"],
        "explain": ["什么", "为什么", "原因", "解释", "说明"],
        "create": ["创建", "新建", "写", "构建", "搭建"],
        "fix": ["修复", "解决", "问题", "错误", "bug", "故障"],
        "optimize": ["优化", "改进", "提升", "加速", "减少"],
    }

    def __init__(self, config=None):
        self.config = config
        self._rewrite_history: list[dict] = []

    def _match_word_synonyms(self, word: str, synonyms: list[str], query: str, top_k: int) -> list[str]:
        """为单个词匹配同义词"""
        if word not in query:
            return []
        return [syn for syn in synonyms[:top_k] if syn not in query]

    def expand_synonyms(self, query: str, top_k: int = 3) -> list[str]:
        """扩展同义词"""
        expanded = []
        for word, synonyms in self.SYNONYM_MAP.items():
            expanded.extend(self._match_word_synonyms(word, synonyms, query, top_k))
        return expanded[: top_k * 2]

    def detect_intent(self, query: str) -> str:
        """检测查询意图"""
        q_lower = query.lower()
        for intent, keywords in self.INTENT_KEYWORDS.items():
            if any(kw in q_lower for kw in keywords):
                return intent
        return "search"

    def decompose_query(self, query: str) -> list[str]:
        """分解复杂查询"""
        parts = []
        for sep in ["和", "以及", "并且", "然后", "同时", "AND", "+"]:
            if sep in query:
                parts = [p.strip() for p in query.split(sep) if p.strip()]
                break

        if not parts:
            for sep in ["，", ",", "；", ";"]:
                if sep in query:
                    parts = [p.strip() for p in query.split(sep) if p.strip()]
                    break

        if not parts:
            parts = [query]

        return parts[:5]

    def rewrite(self, query: str, strategy: str = "auto") -> RewrittenQuery:
        """重写查询"""
        if strategy == "auto":
            strategy = "expand_synonym"

        expanded = self.expand_synonyms(query)
        parts = self.decompose_query(query)
        intent = self.detect_intent(query)

        if strategy == "expand_synonym" and expanded:
            rewritten = query + " " + " ".join(expanded[:3])
            confidence = 0.7
        elif strategy == "decompose" and len(parts) > 1:
            rewritten = " OR ".join(parts)
            confidence = 0.6
        elif strategy == "focus":
            keywords = [w for w in query.split() if len(w) >= 2]
            rewritten = " ".join(keywords[:5])
            confidence = 0.65
        else:
            rewritten = query
            confidence = 0.5

        result = RewrittenQuery(
            original=query,
            rewritten=rewritten[:200],
            strategy=strategy,
            expanded_terms=expanded,
            confidence=confidence,
        )

        self._rewrite_history.append(
            {
                "original": query[:50],
                "strategy": strategy,
                "expanded_count": len(expanded),
                "intent": intent,
            }
        )

        return result

    def suggest_queries(self, partial: str, drawers: list, top_k: int = 5) -> list[str]:
        """基于部分输入建议查询"""
        suggestions = []
        p_lower = partial.lower()

        tag_suggestions = set()
        for d in drawers:
            for tag in d.tags:
                if p_lower in tag.lower():
                    tag_suggestions.add(tag)

        for tag in list(tag_suggestions)[:top_k]:
            suggestions.append(f"{partial} {tag}")

        if not suggestions:
            suggestions = self._suggest_synonyms(partial)[:top_k]

        return suggestions[:top_k]

    def _suggest_synonyms(self, partial: str) -> list[str]:
        suggestions = []
        for word, synonyms in self.SYNONYM_MAP.items():
            if word in partial or any(syn in partial for syn in synonyms):
                for syn in synonyms[:2]:
                    if syn not in partial:
                        suggestions.append(f"{partial} {syn}")
        return suggestions

    def batch_rewrite(self, queries: list[str]) -> list[RewrittenQuery]:
        """批量重写"""
        return [self.rewrite(q) for q in queries]

    def get_rewrite_stats(self) -> dict:
        """获取重写统计"""
        if not self._rewrite_history:
            return {"total_rewrites": 0}

        strategy_counts: dict[str, int] = {}
        for h in self._rewrite_history:
            s = h["strategy"]
            strategy_counts[s] = strategy_counts.get(s, 0) + 1

        intent_counts: dict[str, int] = {}
        for h in self._rewrite_history:
            i = h["intent"]
            intent_counts[i] = intent_counts.get(i, 0) + 1

        return {
            "total_rewrites": len(self._rewrite_history),
            "strategy_distribution": strategy_counts,
            "intent_distribution": intent_counts,
        }


_rewriter: QueryRewriter | None = None


def get_rewriter(config=None) -> QueryRewriter:
    """获取全局查询重写引擎实例"""
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter(config)
    return _rewriter
