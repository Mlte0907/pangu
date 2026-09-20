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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

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
    "collect": {
        "interval_hours": 2,
    },
    # ── P2-1 Step 2：高级推理接入 ──
    # anomaly_detection 24h：detect_anomalies 跑 4 遍时间分桶，实测 92 条
    #   记忆约 0.5s；它是"发现异常"而非高频维护，每天一次足够。
    # knowledge_gaps 12h：identify_knowledge_gaps 实测 <0.01s（很轻），
    #   但结果噪声多（实测 264 条），半天一次避免频繁刷日志。
    "anomaly_detection": {
        "interval_hours": 24,
    },
    "knowledge_gaps": {
        "interval_hours": 12,
    },
    # KG 实体抽取（2026-09-19 接线）：
    # 此前它挂在 LifecycleManager 的两个钩子上（on_memory_added / on_session_end），
    # 但（a）on_memory_added 被同文件的简化版重复定义覆盖、（b）on_session_end 在
    # 服务里从未被调用（只有 CLI run_lifecycle_check 会调）—— 结果服务跑了 172 轮
    # 维护，KG 里只有 4 个实体。正则抽取成本毫秒级（50 条/轮），6 小时一次足够。
    "kg_enrichment": {
        "interval_hours": 6,
    },
    # 夜间巩固（2026-09-20 接线）：巩固的完整实现此前只有 mcp_server 一个宿主，
    # API 服务没有等价循环 —— MCP 客户端全部下线后巩固随之停摆（面板停在"1 天前"）。
    # 挂进引擎统一调度；任务内部自查 03:00–05:00 窗口与到期，与 mcp 循环语义一致。
    # 注意：此任务**不走** _should_run 的 24h 门（否则在窗口外被标记 done 后，
    # 下一次尝试已是 24h 后，会永远错过窗口），注册处为无条件执行 + 任务内自检。
    "consolidation": {
        "interval_hours": 24,
    },
    # 准入复检（2026-09-20 接线）：毕业门只在记忆写入时判一次，之后哪怕被成功召回
    # 也没人重新过门，pending_review 只增不减（实测积压 76 条）。定期重跑
    # _admission_gate，来源/反馈信号齐了的记忆自动毕业。
    "readmission": {
        "interval_hours": 6,
    },
    # 知识结晶（2026-09-20 接线）：记忆→知识的蒸馏此前只有 MCP 工具/CLI 入口，
    # 服务内从未自动运行（实测 180 条记忆仅 9 条手动建的知识）。定期把「已验证」
    # 的记忆（毕业 / 有正向召回反馈 / 高重要度）按主题聚合成知识条目。
    "crystallize": {
        "interval_hours": 12,
    },
}


