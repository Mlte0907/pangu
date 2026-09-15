# 盘古 v0.3.0 方案（最新版，整合 P0-0 实测结果）

> 本文档已根据 P0-0 勘察与修复结果更新。P0-0 完成时间：2026-09-14。
> 历史版本见 git log（`428054f` 之后的所有 commit）。
> 本文档是**讨论稿**——所有结论都有实测证据；标注 ❓ 的需要你判断或
> 进一步调查；执行前须经确认。

---

## 0. 现状快照（2026-09-14，v0.2.0 收尾后）

| 维度 | 数值 | 证据 |
|---|---|---|
| 服务状态 | `active` / `uptime 25800s` | `systemctl --user is-active pangu-api` |
| 健康检查 | `status=ok` / `version=0.2.0` | `curl /health` |
| 默认工具数 | **28**（`tools/list` 实测） | curl POST `/mcp tools/list` |
| v2 记忆库 | **82 条** | `~/.pangu/pangu.db/v2_memories/drawers.json` |
| v1 旧库 | **0 条**（已废弃） | `~/.pangu/palace/drawers.json` |
| FTS 检索 | 查询"盘古"返回 **10 条** | REST fts 端点 |
| 测试套件 | **1476 passed / 0 failed / EXIT=0** | pytest 全量 |
| 累计改动 | 79 文件 / 777+/260- | `git diff --stat` |
| 已发布版本 | v0.2.0（HEAD = `428054f`） | `git log -1` |

**P0-0 已完成的修复**（v0.3.0 起点）：

1. **F2-b** env 覆盖名单从 2 字段扩到 6（+palace_path/identity_path/wiki_path/backup_dir），
   假 HOME 测试隔离可靠。
2. **B7 FTS 索引自锁**修复：warmup 权威化 + 空索引不落盘 + `int|None` 哨兵 +
   条数收缩守卫（`<50% 拒绝写入`）。
3. **7 模块 v1 硬编码**（context_injector/multimodal_search/quality/self_repair/
   auto_pilot/proactive_reminder/fuxi_bridge）改为走权威路径。
4. **74 文件 `PanguConfig.load()` 统一为 `.authoritative_memory_config()`**
   （覆盖 72/74 = 97%；仅 `knowledge_graph.py` 与 `migration.py` 故意不权威化，
   因为 KG DB 与迁移工具需在 v1 palace）。
5. **生产事故恢复**：v2 从 66→10→1 条 fb_min 灾难性回退 → 78→82 条干净记忆。

**核心结论**：盘古已**全功能正常运行**。v0.3.0 可以从"功能扩张"出发。

---

## 1. 回顾此前的判断（Q1–Q6，按 P0-0 后的事实重写）

### Q1：130+ 模块都真的运作起来了吗？

**真实答案：72% 已上线，28% 在 experimental 容器。**

- `pangu/memory/` 共 **132 个模块**
- 默认暴露面 **28 工具**（`pangu/core/config.py:CORE_WHITELIST`）
- 展开 `optional` + `experiments` 可达 **192 工具**
- 全开（`core` 全部 + `advanced` 容器）可达 **408 工具**（AGENTS.md 实证）

**P0-0 改变了判断**：此前我以为 132 个模块"读空文件集体失聪"。
P0-0 修复后，**所有 CORE_WHITELIST 28 工具的完整调用链都走 v2 权威库**。
"模块是概念"这一印象被推翻——模块是真实现的，是**路径分叉**让它们失聪。

剩下的 88 个非主链模块，需要在 v0.3.0 分类处置（见 P2-1）。

### Q2：我作为使用者，盘古真的方便我了吗？

**是。P0-0 后**：

| 收益 | 证据 |
|---|---|
| 跨会话不丢上下文 | 这次会话初始 `wake_up` 注入 ~1586 tokens，立刻给出"测试不能写 prod DB""计量对象错位 7 次"等历史结论 |
| 踩坑记忆救命 | 阻止了 B2 静默空写、B7 索引自锁等多处重蹈覆辙 |
| Token 节省 | 64 记录 / 110,039 字符 ≈ 36,700 tokens；单会话若查 10 次：`1586 + 10×550 ≈ 7,100`，**约 5× 节省** |

**但摩擦仍存在**：
- 写入**完全靠 agent 自觉**——`AGENTS.md` 反复强调主动写，本身就是依赖症状。
- 检索质量不稳仍待解决（P0-2）。
- 噪声"测试内容"压过真实记忆的现象，P0-0 期间**已清空生产库**（82 条干净），但算法层未改。

