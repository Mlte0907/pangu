# 快速开始（5 分钟）

## 1. 安装

```bash
git clone https://github.com/pangu-dev/pangu.git
cd pangu

# 方式 A：使用 venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 方式 B：使用 Docker
docker run -p 19529:19529 pangu/pangu:3.0.0
```

## 2. 启动服务

```bash
# 默认 0.0.0.0:19529
pangu-server

# 或前台
python -m pangu.api.server
```

启动成功后：
- REST 文档（仅本机访问）：<http://127.0.0.1:19529/docs>
- 健康检查：<http://127.0.0.1:19529/health>
- Prometheus 指标：<http://127.0.0.1:19529/metrics>

## 3. 写入第一条记忆

```bash
curl -X POST http://127.0.0.1:19529/api/v3/memories \
  -H "Content-Type: application/json" \
  -H "X-Agent-ID: demo" \
  -d '{
    "content": "盘古是一个 4 层记忆系统",
    "importance": 4.5,
    "tags": ["intro"]
  }'
```

返回：
```json
{
  "code": 0,
  "message": "ok",
  "data": {"drawer_id": "d_2026-06-08_abc123", "importance": 4.5}
}
```

## 4. 检索

```bash
curl "http://127.0.0.1:19529/api/v3/memories/search?q=记忆系统&top_k=5" \
  -H "X-Agent-ID: demo"
```

## 5. 通过 MCP 连接

```json
// Claude Desktop / Cursor 配置
{
  "mcpServers": {
    "pangu": {
      "command": "pangu-mcp",
      "args": [],
      "env": {"PANGU_DATA_DIR": "~/.pangu"}
    }
  }
}
```

## 6. v3.0 新功能速览

### 健康检查

```bash
curl http://127.0.0.1:19529/health/deep
```

### 备份

```bash
curl -X POST http://127.0.0.1:19529/api/v3/backup \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"label": "daily-backup"}'
```

### 记忆质量评估

```bash
curl http://127.0.0.1:19529/api/v3/quality/assess \
  -H "X-API-Key: <your-key>"
```

### 分析概览

```bash
curl http://127.0.0.1:19529/api/v3/analytics/overview \
  -H "X-API-Key: <your-key>"
```

下一步：
- [部署指南](deployment.md)
- [REST API 全参考](api-rest.md)
- [架构](architecture.md)
