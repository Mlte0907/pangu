# 盘古 — LMM+Wiki 超智能记忆系统

> 盘古定位为专业的记忆系统，作为智能系统的"大脑"组件，专注于记忆相关的核心功能。

## 项目特点

- **类人记忆**：遗忘曲线、再巩固、记忆共鸣、压缩
- **LMM 智能层**：多 LLM 后端（OpenAI/Anthropic/Ollama/DeepSeek/智谱/通义千问）
- **知识图谱**：实体关系 + 因果链 + 多视角视图
- **4 层记忆栈**：L0 身份 → L1 摘要 → L2 按需 → L3 深度
- **MCP 协议**：80+ 工具接口，无缝集成上层 Agent 框架
- **多模态**：文本/图像/音频/文件统一管理
- **全息检索**：5 维语义投影融合
- **差分隐私**：ε-隐私保护

## 5 分钟上手

### 安装

```bash
pip install pangu
```

### 启动服务

```bash
pangu serve --host 0.0.0.0 --port 19529
```

### 写入第一条记忆

```bash
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Content-Type: application/json" \
  -d '{
    "text": "盘古是专业的记忆系统",
    "importance": 0.9,
    "tags": ["盘古", "memory"]
  }'
```

### 检索记忆

```bash
curl "http://localhost:19529/api/v3/memories/search?q=记忆"
```

## 架构图

```
┌─────────────────────────────────────────┐
│       上层 Agent 框架（外部）             │
│   (Claude Code / Cursor / 自定义)       │
└─────────────┬───────────────────────────┘
              │ MCP 协议 (stdio)
              │ 80+ 工具
┌─────────────▼───────────────────────────┐
│        盘古 MCP Server                   │
│  - 记忆 CRUD / 搜索 / 关联               │
│  - 知识图谱 / Wiki / 实体关系             │
│  - 衰减 / 巩固 / 共鸣 / 压缩              │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│        盘古核心（4 层记忆栈）             │
│  L0: 身份    L1: 摘要                    │
│  L2: 按需    L3: 深度                    │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│        记忆宫殿 + 知识图谱                │
│  Wings → Rooms → Drawers                │
│  Entities + Relations + Paths           │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│        存储后端                          │
│  JSON / FTS5 / 向量 / SQLite            │
└─────────────────────────────────────────┘
```

## 设计原则

1. **专注记忆** — 盘古不做执行（"不做手脚"）
2. **不重复造轮子** — 使用成熟方案（ChromaDB / SQLite / FastAPI）
3. **类人模拟** — 遗忘曲线 / 工作记忆 / 情感保护
4. **可插拔** — 后端 / LLM / 钩子均可替换
5. **可观测** — Prometheus 指标 + 健康检查 + 链路追踪

## 文档

### 入门
- [快速开始（5 分钟）](getting-started/installation.md)
- [架构详解](architecture/overview.md)
- [部署指南](deploy/docker.md)
- [配置参考](configuration.md)

### 接口
- [REST API 参考](api-rest.md)
- [MCP 协议](api-mcp.md)
- [CLI 工具](api-cli.md)
- [MCP 工具列表](api/mcp-tools.md)
- [鉴权](auth.md)

### 运维
- [故障排除](troubleshooting.md)
- [监控与可观测性](observability.md)
- [安全基线](security.md)
- [备份与迁移](operations/backup.md)

### 开发者
- [模块总览](development/modules.md)
- [测试指南](development/testing.md)
- [贡献规范](development/contributing.md)
- [CHANGELOG](../CHANGELOG.md) · [ROADMAP](../reports/ROADMAP.md) · [测试报告](../reports/TEST_REPORT.md) · [优化方案](../reports/OPTIMIZATION_PLAN.md)

## 许可

MIT License
