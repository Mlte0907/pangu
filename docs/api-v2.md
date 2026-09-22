# 现役 REST API（v2）参考

> Base URL：`http://<host>:19529`，路由前缀 `/api/v2`。
> `docs/api-rest.md` 与 `docs/api-reference.md` 描述的 `/api/v3/*` 为规划中版本，尚未挂载；接入请以本文为准。
> 交互式文档：服务启动后访问 `/docs`（OpenAPI，与本文同源）。

## 通用约定

- 响应信封：`{"code": 0, "message": "ok", "data": {...}}`；`code >= 400` 为错误。
- 鉴权：`Authorization: Bearer <platform_token>`（`pgp_*`，平台接入 Token，经人工审核发放）。
- **单用户模型**：盘古是单所有者记忆库，接入平台同属一个所有者；平台 Token 通过审核后对记忆库持管理权限（成功响应中的 `policy: admin_full` 即此）。接入审核是本系统的唯一安全边界。
- 租户归属：平台 Token 的记忆归入其平台名租户；`metadata.tenant_id` 记录每条记忆的归属，`metadata.owner_id` 记录写入 Token。

## 记忆写入

```http
POST /api/v2/memories
{
  "text": "用户偏好深色主题",
  "wing": "tech",
  "room": "general",
  "importance": 0.5,
  "tags": ["preference"],
  "visibility": "tenant"
}
```

- `importance`：**写入契约 0–1**，服务端按 **0–5 标度**存储（`0.5 → 2.5`）；传 3 / 5 会被 422 拒绝。
- `visibility`：`public`（全平台只读）| `tenant`（本平台租户）| `private`（仅 owner）。
- 写入初始 `metadata.admission = pending_review`；四问准入全过自动毕业（见下文 admission 机制）。

## 记忆读取

```http
GET  /api/v2/memories?wing=tech&room=general&limit=20&offset=0   # 列表（含 tenant 隔离裁剪）
GET  /api/v2/memories/{id}?include_embedding=false                 # 单条
DELETE /api/v2/memories/{id}                                       # 删除（无二次确认，调用方核对 id）
```

- 单条 GET 的 `metadata` **默认剔除内部 embedding 向量**；`?include_embedding=true` 显式取回。
- DELETE 无 `confirm` 参数：单用户模型下由调用方保证 id 正确（见通用约定）。

## 记忆更新（PUT）

```http
PUT /api/v2/memories/{id}
{ "text": "...", "importance": 0.4, "tags": ["a"], "facts": "..." }
```

- `importance` 与 POST 同标度：**输入 0–1 → 存 0–5**。
- ⚠ GET 读回的是 0–5 值（如 2.5），**不能直接回填** PUT（会被 0–1 校验 422），需除以 5（传 0.5）。
- PATCH 未实现：任何 `PATCH /memories/{id}` 返回 405；更新一律使用 PUT。

## 搜索（分层）

```http
GET /api/v2/memories/search?q=关键词&wing=tech&tag=a&tag=b
    &owner_id=ptok_xxx&scope=all&limit=10&offset=0
```

| 参数 | 说明 |
|---|---|
| `q` | 关键词；**省略或空串时返回分层 top-N**（按写入时间倒序），与非空查询同样分层 |
| `scope` | `all`（默认，分层）/ `own`（仅本平台租户）/ `recommend`（仅其他平台） |
| `wing` / `tag` / `owner_id` | 粗过滤，作用于全部候选；`tag` 可重复传参，**AND 语义** |
| `limit` | 1–50，默认 10；`offset` ≥ 0，配合 `total` 真翻页 |

响应：

```json
{
  "results": [
    { "id": "...", "content": "...", "search_score": 1.0,
      "scope": "own", "tenant_id": "mimo-desktop-agent", "...": "..." }
  ],
  "total": 23, "own_total": 5, "recommend_total": 18,
  "limit": 10, "offset": 0
}
```

- **分层排序**：本平台命中（`scope=own`）整体在前，其他平台命中（`scope=recommend`）作为推荐随后；同层内按 `search_score` 降序（空查询按写入时间降序）。
- `search_score` 是 FTS5 BM25 命中强度（词频加权、离散档位，越大越相关），**不是相似度百分比**。
- `total` 为过滤后总命中数（非截断数）；`own_total + recommend_total = total`。
- 空查询不产生召回反馈信号（翻页浏览不算「被搜回」）。

## 检索统计

```http
GET /api/v2/memories/stats
```

`data.search` 含 `total_searches / hits / hit_rate / by_method`（`fts` = 关键词通道）等，计数为进程内存态，服务重启清零。

## admission（准入与毕业）

写入不被阻塞，仅标记；四问全过自动毕业：

1. **无重复**（上游去重融合）；
2. **无冲突**（上游冲突检测）；
3. **有来源指针**：`metadata.source_file` 或 `metadata.source_session` 任一存在（REST 写入自动带 `rest:<token_id>`）；
4. **有正向召回反馈**：`metadata.last_feedback ∈ {recall_success, verified}`——被搜索/召回命中即产生。

毕业时：`metadata.admission = graduated`、`visibility = public`（全平台只读）、写入 `graduated_at`；判定可逆向观察（`admission_reason` / `admission_score`），但不回退已毕业状态。

## importance 漂移（反馈强化）

被召回命中的记忆按 `importance ×1.08` 强化并钳制在 `[0.5, 5.0]`（`metadata.last_feedback` / `feedback_at` 同步更新）。因此同一记忆不同时间 GET 到的 `importance` 小幅上升属设计行为。
