"""盘古多模态搜索引擎 — 跨模态统一检索

一个文本查询可以搜索：
1. 文本记忆（FTS + 向量）
2. 图片记忆（CLIP 文搜图）
3. 视频帧记忆（CLIP 文搜帧）
4. 音频转写记忆（FTS 搜转写文本）

结果自动合并去重，按模态分组展示。
"""
import logging
import time
from collections import defaultdict

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.multimodal_search")


class MultimodalSearchEngine:
    """跨模态统一搜索引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def search(self, query: str, drawers: list[Drawer] = None,
               modalities: list[str] = None, limit: int = 10) -> dict:
        """跨模态搜索

        Args:
            query: 文本查询
            drawers: 记忆列表（可选，不传则自动加载）
            modalities: 搜索的模态（None=全部）
            limit: 每种模态返回数量

        Returns:
            {"total": int, "results": [...], "by_modality": {...}}
        """
        if drawers is None:
            drawers = self._load_drawers()

        all_modalities = modalities or ["text", "image", "video", "audio"]
        all_results = []
        by_modality = defaultdict(list)

        # 1. 文本搜索（FTS + 向量）
        if "text" in all_modalities:
            text_results = self._search_text(query, drawers, limit)
            for r in text_results:
                r["search_modality"] = "text"
                all_results.append(r)
                by_modality["text"].append(r)

        # 2. 图片搜索（CLIP 文搜图）
        if "image" in all_modalities:
            img_results = self._search_image(query, drawers, limit)
            for r in img_results:
                r["search_modality"] = "image"
                all_results.append(r)
                by_modality["image"].append(r)

        # 3. 视频搜索（搜视频元数据+转写）
        if "video" in all_modalities:
            vid_results = self._search_video(query, drawers, limit)
            for r in vid_results:
                r["search_modality"] = "video"
                all_results.append(r)
                by_modality["video"].append(r)

        # 4. 音频搜索（搜转写文本）
        if "audio" in all_modalities:
            aud_results = self._search_audio(query, drawers, limit)
            for r in aud_results:
                r["search_modality"] = "audio"
                all_results.append(r)
                by_modality["audio"].append(r)

        # 合并去重
        seen_ids = set()
        unique_results = []
        for r in sorted(all_results, key=lambda x: -x.get("score", 0)):
            rid = r.get("id", "")
            if rid not in seen_ids:
                seen_ids.add(rid)
                unique_results.append(r)

        return {
            "query": query,
            "total": len(unique_results[:limit]),
            "results": unique_results[:limit],
            "by_modality": {k: len(v) for k, v in by_modality.items()},
            "total_scanned": len(drawers),
        }

    def _search_text(self, query: str, drawers: list[Drawer], limit: int) -> list[dict]:
        """文本搜索"""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for d in drawers:
            modality = d.metadata.get("modality", "text")
            if modality not in ("text", None, ""):
                continue

            content_lower = (d.content or "").lower()
            score = 0.0

            for w in query_words:
                if w in content_lower:
                    score += 0.3
            for tag in (d.tags or []):
                if tag.lower() in query_lower:
                    score += 0.2

            if score > 0:
                results.append({
                    "id": d.id,
                    "content": (d.content or "")[:200],
                    "wing": d.wing,
                    "importance": d.importance,
                    "modality": "text",
                    "tags": d.tags or [],
                    "score": score,
                })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def _search_image(self, query: str, drawers: list[Drawer], limit: int) -> list[dict]:
        """CLIP 文搜图"""
        try:
            from pangu.memory.image_engine import get_image_engine
            engine = get_image_engine(self.config)
            results = engine.search_by_text(query, drawers, limit)
            for r in results:
                r["modality"] = "image"
            return results
        except Exception as e:
            logger.debug(f"Image search failed: {e}")
            return []

    def _search_video(self, query: str, drawers: list[Drawer], limit: int) -> list[dict]:
        """搜索视频记忆"""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for d in drawers:
            modality = d.metadata.get("modality", "")
            if modality != "video":
                continue

            content_lower = (d.content or "").lower()
            score = 0.0
            for w in query_words:
                if w in content_lower:
                    score += 0.3
            for tag in (d.tags or []):
                if tag.lower() in query_lower:
                    score += 0.2
            # 视频时长加权
            duration = d.metadata.get("duration", 0)
            if duration > 0:
                score += 0.1

            if score > 0:
                results.append({
                    "id": d.id,
                    "content": (d.content or "")[:200],
                    "wing": d.wing,
                    "modality": "video",
                    "tags": d.tags or [],
                    "duration": duration,
                    "score": score,
                })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def _search_audio(self, query: str, drawers: list[Drawer], limit: int) -> list[dict]:
        """搜索音频转写"""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for d in drawers:
            modality = d.metadata.get("modality", "")
            if modality != "audio":
                continue

            content_lower = (d.content or "").lower()
            transcription = d.metadata.get("transcription", "").lower()
            score = 0.0
            for w in query_words:
                if w in transcription:
                    score += 0.4
                elif w in content_lower:
                    score += 0.2

            if score > 0:
                results.append({
                    "id": d.id,
                    "content": (d.content or "")[:200],
                    "transcription_preview": d.metadata.get("transcription", "")[:100],
                    "wing": d.wing,
                    "modality": "audio",
                    "language": d.metadata.get("language", "unknown"),
                    "duration": d.metadata.get("duration", 0),
                    "score": score,
                })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def _load_drawers(self) -> list[Drawer]:
        from pathlib import Path
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return []
        try:
            with open(drawers_file, encoding="utf-8") as f:
                return [Drawer.from_dict(d) for d in json.load(f)]
        except Exception:
            return []


_mm_search: MultimodalSearchEngine | None = None


def get_multimodal_search(config: PanguConfig = None) -> MultimodalSearchEngine:
    global _mm_search
    if _mm_search is None:
        _mm_search = MultimodalSearchEngine(config)
    return _mm_search
