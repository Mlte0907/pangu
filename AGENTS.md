# 项目指令：盘古工作区（Pangu Workspace）

> 本文件由 DSH agent-instructions 机制在进入本项目会话时自动注入。
> 项目根：`/home/xiaoxin/pangu`（盘古记忆系统仓库）

## 环境前提（重要）

本文档中的路径、服务名与工具数量**以本机实际部署为准**，不是通用事实。
换机器时请先按下表核实，不要直接照搬：

| 项 | 本机实际值 | 核实方式 |
| --- | --- | --- |
| 仓库路径 | `/home/xiaoxin/pangu` | `pwd` |
| Python | 3.12（`uv` 托管于 `.venv/`） | `.venv/bin/python -V` |
| 服务管理 | `systemctl --user pangu-api` | `systemctl --user status pangu-api` |
| 监听端口 | `127.0.0.1:19529` | `ss -ltn \| grep 19529` |
| MCP 工具数 | 以 `tools/list` 实测为准（非固定值） | 见下方"速查" |

> 历史上本文档曾记录 `421 个工具` 与 `~/.pangu/palace/` 等值，
> 那些来自**另一台主机**的部署，与本机不符，已修正。
> `tools/list` 的实际返回数量取决于服务端版本与启用的处理器，
> 任何写死的数字都会随版本漂移——请以实测为准。

## 盘古服务速查

- MCP 端点：`http://127.0.0.1:19529/mcp`（REST 与 MCP 同端口）
- 服务管理：`systemctl --user {start|stop|restart|status} pangu-api`
- 健康检查：`curl http://127.0.0.1:19529/health`
- 配置：`~/.pangu/config.json`（600）；数据：`~/.pangu/`
- SDK 探针：`scripts/mcp_sdk_probe.mjs <url> <apikey>`
- 接入文档：`docs/PANGU_DSH_INTEGRATION.md`

实测工具数（供参考，会随版本变化）：

```sh
curl -s -X POST http://127.0.0.1:19529/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['result']['tools']))"
```

## 行为规则：主动使用盘古（无需用户指示）

在本工作区工作时，agent 应当**主动、默认地**使用盘古，不等用户要求：

1. **写入即记**：会话中产生值得记住的结论、决策、bug 根因、环境事实时，
   随手调用 `mcp__pangu__pangu_add_memory`（wing=tech 或 default，打上主题标签）。
   短小、一事一条；不要等会话结束。
2. **动手先查**：开始一个任务前，先用 `pangu_search_memories` 或
   `pangu_fts_search` 查相关历史（关键词 2-3 个即可），避免重复踩坑。
3. **状态外置**：长任务的中期状态（做到哪、剩什么、关键发现）写入盘古，
   让任何新会话能通过检索恢复上下文——这是超长会话报废后的标准复活通道。
4. **修复留痕**：修完 bug 后写一条「根因+修法+验证方式」的记忆。

> 若 `mcp__pangu__*` 工具未出现在当前会话的工具列表中，说明 DSH 尚未重启加载
> 插件，或服务端未运行。先确认 `curl http://127.0.0.1:19529/health` 返回正常。

## 已知教训（勿重复）

**部署相关**

- **不要直接 `pip install -r requirements.txt` 的老版本清单**：核心清单已剥离
  `torch` / `sentence-transformers` / `chromadb` / `openai-whisper`。这些包会传递
  引入约 1.3GB CUDA 轮子，且在无 GPU 机器上永不执行（代码路径全是惰性导入）。
  实测：核心清单 56 包 / 236MB / 约 20 秒；含 torch 的完整集下载 987MB+ 仍难落盘。
  需要时用 `pip install -e ".[multimodal]"`，无 GPU 请先装 CPU-only 轮子。
- **`dsh-pangu` 插件的 `node_modules` 被 `.gitignore` 忽略**，克隆后不存在。
  `lib/typert.host.mjs` 会被宿主 typert-loader 自动 import，缺 `zod` 会导致
  DSH 启动失败（`ERR_MODULE_NOT_FOUND`）。安装插件请用
  `scripts/install_dsh_plugin.sh`（幂等，含自检）。
- **`tools.allow` 白名单不生效（仅指客户端侧）**：`@deepseek-ai/dsh-mcp-client`
  的 Config schema 不接受 `tools` 键，该键被静默忽略且无告警。
  **工具范围的真正控制点在服务端**：盘古有三级暴露机制
  （`core` / `optional` / `experimental`，见 `pangu/server/exposure.py`），
  **缺省收敛为 28 个核心工具**（`pangu/core/config.py:39`），其余不会出现在
  `tools/list`；用 `call_tool` 调未暴露工具会被拒（code=1002）。
  放开需改 `~/.pangu/config.json` 的 `exposure` 段。
  ⚠ 这两个"白名单"极易混淆，写文档时务必区分：客户端那个无效，服务端那个有效。

**协议与运行时**

- MCP 服务端工具必须带 `inputSchema` 且不得重名，否则官方 SDK 整表拒收
- `cordis.patch.yml` 的 HMR 在 web 实例不生效，改后需重启 deepseek-harness
- 单会话超过模型上下文窗口（stealth 262144）会被 provider 秒拒且无法自愈——
  长会话要靠「状态外置到盘古」+ 新会话续接，不要无限单轮硬撑
- **cordis 预设互斥**：tool-cordis 的 Host inspect 提供器是进程级单例，
  同一时刻只能有一个活跃的 cordis 会话；第二个挂载报
  `inspect provider "Service" is already registered`。standard 预设无此限制

**容器/受限环境**

- `sudo` 可能被 `no_new_privs` 拦截（容器常见），此时所有配置必须走
  **userspace**：用 `uv` 装 Python、用 `systemctl --user` 管服务，
  不要依赖系统级 `apt` / `systemctl`（非 `--user`）。
- 长时安装/下载务必用 `setsid nohup <cmd> > log 2>&1 < /dev/null &` 完全脱离
  控制终端，否则工具调用中断会连带杀死子进程，导致"缓存涨了但包没装上"。