### Q3：真的省 token 了吗？

**省了 5×，但 P0-0 后** Pangu token 累计 **44,570+ tokens**。
检索质量越准，节省越显著（Q2 论证）。P0-2 是这个比值的瓶颈。

### Q4：自动捕获 = 好坏全进，怎么分辨对错？

**立场不变：不照搬 Hindsight 的自动捕获。**

Hindsight 的失败场景（写错→记入→改正→再记入→**两段并存**）在它的
模型里没有硬性解法（`retain` 追加式，`reflect` 靠 LLM 事后合成）。

盘古这边有现成三件套（**确实存在，未连接入检索链路**）：
- `pangu/memory/conflict.py` → `ConflictDetector` / `MemoryConflict` / `ConflictSeverity`
- `pangu/memory/versioning.py` → `MemoryVersionControl.record_version()` / `get_latest_version()`
- `pangu/memory/dedup.py` → `find_duplicates()` / `_vector_dedup(threshold)`
- `pangu/memory/reconsolidation.py` → `ReconsolidationEngine`（重新巩固旧记忆）

**关键问题**：这三件套**没接进检索链路**。现在写下相互矛盾的记忆，
两段都会留在库里、都会被我搜到——这正是你担心的现象，
**且它现在就在发生**（P0-0 期间 fb_min 灾难就是活案例）。

⇒ **"自动捕获"必须配"冲突治理"才能上。** 只抄 Hindsight 自动写入
而不建冲突消解，是把噪声规模化。P0-1 是这个前提。

### Q5：宿主覆盖——接上 MCP 不就通用了么？

**MCP 通用面已是事实**。`pangu/api/server.py:612` 用 streamable-HTTP，
任何支持 MCP 的宿主都能接（AGENTS.md 证实）。

Hindsight 写 60+ `*-hook.ts` 的真实原因是**它要 hook 注入 + 自动回写
transcript**，需要宿主专属适配。盘古不做自动回写，所以**确实不需要
逐个适配**。

⇒ **宿主覆盖对盘古不是问题**。真正需要适配的只有一件事：**自动捕获**（若要加）。
而这个可以**按需、逐个**加，不必一上来就 18 个。

### Q6：多后端不难吧？

**仍需勘察。** `pangu/core/llm.py` 的 provider 抽象已被验证可行
（`PROVIDER_ENV_KEYS` / `PROVIDER_URLS` / `_get_api_key()` / `_get_base_url()`）。

需要新增的是**存储后端**抽象（目前写死本地文件 + 可选 sqlite）。
`drawer_storage.py` 是集中入口，但 `vector_index.py` 是 numpy 暴力算
（无 faiss/hnswlib），后端若走网络会牵动检索路径。

❓ **执行前须先做代码勘察**：`drawer_storage.py` 与 `vector_index.py` 的
耦合程度决定工作量。未勘察前我不给工期承诺。

---

## 2. 方案（按优先级，含证据）

> **执行状态**（2026-09-15 更新）：
> - ✅ P0-1 `905251b`（supersede + 检索标注 + 双缓存 bug 修复）
> - ✅ P0-2 `fdfae8f`（长度惩罚 + FTS 权重 + 加密过滤）
> - ✅ P1-1 `a4a8942`（upgrade / uninstall / --server）
> - ✅ P1-2 `e0f395e`（文档新鲜度测试 6 条）
> - ✅ P2-1 `f2c6467`（3 模块接入：domain_knowledge / advanced_reasoning / batch_encode）
> - ✅ 缺口 1 `b462047`（supersede 暴露面修复）
> - ✅ 缺口 2 `e1830eb`（handle_add_memory 接入 remember() + REST update 修复）
> - ⏳ 缺口 3：judge 四问准入接入 remember()
> - ⏳ P1-3：按平台分房 + 毕业区机制
> - 🔍 P2-2：多后端（勘察完，暂缓）
>
> 执行顺序：缺口 1 ✅ → 缺口 2 → 缺口 3 → P1-3 → P2-2 暂缓

### P0-1　冲突治理接进检索链路　**〔必须先做〕**

**问题**：互斥记忆并存，检索时同时返回，AI 无法分辨哪条是新的。
这是 Q4 指出的、**当前正在发生**的缺陷（P0-0 期间 fb_min 灾难是活案例）。

**做法**：
1. 写入时（`add_memory`）调用 `ConflictDetector` 比对既有记忆；
2. 检出冲突时，**不静默并存**：给两条打上 `supersedes` / `superseded_by`
   关系，旧的那条在检索结果里**降权或标注**；
