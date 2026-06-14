# 盘古 v2.0 — 专业记忆系统

> 智能体的"大脑"组件，专注解决 Agent 框架中普遍存在的记忆功能短板。

盘古不是一个完整的 Agent 框架，而是专注于记忆相关的核心功能：存储、检索、组织、分类、知识结晶和类人特征的记忆智能体系统。

## 核心定位

- **大脑组件**: 作为智能系统的记忆核心，通过 MCP 协议为上层 Agent 提供记忆服务
- **不做手脚**: 不包含执行层功能（问答、对话、任务执行等）
- **不造轮子**: 不重复开发已有成熟解决方案的基础功能

## v2.0 新增特性

| 特性 | 说明 |
|:---|:---|
| **神经记忆系统** | 海马体-新皮层双系统，4 种记忆类型 × 5 种状态，个性化遗忘曲线 |
| **记忆融合自动化** | 同主题 ≥3 条记忆自动融合为结构化理解 |
| **冲突检测** | 新记忆写入时自动检测矛盾，标记 memory_status |
| **重要性自适应** | 5 种反馈信号（recall_success/miss, vote_up/down, verified）动态调整 |
| **跨会话整合** | 向量相似度 + KG 关系自动发现跨会话关联 |
| **自动压缩** | 长记忆自动提取关键句压缩，保留核心信息 |
| **记忆验证** | 时效性检查（>90天事实类→stale），标记过时/矛盾记忆 |
| **KG 自动提取** | 从记忆中自动识别技术/系统/Agent 实体和关系 |
| **混合检索** | FTS + 向量 + KG 三路召回，RRF 融合排序 |
| **FAISS 加速** | ≥1000 条自动切换 FAISS IVFFlat，20000 条仅 0.22ms |

## v1.0.0 特性

| 特性 | 说明 |
|:---|:---|
| **E2E 加密** | Fernet (AES-128-CBC + HMAC-SHA256) 记忆内容加密存储 |
| **多租户隔离** | agent_id 命名空间隔离，recall() 和 FTS 搜索支持 agent_id 过滤 |
| **OpenTelemetry** | OTLP/Console 分布式追踪，@traced 装饰器 |
| **Prometheus 扩展** | 86 个 pangu_* 指标（含 KG、搜索、向量索引） |
| **模块集成** | 聚类（6 clusters）、模式发现（25 patterns）、巩固、去重全链路验证 |
| **安全加固** | Bandit HIGH: 22→0，host 默认 127.0.0.1，MD5→blake2b |
| **性能基线** | ONNX 0.002ms，向量搜索 0.063ms，并发 5963 ops/s |

## 架构

```
上层 Agent 框架 (Claude Code / Gemini CLI / 自研 Agent)
        │
        │ MCP 协议 / REST API
        ▼
┌──────────────────────────────────────────────────────┐
│                  盘古 v2.0 记忆系统                    │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │ 宫殿结构  │  │ Wiki 引擎 │  │ 知识图谱  │  │ 加密 │ │
│  │ Wing/Room │  │ 自动生成  │  │ KG 自提取 │  │ 模块 │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘ │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │ 神经记忆  │  │ 4层记忆栈 │  │ 混合检索  │  │ OTel │ │
│  │ 海马/新皮 │  │ L0-L3    │  │ FTS+Vec+KG│  │ 追踪 │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘ │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │ 融合抽象  │  │ 冲突检测  │  │ 跨会话整合│  │Prom. │ │
│  │ 自动融合  │  │ 自动标记  │  │ 关联发现  │  │86指标│ │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘ │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ 压缩摘要  │  │ 记忆验证  │  │ 重要性反馈│           │
│  │ 关键句提取│  │ 时效性检查│  │ 5种信号   │           │
│  └──────────┘  └──────────┘  └──────────┘           │
└──────────────────────────────────────────────────────┘
```

## 核心特性

