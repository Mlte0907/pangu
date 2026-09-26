# 模块健康度分级 — 核心 / 活跃 / 边缘

> **版本**：v0.4.1
> **日期**：2026-09-27
> **依据**：基于全部 230 个模块的逐个阅读，按「是否在核心链路上」分类。
> **维护**：新增模块时必须归类；每季度复审一次。

---

## 分级定义

| 级别 | 定义 | 坏了的影响 |
| --- | --- | --- |
| **核心** | 搜索/存储/API 主链路上的模块 | 系统不能工作 |
| **活跃** | 自主任务/辅助功能链路上的模块 | 功能降级但系统还能用 |
| **边缘** | 未接线/实验性/可选功能 | 无感知 |

---

## 核心模块（坏了系统不能工作）

### Core 层（`pangu/core/`）

| 模块 | 职责 |
| --- | --- |
| `config.py` | 全局配置（Pydantic Settings） |
| `llm.py` | LLM 引擎（多提供商、缓存、重试、模型发现） |
| `palace.py` | Drawer/WikiPage 数据结构 |
| `cache.py` | 持久化 LLM 响应缓存（SQLite） |
| `hashing.py` | 统一 blake2b 哈希 |

### API 层（`pangu/api/`）

| 模块 | 职责 |
| --- | --- |
| `server.py` | FastAPI 服务器工厂 |
| `routes_memory.py` | `/api/v2/memories` REST 路由 |
| `routes_dashboard.py` | `/api/v2/dashboard` REST 路由 |
| `routes_keys.py` | `/api/v2/admin/*` REST 路由 |
| `routes_platforms.py` | `/api/v2/platforms` REST 路由 |
| `routes_tags.py` | 标签管理 REST 路由 |
| `routes_tasks.py` | 任务状态同步 REST 路由 |
| `routes_tools.py` | 通用 MCP 工具网关 REST 路由 |
| `auth.py` | 双鉴权（API Key + JWT） |
| `abac.py` | ABAC 属性访问控制 |
| `rbac.py` | RBAC 角色权限模型 |
| `admin_auth.py` | admin 凭据校验 |
| `platform_tokens.py` | 平台接入 Token 管理 |
| `mcp_http.py` | MCP HTTP 传输层 |
| `safe_eval.py` | 安全表达式求值 |

### Server 层（`pangu/server/`）

| 模块 | 职责 |
| --- | --- |
| `mcp_server.py` | MCP 协议服务器 |
| `web_server.py` | Web 服务器（REST API + UI） |
| `websocket_server.py` | WebSocket 服务器 |
| `module_registry.py` | 工具暴露面注册表 |
| `exposure.py` | 工具暴露面过滤器 |
| `handlers/memory_ops.py` | 记忆操作 handler |
| `handlers/search.py` | 搜索 handler |
| `handlers/system.py` | 系统 handler |
| `handlers/advanced.py` | 高级功能 handler |
| `handlers/analytics.py` | 分析 handler |
| `handlers/batch.py` | 批量操作 handler |
| `handlers/consolidation.py` | 巩固 handler |
| `handlers/embed.py` | 嵌入 handler |
| `handlers/io_tools.py` | IO 工具 handler |
| `handlers/knowledge.py` | 知识库 handler |
| `handlers/knowledge_graph.py` | 知识图谱 handler |
| `handlers/llm_tools.py` | LLM 工具 handler |
| `handlers/multimodal.py` | 多模态 handler |
| `handlers/palace.py` | 宫殿 handler |
| `handlers/quality.py` | 质量 handler |
| `handlers/session.py` | 会话 handler |
| `handlers/supersede.py` | 替代链 handler |
| `handlers/timeline.py` | 时间线 handler |
| `handlers/wiki.py` | Wiki handler |

### Search 层（`pangu/search/`）

| 模块 | 职责 |
| --- | --- |
| `engine.py` | SemanticSearch / LexicalSearch / HybridSearch |
| `embedder.py` | ONNX/sentence-transformers 向量嵌入引擎 |

### Memory 核心（`pangu/memory/`）

| 模块 | 职责 |
| --- | --- |
| `layers.py` | 4 层记忆栈（L0-L3） |
| `fts_search.py` | FTS5 + 向量混合搜索引擎 |
| `hybrid_search.py` | FTS + Vector + KG 三路 RRF 融合 |
| `embedding.py` | 统一嵌入服务（ONNX/API/hash 三级降级） |
| `onnx_embedder.py` | ONNX 本地嵌入器 |
| `vector_index.py` | 向量索引加速（numpy/FAISS/hnswlib） |
| `reranker.py` | 语义重排序 |
| `search_cache.py` | 搜索结果缓存 |
| `search_explainer.py` | 搜索结果解释 |
| `ingestion.py` | 记忆摄入管道 |
| `drawer_storage.py` | 抽屉存储后端 |
| `encryption.py` | 记忆数据加密 |
| `knowledge.py` | 知识引擎 |
| `knowledge_graph.py` | 时间知识图谱 |
| `autonomous.py` | 自主记忆管理引擎 |
| `decay.py` | 增强衰减引擎 |
| `lifecycle.py` | 生命周期自动触发器 |
| `utils.py` | 公共工具（cosine_similarity / LRUCache） |
| `wikilink.py` | Wikilink 实体解析器 |
| `sanitizer.py` | 记忆脱敏器 |

