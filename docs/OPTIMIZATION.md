# 盘古优化与迭代方向

> 本文档基于 **2026-09-13 对 v0.1.2 代码库的实地审计**，所有结论都有实测数据或
> 代码位置支撑。每条都标注了**证据**、**工作量估计**与**风险**，便于排期。
>
> 审计基线：`35bddd4`（v0.1.2 之后）、198 个 Python 文件 / 62,257 行 / 36 个测试文件。

---

## 摘要：五个最该做的事

| 优先级 | 事项 | 为什么现在做 | 工作量 |
| --- | --- | --- | --- |
| **P0** | 模型下载失败静默降级 → 检索质量静默错误 | 用户拿到"能跑但结果是错的"系统，零提示 | 0.5 天 |
| **P0** | 远程 Embed API 分支因缺 `aiohttp` 从未生效 | 配置了却静默无效，熔断语义被 ImportError 污染 | 0.5 天 |
| **P0** | 安装流程（12 分钟 + 三个认知陷阱） | 首次体验决定留存，且当前 README 数字失真 | 1 天 ✅已做 |
| **P1** | 向量检索全量重算，无增量索引 | 30 条记忆时无感，1000 条时每次检索 45 秒 | 3-5 天 |
| **P2** | 24 个死测试伪装成环境跳过 + 555 行死代码 | 掩盖真实失效，长期漏修 | 1 天 |

> 前两条**同属"静默失效"家族**：系统不报错、照常服务，但用户以为在用的能力
> 实际从未生效。这类缺陷比崩溃危险得多——崩溃会被发现，静默错误不会。

---

# 第一部分：安装流程优化

## 1.1 实测：安装到底要多久

所有数字均为**本机实测**（aarch64 / Python 3.12 / uv），不是估计值。

| 环节 | 实测 | README 宣称 | 差距 |
| --- | --- | --- | --- |
| `git clone --depth 1` | **13.4 秒** / 5.7 MB | — | — |
| 装依赖（**冷缓存**，56 包） | **8 分 10 秒** / 223 MB | 「约 20 秒」 | **24 倍** |
| ONNX 模型下载（源不可达时） | **3 分 26 秒**（白等） | 未提及 | — |
| **合计（最坏）** | **≈12 分钟** | — | — |

> **证据**：`uv pip install -r requirements.txt` 冷缓存实测 `real 8m9.598s`，
> 装出 `.venv` 223 MB；`du` 显示最大包为 `onnxruntime` 54 MB、`numpy` 55 MB、
> `uvloop` 16 MB、`pillow.libs` 16 MB。
> 模型下载用 `PANGU_ONNX_CACHE_DIR=<空目录>` 实测 `real 3m25.596s`，两个源均超时。

**README 的「20 秒」是错的**——那是 uv **全局缓存已存在**时的数字。用户第一次装
不可能有缓存。这个数字必须修正，否则用户会以为是自己环境有问题。

### 依赖安装无法显著加速，但可感知加速

56 个包 / 223 MB 中，`onnxruntime` + `numpy` 占 ~110 MB，都是必需的二进制。
真正能做的不是"变少"，而是：

1. **安装时给出进度与预期**（"正在下载 onnxruntime 54MB，约需 2 分钟"），
   避免用户以为卡死而中断 —— 中断是"缓存涨了但包没装上"这类事故的根源。
2. **uv 优先、pip 兜底**：实测 uv 冷装 8 分钟，pip 会更慢（无并行下载）。
   安装脚本应检测并提示 `uv`。
3. **可选：预置 wheel 缓存**（后续迭代，见 1.4）。

## 1.2 实测：三个让用户「弄很久」的认知陷阱

这三条是**安装体验的真正痛点**，比耗时更伤——用户不知道自己在做什么。

### 陷阱 ①：`8866` 与 `19529` 是两个完全不同的服务

| 端口 | 应用 | 入口 | 用途 |
| --- | --- | --- | --- |
| **19529** | `pangu/api/server.py:create_app()` | **❌ 无 CLI 命令** | MCP + REST（DSH 插件需要这个） |
| 8866 | `pangu/server/web_server.py:create_app()` | `pangu serve` | 人类可读的 Web 界面 |