### 1. 宫殿记忆结构
- **Wing (空间)**: 顶层隔离，如"工作"、"个人"、"学习"
- **Room (页面)**: Wing 下的子分类
- **Drawer (记忆片段)**: 最小记忆单元
- **Hall (殿堂)**: 跨 Wing 的概念分类（事实、事件、发现、偏好、建议、概念、关系）
- **Tunnel (隧道)**: 跨 Wing 的记忆连接

### 2. 4 层记忆栈
| 层级 | 说明 | Token 预算 | 加载策略 |
|:---|:---|:---|:---|
| L0 | 身份层 | ~100 | 始终加载 |
| L1 | 概要层 | ~500-800 | 始终加载 |
| L2 | 按需层 | ~200-500 | 话题触发加载 |
| L3 | 深度搜索 | 无限 | 显式查询 |

### 3. 类人记忆特征
- **遗忘曲线**: 基于艾宾浩斯遗忘曲线的记忆衰减，不重要的记忆随时间淡化
- **记忆巩固**: 频繁访问的记忆自动强化，间隔重复机制
- **记忆压缩**: 旧记忆自动浓缩为精简摘要
- **关联发现**: LMM 自动检测记忆间的隐藏关联，聚类分析
- **动态重要性**: 综合时间衰减、访问频率、标签密度、内容长度计算

### 4. 知识结晶
- LMM 驱动的 Wiki 页面自动生成
- 页面智能关联与反向链接
- 知识图谱导出

### 5. 多 LLM 后端支持
| 提供商 | 配置值 | 说明 |
|:---|:---|:---|
| OpenAI | `openai` | 默认，需 API Key |
| Anthropic | `anthropic` | 需 API Key |
| Ollama | `ollama` | 本地部署，无需 Key |
| OpenRouter | `openrouter` | 多模型聚合 |
| DeepSeek | `deepseek` | 国产模型 |
| 智谱 GLM | `zhipu` | 国产模型 |
| 通义千问 | `qwen` | 国产模型 |

### 6. ONNX 本地加速嵌入 ⚡

**真实语义向量，本地 CPU 推理，零 API 成本。**

盘古采用三级降级嵌入架构，自动选择最优路径：

```
外部 LLM API (高质量)
   ↓ 失败
ONNX 本地推理 (MiniLM-L6 量化) ⚡ 推荐
   ↓ 失败
Hash 向量 (确定性降级)
```

#### 性能 (ARM aarch64 8核实测)

| 指标 | 值 |
|:---|:---|
| 单条嵌入 | **0.002ms** (缓存命中) |
| 向量搜索 (25v) | **0.063ms** median |
| FTS 搜索 (25d) | **0.006ms** median |
| 并发吞吐 | **5963 ops/s** |

### 7. LLM 响应缓存 ⚡

**双级缓存架构：内存 LRU + 持久化 SQLite，重启不丢，命中率透明可观测。**

### 8. E2E 加密 (v1.0.0)

**Fernet (AES-128-CBC + HMAC-SHA256) 记忆内容加密存储。**

- 首次启动自动生成密钥 (`~/.pangu/.encryption_key`)
- 环境变量 `PANGU_ENCRYPTION_KEY` 覆盖
- 写入时自动加密，读取时自动解密
- 向量嵌入基于明文（保证搜索可用）

### 9. 多租户隔离 (v1.0.0)

**agent_id 命名空间隔离，不同 Agent 的记忆互不可见。**

```python
from pangu.memory.retrieval import recall

# 只返回 agent_xuannv 的记忆
results = recall("任务", agent_id="xuannv", drawers=drawers)

# FTS 搜索也支持
from pangu.memory.fts_search import FTS5SearchEngine
r = engine.search("部署", drawers, agent_id="xuannv")
```

### 10. OpenTelemetry 追踪 (v1.0.0)

**分布式追踪，支持 OTLP 导出到 Jaeger/Zipkin。**

```bash
# 配置 OTLP 端点
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# 或开启 Console 导出（调试）
export OTEL_CONSOLE_EXPORT=1
```

```python
from pangu.observability.tracing import traced

@traced("memory.remember")
def remember(...):
    ...
```

## 性能优化引擎

