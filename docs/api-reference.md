# 盘古 API 参考

## 基础信息

- **Base URL**: `http://<host>:<port>`
- **默认端口**: 19529
- **鉴权**: `X-API-Key: <your-key>` 或 `Authorization: Bearer <key>`
- **公开端点**: `/health`, `/health/deep`, `/metrics`

## 端点列表

### 系统端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/health` | 健康检查 |
| GET | `/health/deep` | 深度健康检查 |
| GET | `/metrics` | Prometheus 指标 |

### 记忆端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/v3/memories` | 列出记忆 |
| POST | `/api/v3/memories` | 写入记忆 |
| GET | `/api/v3/memories/{id}` | 获取记忆详情 |
| PUT | `/api/v3/memories/{id}` | 更新记忆 |
| DELETE | `/api/v3/memories/{id}` | 删除记忆 |
| POST | `/api/v3/memories/search` | 搜索记忆 |
| GET | `/api/v3/memories/stats` | 统计信息 |

### 任务端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/v3/tasks` | 列出任务 |
| POST | `/api/v3/tasks` | 创建任务 |
| GET | `/api/v3/tasks/{id}` | 获取任务详情 |
| PUT | `/api/v3/tasks/{id}` | 更新任务 |
| DELETE | `/api/v3/tasks/{id}` | 删除任务 |

### 标签端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/v3/tags` | 列出标签 |
| POST | `/api/v3/tags` | 创建标签 |
| POST | `/api/v3/tags/merge` | 合并标签 |
| GET | `/api/v3/tags/suggest` | 推荐标签 |

## 响应格式

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code = 0`: 成功
- `code >= 400`: 错误

## 错误码

| 错误码 | 说明 |
|:---|:---|
| 400 | 请求参数错误 |
| 401 | 未鉴权 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 429 | 请求过多 |
| 500 | 服务器内部错误 |

## 示例

### 写入记忆

```bash
curl -X POST http://127.0.0.1:19529/api/v3/memories \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"content": "测试记忆", "importance": 0.8, "tags": ["test"]}'
```

### 搜索记忆

```bash
curl -X POST http://127.0.0.1:19529/api/v3/memories/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"query": "Python", "limit": 5}'
```
