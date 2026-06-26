"""盘古视频记忆引擎 — ffmpeg 提取元数据/帧/音频/摘要

核心能力：
1. 视频元数据：时长/分辨率/编码/帧率/码率
2. 关键帧提取：按间隔提取关键帧图片
3. 音频提取：从视频中提取音频
4. 视频摘要：基于元数据+帧分析生成文字描述
5. CLIP 帧嵌入：对关键帧做 CLIP 向量化
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.video_engine")

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"}


class VideoMemoryEngine:
    """视频记忆引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._ffmpeg = "ffmpeg"
        self._ffprobe = "ffprobe"

    def get_metadata(self, video_path: str) -> dict:
        """提取视频元数据"""
        path = Path(video_path).expanduser()
        if not path.exists():
            return {"error": f"文件不存在: {video_path}"}

        stat = path.stat()
        meta = {
            "file_name": path.name,
            "file_size": stat.st_size,
            "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
            "file_type": path.suffix.lstrip("."),
            "file_path": str(path.absolute()),
        }

        try:
            cmd = [self._ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                meta.update(
                    {
                        "duration": float(fmt.get("duration", 0)),
                        "duration_str": self._format_duration(float(fmt.get("duration", 0))),
                        "bitrate": int(fmt.get("bit_rate", 0)),
                        "format_name": fmt.get("format_long_name", ""),
                        "nb_streams": int(fmt.get("nb_streams", 0)),
                    }
                )

                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        meta.update(
                            {
                                "video_codec": stream.get("codec_name", ""),
                                "width": int(stream.get("width", 0)),
                                "height": int(stream.get("height", 0)),
                                "fps": self._parse_fps(stream.get("r_frame_rate", "0/1")),
                                "video_bitrate": int(stream.get("bit_rate", 0)),
                            }
                        )
                    elif stream.get("codec_type") == "audio":
                        meta.update(
                            {
                                "audio_codec": stream.get("codec_name", ""),
                                "audio_channels": int(stream.get("channels", 0)),
                                "audio_sample_rate": int(stream.get("sample_rate", 0)),
                            }
                        )
        except Exception as e:
            logger.warning(f"ffprobe failed: {e}")

        return meta

    def extract_keyframes(
        self, video_path: str, output_dir: str = None, count: int = 5, interval: str = None
    ) -> list[str]:
        """提取关键帧"""
        path = Path(video_path).expanduser()
        if not path.exists():
            return []

        meta = self.get_metadata(str(path))
        duration = meta.get("duration", 0)
        if duration <= 0:
            return []

        if not interval:
            interval_sec = max(1, duration / (count + 1))
        else:
            interval_sec = self._parse_duration(interval)

        out_dir = Path(output_dir or tempfile.mkdtemp(prefix="pangu_video_"))
        out_dir.mkdir(parents=True, exist_ok=True)

        pattern = str(out_dir / "frame_%03d.jpg")
        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-i",
                str(path),
                "-vf",
                f"fps=1/{interval_sec}",
                "-vframes",
                str(count),
                "-q:v",
                "2",
                pattern,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            frames = sorted(out_dir.glob("frame_*.jpg"))
            return [str(f) for f in frames]
        except Exception as e:
            logger.warning(f"Keyframe extraction failed: {e}")
            return []

    def extract_audio(self, video_path: str, output_path: str = None) -> str:
        """从视频提取音频"""
        path = Path(video_path).expanduser()
        if not path.exists():
            return ""

        if not output_path:
            output_path = str(Path(tempfile.mktemp(suffix=".wav", prefix="pangu_audio_")))

        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-i",
                str(path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
        except Exception as e:
            logger.warning(f"Audio extraction failed: {e}")
        return ""

    def generate_thumbnail(self, video_path: str, output_path: str = None, timestamp: str = "00:00:05") -> str:
        """生成视频缩略图"""
        path = Path(video_path).expanduser()
        if not path.exists():
            return ""

        if not output_path:
            output_path = str(Path(tempfile.mktemp(suffix=".jpg", prefix="pangu_thumb_")))

        try:
            cmd = [
                self._ffmpeg,
                "-y",
                "-ss",
                timestamp,
                "-i",
                str(path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
        except Exception as e:
            logger.warning(f"Thumbnail extraction failed: {e}")
        return ""

    def ingest_video(
        self,
        video_path: str,
        wing: str = "default",
        description: str = "",
        tags: list[str] = None,
        extract_frames: bool = True,
        auto_store: bool = True,
    ) -> dict:
        """从视频提取记忆并入库"""
        path = Path(video_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {video_path}"}
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            return {"error": f"不支持的视频格式: {path.suffix}"}

        meta = self.get_metadata(str(path))

        # 生成描述
        desc_parts = [f"[视频] {path.name}"]
        desc_parts.append(f"时长: {meta.get('duration_str', '?')}")
        if meta.get("width") and meta.get("height"):
            desc_parts.append(f"分辨率: {meta['width']}x{meta['height']}")
        if meta.get("video_codec"):
            desc_parts.append(f"编码: {meta['video_codec']}")
        if meta.get("fps"):
            desc_parts.append(f"帧率: {meta['fps']}fps")
        desc_parts.append(f"大小: {meta.get('file_size_mb', 0)}MB")
        if description:
            desc_parts.append(f"描述: {description}")

        content = "\n".join(desc_parts)

        # 提取关键帧
        frame_paths = []
        if extract_frames:
            frame_paths = self.extract_keyframes(str(path), count=3)

        # 用 CLIP 分析帧
        frame_analysis = []
        if frame_paths:
            try:
                from pangu.memory.image_engine import get_image_engine

                img_engine = get_image_engine(self.config)
                for fp in frame_paths:
                    analysis = img_engine.embed_image(fp)
                    frame_analysis.append(
                        {
                            "file": fp,
                            "embedding_dim": analysis.get("embedding_dim", 0),
                            "colors": analysis.get("dominant_colors", []),
                            "description": analysis.get("content", "")[:100],
                        }
                    )
                # 聚合帧描述
                all_colors = []
                for fa in frame_analysis:
                    all_colors.extend(fa.get("colors", []))
                if all_colors:
                    from collections import Counter

                    top_colors = [c for c, _ in Counter(all_colors).most_common(3)]
                    content += f"\n主色调: {', '.join(top_colors)}"
            except Exception as e:
                logger.debug(f"Frame analysis skipped: {e}")

        result = {
            "modality": "video",
            "content": content,
            "tags": (tags or []) + ["video", path.suffix.lstrip(".")],
            "file_name": path.name,
            "file_size": meta.get("file_size", 0),
            "duration": meta.get("duration", 0),
            "duration_str": meta.get("duration_str", ""),
            "width": meta.get("width", 0),
            "height": meta.get("height", 0),
            "video_codec": meta.get("video_codec", ""),
            "fps": meta.get("fps", 0),
            "frame_count": len(frame_paths),
            "frame_analyses": frame_analysis,
        }

        if auto_store:
            from ..memory.ingestion import remember

            importance = min(1.0, 0.5 + meta.get("duration", 0) / 600)
            item_id, drawer = remember(
                raw_text=content[:1000],
                wing=wing,
                room="video",
                importance=importance,
                tags=result["tags"],
                source="video_engine",
            )
            drawer.metadata["modality"] = "video"
            drawer.metadata["video_path"] = str(path)
            drawer.metadata["duration"] = meta.get("duration", 0)
            drawer.metadata["resolution"] = f"{meta.get('width', 0)}x{meta.get('height', 0)}"
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

    @staticmethod
    def _parse_fps(fps_str: str) -> float:
        try:
            parts = fps_str.split("/")
            return round(float(parts[0]) / float(parts[1]), 2) if len(parts) == 2 else float(fps_str)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        parts = duration_str.split(":")
        try:
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            return float(parts[0])
        except Exception:
            return 5.0


_video_engine: VideoMemoryEngine | None = None


def get_video_engine(config: PanguConfig = None) -> VideoMemoryEngine:
    global _video_engine
    if _video_engine is None:
        _video_engine = VideoMemoryEngine(config)
    return _video_engine
