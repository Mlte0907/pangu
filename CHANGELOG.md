# Changelog

All notable changes to Pangu will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

## v1.0.0 — 分层共存重构 — 2026-09-08

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

- **版本号重置**：v3.7.0 → v1.0.0（全新发布）
- **README 重写**：以"多模态记忆系统 + 分层工具暴露"为主线，包含核心白名单清单、可选模块启用方式、实验模块边界、dsh-pangu 插件接入指引

### Security

- 剥离适配代码时同步移除宿主专属路径探测、环境变量嗅探逻辑
- .gitignore 确保 pid、logs、reports 等运行时产物不入库

### Migration Guide

1. **配置迁移**：旧配置文件（无 `exposure` 段）被接受，默认暴露面为白名单 28 个核心工具
2. **工具调用**：白名单工具行为不变；长尾/实验工具需在配置中启用对应模块
3. **适配剥离**：openclaw/claude code 宿主请通过标准 MCP 接入，不再有专属通道