- **证据**：`pangu/cli.py:1975-1998` 的 `serve` 启动 `pangu.server.web_server:create_app`（默认端口 8866）；
  `pangu/api/server.py:612` 挂载 `/mcp` 路由，**只有这套 app 有 MCP 端点**；
  `pangu/server/web_server.py` 全文无 `mcp` / `streamable` 字样（grep 为空）。
- **后果**：用户按直觉运行 `pangu serve`，打开 8866 看到界面，以为装好了；
  但 DSH 插件连的 19529 **根本没启动**，插件显示 `unreachable`。
- **`pangu CLI` 里没有任何命令能启动 19529**：`--help` 全部子命令中，
  `serve`→8866、`mcp`→stdio；19529 在 `self_improve.py:81` 仅作为**注释**出现。

### 陷阱 ②：`pangu` CLI 的存在感为零

CLI 有 30+ 子命令（`init` / `serve` / `mcp` / `search` / `stats` / `health` / `backup` …），
但 README「快速开始」**一个字都没提**。用户不知道 `pangu init` 能初始化数据目录。

### 陷阱 ③：systemd 服务单元未入库，用户无法复现官方部署

- **证据**：`git ls-files` 显示 `start.sh` **已入库**，但
  `.deploy-logs/DEPLOY-NOTES.md`（唯一记录 systemd 单元的地方）**未入库**
  —— `.gitignore:71` 排除了 `.deploy-logs/`。
- **后果**：仓库里没有任何 `.service` 模板（`find . -name "*.service"` 为空），
  用户想开机自启只能自己摸索。本机的单元还**写死了绝对路径**
  （`ExecStart=/home/xiaoxin/pangu/.venv/bin/python -c "..."`）。

## 1.3 方案：一键安装脚本 `install.sh`

新增仓库根 `install.sh`，把上述陷阱全部消除。设计要点：

```
install.sh [--port 19529] [--no-service] [--model-only] [--dsh-plugin]
```

| 能力 | 解决 |
| --- | --- |
| 环境自检（Python ≥3.11、uv/pip、磁盘空间） | 陷阱②、版本不一致 |
| 依赖安装**带进度与耗时预期** | README 20 秒误导 |
| **预下载 ONNX 模型**（含多源回退 + 失败明确报错） | 陷阱①、静默降级 |
| 生成 `.venv` + 写入 `~/.pangu` | 手工步骤 |
| **安装 systemd 用户服务**（路径自动解析，不写死） | 陷阱③ |
| 可选：调用 `install_dsh_plugin.sh` | 一体化 |
| **结尾醒目提示 19529 与 8866 的区别** | 陷阱① |

关键设计：**模型下载失败必须让脚本以非零码退出并明确告知后果**，
绝不静默继续（当前 `EmbeddingService.embed()` 的行为，见 2.1）。

### 实测验证结果

`install.sh` 已在干净副本上逐路径实测：

| 路径 | 结果 |
| --- | --- |
| 正常安装（模型已缓存） | ✅ 依赖 5s（热缓存）→ 模型复验通过 → 数据目录初始化 → 健康检查 OK |
| ONNX 模型下载失败 | ✅ **立刻中止，exit code = 1**，输出三种修复方案，不静默继续 |
| `--offline-model` 本地装模型 | ✅ 两文件正确落盘，复验 `model_loaded=True`、维度 384 |
| `--no-service` | ✅ 明确提示"未部署常驻服务"，不误报健康 |
| `--port` 自定义端口 | ✅ 单元文件与健康探测均按新端口 |
| 幂等重跑 | ✅ 已存在项跳过，不重复下载 |
| 未知参数 / 缺参数 | ✅ 报错退出 |

### ⚠ 实测中发现并修复的安全缺陷

初次测试"安装 systemd 服务"路径时，脚本**覆盖了本机正在运行的
`pangu-api.service`**（把它改成指向测试副本 `/tmp/inst_e2e/pangu_copy` 与端口 19531），
导致 19529 的生产服务被替换、DSH 插件连接中断。

