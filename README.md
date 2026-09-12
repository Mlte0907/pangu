# 盘古（Pangu）— AI Agent 多模态记忆系统

<p align="center"><b>v0.1.0</b> · 分层工具暴露 · MCP Server + REST API · 让 Agent 拥有会遗忘、会联想、会巩固的长期记忆</p>

盘古以"记忆宫殿"为隐喻，把 Agent 的记忆组织为 **Wing（翼）→ Room（房间）→ Drawer（抽屉）** 三级空间，
配以 **混合检索（向量 + 全文 + RRF）**、**艾宾浩斯个性化遗忘曲线**、**海马体神经激活扩散** 与
**睡眠式夜间巩固**，让记忆不是无限堆砌的日志，而是随时间演化、越用越准的知识体系。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 🧠 记忆宫殿 | Wing→Room→Drawer 三级组织，7 种语义殿堂分类（事实/事件/发现/偏好/建议/概念/关系），跨翼 Tunnel 联通 |
| ✍️ 摄入管道 | 标准脱敏 → 可选 Fernet 加密 → 三级去重（精确 / 语义余弦 0.92 / 文本重叠）→ 重复记忆自动 boost |
| 🔍 混合检索 | ONNX 本地向量（all-MiniLM-L6-v2 INT8，384 维）+ SQLite FTS5（jieba 中文分词）+ **RRF 倒数排名融合**（k=60）+ 多维重排 |
| 🌊 神经激活扩散 | top-K 命中做 spreading activation（深度 3、衰减 0.6），把关联记忆一并唤醒 |
| ⏳ 个性化遗忘 | 艾宾浩斯式衰减曲线按记忆类型（情景 0.6 / 语义 0.15 / 程序 0.08 / 情绪 0.3）区分速率；凌晨 3-5 点夜间巩固因子；低于底限自动归档 |
| 📚 四层记忆栈 | L0 身份层 → L1 概要层 → L2 按需层 → L3 深度搜索，动态 token 预算（1000→3000）随记忆规模伸缩 |
| 🔐 安全 | Fernet 记忆级加密、MemorySanitizer 标准脱敏、JWT / API-Key / RBAC / ABAC 四层鉴权 |
| 🕸️ 知识结晶 | LLM 生成 WikiPage 知识页、Wikilink 实体抽取、知识图谱可视化 |
| 🔄 自动沉淀 | MCP 工具调用透明采集（SelfImproveWorker）、会话桥接摘要、git hook、文件监控 |
| 🖥️ 三形态接入 | MCP stdio / MCP streamable-HTTP + REST/WebSocket / 独立 Web 服务 |
| 🧩 多模态 | 图片（Pillow）/ 音频（whisper）/ PDF（pypdf）内容进记忆 |

## 快速开始

### 一键安装（推荐）

```sh
git clone https://github.com/Mlte0907/pangu.git
cd pangu
./install.sh                 # 装依赖 + 预下载模型 + 注册 systemd 服务
./install.sh --dsh-plugin    # 需要 DSH 集成时追加
```

