# 盘古维护说明书（MAINTAINERS.md）

> **给下一个维护盘古的 agent / 人。** 目标是让你不必靠翻源码和试错来了解盘古。

## 🔴 维护流程（硬性，不是建议）

```
1. 动手之前  →  读完本文件（尤其 §0 四条认知错误 与 §40 已知坑）
2. 定位根因  →  别信注释/docstring，它们会说谎（见 §43 第 4 条）
3. 改 + 验证 →  跑受影响的测试子集（§42）
4. 写日志    →  在下面「维护日志」追加一条：日期 / 改了什么 / 为什么 / 怎么验证
5. 收尾自检  →  pytest tests/test_maintainers_doc.py 必须绿
```

**第 4 步为什么是硬性的**：`tests/test_maintainers_doc.py` 会核对「日志里最新的日期是否
不早于 `pangu/**` 下最新的文件修改时间」。改了代码不写日志 → **测试红**。
这个检查**不依赖 git**，所以云端（`/root/pangu` 无 git、靠 scp 部署）同样有效。

**第 1 步为什么是硬性的**：本文件里每条结论都是踩坑换来的。它有测试与代码交叉核对，
但代码会变、说明书写错也会误导人 —— 所以第 4 步的日志是它的历史账本。

---

## 0. 四条最容易踩的认知错误（先看这个）

| 你可能以为 | 实际是 | 依据 |
| --- | --- | --- |
| `config.json` 里 `llm_model` 是空的 = LLM 没接通 | **正常**。空值意味着「走动态发现」，见 §8 | `llm.py:468-500` |
| 实体表里同一个 id 出现多行 = 数据坏了 | **设计如此**。主键是 `(id, tenant_id)`，跨属主各存一份 | `knowledge_graph.py:126` |
| 某条记忆 `visibility='tenant'` = 只有本平台能看 | 还取决于**归属**。归属为空的记忆**任何平台都看不到** | `layers.py:389` |
| `/api/v2/graph` 挂在网关豁免名单里是正常的 | **不正常**。它 2026-09-26 之前一直**同时**满足「在豁免名单」+「路由内无自校验」，匿名可拉走全库图谱 | `server.py` 的 `_EXEMPT_PREFIXES` |

这三条我今天全部误判过。下面的细节都是为避免重复误判而写的。

---

## 1. 盘古是什么

**一句话：盘古是一个人的记忆系统。** 多个 AI 平台（Claude Code、OpenCode、DSH、Mimo 等）
把工作过程写进同一个盘古，盘古负责把这些碎片**整理、分类、去重、沉淀成知识**，
并在各平台需要时把它们**取回**。

### 它解决什么

各平台的 agent 是**互不通信**的。同一类问题，A 平台踩过的坑，B 平台还会再踩一遍；
B 平台发现 A 平台的记忆有出入、自己复测后写入新记忆，但**没人知道旧的那条已经错了**。
盘古就是那个共同底座：

| 能力 | 说明 |
| --- | --- |
| **跨平台共享** | 所有审核通过的平台写进同一份记忆库，搜到的经验互相可见 |
| **跨平台去重** | 两个平台写了同一件事，盘古识别并合并（实体 id 按**名字哈希**生成，天然同 id） |
| **纠错与归档** | 一条记忆被订正时，旧版本**快照归档**而不是直接覆盖，保留可追溯性 |
| **知识提炼** | 平台 agent 只负责写原始记忆，**由盘古（接 LLM）把它提炼成结构化知识** |
| **毕业机制** | 只有「有来源指针 + 被成功召回验证过」的记忆才对所有平台可见（见 §7） |

### 它不是什么（这条最容易误解）

- **不是多租户 SaaS。** 代码里有 `tenant_id` / `visibility` / `classification` 三轴，
  那是**多租户架构的预留能力**，业务上是**单用户**——所有平台共享全部记忆。
  记忆的 `tenant_id` 只是「哪个平台写的」这个**来源标记**，不是隔离墙。