- **根因**：脚本用 `cat > $UNIT_FILE` 无条件覆盖，无"已存在"检查；
  而 `~/.config/systemd/user/` 是**全局路径**，不随仓库副本隔离。
- **已修**：现在若单元已存在且其 `WorkingDirectory` 不等于本次 `REPO_DIR`，
  脚本**中止并明确告知**，需 `PANGU_REPLACE_SERVICE=1` 显式确认才覆盖。
- **教训（对后续所有部署脚本适用）**：破坏性操作必须**默认拒绝 + 显式 opt-in**。
  这类脚本在副本里测试时，凡写全局路径（systemd unit、`~/.pangu`、`/etc`）
  的分支都不能当作"隔离测试"。
- 另修：健康探测原先只看端口是否有响应，而**旧进程占着端口会误报成功**；
  现增加"用本次 `.venv` 构造 app"的直接校验。

## 1.4 后续迭代（不在本次范围）

- **预置 wheel/模型缓存分发**：把 223 MB 依赖 + 23 MB 模型打包成离线包，
  供内网/弱网环境。收益显著但需存储与分发渠道。
- **`pangu serve --api`**：给 19529 加正式 CLI 入口，彻底消除陷阱①。
  工作量约 0.5 天，建议在 1.3 之后紧跟。
- **Docker 作为首选路径**：镜像已支持 amd64+arm64（实测 `installing: arm64 OK`），
  但 README 把源码安装列为第一选择。镜像可省掉全部依赖安装耗时。

---

# 第二部分：代码与架构优化

## 2.1 【P0】模型下载失败时静默降级，检索质量静默错误

**这是本次审计发现的最严重缺陷**——比安装慢严重得多。

### 现状与证据

`pangu/memory/embedding.py` 的 `_call_api()` → `_onnx_embed()` → `_local_embed()`
构成降级链，最终 `_local_embed()` 返回 **hash 向量**（字符级，无语义能力）。

实测（`PANGU_ONNX_CACHE_DIR=<空目录>`，两个源均超时）：

```
Download failed: https://hf-mirror.com/... → _ssl.c:993: The handshake operation timed out
Download failed: https://huggingface.co/... → timed out
嵌入维度: 384                              ← 仍然"成功"返回！
onnx 状态: {'model_loaded': False, ...}    ← 只有这里能看出问题
```

降级后的相似度实测（hash 向量的真实语义能力）：

| 词对 | cos 值 | 说明 |
| --- | --- | --- |
| 猫 / dog | 0.0000 | 完全无语义 |
| 猫 / 猫咪 | 0.7071 | 字符巧合，非理解 |
| 股票 / 股市 | 0.5000 | 字符巧合 |
| 猫 / 股市 | 0.0000 | — |

### 为什么危险

- `embed()` **不抛异常**、返回**合法的 384 维向量**，所以
  `vec is not None` 与 `len(vec) == 384` **都无法检测** ONNX 失败；
- 服务正常启动、API 正常返回、检索**也返回结果**——只是结果全错；
- 日志里只有一条 `Download failed` 一闪而过，而日志此前长期未初始化
  （v0.1.2 已修 `cae7e7d`），用户更不会注意；
- **v0.1.2 修的 CI ONNX 测试假失败**（`f0f03ec`）是同一根因的另一处表现：
  当时 CI 上 `model_loaded=False` 却是 `1329 passed`，只因断言恰好碰对了。

### 附带发现：降级链第一级（远程 API）结构性不可达

审计中发现一个**独立的、同样严重**的问题：

- `pangu/memory/embedding.py:224` 与 `:270` 在函数内部 `import aiohttp`，
  但 **`aiohttp` 未安装、且未在 `pyproject.toml` / `requirements.txt` /
  `requirements-dev.txt` 任何清单中声明**（三份清单 grep 均为 0）。
- **实测**：配置 `embed_api_url='https://example.invalid/v1/embeddings'` 后调用
  `_call_api('hello')` → `Embed API failed (1): No module named 'aiohttp'` → 返回 `None`；
  `_call_api_batch(['a','b'])` → `[None, None]`。