### Store 层（`pangu/store/`）

| 模块 | 职责 |
| --- | --- |
| `migrations.py` | 数据库 Schema 增量迁移 |

### 其他核心

| 模块 | 职责 |
| --- | --- |
| `pangu/wiki/engine.py` | Wiki 知识引擎 |
| `pangu/cli.py` | CLI 命令行入口 |
| `pangu/client.py` | 外部系统交互封装 |
| `pangu/keys.py` | 钥匙管理器 |
| `pangu/plugins/plugin_manager.py` | 插件管理器 |
| `pangu/observability/health.py` | 健康检查系统 |

---

## 活跃模块（功能降级但系统还能用）

### 自主任务相关

| 模块 | 职责 |
| --- | --- |
| `pangu/memory/compression.py` | LLM 记忆压缩 |
| `pangu/memory/judge.py` | LLM 记忆价值判断 |
| `pangu/memory/enhanced_evaluation.py` | LLM 驱动矛盾检测 |
| `pangu/memory/distill_enhanced.py` | 知识蒸馏增强版 |
| `pangu/memory/retrievability.py` | 可检索性体检 |
| `pangu/memory/fusion.py` | 记忆融合引擎 |
| `pangu/memory/dream_memory.py` | 梦境巩固 |
| `pangu/memory/curiosity.py` | 好奇心探索 |
| `pangu/memory/adaptive_forgetting.py` | 自适应遗忘 |
| `pangu/memory/consolidation.py` | 记忆巩固引擎 |
| `pangu/memory/reconsolidation.py` | 再巩固引擎 |
| `pangu/memory/resonance.py` | 共鸣匹配 |

### 高级推理

| 模块 | 职责 |
| --- | --- |
| `pangu/memory/working_memory.py` | 工作记忆（Miller 定律 7±2） |
| `pangu/memory/attention.py` | 注意力系统（5 策略） |
| `pangu/memory/neural_memory.py` | 类人记忆神经网络 |
| `pangu/memory/causal_reasoning.py` | 因果推理引擎 |
| `pangu/memory/world_model.py` | 预测性世界模型 |
| `pangu/memory/narrative.py` | 叙事引擎 |
| `pangu/memory/deep_emotion.py` | 深度情绪智能 |
| `pangu/memory/emotional_intelligence.py` | 情感智能 |
| `pangu/memory/multi_agent.py` | 多 Agent 协作记忆 |
| `pangu/memory/collaborative_intelligence.py` | 协作智能引擎 |
| `pangu/memory/debate.py` | 多策略辩论引擎 |
| `pangu/memory/advanced_reasoning.py` | 高级推理引擎 |
| `pangu/memory/graph_reasoning.py` | 图推理引擎 |
| `pangu/memory/knowledge_synthesis.py` | 知识综合引擎 |

### 辅助功能