3. `search` 返回时对已 superseded 的记忆加显式标记（如
   `"⚠ 已被更新: mem_xxx"`），让我一眼看出该信哪条；
4. 用已有的 `versioning.py` 记录变更链，可回溯。

**验收**：构造"先写 A → 再写 ¬A"的场景，检索只应高亮 ¬A，
并明确指出 A 已被取代。**注入验证**：故意不修，断言必须失败。

**风险标注**：与 `dedup.py` 的现有逻辑可能重叠——需要先调研两者的
去重/冲突判定边界，**避免双重处理**。❓

### P0-2　检索质量：噪声不能压过信号　**〔必须先做〕**

**问题**：短文本 embedding 分数虚高。P0-0 期间 fb_min（"测试内容"）
在语义搜索里拿到 0.9488 排第一。生产已清空，但**算法未改**，
**下次噪声进入仍会重演**。

**做法**（需实测选型，三选一或组合）：
- 对过短记忆（字符数低于阈值，如 <20 字）加长度惩罚；
- 或降低 `visibility`/`importance` 为 0 的记录在语义通道的权重；
- RRF 融合时对 FTS 命中给更高权重（长文本才容易 FTS 命中）。

**验收**：构造短噪声（<20 字）+ 真长记忆，真记忆必须排前。
**注入验证**：故意不修，断言必须失败。

**风险标注**：阈值需实测选型（不同语料/embedding 模型敏感度不同）。
P0-0 已加 FTS 收缩守卫（防索引退化为子集），但**未改打分逻辑**。

### P1-1　安装体验（你明确要求的重点）

**目标**：`一行命令装完，且能自动升级`。参考 Hindsight 的三个安全默认：

| 做法 | 为什么值得抄 |
|---|---|
| 不给目标就什么都不做，只打印选项 | 避免"意外改遍全机" |
| `uninstall` 精确可逆，只删自己加的 | 用户敢装 |
| `--server` 参数化，可脚本化 | CI/自动化可用 |
| `autoUpdate` 默认开，后台静默升级 | 用户不用管版本 |

**盘古现状**（`install.sh` 实测）：
- ❌ **无 `uninstall`**（`grep -nE "uninstall" install.sh` → 无匹配）
- ❌ **无自动升级**（唯一 `upgrade` 出现在 `install.sh:150` 的
  `pip install --upgrade pip`，是装 pip 自己，不是升级盘古）
- ❌ 无 `--server` 类脚本化参数
- ✅ 已有 9 个函数定义，能生成 systemd unit（`install.sh:327-347`）

**自动升级的具体设计**（❓需你定策略）：
- 方案 A：`pangu upgrade` 子命令 + systemd timer 每日检查；
- 方案 B：启动时检查 GitHub release（不自动装，只提示）；
- 方案 C：完全自动（有风险，代码在跑时替换）。
我倾向 **A**：可控、可审计、符合盘古"本地优先"的定位。

### P1-2　文档新鲜度测试（我欣赏的工程纪律，直接可加）

Hindsight 的 `docs-freshness.test.ts` 让**文档过期就测试失败**。
盘古刚发生过实例：我把镜像 tag 写成 `v0.2.0`（实际是 `0.2.0`），
**没有任何测试能发现**。

**做法**：加一个测试，断言：
- `docs/` 里出现的镜像 tag 必须真实存在于 ghcr
  （或与 `docker-build.yml` 的 `metadata-action` 规则一致）；
- `pyproject.toml` / `pangu/__init__.py` / `README` 的版本号一致；
- 文档里提到的工具名必须真实存在于 `tools/list`。

**成本低、收益持续**。建议做。

### P1-3　共享 observation scope（你点名要的）

**Hindsight 的洞见**（我认同这条设计）：默认按 tag 分组会让
"同一个 repo 被两个 agent 做过"长出**两套互不相知的信念**，
而"是谁在打字并不改变约定是否为真"。他们用 `observationScopes: "shared"` 解决。

**盘古的对应问题**：记忆有 `wing`/`room`/`tenant_id` 分区。
多 AI 协作时，**同一主题的经验可能散在不同 room**，互相搜不到。
这次会话就有迹象：`tech/ci` 与 `tech/testing` 内容高度相关。

**做法（盘古版）**：
1. 引入 **"记忆作用域"** 概念，默认 `shared`：同一项目/wing 下的记忆
   **不分写入者**，检索时统一可见（现在其实已接近，但 `tenant_id` 会隔离）；