- **含义**：三级降级链（`_call_api` → `_onnx_embed` → `_local_embed`）的 **API 分支
  在此环境永远走 `ImportError` 兜底**，而不是 HTTP 错误路径。circuit breaker 的
  `_fail_count >= 5` 由 `ImportError` 触发，而非网络故障——**熔断器的语义已被污染**。
- 若用户指望用远程 embed API（有些部署会这么配），**它从未生效过，且没有任何提示**。
- `tests/` 对 `_call_api|circuit|half_open` grep **零命中** —— 整条错误链无测试。

> 修法二选一：
> 1. 把 `aiohttp` 加为正式依赖；或
> 2. **改用 `httpx`（推荐）**——`httpx>=0.27.0` 已是正式依赖
>    （`pyproject.toml:25`），venv 中实际为 0.28.1，且**同仓库已有范例**：
>    `pangu/memory/onnx_embedder.py:140` 就是用它下载模型的。
>    同项目内统一到一个 HTTP 客户端也减少依赖。
>
> 无论哪种，**都要补测试**：断言 `_fail_count` 增长与熔断状态转换
> （当前 `tests/` 对 `_call_api|circuit|half_open` grep 零命中）。

### 建议修法

| 方案 | 说明 | 取舍 |
| --- | --- | --- |
| **A. 启动即失败**（推荐） | `lifespan` 中校验 `model_loaded`，失败则拒绝启动并给出修复指引 | 最安全，但弱网环境完全不可用 |
| **B. 降级但显式**（推荐组合） | `/health` 返回 `status: "degraded"` + `embedding_backend: "hash"`，日志 ERROR 级 | 保留可用性，可被监控发现 |
| C. 允许显式降级 | 新增 `PANGU_ALLOW_HASH_FALLBACK=1`，默认关闭 | 需 A 或 B 打底 |

**推荐 A+B 组合**：默认拒绝启动（附明确修复指引），环境变量显式允许时降级
且 `/health` 上报 `degraded`。插件的 `healthScore` 逻辑（`lib/index.js:105`）
已支持 `degraded` → 70 分，可直接受益。

> 注意：`ONNXEmbedder.get_stats()` 的 `model_loaded` 是**实时读取**
> （`onnx_embedder.py:365-377`：`self._session is not None and self._tokenizer is not None`），
> 可以放心作为判据；而 `EmbeddingService` 层面的降级信息需要另行透出。

## 2.2 【P1】向量检索全量重算，无增量索引

### 现状与证据

`pangu/memory/fts_search.py:270` 的 `_vector_search()`：

```python
items = [{"id": d.id, "content": d.content} for d in drawers]   # ← 全部候选
scores = self._try_batch_embed(query_vec, items)                 # ← 每次全量推理
```

**每次检索都把全部候选重新向量化**，性能完全依赖 `ONNXEmbedder._cache` 兜住。
实测开销约 **45 ms/条**（1000 条 → 45 秒，见 `mem_tech_aac5d7d38acb4098`）。

### 问题

- 缓存是**进程内内存**，重启即失效 → 这正是 v0.1.2 修的"首次搜索 50 秒"的根因
  （已在 `a5f8654` 用预热缓解，但**没解决架构问题**）；
- 新增记忆时**没有增量索引**，cache miss 会触发新文本推理；
- **`pangu/memory/vector_index.py` 实现了完整的 `VectorIndex`（FAISS/HNSW/numpy）
  却不在检索路径上**——只被 `pangu/server/handlers/embed.py` 的两个 MCP 工具引用
  （`pangu_vector_index_stats` / `pangu_vector_index_build`）。

这是典型的**已有轮子没装上**：索引能力写好了，但 `search()` 没用它。

### 建议

把 `_vector_search` 从"全量重算"改为"查索引"：

1. 记忆写入时增量 upsert 向量到 `VectorIndex`；
2. 检索时 `index.search(query_vec, k)` 取代全量 `embed_batch`；
3. 保留全量重算作为**索引未就绪时的回退**；
4. 索引持久化到磁盘，避免重启后重建。

风险：`VectorIndex` 需要先验证其正确性与当前后端选择逻辑（FAISS 是否已装？
numpy 后端在 1000+ 规模下是否够快？）。**建议先写基准测试再改**。

## 2.3 【P2】测试盲区

