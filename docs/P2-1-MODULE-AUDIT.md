# 盘古 v0.3.0 — P2-1 模块瘦身 / 转正方案

> **状态**：等用户确认；本文件是决策清单，**未执行任何修改**。
> **调查时间**：2026-09-14。
> **方法**：用 Python `ast` 解析所有 `pangu/` 与 `tests/` 的 `.py` 文件，
> 找出每个 memory 模块的真实调用方。

---

## 0. 全景数字

| 维度 | 数量 |
|---|---|
| `pangu/memory/` 下的模块 | **132** |
| 被 17 个 `handlers/` 直接 import | **110**（83%） |
| 仅在 `pangu/memory/` 内部被使用 | **19**（14%） |
| **0 个生产调用方**（仅测试引用） | **3**（2%） |
| 总删除候选行数 | **2,227 行** |

**关键结论**：盘古的 132 个模块**全部有调用方**，"概念性"模块已不存在。
真正的处置对象只有 3 个"测试专用"模块。

---

## 1. 分类总表

### A. 保留（核心基础设施） — 9 个

这些是 `MemoryStack` 或 `handlers/` 依赖的基础模块，**不可删除**：

| 模块 | 行数 | 调用方数 | 备注 |
|---|---|---|---|
| `layers.py` | 897 | 10 | 记忆栈核心 (L0/L1/L2/L3) |
| `embedding.py` | 441 | 26 | 嵌入服务工厂 |
| `onnx_embedder.py` | 413 | 14 | ONNX 嵌入后端 |
| `drawer_storage.py` | 469 | 1 | SQLite / JSON 抽屉存储（P0-0 已修） |
| `consolidation.py` | 296 | 3 | 记忆巩固引擎 |
| `decay.py` | 198 | 5 | 衰减管理 |
| `utils.py` | 235 | 17 | 工具函数 |
| `compression.py` | 142 | 2 | 记忆压缩 |
| `multimodal.py` | 261 | 5 | 多模态注册表 |

### B. 保留（被 handler 直接 import） — 101 个

这些模块都有清晰的工具入口（要么在 `CORE_WHITELIST`，要么在 `optional`/`experimental`）。
详见第 3 节附录。

### C. 保留（仅内部使用） — 19 个

这些模块只被其他 memory 模块引用，**无 handler 入口**，但仍在用：

| 模块 | 行数 | 调用方 | 状态 |
|---|---|---|---|
| `event_bus.py` | 180 | self_improve, lifespan, __init__ | 🟢 内部事件总线 |
| `ingestion.py` | 658 | session_bridge, video_engine, collector... | 🟢 记忆采集后端 |
| `realtime_bridge.py` | 64 | server.py | 🟡 64 行小工具，P0-0 已加权威化 |
| `search_explainer.py` | 301 | hybrid_search | 🟡 仅 hybrid_search 用 |
| `self_improve.py` | 290 | mcp_server.py | 🟢 配置热加载机制 |
| `synonyms.py` | 132 | retrieval.py | 🟢 检索同义词扩展 |
| `warmup.py` | 163 | server.py, llm.py | 🟢 B7 修复 |
| `wikilink.py` | 113 | ingestion, __init__ | 🟡 KG 与采集间桥接 |
| `lifespan.py` | 125 | __init__.py | 🟡 仅 __init__ 暴露 |
| `evaluation.py` | 131 | __init__.py | 🟡 仅 __init__ 暴露 |
| `realtime_bridge.py` | 64 | server.py | 🟡 |

### D. ⛔ 候选删除（0 生产调用方） — 3 个

**唯一达到"概念性"标准的模块**：

| 模块 | 行数 | 测试引用 | docs 引用 | docstring |
|---|---|---|---|---|
| `advanced_reasoning.py` | **757** | `tests/test_v3_modules_f.py` ×6 | `docs/history/v3-technical-documentation.md` | "高级推理引擎 — 因果推断、趋势预测与异常检测" |
| `domain_knowledge.py` | **640** | `tests/test_v3_modules_f.py` ×9 | `docs/history/v3-technical-documentation.md` | "领域知识库 — 软件工程、项目管理、团队协作知识管理" |
| `performance.py` | **830** | `tests/test_memory_system.py` ×2 | `docs/history/v3-technical-documentation.md` | "性能优化模块 — HNSW向量索引 + ARC缓存 + 对象池 + 批量操作" |
| **小计** | **2,227** | | | |

**共同特征**：
- ✅ **0 个生产代码 import**（AST 解析全仓确认）
- ✅ **0 个 handlers 引用**
- ✅ **0 个生产 CLI / API 调用**
- ⚠️ **每个都有测试**，但测试本身只测模块导入与基础属性，不测真实功能
- ⚠️ 都在 `docs/history/v3-technical-documentation.md`（历史文档）中被提及，**非当前活跃文档**
- ⚠️ `performance.py` 在 `docs/dashboard-plugin-design.md` 被提到一次，但只是占位符概念，**不引用模块本身**

---

## 2. 删除前必须确认的 3 个问题

> ⚠️ 删除是不可逆操作。下列问题**必须由你回答**，我不会自行删。

### Q1：是否同意删除 3 个测试专用模块？

- [ ] `advanced_reasoning.py` (757 行)
- [ ] `domain_knowledge.py` (640 行)
- [ ] `performance.py` (830 行)