### 1. 性能优化引擎 (NEW) ⚡

**四大优化组件，大幅降低内存开销与搜索延迟。**

#### HNSW 向量索引

基于论文 "Hierarchical Navigable Small World graphs" 的近似最近邻索引，替代暴力搜索：

- 多层导航结构：高层稀疏长连接快速定位，低层稠密短连接精确搜索
- numpy 向量化批量计算，避免逐条循环
- 可配置 M（连接数）、efConstruction（构建精度）、efSearch（搜索精度）
- 增量添加/删除，自动维护图结构

#### ARC 自适应替换缓存

替代简单 LRU，动态平衡热点/冷数据：

- 双列表结构：T1（最近访问）+ T2（频繁访问）
- Ghost List 自适应调节 p 值，自动适应扫描/点查混合负载
- 命中率统计与可观测性
- 线程安全，无需手动调优

#### 对象池复用

减少 Drawer 等高频创建对象的 GC 压力：

- 池化 Drawer 对象，归还时自动重置状态
- 池容量可配置，超额自动丢弃
- 复用率统计，观察 GC 优化效果

#### 批量操作优化器

- 写入攒批：缓冲区满或定时触发批量写入，减少 I/O 次数
- 向量批量编码：利用 ONNX 批量推理加速，比逐条快 3-5 倍
- RRF 融合排序：多路搜索结果合并为一次批量搜索

#### Python API

```python
from pangu.memory.performance import PerformanceOptimizer

optimizer = PerformanceOptimizer(dim=384)

# HNSW 索引
optimizer.hnsw.add("mem_001", [0.1, 0.2, ...])
results = optimizer.hnsw.search(query_vec, top_k=5)

# ARC 缓存
optimizer.arc_cache.put("key", value)
cached = optimizer.arc_cache.get("key")

# 对象池
pool = optimizer.init_drawer_pool()
obj = pool.acquire()
pool.release(obj)

# 统计
print(optimizer.stats())
```

#### MCP 工具

- `pangu_performance_stats` — 优化器综合统计
- `pangu_hnsw_stats` — HNSW 索引状态
- `pangu_arc_cache_stats` — ARC 缓存命中率与容量
- `pangu_batch_stats` — 批量操作统计

---

### 2. Web Dashboard (NEW)

**可视化管理面板，实时监控记忆系统状态。**

启动方式：

```bash
pangu serve
# 访问 http://127.0.0.1:8866
```

Dashboard 功能：

- **记忆概览**：总记忆数、按 Wing/Room 分布、健康评分
- **衰减监控**：遗忘曲线可视化、衰减分数分布、清除候选预览
- **性能看板**：HNSW 索引大小/层数、ARC 缓存命中率、对象池复用率
- **知识图谱**：实体关系可视化、关联发现展示
- **多 Agent 视图**：Agent 记忆分布、同步事件时间线、冲突检测
- **实时指标**：Prometheus 指标集成，Grafana 大盘兼容

---

### 3. MCP 工具完整列表 (80+ 个)

#### Palace 管理
- `pangu_list_wings` / `pangu_create_wing` / `pangu_delete_wing`
- `pangu_list_rooms` / `pangu_create_room`

#### 记忆操作
- `pangu_add_memory` / `pangu_search_memories`
- `pangu_recall` / `pangu_wake_up`
- `pangu_memory_importance`

#### Wiki 操作
- `pangu_list_wiki_pages` / `pangu_get_wiki_page`
- `pangu_create_wiki_page` / `pangu_auto_generate_wiki`

#### 知识图谱
- `pangu_kg_add_entity` / `pangu_kg_add_relation`
- `pangu_kg_query` / `pangu_kg_neighbors` / `pangu_kg_invalidate`

#### LMM 记忆处理
- `pangu_summarize` / `pangu_classify` / `pangu_insight`

#### 记忆巩固
- `pangu_consolidation_stats` / `pangu_find_forgotten`
- `pangu_compress_memories` / `pangu_detect_associations`

