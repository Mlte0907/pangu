# DSH 前端 Bug 交接文档

> 生成时间：2026-09-20
> 状态：已修复（2026-09-20 03:10 执行完毕，见文末「执行记录」）

---

## 问题总览

DSH Web UI（端口 3080）的平台管理页有 3 个问题：

| # | 问题 | 严重度 | 根因分析 |
|---|------|--------|----------|
| 1 | 知识标签不显示列表 | 高 | typert codec 验证失败 |
| 2 | 平台列表有 2 个 test 残留 | 低 | 手动删除即可 |
| 3 | 点击「通过」按钮没反应 | 高 | typert codec 验证失败，错误被 `catch(_){}` 吞掉 |

**共同根因**：问题 1 和 3 都是 typert gateway 验证失败导致的。错误被前端 `catch(_){}` 静默吞掉，所以用户看不到任何报错。

---

## 修复方案

### 修复 1：知识列表不显示

**文件**：`plugins/dsh-pangu/lib/typert.host.js`

**问题**：`_knowledgeList` codec 的 Zod schema 只定义了 9 个字段，但 API 实际返回 11 个字段（多了 `source_memories` 和 `related_knowledge`）。typert gateway 用 `mode: 'strict'` 验证时，额外字段导致验证失败。

**修复**：在 `_knowledgeList` 的 knowledge 数组元素 schema 中加上 `source_memories` 和 `related_knowledge`：

```javascript
// 第 184-192 行，当前：
const _knowledgeList = () => (_knowledgeList$v ??= z.object({
  knowledge: z.array(z.object({
    id: z.string(), title: z.string(), content: z.string(),
    category: z.string(), tags: z.array(z.string()),
    confidence: z.number(), created_at: z.string(),
    updated_at: z.string(), usage_count: z.number(),
  })).optional(),
  count: z.number(),
}))

// 改为：
const _knowledgeList = () => (_knowledgeList$v ??= z.object({
  knowledge: z.array(z.object({
    id: z.string(), title: z.string(), content: z.string(),
    category: z.string(), tags: z.array(z.string()),
    confidence: z.number(), created_at: z.string(),
    updated_at: z.string(), usage_count: z.number(),
    source_memories: z.array(z.any()).optional(),
    related_knowledge: z.array(z.any()).optional(),
  })).optional(),
  count: z.number(),
}))
```

**验证**：修改后重启 DSH（`dsh-restart`），刷新页面，知识标签应显示 9 条知识。

---

### 修复 2：删除 test 平台

**API 调用**：

```bash
ADMIN_SECRET=$(cat ~/.pangu/.admin_secret)

# 撤销 test
curl -s -X POST http://127.0.0.1:19529/api/v2/platforms/revoke \
  -H "X-Admin-Key: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"token_id":"ptok_132fb954c5c9b0c3"}'

# 撤销 test2
curl -s -X POST http://127.0.0.1:19529/api/v2/platforms/revoke \
  -H "X-Admin-Key: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"token_id":"ptok_1fc3aeaa9d3a2948"}'
```

**验证**：刷新平台列表，应该只剩 opencode。

---

### 修复 3：审核通过按钮

**文件**：`plugins/dsh-pangu/lib/typert.host.js`（同修复 1）

**问题**：`_approveResult` codec 要求 `{ ok: boolean, token_id: string, status: string }`，但后端 API 返回 `{"ok": true, "token_id": "xxx", "status": "active"}`。理论上匹配，但可能有其他字段导致 strict 验证失败。

**建议**：检查 `_pendingList` codec 是否也需要加上额外字段。后端 `listPending` API 返回的每个 platform 对象可能包含 `_platformList` 有但 `_pendingList` 没有的字段（如 `last_used_at`, `approved_at`, `revoked_at`）。

查看 `_pendingList` codec（第 157-165 行）只定义了：`token_id, platform, platform_name, permissions, status, created_at, request_ip`。

而 `listPending` API 实际返回的 platform 对象包含：`token_id, platform, platform_name, permissions, status, created_at, last_used_at, approved_at, revoked_at, request_ip`。

**修复**：给 `_pendingList` 的元素加上缺失字段：

```javascript
const _pendingList = () => (_pendingList$v ??= z.object({
  platforms: z.array(z.object({
    token_id: z.string(), platform: z.string(), platform_name: z.string(),
    permissions: z.array(z.string()), status: z.string(),
    created_at: z.string(), request_ip: z.string().optional(),
    last_used_at: z.string().optional(),
    approved_at: z.string().optional(),
    revoked_at: z.string().optional(),
  })).optional(),
  count: z.number(),
}))
```

