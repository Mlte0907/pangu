# 鉴权与安全

盘古支持 **API Key + JWT 双鉴权**，可单独或组合使用。

## 启用方式

通过环境变量或 `config.json` 配置：

| 变量 | 说明 | 示例 |
|:--|:--|:--|
| `PANGU_API_KEY` | 服务级 API Key | `sk-xxx-xxx` |
| `PANGU_JWT_SECRET` | JWT 签名密钥（留空自动生成到 `jwt_secret_file`） | 32 字节以上随机串 |
| `PANGU_JWT_USERS` | 多用户表 `{username: bcrypt_hash}` | `{"alice": "$2b$12$..."}` |
| `PANGU_JWT_DEFAULT_PASSWORD` | 默认 admin 密码（修改触发启用） | `strong-password` |
| `PANGU_JWT_ACCESS_TTL` | access token 有效期（秒） | `3600` |
| `PANGU_JWT_REFRESH_TTL` | refresh token 有效期（秒） | `604800` |

**鉴权启用条件**（满足任一即生效）：
- `PANGU_API_KEY` 非空
- `PANGU_JWT_USERS` 非空字典
- `PANGU_JWT_DEFAULT_PASSWORD` ≠ 默认值

## 双模式

| 模式 | Header | 适用场景 |
|:--|:--|:--|
| API Key | `X-API-Key: <key>` | 服务到服务、脚本、CI/CD |
| JWT | `Authorization: Bearer <token>` | 用户会话、Web 前端、移动端 |

## 登录流程

```bash
# 1. 登录换取 token 对
curl -X POST http://localhost:19529/api/v3/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"pangu-admin"}'
# → { "access_token": "...", "refresh_token": "...", "expires_in": 3600 }

# 2. 携带 access token 访问受保护接口
curl http://localhost:19529/api/v3/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 3. access 过期前用 refresh 续期
curl -X POST http://localhost:19529/api/v3/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"

# 4. 主动登出（撤销 token）
curl -X POST http://localhost:19529/api/v3/auth/logout \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"
```

## 端点

| 路径 | 鉴权要求 | 说明 |
|:--|:--|:--|
| `POST /api/v3/auth/login` | 公开 | 账号密码登录 |
| `POST /api/v3/auth/refresh` | 公开 | refresh token 换新对 |
| `GET  /api/v3/auth/me` | JWT | 当前用户信息 |
| `POST /api/v3/auth/logout` | JWT | 撤销 token |
| 其它 `/api/v3/*` | API Key 或 JWT | 业务接口 |

## 公开端点（始终豁免）

- `/`、`/health`、`/health/deep`、`/metrics`
- `/docs`、`/redoc`、`/openapi.json`
- `/api/v3/auth/login`、`/api/v3/auth/refresh`

## 安全设计

- 密码使用 **bcrypt cost=12** 哈希
- JWT 采用 **HS256** 默认算法
- 访问令牌默认 **1 小时**有效期，刷新令牌 **7 天**
- **refresh token 旋转**：每次 refresh 自动撤销旧 token，颁发新对
- **jti 黑名单**：所有 token 撤销持久化到 `.jwt_revoked.json`（`chmod 600`）
- **常量时间比较**：API Key 使用 `hmac.compare_digest` 防时序攻击
- **WWW-Authenticate 头**：未授权时返回，引导客户端使用 Bearer 流程

## RBAC 角色权限

盘古内置 4 种角色，可通过 `PANGU_JWT_USER_ROLES` / `PANGU_JWT_ROLES` 覆盖：

| 角色 | 默认权限 scope | 适用 |
|:--|:--|:--|
| `admin` | `*`（全部） | 系统管理员 |
| `operator` | `memories:read/write/delete` + `search:query` + `engines:run` + `system:read` | 业务用户 |
| `viewer` | `memories:read` + `search:query` + `system:read` | 只读审计 |
| `service` | `memories:read/write` + `search:query` + `engines:run` + `system:read` | API Key 服务账号 |

### 权限命名规范

`<resource>:<action>`，支持通配：
- `*` — 超级权限
- `memories:*` — 资源级通配，覆盖该资源所有操作

### 配置示例

