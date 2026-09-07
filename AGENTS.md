# 项目指令：盘古工作区（Pangu Workspace）

> 本文件由 DSH agent-instructions 机制在进入本项目会话时自动注入。
> 项目根：/home/xiaoxin/pangu（盘古记忆系统仓库）

## 盘古服务速查

- MCP 端点：`http://127.0.0.1:19529/mcp`（工具已原生挂载：`mcp__pangu__*`，421 个）
- 服务管理：`systemctl --user {status|restart} pangu-api`
- 健康检查：`curl http://127.0.0.1:19529/health`
- 配置：`~/.pangu/config.json`（600）；数据：`~/.pangu/palace/`
- SDK 探针：`scripts/mcp_sdk_probe.mjs <url> <apikey>`
- 接入文档：`docs/PANGU_DSH_INTEGRATION.md`

## 行为规则：主动使用盘古（无需用户指示）

在本工作区工作时，agent 应当**主动、默认地**使用盘古，不等用户要求：

1. **写入即记**：会话中产生值得记住的结论、决策、bug 根因、环境事实时，
   随手调用 `mcp__pangu__pangu_add_memory`（wing=tech 或 default，打上主题标签）。
   短小、一事一条；不要等会话结束。
2. **动手先查**：开始一个任务前，先用 `mcp__pangu__pangu_fts_search` 或
   `pangu_search_memories` 查相关历史（关键词 2-3 个即可），避免重复踩坑。
3. **状态外置**：长任务的中期状态（做到哪、剩什么、关键发现）写入盘古，
   让任何新会话能通过检索恢复上下文——这是超长会话报废后的标准复活通道。
4. **修复留痕**：修完 bug 后写一条「根因+修法+验证方式」的记忆。

## 已知教训（勿重复）

- MCP 服务端工具必须带 `inputSchema` 且不得重名，否则官方 SDK 整表拒收
- cordis.patch.yml 的 HMR 在 web 实例不生效，改后需重启 deepseek-harness
- 单会话超过模型上下文窗口（stealth 262144）会被 provider 秒拒且无法自愈——
  长会话要靠「状态外置到盘古」+ 新会话续接，不要无限单轮硬撑
- **cordis 预设互斥**：tool-cordis 的 Host inspect 提供器是进程级单例，
  同一时刻只能有一个活跃的 cordis 会话；第二个挂载报
  `inspect provider "Service" is already registered`。standard 预设无此限制
