<!-- 本文件由 scripts/gen_file_index.py 自动生成，**不要手改**。 -->
<!-- 改动生成器后重新运行；tests/test_file_index.py 会校验它与真实目录树一致。 -->

# 盘古文件职责索引

> 全仓库 `*.py` 的逐文件职责。**行数**用于判断体量，**首句 docstring** 是职责摘要。
> 想了解「盘古是什么 / 怎么跑 / 架构与边界」→ 读 [`MAINTAINERS.md`](../MAINTAINERS.md)，本文件只回答「哪个文件干什么」。

共 **350** 个 py 文件 / **106,890** 行。


## `pangu/memory/` — 136 文件 / 43,323 行

记忆系统主体（136 文件）：存取管道、搜索、知识、生命周期、质量治理、推理

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 80 | 盘古记忆模块 |
| `adaptive_architecture.py` | 187 | 盘古自适应记忆架构 — 记忆系统自动重构 |
| `adaptive_forgetting.py` | 307 | 盘古自适应遗忘 — 智能记忆生命周期管理 |
| `adaptive_learning.py` | 217 | 盘古自适应学习系统 — 从用户行为中学习 |
| `adaptive_params.py` | 211 | 盘古自适应参数系统 — 动态调整记忆策略参数 |
| `advanced_reasoning.py` | 764 | 盘古高级推理引擎 — 因果推断、趋势预测与异常检测 |
| `analytics.py` | 433 | 盘古记忆分析看板 — 全面统计与健康监控 |
| `anomaly_detection.py` | 258 | 盘古异常检测 — 发现记忆系统中的异常模式 |
| `attention.py` | 241 | 盘古注意力系统 — 5策略 + 预算分配 + A/B测试 |
| `audio_engine.py` | 252 | 盘古音频记忆引擎 — whisper 转写 + 元数据 + 音频摘要 |
| `audit_analytics.py` | 229 | 盘古审计与分析 — 追踪所有记忆操作 |
| `auto_pilot.py` | 342 | 盘古自动驾驶模式 — 接入后自动完成记忆管理 |
| `autonomous.py` | 1282 | 盘古自主记忆管理引擎 — 自动调度记忆生命周期 |
| `autonomous_learning.py` | 181 | 盘古自主学习 — 自动发现新知识，无需人工干预 |
| `backup_restore.py` | 539 | 盘古记忆备份与恢复 — 防止数据丢失 |
| `batch_import.py` | 242 | 盘古批量多模态导入 — 目录扫描 + 自动检测 + 批量入库 |
| `causal_reasoning.py` | 258 | 盘古因果推理引擎 — 深度因果分析 |
| `cluster.py` | 240 | 盘古搜索结果聚类 — 标签/时间/层次/去重聚类 |
| `clustering.py` | 342 | 盘古记忆聚类引擎 — 自动主题发现与分组 |
| `cognitive_loop.py` | 189 | 盘古认知循环 — 编排记忆系统的思考周期 |
| `collaborative_intelligence.py` | 201 | 盘古多 Agent 协作智能 — Agent 间知识共享和协作推理 |
| `collector.py` | 272 | 盘古通用自动记忆采集器 — 从任意来源采集记忆 |
| `compression.py` | 142 | 盘古 LLM 记忆压缩 — 智能压缩旧记忆 |
| `conflict.py` | 325 | 盘古冲突检测引擎 — 发现矛盾记忆 |
| `consolidation.py` | 296 | 盘古记忆巩固引擎 — 类人记忆特征实现 |
| `consolidation_intelligence.py` | 281 | 盘古记忆巩固智能 — 更智能的记忆合并和巩固策略 |
| `context_injection.py` | 257 | 盘古上下文注入引擎 — 自动为对话注入相关记忆上下文 |
| `context_injector.py` | 155 | 盘古上下文自动注入 — Agent 连接时自动推送相关记忆 |
| `creative_thinking.py` | 217 | 盘古创造性思维 — 基于知识图谱生成新想法 |
| `cross_session.py` | 343 | 盘古跨会话记忆整合 — 自动识别跨会话关联记忆并建立连接 |
| `curiosity.py` | 113 | 盘古好奇心探索引擎 — 知识空白发现与探索建议 |
| `debate.py` | 256 | 盘古多策略辩论引擎 — 并行推理 + 裁判评分选最优 |
| `decay.py` | 234 | 盘古 — 增强衰减引擎（从伏羲 v1.5.6 移植，适配盘古数据模型） |
| `dedup.py` | 329 | 盘古记忆去重引擎 — 检测并合并重复记忆 |
| `deep_emotion.py` | 206 | 盘古深度情绪智能 — 情绪轨迹追踪 / 混合情绪解耦 / 个性化情绪模型 |
| `differential_privacy.py` | 170 | 盘古差分隐私 — 记忆数据隐私保护 |
| `distill_enhanced.py` | 212 | 盘古知识蒸馏增强版 — 自动关联 + 因果链提取 + 知识卡片 |
| `distillation.py` | 252 | 盘古记忆蒸馏 — 从原始记忆中提炼精炼知识 |
| `domain_knowledge.py` | 644 | 盘古领域知识库 — 软件工程、项目管理、团队协作知识管理 |
| `drawer_storage.py` | 486 | 抽屉存储后端 — SQLite 并发安全存储 |
| `dream_memory.py` | 182 | 盘古梦境巩固 — 5步睡眠整理周期 |
| `embedding.py` | 504 | 盘古 — 统一嵌入服务（API → ONNX → hash 三级降级） |
| `emotional_intelligence.py` | 218 | 盘古情感智能 — 理解用户情绪，调整记忆优先级 |
| `encryption.py` | 274 | 盘古 — 记忆数据加密模块 |
| `enhanced_evaluation.py` | 324 | 盘古增强评估 — LLM 驱动矛盾检测 + 轨迹追踪 |
| `error_monitor.py` | 162 | 盘古错误监控 — 集中日志 + 异常追踪 + 健康报告 |
| `evaluation.py` | 131 | 盘古 — 评估缓存独立化（从伏羲 v1.5.6 移植） |
| `event_bus.py` | 180 | 盘古 — 统一事件总线（从伏羲 v1.5.6 移植） |
| `evolution.py` | 265 | 盘古记忆进化模块 |
| `explainable_search.py` | 156 | 盘古可解释搜索 — 为什么这条记忆被返回 |
| `export_import.py` | 404 | 盘古记忆导出导入 — 多格式导出和跨系统导入 |
| `feishu_webhook.py` | 151 | 盘古飞书 Webhook — 记忆事件自动推送到飞书群 |
| `file_watcher.py` | 173 | 盘古文件监控 — 监控目录变更自动提取记忆 |
| `fts_search.py` | 741 | 盘古 FTS5 全文搜索 + RRF 混合搜索引擎 |
| `fusion.py` | 407 | 盘古记忆融合引擎 — 高层抽象理解 |
| `fuxi_bridge.py` | 281 | 盘古-Fuxi 桥接引擎 — 调用 Fuxi 认知能力做深度分析 |
| `git_hook.py` | 179 | 盘古 Git Hook 集成 — 自动记录 git 操作到记忆 |
| `graph_builder.py` | 262 | 盘古记忆图谱构建器 — 自动从记忆中构建和维护知识图谱 |
| `graph_reasoning.py` | 430 | 盘古图推理引擎 — 基于知识图谱的推理能力 |
| `health_monitor.py` | 294 | 盘古记忆健康监控 — 实时监控记忆系统健康状态 |
| `hologram.py` | 372 | 盘古全息记忆编码 — 多维度投影 + 跨维度检索 |
| `hybrid_search.py` | 412 | 盘古混合检索引擎 — 融合 FTS + 向量 + KG 的 RRF 排序 |
| `image_engine.py` | 315 | 盘古图片记忆引擎 — CLIP 嵌入 + 图片分析 + 跨模态搜索 |
| `importance_scorer.py` | 154 | 盘古记忆重要性评分 — 基于多维度特征的智能评分 |
| `ingestion.py` | 935 | 盘古 — 记忆摄入管道（从伏羲 v1.5.6 移植，适配盘古数据模型） |
| `intent_prediction.py` | 174 | 盘古用户意图预测 — 时序意图建模 / 任务链追踪 / 上下文感知建议 |
| `judge.py` | 248 | 盘古 MemoryJudge — LLM 记忆价值判断 |
| `knowledge.py` | 224 | 盘古知识生成模块 |
| `knowledge_graph.py` | 1325 | 盘古时间知识图谱 — 增强版（从伏羲 v1.5.6 移植增强功能） |
| `knowledge_synthesis.py` | 256 | 盘古知识综合 — 从多源记忆中综合提炼新知识 |
| `layers.py` | 1328 | 盘古 4 层记忆栈 — 渐进式记忆加载 + 性能优化 |
| `lifecycle.py` | 680 | 盘古 — 生命周期自动触发器 |
| `lifespan.py` | 125 | 盘古 — 生命周期管理（从伏羲 v1.5.6 移植） |
| `memory_diff.py` | 195 | 盘古记忆差异对比 — 比较记忆版本和内容差异 |
| `memory_events.py` | 262 | 盘古记忆事件流 — 基于 EventBus 的记忆专用事件系统 |
| `memory_validator.py` | 102 | 盘古记忆验证机制 — 验证记忆准确性和时效性 |
| `meta_learning.py` | 306 | 盘古元学习引擎 — 学习如何更好地学习 |
| `migration.py` | 276 | 盘古记忆迁移引擎 — 导出/导入/备份恢复 |
| `multi_agent.py` | 801 | 盘古多Agent协作记忆 — 共享记忆空间 + 权限隔离 + 跨Agent同步 |
| `multimodal.py` | 257 | 盘古多模态记忆支持 — 图片/音频/文件摘要 |
| `multimodal_pipeline.py` | 417 | 盘古多模态输入管道 v3.3 — 图片/文件/URL/音频内容提取并存入记忆 |
| `multimodal_search.py` | 243 | 盘古多模态搜索引擎 — 跨模态统一检索 |
| `multimodal_summary.py` | 203 | 盘古多模态摘要引擎 — 跨模态内容综合摘要 |
| `narrative.py` | 174 | 盘古叙事引擎 — 将碎片化记忆串成连贯叙事 + 主题提取 + 身份连续性 |
| `natural_query.py` | 369 | 盘古 — 自然语言查询接口 |
| `neural_memory.py` | 819 | 盘古类人记忆神经网络 — 海马体-新皮层双系统 |
| `onnx_embedder.py` | 424 | 盘古 — ONNX 本地嵌入器（CPU 加速 3-10x） |
| `patterns.py` | 349 | 盘古模式识别引擎 — 发现记忆中的重复模式和规律 |
| `performance.py` | 830 | 盘古性能优化模块 — HNSW向量索引 + ARC缓存 + 对象池 + 批量操作 |
| `persona.py` | 229 | 盘古人格引擎 — 系统身份、人格特质与健康状态维护 |
| `portal.py` | 207 | 盘古记忆门户 — 一站式记忆操作入口 |
| `predictive_analytics.py` | 183 | 盘古预测分析 — 预测用户需求和记忆趋势 |
| `proactive.py` | 245 | 盘古预测性记忆 — 基于上下文预加载相关记忆 |
| `proactive_reminder.py` | 366 | 盘古主动提醒引擎 — 检测重复问题，推送相关记忆 |
| `production.py` | 316 | 盘古生产加固 — 结构化日志、请求指标、启动校验、优雅关闭 |
| `project_manager.py` | 281 | 盘古多项目支持 — 不同项目独立记忆空间 |
| `qa_engine.py` | 196 | 盘古智能问答引擎 — 基于记忆的智能问答 |
| `quality.py` | 283 | 盘古记忆质量管道 — 自动评估、清洗、优化记忆质量 |
| `quality_scorer.py` | 246 | 盘古记忆质量评分 — 全面评估和改善记忆质量 |
| `query_rewriter.py` | 205 | 盘古搜索查询重写 — 自动改写和优化搜索查询 |
| `realtime.py` | 98 | 盘古实时事件通知 — WebSocket 实时推送记忆变更 |
| `realtime_bridge.py` | 97 | 盘古实时推送桥接 — 事件总线 → WebSocket + 飞书 自动推送 |
| `recommendation.py` | 342 | 盘古记忆推荐系统 — 主动推荐相关记忆 |
| `reconsolidation.py` | 243 | 盘古记忆巩固增强 — 再巩固引擎 + 共鸣匹配 |
| `replay.py` | 399 | 盘古记忆回放引擎 — 按时间线重构事件全景 |
| `reranker.py` | 264 | 盘古语义重排序 — 搜索结果多维重排序 |
| `resonance.py` | 156 | 盘古共鸣匹配 — 发现情感/语义共鸣的记忆对，构建图谱边 |
| `retrievability.py` | 351 | 记忆可检索性体检（2026-09-26）。 |
| `retrieval.py` | 837 | 盘古 — 记忆召回引擎（从伏羲 v1.5.6 移植，适配盘古数据模型） |
| `sanitizer.py` | 150 | 盘古记忆脱敏器 — 记忆内容自动脱敏 |
| `search_analytics.py` | 100 | 盘古搜索模式分析 — 跟踪搜索行为，提供优化建议 |
| `search_cache.py` | 88 | 盘古搜索缓存 — 相同查询 5 分钟内直接返回缓存结果 |
| `search_explainer.py` | 301 | 盘古搜索结果解释 — 为每条搜索结果生成匹配原因说明 |
| `self_evolution.py` | 316 | 盘古自进化引擎 — 系统自我评估与自动优化 |
| `self_improve.py` | 290 | 盘古自我提升工作器 — 服务端透明采集与记忆自我增强 |
| `self_repair.py` | 471 | 盘古自评估+自修复引擎 — 定期检查并自动修复问题 |
| `semantic_compression.py` | 289 | 盘古语义压缩 — AI 驱动的记忆摘要和压缩 |
| `session_bridge.py` | 193 | 盘古 Session Bridge — 跨会话共享上下文 |
| `smart_cache.py` | 237 | 盘古智能缓存管理 — 自适应缓存策略和缓存预热 |
| `smart_indexing.py` | 258 | 盘古智能自动索引 — 根据使用模式自动创建和优化索引 |
| `social_memory.py` | 470 | 盘古记忆社交化模块 — 记忆评论、投票与共享 |
| `streaming_index.py` | 213 | 盘古流式索引 — 增量索引 + WAL 日志 + 断点续传 |
| `sync_manager.py` | 313 | 盘古多端同步 — 支持多设备/多进程间记忆同步 |
| `synonyms.py` | 132 | 盘古同义词扩展 — 搜索时自动扩展同义词，提升召回率 |
| `temporal_reasoning.py` | 251 | 盘古时间推理 — 时间感知记忆，理解事件时间线 |
| `timeline.py` | 430 | 盘古时间线引擎 — 事件链构建与因果推理 |
| `utils.py` | 235 | 盘古记忆系统公共工具模块 |
| `vector_index.py` | 777 | 盘古向量索引加速 — 加速大规模向量相似度搜索 |
| `verification.py` | 196 | 盘古验证循环 — 代码质量门控 |
| `versioning.py` | 151 | 盘古记忆版本控制 — 跟踪记忆如何演变 |
| `video_engine.py` | 334 | 盘古视频记忆引擎 — ffmpeg 提取元数据/帧/音频/摘要 |
| `visualization.py` | 162 | 盘古记忆可视化 — 文本化展示记忆连接关系 |
| `warmup.py` | 163 | 盘古启动预热 — 消除首次查询冷启动延迟 |
| `wikilink.py` | 113 | 盘古 — Wikilink 实体解析器（从伏羲 v1.5.6 移植） |
| `working_memory.py` | 369 | 盘古工作记忆 — Miller 定律 7±2 槽位 + 注意力衰减 + Checkpoint |
| `world_model.py` | 299 | 盘古预测性世界模型 — 基于记忆状态推演未来情景 |