class AutonomousMemoryEngine:
    """自主记忆管理引擎 — 自动调度所有记忆维护任务"""

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
        # P0-0 修复：记忆主存必须用**权威路径**（v2），不能用 v1 palace。
        #
        # 此前 `self._palace_path = Path(self.config.palace_path)` 硬编码 v1，
        # 配合 `get_autonomous_engine()` 默认 `PanguConfig.load()`（也是 v1），
        # 导致自主维护读到空的 v1（实测 0 条），且 `run_cycle()` 末尾会
        # **无条件 `self._save_drawers(drawers)` 回写 v1**。
        #
        # 这是默认 28 工具里的第三条受影响路径：`pangu_add_memory` 第 10 次
        # 调用 → `on_memory_written()` → run_cycle → 以 0 条为基线回写。
        #
        # 状态文件仍留在原 palace 目录（它是运维状态，不是记忆主存），
        # 避免迁移既有 autonomous_state.json 造成状态丢失。
        self._palace_path = Path(self.config.memory_data_dir)
        self._drawers_file = self.config.authoritative_drawers_path
        self._state_file = Path(self.config.palace_path) / "autonomous_state.json"
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

    def _disk_has_records(self) -> bool:
        """权威存储当前是否已有记录（用于空写保护）。

        注意 `_load_drawers()` 的 `except: return []` 是**静默**的——读取失败
        与"真的没有记忆"返回同一个值，所以守卫不能依赖 `_load_drawers()`。
        这里直接看磁盘实际内容。
        """
        try:
            if self._drawers_file.exists():
                with open(self._drawers_file, encoding="utf-8") as f:
                    return bool(json.load(f))
        except Exception:  # noqa: BLE001
            return False
        return False

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
        """自动融合：同主题 >=3 条时融合成知识条目。

        2026-09-20 修两处：
        1. 调用签名错误：`engine.fuse_topic(topic, group, drawers)` 把第三个位置参数
           当成了 `min_similarity`（float），实际传入一个 list，比较时抛 TypeError
           并被 fuse_topic 内部的 except 吞掉 —— 相似度融合通道等于从未生效。
        2. 结果无处可去：`fused` 只自增计数，融合出的知识从未落盘（进程退出即丢）。
           现在写入 KnowledgeEngine（与知识结晶同一存储），并带上来源记忆，便于前端
           「知识」标签页展示与去重（source_memories 已覆盖则跳过）。
        """
        start = time.time()
        try:
            from .fusion import FusionEngine

            engine = FusionEngine(self.config)
            topic_groups = engine._group_by_keywords(drawers)

            covered: set[str] = set()
            try:
                from .knowledge import get_knowledge_engine

                knowledge_engine = get_knowledge_engine()
                for entry in knowledge_engine.list_knowledge():
                    covered.update(entry.source_memories or [])
            except Exception as e:
                logger.debug(f"融合：读取已知知识失败（按无覆盖处理）: {e}")
                knowledge_engine = None

            fused = 0
            for topic, group in topic_groups.items():
                if len(group) < 3:
                    continue
                result = engine.fuse_topic(topic, group)  # 只传 topic + group，用默认阈值
                if not result:
                    continue
                ids = set(result.source_memories or [])
                if not ids or ids <= covered:
                    continue  # 这组记忆已被某条知识覆盖，避免重复结晶
                if knowledge_engine is None:
                    fused += 1  # 无知识库可用时至少如实计数
                    continue
                knowledge_engine.create_knowledge(
                    title=f"【{topic}】{len(group)} 条记忆的融合",
                    content=result.summary,
                    category="insight",
                    source_memories=sorted(ids),
                    tags=[topic],
                    confidence=result.confidence,
                    metadata={"generated_by": "fusion", "at": result.created_at},
                )
                covered.update(ids)
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

    def _task_kg_enrichment(self, drawers: list[Drawer]) -> TaskResult:
        """KG 实体自动提取（正则规则，成本毫秒级）。

        2026-09-19 接线：此前该能力只挂在 LifecycleManager.on_memory_added /
        on_session_end 两个钩子上，而两个钩子在服务里都到不了（一个被同文件简化版
        重复定义覆盖，另一个只有 CLI 调用）—— 服务跑了 172 轮维护，KG 里只有 4 个
        实体。接入自主周期后，图谱随记忆量自然生长。
        """
        start = time.time()
        try:
            from .knowledge_graph import KnowledgeGraph

            kg = KnowledgeGraph(self.config)
            result = kg.auto_extract_entities(drawers, max_drawers=50)
            return TaskResult(
                name="kg_enrichment",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=result,
            )
        except Exception as e:
            return TaskResult(name="kg_enrichment", status="failed", details={"error": str(e)})

    def _task_consolidation(self, drawers: list[Drawer]) -> TaskResult:
        """夜间巩固：03:00–05:00 窗口内且到期时执行 LifecycleManager.run_consolidation。

        为什么在引擎里做（2026-09-20）：巩固此前只有 mcp_server 一个宿主，API 服务
        没有等价循环，MCP 客户端下线后巩固随之停摆。挂进引擎由统一调度驱动；
        窗口外/未到期返回 skipped，不产生副作用。

        注意：run_consolidation 会自己读写权威存储，结束后必须从磁盘**重载** drawers
        （原地替换列表内容），否则本周期末尾的 _save_drawers 会用旧的内存副本
        把巩固结果覆盖回去。
        """
        from datetime import datetime

        start = time.time()
        hour = datetime.now().hour
        if not (3 <= hour < 5):
            return TaskResult(
                name="consolidation",
                status="skipped",
                duration_ms=(time.time() - start) * 1000,
                details={"reason": f"outside 03:00-05:00 window (hour={hour})"},
            )
        try:
            from .lifecycle import LifecycleManager

            mgr = LifecycleManager(self.config)
            if not mgr.needs_consolidation():
                return TaskResult(
                    name="consolidation",
                    status="skipped",
                    duration_ms=(time.time() - start) * 1000,
                    details={"reason": "not due"},
                )
            result = mgr.run_consolidation()
            drawers[:] = self._load_drawers()  # 重载，防本周期末尾回写旧副本
            return TaskResult(
                name="consolidation",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={"result": result},
            )
        except Exception as e:
            return TaskResult(name="consolidation", status="failed", details={"error": str(e)})

    def _task_readmission(self, drawers: list[Drawer]) -> TaskResult:
        """准入复检：对 pending_review 的记忆重跑四问准入门，信号齐了自动毕业。

        毕业（admission=graduated + visibility=public）要求「有来源指针 + 有正向反馈」，
        而门此前只在写入时判一次 —— 之后哪怕被反复成功召回也无人重判，pending 只增
        不减。此任务定期把积压的 pending 记忆重新过门（复用 ingestion._admission_gate
        单点判定），有信号毕业、没信号保持 pending 等使用信号。
        """
        start = time.time()
        try:
            from .ingestion import _admission_gate

            rechecked = graduated = 0
            for d in drawers:
                md = d.metadata if isinstance(d.metadata, dict) else {}
                if md.get("admission") != "pending_review":
                    continue
                rechecked += 1
                _admission_gate(d, None, getattr(d, "id", ""))
                if isinstance(d.metadata, dict) and d.metadata.get("admission") == "graduated":
                    graduated += 1
            return TaskResult(
                name="readmission",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={"rechecked": rechecked, "graduated": graduated},
            )
        except Exception as e:
            return TaskResult(name="readmission", status="failed", details={"error": str(e)})

    def _task_crystallize(self, drawers: list[Drawer]) -> TaskResult:
        """知识结晶（LLM 精炼版，2026-09-20）：把「已验证」的记忆聚合成知识库条目。

        执行条件：04:00–06:00 低繁忙窗口内、距上次 ≥20h（窗口/到期自检，与
        consolidation 同理不走 _should_run，否则会永远错过窗口）。

        模型策略：执行时动态 GET /models 发现列表（平台列表会更新，不写死），
        按家族偏好序排序（deepseek 优先、minicpm 兜底），排除 mineru（文档解析
        模型）；单模型失败（繁忙/超时/输出不可解析）自动降下一个；全部 LLM
        不可用时回退规则式提取，结晶永远有产出。

        护栏：提示词限定「只综合给定记忆，不得补充」；分类受限于 4 枚举（LLM
        越枚举时改用规则分类）；tags 直接继承来源记忆；条目 metadata 记录生成
        模型与时间。知识写走 KnowledgeEngine 自己的存储，不经过 _save_drawers。
        """
        from datetime import datetime

        start = time.time()
        hour = datetime.now().hour
        last = float((self._state.get("last_run") or {}).get("crystallize") or 0)
        if not (4 <= hour < 6) or (time.time() - last) < 20 * 3600:
            return TaskResult(
                name="crystallize",
                status="skipped",
                duration_ms=(time.time() - start) * 1000,
                details={"reason": f"outside 04:00-06:00 window or not due (hour={hour})"},
            )
        try:
            return self._crystallize_impl(drawers, start)
        except Exception as e:
            return TaskResult(name="crystallize", status="failed", details={"error": str(e)})

    def _crystallize_impl(self, drawers: list[Drawer], start: float) -> TaskResult:
        from datetime import datetime

        from .knowledge import get_knowledge_engine

        engine = get_knowledge_engine()
        existing = engine.list_knowledge()
        covered: set[str] = set()
        for e in existing:
            covered.update(e.source_memories or [])

        pool = []
        for d in drawers:
            md = d.metadata if isinstance(d.metadata, dict) else {}
            if (
                md.get("admission") == "graduated"
                or md.get("last_feedback") in ("recall_success", "verified")
                or (d.importance or 0) >= 1.5
            ):
                pool.append(d)
        if len(pool) < 2:
            return TaskResult(
                name="crystallize",
                status="skipped",
                duration_ms=(time.time() - start) * 1000,
                details={"reason": f"verified pool too small ({len(pool)})"},
            )

        tag_groups: dict[str, list] = {}
        for d in pool:
            for tag in (d.tags or [])[:5]:
                tag_groups.setdefault(tag, []).append(d)

        def _rule_category(blob: str) -> str:
            if any(k in blob for k in ("修复", "排查", "问题", "bug", "失败", "错误")):
                return "solution"
            if any(k in blob for k in ("教训", "踩坑", "坑", "警告", "注意")):
                return "insight"
            if any(k in blob for k in ("指南", "教程", "用法", "接入", "配置")):
                return "guide"
            # 2026-09-20：不再硬塞 best_practice —— 关键词不匹配时归「其他」
            return "other"

        # LLM 端点与动态模型发现（列表随平台更新；不可用 → 规则式兜底）
        llm = self._llm_endpoint()
        models = self._llm_discover_models(*llm) if llm else []
        system_prompt = (
            "你是盘古记忆系统的知识结晶引擎。只允许综合给定的记忆内容，"
            "不得补充外部信息或推测。输出 JSON："
            '{"title": "简洁标题", "content": "250字内的综合知识", '
            '"category": "best_practice|solution|guide|insight 四选一，'
            '内容不属于任何一类时选 other"}'
        )

        created = []
        model_used_count: dict[str, int] = {}
        used_ids: set[str] = set()
        for tag, group in sorted(tag_groups.items(), key=lambda x: -len(x[1])):
            if len(created) >= 10:
                break
            group = [d for d in group if d.id not in used_ids]
            if len(group) < 2:
                continue
            ids = {d.id for d in group}
            if ids <= covered:
                continue
            texts = []
            for d in group[:3]:
                first = str(d.content or "").strip().split("\n")[0][:60]
                if first:
                    texts.append(first)
            if len(texts) < 2:
                continue

            # ── LLM 精炼：按偏好序尝试，单模型失败自动降级 ──
            title = content = None
            category = None
            model_used = None
            mem_text = "\n\n".join(f"- [{d.wing}] {str(d.content or '')[:200]}" for d in group[:8])
            for model in models:
                try:
                    raw = self._llm_chat(
                        llm[0],
                        llm[1],
                        model,
                        system_prompt,
                        f"把以下 {min(len(group), 8)} 条记忆结晶为一条可复用知识：\n\n{mem_text}",
                    )
                    obj = self._extract_json(raw)
                    if not obj or not str(obj.get("title", "")).strip() or not str(obj.get("content", "")).strip():
                        continue
                    title = str(obj["title"]).strip()[:80]
                    content = str(obj["content"]).strip()[:600]
                    category = str(obj.get("category", "")).strip().lower()
                    model_used = model
                    break
                except Exception:
                    continue  # 繁忙/超时/输出不可解析 → 降下一个模型

            if not title:
                # 规则式兜底（LLM 全败或未配置）
                title = f"【{tag}】{len(group)} 条经验的结晶"
                content = "；".join(texts)
            if category not in self._LLM_CATEGORIES:
                category = _rule_category(" ".join(texts) + " " + tag)

            entry = engine.create_knowledge(
                title=title,
                content=content,
                category=category,
                source_memories=sorted(ids),
                tags=sorted({tag, *[t for d in group[:3] for t in (d.tags or []) if t != tag]})[:5],
                confidence=min(0.95, 0.5 + len(group) * 0.08),
                metadata={"model": model_used or "rule-based", "generated_at": datetime.now().isoformat()},
            )
            used_ids.update(ids)
            model_used_count[entry.metadata.get("model", "?")] = (
                model_used_count.get(entry.metadata.get("model", "?"), 0) + 1
            )
            created.append(entry.id)

        return TaskResult(
            name="crystallize",
            status="success",
            duration_ms=(time.time() - start) * 1000,
            details={
                "pool": len(pool),
                "created": len(created),
                "models_available": len(models),
                "by_model": model_used_count,
                "ids": created,
            },
        )

    # ── LLM 知识结晶辅助（2026-09-20）──
    # 家族偏好序：deepseek 质量优先，minicpm 作最稳兜底；mineru 是文档解析模型排除。
    # 未识别的家族不盲用 —— 平台列表新增模型时在此加一行家族名即可。
    _LLM_PREFERENCE = ("deepseek", "minicpm")
    _LLM_EXCLUDE = ("mineru",)
    # 4 个预设类 + other 兜底（2026-09-20：内容不属于任何预设类时归「其他」，不硬塞）
    _LLM_CATEGORIES = ("best_practice", "solution", "guide", "insight", "other")
    _LLM_TIMEOUT = 60  # 单次调用超时（秒）

    def _llm_endpoint(self):
        """读 LLM 端点配置（base_url + key）。未配置返回 None。"""
        try:
            cfg = PanguConfig.load()
            base = str(cfg.llm_base_url or "").rstrip("/")
            if not base:
                return None
            key = str(getattr(cfg, "llm_api_key", "") or "")
            if not key:
                from pathlib import Path as _Path

                kf = _Path(str(cfg.llm_api_key_file or ""))
                if kf.exists():
                    key = kf.read_text().strip()
            return (base, key) if key else None
        except Exception:
            return None

    def _llm_discover_models(self, base: str, key: str) -> list[str]:
        """动态发现可用对话模型（GET /models，列表随平台更新，不写死）。

        排序：按 _LLM_PREFERENCE 家族序（同家族保持平台返回顺序，新版本在前）；
        排除 _LLM_EXCLUDE；未识别家族不盲用。
        """
        import urllib.request

        req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data") or data.get("models") or []
        names = [m.get("id") if isinstance(m, dict) else str(m) for m in items]
        names = [n for n in names if n]

        ranked: list[str] = []
        for family in self._LLM_PREFERENCE:
            for n in names:
                low = n.lower()
                if family in low and not any(x in low for x in self._LLM_EXCLUDE) and n not in ranked:
                    ranked.append(n)
        return ranked

    def _llm_chat(self, base: str, key: str, model: str, system: str, user: str) -> str:
        """单次对话补全（同步，调度线程内直跑）。失败抛异常由调用方降级。"""
        import urllib.request

        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            }
        ).encode()
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        return str((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "")

    @staticmethod
    def _extract_json(content: str) -> dict | None:
        """从 LLM 输出提取 JSON（剥 <think> 思考泄漏与代码围栏；失败返回 None）。"""
        import re as _re

        text = _re.sub(r"<think>.*?</think>", "", content, flags=_re.S)
        text = _re.sub(r"```(?:json)?", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

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
        """增量更新向量索引（P2-1 Step 3：改为批量嵌入 + 批量入库）

        改动前：对每条记忆单独 `embed_svc.embed()` + 单独 `vi.add()`。
          `.add()` 每次都会落盘（`_save()`），92 条记忆 = 92 次 ONNX 推理
          + 92 次磁盘写入。
        改动后：用 `BatchProcessor.batch_encode` 一次性批量编码（优先走后端
          `embed_batch`），再用 `vi.add_batch()` 一次性入库（只落盘一次）。

        另注：原有跳过条件
            `if d.id in vi._id_map if hasattr(vi, "_id_map") else False`
        恒为 False —— `VectorIndex` 从未定义过 `_id_map`（全文件 0 处），
        所以该"增量"判断实际上是死的，每次都会全量重嵌。批量化后这一步
        的成本大幅下降，故本次不动该语义（避免改变行为）。
        """
        start = time.time()
        try:
            from .embedding import get_embedding_service
            from .performance import BatchProcessor
            from .vector_index import get_vector_index

            vi = get_vector_index()
            embed_svc = get_embedding_service()

            # 1) 分流：已有预置 embedding 的直接用；其余收集文本待批量编码
            ready: list[tuple[str, list[float]]] = []
            texts: list[str] = []
            text_ids: list[str] = []
            for d in drawers:
                embedding = d.metadata.get("embedding")
                if embedding:
                    ready.append((d.id, embedding))
                else:
                    texts.append(d.content or "")
                    text_ids.append(d.id)

            # 2) 批量编码（batch_encode 内部优先调用后端 embed_batch）
            if texts:
                vecs = BatchProcessor.batch_encode(texts, embed_svc.embed, batch_size=32)
                for did, vec in zip(text_ids, vecs):
                    # 降级路径对失败项会返回全 0 向量，需跳过（否则污染索引）
                    if vec and any(vec):
                        ready.append((did, vec))

            # 3) 批量入库（只落盘一次）
            indexed = 0
            if ready:
                indexed = vi.add_batch([v for _, v in ready], [i for i, _ in ready])

            return TaskResult(
                name="vector_index",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "indexed": indexed,
                    "candidates": len(drawers),
                    "batched": len(ready),
                },
            )
        except Exception as e:
            return TaskResult(name="vector_index", status="failed", details={"error": str(e)})

    def _task_collect(self, drawers: list[Drawer]) -> TaskResult:
        """自动采集：从文件/目录/日志提取记忆"""
        start = time.time()
        try:
            from .collector import get_collector

            collector = get_collector(self.config)
            result = collector.collect_all_sources(min_importance=0.3)
            return TaskResult(
                name="collect",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details=result,
            )
        except Exception as e:
            return TaskResult(name="collect", status="failed", details={"error": str(e)})

    def _task_anomaly_detection(self, drawers: list[Drawer]) -> TaskResult:
        """异常检测：频率/内容/标签集中度/创建间隔四通道。

        P2-1 Step 2：此前 advanced_reasoning.detect_anomalies 因 `d.title`
        （Drawer 无该字段）在有内容的记忆上必抛 AttributeError，故从未被调度。
        bug 修复后接入。
        """
        start = time.time()
        try:
            from .advanced_reasoning import AdvancedReasoning

            engine = AdvancedReasoning(self.config)
            alerts = engine.detect_anomalies(drawers)
            by_severity: dict[str, int] = {}
            for a in alerts:
                by_severity[a.severity.value] = by_severity.get(a.severity.value, 0) + 1
            return TaskResult(
                name="anomaly_detection",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "total_alerts": len(alerts),
                    "by_severity": by_severity,
                },
            )
        except Exception as e:
            return TaskResult(name="anomaly_detection", status="failed", details={"error": str(e)})

    def _task_knowledge_gaps(self, drawers: list[Drawer]) -> TaskResult:
        """知识缺口识别：孤立主题 / 薄弱主题。"""
        start = time.time()
        try:
            from .advanced_reasoning import AdvancedReasoning

            engine = AdvancedReasoning(self.config)
            gaps = engine.identify_knowledge_gaps(drawers)
            high_priority = [g for g in gaps if g.priority >= 0.6]
            return TaskResult(
                name="knowledge_gaps",
                status="success",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "total_gaps": len(gaps),
                    "high_priority_gaps": len(high_priority),
                    "top_topics": [g.topic for g in sorted(gaps, key=lambda x: -x.priority)[:5]],
                },
            )
        except Exception as e:
            return TaskResult(name="knowledge_gaps", status="failed", details={"error": str(e)})

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

        new_count = self._count_new_since(drawers, self._state.get("last_run", {}).get("fusion", 0))
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

        # 自动采集
        if force or self._should_run("collect"):
            tasks.append(("collect", self._task_collect, True))

        # 异常检测（P2-1 Step 2）
        if force or self._should_run("anomaly_detection"):
            tasks.append(("anomaly_detection", self._task_anomaly_detection, True))

        # 知识缺口识别（P2-1 Step 2）
        if force or self._should_run("knowledge_gaps"):
            tasks.append(("knowledge_gaps", self._task_knowledge_gaps, True))

        # KG 实体抽取（2026-09-19 接线：此前挂在从未被调用的 LifecycleManager 钩子上）
        if force or self._should_run("kg_enrichment"):
            tasks.append(("kg_enrichment", self._task_kg_enrichment, True))

        # 夜间巩固（2026-09-20 接线）：每轮无条件尝试，窗口/到期由任务内部自查。
        # 不能走 _should_run 的 24h 门 —— 否则在窗口外被标记 done 后，下次尝试
        # 已是 24h 后，会永远错过 03:00–05:00 窗口。
        tasks.append(("consolidation", self._task_consolidation, False))

        # 准入复检（2026-09-20 接线）：pending_review 积压定期重过四问门
        if force or self._should_run("readmission"):
            tasks.append(("readmission", self._task_readmission, False))

        # 知识结晶（2026-09-20 升级 LLM 精炼）：每轮无条件尝试，窗口（04:00–06:00）
        # 与 20h 到期由任务内部自检 —— 不走 _should_run，否则在窗口外被标记 done
        # 后会永远错过窗口（同 consolidation 的教训）
        tasks.append(("crystallize", self._task_crystallize, False))

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

        # P0-0 修复：**不得以空记忆为基线回写**。
        # 此前无条件 `self._save_drawers(drawers)`；当 `_load_drawers()` 因
        # 路径错位（v1 空库）或读取异常返回 [] 时，这次回写会把**非空**的
        # 权威存储直接清成 0 条——这正是 v1 变成 `[]` 的 runtime 可达路径之一。
        # 现在：内存为空**且**磁盘有记录 ⇒ 跳过回写并告警。
        if not drawers and self._disk_has_records():
            logger.warning("跳过自主维护回写: 内存记忆为空但磁盘有记录（疑似路径错位/空库误写）")
        else:
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
        logger.info(f"自主周期完成: {success}成功, {skipped}跳过, {failed}失败, 耗时{total_ms:.0f}ms, 触发: {trigger}")
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
            pending.append(
                {
                    "task": task,
                    "last_run": datetime.fromtimestamp(last).isoformat() if last else "never",
                    "next_in_minutes": round(remaining / 60, 1),
                }
            )

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
