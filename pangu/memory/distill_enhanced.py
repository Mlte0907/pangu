"""盘古知识蒸馏增强版 — 自动关联 + 因果链提取 + 知识卡片

从伏羲移植：将多条记忆提炼为结构化知识卡片，自动建立语义关联，
提取因果链（因为X所以Y），主动关联已有知识卡片。

纯大脑能力：不做执行，只做知识提炼和结构化。
"""

import json
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger("pangu.memory.distill_enhanced")


class DistillationTower:
    """知识蒸馏增强版 — 自动关联 + 因果链提取

    知识卡片格式: 概念 → 原理 → 应用 → 关联 → 因果链 → 证据数 → 置信度 → 知识空白
    """

    def __init__(self, config=None):
        self.config = config
        self._llm_engine = None
        self._cards: dict[str, dict] = {}  # 已生成的知识卡片

    @property
    def llm_engine(self):
        if self._llm_engine is None:
            try:
                from ..core.llm import LLMEngine
                self._llm_engine = LLMEngine(self.config)
            except ImportError:
                self._llm_engine = None
        return self._llm_engine

    def distill(
        self,
        texts: list[str],
        source_ids: list[str] = None,
        existing_cards: list[dict[str, Any]] = None,
    ) -> dict:
        """从多条记忆中蒸馏出一个知识卡片

        Args:
            texts: 记忆文本列表
            source_ids: 对应的记忆 ID 列表
            existing_cards: 已有知识卡片（用于关联）

        Returns:
            知识卡片 dict
        """
        if source_ids is None:
            source_ids = []

        combined = "\n\n".join(f"[记忆{i + 1}] {t[:200]}" for i, t in enumerate(texts))

        # 已有知识卡片摘要
        existing_context = ""
        if existing_cards:
            existing_context = "\n\n已有知识卡片参考:\n"
            for card in existing_cards[:5]:
                concept = card.get("knowledge_card", {}).get("concept", card.get("concept", "未知"))
                existing_context += f"- {concept}\n"

        prompt = self._build_prompt(combined, existing_context, len(texts))

        try:
            if self.llm_engine:
                resp = self.llm_engine.chat([{"role": "user", "content": prompt}])
                if resp and resp.content:
                    return self._parse_response(resp.content, source_ids, texts)
        except Exception as e:
            logger.debug(f"Distillation LLM failed: {e}")

        # 降级：基于关键词提取
        return self._fallback_distill(texts, source_ids)

    def _build_prompt(self, combined: str, existing_context: str, evidence_count: int) -> str:
        return f"""你是一个知识整理助手。请根据以下记忆片段，生成一个结构化知识卡片。

{combined}
{existing_context}

请生成 JSON 格式的知识卡片，必须包含以下字段：
{{
  "concept": "核心概念（简洁的一句话，15字以内）",
  "principle": "基本原理或发现（50字以内）",
  "applications": ["应用场景1", "应用场景2"],
  "relations": ["关联的概念或记忆主题1", "关联的概念或记忆主题2", "关联的概念或记忆主题3"],
  "causal_links": ["因为X，所以Y", "Z导致W"],
  "evidence_count": {evidence_count},
  "confidence": 0.7-0.95之间的数值,
  "knowledge_gaps": ["尚不明确的知识点1", "尚不明确的知识点2"]
}}

只输出 JSON，不要多余内容。"""

    def _parse_response(self, content: str, source_ids: list[str], texts: list[str]) -> dict:
        """解析 LLM 返回的知识卡片"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r'\{[^{}]*"concept"[^{}]*\}', content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    return self._fallback_distill(texts, source_ids)
            else:
                return self._fallback_distill(texts, source_ids)

        card = {
            "knowledge_card": {
                "concept": data.get("concept", "未命名概念"),
                "principle": data.get("principle", ""),
                "applications": data.get("applications", []),
                "relations": data.get("relations", []),
                "causal_links": data.get("causal_links", []),
                "evidence_count": data.get("evidence_count", len(texts)),
                "confidence": data.get("confidence", 0.7),
                "knowledge_gaps": data.get("knowledge_gaps", []),
            },
            "source_ids": source_ids,
            "distilled_at": datetime.now().isoformat(),
            "source_texts": [t[:100] for t in texts],
        }

        # 缓存卡片
        concept = data.get("concept", "未命名概念")
        self._cards[concept] = card

        return card

    def _fallback_distill(self, texts: list[str], source_ids: list[str]) -> dict:
        """降级蒸馏：基于关键词提取"""
        # 提取高频关键词
        all_words = []
        for text in texts:
            words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text.lower())
            all_words.extend(words)

        from collections import Counter
        word_counts = Counter(all_words)
        top_words = [w for w, _ in word_counts.most_common(5)]

        # 提取可能的因果链
        causal_patterns = re.findall(
            r'(?:因为|由于|所以|因此|导致|造成|引起|从而|进而|使得)([^，。；]{5,30})',
            " ".join(texts)
        )

        return {
            "knowledge_card": {
                "concept": top_words[0] if top_words else "未命名概念",
                "principle": f"基于 {len(texts)} 条记忆的自动提炼",
                "applications": top_words[1:3] if len(top_words) > 1 else [],
                "relations": top_words[:2] if top_words else [],
                "causal_links": list(set(causal_patterns))[:3],
                "evidence_count": len(texts),
                "confidence": 0.5,
                "knowledge_gaps": ["需要更多证据", "LLM 精炼不可用，使用关键词提取"],
            },
            "source_ids": source_ids,
            "distilled_at": datetime.now().isoformat(),
            "source_texts": [t[:100] for t in texts],
            "method": "fallback_keyword",
        }

    def get_causal_chains(self) -> list[dict]:
        """提取所有已蒸馏知识卡片中的因果链"""
        chains = []
        for concept, card in self._cards.items():
            for link in card.get("knowledge_card", {}).get("causal_links", []):
                chains.append({
                    "concept": concept,
                    "causal_link": link,
                    "confidence": card.get("knowledge_card", {}).get("confidence", 0.5),
                })
        return chains

    def get_knowledge_graph(self) -> dict:
        """获取知识关联图"""
        nodes = []
        edges = []
        for concept, card in self._cards.items():
            kc = card.get("knowledge_card", {})
            nodes.append({
                "id": concept,
                "confidence": kc.get("confidence", 0.5),
                "evidence_count": kc.get("evidence_count", 0),
            })
            for rel in kc.get("relations", []):
                edges.append({"source": concept, "target": rel, "type": "related"})

        return {"nodes": nodes, "edges": edges}

    def stats(self) -> dict:
        """蒸馏统计"""
        return {
            "total_cards": len(self._cards),
            "concepts": list(self._cards.keys()),
            "total_causal_chains": len(self.get_causal_chains()),
        }