## `tests/` — 103 文件 / 31,846 行

测试

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 1 | 盘古测试模块 |
| `conftest.py` | 283 | pytest session-level fixtures |
| `manual_api_smoke.py` | 264 | 盘古系统接口契约/冒烟测试 — REST API + MCP 工具 + CLI |
| `manual_benchmark.py` | 133 | 盘古 Benchmark — 性能基准测试 + 竞品对比 |
| `manual_e2e/__init__.py` | 1 | (无 docstring) |
| `manual_e2e/run_e2e.py` | 1071 | 盘古记忆系统全量 E2E 测试 — 覆盖全部 423 个 MCP 工具的真实性验证 |
| `manual_e2e/test_comprehensive.py` | 1538 | 盘古记忆系统全量 E2E 测试 — 覆盖全部 423 个 MCP 工具的真实性验证 |
| `manual_full.py` | 149 | 盘古记忆系统全面测试 |
| `manual_perf.py` | 255 | 盘古性能基准 — ONNX 嵌入 / SQLite 缓存 / 记忆读写（修正 API 签名） |
| `manual_security.py` | 213 | 盘古安全测试 — 危险 API、SQL 注入、secret 扫描、越权 |
| `run_full_regression.py` | 224 | 盘古综合回归与报告生成器 |
| `test_abac.py` | 391 | 盘古 ABAC 多租户测试 |
| `test_auth.py` | 387 | 盘古 — 双鉴权 (API Key + JWT) 单元测试 |
| `test_auto_collect_handler.py` | 121 | pangu_auto_collect handler 回归测试 |
| `test_bench.py` | 406 | 盘古性能基准测试 — 搜索/检索/索引速度、并发压测、内存分析 |
| `test_benchmark_v2.py` | 85 | 盘古 v2.0 综合性能基准测试 |
| `test_benchmark_v3.py` | 207 | 盘古性能基准测试 — 延迟/吞吐量/并发/内存 |
| `test_boundary_cases.py` | 983 | 盘古记忆系统边界与极端情况测试 |
| `test_cache_warmup.py` | 357 | 盘古 — 缓存预热 功能测试 |
| `test_ci_covers_everything.py` | 126 | CI 的测试范围必须是「整个目录」，不能是手写文件清单。 |
| `test_cli_serve.py` | 120 | `pangu serve` 的命令行语义测试 |
| `test_core.py` | 1658 | 盘古核心功能测试 |
| `test_e2e_rbac_abac.py` | 188 | 盘古 E2E 联调测试 — RBAC + ABAC + 记忆业务路由 |
| `test_embedding_cache_persistence.py` | 282 | 盘古 — 嵌入缓存跨进程持久化测试（v0.2.0） |
| `test_embedding_degradation.py` | 325 | 盘古 — 嵌入后端降级可见性测试（v0.1.3 P0） |
| `test_embedding_onnx_cache.py` | 149 | ONNX 批量嵌入必须走缓存 —— 修「每次搜索重算整个语料」。 |
| `test_embedding_remote_api.py` | 196 | 盘古 — 远程 Embedding API 分支可用性测试（v0.1.3 P0） |
| `test_encryption.py` | 57 | 盘古 encryption.py 测试 — E2E 加密模块 |
| `test_fuxi_port.py` | 212 | 盘古伏羲移植模块测试 |
| `test_gap1_exposure.py` | 68 | 缺口 1 回归测试：核心链路工具必须出现在 tools/list。 |
| `test_gap2_write_channel.py` | 69 | 缺口 2 回归测试：handle_add_memory 接入 remember() 管道。 |
| `test_gap3_admission_gate.py` | 206 | P1-3 回归测试：四问准入门强化 + 毕业区。 |
| `test_graph_dedupe_by_id.py` | 154 | 图谱接口按 id 合并的回归测试（2026-09-26）。 |
| `test_hotfix_llm_key.py` | 51 | 热修：resolveLlmApiKey + testConnection 逻辑分支测试 |
| `test_ingestion.py` | 79 | 盘古 ingestion.py 测试 — 核心写入路径 |
| `test_integration.py` | 659 | 盘古 API 服务器 + MCP 集成测试 |
| `test_llm_model_switch.py` | 257 | 盘古 — LLM 候选模型发现与切换测试 |
| `test_llm_optimizations.py` | 734 | 盘古 — LLM 优化功能测试 |
| `test_llm_providers.py` | 378 | 盘古 — LLM 后端集成测试 |
| `test_maintainers_doc.py` | 409 | 维护说明书（MAINTAINERS.md）与代码的一致性检查。 |
| `test_mcp_auth_exposure.py` | 35 | 「监听暴露 + MCP 免鉴权」告警的单测。 |
| `test_mcp_tenant_fallback.py` | 107 | MCP 写入的 tenant_id 归属回退（2026-09-26）。 |
| `test_mcp_warmup.py` | 87 | 盘古 — MCP 服务器启动预热测试 |
| `test_memory_system.py` | 962 | 盘古记忆系统综合测试 — 覆盖存储/检索/遗忘曲线/巩固/自然语言查询/多Agent协作 |
| `test_onnx_embedder.py` | 417 | 盘古 — ONNX 嵌入器测试 |
| `test_optimization_2026_08_27.py` | 885 | PANGU 优化改进项 2026-08-27 实现验证（R1-R4 盘古侧） |
| `test_p0_0_authoritative_path.py` | 1278 | P0-0 回归测试：统一权威记忆路径 + 空写保护。 |
| `test_p0_1_supersede.py` | 722 | P0-1 supersede 全链路测试 |
| `test_p0_2_search_quality.py` | 191 | P0-2 回归测试：检索质量——噪声不能压过信号。 |
| `test_p1_1_install_experience.py` | 109 | P1-1 回归测试：安装体验（upgrade / uninstall / --server）。 |
| `test_p1_2_docs_freshness.py` | 173 | P1-2 回归测试：文档新鲜度——版本号/工具名/镜像 tag 必须与代码一致。 |
| `test_p1_3_access_feedback.py` | 108 | 访问反馈环（2026-09-19）：搜索命中 → record_access → 衰减/遗忘读它。 |
| `test_p1_3_backup_restore.py` | 267 | 备份/恢复真落盘回归（2026-09-19）。 |
| `test_p1_3_classification_axis.py` | 283 | P1-3 阶段 4：classification（密级）轴 —— 与租户**正交**的第二条可读判据。 |
| `test_p1_3_decay_idempotent.py` | 101 | 衰减幂等性（2026-09-19 修复回归）。 |
| `test_p1_3_encryption.py` | 110 | 加密边界回归（2026-09-19）。 |
| `test_p1_3_honest_returns.py` | 65 | 落盘失败时的诚实返回（2026-09-19 修 BUG）。 |
| `test_p1_3_kg_tenant_scope.py` | 334 | P1-3 阶段 3：知识图谱（KG）多租户回归测试。 |
| `test_p1_3_kg_wiki_classification.py` | 137 | KG / wiki 的**密级轴** —— 第二条正交判据，与记忆层 metadata_readable 同规则。 |
| `test_p1_3_leak_sweep.py` | 206 | 跨租户泄漏扫描（in-process 版）—— CI 里的租户隔离闸门。 |
| `test_p1_3_migration.py` | 109 | 导入/导出链路回归（2026-09-19）。 |
| `test_p1_3_palace_structure.py` | 94 | P1-3 阶段 3：Palace 骨架（翼/房间/隧道）的租户归属与删除授权。 |
| `test_p1_3_phase2_scope.py` | 79 | P1-3 阶段 2 退回修复测试：过滤轴从 Drawer.room 改为 metadata.tenant_id |
| `test_p1_3_recall_decay.py` | 78 | recall 排序并入衰减分（2026-09-19）。 |
| `test_p1_3_rest_tenant_hardening.py` | 150 | P1-3 阶段 3：REST 侧租户收口（租户由凭据决定，不能由调用方声明）。 |
| `test_p1_3_scope_guard.py` | 113 | scope 强制 + config 保护名单（2026-09-19 安全收口）。 |
| `test_p1_3_search_quality.py` | 79 | 搜索结果质量自检（2026-09-19）。 |
| `test_p1_3_set_source.py` | 149 | pangu_set_source：补来源指针 —— 解「缺来源」的准入死结。 |
| `test_p1_3_tenant_scope.py` | 177 | P1-3 租户作用域（MemoryStack 读路径闸门）回归测试。 |
| `test_p1_3_wiki_tenant_scope.py` | 252 | P1-3 阶段 3：Wiki 租户化回归测试。 |
| `test_p1_3_write_lock.py` | 228 | 写路径互斥（2026-09-19）：MemoryStack 的"读-改-写"并发丢更新回归。 |
| `test_p1_3_ws_backpressure.py` | 144 | 事件推送背压回归（2026-09-19）。 |
| `test_p1_4_batch1_data_integrity.py` | 305 | 第 1 批修复的回归测试（2026-09-20）。 |
| `test_p1_4_batch2_gate.py` | 199 | 第 2 批（门 + 功能空转）的回归测试（2026-09-20）。 |
| `test_p1_4_batch2_noop_fixes.py` | 206 | 第 2 批「功能空转」修复的回归测试（2026-09-20）。 |
| `test_p1_4_hygiene_fixes.py` | 211 | 卫生类修复的回归测试（2026-09-20）。 |
| `test_p2_1_advanced_reasoning.py` | 144 | P2-1 Step 2 回归测试：advanced_reasoning 接入。 |
| `test_p2_1_knowledge_integration.py` | 205 | P2-1 Step 1 回归测试：domain_knowledge 接入。 |
| `test_p2_1_performance_batch.py` | 105 | P2-1 Step 3 回归测试：performance.BatchProcessor 接入 autonomous 向量索引任务。 |
| `test_perf_regression.py` | 165 | 盘古性能回归检测 — 自动对比基准，检测性能退化 |
| `test_performance_optimizations.py` | 420 | 测试性能优化效果 |
| `test_persistent_cache.py` | 476 | 盘古 — 持久化缓存 + Prometheus 指标 测试 |
| `test_phase1_keys.py` | 248 | 阶段 1 测试：钥匙管理 + 身份解析 + 管理端点鉴权 + require_auth |
| `test_python_version_matrix.py` | 128 | CI 的 Python 矩阵必须与 `pyproject.toml` 的声明一致，且覆盖开发实际使用的版本。 |
| `test_rbac.py` | 246 | 盘古 RBAC 角色权限测试 |
| `test_real_llm.py` | 528 | 盘古 — 真实 LLM 集成测试 |
| `test_rest_v2_contract.py` | 234 | REST v2 契约回归（2026-09-22 mimo-desktop-agent 接入实测报告）。 |
| `test_retrievability_audit.py` | 201 | 可检索性体检（memory/retrievability.py）的回归测试。 |
| `test_retrievability_llm.py` | 148 | 可检索性体检的 LLM 阶段（2026-09-26）。 |
| `test_search_own_first.py` | 321 | 搜索「本平台优先」的两个模式（2026-09-26）。 |
| `test_top_level_intelligence.py` | 258 | 盘古顶级智能验证 — 端到端集成测试 |
| `test_v2_features.py` | 231 | 盘古 v2.0 新功能测试 — neural_memory / multi_agent / social_memory |
| `test_v3_modules_a.py` | 334 | 盘古 V3.0 模块测试 — 7 个记忆引擎 |
| `test_v3_modules_b.py` | 245 | Pangu v3.0 模块测试 — 第二批 7 个记忆子系统 |
| `test_v3_modules_c.py` | 401 | 盘古 V3.0 模块测试 C — 7 个记忆引擎 |
| `test_v3_modules_d.py` | 596 | Pangu v3.0 模块测试 — 第四批 7 个记忆子系统 |
| `test_v3_modules_e.py` | 354 | Pangu v3.0 模块测试 — 第五批 3 个记忆子系统 |
| `test_v3_modules_f.py` | 1082 | Pangu v3.0 模块测试 — 第六批 11 个记忆子系统 |
| `test_v3_modules_g.py` | 820 | 盘古 V3.0 模块测试 — 11 个记忆引擎 |
| `test_v3_modules_h.py` | 812 | V3 模块测试 H — onnx_embedder / proactive / reconsolidation / sanitizer / |
| `test_vacuum.py` | 248 | 盘古 — 持久化缓存 VACUUM 后台任务测试 |
| `test_vector_degradation_visible.py` | 167 | 向量路径的降级必须**看得见**。 |
| `test_warmup_audit.py` | 133 | 盘古 — 缓存预热审计日志测试 |

