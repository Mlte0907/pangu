# MCP 集成

## 什么是 MCP？

[Model Context Protocol](https://modelcontextprotocol.io/) 是 Anthropic 提出的标准协议，让 AI Agent 与外部工具/数据源通信。

盘古通过 MCP 暴露 **80+ 工具** 给上层 Agent 框架。

## 配置 Claude Code

```json
// ~/.config/claude-code/mcp.json
{
  "mcpServers": {
    "pangu": {
      "command": "python",
      "args": ["-m", "pangu", "mcp"],
      "env": {
        "PANGU_LLM_API_KEY": "sk-xxxxx"
      }
    }
  }
}
```

## 配置 Cursor

```json
// ~/.cursor/mcp.json
{
  "mcpServers": {
    "pangu": {
      "command": "python",
      "args": ["-m", "pangu", "mcp"]
    }
  }
}
```

## 核心工具

### 记忆操作

| 工具 | 描述 |
|:---|:---|
| `pangu_add_memory` | 写入记忆 |
| `pangu_search_memories` | 搜索记忆（FTS5 + 向量） |
| `pangu_recall` | 唤醒上下文（L0-L3 层级） |
| `pangu_wake_up` | 启动时上下文注入 |

### 知识图谱

| 工具 | 描述 |
|:---|:---|
| `pangu_kg_add_entity` | 添加实体 |
| `pangu_kg_add_relation` | 添加关系 |
| `pangu_kg_query` | 图谱查询 |
| `pangu_kg_neighbors` | 邻居节点 |

### 伏羲移植模块

| 工具 | 描述 |
|:---|:---|
| `pangu_fts_search` | FTS5 混合搜索 |
| `pangu_holographic_search` | 全息跨维度搜索 |
| `pangu_judge_memory` | LLM 价值判断 |
| `pangu_wm_push` | 工作记忆推入 |
| `pangu_distill_knowledge` | 知识蒸馏 |
| `pangu_attention_state` | 注意力状态 |
| `pangu_verify` | 验证循环 |

## 完整工具列表

详见 [MCP 工具参考](../api/mcp-tools.md)

## 使用示例

### 在 Claude Code 中

```
你：帮我检索关于 Python 异步的记忆
[自动调用 pangu_search_memories]
[返回结果]
你：把这条记忆保存到工作记忆
[自动调用 pangu_wm_push]
```

### 编程方式调用

```python
from pangu.client import PanguClient

client = PanguClient()
results = client.memory.search("Python 异步")
for r in results:
    print(r.content)
```

## Hook 集成

盘古提供 Claude Code 钩子，自动捕获和注入记忆：

```json
// ~/.config/claude-code/settings.json
{
  "hooks": {
    "SessionStart": [{
      "command": "python -m pangu.hooks.session_hook"
    }],
    "PostToolUse": [{
      "command": "python -m pangu.hooks.tool_hook"
    }]
  }
}
```

## 高级用法

### 异步调用多个工具

Claude Code 会自动并行调用独立工具以加速响应。

### 自定义工具过滤

通过 `pangu_remember_filter` 配置写入规则：

```python
config.remember_filter = {
    "min_importance": 0.3,
    "allowed_tools": ["Bash", "Edit", "Write"],
    "blocked_paths": [".env", "*.key"],
}
```

## 故障排查

### 工具调用失败

```bash
# 启用调试日志
export PANGU_LOG_LEVEL=DEBUG

# 测试 MCP 连接
pangu mcp --test
```

### 性能调优

```bash
# 启用嵌入缓存
export PANGU_EMBED_CACHE_MAX=1024

# 启用记忆压缩
export PANGU_COMPRESSION_ENABLED=true
```
