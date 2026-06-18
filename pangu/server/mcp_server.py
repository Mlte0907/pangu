"""盘古 MCP 服务器 — 为 AI Agent 提供记忆工具接口
==================================================
盘古定位为专业的记忆系统（智能体的大脑组件），
MCP 工具只提供记忆的存储、检索、组织和管理功能。
不包含 Agent 执行功能（问答、对话、任务执行等）。

上层 Agent 框架通过 MCP 调用这些工具获取记忆数据后，
自行完成推理、决策和行动。"""
import asyncio
import json
import sys
import time

from ..core.config import PanguConfig
from ..core.llm import LLMEngine
from ..core.palace import Drawer, Palace
from ..memory.adaptive_params import get_adaptive_engine
from ..memory.attention import AttentionStrategy, get_attention_system
from ..memory.differential_privacy import DifferentialPrivacy
from ..memory.distill_enhanced import DistillationTower
from ..memory.enhanced_evaluation import EnhancedContradictionDetector, TrajectoryTracker
from ..memory.fts_search import FTS5SearchEngine, get_search_stats, holographic_search
from ..memory.hologram import get_holographic_encoder
from ..memory.judge import get_memory_judge
from ..memory.knowledge_graph import KnowledgeGraph
from ..memory.layers import MemoryStack
from ..memory.reconsolidation import ReconsolidationEngine, ResonanceEngine
from ..memory.sanitizer import MemorySanitizer
from ..memory.streaming_index import StreamingIndexer
from ..memory.vector_index import get_vector_index
from ..memory.verification import VerificationLoop
from ..memory.working_memory import WMItem, get_working_memory
from ..search.engine import HybridSearch
from ..wiki.engine import WikiEngine


