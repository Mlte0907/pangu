# 盘古记忆系统（pangu）内部原理报告

> 调研基线：仓库 `/home/xiaoxin/pangu`，pyproject 版本 **0.1.0**（`pyproject.toml:3`）。本文所有结论均附文件路径 + 行号。

## 1. 仓库全貌

### 1.1 顶层结构

```
pangu/                    # Python 主包（唯一打包目标，pyproject.toml:68）
├── core/                 # 配置(PanguConfig)、LLM 客户端(LLMEngine)、宫殿模型(Palace/Drawer)
├── api/                  # FastAPI 工厂 create_app、REST 路由、JWT/API-Key/RBAC/ABAC
├── server/               # MCPServer(stdio+HTTP) + 21 个 handler 模块、web_server、websocket_server
├── memory/               # 135 个记忆模块：摄入/检索/衰减/去重/FTS/向量/神经记忆/知识图谱…
├── search/               # SemanticSearch / LexicalSearch / HybridSearch
├── store/                # SQLite migrations (init_db)
├── hooks/                # Claude Code SessionStart/工具钩子脚本
├── wiki/ ui/ mining/     # Wiki 引擎、UI、挖掘
└── cli.py                # Typer CLI，约 70 个子命令
plugins/dsh-pangu/        # DeepSeek Harness 插件（lib/ 即源码）
docs/ reports/ tests/ scripts/ deploy/ monitoring/ .github/
pyproject.toml  requirements.txt  Dockerfile  docker-compose.yml  mkdocs.yml
README.md / README_EN.md / CHANGELOG.md / AGENTS.md / ROADMAP_V2.md
```

### 1.2 版本与入口

| 项 | 值 | 证据 |
|---|---|---|
| 包名/版本 | `pangu` / `0.1.0` | `pyproject.toml:2-3` |
| 描述 | "盘古 — AI Agent 多模态记忆系统" | `pyproject.toml:4` |
| 控制台入口 | `pangu = "pangu.cli:app"` | `pyproject.toml:60-61` |
| API 标题 | "盘古 v0.1 — AI Agent 多模态记忆系统" | `pangu/api/server.py:144-147` |

### 1.3 三种运行形态

1. **MCP stdio**：`pangu mcp` → `MCPServer.run_stdio()`（`pangu/cli.py:2001-2013`，`pangu/server/mcp_server.py:286-307`）。
2. **REST/WebSocket API**：`python -m uvicorn pangu.api.server:create_app`（`pangu/api/server.py:45`；`/mcp`、`/sse` HTTP 传输层在 `pangu/api/mcp_http.py:147-154`）。生产端口 19529。
3. **Web 服务**：`pangu serve` → `pangu.server.web_server:create_app`，端口 8866（`pangu/cli.py:1974-1998`）。

## 2. 记忆系统全景

### 2.1 数据模型：一条记忆 = 一个 Drawer

`pangu/core/palace.py:10-25`：

```python
@dataclass
class Drawer:
    """记忆抽屉 — 存储原始记忆片段"""
    id: str
    content: str
    wing: str = "default"          # 翼（空间分区）
    room: str = "general"          # 房间（主题页）
    hall: str = "hall_events"      # 殿堂（语义类别）
    importance: float = 3.0        # 0-5
    emotional_weight: float = 0.0
    source_file: str = ""
    tags: list = field(default_factory=list)
    author: str = ""               # 写入者 agent_id（多租户隔离）
    created_at: str = ...          # ISO 时间戳
    metadata: dict = ...
```

- `metadata` 动态扩展：`source`、`confidence`、`facts`、`memory_status`（`ingestion.py:198-205`）、`embedding`（`ingestion.py:209-216`）、`wikilinks`、`conflicts`、`decay_score`（`decay.py:69-70`）、`fused_count/fused_at`（`ingestion.py:162-163`）、`access_count`、`boosted_at`（`ingestion.py:521-524`）、`tenant_id/owner_id/classification/visibility`（ABAC，`routes_memory.py:264-272`）。
- 字符串重要性兼容：`"high"→5.0, "medium"→3.0, "low"→1.0, "critical"→6.0`（`palace.py:47-60`）。
- 组织层级：Wing → Room → Drawer；跨 Wing 用 Tunnel；7 种 Hall 分类（事实/事件/发现/偏好/建议/概念/关系，`palace.py:131-140`）。
- 次级产物：`WikiPage`（LLM 生成的知识结晶页，`palace.py:80-95`）。