> 本节的覆盖率数据由独立审计子代理实测产出，详见其报告。
> 已知的**测试基础设施**问题：

- **wall-clock 阈值断言**（**8 处**，比预想的多）：最危险的是
  `tests/test_performance_optimizations.py:51` 的 `avg_time < 0.1`
  —— **亚毫秒级阈值**，任何 CI 抖动即失败。同类还有 `:65 <2`、`:119 <50`、
  `:147 <20`、`:176 <100`、`:177 <1`（实测出现过 `1.59ms` flake，单独跑 3/3 通过），
  以及 `test_bench.py:332`、`test_boundary_cases.py:780`、`test_llm_optimizations.py:570`。
  建议改**相对比较**（A/B 比值）或大幅放宽阈值。
- **测试基础设施四项全缺**（`pyproject.toml:103-110` 的 `[tool.pytest.ini_options]`
  只有 `testpaths` / `asyncio_mode` / 3 个 marker）：
  无超时、无随机顺序、无 xdist、无 flaky 重试。
  后果：**顺序固定 → 状态泄漏不会被暴露；无超时 → 单个挂起用例拖满 9 分钟**。
  当前靠 `tests/conftest.py` 两个 autouse fixture（`_isolate_pangu_cache`、
  `_reset_vector_index_singleton`）手工兜底，属"靠约定而非机制"。
- **`collect_ignore_glob`** 必须放在 `tests/conftest.py`（不是 `pyproject.toml`）。

### 24 个"永久死测试"伪装成环境问题

`tests/test_v3_modules_f.py` 的 4 个测试类共 **24 个方法永久 skip**：

- **证据**：`:394-398` 用 `try: from pangu.memory.auto_collector import ... / except ImportError`
  设 `AUTO_COLLECTOR_AVAILABLE = False`，4 个 `setup_method`（`:403,451,486,518`）据此 skip。
  实测 `.venv/bin/python -m pytest tests/test_v3_modules_f.py -q -rs`
  → `119 passed, 24 skipped`，skip 原因全是 `auto_collector module not available`。
- **真相**：`pangu/memory/auto_collector.py` **根本不存在**（`ls` 报 No such file），
  全库仅 1 处引用（就是这个测试）。即这 24 个测试**从未可能通过**。
- **危害**：写法让 pytest 报告显示为"环境缺失"而非"测试已失效"，
  容易被误读成 CI 环境问题而**长期漏修**。建议：要么补模块，要么删测试，
  但**不要用运行时 try/except 掩盖**——应改成模块顶层的直接 import，
  让它立刻失败暴露。

### 覆盖率口径诚实性问题

- 全库实测 **62.8%**（24158 stmts / 8982 miss），门槛 60%。
- **但 omit 列表（`pyproject.toml:131-173`，40 项）排除了 `pangu/cli.py` 与
  39 个实验模块 —— 排掉的恰是复杂度最高处**。omit 本身**确实生效**
  （端到端验证：import omit 内模块后跑 `coverage run`，其不出现在报告中）。
- **26 个模块「既无测试又计入分母」**，其中 `handlers/advanced.py`
  （2129 行，36.9%）是最大单点缺口。
- **`pangu/memory/knowledge_extractor.py`（555 行）是彻底的死代码**：
  零测试引用、**零源码引用**、不在 omit、未在 `__init__` 导出，
  且文件末尾 `:544` 有 `main()`（像是独立脚本误入包内）。
  这不是"未覆盖"，而是"没接线"——应先确认是否该删或该接。

> 方法论提醒：覆盖率报告要用 `coverage report --sort=cover` 单独出表；
> 原命令尾部 `tail -80` 恰好会**截掉覆盖率最低的那批模块**，导致误判。

## 2.4 【P2】代码质量

- **超长文件**（拆分候选）：`pangu/cli.py` 2274 行、`handlers/advanced.py` 2129 行、
  `core/llm.py` 1415 行、`api/server.py` 1129 行。