## `pangu/server/` — 26 文件 / 11,456 行

服务器层：MCP 服务器、Web 服务器、WebSocket、工具 handler 与暴露面

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 7 | 盘古服务器模块 |
| `exposure.py` | 235 | 暴露面过滤器 — MCP/REST 双通道单一拦截点 |
| `handlers/__init__.py` | 325 | 盘古 MCP Handler 路由 |
| `handlers/advanced.py` | 2121 | 盘古 MCP Handler — advanced (121 tools) |
| `handlers/analytics.py` | 751 | 盘古 MCP Handler — analytics (37 tools) |
| `handlers/batch.py` | 57 | 盘古 MCP Handler — batch (3 tools) |
| `handlers/consolidation.py` | 561 | 盘古 MCP Handler — consolidation (32 tools) |
| `handlers/embed.py` | 143 | 盘古 MCP Handler — embed (6 tools) |
| `handlers/io_tools.py` | 458 | 盘古 MCP Handler — io_tools (30 tools) |
| `handlers/knowledge.py` | 178 | 盘古 MCP Handler — knowledge (8 tools, P2-1 Step 1) |
| `handlers/knowledge_graph.py` | 116 | 盘古 MCP Handler — knowledge_graph (7 tools) |
| `handlers/llm_tools.py` | 288 | 盘古 MCP Handler — llm_tools (19 tools) |
| `handlers/memory_ops.py` | 784 | 盘古 MCP Handler — memory_ops (4 tools) |
| `handlers/multimodal.py` | 324 | 盘古 MCP Handler — multimodal (17 tools) |
| `handlers/palace.py` | 88 | 盘古 MCP Handler — palace (4 tools) |
| `handlers/quality.py` | 407 | 盘古 MCP Handler — quality (20 tools) |
| `handlers/search.py` | 919 | 盘古 MCP Handler — search (33 tools) |
| `handlers/session.py` | 425 | 盘古 MCP Handler — session (28 tools) |
| `handlers/supersede.py` | 170 | 盘古 MCP Handler — supersede (1 tool) |
| `handlers/system.py` | 903 | 盘古 MCP Handler — system (44 tools) |
| `handlers/timeline.py` | 400 | 盘古 MCP Handler — timeline (16 tools) |
| `handlers/wiki.py` | 66 | 盘古 MCP Handler — wiki (4 tools) |
| `mcp_server.py` | 496 | 盘古 MCP 服务器 — 为 AI Agent 提供记忆工具接口 |
| `module_registry.py` | 357 | 模块注册表 — 盘古工具暴露面的单一事实源 |
| `web_server.py` | 543 | 盘古 Web 服务器 — 提供记忆管理 Web UI 和 REST API |
| `websocket_server.py` | 334 | 盘古 WebSocket 服务器 — 实时记忆流推送 |

