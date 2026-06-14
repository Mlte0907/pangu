# 第一个记忆

## 5 步上手

### 1. 启动服务

```bash
pangu serve
```

### 2. 写入记忆

```bash
curl -X POST http://localhost:19528/api/v2/memories \
  -H "Content-Type: application/json" \
  -d '{
    "text": "盘古是专业的记忆系统，专注于类人记忆能力",
    "importance": 0.8,
    "tags": ["盘古", "介绍"],
    "wing": "default",
    "room": "general"
  }'
```

### 3. 搜索

```bash
curl "http://localhost:19528/api/v2/memories/search?q=记忆&limit=5"
```

### 4. 唤醒（上下文检索）

```bash
curl "http://localhost:19528/api/v2/memories/wake-up?token_budget=2000"
```

返回的 `L0/L1/L2/L3` 层级上下文可直接喂给 LLM。

### 5. 进阶操作

#### 工作记忆推入

```bash
curl -X POST http://localhost:19528/api/v2/wm/push \
  -d '{"content": "今天需要完成 X 任务", "urgency": 0.8}'
```

#### 知识图谱查询

```bash
# 通过 MCP
pangu_kg_query(start_entity="盘古", depth=3)
```

#### 记忆衰减

```bash
curl -X POST http://localhost:19528/api/v2/memories/decay
```

## 下一步

- [MCP 集成指南](../guides/mcp-integration.md)
- [REST API 完整参考](../api/rest-endpoints.md)
- [CLI 使用](../guides/cli.md)
