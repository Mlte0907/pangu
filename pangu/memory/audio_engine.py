"""盘古音频记忆引擎 — whisper 转写 + 元数据 + 音频摘要

核心能力：
1. 语音转文字：Whisper 模型自动转写
2. 音频元数据：时长/格式/采样率/声道
3. 音频摘要：基于转写文本生成记忆
4. 自动入库：转写后自动存入 Palace 记忆
"""
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.audio_engine")

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}


class AudioMemoryEngine:
    """音频记忆引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._whisper_model = None
        self._whisper_name = "base"

    @property
    def whisper(self):
        if self._whisper_model is None:
            try:
                import whisper
                self._whisper_model = whisper.load_model(self._whisper_name)
                logger.info(f"Whisper model '{self._whisper_name}' loaded")
            except Exception as e:
                logger.debug(f"Whisper unavailable: {e}")
                self._whisper_model = False
        return self._whisper_model if self._whisper_model is not False else None

    def get_metadata(self, audio_path: str) -> dict:
        """提取音频元数据"""
        path = Path(audio_path).expanduser()
        if not path.exists():
            return {"error": f"文件不存在: {audio_path}"}

        stat = path.stat()
        meta = {
            "file_name": path.name,
            "file_size": stat.st_size,
            "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
            "file_type": path.suffix.lstrip("."),
            "file_path": str(path.absolute()),
        }

        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                meta.update({
                    "duration": float(fmt.get("duration", 0)),
                    "duration_str": self._format_duration(float(fmt.get("duration", 0))),
                    "bitrate": int(fmt.get("bit_rate", 0)),
                    "format_name": fmt.get("format_long_name", ""),
                })

                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "audio":
                        meta.update({
                            "audio_codec": stream.get("codec_name", ""),
                            "channels": int(stream.get("channels", 0)),
                            "sample_rate": int(stream.get("sample_rate", 0)),
                        })
                        break
        except Exception as e:
            logger.warning(f"ffprobe failed: {e}")

        return meta

    def transcribe(self, audio_path: str, language: str = None,
                   task: str = "transcribe") -> dict:
        """语音转文字"""
        path = Path(audio_path).expanduser()
        if not path.exists():
            return {"error": f"文件不存在: {audio_path}"}

        if not self.whisper:
            return {"error": "Whisper model not available", "transcription": ""}

        try:
            opts = {"task": task}
            if language:
                opts["language"] = language

            result = self.whisper.transcribe(str(path), **opts)

            segments = []
            for seg in result.get("segments", []):
                segments.append({
                    "start": round(seg["start"], 2),
                    "end": round(seg["end"], 2),
                    "text": seg["text"].strip(),
                })

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "unknown"),
                "segments": segments,
                "segment_count": len(segments),
            }
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return {"error": str(e), "transcription": ""}

    def ingest_audio(self, audio_path: str, wing: str = "default",
                     description: str = "", tags: list[str] = None,
                     auto_store: bool = True) -> dict:
        """从音频提取记忆并入库"""
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {audio_path}"}
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return {"error": f"不支持的音频格式: {path.suffix}"}

        meta = self.get_metadata(str(path))

        # 转写
        transcribe_result = self.transcribe(str(path))
        transcription = transcribe_result.get("text", "")
        language = transcribe_result.get("language", "unknown")

        # 构建描述
        desc_parts = [f"[音频] {path.name}"]
        desc_parts.append(f"时长: {meta.get('duration_str', '?')}")
        if meta.get("channels"):
            desc_parts.append(f"声道: {meta['channels']}")
        if meta.get("sample_rate"):
            desc_parts.append(f"采样率: {meta['sample_rate']}Hz")
        if language != "unknown":
            desc_parts.append(f"语言: {language}")
        if description:
            desc_parts.append(f"描述: {description}")

        content = "\n".join(desc_parts)
        if transcription:
            content += f"\n\n转写:\n{transcription[:3000]}"

        tags = (tags or []) + ["audio", path.suffix.lstrip(".")]
        if language != "unknown":
            tags.append(language)

        result = {
            "modality": "audio",
            "content": content,
            "tags": tags,
            "file_name": path.name,
            "file_size": meta.get("file_size", 0),
            "duration": meta.get("duration", 0),
            "duration_str": meta.get("duration_str", ""),
            "audio_codec": meta.get("audio_codec", ""),
            "channels": meta.get("channels", 0),
            "sample_rate": meta.get("sample_rate", 0),
            "transcription": transcription,
            "language": language,
            "segment_count": transcribe_result.get("segment_count", 0),
        }

        if auto_store and transcription:
            from ..memory.ingestion import remember
            importance = min(1.0, 0.5 + len(transcription) / 5000)
            item_id, drawer = remember(
                raw_text=content[:2000],
                wing=wing,
                room="audio",
                importance=importance,
                tags=tags,
                source="audio_engine",
            )
            drawer.metadata["modality"] = "audio"
            drawer.metadata["audio_path"] = str(path)
            drawer.metadata["duration"] = meta.get("duration", 0)
            drawer.metadata["language"] = language
            drawer.metadata["transcription"] = transcription[:500]
            result["stored"] = True
            result["memory_id"] = drawer.id

        return result

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds <= 0:
            return "未知"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}时{m:02d}分{s:02d}秒"
        return f"{m}分{s:02d}秒"


_audio_engine: AudioMemoryEngine | None = None


def get_audio_engine(config: PanguConfig = None) -> AudioMemoryEngine:
    global _audio_engine
    if _audio_engine is None:
        _audio_engine = AudioMemoryEngine(config)
    return _audio_engine