脚本会做完整的环境自检，并在 **ONNX 模型下载失败时明确报错中止**
（而不是让服务静默降级到无语义的 hash 向量，见
[`docs/OPTIMIZATION.md`](docs/OPTIMIZATION.md#21-p0模型下载失败时静默降级检索质量静默错误)）：

```
./install.sh --help                    # 全部选项
./install.sh --no-service              # 只装到目录，不注册服务
./install.sh --port 19529              # 自定义端口
./install.sh --offline-model m.onnx,tokenizer.json   # 内网/弱网：从本地文件装模型
```

### 手动安装

```sh
# 安装（Python ≥ 3.11）
pip install -e .
```

> **依赖说明**
>
> 核心依赖**不含** `torch` / `sentence-transformers` / `chromadb` / `openai-whisper`。
> 这些包会传递引入约 1.3GB 的 CUDA 轮子（`nvidia-cudnn` 620MB、`nvidia-cublas`
> 517MB、`triton` 216MB 等），而它们的代码路径**全部是惰性导入**，在无 GPU 的机器上
> 永不执行：
>
> | 包 | 引用位置 | 是否影响启动 |
> | --- | --- | --- |
> | `sentence-transformers` | `pangu/search/embedder.py:74`（`@property model` 内） | 否，默认走 ONNX |
> | `torch` | `pangu/memory/image_engine.py:85,111,139`（CLIP 图像向量） | 否，try/except 降级 |
> | `openai-whisper` | `pangu/memory/audio_engine.py:34`（`@property whisper` 内） | 否，失败降级 |
> | `chromadb` | 全库无 import，仅 `config.backend` 默认值 | 否 |
>
> 默认嵌入路径是 **ONNX**（`onnx_enabled` 默认为 `True`，见 `pangu/core/config.py:135`），
> 无需 torch。实测在 aarch64 无 GPU 环境下：核心依赖 **56 包 / 223MB**；
> 安装耗时**因缓存状态而异**——
>
> | 场景 | 耗时 |
> | --- | --- |
> | uv **全局缓存已存在** | 约 20 秒 |
> | **首次安装（冷缓存）** | **约 8 分 10 秒** |
> | 加上 ONNX 模型下载（源可达） | +约 30 秒 |
>
> 首次安装请预留 **10 分钟以上**；`onnxruntime`(54MB) 与 `numpy`(55MB) 是大头，
> 中途别中断（中断会导致缓存已下载但包未装好）。
> 而包含 torch 的完整集会下载 987MB 以上仍难以落盘。
>
> 需要图像 / 音频 / 备用嵌入能力时：
>
> ```sh
> # 无 GPU 机器建议先装 CPU-only 轮子，可省下全部 CUDA 负载
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -e ".[multimodal]"
> ```
>
> ⚠ **注意两个不同的服务**——最容易搞混的地方：
>
> | 端口 | 应用 | 启动方式 | 用途 |
> | --- | --- | --- | --- |
> | **19529** | `pangu/api/server.py` | `./install.sh` / `./start.sh` | **MCP + REST**，DSH 插件连这个 |
> | 8866 | `pangu/server/web_server.py` | `pangu serve` | 浏览器仪表盘，**不含 MCP 接口** |
>
> `pangu serve` 启动的是 8866 的界面服务，**不能**替代 19529。

```sh
# 方式一：MCP over HTTP（API + MCP 同端口，生产推荐）
python -m uvicorn pangu.api.server:create_app --host 127.0.0.1 --port 19529

# 方式二：MCP stdio（Claude Code / 其它 MCP 客户端）
pangu mcp

# 方式三：独立 Web 服务
pangu serve          # http://127.0.0.1:8866
```

### Docker

```sh
docker compose up -d
```

## 接入 DeepSeek Harness（dsh-pangu 插件）

`plugins/dsh-pangu` 让 DSH 会话自动拥有盘古记忆：

- **记忆注入**：`system-prompt/assemble` waterfall 每轮取会话意图检索相关记忆（top-5，
  每条 200 字符），以 `[盘古记忆系统]` 上下文块注入——异常时静默降级，永不阻塞会话；
- **工具暴露**：服务端默认收敛为 **28 个核心工具**的白名单（见下方说明），
  经宿主 MCP 客户端直连（streamable-http，60s 超时）。
  > **关于"白名单"的两层含义** —— 容易混淆，这里说清楚：
  >
  > 1. **服务端白名单（真实生效）**：盘古自身有三级工具暴露机制
  >    （`core` / `optional` / `experimental`，见 `pangu/server/exposure.py`
  >    与 `pangu/core/config.py:39`）。**缺省即收敛为 28 个核心工具**，
  >    其余 100+ 个工具不会出现在 `/mcp` 的 `tools/list` 中。若要放开，
  >    在 `~/.pangu/config.json` 配置：
  >    ```json
  >    { "exposure": {
  >        "enabled_optional_modules": ["multimodal", "knowledge_graph"],
  >        "enabled_core_modules":     ["search", "palace"],
  >        "enabled_experiments":      ["causal", "advanced"] } }
  >    ```
  >    可选模块：`multimodal / timeline / analytics / quality / consolidation /
  >    embed / knowledge_graph / wiki / llm_tools / session`。
  >    - `enabled_core_modules` 用来展开 **core 层**的非白名单工具
  >      （`pangu_fts_search` / `pangu_holographic_encode` 等约 76 个）。
  >      core 层默认启用，但这些工具此前没有任何配置途径可以暴露。
  >    - `enabled_experiments` 按实验组名启用，`advanced` 是 experimental
  >      层的容器模块（其工具名不带实验前缀）。
  >    - 实测规模：默认 28 → 全开 408 个工具。
  >
  >    **错误码**：`1001` = 工具不存在；`1002` = 工具存在但所在模块未启用
  >    （按提示在 `exposure` 段开启即可）；`5000` = handler 抛出异常。
  >
  > 2. **客户端白名单（不生效，已移除）**：本插件早期在 `cordis.patch.yml`
  >    中配置过 `tools.allow`，但 `@deepseek-ai/dsh-mcp-client` 的 Config
  >    schema **不含 `tools` 键**，该键会被 schemastery 非严格模式静默忽略
  >    且无告警——工具照样全部注册。因此该配置已删除，以免造成
  >    "看似有保护、实际没有"的错误预期。**要限制工具范围，请用上面第 1 种。**
- **仪表盘**：侧栏指标卡 + "盘古"标签页（概览 / 3D 星系记忆图谱 / 知识卡片）+ 设置页配置读写。
- **设置页填写 LLM**：DSH 设置 →「盘古记忆系统」，可直接选择提供商（OpenAI /
  DeepSeek / 智谱 / 通义 / OpenRouter / Ollama）、填模型名、Base URL 与 API Key，
  并可用「测试连接」验证该组合是否真的可用。**API Key 不回显明文**
  （只显示 `****后4位`），保存后写入 `~/.pangu/.llm_api_key`（权限 0600），
  **不进 `config.json`**，重启不丢。

  > 因为明文不下发到页面，密钥输入框**留空 = 保持原有 Key 不变**；
  > 只改模型或 Base URL 时不必重填 Key。想清除 Key 需显式清空
  > `~/.pangu/.llm_api_key`。

  > 未配置 LLM 时记忆的**存入与检索完全正常**（走 ONNX 本地嵌入），
  > 仅「知识结晶 / 记忆蒸馏 / 摘要」等需要语言模型的功能会被跳过。

**安装插件**（`plugins/dsh-pangu` 的 `lib/` 为入库源码，但 `node_modules` 被
`.gitignore` 忽略，需先装其自身依赖，否则 `lib/typert.host.mjs` 会因缺少 `zod` 而
导致宿主启动失败）：

```sh
# 推荐：用仓库自带脚本（幂等，含依赖与配置自检）
scripts/install_dsh_plugin.sh          # 默认装到 web profile
scripts/install_dsh_plugin.sh tui      # 指定 profile
```

或手动两步：

```sh
# 1) 先装插件的运行时依赖（必需，否则启动报 ERR_MODULE_NOT_FOUND: zod）
cd plugins/dsh-pangu && pnpm install --prod && cd -

# 2) 再把插件装进 DSH 的 profile
dsh plugin --profile web add "$(pwd)/plugins/dsh-pangu"
```

第二步会同时把 `dsh-pangu` 写入 profile 的 `dependencies` 与
`dsh.profile.bundles`（因其 `package.json` 声明了 `dsh.bundle`）。

> 注：`cordis.patch.yml` 的 HMR 在 web 实例不生效，改后需重启 DSH。

```yaml
# cordis.patch.yml（关键片段）
- insert:
    - id: mcp-pangu
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: streamable-http
        url: http://127.0.0.1:19529/mcp
    - id: pangu-dashboard
      name: dsh-pangu
```

## 记忆是怎么工作的

```
检索 → 注入
  用户发消息 → 插件 waterfall 取会话意图
  → MCP pangu_search_memories(limit=5)
  → HybridSearch：语义向量（0.65 阈值）+ FTS5 中文全文
  → RRF 融合 + 衰减分/重要性/标签重排 + 神经激活扩散
  → [盘古记忆系统] 上下文块注入 system prompt

写入 → 落盘
  Agent 调 pangu_add_memory（或 REST remember()）
  → 脱敏 → 加密(可选) → 三级去重 → 融合 → embedding → 索引 → 冲突检测
  → 原子写 ~/.pangu/pangu.db/v2_memories/drawers.json

后台 → 巩固
  每 30 分钟：遗忘曲线衰减 + 夜间巩固因子 + 低于底限归档
  透明采集：工具调用自动沉淀为 self_improvement 翼记忆
```

完整内部原理（含全部文件:行号证据链）见 **[docs/memory-system-internals.md](docs/memory-system-internals.md)**。

## 配置

配置文件 `~/.pangu/config.json`，全部字段可用 `PANGU_*` 环境变量覆盖：

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `port` | `19528` | API 端口 |
| `onnx_enabled` | `true` | 本地 ONNX 嵌入（离线可用，模型自动下载） |
| `embed_api_url` | 空 | 外部 embedding API（设置后优先于 ONNX） |
| `similarity_threshold` | `0.65` | 向量检索相似度阈值 |
| `decay_base` / `decay_floor` | `0.95` / `0.15` | 遗忘曲线基数 / 归档底限 |
| `neural_enabled` | `true` | 海马体神经激活扩散 |
| `api_key` / `jwt_secret` | 空 | 为空则不启用鉴权（生产建议开启） |

> 敏感字段（api_key / jwt_secret 等）在对应 `PANGU_*` 环境变量存在时会从 JSON 中忽略并告警。

## 测试

```sh
pytest tests/ -v                  # 全量
pytest tests/ -v -m "not slow"    # 跳过慢用例
```

CI：Python 3.10/3.11/3.12 矩阵 + 覆盖率门禁（`.github/workflows/test.yml`）。

## 文档

- [记忆系统内部原理](docs/memory-system-internals.md) — 数据模型 / 存储格式 / 检索打分公式 / 衰减曲线，全链路文件行号级证据
- [AGENTS.md](AGENTS.md) — Agent 行为规范（写入即记 / 动手先查 / 状态外置 / 修复留痕）
- English overview: [README_EN.md](README_EN.md)

## License

见仓库许可文件。
