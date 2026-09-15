# 盘古 v0.3.0 — P2-1 模块接入方案（替代原"瘦身"路线）

> **方向调整**：原 P2-1 计划是"瘦身 / 删除"；经用户确认，3 个核心模块
> 都是真实可用的实现，**目标改为接入**——让它们在生产链路上跑起来。
>
> **调查时间**：2026-09-14
> **原则**：接入必须先勘察代码、写接入测试、全量回归、端到端验证。
> 不能"接入后只跑测试"——必须验证用户视角下真的能用到。

---

## 0. 三个模块现状（用户已确认"有作用"）

| 模块 | 行数 | 实现质量 | 当前状态 |
|---|---|---|---|
| `advanced_reasoning.py` | 757 | 高（完整因果/趋势/异常/缺口 4 大功能） | 仅 tests/test_v3_modules_f.py 引用 |
| `domain_knowledge.py` | 640 | 中（CRUD + 检索 + 关联，SQLite 后端） | 仅 tests/test_v3_modules_f.py 引用 |
| `performance.py` | 830 | 中（numpy HNSW + ARC + ObjectPool） | 仅 tests/test_memory_system.py 引用 |

---

## 1. 接入点设计

### 1.1 `advanced_reasoning` — 高级推理引擎

**4 大功能与对应接入点**：

| 功能 | 接入点 | 触发场景 | 价值 |
|---|---|---|---|
| 因果链发现 (`discover_causal_chains`) | `handlers/analytics.py` 新增工具 `pangu_discover_causal_chains` | 用户查询"为什么 X 发生"时 | 揭示记忆间因果，补检索语义 |
| 趋势预测 (`predict_trends`) | `handlers/analytics.py` 新增 `pangu_predict_trends` | 周期性任务（autonomous 中） | 主动告知趋势变化 |
| 异常检测 (`detect_anomalies`) | autonomous 新增 `_task_anomaly_detection` | 每天跑一次 | 自动发现异常记忆 |
| 知识缺口 (`identify_knowledge_gaps`) | autonomous 新增 `_task_knowledge_gaps` | 每周跑一次 | 提示补全什么知识 |

**接入设计**：
- 在 `handlers/analytics.py` 注册 4 个新工具（标注 `level="experimental"`）
- 在 `autonomous.py` 添加 2 个新任务（anomaly / gap）
- 任务结果写入 `pangu.db/v2_memories/drawers.json`（已被 P0-0 修过走权威路径）

**验收**：
- 至少有 1 条记忆时，`discover_causal_chains` 能返回非空结果
- `detect_anomalies` 在生产 82 条记忆上能跑出至少 1 个 anomaly
- 注入验证：不接入时工具不存在（1001 错误）；接入后工具可用

### 1.2 `domain_knowledge` — 领域知识库

**核心功能**：软件工程 / 项目管理 / 团队协作 三大领域的知识管理。

**接入点**：
- 注册到 `handlers/llm_tools.py`（或新建 `handlers/knowledge.py`）
- 工具列表：
  - `pangu_knowledge_create` — 创建知识条目
  - `pangu_knowledge_search` — 关键词检索
  - `pangu_knowledge_get_related` — 关联条目
  - `pangu_knowledge_stats` — 统计
  - `pangu_knowledge_deprecate` — 弃用条目

**特殊考虑**：domain_knowledge 用**独立的 SQLite DB**（不在 drawer.json 里）。
这意味着它和主记忆库是**两套存储**，需要在 PanguConfig 里新增配置项：
- `domain_knowledge_db_path`（默认 `palace_path/domain_knowledge.db`）

**验收**：
- 创建 1 条软件工程知识 → 检索能找到 → 关联另一条 → 统计计数 +1
- 端到端：CLI 调用 → DB 写入 → 重启服务后仍在

### 1.3 `performance` — 性能优化模块

**4 大组件与接入点**：

