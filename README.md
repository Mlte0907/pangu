# 盘古 v3.0 — AI Agent 记忆系统

> 智能体的"大脑"组件，专注解决 Agent 框架中普遍存在的记忆功能短板。

盘古不是一个完整的 Agent 框架，而是专注于记忆相关的核心功能：存储、检索、组织、分类、知识结晶和类人特征的记忆智能体系统。通过 MCP 协议为上层 Agent 提供记忆服务。

| 指标 | 值 | 指标 | 值 |
|:---|:---|:---|:---|
| 版本 | v3.0 | 端口 | 19529 |
| Git 提交 | 104 | 技术栈 | Python 3.12, ONNX, FAISS, SQLite |
| 测试用例 | 428 | 运行时数据 | `~/.pangu/` |
| MCP 工具 | 315 | 功能模块 | 94 |
| 代码行数 | 30K+ | 许可证 | MIT |

## 架构

```
┌───────────────────────────────────────────────────────────┐
│              上层 Agent (Claude Code / Gemini CLI)          │
└─────────────────────────┬─────────────────────────────────┘
                          │ MCP 协议 / REST API / WebSocket
                          ▼
┌───────────────────────────────────────────────────────────┐
│                    盘古 v3.0 记忆系统                       │
│                                                           │
│  ┌──────────────────────────────────────────────────┐     │
│  │             4 层记忆栈 (L0-L3)                    │     │
│  │  L0 身份 │ L1 概要 │ L2 按需 │ L3 深度搜索       │     │
│  │  ~100tok │ ~500-800│ ~200-500│ 无限               │     │
│  │  始终加载 │ 始终加载 │ 话题触发 │ 显式查询          │     │
│  └──────────────────────────────────────────────────┘     │
│                                                           │
│  宫殿结构   Wiki 引擎   知识图谱   E2E 加密   OTel 追踪    │
│  神经记忆   混合检索    知识结晶   Prometheus  WebSocket    │
│  自进化引擎  因果推理    元学习    协作智能    智能问答       │
│  预测分析   异常检测    统一门户   事件流     多端同步       │
│  记忆版本   审计分析    多租户    多项目支持  生产加固       │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │  SQLite   │  │   FAISS  │  │   ONNX   │                │
│  │ WAL 持久化│  │ 向量索引  │  │ 本地嵌入  │                │
│  └──────────┘  └──────────┘  └──────────┘                │
└───────────────────────────────────────────────────────────┘
```

## 核心特性

| 特性 | 说明 |
|:---|:---|
| **4 层记忆栈** | L0 身份 / L1 概要 / L2 按需 / L3 深度搜索，按需加载 |
| **宫殿结构** | Wing 空间 → Room 页面 → Drawer 记忆片段，Hall 概念分类 |
| **混合检索** | FTS + 向量 + KG 三路召回，RRF 融合排序 |
| **ONNX 本地嵌入** | MiniLM-L6 量化推理，0.002ms/条，零 API 成本 |
| **FAISS 向量索引** | ≥1000 条自动切换，20000 条仅 0.22ms |
| **SQLite 持久化** | WAL 模式，知识图谱/LLM 缓存/社交流数据 |
| **E2E 加密** | Fernet AES-128-CBC + HMAC-SHA256 |
| **多租户隔离** | agent_id 命名空间隔离，不同 Agent 互不可见 |
| **OpenTelemetry** | OTLP/Console 分布式追踪，@traced 装饰器 |
| **Prometheus** | 86 个 pangu_* 指标，Grafana 大盘兼容 |
| **WebSocket** | 实时记忆事件流，topic 订阅，30s 心跳 |
| **LLM 多后端** | OpenAI / Anthropic / Ollama / OpenRouter / DeepSeek / 智谱 / 通义 |
| **LLM 缓存** | 内存 LRU + SQLite 双级缓存，重启不丢 |
| **多 Agent 协作** | private/shared/public 三级权限，评论/投票 |
| **知识结晶** | LLM 驱动 Wiki 自动生成，智能关联 |
| **安全加固** | Bandit HIGH: 22→0，参数化查询，blake2b 哈希 |

