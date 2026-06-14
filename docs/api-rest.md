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
| GET | `/api/v2/memories/stats` | 统计 |

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

**响应**：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "drawer_id": "d_2026-06-08_a1b2c3",
    "version": 1,
    "layer": "L2",
    "created_at": "2026-06-08T15:30:00+08:00",
    "importance": 4.2
  }
}
```

字段：
- `content` *string* 必填，最长 16 384 字符
- `importance` *float* 0.0-5.0，默认 3.0
- `tags` *string[]* 默认 `[]`
- `ttl_days` *int* 0=永不过期
- `metadata` *object* 自定义键值

## 检索

```http
POST /api/v2/memories/search
{
  "q": "用户喜欢什么颜色",
  "top_k": 5,
  "mode": "hybrid",   // semantic | lexical | hybrid
  "filters": {"tags": ["preference"]},
  "min_score": 0.35
}
```

**响应**：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "results": [
      {
        "drawer_id": "d_...",
        "content": "用户偏好深色主题",
        "score": 0.92,
        "match_layer": "L2",
        "highlights": ["**深色** 主题"]
      }
    ],
    "total": 1,
    "took_ms": 18
  }
}
```

## 上下文注入

```http
GET /api/v2/memories/context?budget=1000&agent_id=agent-001
```

返回当前对话该携带的所有记忆摘要（L0 + L1 + 命中 L2）。

## 错误码

| code | 含义 | 排查 |
|:---:|:---|:---|
| 400 | 输入校验失败 | 检查字段 |
| 401 | 鉴权失败 | 补 `X-API-Key` |
| 403 | 越权 | 跨 agent 访问需要 `admin` |
| 404 | 资源不存在 | 检查 drawer_id |
| 409 | 版本冲突 | 重新 GET 后再写 |
| 413 | 内容过长 | 拆条 |
| 429 | 速率超限 | 退避 |
| 500 | 服务错误 | 检查 `/health/deep` 与日志 |
| 503 | 降级中 | 等 |

## 速率限制

默认无限制。建议在反向代理层（nginx `limit_req`）设置：
- 写入：10 r/s per IP
- 读取：100 r/s per IP

## 完整 OpenAPI 规范

启动后访问 `http://<host>:<port>/openapi.json`（仅本机）。

或参考 [OpenAPI 3.0 schema](./openapi.json)（如有生成）。