## `pangu/api/` — 16 文件 / 5,936 行

FastAPI 层：路由、鉴权（ABAC/RBAC/JWT）、平台 Token、MCP-HTTP 传输

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 5 | 盘古 API 模块 |
| `abac.py` | 570 | 盘古 — ABAC 属性访问控制 |
| `admin_auth.py` | 58 | 盘古 admin 凭据校验（唯一实现）。 |
| `auth.py` | 560 | 盘古 — 双鉴权模块 (API Key + JWT) |
| `mcp_http.py` | 285 | 盘古 MCP HTTP 传输层 — 支持 SSE + StreamableHTTP 远程访问 |
| `platform_tokens.py` | 235 | 盘古平台接入 Token 管理 |
| `rbac.py` | 306 | 盘古 — RBAC 角色权限模型 |
| `routes_dashboard.py` | 164 | 盘古 REST API 路由 — /api/v2/dashboard（仪表盘） |
| `routes_keys.py` | 285 | 盘古 REST API 路由 — /api/v2/admin/keys（钥匙管理） |
| `routes_memory.py` | 943 | 盘古 REST API 路由 — /api/v2/memories（伏羲移植） |
| `routes_platforms.py` | 141 | 盘古 REST API 路由 — /api/v2/platforms（平台接入审核） |
| `routes_tags.py` | 303 | 盘古标签管理 API — CRUD + 统计 + 合并 + 推荐 |
| `routes_tasks.py` | 249 | 盘古任务状态同步 API — 跨 Agent 任务追踪（SQLite 持久化） |
| `routes_tools.py` | 105 | 盘古 REST API 路由 — /api/v2/tools（通用 MCP 工具网关） |
| `safe_eval.py` | 218 | Safe expression evaluator for ABAC conditions. |
| `server.py` | 1509 | 盘古 FastAPI 服务器工厂（伏羲移植） |

