# 盘古 v3.6 — AI Agent 记忆系统

> 智能体的"大脑组件"，通过 MCP 协议为 AI Agent 提供 421 个多模态记忆工具。

盘古是一个完整的 AI Agent 记忆系统，支持文本、图片、视频、音频四种模态输入，具备跨模态搜索、自主记忆管理、会话桥接等能力。

| 指标 | 值 | 指标 | 值 |
|:---|:---|:---|:---|
| 版本 | v3.6 | 端口 | 19529 |
| MCP 工具 | **421** | 技术栈 | Python 3.12, ONNX, FAISS |
| 模态 | 文本/图片/视频/音频 | 运行时数据 | `~/.pangu/` |
| 测试 | 82/82 通过 | 许可证 | MIT |

## 安装

### 方式一：从源码安装（推荐）

```bash
git clone https://github.com/Mlte0907/pangu.git
cd pangu
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pangu init
```

### 方式二：Docker

```bash
git clone https://github.com/Mlte0907/pangu.git
cd pangu
docker compose up -d
```

### 环境要求

- Python 3.11+
- SQLite3
- ffmpeg（视频处理）
- 约 2GB 磁盘空间（ONNX 模型 + Whisper 模型）

## 快速开始

### 1. 启动服务

```bash
pangu mcp    # MCP 服务器 (端口 19529)
```

### 2. 写入记忆

```bash
curl -X POST http://localhost:19529/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "pangu_add_memory",
      "arguments": {"content": "这是一个测试记忆", "wing": "default"}
    }
  }'
```

### 3. 搜索记忆

```bash
curl -X POST http://localhost:19529/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", "id": 2,
    "method": "tools/call",
    "params": {
      "name": "pangu_search_memories",
      "arguments": {"query": "测试", "limit": 5}
    }
  }'
```

### 4. 接入 Claude Code

在 MCP 配置中添加：

```json
{
  "mcpServers": {
    "pangu": {
      "url": "http://localhost:19529/mcp"
    }
  }
}
```

### 5. 浏览器访问

- 仪表盘：`http://localhost:19529/dashboard`
- 知识图谱：`http://localhost:19529/graph`
- API 文档：`http://localhost:19529/docs`

## 核心能力

| 能力 | 说明 | 工具数 |
|:---|:---|:---|
| 🧠 记忆管理 | 添加/搜索/回顾/唤醒记忆 | 30+ |
| 📷 图片输入 | CLIP 嵌入 + 零样本分类 | 4 |
| 🎬 视频输入 | ffmpeg 元数据 + 关键帧提取 | 3 |
| 🎵 音频输入 | Whisper 语音转写 | 3 |
| 🔍 跨模态搜索 | 文本搜图片/视频/音频 | 1 |
| 📊 批量导入 | 自动检测文件类型 | 3 |
| 🤖 自主管理 | 自动融合/衰减/压缩 | 8 |
| 💡 上下文注入 | 基于上下文自动推荐相关记忆 | 2 |
| 📡 实时推送 | WebSocket + 飞书 Webhook | 3 |
| 🔗 会话桥接 | 跨会话共享上下文 | 5 |
| 🎯 自动驾驶 | 自动组织/维护/推荐 | 5 |
| 📁 Git Hook | commit 自动记录到记忆 | 4 |
| 📂 文件监控 | 目录变更自动提取 | 2 |
| 🛡️ 错误监控 | 健康报告 + 异常追踪 | 3 |
| ⚡ 搜索缓存 | LRU + 5 分钟 TTL | 2 |
| 🔒 JWT 认证 | 双模式认证 + RBAC | - |

## 配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `llm_provider` | `PANGU_LLM_PROVIDER` | `openai` | LLM 提供商 |
| `llm_model` | `PANGU_LLM_MODEL` | `gpt-4o` | 模型名称 |
| `llm_api_key` | `PANGU_LLM_API_KEY` | - | API 密钥 |
| `port` | `PANGU_PORT` | `19529` | MCP/API 端口 |
| `onnx_enabled` | `PANGU_ONNX_ENABLED` | `true` | ONNX 本地嵌入 |

## 认证

服务启动后默认无认证。配置 JWT：

```bash
# 编辑 ~/.pangu/config.json
{
  "jwt_default_password": "your-password",
  "jwt_users": {"admin": "your-password"}
}
```

登录获取 token：

```bash
curl -X POST http://localhost:19529/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'
```

使用 token：

```bash
curl http://localhost:19529/api/v2/memories \
  -H "Authorization: Bearer <token>"
```

## 测试

```bash
pytest tests/ -v
```

82/82 全部通过。

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
