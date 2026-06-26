"""盘古记忆蒸馏 — 从原始记忆中提炼精炼知识

核心能力：
1. 知识蒸馏：从多条相关记忆中蒸馏出核心知识
2. 关键词提取：自动提取记忆中的关键词和主题
3. 摘要生成：将长文本压缩为精炼摘要
4. 知识结晶：将散乱记忆转化为结构化知识
5. 蒸馏追踪：追踪蒸馏过程和信息保留率
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.distillation")


@dataclass
class DistilledKnowledge:
    """蒸馏后的知识"""

    id: str
    original_ids: list[str]
    summary: str
    keywords: list[str]
    wing: str
    importance: float
    confidence: float
    tokens_saved: int


@dataclass
class DistillationReport:
    """蒸馏报告"""

    input_count: int
    output_count: int
    tokens_saved: int
    avg_confidence: float
    distilled: list[DistilledKnowledge]


class DistillationEngine:
    """记忆蒸馏引擎"""

    STOP_WORDS = {
        "的",
        "了",
        "是",
        "在",
        "和",
        "有",
        "这",
        "个",
        "就",
        "不",
        "也",
        "都",
        "而",
        "及",
        "与",
        "或",
        "但",
        "如果",
        "可以",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "it",
        "that",
    }

    def __init__(self, config=None):
        self.config = config
        self._distillation_history: list[dict] = []

    def extract_keywords(self, text: str, top_k: int = 5) -> list[str]:
        """提取关键词"""
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text)
        word_freq: dict[str, int] = {}
        for w in words:
            wl = w.lower()
            if wl not in self.STOP_WORDS and len(wl) >= 2:
                word_freq[wl] = word_freq.get(wl, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:top_k]]

    def summarize(self, texts: list[str], max_len: int = 100) -> str:
        """从多条文本生成摘要"""
        if not texts:
            return ""
        if len(texts) == 1:
            return texts[0][:max_len]

        # 提取高频词
        all_words: dict[str, int] = {}
        for text in texts:
            for word in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text):
                wl = word.lower()
                if wl not in self.STOP_WORDS:
                    all_words[wl] = all_words.get(wl, 0) + 1

        top_words = sorted(all_words.items(), key=lambda x: -x[1])[:8]
        summary_parts = [w for w, _ in top_words]

        prefix = f"[蒸馏自{len(texts)}条记忆]"
        summary = f"{prefix} 核心知识: {'、'.join(summary_parts)}"

        # 补充最相关的原文片段
        for text in texts:
            for w, _ in top_words[:3]:
                if w in text.lower():
                    summary += f"。{text[:60]}"
                    break

        return summary[:max_len]

    def distill_group(self, drawers: list) -> DistilledKnowledge:
        """蒸馏一组相关记忆"""
        contents = [d.content for d in drawers]
        all_tags = set()
        for d in drawers:
            all_tags.update(d.tags)

        keywords = []
        for content in contents:
            keywords.extend(self.extract_keywords(content, 3))

        keyword_freq: dict[str, int] = {}
        for k in keywords:
            keyword_freq[k] = keyword_freq.get(k, 0) + 1
        top_keywords = sorted(keyword_freq.items(), key=lambda x: -x[1])[:5]

        summary = self.summarize(contents)
        total_tokens = sum(len(c) * 1.5 for c in contents)
        saved = int(total_tokens - len(summary) * 1.5)

        max_imp = max(d.importance for d in drawers)
        avg_tags = sum(len(d.tags) for d in drawers) / len(drawers)

        return DistilledKnowledge(
            id=f"distilled_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            original_ids=[d.id for d in drawers],
            summary=summary,
            keywords=[w for w, _ in top_keywords],
            wing=drawers[0].wing if drawers else "unknown",
            importance=min(5.0, max_imp + 0.3),
            confidence=min(0.95, 0.5 + len(drawers) * 0.08 + avg_tags * 0.02),
            tokens_saved=saved,
        )

    def distill_all(self, drawers: list, min_group_size: int = 2) -> DistillationReport:
        """蒸馏所有记忆"""
        tag_groups: dict[str, list] = {}
        for d in drawers:
            for tag in d.tags:
                tag_groups.setdefault(tag, []).append(d)

        distilled = []
        seen_ids: set[str] = set()

        for tag, group in sorted(tag_groups.items(), key=lambda x: -len(x[1])):
            if len(group) < min_group_size:
                continue

            unique = [d for d in group if d.id not in seen_ids]
            if len(unique) < min_group_size:
                continue

            dk = self.distill_group(unique[:10])
            distilled.append(dk)
            seen_ids.update(d.id for d in unique)

        total_input = len(drawers)
        total_output = len(distilled)
        total_saved = sum(dk.tokens_saved for dk in distilled)
        avg_conf = sum(dk.confidence for dk in distilled) / max(len(distilled), 1)

        report = DistillationReport(
            input_count=total_input,
            output_count=total_output,
            tokens_saved=total_saved,
            avg_confidence=round(avg_conf, 3),
            distilled=distilled,
        )

        self._distillation_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "input": total_input,
                "output": total_output,
                "saved": total_saved,
            }
        )

        return report

    def distill_by_wing(self, drawers: list) -> dict:
        """按 Wing 蒸馏"""
        wing_groups: dict[str, list] = {}
        for d in drawers:
            wing_groups.setdefault(d.wing, []).append(d)

        results = {}
        for wing, group in wing_groups.items():
            if len(group) >= 2:
                dk = self.distill_group(group)
                results[wing] = {
                    "summary": dk.summary,
                    "keywords": dk.keywords,
                    "confidence": dk.confidence,
                    "original_count": len(group),
                }

        return results

    def get_distillation_stats(self) -> dict:
        """获取蒸馏统计"""
        if not self._distillation_history:
            return {"total_runs": 0}

        total_saved = sum(h["saved"] for h in self._distillation_history)
        return {
            "total_runs": len(self._distillation_history),
            "total_tokens_saved": total_saved,
            "latest": self._distillation_history[-1],
        }


_distiller: DistillationEngine | None = None


def get_distiller(config=None) -> DistillationEngine:
    """获取全局蒸馏引擎实例"""
    global _distiller
    if _distiller is None:
        _distiller = DistillationEngine(config)
    return _distiller