## `scripts/` — 21 文件 / 3,349 行

运维脚本

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `ab_own_first.py` | 164 | 搜索「本平台优先」改造前后的 A/B 对比（只读，不改任何数据）。 |
| `bench_large_scale.py` | 160 | 盘古大规模数据测试脚本 — 生成1000条测试记忆并测试搜索性能 |
| `consolidate.py` | 100 | 盘古记忆巩固定时任务 |
| `dump_llm_cache.py` | 203 | 盘古 — LLM 缓存调试脚本 |
| `e2e_warmup.py` | 260 | 盘古 — LLM 缓存预热 E2E 验证 |
| `embed_all.py` | 98 | 为所有抽屉生成 ONNX 嵌入并重建向量索引 |
| `eval_report.py` | 107 | 盘古记忆评估报告 |
| `fast_collect.py` | 106 | 盘古自动采集脚本 — 简化版（跳过嵌入） |
| `gen_file_index.py` | 185 | 生成「文件职责索引」→ docs/FILE_INDEX.md。 |
| `generate_knowledge.py` | 261 | 盘古知识生成脚本 — 从记忆中提取知识 |
| `mcp_stdio_bridge.py` | 131 | 盘古 MCP 的 stdio ↔ HTTP 桥。 |
| `merge_kg_duplicates.py` | 134 | 合并 entities_all / relations_all 里同 id 多属主的重复行（2026-09-26）。 |
| `migrate_add_source.py` | 114 | 盘古数据迁移脚本 — 给现有记忆添加 source 字段 |
| `migrate_rooms.py` | 82 | 存量迁移：把缺 tenant_id 的存量记忆标 'dsh' |
| `osv_audit.py` | 62 | OSV 漏洞审计脚本 — 查询 Google OSV 数据库 |
| `p2_1_module_audit.py` | 187 | P2-1 模块处置清单：从真实入口出发做可达性分析，把模块分三类。 |
| `probe_mcp_tools.py` | 122 | MCP 工具面健康探测：只调只读工具，按 schema 必填字段构造合法参数。 |
| `split_mcp_server.py` | 371 | 自动拆分 mcp_server.py — 修复版 |
| `tenant_leak_sweep.py` | 231 | 跨租户泄漏扫描：以一个租户的身份遍历所有只读工具，检查是否能看到另一个租户的数据。 |
| `test_real_llm.py` | 202 | 盘古 — 真实 LLM 快速验证脚本 |
| `trigger_crystallize.py` | 69 | 一次性触发知识结晶（绕过时间窗口，跳过 LLM 用规则式） |

