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

            # ── 伏羲移植 ──

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

            # ── 混合检索 (v2.0) ──
            {"name": "pangu_hybrid_search", "description": "FTS+向量+KG三路召回 RRF融合检索", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "limit": {"type": "integer", "description": "返回数量", "default": 10}}, "required": ["query"]}},
            {"name": "pangu_cluster_by_tags", "description": "按标签聚类搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "limit": {"type": "integer", "description": "返回数量", "default": 20}}, "required": ["query"]}},
            {"name": "pangu_cluster_by_time", "description": "按时间聚类搜索结果", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "buckets": {"type": "integer", "description": "时间段数", "default": 3}}, "required": ["query"]}},
            {"name": "pangu_hierarchical_cluster", "description": "层次聚类（基于向量相似度）", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索查询"}, "max_clusters": {"type": "integer", "description": "最大聚类数", "default": 5}}, "required": ["query"]}},

            # ── 多Agent协作记忆 (v2.0) ──
            {"name": "pangu_multi_register", "description": "注册Agent到协作记忆空间", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "Agent ID"}, "priority": {"type": "integer", "description": "优先级", "default": 5}}, "required": ["agent_id"]}},
            {"name": "pangu_multi_write", "description": "写入多Agent共享记忆", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "写入者Agent ID"}, "content": {"type": "string", "description": "记忆内容"}, "scope": {"type": "string", "description": "权限范围: private/shared/public", "default": "public"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"}}, "required": ["agent_id", "content"]}},
            {"name": "pangu_multi_read", "description": "读取Agent可见的记忆", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string", "description": "Agent ID"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "过滤标签"}}, "required": ["agent_id"]}},
            {"name": "pangu_multi_agents", "description": "获取所有已注册Agent", "inputSchema": {"type": "object", "properties": {}}},

            # ── 图推理 (v2.0) ──
            {"name": "pangu_graph_infer", "description": "基于知识图谱推理", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "推理查询"}}, "required": ["query"]}},
            {"name": "pangu_graph_contradictions", "description": "检测图中的矛盾关系", "inputSchema": {"type": "object", "properties": {}}},

            # ── 预测性记忆 (v2.0) ──
            {"name": "pangu_proactive_predict", "description": "基于上下文预测相关记忆", "inputSchema": {"type": "object", "properties": {"context": {"type": "string", "description": "当前上下文"}, "limit": {"type": "integer", "description": "推荐数量", "default": 5}}, "required": ["context"]}},

            # ── 社交记忆 (v2.0) ──
            {"name": "pangu_comment_add", "description": "添加记忆评论", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "author_id": {"type": "string", "description": "作者ID"}, "content": {"type": "string", "description": "评论内容"}}, "required": ["memory_id", "author_id", "content"]}},
            {"name": "pangu_comment_list", "description": "获取记忆评论列表", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}}, "required": ["memory_id"]}},
            {"name": "pangu_vote", "description": "对记忆投票", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}, "user_id": {"type": "string", "description": "用户ID"}, "vote_type": {"type": "string", "description": "投票类型: up/down/bookmark"}}, "required": ["memory_id", "user_id", "vote_type"]}},
            {"name": "pangu_vote_stats", "description": "获取记忆投票统计", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string", "description": "记忆ID"}}, "required": ["memory_id"]}},
            {"name": "pangu_search_stats", "description": "获取搜索命中率统计"},
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
