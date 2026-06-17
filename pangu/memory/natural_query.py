"""盘古 — 自然语言查询接口
将自然语言查询转换为结构化记忆检索
"""
import re
from datetime import datetime, timedelta
from typing import Optional

from ..core.palace import Drawer


class NaturalLanguageQuery:
    """自然语言查询解析器"""

    # 时间关键词映射
    TIME_KEYWORDS = {
        '今天': 0,
        '昨天': 1,
        '前天': 2,
        '上周': 7,
        '本周': 0,
        '最近': 7,
        '最近一周': 7,
        '最近一个月': 30,
        '最近三天': 3,
        '最近七天': 7,
    }

    # 空间关键词映射
    WING_KEYWORDS = {
        '技术': 'tech',
        '技术相关': 'tech',
        '代码': 'tech',
        '开发': 'tech',
        '工作': 'work',
        '项目': 'work',
        '个人': 'personal',
        '生活': 'personal',
        '学习': 'learning',
        '知识': 'learning',
    }

    # 重要性关键词
    IMPORTANCE_KEYWORDS = {
        '重要': 0.8,
        '关键': 0.9,
        '紧急': 0.9,
        '必须': 0.8,
        '重要事件': 0.8,
        '决策': 0.7,
        '决定': 0.7,
    }

    def parse(self, query: str) -> dict:
        """解析自然语言查询

        Args:
            query: 自然语言查询字符串

        Returns:
            解析后的查询参数
        """
        result = {
            'original_query': query,
            'keywords': [],
            'wing': None,
            'room': None,
            'time_range': None,
            'importance_threshold': 0.0,
            'sort_by': 'relevance',
            'intent': 'search',
        }

        # 提取时间范围
        result['time_range'] = self._extract_time_range(query)

        # 提取空间
        result['wing'] = self._extract_wing(query)

        # 提取重要性
        result['importance_threshold'] = self._extract_importance(query)

        # 提取关键词
        result['keywords'] = self._extract_keywords(query)

        # 识别意图
        result['intent'] = self._detect_intent(query)

        return result

    def _extract_time_range(self, query: str) -> Optional[timedelta]:
        """提取时间范围"""
        for keyword, days in self.TIME_KEYWORDS.items():
            if keyword in query:
                return timedelta(days=days)

        # 尝试匹配数字+天/周/月
        patterns = [
            (r'(\d+)天', lambda x: timedelta(days=int(x))),
            (r'(\d+)周', lambda x: timedelta(weeks=int(x))),
            (r'(\d+)个月', lambda x: timedelta(days=int(x) * 30)),
        ]

        for pattern, converter in patterns:
            match = re.search(pattern, query)
            if match:
                return converter(match.group(1))

        return None

    def _extract_wing(self, query: str) -> Optional[str]:
        """提取空间"""
        for keyword, wing in self.WING_KEYWORDS.items():
            if keyword in query:
                return wing
        return None

    def _extract_importance(self, query: str) -> float:
        """提取重要性阈值"""
        for keyword, importance in self.IMPORTANCE_KEYWORDS.items():
            if keyword in query:
                return importance
        return 0.0

    def _extract_keywords(self, query: str) -> list[str]:
        """提取关键词"""
        # 移除时间词和空间词
        cleaned = query
        for keyword in list(self.TIME_KEYWORDS.keys()) + list(self.WING_KEYWORDS.keys()):
            cleaned = cleaned.replace(keyword, '')

        # 简单分词
        keywords = cleaned.split()
        return [kw for kw in keywords if len(kw) > 1]

    def _detect_intent(self, query: str) -> str:
        """检测查询意图"""
        intent_patterns = {
            'search': ['查找', '搜索', '找', '回忆', '记得', '看看'],
            'summary': ['总结', '概括', '归纳', '概述'],
            'analysis': ['分析', '统计', '看看有多少', '多少条'],
            'recommend': ['推荐', '建议', '应该', '需要'],
            'timeline': ['时间线', '什么时候', '何时', '哪天'],
            'relation': ['关联', '相关', '联系', '关系'],
        }

        for intent, patterns in intent_patterns.items():
            if any(pattern in query for pattern in patterns):
                return intent

        return 'search'


