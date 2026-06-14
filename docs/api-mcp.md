# MCP 协议

盘古通过 [Model Context Protocol](https://modelcontextprotocol.io) 向智能体暴露记忆能力。

## 启动

```bash
# stdio 模式（默认；用于本地客户端）
pangu-mcp

# HTTP 模式（用于远程）
pangu-mcp --transport=http --port=19529
```

## 配置（Claude Desktop / Cursor）

```json
{
  "mcpServers": {
    "pangu": {
      "command": "pangu-mcp",
      "args": [],
      "env": {
        "PANGU_DATA_DIR": "/Users/me/.pangu",
        "PANGU_LLM_API_KEY": "<key>"
      }
    }
  }
}
```

## 暴露的工具

| 工具名 | 用途 |
|:---|:---|
| `memory_add` | 写入一条记忆 |
| `memory_search` | 检索 |
| `memory_get_context` | 获取当前上下文 |
| `memory_update` | 更新（按 drawer_id） |
| `memory_delete` | 删除 |
| `memory_stats` | 统计 |
| `wiki_write` | 写入 Wiki 页面 |
| `wiki_search` | 检索 Wiki |
| `kg_query` | 知识图谱查询 |
| `kg_relate` | 添加关系 |
| `system_info` | 服务信息 |

## 工具示例

### memory_add

```json
{
  "name": "memory_add",
  "arguments": {
    "content": "用户在 2026-06-08 询问过盘古",
    "importance": 4.0,
    "tags": ["interaction"],
    "agent_id": "agent-001"
  }
}
```

### memory_search

```json
{
  "name": "memory_search",
  "arguments": {
    "q": "用户询问过什么",
    "top_k": 5,
    "mode": "hybrid"
  }
}
```

### kg_query

```json
{
  "name": "kg_query",
  "arguments": {
    "entity": "盘古",
    "depth": 2,
    "edge_types": ["causes", "refines"]
  }
}
```

## JSON-RPC 帧格式

请求：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "memory_add",
    "arguments": {...}
  }
}
```

响应：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "{...JSON...}"}],
    "isError": false
  }
}
```

## 错误处理

| error code | 含义 |
|:---|:---|
| -32700 | JSON parse 错误 |
| -32600 | 无效请求 |
| -32601 | 方法不存在 |
| -32602 | 参数无效 |
| -32603 | 内部错误 |
| -32001 | 速率超限 |
| -32002 | 服务降级中 |

## 调试

```bash
# JSON-RPC stdio echo 测试
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | pangu-mcp
```

## 安全

- 本地 stdio 默认仅本机可访问
- HTTP 模式建议 `PANGU_API_KEY` 启用鉴权
- 远程暴露时必须反向代理 + TLS