## `pangu/` — 6 文件 / 3,302 行

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 50 | 盘古 — 专业记忆系统（智能体的"大脑"组件） |
| `autonomous.py` | 185 | 盘古自主判断引擎 — 根据任务类型自动决定调用哪些能力（伏羲移植） |
| `cli.py` | 2616 | 盘古 CLI — 命令行入口 |
| `client.py` | 163 | 盘古记忆客户端 — 外部系统交互封装（伏羲移植） |
| `keys.py` | 145 | 盘古钥匙管理器 |
| `task_tracker.py` | 143 | 任务进度追踪器 — 在工具执行后自动保存任务状态（伏羲移植） |

## `pangu/core/` — 6 文件 / 2,989 行

核心设施：配置、LLM 接入、加密、哈希、缓存、宫殿数据模型

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 7 | 盘古核心模块 |
| `cache.py` | 452 | 盘古 — 持久化 LLM 响应缓存 |
| `config.py` | 630 | 盘古核心配置模块 — 基于 pydantic-settings（伏羲移植） |
| `hashing.py` | 39 | 盘古 — 统一哈希工具 |
| `llm.py` | 1553 | 盘古 LMM 集成层 — 大语言模型驱动的智能记忆处理 |
| `palace.py` | 308 | 盘古宫殿核心 — Wings/Rooms/Drawers/Halls/Tunnels 管理 |

