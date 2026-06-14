"""盘古多模态记忆支持 — 图片/音频/文件摘要
==============================================
支持非文本记忆的提取和摘要：
- 图片：提取文件名、路径、大小、描述（可选 OCR）
- 音频：提取文件名、时长、格式
- 文件：通用文件元数据提取

注意：多模态内容理解（OCR、语音转文字）需要额外的 LMM 支持，
盘古提供基础的多模态数据结构，实际理解由上层 Agent 完成。
"""
import base64
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class MultimodalMemory:
    """多模态记忆片段"""
    id: str
    content: str  # 文本描述/摘要
    modality: str  # text, image, audio, file
    wing: str = "default"
    room: str = "general"
    importance: float = 3.0
    tags: list[str] = field(default_factory=list)

    # 文件元数据
    file_path: str = ""
    file_name: str = ""
    file_size: int = 0
    file_type: str = ""
    mime_type: str = ""

    # 图片特定
    image_width: int = 0
    image_height: int = 0

    # 音频特定
    audio_duration: float = 0.0
    audio_format: str = ""

    # 文件哈希
    file_hash: str = ""

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "modality": self.modality,
            "wing": self.wing,
            "room": self.room,
            "importance": self.importance,
            "tags": self.tags,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "audio_duration": self.audio_duration,
            "audio_format": self.audio_format,
            "file_hash": self.file_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MultimodalMemory":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# MIME 类型映射
MIME_MAP = {
    # 图片
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    # 音频
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    # 文档
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # 文本
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".html": "text/html",
    ".css": "text/css",
    ".sql": "text/sql",
    # 压缩
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
}


def get_mime_type(file_path: str) -> str:
    """根据文件扩展名获取 MIME 类型"""
    ext = Path(file_path).suffix.lower()
    return MIME_MAP.get(ext, "application/octet-stream")


def get_modality(file_path: str) -> str:
    """根据文件类型判断模态"""
    mime = get_mime_type(file_path)
    if mime.startswith("image/"):
        return "image"
    elif mime.startswith("audio/"):
        return "audio"
    elif mime.startswith("text/") or mime.startswith("application/"):
        return "file"
    return "file"


def compute_file_hash(file_path: str) -> str:
    """计算文件 SHA256 哈希"""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class MultimodalExtractor:
    """多模态记忆提取器"""

    def __init__(self):
        pass

    def extract_from_file(self, file_path: str, wing: str = "default",
                          room: str = None, tags: list[str] = None) -> MultimodalMemory:
        """从文件提取多模态记忆"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        stat = path.stat()
        mime_type = get_mime_type(file_path)
        modality = get_modality(file_path)
        file_hash = compute_file_hash(file_path)

        # 生成描述
        desc = self._generate_description(path, modality, stat)

        memory = MultimodalMemory(
            id=f"mm_{hash(file_path)}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            content=desc,
            modality=modality,
            wing=wing,
            room=room or modality,
            tags=tags or [],
            file_path=str(path.absolute()),
            file_name=path.name,
            file_size=stat.st_size,
            file_type=path.suffix.lower().lstrip("."),
            mime_type=mime_type,
            file_hash=file_hash,
        )

        # 图片尺寸
        if modality == "image":
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    memory.image_width = img.width
                    memory.image_height = img.height
            except ImportError:
                pass

        return memory

    def extract_from_directory(self, dir_path: str, wing: str = "default",
                               recursive: bool = True, tags: list[str] = None) -> list[MultimodalMemory]:
        """从目录批量提取多模态记忆"""
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")

        memories = []
        pattern = "**/*" if recursive else "*"
        supported_exts = set(MIME_MAP.keys())

        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in supported_exts:
                try:
                    memory = self.extract_from_file(
                        str(file_path), wing=wing,
                        room=file_path.parent.name,
                        tags=tags,
                    )
                    memories.append(memory)
                except Exception:
                    continue

        return memories

    def _generate_description(self, path: Path, modality: str, stat: os.stat_result) -> str:
        """生成文件描述"""
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

        if modality == "image":
            return f"[图片] {path.name} ({size_mb:.1f}MB, {path.suffix.upper()}, 修改于 {modified})"
        elif modality == "audio":
            return f"[音频] {path.name} ({size_mb:.1f}MB, {path.suffix.upper()}, 修改于 {modified})"
        else:
            return f"[文件] {path.name} ({size_mb:.1f}MB, {path.suffix.upper()}, 修改于 {modified})"

    def create_base64_url(self, file_path: str) -> str:
        """将图片文件编码为 base64 data URL"""
        mime = get_mime_type(file_path)
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{data}"

    def create_text_preview(self, file_path: str, max_chars: int = 500) -> str:
        """创建文本文件预览"""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read(max_chars)
            if len(content) >= max_chars:
                content += "...[已截断]"
            return content
        except Exception:
            return f"[无法预览 {file_path}]"
