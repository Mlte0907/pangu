"""盘古上下文自动注入 — Agent 连接时自动推送相关记忆

核心能力：
1. 上下文感知：分析当前对话/任务上下文
2. 自动推荐：基于上下文搜索最相关的 5 条记忆
3. 推送通知：通过 WebSocket 自动推送给 Agent
4. 记录注入：记录注入历史，优化后续推荐
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.context_injector")


class ContextInjector:
    """上下文自动注入引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._injection_history: list[dict] = []
        self._max_history = 500

    def auto_inject(self, context: str = "", drawers: list[Drawer] = None, limit: int = 5) -> dict:
        """基于上下文自动注入相关记忆"""
        if not context and not drawers:
            return {"injected": 0, "suggestions": [], "reason": "no context"}

        if drawers is None:
            drawers = self._load_drawers()

        query_words = set(self._extract_keywords(context)) if context else set()
        suggestions = []

        for d in drawers:
            score = 0.0
            content_lower = (d.content or "").lower()

            # 关键词匹配
            for w in query_words:
                if w in content_lower:
                    score += 0.3

            # 标签匹配
            for tag in d.tags or []:
                if tag.lower() in context.lower():
                    score += 0.2

            # 重要性加成
            score += (d.importance or 0) * 0.1

            # 时效性加成（7天内优先）
            try:
                created = datetime.fromisoformat(d.created_at)
                days_old = (datetime.now() - created).total_seconds() / 86400
                if days_old < 7:
                    score += 0.2
                elif days_old < 30:
                    score += 0.1
            except Exception:
                pass

            if score > 0.15:
                suggestions.append(
                    {
                        "id": d.id,
                        "content": (d.content or "")[:100],
                        "wing": d.wing,
                        "importance": d.importance,
                        "score": round(score, 3),
                        "created_at": d.created_at,
                    }
                )

        suggestions.sort(key=lambda x: -x["score"])
        top = suggestions[:limit]

        # 解密
        self._decrypt_suggestions(top)

        # 记录注入
        injection = {
            "timestamp": datetime.now().isoformat(),
            "context": context[:200],
            "injected_count": len(top),
            "total_matches": len(suggestions),
        }
        self._injection_history.append(injection)
        if len(self._injection_history) > self._max_history:
            self._injection_history = self._injection_history[-self._max_history :]

        return {
            "injected": len(top),
            "suggestions": top,
            "total_matches": len(suggestions),
            "context_preview": context[:100],
        }

    def get_injection_stats(self) -> dict:
        """获取注入统计"""
        return {
            "total_injections": len(self._injection_history),
            "last_injection": self._injection_history[-1] if self._injection_history else None,
        }

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """提取关键词"""
        import re

        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        en_words = re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
        return cn_words + en_words

    def _decrypt_suggestions(self, suggestions: list[dict]):
        """解密建议内容"""
        try:
            import importlib

            encryption_mod = importlib.import_module("pangu.memory.encryption")
            decrypt = encryption_mod.decrypt
            for s in suggestions:
                c = s.get("content", "")
                if c and c.startswith("gAAAAAB"):
                    try:
                        s["content"] = decrypt(c)
                    except Exception:
                        pass
        except Exception:
            pass

    def _load_drawers(self) -> list[Drawer]:
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return []
        try:
            with open(drawers_file, encoding="utf-8") as f:
                return [Drawer.from_dict(d) for d in json.load(f)]
        except Exception:
            return []


_injector: ContextInjector | None = None


def get_context_injector(config: PanguConfig = None) -> ContextInjector:
    global _injector
    if _injector is None:
        _injector = ContextInjector(config)
    return _injector