### 2.2 存储层：JSON 为主、SQLite 可选

主存储 = JSON 文件，路径由 `PanguConfig` 决定（`pangu/core/config.py:38,249-264`）：`base_dir=~/.pangu`，`palace_path=~/.pangu/palace`。

| 文件 | 作用 | 证据 |
|---|---|---|
| `{palace_path}/drawers.json` | v1 记忆库 | `layers.py:293`、`routes_memory.py:303` |
| `~/.pangu/pangu.db/v2_memories/drawers.json` | **v2 权威记忆库**（API/MCP 读写源） | `server.py:391-400`、`mcp_server.py:52-67` |
| `{palace}/palace_meta.json / wings.json / rooms.json` | 宫殿结构元数据 | `palace.py:150-153` |
| `{palace}/sessions.json` | 会话桥接摘要 | `session_bridge.py:25` |
| `~/.pangu/.encryption_key` | Fernet 主密钥（0600） | `encryption.py:45-52` |
| `~/.cache/pangu/vector_index.{npz,faiss,hnsw}` | 向量索引持久化 | `vector_index.py:48-53` |
| `~/.cache/pangu/onnx/<model>/` | ONNX 模型缓存（约 22MB 量化） | `onnx_embedder.py:76-81` |

写入实现（`pangu/memory/layers.py`）：`JsonDrawerStorage` 原子写（tmp+fsync+`os.replace`，`layers.py:413-434`）；`use_sqlite=True` 切 `SqliteDrawerStorage`（WAL+线程锁，`drawer_storage.py:99-120`）；脏检查防误覆盖（`layers.py:414-426`）；删除自动备份保留 5 份（`layers.py:483-499`）；LRU 缓存 30s（`layers.py:303-306`）。v1/v2 合并：MCP 侧以 v2 为主、v1 只读合并去重（`mcp_server.py:49-68`）。

### 2.3 写入链路

**A. 核心管道 `remember()`**（`pangu/memory/ingestion.py:280-389`，REST `POST /api/v2/memories`）：

1. 脱敏 `MemorySanitizer.sanitize(level="standard")`（`ingestion.py:69-77,330`）；
2. 可选 Fernet 加密（`ingestion.py:80-88,333`）；
3. **去重三级**：精确 content 相等 → 语义余弦 > 0.92（`ingestion.py:24,104-125`）→ 文本重叠 > 0.85 降级（`ingestion.py:127-137`）；重复命中 boost 旧记忆 +0.25（`ingestion.py:521-524`）；
4. **融合**：相似 >0.92 保留更长内容、confidence +0.1、fused_count+1（`ingestion.py:156-167`）；
5. Drawer → embedding（ONNX，384 维，`ingestion.py:209-216`）→ 全息编码 → Wikilink 实体抽取 → 向量索引 → 神经记忆编码 → 冲突检测（回溯 20 条，`ingestion.py:259-277`）。

**B. MCP 工具 `pangu_add_memory`**（`pangu/server/handlers/memory_ops.py:26-56`）：直接构造 Drawer → `add_drawer()` 落盘 v2 + WebSocket 事件。**注意：此路径不经过 `remember()` 的去重/融合管道**。

**C. 自动沉淀**：
- **服务端透明采集**：每次 MCP `tools/call` 发布 `mcp.tool_invocation` 事件（`mcp_server.py:249-269`）→ `SelfImproveWorker` 消费（排除 12 个噪声工具、<60 字符跳过、5 分钟去重、30s/5 条批量，`pangu/memory/self_improve.py:33-51,129-153`）→ HTTP 写自身 `/api/v2/memories`（wing=`self_improvement`，`self_improve.py:220-242`）。
- **OpenClaw 会话采集器**：监控会话目录 JSONL → 过滤去重分类 → `remember()`（`auto_collector.py:1-12`）。
- **会话桥接**：`SessionBridge` 存摘要至 `sessions.json`（`session_bridge.py:44-58`）。
- git hook / 文件监控（`git_hook.py`、`file_watcher.py`）。