#### 迁移与备份
- `pangu_export` / `pangu_import` / `pangu_backup`
- `pangu_list_backups` / `pangu_restore_backup`

#### 聚类、去重、冲突
- `pangu_cluster_memories` / `pangu_find_related`
- `pangu_find_duplicates` / `pangu_merge_duplicates` / `pangu_similarity_check`
- `pangu_detect_conflicts` / `pangu_check_pair`

#### 分析与时间线
- `pangu_analyze` / `pangu_health_check` / `pangu_anomaly_detect` / `pangu_growth_trend`
- `pangu_build_timeline` / `pangu_find_causal_links` / `pangu_event_chains` / `pangu_timeline_query`

#### 融合、模式、回放
- `pangu_fuse_topic` / `pangu_progressive_summarize` / `pangu_crystallize_knowledge`
- `pangu_discover_patterns` / `pangu_pattern_insights`
- `pangu_timeline_replay` / `pangu_topic_replay` / `pangu_highlight_reel`

#### ONNX 加速嵌入
- `pangu_onnx_embed` / `pangu_onnx_embed_batch`
- `pangu_onnx_similarity` / `pangu_onnx_status`

#### 伏羲移植模块

**FTS5 混合搜索**
- `pangu_fts_search` / `pangu_fts_search_stats`

**全息记忆**
- `pangu_holographic_encode` / `pangu_holographic_search`

**记忆法官**
- `pangu_judge_memory` / `pangu_judge_stats`

**自适应参数**
- `pangu_adaptive_params` / `pangu_adaptive_evaluate`

**工作记忆**
- `pangu_wm_push` / `pangu_wm_get` / `pangu_wm_stats` / `pangu_wm_clear`

**记忆脱敏**
- `pangu_sanitize` / `pangu_sanitize_check`

**再巩固 + 共鸣**
- `pangu_reconsolidate` / `pangu_find_resonance` / `pangu_cross_wing_resonance`

**知识蒸馏增强**
- `pangu_distill_knowledge` / `pangu_distill_causal_chains` / `pangu_distill_graph` / `pangu_distill_stats`

**向量索引**
- `pangu_vector_index_stats` / `pangu_vector_index_build`

**注意力系统**
- `pangu_attention_state` / `pangu_attention_switch` / `pangu_attention_ab_test`

**增强评估**
- `pangu_enhanced_contradictions` / `pangu_trajectory_track` / `pangu_trajectory_compare`

**流式索引**
- `pangu_streaming_index` / `pangu_streaming_stats`

**验证循环**
- `pangu_verify` / `pangu_verify_phase`

**差分隐私**
- `pangu_privacy_stats` / `pangu_privatize_count`

#### 性能优化 (NEW)
- `pangu_performance_stats` — 优化器综合统计
- `pangu_hnsw_stats` — HNSW 索引状态
- `pangu_arc_cache_stats` — ARC 缓存统计
- `pangu_batch_stats` — 批量操作统计

#### 服务器增强
- `pangu_system_health` / `pangu_system_metrics`
- `pangu_config_get` / `pangu_config_set` / `pangu_config_reload`
- `pangu_schema_version` / `pangu_schema_migrations`
- `pangu_autonomous_analyze` / `pangu_api_server_start`

#### 其他
- `pangu_create_tunnel` / `pangu_list_tunnels` / `pangu_find_tunnels`
- `pangu_stats` / `pangu_graph` / `pangu_identity`

---

## 安全 (v1.0.0)

| 检查项 | 结果 |
|:---|:---|
| Bandit HIGH | **0** (从 22 降至 0) |
| Bandit MEDIUM | 10 (非关键) |
| Secret 扫描 | 0 命中 |
| SQL 注入 | 免疫（参数化查询） |
| 路径穿越 | 免疫（404 响应） |
| 依赖 CVE | python-multipart >=0.0.18 |
| E2E 加密 | Fernet AES-128-CBC |

## 测试

### v2.0

```
172 passed, 1 deselected, 1 warning in 1.61s
```

### v1.0.0

