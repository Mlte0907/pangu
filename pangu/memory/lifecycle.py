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
from typing import Optional

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer

logger = logging.getLogger("pangu.memory.lifecycle")


class LifecycleManager:
    """生命周期管理器 — 自动触发记忆维护任务"""

    def __init__(self, config: PanguConfig | None = None):
        self.config = config or PanguConfig.load()
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
        """检查是否需要重建向量索引

        Args:
            threshold: 新增记忆数量阈值
        """
        now = time.time()
        # 每小时最多重建一次，或新增超过阈值
        if (now - self._last_index_rebuild) > 3600:
            return True
        return False

    def run_consolidation(self) -> dict:
        """执行记忆巩固"""
        from pangu.memory.consolidation import MemoryConsolidator

        logger.info("Starting memory consolidation...")

        # 加载记忆
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_memories"}

        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

        # 执行巩固
        consolidator = MemoryConsolidator(self.config)
        stats = consolidator.stats(drawers)

        # 找出需要遗忘的记忆
        forgotten = consolidator.find_forgotten(drawers)
        if forgotten:
            logger.info(f"Found {len(forgotten)} memories to forget")
            # 标记为已遗忘（不删除，降低重要性）
            for d in forgotten:
                d.importance = max(0.1, d.importance * 0.5)
                d.metadata["forgotten_at"] = datetime.now().isoformat()

        # 找出需要复习的记忆
        due_reviews = consolidator.find_due_reviews(drawers)
        if due_reviews:
            logger.info(f"Found {len(due_reviews)} memories due for review")
            # 提升重要性
            for d in due_reviews:
                d.importance = min(5.0, d.importance * 1.1)
                d.metadata["reviewed_at"] = datetime.now().isoformat()

        # 保存更新后的记忆
        with open(drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)

        self._last_consolidation = time.time()
        self._save_state()

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

        # 加载记忆
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_memories"}

        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

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

    def _count_new_memories(self) -> int:
        """自上次巩固以来新增的记忆数"""
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return 0
        try:
            with open(drawers_file, encoding="utf-8") as f:
                drawers = json.load(f)
            if not self._last_consolidation:
                return len(drawers)
            new_count = 0
            for d in drawers:
                created = d.get("created_at", "")
                if created:
                    try:
                        ts = datetime.fromisoformat(created).timestamp()
                        if ts > self._last_consolidation:
                            new_count += 1
                    except (ValueError, TypeError):
                        pass
            return new_count
        except Exception:
            return 0

    def on_memory_added(self) -> dict:
        """新记忆写入后检查是否触发 lifecycle 任务

        触发条件：
        - 新增 >10 条 → 触发 fusion + validation
        - 新增 >20 条 → 触发 compression + KG enrichment
        - 新增 >50 条 → 触发全量 lifecycle
        """
        new_count = self._count_new_memories()
        if new_count < 10:
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

        # 重置计数器
        self._last_consolidation = time.time()
        self._save_state()

        return results

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

        # 自动压缩长记忆
        compress_result = self.run_auto_compress()
        if compress_result.get("compressed", 0) > 0:
            results["compression"] = compress_result

        # KG 实体自动提取
        kg_result = self.run_kg_enrichment()
        if kg_result.get("entities_added", 0) > 0:
            results["kg_enrichment"] = kg_result

        return results

    def run_auto_fusion(self) -> dict:
        """自动融合碎片记忆 — 同主题 >=3 条时触发融合"""
        try:
            from pangu.memory.fusion import FusionEngine
        except ImportError:
            return {"status": "skip", "reason": "fusion module not available"}

        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_memories"}

        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

        if len(drawers) < 3:
            return {"status": "skip", "reason": "too_few_memories"}

        engine = FusionEngine(self.config)
        fused_count = 0

        # 按 wing 分组，每组内做主题融合
        by_wing: dict[str, list[Drawer]] = {}
        for d in drawers:
            by_wing.setdefault(d.wing, []).append(d)

        for wing, wing_drawers in by_wing.items():
            if len(wing_drawers) < 3:
                continue
            # 用高频标签作为主题候选
            tag_freq: dict[str, int] = {}
            for d in wing_drawers:
                for t in d.tags:
                    tag_freq[t] = tag_freq.get(t, 0) + 1
            for tag, count in sorted(tag_freq.items(), key=lambda x: -x[1]):
                if count < 3:
                    continue
                result = engine.fuse_topic(tag, wing_drawers, min_similarity=0.25)
                if result and len(result.key_points) >= 2:
                    # 创建融合记忆
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
                    # 写入 drawers.json（去重检查）
                    existing_ids = {d.id for d in drawers}
                    if fused_drawer.id not in existing_ids:
                        drawers.append(fused_drawer)
                        fused_count += 1

        if fused_count > 0:
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
            logger.info(f"Auto fusion: created {fused_count} fused memories")

        return {"status": "completed", "fused": fused_count, "total": len(drawers)}

    def on_memory_added(self) -> dict:
        """新记忆入库后触发"""
        # 检查是否需要重建索引
        if self.needs_index_rebuild():
            return self.rebuild_vector_index()
        return {"status": "deferred"}

    def run_kg_enrichment(self) -> dict:
        """KG 实体自动提取 — 从记忆中提取实体和关系"""
        try:
            from pangu.memory.knowledge_graph import KnowledgeGraph
        except ImportError:
            return {"status": "skip", "reason": "KG module not available"}

        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_memories"}

        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

        if len(drawers) < 3:
            return {"status": "skip", "reason": "too_few"}

        kg = KnowledgeGraph(self.config)
        result = kg.auto_extract_entities(drawers, max_drawers=50)
        logger.info(f"KG enrichment: {result}")
        return result

    def run_auto_compress(self) -> dict:
        """自动压缩长记忆 — >30天且importance<0.3的长记忆自动压缩"""
        try:
            from pangu.memory.consolidation import MemoryConsolidator
        except ImportError:
            return {"status": "skip", "reason": "consolidation module not available"}

        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"status": "no_memories"}

        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

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

        # 加载记忆
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        drawers = []
        if drawers_file.exists():
            try:
                with open(drawers_file, encoding="utf-8") as f:
                    drawers = [Drawer.from_dict(d) for d in json.load(f)]
            except Exception:
                pass

        stats = consolidator.stats(drawers) if drawers else {}

        return {
            "consolidation_enabled": self.config.consolidation_enabled,
            "consolidation_interval_hours": self.config.consolidation_interval_hours,
            "needs_consolidation": self.needs_consolidation(),
            "last_consolidation": datetime.fromtimestamp(self._last_consolidation).isoformat() if self._last_consolidation else None,
            "last_index_rebuild": datetime.fromtimestamp(self._last_index_rebuild).isoformat() if self._last_index_rebuild else None,
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