## v3.0 新增模块 (31 个)

| 模块 | 说明 | 工具数 | 模块 | 说明 | 工具数 |
|:---|:---|:---|:---|:---|:---|
| 自进化引擎 | 自诊断、进化计划、性能趋势 | 4 | 因果推理 | 因果发现、反事实、根因分析 | 5 |
| 时间推理 | 时间线、时序关系、时间查询 | 4 | 可解释搜索 | 搜索解释、查询建议 | 2 |
| 语义压缩 | 按标签压缩、重要性重评 | 3 | 异常检测 | 内容/统计异常扫描 | 3 |
| 协作智能 | Agent 注册/分享、协作推理 | 4 | 知识综合 | 矛盾检测、核心洞察 | 4 |
| 预测分析 | 查询/遗忘预测、热点话题 | 4 | 自适应架构 | 架构分析、冷热分离 | 4 |
| 智能问答 | QA 引擎、批量查询 | 3 | 上下文注入 | 注入/更新/查询上下文 | 4 |
| 自适应遗忘 | 遗忘评估、自动归档 | 4 | 巩固智能 | 智能巩固、合并、冲突解决 | 4 |
| 记忆推荐 | 相似/及时推荐、反馈 | 5 | 质量评分 | 质量评估、批量修复 | 4 |
| 元学习 | 观察、策略推荐、自动调优 | 5 | 记忆蒸馏 | 蒸馏、关键词提取 | 4 |
| 查询重写 | 查询重写、建议 | 3 | 图谱构建 | 图谱构建、实体/路径 | 5 |
| 健康监控 | 健康趋势、统计 | 3 | 备份恢复 | 备份/验证/恢复 | 5 |
| 多项目支持 | 项目创建/切换/搜索/合并 | 10 | 审计分析 | 日志/访问模式/安全摘要 | 5 |
| 多端同步 | 同步/冲突解决 | 6 | 事件流 | 发布/订阅/Webhook | 4 |
| 智能索引 | 索引构建/搜索/推荐 | 5 | 智能缓存 | 缓存统计/清理/失效 | 3 |
| 统一门户 | 写入/搜索/全景视图 | 5 | 记忆差异 | 差异/相似度/统计 | 4 |
| 生产加固 | 环境检查、启动验证 | 2 | | | |

## 快速开始

### 安装与初始化

```bash
cd pangu
pip install -e .
pangu init
```

### 配置 LLM

```bash
# OpenAI
export OPENAI_API_KEY="sk-xxx"
pangu init --force

# Ollama (本地)
export PANGU_LLM_PROVIDER=ollama
export PANGU_LLM_MODEL=qwen2.5:7b
pangu init --force

# DeepSeek
export PANGU_LLM_PROVIDER=deepseek
export PANGU_LLM_API_KEY="your-key"
pangu init --force
```

### 启动服务

```bash
pangu mcp          # MCP 服务器 (端口 19529)
pangu serve        # Web UI (端口 8866)
pangu api          # API 服务
```

### CLI 命令

```bash
pangu search "关键词"           # 搜索记忆
pangu wake-up                  # 获取唤醒上下文
pangu recall --wing work       # 按空间回忆
pangu mine ~/projects --wing work  # 从文件挖掘记忆
pangu wiki-list                # Wiki 列表
pangu wiki-generate "主题"      # 自动生成 Wiki
pangu consolidate              # 巩固状态
pangu forget --dry-run         # 预览遗忘
pangu stats                    # 系统统计
```

### MCP 工具调用

```python
from pangu.server.mcp_server import MCPServer
server = MCPServer()

# 添加记忆
server.call_tool("pangu_add_memory", {"content": "项目使用 FAISS", "wing": "work"})

# 搜索
results = server.call_tool("pangu_search_memories", {"query": "FAISS", "limit": 5})

# 唤醒
context = server.call_tool("pangu_wake_up", {})
```

## 性能指标

### 向量搜索 (FAISS 自动切换)