2. 保留 `per_tenant` 作为可选（多用户部署需要）；
3. **关键**：去重/冲突检测也应在 `shared` 作用域内跨写入者进行——
   否则两个 agent 会各自积累重复经验。

❓ 这里需要你确认：盘古是**单用户**定位还是要**多用户**？
这决定 `shared` 是默认还是可选。

### P2-1　模块瘦身／转正（回应 Q1）

~88 个不在主链路的模块（扣去 experimental 容器里的 ≈44 个 advanced），
需要**分类处置**，不能一刀切：

| 类别 | 处置 |
|---|---|
| 真有用但没入口（如 `git_hook`） | **接入**（挂到工具或生命周期） |
| 实验性、有独立价值 | 保留在 `experimental`，**明确标注**，不加测试 |
| 概念性、无实际调用 | **列出清单给你确认后删除** |

❗ 删除是不可逆操作，**必须逐个经你确认**，我不会自行删。

### P2-2　多后端　〔需先勘察〕

复用 `core/llm.py` 的 provider 抽象模式，新增存储后端（本地/S3/远端 API）。
❓ **执行前须先做代码勘察**：`drawer_storage.py` 与 `vector_index.py` 的
耦合程度决定工作量。**未勘察前我不给工期承诺。**

---

## 3. 我**不建议**做的（明确说清）

1. **不照搬自动捕获**。理由见 Q4：没有冲突治理的自动写入是把噪声规模化。
   **先做 P0-1，再考虑自动捕获**。
2. **不为宿主适配写 60 个 hook 文件**。MCP 已通用（Q5），
   只需按需给"自动捕获"加适配。
3. **不补 `advanced.py` 的覆盖率**（v0.2.x 已裁决）。
4. **不追 Hindsight 的 23.6k star 式扩张**。盘古的价值在本地、可审计、
   深度检索，不在宿主数量。
5. **不重做 P0-0 已修的路径分叉**。v0.3.0 起点是"全功能正常运行"，
   不要回退到"再修一次 wiring"。

---

## 4. 待你确认的决策点

| # | 问题 | 我的倾向 |
|---|---|---|
| 1 | P0-1/P0-2 是否作为 v0.3.0 的**前置必修**？ | 是，不做则自动写入不可上 |
| 2 | 自动升级策略选 A / B / C？ | **A**（`pangu upgrade` + timer） |
| 3 | 盘古是单用户还是多用户？决定 `shared` 是否默认 | ❓需你答 |
| 4 | P2-1 的"概念性模块"清单，你确认后我才删 | 先出清单 |
| 5 | 多后端先做勘察再定工期，是否同意？ | 是 |
| 6 | 执行顺序：P0-1 → P0-2 → P1-1 → P1-2 → P1-3 → P2？ | 建议如此 |

---

## 5. 执行方式建议

按你此前的偏好，**P0-1 与 P0-2 用 TeamsX 执行**：
- researcher 只读调研（现状 + 证据）
- engineer 按结论实现（限定路径）
- reviewer 独立复跑验收（不采信自述）

P1-2（文档测试）简单，可单独直接做。

---

## 6. P0-0 教训沉淀（影响 v0.3.0 设计）

为了让 v0.3.0 不再重蹈"大量模块像没运作"的覆辙，把这次教训固化：

| 教训 | v0.3.0 的应对 |
|---|---|
| **路径分叉静默失聪**——19 个文件各自拼路径，只有 2 个知道 v2 存在 | P2-1 模块瘦身时，**所有写盘模块必须走 `authoritative_drawers_path`**，否则不通过准入 |
| **"被 import" ≠ "被调用" ≠ "在默认暴露面内" ≠ "看到数据"** | 任何新模块接入前，**必须先给出 4 级证据链**（被 import / 被调用 / 在暴露面 / 看到真实数据） |
| **`except: return []` 静默空** 是最危险失败模式 | 引入守卫：空列表路径必须显式标注"空是有意 vs 异常导致"，并在 production 探针里区分两者 |
| **单向验证不够**——7 种 "should-block / should-allow / 异常行为" 都要测 | P0-1/P0-2 的验收必须三项齐全 |
| **U1 数据库污染：测试套件不应写生产 DB** | 已有 `clean_home` fixture + `0cd5ded` 修复（HEAD 之前）。新测试必须用 `FAKEHOME=$(mktemp -d)`，禁止依赖生产路径 |
| **teammate "claimed → completed" 必须先 in_progress** + 必须填 `acceptanceResults` | TeamsX 流程不变 |

---

**本文档未执行任何改动。** 等你确认后再动。
