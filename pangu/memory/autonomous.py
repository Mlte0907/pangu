"""盘古自主记忆管理引擎 — 自动调度记忆生命周期
==================================================
自动管理记忆的完整生命周期，无需手动触发：
- 新记忆写入过多时自动融合
- 旧记忆自动压缩和衰减
- 知识空白自动探索
- 空闲时自动巩固和梦境整理
- 根据系统负载自适应调度

使用方式：
    engine = AutonomousMemoryEngine()
    result = engine.run_cycle()  # 运行一次自主周期
    result = engine.tick()      # 检查是否需要运行（轻量）
"""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.autonomous")


@dataclass
class TaskResult:
    """单个任务的执行结果"""
    name: str
    status: str  # success / skipped / failed
    duration_ms: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class CycleResult:
    """一个完整周期的执行结果"""
    timestamp: str
    total_duration_ms: float
    tasks_run: int
    tasks_skipped: int
    tasks_failed: int
    results: list[TaskResult] = field(default_factory=list)
    trigger: str = ""


# ── 调度规则 ──
SCHEDULE_RULES = {
    "fusion": {
        "min_new_since_last": 10,
        "interval_hours": 4,
    },
    "compression": {
        "min_old_memories": 20,
        "interval_hours": 24,
    },
    "decay": {
        "interval_hours": 6,
    },
    "forget": {
        "min_forgettable": 5,
        "interval_hours": 24,
    },
    "dream": {
        "interval_hours": 12,
    },
    "curiosity": {
        "interval_hours": 8,
    },
    "vector_rebuild": {
        "min_new_embeddings": 15,
        "interval_hours": 2,
    },
}