| 规模 | 后端 | 搜索延迟 |
|:---|:---|:---|
| <1000 条 | numpy | 0.10ms |
| ≥1000 条 | FAISS IVFFlat | 0.14ms |
| ≥10000 条 | FAISS IVFFlat | 0.18ms |
| ≥20000 条 | FAISS IVFFlat | 0.22ms |

### 嵌入与检索

| 指标 | 值 | 指标 | 值 |
|:---|:---|:---|:---|
| ONNX 单条嵌入 | 0.002ms | FTS 搜索 (25d) | 0.006ms |
| ONNX 模型大小 | ~22MB | 向量搜索 (25v) | 0.063ms |
| 模型 | MiniLM-L6 (384-dim) | 混合检索 | 3.7ms |
| 批量编码加速 | 3-5x | 并发吞吐 | 5963 ops/s |
| 神经巩固 (20条) | 0.2ms | 记忆验证 (37条) | 18.4ms |

## 测试覆盖

**428 个测试全部通过**

| 类别 | 数量 | 类别 | 数量 |
|:---|:---|:---|:---|
| 核心单元测试 | 128 | v2 功能测试 | 17 |
| 智能测试 | 8 | v3.0 模块测试 | 275 |

```bash
pytest tests/ -v                    # 全部测试
pytest tests/test_v3_modules_a.py -v  # v3.0 模块 A-E
pytest tests/test_benchmark_v2.py -v --benchmark  # 性能基准
```

## 配置

所有配置通过 `~/.pangu/config.json` 和环境变量管理。

| 配置 | 环境变量 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `llm_provider` | `PANGU_LLM_PROVIDER` | `openai` | LLM 提供商 |
| `llm_model` | `PANGU_LLM_MODEL` | `gpt-4o` | 模型名称 |
| `llm_api_key` | `PANGU_LLM_API_KEY` | - | API 密钥 |
| `llm_base_url` | `PANGU_LLM_BASE_URL` | - | 自定义 API 地址 |
| `web_port` | `PANGU_WEB_PORT` | `8866` | Web 端口 |
| `port` | `PANGU_PORT` | `19529` | MCP/API 端口 |
| `onnx_enabled` | `PANGU_ONNX_ENABLED` | `true` | ONNX 本地嵌入 |
| `onnx_model_id` | `PANGU_ONNX_MODEL` | `Xenova/all-MiniLM-L6-v2` | ONNX 模型 |
| `consolidation_enabled` | - | `true` | 启用记忆巩固 |
| `forgetting_curve_decay` | - | `0.5` | 遗忘曲线衰减率 |
| `compression_threshold` | - | `100` | 压缩触发阈值 |

## 部署

### Shell 脚本

```bash
./start_pangu.sh          # 前台启动
./start_pangu_bg.sh       # 后台启动
./stop_pangu.sh           # 停止
```

### Docker

```bash
docker compose up -d
```

### systemd

```ini
[Unit]
Description=Pangu Memory System
After=network.target

[Service]
Type=simple
User=pangu
ExecStart=/opt/pangu/.venv/bin/pangu mcp --host 0.0.0.0 --port 19529
Restart=always
RestartSec=5
Environment=PANGU_HOME=/home/pangu/.pangu

[Install]
WantedBy=multi-user.target
```

### 监控

```bash
cp deploy/prometheus.yml /etc/prometheus/
cp deploy/grafana-dashboards/pangu-overview.json /var/lib/grafana/dashboards/
cp deploy/prometheus-alerts.yml /etc/prometheus/rules/
```

10 条告警规则覆盖：服务宕机、错误率、延迟、嵌入降级、缓存命中、API 成本、数据库大小、内存、文件描述符。

### 启动验证

```bash
pangu env-check           # 检查环境
pangu startup-validate    # 验证配置
curl http://127.0.0.1:19529/health/deep  # 深度健康
```

## REST API