| 模块 | 职责 |
| --- | --- |
| `pangu/memory/event_bus.py` | 统一事件总线 |
| `pangu/memory/memory_events.py` | 记忆事件流 |
| `pangu/memory/self_improve.py` | 自我提升工作器 |
| `pangu/memory/self_repair.py` | 自评估+自修复引擎 |
| `pangu/memory/backup_restore.py` | 备份与恢复 |
| `pangu/memory/export_import.py` | 导出导入引擎 |
| `pangu/memory/analytics.py` | 记忆分析看板 |
| `pangu/memory/health_monitor.py` | 记忆健康监控 |
| `pangu/memory/error_monitor.py` | 错误监控 |
| `pangu/memory/search_analytics.py` | 搜索模式分析 |
| `pangu/memory/query_rewriter.py` | 搜索查询重写 |
| `pangu/memory/natural_query.py` | 自然语言查询解析 |
| `pangu/memory/intent_prediction.py` | 用户意图预测 |
| `pangu/memory/predictive_analytics.py` | 预测分析 |
| `pangu/memory/recommendation.py` | 记忆推荐系统 |
| `pangu/memory/proactive.py` | 预测性记忆 |
| `pangu/memory/proactive_reminder.py` | 主动提醒引擎 |
| `pangu/memory/timeline.py` | 时间线引擎 |
| `pangu/memory/temporal_reasoning.py` | 时间推理 |
| `pangu/memory/adaptive_learning.py` | 自适应学习系统 |
| `pangu/memory/adaptive_params.py` | 自适应参数系统 |
| `pangu/memory/adaptive_architecture.py` | 自适应记忆架构 |
| `pangu/memory/self_evolution.py` | 自进化引擎 |
| `pangu/memory/meta_learning.py` | 元学习引擎 |
| `pangu/memory/cognitive_loop.py` | 认知循环 |
| `pangu/memory/auto_pilot.py` | 自动驾驶模式 |
| `pangu/memory/collector.py` | 通用自动记忆采集器 |
| `pangu/memory/batch_import.py` | 批量多模态导入 |
| `pangu/memory/multimodal.py` | 多模态记忆支持 |
| `pangu/memory/multimodal_pipeline.py` | 多模态输入管道 |
| `pangu/memory/multimodal_search.py` | 多模态搜索引擎 |
| `pangu/memory/multimodal_summary.py` | 多模态摘要引擎 |
| `pangu/memory/image_engine.py` | 图片记忆引擎 |
| `pangu/memory/audio_engine.py` | 音频记忆引擎 |
| `pangu/memory/video_engine.py` | 视频记忆引擎 |
| `pangu/memory/domain_knowledge.py` | 领域知识库 |
| `pangu/memory/hologram.py` | 全息记忆编码 |
| `pangu/memory/memory_validator.py` | 记忆验证机制 |
| `pangu/memory/quality.py` | 记忆质量管道 |
| `pangu/memory/quality_scorer.py` | 记忆质量评分 |
| `pangu/memory/importance_scorer.py` | 记忆重要性评分 |
| `pangu/memory/dedup.py` | 记忆去重引擎 |
| `pangu/memory/conflict.py` | 冲突检测引擎 |
| `pangu/memory/memory_diff.py` | 记忆差异对比 |
| `pangu/memory/versioning.py` | 记忆版本控制 |
| `pangu/memory/evolution.py` | 记忆进化模块 |
| `pangu/memory/session_bridge.py` | 跨会话记忆整合 |
| `pangu/memory/cross_session.py` | 跨会话记忆整合 |
| `pangu/memory/context_injection.py` | 上下文自动注入 |
| `pangu/memory/context_injector.py` | 上下文注入引擎 |
| `pangu/memory/smart_cache.py` | 智能缓存管理 |
| `pangu/memory/smart_indexing.py` | 智能自动索引 |
| `pangu/memory/streaming_index.py` | 流式索引 |
| `pangu/memory/sync_manager.py` | 多端同步 |
| `pangu/memory/synonyms.py` | 同义词扩展 |
| `pangu/memory/anomaly_detection.py` | 异常检测 |
| `pangu/memory/patterns.py` | 模式识别引擎 |
| `pangu/memory/clustering.py` | 记忆聚类引擎 |
| `pangu/memory/cluster.py` | 搜索结果聚类 |
| `pangu/memory/semantic_compression.py` | 语义压缩 |
| `pangu/memory/explainable_search.py` | 可解释搜索 |
| `pangu/memory/evaluation.py` | 评估缓存独立化 |
| `pangu/memory/warmup.py` | 启动预热 |
| `pangu/memory/performance.py` | 性能基准监控 |
| `pangu/memory/differential_privacy.py` | 差分隐私 |
| `pangu/memory/lifespan.py` | 生命周期管理 |
| `pangu/mining/miners.py` | 挖掘模块 |
| `pangu/observability/metrics.py` | Prometheus 指标导出 |
| `pangu/observability/performance_monitor.py` | 性能基准监控 |
| `pangu/observability/tracing.py` | OpenTelemetry 分布式追踪 |
| `pangu/autonomous.py` | 自主判断引擎 |

---

## 边缘模块（未接线/实验性/可选）

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `pangu/memory/feishu_webhook.py` | 飞书 Webhook | 可选功能，默认关闭 |
| `pangu/memory/git_hook.py` | Git Hook 集成 | 可选功能 |
| `pangu/memory/file_watcher.py` | 文件监控 | 可选功能 |
| `pangu/memory/social_memory.py` | 记忆社交化 | 实验性 |
| `pangu/memory/portal.py` | 记忆门户 | 实验性 |
| `pangu/memory/persona.py` | 人格引擎 | 实验性 |
| `pangu/memory/project_manager.py` | 多项目管理 | 实验性 |
| `pangu/memory/qa_engine.py` | 智能问答引擎 | 实验性 |
| `pangu/memory/replay.py` | 记忆回放引擎 | 实验性 |
| `pangu/memory/fuxi_bridge.py` | 伏羲桥接引擎 | 实验性 |
| `pangu/memory/creative_thinking.py` | 创造性思维 | 实验性 |
| `pangu/memory/consolidation_intelligence.py` | 记忆巩固智能 | 实验性 |
| `pangu/memory/verification.py` | 验证循环 | 实验性 |
| `pangu/task_tracker.py` | 任务进度追踪器 | 独立工具 |
| `pangu/ui/__init__.py` | UI 模块 | 占位 |

---

## 统计

| 级别 | 数量 | 占比 |
| --- | --- | --- |
| 核心 | ~60 | 26% |
| 活跃 | ~140 | 61% |
| 边缘 | ~30 | 13% |

---

## 维护规则

1. **新增模块时必须归类** — 在对应级别表格里加一行
2. **每季度复审一次** — 边缘模块如果接线了就升级到活跃
3. **核心模块覆盖率 100%** — 核心模块必须有测试覆盖
4. **边缘模块不阻塞发布** — 边缘模块坏了不影响核心功能

---

*本文档随迭代推进持续更新。*