```
307 passed, 3 deselected, 1 warning in 7.12s
```

- 核心单元测试: 208/208 ✅
- 集成测试: 45/45 ✅
- 缓存/LLM 测试: 54/54 ✅
- 真实 LLM 测试: 按 API key 可用性跳过

## 性能基线

### v2.0 (FAISS + 预归一化)

| 指标 | 值 | 说明 |
|:---|:---|:---|
| ONNX 嵌入 | 0.0015ms | 本地 CPU 推理，缓存命中 |
| 向量搜索 1000v | 0.10ms | numpy brute-force |
| 向量搜索 5000v | 0.14ms | FAISS IVFFlat |
| 向量搜索 20000v | 0.22ms | FAISS IVFFlat |
| 混合检索 (FTS+Vec+KG) | 3.7ms | RRF 融合排序 |
| 神经睡眠巩固 (20条) | 0.2ms | 海马体→新皮层 |
| 记忆验证 (37条) | 18.4ms | 时效性+冲突检查 |

### v1.0 (numpy brute-force)

| 指标 | 值 |
|:---|:---|
| ONNX 嵌入 | 0.002ms |
| 向量搜索 (25v) | 0.063ms |
| FTS 搜索 (25d) | 0.006ms |
| 并发吞吐 | 5963 ops/s |

### FAISS 自动切换

| 规模 | 后端 | 搜索延迟 | 说明 |
|:---|:---|:---|:---|
| <1000 条 | numpy | 0.10ms | 预归一化，直接 dot product |
| ≥1000 条 | FAISS IVFFlat | 0.14ms | O(log n)，自动切换 |
| ≥10000 条 | FAISS IVFFlat | 0.18ms | nlist=100, nprobe=16 |

## 快速开始

### 安装

```bash
cd pangu
pip install -e .
```

### 初始化

```bash
pangu init
```

### 配置 LLM

```bash
# OpenAI
export OPENAI_API_KEY="sk-xxx"
pangu init --force

# Ollama (本地)
# 先启动 Ollama: ollama serve
export PANGU_LLM_PROVIDER=ollama
export PANGU_LLM_MODEL=qwen2.5:7b
pangu init --force
```

### 启动服务

```bash
# Web UI (http://127.0.0.1:8866)
pangu serve

# MCP 服务器 (供 Agent 框架调用)
pangu mcp
```

### CLI 命令

```bash
# 记忆管理
pangu search "关键词"           # 搜索记忆
pangu wake-up                  # 获取唤醒上下文
pangu recall --wing work       # 按空间回忆

# 记忆挖掘
pangu mine ~/projects --wing work  # 从文件挖掘记忆

# Wiki 管理
pangu wiki-list                # 列出 Wiki 页面
pangu wiki-generate "主题"      # 自动生成 Wiki

# 知识图谱
pangu kg-stats                 # 图谱统计

# 记忆巩固 (NEW)
pangu consolidate              # 查看巩固状态
pangu forget --dry-run         # 预览将被遗忘的记忆
pangu compress                 # 压缩旧记忆
pangu associations             # 检测记忆关联

# 系统
pangu stats                    # 系统统计
pangu identity --set "新身份"   # 设置 AI 身份
```

## MCP 工具列表 (80+ 个)

### Palace 管理
- `pangu_list_wings` / `pangu_create_wing`
- `pangu_list_rooms` / `pangu_create_room`

### 记忆操作
- `pangu_add_memory` / `pangu_search_memories`
- `pangu_recall` / `pangu_wake_up`

### Wiki 操作
- `pangu_list_wiki_pages` / `pangu_get_wiki_page`
- `pangu_create_wiki_page` / `pangu_auto_generate_wiki`

### 知识图谱
- `pangu_kg_add_entity` / `pangu_kg_add_relation`
- `pangu_kg_query` / `pangu_kg_neighbors`

### LMM 记忆处理
- `pangu_summarize` / `pangu_classify` / `pangu_insight`

