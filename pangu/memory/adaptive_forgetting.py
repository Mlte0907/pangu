"""盘古自适应遗忘 — 智能记忆生命周期管理

核心能力：
1. 遗忘评估：评估每条记忆的遗忘价值
2. 自动归档：自动将低价值记忆归档到冷存储
3. 智能压缩：将多条相似记忆压缩为精炼摘要
4. 选择性遗忘：基于重要性/时效/访问频率智能遗忘
5. 遗忘效果追踪：追踪遗忘后的系统改善
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.adaptive_forgetting")


@dataclass
class ForgettingDecision:
    """遗忘决策"""

    memory_id: str
    action: str  # keep / archive / compress / forget
    reason: str
    priority: float  # 0-1, 越高越应该遗忘
    original_importance: float
    current_score: float


@dataclass
class ForgettingReport:
    """遗忘报告"""

    total_evaluated: int
    keep_count: int
    archive_count: int
    compress_count: int
    forget_count: int
    estimated_tokens_freed: int
    decisions: list[ForgettingDecision]


class AdaptiveForgetting:
    """自适应遗忘引擎"""

    def __init__(self, config=None):
        self.config = config
        self._forgetting_history: list[dict] = []
        self._archive: list[dict] = []
        # 归档落盘路径：与 palace 同级的 forgetting_archive.json。
        # 此前归档只存内存，服务重启即丢——而「归档」的语义就是把记忆
        # 移出活跃检索但**保留可查**，丢失等于静默删除。
        self._archive_file: Path | None = self._resolve_archive_file(config)
        self._load_archive()

    @staticmethod
    def _resolve_archive_file(config) -> Path | None:
        """定位归档文件路径（配置不可用时不落盘，保持内存模式）"""
        if config is None:
            return None
        try:
            palace = getattr(config, "palace_path", None)
            if palace:
                return Path(palace).parent / "forgetting_archive.json"
            base = getattr(config, "base_dir", None)
            if base:
                return Path(base) / "forgetting_archive.json"
        except Exception:  # noqa: BLE001
            return None
        return None

    def _load_archive(self) -> None:
        """从磁盘恢复归档（损坏则忽略，不阻断启动）"""
        if self._archive_file is None or not self._archive_file.exists():
            return
        try:
            data = json.loads(self._archive_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._archive = data
        except (json.JSONDecodeError, OSError):
            pass

    def _persist_archive(self) -> None:
        """把归档表写回磁盘（原子替换，避免半截文件）"""
        if self._archive_file is None:
            return
        try:
            self._archive_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._archive_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._archive, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._archive_file)
        except OSError:
            pass

    def _compute_decision(self, forget_score: float, content_len: int) -> tuple[str, str]:
        if forget_score > 0.8:
            return "forget", f"极低价值(得分{forget_score:.2f})"
        elif forget_score > 0.6:
            return "archive", f"低活跃(得分{forget_score:.2f})"
        elif forget_score > 0.4 and content_len > 500:
            return "compress", f"可压缩(得分{forget_score:.2f}, {content_len}字)"
        else:
            return "keep", f"有价值(得分{forget_score:.2f})"

    def _compute_recency_score(self, days_since_access: int) -> float:
        """根据访问距今天数计算时效分数"""
        if days_since_access < 7:
            return 1.0
        elif days_since_access < 30:
            return 0.7
        elif days_since_access < 90:
            return 0.4
        return 0.1

    def evaluate_memory(self, drawer, access_count: int = 0, days_since_access: int = 0) -> ForgettingDecision:
        imp_norm = drawer.importance / 5.0
        content_len = len(drawer.content)

        freq_score = min(1.0, access_count / 20.0)
        recency = self._compute_recency_score(days_since_access)

        forget_score = (1 - imp_norm) * 0.4 + (1 - freq_score) * 0.3 + (1 - recency) * 0.3

        action, reason = self._compute_decision(forget_score, content_len)

        return ForgettingDecision(
            memory_id=drawer.id,
            action=action,
            reason=reason,
            priority=forget_score,
            original_importance=drawer.importance,
            current_score=round(forget_score, 3),
        )

    def evaluate_all(self, drawers: list, access_log: dict = None) -> ForgettingReport:
        """评估所有记忆"""
        access_log = access_log or {}
        decisions = []

        for d in drawers:
            log = access_log.get(d.id, {})
            decision = self.evaluate_memory(
                d,
                access_count=log.get("access_count", 0),
                days_since_access=log.get("days_since_access", 30),
            )
            decisions.append(decision)

        keep = [d for d in decisions if d.action == "keep"]
        archive = [d for d in decisions if d.action == "archive"]
        compress = [d for d in decisions if d.action == "compress"]
        forget = [d for d in decisions if d.action == "forget"]

        estimated_freed = len(forget) * 100 + len(archive) * 50 + len(compress) * 30

        return ForgettingReport(
            total_evaluated=len(decisions),
            keep_count=len(keep),
            archive_count=len(archive),
            compress_count=len(compress),
            forget_count=len(forget),
            estimated_tokens_freed=estimated_freed,
            decisions=decisions,
        )

    def auto_forget(self, drawers: list, access_log: dict = None) -> dict:
        """自动执行遗忘"""
        report = self.evaluate_all(drawers, access_log)

        archived = []
        forgotten = []

        for d in drawers:
            decision = next((dec for dec in report.decisions if dec.memory_id == d.id), None)
            if not decision:
                continue

            if decision.action == "archive":
                self._archive.append(
                    {
                        "id": d.id,
                        "content": d.content[:200],
                        "wing": d.wing,
                        "room": getattr(d, "room", "general"),
                        "importance": d.importance,
                        "archived_at": datetime.now().isoformat(),
                    }
                )
                archived.append(d.id)

            elif decision.action == "forget":
                forgotten.append(d.id)

        self._forgetting_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "evaluated": report.total_evaluated,
                "archived": len(archived),
                "forgotten": len(forgotten),
            }
        )
        if archived:
            self._persist_archive()

        return {
            "evaluated": report.total_evaluated,
            "kept": report.keep_count,
            "archived": len(archived),
            "compressed": report.compress_count,
            "forgotten": len(forgotten),
            "tokens_freed": report.estimated_tokens_freed,
        }

    def archive_memory(self, drawer) -> dict:
        """归档单条记忆（供 pangu_archive_memory 工具使用）

        与 `auto_forget` 的归档分支写入同一结构（含 room），使
        `get_archive()` / `get_forgetting_stats()` 对两条路径的结果口径一致。

        Returns:
            写入归档表的条目（含 archived_at / wing / room）。
        """
        entry = {
            "id": drawer.id,
            "content": drawer.content[:200],
            "wing": getattr(drawer, "wing", "default"),
            "room": getattr(drawer, "room", "general"),
            "importance": getattr(drawer, "importance", 0.0),
            "archived_at": datetime.now().isoformat(),
            "reason": "manual_archive",
        }
        self._archive.append(entry)
        self._persist_archive()
        return entry

    def get_archive(self, limit: int = 20) -> list[dict]:
        """获取归档记忆"""
        return self._archive[-limit:]

    def get_forgetting_stats(self) -> dict:
        """获取遗忘统计"""
        if not self._forgetting_history:
            return {"total_cycles": 0, "total_archived": 0, "total_forgotten": 0}

        total_archived = sum(h["archived"] for h in self._forgetting_history)
        total_forgotten = sum(h["forgotten"] for h in self._forgetting_history)
        return {
            "total_cycles": len(self._forgetting_history),
            "total_archived": total_archived,
            "total_forgotten": total_forgotten,
            "archive_size": len(self._archive),
        }


_forgetting: AdaptiveForgetting | None = None


def get_forgetting(config=None) -> AdaptiveForgetting:
    """获取全局自适应遗忘实例"""
    global _forgetting
    if _forgetting is None:
        _forgetting = AdaptiveForgetting(config)
    return _forgetting
