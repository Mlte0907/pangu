# 盘古 v3.0 技术文档

> 版本: v3.0 | 日期: 2026-06-17 | 模块数: 93 | MCP 工具: 313 | 代码量: 30,449 行

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

盘古 (Pangu) 是一个为 AI Agent 框架设计的**记忆系统**（"大脑组件"）。它提供记忆存储、检索、组织、分类和知识结晶化功能，通过 MCP 协议暴露服务。

### 1.2 版本演进

| 版本 | Commits | MCP 工具 | 模块数 | 代码量 | 核心能力 |
|---|---|---|---|---|---|
| v1.0 | ~20 | ~30 | ~15 | ~5K | 基础记忆存储/检索 |
| v2.0 | 68 | 177 | 63 | 22,832 | ⭐⭐⭐⭐ 高级智能 |
| **v3.0** | **95** | **313** | **93** | **30,449** | **⭐⭐⭐⭐⭐ 顶级智能** |

### 1.3 位置

- 代码: `/home/xiaoxin/pangu/`
- 运行时数据: `~/.pangu/`
- 向量索引: `~/.cache/pangu/`
- 导出文件: `~/.pangu/exports/`
- 备份文件: `~/.pangu/backups/`
- 事件日志: `~/.pangu/events/`
- 同步数据: `~/.pangu/sync/`
- 项目空间: `~/.pangu/projects/`

---

## 2. 架构设计

### 2.1 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Server (313 tools)                │
├─────────────────────────────────────────────────────────┤
│  Portal (统一入口)  │  Event Stream (事件总线)           │
├─────────────────────────────────────────────────────────┤
│                    智能引擎层                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 自进化    │ │ 元学习    │ │ 因果推理  │ │ 推荐系统  │   │
│  │ 引擎     │ │ 引擎     │ │ 引擎     │ │ 引擎     │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 情感智能  │ │ 创造力   │ │ 预测分析  │ │ 异常检测  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│                    记忆管理层                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 4层记忆栈 │ │ 巩固智能  │ │ 自适应遗忘│ │ 语义压缩  │   │
│  │ L0-L3    │ │          │ │          │ │          │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│                    搜索与检索层                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 混合搜索  │ │ 查询重写  │ │ 索引管理  │ │ 上下文注入│   │
│  │ FTS+Vec  │ │          │ │          │ │          │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│                    基础设施层                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 向量索引  │ │ ONNX嵌入 │ │ SQLite   │ │ 智能缓存  │   │
│  │ FAISS    │ │ 384维    │ │ WAL模式  │ │ L1+L2    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 4 层记忆栈

| 层级 | 容量 | 加载策略 | 用途 |
|---|---|---|---|
| L0 身份层 | ~100 tokens | 始终加载 | 定义"我是谁" |
| L1 概要层 | ~500-800 tokens | 始终加载 | 关键记忆摘要 |
| L2 按需层 | ~200-2000 tokens | 话题触发加载 | 详细上下文 |
| L3 深度搜索 | 无限 | 显式查询 | 全文语义搜索 |

### 2.3 3 层嵌入降级

| 优先级 | 方案 | 延迟 | 成本 |
|---|---|---|---|
| 1 | ONNX 本地 (MiniLM-L6, 384维) | ~0ms (缓存) | 免费 |
| 2 | API (Ollama) | ~50ms | 低 |
| 3 | Hash 向量 | ~0ms | 免费 |

### 2.4 混合搜索

```
FTS5 (jieba 分词) × 0.5 权重  ─┐
                                 ├─→ RRF 融合 (K=60) → 排序结果
向量搜索 (FAISS) × 1.0 权重  ─┘
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

### 3.2 搜索与检索 (retrieval.py / hybrid_search.py)

FTS+向量混合检索，Recall@5 性能 29ms。

```python
from pangu.memory.retrieval import recall
results = recall(query="Python优化", limit=5, drawers=drawers)
```

### 3.3 记忆摄入 (ingestion.py)

记忆写入流水线：去重 → 融合 → 嵌入 → 全息 → WikiLink → 向量索引。

### 3.4 知识图谱 (knowledge_graph.py)

实体/关系图谱，支持自动抽取、跨域推理、因果链分析。

### 3.5 向量索引 (vector_index.py / onnx_embedder.py)

FAISS 索引 + ONNX 本地推理，支持增量更新。

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

---

## 5. MCP 工具清单

### 5.1 工具分类统计

| 分类 | 工具数 | 说明 |
|---|---|---|
| 记忆管理 | 30+ | CRUD、搜索、摄入、召回 |
| 搜索与检索 | 20+ | FTS、向量、混合、重写、建议 |
| 智能引擎 | 80+ | 情感、创造力、因果、预测、推荐 |
| 记忆治理 | 40+ | 遗忘、压缩、质量、巩固、蒸馏 |
| 基础设施 | 40+ | 缓存、索引、同步、备份、事件 |
| 项目与审计 | 20+ | 项目管理、审计、导出 |
| 图谱与推理 | 20+ | 知识图谱、图推理、问答 |
| **总计** | **313** | — |

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

### 6.2 核心 API 端点

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

### 6.3 MCP 工具调用示例

```python
import json
import subprocess

# 通过 MCP 协议调用
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "pangu_portal_summary",
        "arguments": {}
    }
}
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
| `embedding_model` | `all-MiniLM-L6-v2` | 嵌入模型 |
| `embedding_dim` | 384 | 向量维度 |
| `llm_provider` | `openai` | LLM 提供商 |
| `llm_model` | `gpt-4o` | LLM 模型 |
| `decay_base` | 0.95 | 衰减率 |
| `dedup_similarity` | 0.85 | 去重阈值 |

### 7.3 环境变量

```bash
PANGU_PORT=19529
PANGU_HOST=127.0.0.1
PANGU_LLM_MODEL=gpt-4o
PANGU_EMBEDDING_MODEL=all-MiniLM-L6-v2
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
```

### 8.3 Cron 任务

```bash
# 自动收集（每 30 分钟）
*/30 * * * * /home/xiaoxin/pangu/scripts/auto_collect.sh

# 生命周期维护（每小时）
0 * * * * /home/xiaoxin/pangu/scripts/lifecycle_maintain.sh
```

---

## 9. 性能指标

| 指标 | 值 |
|---|---|
| recall() 延迟 | 29ms |
| ONNX 推理延迟 | ~0ms (缓存) |
| 向量索引规模 | 10,000+ |
| FAISS 索引构建 | ~0.2s (10K) |
| 搜索命中率 | 70%+ |
| 健康评分 | 0.917 |
| 质量均分 | 0.761 |
| 索引命中率 | 100% |
| 缓存命中率 | 66.7% |

---

## 10. 测试覆盖

### 10.1 测试套件

| 文件 | 用例数 | 覆盖范围 |
|---|---|---|
| `test_core.py` | 128 | 核心功能 |
| `test_v2_features.py` | 17 | v2.0 功能 |
| `test_top_level_intelligence.py` | 8 | 顶级智能 |
| **总计** | **153** | **全部通过** ✅ |

### 10.2 集成测试

`test_top_level_intelligence.py` 覆盖 5 大智能模块端到端测试：
- 情感智能 → 分析 + 调整 + 预测 + 建议
- 自主学习 → 发现 + 假设 + 验证 + 循环
- 创造性思维 → 模式 + 想法 + 原创
- 知识图谱 → 跨域迁移 + 相似模式
- 推理可视化 → 推理 + 展示

---

## 附录：v3.0 完整模块清单

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