```bash
# 1. 自定义用户角色映射
export PANGU_JWT_USER_ROLES='{"alice":"operator","bob":"viewer","carol":"admin"}'

# 2. 覆盖角色权限集
export PANGU_JWT_ROLES='{
  "auditor": ["memories:read", "system:read", "search:query"],
  "power_user": ["*", "!auth:manage"]
}'

# 3. 单用户默认角色（未在映射表中的用户）
export PANGU_JWT_DEFAULT_ROLE="operator"
```

### 受保护端点用法

```python
from pangu.api.rbac import require_scope, Principal
from fastapi import Depends

@app.delete("/api/v3/memories/{mid}")
async def delete_memory(
    mid: str,
    principal: Principal = Depends(require_scope("memories:delete")),
):
    # principal.user_id / principal.role / principal.scopes 可用
    ...

@app.get("/api/v3/admin/users")
async def list_users(
    _admin: Principal = Depends(require_scope("admin:*")),
):
    ...
```

### 错误响应

| 状态 | 触发条件 | 响应体 |
|:--|:--|:--|
| 401 | 未携带凭证 | `{"code":401, "message":"Authentication required", ...}` |
| 403 | 已鉴权但缺少 scope | `{"code":403, "message":"Forbidden: missing scope (memories:write)", "data":{"required":[...], "granted":[...]}}` |

### API Key 默认角色

通过 `X-API-Key` 鉴权的请求默认获得 `service` 角色（业务权限 + 读 + 写，不含 admin 权限）。
若需要 API Key 拥有 admin 权限，可在 `PANGU_JWT_ROLES` 中将 `service` 改为 `["*"]` 并对 `X-API-Key` 走 service 角色映射（生产环境建议为 API Key 单独签发专属 token）。

## ABAC 属性访问控制

ABAC（Attribute-Based Access Control）在 RBAC 角色之上提供更细粒度的访问控制，支持多租户隔离、资源所有权、密级分类和基于属性的策略规则。

### 启用配置

```bash
# 启用/禁用 ABAC（默认启用）
export PANGU_ABAC_ENABLED="true"

# 缺省 tenant_id（未指定时回退）
export PANGU_ABAC_DEFAULT_TENANT="default"

# 租户切换 Header
export PANGU_ABAC_TENANT_HEADER="x-tenant-id"

# 用户 ABAC 属性映射（嵌入 JWT extra claims）
export PANGU_ABAC_USER_ATTRS='{
  "alice": {"tenant_id": "acme", "clearance": 1, "department": "rd",   "groups": ["dev"]},
  "bob":   {"tenant_id": "globex","clearance": 2, "department": "sales","groups": ["sales"]},
  "admin": {"tenant_id": "acme", "clearance": 3, "department": "ops",  "groups": ["admins"]}
}'

# 自定义策略（JSON list，补充内置策略）
export PANGU_ABAC_POLICIES='[
  {
    "name": "global_readonly",
    "description": "审计组全局只读",
    "priority": 10,
    "rules": [
      {"effect": "allow", "condition": "s.groups contains \"auditors\" and act in [\"read\",\"search\"]", "description": "审计组只读放行"}
    ]
  }
]'
```

### 内置策略

| 策略 | 优先级 | 效果 | 说明 |
|:--|:--|:--|:--|
| `tenant_isolation` | 100 | deny | 跨租户访问拒绝（公开资源除外） |
| `deny_blacklist` | 80 | deny | 封禁部门/IP 拒绝（admin 豁免） |
| `owner_or_admin` | 50 | allow | 资源所有者或 admin 全部操作放行 |
| `classification_based` | 40 | deny | subject.clearance < resource.classification 时拒绝（admin 豁免） |
| `admin_full` | 30 | allow | admin 角色所有操作放行 |
| `authenticated` | 20 | allow | 已认证用户基本操作放行 |
| `public_resource` | 10 | allow | visibility="public" 的资源所有用户可读 |
| `default_deny` | 0 | deny | 兜底策略：无命中则拒绝 |

### 决策机制

策略按 **优先级 desc** 顺序评估：

1. **任意 DENY 命中** → 立即拒绝（高优先级）
2. **首个 ALLOW 命中** → 记录但继续（让后续高优 DENY 仍可覆盖）
3. **全部遍历完**：有 ALLOW → 放行；否则 → 默认拒绝

### 策略语法（JSON 自定义策略）

```json
{
  "name": "str",           // 策略名（唯一）
  "description": "str",    // 描述
  "priority": 0,           // 优先级（越大越先评估）
  "rules": [
    {
      "effect": "allow|deny",
      "condition": "expr",   // Python 表达式，可引用：s/subject, r/resource, e/env, act
      "description": "str"   // 命中说明
    }
  ]
}
```