- **不是向量数据库。** 向量只是检索通道之一；主存是 JSON 抽屉 + SQLite。
- **不含界面。** 仪表盘在插件仓 [`dsh-pangu`](https://github.com/Mlte0907/dsh-pangu)，
  盘古只提供数据面。

### 主存是什么

**记忆 = Drawer**（`pangu/core/palace.py`）：

| 字段 | 含义 |
| --- | --- |
| `id` | 记忆 id |
| `content` | 正文（**密文落库**，见 §7） |
| `wing` / `room` / `hall` | 宫殿结构：翼 / 房间 / 厅 |
| `importance` | 重要度 0~5（默认 3.0） |
| `emotional_weight` | 情绪权重 |
| `source` / `source_file` / `author` | 来源平台 / 来源文件 / 写入者 |
| `tags` / `created_at` | 标签 / 创建时间 |
| `metadata` | **扩展位**：`tenant_id` / `visibility` / `classification` / `owner_key_id` / `admission` / `last_feedback` 等 |

### 四层记忆栈（`pangu/memory/layers.py`）

渐进式加载，**避免一次把整个库塞进上下文**：

| 层 | 体积 | 何时加载 |
| --- | --- | --- |
| **L0 身份层** | ~100 tokens | 始终。读 `~/.pangu/identity.txt`，定义「我是谁」 |
| **L1 概要层** | ~500-800 | 始终。最重要/最近的记忆摘要 |
| **L2 按需层** | ~200-500 | 话题触发时 |
| **L3 深度搜索** | 无限 | 全文语义搜索 |

---

## 2. 运行模式

盘古有 **5 种运行形态**，默认端口 19529（MCP 与 REST 同端口）。

### 2.1 API 服务（当前部署形态）

```sh
# start.sh / install.sh 生成 systemd --user 单元
exec python -c "from pangu.api.server import create_app; uvicorn.run(create_app(), host=..., port=19529)"
```

- 入口：`pangu/api/server.py` 的 `create_app()`（FastAPI 工厂，1509 行）
- 提供 REST（`/api/v2/*`）+ MCP-HTTP（`/mcp`）+ WebSocket（`/ws`）
- 进程内还会起自主引擎的后台线程（§2.5）
- **云端 `/root/pangu` 不是 git 仓库**，部署 = `scp` 覆盖 + `systemctl --user restart pangu-api`

### 2.2 MCP over HTTP

- 传输层 `pangu/api/mcp_http.py`；端点 `POST /mcp`，支持 **SSE** 与 **StreamableHTTP**
- 握手鉴权：token 走 query 参数（api_key / `pgk_` 主密钥 / JWT）

### 2.3 MCP over stdio

给本地 MCP 客户端（如 Claude Code）用。`scripts/mcp_stdio_bridge.py` 是 stdio ↔ HTTP 桥。

### 2.4 CLI

`pangu/cli.py`（2616 行，typer，**75 个命令**），`pyproject.toml` 注册为 `pangu`。
覆盖记忆读写、搜索、备份、配置、诊断。适合手工排查与脚本化。

### 2.5 自主引擎（进程内后台线程）

`pangu/memory/autonomous.py` 的 `AutonomousMemoryEngine` + `BackgroundScheduler`，
按 `SCHEDULE_RULES` 周期跑 **15 个维护任务**（见 §9）。

> **这段历史上停摆过**：巩固、准入复检此前只挂在 MCP 宿主上，MCP 客户端全部下线后
> 面板就停在「1 天前」。现已统一挂进引擎调度。

### 2.6 另外两个独立 Web 服务器

- `pangu/server/web_server.py`（543 行）：记忆管理 Web UI + REST
- `pangu/server/websocket_server.py`（334 行）：实时记忆流推送

---

## 3. 功能地图

136 个记忆模块不是并列的，按能力域分九块。下表是**导航**；逐文件职责见
[`docs/FILE_INDEX.md`](./docs/FILE_INDEX.md)（自动生成，346 个文件）。

| 能力域 | 关键文件（行数） | 说明 |
| --- | --- | --- |
| **存取管道** | `ingestion.py`(935) `retrieval.py`(837) `layers.py`(1328) `drawer_storage.py` `encryption.py` | 写入走 `remember()` 全管道（脱敏→去重→冲突检测→supersede→版本链）；读走 `_read_drawers()` |
| **搜索** | `fts_search.py`(674) `hybrid_search.py` `vector_index.py`(777) `embedding.py`(441) `reranker.py` `query_rewriter.py` `synonyms.py` | FTS5 + 向量 + KG 三路，RRF 融合。嵌入三级降级：API → ONNX → hash |
| **知识** | `knowledge_graph.py`(1325) `distillation.py` `distill_enhanced.py` `domain_knowledge.py`(644) `knowledge_synthesis.py` `wiki/engine.py` | 实体/关系图谱、记忆→知识蒸馏、领域知识库、Wiki 知识页 |
| **生命周期** | `autonomous.py`(1282) `consolidation.py` `decay.py` `lifespan.py` `dream_memory.py` `adaptive_forgetting.py` `compression.py` | 巩固、衰减、遗忘、压缩、梦境整理 |
| **质量治理** | `dedup.py` `conflict.py` `sanitizer.py` `quality.py` `importance_scorer.py` `memory_validator.py` `versioning.py` | 去重、矛盾检测、脱敏、质量评分、验证、版本链 |
| **推理** | `advanced_reasoning.py`(764) `causal_reasoning.py` `temporal_reasoning.py` `graph_reasoning.py` `debate.py` `world_model.py` | 因果、时间、图推理、多策略辩论、世界模型 |
| **多智能体** | `multi_agent.py`(801) `collaborative_intelligence.py` `session_bridge.py` `cross_session.py` `social_memory.py`(470) | 共享记忆空间、跨会话桥接与关联、记忆社交化 |
| **多模态** | `multimodal_pipeline.py` `image_engine.py` `audio_engine.py` `video_engine.py` | 图片/音频/视频/文件/URL 提取并存入记忆 |
| **观测运维** | `observability/` `error_monitor.py` `health_monitor.py` `analytics.py` `audit_analytics.py` `retrievability.py` | 健康检查、Prometheus 指标、OTel 追踪、错误监控、可检索性体检 |

**会真的调 LLM 的模块**（耗时/花钱）：`distill_enhanced` `debate` `world_model`
`semantic_compression` `judge` `query_rewriter` `retrievability`(LLM 阶段) 等。

**工具规模**：handler 注册了约 **430** 个 MCP 工具（`advanced` 121 / `system` 44 / `analytics` 37 /
`search` 33 / `consolidation` 32 / `io_tools` 30 / `session` 28 / `quality` 20 / `llm_tools` 19 /
`multimodal` 17 / `timeline` 16 / … ），但**默认只暴露 31 个**，其余需开 `exposure`（见 §6）。

---

## 4. 东西在哪

| 项 | 值 |
| --- | --- |
| 云端仓库 | `/root/pangu` —— **不是 git 仓库** |
| 部署方式 | `scp` 覆盖文件 + `systemctl --user restart pangu-api` |
| 服务 | `systemctl --user pangu-api`，监听 `0.0.0.0:19529` |
| 数据目录 | `/root/.pangu/` |
| 权威记忆库 | `/root/.pangu/pangu.db/v2_memories/`（`drawers.json` + `knowledge_graph.db`） |
| 旧版目录 | `/root/.pangu/`（v1）。**别读它** —— `KnowledgeGraph` 读 v2，读 v1 会得到「stats 报 19 实体、graph 返回 0」这类假象 |
| Python | `/root/pangu/.venv/bin/python`。用 `.venv/bin/python -m pytest` |

**没有 CI 部署**（`.github/workflows` 里唯一的 deploy 是文档站）。所以「改了没生效」= 忘了 scp 或忘了 restart。

---

## 5. 怎么连、怎么发请求

```sh
# 远程执行（注意 heredoc 与 setlocale 过滤）
ssh -4 -i ~/.ssh/id_rsa_113 root@113.45.134.86 'bash -s' <<'EOF' 2>&1 | grep -v setlocale
...
EOF
```

- 主机名 `hcss-ecs-e9ef`（`hcss` = 华为云）。别名 `hcss113` **在本机不存在**，没有 ssh config。
- **只试 `root`**。连续试多个用户名（6 次 publickey 失败）会触发 fail2ban，22 端口直接
  `Connection refused`，而 8443/8444/19529/7000 仍通 → 只能等解封。

### 身份与边界（两条取数路径，2026-09-26 实测）

| 身份 | 凭据 | 能走 MCP | 能走 FastAPI |
| --- | --- | --- | --- |
| 平台 agent | `pgp_` / `ptok_` 平台 Token | ✅ | ❌ 全部 401 |
| 管理员 / 仪表盘 | `api_key`（配置文件的 `api_key`） | ✅ | ✅ |
| 管理员 / 仪表盘 | `X-Admin-Key`（独立管理员密钥） | ❌ | ✅（`/admin/*`） |

- `api_key` **不能**当管理员密钥用：打 `/api/v2/platforms`、`/api/v2/dashboard/stats` 仍返回
  401「需要 admin 凭据」，因为它们校验的是 `X-Admin-Key`。
- `~/.pangu/.deepseek_harness_platform_token` 那枚**已失效**，用会得 401「无效的平台接入 Token」。

---

## 6. 工具暴露面

`tools/list` 实测 **31 个**。数量会随版本漂移，**以实测为准，别写死**。

未暴露的工具要开 `~/.pangu/config.json` 的 `exposure` 段（结构对应 `core.config.ExposureConfig`，
**这三个是嵌套字段，不是 PanguConfig 顶层字段**）：

```json
{ "exposure": {
    "enabled_optional_modules": ["multimodal", "timeline"],
    "enabled_core_modules":     ["search", "palace"],
    "enabled_experiments":      ["causal", "cognitive"]
} }
```

**错误码 1001 vs 1002 必须分清**（极易混淆）：

| code | 含义 | 怎么办 |
| --- | --- | --- |
| 1001 | 工具**不存在**于任何模块 | 改配置永远修不好，检查工具名或先注册 |
| 1002 | 工具存在，但模块/实验组未启用 | 去 `exposure` 开对应模块 |
| 5000 | handler 执行抛异常 | 看 error 字段 |

注意：客户端 `tools` 白名单**是无效的**（`Config` schema 不接受该键，静默忽略）。范围控制点只在服务端。

---

## 7. 记忆模型（最容易误解的部分）

### 4.1 单用户，不做租户隔离

盘古是**单用户**的。代码里有 `tenant_id` / `visibility` / `classification` 三轴，但那是**多租户架构的预留能力**，业务上所有审核通过的平台共享全部记忆。

- 记忆的归属来自**平台 token**（`metadata.tenant_id` = 平台名，如 `deepseek-harness`、`opencode`）。
- 用 `api_key` 经 MCP 写入时，身份的 `room` **是空串** → 归属为 `''`。已修（见 §40），
  但**存量 46 条仍是空归属**。空归属 + `vis='tenant'` = **任何平台都不可见**。

### 4.2 `visibility` 三档

| 值 | 含义 |
| --- | --- |
| `public` | **毕业区** —— 所有平台可见 |
| `tenant` | 同归属可见 |
| `private` | 仅属主那把钥匙可见（靠 `owner_key_id` 判据） |

**`public` 是挣来的学位，不是「因为单用户所以共享」的标签。** 毕业门在 `ingestion.py:478-503`：

1. **来源指针**：`source_file` 或 `source_session` 任一存在
2. **正向验证反馈**：`last_feedback ∈ {recall_success, verified}`

两问全过 → `admission=graduated` + `visibility=public`。
验证信号来自 `record_recall_hits`（**被搜到才会毕业**，`retrieval.py:804`）。

> ⚠️ **不要为了「让所有平台都能看到」而批量把 `tenant` 改成 `public`。** 那是跳过质量门，
> 会让「避免错误记忆误导别的平台 agent」这个设计目标失效。实测 275 条里 152 条已毕业共享、
> 123 条按门禁待验证 —— 后者不是「该共享却没共享」，是**还没被验证过**。

### 4.3 内容是密文

`drawers.json` 里的 `content` 是 **Fernet 密文**（以 `gAAAAA` 开头）。

- **grep 内容搜不到**，只能按 `id` 前 8 位找，或用 `pangu.memory.encryption.decrypt` 解密。
- 任何要读正文的地方都必须先解密；解密失败要**跳过**而不是把密文当明文 ——
  这是 2026-09-19 修过的同类泄露/误判坑（`search` / `recall` / `hybrid` / `embeddings` 四处都漏过）。

---

## 8. LLM：动态模型 + 轮换

用的是 AMD 的**免费**模型（`llm_base_url=https://developer.amd.com.cn/radeon/api/v1`）。
**必须动态**，因为：① 平台模型列表会变，写死的模型可能已下线；② 免费模型经常限流/拥塞。

- `discover_chat_models()`：`GET /models` 动态发现（`llm.py:46`，注释原话「列表随平台更新，不写死」）。
- 候选顺序：`llm_model` **配置值优先**；配了就先只用它，**整轮失败才懒发现**备选
  （让「一切正常」的调用不碰网络，也让配了假地址的 mock 测试不受影响）。
  **`llm_model` 留空 = 一开始就发现**，这是正常状态。
- 切换条件：某模型限流/繁忙，或 JSON 模式输出不可解析 → 换下一个。
- 全部候选失败才线性退避（`retry_delay×(n+1)`）进下一轮；轮次耗尽仍失败则返回最后一次响应，
  由调用方各自降级。
- 实测延迟：**热 1.1~2.6s，冷启动约 52s**。定时任务里遇到 50s+ 的首次调用是正常的，别当挂起。
- 密钥在 `/root/.pangu/.llm_api_key`（0600），**不在 `config.json` 里**（`save()` 会排除密钥字段）。
  判定「配没配密钥」要看这个文件，只看 `config.json` 会永远得出「没配」。

---

## 9. 自主任务

引擎：`pangu/memory/autonomous.py`，`SCHEDULE_RULES` 是唯一的调度表。

| 任务 | 间隔 | 触发条件 / 说明 |
| --- | --- | --- |
| `vector_rebuild` | 2h | |
| `collect` | 2h | |
| `fusion` | 4h | `min_new_since_last=10` |
| `decay` | 6h | |
| `kg_enrichment` | 6h | 抽取实体进图谱。**只处理前 50 条** |
| `readmission` | 6h | 重跑准入门，pending 的自动毕业 |
| `curiosity` | 8h | |
| `knowledge_gaps` | 12h | 主题孤立/因果断裂，噪声多 |
| `crystallize` | 12h | 记忆→知识蒸馏 |
| `dream` | 12h | |
| `anomaly_detection` | 24h | |
| `compression` | 24h | `min_old_memories=20` |
| `forget` | 24h | `min_forgettable=5` |
| `consolidation` | 24h | 夜间巩固，**任务内自查 03:00–05:00 窗口** |
| `retrievability` | 24h | 可检索性体检，见 §41 |

共 15 个任务。带 `min_*` 的除间隔外还有「量够了才跑」的条件。

- 状态在 `/root/.pangu/pangu.db/v2_memories/autonomous_state.json`（只有 `last_run` 时间戳）。
- **`TaskResult.details` 不落盘** —— 任务跑完就没痕迹。需要留痕的任务得自己写文件
  （`retrievability` 写 `retrievability_report.json`）。
- `consolidation` / `crystallize` 走**无条件执行 + 任务内自检窗口**，不要给它们套 `_should_run` 的 24h 门，
  否则窗口外被标记 done 后会永远错过窗口。

---

## 10. 已知的坑（都是实测踩出来的）

1. **`entities_all` 主键是 `(id, tenant_id)`** —— 同一 id 在不同属主下各一行，**不是脏数据**。
   `INSERT OR REPLACE` 只覆盖「同 id 同属主」那份；换属主就变成新增。
   `migration.py` 曾写着「add_entity 均为 INSERT OR REPLACE，天然幂等」——**这句在复合主键下不成立**（已订正）。
   读取侧要按 id 合并（`api/server.py` 的 `graph_data` 已做）。
2. **REST 路径从不绑定租户作用域** —— `set_tenant_scope` 全仓只在 `mcp_server.py:376`（MCP `call_tool`）调过一次，
   默认 `''`，而实体/关系视图首句就是「租户为空＝全库视角」。所以任何走 REST 的图谱读都是全库视角。
3. **搜索结果的条目里没有 `tenant_id`**（只有 id/content/wing/room/hall/importance/source/source_file/tags/created_at）。
   要按归属判断就得用 `drawers` 现建对照表。
4. **搜索两种来源的分数量纲不同**：`semantic` 是余弦（0.33~0.76），`lexical` 是关键词计数
   （`engine.py:102`，个位数到几十）。**按分数做加权会失真**，要按位次。
5. **写测试鉴权相关行为**时，必须 patch 全局单例 `pangu.core.config.config` 的字段并把 `base_dir`
   指到 tmp —— 只 patch `PanguConfig.load` 无效，`create_app` 会用 `config.json` 的显式字段覆盖单例
   （`server.py:116-129`）。且网关 `enabled` 是全局开关，`api_key`/`jwt_secret`/`mcp_require_auth`
   皆空时中间件整体不生效，不显式配 `api_key` 会假绿。
6. ~~**全量测试套件很慢**（几分钟才到 3%）。~~ **2026-09-26 已测清，见 §10 第 9 条：**
   全量 **41 分 33 秒**跑完（1 failed / 1913 passed / 17 skipped），
   其中**一个测试就占 31 分钟**。慢的不是套件，是那一个用例。
7. **云端不是 git 仓库，所以「本地改了」不会自动到云端，反过来「云端漏了」也没人提醒。**
   2026-09-26 实测：当天修的三个洞（图谱按 id 聚合、MCP 写入归属回退、搜索本平台优先）
   的**回归测试和清理脚本一个都没部署到云端**，而云端的 `tests/test_p1_4_batch2_gate.py`
   还是修复前的版本，**仍在断言「`/api/v2/graph` 属于豁免路径、无凭据可访问」** ——
   也就是说线上没有任何测试在保护那三个修复。
   比对办法（全树 md5，别只看文件名/行数，等行数的内容差异索引抓不到）：
   ```sh
   ssh -4 -i ~/.ssh/id_rsa_113 root@113.45.134.86 'cd /root/pangu && find . -name "*.py" \
     -not -path "./.venv/*" -not -path "*/__pycache__/*" -type f -print0 | xargs -0 md5sum' > /tmp/cloud.md5
   python3 /tmp/opencode/cmp_tree.py /home/xiaoxin/pangu-dev /tmp/cloud.md5
   ```
   > 教训：**改代码和改它的测试要当成一个不可分割的部署单元**。只 scp 代码，线上就退回到
   > 「没有测试保护」的状态，而且没有任何症状。
8. **云端 venv 是 Python 3.11.2，本地是 3.13.5。** 本地测试绿不证明线上能跑，见 §15 的警告。
9. **「全量跑不动」的真相：慢的是一个测试，而且 CI 门禁根本没在跑全量。**

   2026-09-26 首次把全量跑完（1931 个用例）：

   | 项 | 实测 |
   | --- | --- |
   | 全量耗时 | **41 分 33 秒**（1 failed / 1913 passed / 17 skipped / 25 warnings） |
   | 其中 `test_bench.py::TestConcurrencyBench::test_concurrent_search` | **1863 秒 = 31 分钟，占 74%** |
   | 其余 1930 个用例合计 | 约 10 分钟 |

   **CI 侧的三个事实（互相印证）：**

   - `ci.yml` 的门禁 job 只列了 **33 / 88** 个测试文件
     （`test_core` + `v2_features` + `top_level_intelligence` + `v3_modules_*` + `integration` + `p1_3_*`，
     带 `--maxfail=20`）。另外 **55 个文件 CI 从来没跑过**，
     含 `test_auth.py` / `test_abac.py` / `test_e2e_rbac_abac.py` / `test_benchmark_*` 等。
   - `test.yml` 是唯一跑 `pytest tests/`（全量）的，但 `timeout-minutes: 30` ——
     **而全量要 41 分半，单个测试就 31 分钟，所以那个 job 必然超时被杀。**
   - 结论：**「全量从没成功跑过」不是谁忘了，是机制上跑不完。** 别再把它当「懒得跑」。

   **唯一失败项是墙钟预算断言，不是逻辑坏了**：

   ```
   AssertionError: 平均搜索耗时 18630.1ms 超过预算 15000ms
   ```

   测试自己的注释已经承认 `asyncio.gather` 在这里**根本不并发**（`_search` 内没有 await 点），
   所以它测的是「100 次搜索的平均墙钟」，不是并发吞吐。预算值只可用
   `PANGU_BENCH_SEARCH_MS` 调整，且注释里写明「该值受机器性能影响」。
   **别为了让套件变绿去调大这个数字** —— 那是把「机器速度」伪装成「代码质量」。

10. ~~**搜索每次都重算整个语料的嵌入（O(全库)）。**~~ **2026-09-26 已修，根因在嵌入层不在检索层。**

    **我此前两次判断都是错的，记在这里当反面教材：**

    - 第一次说「`FTS5SearchEngine.search()` 没有跨调用缓存」，并拿「275 条单次 2.24s」当证据。
      那 2.24s 是**坏数据** —— 当时向量路径静默失败，我拿一个「没干活」的数字当性能。
    - 第二次查 `EmbeddingService`，发现它**有** `_cache`，于是改口说「缓存有效，另有原因」。
      只看了一半：`embed_batch` 的 **API 分支**（`embedding.py:259-262`）有缓存，
      而 **ONNX 分支完全没有** —— 生产与测试环境走的正是 ONNX 分支。

    **真正的根因**：`EmbeddingService.embed_batch` 的 ONNX 分支既不查也不写 `_cache`。
    于是每次搜索都用 ONNX 把**整个语料**重算一遍（单条约 15ms；1000 条 ≈ 15 秒/次）。
    证据：pytest 环境里连搜 4 次后 `len(_cache) == 4` —— 只有 4 个**查询**向量，
    1000 条文档向量一个都没缓存。

    修法：ONNX 分支按 `hex_digest(text)` 查/写缓存（ONNX 是确定性的，同文同向量）。
    **降级补位的 hash 向量绝不写进缓存** —— 那会把一次偶发失败永久固化成无语义向量。

    | | 修前 | 修后 |
    | --- | --- | --- |
    | `test_concurrent_search`（1000 条 × 100 查询） | 1863 s，**FAILED** | **42.7 s，PASSED** |
    | 单次搜索平均 | 18630 ms | **~427 ms** |

    **预算一个字没动**（仍是 15000ms）—— 修的是缺陷，不是把及格线搬家。
    回归测试 `tests/test_embedding_onnx_cache.py`（6 项），其中
    `test_cache_does_not_change_vectors` 钉死「命中缓存与重算逐维相等」。

    > 顺带修掉一个**我自己造出来的回归**：把 hash 补位提前后，原来那句
    > 「补位后再遍历一次数 `None`」永远数到 0，于是 `partial_hash_vectors` 一直是 0 ——
    > **部分降级在 `/health` 里彻底不可见**，正是第 11 条刚修的那类 bug。
    > 既有测试 `test_embedding_degradation.py::test_partial_fill_counts_and_warns` 逮住了它。
    > **教训：给带记账的代码加缓存，记账必须跟着挪到同一处，否则静默归零。**

11. ~~**`fts_search.py` 的向量路径把异常全吞了、连日志都没有。**~~ **2026-09-26 已修。**
    修前：`_try_batch_embed` 的 `except: scores = self._fallback_embed(...)`，
    `_fallback_embed` 逐条 `except: continue` —— 向量路径整体失效时**不报错、不记录、不降级告警**，
    悄悄退化成纯 FTS。

    > 这不是理论问题：2026-09-26 做基准时，`build_index` 在 275 条要 0.66s、在 500 条却只要 0.03s、
    > search 0.00s —— 「越跑越快」是不可能的，真实原因是嵌入抛异常被吞了。
    > **我差点把那个 0.03s 当成好性能报出来。** 对照组 `hybrid_search.py` 同样吞异常，
    > 但至少有 `logger.debug`。差距就在这。

    修后（`pangu/memory/fts_search.py`）：

    - 4 处静默吞异常全部留痕：批量失败 → `warning`（含堆栈）；逐条失败 → **聚合成 1 条**
      `warning`（写明 `N/M 条失败`，避免 1000 条全失败刷 1000 行）；
      查询嵌入失败 → `warning`；**没有嵌入器** → `debug`（那是部署状态不是故障，与
      `hybrid_search.py` 的 ONNX 不可用一致）。
    - 返回值新增 `degraded: bool`：**True 表示向量路径故障降级过**。
      这是关键 —— 此前 `method` 在两种完全不同的情况下都是 `"fts"`：
      向量**坏了**（该告警）vs 向量正常但**没有文档达阈值**（完全正常）。
      不区分，故障就隐形了。
    - 降级标志用 `threading.local()` 而非实例属性：`_get_fts_engine()` 是**跨线程共享单例**，
      挂实例属性会让 A 请求的降级状态报到 B 请求头上。
    - 三个 `empty` 早退分支统一走 `_empty_response()`：原先各写各的、键集合不一致，
      调用方按 `r["degraded"]` 取值会在其中一条路上 **KeyError**（写测试时当场抓到）。
    - 回归测试 `tests/test_vector_degradation_visible.py`（6 项），其中两项是**行为不变**断言：
      降级前后返回的结果 id 序列必须一致 —— 加可观测性不许动行为。

    > 写这个测试时踩到的坑，值得单独记：**`_SEARCH_CACHE` 是模块级全局 LRU**，
    > key 只由 `(query, wing, room, limit, offset, min_importance, vector_weight)` 组成，
    > **与嵌入器状态无关**。所以同一 query 的第二次调用会直接拿到上一次的响应，
    > `degraded` 读到的是别人的结果。测试里必须 `use_cache=False`；
    > 线上排查「为什么这次报了降级那次没有」时，先想到它。

12. **教训（我这一轮连犯两次）：结论看着很炸裂时，先怀疑「测量本身坏了」。**
    - 第一次：`pgrep -f pytest` 先匹配到 bash 包装进程，CPU 读数取错对象，
      于是把「满负荷 3.5 核在算」误判成「卡死」。
    - 第二次：shell 管道里定义的函数不生效，比对输出全空；以及忘了归一化 `./` 前缀，
      把 346 个文件全报成不一致。
    - 正确做法：拿**能独立复核的判据**（`/proc/<pid>/stat` 的 CPU tick 增量、
      拿真实进程重跑一遍），别拿单一读数下结论。

---

## 11. 可检索性体检（`retrievability` 自主任务）

模块：`pangu/memory/retrievability.py`。两个阶段，**能力边界不同，别混为一谈**。

**规则阶段**（3s，40 候选）：用记忆**自身**的罕见词造探针回搜，搜不回自己就报。
→ 实际只命中叙述型记忆（发布记录、踩坑流水账），**误报率高**（40 报 23）。

**LLM 阶段**（12 候选约 137s，含冷启动）：让 LLM 挑出「与自身主题无关、但仍关键」的事实
（访问方式/端口/路径/命令/凭据位置），再针对**那个事实**去搜。这才对得上真实失败。
→ 实测 12 候选抽出 12 个事实，8 个可检索、4 个埋住。

> ⚠️ 立项动机（「云端盘古怎么连」这条信息埋在 dsh-remote-x 上线记录中间）**实测是能被搜到的**
> （排第 2 位）。所以本模块给的是**可发现性信号**，不是「检索不到」的判定。别夸大它。

报告：`retrievability_report.json`，经 `/api/v2/autonomous/status` 的 `retrievability` 字段暴露。

---

## 12. 测试怎么跑

```sh
cd /root/pangu
.venv/bin/python -m pytest tests/test_xxx.py -q          # 单个
.venv/bin/python -m pytest tests/test_a.py tests/test_b.py -q   # 相关子集，十几秒
```

改了东西至少跑这几个：`test_p1_3_tenant_scope` / `test_p1_3_kg_tenant_scope`（多租户语义）
`test_p1_3_leak_sweep`（访问控制）/ `test_p1_4_batch2_gate`（网关）/ `test_auth`。
**它们锁的是有意设计，不是历史包袱 —— 别为了让测试变绿去改它们。**

新增测试的坑：
- 渲染类测试要 `PANGU_TEST_MODULES=<repo>/node_modules`（插件仓同理，默认路径不存在会静默跳过）。
- React 的 act 弃用提示走 `console.error`，会被「收集渲染错误」的钩子误判为失败。

---

## 13. 维护日志

> 格式：`- **YYYY-MM-DD** — 改了什么 / 为什么 / 怎么验证的`
> **最新的一条在最上面。** 由 `tests/test_maintainers_doc.py` 核对最新日期。

- **2026-09-27** — 修 CI 的 Python 矩阵，并**订正我昨天那条错误的建议**。
  - **我昨天说「让 CI 固定用 3.11」是错的，而且方向正好相反。** 核对后发现：
    生产版本 3.11 **一直**在 `test.yml` 矩阵里、一直被门禁着；
    真正的缺口是**本地开发用的 3.13 不在任何 CI job 里** ——
    而「本地全绿」恰恰是每天都在依赖的信号。
  - **改**（`.github/workflows/test.yml`）：矩阵 `3.10/3.11/3.12` → **`3.11/3.12/3.13`**。
    去掉 3.10（**低于** `pyproject.toml` 的 `requires-python = ">=3.11"`，
    在测一个官方不声称支持的版本，绿灯没有意义）；加上 3.13（开发实际使用的版本）。
  - **加**：`tests/test_python_version_matrix.py`（5 项 + 1 skip）把规则钉死 ——
    矩阵不得低于 `requires-python`；必须含云端版本（3.11）；必须含本地开发版本（3.13）；
    门禁默认版本必须在矩阵里；且代码里不得出现 PEP 695 `type X = ...` 之类
    3.12+ 独占语法（否则生产 3.11 直接 SyntaxError，而矩阵缺位时这类错误是**静默**的）。
    改之前它先红了两条，正是那两处矛盾。
  - **订正**说明书 §15 的框架：那条警告的**方向**是错的，已重写并保留仍成立的部分
    （改了运行时代码仍需在云端复跑一次）。
  - **验证**：新测试 5 passed / 1 skipped。**未改任何运行时代码。**

- **2026-09-26** — 修「每次搜索重算整个语料」：**根因在嵌入层，不在检索层**。
  - **两次判断错在先，记下来**：① 先说「`FTS5SearchEngine.search()` 无跨调用缓存」，
    证据「275 条单次 2.24s」——**那 2.24s 是向量路径静默失败时的坏数据**；
    ② 改口说「`EmbeddingService` 有缓存、另有原因」—— 只看了一半：
    `embed_batch` 的 **API 分支**有缓存，**ONNX 分支完全没有**，而生产/测试走的正是 ONNX。
  - **真根因**：`embedding.py` 的 ONNX 分支既不查也不写 `_cache`，每次搜索用 ONNX
    重算全库（单条 ~15ms，1000 条 ≈15s/次）。证据：pytest 里连搜 4 次后
    `len(_cache) == 4` —— 只有 4 个查询向量，1000 条文档向量一个都没缓存。
  - **修**：ONNX 分支按 `hex_digest(text)` 查/写缓存（ONNX 确定性，同文同向量）。
    **降级补位的 hash 向量绝不写缓存** —— 会把偶发失败永久固化成无语义向量。
  - **结果**：`test_concurrent_search` **1863s FAILED → 42.7s PASSED**，
    单次搜索 **18630ms → ~427ms**（快 43 倍），**预算 15000ms 一个字没动**。
    修缺陷，不是把及格线搬家。
  - **修掉自己造的一个回归**：把 hash 补位提前后，「补位后再遍历数 `None`」永远数到 0，
    `partial_hash_vectors` 恒为 0 ⇒ **部分降级在 `/health` 里不可见**。
    被既有测试 `test_embedding_degradation.py::test_partial_fill_counts_and_warns` 逮住。
    **给带记账的代码加缓存，记账必须挪到同一处，否则静默归零。**
  - **加**：`tests/test_embedding_onnx_cache.py`（6 项），含
    `test_cache_does_not_change_vectors`（命中缓存与重算逐维相等）、
    `test_none_result_is_not_cached`（None 不入缓存，否则故障无法恢复）、
    `test_search_over_corpus_becomes_sublinear`（重复搜索不再重算全库）。
  - **验证**：嵌入/搜索相关子集 **268 passed**；`test_concurrent_search` 单独跑 PASSED。
  - **未完成**：全套 `test_bench.py` 与全量套件的复测结果见下一条补记。

- **2026-09-26** — 修 CI 的「手写测试清单」腐烂：门禁原本 88 个文件只列 33 个，55 个从未被跑过且无任何症状。
  - **问题**：门禁 job 逐个列文件名，88 个文件里只列 33 个，另外 55 个**从未被 CI 跑过**。
    门铃装在门上，一半窗户没接线，而这种遗漏**没有任何症状** —— CI 不红、PR 不卡。
    清单本身就是腐烂根源：新增测试文件默认不被跑到。注释里那句「改动测试清单时勿漏」
    就是历史上留给自己的警告。
  - **改**（`.github/workflows/ci.yml`）：门禁与覆盖率两步都改成
    `pytest tests/ --ignore=tests/test_bench.py`。
    排除项是**显式决策**（留在 diff 里），而漏掉的文件不会有任何痕迹。
    排除 `test_bench.py` 的理由写进注释：它断言的是**墙钟预算**，取决于机器快慢，
    拿它当门禁必然变成随机红灯；它仍在 `test.yml` 的全量 job 里跑完整套。
  - **改**（`.github/workflows/test.yml`）：超时 30 → **60 分钟**。实测全套 14 分 27 秒，
    30 分钟在 GitHub runner（通常慢 2~3 倍）上**必然被杀** ——
    「全量已验证」这个状态此前从未存在过。
  - **加**：`tests/test_ci_covers_everything.py`（5 项）把规则钉死：
    门禁不得出现裸的 `tests/xxx.py`；每个测试文件要么被 `--ignore` 排除、要么靠跑整个
    目录自动纳入；排除项必须带理由注释；全量 job 的超时必须大于「实测 × 3」。
    已用「把 ci.yml 改回手写清单」验过确实会红。
  - **前提**：这次敢改成跑全目录，是因为全量实测**那 55 个文件全部通过**。
    没验证就改，等于把「CI 报绿但没在守」换成「CI 一直红」。

- **2026-09-26（补记）** — 上一条的复测结果：bench 与全量套件失败归零，耗时降到三分之一。
  - `test_bench.py` 全文件：**21 passed / 0 failed，437s**（修前约 2400s 且 1 failed）。
    其中 `test_fts_engine_memory` 153→175s、`test_bench_fts_search_large` 141→171s
    **变慢了 14%~21%** —— 它们是内存/索引基准、不走搜索缓存，回退来自缓存查找开销 + 机器噪声。
    **不 claim「全都变快」。**
  - **全量套件：1926 passed / 17 skipped / 0 failed，14 分 27 秒**
    （修前 `1 failed / 1913 passed / 41 分 33 秒`）。失败归零、耗时降到三分之一。


- **2026-09-26** — 修「向量路径静默降级」：加日志 + 返回值加 `degraded` 标志。**本轮唯一改运行时代码的一次。**
  - **为什么**：见 §10 第 11 条。嵌入器一坏，搜索悄悄退化成纯 FTS，结果变差而没人知道；
    我自己被它骗过，差点把「500 条只要 0.03s」当性能优化报出来。
  - **改**（`pangu/memory/fts_search.py`）：4 处静默 `except` 全部留痕；逐条失败聚合成 1 条日志；
    返回值加 `degraded: bool` 区分「向量坏了」与「没有文档达阈值」——
    **此前 `method` 在这两种情况下都是 `"fts"`，故障因此隐形。**
    降级标志用 `threading.local()`（`_get_fts_engine()` 是跨线程共享单例，实例属性会竞态）。
    三个 `empty` 早退分支统一到 `_empty_response()`（原先键集合不一致，按 key 取会 KeyError）。
  - **加**：`tests/test_vector_degradation_visible.py`（6 项）。含两项**行为不变**断言 ——
    降级前后结果 id 序列必须一致，即「加可观测性不许动行为」。
  - **踩**：写测试时 `degraded` 恒为 False，查出是**模块级全局 `_SEARCH_CACHE` 命中了上一次结果**
    （key 与嵌入器状态无关），必须 `use_cache=False`。已写进 §10 第 11 条。
    另有一处**我自己写错的断言**：曾断言降级后 `vector_used is False` ——
    错在「降级 ≠ 向量不可用」，逐条路径的意义就是「慢但能用」，断言成不可用等于要求它别救场。
  - **验证**：新测试 6 passed；受影响子集 **263 passed**（core / 搜索质量 / 嵌入 / own-first / retrievability）；
    契约类 **89 passed**（rest_v2_contract / honest_returns / integration / docs_freshness）。
    **未部署云端**（见下一条）。
  - **遗留**：本条只改本地。云端 `/root/pangu` 仍是旧代码 —— 见 §10 第 7 条，
    **改完运行时代码必须连测试一起 scp**，这次别再漏。

- **2026-09-26** — **首次把全量测试套件跑完**（还清了一笔挂了两天的债），并查清「为什么跑不动」。
  - **结果**：`1 failed, 1913 passed, 17 skipped, 25 warnings in 41:33`。
    其中 `test_bench.py::TestConcurrencyBench::test_concurrent_search` **一个就烧 1863 秒（74%）**，
    其余 1930 个用例合计约 10 分钟。所以「全量很慢」从来不是套件的问题，是那一个用例。
  - **查清 CI 的真相**：`ci.yml` 门禁只跑 **33/88** 个文件（另外 55 个从来没跑过）；
    `test.yml` 是唯一跑全量的，但 `timeout-minutes: 30` 而全量要 41 分半
    ⇒ **那个 job 必然超时**。「全量从没成功跑过」是机制问题，不是谁偷懒。详见 §10 第 9 条。
  - **唯一失败项是墙钟预算断言**（18630ms > 15000ms），不是逻辑坏了。
    **刻意没有调大这个数字让它变绿** —— 那是把机器速度伪装成代码质量。
    它不在 `ci.yml` 的门禁清单里，所以留着红也不新增破坏；要改预算或标 slow 都会改变 CI  enforcing 什么，
    属于要人拍板的事。
  - **顺带查清一个真性能特征**：`FTS5SearchEngine.search()` 每次调用重新嵌入全库（无缓存），
    275 条实测单次 ≈2.24s。但**当前不影响线上**：`pangu_fts_search` 不在 31 个默认暴露工具里
    （`CORE_WHITELIST` 与线上 `tools/list` 双向确认），暴露的 `pangu_hybrid_search` 实测 857ms，
    生产检索 `retrieval.py:211` 走纯 FTS 不走向量。**同样刻意没动生产检索代码。**
  - **记一个真实的观测缺陷**：`fts_search.py` 的向量路径把异常全吞、连 `logger.debug` 都没有，
    向量失效时静默退化成纯 FTS。我做基准时就撞上了 —— 275 条 `build_index` 0.66s、500 条却 0.03s，
    「越跑越快」只能是异常被吞。差点据此报出「500 条只要 0.03s」的性能优化。详见 §10 第 11 条。
  - **踩坑**：本轮两次因「测量对象搞错」下结论（`pgrep` 匹配到 bash 包装进程 → 误判卡死；
    shell 管道里函数失效 → 比对输出全空）。已写进 §10 第 12 条。
  - **验证**：`pytest tests/test_maintainers_doc.py` → 27 passed。**本轮只改文档，未改任何运行时代码。**

- **2026-09-26** — 说明书补齐「是什么/运行模式/功能地图」三节；`AGENTS.md` 从 14KB 压成索引。
  - **为什么**：原 `AGENTS.md` 14350 字节、6 节，而它被 DSH **自动注入每个进入本项目的会话** ——
    篇幅一大就稀释注意力（用户 2026-09-26 明确提出）。所以定成「`AGENTS.md` 只做索引，
    细节全进说明书」，并加测试把预算焊死（4KB）。
  - **加**：`AGENTS.md` 旧内容里属于说明书的部分迁进 §14（行为规则、配置热加载的坑、协议约束、
    容器约束、dsh-brake 死亡循环预防）与 §15（环境事实表）。测试核对「迁走的内容真的在说明书里」。
  - **加**：§1 盘古是什么（含**它不是什么**：不是多租户 SaaS、不是向量库、不含界面）、§2 运行模式
    （API/MCP-HTTP/MCP-stdio/CLI/进程内自主引擎）、§3 功能地图（136 个记忆模块分九大能力域）。
  - **修**（自己踩的）：为插入这三节把手册整体右移重编号后，`AGENTS.md` 的节索引**没跟着改**，
    索引把读者指到错误的节。新增 `test_agents_md_section_index_points_at_real_sections` 校验
    「§号 → 节标题文字」逐行对得上（只认表格行；允许短标题 vs 括号后缀的前缀匹配）。
    故意把 `§13 维护日志` 改成 `§10 维护日志` 验过确实会红。
  - **加**：`test_file_index_is_current` 调 `scripts/gen_file_index.py --check`，
    索引过期即红 —— 加上当天就抓到一次（加完三节索引就过期了）。
  - **验证**：`pytest tests/test_maintainers_doc.py` → 27 passed。`AGENTS.md` 3167 字节。
  - **加**：把说明书部署到云端时顺手做**全树 md5 比对**（本地 vs `scp` 后的线上），
    逮到一个一直没人提的部署缺口，见 §10 第 7 条：
    当天修的三个洞的**回归测试 + 清理脚本一个都没上云**，云端 `tests/test_p1_4_batch2_gate.py`
    还是修复前的版本、**仍在断言「`/api/v2/graph` 无凭据可访问」** —— 线上没有任何测试在保护那三个修复。
    已补齐 7 个缺失文件 + 更新那 1 个落后的，云端跑受影响子集 **108 passed**。
    **教训：改代码和改它的测试是一个不可分割的部署单元。**
  - **修**：生成器会把 `.bak-*` 这类备份目录索引进去（云端 4 个 `.bak-decrypt-fix/*.py`
    被算进 343）。已改成跳过一切点开头目录；实测云端 350 个 `.py` → 索引 346 条、`.bak` 命中 0。
  - **修**：说明书 §15 写「Python 3.13」—— 那是**本地** venv；云端实测 **3.11.2**，且服务
    `ExecStart` 用的就是它。本地测试绿**不证明线上能跑**。已改成「以 `.venv/bin/python -V` 为准」
    并加两条测试禁止再写死版本号。
  - **踩**：比对脚本第一版用 shell 管道归一化路径，函数在管道里没生效导致输出全空；
    第二版忘了归一化 `./` 前缀，把 346 个文件**全报成不一致**。两次都是「结论看着炸裂、
    其实是脚本坏了」。最后用 Python 重写才拿到可信结果（7 缺 / 4 多 / 1 不同）。

- **2026-09-26** — 建这份说明书 + 加交叉核对测试；修 3 个缺陷；加 2 个能力。
  - **修**：`/api/v2/graph` 从网关 `_EXEMPT_PREFIXES` 摘掉。此前它**同时**满足「在豁免名单」
    +「路由内无自校验」，实测**匿名可拉走全库图谱**（nodes 33 / edges 14），平台 token 同样畅通。
    同名单的 `admin`/`platforms`/`dashboard` 在路由内自己校验 admin，不受影响。
  - **修**：图谱按 id 聚合（`graph_data` 先合并再截断；边按「源|目标|谓词」去重）。
    成因是 `entities_all` 主键 `(id, tenant_id)` 遇上一次性把记忆归属改写成按平台分，
    下一轮抽取换了属主 → `INSERT OR REPLACE` 退化成 INSERT。线上 33 行 → 19 行、8 → 5、悬空关系 0。
    附：`memory_count` 原恒为 0（表里无此列），改为按抽取器同一判定现算 —— **必须先解密**，
    记忆是 Fernet 密文落库，在密文上匹配会报出「看着合理实则随机」的数。
  - **修**：MCP 写入 `tenant_id` 落成空串。`identity.get("room", 默认)` 只在 key 缺失时回退，
    而 api_key 身份的 room 是**存在但为空串** → 46 条记忆归属为空、对任何平台都不可见。改成 `or` 链。
  - **加**：搜索「本平台优先」，默认 `boost`（位次加权，提前 4 位）。`PANGU_OWN_FIRST_MODE`
    与 `PANGU_OWN_FIRST_BOOST` 两个 env 可回退/调参。**加权必须按位次不能按分数** ——
    引擎 semantic 是余弦（0.33~0.76）、lexical 是关键词计数（个位数到几十），量纲不同。
  - **加**：`retrievability` 自主任务（可检索性体检，24h）。规则阶段 3s；LLM 阶段 ~137s。
  - **验证**：线上匿名 401 / 平台 token 401 / admin 200；图谱 19 节点 19 唯一、5 边 5 唯一；
    相关子集 164 passed。（全量套件很慢，未跑完 —— 不等于全绿。）
  - **遗留**：46 条空归属的存量未回填（功能上无影响，`public` 行先于租户判定短路）。

---

## 14. 运维与协作细节（从旧 AGENTS.md 迁入）

> 原来这些都在 `AGENTS.md` 里，会被注入**每个**进入本项目的会话，篇幅一大就稀释注意力。
> 现在 AGENTS.md 只留硬规则 + 索引，细节在这里。

### 12.1 使用盘古的行为规则

1. **会话开始先查记忆**：`pangu_search_memories` / `pangu_fts_search`，关键词 2-3 个，
   把上次会话的结论与未完成事项检索出来（相当于「翻笔记本」）。
2. **会话结束前写记忆**：核心成果 / 结论 / 没做完的，一事一条、标主题标签。
3. **动手前先查**具体任务相关历史，避免重复踩坑。
4. **写入即记**：过程中出现值得记住的结论、决策、bug 根因，随手 `pangu_add_memory`（`wing=tech`）。
5. **状态外置**：长任务的中期状态写进盘古，任何新会话能检索恢复上下文。
6. **修复留痕**：修完 bug 写一条「根因 + 修法 + 验证方式」。
7. 长期政策：系统/技术/修复类记忆直接写公共区（`wing=default`），方便其他平台 agent 知晓。

### 12.2 配置热加载的坑

只替换 `server.config` 引用**不够**：`llm` / `search` / `wiki` 三个属性在首次访问时就把**旧
config 对象**存进了实例（如 `LLMEngine(self.config)`）。改 `config.json` 或只换 `server.config`，
这些已构造对象仍用旧值 —— 表现是「改了 LLM 模型/Key，保存后毫无变化，也不报错」。

修法：`MCPServer.invalidate_config_dependents()` 丢弃 `_llm`/`_search`/`_wiki`/`_persistent_cache`。
`pangu_config_set` 与 `pangu_config_reload` 都会调它。**新增持有 config 的组件时必须同步加进这个方法。**

密钥从不落 `config.json`（`save()` 排除了密钥字段），只存 `~/.pangu/.llm_api_key`（0600）。
**判定「配没配密钥」必须看那个文件** —— 只看 `config.json` 会永远得出「没配」。

### 12.3 协议与运行时约束

- MCP 工具必须带 `inputSchema` 且**不得重名**，否则官方 SDK 整表拒收。
- `pangu_config_reload` **不在**默认暴露面内（调它得 code=1002）；改配置用 `pangu_config_set`
  （它自己会落盘 + 失效组件缓存）。
- **`cordis.patch.yml` 的 HMR 在 web 实例不生效**，改完必须重启宿主。

### 12.4 容器 / 受限环境

- `sudo` 可能被 `no_new_privs` 拦截 → 走 **userspace**（`uv` 装 Python、`systemctl --user` 管服务），
  不要依赖 `apt` / 系统级 `systemctl`。
- 长时安装/下载要 `setsid nohup ... &` 完全脱离控制终端，否则工具调用中断会连带杀掉子进程。
- **不要 `pip install -r requirements.txt` 的老清单**：会传递引入约 1.3GB CUDA 轮子，且无 GPU
  机器上永不执行（代码路径都是惰性导入）。用 `pip install -e ".[multimodal]"`，无 GPU 装 CPU-only。

### 12.5 死亡循环预防（dsh-brake）

DSH 装了 `dsh-brake`，连续 6 个同类工具 step 会警告、10 个拒绝执行。硬规则：

1. 同一方向试 2 次失败就停 —— 换工具不算「新方向」（grep/read/bash 查同一问题本质同方向）。
2. 第 3 次碰壁必须向用户报告：试了什么、为什么失败、需要什么帮助。
3. 区分「代码错误」与「运行时问题」：代码逻辑对 ≠ 运行时正常。
4. 设硬停条件：两个不同路径都失败 → 停下来汇报、等指示。

---

## 15. 环境前提（部署形态相关）

| 项 | 值 | 核实方式 |
| --- | --- | --- |
| 仓库路径 | 云端 `/root/pangu`（**非 git**） | `pwd` |
| Python | **云端 3.11.2 / 本地 3.13.5**（见下方警告） | `.venv/bin/python -V` |
| 服务管理 | `systemctl --user pangu-api` | `systemctl --user status pangu-api` |
| 监听 | `0.0.0.0:19529`（MCP 与 REST 同端口） | `ss -ltn \| grep 19529` |
| 版本 | 以 `/health` 的 `data.version` 为准（实测 `0.4.1`） | `curl -s .../health` |

> 历史上曾有文档记录「421 个工具」与 `~/.pangu/palace/` 等值，来自**另一台主机**，与本机不符。
> **工具数量、路径、端口这类事实一律以实测为准**，别照搬任何文档（包括本文件）。

### ⚠️ 本地 Python 比云端新，测试绿不等于能上线

2026-09-26 实测：**云端 `.venv` 是 3.11.2，本地是 3.13.5**，服务 `ExecStart` 用的就是云端那个 venv。

> **2026-09-27 订正**：我此前把这条写成「CI 没在测生产版本、建议让 CI 固定用 3.11」——
> **那是错的，而且方向正好相反。** 核对 `test.yml` 矩阵后发现：
>
> | | 修前 | 修后 |
> | --- | --- | --- |
> | `pyproject.toml` `requires-python` | `>=3.11` | 不变 |
> | `test.yml` 矩阵 | 3.10, 3.11, 3.12 | **3.11, 3.12, 3.13** |
> | 云端生产版本 3.11 被门禁？ | ✅ 一直在 | ✅ |
> | **本地开发版本 3.13 被门禁？** | ❌ **不在任何 job 里** | ✅ |
>
> 也就是说：生产版本（3.11）**一直**被 CI 守着；真正的缺口是**开发版本（3.13）没人测** ——
> 而「本地全绿」恰恰是每天都在依赖的那个信号。
> 顺带修掉一处自相矛盾：矩阵里的 **3.10 低于声明的 `>=3.11`**，在测一个官方不声称支持的版本。
>
> 规则已钉成 `tests/test_python_version_matrix.py`：矩阵不得低于 `requires-python`、
> 必须含云端版本、必须含本地开发版本、门禁默认版本必须在矩阵里，
> 且不得出现 PEP 695 这类 3.12+ 独占语法（否则生产 3.11 直接 SyntaxError）。

仍然成立的部分：

- 在本地跑绿的测试只证明 **3.13** 能跑。**改了运行时代码，在云端再跑一次才算数**：
  ```sh
  ssh -4 -i ~/.ssh/id_rsa_113 root@113.45.134.86 'cd /root/pangu && .venv/bin/python -m pytest tests/test_xxx.py -q'
  ```
- 这条对**新写的运维脚本**尤其要紧：它们大多只在云端手动跑，本地根本不会执行到。

### 常用命令

```sh
curl -s http://127.0.0.1:19529/health
# 数一下当前暴露了几个工具（别写死这个数字）
curl -s -X POST http://127.0.0.1:19529/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['result']['tools']))"
cd /root/pangu && .venv/bin/python -m pytest tests/test_xxx.py -q
```

---

## 16. 维护规矩

1. 改了 `pangu/**` → **同步更新本文件**，并跑 `tests/test_maintainers_doc.py`。
2. 查清「为什么这样设计」比「它现在坏没坏」重要 —— 上面 §0/§7/§8 那些坑都是这么来的。
3. 改数据前先备份；`merge_kg_duplicates.py` 是范例（dry-run 默认、事务、自动备份、幂等、校验）。
4. 定位到根因再动手。**注释和文档可能说谎**：今天就遇到
   `graph_data` 的 docstring 声称「已从豁免前缀中移除」，而代码里其实一直还在。