class MemoryRecommender:
    """记忆推荐引擎"""

    def __init__(self, drawers: list[Drawer] = None):
        self.drawers = drawers or []

    def recommend(self, context: str, limit: int = 5) -> list[dict]:
        """基于上下文推荐相关记忆

        Args:
            context: 当前上下文（如会话内容、任务描述）
            limit: 推荐数量

        Returns:
            推荐的记忆列表
        """
        if not self.drawers:
            return []

        # 计算上下文向量
        from ..memory.embedding import get_embedding_service
        embed_svc = get_embedding_service()
        context_vec = embed_svc.embed(context)

        if not context_vec:
            return self._fallback_recommend(limit)

        # 计算相似度
        scored = []
        for drawer in self.drawers:
            drawer_vec = drawer.metadata.get('embedding')
            if drawer_vec:
                similarity = self._cosine_similarity(context_vec, drawer_vec)
                # 综合评分：相似度 + 重要性 + 时间衰减
                score = self._calculate_score(drawer, similarity)
                scored.append((score, drawer))

        # 排序并返回top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                'id': d.id,
                'content': d.content,
                'wing': d.wing,
                'room': d.room,
                'importance': d.importance,
                'score': round(s, 3),
                'reason': self._generate_reason(d, s),
            }
            for s, d in scored[:limit]
        ]

    def _calculate_score(self, drawer: Drawer, similarity: float) -> float:
        """计算综合评分"""
        # 基础相似度权重
        base_score = similarity * 0.6

        # 重要性权重
        importance_score = (drawer.importance / 10.0) * 0.2

        # 时间衰减
        time_score = self._time_decay_score(drawer) * 0.2

        return base_score + importance_score + time_score

    def _time_decay_score(self, drawer: Drawer) -> float:
        """时间衰减评分"""
        try:
            created = datetime.fromisoformat(drawer.created_at)
            days_ago = (datetime.now() - created).days
            # 7天内满分，之后指数衰减
            if days_ago <= 7:
                return 1.0
            return max(0.1, 0.9 ** (days_ago - 7))
        except Exception:
            return 0.5

    def _cosine_similarity(self, a: list, b: list) -> float:
        """余弦相似度"""
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        a_trunc = a[:n]
        b_trunc = b[:n]
        dot = sum(x * y for x, y in zip(a_trunc, b_trunc))
        norm_a = sum(x * x for x in a_trunc) ** 0.5
        norm_b = sum(x * x for x in b_trunc) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _fallback_recommend(self, limit: int) -> list[dict]:
        """降级推荐：返回最近的重要记忆"""
        sorted_drawers = sorted(
            self.drawers,
            key=lambda d: (d.importance, d.created_at),
            reverse=True
        )
        return [
            {
                'id': d.id,
                'content': d.content,
                'wing': d.wing,
                'room': d.room,
                'importance': d.importance,
                'score': 0.5,
                'reason': '基于重要性推荐',
            }
            for d in sorted_drawers[:limit]
        ]

    def _generate_reason(self, drawer: Drawer, score: float) -> str:
        """生成推荐理由"""
        if score > 0.8:
            return '高度相关'
        elif score > 0.6:
            return '较为相关'
        elif score > 0.4:
            return '可能相关'
        else:
            return '基于重要性推荐'


def natural_language_search(query: str, drawers: list[Drawer], limit: int = 10) -> list[dict]:
    """自然语言搜索入口

    Args:
        query: 自然语言查询
        drawers: 记忆列表
        limit: 返回数量

    Returns:
        搜索结果列表
    """
    parser = NaturalLanguageQuery()
    parsed = parser.parse(query)

    # 根据意图执行不同操作
    if parsed['intent'] == 'summary':
        return _summarize_memories(drawers, parsed, limit)
    elif parsed['intent'] == 'analysis':
        return _analyze_memories(drawers, parsed)
    elif parsed['intent'] == 'timeline':
        return _timeline_query(drawers, parsed, limit)
    else:
        return _search_memories(drawers, parsed, limit)


def _search_memories(drawers: list[Drawer], parsed: dict, limit: int) -> list[dict]:
    """执行搜索"""
    from .retrieval import recall

    # 构建查询关键词
    keywords = parsed['keywords']
    query = ' '.join(keywords) if keywords else parsed['original_query']

    return recall(
        query=query,
        wing=parsed['wing'],
        limit=limit,
        min_importance=parsed['importance_threshold'],
        sort_by=parsed['sort_by'],
        drawers=drawers,
    )


def _summarize_memories(drawers: list[Drawer], parsed: dict, limit: int) -> list[dict]:
    """总结记忆"""
    filtered = drawers
    if parsed['wing']:
        filtered = [d for d in filtered if d.wing == parsed['wing']]

    # 按重要性排序
    sorted_drawers = sorted(filtered, key=lambda d: d.importance, reverse=True)

    return [
        {
            'id': d.id,
            'content': d.content,
            'wing': d.wing,
            'importance': d.importance,
            'type': 'summary_item',
        }
        for d in sorted_drawers[:limit]
    ]


def _analyze_memories(drawers: list[Drawer], parsed: dict) -> list[dict]:
    """分析记忆统计"""
    from collections import Counter

    wing_counts = Counter(d.wing for d in drawers)
    room_counts = Counter(d.room for d in drawers)

    return [{
        'type': 'analysis',
        'total': len(drawers),
        'by_wing': dict(wing_counts),
        'by_room': dict(room_counts),
        'avg_importance': sum(d.importance for d in drawers) / max(len(drawers), 1),
    }]


def _timeline_query(drawers: list[Drawer], parsed: dict, limit: int) -> list[dict]:
    """时间线查询"""
    time_range = parsed.get('time_range')
    if time_range:
        cutoff = datetime.now() - time_range
        filtered = [
            d for d in drawers
            if datetime.fromisoformat(d.created_at) >= cutoff
        ]
    else:
        filtered = drawers

    # 按时间排序
    sorted_drawers = sorted(filtered, key=lambda d: d.created_at, reverse=True)

    return [
        {
            'id': d.id,
            'content': d.content,
            'wing': d.wing,
            'created_at': d.created_at,
            'importance': d.importance,
            'type': 'timeline_item',
        }
        for d in sorted_drawers[:limit]
    ]