| 组件 | 接入点 | 当前替代 | 提升 |
|---|---|---|---|
| `HNSWVectorIndex` | `pangu/memory/vector_index.py` 当前用 numpy 暴力算 | numpy 暴力 | 大库（>1000 条）查询提升 10-100× |
| `ARCCache` | `pangu/memory/search_cache.py` 当前用 LRU | LRU | 缓存命中率提升 ~10% |
| `ObjectPool` | `pangu/memory/drawer_storage.py` 频繁创建 Drawer 对象 | 无 | 减少 GC 压力 |
| `BatchProcessor` | `pangu/memory/autonomous.py` 的 collect / decay / dream | 单条处理 | 批量处理吞吐提升 3-10× |

**接入策略**：分两步：
- **第一步（验证收益）**：先在测试中对比新旧实现的耗时
- **第二步（接入）**：仅当新实现确实更快/更好时再替换默认路径

**风险**：
- `HNSWVectorIndex` 是纯 numpy 实现，**生产规模下可能不如 faiss**——需要实测
- `ObjectPool` 改造可能影响 P0-0 已修的并发安全
- `BatchProcessor` 接入需要 autonomous 任务全部改为批量接口

**验收**：
- 基准测试：1000 条记忆下，新 HNSW 比暴力算快 ≥5×
- 不破坏 P0-0 测试覆盖（drawer 对象池不影响 drawers.json 内容）

---

## 2. 执行顺序

按依赖关系：

```
[Step 1] domain_knowledge — 独立 DB，独立工具，不影响其他模块
   ↓
[Step 2] advanced_reasoning — 用主记忆库，无外部依赖
   ↓
[Step 3] performance — 触及核心检索路径，必须最后做
```

**每个 Step 内部**：
1. 勘察代码 + 写接入测试（必须有「故意不接入则失败」的反向断言）
2. 接入到对应 handler / autonomous 任务
3. 跑全量测试（1476 passed 基线不能掉）
4. 端到端验证（curl + CLI）
5. 提交推送 + CI 通过

---

## 3. 风险与回退

| 风险 | 影响 | 缓解 |
|---|---|---|
| `advanced_reasoning.discover_causal_chains` 在大数据集下慢 | autonomous 任务超时 | 加超时 + 数据集大小限制 |
| `domain_knowledge` 新增 DB 路径与 PanguConfig 改动冲突 | P0-0 B7-a 之类问题 | 在 PanguConfig 加新字段，不动现有路径 |
| `performance.HNSWVectorIndex` 替换默认路径后回归 | 检索性能下降或行为变化 | 双路径并行（开关切换）+ 灰度 |
| `ObjectPool` 改动 drawer_storage.py | 破坏 P0-0 并发安全 | 跳过 ObjectPool，先做 HNSW/ARC/Batch |
| 接入后测试覆盖率不变（仍 1476） | 测试可能没真正验证接入 | 必须新增「端到端冒烟」测试 |

---

## 4. 验收门槛

P2-1 完成的定义：
1. 三个模块都在 `tools/list` 真实可调（不是 1001 也不是 1002）
2. 每个模块至少有一个**生产可观察**的效果：
   - `advanced_reasoning` → 用户能看到因果/异常/趋势的输出
   - `domain_knowledge` → 用户能创建/检索/关联知识条目
   - `performance` → 至少 HNSW 在测试中跑通加速对比
3. 全量测试 1476 passed 不掉
4. 服务运行 24 小时无崩溃

---

## 5. 不做的事

- ❌ **不删任何模块**（用户已明确"要用起来"）
- ❌ **不修改 P0-0 已修的权威化路径**（避免 B7 类问题复发）
- ❌ **不把 ObjectPool 接入 drawer_storage.py**（风险过高）
- ❌ **不接入 `performance` 的 numpy HNSW 到默认路径**（先实测，可能不如不接）
- ❌ **不补全 132 模块的测试覆盖率**（范围严格限于 3 个）

---

**等你拍板「先做哪个」。** 建议 Step 1 → 2 → 3 顺序，因为 domain_knowledge
风险最低、收益最高（独立 DB，不影响主链）。