### 记忆巩固 (NEW)
- `pangu_consolidation_stats` / `pangu_find_forgotten`
- `pangu_compress_memories` / `pangu_detect_associations`
- `pangu_memory_importance`

### 迁移与备份 (NEW)
- `pangu_export` / `pangu_import` / `pangu_backup`
- `pangu_list_backups` / `pangu_restore_backup`

### 聚类、去重、冲突 (NEW)
- `pangu_cluster_memories` / `pangu_find_related`
- `pangu_find_duplicates` / `pangu_merge_duplicates` / `pangu_similarity_check`
- `pangu_detect_conflicts` / `pangu_check_pair`

### 分析与时间线 (NEW)
- `pangu_analyze` / `pangu_health_check` / `pangu_anomaly_detect` / `pangu_growth_trend`
- `pangu_build_timeline` / `pangu_find_causal_links` / `pangu_event_chains` / `pangu_timeline_query`

### 融合、模式、回放 (NEW)
- `pangu_fuse_topic` / `pangu_progressive_summarize` / `pangu_crystallize_knowledge`
- `pangu_discover_patterns` / `pangu_pattern_insights`
- `pangu_timeline_replay` / `pangu_topic_replay` / `pangu_highlight_reel`

### ── ONNX 加速嵌入 (NEW) ──

- `pangu_onnx_embed` / `pangu_onnx_embed_batch` — 本地 CPU 推理 384-dim 真实语义向量
- `pangu_onnx_similarity` / `pangu_onnx_status` — 相似度计算 + 性能统计

### ── 伏羲移植模块 (NEW) ──

**FTS5 混合搜索**
- `pangu_fts_search` / `pangu_fts_search_stats` — FTS5 + 向量 RRF 融合搜索

**全息记忆**
- `pangu_holographic_encode` / `pangu_holographic_search` — 5维投影跨维度融合检索

**记忆法官**
- `pangu_judge_memory` / `pangu_judge_stats` — LLM A/B/C 三级价值判断

**自适应参数**
- `pangu_adaptive_params` / `pangu_adaptive_evaluate` — 系统状态驱动参数调整

**工作记忆**
- `pangu_wm_push` / `pangu_wm_get` / `pangu_wm_stats` / `pangu_wm_clear` — Miller 7±2 槽位短期记忆

**记忆脱敏**
- `pangu_sanitize` / `pangu_sanitize_check` — 3 级脱敏 + XSS 检测

**再巩固 + 共鸣**
- `pangu_reconsolidate` / `pangu_find_resonance` / `pangu_cross_wing_resonance`

**知识蒸馏增强**
- `pangu_distill_knowledge` / `pangu_distill_causal_chains` / `pangu_distill_graph` / `pangu_distill_stats`

**向量索引**
- `pangu_vector_index_stats` / `pangu_vector_index_build` — 加速大规模 ANN 搜索

**注意力系统**
- `pangu_attention_state` / `pangu_attention_switch` / `pangu_attention_ab_test` — 5策略 + A/B测试

**增强评估**
- `pangu_enhanced_contradictions` / `pangu_trajectory_track` / `pangu_trajectory_compare` — 6种LLM裁决

**流式索引**
- `pangu_streaming_index` / `pangu_streaming_stats` — 增量索引 + WAL + 断点续传

**验证循环**
- `pangu_verify` / `pangu_verify_phase` — 6 阶段质量门控

**差分隐私**
- `pangu_privacy_stats` / `pangu_privatize_count` — ε-差分隐私

**服务器增强**
- `pangu_system_health` / `pangu_system_metrics` / `pangu_config_get` / `pangu_config_set` / `pangu_config_reload`
- `pangu_schema_version` / `pangu_schema_migrations` / `pangu_autonomous_analyze` / `pangu_api_server_start`

#### 神经记忆系统 (v2.0)
- `pangu_neural_stats` — 海马体-新皮层双系统统计
- `pangu_neural_sleep` — 触发睡眠巩固（海马体→新皮层重播）
- `pangu_neural_spreading` — 激活扩散，找到关联记忆
- `pangu_neural_inhibition` — 竞争抑制，返回有效激活值
- `pangu_neural_decay` — 个性化遗忘曲线衰减