**验证**：修改后重启 DSH，平台标签页的待审核列表应正常显示，点击「通过」按钮应弹出确认框并完成审核。

---

## 快速修复脚本

修复 typert.host.js 后：

```bash
# 1. 重启 DSH
~/.local/bin/dsh-restart

# 2. 撤销测试平台（注意：撤销路由是 DELETE /platforms/{token_id}，
#    文档旧版写的 POST /platforms/revoke 不存在，会返回 405）
ADMIN_SECRET=$(cat ~/.pangu/.admin_secret)
curl -s -X DELETE http://127.0.0.1:19529/api/v2/platforms/ptok_132fb954c5c9b0c3 \
  -H "X-Admin-Key: $ADMIN_SECRET"
curl -s -X DELETE http://127.0.0.1:19529/api/v2/platforms/ptok_1fc3aeaa9d3a2948 \
  -H "X-Admin-Key: $ADMIN_SECRET"

# 3. 打开浏览器验证（dsh-restart 会输出当次最新的登录链接，重启后旧 token 失效）
```

---

## 关键文件清单

| 文件 | 作用 | 本次改动 |
|------|------|----------|
| `plugins/dsh-pangu/lib/typert.host.js` | Host 侧 Zod codec | 需修改 `_knowledgeList` 和 `_pendingList` |
| `plugins/dsh-pangu/lib/index.js` | Host 服务（adminFetch 调 API） | 无需修改 |
| `plugins/dsh-pangu/lib/client.js` | 前端 UI（React） | 无需修改 |
| `pangu/api/platform_tokens.py` | 平台 Token 管理 | `get_pending()` 已修复（只返回 pending 状态） |
| `pangu/api/routes_platforms.py` | 平台 API 路由 | 无需修改 |

---

## 环境速查

- **DSH Web**：端口 3080，`~/.local/bin/dsh-restart`
- **盘古 API**：端口 19529，`systemctl --user restart pangu-api`
- **Admin Secret**：`~/.pangu/.admin_secret`
- **浏览器 URL**：`http://127.0.0.1:3080/?token=CY8AqhtP3FceD_SxzZXCQB83d64b2qrYJ0eKdWYKkik`

---

## 防循环提醒

之前的会话在诊断过程中陷入了"分析→循环→再分析"的死循环。核心教训：

1. **typert 验证失败是静默的**：前端 `catch(_){}` 吞掉所有错误，不会弹任何提示
2. **用 curl 直接测 API**：确认后端没问题后，直接改 typert codec，不要反复猜
3. **改完 typert.host.js 必须 `dsh-restart`**：client.js 刷新即可，host 代码必须重启
4. **后端时间字段返回 null 而非缺省**：`list_tokens`/`get_pending` 对未发生的时间字段
   （`last_used_at`/`approved_at`/`revoked_at`/`request_ip`）返回 `null`，Zod 的
   `.optional()` 不接受 null，必须用 `.nullish()`（`.optional()` 只能挡住缺字段，挡不住 null）

---

## 执行记录（2026-09-20 03:10）

| # | 结果 |
|---|------|
| 1 | ✅ `_knowledgeList` 已含 `source_memories`/`related_knowledge`（本会话前已落盘），Zod strict 验证对真实 API 响应 PASS，知识 9 条 |
| 2 | ✅ 两个 test token 此前已被撤销（DELETE 返回 404 未找到活跃平台），平台列表仅剩 opencode、dsh |
| 3 | ✅ `_platformList`/`_pendingList` 时间字段改 `.nullish()`（本会话新增修复，null 根因见防循环提醒 #4），`_approveResult` 等响应 codec 与后端返回一致，验证 PASS |
| - | `systemctl --user restart pangu-api` 已执行，`get_pending()` 修复生效（pending 现只返回 pending 状态） |
| - | `dsh-restart` 已执行（pid 1476585 起），登录链接当次为 `?token=jl781n3tcVhe-Rsows-QkA_Awr4PIU4W30rFBf63TfE` |

未做：浏览器 UI 点按级最终验收（本机无可用浏览器后端）。typert 层已用同一份 Zod schema
对真实 API 响应做 strict 验证通过，client.js 无改动，UI 应正常。
