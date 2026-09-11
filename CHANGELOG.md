# Changelog

All notable changes to Pangu will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

> 版本号以 `pyproject.toml` 与 `pangu/__init__.py` 的 `__version__` 为唯一事实源。
> 本文件此前的 `v1.0.0` 标题是「分层共存重构」时期的旧称，代码侧已在
> commit `ac563b4`（unify all version strings to 0.1.0）统一为 `0.1.0`，此处同步更正。

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
