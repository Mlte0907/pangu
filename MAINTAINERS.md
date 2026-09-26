# 盘古维护说明书（MAINTAINERS.md）

> **给下一个维护盘古的 agent / 人。** 目标是让你不必靠翻源码和试错来了解盘古。

## 🔴 维护流程（硬性，不是建议）

```
1. 动手之前  →  读完本文件（尤其 §0 四条认知错误 与 §7 已知坑）
2. 定位根因  →  别信注释/docstring，它们会说谎（见 §10 第 4 条）
3. 改 + 验证 →  跑受影响的测试子集（§9）
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
| `config.json` 里 `llm_model` 是空的 = LLM 没接通 | **正常**。空值意味着「走动态发现」，见 §5 | `llm.py:468-500` |
| 实体表里同一个 id 出现多行 = 数据坏了 | **设计如此**。主键是 `(id, tenant_id)`，跨属主各存一份 | `knowledge_graph.py:126` |
| 某条记忆 `visibility='tenant'` = 只有本平台能看 | 还取决于**归属**。归属为空的记忆**任何平台都看不到** | `layers.py:389` |
| `/api/v2/graph` 挂在网关豁免名单里是正常的 | **不正常**。它 2026-09-26 之前一直**同时**满足「在豁免名单」+「路由内无自校验」，匿名可拉走全库图谱 | `server.py` 的 `_EXEMPT_PREFIXES` |

这三条我今天全部误判过。下面的细节都是为避免重复误判而写的。

---

## 1. 东西在哪

| 项 | 值 |
| --- | --- |
| 云端仓库 | `/root/pangu` —— **不是 git 仓库** |
| 部署方式 | `scp` 覆盖文件 + `systemctl --user restart pangu-api` |
| 服务 | `systemctl --user pangu-api`，监听 `0.0.0.0:19529` |
| 数据目录 | `/root/.pangu/` |
| 权威记忆库 | `/root/.pangu/pangu.db/v2_memories/`（`drawers.json` + `knowledge_graph.db`） |
| 旧版目录 | `/root/.pangu/`（v1）。**别读它** —— `KnowledgeGraph` 读 v2，读 v1 会得到「stats 报 19 实体、graph 返回 0」这类假象 |
| Python | `/root/pangu/.venv/bin/python`（3.13）。用 `.venv/bin/python -m pytest` |

**没有 CI 部署**（`.github/workflows` 里唯一的 deploy 是文档站）。所以「改了没生效」= 忘了 scp 或忘了 restart。

---

## 2. 怎么连、怎么发请求

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

## 3. 工具暴露面

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

## 4. 记忆模型（最容易误解的部分）

### 4.1 单用户，不做租户隔离

盘古是**单用户**的。代码里有 `tenant_id` / `visibility` / `classification` 三轴，但那是**多租户架构的预留能力**，业务上所有审核通过的平台共享全部记忆。

- 记忆的归属来自**平台 token**（`metadata.tenant_id` = 平台名，如 `deepseek-harness`、`opencode`）。
- 用 `api_key` 经 MCP 写入时，身份的 `room` **是空串** → 归属为 `''`。已修（见 §7），
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

## 5. LLM：动态模型 + 轮换

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

## 6. 自主任务

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
| `retrievability` | 24h | 可检索性体检，见 §8 |

共 15 个任务。带 `min_*` 的除间隔外还有「量够了才跑」的条件。

- 状态在 `/root/.pangu/pangu.db/v2_memories/autonomous_state.json`（只有 `last_run` 时间戳）。
- **`TaskResult.details` 不落盘** —— 任务跑完就没痕迹。需要留痕的任务得自己写文件
  （`retrievability` 写 `retrievability_report.json`）。
- `consolidation` / `crystallize` 走**无条件执行 + 任务内自检窗口**，不要给它们套 `_should_run` 的 24h 门，
  否则窗口外被标记 done 后会永远错过窗口。

---

## 7. 已知的坑（都是实测踩出来的）

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
6. **全量测试套件很慢**（几分钟才到 3%）。改完先跑受影响的子集，别等全量。

---

## 8. 可检索性体检（`retrievability` 自主任务）

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

## 9. 测试怎么跑

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

## 10. 维护日志

> 格式：`- **YYYY-MM-DD** — 改了什么 / 为什么 / 怎么验证的`
> **最新的一条在最上面。** 由 `tests/test_maintainers_doc.py` 核对最新日期。

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

## 11. 维护规矩

1. 改了 `pangu/**` → **同步更新本文件**，并跑 `tests/test_maintainers_doc.py`。
2. 查清「为什么这样设计」比「它现在坏没坏」重要 —— 上面 §0/§4/§5 那些坑都是这么来的。
3. 改数据前先备份；`merge_kg_duplicates.py` 是范例（dry-run 默认、事务、自动备份、幂等、校验）。
4. 定位到根因再动手。**注释和文档可能说谎**：今天就遇到
   `graph_data` 的 docstring 声称「已从豁免前缀中移除」，而代码里其实一直还在。
