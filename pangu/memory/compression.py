"""盘古 LLM 记忆压缩 — 智能压缩旧记忆

核心功能：
1. 识别可压缩记忆：>30天 且 importance <0.3
2. LLM 提取关键点：从长记忆中提取核心信息
3. 存储压缩版本：保留压缩版 + 原始引用
4. 自动触发：lifecycle 定期执行压缩
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.compression")


@dataclass
class CompressionResult:
    """压缩结果"""
    original: str
    compressed: str
    compression_ratio: float
    key_points: list[str]
    memory_id: str


class MemoryCompressor:
    """LLM 记忆压缩引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._llm_engine = None

    @property
    def llm_engine(self):
        if self._llm_engine is None:
            try:
                from ..core.llm import LLMEngine
                self._llm_engine = LLMEngine(self.config)
            except ImportError:
                self._llm_engine = None
        return self._llm_engine

    def _is_compressible(self, drawer: Drawer) -> bool:
        """判断记忆是否可压缩"""
        # 长度检查
        if len(drawer.content) < 100:
            return False

        # 时间检查：>30天
        try:
            days_old = (datetime.now() - datetime.fromisoformat(drawer.created_at)).total_seconds() / 86400
            if days_old < 30:
                return False
        except (ValueError, TypeError):
            return False

        # 重要性检查：<0.3
        if drawer.importance / 5.0 > 0.3:
            return False

        return True

    def compress(self, drawer: Drawer) -> CompressionResult | None:
        """用 LLM 压缩记忆"""
        if not self._is_compressible(drawer):
            return None

        # 尝试 LLM 压缩
        key_points = []
        if self.llm_engine:
            try:
                prompt = f"请从以下记忆中提取3个关键点，用分号分隔：\n{drawer.content[:500]}"
                resp = self.llm_engine.chat([{"role": "user", "content": prompt}])
                if resp and resp.content:
                    key_points = [kp.strip() for kp in resp.content.split(";") if kp.strip()]
            except Exception as e:
                logger.debug(f"LLM compression failed: {e}")

        # 降级：基于关键词提取
        if not key_points:
            key_points = self._extract_key_points(drawer.content)

        # 生成压缩版本
        compressed = f"关键点: {'; '.join(key_points[:3])}"
        if len(compressed) > 200:
            compressed = compressed[:197] + "..."

        compression_ratio = len(compressed) / len(drawer.content)

        return CompressionResult(
            original=drawer.content,
            compressed=compressed,
            compression_ratio=round(compression_ratio, 3),
            key_points=key_points[:3],
            memory_id=drawer.id,
        )

    def _extract_key_points(self, content: str) -> list[str]:
        """基于关键词提取关键点"""
        # 简单的关键词提取
        important_words = {"重要", "关键", "决定", "结论", "注意", "总结", "方法", "原因", "结果"}
        sentences = content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")

        key_points = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if any(w in s for w in important_words):
                key_points.append(s[:50])
            elif len(s) > 20:
                key_points.append(s[:50])

        return key_points[:3] if key_points else [content[:50]]

    def batch_compress(self, drawers: list[Drawer]) -> list[CompressionResult]:
        """批量压缩记忆"""
        results = []
        for d in drawers:
            if self._is_compressible(d):
                result = self.compress(d)
                if result:
                    results.append(result)
        return results


# 全局单例
_compressor: MemoryCompressor | None = None


def get_compressor(config: PanguConfig = None) -> MemoryCompressor:
    """获取全局压缩引擎"""
    global _compressor
    if _compressor is None:
        _compressor = MemoryCompressor(config)
    return _compressor