## `experimental/` — 16 文件 / 1,172 行

实验性功能

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 95 | 实验模块目录 — 承载"类人大脑"愿景的研究性功能 |
| `advanced.py` | 98 | 实验工具实现 — 自 pangu/server/handlers/advanced.py 迁入 |
| `auto_collector.py` | 515 | 盘古 — OpenClaw 会话自动采集器 |
| `autonomous.py` | 12 | 自主循环实验工具 — autonomous 组 |
| `autopilot.py` | 11 | 自动驾驶实验工具 — autopilot 组 |
| `causal.py` | 9 | 因果发现实验工具 — causal 组 |
| `cognitive.py` | 10 | 认知循环实验工具 — cognitive 组 |
| `dream.py` | 10 | 梦境实验工具 — dream 组 |
| `evolution.py` | 10 | 进化实验工具 — evolution 组 |
| `meta.py` | 15 | 元认知实验工具 — meta 组 |
| `neural.py` | 13 | 神经网络实验工具 — neural 组 |
| `probes/auto_extract.py` | 154 | 盘古记忆自动提取脚本 |
| `probes/phase3_enhance.py` | 109 | Phase 3: 智能增强 — 去重 + KG 丰富化 + 管道验证 |
| `probes/test_extract.py` | 88 | 测试自动提取功能 |
| `self_aware.py` | 11 | 自我感知实验工具 — self_aware 组 |
| `worldmodel.py` | 12 | 世界模型实验工具 — worldmodel 组 |

