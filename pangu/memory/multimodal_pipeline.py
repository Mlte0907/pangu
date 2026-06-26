"""盘古多模态输入管道 v3.3 — 图片/文件/URL/音频内容提取并存入记忆

支持：
1. 图片：PIL 尺寸+格式，可选 LLM 描述
2. 文件：PDF 文本提取，代码文件预览，通用元数据
3. URL：网页抓取+内容提取
4. 音频：元数据提取（时长/格式）
5. 自动入库：提取后自动存入 Palace 记忆
"""

import logging
import re
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.multimodal_pipeline")


class MultimodalPipeline:
    """多模态输入管道"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._text_extensions = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".xml",
            ".html",
            ".css",
            ".sql",
            ".sh",
            ".bash",
            ".csv",
            ".log",
            ".ini",
            ".cfg",
        }
        self._image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
        self._doc_extensions = {".pdf"}
        self._audio_extensions = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

    def ingest_file(
        self,
        file_path: str,
        wing: str = "default",
        description: str = "",
        tags: list[str] = None,
        auto_store: bool = True,
    ) -> dict:
        """从文件提取多模态记忆并入库"""
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        if not path.is_file():
            return {"error": f"不是文件: {file_path}"}

        ext = path.suffix.lower()
        result = {"file": str(path), "modality": "unknown"}

        if ext in self._text_extensions:
            result = self._extract_text(path, description, tags)
        elif ext in self._image_extensions:
            result = self._extract_image(path, description, tags)
        elif ext in self._doc_extensions:
            result = self._extract_pdf(path, description, tags)
        elif ext in self._audio_extensions:
            result = self._extract_audio(path, description, tags)
        else:
            result = self._extract_generic(path, description, tags)

        if auto_store and "content" in result and not result.get("error"):
            drawer = self._store_memory(result, wing)
            result["stored"] = True
            result["memory_id"] = drawer.id

        result["file"] = str(path)
        return result

    def ingest_url(
        self, url: str, wing: str = "default", description: str = "", tags: list[str] = None, auto_store: bool = True
    ) -> dict:
        """从 URL 抓取网页内容并存入记忆"""
        import httpx

        try:
            resp = httpx.get(
                url, timeout=15, follow_redirects=True, headers={"User-Agent": "Pangu/3.3 Memory Collector"}
            )
            content_type = resp.headers.get("content-type", "")

            if "html" in content_type or "text" in content_type:
                text = self._extract_text_from_html(resp.text)
                result = {
                    "modality": "url",
                    "url": url,
                    "title": self._extract_title(resp.text),
                    "content": text[:2000],
                    "content_length": len(resp.text),
                    "content_type": content_type,
                    "tags": (tags or []) + ["url", "web"],
                }
            elif "json" in content_type:
                result = {
                    "modality": "url",
                    "url": url,
                    "content": resp.text[:2000],
                    "content_type": content_type,
                    "tags": (tags or []) + ["url", "api"],
                }
            else:
                result = {
                    "modality": "url",
                    "url": url,
                    "content": f"[{content_type}] {url} ({len(resp.text)} bytes)",
                    "content_type": content_type,
                    "tags": (tags or []) + ["url"],
                }

            if description:
                result["content"] = f"{description}\n\n{result['content']}"

            if auto_store and result.get("content"):
                drawer = self._store_memory(result, wing)
                result["stored"] = True
                result["memory_id"] = drawer.id

            return result

        except Exception as e:
            return {"error": f"URL抓取失败: {e}", "url": url}

    def ingest_text(
        self,
        text: str,
        wing: str = "default",
        description: str = "",
        tags: list[str] = None,
        modality: str = "text",
        auto_store: bool = True,
    ) -> dict:
        """直接存入文本记忆"""
        content = f"{description}\n\n{text}" if description else text
        result = {
            "modality": modality,
            "content": content[:5000],
            "content_length": len(text),
            "tags": tags or [],
        }

        if auto_store:
            drawer = self._store_memory(result, wing)
            result["stored"] = True
            result["memory_id"] = drawer.id

        return result

    def _extract_text(self, path: Path, description: str, tags: list[str]) -> dict:
        """提取文本文件内容"""
        try:
            import chardet

            raw = path.read_bytes()
            detected = chardet.detect(raw)
            encoding = detected.get("encoding", "utf-8") or "utf-8"
            content = raw.decode(encoding, errors="ignore")
        except ImportError:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = path.read_text(encoding="utf-8", errors="ignore")

        # 对大文件截取
        if len(content) > 10000:
            content = content[:10000] + f"\n...[截断，原始 {len(content)} 字符]"

        return {
            "modality": "file",
            "file_type": "text",
            "content": (f"{description}\n\n{content}" if description else content)[:5000],
            "content_length": len(content),
            "tags": (tags or []) + ["text_file"],
            "file_name": path.name,
            "file_size": path.stat().st_size,
        }

    def _extract_image(self, path: Path, description: str, tags: list[str]) -> dict:
        """提取图片信息"""
        width, height = 0, 0
        try:
            from PIL import Image

            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            pass

        stat = path.stat()
        desc = description or f"图片 {path.name} ({width}x{height}, {stat.st_size / 1024:.1f}KB)"

        return {
            "modality": "image",
            "content": desc,
            "tags": (tags or []) + ["image", path.suffix.lstrip(".")],
            "file_name": path.name,
            "file_size": stat.st_size,
            "image_width": width,
            "image_height": height,
        }

    def _extract_pdf(self, path: Path, description: str, tags: list[str]) -> dict:
        """提取 PDF 文本"""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            texts = []
            for page in reader.pages[:20]:
                text = page.extract_text()
                if text:
                    texts.append(text.strip())
            content = "\n\n".join(texts)
            if len(content) > 10000:
                content = content[:10000] + f"\n...[截断，原始 {len(content)} 字符]"

            desc = description or f"PDF文档 {path.name} ({len(reader.pages)}页)"
            if content:
                desc = f"{desc}\n\n{content}"

            return {
                "modality": "file",
                "file_type": "pdf",
                "content": desc[:5000],
                "content_length": len(content),
                "tags": (tags or []) + ["pdf"],
                "file_name": path.name,
                "file_size": path.stat().st_size,
                "pdf_pages": len(reader.pages),
            }
        except Exception as e:
            return {"error": f"PDF提取失败: {e}", "modality": "file"}

    def _extract_audio(self, path: Path, description: str, tags: list[str]) -> dict:
        """提取音频元数据"""
        stat = path.stat()
        desc = description or f"音频文件 {path.name} ({stat.st_size / 1024:.1f}KB, {path.suffix.upper()})"
        return {
            "modality": "audio",
            "content": desc,
            "tags": (tags or []) + ["audio", path.suffix.lstrip(".")],
            "file_name": path.name,
            "file_size": stat.st_size,
            "audio_format": path.suffix.lstrip("."),
        }

    def _extract_generic(self, path: Path, description: str, tags: list[str]) -> dict:
        """通用文件提取"""
        stat = path.stat()
        desc = description or f"文件 {path.name} ({stat.st_size / 1024:.1f}KB, {path.suffix.upper()})"
        return {
            "modality": "file",
            "content": desc,
            "tags": (tags or []) + ["file"],
            "file_name": path.name,
            "file_size": stat.st_size,
        }

    def _extract_text_from_html(self, html: str) -> str:
        """从 HTML 提取纯文本"""
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:3000]

    def _extract_title(self, html: str) -> str:
        """提取 HTML title"""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip()[:200] if match else ""

    def _store_memory(self, result: dict, wing: str) -> Drawer:
        """将提取结果存入 Palace 记忆"""
        from ..memory.ingestion import remember

        content = result.get("content", "")
        tags = result.get("tags", [])
        modality = result.get("modality", "text")
        importance = 0.5

        if modality == "image":
            importance = 0.6
        elif modality == "url":
            importance = 0.7
        elif modality == "file" and result.get("file_type") == "pdf":
            importance = 0.7

        item_id, drawer = remember(
            raw_text=content[:1000],
            wing=wing,
            room=modality,
            importance=importance,
            tags=tags,
            source=f"multimodal:{modality}",
        )
        drawer.metadata["modality"] = modality
        drawer.metadata["file_name"] = result.get("file_name", "")
        drawer.metadata["file_path"] = result.get("file", result.get("url", ""))
        return drawer


_pipeline: MultimodalPipeline | None = None


def get_multimodal_pipeline(config: PanguConfig = None) -> MultimodalPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = MultimodalPipeline(config)
    return _pipeline
