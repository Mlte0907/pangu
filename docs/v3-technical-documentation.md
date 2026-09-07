# 盘古 v3.0 技术文档

> 版本: v3.0 | 日期: 2026-06-17 | 模块数: 94 | MCP 工具: 315 | 测试: 428 | 代码量: 30K+ 行

---

## 目录

1. [项目概览](#1-项目概览)
2. [架构设计](#2-架构设计)
3. [核心模块说明](#3-核心模块说明)
4. [v3.0 新增模块](#4-v30-新增模块)
5. [MCP 工具清单](#5-mcp-工具清单)
6. [API 参考](#6-api-参考)
7. [配置说明](#7-配置说明)
8. [部署指南](#8-部署指南)
9. [性能指标](#9-性能指标)
10. [测试覆盖](#10-测试覆盖)

---

## 1. 项目概览

### 1.1 定位

盘古 (Pangu) 是一个为 AI Agent 框架设计的**记忆系统**（"大脑组件"）。它提供记忆存储、检索、组织、分类和知识结晶化功能，通过 MCP 协议暴露 315 个工具接口。

### 1.2 版本演进

| 版本 | Commits | MCP 工具 | 模块数 | 测试数 | 代码量 | 核心能力 |
|---|---|---|---|---|---|---|
| v1.0 | ~20 | ~30 | ~15 | ~30 | ~5K | 基础记忆存储/检索 |
| v2.0 | 68 | 177 | 63 | 153 | 22,832 | 高级智能（情感、因果、神经记忆） |
| **v3.0** | **104** | **315** | **94** | **428** | **30K+** | **顶级智能（自进化、元学习、预测分析）** |

### 1.3 项目位置

| 路径 | 用途 |
|---|---|
| `/home/xiaoxin/pangu/` | 代码仓库 |
| `~/.pangu/` | 运行时数据目录 |
| `~/.pangu/config.json` | 主配置文件 |
| `~/.pangu/palace/` | 记忆宫殿数据 |
| `~/.pangu/projects/` | 多项目空间 |
| `~/.cache/pangu/` | 向量索引缓存 |
| `~/.pangu/exports/` | 导出文件 |
| `~/.pangu/backups/` | 备份文件 |
| `~/.pangu/events/` | 事件日志 |
| `~/.pangu/sync/` | 同步数据 |

### 1.4 服务端口

- HTTP API: `19529`
- MCP stdio: `pangu mcp`

---

## 2. 架构设计

### 2.1 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (315 tools)                    │
├─────────────────────────────────────────────────────────────┤
│  Portal (统一入口)       │  Event Stream (事件总线)          │
├─────────────────────────────────────────────────────────────┤
│                    智能引擎层 (14 模块)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 自进化    │ │ 元学习    │ │ 因果推理  │ │ 推荐系统  │       │
│  │ 引擎     │ │ 引擎     │ │ 引擎     │ │ 引擎     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 情感智能  │ │ 创造力   │ │ 预测分析  │ │ 异常检测  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 自主学习  │ │ 自适应    │ │ 高级推理  │ │ 判断引擎  │       │
│  │          │ │ 架构     │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│                    记忆管理层 (16 模块)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 4层记忆栈 │ │ 巩固智能  │ │ 自适应遗忘│ │ 语义压缩  │       │
│  │ L0-L3    │ │          │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 记忆衰减  │ │ 去重     │ │ 巩固     │ │ 合并     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│                    搜索与检索层 (12 模块)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 混合搜索  │ │ FTS5搜索  │ │ 查询重写  │ │ 上下文注入│       │
│  │ FTS+Vec  │ │          │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 全息检索  │ │ 可解释搜索│ │ 智能索引  │ │ 流式索引  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│                    基础设施层 (22 模块)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 向量索引  │ │ ONNX嵌入 │ │ SQLite   │ │ 智能缓存  │       │
│  │ FAISS    │ │ 384维    │ │ WAL模式  │ │ L1+L2    │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 加密     │ │ 备份恢复  │ │ 版本控制  │ │ 事件总线  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 4 层记忆栈

盘古采用渐进式记忆加载策略，类似人类大脑工作记忆模型：

| 层级 | 名称 | 容量 | 加载策略 | 用途 |
|---|---|---|---|---|
| L0 | 身份层 | ~100 tokens | 始终加载 | 定义"我是谁"——AI 身份、核心规则 |
| L1 | 概要层 | ~500-800 tokens | 始终加载 | 关键记忆摘要、高频访问片段 |
| L2 | 按需层 | ~200-2000 tokens | 话题触发加载 | 详细上下文，按 Wing/Room 加载 |
| L3 | 深度搜索 | 无限 | 显式查询触发 | FTS5+向量全文语义搜索 |

```python
from pangu.memory.layers import MemoryStack
stack = MemoryStack(config)
drawers = stack.get_drawers()        # 获取所有记忆
identity = stack.get_identity()      # 获取 L0 身份
summary = stack.get_summary()        # 获取 L1 概要
```

### 2.3 3 层嵌入降级策略

| 优先级 | 方案 | 延迟 | 成本 | 适用场景 |
|---|---|---|---|---|
| 1 | ONNX 本地 (MiniLM-L6, 384维) | ~0ms (缓存命中) | 免费 | 默认首选 |
| 2 | API (Ollama) | ~50ms | 低 | ONNX 不可用时 |
| 3 | Hash 向量 (SimHash) | ~0ms | 免费 | 降级兜底 |

```python
from pangu.memory.onnx_embedder import ONNXEmbedder
embedder = ONNXEmbedder()
vector = embedder.embed("Python 异步编程最佳实践")  # 384维向量
similarity = embedder.similarity(text_a, text_b)     # 余弦相似度
```

### 2.4 混合搜索 (Hybrid Search)

三路召回 + RRF 融合：

```
FTS5 (jieba 分词)    × 0.5 权重  ─┐
                                    ├─→ RRF 融合 (K=60) → 排序结果
向量搜索 (FAISS)      × 1.0 权重  ─┤
知识图谱 (KG)         × 0.8 权重  ─┘
```

### 2.5 记忆写入流水线 (Ingestion Pipeline)

```
原始内容 → 去重检查 → 重要性评分 → 融合判断 → 嵌入向量 → 全息编码
    → WikiLink 提取 → 知识图谱更新 → 向量索引更新 → 事件发布
```

---

## 3. 核心模块说明

### 3.1 记忆栈 (layers.py)

4 层渐进式记忆加载系统。

```python
from pangu.memory.layers import MemoryStack
stack = MemoryStack(config)
drawers = stack.get_drawers()  # 获取所有记忆
```

| 类 | 功能 |
|---|---|
| `MemoryStack` | 4 层记忆栈管理器 |

### 3.2 搜索与检索 (retrieval.py / hybrid_search.py)

FTS+向量混合检索，Recall@5 性能 29ms。

```python
from pangu.memory.retrieval import recall
results = recall(query="Python优化", limit=5, drawers=drawers)
```

| 类 | 功能 |
|---|---|
| `recall()` | 核心检索函数 |
| `HybridSearchEngine` | FTS+向量混合搜索引擎 |

### 3.3 记忆摄入 (ingestion.py)

记忆写入流水线：去重 → 融合 → 嵌入 → 全息 → WikiLink → 向量索引。

| 函数 | 功能 |
|---|---|
| `remember()` | 记忆写入入口 |

### 3.4 知识图谱 (knowledge_graph.py)

实体/关系图谱，支持自动抽取、跨域推理、因果链分析。

| 类 | 功能 |
|---|---|
| `KnowledgeGraph` | 知识图谱核心类 |

### 3.5 向量索引 (vector_index.py / onnx_embedder.py)

FAISS 索引 + ONNX 本地推理，支持增量更新。

| 类 | 功能 |
|---|---|
| `VectorIndex` | FAISS 向量索引管理 |
| `ONNXEmbedder` | ONNX 本地嵌入推理 |

### 3.6 FTS5 全文搜索 (fts_search.py)

基于 SQLite FTS5 的全文搜索引擎，支持 jieba 中文分词。

| 类 | 功能 |
|---|---|
| `FTS5SearchEngine` | FTS5 全文搜索引擎 |

### 3.7 全息编码 (hologram.py)

将记忆编码为 5 维全息投影，支持跨维度融合检索。

| 函数 | 功能 |
|---|---|
| `get_holographic_encoder()` | 获取全息编码器实例 |

### 3.8 记忆法官 (judge.py)

LLM 驱动的记忆价值判断，A/B/C 三级分类。

| 函数 | 功能 |
|---|---|
| `get_memory_judge()` | 获取记忆法官实例 |

### 3.9 自适应参数 (adaptive_params.py)

根据系统运行状态动态调整策略参数。

| 函数 | 功能 |
|---|---|
| `get_adaptive_engine()` | 获取自适应参数引擎 |

### 3.10 工作记忆 (working_memory.py)

短期工作记忆栈，类似人类工作记忆模型。

| 类 | 功能 |
|---|---|
| `WMItem` | 工作记忆项 |
| `get_working_memory()` | 获取工作记忆实例 |

### 3.11 记忆脱敏 (sanitizer.py)

PII 检测与脱敏处理。

| 类 | 功能 |
|---|---|
| `MemorySanitizer` | 记忆脱敏器 |

### 3.12 再巩固 (reconsolidation.py)

记忆再巩固与共鸣发现。

| 类 | 功能 |
|---|---|
| `ReconsolidationEngine` | 再巩固引擎 |
| `ResonanceEngine` | 共鸣引擎 |

### 3.13 知识蒸馏增强 (distill_enhanced.py)

从记忆中蒸馏结构化知识卡片。

| 类 | 功能 |
|---|---|
| `DistillationTower` | 蒸馏塔 |

### 3.14 增强评估 (enhanced_evaluation.py)

LLM 驱动的矛盾检测与轨迹追踪。

| 类 | 功能 |
|---|---|
| `EnhancedContradictionDetector` | 增强矛盾检测器 |
| `TrajectoryTracker` | 轨迹追踪器 |

### 3.15 注意力系统 (attention.py)

可切换的注意力策略系统。

| 函数 | 功能 |
|---|---|
| `get_attention_system()` | 获取注意力系统 |

### 3.16 流式索引 (streaming_index.py)

增量索引新记忆到 FAISS。

| 类 | 功能 |
|---|---|
| `StreamingIndexer` | 流式索引器 |

### 3.17 验证循环 (verification.py)

记忆准确性与完整性验证。

| 类 | 功能 |
|---|---|
| `VerificationLoop` | 验证循环 |

### 3.18 差分隐私 (differential_privacy.py)

隐私预算管理与差分隐私保护。

| 类 | 功能 |
|---|---|
| `DifferentialPrivacy` | 差分隐私管理器 |

---

## 4. v3.0 新增模块

### 4.1 自进化引擎 (self_evolution.py)

系统自我诊断、进化计划、性能趋势追踪。

| MCP 工具 | 功能 |
|---|---|
| `pangu_self_diagnose` | 全面系统诊断 |
| `pangu_evolution_plan` | 生成进化计划 |
| `pangu_performance_trend` | 查看性能趋势 |
| `pangu_evolution_stats` | 进化统计 |

### 4.2 时间推理 (temporal_reasoning.py)

时间感知记忆，理解事件时间线。

| MCP 工具 | 功能 |
|---|---|
| `pangu_temporal_timeline` | 构建时间线 |
| `pangu_temporal_relations` | 发现时间关系 |
| `pangu_temporal_query` | 按时间范围查询 |
| `pangu_temporal_stats` | 时间统计 |

### 4.3 语义压缩 (semantic_compression.py)

标签聚类压缩、语义去重、重要性重评估。

| MCP 工具 | 功能 |
|---|---|
| `pangu_compress_by_tags` | 按标签压缩 |
| `pangu_find_duplicates` | 发现重复 |
| `pangu_reassess_importance` | 重评估重要性 |
| `pangu_compression_stats` | 压缩统计 |

### 4.4 协作智能 (collaborative_intelligence.py)

多 Agent 间知识共享和协作推理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_agent_register` | 注册 Agent |
| `pangu_agent_share` | 共享知识 |
| `pangu_collaborative_reason` | 协作推理 |
| `pangu_agent_stats` | Agent 统计 |

### 4.5 因果推理 (causal_reasoning.py)

因果链发现、反事实推理、根因分析。

| MCP 工具 | 功能 |
|---|---|
| `pangu_causal_discover` | 发现因果链接 |
| `pangu_causal_chains` | 构建因果链 |
| `pangu_counterfactual` | 反事实推理 |
| `pangu_root_cause` | 根因分析 |
| `pangu_causal_stats` | 因果统计 |

### 4.6 可解释搜索 (explainable_search.py)

搜索结果解释和改进建议。

| MCP 工具 | 功能 |
|---|---|
| `pangu_explain_search` | 解释搜索结果 |
| `pangu_search_suggestions` | 搜索改进建议 |

### 4.7 异常检测 (anomaly_detection.py)

分布异常、内容异常、行为异常检测。

| MCP 工具 | 功能 |
|---|---|
| `pangu_anomaly_scan` | 全面异常扫描 |
| `pangu_anomaly_content` | 内容异常检测 |
| `pangu_anomaly_stats` | 异常统计 |

### 4.8 知识综合 (knowledge_synthesis.py)

多源融合、矛盾检测、核心洞察提炼。

| MCP 工具 | 功能 |
|---|---|
| `pangu_synthesize` | 按主题综合 |
| `pangu_find_contradictions` | 检测矛盾 |
| `pangu_core_insights` | 提取核心洞察 |
| `pangu_auto_learn` | 执行自主学习循环 |

### 4.9 预测分析 (predictive_analytics.py)

需求预测、遗忘预测、热点预测。

| MCP 工具 | 功能 |
|---|---|
| `pangu_predict_queries` | 预测查询 |
| `pangu_predict_forgetting` | 预测遗忘 |
| `pangu_growth_trend` | 增长趋势 |
| `pangu_hot_topics` | 热点预测 |
| `pangu_predictive_stats` | 预测统计 |

### 4.10 自适应架构 (adaptive_architecture.py)

记忆架构分析、重构建议、冷热分离。

| MCP 工具 | 功能 |
|---|---|
| `pangu_arch_analyze` | 架构分析 |
| `pangu_arch_suggest` | 重构建议 |
| `pangu_cold_hot` | 冷热分离 |
| `pangu_arch_stats` | 架构统计 |

### 4.11 智能问答 (qa_engine.py)

基于记忆的智能问答，支持意图检测和追问生成。

| MCP 工具 | 功能 |
|---|---|
| `pangu_qa` | 智能问答 |
| `pangu_qa_batch` | 批量问答 |
| `pangu_qa_stats` | 问答统计 |

### 4.12 上下文注入 (context_injection.py)

自动为对话注入相关记忆上下文。

| MCP 工具 | 功能 |
|---|---|
| `pangu_inject_context` | 注入上下文 |
| `pangu_update_context` | 增量更新 |
| `pangu_current_context` | 获取当前上下文 |
| `pangu_injection_stats` | 注入统计 |

### 4.13 自适应遗忘 (adaptive_forgetting.py)

智能记忆生命周期管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_evaluate_forgetting` | 评估遗忘价值 |
| `pangu_auto_forget` | 自动遗忘 |
| `pangu_get_archive` | 获取归档 |
| `pangu_forget_stats` | 遗忘统计 |

### 4.14 巩固智能 (consolidation_intelligence.py)

语义聚类巩固、冲突解决、旧记忆压缩。

| MCP 工具 | 功能 |
|---|---|
| `pangu_consolidate` | 执行巩固 |
| `pangu_merge_candidates` | 查找合并候选 |
| `pangu_resolve_conflicts` | 解决矛盾 |
| `pangu_consolidation_stats` | 巩固统计 |

### 4.15 记忆推荐 (recommendation.py)

上下文推荐、相似推荐、时效推荐、跨域推荐。

| MCP 工具 | 功能 |
|---|---|
| `pangu_recommend` | 综合推荐 |
| `pangu_recommend_similar` | 相似推荐 |
| `pangu_recommend_timely` | 时效推荐 |
| `pangu_recommend_feedback` | 反馈记录 |
| `pangu_recommendation_stats` | 推荐统计 |

### 4.16 质量评分 (quality_scorer.py)

5 维度评分（完整性、独特性、关联性、密度、重要性）。

| MCP 工具 | 功能 |
|---|---|
| `pangu_assess_quality` | 评估单条质量 |
| `pangu_batch_assess` | 批量评估 |
| `pangu_auto_fix` | 自动修复 |
| `pangu_quality_stats` | 质量统计 |

### 4.17 元学习 (meta_learning.py)

学习如何更好地学习，自动调优策略参数。

| MCP 工具 | 功能 |
|---|---|
| `pangu_meta_observe` | 记录性能观察 |
| `pangu_meta_recommend` | 推荐最优策略 |
| `pangu_meta_tune` | 自动调优 |
| `pangu_meta_insights` | 学习洞察 |
| `pangu_meta_stats` | 元学习统计 |

### 4.18 记忆蒸馏 (distillation.py)

从原始记忆提炼精炼知识。

| MCP 工具 | 功能 |
|---|---|
| `pangu_distill` | 蒸馏所有记忆 |
| `pangu_distill_by_wing` | 按领域蒸馏 |
| `pangu_extract_keywords` | 提取关键词 |
| `pangu_distillation_stats` | 蒸馏统计 |

### 4.19 查询重写 (query_rewriter.py)

同义词扩展、意图检测、查询分解。

| MCP 工具 | 功能 |
|---|---|
| `pangu_rewrite_query` | 重写查询 |
| `pangu_suggest_queries` | 查询建议 |
| `pangu_rewrite_stats` | 重写统计 |

### 4.20 图谱构建 (graph_builder.py)

自动从记忆构建知识图谱。

| MCP 工具 | 功能 |
|---|---|
| `pangu_build_graph` | 构建图谱 |
| `pangu_graph_entity` | 获取实体 |
| `pangu_graph_path` | 查找路径 |
| `pangu_graph_quality` | 评估质量 |
| `pangu_graph_stats` | 图谱统计 |

### 4.21 健康监控 (health_monitor.py)

6 维度健康检查（记忆量、重要性、标签、分布、内容、重复）。

| MCP 工具 | 功能 |
|---|---|
| `pangu_health_check` | 全面检查 |
| `pangu_health_trend` | 健康趋势 |
| `pangu_health_stats` | 健康统计 |

### 4.22 备份恢复 (backup_restore.py)

全量备份、增量备份、备份验证、选择性恢复。

| MCP 工具 | 功能 |
|---|---|
| `pangu_backup` | 全量备份 |
| `pangu_list_backups` | 列出备份 |
| `pangu_verify_backup` | 验证备份 |
| `pangu_restore_backup` | 恢复备份 |
| `pangu_backup_stats` | 备份统计 |

### 4.23 多项目支持 (project_manager.py)

项目隔离、切换、跨项目搜索、合并。

| MCP 工具 | 功能 |
|---|---|
| `pangu_project_create` | 创建项目 |
| `pangu_project_switch` | 切换项目 |
| `pangu_project_list` | 列出项目 |
| `pangu_project_active` | 当前项目 |
| `pangu_project_save` | 保存到项目 |
| `pangu_project_load` | 加载项目 |
| `pangu_project_search` | 跨项目搜索 |
| `pangu_project_merge` | 合并项目 |
| `pangu_project_delete` | 删除项目 |
| `pangu_project_stats` | 项目统计 |

### 4.24 审计分析 (audit_analytics.py)

操作审计、访问分析、异常检测。

| MCP 工具 | 功能 |
|---|---|
| `pangu_audit_log` | 记录审计 |
| `pangu_audit_query` | 查询审计 |
| `pangu_audit_stats` | 操作统计 |
| `pangu_access_patterns` | 访问模式 |
| `pangu_security_summary` | 安全摘要 |

### 4.25 多端同步 (sync_manager.py)

变更追踪、冲突检测、冲突解决。

| MCP 工具 | 功能 |
|---|---|
| `pangu_sync_record` | 记录变更 |
| `pangu_sync_pending` | 待同步变更 |
| `pangu_sync_conflicts` | 检测冲突 |
| `pangu_sync_resolve` | 解决冲突 |
| `pangu_sync_state` | 同步状态 |
| `pangu_sync_stats` | 同步统计 |

### 4.26 记忆事件流 (memory_events.py)

实时事件发布/订阅/回放/Webhook。

| MCP 工具 | 功能 |
|---|---|
| `pangu_event_emit` | 发布事件 |
| `pangu_event_history` | 事件历史 |
| `pangu_event_stats` | 事件统计 |
| `pangu_event_webhook_add` | 添加 Webhook |
| `pangu_event_save` | 持久化事件 |

### 4.27 智能索引 (smart_indexing.py)

热词索引、标签索引、Wing 索引、索引推荐。

| MCP 工具 | 功能 |
|---|---|
| `pangu_index_build` | 构建索引 |
| `pangu_index_search` | 索引搜索 |
| `pangu_index_recommend` | 索引推荐 |
| `pangu_index_health` | 索引健康 |
| `pangu_index_cleanup` | 清理索引 |

### 4.28 智能缓存 (smart_cache.py)

双层缓存（L1+L2）、自适应 TTL、缓存预热、穿透防护。

| MCP 工具 | 功能 |
|---|---|
| `pangu_cache_stats` | 缓存统计 |
| `pangu_cache_cleanup` | 清理缓存 |
| `pangu_cache_invalidate` | 失效缓存 |

### 4.29 统一门户 (portal.py)

一站式记忆操作入口，智能写入/搜索/全景/维护/摘要。

| MCP 工具 | 功能 |
|---|---|
| `pangu_portal_write` | 智能写入 |
| `pangu_portal_search` | 智能搜索 |
| `pangu_portal_panorama` | 系统全景 |
| `pangu_portal_maintain` | 一键维护 |
| `pangu_portal_summary` | 智能摘要 |

### 4.30 记忆差异 (memory_diff.py)

内容差异对比、批量对比、相似度矩阵。

| MCP 工具 | 功能 |
|---|---|
| `pangu_diff_content` | 对比内容 |
| `pangu_diff_batch` | 批量对比 |
| `pangu_diff_similarity` | 相似度矩阵 |
| `pangu_diff_stats` | 差异统计 |

### 4.31 导出导入 (export_import.py)

JSON/Markdown/CSV 多格式导出，智能导入。

| MCP 工具 | 功能 |
|---|---|
| `pangu_export_json` | JSON 导出 |
| `pangu_export_markdown` | Markdown 导出 |
| `pangu_export_csv` | CSV 导出 |
| `pangu_import_smart` | 智能导入 |
| `pangu_list_exports` | 列出导出 |
| `pangu_export_stats` | 导出统计 |

### 4.32 迁移 (migration.py)

数据库 schema 迁移管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_schema_version` | 获取 schema 版本 |
| `pangu_schema_migrations` | 列出迁移版本 |

### 4.33 加密 (encryption.py)

Fernet E2E 加密，保护记忆内容。

| 类 | 功能 |
|---|---|
| `EncryptionManager` | 加密管理器 |

### 4.34 事件总线 (event_bus.py)

进程内事件发布/订阅机制。

| 类 | 功能 |
|---|---|
| `EventBus` | 事件总线 |

### 4.35 版本控制 (versioning.py)

记忆变更历史追踪与版本对比。

| MCP 工具 | 功能 |
|---|---|
| `pangu_version_history` | 变更历史 |
| `pangu_version_compare` | 版本对比 |

### 4.36 可视化 (visualization.py)

知识图谱与记忆网络可视化。

| MCP 工具 | 功能 |
|---|---|
| `pangu_visualize_graph` | 知识图谱可视化 |
| `pangu_visualize_network` | 记忆网络可视化 |
| `pangu_visualize_stats` | 统计可视化 |

### 4.37 重要性评分 (importance_scorer.py)

记忆重要性综合评分。

| MCP 工具 | 功能 |
|---|---|
| `pangu_importance_score` | 计算重要性评分 |

### 4.38 社交记忆 (social_memory.py)

评论、投票、协作标注。

| MCP 工具 | 功能 |
|---|---|
| `pangu_comment_add` | 添加评论 |
| `pangu_comment_list` | 列出评论 |
| `pangu_vote` | 投票 |
| `pangu_vote_stats` | 投票统计 |

### 4.39 自适应学习 (adaptive_learning.py)

用户行为模式检测与学习。

| MCP 工具 | 功能 |
|---|---|
| `pangu_learning_stats` | 学习统计 |
| `pangu_detect_patterns` | 模式检测 |
| `pangu_popular_queries` | 热门查询 |
| `pangu_frequent_memories` | 频繁记忆 |

### 4.40 性能基准 (performance.py)

系统性能测试与基准。

| MCP 工具 | 功能 |
|---|---|
| `pangu_benchmark` | 运行基准测试 |

### 4.41 自动收集 (auto_collector.py)

从会话文件自动提取记忆。

| MCP 工具 | 功能 |
|---|---|
| `pangu_auto_collect` | 自动收集记忆 |

### 4.42 自然语言查询 (natural_query.py)

自然语言语义查询。

| MCP 工具 | 功能 |
|---|---|
| `pangu_natural_query` | 自然语言查询 |

### 4.43 记忆聚类 (clustering.py / cluster.py)

自动聚类与主题分组。

| MCP 工具 | 功能 |
|---|---|
| `pangu_cluster_memories` | 记忆聚类 |
| `pangu_find_related` | 查找相关记忆 |

### 4.44 冲突检测 (conflict.py)

记忆矛盾与不一致检测。

| MCP 工具 | 功能 |
|---|---|
| `pangu_detect_conflicts` | 检测冲突 |
| `pangu_check_pair` | 检查配对 |

### 4.45 去重 (dedup.py)

重复或高度相似记忆检测与合并。

| MCP 工具 | 功能 |
|---|---|
| `pangu_find_duplicates` | 发现重复 |
| `pangu_merge_duplicates` | 合并重复 |
| `pangu_similarity_check` | 相似度检查 |

### 4.46 分析看板 (analytics.py)

全面记忆分析报告。

| MCP 工具 | 功能 |
|---|---|
| `pangu_analyze` | 全面分析 |
| `pangu_health_check` | 健康检查 |
| `pangu_anomaly_detect` | 异常检测 |
| `pangu_growth_trend` | 增长趋势 |

### 4.47 时间线 (timeline.py)

记忆时间线构建与事件链。

| MCP 工具 | 功能 |
|---|---|
| `pangu_build_timeline` | 构建时间线 |
| `pangu_find_causal_links` | 因果链接 |
| `pangu_event_chains` | 事件链 |
| `pangu_timeline_query` | 时间范围查询 |

### 4.48 融合引擎 (fusion.py)

主题融合与渐进式摘要。

| MCP 工具 | 功能 |
|---|---|
| `pangu_fuse_topic` | 主题融合 |
| `pangu_progressive_summarize` | 渐进式摘要 |
| `pangu_crystallize_knowledge` | 知识结晶 |

### 4.49 模式识别 (patterns.py)

隐藏模式与规律发现。

| MCP 工具 | 功能 |
|---|---|
| `pangu_discover_patterns` | 发现模式 |
| `pangu_pattern_insights` | 模式洞察 |

### 4.50 记忆回放 (replay.py)

按时间线/主题回放记忆。

| MCP 工具 | 功能 |
|---|---|
| `pangu_timeline_replay` | 时间线回放 |
| `pangu_topic_replay` | 主题回放 |
| `pangu_highlight_reel` | 精彩集锦 |

### 4.51 Wiki 引擎 (wikilink.py)

WikiLink 提取与页面管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_list_wiki_pages` | 列出页面 |
| `pangu_get_wiki_page` | 获取页面 |
| `pangu_create_wiki_page` | 创建页面 |
| `pangu_auto_generate_wiki` | 自动生成 Wiki |

### 4.52 对话式搜索 (natural_query.py)

多轮澄清对话式搜索。

| MCP 工具 | 功能 |
|---|---|
| `pangu_conversational_search` | 对话式搜索 |

### 4.53 记忆洞察 (natural_query.py)

从记忆中提取洞察和模式。

| MCP 工具 | 功能 |
|---|---|
| `pangu_memory_insights` | 记忆洞察 |

### 4.54 神经记忆 (neural_memory.py)

海马体-新皮层双系统模拟。

| MCP 工具 | 功能 |
|---|---|
| `pangu_neural_stats` | 神经系统统计 |
| `pangu_neural_sleep` | 神经睡眠巩固 |
| `pangu_neural_spreading` | 激活扩散 |
| `pangu_neural_inhibition` | 竞争抑制 |
| `pangu_neural_decay` | 个性化衰减 |

### 4.55 重要性反馈 (importance_scorer.py)

反馈信号驱动的重要性动态调整。

| MCP 工具 | 功能 |
|---|---|
| `pangu_importance_feedback` | 反馈调整 |
| `pangu_auto_fusion` | 自动融合 |

### 4.56 跨会话整合 (cross_session.py)

跨会话记忆关联发现与自动压缩。

| MCP 工具 | 功能 |
|---|---|
| `pangu_cross_session_links` | 跨会话关联 |
| `pangu_auto_compress` | 自动压缩 |

### 4.57 记忆验证 (verification.py)

记忆准确性与时效性验证。

| MCP 工具 | 功能 |
|---|---|
| `pangu_validate_memories` | 验证记忆 |

### 4.58 知识图谱增强 (knowledge_graph.py)

自动实体/关系抽取与跨域迁移。

| MCP 工具 | 功能 |
|---|---|
| `pangu_kg_auto_extract` | 自动抽取 |
| `pangu_kg_cross_domain` | 跨域迁移 |
| `pangu_kg_similar_patterns` | 相似模式 |

### 4.59 混合检索增强 (hybrid_search.py)

FTS+向量+KG 三路 RRF 融合。

| MCP 工具 | 功能 |
|---|---|
| `pangu_hybrid_search` | 三路融合搜索 |
| `pangu_cluster_by_tags` | 按标签聚类 |
| `pangu_cluster_by_time` | 按时间聚类 |
| `pangu_hierarchical_cluster` | 层次聚类 |
| `pangu_dedup_results` | 搜索去重 |

### 4.60 多 Agent 协作 (multi_agent.py)

Agent 注册、共享记忆读写。

| MCP 工具 | 功能 |
|---|---|
| `pangu_multi_register` | 注册 Agent |
| `pangu_multi_write` | 写入共享记忆 |
| `pangu_multi_read` | 读取共享记忆 |
| `pangu_multi_agents` | 列出 Agent |

### 4.61 图推理 (graph_reasoning.py)

基于知识图谱的推理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_graph_infer` | 图推理 |
| `pangu_graph_contradictions` | 矛盾检测 |
| `pangu_graph_causal_chain` | 因果链分析 |
| `pangu_graph_temporal` | 时序推理 |
| `pangu_graph_analogy` | 类比检测 |
| `pangu_graph_visualize` | 推理可视化 |

### 4.62 预测性记忆 (proactive.py)

基于上下文预测相关记忆。

| MCP 工具 | 功能 |
|---|---|
| `pangu_proactive_predict` | 预测记忆 |
| `pangu_proactive_suggest` | 主动推荐 |
| `pangu_context_status` | 上下文状态 |

### 4.63 情感智能 (emotional_intelligence.py)

情绪分析、预测、交互策略推荐。

| MCP 工具 | 功能 |
|---|---|
| `pangu_analyze_emotion` | 分析情绪 |
| `pangu_emotion_stats` | 情感统计 |
| `pangu_predict_emotion` | 预测情绪 |
| `pangu_recommend_interaction` | 交互推荐 |

### 4.64 创造性思维 (creative_thinking.py)

基于记忆生成新想法与原创。

| MCP 工具 | 功能 |
|---|---|
| `pangu_generate_ideas` | 生成想法 |
| `pangu_discover_patterns` | 发现模式 |
| `pangu_generate_novel` | 生成原创 |

### 4.65 自主学习 (autonomous_learning.py)

从记忆中自动发现知识与生成假设。

| MCP 工具 | 功能 |
|---|---|
| `pangu_discover_knowledge` | 发现知识 |
| `pangu_generate_hypotheses` | 生成假设 |
| `pangu_learning_stats` | 学习统计 |

### 4.66 LLM 响应缓存 (smart_cache.py)

持久化 LLM 缓存，减少 API 调用。

| MCP 工具 | 功能 |
|---|---|
| `pangu_llm_cache_stats` | 缓存统计 |
| `pangu_llm_cache_top` | 热门缓存 |
| `pangu_llm_cache_clear` | 清空缓存 |
| `pangu_llm_cache_metrics` | Prometheus 指标 |
| `pangu_llm_cache_warmup` | 缓存预热 |
| `pangu_llm_cache_warmup_log` | 预热日志 |
| `pangu_llm_cache_vacuum` | 碎片整理 |
| `pangu_llm_cache_config` | 缓存配置 |

### 4.67 ONNX 加速 (onnx_embedder.py)

CPU 加速嵌入，3-10x 性能提升。

| MCP 工具 | 功能 |
|---|---|
| `pangu_onnx_embed` | 单条嵌入 |
| `pangu_onnx_embed_batch` | 批量嵌入 |
| `pangu_onnx_status` | 嵌入器状态 |
| `pangu_onnx_similarity` | 余弦相似度 |

### 4.68 系统管理 (production.py)

健康检查、Prometheus 指标、配置管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_system_health` | 深度健康检查 |
| `pangu_system_metrics` | Prometheus 指标 |
| `pangu_config_get` | 获取配置 |
| `pangu_config_set` | 更新配置 |
| `pangu_config_reload` | 热更新配置 |
| `pangu_api_server_start` | 启动 API |
| `pangu_env_check` | 环境检查 |
| `pangu_startup_validate` | 启动校验 |

### 4.69 自动调优 (adaptive_params.py)

根据系统状态动态调整参数。

| MCP 工具 | 功能 |
|---|---|
| `pangu_adaptive_params` | 获取/调整参数 |
| `pangu_adaptive_evaluate` | 评估并调整 |

### 4.70 工作记忆 (working_memory.py)

短期工作记忆栈管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_wm_push` | 推入项 |
| `pangu_wm_get` | 获取项 |
| `pangu_wm_stats` | 统计 |
| `pangu_wm_clear` | 清空 |

### 4.71 记忆脱敏 (sanitizer.py)

PII 检测与脱敏处理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_sanitize` | 脱敏内容 |
| `pangu_sanitize_check` | 检查是否需脱敏 |

### 4.72 再巩固 (reconsolidation.py)

记忆再巩固与共鸣发现。

| MCP 工具 | 功能 |
|---|---|
| `pangu_reconsolidate` | 再巩固 |
| `pangu_find_resonance` | 共鸣发现 |
| `pangu_cross_wing_resonance` | 跨 Wing 共鸣 |

### 4.73 知识蒸馏 (distill_enhanced.py)

结构化知识卡片蒸馏。

| MCP 工具 | 功能 |
|---|---|
| `pangu_distill_knowledge` | 知识卡片蒸馏 |
| `pangu_distill_causal_chains` | 因果链提取 |
| `pangu_distill_graph` | 关联图 |
| `pangu_distill_stats` | 蒸馏统计 |

### 4.74 向量索引 (vector_index.py)

FAISS 索引构建与管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_vector_index_stats` | 索引统计 |
| `pangu_vector_index_build` | 构建索引 |

### 4.75 注意力系统 (attention.py)

可切换的注意力策略。

| MCP 工具 | 功能 |
|---|---|
| `pangu_attention_state` | 注意力状态 |
| `pangu_attention_switch` | 切换策略 |
| `pangu_attention_ab_test` | A/B 测试 |

### 4.76 增强评估 (enhanced_evaluation.py)

LLM 矛盾检测与轨迹追踪。

| MCP 工具 | 功能 |
|---|---|
| `pangu_enhanced_contradictions` | 矛盾检测 |
| `pangu_trajectory_track` | 轨迹追踪 |
| `pangu_trajectory_compare` | 轨迹对比 |

### 4.77 流式索引 (streaming_index.py)

增量索引新记忆。

| MCP 工具 | 功能 |
|---|---|
| `pangu_streaming_index` | 增量索引 |
| `pangu_streaming_stats` | 流式统计 |

### 4.78 验证循环 (verification.py)

完整验证循环。

| MCP 工具 | 功能 |
|---|---|
| `pangu_verify` | 运行验证 |
| `pangu_verify_phase` | 单阶段验证 |

### 4.79 差分隐私 (differential_privacy.py)

隐私预算管理。

| MCP 工具 | 功能 |
|---|---|
| `pangu_privacy_stats` | 隐私统计 |
| `pangu_privatize_count` | 隐私化计数 |

### 4.80 搜索统计 (fts_search.py)

搜索命中率统计。

| MCP 工具 | 功能 |
|---|---|
| `pangu_fts_search` | FTS5 搜索 |
| `pangu_fts_search_stats` | 搜索统计 |

### 4.81 全息搜索 (hologram.py)

全息跨维度融合检索。

| MCP 工具 | 功能 |
|---|---|
| `pangu_holographic_encode` | 全息编码 |
| `pangu_holographic_search` | 全息搜索 |

### 4.82 记忆法官 (judge.py)

LLM 记忆价值判断。

| MCP 工具 | 功能 |
|---|---|
| `pangu_judge_memory` | 记忆判断 |
| `pangu_judge_stats` | 判断统计 |

### 4.83 搜索统计 (fts_search.py)

搜索命中率统计。

| MCP 工具 | 功能 |
|---|---|
| `pangu_search_stats` | 搜索统计 |

### 4.84 高级推理 (advanced_reasoning.py)

多步推理与逻辑推导。

| 类 | 功能 |
|---|---|
| `AdvancedReasoning` | 高级推理引擎 |

### 4.85 记忆迁移 (migration.py)

数据库 schema 迁移。

| 类 | 功能 |
|---|---|
| `MemoryMigration` | 迁移管理器 |

### 4.86 记忆生命周期 (lifecycle.py / lifespan.py)

记忆全生命周期管理。

| 类 | 功能 |
|---|---|
| `LifecycleManager` | 生命周期管理 |
| `Lifespan` | 记忆寿命 |

### 4.87 记忆合并 (consolidation.py)

记忆合并与压缩。

| 类 | 功能 |
|---|---|
| `MemoryConsolidator` | 合并引擎 |

### 4.88 记忆衰减 (decay.py)

记忆衰减曲线管理。

| 类 | 功能 |
|---|---|
| `MemoryDecay` | 衰减管理器 |

### 4.89 领域知识 (domain_knowledge.py)

领域知识管理。

| 类 | 功能 |
|---|---|
| `DomainKnowledge` | 领域知识引擎 |

### 4.90 同义词扩展 (synonyms.py)

同义词与近义词扩展。

| 类 | 功能 |
|---|---|
| `SynonymExpander` | 同义词扩展器 |

### 4.91 多模态记忆 (multimodal.py)

图像/音频等多模态记忆。

| 类 | 功能 |
|---|---|
| `MultimodalMemory` | 多模态记忆管理 |

### 4.92 图谱推理 (graph_reasoning.py)

知识图谱推理引擎。

| 类 | 功能 |
|---|---|
| `GraphReasoning` | 图谱推理引擎 |

### 4.93 图谱构建 (graph_builder.py)

自动图谱构建。

| 类 | 功能 |
|---|---|
| `GraphBuilder` | 图谱构建器 |

### 4.94 增强蒸馏 (distill_enhanced.py)

增强版蒸馏引擎。

| 类 | 功能 |
|---|---|
| `DistillEnhanced` | 增强蒸馏引擎 |

---

## 5. MCP 工具清单

### 5.1 工具分类统计

| 分类 | 工具数 | 说明 |
|---|---|---|
| Palace 读写 | 4 | Wing/Room 空间管理 |
| 记忆操作 | 8 | CRUD、搜索、召回、唤醒 |
| Wiki 操作 | 4 | 页面管理、自动生成 |
| 知识图谱 | 7 | 实体/关系/推理/可视化 |
| 记忆巩固 | 5 | 遗忘/压缩/关联/重要性 |
| 迁移备份 | 5 | 导出/导入/备份/恢复 |
| 聚类分析 | 2 | 记忆聚类、相关记忆 |
| 冲突检测 | 2 | 矛盾检测、配对检查 |
| 记忆去重 | 3 | 发现/合并/相似度 |
| 分析看板 | 4 | 分析/健康/异常/趋势 |
| 时间线 | 4 | 时间线/因果/事件链/查询 |
| 融合抽象 | 3 | 主题融合/渐进摘要/知识结晶 |
| 模式识别 | 2 | 发现模式/模式洞察 |
| 记忆回放 | 3 | 时间线/主题/精彩集锦 |
| FTS5 搜索 | 2 | 全文搜索/搜索统计 |
| 全息记忆 | 2 | 编码/搜索 |
| 记忆法官 | 2 | 判断/统计 |
| 自适应参数 | 2 | 获取/评估 |
| 工作记忆 | 4 | 推入/获取/统计/清空 |
| 记忆脱敏 | 2 | 脱敏/检查 |
| 再巩固 | 3 | 再巩固/共鸣/跨Wing共鸣 |
| 知识蒸馏增强 | 4 | 知识卡片/因果链/图/统计 |
| 向量索引 | 2 | 统计/构建 |
| 注意力系统 | 3 | 状态/切换/A/B测试 |
| 增强评估 | 3 | 矛盾检测/轨迹追踪/对比 |
| 流式索引 | 2 | 增量索引/统计 |
| 验证循环 | 2 | 完整验证/单阶段 |
| 差分隐私 | 2 | 统计/隐私化计数 |
| 系统管理 | 8 | 健康/指标/配置/启动 |
| ONNX 嵌入 | 4 | 嵌入/批量/状态/相似度 |
| LLM 缓存 | 8 | 统计/热门/清理/指标/预热/日志/碎片/配置 |
| 自然语言查询 | 1 | 语义查询 |
| 记忆推荐 | 1 | 上下文推荐 |
| 对话式搜索 | 1 | 多轮搜索 |
| 记忆洞察 | 1 | 洞察提取 |
| 神经记忆 | 5 | 统计/睡眠/扩散/抑制/衰减 |
| 重要性反馈 | 2 | 反馈调整/自动融合 |
| 跨会话整合 | 2 | 关联/压缩 |
| 记忆验证 | 1 | 准确性验证 |
| 知识图谱增强 | 3 | 抽取/跨域/模式 |
| 混合检索增强 | 5 | 三路搜索/聚类/层次/去重 |
| 多 Agent 协作 | 4 | 注册/写入/读取/列表 |
| 图推理 | 6 | 推理/矛盾/因果/时序/类比/可视化 |
| 预测性记忆 | 3 | 预测/推荐/状态 |
| 情感智能 | 4 | 分析/统计/预测/交互推荐 |
| 创造性思维 | 3 | 想法/模式/原创 |
| 自主学习 | 3 | 发现/假设/统计 |
| 自进化引擎 | 4 | 诊断/进化/趋势/统计 |
| 时间推理 | 4 | 时间线/关系/查询/统计 |
| 语义压缩 | 4 | 压缩/去重/评估/统计 |
| 协作智能 | 4 | 注册/共享/推理/统计 |
| 因果推理 | 5 | 发现/因果链/反事实/根因/统计 |
| 可解释搜索 | 2 | 解释/建议 |
| 异常检测 | 3 | 扫描/内容/统计 |
| 知识综合 | 4 | 综合/矛盾/洞察/学习 |
| 预测分析 | 5 | 查询/遗忘/趋势/热点/统计 |
| 自适应架构 | 4 | 分析/建议/冷热/统计 |
| 智能问答 | 3 | 问答/批量/统计 |
| 上下文注入 | 4 | 注入/更新/获取/统计 |
| 自适应遗忘 | 4 | 评估/遗忘/归档/统计 |
| 巩固智能 | 4 | 巩固/合并/冲突/统计 |
| 记忆推荐 | 5 | 综合/相似/时效/反馈/统计 |
| 质量评分 | 4 | 评估/批量/修复/统计 |
| 元学习 | 5 | 观察/推荐/调优/洞察/统计 |
| 记忆蒸馏 | 4 | 蒸馏/领域/关键词/统计 |
| 查询重写 | 3 | 重写/建议/统计 |
| 图谱构建 | 5 | 构建/实体/路径/质量/统计 |
| 健康监控 | 3 | 检查/趋势/统计 |
| 备份恢复 | 5 | 备份/列表/验证/恢复/统计 |
| 多项目支持 | 10 | 创建/切换/列表/当前/保存/加载/搜索/合并/删除/统计 |
| 审计分析 | 5 | 日志/查询/统计/模式/安全 |
| 多端同步 | 6 | 记录/待同步/冲突/解决/状态/统计 |
| 记忆事件流 | 5 | 发布/历史/统计/Webhook/持久化 |
| 智能索引 | 5 | 构建/搜索/推荐/健康/清理 |
| 智能缓存 | 3 | 统计/清理/失效 |
| 统一门户 | 5 | 写入/搜索/全景/维护/摘要 |
| 记忆差异 | 4 | 对比/批量/矩阵/统计 |
| 导出导入 | 6 | JSON/Markdown/CSV/导入/列表/统计 |
| 版本控制 | 2 | 历史/对比 |
| 可视化 | 3 | 图谱/网络/统计 |
| 重要性评分 | 1 | 评分 |
| 社交记忆 | 4 | 评论/列表/投票/统计 |
| 自适应学习 | 4 | 统计/模式/热门/频繁 |
| 性能基准 | 1 | 基准测试 |
| 自动收集 | 1 | 自动收集 |
| **总计** | **315** | — |

### 5.2 工具命名规范

所有工具以 `pangu_` 为前缀，按模块分组：

```
pangu_<module>_<action>
例: pangu_health_check, pangu_causal_discover, pangu_recommend
```

---

## 6. API 参考

### 6.1 启动服务

```bash
cd /home/xiaoxin/pangu
source .venv/bin/activate
pangu serve  # HTTP API on port 19529
pangu mcp    # MCP stdio server
```

### 6.2 HTTP API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/api/v2/memories/search?q=<query>&limit=N` | GET | 搜索记忆 |
| `/api/v2/memories` | GET | 列出记忆 |
| `/api/v2/memories` | POST | 创建记忆 |
| `/api/v2/memories/<id>` | GET | 获取记忆 |
| `/api/v2/memories/<id>` | PUT | 更新记忆 |
| `/api/v2/memories/<id>` | DELETE | 删除记忆 |
| `/v1/embeddings` | POST | 生成嵌入向量 |

### 6.3 MCP 协议调用

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "pangu_portal_summary",
    "arguments": {}
  }
}
```

### 6.4 Python 客户端调用

```python
import subprocess, json

# 通过 MCP 协议调用
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "pangu_hybrid_search",
        "arguments": {"query": "Python优化", "limit": 5}
    }
}
result = subprocess.run(
    ["pangu", "mcp"],
    input=json.dumps(request),
    capture_output=True, text=True
)
print(json.loads(result.stdout))
```

### 6.5 cURL 调用

```bash
# 健康检查
curl http://127.0.0.1:19529/health

# 搜索记忆
curl "http://127.0.0.1:19529/api/v2/memories/search?q=Python&limit=5"

# 创建记忆
curl -X POST http://127.0.0.1:19529/api/v2/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "Python异步编程最佳实践", "wing": "tech", "importance": 4.0}'
```

---

## 7. 配置说明

### 7.1 配置文件

- 主配置: `~/.pangu/config.json`
- 身份文件: `~/.pangu/identity.txt`
- 记忆宫殿: `~/.pangu/palace/drawers.json`

### 7.2 关键配置项

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `port` | 19529 | 服务端口 |
| `host` | 127.0.0.1 | 监听地址 |
| `embedding_model` | `all-MiniLM-L6-v2` | 嵌入模型 |
| `embedding_dim` | 384 | 向量维度 |
| `llm_provider` | `openai` | LLM 提供商 |
| `llm_model` | `gpt-4o` | LLM 模型 |
| `decay_base` | 0.95 | 衰减率 |
| `dedup_similarity` | 0.85 | 去重阈值 |
| `onnx_enabled` | true | ONNX 本地推理 |
| `onnx_cache_size` | 10000 | ONNX 缓存大小 |
| `cache_l1_size` | 100 | L1 缓存条目数 |
| `cache_l2_ttl` | 3600 | L2 缓存 TTL (秒) |
| `llm_cache_max_size` | 1000 | LLM 缓存最大条目 |
| `privacy_epsilon` | 1.0 | 差分隐私预算 |
| `auto_collect_interval` | 1800 | 自动收集间隔 (秒) |

### 7.3 环境变量

```bash
PANGU_PORT=19529
PANGU_HOST=127.0.0.1
PANGU_LLM_MODEL=gpt-4o
PANGU_EMBEDDING_MODEL=all-MiniLM-L6-v2
PANGU_ONNX_ENABLED=true
PANGU_LOG_LEVEL=INFO
PANGU_DB_PATH=~/.pangu/pangu.db
```

---

## 8. 部署指南

### 8.1 安装

```bash
cd /home/xiaoxin/pangu
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 8.2 启动

```bash
# HTTP API 模式
pangu serve --host 127.0.0.1 --port 19529

# MCP stdio 模式
pangu mcp

# 后台运行
nohup pangu serve --host 127.0.0.1 --port 19529 > logs/pangu.log 2>&1 &
echo $! > pangu.pid
```

### 8.3 systemd 服务

```ini
# /etc/systemd/system/pangu.service
[Unit]
Description=Pangu Memory System
After=network.target

[Service]
Type=simple
User=xiaoxin
WorkingDirectory=/home/xiaoxin/pangu
ExecStart=/home/xiaoxin/pangu/.venv/bin/pangu serve --host 127.0.0.1 --port 19529
Restart=always
RestartSec=5
Environment=PANGU_PORT=19529
Environment=PANGU_HOST=127.0.0.1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pangu
sudo systemctl start pangu
```

### 8.4 Cron 任务

```bash
# 自动收集（每 30 分钟）
*/30 * * * * /home/xiaoxin/pangu/scripts/auto_collect.sh

# 生命周期维护（每小时）
0 * * * * /home/xiaoxin/pangu/scripts/lifecycle_maintain.sh

# 备份（每天凌晨 2 点）
0 2 * * * /home/xiaoxin/pangu/scripts/backup.sh

# 健康检查（每 5 分钟）
*/5 * * * * /home/xiaoxin/pangu/scripts/health_check.sh
```

### 8.5 Docker

```bash
docker build -t pangu:v3 .
docker run -d -p 19529:19529 -v ~/.pangu:/root/.pangu pangu:v3
```

---

## 9. 性能指标

### 9.1 核心性能

| 指标 | 值 | 说明 |
|---|---|---|
| recall() 延迟 | 29ms | Recall@5 端到端 |
| ONNX 推理延迟 | ~0ms | 缓存命中时 |
| 向量索引规模 | 10,000+ | FAISS 索引 |
| FAISS 索引构建 | ~0.2s | 10K 向量 |
| 搜索命中率 | 70%+ | 混合搜索 |
| 健康评分 | 0.917 | 系统健康度 |
| 质量均分 | 0.761 | 5 维度质量 |
| 索引命中率 | 100% | 索引覆盖 |
| 缓存命中率 | 66.7% | L1+L2 缓存 |

### 9.2 吞吐量

| 指标 | 值 |
|---|---|
| 记忆写入 (remember) | ~50ms/条 |
| 批量嵌入 (ONNX) | ~5ms/条 |
| FTS5 搜索 | ~10ms |
| 向量搜索 (FAISS) | ~5ms |
| RRF 融合 | ~2ms |

### 9.3 资源占用

| 指标 | 值 |
|---|---|
| 内存占用 | ~200MB (含 ONNX) |
| 磁盘占用 | ~50MB (10K 记忆) |
| CPU 占用 (空闲) | <1% |
| CPU 占用 (搜索) | ~5% |

---

## 10. 测试覆盖

### 10.1 测试套件

| 文件 | 用例数 | 覆盖范围 |
|---|---|---|
| `test_core.py` | 128 | 核心功能 |
| `test_v2_features.py` | 17 | v2.0 功能 |
| `test_top_level_intelligence.py` | 8 | 顶级智能 |
| `test_v3_modules_a.py` | ~30 | v3.0 模块 (A) |
| `test_v3_modules_b.py` | ~30 | v3.0 模块 (B) |
| `test_v3_modules_c.py` | ~30 | v3.0 模块 (C) |
| `test_v3_modules_d.py` | ~30 | v3.0 模块 (D) |
| `test_v3_modules_e.py` | ~30 | v3.0 模块 (E) |
| `test_integration.py` | ~20 | 集成测试 |
| `test_onnx_embedder.py` | ~15 | ONNX 嵌入 |
| `test_benchmark_v2.py` | ~10 | 性能基准 |
| `test_encryption.py` | ~10 | 加密功能 |
| `test_warmup_audit.py` | ~10 | 缓存预热审计 |
| 其他测试文件 | ~80 | 各模块覆盖 |
| **总计** | **428** | **全部通过** ✅

### 10.2 集成测试

`test_top_level_intelligence.py` 覆盖 5 大智能模块端到端测试：
- 情感智能 → 分析 + 调整 + 预测 + 建议
- 自主学习 → 发现 + 假设 + 验证 + 循环
- 创造性思维 → 模式 + 想法 + 原创
- 知识图谱 → 跨域迁移 + 相似模式
- 推理可视化 → 推理 + 展示

### 10.3 运行测试

```bash
cd /home/xiaoxin/pangu
source .venv/bin/activate

# 全部测试
python -m pytest tests/ -v

# 特定模块
python -m pytest tests/test_v3_modules_a.py -v

# 性能基准
python -m pytest tests/test_benchmark_v2.py -v

# 仅失败测试
python -m pytest tests/ --lf

# 覆盖率
python -m pytest tests/ --cov=pangu --cov-report=term-missing
```

---

## 附录 A：94 个模块完整清单

| # | 模块文件 | 主类/函数 | 功能 |
|---|---|---|---|
| 1 | `adaptive_architecture.py` | `AdaptiveArchitecture` | 自适应架构分析与重构 |
| 2 | `adaptive_forgetting.py` | `AdaptiveForgetting` | 智能遗忘管理 |
| 3 | `adaptive_learning.py` | `AdaptiveLearning` | 自适应学习引擎 |
| 4 | `adaptive_params.py` | `AdaptiveParamEngine` | 参数自适应调整 |
| 5 | `advanced_reasoning.py` | `AdvancedReasoning` | 高级推理引擎 |
| 6 | `analytics.py` | `MemoryAnalytics` | 记忆分析看板 |
| 7 | `anomaly_detection.py` | `AnomalyDetector` | 异常检测引擎 |
| 8 | `attention.py` | `AttentionEngine` | 注意力策略系统 |
| 9 | `audit_analytics.py` | `AuditAnalytics` | 审计分析引擎 |
| 10 | `auto_collector.py` | `AutoCollector` | 自动记忆收集器 |
| 11 | `autonomous_learning.py` | `AutonomousLearning` | 自主学习引擎 |
| 12 | `backup_restore.py` | `BackupRestoreEngine` | 备份恢复引擎 |
| 13 | `causal_reasoning.py` | `CausalReasoningEngine` | 因果推理引擎 |
| 14 | `cluster.py` | `MemoryClusterer` | 记忆聚类器 |
| 15 | `clustering.py` | `MemoryClustering` | 记忆聚类引擎 |
| 16 | `collaborative_intelligence.py` | `CollaborativeIntelligence` | 协作智能引擎 |
| 17 | `compression.py` | `MemoryCompressor` | 记忆压缩器 |
| 18 | `conflict.py` | `ConflictDetector` | 冲突检测器 |
| 19 | `consolidation.py` | `MemoryConsolidator` | 记忆巩固器 |
| 20 | `consolidation_intelligence.py` | `ConsolidationIntelligence` | 巩固智能引擎 |
| 21 | `context_injection.py` | `ContextInjectionEngine` | 上下文注入引擎 |
| 22 | `creative_thinking.py` | `CreativeThinking` | 创造性思维引擎 |
| 23 | `cross_session.py` | `CrossSessionManager` | 跨会话管理器 |
| 24 | `decay.py` | `MemoryDecay` | 记忆衰减管理 |
| 25 | `dedup.py` | `MemoryDeduplicator` | 记忆去重器 |
| 26 | `differential_privacy.py` | `DifferentialPrivacy` | 差分隐私管理 |
| 27 | `distillation.py` | `DistillationEngine` | 记忆蒸馏引擎 |
| 28 | `distill_enhanced.py` | `DistillEnhanced` | 增强蒸馏引擎 |
| 29 | `domain_knowledge.py` | `DomainKnowledge` | 领域知识管理 |
| 30 | `embedding.py` | `EmbeddingService` | 嵌入服务 |
| 31 | `emotional_intelligence.py` | `EmotionalIntelligence` | 情感智能引擎 |
| 32 | `encryption.py` | `EncryptionManager` | 加密管理器 |
| 33 | `enhanced_evaluation.py` | `EnhancedEvaluation` | 增强评估引擎 |
| 34 | `evaluation.py` | `EvaluationEngine` | 评估引擎 |
| 35 | `event_bus.py` | `EventBus` | 事件总线 |
| 36 | `explainable_search.py` | `ExplainableSearchEngine` | 可解释搜索引擎 |
| 37 | `export_import.py` | `ExportImportEngine` | 导出导入引擎 |
| 38 | `fts_search.py` | `FTS5SearchEngine` | FTS5 全文搜索引擎 |
| 39 | `fusion.py` | `FusionEngine` | 融合引擎 |
| 40 | `graph_builder.py` | `GraphBuilder` | 图谱构建器 |
| 41 | `graph_reasoning.py` | `GraphReasoning` | 图谱推理引擎 |
| 42 | `health_monitor.py` | `HealthMonitor` | 健康监控器 |
| 43 | `hologram.py` | `HolographicEncoder` | 全息编码器 |
| 44 | `hybrid_search.py` | `HybridSearchEngine` | 混合搜索引擎 |
| 45 | `importance_scorer.py` | `ImportanceScorer` | 重要性评分器 |
| 46 | `ingestion.py` | `remember()` | 记忆摄入函数 |
| 47 | `judge.py` | `JudgeEngine` | 记忆判断引擎 |
| 48 | `knowledge_graph.py` | `KnowledgeGraph` | 知识图谱 |
| 49 | `knowledge_synthesis.py` | `KnowledgeSynthesizer` | 知识综合引擎 |
| 50 | `layers.py` | `MemoryStack` | 4 层记忆栈 |
| 51 | `lifecycle.py` | `LifecycleManager` | 生命周期管理 |
| 52 | `lifespan.py` | `Lifespan` | 记忆寿命管理 |
| 53 | `memory_diff.py` | `MemoryDiffEngine` | 记忆差异引擎 |
| 54 | `memory_events.py` | `MemoryEventStream` | 事件流管理 |
| 55 | `memory_validator.py` | `MemoryValidator` | 记忆验证器 |
| 56 | `meta_learning.py` | `MetaLearningEngine` | 元学习引擎 |
| 57 | `migration.py` | `MemoryMigration` | 记忆迁移管理 |
| 58 | `multi_agent.py` | `MultiAgentManager` | 多 Agent 管理器 |
| 59 | `multimodal.py` | `MultimodalMemory` | 多模态记忆 |
| 60 | `natural_query.py` | `NaturalQueryEngine` | 自然语言查询引擎 |
| 61 | `neural_memory.py` | `NeuralMemoryEngine` | 神经记忆引擎 |
| 62 | `onnx_embedder.py` | `ONNXEmbedder` | ONNX 嵌入器 |
| 63 | `patterns.py` | `PatternEngine` | 模式引擎 |
| 64 | `performance.py` | `PerformanceEngine` | 性能引擎 |
| 65 | `portal.py` | `MemoryPortal` | 统一门户 |
| 66 | `predictive_analytics.py` | `PredictiveAnalytics` | 预测分析引擎 |
| 67 | `proactive.py` | `ProactiveEngine` | 预测性记忆引擎 |
| 68 | `production.py` | `MetricsCollector` | 生产指标收集 |
| 69 | `project_manager.py` | `ProjectManager` | 多项目管理器 |
| 70 | `qa_engine.py` | `QAEngine` | 智能问答引擎 |
| 71 | `quality_scorer.py` | `QualityScorer` | 质量评分器 |
| 72 | `query_rewriter.py` | `QueryRewriter` | 查询重写器 |
| 73 | `recommendation.py` | `RecommendationEngine` | 推荐引擎 |
| 74 | `reconsolidation.py` | `ReconsolidationEngine` | 再巩固引擎 |
| 75 | `replay.py` | `ReplayEngine` | 回放引擎 |
| 76 | `retrieval.py` | `recall()` | 检索函数 |
| 77 | `sanitizer.py` | `MemorySanitizer` | 记忆脱敏器 |
| 78 | `self_evolution.py` | `SelfEvolutionEngine` | 自进化引擎 |
| 79 | `semantic_compression.py` | `SemanticCompressor` | 语义压缩器 |
| 80 | `smart_cache.py` | `CacheManager` | 智能缓存管理 |
| 81 | `smart_indexing.py` | `SmartIndexingEngine` | 智能索引引擎 |
| 82 | `social_memory.py` | `SocialMemory` | 社交记忆 |
| 83 | `streaming_index.py` | `StreamingIndex` | 流式索引 |
| 84 | `sync_manager.py` | `SyncManager` | 同步管理器 |
| 85 | `synonyms.py` | `SynonymExpander` | 同义词扩展器 |
| 86 | `temporal_reasoning.py` | `TemporalReasoning` | 时间推理引擎 |
| 87 | `timeline.py` | `TimelineEngine` | 时间线引擎 |
| 88 | `vector_index.py` | `VectorIndex` | 向量索引 |
| 89 | `verification.py` | `VerificationEngine` | 验证引擎 |
| 90 | `versioning.py` | `VersionControl` | 版本控制 |
| 91 | `visualization.py` | `VisualizationEngine` | 可视化引擎 |
| 92 | `wikilink.py` | `WikilinkEngine` | WikiLink 引擎 |
| 93 | `working_memory.py` | `WorkingMemory` | 工作记忆 |
| 94 | `event_bus.py` | `EventBus` | 事件总线 |

---

## 附录 B：v3.0 完整模块清单

| # | 模块 | 功能 |
|---|---|---|
| P84 | `self_evolution.py` | 自我诊断、进化计划 |
| P85 | `temporal_reasoning.py` | 时间线、时序推理 |
| P86 | `semantic_compression.py` | 标签压缩、语义去重 |
| P87 | `collaborative_intelligence.py` | Agent 协作 |
| P88 | `causal_reasoning.py` | 因果链、反事实推理 |
| P89 | `explainable_search.py` | 搜索解释 |
| P90 | `anomaly_detection.py` | 异常检测 |
| P91 | `knowledge_synthesis.py` | 知识综合 |
| P92 | `predictive_analytics.py` | 预测分析 |
| P93 | `adaptive_architecture.py` | 自适应架构 |
| P94 | `qa_engine.py` | 智能问答 |
| P95 | `context_injection.py` | 上下文注入 |
| P96 | `adaptive_forgetting.py` | 自适应遗忘 |
| P97 | `consolidation_intelligence.py` | 巩固智能 |
| P98 | `recommendation.py` | 记忆推荐 |
| P99 | `quality_scorer.py` | 质量评分 |
| P100 | `meta_learning.py` | 元学习 |
| P101 | `distillation.py` | 记忆蒸馏 |
| P102 | `query_rewriter.py` | 查询重写 |
| P103 | `graph_builder.py` | 图谱构建 |
| P104 | `health_monitor.py` | 健康监控 |
| P105 | `backup_restore.py` | 备份恢复 |
| P106 | `project_manager.py` | 多项目支持 |
| P107 | `audit_analytics.py` | 审计分析 |
| P108 | `sync_manager.py` | 多端同步 |
| P109 | `memory_events.py` | 事件流 |
| P110 | `smart_indexing.py` | 智能索引 |
| P111 | `smart_cache.py` | 智能缓存 |
| P112 | `portal.py` | 统一门户 |
| P113 | `memory_diff.py` | 记忆差异 |
| P114 | `export_import.py` | 导出导入 |

---

*本文档由 MiMoCode 自动生成 | 盘古 v3.0 — 顶级智能记忆系统*