启动后访问 `http://127.0.0.1:8866/docs` 查看完整文档。

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET/POST | `/api/wings` | 空间管理 |
| GET/POST/DELETE | `/api/memories` | 记忆 CRUD |
| POST | `/api/memories/search` | 搜索记忆 |
| GET | `/api/memories/wake-up` | 唤醒上下文 |
| GET/POST/PUT/DELETE | `/api/wiki/pages` | Wiki 管理 |
| POST | `/api/wiki/generate` | 自动生成 Wiki |
| GET/POST | `/api/kg/entities` | 知识图谱实体 |
| GET | `/api/stats` | 系统统计 |
| GET | `/api/graph` | 导出图谱 |
| GET/POST | `/api/backups` | 备份管理 |
| GET | `/health` / `/health/deep` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

WebSocket: `ws://127.0.0.1:8866/ws`，支持 MEMORY/WIKI/KG 事件订阅。

## MCP 工具 (315 个)

### 记忆核心

| 类别 | 工具 |
|:---|:---|
| Palace | `pangu_list_wings/create_wing/delete_wing/list_rooms/create_room` |
| 记忆操作 | `pangu_add_memory/search_memories/recall/wake_up/memory_importance` |
| Wiki | `pangu_list_wiki_pages/get_wiki_page/create_wiki_page/auto_generate_wiki` |
| 知识图谱 | `pangu_kg_add_entity/add_relation/query/neighbors/auto_extract/cross_domain` |
| LLM 处理 | `pangu_summarize/classify/insight` |
| 隧道 | `pangu_create_tunnel/list_tunnels/find_tunnels` |

### 记忆智能

| 类别 | 工具 |
|:---|:---|
| 巩固 | `pangu_consolidation_stats/find_forgotten/compress_memories/detect_associations` |
| 迁移备份 | `pangu_export/import/backup/list_backups/restore_backup/verify_backup` |
| 聚类去重 | `pangu_cluster_memories/find_related/find_duplicates/merge_duplicates/similarity_check` |
| 冲突检测 | `pangu_detect_conflicts/check_pair` |
| 分析时间线 | `pangu_analyze/health_check/anomaly_detect/growth_trend/build_timeline/find_causal_links` |
| 融合回放 | `pangu_fuse_topic/progressive_summarize/crystallize_knowledge/timeline_replay/topic_replay` |
| 模式识别 | `pangu_discover_patterns/pattern_insights` |

### 伏羲移植

| 类别 | 工具 |
|:---|:---|
| FTS5 混合搜索 | `pangu_fts_search/fts_search_stats` |
| 全息记忆 | `pangu_holographic_encode/holographic_search` |
| 记忆法官 | `pangu_judge_memory/judge_stats` |
| 自适应参数 | `pangu_adaptive_params/adaptive_evaluate` |
| 工作记忆 | `pangu_wm_push/wm_get/wm_stats/wm_clear` |
| 记忆脱敏 | `pangu_sanitize/sanitize_check` |
| 再巩固共鸣 | `pangu_reconsolidate/find_resonance/cross_wing_resonance` |
| 知识蒸馏 | `pangu_distill_knowledge/distill_causal_chains/distill_graph/distill_stats` |
| 向量索引 | `pangu_vector_index_stats/vector_index_build` |
| 注意力系统 | `pangu_attention_state/attention_switch/attention_ab_test` |
| 增强评估 | `pangu_enhanced_contradictions/trajectory_track/trajectory_compare` |
| 流式索引 | `pangu_streaming_index/streaming_stats` |
| 验证循环 | `pangu_verify/verify_phase` |
| 差分隐私 | `pangu_privacy_stats/privatize_count` |

### v2.0 智能

| 类别 | 工具 |
|:---|:---|
| 神经记忆 | `pangu_neural_stats/sleep/spreading/inhibition/decay` |
| 记忆智能 | `pangu_importance_feedback/auto_fusion/cross_session_links/auto_compress/validate_memories` |
| 多 Agent | `pangu_multi_register/write/read/agents` |
| 图推理 | `pangu_graph_infer/contradictions/causal_chain/temporal/analogy/visualize` |
| 预测记忆 | `pangu_proactive_predict/suggest/context_status` |
| 情感智能 | `pangu_analyze_emotion/emotion_stats/predict_emotion/recommend_interaction` |
| 创造思维 | `pangu_generate_ideas/discover_patterns/generate_novel` |
| 自主学习 | `pangu_discover_knowledge/generate_hypotheses/learning_stats` |