**D. 衰减与淘汰**（`pangu/memory/decay.py`）：
- `decay_batch()`：`new_score = score × base_decay^(idle_h/168) × importance_factor × night_factor × touch_factor`；夜间因子凌晨 3-5 点最强（模拟睡眠巩固，`decay.py:125-127`）；<24h 触达 ×1.35、>30 天 ×1.06（`decay.py:130-135`）；底限 `decay_floor=0.15`。
- `purge_below_floor()`：低于底限打 `archived`（`decay.py:158-179`）。
- 个性化遗忘曲线：按 tags 推断类型取衰减率（episodic 0.6 / semantic 0.15 / procedural 0.08 / emotional 0.3，`config.py:176-183`、`retrieval.py:437-478`）。
- 触发：启动 + 每 30 分钟自主调度器（`server.py:96-120`）+ REST（`routes_memory.py:511-538`）。
- 重要性反馈：召回成功 ×1.08 / 失败 ×0.92 / 投票 ±5% / 验证 +15%（`retrieval.py:593-659`）。

### 2.4 检索链路（混合检索 + RRF）

主引擎 `recall()`（`pangu/memory/retrieval.py:228-399`）：

1. 过滤 wing/room/agent_id/min_importance（`retrieval.py:271-280`）；
2. 短查询标签+同义词扩展（`retrieval.py:283-292,481-499`）；
3. **向量搜索**：ONNX 嵌入（1h 缓存，`retrieval.py:127-140`），`VectorIndex`（≥1000 条 FAISS IVFFlat，否则 NumPy，`vector_index.py:21-31`），阈值 **0.65**（`retrieval.py:154,170`）；
4. **FTS5 全文**：jieba 中文分词（`fts_search.py:21-39`）；
5. **RRF 融合**（k=60）：向量 1.0 / FTS 0.5（`retrieval.py:295-310`）；
6. **多维重排**：RRF + 神经衰减分×0.15 + (importance/5)×0.05 + 标签命中×0.03（`retrieval.py:316-341`）；
7. **神经激活扩散**：top5 spreading activation 深度 3、衰减 0.6（`retrieval.py:208-225`）；
8. LRU 缓存 60s（`retrieval.py:25`）、命中率统计（`retrieval.py:28-54`）。

**Embedding 三级降级**（`pangu/memory/embedding.py:1-13,83-121`）：
1. 外部 API（OpenAI `/embeddings` 格式，Bearer `llm_api_key`）；
2. ONNX 本地：`Xenova/all-MiniLM-L6-v2` INT8 量化、384 维（hf-mirror.com 下载，`onnx_embedder.py:47-52`）；
3. Hash 兜底：字符 trigram + blake2b 投影 384 维 L2 归一化（`embedding.py:304-323`）。
附电路断路器：连续 5 次失败断开、60s half-open（`embedding.py:238-246`）。

### 2.5 注入链路

**A. dsh-pangu 插件（主动注入）**：`plugins/dsh-pangu/lib/index.js:299-349`。取会话首条 user 消息为 query → MCP `pangu_search_memories {limit:5}` → markdown 片段（每条截 200 字符、wing+标签）→ `assembly.contexts.push({name:'pangu-memory', text})`；异常静默降级。

**B. pangu 自身四层记忆栈**（`pangu/memory/layers.py:1-11`）：

| 层 | 内容 | 预算 | 证据 |
|---|---|---|---|
| L0 身份层 | `~/.pangu/identity.txt` 全文 | ~100 tokens 始终加载 | `layers.py:54-74` |
| L1 概要层 | importance Top-15 按 room 分组、每条 200 字 | `MAX_CHARS=3200` | `layers.py:77-125` |
| L2 按需层 | wing/room 过滤按重要性排序 | 每条 300 字，动态 token 预算 | `layers.py:128-180` |
| L3 深度搜索 | 关键词+重要性评分 | 2000 tokens 默认 | `layers.py:183-253` |

动态预算（`layers.py:565-586`）：<50 条→1000t；50-200→1500t；200-500→2500t；>500→3000t。入口：MCP `pangu_wake_up`（L0+L1）、`pangu_recall`（L2）、REST `GET /api/v2/memories/context?budget=`。