class AutonomousMemoryEngine:
    """自主记忆管理引擎 — 自动调度所有记忆维护任务"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._palace_path = Path(self.config.palace_path)
        self._drawers_file = self._palace_path / "drawers.json"
        self._state_file = self._palace_path / "autonomous_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_run": {},
            "total_runs": 0,
            "total_tasks": 0,
        }

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存自主状态失败: {e}")

    def _load_drawers(self) -> list[Drawer]:
        if not self._drawers_file.exists():
            return []
        try:
            with open(self._drawers_file, encoding="utf-8") as f:
                return [Drawer.from_dict(d) for d in json.load(f)]
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
            return []

    def _save_drawers(self, drawers: list[Drawer]):
        try:
            with open(self._drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    def _should_run(self, task: str, extra_check: Callable[[], bool] = None) -> bool:
        """检查某任务是否应该执行"""
        rule = SCHEDULE_RULES.get(task, {})
        interval = rule.get("interval_hours", 1) * 3600
        last_run = self._state.get("last_run", {}).get(task, 0)
        now = time.time()
        if (now - last_run) < interval:
            return False
        if extra_check and not extra_check():
            return False
        return True

    def _mark_done(self, task: str):
        self._state.setdefault("last_run", {})[task] = time.time()
        self._state["total_runs"] = self._state.get("total_runs", 0) + 1

    def _count_new_since(self, drawers: list[Drawer], since: float) -> int:
        count = 0
        for d in drawers:
            try:
                ts = datetime.fromisoformat(d.created_at).timestamp()
                if ts > since:
                    count += 1
            except Exception:
                pass
        return count

    def _count_old_memories(self, drawers: list[Drawer], days: int = 30) -> int:
        cutoff = time.time() - days * 86400
        count = 0
        for d in drawers:
            try:
                ts = datetime.fromisoformat(d.created_at).timestamp()
                if ts < cutoff:
                    count += 1
            except Exception:
                pass
        return count

    # ── 各子任务 ──

    def _task_fusion(self, drawers: list[Drawer]) -> TaskResult:
        """自动融合：同主题>=3条时融合"""
        start = time.time()
        try:
            from .fusion import FusionEngine
            engine = FusionEngine(self.config)
            topic_groups = engine._group_by_keywords(drawers)
            fused = 0
            for topic, group in topic_groups.items():
                if len(group) >= 3:
                    result = engine.fuse_topic(topic, group, drawers)
                    if result:
                        fused += 1
            return TaskResult(
                name="fusion",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={"fused_groups": fused, "total_topics": len(topic_groups)},
            )
        except Exception as e:
            return TaskResult(name="fusion", status="failed", details={"error": str(e)})

    def _task_compression(self, drawers: list[Drawer]) -> TaskResult:
        """自动压缩：旧长记忆→精简摘要"""
        start = time.time()
        try:
            from .compression import MemoryCompressor
            compressor = MemoryCompressor(self.config)
            compressible = [d for d in drawers if compressor._is_compressible(d)]
            compressed = 0
            tokens_saved = 0
            for d in compressible[:10]:
                result = compressor.compress(d)
                if result:
                    old_len = len(d.content)
                    d.content = result.compressed
                    d.metadata["compressed"] = True
                    d.metadata["original_length"] = old_len
                    compressed += 1
                    tokens_saved += old_len - len(result.compressed)
            return TaskResult(
                name="compression",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={"compressed": compressed, "tokens_saved": tokens_saved},
            )
        except Exception as e:
            return TaskResult(name="compression", status="failed", details={"error": str(e)})

    def _task_decay(self, drawers: list[Drawer]) -> TaskResult:
        """自动衰减：基于遗忘曲线降低不活跃记忆重要性"""
        start = time.time()
        try:
            from .decay import decay_batch
            stats = decay_batch(drawers, dry_run=False)
            return TaskResult(
                name="decay",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=stats,
            )
        except Exception as e:
            return TaskResult(name="decay", status="failed", details={"error": str(e)})

    def _task_forget(self, drawers: list[Drawer]) -> TaskResult:
        """自动遗忘：归档+清理低价值记忆"""
        start = time.time()
        try:
            from .adaptive_forgetting import AdaptiveForgetting
            af = AdaptiveForgetting(self.config)
            result = af.auto_forget(drawers)
            return TaskResult(
                name="forget",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=result,
            )
        except Exception as e:
            return TaskResult(name="forget", status="failed", details={"error": str(e)})

    def _task_dream(self, drawers: list[Drawer]) -> TaskResult:
        """梦境巩固：fetch→dedup→link→decay→distill"""
        start = time.time()
        try:
            from .dream_memory import DreamConsolidation
            dream = DreamConsolidation(self.config)
            result = dream.run_dream_cycle(drawers)
            return TaskResult(
                name="dream",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=result,
            )
        except Exception as e:
            return TaskResult(name="dream", status="failed", details={"error": str(e)})

    def _task_curiosity(self, drawers: list[Drawer]) -> TaskResult:
        """好奇心探索：发现知识空白"""
        start = time.time()
        try:
            from .curiosity import CuriosityEngine
            engine = CuriosityEngine(self.config)
            result = engine.explore(drawers)
            return TaskResult(
                name="curiosity",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "gaps_found": result.get("knowledge_gaps", 0),
                    "suggestions": len(result.get("suggestions", [])),
                },
            )
        except Exception as e:
            return TaskResult(name="curiosity", status="failed", details={"error": str(e)})

    def _task_vector_rebuild(self, drawers: list[Drawer]) -> TaskResult:
        """重建向量索引"""
        start = time.time()
        try:
            from .lifecycle import LifecycleManager
            lm = LifecycleManager(self.config)
            result = lm.rebuild_vector_index()
            return TaskResult(
                name="vector_rebuild",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=result,
            )
        except Exception as e:
            return TaskResult(name="vector_rebuild", status="failed", details={"error": str(e)})

    def _task_neural_sleep(self, drawers: list[Drawer]) -> TaskResult:
        """神经记忆巩固：海马体重播"""
        start = time.time()
        try:
            from .neural_memory import get_neural_engine
            engine = get_neural_engine()
            if engine.needs_sleep():
                result = engine.sleep()
                return TaskResult(
                    name="neural_sleep",
                    status="success",
                    duration_ms=(time.time() - start) * 1000,
                    details=result,
                )
            return TaskResult(name="neural_sleep", status="skipped", details={"reason": "not needed"})
        except Exception as e:
            return TaskResult(name="neural_sleep", status="failed", details={"error": str(e)})

    def _task_vector_index(self, drawers: list[Drawer]) -> TaskResult:
        """增量更新向量索引"""
        start = time.time()
        try:
            from .vector_index import get_vector_index
            from .embedding import get_embedding_service

            vi = get_vector_index()
            embed_svc = get_embedding_service()

            indexed = 0
            for d in drawers:
                if d.id in vi._id_map if hasattr(vi, '_id_map') else False:
                    continue
                embedding = d.metadata.get("embedding")
                if not embedding:
                    try:
                        embedding = embed_svc.embed(d.content)
                    except Exception:
                        continue
                if embedding:
                    vi.add(embedding, d.id)
                    indexed += 1

            return TaskResult(
                name="vector_index",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={"indexed": indexed},
            )
        except Exception as e:
            return TaskResult(name="vector_index", status="failed", details={"error": str(e)})

    # ── 主循环 ──

    def tick(self) -> dict:
        """轻量检查：是否需要运行周期"""
        drawers = self._load_drawers()
        now = time.time()
        last_consolidation = self._state.get("last_run", {}).get("decay", 0)
        new_count = self._count_new_since(drawers, last_consolidation)
        old_count = self._count_old_memories(drawers)

        pending = []
        for task, rule in SCHEDULE_RULES.items():
            last = self._state.get("last_run", {}).get(task, 0)
            interval = rule.get("interval_hours", 1) * 3600
            if (now - last) >= interval:
                pending.append(task)

        return {
            "total_memories": len(drawers),
            "new_since_last": new_count,
            "old_memories": old_count,
            "pending_tasks": pending,
            "should_run": len(pending) > 0,
        }

    def run_cycle(self, force: bool = False) -> CycleResult:
        """运行一次完整的自主管理周期"""
        cycle_start = time.time()
        drawers = self._load_drawers()
        results: list[TaskResult] = []

        if not drawers:
            return CycleResult(
                timestamp=datetime.now().isoformat(),
                total_duration_ms=0,
                tasks_run=0,
                tasks_skipped=0,
                tasks_failed=0,
                results=[],
                trigger="no_memories",
            )

        new_count = self._count_new_since(
            drawers, self._state.get("last_run", {}).get("fusion", 0)
        )
        old_count = self._count_old_memories(drawers)

        tasks: list[tuple[str, Callable, bool]] = []

        # 新记忆过多 → 融合
        if force or new_count >= SCHEDULE_RULES["fusion"]["min_new_since_last"]:
            if self._should_run("fusion"):
                tasks.append(("fusion", self._task_fusion, True))

        # 旧记忆过多 → 压缩
        if old_count >= SCHEDULE_RULES["compression"]["min_old_memories"]:
            if self._should_run("compression"):
                tasks.append(("compression", self._task_compression, True))

        # 定期衰减
        if force or self._should_run("decay"):
            tasks.append(("decay", self._task_decay, True))

        # 定期遗忘
        if force or self._should_run("forget"):
            tasks.append(("forget", self._task_forget, True))

        # 梦境巩固
        if force or self._should_run("dream"):
            tasks.append(("dream", self._task_dream, True))

        # 好奇心探索
        if force or self._should_run("curiosity"):
            tasks.append(("curiosity", self._task_curiosity, True))

        # 向量索引重建
        if force or self._should_run("vector_rebuild"):
            tasks.append(("vector_rebuild", self._task_vector_rebuild, True))

        # 神经巩固
        if force or self._should_run("dream"):
            tasks.append(("neural_sleep", self._task_neural_sleep, True))

        trigger = f"new={new_count},old={old_count},force={force}"
        success = 0
        skipped = 0
        failed = 0

        for name, task_fn, _ in tasks:
            try:
                result = task_fn(drawers)
                results.append(result)
                self._mark_done(name)
                if result.status == "success":
                    success += 1
                elif result.status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                logger.info(f"自主任务 {name}: {result.status} ({result.duration_ms:.0f}ms)")
            except Exception as e:
                logger.error(f"自主任务 {name} 异常: {e}")
                results.append(TaskResult(name=name, status="failed", details={"error": str(e)}))
                failed += 1

        self._save_drawers(drawers)
        self._state["total_tasks"] = self._state.get("total_tasks", 0) + len(tasks)
        self._save_state()

        total_ms = (time.time() - cycle_start) * 1000
        cycle = CycleResult(
            timestamp=datetime.now().isoformat(),
            total_duration_ms=round(total_ms, 1),
            tasks_run=success,
            tasks_skipped=skipped,
            tasks_failed=failed,
            results=results,
            trigger=trigger,
        )
        logger.info(
            f"自主周期完成: {success}成功, {skipped}跳过, {failed}失败, "
            f"耗时{total_ms:.0f}ms, 触发: {trigger}"
        )
        return cycle

    def get_status(self) -> dict:
        """获取自主引擎状态"""
        now = time.time()
        last_run = self._state.get("last_run", {})
        pending = []
        for task, rule in SCHEDULE_RULES.items():
            last = last_run.get(task, 0)
            interval = rule.get("interval_hours", 1) * 3600
            remaining = max(0, interval - (now - last))
            pending.append({
                "task": task,
                "last_run": datetime.fromtimestamp(last).isoformat() if last else "never",
                "next_in_minutes": round(remaining / 60, 1),
            })

        drawers = self._load_drawers()
        return {
            "total_memories": len(drawers),
            "total_runs": self._state.get("total_runs", 0),
            "total_tasks": self._state.get("total_tasks", 0),
            "tasks": pending,
        }


# 全局单例
_autonomous_engine: AutonomousMemoryEngine | None = None


def get_autonomous_engine(config: PanguConfig = None) -> AutonomousMemoryEngine:
    global _autonomous_engine
    if _autonomous_engine is None:
        _autonomous_engine = AutonomousMemoryEngine(config)
    return _autonomous_engine


# ── 后台调度器 ──

import threading


class BackgroundScheduler:
    """后台自主调度器 — 在服务器进程内持续运行维护任务"""

    def __init__(self, config: PanguConfig = None, interval_minutes: int = 30):
        self.config = config or PanguConfig()
        self.interval = interval_minutes * 60
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_run: float = 0.0
        self._run_count: int = 0
        self._last_result: dict = {}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pangu-autonomous")
        self._thread.start()
        logger.info(f"Autonomous scheduler started (interval={self.interval}s)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Autonomous scheduler stopped")

    def _loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.interval)
            if self._stop_event.is_set():
                break
            try:
                engine = get_autonomous_engine(self.config)
                tick = engine.tick()
                if tick["should_run"]:
                    cycle = engine.run_cycle()
                    self._last_run = time.time()
                    self._run_count += 1
                    self._last_result = {
                        "timestamp": cycle.timestamp,
                        "tasks_run": cycle.tasks_run,
                        "tasks_failed": cycle.tasks_failed,
                        "duration_ms": cycle.total_duration_ms,
                    }
                    logger.info(
                        f"Autonomous scheduler cycle #{self._run_count}: "
                        f"{cycle.tasks_run} ran, {cycle.tasks_failed} failed, {cycle.total_duration_ms:.0f}ms"
                    )
            except Exception as e:
                logger.error(f"Autonomous scheduler error: {e}")

    def get_status(self) -> dict:
        return {
            "running": self._thread.is_alive() if self._thread else False,
            "interval_minutes": self.interval // 60,
            "total_runs": self._run_count,
            "last_run": datetime.fromtimestamp(self._last_run).isoformat() if self._last_run else "never",
            "last_result": self._last_result,
        }


_scheduler: BackgroundScheduler | None = None


def get_scheduler(config: PanguConfig = None) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(config)
    return _scheduler


# ── 记忆写入钩子 ──

_write_counter = 0
_WRITE_HOOK_THRESHOLD = 10


def on_memory_written():
    """记忆写入后调用 — 达到阈值时触发自主维护"""
    global _write_counter
    _write_counter += 1
    if _write_counter >= _WRITE_HOOK_THRESHOLD:
        _write_counter = 0
        try:
            engine = get_autonomous_engine()
            cycle = engine.run_cycle()
            logger.info(f"Auto-triggered by writes: {cycle.tasks_run} tasks, {cycle.total_duration_ms:.0f}ms")
        except Exception as e:
            logger.debug(f"Write-hook auto-trigger failed: {e}")
