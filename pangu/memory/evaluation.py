"""盘古 — 评估缓存独立化（从伏羲 v1.5.6 移植）

提供独立的评估结果缓存，避免重复 LLM 调用。
支持文件持久化和内存缓存双模式。
"""

import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.evaluation")


class EvaluationCache:
    """评估结果缓存，避免重复 LLM 调用"""

    def __init__(self, cache_path: str = "~/.pangu/evaluation_cache.jsonl"):
        self.cache_path = Path(cache_path).expanduser()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict = {}
        self._lock = threading.Lock()

    def get(self, prompt_hash: str) -> dict | None:
        """获取缓存结果"""
        # 先查内存缓存
        with self._lock:
            if prompt_hash in self._memory_cache:
                return self._memory_cache[prompt_hash]

        # 再查文件缓存
        return self._search_file_cache(prompt_hash)

    def _scan_cache_file(self, prompt_hash: str) -> dict | None:
        with open(self.cache_path) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("hash") == prompt_hash:
                    return entry
        return None

    def _search_file_cache(self, prompt_hash: str) -> dict | None:
        if not self.cache_path.exists():
            return None
        try:
            entry = self._scan_cache_file(prompt_hash)
            if entry:
                with self._lock:
                    self._memory_cache[prompt_hash] = entry
                return entry
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache read error: {e}")
        return None

    def put(self, prompt_hash: str, verdict: str, confidence: float) -> None:
        """写入缓存"""
        entry = {
            "hash": prompt_hash,
            "verdict": verdict,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._memory_cache[prompt_hash] = entry
        try:
            with open(self.cache_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.warning(f"Cache write error: {e}")

    def clear(self):
        """清除缓存"""
        with self._lock:
            self._memory_cache.clear()
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
        except OSError as e:
            logger.warning(f"Cache clear error: {e}")

    @property
    def stats(self) -> dict:
        with self._lock:
            mem_size = len(self._memory_cache)
        try:
            file_entries = sum(1 for _ in self.cache_path.open()) if self.cache_path.exists() else 0
        except (OSError, ValueError):
            file_entries = 0
        return {
            "memory_cache_size": mem_size,
            "file_cache_entries": file_entries,
            "cache_path": str(self.cache_path),
        }


# 判决类型定义
VERDICTS = {
    "contradiction": "真正的矛盾",
    "temporal_supersession": "新 claim 替代旧 claim（正常）",
    "temporal_regression": "指标/状态倒退（需标记）",
    "temporal_evolution": "合法的时间演变",
    "negation_artifact": "LLM 误读否定词（数据正确）",
    "no_contradiction": "兼容",
}


def get_evaluation_stats(drawers: list) -> dict:
    """获取评估统计信息"""
    total = len(drawers)
    if total == 0:
        return {"items": 0, "edges": 0}

    # 统计有元数据的记忆
    with_embedding = sum(1 for d in drawers if d.metadata.get("embedding"))
    with_decay = sum(1 for d in drawers if "decay_score" in d.metadata)
    with_fusion = sum(1 for d in drawers if d.metadata.get("fused_count", 0) > 0)

    return {
        "items": total,
        "with_embedding": with_embedding,
        "with_decay_score": with_decay,
        "fused_items": with_fusion,
    }


def _make_prompt_hash(text_a: str, text_b: str) -> str:
    """生成 prompt hash"""
    combined = text_a + "|||" + text_b
    return hashlib.sha256(combined.encode()).hexdigest()[:16]
