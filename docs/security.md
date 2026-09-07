# 安全基线

## 网络

- **生产端口**：只绑 `127.0.0.1` + 反代（nginx / traefik / Caddy）
- **TLS**：必须 ≥ TLS 1.2；推荐 1.3；禁用弱 cipher
- **防火墙**：限制 19529 端口源 IP
- **CORS**：默认 `*`；生产请在 `pangu.core.config.cors_origins` 配置白名单

## 鉴权

- ✅ 启用 `PANGU_API_KEY`（至少 32 字节强随机）
- ✅ 定期轮换（建议 90 天）
- ✅ 启用鉴权后 `/docs` 仅本机访问（默认行为）
- 🔄 多 key / ACL（v0.3+）

## 密钥管理

| 密钥 | 存储 | 注入方式 |
|:---|:---|:---|
| `PANGU_LLM_API_KEY` | 环境变量 / Vault | 不进 .env 文件 |
| `PANGU_API_KEY` | 部署 Secret | K8s Secret / SOPS |
| 数据库加密密钥 | KMS | 通过 init container 注入 |

**禁止**：
- 硬编码密钥（CI 强制 grep 扫描）
- 提交到 Git（pre-commit + gitleaks）
- 通过 HTTP 传输

## 数据加密

- **静态**：当前版本 **未加密**（v0.3 引入 sealed box）
- **传输**：TLS 1.2+
- **备份**：加密归档（`age` / `gpg`）

## 依赖安全

```bash
# 周期审计
pip-audit -r requirements.txt
bandit -r pangu -f json

# 自动修复
dependabot update
```

定期检查：
- `python-multipart` ≥ 0.0.18（CVE-2024-53981）
- `fastapi` 最新稳定
- `cryptography` ≥ 41.0.0

## 输入验证

- 全部 REST 入参走 Pydantic 校验
- 抽屉内容 16 KB 上限
- 标签白名单（`^[a-z0-9-]{1,32}$`）
- 文件名防止 `..` 路径穿越

## 审计日志

- 写操作全部记录：agent_id / drawer_id / ip / ts / 操作类型
- 保留 90 天
- 不可篡改（追加写）
- 查询：`pangu-cli audit query`

## 漏洞披露

- 邮箱：security@pangu.dev
- PGP key：<https://pangu.dev/.well-known/pgp-key.asc>
- SLA：72h 确认，30d 修复 HIGH 严重度

## 加固清单

- [x] 启用 `PANGU_API_KEY`
- [x] 升级 `python-multipart` ≥ 0.0.18
- [x] `/docs` 仅本机
- [ ] v0.2: 替换 MD5 为 blake2b（OPT-5）
- [ ] v0.2: 替换 `urllib` 为 `httpx`（OPT-4）
- [ ] v0.3: 端到端加密
- [ ] v0.3: 多租户隔离

## 应急响应

| 等级 | 触发 | 响应 |
|:---|:---|:---|
| P0 | 数据泄露 / RCE | 24h 修复 + 公开披露 |
| P1 | 鉴权绕过 | 1 周内修复 |
| P2 | DoS / 信息泄露 | 30 天内 |
| P3 | 最佳实践偏差 | backlog |