**C. Claude Code hooks**：`pangu/hooks/session_hook.py`（SessionStart 拉 10 条 + 4 Wing 摘要，`session_hook.py:51-100`）。

### 2.6 配置速查（`~/.pangu/config.json` + `PANGU_*` 环境变量）

定义于 `pangu/core/config.py:32-247`。关键默认：`port` 19528、`embedding_model` all-MiniLM-L6-v2/384、`onnx_enabled` true、`similarity_threshold` 0.65、`decay_base` 0.95 / `decay_floor` 0.15 / `night_decay_factor` 0.5、`neural_enabled` true / `hippocampus_capacity` 40 / `spreading_depth` 3、`l1_max_drawers` 15 / `l1_max_chars` 3200 / `default_context_budget` 1000、`api_key`/`jwt_secret` 空=不启用鉴权（`config.py:51-61`）。

## 3. dsh-pangu 插件（DeepSeek Harness）

### 3.1 装配

`cordis.patch.yml:1-25` 向宿主 cordis 容器 **insert** 两个服务：
1. `mcp-pangu`：宿主自带 `@deepseek-ai/dsh-mcp-client`，`transport: streamable-http`，`url: http://127.0.0.1:19529/mcp`，**11 个工具白名单**（add/search/get/list/delete/update/stats/export/import/backup/restore）；
2. `pangu-dashboard`：本插件（`lib/index.js`）。

### 3.2 宿主端功能（`lib/index.js`）

| 功能 | 行号 |
|---|---|
| 仪表盘数据 Remote（MCP `pangu_stats` + `/health` 聚合） | `index.js:213-264` |
| 知识图谱 Remote（`/api/v2/graph?limit=400`） | `index.js:266-276` |
| 配置读写 Remote（`~/.pangu/config.json` 原子写） | `index.js:164-175,278-292` |
| **记忆注入 waterfall**（`system-prompt/assemble`） | `index.js:297-349` |
| WebSocket 实时事件（指数退避 1s→30s，缓冲 100 条） | `index.js:105-145` |

### 3.3 浏览器端（`lib/client.js` v4.3）

三个 slots：`sidebar.footer.action`（指标卡）、`conversation.view`（"盘古"标签页：概览/3D 星系图谱/知识卡片）、`settings.section`（config.json 读写）。9 个 Typert Remote invocation；无第三方运行时依赖；3D 图谱为 Canvas2D 手写透视投影。

## 4. 数据流图

```
【检索→注入】
① 用户在 DSH 发消息
② dsh-pangu waterfall 触发          plugins/dsh-pangu/lib/index.js:299
③ POST :19529/mcp pangu_search_memories {limit:5}   index.js:307-319
④ HybridSearch.search               pangu/search/engine.py:164-190
⑤ 结果 → markdown 片段（200 字/条）   index.js:328-338
⑥ assembly.contexts.push            index.js:340-343
⑦ Agent 亦可主动调 11 个 MCP 工具查/写记忆

【写入→落盘】
⑧ Agent 调 pangu_add_memory          handlers/memory_ops.py:26-56
   └ MemoryStack 原子写 v2 drawers.json   layers.py:395-434
⑨ 透明采集：tools/call 事件 → SelfImproveWorker → wing=self_improvement
⑩ 后台：每 30 分钟 decay/consolidation   server.py:113-120
```

## 5. 敏感信息排查（2026-09-07 已处置）

| 项 | 处置 |
|---|---|
| `CLAUDE.md.local`（内部凭证字符串） | ✅ 已移出 git 跟踪 + gitignore |
| `reports/*.md`（含内网拓扑与安全审计细节） | ✅ 已移出 git 跟踪 + gitignore `reports/` |
| `api.pid` / `pangu.pid` | ✅ 已移出跟踪 + gitignore `*.pid` |
| `config.py` CORS 硬编码内网 IP | ✅ 已删除，改由 config.json/env 配置 |
| `vector_index.py` 硬编码 `/home/xiaoxin` | ✅ 改 `Path.home()` |
| `.gitignore` `lib/` 误伤插件源码风险 | ✅ 加 `!plugins/dsh-pangu/lib/` 否定规则 |
| `.mimosa/` 运行状态目录 | ✅ gitignore |
| 真实密钥 | 未发现（历史命中均为测试占位符） |
