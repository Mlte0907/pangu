"""盘古多模态摘要引擎 — 跨模态内容综合摘要

核心能力：
1. 单模态摘要：对图片/视频/音频/文本分别生成摘要
2. 跨模态摘要：综合多种模态内容生成统一摘要
3. 时间线摘要：按时间顺序串联多模态内容
4. 主题摘要：按主题聚合多模态内容
"""

import logging
from collections import defaultdict
from datetime import datetime

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.multimodal_summary")


class MultimodalSummaryEngine:
    """多模态摘要引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def summarize_memories(self, drawers: list[Drawer], limit: int = 50) -> dict:
        """对记忆列表生成综合摘要"""
        if not drawers:
            return {"summary": "无记忆可摘要", "modality_stats": {}}

        by_modality = defaultdict(list)
        for d in drawers:
            mod = d.metadata.get("modality", "text")
            by_modality[mod].append(d)

        sections = []
        total = len(drawers)

        # 模态统计
        modality_stats = {k: len(v) for k, v in by_modality.items()}

        # 文本摘要
        text_drawers = by_modality.get("text", [])
        if text_drawers:
            text_summary = self._summarize_text(text_drawers)
            sections.append(f"📝 文本记忆 ({len(text_drawers)}条): {text_summary}")

        # 图片摘要
        img_drawers = by_modality.get("image", [])
        if img_drawers:
            img_summary = self._summarize_images(img_drawers)
            sections.append(f"📷 图片记忆 ({len(img_drawers)}条): {img_summary}")

        # 视频摘要
        vid_drawers = by_modality.get("video", [])
        if vid_drawers:
            vid_summary = self._summarize_videos(vid_drawers)
            sections.append(f"🎬 视频记忆 ({len(vid_drawers)}条): {vid_summary}")

        # 音频摘要
        aud_drawers = by_modality.get("audio", [])
        if aud_drawers:
            aud_summary = self._summarize_audio(aud_drawers)
            sections.append(f"🎵 音频记忆 ({len(aud_drawers)}条): {aud_summary}")

        # 跨模态关联
        cross_modal = self._find_cross_modal_links(drawers)

        summary = f"共 {total} 条记忆，涵盖 {len(modality_stats)} 种模态。\n\n" + "\n".join(sections)
        if cross_modal:
            summary += f"\n\n🔗 跨模态关联: {cross_modal}"

        return {
            "summary": summary,
            "total_memories": total,
            "modality_stats": modality_stats,
            "sections": sections,
            "cross_modal_links": cross_modal,
        }

    def summarize_by_topic(self, drawers: list[Drawer], topic: str, limit: int = 20) -> dict:
        """按主题聚合摘要"""
        topic_lower = topic.lower()
        matched = []
        for d in drawers:
            content = (d.content or "").lower()
            tags = [t.lower() for t in (d.tags or [])]
            if topic_lower in content or any(topic_lower in t for t in tags):
                matched.append(d)

        if not matched:
            return {"topic": topic, "summary": f"未找到与「{topic}」相关的记忆", "count": 0}

        by_modality = defaultdict(list)
        for d in matched[:limit]:
            mod = d.metadata.get("modality", "text")
            by_modality[mod].append(d)

        parts = [f"主题「{topic}」共 {len(matched)} 条记忆："]
        for mod, items in by_modality.items():
            mod_label = {"text": "📝文本", "image": "📷图片", "video": "🎬视频", "audio": "🎵音频"}.get(mod, mod)
            previews = [f"{d.content[:50]}..." for d in items[:3]]
            parts.append(f"  {mod_label} ({len(items)}条): {'; '.join(previews)}")

        return {
            "topic": topic,
            "summary": "\n".join(parts),
            "count": len(matched),
            "by_modality": {k: len(v) for k, v in by_modality.items()},
        }

    def summarize_timeline(self, drawers: list[Drawer], days: int = 7) -> dict:
        """按时间线生成摘要"""
        now = datetime.now()
        recent = []
        for d in drawers:
            try:
                dt = datetime.fromisoformat(d.created_at)
                if (now - dt).days <= days:
                    recent.append(d)
            except Exception:
                continue

        if not recent:
            return {"days": days, "summary": f"最近 {days} 天无新记忆", "count": 0}

        recent.sort(key=lambda d: d.created_at, reverse=True)
        by_date = defaultdict(list)
        for d in recent:
            try:
                date_str = datetime.fromisoformat(d.created_at).strftime("%m-%d")
                by_date[date_str].append(d)
            except Exception:
                by_date["未知"].append(d)

        parts = [f"最近 {days} 天共 {len(recent)} 条新记忆："]
        for date, items in sorted(by_date.items(), reverse=True)[:7]:
            mod_counts = defaultdict(int)
            for d in items:
                mod_counts[d.metadata.get("modality", "text")] += 1
            mod_str = ", ".join(f"{k}:{v}" for k, v in mod_counts.items())
            preview = items[0].content[:40] if items else ""
            parts.append(f"  {date}: {len(items)}条 [{mod_str}] {preview}...")

        return {
            "days": days,
            "count": len(recent),
            "summary": "\n".join(parts),
            "daily_breakdown": {k: len(v) for k, v in by_date.items()},
        }

    def _summarize_text(self, drawers: list[Drawer]) -> str:
        if not drawers:
            return "无文本记忆"
        tags = set()
        for d in drawers:
            tags.update(d.tags or [])
        wings = set(d.wing for d in drawers)
        preview = drawers[0].content[:60] if drawers else ""
        return f"涵盖 {len(wings)} 个领域, {len(tags)} 个标签. 例: {preview}..."

    def _summarize_images(self, drawers: list[Drawer]) -> str:
        if not drawers:
            return "无图片记忆"
        formats = set(d.metadata.get("file_type", "") for d in drawers)
        colors = set()
        for d in drawers:
            colors.update(d.metadata.get("dominant_colors", []))
        return f"{len(drawers)}张图片, 格式: {', '.join(formats)}, 主色调: {', '.join(list(colors)[:5])}"

    def _summarize_videos(self, drawers: list[Drawer]) -> str:
        if not drawers:
            return "无视频记忆"
        total_duration = sum(d.metadata.get("duration", 0) for d in drawers)
        codecs = set(d.metadata.get("video_codec", "") for d in drawers if d.metadata.get("video_codec"))
        return f"{len(drawers)}个视频, 总时长: {total_duration / 60:.1f}分钟, 编码: {', '.join(codecs)}"

    def _summarize_audio(self, drawers: list[Drawer]) -> str:
        if not drawers:
            return "无音频记忆"
        langs = set(d.metadata.get("language", "unknown") for d in drawers)
        total_duration = sum(d.metadata.get("duration", 0) for d in drawers)
        has_transcription = sum(1 for d in drawers if d.metadata.get("transcription"))
        return f"{len(drawers)}段音频, 总时长: {total_duration / 60:.1f}分钟, 语言: {', '.join(langs)}, 已转写: {has_transcription}段"

    def _find_cross_modal_links(self, drawers: list[Drawer]) -> str:
        """发现跨模态关联"""
        mod_count = set(d.metadata.get("modality", "text") for d in drawers)
        if len(mod_count) <= 1:
            return ""
        mod_labels = {"text": "文本", "image": "图片", "video": "视频", "audio": "音频"}
        labels = [mod_labels.get(m, m) for m in mod_count]
        return f"存在 {len(labels)} 种模态内容 ({', '.join(labels)})，可进行跨模态关联分析"


_summary: MultimodalSummaryEngine | None = None


def get_multimodal_summary(config: PanguConfig = None) -> MultimodalSummaryEngine:
    global _summary
    if _summary is None:
        _summary = MultimodalSummaryEngine(config)
    return _summary
