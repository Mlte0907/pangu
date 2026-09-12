# Changelog

All notable changes to Pangu will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

> 版本号以 `pyproject.toml` 与 `pangu/__init__.py` 的 `__version__` 为唯一事实源。
> 本文件此前的 `v1.0.0` 标题是「分层共存重构」时期的旧称，代码侧已在
> commit `ac563b4`（unify all version strings to 0.1.0）统一为 `0.1.0`，此处同步更正。

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