- **`docs/getting-started/installation.md` 与 `pyproject.toml` 冲突**：
  前者写 `Python >= 3.10`，后者 `requires-python = ">=3.11"`。
  用 3.10 的用户会被 pip 直接拒绝，但文档说可以。
  另：该文件还引用 `github.com/xiaoxin/pangu`（实际是 `Mlte0907/pangu`）
  与 `pip install pangu`（**未发布到 PyPI**）、`docker pull ghcr.io/xiaoxin/...`
  （实际是 `ghcr.io/mlte0907/...`）—— **三处错误引用**。

## 2.5 【P3】DSH 插件侧

- **`PANGU_BASE` 硬编码**（`plugins/dsh-pangu/lib/index.js:27`）：
  `const PANGU_BASE = 'http://127.0.0.1:19529'`，端口/地址不可配。
  多实例或改端口场景下插件直接失效。
- **无自动拉起服务能力**：插件不检测也不启动 19529，失败只标记 `unreachable`
  （`lib/index.js:107`）。用户需自行保证服务在跑。
- **HMR 不生效**：`cordis.patch.yml` 的 HMR 在 web 实例无效，改后必须重启 DSH。

---

# 第三部分：迭代路线建议

| 版本 | 主题 | 内容 |
| --- | --- | --- |
| **v0.1.3** | 可用性兜底 | 2.1 静默降级（P0）、远程 API 分支修复（P0）、1.3 一键安装脚本 ✅、1.4 `pangu serve --api` |
| **v0.2.0** | 检索架构 | 2.2 增量向量索引接入检索路径（**性能与正确性的真正提升**） |
| **v0.2.x** | 测试与清理 | 2.3 死测试清理 + 基础设施补全、2.4 文档修正（含三处错误引用）与文件拆分 |
| **v0.3.0** | 插件自治 | 2.5 插件可配置化 + 服务自动拉起 + 多实例支持 |

## 判断依据

- **v0.1.3 优先做 P0**：静默降级会让用户对系统产生**错误信任**，
  这比功能缺失危险——用户会以为检索是对的，直到发现召回全是噪声。
  同版本内一并修 `aiohttp` 缺失（同为"配了却不生效"）。
- **v0.2.0 做检索架构**：当前 30 条记忆无感，但这是**规模化的硬门槛**。
  1000 条时每次冷缓存检索 45 秒，完全不可用。
- **v0.2.x 清理优先于新功能**：24 个死测试 + 555 行死代码是**认知负担**，
  每新增一个贡献者都要重新踩一遍。清理成本低（1 天），收益是账目诚实。
- **不建议现在做**：`vector_index` 已有实现，先测量再决定是否需要 FAISS
  （引入 FAISS 会增加安装体积，与 1.1 的安装优化目标冲突）。

## 已在本轮完成

| 项 | 状态 | 交付物 |
| --- | --- | --- |
| 一键安装脚本 | ✅ 已提交 `0b4b916` | `install.sh`（7 条路径实测通过） |
| README 数字修正 + 两服务对照表 | ✅ 已提交 | `README.md` |
| 本方案文档 | ✅ 已提交 | `docs/OPTIMIZATION.md` |

## 尚未做（用户已明确"先不动，写进方案排优先级"）

- 2.1 静默降级修复 —— **文档已详述，代码未改**
- 远程 API 分支（`aiohttp`）修复 —— 同上
- 其余全部条目 —— 均只做分析与排序，未改动代码

---

## 附录：本次审计的实测命令

```bash
# 冷缓存依赖安装耗时
UV_CACHE_DIR=$(mktemp -d) uv pip install -r requirements.txt --python .venv/bin/python

# 模型下载失败路径（不影响本机真实缓存）
PANGU_ONNX_CACHE_DIR=$(mktemp -d) .venv/bin/python -c "
from pangu.core.config import PanguConfig
from pangu.memory.embedding import EmbeddingService
svc = EmbeddingService(PanguConfig.load()); svc.embed('测试')"

# 降级后的语义能力（hash 向量）
# 见 2.1 表格，cos(猫,dog)=0.0000

# 服务边界确认
grep -n "def serve" -A 20 pangu/cli.py            # → web_server, 8866
grep -n "mcp_http_routes" pangu/api/server.py     # → 612, 仅 api/server 有 /mcp
grep -n "mcp" pangu/server/web_server.py          # → 空
```