**如果同意**，我还会顺手清理：
- 同步删除 `tests/test_v3_modules_f.py` 中对这 3 个模块的 import 与测试
- `tests/test_memory_system.py` 中 `performance` 的 2 处引用
- 在 `CHANGELOG.md` 加一条 "Removed unused modules (advanced_reasoning, domain_knowledge, performance)"

### Q2：是否要把 19 个"仅内部使用"模块中靠左的几个挪入 experimental？

下列 5 个模块**只在 `__init__.py` 注册**，无独立 handler 与独立价值：

| 模块 | 行数 | 建议 |
|---|---|---|
| `evaluation.py` | 131 | 标注 experimental，**保留** |
| `lifespan.py` | 125 | 标注 experimental，**保留** |
| `realtime_bridge.py` | 64 | 已被 P0-0 修复，**保留** |
| `search_explainer.py` | 301 | 仅 hybrid_search 用，**保留**（hybrid_search 是核心） |
| `wikilink.py` | 113 | KG 桥接，**保留** |

我倾向**不动它们**——它们要么是底层依赖，要么行数很小，删了不省多少。

### Q3：是否要给 `pangu/memory/__init__.py` 加注释，标明模块分级？

我倾向**加**。建议加一段模块分级注释，让新人能一眼看出哪些是核心、哪些是实验：

```python
# ── 模块分级 ──
# A. 核心基础设施（被 MemoryStack / handlers 直接依赖，删了必崩）：
#    layers, embedding, onnx_embedder, drawer_storage, consolidation,
#    decay, utils, compression, multimodal
#
# B. 主链路模块（被 handlers/* 直接 import，对应工具入口）：
#    retrieval, fts_search, vector_index, hybrid_search, knowledge_graph,
#    working_memory, autonomous, lifecycle, ... 共 110 个
#
# C. 内部桥接（仅在 memory/ 内部被引用，无独立入口）：
#    event_bus, ingestion, search_explainer, self_improve, ...
#
# D. 实验性 / 候删除（无生产调用方）：当前已清理
```

---

## 3. 附录：handler → 模块映射（17 个 handler 共引用 110 个 memory 模块）

### core（6 handler，28 工具）
- **memory_ops** (6 工具): `adaptive_forgetting, autonomous, encryption, memory_events`
- **search** (42 工具): `cluster, clustering, emotional_intelligence, explainable_search, fts_search, fuxi_bridge, ...`
- **system** (44 工具): `audit_analytics, graph_builder, graph_reasoning, project_manager, versioning`
- **io_tools** (30 工具): `auto_collector, backup_restore, collector, export_import, feishu_webhook, file_watcher`
- **palace** (4 工具): 0 个 memory 直接引用（用 Palace 自身）
- **batch** (3 工具): `batch_import`

### optional（10 handler）
- **multimodal** (17 工具): `audio_engine, image_engine, multimodal_pipeline, multimodal_search, multimodal_summary, video_engine`
- **timeline** (16 工具): `causal_reasoning, replay, temporal_reasoning, timeline`
- **analytics** (37 工具): `adaptive_learning, analytics, anomaly_detection, autonomous_learning, creative_thinking, ...`
- **quality** (20 工具): `conflict, dedup, enhanced_evaluation, memory_events, quality, quality_scorer, sanitizer`
- **consolidation** (32 工具): `adaptive_forgetting, consolidation_intelligence, context_injector, distill_enhanced, ...`
- **embed** (6 工具): `vector_index`
- **knowledge_graph** (7 工具): `knowledge_graph`
- **wiki** (4 工具): 0 个 memory 直接引用
- **llm_tools** (19 工具): `debate, deep_emotion, narrative`
- **session** (28 工具): `auto_pilot, cross_session, encryption, portal, session_bridge, sync_manager`

### experimental（1 handler）
- **advanced** (120 工具): `adaptive_architecture, adaptive_forgetting, adaptive_learning, adaptive_params, ...`（含 33 个 experimental 模块）

**合计**：17 个 handler × 平均 6.5 模块/handler ≈ **110 个 memory 模块**被直接 import。

---

## 4. 风险评估

| 操作 | 风险 | 缓解 |
|---|---|---|
| 删除 `advanced_reasoning.py` | 低（0 调用方） | 同步清理 `test_v3_modules_f.py` 6 处 import |
| 删除 `domain_knowledge.py` | 低（0 调用方） | 同步清理 `test_v3_modules_f.py` 9 处 import |
| 删除 `performance.py` | 低（0 调用方） | 同步清理 `test_memory_system.py` 2 处 + dashboard docs 占位符 |
| 加 `__init__.py` 分级注释 | 极低 | 注释不影响行为 |

**执行顺序**（P0-0 教训：永远测全量）：
1. 用户确认 Q1/Q2/Q3 的回答
2. 删除 3 个模块
3. 同步清理测试 + docs
4. 跑全量测试（1476 passed 基线）
5. 跑 ruff 检查
6. 提交并推送

---

## 5. 不做的事

- ❌ **不删任何 handler**（17 个全部保留，入口稳定）
- ❌ **不删任何 core 模块**（layers/embedding/onnx_embedder/drawer_storage 等 9 个核心基础设施）
- ❌ **不删 19 个仅内部使用模块**——它们都有真实调用方
- ❌ **不做大规模重命名或重构**——P2-1 范围限于"瘦身 / 转正"

---

**等你确认。** 决策完再动。