## `pangu/observability/` — 5 文件 / 836 行

可观测性：健康检查、Prometheus 指标、OpenTelemetry 追踪

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 12 | 盘古可观测性模块 |
| `health.py` | 223 | 盘古健康检查系统（伏羲移植） |
| `metrics.py` | 367 | 盘古 Prometheus 指标导出（伏羲移植） |
| `performance_monitor.py` | 119 | 盘古性能基准监控 — 持续监控性能变化 |
| `tracing.py` | 115 | 盘古 — OpenTelemetry 分布式追踪模块 |

## `pangu/plugins/` — 2 文件 / 782 行

插件系统

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 327 | 盘古插件系统 — 可扩展的记忆处理器 |
| `plugin_manager.py` | 455 | 盘古插件管理器 — 插件化架构核心 |

## `pangu/search/` — 3 文件 / 698 行

搜索层：嵌入引擎 + 混合检索引擎

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 5 | 盘古搜索模块 |
| `embedder.py` | 479 | 盘古向量嵌入引擎 — 真正的语义搜索 |
| `engine.py` | 214 | 盘古搜索模块 — 多模式记忆搜索 |

## `pangu/wiki/` — 2 文件 / 376 行

Wiki 知识页引擎

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 5 | 盘古 Wiki 模块 |
| `engine.py` | 371 | 盘古 Wiki 引擎 — 知识页面的创建、链接和维护 |

## `pangu/store/` — 2 文件 / 371 行

存储 schema 与增量迁移

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 10 | 盘古存储模块 |
| `migrations.py` | 361 | 盘古数据库Schema — 增量迁移系统（伏羲移植） |

## `pangu/mining/` — 2 文件 / 363 行

记忆挖掘：从外部来源提取记忆

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 5 | 盘古挖掘模块 |
| `miners.py` | 358 | 盘古挖掘模块 — 从各种来源提取记忆 |

## `plugins/` — 3 文件 / 90 行

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `examples/auto_tagger.py` | 36 | 自动标签插件 — 根据内容自动添加标签 |
| `examples/dedup_guard.py` | 29 | 去重守卫插件 — 防止重复记忆写入 |
| `examples/notification.py` | 25 | 通知插件 — 记忆变更时发送通知 |

## `pangu/ui/` — 1 文件 / 1 行

| 文件 | 行 | 职责（首句 docstring） |
| --- | ---: | --- |
| `__init__.py` | 1 | 盘古 UI 模块 |

---

## 怎么读这个索引

- **改动前**：先在 `MAINTAINERS.md` 找相关子系统，再到这里定位文件。
- **改动后**：`tests/test_file_index.py` 会校验索引与真实目录树一致；新增文件忘了重新生成
  就会红。
- docstring 缺失的文件会标 `(无 docstring)` —— 那本身是个信号，说明该文件缺文档。