**条件表达式可用变量**：

| 变量 | 类型 | 说明 |
|:--|:--|:--|
| `s` | `Subject` | `s.user_id`, `s.role`, `s.tenant_id`, `s.clearance`, `s.department`, `s.groups`(set), `s.is_admin`(bool) |
| `r` | `Resource` | `r.type`, `r.id`, `r.owner_id`, `r.tenant_id`, `r.classification`, `r.visibility` |
| `e` | `Environment` | `e.client_ip`, `e.method`, `e.path` |
| `act` | `str` | 操作类型 `"read"`, `"write"`, `"delete"`, `"admin"`, `"search"` |

### 多租户使用流程

**1. 配置用户租户属性**
```bash
export PANGU_ABAC_USER_ATTRS='{
  "alice": {"tenant_id": "acme",    "clearance": 1},
  "bob":   {"tenant_id": "globex",  "clearance": 2},
  "carol": {"tenant_id": "acme",    "clearance": 1}
}'
```

**2. 创建租户隔离资源**
```bash
# alice 创建记忆 → 自动写入 tenant_id="acme"
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(alice_token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "alice 的笔记", "visibility": "tenant"}'

# bob 创建记忆 → 自动写入 tenant_id="globex"
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(bob_token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "bob 的笔记", "visibility": "tenant"}'
```

**3. 租户隔离验证**
```bash
# bob 列出记忆 → 只能看到 globex 的
curl http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(bob_token)"
# → items 全是 tenant_id="globex"

# bob 尝试读 alice 的记忆 → 403
curl http://localhost:19529/api/v3/memories/{alice_memory_id} \
  -H "Authorization: Bearer $(bob_token)"
# → {"code": 403, "message": "ABAC deny: ..."}
```

**4. 跨租户资源共享**
```bash
# alice 创建公开资源 → 任意租户可读
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(alice_token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "公告", "visibility": "public"}'

# bob（globex）也能读到
curl http://localhost:19529/api/v3/memories/{public_id} \
  -H "Authorization: Bearer $(bob_token)"
# → 200
```

**5. 密级控制**
```bash
# alice clearance=1 无法写 classification=3(top_secret)
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(alice_token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "机密文档", "classification": 3, "visibility": "tenant"}'
# → {"code": 403, "message": "ABAC deny: 策略 'classification_based' 命中"}

# admin clearance=3 可以写
curl -X POST http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(admin_token)" \
  -H "Content-Type: application/json" \
  -d '{"text": "机密文档", "classification": 3, "visibility": "tenant"}'
# → 200
```

**6. Header 切换租户**（管理员跨租户操作）
```bash
# admin 以 acme 租户身份操作
curl http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(admin_token)" \
  -H "x-tenant-id: acme"

# admin 切换到 globex 查看
curl http://localhost:19529/api/v3/memories \
  -H "Authorization: Bearer $(admin_token)" \
  -H "x-tenant-id: globex"
```

### ABAC 决策上下文

每次授权请求构建的上下文：

```
Subject(user_id, role, tenant_id, department, clearance, groups, is_admin)
    ×
Resource(type, id, owner_id, tenant_id, classification, visibility)
    ×
Environment(client_ip, method, path)
    ×
Action(read|write|delete|admin|search)
    →
Decision(allowed, effect, reason, policy)
```

### 自定义策略示例

```json
[
  {
    "name": "department_read_only",
    "description": "同部门可读，跨部门拒绝（非 admin）",
    "priority": 45,
    "rules": [
      {
        "effect": "allow",
        "condition": "act == \"read\" and s.department == r.metadata.get(\"department\", \"\")",
        "description": "同部门读放行"
      },
      {
        "effect": "deny",
        "condition": "act == \"read\" and s.department != r.metadata.get(\"department\", \"\") and not s.is_admin",
        "description": "跨部门读拒绝"
      }
    ]
  },
  {
    "name": "time_window",
    "priority": 35,
    "description": "仅工作日 9:00-18:00 允许写入",
    "rules": [
      {
        "effect": "deny",
        "condition": "act == \"write\" and not (e.timestamp.weekday() < 5 and 9 <= e.timestamp.hour < 18)",
        "description": "非工作时间禁止写入"
      }
    ]
  }
]
```
