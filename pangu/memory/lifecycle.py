"""盘古 — 生命周期自动触发器

自动执行记忆巩固、向量索引重建等周期性任务。

功能：
1. 定期检查并执行记忆巩固（遗忘、压缩、复习）
2. 新记忆入库后自动更新向量索引
3. 会话结束时自动触发记忆整理
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer

logger = logging.getLogger("pangu.memory.lifecycle")


class LifecycleManager:
    """生命周期管理器 — 自动触发记忆维护任务"""

    def __init__(self, config: PanguConfig | None = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
        self._last_consolidation: float = 0.0
        self._last_index_rebuild: float = 0.0

        # 状态文件
        self._state_file = Path(self.config.palace_path) / "lifecycle_state.json"
        self._load_state()

    def _load_state(self):
        """加载生命周期状态"""
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    state = json.load(f)
                self._last_consolidation = state.get("last_consolidation", 0.0)
                self._last_index_rebuild = state.get("last_index_rebuild", 0.0)
            except Exception:
                pass

    def _save_state(self):
        """保存生命周期状态"""
        state = {
            "last_consolidation": self._last_consolidation,
            "last_index_rebuild": self._last_index_rebuild,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save lifecycle state: {e}")

    def needs_consolidation(self) -> bool:
        """检查是否需要执行巩固"""
        if not self.config.consolidation_enabled:
            return False

        now = time.time()
        interval = self.config.consolidation_interval_hours * 3600
        return (now - self._last_consolidation) > interval

    def needs_index_rebuild(self, threshold: int = 10) -> bool:
        """检查是否需要重建向量索引。

        ⚠ 此前 `threshold` 参数被完全忽略、只按"距上次重建 > 1 小时"判断，
        参数是死参（名为阈值却不生效）。现在：新增记忆数达到阈值即需重建，
        否则退回时间兜底（默认 1 小时），两者取或。

        Args:
            threshold: 新增记忆数量阈值
        """
        now = time.time()
        # 新增超过阈值
        try:
            if self._count_new_memories() >= threshold:
                return True
        except Exception as e:
            logger.debug(f"needs_index_rebuild 计数失败，退回时间判断: {e}")
        # 时间兜底：每小时最多重建一次
        return (now - self._last_index_rebuild) > 3600

    def run_consolidation(self) -> dict:
        """执行记忆巩固。

        ⚠ 写路径（2026-09-18 加固）：**必须走 MemoryStack.update_drawer**，而不是
        读快照后 `json.dump` 全量覆盖。后者是典型的"读-改-写"竞态：从读盘到写回之间
        若有并发写入（服务在跑时随时可能），那些新记忆会被整份覆盖抹掉 —— 与 layers
        里反复出现的空写保护/整份写回是同一类失败模式（那套保护只覆盖 MemoryStack，
        管不到这里的裸文件写）。update_drawer 每次以「重读全库 + 改单条 + 原子写 +
        失效缓存」落盘，与其它写入共享同一语义。
        """
        from pangu.memory.consolidation import MemoryConsolidator
        from pangu.memory.layers import MemoryStack

        logger.info("Starting memory consolidation...")

        # 读全库（经 MemoryStack，拿到缓存与空写保护的语义）。
        # 后台线程无租户作用域 → 自然是全库视角（正确：巩固是系统自身的行为）。
        stack = MemoryStack(self.config)
        stack.invalidate_cache()  # 强制读盘：不能拿 30 秒 TTL 内的旧缓存当基底
        drawers = stack.get_drawers()
        if not drawers:
            return {"status": "no_memories"}

        # 执行巩固
        consolidator = MemoryConsolidator(self.config)
        consolidator.stats(drawers)

        changed: list[Drawer] = []

        # 找出需要遗忘的记忆
        forgotten = consolidator.find_forgotten(drawers)
        if forgotten:
            logger.info(f"Found {len(forgotten)} memories to forget")
            # 标记为已遗忘（不删除，降低重要性）
            for d in forgotten:
                d.importance = max(0.1, d.importance * 0.5)
                d.metadata["forgotten_at"] = datetime.now().isoformat()
                changed.append(d)

        # 找出需要复习的记忆
        due_reviews = consolidator.find_due_reviews(drawers)
        if due_reviews:
            logger.info(f"Found {len(due_reviews)} memories due for review")
            # 提升重要性
            for d in due_reviews:
                d.importance = min(5.0, d.importance * 1.1)
                d.metadata["reviewed_at"] = datetime.now().isoformat()
                changed.append(d)

        # 批量落盘（一次全量读 + 批量改 + 一次全量写 = O(N+M)）。
        # 此前逐条 update_drawer 是 O(N×M)：3000 条库、每轮改 200 条约 14 秒，
        # 批量后同规模 ~0.1 秒（2026-09-19 实测）。整批在同一把 _DRAWERS_IO_LOCK
        # 内完成，比逐条更强（不存在"写了一半"的中间态），也仍满足旧注释的顾虑
        # （"任何时刻不覆盖别人刚写入的内容"）：持锁期间没有其他写者能插进来。
        saved = 0
        if changed:
            try:
                saved = stack.update_drawers_bulk(changed)
            except Exception as e:
                logger.warning(f"巩固批量落盘失败（{len(changed)} 条）: {e}")

        self._last_consolidation = time.time()
        self._save_state()
        drawers_file = self.config.authoritative_drawers_path

        # 神经睡眠巩固（海马体 → 新皮层重播）
        neural_stats = {}
        try:
            from pangu.memory.neural_memory import get_neural_engine

            engine = get_neural_engine()
            if engine.needs_sleep():
                neural_stats = engine.sleep()
                logger.info(f"Neural sleep consolidation: {neural_stats}")
        except Exception as e:
            logger.debug(f"Neural sleep consolidation skipped: {e}")

        result = {
            "status": "completed",
            "total_memories": len(drawers),
            "forgotten": len(forgotten),
            "reviewed": len(due_reviews),
            "neural": neural_stats,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"Consolidation completed: {result}")
        return result

    def rebuild_vector_index(self) -> dict:
        """重建向量索引"""
        from pangu.memory.embedding import get_embedding_service
        from pangu.memory.vector_index import get_vector_index

        logger.info("Rebuilding vector index...")

        # 加载记忆（P0-0 修复：读**权威路径** v2，而不是 v1 palace）
        # 此前读 `self.config.palace_path/drawers.json`（v1）。实测 v1=[] 时
        # 返回 {'total_memories': 0, 'indexed': 0} —— 而自主维护每次"重建索引"
        # 走的都是这条路，等于**反复把向量索引清零**。
        #
        # ⚠ 这里只读权威路径，**不再回退 v1**。
        # 早期版本写过 "v2 不存在则回退读 v1"，那是个有缺陷的写法：
        # 回退只检查"文件存在"而不检查"内容非空"，于是 fresh install
        # （v2 未初始化 + v1 是空 `[]`）时会读进空数组、继续执行到
        # `vector_idx.clear()` 后一条都不加 —— 仍然清零索引。
        # "空 `[]` 不算数据源"这条规则统一由
        # `PanguConfig.load_drawers_nonempty()` 定义，这里直接用它。
        drawers_file = self.config.authoritative_drawers_path
        raw = PanguConfig.load_drawers_nonempty(drawers_file)
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        # 获取嵌入服务和向量索引
        embed_svc = get_embedding_service()
        vector_idx = get_vector_index()

        # 清空并重建
        vector_idx.clear()

        added = 0
        skipped = 0

        for drawer in drawers:
            # 如果已有嵌入，直接使用
            embedding = drawer.metadata.get("embedding")
            if not embedding:
                # 生成嵌入
                try:
                    embedding = embed_svc.embed(drawer.content)
                except Exception as e:
                    logger.warning(f"Failed to generate embedding for {drawer.id[:8]}: {e}")
                    skipped += 1
                    continue

            if embedding:
                vector_idx.add(embedding, drawer.id)
                added += 1

        self._last_index_rebuild = time.time()
        self._save_state()

        result = {
            "status": "completed",
            "total_memories": len(drawers),
            "indexed": added,
            "skipped": skipped,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"Vector index rebuilt: {result}")
        return result

    def run_decay(self) -> dict:
        """整段「读-改-写」持 drawers IO 锁后转内部实现（2026-09-18 加固）。

        为什么要锁：本方法读全库快照、改完**整份写回**。与并发写入交错时，后写者会
        覆盖前者的改动（记忆无声消失、无报错）。锁定义在 layers，与 MemoryStack 的
        写路径（add/update/remove）共用同一把，故单进程内互相串行。
        """
        from pangu.memory.layers import drawers_io_lock

        with drawers_io_lock():
            return self._run_decay_locked()

    def _run_decay_locked(self) -> dict:
        """执行记忆衰减"""
        try:
            from pangu.memory.decay import decay_batch
        except ImportError:
            return {"status": "skip", "reason": "decay module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        drawers_file = self.config.authoritative_drawers_path
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        # 执行衰减
        stats = decay_batch(drawers, dry_run=False)

        # 保存衰减后的记忆
        if stats.get("decayed", 0) > 0 or stats.get("purge_candidates", 0) > 0:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)

        return stats

    def get_decay_stats(self) -> dict:
        """获取衰减统计信息"""
        try:
            from pangu.memory.consolidation import MemoryConsolidator
        except ImportError:
            return {"status": "skip", "reason": "consolidation module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        consolidator = MemoryConsolidator(self.config)
        forgotten = consolidator.find_forgotten(drawers)
        compressible = consolidator.find_compressible(drawers)

        importance_dist = {"high": 0, "medium": 0, "low": 0}
        for d in drawers:
            if d.importance >= 4.0:
                importance_dist["high"] += 1
            elif d.importance >= 2.0:
                importance_dist["medium"] += 1
            else:
                importance_dist["low"] += 1

        return {
            "total": len(drawers),
            "forgotten": len(forgotten),
            "compressible": len(compressible),
            "importance_distribution": importance_dist,
            "average_importance": round(sum(d.importance for d in drawers) / max(len(drawers), 1), 2),
        }

    def _count_new_memories(self) -> int:
        """自上次巩固以来新增的记忆数"""
        drawers = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        if not drawers:
            return 0
        try:
            if not self._last_consolidation:
                return len(drawers)
            return self._count_memories_after(drawers, self._last_consolidation)
        except Exception:
            return 0

    def _count_memories_after(self, drawers: list, after_timestamp: float) -> int:
        new_count = 0
        for d in drawers:
            created = d.get("created_at", "")
            if created:
                try:
                    ts = datetime.fromisoformat(created).timestamp()
                    if ts > after_timestamp:
                        new_count += 1
                except (ValueError, TypeError):
                    pass
        return new_count

    def on_memory_added(self) -> dict:
        """新记忆写入后检查是否触发 lifecycle 任务

        触发条件：
        - 新增 >10 条 → 触发 fusion + validation
        - 新增 >20 条 → 触发 compression + KG enrichment
        - 新增 >50 条 → 触发全量 lifecycle
        """
        new_count = self._count_new_memories()

        # 神经记忆：海马体负载超过 50% 时自动巩固
        neural_result = {}
        try:
            from pangu.memory.neural_memory import get_neural_engine

            engine = get_neural_engine()
            if engine.needs_sleep() or engine.hippocampus.load_factor > 0.5:
                neural_result = engine.sleep()
        except Exception:
            pass

        if new_count < 10 and not neural_result:
            return {"status": "deferred", "new_count": new_count}

        results = {"new_count": new_count}

        if new_count >= 10:
            fusion_result = self.run_auto_fusion()
            if fusion_result.get("fused", 0) > 0:
                results["fusion"] = fusion_result

            # 验证记忆
            try:
                from pangu.memory.memory_validator import MemoryValidator

                validator = MemoryValidator(self.config)
                val_result = validator.validate_all()
                results["validation"] = val_result
            except Exception:
                pass

        if new_count >= 20:
            compress_result = self.run_auto_compress()
            if compress_result.get("compressed", 0) > 0:
                results["compression"] = compress_result

            kg_result = self.run_kg_enrichment()
            if kg_result.get("entities_added", 0) > 0:
                results["kg_enrichment"] = kg_result

        if new_count >= 50:
            if self.needs_consolidation():
                results["consolidation"] = self.run_consolidation()
            if self.needs_index_rebuild():
                results["index_rebuild"] = self.rebuild_vector_index()

        # 神经记忆巩固结果
        if neural_result:
            results["neural_sleep"] = neural_result

        # 重置计数器
        self._last_consolidation = time.time()
        self._save_state()

        return results

    def run_auto_decay(self) -> dict:
        """整段「读-改-写」持 drawers IO 锁后转内部实现（2026-09-18 加固）。

        为什么要锁：本方法读全库快照、改完**整份写回**。与并发写入交错时，后写者会
        覆盖前者的改动（记忆无声消失、无报错）。锁定义在 layers，与 MemoryStack 的
        写路径（add/update/remove）共用同一把，故单进程内互相串行。
        """
        from pangu.memory.layers import drawers_io_lock

        with drawers_io_lock():
            return self._run_auto_decay_locked()

    def _run_auto_decay_locked(self) -> dict:
        """自动衰减：定期降低未访问记忆的重要性"""
        try:
            from pangu.memory.decay import decay_batch
        except ImportError:
            return {"status": "skip", "reason": "decay module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]
        # 写回路径必须与读取路径**同源**（P0-0：读 v2 就必须写 v2）
        drawers_file = self.config.authoritative_drawers_path

        stats = decay_batch(drawers, dry_run=False)

        if stats.get("decayed", 0) > 0 or stats.get("purge_candidates", 0) > 0:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)

        return stats

    def on_session_end(self) -> dict:
        """会话结束时触发的生命周期任务"""
        results = {}

        # 检查是否需要巩固
        if self.needs_consolidation():
            results["consolidation"] = self.run_consolidation()

        # 检查是否需要重建索引
        if self.needs_index_rebuild():
            results["index_rebuild"] = self.rebuild_vector_index()

        # 自动融合碎片记忆
        fusion_result = self.run_auto_fusion()
        if fusion_result.get("fused", 0) > 0:
            results["fusion"] = fusion_result

        # LLM 压缩旧记忆
        llm_compress_result = self.run_llm_compress()
        if llm_compress_result.get("compressed", 0) > 0:
            results["llm_compression"] = llm_compress_result

        # 自动压缩长记忆
        compress_result = self.run_auto_compress()
        if compress_result.get("compressed", 0) > 0:
            results["compression"] = compress_result

        # 记忆衰减
        decay_result = self.run_decay()
        if decay_result.get("decayed", 0) > 0:
            results["decay"] = decay_result

        # 自动衰减（定期降低未访问记忆的重要性）
        auto_decay_result = self.run_auto_decay()
        if auto_decay_result.get("decayed", 0) > 0:
            results["auto_decay"] = auto_decay_result

        # KG 实体自动提取
        kg_result = self.run_kg_enrichment()
        if kg_result.get("entities_added", 0) > 0:
            results["kg_enrichment"] = kg_result

        # 跨会话记忆整合
        cross_result = self.run_cross_session()
        if cross_result.get("cross_session_links", 0) > 0:
            results["cross_session"] = cross_result

        # 神经记忆巩固
        try:
            from pangu.memory.neural_memory import get_neural_engine

            engine = get_neural_engine()
            if engine.needs_sleep() or engine.hippocampus.load_factor > 0.5:
                neural_result = engine.sleep()
                if neural_result.get("consolidated", 0) > 0:
                    results["neural_sleep"] = neural_result
        except Exception:
            pass

        return results

    def _fuse_tag_in_wing(self, tag: str, count: int, wing: str, wing_drawers: list, engine, drawers: list) -> int:
        if count < 3:
            return 0
        result = engine.fuse_topic(tag, wing_drawers, min_similarity=0.25)
        if not (result and len(result.key_points) >= 2):
            return 0
        fused_drawer = Drawer(
            id=f"fused-{wing}-{tag}",
            content=f"[融合] {result.topic}: {'; '.join(result.key_points[:3])}",
            wing=wing,
            room="fused",
            importance=min(4.0, 2.0 + len(result.source_memories) * 0.3),
            tags=[tag, "fused"],
            author="lifecycle-fusion",
            created_at=datetime.now().isoformat(),
            metadata={
                "source": "auto_fusion",
                "fused_from": result.source_memories[:10],
                "confidence": result.confidence,
            },
        )
        existing_ids = {d.id for d in drawers}
        if fused_drawer.id not in existing_ids:
            drawers.append(fused_drawer)
            return 1
        return 0

    def _process_wing_fusion(self, wing: str, wing_drawers: list, engine, drawers: list) -> int:
        if len(wing_drawers) < 3:
            return 0
        tag_freq: dict[str, int] = {}
        for d in wing_drawers:
            for t in d.tags:
                tag_freq[t] = tag_freq.get(t, 0) + 1
        fused_count = 0
        for tag, count in sorted(tag_freq.items(), key=lambda x: -x[1]):
            fused_count += self._fuse_tag_in_wing(tag, count, wing, wing_drawers, engine, drawers)
        return fused_count

    def run_auto_fusion(self) -> dict:
        try:
            from pangu.memory.fusion import FusionEngine
        except ImportError:
            return {"status": "skip", "reason": "fusion module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        drawers_file = self.config.authoritative_drawers_path
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        if len(drawers) < 3:
            return {"status": "skip", "reason": "too_few_memories"}

        engine = FusionEngine(self.config)
        fused_count = 0

        # 按 wing 分组，每组内做主题融合
        by_wing: dict[str, list[Drawer]] = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            fused_count += self._process_wing_fusion(wing, wing_drawers, engine, drawers)

        if fused_count > 0:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
            logger.info(f"Auto fusion: created {fused_count} fused memories")

        return {"status": "completed", "fused": fused_count, "total": len(drawers)}

    # NOTE（2026-09-19）：此处原有一个简化版 on_memory_added（只重建索引），它覆盖了
    # 第 328 行的完整版（含 fusion / compression / KG enrichment 触发链）——Python
    # 同名后定义覆盖先定义，完整钩子因此从未执行过。已删除覆盖版。
    # 另外两个钩子（on_memory_added / on_session_end）在服务进程中都没有调用方
    # （on_session_end 只有 CLI 的 run_lifecycle_check 会调），KG 抽取已改由自主
    # 周期任务 kg_enrichment 承担，见 autonomous.py。

    def run_cross_session(self) -> dict:
        """跨会话记忆整合"""
        try:
            from pangu.memory.cross_session import CrossSessionIntegrator

            integrator = CrossSessionIntegrator(self.config)
        except ImportError:
            return {"status": "skip", "reason": "cross_session module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        if len(drawers) < 5:
            return {"status": "skip", "reason": "too_few_memories"}

        # 使用最近 10 条记忆作为新会话记忆
        new_drawers = drawers[-10:] if len(drawers) > 10 else drawers
        links = integrator.find_cross_session_links(new_drawers, drawers)

        if links:
            # 写入 KG
            added = integrator.build_kg_links(links)
            return {"status": "completed", "cross_session_links": len(links), "kg_links_added": added}

        return {"status": "completed", "cross_session_links": 0}

    def run_kg_enrichment(self) -> dict:
        """KG 实体自动提取 — 从记忆中提取实体和关系"""
        try:
            from pangu.memory.knowledge_graph import KnowledgeGraph
        except ImportError:
            return {"status": "skip", "reason": "KG module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        if len(drawers) < 3:
            return {"status": "skip", "reason": "too_few"}

        kg = KnowledgeGraph(self.config)
        result = kg.auto_extract_entities(drawers, max_drawers=50)
        logger.info(f"KG enrichment: {result}")
        return result

    def run_llm_compress(self) -> dict:
        """LLM 驱动的记忆压缩"""
        try:
            from pangu.memory.compression import get_compressor

            compressor = get_compressor(self.config)
        except ImportError:
            return {"status": "skip", "reason": "compression module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        drawers_file = self.config.authoritative_drawers_path
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        results = compressor.batch_compress(drawers)
        if not results:
            return {"status": "skip", "reason": "no compressible memories"}

        # 保存压缩结果
        for r in results:
            for d in drawers:
                if d.id == r.memory_id:
                    d.content = r.compressed
                    d.metadata["compressed"] = True
                    d.metadata["original_content"] = r.original
                    d.metadata["compression_ratio"] = r.compression_ratio
                    break

        with open(drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)

        return {"status": "completed", "compressed": len(results), "total": len(drawers)}

    def run_auto_compress(self) -> dict:
        """自动压缩长记忆"""
        try:
            from pangu.memory.consolidation import MemoryConsolidator
        except ImportError:
            return {"status": "skip", "reason": "consolidation module not available"}

        # P0-0：读权威路径 v2（此前读 v1 → 维护任务在空库上空转）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        drawers_file = self.config.authoritative_drawers_path
        if not raw:
            return {"status": "no_memories"}
        drawers = [Drawer.from_dict(d) for d in raw]

        consolidator = MemoryConsolidator(self.config)
        compressible = consolidator.find_compressible(drawers)

        compressed = 0
        for d in compressible:
            # 只压缩长内容
            if len(d.content) <= 100:
                continue
            # 检查是否已压缩过
            if d.metadata.get("compressed"):
                continue
            old_content = d.content
            d.content = consolidator.compress_memory(d)
            d.metadata["compressed"] = True
            d.metadata["original_length"] = len(old_content)
            # ⚠ 必须留原文：compress_memory 是**有损**的（关键句提取 + 截断），
            # 此前只存长度不存内容 ⇒ 一旦压缩就永久丢失。与 run_llm_compress
            # 的 original_content 口径保持一致，便于事后恢复/审计。
            d.metadata.setdefault("original_content", old_content)
            d.metadata["compressed_at"] = datetime.now().isoformat()
            compressed += 1

        if compressed > 0:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
            logger.info(f"Auto compressed {compressed} memories")

        return {"status": "completed", "compressed": compressed, "total": len(drawers)}

    def get_status(self) -> dict:
        """获取生命周期状态"""
        from pangu.memory.consolidation import MemoryConsolidator

        consolidator = MemoryConsolidator(self.config)

        # 加载记忆（P0-0：读权威路径 v2，此前读 v1 → 统计恒为空）
        raw = PanguConfig.load_drawers_nonempty(self.config.authoritative_drawers_path)
        drawers = [Drawer.from_dict(d) for d in raw]

        stats = consolidator.stats(drawers) if drawers else {}

        return {
            "consolidation_enabled": self.config.consolidation_enabled,
            "consolidation_interval_hours": self.config.consolidation_interval_hours,
            "needs_consolidation": self.needs_consolidation(),
            "last_consolidation": datetime.fromtimestamp(self._last_consolidation).isoformat()
            if self._last_consolidation
            else None,
            "last_index_rebuild": datetime.fromtimestamp(self._last_index_rebuild).isoformat()
            if self._last_index_rebuild
            else None,
            "memories": stats,
        }


def run_lifecycle_check():
    """运行一次生命周期检查"""
    manager = LifecycleManager()
    results = manager.on_session_end()

    if results:
        print("=== 生命周期检查完成 ===")
        for task, result in results.items():
            print(f"  {task}: {result.get('status', 'unknown')}")
    else:
        print("无需执行维护任务")


if __name__ == "__main__":
    run_lifecycle_check()
