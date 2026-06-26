"""盘古图片记忆引擎 — CLIP 嵌入 + 图片分析 + 跨模态搜索

核心能力：
1. 图片嵌入：用 CLIP 将图片转为 512 维向量
2. 图片分析：颜色直方图、尺寸、格式、EXIF
3. 图片描述：基于 CLIP 的零样本分类
4. 跨模态搜索：文本搜图 / 图搜图
5. 图片记忆存储：元数据+向量+缩略图摘要
"""

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.image_engine")

# CLIP 零样本标签
CLIP_CATEGORIES = [
    "photo",
    "screenshot",
    "diagram",
    "chart",
    "code",
    "document",
    "person",
    "landscape",
    "object",
    "logo",
    "icon",
    "text_image",
    "architecture",
    "interface",
    "poster",
    "handwriting",
]


class ImageMemoryEngine:
    """图片记忆引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._clip_model = None
        self._clip_processor = None

    @property
    def clip(self):
        if self._clip_model is None:
            try:
                import os

                os.environ["HF_HUB_OFFLINE"] = "1"
                from transformers import CLIPModel, CLIPProcessor

                self._clip_model = CLIPModel.from_pretrained(
                    "openai/clip-vit-base-patch32",
                    local_files_only=True,
                )
                self._clip_processor = CLIPProcessor.from_pretrained(
                    "openai/clip-vit-base-patch32",
                    local_files_only=True,
                )
                logger.info("CLIP model loaded")
            except Exception as e:
                logger.debug(f"CLIP unavailable (using fallback): {e}")
                self._clip_model = False
        return self._clip_model if self._clip_model is not False else None

    def embed_image(self, image_path: str) -> dict:
        """将图片转为 512 维向量"""
        path = Path(image_path).expanduser()
        if not path.exists():
            return {"error": f"文件不存在: {image_path}"}

        img = Image.open(str(path)).convert("RGB")
        analysis = self._analyze_image(img, path)

        if self.clip:
            try:
                import torch

                inputs = self._clip_processor(images=img, text=["a photo"], return_tensors="pt")
                with torch.no_grad():
                    outputs = self.clip(**inputs)
                vector = outputs.image_embeds[0].cpu().numpy().tolist()
                analysis["embedding"] = vector
                analysis["embedding_dim"] = len(vector)
                analysis["embedding_model"] = "clip-vit-base-patch32"
            except Exception as e:
                logger.warning(f"CLIP embed failed: {e}")
                analysis["embedding"] = self._fallback_embedding(img)
                analysis["embedding_dim"] = len(analysis["embedding"])
                analysis["embedding_model"] = "fallback-color-histogram"
        else:
            analysis["embedding"] = self._fallback_embedding(img)
            analysis["embedding_dim"] = len(analysis["embedding"])
            analysis["embedding_model"] = "fallback-color-histogram"

        return analysis

    def embed_text(self, text: str) -> list[float]:
        """将文本转为 CLIP 向量（跨模态搜索用）"""
        if not self.clip:
            return []
        try:
            import torch

            dummy_img = Image.new("RGB", (224, 224), (128, 128, 128))
            inputs = self._clip_processor(text=[text], images=dummy_img, return_tensors="pt")
            with torch.no_grad():
                outputs = self.clip(**inputs)
            return outputs.text_embeds[0].cpu().numpy().tolist()
        except Exception as e:
            logger.warning(f"CLIP text embed failed: {e}")
            return []
        try:
            inputs = self._clip_processor(text=[text], return_tensors="pt", padding=True)
            with __import__("torch").no_grad():
                features = self.clip.get_text_features(**inputs)
            return features[0].cpu().numpy().tolist()
        except Exception as e:
            logger.warning(f"CLIP text embed failed: {e}")
            return []

    def classify_image(self, image_path: str) -> dict:
        """CLIP 零样本分类"""
        if not self.clip:
            return {"error": "CLIP model not available"}

        path = Path(image_path).expanduser()
        img = Image.open(str(path)).convert("RGB")

        try:
            import torch

            inputs = self._clip_processor(text=CLIP_CATEGORIES, images=img, return_tensors="pt", padding=True)
            with torch.no_grad():
                outputs = self.clip(**inputs)
            logits = outputs.logits_per_image[0]
            probs = logits.softmax(dim=-1).cpu().numpy()

            results = []
            for i in np.argsort(probs)[::-1][:5]:
                results.append(
                    {
                        "category": CLIP_CATEGORIES[i],
                        "score": float(probs[i]),
                    }
                )

            return {
                "image": str(path),
                "top_categories": results,
                "predicted": results[0]["category"] if results else "unknown",
                "confidence": results[0]["score"] if results else 0,
            }
        except Exception as e:
            return {"error": str(e)}

    def _analyze_image(self, img: Image.Image, path: Path) -> dict:
        """分析图片基础属性"""
        stat = path.stat()
        w, h = img.size
        mode = img.mode
        format_name = img.format or path.suffix.upper().lstrip(".")

        # 颜色直方图
        colors = self._dominant_colors(img)

        # 方位比
        aspect = round(w / h, 2) if h > 0 else 1.0

        # 描述生成
        desc_parts = [f"[图片] {path.name}"]
        desc_parts.append(f"{w}x{h}px, {mode}, {format_name}")
        desc_parts.append(f"{stat.st_size / 1024:.1f}KB")
        if colors:
            desc_parts.append(f"主色调: {', '.join(colors[:3])}")

        return {
            "modality": "image",
            "file_name": path.name,
            "file_size": stat.st_size,
            "file_type": path.suffix.lstrip("."),
            "image_width": w,
            "image_height": h,
            "image_mode": mode,
            "image_format": format_name,
            "aspect_ratio": aspect,
            "dominant_colors": colors,
            "content": " ".join(desc_parts),
            "tags": ["image", path.suffix.lstrip(".").lower()],
        }

    def _dominant_colors(self, img: Image.Image, n_colors: int = 5) -> list[str]:
        """提取主色调"""
        try:
            small = img.resize((64, 64)).convert("RGB")
            pixels = np.array(small).reshape(-1, 3)

            # 简单 K-means 近似
            indices = np.random.choice(len(pixels), min(200, len(pixels)), replace=False)
            sampled = pixels[indices].astype(float)

            # 量化到 8 个级别
            quantized = (sampled // 32).astype(int)
            unique, counts = np.unique(quantized, axis=0, return_counts=True)
            top = unique[np.argsort(counts)[::-1][:n_colors]]

            color_names = []
            for r, g, b in top:
                name = self._rgb_to_name(r * 32, g * 32, b * 32)
                color_names.append(name)

            return color_names
        except Exception:
            return []

    @staticmethod
    def _rgb_to_name(r: int, g: int, b: int) -> str:
        """RGB 转颜色名"""
        colors = {
            "红色": (180, 30, 30),
            "蓝色": (30, 30, 180),
            "绿色": (30, 150, 30),
            "黄色": (200, 200, 30),
            "白色": (220, 220, 220),
            "黑色": (30, 30, 30),
            "灰色": (128, 128, 128),
            "橙色": (220, 120, 30),
            "紫色": (120, 30, 180),
            "青色": (30, 180, 180),
            "粉色": (220, 120, 160),
        }
        best_name, best_dist = "未知", float("inf")
        for name, (cr, cg, cb) in colors.items():
            dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name

    @staticmethod
    def _fallback_embedding(img: Image.Image) -> list[float]:
        """无 CLIP 时的降级嵌入：颜色直方图"""
        small = img.resize((32, 32)).convert("RGB")
        arr = np.array(small).flatten().astype("float32")
        arr = arr / (np.linalg.norm(arr) + 1e-8)
        return arr.tolist()

    def search_by_image(self, image_path: str, drawers: list[Drawer], limit: int = 5) -> list[dict]:
        """以图搜图"""
        query = self.embed_image(image_path)
        query_vec = query.get("embedding", [])
        if not query_vec:
            return []

        scored = []
        for d in drawers:
            stored_vec = d.metadata.get("embedding")
            if not stored_vec:
                continue
            try:
                n = min(len(query_vec), len(stored_vec))
                dot = sum(a * b for a, b in zip(query_vec[:n], stored_vec[:n], strict=False))
                norm_a = sum(a * a for a in query_vec[:n]) ** 0.5
                norm_b = sum(b * b for b in stored_vec[:n]) ** 0.5
                sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0
                if sim > 0.3:
                    scored.append({"id": d.id, "content": d.content[:100], "similarity": round(sim, 4)})
            except Exception:
                continue

        scored.sort(key=lambda x: -x["similarity"])
        return scored[:limit]

    def search_by_text(self, query: str, drawers: list[Drawer], limit: int = 5) -> list[dict]:
        """以文搜图"""
        query_vec = self.embed_text(query)
        if not query_vec:
            return []

        scored = []
        for d in drawers:
            stored_vec = d.metadata.get("embedding")
            if not stored_vec:
                continue
            try:
                n = min(len(query_vec), len(stored_vec))
                dot = sum(a * b for a, b in zip(query_vec[:n], stored_vec[:n], strict=False))
                norm_a = sum(a * a for a in query_vec[:n]) ** 0.5
                norm_b = sum(b * b for b in stored_vec[:n]) ** 0.5
                sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0
                if sim > 0.15:
                    scored.append({"id": d.id, "content": d.content[:100], "similarity": round(sim, 4)})
            except Exception:
                continue

        scored.sort(key=lambda x: -x["similarity"])
        return scored[:limit]


_engine: ImageMemoryEngine | None = None


def get_image_engine(config: PanguConfig = None) -> ImageMemoryEngine:
    global _engine
    if _engine is None:
        _engine = ImageMemoryEngine(config)
    return _engine