### v3.0 新模块

| 类别 | 工具 |
|:---|:---|
| 自进化 | `pangu_self_diagnose/evolution_plan/performance_trend/evolution_stats` |
| 时间推理 | `pangu_temporal_timeline/relations/query/stats` |
| 语义压缩 | `pangu_compress_by_tags/reassess_importance/compression_stats` |
| 协作智能 | `pangu_agent_register/share/collaborative_reason/agent_stats` |
| 因果推理 | `pangu_causal_discover/chains/counterfactual/root_cause/causal_stats` |
| 可解释搜索 | `pangu_explain_search/search_suggestions` |
| 异常检测 | `pangu_anomaly_scan/content/stats` |
| 知识综合 | `pangu_synthesize/find_contradictions/core_insights/auto_learn` |
| 预测分析 | `pangu_predict_queries/forgetting/hot_topics/predictive_stats` |
| 自适应架构 | `pangu_arch_analyze/suggest/stats/cold_hot` |
| 智能问答 | `pangu_qa/qa_batch/qa_stats` |
| 上下文注入 | `pangu_inject_context/update_context/current_context/injection_stats` |
| 自适应遗忘 | `pangu_evaluate_forgetting/auto_forget/get_archive/forget_stats` |
| 巩固智能 | `pangu_consolidate/merge_candidates/resolve_conflicts/consolidation_stats` |
| 记忆推荐 | `pangu_recommend/recommend_similar/recommend_timely/recommend_feedback/recommendation_stats` |
| 质量评分 | `pangu_assess_quality/batch_assess/auto_fix/quality_stats` |
| 元学习 | `pangu_meta_observe/recommend/tune/insights/stats` |
| 记忆蒸馏 | `pangu_distill/distill_by_wing/extract_keywords/distillation_stats` |
| 查询重写 | `pangu_rewrite_query/suggest_queries/rewrite_stats` |
| 图谱构建 | `pangu_build_graph/graph_entity/path/quality/stats` |
| 健康监控 | `pangu_health_trend/stats` |
| 多项目 | `pangu_project_create/switch/list/active/save/load/search/merge/delete/stats` |
| 审计分析 | `pangu_audit_log/query/stats/access_patterns/security_summary` |
| 多端同步 | `pangu_sync_record/pending/conflicts/resolve/state/stats` |
| 事件流 | `pangu_event_emit/history/stats/event_webhook_add/event_save` |
| 智能索引 | `pangu_index_build/search/recommend/health/cleanup` |
| 智能缓存 | `pangu_cache_stats/cleanup/invalidate` |
| 统一门户 | `pangu_portal_write/search/panorama/maintain/summary` |
| 记忆差异 | `pangu_diff_content/batch/similarity/stats` |
| 导出导入 | `pangu_export_json/markdown/csv/import_smart/list_exports/export_stats` |
| 生产加固 | `pangu_env_check/startup_validate` |

### LLM 缓存 & 服务器

| 类别 | 工具 |
|:---|:---|
| LLM 缓存 | `pangu_llm_cache_stats/top/clear/metrics/warmup/warmup_log/vacuum/config` |
| 服务器 | `pangu_system_health/metrics/config_get/config_set/config_reload/schema_version/schema_migrations` |
| 自然语言 | `pangu_natural_query/conversational_search/memory_insights` |

## 安全

| 检查项 | 结果 |
|:---|:---|
| Bandit HIGH | **0** (从 22 降至 0) |
| Bandit MEDIUM | 10 (非关键) |
| Secret 扫描 | 0 命中 |
| SQL 注入 | 免疫（参数化查询） |
| E2E 加密 | Fernet AES-128-CBC + HMAC-SHA256 |
| 哈希算法 | blake2b (替代 MD5) |
| 认证 | JWT + API Key 双模式 |
| 授权 | RBAC + ABAC 多级权限 |

## 开发

```bash
pip install -e ".[dev]"    # 安装开发依赖
pytest tests/ -v           # 运行测试
ruff check pangu/          # 代码检查
mypy pangu/                # 类型检查
```

## License

MIT
