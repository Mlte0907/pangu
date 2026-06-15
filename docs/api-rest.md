# REST API 参考

> Base URL: `http://<host>:<port>`
> 鉴权：当 `PANGU_API_KEY` 设置时，**所有非公开端点**需要 `X-API-Key` 头（或 `Authorization: Bearer <key>`）
> 公开端点：`/`, `/health`, `/health/deep`, `/metrics`, `/docs`, `/openapi.json`

## 通用响应信封

```json
{ "code": 0, "message": "ok", "data": {...} }
```

- `code == 0` 成功；`>= 400` 表示错误
- 4xx 输入错误；5xx 服务错误；401 未鉴权；403 无权限

## 端点索引

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET | `/health` | 快速健康检查 |
| GET | `/health/deep` | 深度健康（依赖项） |
| GET | `/metrics` | Prometheus 文本 |
| GET | `/api/v2/system/info` | 服务信息 |
| GET | `/api/v2/memories` | 列表 |
| GET | `/api/v2/memories/{id}` | 详情 |
| POST | `/api/v2/memories` | 写入 |
| DELETE | `/api/v2/memories/{id}` | 删除 |
| POST | `/api/v2/memories/search` | 检索 |
| GET | `/api/v2/memories/context` | 上下文注入 |
| POST | `/api/v2/memories/decay` | 触发衰减 |
| POST | `/api/v2/memories/export` | 导出 |
| POST | `/api/v2/memories/purge` | 清空（危险） |
| GET | `/api/v2/memories/stats` | 统计（含搜索/健康/token） |
| POST | `/api/v2/tasks` | 创建任务 |
| GET | `/api/v2/tasks` | 列出任务 |
| GET | `/api/v2/tasks/{id}` | 任务详情 |
| PUT | `/api/v2/tasks/{id}` | 更新任务 |
| DELETE | `/api/v2/tasks/{id}` | 删除任务 |
| GET | `/api/v2/tags` | 列出标签 |
| POST | `/api/v2/tags` | 创建标签 |
| POST | `/api/v2/tags/merge` | 合并标签 |
| GET | `/api/v2/tags/suggest` | 推荐标签 |

## 写入记忆

```http
POST /api/v2/memories
Content-Type: application/json
X-Agent-ID: agent-001
X-API-Key: <your-key>

{
  "content": "用户偏好深色主题",
  "importance": 4.2,
  "tags": ["preference", "ui"],
  "ttl_days": 90,
  "metadata": {"source": "settings-dialog"}
}
```

## 检索记忆

```http
POST /api/v2/memories/search
Content-Type: application/json
X-API-Key: <your-key>

{
  "q": "用户偏好",
  "top_k": 5,
  "mode": "hybrid"
}
```

## v2.0 新增端点

### 统计（含搜索/健康/token）

```http
GET /api/v2/memories/stats
X-API-Key: <your-key>
```

响应示例：
```json
{
  "code": 0,
  "data": {
    "total": 48,
    "by_wing": {"tech": 18, "system": 1},
    "search": {
      "total_searches": 10,
      "hits": 8,
      "hit_rate": 0.8
    },
    "health": {
      "status": "healthy",
      "onnx": {"available": true}
    },
    "tokens": {
      "total": 6890,
      "avg_per_memory": 143
    }
  }
}
```

### 任务管理

```http
POST /api/v2/tasks
Content-Type: application/json
X-API-Key: <your-key>

{
  "task_id": "task-001",
  "title": "优化搜索性能",
  "description": "集成hnswlib向量索引",
  "agent_id": "xihe"
}
```

### 标签管理

```http
POST /api/v2/tags
Content-Type: application/json
X-API-Key: <your-key>

{
  "name": "python",
  "description": "编程语言",
  "color": "#3776AB"
}
```
