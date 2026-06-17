"""盘古跨会话记忆整合 — 自动识别跨会话关联记忆并建立连接

功能：
1. 会话结束时提取关键记忆
2. 基于向量相似度发现跨会话关联
3. 自动建立 KG 实体关系
4. 构建跨会话知识链
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.cross_session")


class CrossSessionIntegrator:
    """跨会话记忆整合器"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def find_cross_session_links(
        self, new_drawers: list[Drawer], all_drawers: list[Drawer],
        min_similarity: float = 0.4, max_links: int = 10,
    ) -> list[dict]:
        """发现跨会话记忆关联

        Args:
            new_drawers: 新会话的记忆
            all_drawers: 所有历史记忆
            min_similarity: 最小相似度阈值
            max_links: 最大关联数

        Returns:
            关联列表 [{source_id, target_id, similarity, shared_tags}]
        """
        if not new_drawers or not all_drawers:
            return []

        try:
            from pangu.memory.embedding import get_embedding_service
            embed_svc = get_embedding_service()
        except Exception:
            return self._keyword_fallback(new_drawers, all_drawers, max_links)

        new_ids = {d.id for d in new_drawers}
        history = [d for d in all_drawers if d.id not in new_ids]
        if not history:
            return []

        links = []
        for new_d in new_drawers:
            new_vec = new_d.metadata.get("embedding")
            if not new_vec:
                try:
                    new_vec = embed_svc.embed(new_d.content)
                except Exception:
                    continue
            if not new_vec:
                continue

            best_sim = 0.0
            best_match = None
            for hist_d in history:
                hist_vec = hist_d.metadata.get("embedding")
                if not hist_vec:
                    continue
                try:
                    n = min(len(new_vec), len(hist_vec))
                    dot = sum(a * b for a, b in zip(new_vec[:n], hist_vec[:n]))
                    norm_a = sum(a * a for a in new_vec[:n]) ** 0.5
                    norm_b = sum(b * b for b in hist_vec[:n]) ** 0.5
                    sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
                except Exception:
                    continue
                if sim > best_sim and sim >= min_similarity:
                    best_sim = sim
                    best_match = hist_d

            if best_match:
                shared_tags = set(new_d.tags) & set(best_match.tags)
                links.append({
                    "source_id": new_d.id,
                    "target_id": best_match.id,
                    "similarity": round(best_sim, 4),
                    "shared_tags": list(shared_tags),
                    "source_content": new_d.content[:100],
                    "target_content": best_match.content[:100],
                })

        links.sort(key=lambda x: -x["similarity"])
        return links[:max_links]

    def _keyword_fallback(
        self, new_drawers: list[Drawer], all_drawers: list[Drawer],
        max_links: int,
    ) -> list[dict]:
        """关键词降级关联发现"""
        new_ids = {d.id for d in new_drawers}
        history = [d for d in all_drawers if d.id not in new_ids]
        links = []

        for new_d in new_drawers:
            new_words = set(new_d.content.lower().split())
            best_overlap = 0
            best_match = None
            for hist_d in history:
                hist_words = set(hist_d.content.lower().split())
                overlap = len(new_words & hist_words)
                if overlap > best_overlap and overlap >= 3:
                    best_overlap = overlap
                    best_match = hist_d
            if best_match:
                links.append({
                    "source_id": new_d.id,
                    "target_id": best_match.id,
                    "similarity": round(best_overlap / max(len(new_words), 1), 4),
                    "shared_tags": list(set(new_d.tags) & set(best_match.tags)),
                })

        links.sort(key=lambda x: -x["similarity"])
        return links[:max_links]

    def build_kg_links(self, links: list[dict]) -> int:
        """将跨会话关联写入知识图谱"""
        if not links:
            return 0

        try:
            from ..memory.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(self.config)
        except Exception:
            return 0

        added = 0
        for link in links:
            src_id = link["source_id"]
            tgt_id = link["target_id"]
            sim = link.get("similarity", 0.5)
            # 确保实体存在
            try:
                kg.add_entity(src_id, link.get("source_content", "")[:50], "memory")
                kg.add_entity(tgt_id, link.get("target_content", "")[:50], "memory")
                kg.add_relation(src_id, "related_to", tgt_id, confidence=sim, source="cross_session")
                added += 1
            except Exception:
                continue

        logger.info(f"Built {added} KG links from cross-session analysis")
        return added

    def on_session_end(self, session_memories: list[Drawer]) -> dict:
        """会话结束时的整合入口"""
        if not session_memories:
            return {"status": "no_memories"}

        # 加载所有记忆
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_history"}

        with open(drawers_file, encoding="utf-8") as f:
            all_drawers = [Drawer.from_dict(d) for d in json.load(f)]

        # 发现跨会话关联
        links = self.find_cross_session_links(session_memories, all_drawers)

        # 写入 KG
        kg_links = self.build_kg_links(links)

        return {
            "status": "completed",
            "session_memories": len(session_memories),
            "cross_session_links": len(links),
            "kg_links_added": kg_links,
            "top_links": links[:5],
        }

    def generate_session_summary(self, session_memories: list[Drawer]) -> dict:
        """生成会话摘要"""
        if not session_memories:
            return {"summary": "无记忆", "topics": [], "key_memories": []}

        # 提取主题
        all_tags = set()
        for d in session_memories:
            all_tags.update(d.tags)

        # 按重要性排序
        sorted_memories = sorted(session_memories, key=lambda d: d.importance, reverse=True)

        # 生成摘要
        top_memories = sorted_memories[:5]
        topics = list(all_tags)[:10]
        summary_parts = []
        for m in top_memories:
            summary_parts.append(m.content[:60])

        return {
            "summary": " | ".join(summary_parts)[:300],
            "topics": topics,
            "key_memories": [
                {"id": m.id, "content": m.content[:80], "importance": m.importance, "wing": m.wing}
                for m in top_memories
            ],
            "total_memories": len(session_memories),
            "timestamp": datetime.now().isoformat(),
        }

    def build_context_bridge(self, current_memories: list[Drawer],
                              all_drawers: list[Drawer] = None) -> dict:
        """构建上下文桥接 — 为新会话准备上下文"""
        if not current_memories:
            return {"bridge": [], "context_summary": "无上下文"}

        # 加载历史记忆
        if all_drawers is None:
            drawers_file = Path(self.config.palace_path) / "drawers.json"
            if drawers_file.exists():
                with open(drawers_file, encoding="utf-8") as f:
                    all_drawers = [Drawer.from_dict(d) for d in json.load(f)]
            else:
                all_drawers = []

        # 发现关联
        links = self.find_cross_session_links(current_memories, all_drawers, max_links=5)

        # 提取上下文
        current_topics = set()
        for d in current_memories:
            current_topics.update(d.tags)

        related_memories = []
        for link in links:
            for d in all_drawers:
                if d.id == link["target_id"]:
                    related_memories.append({
                        "id": d.id,
                        "content": d.content[:80],
                        "similarity": link["similarity"],
                        "wing": d.wing,
                    })
                    break

        context_summary = f"当前话题: {', '.join(list(current_topics)[:5])}; 关联历史记忆: {len(related_memories)} 条"

        return {
            "bridge": related_memories,
            "context_summary": context_summary,
            "current_topics": list(current_topics),
            "link_count": len(links),
        }

    def get_session_stats(self, session_memories: list[Drawer]) -> dict:
        """获取会话统计"""
        if not session_memories:
            return {"total": 0, "wings": {}, "avg_importance": 0}

        wing_counts = {}
        total_importance = 0
        for d in session_memories:
            wing_counts[d.wing] = wing_counts.get(d.wing, 0) + 1
            total_importance += d.importance

        return {
            "total": len(session_memories),
            "wings": wing_counts,
            "avg_importance": round(total_importance / len(session_memories), 2),
            "top_wing": max(wing_counts, key=wing_counts.get) if wing_counts else "none",
        }