#### 记忆智能 (v2.0)
- `pangu_importance_feedback` — 5 种反馈信号动态调整重要性
- `pangu_auto_fusion` — 自动融合同主题碎片记忆
- `pangu_cross_session_links` — 发现跨会话记忆关联
- `pangu_auto_compress` — 长记忆自动压缩为精简摘要
- `pangu_validate_memories` — 验证记忆准确性和时效性
- `pangu_kg_auto_extract` — 从记忆中自动提取实体和关系
- `pangu_hybrid_search` — FTS+向量+KG 三路 RRF 融合检索

### 其他
- `pangu_create_tunnel` / `pangu_list_tunnels` / `pangu_find_tunnels`
- `pangu_stats` / `pangu_graph` / `pangu_identity`

## REST API

启动 Web 服务后访问 `http://127.0.0.1:8866/docs` 查看完整 API 文档。

主要端点：
- `GET/POST /api/wings` — 空间管理
- `GET/POST/DELETE /api/memories` — 记忆 CRUD
- `POST /api/memories/search` — 搜索记忆
- `GET /api/memories/wake-up` — 唤醒上下文
- `GET/POST/PUT/DELETE /api/wiki/pages` — Wiki 页面管理
- `POST /api/wiki/generate` — 自动生成 Wiki
- `GET/POST /api/kg/entities` — 知识图谱实体
- `GET/POST /api/kg/relations` — 知识图谱关系
- `GET /api/consolidation/stats` — 巩固统计 (NEW)
- `POST /api/consolidation/compress` — 压缩记忆 (NEW)
- `POST /api/llm/detect-associations` — 检测关联 (NEW)
- `GET/POST /api/identity` — 身份管理

### API v2 (伏羲移植)
- `GET /health` / `GET /health/deep` — 健康检查
- `GET /metrics` — Prometheus 指标
- `GET/POST/DELETE /api/v2/memories` — 记忆 CRUD
- `GET /api/v2/memories/search` — 搜索

## 配置

所有配置通过 `~/.pangu/config.json` 和环境变量管理。

### 关键配置项

| 配置 | 环境变量 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `llm_provider` | `PANGU_LLM_PROVIDER` | `openai` | LLM 提供商 |
| `llm_model` | `PANGU_LLM_MODEL` | `gpt-4o` | 模型名称 |
| `llm_api_key` | `PANGU_LLM_API_KEY` | - | API 密钥 |
| `llm_base_url` | `PANGU_LLM_BASE_URL` | - | 自定义 API 地址 |
| `backend` | `PANGU_BACKEND` | `chromadb` | 向量存储后端 |
| `web_port` | `PANGU_WEB_PORT` | `8866` | Web 端口 |
| `consolidation_enabled` | - | `true` | 启用记忆巩固 |
| `forgetting_curve_decay` | - | `0.5` | 遗忘曲线衰减率 |
| `compression_threshold` | - | `100` | 压缩触发阈值 |

## 终极目标

构建具备类人特征的超智能记忆智能体系统，为各类智能应用提供强大、高效、类人的记忆能力支持。

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check pangu/

# 真实 LLM 集成测试（需 API key）
export ZHIPU_API_KEY="your-key"
pytest tests/test_real_llm.py -v -m integration

# 或使用快速验证脚本
python scripts/test_real_llm.py
```

### 真实 LLM 测试覆盖

盘古支持 6 大 LLM provider（OpenAI / Anthropic / DeepSeek / 智谱 / 通义千问 / OpenRouter）的真实集成测试：

- **连通性验证**：基础对话、中文/英文、JSON 输出
- **错误处理**：无效 key、网络超时
- **记忆专用方法**：summarize_memories / classify_memory / generate_wiki_page
- **性能基线**：记录 P95 延迟、调用次数
- **Provider 矩阵**：参数化多 provider 同时验证

无 API key 时全部自动 skip，配置后即跑即用。

## License

MIT