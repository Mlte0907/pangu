# Changelog

All notable changes to Pangu will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

> 版本号以 `pyproject.toml` 与 `pangu/__init__.py` 的 `__version__` 为唯一事实源。
> 本文件此前的 `v1.0.0` 标题是「分层共存重构」时期的旧称，代码侧已在
> commit `ac563b4`（unify all version strings to 0.1.0）统一为 `0.1.0`，此处同步更正。
> 自 `0.4.1` 起 `plugins/dsh-pangu/package.json` 与上述两者保持同一版本号，
> 设置页「关于与更新」显示的插件版本即读自此文件。

## [Unreleased]

### 安全：REST 网关接入钥匙体系，老网页退役

- **REST 全面要求凭据**（`mcp_require_auth=true` 时）：`_AuthMiddleware` 启用条件
  增加 `mcp_require_auth`；`/api/v2/memories`、`/api/v2/graph`、`/api/v2/tools*`、
  `/api/v2/autonomous/status` 不再豁免，无凭据一律 401。凭据三选一：盘古钥匙
  （pgk_，与 MCP 同一张钥匙表，租户＝room）、静态 api_key、JWT。`/ws` 握手同样
  接受 pgk_ 钥匙。豁免名单收窄为探针（/health*、/metrics）、文档（/docs*）与
  登录（/api/v2/auth/*）；`/api/v2/admin/*` 仍走自己的 X-Admin-Key 自保护。
- **老网页退役**：`/`（重定向保留）、`/dashboard`、`/graph`、`/performance` 中的
  三个 HTML 页面与路由删除（`pangu/ui/templates/` 清空）。它们是无钥匙直连 REST
  的唯一消费者，也是此前豁免名单存在的原因。
- **dsh 插件适配**：宿主侧 `fetchJson` 给所有发往盘古本机的请求（/mcp、/health、
  /api/v2/graph）自动带 `X-API-Key`；发往外部 LLM 端点（/v1/usage）的请求依旧
  不带，防钥匙外泄。

## [0.4.1] — 2026-09-17

dsh 插件（0.1.6 基座）兼容与可用性修复 + 版本号统一。**无破坏性变更**。

### 版本号统一（0.3.0 / 1.4.0 → 0.4.1）

- `pyproject.toml` 的 version、`pangu/__init__.py` 的 `__version__`（`/health` 自报）
  与 `plugins/dsh-pangu/package.json` 的 version 原来各不相同（0.3.0 / 0.3.0 / 1.4.0），
  设置页还另有一个写死的 `v1.5.0`。现全部对齐到 `0.4.1`。
- 插件设置页「关于与更新」不再显示硬编码版本：本地插件版本读 `package.json`、
  盘古服务版本读 `/health`，GitHub Release 仅标注为「上游发布，仅供参考」。

### 插件修复（`plugins/dsh-pangu`）

- **设置页整段不显示**：`updateInfo` / `updateLoading` 状态残留在 `AdminPane`，
  而使用它们的更新检查 UI 已在 `PanguSettings`，渲染时抛 `ReferenceError`，
  槽位条目崩溃（控制台 `slot entry crashed in 'settings.section'`）。状态移回
  `PanguSettings`（`5ed3b0f`）。
- **`/api/panguDashboard/checkUpdate` 404**：宿主 Typert 清单缺该 invocation 与
  `CheckUpdateResult` schema，已补齐（`5ed3b0f`）。
- 钥匙创建/重发响应缺明文字段时改为大声报错，避免静默丢钥匙（`309d6b3`）。
- 客户端 `DESCRIPTORS` 补 `checkUpdate`，`apply()` 加 try-catch（`2a9413d`）。

### 运维规范

- 新增 `dsh-restart`（`~/.local/bin/`）作为 dsh-web 的唯一重启入口：先清掉占用
  3080 的孤儿进程，再执行 `sudo -n /usr/bin/systemctl restart dsh-web.service`
  （sudoers 仅精确放行全路径 + 全单元名），最后校验新主进程持有端口。
  手工 `node ... web &` 产生的孤儿会让 systemd 进入 `EADDRINUSE` 崩溃循环、
  界面停留在旧代码——即本次设置页问题的现场成因。详见 `DSH-WEB-OPS.md`。

## [0.3.0] — 2026-09-16

记忆治理第一阶段 + 多平台接入第二阶段落地。**无破坏性变更**；新增 opt-in 的 MCP
准入鉴权（`mcp_require_auth`，默认 `false`）。

### 权威路径（P0-0）

- 记忆读写统一到**唯一权威路径** `db_path/v2_memories`（`PanguConfig.authoritative_drawers_path`）。
  此前全仓 49 处 `MemoryStack(...)` 只有 API 与 MCP 两处指向 v2，其余（CLI 34 处、
  routes_memory、web_server、warmup、autonomous 维护）都读 v1 空库，导致同一进程内
  「两条路径给出两个答案」、自主维护连续空转 81 次。`palace_path`（v1）保留作迁移输入。

### 记忆治理（P0-1 / P0-2 / 缺口 1-3）

- **P0-1 冲突治理接进检索链路**（`905251b`）：supersede 语义 + 检索结果标注 + 双缓存 bug 修复。
- **P0-2 检索质量**（`fdfae8f`）：长度惩罚 + FTS 权重 + 加密内容过滤。
- 缺口 1：supersede 暴露面修复（`b462047`）；缺口 2：`handle_add_memory` 接入
  `remember()` 全管道 + REST update 路径改用 `update_drawer`（`e1830eb`）；
  缺口 3：judge 四问准入接入 `remember()`（`d9748ce`）。

### 平台分房（P1-3）

- 按平台分房 + 毕业区（`cb6a4ab`）：写入打 `metadata.tenant_id`，读取按 `tenant_id`
  （或 `visibility=public`）预过滤；`source_session` 全链路贯通（`cf325f0`、`f041981`）。
- **租户语义默认为 `per_tenant`**（多用户定位）：不同钥匙（房间）之间互不可见；
  `shared`（同一 wing 内不分写入者、统一可见）保留为可选。
- MCP 身份解析：`X-API-Key` → 钥匙表 → `{key_id, room, scope}` 注入 `msg["_identity"]`，
  再经 `server/mcp_server.py` 桥接进 handler 参数（阶段 1.4；读取侧消费于阶段 2.2，
  过滤轴由 `Drawer.room` 改为 `metadata.tenant_id`，`69802bb`）。

### 钥匙与准入（第二阶段 阶段 1 / 2 / 3）

- 钥匙管理 CLI + REST 管理端点 + 房间隔离迁移脚本（`3db075b`、`3dc458a`、`a6c9b5a`）。
- **MCP 准入鉴权 `mcp_require_auth`（opt-in）**：为 `true` 时 `/mcp` 无凭据或无效钥匙
  返回 401。配套的 dsh 插件凭据链路：客户端改发 `X-API-Key`、服务端兼容
  `Authorization: Bearer`、凭据解析 `PANGU_API_KEY` > `config.json:api_key` >
  `~/.pangu/.mcp_key`(0600)（`9f37ca4`）。
- **dsh 入住完成**：钥匙 `room=dsh`（0600 落盘、明文不入日志/会话），鉴权已开启，
  三条 MCP 路径（配置页 / 注入通道 / 工具调用）均以 `keys.json:last_used_at` 取证。

### 安装与运维（P1-1 / 阶段 0）

- `pangu upgrade` / `pangu uninstall` / `--server`（`a4a8942`）；restart-and-verify + timer +
  consolidate 压缩 + eval_report（`f5e9b4b`）。

### 文档纪律（P1-2）

- 文档新鲜度测试 6 条（`e0f395e`）：版本号三处一致、README 不得残留过期版本号、
  ghcr 镜像 tag 不得带 `v` 前缀、文档提到的 `pangu_*` 工具名必须真实存在、
  CHANGELOG 必须含当前版本条目。

### 宿主兼容（DSH 0.1.6-alpha.1）

- dsh-pangu 插件：typert.host 清单、CJS 化、客户端清单 `create:` 工厂迁移、
  `typertRemote` 绑定补回（`b39367e`…`c8fd105`）。
- dsh-teams-x：会话生命周期事件双基线注册（0.1.5 `agent/session-start` /
  0.1.6 `agent/created`），并以显式监听器签名转型保住 peerDep 下限。

### 已知问题

- **AMD Radeon 网关上游故障**：`developer.amd.com.cn/radeon/api/v1` 当前对
  `/v1/chat/completions` 与 `/v1/models` 一律返回 `502 Model gateway is unavailable`
  （主机可达、TLS 正常）。非本仓库问题，但会拖累依赖 LLM 的能力（结晶 / 蒸馏 / 摘要）。
- `llm_fallback_models` 仍为 OpenAI/Anthropic 模型名（`gpt-4o-mini`、`claude-3-haiku`），
  在该网关上不存在，网关故障期间回退链无效。
- ghcr 镜像 tag 仍为 `0.2.0`（0.3.0 镜像未构建发布），故 `docs/` 内镜像引用保持
  `0.2.0`，避免指向不存在的 tag。

## [0.2.x] — 2026-09-13

清理测试债务与生产死代码。**无破坏性变更，无 API 改动。**

### Security / Data-integrity — 测试套件写入生产数据库（重要）

**这是一个长期存在的严重缺陷：跑 `pytest tests/` 会直接写入用户真实的
`~/.pangu` 数据库。**

根因链条：

1. 测试用 `monkeypatch.setenv("PANGU_DB_PATH", tmp_path)` 隔离
   （`tests/test_e2e_rbac_abac.py`）；
2. 但 `create_app()` 会调 `PanguConfig.load()` 读真实 `~/.pangu/config.json`，
   再把**文件里显式写明的每个字段** `setattr` 回全局单例 `config`
   —— 而该文件显式写着 `"db_path": "~/.pangu/pangu.db"`；
3. `pangu/api/server.py` 的 `_build_memory_store()` 用
   `Path(config.db_path) / "v2_memories"` 定位 MemoryStack 的存储。

⇒ 环境变量的隔离被覆盖回生产路径，测试读写真库。实测：跑一条
`test_cross_tenant_list_isolated` 就让生产库 drawers **108 → 111（+3）**；
本轮全量测试期间从 **69 涨到 118**。

**二次症状（易被误判为业务 bug）**：该用例断言 bob（globex）看不到 acme 记录
而失败。但过滤逻辑本身是**正确的**——`routes_memory.py:201` 为
`if vis == "public" or d_tid == subject.tenant_id`，**按设计允许 public
跨租户可见**。失败的真实原因是隔离库被累积污染，破坏了"库中只有本次写入"
这一前置条件。

修复：

- `pangu/api/server.py`：新增 `_ENV_OVERRIDABLE_PATHS = ("db_path", "base_dir")`。
  只要调用方显式设置了 `PANGU_DB_PATH` / `PANGU_BASE_DIR`，就**跳过**
  config.json 对该字段的覆盖（与 pydantic-settings 的 `env > 文件` 优先级一致）。
- `tests/conftest.py`：新增 autouse fixture `_isolate_pangu_data_dir`，
  同时隔离 `PANGU_BASE_DIR` 与 `PANGU_DB_PATH` 并逐用例复位 config 单例。
  ⚠ **只设 `PANGU_DB_PATH` 不够**（`base_dir` 才是派生路径的根）。

验证：`pytest tests/ -q` → **1416 passed / 16 skipped / 0 failed**；
跑全量前后生产库 drawers **118 → 118（零写入）**；生产 systemd unit 未设
这两个变量，`config.json` 语义完整保留（实测 `db_path` 仍解析为
`~/.pangu/pangu.db`）。

### Fixed — CI 工作流分支不匹配（`main` vs `master`）

`docker-build.yml` / `docs.yml` / `release-drafter.yml` 的触发器与 `if`
条件写的是 `main`，而本仓库默认分支是 **`master`**，导致：

- `docs.yml` 与 `release-drafter.yml` 的 `gh run list` 历史为**空**——
  **从未运行过一次**（文档站从未自动部署）；
- `docker-build.yml` 在分支 push 时从不触发，仅靠 tag / 手动 dispatch；
- `docs.yml` 的 deploy 门禁 `github.ref == 'refs/heads/main'` **永假**。

已全部改为 `master`，并在 `.gitignore` 加入 `site/`（mkdocs 构建产物）。
验证：`mkdocs build --strict` 本地实测通过（exit 0），三份 workflow YAML
均 `yaml.safe_load` 合法。

### Changed — v0.2.x 剩余项裁决（记录为"不做"，含依据）

- **2.3 `handlers/advanced.py` 覆盖率 → 不补测**：该模块在
  `module_registry.py:174` 登记为 `experimental` 层，默认 `tools/list`
  的 28 个工具**不含其中任何一个**（默认部署下用户不可达），为 121 个
  不可达 handler 补测只是覆盖率数字工程。
- **2.4 文件拆分 → 不拆分**：四个大文件（`cli.py` 2319 行等）是
  "大而内聚"而非"大而混乱"；而 `pangu.cli:app` 与 `api.server:create_app`
  是**契约入口**，且 `core/llm.py` 有 **32 处**外部引用（含以模块对象方式
  monkeypatch 的 `test_warmup_audit.py:19`），拆分易引入静默失效。
  将来若某文件因**具体缺陷**难以维护，届时针对该文件拆分。

### Fixed — 性能测试墙钟断言间歇失败（flake）

`tests/test_performance_optimizations.py` 中 6 处墙钟断言在负载或降频时
间歇失败。根因经实测确认是**四层问题叠加**，而非单纯的"机器慢"：

1. **缓存命中被当成真实搜索**：`hybrid_search` 有 `search_cache`
   （`pangu/memory/search_cache.py:28`，key 仅含 query/modalities/limit，
   **不含 drawers**），同一 query 重复测量只会量到约 0.003ms 的缓存命中；
2. **均值采样**：被抢占或降频的轮次会被算进均值；
3. **冷启动混入**：query 嵌入走惰性单例（`hybrid_search.py:110`），
   未预热 52~54ms vs 预热后 8~10ms，相差 5 倍；
4. **阈值低于真实成本**：L255 实测 min≈49.6ms 而阈值为 50ms，
   余量仅 1.005 倍——min-of-N 只能剔除噪声，剔不掉真实成本。

修法：统一改为 **min-of-N** 采样（配合显式预热 embedder 单例与
每轮使用互不相同的 query），并新增护栏
`assert min(samples) > 0.5`，防止日后有人写成同一 query 循环
导致 min 塌缩到缓存命中值、断言静默失效。

阈值调整仅限于成本测量本身有误的两处：

| 断言 | 调整 | 真实成本 |
| --- | --- | --- |
| L255 混合搜索 | 50ms → **125ms** | min≈49.6ms |
| L324 混合搜索 | 20ms → **100ms** | min≈46.7ms |

二者测量的是同一成本项（一次 ONNX query 嵌入）。其余红线
（`0.1` / `2` / `100` / `1`）保持原值不动。

> 曾有放宽到 150ms 的提议，实测否决：注入 60ms 延迟后实录 106ms，
> 在 150ms 阈值下**仍然通过**，即该放宽会让回归漏网。

### Fixed — 24 个"永久死测试"

`tests/test_v3_modules_f.py` 用 `try/except ImportError` + 4 处
`pytest.skip` 包裹 `experimental.auto_collector` 的导入，把硬失败
变成了静默跳过。实际导入路径写错了：模块自始就在 `experimental/`，
`pangu.memory.auto_collector` **从不存在**。改为模块顶层直接导入后：

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 通过 | 119 | **143** |
| 跳过 | 24 | **0** |

已用缺陷注入验证这 24 条确会失败（是"救活"而非删除）。

### Fixed — `pangu_auto_collect` 双重损坏

该工具在默认核心工具集中可达（`io_tools` 属核心模块，
`pangu/server/module_registry.py:159`），但调用必然失败：

- 导入写的是相对路径 `from ...memory.auto_collector import ...`，
  解析到 `pangu.memory.auto_collector`——该模块**从未存在**；
- 即便导入成功，所调用的 `collect_from_file` 也不存在，
  `AutoCollector` 只有 `collect_from_session`。

修复为延迟绝对导入 + 修正方法名，并让导入失败时返回显式 error，
而非静默返回空结果（避免"没有采集到"与"功能完全不可用"无法区分）。
新增 `tests/test_auto_collect_handler.py`（5 条回归测试）。

### Added — systemd unit 模板

新增 `systemd/pangu-api.service`，使用占位符
（`__REPO_DIR__` / `__VENV_PYTHON__` / `__HOST__` / `__PORT__` / `__LOG_DIR__`），
不含任何机器特定路径，供手工部署参考。

> 注意：`install.sh` 自带 heredoc 生成 unit（`install.sh:327-347`），
> **不读取本目录**，故新增该模板不影响安装流程。

### Changed — 移除死代码 `pangu/memory/knowledge_extractor.py`

555 行、**零引用**（不在 `__init__` 导出、非 entry point、
全库除自身 logger 名外无 import）、文件末尾带独立 `main()`——
独立脚本误入包内。删除后覆盖率分母同步收窄。

## [0.2.0] — 2026-09-13

修复嵌入缓存的**跨进程失效**问题——这是本系统首个真正影响
规模化可用性的检索缺陷。**无破坏性变更**。

### Fixed — 嵌入缓存键不可复现，且不落盘 → 每次重启全失效

两处缺陷叠加，导致嵌入缓存**在任何一次服务重启后完全归零**：

1. **缓存键用 `hash(text)`**：CPython 对 `str` 的哈希受
   `PYTHONHASHSEED` 随机化影响，同一文本在不同进程中得到不同键。
   实测 `PYTHONHASHSEED=0/1/2` 下 `hash('记忆')` 三次结果各不相同。
   改用 `blake2b(text, digest_size=16)`，跨进程稳定。
2. **`EmbeddingCache` 仅在进程内存在**：进程退出即丢弃。
   改为持久化到磁盘（`~/.cache/pangu/`，可用 `PANGU_CACHE_DIR` 覆盖，
   `PANGU_EMBEDDING_CACHE=0` 关闭）。

持久化实现要点：带 `FORMAT_VERSION` 与模型指纹（覆盖
model/dim/quantized/max_length），指纹不匹配即整体丢弃；
写入采用 `tempfile.mkstemp` + `os.replace` 原子替换，避免半写坏文件；
每累积 100 条脏数据落盘一次，服务关闭时（lifespan shutdown）强制 flush。

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 重启后首次检索 | **696.9ms** | **7.4ms**（≈94×） |

新增 `tests/test_embedding_cache_persistence.py`（16 条测试）。

## [0.1.3] — 2026-09-13

可用性兜底：消除"配置了却不生效"的静默降级，并补上 API 服务的 CLI 入口。
**无破坏性变更。**

### Fixed — 模型下载失败静默降级为 hash 嵌入

ONNX 模型不可用时检索照常返回结果，但嵌入质量降级为哈希向量——
用户拿到的是"能跑但结果是错的"系统，且**没有任何提示**。
现改为显式上报：`pangu/observability/health.py:52-56` 在
`active_backend == "hash"` 时把 `/health` 改判为
`{"status":"degraded","embedding_backend":"hash","embedding_degraded":true}`，
`pangu/core/config.py:193` 同步记 ERROR 日志。
（仅在状态**已确定且为降级**时改判，避免把 `unknown` 误当异常。）

### Fixed — 远程 Embed API 分支因缺 `aiohttp` 从未生效

该分支依赖 `aiohttp`，而它不是正式依赖，导致配置了远程 Embed API 后
**静默走回本地路径**，且熔断器语义被 `ImportError` 污染。
改用 `httpx`（`httpx>=0.27.0` 本就是正式依赖）。

### Added — `pangu serve --api`：19529 的 CLI 入口

此前 `pangu/api/server.py:create_app()` 没有任何 CLI 命令可启动，
用户无从得知如何拉起同时提供 MCP 与 REST 的服务（DSH 插件所依赖的正是它）。

> 两个服务容易混淆，务必区分：
> - **19529** = `pangu/api/server.py:create_app()`，MCP + REST 同端口
>   （`/mcp` 挂载于 `api/server.py:612`）——**DSH 插件用这个**
> - **8866** = `pangu/server/web_server.py:create_app()`，由普通
>   `pangu serve` 启动，**不含 MCP 端点**

### Added — 一键安装脚本 `install.sh`

7 条路径实测通过（含依赖冷装、ONNX 模型下载失败降级、
`--no-service` 与 systemd 单元生成）。

### Changed — `PluginInfo.version` 默认值与软件版本解耦

插件版本不再随主程序版本漂移。

## [0.1.2] — 2026-09-12

修复 v0.1.1 之后发现的**首个检索性能缺陷**与**日志静默**问题，并消除全仓库
硬编码版本号。**无破坏性变更，无 API 改动**，升级即可显著改善首次检索延迟。

### Fixed — 向量预热未生效，首次搜索冷启动约 50 秒

`warmup_vector_index()` 此前只调用 `vector_index.get_vector_index()`，拿到的是
一个**空索引**（`size=0`）——什么都没预热。预热耗时照常上报、日志照常打印
「完成」，看起来一切正常，因此该缺陷长期未被发现。

真实的检索路径读的是 `FTS5SearchEngine.embedder` 的嵌入缓存，而预热从未往
那里写过任何东西。于是服务启动后的第一次语义检索要**现场推理全部文档向量**：

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 预热后首次搜索（1000 条文档） | **50.28s** | **1.8ms** |

修法是让预热真正写入运行期会读的那个缓存：加载 `PanguConfig` → 构建
`MemoryStack` → 取出 `drawers` → 用 `FTS5SearchEngine`（而非新实例，否则写的
是另一个单例缓存）建索引 → 对文档全集调 `embed_batch()` 填充嵌入缓存。

现在 `Warmup complete` 日志会如实列出各阶段耗时，包括此前缺失的 `vector_index`：

```
Warmup complete: 306ms (jieba=0ms, onnx=179ms, fts_index=7ms, vector_index=120ms)
```

### Fixed — 日志从未初始化，所有 `logger.info` 被静默丢弃

`.deploy-logs/pangu-api.log` 里只有 uvicorn 的 access log，盘古自身的启动信息
一条都没有——排查故障最需要的信息（预热耗时、MCPServer 预加载、自主维护周期、
工作记忆恢复）全部不可见。

根因是 `create_app()` 全程没有日志初始化，而 Python 的 root logger **默认
level=WARNING 且 handler 为空**，所有 `logger.info` 调用被直接丢弃。
`pangu/memory/production.py` 里其实早已实现 `setup_structured_logging`
（结构化 JSON 输出），但**从未被任何调用点引用**——属于同一问题的另一半。

现在在 `lifespan` 启动处调用它（放在 lifespan 而非 `create_app`，符合 FastAPI
语义：只有服务真正启动才配置日志，光构造 app 不会误改调用方的 logging 配置）。
可用 `PANGU_LOG_LEVEL` / `PANGU_LOG_FILE` 覆盖，默认只写 stdout 交由 systemd
落盘。该调用幂等，且失败时回退 `basicConfig` 并告警，不影响服务启动。

这也解释了上面的向量冷启动缺陷为何能潜伏：日志里根本看不到预热输出，
连「预热到底跑没跑」都无法从部署日志判断。

### Changed — 消除全仓库硬编码版本号

版本号此前散落在 6 个位置，升级时漏改会导致 `tests/test_integration.py` 之类的
断言失败。现在统一以 `pangu/__init__.py` 的 `__version__` 为唯一事实源：
`health.py`、`tracing.py`、`web_server.py` 改为从包导入。

同时区分了两类此前被混为一谈的版本号——**软件版本**与**数据格式版本**，
后者**不应**随发版变动，故加注释说明并保留原值：`drawer_storage.py` 的
存储格式版本（已提为具名常量 `_STORAGE_FORMAT_VERSION`）、`palace.py` 的
结构版本、`store/migrations.py` 的迁移版本（迁移逻辑实际读 `schema_version`）。

顺带修掉 `self_improve.py` 的一处死代码：它从 `~/.pangu/config.json` 读
`server_url` / `api_key`，但该文件因 `PanguConfig.save()` 的密钥排除机制
**永远不含这两个键**，配置读取从未生效；现改为走 `PanguConfig.load()`。

### Fixed — CI: ONNX 测试在模型不可用时误报失败

`tests/test_onnx_embedder.py::test_service_embed_uses_onnx` 曾在某个 CI 的
Python 3.10 job 上失败（同一次运行的 3.11/3.12 通过），报错为毫无线索的
`assert False is True`。

根因：跳过条件 `_onnx_available()` 只检查 `onnxruntime`/`tokenizers` 能否
import，**不检查模型文件是否可用**。ONNX 模型不在仓库里，CI 上缓存目录每次
是空的，需现从镜像下载；下载失败时 `EmbeddingService.embed()` 会**静默降级**
到 hash 向量，于是 `vec is not None`、`len(vec) == 384` 等断言照样通过，
只有读 `stats["onnx"]["model_loaded"]` 的那句会炸。

新增 `pytestmark_onnx_model`：真正构造 `ONNXEmbedder` 并调 `_ensure_loaded()`
来判定模型可用性，不可用时**跳过而非失败**；探针复用 `PanguConfig.load()`
的配置（否则当测试用环境变量覆盖 cache_dir 时会误判）。同时给该断言补上
诊断信息，失败时打印 onnx stats 与 `_load_error`。

## [0.1.1] — 2026-09-12

一次以「让流水线说真话」为主的维护发布：修复了 v0.1.0 之后暴露的测试、
CI 与镜像构建缺陷，并清零全部静态检查债务。**无破坏性变更，无 API 改动。**

### Fixed — Docker 镜像构建

v0.1.0 的多架构镜像构建自创建起从未成功过。根因是 `Dockerfile` 的
`docs` 阶段三层缺失，逐层修完才构建通过：

- **mkdocs 插件依赖缺失**：`mkdocs.yml` 启用了 `git-revision-date-localized`
  与 `minify`，但 Dockerfile 只装了 `mkdocs mkdocs-material`，`--strict`
  下直接 `Aborted with a configuration error!`。仓库其实一直有权威清单
  `requirements-docs.txt`（`docs.yml` 正是用它构建且始终正常），唯独
  Dockerfile 手写包名未与之同步。现改为 `pip install -r requirements-docs.txt`，
  以该文件为单一事实来源
- **缺少 git 可执行文件**：`git-revision-date-localized` 依赖 gitpython，
  初始化即要求系统存在 `git`，而基础阶段只装了
  `ca-certificates` / `curl` / `tini`
- **strict 模式把插件告警当失败**：构建上下文不含 `.git`，插件对每一页
  各出一条 WARNING，而 `mkdocs build --strict` 视任何 WARNING 为失败。
  `fallback_to_build_date: true` 只保证不抛异常，并不消除告警。现于
  `docs` 阶段就地 `git init` 并提交文档树，使插件能取到 revision 日期

本地已复现并验证：无 git 仓库时精确复现 `Aborted with 1 warnings in
strict mode!`；补齐后 `Documentation built in 2.42 seconds`，
产出 79 个文件 / 4.5 MB 站点。

### Fixed — CI 流水线

- **`arm64` 测试任务永远排队，拖死下游**：`ci.yml` 的测试矩阵引用了
  `ubuntu-24.04-arm64`——该标签**不存在**（公开仓库可用的正确标签是
  `ubuntu-24.04-arm`，无 `64`）。矩阵中任一组合未完成即视为整个 job
  未完成，使依赖它的 `benchmark` 与 `quality-gate` **自创建以来从未
  执行过**，且症状是静默的 `queued` 而非报错。已移除该条目；经临时
  探针实测确认 `ubuntu-24.04-arm` 可正常调度（16 秒完成，
  `uname -m` = `aarch64`，`onnxruntime` 1.30.0 可用）
- **同一 commit 把测试跑两遍**：`ci.yml` 的测试子集（3.11 + 3.12）与
  `test.yml` 的全量测试（3.10 + 3.11 + 3.12）范围重叠，后者完全覆盖
  前者。现 `ci.yml` 收敛为单一 Python 版本，定位明确为「快速反馈 +
  产出 junit」，跨版本与全量测试交给 `test.yml`
- **删除永不触发的 `lint.yml`**：它监听 `branches: [main, develop]`，
  而本仓库默认分支是 `master` 且只存在 `master`，从未运行过。其职责
  与 `ci.yml` 的 lint 任务重复，后者还额外含 bandit 扫描

### Fixed — DSH 插件

- **「测试连接」报 HTTP 404**：插件的宿主清单（`lib/typert.host.mjs`）
  缺少 `panguConfig/testLlm` 成员声明，而客户端清单已声明该成员。
  宿主清单决定路由注册，故端点实际不存在。补齐声明后恢复

### Fixed — 测试可靠性

- **`pytest tests/` 收集中断**：全量收集会导入
  `tests/manual_e2e/test_comprehensive.py`，而它依赖一个从未提交的
  `mcp_helper.py`，`ModuleNotFoundError` 使整个会话失败。现于
  `tests/conftest.py` 加入 `collect_ignore_glob = ["manual_e2e/*"]`
- **基准测试不可靠断言**：修正随环境波动而随机失败的断言，并顺带修复
  由此暴露的两处真实缺陷
- **61 处断言错误**：修复 CI 全量运行暴露的断言与工具注册问题

### Changed — 静态检查债务清零

- `ruff check pangu/ tests/` 从 **278 个错误清零**，`ruff format` 的
  40 个未格式化文件亦整理完毕。改动**纯属风格**，已用 AST 指纹逐一
  比对确认结构未变（245 个文件，0 处 AST 结构差异）
- 其中一处并非风格问题：`pangu/memory/knowledge_extractor.py` 有个字典项
  的注释吞掉了行尾逗号，构成真实 `SyntaxError`——该文件此前完全无法
  导入，只因没有任何模块引用它而未被发现

### Changed — 覆盖率口径

- 明确覆盖率分母：排除 CLI 入口与零覆盖的实验模块，并在注释中约定
  不得把新增核心模块加入排除列表

### Docs

- 补全工具暴露面配置说明（`core` / `optional` / `experimental` 三级）
  与 `1001` / `1002` 错误码语义，此前二者共用同一文案，容易误导排查方向
- Release 正文去除三处不实宣称，并修正变更日志范围

## [0.1.0] — 2026-09-11

首个正式发布。分层工具暴露 + 多模态记忆 + DSH 插件接入。

### Added — DSH 插件内配置 LLM

- **设置页配置表单**（DSH 设置 →「盘古记忆系统」）：提供商下拉（OpenAI /
  DeepSeek / 智谱 / 通义 / OpenRouter / Ollama）、模型名、Base URL、API Key，
  无需手改配置文件
- **「测试连接」**：以 20 秒超时向 `${base_url}/chat/completions` 发一次探测请求，
  可区分「Key 无效」（HTTP 401）与「网络不可达」（超时），便于定位问题
- **密钥独立存储**：API Key 写入 `~/.pangu/.llm_api_key`（权限 `0600`），
  **不进 `config.json`**，服务重启后仍存活；加载优先级为
  环境变量 > 密钥文件 > 空
- **密钥不回显**：`pangu_config_set` 对密钥类字段回显 `****`；插件把密钥脱敏为
  `*_set`（是否已配置）与 `*_hint`（尾 4 位）。前端拿不到明文，
  因此输入框**留空 = 保持原值不变**，清空需显式传 `null`

### Added — 测试

- `plugins/dsh-pangu/test/settings/llm-config.test.js`：脱敏与保存语义的纯逻辑测试，
  含「实现未漂移」源码守卫
- `plugins/dsh-pangu/test/settings/llm-form.test.js`：jsdom 真实渲染设置页，
  验证表单字段齐全、明文绝不下发到前端、交互与「测试连接」结果渲染
- `plugins/dsh-pangu/test/settings/save-semantics.mjs`：独立进程验证
  「留空不覆盖已存 Key、填新值才覆盖」两个方向

### Fixed — 配置热加载

- **改配置后组件仍用旧值**：`llm` / `search` / `wiki` / `persistent_cache` 在首次
  访问时就把旧 config 对象存进了实例，只替换 `server.config` 引用对它们无效——
  表现为「改了 LLM 模型或 Key，保存后毫无变化，也不报错」。
  新增 `MCPServer.invalidate_config_dependents()`，在 `config_set` 时丢弃这些实例，
  使其按新配置惰性重建
- **保存 Key 后设置页仍显示「未配置」**：`config.json` 因安全设计不含密钥，
  而插件只读它，导致判定为未配置——用户保存成功后刷新页面仍见空白，
  看起来像没生效。改为在 `config.json` 无密钥时补读密钥文件，
  仅用于判定状态与生成尾 4 位提示
- **密钥重启即丢**：`PanguConfig.save()` 用 `exclude` 排除密钥字段（安全设计），
  此前通过设置页写入的 Key 只存在内存里，服务一重启就丢

### Changed — 部署体验

- **剥离重型依赖**：`requirements.txt` 与 `pyproject.toml` 双双移除
  `torch` / `sentence-transformers` / `chromadb` / `openai-whisper`。
  实测核心依赖 56 包 / 236MB / 约 20 秒，对比完整集 987MB+。
  需要多模态时用 `pip install -e ".[multimodal]"`（无 GPU 请先装 CPU-only 轮子）
- **嵌入后端治本重构**：原实现硬依赖 `sentence-transformers`，未安装即抛
  `ImportError`，尽管 ONNX 本可独立工作。改为优先 ONNX、失败才回退 ST，
  两后端皆不可用时给出可操作的错误提示。对外仍返回 `ndarray(384)`，调用方零改动
- **新增 `scripts/install_dsh_plugin.sh`**：幂等安装，含 `zod` / typert 自检，
  避免缺依赖导致宿主启动失败（`ERR_MODULE_NOT_FOUND`）
- **脚本去硬编码**：`start.sh` / `stop.sh` / `switch_to_user_service.sh`
  移除写死的用户名与不实的 `MemoryMax` 宣称

### Fixed — 文档

- **澄清两层「白名单」**（此前极易混淆）：
  - **服务端（有效）**：`pangu/server/exposure.py` 的暴露面过滤器，
    缺省收敛为 **28 个核心工具**；扩展需改 `~/.pangu/config.json` 的 `exposure` 段
  - **客户端（无效）**：`cordis.patch.yml` 的 `tools.allow` 被 `dsh-mcp-client`
    的 Config schema 静默忽略，且无任何告警

### Security

- API Key 不写入 `config.json`，独立文件权限 `0600`
- 前端永远拿不到密钥明文，仅显示尾 4 位提示
- `pangu_config_get` 的全量接口主动排除 `api_key` / `llm_api_key` / `siliconflow_key`

### Notes — 已知行为

- **未配置 LLM 时记忆的存入与检索完全正常**（走 ONNX 本地嵌入），
  仅「知识结晶 / 记忆蒸馏 / 摘要」等需要语言模型的功能会被跳过
- **`pangu_config_reload` 不在默认暴露面内**，调用会返回 `code=1002`；
  改配置请用 `pangu_config_set`（它会自行落盘并失效组件缓存）

## [1.0.0] — 2026-09-08 — 分层共存重构（历史条目）

> 此条目对应的代码版本号已在后续提交中统一为 `0.1.0`，保留以供追溯。

### Added — 工具分层暴露

- **模块注册表** (`pangu/server/module_registry.py`)：17 个 handler 模块的元数据（模块名 → 工具名集合 → 层级 → 默认开关），作为白名单与可选模块清单的唯一事实源
- **暴露面配置模型** (`ExposureConfig`)：`~/.pangu/config.json` 新增 `exposure` 段，承载 `enabled_optional_modules` 与 `enabled_experiments` 两组开关
- **暴露面过滤器** (`pangu/server/exposure.py`)：在 MCP/REST 双通道插入单一拦截点，`tools/list` 输出过滤 + `tools/call` 前置校验，未暴露工具返回 code=1002 结构化错误
- **实验模块目录** (`experimental/`)：实验性功能（认知循环/世界模型/因果/autopilot/autonomous/neural/dream/evolution/meta/self_*）物理隔离于核心引擎，默认关闭

### Changed — 工具暴露面收敛

- **默认暴露 28 个核心工具**：记忆 CRUD 与召回 (7)、关联与统计 (5)、备份与迁移 (6)、项目与配置 (4)、内容采集 (2)、宫殿浏览 (2)、批量导入 (2)
- **长尾工具按模块可选启用**：multimodal/timeline/analytics/quality/consolidation/embed/knowledge_graph/wiki/llm_tools/session 等 10 个模块默认关闭
- **实验工具默认关闭**：35 个实验工具（前缀 autonomous/autopilot/causal/cognitive/worldmodel/neural/dream/evolution/meta/self_*）默认不加载

### Removed — 第三方适配剥离

- **openclaw 适配剥离**：移除 `OpenClawMiner` 类、`parse_claude_jsonl` 通用化为 `parse_jsonl_session`、移除 openclaw 路径探测、移除 openclaw 源映射
- **claude code 适配剥离**：`agent` 参数默认值 "claude" → "mcp_client"、`CLAUDE_CODE_SESSION_ID` → `PANGU_SESSION_ID`、删除 `pangu/hooks/` 整目录、删除 `CLAUDE.md.local`
- **宿主探针脚本迁移**：`auto_extract.py`、`phase3_enhance.py`、`test_extract.py` → `experimental/probes/`

### Changed — 仓库结构治理

- **根目录脚本收敛**：8 个启动/停止脚本 → 2 个（start.sh、stop.sh）
- **测试归位**：`benchmark.py` → `tests/manual_benchmark.py`、`test_full.py` → `tests/manual_full.py`
- **.gitignore 完善**：追加显式条目 `logs/`、`api.pid`、`pangu.pid`

### Changed — 文档与版本治理

- **版本号重置**：v3.7.0 → v1.0.0（当时称「全新发布」，后统一为 0.1.0）
- **README 重写**：以"多模态记忆系统 + 分层工具暴露"为主线，包含核心白名单清单、可选模块启用方式、实验模块边界、dsh-pangu 插件接入指引

### Security

- 剥离适配代码时同步移除宿主专属路径探测、环境变量嗅探逻辑
- .gitignore 确保 pid、logs、reports 等运行时产物不入库

### Migration Guide

1. **配置迁移**：旧配置文件（无 `exposure` 段）被接受，默认暴露面为白名单 28 个核心工具
2. **工具调用**：白名单工具行为不变；长尾/实验工具需在配置中启用对应模块
3. **适配剥离**：openclaw/claude code 宿主请通过标准 MCP 接入，不再有专属通道

[0.1.0]: https://github.com/Mlte0907/pangu/commits/v0.1.0
[1.0.0]: https://github.com/Mlte0907/pangu/commits/1122031