class MCPServer:
    """MCP 协议服务器 — 35 个记忆工具"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._palace = None
        self._memory = None
        self._knowledge_graph = None
        self._wiki = None
        self._search = None
        self._llm = None
        self._persistent_cache = None
        self._warmup_task: asyncio.Task | None = None
        self._vacuum_task: asyncio.Task | None = None
        self._periodic_vacuum_task: asyncio.Task | None = None

    @property
    def palace(self):
        if self._palace is None:
            self._palace = Palace(self.config.palace_path)
        return self._palace

    @property
    def memory(self):
        if self._memory is None:
            self._memory = MemoryStack(self.config)
        return self._memory

    @property
    def knowledge_graph(self):
        if self._knowledge_graph is None:
            self._knowledge_graph = KnowledgeGraph(self.config)
        return self._knowledge_graph

    @property
    def wiki(self):
        if self._wiki is None:
            self._wiki = WikiEngine(self.config)
        return self._wiki

    @property
    def search(self):
        if self._search is None:
            self._search = HybridSearch(self.config)
        return self._search

    @property
    def llm(self):
        if self._llm is None:
            self._llm = LLMEngine(self.config)
            self._persistent_cache = self._llm._persistent_cache
            self._maybe_schedule_warmup()
            self._maybe_schedule_vacuum()
        return self._llm

    def _ensure_initialized(self):
        """确保核心组件已初始化（首次调用时触发）"""
        _ = self.palace
        _ = self.memory
        _ = self.knowledge_graph
        _ = self.wiki
        _ = self.search
        _ = self.llm

    def _maybe_schedule_warmup(self) -> None:
        """在事件循环可用时把缓存预热调度为后台任务

        行为：
        - 配置 llm_cache_warmup_on_start=False → 跳过
        - 配置 llm_cache_warmup_prompts 为空 → 跳过
        - 无运行中的事件循环（如单元测试中） → 跳过
        """
        if not getattr(self.config, "llm_cache_warmup_on_start", False):
            return
        if not getattr(self.config, "llm_cache_warmup_prompts", []):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（同步上下文或测试），跳过
            return
        self._warmup_task = loop.create_task(
            self.llm.auto_warmup_on_start(),
            name="pangu-llm-cache-warmup",
        )

    async def await_warmup(self) -> dict | None:
        """等待预热任务完成（用于 graceful shutdown）"""
        if self._warmup_task is None:
            return None
        try:
            return await self._warmup_task
        except Exception:
            return {"error": "warmup failed"}

    def _maybe_schedule_vacuum(self) -> None:
        """在事件循环可用时调度自动 VACUUM / 周期 VACUUM 后台任务

        行为：
        - llm_cache_vacuum_on_start=True → 启动时立即跑一次
        - llm_cache_vacuum_interval_hours > 0 → 周期执行
        - 无事件循环 → 跳过
        """
        if self._persistent_cache is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        # 启动时立即一次
        if getattr(self.config, "llm_cache_vacuum_on_start", False):
            self._vacuum_task = loop.create_task(
                self._run_vacuum(),
                name="pangu-llm-cache-vacuum-once",
            )
        # 周期任务
        interval = getattr(self.config, "llm_cache_vacuum_interval_hours", 0.0)
        if interval > 0:
            self._periodic_vacuum_task = loop.create_task(
                self.llm.start_periodic_vacuum(interval),
                name="pangu-llm-cache-vacuum-periodic",
            )

    async def _run_vacuum(self) -> dict:
        """包装 auto_vacuum_on_start 为 async"""
        return self.llm.auto_vacuum_on_start()

    # ── 工具定义 ──

    @property
    def tools(self) -> list[dict]:
        _empty_schema = {"type": "object", "properties": {}}
        raw = [
            # Palace 读写
            {"name": "pangu_list_wings", "description": "列出所有 Wing（空间）"},
            {"name": "pangu_create_wing", "description": "创建新 Wing"},
            {"name": "pangu_list_rooms", "description": "列出 Wing 下的所有 Room"},
            {"name": "pangu_create_room", "description": "在 Wing 下创建 Room"},

            # 记忆操作
            {"name": "pangu_add_memory", "description": "添加记忆片段"},
            {"name": "pangu_search_memories", "description": "搜索记忆"},
            {"name": "pangu_recall", "description": "按 Wing/Room 回忆记忆"},
            {"name": "pangu_wake_up", "description": "获取 L0+L1 唤醒上下文"},

            # Wiki 操作
            {"name": "pangu_list_wiki_pages", "description": "列出 Wiki 页面"},
            {"name": "pangu_get_wiki_page", "description": "获取 Wiki 页面内容"},
            {"name": "pangu_create_wiki_page", "description": "创建 Wiki 页面"},
            {"name": "pangu_auto_generate_wiki", "description": "LMM 自动生成 Wiki 页面"},

            # 知识图谱
            {"name": "pangu_kg_add_entity", "description": "添加知识图谱实体"},
            {"name": "pangu_kg_add_relation", "description": "添加知识图谱关系"},
            {"name": "pangu_kg_query", "description": "查询知识图谱"},
            {"name": "pangu_kg_neighbors", "description": "获取实体邻居"},

            # LMM 记忆处理
            {"name": "pangu_summarize", "description": "总结记忆"},
            {"name": "pangu_classify", "description": "LMM 分类记忆"},
            {"name": "pangu_insight", "description": "从记忆中提取洞察"},

            # 隧道
            {"name": "pangu_create_tunnel", "description": "创建跨 Wing 隧道"},
            {"name": "pangu_list_tunnels", "description": "列出隧道"},
            {"name": "pangu_find_tunnels", "description": "查找 Wing 间隧道"},

            # 统计
            {"name": "pangu_stats", "description": "获取系统统计"},
            {"name": "pangu_graph", "description": "导出知识图谱"},
            {"name": "pangu_identity", "description": "获取/设置 AI 身份"},

            # 记忆巩固（类人特征）
            {"name": "pangu_consolidation_stats", "description": "获取记忆巩固统计（遗忘/复习/压缩状态）"},
            {"name": "pangu_find_forgotten", "description": "找出应被遗忘的低重要性记忆"},
            {"name": "pangu_compress_memories", "description": "使用 LMM 压缩旧记忆为精简摘要"},
            {"name": "pangu_detect_associations", "description": "LMM 自动检测记忆片段之间的关联"},
            {"name": "pangu_memory_importance", "description": "计算指定记忆的综合重要性评分"},

            # 迁移与备份
            {"name": "pangu_export", "description": "导出记忆数据为 JSON/ZIP"},
            {"name": "pangu_import", "description": "从文件导入记忆数据"},
            {"name": "pangu_backup", "description": "创建备份快照"},
            {"name": "pangu_list_backups", "description": "列出所有备份"},
            {"name": "pangu_restore_backup", "description": "从备份恢复"},

            # 记忆聚类
            {"name": "pangu_cluster_memories", "description": "将记忆自动聚类为主题分组"},
            {"name": "pangu_find_related", "description": "找到与指定记忆最相关的其他记忆"},

            # 冲突检测
            {"name": "pangu_detect_conflicts", "description": "检测记忆中的矛盾和不一致"},
            {"name": "pangu_check_pair", "description": "检查两条记忆是否存在冲突"},

            # 记忆去重
            {"name": "pangu_find_duplicates", "description": "检测重复或高度相似的记忆"},
            {"name": "pangu_merge_duplicates", "description": "合并重复记忆组"},
            {"name": "pangu_similarity_check", "description": "检查两条记忆的相似度"},

            # 分析看板
            {"name": "pangu_analyze", "description": "生成全面记忆分析报告"},
            {"name": "pangu_health_check", "description": "检查记忆系统健康度"},
            {"name": "pangu_anomaly_detect", "description": "检测记忆系统异常"},
            {"name": "pangu_growth_trend", "description": "分析记忆增长趋势"},

            # 时间线
            {"name": "pangu_build_timeline", "description": "构建记忆时间线"},
            {"name": "pangu_find_causal_links", "description": "发现记忆间的因果关系"},
            {"name": "pangu_event_chains", "description": "构建事件链（时间相近的事件分组）"},
            {"name": "pangu_timeline_query", "description": "按时间范围查询记忆"},

            # 融合与抽象
            {"name": "pangu_fuse_topic", "description": "融合同一主题的记忆为结构化理解"},
            {"name": "pangu_progressive_summarize", "description": "渐进式摘要（从细节到抽象）"},
            {"name": "pangu_crystallize_knowledge", "description": "从记忆中结晶可复用知识"},

            # 模式识别
            {"name": "pangu_discover_patterns", "description": "发现记忆中的隐藏模式和规律"},
            {"name": "pangu_pattern_insights", "description": "从模式中提取洞察"},

            # 记忆回放
            {"name": "pangu_timeline_replay", "description": "按时间线回放记忆"},
            {"name": "pangu_topic_replay", "description": "围绕主题回放相关记忆"},
            {"name": "pangu_highlight_reel", "description": "提取最重要的记忆时刻（精彩集锦）"},

            # ── 深度情绪智能 (移植自伏羲) ──
            {"name": "pangu_deep_emotion_trajectory", "description": "情绪轨迹追踪（速度/加速度/趋势）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_deep_emotion_decompose", "description": "混合情绪解耦（识别复杂情绪中的多个成分）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_deep_emotion_stats", "description": "获取深度情绪统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 多策略辩论 (移植自伏羲) ──
            {"name": "pangu_debate_run", "description": "运行多策略辩论（分析/创意/保守三策略评分选优）", "inputSchema": {"type": "object", "properties": {"question": {"type": "string", "description": "待辩论的问题"}, "strategies_count": {"type": "integer", "description": "策略数量(2-3)", "default": 2}, "context": {"type": "string", "description": "上下文信息", "default": ""}}, "required": ["question"]}},
            {"name": "pangu_debate_stats", "description": "获取辩论统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 叙事引擎 (移植自伏羲) ──
            {"name": "pangu_narrative_generate", "description": "生成记忆叙事（按Wing聚合为连贯叙事线）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_narrative_themes", "description": "提取记忆主题", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_narrative_identity", "description": "生成身份连续性叙事", "inputSchema": {"type": "object", "properties": {}}},

            # ── 伏羲移植 ──

            # 认知循环
            {"name": "pangu_cognitive_loop", "description": "运行一次认知循环（observe→think→evaluate→act）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_cognitive_stats", "description": "获取认知循环统计", "inputSchema": {"type": "object", "properties": {}}},

            # 元认知
            {"name": "pangu_metacognition_monitor", "description": "系统级健康监测（策略表现、观察数据、建议）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_metacognition_reconfig", "description": "自重构检测（低效策略、未使用策略、异常模块）", "inputSchema": {"type": "object", "properties": {}}},

            # 世界模型
            {"name": "pangu_worldmodel_forecast", "description": "基于当前状态预测未来情景", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_worldmodel_plan", "description": "为指定情景生成应对计划", "inputSchema": {"type": "object", "properties": {"scenario_id": {"type": "string", "description": "情景ID"}}, "required": ["scenario_id"]}},
            {"name": "pangu_worldmodel_match", "description": "将事件与预测情景匹配", "inputSchema": {"type": "object", "properties": {"event_type": {"type": "string"}, "event_data": {"type": "object", "default": {}}}, "required": ["event_type"]}},
            {"name": "pangu_worldmodel_stats", "description": "获取世界模型统计", "inputSchema": {"type": "object", "properties": {}}},

            # FTS5 混合搜索
            {"name": "pangu_fts_search", "description": "FTS5全文+向量混合搜索(RRF融合)"},
            {"name": "pangu_fts_search_stats", "description": "获取搜索引擎统计"},

            # 全息记忆
            {"name": "pangu_holographic_encode", "description": "将记忆编码为全息投影（5维）"},
            {"name": "pangu_holographic_search", "description": "全息跨维度融合检索"},

            # 记忆法官
            {"name": "pangu_judge_memory", "description": "LLM判断记忆价值(A/B/C三级分类)"},
            {"name": "pangu_judge_stats", "description": "获取判断统计"},

            # 自适应参数
            {"name": "pangu_adaptive_params", "description": "获取/调整自适应参数"},
            {"name": "pangu_adaptive_evaluate", "description": "根据系统统计评估并调整参数"},

            # 工作记忆
            {"name": "pangu_wm_push", "description": "推入工作记忆项"},
            {"name": "pangu_wm_get", "description": "获取工作记忆项"},
            {"name": "pangu_wm_stats", "description": "获取工作记忆统计"},
            {"name": "pangu_wm_clear", "description": "清空工作记忆"},

            # 记忆脱敏
            {"name": "pangu_sanitize", "description": "脱敏记忆内容"},
            {"name": "pangu_sanitize_check", "description": "检查是否需要脱敏"},

            # 再巩固 + 共鸣
            {"name": "pangu_reconsolidate", "description": "再巩固记忆（刷新衰减分数）"},
            {"name": "pangu_find_resonance", "description": "发现情感/语义共鸣的记忆对"},
            {"name": "pangu_cross_wing_resonance", "description": "发现跨Wing的知识共鸣"},

            # 知识蒸馏增强
            {"name": "pangu_distill_knowledge", "description": "从记忆中蒸馏结构化知识卡片"},
            {"name": "pangu_distill_causal_chains", "description": "提取所有因果链"},
            {"name": "pangu_distill_graph", "description": "获取知识关联图"},
            {"name": "pangu_distill_stats", "description": "获取蒸馏统计"},

            # 向量索引
            {"name": "pangu_vector_index_stats", "description": "获取向量索引统计"},
            {"name": "pangu_vector_index_build", "description": "构建向量索引"},

            # 注意力系统
            {"name": "pangu_attention_state", "description": "获取当前注意力状态"},
            {"name": "pangu_attention_switch", "description": "切换注意力策略"},
            {"name": "pangu_attention_ab_test", "description": "启动注意力策略A/B测试"},

            # 增强评估
            {"name": "pangu_enhanced_contradictions", "description": "LLM驱动矛盾检测（6种裁决）"},
            {"name": "pangu_trajectory_track", "description": "追踪记忆时间轨迹"},
            {"name": "pangu_trajectory_compare", "description": "比较两个时间段的记忆变化"},

            # 流式索引
            {"name": "pangu_streaming_index", "description": "增量索引新记忆"},
            {"name": "pangu_streaming_stats", "description": "获取流式索引统计"},

            # 验证循环
            {"name": "pangu_verify", "description": "运行完整验证循环"},
            {"name": "pangu_verify_phase", "description": "运行单个验证阶段"},

            # 差分隐私
            {"name": "pangu_privacy_stats", "description": "获取隐私预算统计"},
            {"name": "pangu_privatize_count", "description": "隐私化计数结果"},

            # ── 伏羲服务器增强 ──
            {"name": "pangu_system_health", "description": "深度系统健康检查（DB/结构/嵌入/统计）"},
            {"name": "pangu_system_metrics", "description": "获取 Prometheus 格式系统指标"},
            {"name": "pangu_config_get", "description": "获取当前配置"},
            {"name": "pangu_config_set", "description": "更新配置项"},
            {"name": "pangu_config_reload", "description": "热更新配置"},
            {"name": "pangu_schema_version", "description": "获取数据库 schema 版本"},
            {"name": "pangu_schema_migrations", "description": "列出所有迁移版本"},
            {"name": "pangu_autonomous_analyze", "description": "分析任务复杂度并推荐能力"},
            {"name": "pangu_api_server_start", "description": "启动 REST API 服务器"},

            # ── ONNX 加速嵌入 ──
            {"name": "pangu_onnx_embed", "description": "使用 ONNX 本地推理嵌入单条文本（CPU 加速 3-10x）", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "要嵌入的文本"}}, "required": ["text"]}},
            {"name": "pangu_onnx_embed_batch", "description": "ONNX 批量嵌入多条文本", "inputSchema": {"type": "object", "properties": {"texts": {"type": "array", "items": {"type": "string"}, "description": "要嵌入的文本列表"}}, "required": ["texts"]}},
            {"name": "pangu_onnx_status", "description": "获取 ONNX 嵌入器状态（模型/缓存/性能）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_onnx_similarity", "description": "使用 ONNX 计算两条文本的余弦相似度", "inputSchema": {"type": "object", "properties": {"text_a": {"type": "string"}, "text_b": {"type": "string"}}, "required": ["text_a", "text_b"]}},

            # ── LLM 响应缓存 (v0.1.2) ──
            {"name": "pangu_llm_cache_stats", "description": "获取 LLM 缓存统计（命中、token、成本、磁盘）"},
            {"name": "pangu_llm_cache_top", "description": "获取访问最频繁的缓存键"},
            {"name": "pangu_llm_cache_clear", "description": "清空 LLM 缓存（内存/磁盘）"},
            {"name": "pangu_llm_cache_metrics", "description": "导出 Prometheus 格式 LLM 缓存指标"},
            {"name": "pangu_llm_cache_warmup", "description": "预热 LLM 缓存（按 prompt 列表批量填充）"},
            {"name": "pangu_llm_cache_warmup_log", "description": "查看 LLM 缓存预热审计日志"},
            {"name": "pangu_llm_cache_vacuum", "description": "对持久化缓存执行 VACUUM，释放 SQLite 碎片空间"},
            {"name": "pangu_llm_cache_config", "description": "查看当前 LLM 缓存相关配置"},

            # ── 自然语言查询 + 记忆推荐 (v0.2.0) ──
            {"name": "pangu_natural_query", "description": "自然语言查询记忆（支持时间、空间、重要性等语义理解）", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "自然语言查询，如'上周关于API设计的重要讨论'"}, "limit": {"type": "integer", "description": "返回数量", "default": 10}}, "required": ["query"]}},
            {"name": "pangu_recommend", "description": "基于上下文智能推荐相关记忆", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "当前上下文（会话内容、任务描述等）"}, "limit": {"type": "integer", "description": "推荐数量", "default": 5}}, "required": ["context"]}},
            {"name": "pangu_conversational_search", "description": "对话式记忆搜索（支持多轮澄清）", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "session_id": {"type": "string", "description": "会话ID（用于多轮对话）"}, "clarify": {"type": "boolean", "description": "是否需要澄清", "default": False}}, "required": ["query"]}},
            {"name": "pangu_memory_insights", "description": "从记忆中提取洞察和模式", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string", "description": "主题（可选）"}, "time_range": {"type": "string", "description": "时间范围（如'7d', '30d'）"}}, "required": []}},

            # ── 神经记忆系统 (v2.0) ──
            {"name": "pangu_neural_stats", "description": "获取海马体-新皮层双系统统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_neural_sleep", "description": "触发神经睡眠巩固（海马体→新皮层重播）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_neural_spreading", "description": "基于种子记忆执行激活扩散，找到关联记忆", "inputSchema": {"type": "object", "properties": {"seed_ids": {"type": "array", "items": {"type": "string"}, "description": "种子记忆ID列表"}, "depth": {"type": "integer", "description": "最大扩散深度", "default": 3}}, "required": ["seed_ids"]}},
            {"name": "pangu_neural_inhibition", "description": "对一组记忆执行竞争抑制，返回有效激活值", "inputSchema": {"type": "object", "properties": {"memory_ids": {"type": "array", "items": {"type": "string"}, "description": "记忆ID列表"}}, "required": ["memory_ids"]}},
            {"name": "pangu_neural_decay", "description": "对所有神经记忆应用个性化衰减", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆重要性反馈 (v2.0) ──
            {"name": "pangu_importance_feedback", "description": "根据反馈信号动态调整记忆重要性", "inputSchema": {"type": "object", "properties": {"drawer_id": {"type": "string", "description": "记忆ID"}, "signal": {"type": "string", "description": "反馈信号: recall_success/recall_miss/vote_up/vote_down/verified"}}, "required": ["drawer_id", "signal"]}},
            {"name": "pangu_auto_fusion", "description": "触发自动记忆融合（同主题>=3条）", "inputSchema": {"type": "object", "properties": {}}},

            # ── 跨会话整合 (v2.0) ──
            {"name": "pangu_cross_session_links", "description": "发现跨会话记忆关联", "inputSchema": {"type": "object", "properties": {"min_similarity": {"type": "number", "description": "最小相似度", "default": 0.4}, "max_links": {"type": "integer", "description": "最大关联数", "default": 10}}, "required": []}},
            {"name": "pangu_auto_compress", "description": "触发自动记忆压缩（长记忆→精简摘要）", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆验证 (v2.0) ──
            {"name": "pangu_validate_memories", "description": "验证所有记忆的准确性和时效性", "inputSchema": {"type": "object", "properties": {}}},

            # ── 知识图谱增强 (v2.0) ──
            {"name": "pangu_kg_auto_extract", "description": "从记忆中自动提取实体和关系丰富KG", "inputSchema": {"type": "object", "properties": {"max_drawers": {"type": "integer", "description": "最多处理的记忆数", "default": 50}}, "required": []}},
            {"name": "pangu_kg_cross_domain", "description": "跨领域知识迁移", "inputSchema": {"type": "object", "properties": {"source_domain": {"type": "string", "description": "源领域"}, "target_domain": {"type": "string", "description": "目标领域"}}, "required": ["source_domain", "target_domain"]}},
            {"name": "pangu_kg_similar_patterns", "description": "查找相似模式", "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string", "description": "实体ID"}}, "required": ["entity_id"]}},

            # ── 混合检索 (v2.0) ──
            {"name": "pangu_hybrid_search", "description": "FTS+向量+KG三路召回 RRF融合检索", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "limit": {"type": "integer", "description": "返回数量", "default": 10}}, "required": ["query"]}},
            {"name": "pangu_cluster_by_tags", "description": "按标签聚类搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "limit": {"type": "integer", "description": "返回数量", "default": 20}}, "required": ["query"]}},
            {"name": "pangu_cluster_by_time", "description": "按时间聚类搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "buckets": {"type": "integer", "description": "时间段数", "default": 3}}, "required": ["query"]}},
            {"name": "pangu_hierarchical_cluster", "description": "层次聚类（基于向量相似度）", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "max_clusters": {"type": "integer", "description": "最大聚类数", "default": 5}}, "required": ["query"]}},
            {"name": "pangu_dedup_results", "description": "去重搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "limit": {"type": "integer", "description": "返回数量", "default": 10}}, "required": ["query"]}},
            {"name": "pangu_multi_register", "description": "注册Agent到协作记忆空间", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "Agent ID"}, "priority": {"type": "integer", "description": "优先级", "default": 5}}, "required": ["agent_id"]}},
            {"name": "pangu_multi_write", "description": "写入多Agent共享记忆", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "写入者Agent ID"}, "content": {"type": "string", "description": "记忆内容"}, "scope": {"type": "string", "description": "权限范围: private/shared/public", "default": "public"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"}}, "required": ["agent_id", "content"]}},
            {"name": "pangu_multi_read", "description": "读取Agent可见的记忆", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "Agent ID"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "过滤标签"}}, "required": ["agent_id"]}},
            {"name": "pangu_multi_agents", "description": "获取所有已注册Agent", "inputSchema": {"type": "object", "properties": {}}},

            # ── 图推理 (v2.0) ──
            {"name": "pangu_graph_infer", "description": "基于知识图谱推理", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "推理查询"}}, "required": ["query"]}},
            {"name": "pangu_graph_contradictions", "description": "检测图中的矛盾关系", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_graph_causal_chain", "description": "因果链分析", "inputSchema": {"type": "object", "properties": {"entity_id": {"type": "string", "description": "实体ID"}, "max_depth": {"type": "integer", "description": "最大深度", "default": 5}}, "required": ["entity_id"]}},
            {"name": "pangu_graph_temporal", "description": "时序推理", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "查询文本"}}, "required": ["query"]}},
            {"name": "pangu_graph_analogy", "description": "类比检测", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "查询文本"}}, "required": ["query"]}},
            {"name": "pangu_graph_visualize", "description": "推理过程可视化", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "推理查询"}}, "required": ["query"]}},

            # ── 预测性记忆 (v2.0) ──
            {"name": "pangu_proactive_predict", "description": "基于上下文预测相关记忆", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "当前上下文"}, "limit": {"type": "integer", "description": "推荐数量", "default": 5}}, "required": ["context"]}},
            {"name": "pangu_proactive_suggest", "description": "基于当前上下文主动推荐记忆", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "推荐数量", "default": 5}}}},
            {"name": "pangu_context_status", "description": "获取当前上下文状态", "inputSchema": {"type": "object", "properties": {}}},

# ── 情感智能 (v2.0) ──
            {"name": "pangu_analyze_emotion", "description": "分析文本情绪", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "待分析文本"}}, "required": ["text"]}},
            {"name": "pangu_emotion_stats", "description": "获取情感统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_predict_emotion", "description": "预测用户情绪", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "上下文文本"}}, "required": ["context"]}},
            {"name": "pangu_recommend_interaction", "description": "推荐交互策略", "inputSchema": {"type": "object", "properties": {"emotion_state": {"type": "object", "description": "情绪状态"}}, "required": ["emotion_state"]}},

            # ── 创造性思维 (v2.0) ──
            {"name": "pangu_generate_ideas", "description": "基于记忆生成新想法", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "想法数量", "default": 5}}}},
            {"name": "pangu_discover_patterns", "description": "发现记忆中的模式", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_generate_novel", "description": "生成原创想法", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string", "description": "领域"}, "context": {"type": "string", "description": "上下文"}}}},

            # ── 自主学习 (v2.0) ──
            {"name": "pangu_discover_knowledge", "description": "从记忆中自动发现新知识", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_generate_hypotheses", "description": "基于记忆生成假设", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "假设数量", "default": 5}}}},
            {"name": "pangu_learning_stats", "description": "获取自主学习统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 自进化引擎 (v3.0) ──
            {"name": "pangu_self_diagnose", "description": "系统自我诊断", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_evolution_plan", "description": "生成进化计划", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_performance_trend", "description": "查看性能趋势", "inputSchema": {"type": "object", "properties": {"metric": {"type": "string", "description": "指标名称"}}}},
            {"name": "pangu_evolution_stats", "description": "获取进化统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 时间推理 (v3.0) ──
            {"name": "pangu_temporal_timeline", "description": "构建时间线", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_temporal_relations", "description": "发现时间关系", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_temporal_query", "description": "按时间范围查询", "inputSchema": {"type": "object", "properties": {"start": {"type": "string", "description": "开始日期 (YYYY-MM-DD)"}, "end": {"type": "string", "description": "结束日期 (YYYY-MM-DD)"}}, "required": []}},
            {"name": "pangu_temporal_stats", "description": "获取时间统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 语义压缩 (v3.0) ──
            {"name": "pangu_compress_by_tags", "description": "按标签聚类压缩记忆", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_find_duplicates", "description": "发现语义重复记忆", "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number", "description": "相似度阈值", "default": 0.8}}}},
            {"name": "pangu_reassess_importance", "description": "基于记忆网络重新评估重要性", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_compression_stats", "description": "获取压缩统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 协作智能 (v3.0) ──
            {"name": "pangu_agent_register", "description": "注册 Agent", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string"}, "name": {"type": "string"}, "specialties": {"type": "array", "items": {"type": "string"}}}, "required": ["agent_id", "name"]}},
            {"name": "pangu_agent_share", "description": "Agent 间共享知识", "inputSchema": {"type": "object", "properties": {"from_agent": {"type": "string"}, "to_agent": {"type": "string"}, "knowledge_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["from_agent", "to_agent", "knowledge_ids"]}},
            {"name": "pangu_collaborative_reason", "description": "协作推理", "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}, "agent_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["task"]}},
            {"name": "pangu_agent_stats", "description": "获取 Agent 统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 因果推理 (v3.0) ──
            {"name": "pangu_causal_discover", "description": "发现因果链接", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_causal_chains", "description": "构建因果链", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_counterfactual", "description": "反事实推理", "inputSchema": {"type": "object", "properties": {"cause_id": {"type": "string"}, "counterfactual": {"type": "string"}}, "required": ["cause_id", "counterfactual"]}},
            {"name": "pangu_root_cause", "description": "根因分析", "inputSchema": {"type": "object", "properties": {"effect_text": {"type": "string"}}, "required": ["effect_text"]}},
            {"name": "pangu_causal_stats", "description": "因果推理统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 可解释搜索 (v3.0) ──
            {"name": "pangu_explain_search", "description": "解释搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "result_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["query"]}},
            {"name": "pangu_search_suggestions", "description": "搜索改进建议", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},

            # ── 异常检测 (v3.0) ──
            {"name": "pangu_anomaly_scan", "description": "全面异常扫描", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_anomaly_content", "description": "内容异常检测", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_anomaly_stats", "description": "异常检测统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 知识综合 (v3.0) ──
            {"name": "pangu_synthesize", "description": "按主题综合知识", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}},
            {"name": "pangu_find_contradictions", "description": "检测矛盾信息", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_core_insights", "description": "提取核心洞察", "inputSchema": {"type": "object", "properties": {"top_k": {"type": "integer", "default": 10}}}},
            {"name": "pangu_auto_learn", "description": "执行自主学习循环", "inputSchema": {"type": "object", "properties": {}}},

            # ── 共鸣匹配 (伏羲移植) ──
            {"name": "pangu_resonance_find", "description": "发现情感/语义共鸣的记忆对并构建图谱边", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "扫描数量上限", "default": 30}, "sim_threshold": {"type": "number", "description": "相似度阈值", "default": 0.7}}, "required": []}},
            {"name": "pangu_resonance_edges", "description": "为共鸣匹配建立图谱边", "inputSchema": {"type": "object", "properties": {"matches": {"type": "array", "description": "共鸣匹配列表（来自 pangu_resonance_find）", "default": []}, "max_edges": {"type": "integer", "description": "最多建立边数", "default": 5}}, "required": []}},
            {"name": "pangu_resonance_stats", "description": "获取共鸣匹配统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 意图预测 (伏羲移植) ──
            {"name": "pangu_intent_predict", "description": "从记忆行为序列推断当前用户意图", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "额外上下文文本", "default": ""}}, "required": []}},
            {"name": "pangu_intent_tasks", "description": "任务链追踪 — 跟踪多步骤任务进度", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_intent_stats", "description": "获取意图预测统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 知识综合增强 (伏羲移植) ──
            {"name": "pangu_synthesis_cross_cluster", "description": "跨集群联想 — 发现不同Wing间的知识关联", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_synthesis_gaps", "description": "知识缺口识别 — 找出缺少深度分析的主题", "inputSchema": {"type": "object", "properties": {}}},

            # ── 预测分析 (v3.0) ──
            {"name": "pangu_predict_queries", "description": "预测用户下一步查询", "inputSchema": {"type": "object", "properties": {"top_k": {"type": "integer", "default": 5}}}},
            {"name": "pangu_predict_forgetting", "description": "预测即将遗忘的记忆", "inputSchema": {"type": "object", "properties": {"days_threshold": {"type": "integer", "default": 30}}}},
            {"name": "pangu_growth_trend", "description": "分析增长趋势", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_hot_topics", "description": "预测热点主题", "inputSchema": {"type": "object", "properties": {"top_k": {"type": "integer", "default": 5}}}},
            {"name": "pangu_predictive_stats", "description": "预测分析统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 自适应架构 (v3.0) ──
            {"name": "pangu_arch_analyze", "description": "分析记忆架构", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_arch_suggest", "description": "架构重构建议", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_cold_hot", "description": "冷热分离建议", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_arch_stats", "description": "架构统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 智能问答 (v3.0) ──
            {"name": "pangu_qa", "description": "基于记忆的智能问答", "inputSchema": {"type": "object", "properties": {"question": {"type": "string", "description": "用户问题"}}, "required": ["question"]}},
            {"name": "pangu_qa_batch", "description": "批量智能问答", "inputSchema": {"type": "object", "properties": {"questions": {"type": "array", "items": {"type": "string"}, "description": "问题列表"}}, "required": ["questions"]}},
            {"name": "pangu_qa_stats", "description": "问答统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 上下文注入 (v3.0) ──
            {"name": "pangu_inject_context", "description": "为文本注入相关记忆上下文", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "待注入文本"}, "token_budget": {"type": "integer", "description": "Token预算", "default": 500}}, "required": ["text"]}},
            {"name": "pangu_update_context", "description": "增量更新上下文", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "新文本"}}, "required": ["text"]}},
            {"name": "pangu_current_context", "description": "获取当前上下文缓冲", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_injection_stats", "description": "上下文注入统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 自适应遗忘 (v3.0) ──
            {"name": "pangu_evaluate_forgetting", "description": "评估所有记忆的遗忘价值", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_auto_forget", "description": "自动执行遗忘（归档+清理）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_get_archive", "description": "获取归档记忆", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}},
            {"name": "pangu_forget_stats", "description": "遗忘统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 巩固智能 (v3.0) ──
            {"name": "pangu_consolidate", "description": "执行智能记忆巩固", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_merge_candidates", "description": "查找可合并记忆", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_resolve_conflicts", "description": "发现并解决矛盾记忆", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_consolidation_stats", "description": "巩固统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆推荐 (v3.0) ──
            {"name": "pangu_recommend", "description": "综合记忆推荐", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "当前上下文"}, "memory_id": {"type": "string", "description": "当前记忆ID"}, "top_k": {"type": "integer", "default": 5}}}},
            {"name": "pangu_recommend_similar", "description": "推荐相似记忆", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}, "top_k": {"type": "integer", "default": 5}}, "required": ["memory_id"]}},
            {"name": "pangu_recommend_timely", "description": "推荐时效性记忆", "inputSchema": {"type": "object", "properties": {"top_k": {"type": "integer", "default": 5}}}},
            {"name": "pangu_recommend_feedback", "description": "记录推荐反馈", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}, "liked": {"type": "boolean"}}, "required": ["memory_id", "liked"]}},
            {"name": "pangu_recommendation_stats", "description": "推荐统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 质量评分 (v3.0) ──
            {"name": "pangu_assess_quality", "description": "评估记忆质量", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}}}},
            {"name": "pangu_batch_assess", "description": "批量质量评估", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_auto_fix", "description": "自动修复质量问题", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_quality_stats", "description": "质量统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 元学习 (v3.0 里程碑) ──
            {"name": "pangu_meta_observe", "description": "记录性能观察", "inputSchema": {"type": "object", "properties": {"module": {"type": "string"}, "metric": {"type": "string"}, "value": {"type": "number"}}, "required": ["module", "metric", "value"]}},
            {"name": "pangu_meta_recommend", "description": "推荐最优策略", "inputSchema": {"type": "object", "properties": {"task_type": {"type": "string", "default": "search"}}}},
            {"name": "pangu_meta_tune", "description": "自动调优参数", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_meta_insights", "description": "获取学习洞察", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_meta_stats", "description": "元学习统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆蒸馏 (v3.0) ──
            {"name": "pangu_distill", "description": "蒸馏所有记忆为精炼知识", "inputSchema": {"type": "object", "properties": {"min_group_size": {"type": "integer", "default": 2}}}},
            {"name": "pangu_distill_by_wing", "description": "按领域蒸馏", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_extract_keywords", "description": "提取关键词", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "top_k": {"type": "integer", "default": 5}}, "required": ["text"]}},
            {"name": "pangu_distillation_stats", "description": "蒸馏统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 查询重写 (v3.0) ──
            {"name": "pangu_rewrite_query", "description": "重写搜索查询", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "strategy": {"type": "string", "default": "auto"}}, "required": ["query"]}},
            {"name": "pangu_suggest_queries", "description": "查询建议", "inputSchema": {"type": "object", "properties": {"partial": {"type": "string"}, "top_k": {"type": "integer", "default": 5}}, "required": ["partial"]}},
            {"name": "pangu_rewrite_stats", "description": "重写统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 图谱构建 (v3.0) ──
            {"name": "pangu_build_graph", "description": "从记忆构建知识图谱", "inputSchema": {"type": "object", "properties": {"max_drawers": {"type": "integer", "default": 100}}}},
            {"name": "pangu_graph_entity", "description": "获取实体信息", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            {"name": "pangu_graph_path", "description": "查找实体间路径", "inputSchema": {"type": "object", "properties": {"from_name": {"type": "string"}, "to_name": {"type": "string"}}, "required": ["from_name", "to_name"]}},
            {"name": "pangu_graph_quality", "description": "评估图谱质量", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_graph_stats", "description": "图谱统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 健康监控 (v3.0) ──
            {"name": "pangu_health_check", "description": "全面健康检查", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_health_trend", "description": "健康趋势", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_health_stats", "description": "健康统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 备份恢复 (v3.0) ──
            {"name": "pangu_backup", "description": "全量备份记忆", "inputSchema": {"type": "object", "properties": {"description": {"type": "string"}}}},
            {"name": "pangu_list_backups", "description": "列出所有备份", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_verify_backup", "description": "验证备份完整性", "inputSchema": {"type": "object", "properties": {"backup_id": {"type": "string"}}, "required": ["backup_id"]}},
            {"name": "pangu_restore_backup", "description": "恢复备份", "inputSchema": {"type": "object", "properties": {"backup_id": {"type": "string"}}, "required": ["backup_id"]}},
            {"name": "pangu_backup_stats", "description": "备份统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 多项目支持 (v3.0) ──
            {"name": "pangu_project_create", "description": "创建项目", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string", "default": ""}}, "required": ["project_id", "name"]}},
            {"name": "pangu_project_switch", "description": "切换项目", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}},
            {"name": "pangu_project_list", "description": "列出所有项目", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_project_active", "description": "获取当前项目", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_project_save", "description": "保存记忆到当前项目", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_project_load", "description": "加载项目记忆", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}}},
            {"name": "pangu_project_search", "description": "跨项目搜索", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
            {"name": "pangu_project_merge", "description": "合并项目", "inputSchema": {"type": "object", "properties": {"source_id": {"type": "string"}, "target_id": {"type": "string"}}, "required": ["source_id"]}},
            {"name": "pangu_project_delete", "description": "删除项目", "inputSchema": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}},
            {"name": "pangu_project_stats", "description": "项目统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 审计分析 (v3.0) ──
            {"name": "pangu_audit_log", "description": "记录审计日志", "inputSchema": {"type": "object", "properties": {"operation": {"type": "string"}, "target_id": {"type": "string", "default": ""}}, "required": ["operation"]}},
            {"name": "pangu_audit_query", "description": "查询审计日志", "inputSchema": {"type": "object", "properties": {"operation": {"type": "string"}, "user_id": {"type": "string"}, "limit": {"type": "integer", "default": 50}}}},
            {"name": "pangu_audit_stats", "description": "操作统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_access_patterns", "description": "访问模式分析", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_security_summary", "description": "安全摘要", "inputSchema": {"type": "object", "properties": {}}},

            # ── 多端同步 (v3.0) ──
            {"name": "pangu_sync_record", "description": "记录变更", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}, "operation": {"type": "string"}, "content": {"type": "string", "default": ""}}, "required": ["memory_id", "operation"]}},
            {"name": "pangu_sync_pending", "description": "获取待同步变更", "inputSchema": {"type": "object", "properties": {"since": {"type": "string"}}}},
            {"name": "pangu_sync_conflicts", "description": "检测冲突", "inputSchema": {"type": "object", "properties": {"remote_changes": {"type": "array", "items": {"type": "object"}, "default": []}}}},
            {"name": "pangu_sync_resolve", "description": "解决冲突", "inputSchema": {"type": "object", "properties": {"change_id": {"type": "string"}, "resolution": {"type": "string", "default": "keep_latest"}}, "required": ["change_id"]}},
            {"name": "pangu_sync_state", "description": "同步状态", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_sync_stats", "description": "同步统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆事件流 (v3.0) ──
            {"name": "pangu_event_emit", "description": "发布记忆事件", "inputSchema": {"type": "object", "properties": {"event_type": {"type": "string"}, "memory_id": {"type": "string", "default": ""}, "data": {"type": "object", "default": {}}}, "required": ["event_type"]}},
            {"name": "pangu_event_history", "description": "查询事件历史", "inputSchema": {"type": "object", "properties": {"event_type": {"type": "string"}, "limit": {"type": "integer", "default": 50}}}},
            {"name": "pangu_event_stats", "description": "事件统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_event_webhook_add", "description": "添加 Webhook", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "event_types": {"type": "array", "items": {"type": "string"}}}, "required": ["url", "event_types"]}},
            {"name": "pangu_event_save", "description": "持久化事件历史", "inputSchema": {"type": "object", "properties": {}}},

            # ── 智能索引 (v3.0) ──
            {"name": "pangu_index_build", "description": "构建所有索引", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_index_search", "description": "通过索引搜索", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
            {"name": "pangu_index_recommend", "description": "索引推荐", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_index_health", "description": "索引健康检查", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_index_cleanup", "description": "清理无效索引", "inputSchema": {"type": "object", "properties": {}}},

            # ── 智能缓存 (v3.0) ──
            {"name": "pangu_cache_stats", "description": "缓存统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_cache_cleanup", "description": "清理过期缓存", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_cache_invalidate", "description": "失效缓存", "inputSchema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},

            # ── 统一门户 (v3.0) ──
            {"name": "pangu_portal_write", "description": "智能写入（自动标签+索引+事件）", "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}, "wing": {"type": "string", "default": "default"}, "tags": {"type": "array", "items": {"type": "string"}, "default": []}, "importance": {"type": "number", "default": 3.0}}, "required": ["content"]}},
            {"name": "pangu_portal_search", "description": "智能搜索（自动重写+索引+排序）", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}}, "required": ["query"]}},
            {"name": "pangu_portal_panorama", "description": "系统全景", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_portal_maintain", "description": "一键维护", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_portal_summary", "description": "智能摘要", "inputSchema": {"type": "object", "properties": {}}},

            # ── 记忆差异 (v3.0) ──
            {"name": "pangu_diff_content", "description": "对比两段内容差异", "inputSchema": {"type": "object", "properties": {"content_a": {"type": "string"}, "content_b": {"type": "string"}}, "required": ["content_a", "content_b"]}},
            {"name": "pangu_diff_batch", "description": "批量差异对比", "inputSchema": {"type": "object", "properties": {"reference_id": {"type": "string"}}}},
            {"name": "pangu_diff_similarity", "description": "计算记忆相似度矩阵", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_diff_stats", "description": "差异统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 导出导入 (v3.0) ──
            {"name": "pangu_export_json", "description": "JSON格式导出", "inputSchema": {"type": "object", "properties": {"filepath": {"type": "string"}}}},
            {"name": "pangu_export_markdown", "description": "Markdown格式导出", "inputSchema": {"type": "object", "properties": {"filepath": {"type": "string"}}}},
            {"name": "pangu_export_csv", "description": "CSV格式导出", "inputSchema": {"type": "object", "properties": {"filepath": {"type": "string"}}}},
            {"name": "pangu_import_smart", "description": "智能导入（自动检测格式）", "inputSchema": {"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]}},
            {"name": "pangu_list_exports", "description": "列出所有导出文件", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_export_stats", "description": "导出导入统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 生产加固 (v3.0) ──
            {"name": "pangu_env_check", "description": "运行环境检查", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_startup_validate", "description": "启动校验", "inputSchema": {"type": "object", "properties": {}}},

            # ── 插件管理 ──
            {"name": "pangu_plugin_list", "description": "列出所有插件", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_plugin_enable", "description": "启用插件", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            {"name": "pangu_plugin_disable", "description": "禁用插件", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            {"name": "pangu_plugin_config", "description": "获取插件配置", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            {"name": "pangu_plugin_discover", "description": "发现并加载自定义插件", "inputSchema": {"type": "object", "properties": {"path": {"type": "string", "description": "插件目录路径"}}}},

            # ── 跨会话增强 (v3.0) ──
            {"name": "pangu_session_summary", "description": "生成会话摘要", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_session_bridge", "description": "构建上下文桥接", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_session_stats", "description": "会话统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_session_inject", "description": "跨会话上下文注入", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "当前查询/文本"}}, "required": ["query"]}},

            # ── 记忆版本控制 (v2.0) ──
            {"name": "pangu_version_history", "description": "获取记忆变更历史", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}}, "required": ["memory_id"]}},
            {"name": "pangu_version_compare", "description": "比较两个版本的差异", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "v1": {"type": "integer", "description": "版本1"}, "v2": {"type": "integer", "description": "版本2"}}, "required": ["memory_id", "v1", "v2"]}},

            # ── 记忆可视化 (v2.0) ──
            {"name": "pangu_visualize_graph", "description": "可视化知识图谱", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_visualize_network", "description": "可视化记忆网络", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_visualize_stats", "description": "可视化统计信息", "inputSchema": {"type": "object", "properties": {}}},

            # ── 重要性评分 (v2.0) ──
            {"name": "pangu_importance_score", "description": "计算记忆重要性评分", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "context": {"type": "string", "description": "当前上下文"}}, "required": ["memory_id"]}},

            # ── 自适应学习 (v2.0) ──
            {"name": "pangu_learning_stats", "description": "获取自适应学习统计", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_detect_patterns", "description": "检测用户行为模式", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_popular_queries", "description": "获取热门查询", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回数量", "default": 10}}}},
            {"name": "pangu_frequent_memories", "description": "获取频繁访问的记忆", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回数量", "default": 10}}}},
            {"name": "pangu_benchmark", "description": "运行性能基准测试", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_auto_collect", "description": "从会话文件自动提取记忆", "inputSchema": {"type": "object", "properties": {"session_file": {"type": "string", "description": "会话文件路径"}, "min_importance": {"type": "number", "description": "最小重要性阈值", "default": 0.3}}, "required": ["session_file"]}},

            # ── 社交记忆 (v2.0) ──
            {"name": "pangu_comment_add", "description": "添加记忆评论", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "author_id": {"type": "string", "description": "作者ID"}, "content": {"type": "string", "description": "评论内容"}}, "required": ["memory_id", "author_id", "content"]}},
            {"name": "pangu_comment_list", "description": "获取记忆评论列表", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}}, "required": ["memory_id"]}},
            {"name": "pangu_vote", "description": "对记忆投票", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "user_id": {"type": "string", "description": "用户ID"}, "vote_type": {"type": "string", "description": "投票类型: up/down/bookmark"}}, "required": ["memory_id", "user_id", "vote_type"]}},
            {"name": "pangu_vote_stats", "description": "获取记忆投票统计", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}}, "required": ["memory_id"]}},
            {"name": "pangu_search_stats", "description": "获取搜索命中率统计"},

            # ── 梦境巩固 (v3.0) ──
            {"name": "pangu_dream_cycle", "description": "运行一次梦境巩固周期（fetch→dedup→link→decay→distill）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_dream_stats", "description": "获取梦境巩固统计", "inputSchema": {"type": "object", "properties": {}}},

            # ── 好奇心探索 (v3.0) ──
            {"name": "pangu_curiosity_explore", "description": "运行好奇心探索（发现知识空白）", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_curiosity_gaps", "description": "发现知识空白并生成探索建议", "inputSchema": {"type": "object", "properties": {}}},

            # ── 人格引擎 (v3.0) ──
            {"name": "pangu_persona_identity", "description": "获取系统身份和人格特质", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_persona_values", "description": "获取系统价值观和原则", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "pangu_persona_health", "description": "系统综合健康度检查", "inputSchema": {"type": "object", "properties": {}}},
        ]
        for tool in raw:
            if "inputSchema" not in tool:
                tool["inputSchema"] = _empty_schema
        return raw

    # ── 工具调用 ──

    async def call_tool(self, tool_name: str, arguments: dict, request: dict = None) -> str:
        """调用工具并返回结果"""
        self._ensure_initialized()
        drawers = self.memory.get_drawers()

        try:
            # Palace 操作
            if tool_name == "pangu_list_wings":
                return json.dumps(self.palace.list_wings(), ensure_ascii=False)

            elif tool_name == "pangu_create_wing":
                name = arguments.get("name", "")
                desc = arguments.get("description", "")
                return json.dumps({"wing": self.palace.create_wing(name, desc)}, ensure_ascii=False)

            elif tool_name == "pangu_list_rooms":
                wing = arguments.get("wing")
                return json.dumps(self.palace.list_rooms(wing), ensure_ascii=False)

            elif tool_name == "pangu_create_room":
                wing = arguments.get("wing", "default")
                room = arguments.get("room", "")
                desc = arguments.get("description", "")
                return json.dumps({"room": self.palace.create_room(wing, room, desc)}, ensure_ascii=False)

            # 记忆操作
            elif tool_name == "pangu_add_memory":
                drawer = Drawer(
                    id=f"mem_{arguments.get('wing', 'default')}_{arguments.get('content', '')[:20]}",
                    content=arguments.get("content", ""),
                    wing=arguments.get("wing", "default"),
                    room=arguments.get("room", "general"),
                    hall=arguments.get("hall", "hall_events"),
                    importance=arguments.get("importance", 3.0),
                    tags=arguments.get("tags", []),
                )
                self.memory.add_drawer(drawer)
                return json.dumps({"status": "added", "id": drawer.id}, ensure_ascii=False)

            elif tool_name == "pangu_search_memories":
                query = arguments.get("query", "")
                wing = arguments.get("wing")
                room = arguments.get("room")
                results = self.search.search(query, drawers, wing=wing, room=room)
                return json.dumps(results, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recall":
                wing = arguments.get("wing")
                room = arguments.get("room")
                return self.memory.recall(wing=wing, room=room)

            elif tool_name == "pangu_wake_up":
                wing = arguments.get("wing")
                return self.memory.wake_up(wing=wing)

            # Wiki 操作
            elif tool_name == "pangu_list_wiki_pages":
                wing = arguments.get("wing")
                tag = arguments.get("tag")
                pages = self.wiki.list_pages(wing=wing, tag=tag)
                return json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2)

            elif tool_name == "pangu_get_wiki_page":
                page_id = arguments.get("page_id", "")
                page = self.wiki.get_page(page_id)
                if page:
                    return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)
                return json.dumps({"error": "页面不存在"})

            elif tool_name == "pangu_create_wiki_page":
                from ..core.palace import WikiPage
                page = WikiPage(
                    id=f"wiki_manual_{arguments.get('title', '')[:20]}",
                    title=arguments.get("title", ""),
                    wing=arguments.get("wing", "default"),
                    content=arguments.get("content", ""),
                    summary=arguments.get("summary", ""),
                    tags=arguments.get("tags", []),
                )
                self.wiki.create_page(page)
                return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_generate_wiki":
                title = arguments.get("title", "")
                wing = arguments.get("wing", "default")
                memories = [
                    {"content": d.content, "wing": d.wing, "room": d.room}
                    for d in drawers if d.wing == wing
                ]
                page = await self.wiki.auto_generate_page(self.llm, title, wing, memories)
                return json.dumps(page.to_dict(), ensure_ascii=False, indent=2)

            # 知识图谱
            elif tool_name == "pangu_kg_add_entity":
                entity = self.knowledge_graph.add_entity(
                    id=arguments.get("id", ""),
                    name=arguments.get("name", ""),
                    entity_type=arguments.get("type", "concept"),
                    description=arguments.get("description", ""),
                )
                return json.dumps(entity, ensure_ascii=False)

            elif tool_name == "pangu_kg_add_relation":
                rel = self.knowledge_graph.add_relation(
                    id=arguments.get("id", ""),
                    subject_id=arguments.get("subject_id", ""),
                    predicate=arguments.get("predicate", ""),
                    object_id=arguments.get("object_id", ""),
                    valid_from=arguments.get("valid_from"),
                    valid_until=arguments.get("valid_until"),
                    confidence=arguments.get("confidence", 1.0),
                    source=arguments.get("source", ""),
                )
                return json.dumps(rel, ensure_ascii=False)

            elif tool_name == "pangu_kg_query":
                relations = self.knowledge_graph.query_relations(
                    subject_id=arguments.get("subject_id"),
                    object_id=arguments.get("object_id"),
                    predicate=arguments.get("predicate"),
                    at_time=arguments.get("at_time"),
                )
                return json.dumps(relations, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_kg_neighbors":
                neighbors = self.knowledge_graph.get_neighbors(
                    entity_id=arguments.get("entity_id", ""),
                    at_time=arguments.get("at_time"),
                )
                return json.dumps(neighbors, ensure_ascii=False, indent=2)

            # LMM 记忆处理
            elif tool_name == "pangu_summarize":
                memories = [
                    {"content": d.content, "wing": d.wing, "room": d.room}
                    for d in drawers[:20]
                ]
                return await self.llm.summarize_memories(memories)

            elif tool_name == "pangu_classify":
                content = arguments.get("content", "")
                result = await self.llm.classify_memory(content)
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "pangu_insight":
                related = self.search.search(
                    arguments.get("topic", ""), drawers
                ) if arguments.get("topic") else [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:5]]
                return await self.llm.generate_insight(related)

            # 隧道
            elif tool_name == "pangu_create_tunnel":
                tunnel = self.palace.create_tunnel(
                    wing_a=arguments.get("wing_a", ""),
                    wing_b=arguments.get("wing_b", ""),
                    room=arguments.get("room", ""),
                )
                return json.dumps(tunnel, ensure_ascii=False)

            elif tool_name == "pangu_list_tunnels":
                return json.dumps(self.palace.list_tunnels(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_tunnels":
                tunnels = self.palace.find_tunnels(
                    wing_a=arguments.get("wing_a", ""),
                    wing_b=arguments.get("wing_b", ""),
                )
                return json.dumps(tunnels, ensure_ascii=False, indent=2)

            # 统计
            elif tool_name == "pangu_stats":
                stats = {
                    "palace": self.palace.stats(),
                    "memory": self.memory.status(),
                    "wiki": self.wiki.stats(),
                    "knowledge_graph": self.knowledge_graph.stats(),
                }
                return json.dumps(stats, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph":
                graph = {
                    "palace": self.palace.export_structure(),
                    "wiki": self.wiki.export_graph(),
                    "knowledge_graph": self.knowledge_graph.export_graph(),
                }
                return json.dumps(graph, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_identity":
                action = arguments.get("action", "get")
                if action == "set":
                    self.memory.l0.set_identity(arguments.get("text", ""))
                    return json.dumps({"status": "identity set"})
                return json.dumps({"identity": self.memory.l0.render()}, ensure_ascii=False)

            # 记忆巩固
            elif tool_name == "pangu_consolidation_stats":
                stats = self.memory.get_consolidation_stats()
                return json.dumps(stats, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_forgotten":
                forgotten = self.memory.find_forgotten()
                return json.dumps([d.to_dict() for d in forgotten], ensure_ascii=False, indent=2)

            elif tool_name == "pangu_compress_memories":
                compressible = self.memory.find_compressible()
                if not compressible:
                    return json.dumps({"status": "nothing to compress"})
                memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in compressible]
                result = await self.llm.compress_memories(memories, target_count=arguments.get("target_count", 5))
                return json.dumps({"status": "compressed", "result": result}, ensure_ascii=False)

            elif tool_name == "pangu_detect_associations":
                memories = [
                    {"content": d.content, "wing": d.wing, "room": d.room}
                    for d in drawers[:20]
                ]
                result = await self.llm.detect_associations(memories)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_memory_importance":
                drawer_id = arguments.get("drawer_id", "")
                importance = self.memory.get_memory_importance(drawer_id)
                return json.dumps({"drawer_id": drawer_id, "importance": importance}, ensure_ascii=False)

            # 迁移与备份
            elif tool_name == "pangu_export":
                from ..memory.migration import MemoryExporter
                exporter = MemoryExporter(self.config)
                output = arguments.get("output_path", "/tmp/pangu_export.json")
                fmt = arguments.get("format", "json")
                result_path = exporter.export_all(output, format=fmt)
                return json.dumps({"status": "exported", "path": result_path}, ensure_ascii=False)

            elif tool_name == "pangu_import":
                from ..memory.migration import MemoryImporter
                importer = MemoryImporter(self.config)
                file_path = arguments.get("file_path", "")
                merge = arguments.get("merge", True)
                stats = importer.import_from_file(file_path, merge=merge)
                return json.dumps(stats, ensure_ascii=False)

            elif tool_name == "pangu_backup":
                from ..memory.migration import BackupManager
                manager = BackupManager(self.config)
                label = arguments.get("label")
                path = manager.create_backup(label=label)
                return json.dumps({"status": "backup_created", "path": path}, ensure_ascii=False)

            elif tool_name == "pangu_list_backups":
                from ..memory.migration import BackupManager
                manager = BackupManager(self.config)
                return json.dumps(manager.list_backups(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_restore_backup":
                from ..memory.migration import BackupManager
                manager = BackupManager(self.config)
                backup_name = arguments.get("backup_name", "")
                merge = arguments.get("merge", False)
                result = manager.restore_backup(backup_name, merge=merge)
                return json.dumps(result, ensure_ascii=False)

            # 记忆聚类
            elif tool_name == "pangu_cluster_memories":
                from ..memory.clustering import MemoryClusterer
                clusterer = MemoryClusterer(self.config)
                n_clusters = arguments.get("n_clusters", 0)
                min_sim = arguments.get("min_similarity", 0.3)
                wing = arguments.get("wing")
                filtered = [d for d in drawers if not wing or d.wing == wing]
                clusters = clusterer.cluster(filtered, n_clusters=n_clusters, min_similarity=min_sim)
                stats = clusterer.cluster_stats(clusters)
                result = {
                    "stats": stats,
                    "clusters": [
                        {"id": c.id, "label": c.label, "keywords": c.keywords,
                         "size": c.size, "cohesion": c.cohesion,
                         "memory_ids": c.memory_ids[:5]}
                        for c in clusters
                    ],
                }
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_related":
                from ..memory.clustering import MemoryClusterer
                clusterer = MemoryClusterer(self.config)
                drawer_id = arguments.get("drawer_id", "")
                target = self.memory.get_drawer_by_id(drawer_id)
                if not target:
                    return json.dumps({"error": "记忆不存在"})
                related = clusterer.find_related(target, drawers)
                return json.dumps(related, ensure_ascii=False, indent=2)

            # 冲突检测
            elif tool_name == "pangu_detect_conflicts":
                from ..memory.conflict import ConflictDetector
                detector = ConflictDetector(self.config)
                wing = arguments.get("wing")
                filtered = [d for d in drawers if not wing or d.wing == wing]
                conflicts = detector.detect_conflicts(filtered)
                return json.dumps([
                    {"id": c.id, "memory_a": c.memory_a, "memory_b": c.memory_b,
                     "content_a": c.content_a[:100], "content_b": c.content_b[:100],
                     "description": c.description, "severity": c.severity.value,
                     "confidence": c.confidence,
                     "suggestion": detector.resolve_suggestion(c)}
                    for c in conflicts
                ], ensure_ascii=False, indent=2)

            elif tool_name == "pangu_check_pair":
                from ..memory.conflict import ConflictDetector
                detector = ConflictDetector(self.config)
                id_a = arguments.get("id_a", "")
                id_b = arguments.get("id_b", "")
                drawer_a = self.memory.get_drawer_by_id(id_a)
                drawer_b = self.memory.get_drawer_by_id(id_b)
                if not drawer_a or not drawer_b:
                    return json.dumps({"error": "记忆不存在"})
                result = detector.check_pair(drawer_a, drawer_b)
                return json.dumps(result, ensure_ascii=False)

            # 记忆去重
            elif tool_name == "pangu_find_duplicates":
                from ..memory.dedup import MemoryDeduplicator
                deduper = MemoryDeduplicator(self.config)
                threshold = arguments.get("threshold", 0.85)
                method = arguments.get("method", "auto")
                groups = deduper.find_duplicates(drawers, threshold=threshold, method=method)
                stats = deduper.dedup_stats(groups)
                return json.dumps({
                    "stats": stats,
                    "groups": [
                        {"id": g.id, "primary_id": g.primary_id,
                         "duplicate_ids": g.duplicate_ids,
                         "avg_similarity": g.avg_similarity}
                        for g in groups
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_merge_duplicates":
                from ..memory.dedup import DuplicateGroup, MemoryDeduplicator
                deduper = MemoryDeduplicator(self.config)
                group_data = arguments.get("group", {})
                group = DuplicateGroup(
                    id=group_data.get("id", ""),
                    memory_ids=group_data.get("memory_ids", []),
                    primary_id=group_data.get("primary_id", ""),
                    duplicate_ids=group_data.get("duplicate_ids", []),
                    similarity_matrix=group_data.get("similarity_matrix", {}),
                    avg_similarity=group_data.get("avg_similarity", 0.0),
                )
                merged = deduper.merge_duplicates(group, drawers)
                if merged:
                    # 删除重复的
                    self.memory.remove_drawers(group.duplicate_ids)
                    # 更新主记忆
                    self.memory.add_drawer(merged)
                    return json.dumps({"status": "merged", "merged_id": merged.id,
                                       "removed": group.duplicate_ids}, ensure_ascii=False)
                return json.dumps({"error": "合并失败"})

            elif tool_name == "pangu_similarity_check":
                from ..memory.dedup import MemoryDeduplicator
                deduper = MemoryDeduplicator(self.config)
                id_a = arguments.get("id_a", "")
                id_b = arguments.get("id_b", "")
                drawer_a = self.memory.get_drawer_by_id(id_a)
                drawer_b = self.memory.get_drawer_by_id(id_b)
                if not drawer_a or not drawer_b:
                    return json.dumps({"error": "记忆不存在"})
                result = deduper.similarity_check(drawer_a, drawer_b)
                return json.dumps(result, ensure_ascii=False)

            # 分析看板
            elif tool_name == "pangu_analyze":
                from ..memory.analytics import MemoryAnalyzer
                analyzer = MemoryAnalyzer(self.config)
                wiki_count = self.wiki.stats().get("total_pages", 0)
                analysis = analyzer.analyze(drawers, wiki_page_count=wiki_count)
                return json.dumps(analysis.__dict__, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_health_check":
                from ..memory.analytics import MemoryAnalyzer
                analyzer = MemoryAnalyzer(self.config)
                wiki_count = self.wiki.stats().get("total_pages", 0)
                analysis = analyzer.analyze(drawers, wiki_page_count=wiki_count)
                return json.dumps({
                    "health_score": analysis.health_score,
                    "issues": analysis.health_issues,
                    "recommendations": analysis.recommendations,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_anomaly_detect":
                from ..memory.analytics import MemoryAnalyzer
                analyzer = MemoryAnalyzer(self.config)
                anomalies = analyzer.anomaly_detect(drawers)
                return json.dumps(anomalies, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_growth_trend":
                from ..memory.analytics import MemoryAnalyzer
                analyzer = MemoryAnalyzer(self.config)
                days = arguments.get("days", 30)
                trend = analyzer.growth_trend(drawers, days=days)
                return json.dumps(trend, ensure_ascii=False, indent=2)

            # 时间线
            elif tool_name == "pangu_build_timeline":
                from ..memory.timeline import TimelineEngine
                engine = TimelineEngine(self.config)
                wing = arguments.get("wing")
                events = engine.build_timeline(drawers, wing=wing)
                stats = engine.timeline_stats(events)
                return json.dumps({
                    "stats": stats,
                    "events": [{"id": e.drawer_id, "content": e.content[:150],
                                "timestamp": e.timestamp, "wing": e.wing,
                                "room": e.room, "importance": e.importance}
                               for e in events[:30]],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_causal_links":
                from ..memory.timeline import TimelineEngine
                engine = TimelineEngine(self.config)
                events = engine.build_timeline(drawers)
                links = engine.find_causal_links(events)
                return json.dumps([
                    {"source_id": link.source_id, "target_id": link.target_id,
                     "confidence": link.confidence, "reason": link.reason,
                     "source": link.source_content, "target": link.target_content}
                    for link in links[:20]
                ], ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_chains":
                from ..memory.timeline import TimelineEngine
                engine = TimelineEngine(self.config)
                events = engine.build_timeline(drawers)
                chains = engine.build_event_chain(events)
                return json.dumps({
                    "total_chains": len(chains),
                    "chains": [
                        {"id": c.id, "span": c.span, "summary": c.summary,
                         "event_count": len(c.events)}
                        for c in chains[:10]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_timeline_query":
                from ..memory.timeline import TimelineEngine
                engine = TimelineEngine(self.config)
                events = engine.build_timeline(drawers)
                result = engine.query_timeline(
                    events,
                    start=arguments.get("start"),
                    end=arguments.get("end"),
                    wing=arguments.get("wing"),
                    room=arguments.get("room"),
                )
                return json.dumps([
                    {"id": e.drawer_id, "content": e.content[:150],
                     "timestamp": e.timestamp, "wing": e.wing, "room": e.room}
                    for e in result[:30]
                ], ensure_ascii=False, indent=2)

            # 融合与抽象
            elif tool_name == "pangu_fuse_topic":
                from ..memory.fusion import FusionEngine
                engine = FusionEngine(self.config)
                topic = arguments.get("topic", "")
                fused = engine.fuse_topic(topic, drawers)
                if fused:
                    return json.dumps({
                        "id": fused.id, "topic": fused.topic,
                        "summary": fused.summary, "key_points": fused.key_points,
                        "confidence": fused.confidence,
                        "contradictions": fused.contradictions,
                        "source_count": len(fused.source_memories),
                    }, ensure_ascii=False, indent=2)
                return json.dumps({"status": "no relevant memories found"})

            elif tool_name == "pangu_progressive_summarize":
                from ..memory.fusion import FusionEngine
                engine = FusionEngine(self.config)
                result = engine.progressive_summarize(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_crystallize_knowledge":
                from ..memory.fusion import FusionEngine
                engine = FusionEngine(self.config)
                topic = arguments.get("topic", "")
                knowledge = engine.crystallize_knowledge(drawers, topic=topic)
                return json.dumps({
                    k: len(v) for k, v in knowledge.items()
                }, ensure_ascii=False, indent=2)

            # 模式识别
            elif tool_name == "pangu_discover_patterns":
                from ..memory.patterns import PatternEngine
                engine = PatternEngine(self.config)
                patterns = engine.discover_all(drawers)
                stats = engine.pattern_stats(patterns)
                return json.dumps({
                    "stats": stats,
                    "patterns": [
                        {"id": p.id, "type": p.pattern_type,
                         "description": p.description,
                         "confidence": p.confidence, "frequency": p.frequency}
                        for p in patterns[:20]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_pattern_insights":
                from ..memory.patterns import PatternEngine
                engine = PatternEngine(self.config)
                patterns = engine.discover_all(drawers)
                insights = engine.pattern_insights(patterns)
                return json.dumps(insights, ensure_ascii=False, indent=2)

            # 记忆回放
            elif tool_name == "pangu_timeline_replay":
                from ..memory.replay import ReplayEngine
                engine = ReplayEngine(self.config)
                session = engine.timeline_replay(
                    drawers,
                    start=arguments.get("start"),
                    end=arguments.get("end"),
                    wing=arguments.get("wing"),
                    room=arguments.get("room"),
                )
                return json.dumps({
                    "id": session.id, "title": session.title,
                    "span": session.span, "event_count": session.event_count,
                    "wings": session.wings,
                    "key_moments": [
                        {"time": m["time"][:16], "content": m["content"][:100],
                         "importance": m["importance"]}
                        for m in session.key_moments[:5]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_topic_replay":
                from ..memory.replay import ReplayEngine
                engine = ReplayEngine(self.config)
                topic = arguments.get("topic", "")
                session = engine.topic_replay(topic, drawers)
                return json.dumps({
                    "id": session.id, "title": session.title,
                    "span": session.span, "event_count": session.event_count,
                    "key_moments": [
                        {"time": m["time"][:16], "content": m["content"][:100],
                         "importance": m["importance"]}
                        for m in session.key_moments[:5]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_highlight_reel":
                from ..memory.replay import ReplayEngine
                engine = ReplayEngine(self.config)
                session = engine.highlight_reel(drawers)
                return json.dumps({
                    "id": session.id, "title": session.title,
                    "event_count": session.event_count,
                    "highlights": [
                        {"time": m["time"][:16], "content": m["content"][:100],
                         "importance": m["importance"]}
                        for m in session.key_moments
                    ],
                }, ensure_ascii=False, indent=2)

            # ── 伏羲服务器增强 ──

            elif tool_name == "pangu_system_health":
                from ..observability.health import deep_health_check
                return json.dumps(deep_health_check(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_system_metrics":
                from ..observability.metrics import get_metrics_response
                content, _ = get_metrics_response()
                if isinstance(content, bytes):
                    content = content.decode()
                return content

            elif tool_name == "pangu_config_get":
                key = arguments.get("key")
                cfg = self.config
                if key:
                    val = getattr(cfg, key, None)
                    return json.dumps({key: str(val) if val is not None else None}, ensure_ascii=False)
                # 返回所有非敏感配置
                safe = cfg.model_dump(exclude={"api_key", "llm_api_key", "siliconflow_key"})
                return json.dumps(safe, ensure_ascii=False, indent=2, default=str)

            elif tool_name == "pangu_config_set":
                key = arguments.get("key", "")
                value = arguments.get("value")
                if key and hasattr(self.config, key):
                    setattr(self.config, key, value)
                    return json.dumps({"status": "updated", "key": key, "value": str(value)}, ensure_ascii=False)
                return json.dumps({"error": f"unknown config key: {key}"})

            elif tool_name == "pangu_config_reload":
                from ..core.config import PanguConfig
                new_cfg = PanguConfig.reload()
                self.config = new_cfg
                return json.dumps({"status": "reloaded", "llm_provider": new_cfg.llm_provider}, ensure_ascii=False)

            elif tool_name == "pangu_schema_version":
                from ..store.migrations import get_schema_version
                version = get_schema_version()
                return json.dumps({"schema_version": version}, ensure_ascii=False)

            elif tool_name == "pangu_schema_migrations":
                from ..store.migrations import get_available_migrations
                migrations = get_available_migrations()
                return json.dumps(migrations, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_autonomous_analyze":
                from ..autonomous import analyze_task
                task = arguments.get("task", "")
                result = analyze_task(task)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_api_server_start":
                import uvicorn

                from ..api.server import create_app
                host = arguments.get("host", self.config.host)
                port = arguments.get("port", self.config.port)
                app = create_app()
                config = uvicorn.Config(app, host=host, port=port, log_level="info")
                server = uvicorn.Server(config)
                # 在后台启动
                import asyncio as _asyncio
                _asyncio.create_task(server.serve())
                return json.dumps({
                    "status": "starting",
                    "host": host,
                    "port": port,
                    "health_url": f"http://{host}:{port}/health",
                }, ensure_ascii=False)

            # ── 深度情绪智能 (移植自伏羲) ──

            elif tool_name == "pangu_deep_emotion_trajectory":
                from ..memory.deep_emotion import get_deep_emotion_engine
                engine = get_deep_emotion_engine(self.config)
                return json.dumps(engine.analyze_trajectory(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_deep_emotion_decompose":
                from ..memory.deep_emotion import get_deep_emotion_engine
                engine = get_deep_emotion_engine(self.config)
                return json.dumps(engine.decompose_emotions(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_deep_emotion_stats":
                from ..memory.deep_emotion import get_deep_emotion_engine
                engine = get_deep_emotion_engine(self.config)
                return json.dumps(engine.get_stats(drawers), ensure_ascii=False, indent=2)

            # ── 多策略辩论 (移植自伏羲) ──

            elif tool_name == "pangu_debate_run":
                from ..memory.debate import get_debate_engine
                engine = get_debate_engine(self.config)
                result = engine.run_debate(
                    question=arguments.get("question", ""),
                    strategies_count=arguments.get("strategies_count", 2),
                    context=arguments.get("context", ""),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_debate_stats":
                from ..memory.debate import get_debate_engine
                engine = get_debate_engine(self.config)
                return json.dumps(engine.get_stats(), ensure_ascii=False, indent=2)

            # ── 叙事引擎 (移植自伏羲) ──

            elif tool_name == "pangu_narrative_generate":
                from ..memory.narrative import get_narrative_engine
                engine = get_narrative_engine(self.config)
                return json.dumps(engine.generate_narrative(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_narrative_themes":
                from ..memory.narrative import get_narrative_engine
                engine = get_narrative_engine(self.config)
                return json.dumps(engine.extract_themes(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_narrative_identity":
                from ..memory.narrative import get_narrative_engine
                engine = get_narrative_engine(self.config)
                return json.dumps(engine.identity_statement(drawers), ensure_ascii=False, indent=2)

            # ── 伏羲移植：FTS5 混合搜索 ──

            elif tool_name == "pangu_fts_search":
                engine = FTS5SearchEngine(self.config)
                engine.build_index(drawers)
                result = engine.search(
                    query=arguments.get("query", ""),
                    drawers=drawers,
                    wing=arguments.get("wing"),
                    room=arguments.get("room"),
                    limit=arguments.get("limit", 10),
                    offset=arguments.get("offset", 0),
                    min_importance=arguments.get("min_importance", 0.0),
                    vector_weight=arguments.get("vector_weight"),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_fts_search_stats":
                return json.dumps(get_search_stats(), ensure_ascii=False, indent=2)

            # ── 伏羲移植：全息记忆 ──

            elif tool_name == "pangu_holographic_encode":
                encoder = get_holographic_encoder(self.config)
                holo = encoder.encode(
                    item_id=arguments.get("item_id", f"holo_{int(time.time())}"),
                    raw_text=arguments.get("raw_text", ""),
                    created_at=arguments.get("created_at", ""),
                    wing=arguments.get("wing", ""),
                    room=arguments.get("room", ""),
                    causal_summary=arguments.get("causal_summary", ""),
                    source_type=arguments.get("source_type", ""),
                    agent_id=arguments.get("agent_id", ""),
                )
                return json.dumps({
                    "item_id": holo.item_id,
                    "dimensions": holo.all_dims(),
                    "byte_size": holo.byte_size,
                }, ensure_ascii=False)

            elif tool_name == "pangu_holographic_search":
                result = holographic_search(
                    query=arguments.get("query", ""),
                    drawers=drawers,
                    weights=arguments.get("weights"),
                    top_k=arguments.get("top_k", 10),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            # ── 伏羲移植：记忆法官 ──

            elif tool_name == "pangu_judge_memory":
                judge = get_memory_judge(self.config)
                result = judge.evaluate(
                    task_type=arguments.get("task_type", "unknown"),
                    task_description=arguments.get("task_description", ""),
                    output_summary=arguments.get("output_summary", ""),
                    agent_id=arguments.get("agent_id", ""),
                )
                return json.dumps({
                    "verdict": result.verdict.value,
                    "reasoning": result.reasoning,
                    "confidence": result.confidence,
                    "suggested_tags": result.suggested_tags,
                    "suggested_importance": result.suggested_importance,
                    "suggested_wing": result.suggested_wing,
                    "suggested_room": result.suggested_room,
                }, ensure_ascii=False)

            elif tool_name == "pangu_judge_stats":
                judge = get_memory_judge(self.config)
                return json.dumps(judge.stats(), ensure_ascii=False, indent=2)

            # ── 伏羲移植：自适应参数 ──

            elif tool_name == "pangu_adaptive_params":
                engine = get_adaptive_engine(self.config)
                action = arguments.get("action", "get")
                if action == "reset":
                    params = engine.reset()
                    return json.dumps({"status": "reset", "params": params.to_dict()}, ensure_ascii=False)
                elif action == "history":
                    history = engine.get_history(limit=arguments.get("limit", 10))
                    return json.dumps(history, ensure_ascii=False, indent=2)
                else:
                    return json.dumps(engine.get_params().to_dict(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_adaptive_evaluate":
                engine = get_adaptive_engine(self.config)
                stats = arguments.get("stats", {})
                if not stats:
                    stats = {
                        "total_memories": len(drawers),
                        "growth_rate": 0,
                        "duplicate_rate": 0,
                        "forget_rate": 0,
                        "avg_search_score": 0.5,
                    }
                params = engine.evaluate(stats)
                return json.dumps({
                    "params": params.to_dict(),
                    "updated": bool(params.update_reason and params.update_reason != "no_change"),
                    "reason": params.update_reason,
                }, ensure_ascii=False, indent=2)

            # ── 伏羲移植：工作记忆 ──

            elif tool_name == "pangu_wm_push":
                wm = get_working_memory()
                item = WMItem(
                    id=arguments.get("item_id", f"wm_{int(time.time())}"),
                    content=arguments.get("content", ""),
                    source=arguments.get("source", "mcp"),
                    emotional_valence=arguments.get("emotional_valence", 0.0),
                    urgency=arguments.get("urgency", 0.0),
                    tokens=arguments.get("tokens", len(arguments.get("content", "")) // 4),
                )
                evicted = wm.push(item)
                return json.dumps({
                    "status": "pushed",
                    "item_id": item.id,
                    "evicted": evicted.id if evicted else None,
                    "slots_used": len(wm.slots),
                }, ensure_ascii=False)

            elif tool_name == "pangu_wm_get":
                wm = get_working_memory()
                item_id = arguments.get("item_id")
                if item_id:
                    item = wm.get(item_id)
                    if item:
                        return json.dumps({
                            "id": item.id,
                            "content": item.content[:200],
                            "activation": round(item.activation, 4),
                            "emotional_valence": item.emotional_valence,
                            "access_count": item.access_count,
                        }, ensure_ascii=False)
                    return json.dumps({"error": "item not found"})
                # 返回焦点项
                focus = wm.focus
                if focus:
                    return json.dumps({
                        "focus": {
                            "id": focus.id,
                            "content": focus.content[:200],
                            "activation": round(focus.activation, 4),
                        },
                        "slots_used": len(wm.slots),
                    }, ensure_ascii=False)
                return json.dumps({"slots": [], "slots_used": 0})

            elif tool_name == "pangu_wm_stats":
                wm = get_working_memory()
                return json.dumps(wm.stats, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_wm_clear":
                wm = get_working_memory()
                wm.clear()
                return json.dumps({"status": "cleared"})

            # ── 伏羲移植：记忆脱敏 ──

            elif tool_name == "pangu_sanitize":
                text = arguments.get("text", "")
                level = arguments.get("level", "standard")
                sanitized, redactions = MemorySanitizer.sanitize(text, level=level)
                return json.dumps({
                    "sanitized": sanitized,
                    "redactions": redactions,
                    "total_redactions": sum(redactions.values()),
                }, ensure_ascii=False)

            elif tool_name == "pangu_sanitize_check":
                text = arguments.get("text", "")
                level = arguments.get("level", "standard")
                summary = MemorySanitizer.get_redaction_summary(text, level=level)
                return json.dumps(summary, ensure_ascii=False, indent=2)

            # ── 伏羲移植：再巩固 + 共鸣 ──

            elif tool_name == "pangu_reconsolidate":
                engine = ReconsolidationEngine(self.config)
                result = engine.run(
                    drawers,
                    min_importance=arguments.get("min_importance", 0.3),
                    max_importance=arguments.get("max_importance", 0.7),
                    limit=arguments.get("limit", 20),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_resonance":
                engine = ResonanceEngine(self.config)
                matches = engine.find_resonance(
                    drawers,
                    limit=arguments.get("limit", 30),
                    sim_threshold=arguments.get("sim_threshold", 0.7),
                )
                return json.dumps(matches, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cross_wing_resonance":
                engine = ResonanceEngine(self.config)
                matches = engine.find_cross_wing_resonance(
                    drawers,
                    sim_threshold=arguments.get("sim_threshold", 0.65),
                )
                return json.dumps(matches, ensure_ascii=False, indent=2)

            # ── 伏羲移植：知识蒸馏增强 ──

            elif tool_name == "pangu_distill_knowledge":
                tower = DistillationTower(self.config)
                texts = arguments.get("texts", [])
                source_ids = arguments.get("source_ids", [])
                if not texts:
                    texts = [d.content for d in drawers[:10]]
                card = tower.distill(texts, source_ids=source_ids)
                return json.dumps(card, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distill_causal_chains":
                tower = DistillationTower(self.config)
                chains = tower.get_causal_chains()
                return json.dumps(chains, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distill_graph":
                tower = DistillationTower(self.config)
                graph = tower.get_knowledge_graph()
                return json.dumps(graph, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distill_stats":
                tower = DistillationTower(self.config)
                return json.dumps(tower.stats(), ensure_ascii=False, indent=2)

            # ── 伏羲移植：向量索引 ──

            elif tool_name == "pangu_vector_index_stats":
                idx = get_vector_index()
                return json.dumps(idx.stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_vector_index_build":
                from pangu.memory.onnx_embedder import get_onnx_embedder
                embedder = get_onnx_embedder()
                idx = get_vector_index()
                success = idx.build_from_drawers(drawers, embedder=embedder,
                                                  min_count=arguments.get("min_count", 1))
                return json.dumps({
                    "status": "built" if success else "skipped",
                    "stats": idx.stats(),
                }, ensure_ascii=False)

            # ── 伏羲移植：注意力系统 ──

            elif tool_name == "pangu_attention_state":
                attn = get_attention_system()
                return json.dumps(attn.stats, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_attention_switch":
                attn = get_attention_system()
                strategy_str = arguments.get("strategy", "bottom_up")
                reason = arguments.get("reason", "")
                try:
                    strategy = AttentionStrategy(strategy_str)
                except ValueError:
                    return json.dumps({"error": f"unknown strategy: {strategy_str}, valid: {[s.value for s in AttentionStrategy]}"})
                old, new = attn.switch(strategy, reason=reason)
                return json.dumps({
                    "old": old.value,
                    "new": new.value,
                    "reason": reason,
                }, ensure_ascii=False)

            elif tool_name == "pangu_attention_ab_test":
                attn = get_attention_system()
                action = arguments.get("action", "start")
                if action == "stop":
                    result = attn.stop_ab_test()
                    return json.dumps(result, ensure_ascii=False, indent=2)
                else:
                    strategy_a = arguments.get("strategy_a", "bottom_up")
                    strategy_b = arguments.get("strategy_b", "focus")
                    try:
                        sa = AttentionStrategy(strategy_a)
                        sb = AttentionStrategy(strategy_b)
                    except ValueError:
                        return json.dumps({"error": "invalid strategy name"})
                    attn.start_ab_test(sa, sb, duration_days=arguments.get("duration_days", 7))
                    return json.dumps({
                        "status": "started",
                        "strategy_a": sa.value,
                        "strategy_b": sb.value,
                    }, ensure_ascii=False)

            # ── 伏羲移植：增强评估 ──

            elif tool_name == "pangu_enhanced_contradictions":
                detector = EnhancedContradictionDetector(self.config)
                result = detector.detect_contradictions(drawers, top_k=arguments.get("top_k", 50))
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_trajectory_track":
                tracker = TrajectoryTracker(self.config)
                result = tracker.track(
                    drawers,
                    item_id=arguments.get("item_id"),
                    wing=arguments.get("wing"),
                    room=arguments.get("room"),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_trajectory_compare":
                tracker = TrajectoryTracker(self.config)
                result = tracker.compare_periods(
                    drawers,
                    period_a=arguments.get("period_a", ""),
                    period_b=arguments.get("period_b", ""),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            # ── 伏羲移植：流式索引 ──

            elif tool_name == "pangu_streaming_index":
                from ..search.embedder import VectorEmbedder
                indexer = StreamingIndexer(self.config)
                embedder = VectorEmbedder(self.config)
                result = indexer.index(drawers, embedder=embedder)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_streaming_stats":
                indexer = StreamingIndexer(self.config)
                return json.dumps(indexer.stats(), ensure_ascii=False, indent=2)

            # ── 伏羲移植：验证循环 ──

            elif tool_name == "pangu_verify":
                loop = VerificationLoop(project_path=arguments.get("project_path", "."))
                result = loop.run_full_verification()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_verify_phase":
                phase = arguments.get("phase", "build")
                loop = VerificationLoop(project_path=arguments.get("project_path", "."))
                phase_map = {
                    "build": loop.run_build,
                    "type_check": loop.run_type_check,
                    "lint": loop.run_lint,
                    "tests": loop.run_tests,
                    "security": loop.run_security_scan,
                    "diff_review": loop.run_diff_review,
                }
                if phase in phase_map:
                    result = phase_map[phase]()
                    return json.dumps({
                        "phase": result.phase,
                        "passed": result.passed,
                        "output": result.output[:1000],
                        "warnings": result.warnings,
                        "errors": result.errors,
                    }, ensure_ascii=False)
                return json.dumps({"error": f"unknown phase: {phase}"})

            # ── 伏羲移植：差分隐私 ──

            elif tool_name == "pangu_privacy_stats":
                dp = DifferentialPrivacy(
                    epsilon=arguments.get("epsilon", 1.0),
                    delta=arguments.get("delta", 1e-5),
                )
                return json.dumps(dp.stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_privatize_count":
                dp = DifferentialPrivacy(
                    epsilon=arguments.get("epsilon", 1.0),
                    delta=arguments.get("delta", 1e-5),
                )
                count = arguments.get("count", 0)
                result = dp.privatize_count(count)
                return json.dumps({
                    "original": count,
                    "privatized": result,
                    "budget": dp.stats(),
                }, ensure_ascii=False)

            # ── ONNX 本地加速嵌入 ──

            elif tool_name == "pangu_onnx_embed":
                from pangu.memory.onnx_embedder import get_onnx_embedder
                emb = get_onnx_embedder()
                # 尝试从多个位置获取text参数
                params = request.get("params", {}) if isinstance(request, dict) else {}
                text = arguments.get("text") or params.get("text") or params.get("arguments", {}).get("text") or ""
                if not text:
                    # 尝试从工具名提取（最后手段）
                    text = tool_name.split("_")[-1] if "_" in tool_name else "test"
                vec = emb.embed(text)
                return json.dumps({
                    "text": text,
                    "dim": len(vec) if vec else 0,
                    "vector": vec,
                    "source": "onnx" if emb.is_loaded else "unavailable",
                }, ensure_ascii=False)

            elif tool_name == "pangu_onnx_embed_batch":
                from pangu.memory.onnx_embedder import get_onnx_embedder
                emb = get_onnx_embedder()
                texts = arguments.get("texts", [])
                results = emb.embed_batch(texts)
                return json.dumps({
                    "count": len(results),
                    "dim": emb.embedding_dim,
                    "vectors": results,
                    "source": "onnx" if emb.is_loaded else "unavailable",
                }, ensure_ascii=False)

            elif tool_name == "pangu_onnx_status":
                from pangu.memory.onnx_embedder import get_onnx_embedder
                emb = get_onnx_embedder()
                return json.dumps(emb.get_stats(), ensure_ascii=False, indent=2, default=str)

            elif tool_name == "pangu_onnx_similarity":
                import math as _math

                from pangu.memory.onnx_embedder import get_onnx_embedder
                emb = get_onnx_embedder()
                text_a = arguments.get("text_a", "")
                text_b = arguments.get("text_b", "")
                va = emb.embed(text_a)
                vb = emb.embed(text_b)
                if va is None or vb is None:
                    sim = None
                else:
                    dot = sum(x * y for x, y in zip(va, vb, strict=False))
                    na = _math.sqrt(sum(x * x for x in va))
                    nb = _math.sqrt(sum(y * y for y in vb))
                    sim = dot / (na * nb + 1e-9)
                return json.dumps({
                    "text_a": text_a,
                    "text_b": text_b,
                    "cosine_similarity": sim,
                    "source": "onnx" if emb.is_loaded else "unavailable",
                }, ensure_ascii=False)

            # ── LLM 响应缓存工具 ──
            elif tool_name == "pangu_llm_cache_stats":
                return json.dumps(self.llm.get_stats(), ensure_ascii=False)

            elif tool_name == "pangu_llm_cache_top":
                limit = int(arguments.get("limit", 10))
                if self._persistent_cache is None:
                    return json.dumps({"error": "persistent cache disabled"}, ensure_ascii=False)
                return json.dumps(
                    self._persistent_cache.get_top_keys(limit),
                    ensure_ascii=False,
                )

            elif tool_name == "pangu_llm_cache_clear":
                cleared = {"memory": 0, "persistent": 0}
                if arguments.get("memory", True):
                    cleared["memory"] = self.llm.clear_cache()
                if arguments.get("persistent", False):
                    cleared["persistent"] = self.llm.clear_persistent_cache()
                return json.dumps({"status": "cleared", **cleared}, ensure_ascii=False)

            elif tool_name == "pangu_llm_cache_metrics":
                return self.llm.export_prometheus_metrics()

            elif tool_name == "pangu_llm_cache_warmup":
                prompts = arguments.get("prompts") or []
                concurrency = int(arguments.get("concurrency", 3))
                skip_existing = bool(arguments.get("skip_existing", True))
                result = await self.llm.warmup_cache(
                    prompts, concurrency=concurrency, skip_existing=skip_existing
                )
                return json.dumps(result, ensure_ascii=False)

            elif tool_name == "pangu_llm_cache_warmup_log":
                limit = int(arguments.get("limit", 20))
                log_path = arguments.get("log_path", "")
                records = LLMEngine.get_warmup_history(log_path=log_path, limit=limit)
                return json.dumps({"count": len(records), "records": records}, ensure_ascii=False)

            elif tool_name == "pangu_llm_cache_vacuum":
                return json.dumps(
                    self.llm.vacuum_persistent_cache(), ensure_ascii=False
                )

            elif tool_name == "pangu_llm_cache_config":
                cfg_keys = [
                    "llm_cache_enabled", "llm_cache_max", "llm_cache_persist",
                    "llm_cache_persist_path", "llm_cache_ttl_days", "llm_cache_max_disk_mb",
                    "llm_cache_write_throttle", "llm_cache_warmup_on_start",
                    "llm_cache_warmup_prompts", "llm_cache_vacuum_on_start",
                    "llm_cache_vacuum_interval_hours",
                ]
                return json.dumps(
                    {k: getattr(self.config, k, None) for k in cfg_keys},
                    ensure_ascii=False,
                )

            # ── 自然语言查询 + 记忆推荐 ──
            elif tool_name == "pangu_natural_query":
                from ..memory.natural_query import natural_language_search
                query = arguments.get("query", "")
                limit = int(arguments.get("limit", 10))
                results = natural_language_search(query, drawers, limit)
                return json.dumps(results, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend":
                from ..memory.natural_query import MemoryRecommender
                context = arguments.get("context", "")
                limit = int(arguments.get("limit", 5))
                recommender = MemoryRecommender(drawers)
                results = recommender.recommend(context, limit)
                return json.dumps(results, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_conversational_search":
                from ..memory.natural_query import natural_language_search
                query = arguments.get("query", "")
                session_id = arguments.get("session_id", "")
                clarify = arguments.get("clarify", False)

                # 简单的对话式搜索
                results = natural_language_search(query, drawers, limit=10)

                # 如果需要澄清，添加提示
                if clarify and len(results) > 5:
                    results.append({
                        "type": "clarification",
                        "message": f"找到 {len(results)} 条相关记忆，是否需要更精确的搜索？",
                        "suggestions": [
                            "缩小时间范围",
                            "指定空间(Wing)",
                            "提高重要性阈值"
                        ]
                    })

                return json.dumps(results, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_memory_insights":
                from ..memory.natural_query import _analyze_memories, _timeline_query
                from datetime import timedelta

                topic = arguments.get("topic", "")
                time_range = arguments.get("time_range", "")

                # 过滤记忆
                filtered = drawers
                if topic:
                    filtered = [d for d in filtered if topic.lower() in d.content.lower()]

                if time_range:
                    try:
                        days = int(time_range.replace('d', ''))
                        cutoff = datetime.now() - timedelta(days=days)
                        filtered = [d for d in filtered if datetime.fromisoformat(d.created_at) >= cutoff]
                    except:
                        pass

                # 分析
                analysis = _analyze_memories(filtered, {"wing": None})
                insights = {
                    "analysis": analysis[0] if analysis else {},
                    "top_memories": [
                        {"content": d.content[:100], "importance": d.importance}
                        for d in sorted(filtered, key=lambda x: x.importance, reverse=True)[:5]
                    ],
                    "patterns": self._discover_simple_patterns(filtered),
                }

                return json.dumps(insights, ensure_ascii=False, indent=2)

            # ── 神经记忆系统 ──
            elif tool_name == "pangu_neural_stats":
                from ..memory.neural_memory import get_neural_engine
                engine = get_neural_engine()
                return json.dumps(engine.stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_neural_sleep":
                from ..memory.neural_memory import get_neural_engine
                engine = get_neural_engine()
                result = engine.sleep()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_neural_spreading":
                from ..memory.neural_memory import get_neural_engine
                engine = get_neural_engine()
                seed_ids = arguments.get("seed_ids", [])
                depth = arguments.get("depth", engine.config.neural_spreading_depth)
                activations = engine.neocortex.activate_spreading(
                    seed_ids,
                    decay_factor=engine.config.neural_spreading_decay,
                    max_depth=depth,
                )
                results = []
                for mid, act in activations[:20]:
                    mem = engine.neocortex.get(mid)
                    if mem:
                        results.append({
                            "id": mid,
                            "content": mem.content[:200],
                            "activation": round(act, 4),
                            "type": mem.memory_type.value,
                            "state": mem.state.value,
                        })
                return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_neural_inhibition":
                from ..memory.neural_memory import get_neural_engine
                engine = get_neural_engine()
                memory_ids = arguments.get("memory_ids", [])
                activations = engine.neocortex.mutual_inhibition(memory_ids)
                return json.dumps({
                    "activations": {k: round(v, 4) for k, v in activations.items()},
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_neural_decay":
                from ..memory.neural_memory import get_neural_engine
                engine = get_neural_engine()
                forgotten = engine.apply_global_decay()
                return json.dumps({
                    "forgotten_count": len(forgotten),
                    "forgotten_ids": [m.id for m in forgotten],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_importance_feedback":
                from ..memory.retrieval import importance_feedback
                result = importance_feedback(
                    arguments["drawer_id"],
                    arguments["signal"],
                    drawers,
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_fusion":
                from ..lifecycle import LifecycleManager
                mgr = LifecycleManager(self.config)
                result = mgr.run_auto_fusion()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cross_session_links":
                from ..memory.cross_session import CrossSessionIntegrator
                integrator = CrossSessionIntegrator(self.config)
                min_sim = arguments.get("min_similarity", 0.4)
                max_links = arguments.get("max_links", 10)
                links = integrator.find_cross_session_links(drawers[-10:], drawers, min_sim, max_links)
                return json.dumps({"links": links, "count": len(links)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_compress":
                from ..lifecycle import LifecycleManager
                mgr = LifecycleManager(self.config)
                result = mgr.run_auto_compress()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_validate_memories":
                from ..memory.memory_validator import MemoryValidator
                validator = MemoryValidator(self.config)
                result = validator.validate_all(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_kg_auto_extract":
                from ..memory.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph(self.config)
                max_d = arguments.get("max_drawers", 50)
                result = kg.auto_extract_entities(drawers, max_d)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_kg_cross_domain":
                from ..memory.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph(self.config)
                source = arguments.get("source_domain", "")
                target = arguments.get("target_domain", "")
                result = kg.cross_domain_transfer(source, target)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_kg_similar_patterns":
                from ..memory.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph(self.config)
                entity_id = arguments.get("entity_id", "")
                patterns = kg.find_similar_patterns(entity_id)
                return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_hybrid_search":
                from ..memory.hybrid_search import hybrid_search
                query = arguments.get("query", "")
                limit = arguments.get("limit", 10)
                results = hybrid_search(query, drawers, self.config, limit)
                return json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cluster_by_tags":
                from ..memory.cluster import cluster_by_tags, get_cluster_summary
                query = arguments.get("query", "")
                limit = arguments.get("limit", 20)
                results = hybrid_search(query, drawers, self.config, limit)
                clusters = cluster_by_tags(results)
                summary = get_cluster_summary(clusters)
                return json.dumps({"clusters": summary, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cluster_by_time":
                from ..memory.cluster import cluster_by_time, get_cluster_summary
                query = arguments.get("query", "")
                buckets = arguments.get("buckets", 3)
                results = hybrid_search(query, drawers, self.config, 20)
                clusters = cluster_by_time(results, buckets)
                summary = get_cluster_summary(clusters)
                return json.dumps({"clusters": summary, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_hierarchical_cluster":
                from ..memory.cluster import hierarchical_cluster
                query = arguments.get("query", "")
                max_clusters = arguments.get("max_clusters", 5)
                results = hybrid_search(query, drawers, self.config, limit=20)
                clusters = hierarchical_cluster(results, max_clusters=max_clusters)
                return json.dumps({"clusters": clusters, "total_clusters": len(clusters)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_dedup_results":
                from ..memory.cluster import deduplicate_results
                query = arguments.get("query", "")
                limit = arguments.get("limit", 10)
                results = hybrid_search(query, drawers, self.config, limit=limit)
                deduped = deduplicate_results(results)
                return json.dumps({"results": deduped, "total": len(deduped), "removed": len(results) - len(deduped)}, ensure_ascii=False, indent=2)

            # ── 多Agent协作记忆 ──
            elif tool_name == "pangu_multi_register":
                from ..memory.multi_agent import get_multi_agent_memory
                mam = get_multi_agent_memory()
                agent_id = arguments.get("agent_id", "")
                priority = arguments.get("priority", 5)
                mam.register_agent(agent_id, priority)
                return json.dumps({"status": "registered", "agent_id": agent_id, "priority": priority}, ensure_ascii=False)

            elif tool_name == "pangu_multi_write":
                from ..memory.multi_agent import get_multi_agent_memory, MemoryScope
                mam = get_multi_agent_memory()
                agent_id = arguments.get("agent_id", "")
                content = arguments.get("content", "")
                scope_str = arguments.get("scope", "public")
                tags = arguments.get("tags", [])
                scope = MemoryScope(scope_str) if scope_str in ["private", "shared", "public"] else MemoryScope.PUBLIC
                mem = mam.write(agent_id, content, scope=scope, tags=tags)
                return json.dumps({"id": mem.id, "content": mem.content[:50], "scope": mem.scope.value}, ensure_ascii=False)

            elif tool_name == "pangu_multi_read":
                from ..memory.multi_agent import get_multi_agent_memory
                mam = get_multi_agent_memory()
                agent_id = arguments.get("agent_id", "")
                tags = arguments.get("tags", None)
                results = mam.read(agent_id, tags=tags)
                return json.dumps({"count": len(results), "memories": [{"id": m.id, "content": m.content[:50], "owner": m.owner, "scope": m.scope.value} for m in results[:10]]}, ensure_ascii=False)

            elif tool_name == "pangu_multi_agents":
                from ..memory.multi_agent import get_multi_agent_memory
                mam = get_multi_agent_memory()
                agents = mam.get_agents()
                return json.dumps({"agents": agents, "count": len(agents)}, ensure_ascii=False)

            # ── 图推理 ──
            elif tool_name == "pangu_graph_infer":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                query = arguments.get("query", "")
                result = gr.infer(query)
                summary = gr.get_reasoning_summary(result)
                return json.dumps({
                    "entities": len(result.entities),
                    "paths": len(result.paths),
                    "inferences": len(result.inferences),
                    "confidence": result.confidence,
                    "summary": summary,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_contradictions":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                contradictions = gr.detect_contradictions()
                return json.dumps({
                    "contradictions": contradictions,
                    "count": len(contradictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_causal_chain":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                entity_id = arguments.get("entity_id", "")
                max_depth = arguments.get("max_depth", 5)
                chain = gr.causal_chain_analysis(entity_id, max_depth)
                return json.dumps({"chain": chain, "length": len(chain)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_temporal":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                query = arguments.get("query", "")
                result = gr.temporal_reasoning(query)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_analogy":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                query = arguments.get("query", "")
                result = gr.analogy_detection(query)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_visualize":
                from ..memory.graph_reasoning import GraphReasoning
                gr = GraphReasoning(self.config)
                query = arguments.get("query", "")
                result = gr.infer(query)
                visualization = gr.visualize_reasoning(result)
                return json.dumps(visualization, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_proactive_predict":
                from ..memory.proactive import get_proactive_engine
                engine = get_proactive_engine(self.config)
                context = arguments.get("context", "")
                limit = arguments.get("limit", 5)
                predictions = engine.predict(context, drawers, limit)
                return json.dumps({
                    "predictions": [
                        {"id": p.memory_id, "content": p.content, "score": p.relevance_score, "reason": p.reason}
                        for p in predictions
                    ],
                    "count": len(predictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_proactive_suggest":
                from ..memory.proactive import get_proactive_engine
                engine = get_proactive_engine(self.config)
                context = engine.get_context()
                limit = arguments.get("limit", 5)
                predictions = engine.predict(context, drawers, limit)
                return json.dumps({
                    "context": context[:100] if context else "",
                    "predictions": [
                        {"id": p.memory_id, "content": p.content, "score": p.relevance_score, "reason": p.reason}
                        for p in predictions
                    ],
                    "count": len(predictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_context_status":
                from ..memory.proactive import get_proactive_engine
                engine = get_proactive_engine(self.config)
                context = engine.get_context()
                return json.dumps({
                    "context": context[:200] if context else "",
                    "context_length": len(context),
                    "history_size": len(engine._context_history),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_analyze_emotion":
                from ..memory.emotional_intelligence import get_emotional_intelligence
                ei = get_emotional_intelligence(self.config)
                text = arguments.get("text", "")
                result = ei.analyze_emotion(text)
                ei.record_emotion(text, result)
                return json.dumps({
                    "emotion": result.emotion.value,
                    "intensity": result.intensity,
                    "keywords": result.keywords,
                    "confidence": result.confidence,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_emotion_stats":
                from ..memory.emotional_intelligence import get_emotional_intelligence
                ei = get_emotional_intelligence(self.config)
                return json.dumps(ei.get_emotion_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_predict_emotion":
                from ..memory.emotional_intelligence import get_emotional_intelligence
                ei = get_emotional_intelligence(self.config)
                context = arguments.get("context", "")
                result = ei.predict_emotion(context)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend_interaction":
                from ..memory.emotional_intelligence import get_emotional_intelligence
                ei = get_emotional_intelligence(self.config)
                emotion_state = arguments.get("emotion_state", {})
                result = ei.recommend_interaction(emotion_state)
                return json.dumps({"recommendation": result}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_generate_ideas":
                from ..memory.creative_thinking import get_creative_thinking
                ct = get_creative_thinking(self.config)
                limit = arguments.get("limit", 5)
                ideas = ct.generate_ideas(drawers)
                return json.dumps({
                    "ideas": [
                        {"title": i.title, "description": i.description, "category": i.category, "confidence": i.confidence}
                        for i in ideas[:limit]
                    ],
                    "count": len(ideas),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_discover_patterns":
                from ..memory.creative_thinking import get_creative_thinking
                ct = get_creative_thinking(self.config)
                patterns = ct.discover_patterns(drawers)
                return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_generate_novel":
                from ..memory.creative_thinking import get_creative_thinking
                ct = get_creative_thinking(self.config)
                domain = arguments.get("domain", "")
                context = arguments.get("context", "")
                ideas = ct.generate_novel_ideas(domain, context, drawers)
                return json.dumps({"ideas": ideas, "count": len(ideas)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_discover_knowledge":
                from ..memory.autonomous_learning import get_autonomous_learning
                al = get_autonomous_learning(self.config)
                discoveries = al.discover_knowledge(drawers)
                return json.dumps({"discoveries": discoveries, "count": len(discoveries)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_generate_hypotheses":
                from ..memory.autonomous_learning import get_autonomous_learning
                al = get_autonomous_learning(self.config)
                limit = arguments.get("limit", 5)
                hypotheses = al.generate_hypotheses(drawers)
                return json.dumps({
                    "hypotheses": [
                        {"statement": h.statement, "confidence": h.confidence, "status": h.status}
                        for h in hypotheses[:limit]
                    ],
                    "count": len(hypotheses),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_learning_stats":
                from ..memory.autonomous_learning import get_autonomous_learning
                al = get_autonomous_learning(self.config)
                return json.dumps(al.get_learning_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_learn":
                from ..memory.autonomous_learning import get_autonomous_learning
                al = get_autonomous_learning(self.config)
                result = al.auto_learn(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_self_diagnose":
                from ..memory.self_evolution import get_evolution_engine
                se = get_evolution_engine(self.config)
                diagnosis = se.diagnose(drawers)
                return json.dumps({
                    "issues": [
                        {"category": d.category, "severity": d.severity,
                         "description": d.description, "recommendation": d.recommendation}
                        for d in diagnosis
                    ],
                    "total_issues": len(diagnosis),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_evolution_plan":
                from ..memory.self_evolution import get_evolution_engine
                se = get_evolution_engine(self.config)
                diagnosis = se.diagnose(drawers)
                plan = se.generate_evolution_plan(diagnosis)
                return json.dumps({
                    "name": plan.name,
                    "actions": plan.actions,
                    "expected_improvement": plan.expected_improvement,
                    "priority": plan.priority,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_performance_trend":
                from ..memory.self_evolution import get_evolution_engine
                se = get_evolution_engine(self.config)
                metric = arguments.get("metric", "search_score")
                trend = se.get_performance_trend(metric)
                return json.dumps(trend, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_evolution_stats":
                from ..memory.self_evolution import get_evolution_engine
                se = get_evolution_engine(self.config)
                return json.dumps(se.get_evolution_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_temporal_timeline":
                from ..memory.temporal_reasoning import get_temporal_engine
                te = get_temporal_engine(self.config)
                events = te.build_timeline(drawers)
                return json.dumps({
                    "events": [
                        {"id": e.memory_id, "content": e.content,
                         "timestamp": e.timestamp, "wing": e.wing}
                        for e in events
                    ],
                    "count": len(events),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_temporal_relations":
                from ..memory.temporal_reasoning import get_temporal_engine
                te = get_temporal_engine(self.config)
                rels = te.find_temporal_relations(drawers)
                return json.dumps({
                    "relations": [
                        {"before": r.before_id, "after": r.after_id,
                         "relation": r.relation, "confidence": r.confidence}
                        for r in rels
                    ],
                    "count": len(rels),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_temporal_query":
                from ..memory.temporal_reasoning import get_temporal_engine
                te = get_temporal_engine(self.config)
                start = arguments.get("start")
                end = arguments.get("end")
                results = te.query_by_time_range(drawers, start, end)
                return json.dumps({
                    "results": [{"id": d.id, "content": d.content[:80]} for d in results],
                    "count": len(results),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_temporal_stats":
                from ..memory.temporal_reasoning import get_temporal_engine
                te = get_temporal_engine(self.config)
                return json.dumps(te.get_temporal_stats(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_compress_by_tags":
                from ..memory.semantic_compression import get_compressor
                comp = get_compressor(self.config)
                result = comp.compress_by_tags(drawers)
                return json.dumps({
                    "original_count": result.original_count,
                    "compressed_count": result.compressed_count,
                    "merged_groups": len(result.merged_groups),
                    "information_loss": result.information_loss,
                    "tokens_saved": result.tokens_saved,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_duplicates":
                from ..memory.semantic_compression import get_compressor
                comp = get_compressor(self.config)
                threshold = arguments.get("threshold", 0.8)
                dups = comp.find_semantic_duplicates(drawers, threshold)
                return json.dumps({"duplicates": dups, "count": len(dups)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_reassess_importance":
                from ..memory.semantic_compression import get_compressor
                comp = get_compressor(self.config)
                updates = comp.reassess_importance(drawers)
                return json.dumps({"updates": updates, "count": len(updates)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_compression_stats":
                from ..memory.semantic_compression import get_compressor
                comp = get_compressor(self.config)
                return json.dumps(comp.get_compression_stats(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_agent_register":
                from ..memory.collaborative_intelligence import get_collaborative
                ci = get_collaborative(self.config)
                result = ci.register_agent(
                    arguments["agent_id"], arguments["name"],
                    arguments.get("specialties", []),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_agent_share":
                from ..memory.collaborative_intelligence import get_collaborative
                ci = get_collaborative(self.config)
                result = ci.share_knowledge(
                    arguments["from_agent"], arguments["to_agent"],
                    arguments["knowledge_ids"],
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_collaborative_reason":
                from ..memory.collaborative_intelligence import get_collaborative
                ci = get_collaborative(self.config)
                result = ci.collaborative_reasoning(
                    arguments["task"], arguments.get("agent_ids"),
                )
                return json.dumps({
                    "task": result.task,
                    "participants": result.participants,
                    "consensus": result.consensus,
                    "confidence": result.confidence,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_agent_stats":
                from ..memory.collaborative_intelligence import get_collaborative
                ci = get_collaborative(self.config)
                return json.dumps(ci.get_agent_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_causal_discover":
                from ..memory.causal_reasoning import get_causal_engine
                cr = get_causal_engine(self.config)
                links = cr.discover_causal_links(drawers)
                return json.dumps({
                    "links": [
                        {"cause": l.cause_text[:50], "effect": l.effect_text[:50],
                         "type": l.relation_type, "confidence": l.confidence}
                        for l in links
                    ],
                    "count": len(links),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_causal_chains":
                from ..memory.causal_reasoning import get_causal_engine
                cr = get_causal_engine(self.config)
                cr.discover_causal_links(drawers)
                chains = cr.build_causal_chains()
                return json.dumps({
                    "chains": [
                        {"id": c.chain_id, "root": c.root_cause[:50],
                         "effect": c.final_effect[:50], "length": c.chain_length,
                         "confidence": c.overall_confidence}
                        for c in chains
                    ],
                    "count": len(chains),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_counterfactual":
                from ..memory.causal_reasoning import get_causal_engine
                cr = get_causal_engine(self.config)
                cr.discover_causal_links(drawers)
                result = cr.counterfactual_reasoning(
                    arguments["cause_id"], arguments["counterfactual"], drawers,
                )
                return json.dumps({
                    "original": result.original_cause,
                    "counterfactual": result.counterfactual,
                    "predicted_effect": result.predicted_effect,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_root_cause":
                from ..memory.causal_reasoning import get_causal_engine
                cr = get_causal_engine(self.config)
                cr.discover_causal_links(drawers)
                result = cr.root_cause_analysis(arguments["effect_text"], drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_causal_stats":
                from ..memory.causal_reasoning import get_causal_engine
                cr = get_causal_engine(self.config)
                return json.dumps(cr.get_causal_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_explain_search":
                from ..memory.explainable_search import get_explainable_engine
                ee = get_explainable_engine(self.config)
                query = arguments.get("query", "")
                result_ids = arguments.get("result_ids", [])
                mock_results = [{"id": rid, "score": 0.5} for rid in result_ids]
                explanations = ee.explain_results(query, mock_results, drawers)
                return json.dumps({
                    "explanations": [
                        {"id": e.memory_id, "preview": e.content_preview,
                         "score": e.score, "factors": e.factors,
                         "reason": e.primary_reason}
                        for e in explanations
                    ],
                    "count": len(explanations),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_search_suggestions":
                from ..memory.explainable_search import get_explainable_engine
                ee = get_explainable_engine(self.config)
                query = arguments.get("query", "")
                suggestions = ee.suggest_improvement(query, [])
                return json.dumps({"suggestions": suggestions}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_anomaly_scan":
                from ..memory.anomaly_detection import get_detector
                det = get_detector(self.config)
                result = det.full_scan(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_anomaly_content":
                from ..memory.anomaly_detection import get_detector
                det = get_detector(self.config)
                anomalies = det.detect_content_anomalies(drawers)
                return json.dumps({
                    "anomalies": [{"type": a.anomaly_type, "severity": a.severity,
                                   "description": a.description} for a in anomalies],
                    "count": len(anomalies),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_anomaly_stats":
                from ..memory.anomaly_detection import get_detector
                det = get_detector(self.config)
                return json.dumps(det.get_anomaly_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_synthesize":
                from ..memory.knowledge_synthesis import get_synthesizer
                ks = get_synthesizer(self.config)
                limit = arguments.get("limit", 10)
                insights = ks.synthesize_by_topic(drawers)
                return json.dumps({
                    "insights": [
                        {"topic": i.topic, "summary": i.summary, "sources": i.sources,
                         "confidence": i.confidence}
                        for i in insights[:limit]
                    ],
                    "count": len(insights),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_find_contradictions":
                from ..memory.knowledge_synthesis import get_synthesizer
                ks = get_synthesizer(self.config)
                contradictions = ks.detect_contradictions(drawers)
                return json.dumps({
                    "contradictions": [
                        {"topic": c.topic, "claim_a": c.claim_a[:50],
                         "claim_b": c.claim_b[:50], "severity": c.severity}
                        for c in contradictions
                    ],
                    "count": len(contradictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_core_insights":
                from ..memory.knowledge_synthesis import get_synthesizer
                ks = get_synthesizer(self.config)
                top_k = arguments.get("top_k", 10)
                insights = ks.extract_core_insights(drawers, top_k)
                return json.dumps({"insights": insights, "count": len(insights)}, ensure_ascii=False, indent=2)

            # ── 共鸣匹配 ──

            elif tool_name == "pangu_resonance_find":
                from ..memory.resonance import get_resonance_engine
                engine = get_resonance_engine(self.config)
                matches = engine.find_resonance(
                    drawers,
                    limit=arguments.get("limit", 30),
                    sim_threshold=arguments.get("sim_threshold", 0.7),
                )
                edges = engine.build_edges(matches, drawers)
                return json.dumps({
                    "matches": matches,
                    "edges_created": len(edges),
                    "total_matches": len(matches),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_resonance_edges":
                from ..memory.resonance import get_resonance_engine
                engine = get_resonance_engine(self.config)
                matches = arguments.get("matches", [])
                edges = engine.build_edges(
                    matches, drawers,
                    max_edges=arguments.get("max_edges", 5),
                )
                return json.dumps({"edges": edges, "count": len(edges)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_resonance_stats":
                from ..memory.resonance import get_resonance_engine
                engine = get_resonance_engine(self.config)
                return json.dumps(engine.stats(), ensure_ascii=False, indent=2)

            # ── 意图预测 ──

            elif tool_name == "pangu_intent_predict":
                from ..memory.intent_prediction import get_intent_predictor
                predictor = get_intent_predictor(self.config)
                intent = predictor.predict_intent(drawers, arguments.get("context", ""))
                task_chain = predictor.track_task_chain(drawers)
                suggestions = predictor.suggest_next(drawers, intent, task_chain)
                return json.dumps({
                    "intent": intent,
                    "task_chain": task_chain,
                    "suggestions": suggestions,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_intent_tasks":
                from ..memory.intent_prediction import get_intent_predictor
                predictor = get_intent_predictor(self.config)
                task_chain = predictor.track_task_chain(drawers)
                return json.dumps(task_chain, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_intent_stats":
                from ..memory.intent_prediction import get_intent_predictor
                predictor = get_intent_predictor(self.config)
                return json.dumps(predictor.stats(), ensure_ascii=False, indent=2)

            # ── 知识综合增强 ──

            elif tool_name == "pangu_synthesis_cross_cluster":
                from ..memory.knowledge_synthesis import get_synthesizer
                ks = get_synthesizer(self.config)
                insights = ks.cross_cluster_association(drawers)
                return json.dumps({"insights": insights, "count": len(insights)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_synthesis_gaps":
                from ..memory.knowledge_synthesis import get_synthesizer
                ks = get_synthesizer(self.config)
                gaps = ks.knowledge_gap_detection(drawers)
                return json.dumps({"gaps": gaps, "count": len(gaps)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_predict_queries":
                from ..memory.predictive_analytics import get_analytics
                pa = get_analytics(self.config)
                top_k = arguments.get("top_k", 5)
                predictions = pa.predict_next_queries([], top_k)
                return json.dumps({
                    "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
                    "count": len(predictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_predict_forgetting":
                from ..memory.predictive_analytics import get_analytics
                pa = get_analytics(self.config)
                threshold = arguments.get("days_threshold", 30)
                predictions = pa.predict_forgetting(drawers, threshold)
                return json.dumps({
                    "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
                    "count": len(predictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_growth_trend":
                from ..memory.predictive_analytics import get_analytics
                pa = get_analytics(self.config)
                trend = pa.analyze_growth_trend(drawers)
                return json.dumps(trend, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_hot_topics":
                from ..memory.predictive_analytics import get_analytics
                pa = get_analytics(self.config)
                top_k = arguments.get("top_k", 5)
                predictions = pa.predict_hot_topics(drawers, top_k)
                return json.dumps({
                    "predictions": [{"statement": p.statement, "confidence": p.confidence} for p in predictions],
                    "count": len(predictions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_predictive_stats":
                from ..memory.predictive_analytics import get_analytics
                pa = get_analytics(self.config)
                return json.dumps(pa.get_prediction_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_arch_analyze":
                from ..memory.adaptive_architecture import get_architecture
                aa = get_architecture(self.config)
                return json.dumps(aa.analyze_architecture(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_arch_suggest":
                from ..memory.adaptive_architecture import get_architecture
                aa = get_architecture(self.config)
                suggestions = aa.suggest_restructuring(drawers)
                return json.dumps({
                    "suggestions": [{"action": s.action, "reason": s.reason, "priority": s.priority} for s in suggestions],
                    "count": len(suggestions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cold_hot":
                from ..memory.adaptive_architecture import get_architecture
                aa = get_architecture(self.config)
                result = aa.suggest_cold_hot_separation(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_arch_stats":
                from ..memory.adaptive_architecture import get_architecture
                aa = get_architecture(self.config)
                return json.dumps(aa.get_architecture_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_qa":
                from ..memory.qa_engine import get_qa_engine
                qa = get_qa_engine(self.config)
                question = arguments.get("question", "")
                result = qa.answer(question, drawers)
                return json.dumps({
                    "question": result.question,
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "sources": result.source_memories,
                    "follow_up": result.follow_up_questions,
                    "reasoning": result.reasoning_steps,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_qa_batch":
                from ..memory.qa_engine import get_qa_engine
                qa = get_qa_engine(self.config)
                questions = arguments.get("questions", [])
                results = qa.batch_answer(questions, drawers)
                return json.dumps({
                    "results": [
                        {"question": r.question, "answer": r.answer, "confidence": r.confidence}
                        for r in results
                    ],
                    "count": len(results),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_qa_stats":
                from ..memory.qa_engine import get_qa_engine
                qa = get_qa_engine(self.config)
                return json.dumps(qa.get_qa_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_inject_context":
                from ..memory.context_injection import get_injection_engine
                ie = get_injection_engine(self.config)
                text = arguments.get("text", "")
                budget = arguments.get("token_budget", 500)
                result = ie.inject_context(text, drawers, budget)
                return json.dumps({
                    "injected_text": result.injected_text[:2000],
                    "context_count": result.context_count,
                    "tokens_used": result.tokens_used,
                    "token_budget": result.token_budget,
                    "injections": result.injection_positions,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_update_context":
                from ..memory.context_injection import get_injection_engine
                ie = get_injection_engine(self.config)
                text = arguments.get("text", "")
                result = ie.update_context(text, drawers)
                return json.dumps({
                    "context_count": result.context_count,
                    "tokens_used": result.tokens_used,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_current_context":
                from ..memory.context_injection import get_injection_engine
                ie = get_injection_engine(self.config)
                context = ie.get_current_context()
                return json.dumps({"context": context, "count": len(context)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_injection_stats":
                from ..memory.context_injection import get_injection_engine
                ie = get_injection_engine(self.config)
                return json.dumps(ie.get_injection_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_evaluate_forgetting":
                from ..memory.adaptive_forgetting import get_forgetting
                af = get_forgetting(self.config)
                report = af.evaluate_all(drawers)
                return json.dumps({
                    "total": report.total_evaluated,
                    "keep": report.keep_count,
                    "archive": report.archive_count,
                    "compress": report.compress_count,
                    "forget": report.forget_count,
                    "tokens_freed": report.estimated_tokens_freed,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_forget":
                from ..memory.adaptive_forgetting import get_forgetting
                af = get_forgetting(self.config)
                result = af.auto_forget(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_get_archive":
                from ..memory.adaptive_forgetting import get_forgetting
                af = get_forgetting(self.config)
                limit = arguments.get("limit", 20)
                archive = af.get_archive(limit)
                return json.dumps({"archive": archive, "count": len(archive)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_forget_stats":
                from ..memory.adaptive_forgetting import get_forgetting
                af = get_forgetting(self.config)
                return json.dumps(af.get_forgetting_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_consolidate":
                from ..memory.consolidation_intelligence import get_consolidation_intel
                ci = get_consolidation_intel(self.config)
                report = ci.run_consolidation(drawers)
                return json.dumps({
                    "total_actions": report.total_actions,
                    "merges": report.merges,
                    "promotions": report.promotions,
                    "resolutions": report.resolutions,
                    "compressions": report.compressions,
                    "avg_info_preserved": report.avg_info_preserved,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_merge_candidates":
                from ..memory.consolidation_intelligence import get_consolidation_intel
                ci = get_consolidation_intel(self.config)
                candidates = ci.find_merge_candidates(drawers)
                return json.dumps({
                    "candidates": [
                        {"ids": [d.id for d in group], "count": len(group),
                         "tags": list(set(t for d in group for t in d.tags))[:5]}
                        for group in candidates
                    ],
                    "count": len(candidates),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_resolve_conflicts":
                from ..memory.consolidation_intelligence import get_consolidation_intel
                ci = get_consolidation_intel(self.config)
                actions = ci.find_conflicts(drawers)
                return json.dumps({
                    "conflicts": [
                        {"target": a.target_id, "description": a.description}
                        for a in actions
                    ],
                    "count": len(actions),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_consolidation_stats":
                from ..memory.consolidation_intelligence import get_consolidation_intel
                ci = get_consolidation_intel(self.config)
                return json.dumps(ci.get_consolidation_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend":
                from ..memory.recommendation import get_recommendation
                rec = get_recommendation(self.config)
                context = arguments.get("context", "")
                memory_id = arguments.get("memory_id", "")
                top_k = arguments.get("top_k", 5)
                result = rec.get_full_recommendations(context, memory_id, drawers, top_k)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend_similar":
                from ..memory.recommendation import get_recommendation
                rec = get_recommendation(self.config)
                memory_id = arguments.get("memory_id", "")
                top_k = arguments.get("top_k", 5)
                results = rec.recommend_similar(memory_id, drawers, top_k)
                return json.dumps({
                    "recommendations": [
                        {"id": r.memory_id, "preview": r.content_preview,
                         "score": r.score, "reason": r.reason}
                        for r in results
                    ],
                    "count": len(results),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend_timely":
                from ..memory.recommendation import get_recommendation
                rec = get_recommendation(self.config)
                top_k = arguments.get("top_k", 5)
                results = rec.recommend_timely(drawers, top_k)
                return json.dumps({
                    "recommendations": [
                        {"id": r.memory_id, "preview": r.content_preview,
                         "wing": r.wing, "score": r.score, "reason": r.reason}
                        for r in results
                    ],
                    "count": len(results),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommend_feedback":
                from ..memory.recommendation import get_recommendation
                rec = get_recommendation(self.config)
                memory_id = arguments.get("memory_id", "")
                liked = arguments.get("liked", True)
                rec.record_feedback("default", memory_id, liked)
                return json.dumps({"status": "recorded", "memory_id": memory_id, "liked": liked}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_recommendation_stats":
                from ..memory.recommendation import get_recommendation
                rec = get_recommendation(self.config)
                return json.dumps(rec.get_recommendation_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_assess_quality":
                from ..memory.quality_scorer import get_scorer
                qs = get_scorer(self.config)
                memory_id = arguments.get("memory_id", "")
                target = next((d for d in drawers if d.id == memory_id), None)
                if not target:
                    return json.dumps({"error": "memory not found"}, ensure_ascii=False, indent=2)
                assessment = qs.assess(target, drawers)
                return json.dumps({
                    "id": assessment.memory_id,
                    "score": assessment.overall_score,
                    "grade": assessment.grade,
                    "dimensions": [{"name": d.name, "score": d.score, "detail": d.detail} for d in assessment.dimensions],
                    "issues": assessment.issues,
                    "suggestions": assessment.suggestions,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_batch_assess":
                from ..memory.quality_scorer import get_scorer
                qs = get_scorer(self.config)
                result = qs.batch_assess(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_fix":
                from ..memory.quality_scorer import get_scorer
                qs = get_scorer(self.config)
                result = qs.auto_fix(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_quality_stats":
                from ..memory.quality_scorer import get_scorer
                qs = get_scorer(self.config)
                return json.dumps(qs.get_quality_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_meta_observe":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                ml.observe(arguments["module"], arguments["metric"], arguments["value"])
                return json.dumps({"status": "recorded"}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_meta_recommend":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                task_type = arguments.get("task_type", "search")
                result = ml.recommend_strategy(task_type)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_meta_tune":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                result = ml.auto_tune()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_meta_insights":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                return json.dumps(ml.get_learning_insights(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_meta_stats":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                return json.dumps(ml.get_meta_stats(), ensure_ascii=False, indent=2)

            # ── 认知循环 ──

            elif tool_name == "pangu_cognitive_loop":
                from ..memory.cognitive_loop import get_cognitive_loop
                loop = get_cognitive_loop(self.config)
                result = loop.run_cycle()
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cognitive_stats":
                from ..memory.cognitive_loop import get_cognitive_loop
                loop = get_cognitive_loop(self.config)
                return json.dumps(loop.get_stats(), ensure_ascii=False, indent=2)

            # ── 元认知 ──

            elif tool_name == "pangu_metacognition_monitor":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                return json.dumps(ml.monitor_system_health(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_metacognition_reconfig":
                from ..memory.meta_learning import get_meta_engine
                ml = get_meta_engine(self.config)
                return json.dumps(ml.detect_self_reconfig(), ensure_ascii=False, indent=2)

            # ── 世界模型 ──

            elif tool_name == "pangu_worldmodel_forecast":
                from ..memory.world_model import get_world_model, TOP_SCENARIOS
                wm_model = get_world_model(self.config)
                scenarios = wm_model.forecast()
                return json.dumps({
                    "scenarios_count": len(scenarios),
                    "scenarios": [
                        {
                            "id": s.id,
                            "trigger": s.trigger,
                            "description": s.description,
                            "probability": round(s.probability, 3),
                            "severity": round(s.severity, 3),
                            "causal_depth": len(s.causal_path),
                            "impact": s.estimated_impact,
                            "actions": s.suggested_actions,
                        }
                        for s in scenarios[:TOP_SCENARIOS]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_worldmodel_plan":
                from ..memory.world_model import get_world_model
                wm_model = get_world_model(self.config)
                scenario_id = arguments.get("scenario_id", "")
                scenarios = wm_model.forecast()
                target = next((s for s in scenarios if s.id == scenario_id), None)
                if not target:
                    return json.dumps({"error": f"scenario not found: {scenario_id}"})
                plan = wm_model.generate_plan(target)
                return json.dumps({
                    "scenario_id": plan.scenario_id,
                    "description": plan.description,
                    "actions": plan.suggested_actions,
                    "estimated_effect": plan.estimated_effect,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_worldmodel_match":
                from ..memory.world_model import get_world_model
                wm_model = get_world_model(self.config)
                event_type = arguments.get("event_type", "")
                event_data = arguments.get("event_data", {})
                matched = wm_model.match_event(event_type, event_data)
                if matched:
                    return json.dumps({
                        "matched": True,
                        "scenario_id": matched.id,
                        "trigger": matched.trigger,
                        "probability": round(matched.probability, 3),
                        "actions": matched.suggested_actions,
                    }, ensure_ascii=False, indent=2)
                return json.dumps({"matched": False})

            elif tool_name == "pangu_worldmodel_stats":
                from ..memory.world_model import get_world_model
                wm_model = get_world_model(self.config)
                return json.dumps(wm_model.get_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distill":
                from ..memory.distillation import get_distiller
                d = get_distiller(self.config)
                min_size = arguments.get("min_group_size", 2)
                report = d.distill_all(drawers, min_size)
                return json.dumps({
                    "input": report.input_count,
                    "output": report.output_count,
                    "tokens_saved": report.tokens_saved,
                    "avg_confidence": report.avg_confidence,
                    "distilled": [
                        {"summary": dk.summary[:100], "keywords": dk.keywords,
                         "wing": dk.wing, "confidence": dk.confidence}
                        for dk in report.distilled[:10]
                    ],
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distill_by_wing":
                from ..memory.distillation import get_distiller
                d = get_distiller(self.config)
                result = d.distill_by_wing(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_extract_keywords":
                from ..memory.distillation import get_distiller
                d = get_distiller(self.config)
                text = arguments.get("text", "")
                top_k = arguments.get("top_k", 5)
                keywords = d.extract_keywords(text, top_k)
                return json.dumps({"keywords": keywords}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_distillation_stats":
                from ..memory.distillation import get_distiller
                d = get_distiller(self.config)
                return json.dumps(d.get_distillation_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_rewrite_query":
                from ..memory.query_rewriter import get_rewriter
                rw = get_rewriter(self.config)
                query = arguments.get("query", "")
                strategy = arguments.get("strategy", "auto")
                result = rw.rewrite(query, strategy)
                return json.dumps({
                    "original": result.original,
                    "rewritten": result.rewritten,
                    "strategy": result.strategy,
                    "expanded_terms": result.expanded_terms,
                    "confidence": result.confidence,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_suggest_queries":
                from ..memory.query_rewriter import get_rewriter
                rw = get_rewriter(self.config)
                partial = arguments.get("partial", "")
                top_k = arguments.get("top_k", 5)
                suggestions = rw.suggest_queries(partial, drawers, top_k)
                return json.dumps({"suggestions": suggestions, "count": len(suggestions)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_rewrite_stats":
                from ..memory.query_rewriter import get_rewriter
                rw = get_rewriter(self.config)
                return json.dumps(rw.get_rewrite_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_build_graph":
                from ..memory.graph_builder import get_builder
                gb = get_builder(self.config)
                max_d = arguments.get("max_drawers", 100)
                result = gb.build_from_drawers(drawers, max_d)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_entity":
                from ..memory.graph_builder import get_builder
                gb = get_builder(self.config)
                name = arguments.get("name", "")
                entity = gb.get_entity(name)
                if not entity:
                    return json.dumps({"error": f"Entity '{name}' not found"}, ensure_ascii=False, indent=2)
                rels = gb.get_entity_relations(name)
                return json.dumps({
                    "name": entity.name, "type": entity.entity_type,
                    "confidence": entity.confidence,
                    "relations": rels, "relation_count": len(rels),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_path":
                from ..memory.graph_builder import get_builder
                gb = get_builder(self.config)
                path = gb.find_path(arguments["from_name"], arguments["to_name"])
                return json.dumps({
                    "from": arguments["from_name"], "to": arguments["to_name"],
                    "path": path, "found": len(path) > 0,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_quality":
                from ..memory.graph_builder import get_builder
                gb = get_builder(self.config)
                return json.dumps(gb.assess_quality(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_graph_stats":
                from ..memory.graph_builder import get_builder
                gb = get_builder(self.config)
                return json.dumps(gb.get_graph_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_health_check":
                from ..memory.health_monitor import get_monitor
                hm = get_monitor(self.config)
                return json.dumps(hm.full_check(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_health_trend":
                from ..memory.health_monitor import get_monitor
                hm = get_monitor(self.config)
                return json.dumps(hm.get_trend(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_health_stats":
                from ..memory.health_monitor import get_monitor
                hm = get_monitor(self.config)
                return json.dumps(hm.get_health_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_backup":
                from ..memory.backup_restore import get_backup_engine
                be = get_backup_engine(self.config)
                desc = arguments.get("description", "")
                info = be.backup(drawers, desc)
                return json.dumps({
                    "backup_id": info.backup_id, "memories": info.memory_count,
                    "size": info.size_bytes, "checksum": info.checksum,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_list_backups":
                from ..memory.backup_restore import get_backup_engine
                be = get_backup_engine(self.config)
                return json.dumps({"backups": be.list_backups(), "count": len(be.list_backups())}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_verify_backup":
                from ..memory.backup_restore import get_backup_engine
                be = get_backup_engine(self.config)
                return json.dumps(be.verify_backup(arguments["backup_id"]), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_restore_backup":
                from ..memory.backup_restore import get_backup_engine
                be = get_backup_engine(self.config)
                result = be.restore(arguments["backup_id"])
                result.pop("drawers", None)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_backup_stats":
                from ..memory.backup_restore import get_backup_engine
                be = get_backup_engine(self.config)
                return json.dumps(be.get_backup_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_create":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.create_project(
                    arguments["project_id"], arguments["name"],
                    arguments.get("description", ""),
                ), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_switch":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.switch_project(arguments["project_id"]), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_list":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps({"projects": pm.list_projects()}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_active":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.get_active_project(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_save":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.save_memories(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_load":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                pid = arguments.get("project_id")
                memories = pm.load_memories(pid)
                return json.dumps({"memories": len(memories), "project": pid or pm._active_project}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_search":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                results = pm.search_cross_project(arguments["query"], arguments.get("limit", 10))
                return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_merge":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.merge_project(
                    arguments["source_id"], arguments.get("target_id"),
                ), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_delete":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.delete_project(arguments["project_id"]), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_project_stats":
                from ..memory.project_manager import get_project_manager
                pm = get_project_manager(self.config)
                return json.dumps(pm.get_project_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_audit_log":
                from ..memory.audit_analytics import get_audit
                audit = get_audit(self.config)
                entry = audit.log(arguments["operation"], arguments.get("target_id", ""))
                return json.dumps({"entry_id": entry.entry_id, "timestamp": entry.timestamp}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_audit_query":
                from ..memory.audit_analytics import get_audit
                audit = get_audit(self.config)
                entries = audit.get_entries(
                    arguments.get("operation"), arguments.get("user_id"),
                    arguments.get("limit", 50),
                )
                return json.dumps({"entries": entries, "count": len(entries)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_audit_stats":
                from ..memory.audit_analytics import get_audit
                audit = get_audit(self.config)
                return json.dumps(audit.get_operation_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_access_patterns":
                from ..memory.audit_analytics import get_audit
                audit = get_audit(self.config)
                return json.dumps(audit.get_access_patterns(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_security_summary":
                from ..memory.audit_analytics import get_audit
                audit = get_audit(self.config)
                return json.dumps(audit.get_security_summary(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_record":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                entry = sm.record_change(
                    arguments["memory_id"], arguments["operation"],
                    arguments.get("content", ""),
                )
                return json.dumps({"change_id": entry.change_id, "timestamp": entry.timestamp}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_pending":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                pending = sm.get_pending_changes(arguments.get("since"))
                return json.dumps({"pending": pending, "count": len(pending)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_conflicts":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                remote = arguments.get("remote_changes", [])
                conflicts = sm.detect_conflicts(remote)
                return json.dumps({"conflicts": conflicts, "count": len(conflicts)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_resolve":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                result = sm.resolve_conflict(
                    arguments["change_id"],
                    arguments.get("resolution", "keep_latest"),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_state":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                return json.dumps(sm.get_sync_state(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_sync_stats":
                from ..memory.sync_manager import get_sync
                sm = get_sync(self.config)
                return json.dumps(sm.get_sync_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_emit":
                from ..memory.memory_events import get_event_stream
                es = get_event_stream(self.config)
                event = es.emit(
                    arguments["event_type"],
                    arguments.get("memory_id", ""),
                    arguments.get("data", {}),
                )
                return json.dumps({"event_id": event.event_id, "type": event.event_type, "timestamp": event.timestamp}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_history":
                from ..memory.memory_events import get_event_stream
                es = get_event_stream(self.config)
                history = es.get_history(arguments.get("event_type"), arguments.get("limit", 50))
                return json.dumps({"events": history, "count": len(history)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_stats":
                from ..memory.memory_events import get_event_stream
                es = get_event_stream(self.config)
                return json.dumps(es.get_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_webhook_add":
                from ..memory.memory_events import get_event_stream
                es = get_event_stream(self.config)
                result = es.add_webhook(arguments["url"], arguments["event_types"])
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_event_save":
                from ..memory.memory_events import get_event_stream
                es = get_event_stream(self.config)
                saved = es.save_history()
                return json.dumps({"saved": saved}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_index_build":
                from ..memory.smart_indexing import get_smart_indexing
                si = get_smart_indexing(self.config)
                result = si.build_all_indexes(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_index_search":
                from ..memory.smart_indexing import get_smart_indexing
                si = get_smart_indexing(self.config)
                results = si.search_index(arguments["query"])
                return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_index_recommend":
                from ..memory.smart_indexing import get_smart_indexing
                si = get_smart_indexing(self.config)
                recs = si.recommend_indexes(drawers)
                return json.dumps({
                    "recommendations": [
                        {"type": r.index_type, "key": r.key, "reason": r.reason, "priority": r.priority}
                        for r in recs
                    ],
                    "count": len(recs),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_index_health":
                from ..memory.smart_indexing import get_smart_indexing
                si = get_smart_indexing(self.config)
                return json.dumps(si.get_index_health(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_index_cleanup":
                from ..memory.smart_indexing import get_smart_indexing
                si = get_smart_indexing(self.config)
                cleaned = si.cleanup_indexes()
                return json.dumps({"cleaned": cleaned, "remaining": len(si._indexes)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cache_stats":
                from ..memory.smart_cache import get_cache_manager
                cm = get_cache_manager(self.config)
                return json.dumps(cm.get_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cache_cleanup":
                from ..memory.smart_cache import get_cache_manager
                cm = get_cache_manager(self.config)
                c1 = cm._l1.cleanup_expired()
                c2 = cm._l2.cleanup_expired()
                return json.dumps({"l1_cleaned": c1, "l2_cleaned": c2, "total": c1 + c2}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_cache_invalidate":
                from ..memory.smart_cache import get_cache_manager
                cm = get_cache_manager(self.config)
                pattern = arguments.get("pattern", "")
                c1 = cm._l1.invalidate_pattern(pattern)
                c2 = cm._l2.invalidate_pattern(pattern)
                return json.dumps({"pattern": pattern, "invalidated": c1 + c2}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_portal_write":
                from ..memory.portal import get_portal
                portal = get_portal(self.config)
                result = portal.smart_write(
                    drawers, arguments["content"],
                    arguments.get("wing", "default"),
                    arguments.get("tags", []),
                    arguments.get("importance", 3.0),
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_portal_search":
                from ..memory.portal import get_portal
                portal = get_portal(self.config)
                result = portal.smart_search(drawers, arguments["query"], arguments.get("limit", 5))
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_portal_panorama":
                from ..memory.portal import get_portal
                portal = get_portal(self.config)
                return json.dumps(portal.system_panorama(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_portal_maintain":
                from ..memory.portal import get_portal
                portal = get_portal(self.config)
                return json.dumps(portal.one_click_maintenance(drawers), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_portal_summary":
                from ..memory.portal import get_portal
                portal = get_portal(self.config)
                summary = portal.get_smart_summary(drawers)
                return json.dumps({"summary": summary}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_diff_content":
                from ..memory.memory_diff import get_diff_engine
                de = get_diff_engine(self.config)
                diff = de.diff_content(arguments["content_a"], arguments["content_b"])
                return json.dumps({
                    "similarity": diff.similarity,
                    "added": diff.added, "removed": diff.removed,
                    "modified": diff.modified, "unchanged": diff.unchanged,
                    "summary": de.generate_change_summary(diff),
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_diff_batch":
                from ..memory.memory_diff import get_diff_engine
                de = get_diff_engine(self.config)
                results = de.batch_diff(drawers, arguments.get("reference_id"))
                return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_diff_similarity":
                from ..memory.memory_diff import get_diff_engine
                de = get_diff_engine(self.config)
                matrix = de.similarity_matrix(drawers)
                return json.dumps({"size": matrix["size"], "ids": matrix["ids"]}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_diff_stats":
                from ..memory.memory_diff import get_diff_engine
                de = get_diff_engine(self.config)
                return json.dumps(de.get_diff_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_export_json":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                result = ee.export_json(drawers, arguments.get("filepath"))
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_export_markdown":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                result = ee.export_markdown(drawers, arguments.get("filepath"))
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_export_csv":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                result = ee.export_csv(drawers, arguments.get("filepath"))
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_import_smart":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                result = ee.smart_import(arguments["filepath"])
                result.pop("data", None)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_list_exports":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                return json.dumps({"exports": ee.list_exports()}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_export_stats":
                from ..memory.export_import import get_export_engine
                ee = get_export_engine(self.config)
                return json.dumps(ee.get_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_env_check":
                from ..memory.production import check_environment
                return json.dumps(check_environment(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_startup_validate":
                from ..memory.production import default_startup_checks
                validator = default_startup_checks()
                ok, results = validator.validate()
                return json.dumps({"ok": ok, "checks": results}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_plugin_list":
                from ..plugins import get_plugin_manager
                pm = get_plugin_manager()
                return json.dumps({"plugins": pm.list_plugins(), "count": pm.plugin_count}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_plugin_enable":
                from ..plugins import get_plugin_manager
                pm = get_plugin_manager()
                ok = pm.enable(arguments["name"])
                return json.dumps({"status": "enabled" if ok else "not_found"}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_plugin_disable":
                from ..plugins import get_plugin_manager
                pm = get_plugin_manager()
                ok = pm.disable(arguments["name"])
                return json.dumps({"status": "disabled" if ok else "not_found"}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_plugin_config":
                from ..plugins import get_plugin_manager
                pm = get_plugin_manager()
                config = pm.get_config(arguments["name"])
                return json.dumps({"name": arguments["name"], "config": config}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_plugin_discover":
                from ..plugins import get_plugin_manager
                pm = get_plugin_manager()
                path = arguments.get("path")
                count = pm.discover_plugins(path)
                return json.dumps({"discovered": count}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_session_summary":
                from ..memory.cross_session import CrossSessionIntegrator
                cs = CrossSessionIntegrator(self.config)
                summary = cs.generate_session_summary(drawers)
                return json.dumps(summary, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_session_bridge":
                from ..memory.cross_session import CrossSessionIntegrator
                cs = CrossSessionIntegrator(self.config)
                bridge = cs.build_context_bridge(drawers)
                return json.dumps(bridge, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_session_stats":
                from ..memory.cross_session import CrossSessionIntegrator
                cs = CrossSessionIntegrator(self.config)
                stats = cs.get_session_stats(drawers)
                return json.dumps(stats, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_session_inject":
                from ..memory.cross_session import CrossSessionIntegrator
                cs = CrossSessionIntegrator(self.config)
                result = cs.inject_session_context(arguments.get("query", ""), drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_version_history":
                from ..memory.versioning import get_version_control
                vc = get_version_control(self.config)
                memory_id = arguments.get("memory_id", "")
                history = vc.get_change_history(memory_id)
                return json.dumps({"history": history, "count": len(history)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_version_compare":
                from ..memory.versioning import get_version_control
                vc = get_version_control(self.config)
                memory_id = arguments.get("memory_id", "")
                v1 = arguments.get("v1", 1)
                v2 = arguments.get("v2", 2)
                diff = vc.compare_versions(memory_id, v1, v2)
                return json.dumps(diff, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_visualize_graph":
                from ..memory.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph(self.config)
                entities = kg.list_entities()
                relations = []
                with kg._conn() as conn:
                    rows = conn.execute("SELECT * FROM relations").fetchall()
                    relations = [dict(r) for r in rows]
                from ..memory.visualization import get_visualizer
                viz = get_visualizer(self.config)
                return viz.visualize_graph(entities, relations)

            elif tool_name == "pangu_visualize_network":
                from ..memory.visualization import get_visualizer
                viz = get_visualizer(self.config)
                return viz.visualize_network(drawers)

            elif tool_name == "pangu_visualize_stats":
                from ..memory.visualization import get_visualizer
                viz = get_visualizer(self.config)
                return viz.visualize_stats(drawers)

            elif tool_name == "pangu_importance_score":
                from ..memory.importance_scorer import get_importance_scorer
                scorer = get_importance_scorer(self.config)
                memory_id = arguments.get("memory_id", "")
                context = arguments.get("context", "")
                # 查找记忆
                drawer = next((d for d in drawers if d.id == memory_id), None)
                if not drawer:
                    return json.dumps({"error": f"Memory not found: {memory_id}"})
                result = scorer.score(drawer, context)
                return json.dumps({
                    "score": result.score,
                    "factors": result.factors,
                    "explanation": result.explanation,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_learning_stats":
                from ..memory.adaptive_learning import get_adaptive_learning
                al = get_adaptive_learning(self.config)
                return json.dumps(al.get_learning_stats(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_detect_patterns":
                from ..memory.adaptive_learning import get_adaptive_learning
                al = get_adaptive_learning(self.config)
                patterns = al.detect_patterns()
                return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_popular_queries":
                from ..memory.adaptive_learning import get_adaptive_learning
                al = get_adaptive_learning(self.config)
                limit = arguments.get("limit", 10)
                return json.dumps(al.get_popular_queries(limit), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_frequent_memories":
                from ..memory.adaptive_learning import get_adaptive_learning
                al = get_adaptive_learning(self.config)
                limit = arguments.get("limit", 10)
                return json.dumps(al.get_frequent_memories(limit), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_benchmark":
                from ..observability.performance_monitor import PerformanceMonitor
                monitor = PerformanceMonitor(self.config)
                result = monitor.run_benchmark()
                return json.dumps({
                    "timestamp": result.timestamp,
                    "total_memories": result.total_memories,
                    "vector_count": result.vector_count,
                    "embed_latency_ms": result.embed_latency_ms,
                    "search_latency_ms": result.search_latency_ms,
                    "hybrid_latency_ms": result.hybrid_latency_ms,
                    "token_count": result.token_count,
                    "token_per_memory": result.token_per_memory,
                }, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_auto_collect":
                from ..memory.auto_collector import AutoCollector
                collector = AutoCollector(self.config)
                session_file = arguments.get("session_file", "")
                min_importance = arguments.get("min_importance", 0.3)
                result = collector.collect_from_file(session_file, min_importance=min_importance)
                return json.dumps(result, ensure_ascii=False, indent=2)

            # ── 社交记忆 ──
            elif tool_name == "pangu_comment_add":
                from ..memory.social_memory import SocialMemory
                sm = SocialMemory(self.config)
                memory_id = arguments.get("memory_id", "")
                author_id = arguments.get("author_id", "")
                content = arguments.get("content", "")
                comment = sm.add_comment(memory_id, author_id, content)
                return json.dumps({"id": comment.id, "memory_id": memory_id, "content": content[:50]}, ensure_ascii=False)

            elif tool_name == "pangu_comment_list":
                from ..memory.social_memory import SocialMemory
                sm = SocialMemory(self.config)
                memory_id = arguments.get("memory_id", "")
                comments = sm.get_comments(memory_id, top_level_only=False)
                return json.dumps({"count": len(comments), "comments": [{"id": c.id, "author": c.author_id, "content": c.content[:50], "likes": c.likes} for c in comments[:10]]}, ensure_ascii=False)

            elif tool_name == "pangu_vote":
                from ..memory.social_memory import SocialMemory, VoteType
                sm = SocialMemory(self.config)
                memory_id = arguments.get("memory_id", "")
                user_id = arguments.get("user_id", "")
                vote_type_str = arguments.get("vote_type", "up")
                vote_type = VoteType(vote_type_str) if vote_type_str in ["up", "down", "bookmark"] else VoteType.UP
                vote = sm.vote(memory_id, user_id, vote_type)
                return json.dumps({"memory_id": memory_id, "user_id": user_id, "vote_type": vote_type.value}, ensure_ascii=False)

            elif tool_name == "pangu_vote_stats":
                from ..memory.social_memory import SocialMemory
                sm = SocialMemory(self.config)
                memory_id = arguments.get("memory_id", "")
                stats = sm.get_votes(memory_id)
                return json.dumps(stats, ensure_ascii=False)

            elif tool_name == "pangu_search_stats":
                from ..memory.retrieval import get_search_stats
                return json.dumps(get_search_stats(), ensure_ascii=False, indent=2)

            # ── 梦境巩固 ──

            elif tool_name == "pangu_dream_cycle":
                from ..memory.dream_memory import get_dream_engine
                engine = get_dream_engine(self.config)
                result = engine.run_dream_cycle(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_dream_stats":
                from ..memory.dream_memory import get_dream_engine
                engine = get_dream_engine(self.config)
                return json.dumps(engine.dream_stats(), ensure_ascii=False, indent=2)

            # ── 好奇心探索 ──

            elif tool_name == "pangu_curiosity_explore":
                from ..memory.curiosity import get_curiosity_engine
                engine = get_curiosity_engine(self.config)
                result = engine.explore(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "pangu_curiosity_gaps":
                from ..memory.curiosity import get_curiosity_engine
                engine = get_curiosity_engine(self.config)
                result = engine.find_gaps(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            # ── 人格引擎 ──

            elif tool_name == "pangu_persona_identity":
                from ..memory.persona import get_persona_engine
                engine = get_persona_engine(self.config)
                return json.dumps(engine.get_identity(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_persona_values":
                from ..memory.persona import get_persona_engine
                engine = get_persona_engine(self.config)
                return json.dumps(engine.get_values(), ensure_ascii=False, indent=2)

            elif tool_name == "pangu_persona_health":
                from ..memory.persona import get_persona_engine
                engine = get_persona_engine(self.config)
                result = engine.health_check(drawers)
                return json.dumps(result, ensure_ascii=False, indent=2)

            else:
                return json.dumps({"error": f"未知工具: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    # ── MCP 协议 ──

    async def handle_request(self, request: dict) -> dict:
        """处理 MCP JSON-RPC 请求"""
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "pangu", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.tools},
            }

        elif method == "tools/call":
            tool_name = request.get("params", {}).get("name", "")
            arguments = request.get("params", {}).get("arguments", {})
            # 传递完整request以便handler可以访问params
            result = await self.call_tool(tool_name, arguments, request)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }

        elif method == "notifications/initialized":
            return None  # 无需响应

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"未知方法: {method}"},
            }

    async def run_stdio(self) -> None:
        """通过 stdio 运行 MCP 服务器"""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line.strip())
                response = await self.handle_request(request)

                if response:
                    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError:
                continue
            except EOFError:
                break

        if self._llm is not None:
            await self.llm.close()
