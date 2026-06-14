# 盘古版本迭代路线图（v0.1.0 → v1.0.0）

> 配套：`reports/TEST_REPORT.md`、`reports/OPTIMIZATION_PLAN.md`
> 范围：未来 6 个迭代周期（约 6 个月）
> 规则：**所有大版本（v0.2 / v0.3 / v1.0）必须基于 v0.1.0 + 上一版本 release tag**

---

## 一、版本规划（Semantic Versioning）

| 版本 | 周期 | 主题 | 状态 |
|:---|:---|:---|:---:|
| **v0.1.0**（基线）| 已发布 | 核心 4 层记忆栈 + MCP + REST + CLI | ✅ 当前 |
| v0.1.1 | 1 周 | 修复 P1（D-001/D-002）| ⏳ |
| v0.1.2 | 1 周 | 修复 P2 安全/性能（D-004/005/008/009 子集）| ⏳ |
| v0.2.0 | 4 周 | **P2 全部关闭 + 性能基线提升 5x** | 🎯 |
| v0.3.0 | 6 周 | **新特性：多租户 + 端到端加密** | 🎯 |
| v0.9.0 | 8 周 | **RC 候选冻结** | 🎯 |
| **v1.0.0** | 4 周 | **生产就绪 GA** | 🎯 |

> 后续 v1.x 主要做兼容性维护 + 选配 feature flag，不再引入破坏性 API。

---

## 二、迭代周期（Cadence）

- **小版本**（v0.1.x）：每 1-2 周一次，仅修 bug 或依赖升级
- **特性版本**（v0.x.0）：每 4-6 周一次；含 1 周 hardening + 1 周发版
- **大版本**（vX.0.0）：每 6 个月一次
- **热修复**（v0.1.x-hotfix.N）：出现 P0 / 数据丢失 / 安全 CVE 时随时

**节奏**：
- 周一：sprint planning（feature 拆解 + 估时）
- 周三：mid-sprint check
- 周五：release candidate + 全套 CI
- 周末：手工 smoke（可选）
- 下周一：GA + tag + 报告归档

---

## 三、特性优先级排序

### Backlog（按价值 / 风险 / 工作量）

| 优先级 | 特性 | 价值 | 工作量 | 版本 | 依赖 |
|:---:|:---|:---:|:---:|:---|:---|
| P0 | 修复 P1 缺陷（D-001/002）| 阻塞 | 1.25 d | v0.1.1 | — |
| P0 | 鉴权中间件（OPT-3）| 高 | 1.5 d | v0.1.2 | — |
| P0 | 依赖 CVE 升级（OPT-6）| 高 | 0.5 d | v0.1.2 | — |
| P1 | SQLite WAL + 连接池（OPT-7）| 高 | 2 d | v0.2.0 | — |
| P1 | 嵌入器字段修复（OPT-1）| 中 | 1 d | v0.1.1 | — |
| P1 | MD5 → blake2b（OPT-5）| 中 | 1 d | v0.2.0 | — |
| P1 | urllib → httpx（OPT-4）| 低 | 0.5 d | v0.1.2 | — |
| P1 | 全局异常信封（OPT-9）| 中 | 0.5 d | v0.2.0 | — |
| P2 | 异步 I/O（asyncio 化的 WikiEngine/Export）| 中 | 3 d | v0.3.0 | v0.2 |
| P2 | **多租户**（agent_id 命名空间隔离）| 高 | 5 d | v0.3.0 | v0.2 |
| P2 | **端到端加密**（libsodium sealed box）| 高 | 4 d | v0.3.0 | v0.2 |
| P2 | Prometheus 指标扩展 | 中 | 1 d | v0.2.0 | — |
| P2 | OpenTelemetry tracing | 中 | 2 d | v0.3.0 | v0.2 |
| P3 | Web UI（仪表盘）| 中 | 8 d | v0.9.0 | v0.3 |
| P3 | 联邦学习 / 跨实例合并 | 低 | 12 d | v2.x | v1.0 |
| P3 | 桌面端（Electron / Tauri）| 低 | 10 d | v2.x | v1.0 |

---

## 四、质量保障机制

### 4.1 质量门禁（Quality Gates）

| 阶段 | 强制项 | 阻塞 | 工具 |
|:---|:---|:---:|:---|
| PR 提交 | ruff / bandit / pytest（核心）| ✅ | GitHub Actions |
| 合并主干 | 全套 pytest + 接口契约 | ✅ | CI |
| RC 标签 | 性能基线 ±5% + 兼容性矩阵 | ✅ | perf.json 比对 |
| GA 发布 | bandit HIGH = 0 + OSV HIGH = 0 + 测试通过率 ≥ 99% | ✅ | 多工具 |

### 4.2 CI 矩阵

```yaml
matrix:
  python: ['3.10', '3.11', '3.12']
  os: [ubuntu-latest, ubuntu-24.04-arm]
  exclude:    # 性能测试只在 main 分支
    - python: '3.10'
      os: ubuntu-24.04-arm  # arm python 3.10 暂缺
```

### 4.3 回归基线

- 每次 PR 自动跑 `tests/manual_perf.py`，结果与 `reports/perf.json` 对比
- 延迟劣化 > 5% 或吞吐下降 > 5% → 标红
- 持续 3 次失败 → 阻止合并

### 4.4 文档 / Changelog

- 采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范
- 每次发版前自动生成 `CHANGELOG.md` diff
- API 破坏性变更必须在 `docs/BREAKING.md` 单独说明

### 4.5 缺陷管理

- **GitHub Issue 模板**（3 类）：
  - `bug_report.md`（必填：复现 / 期望 / 实际 / 环境）
  - `feature_request.md`（必填：动机 / 提案 / 替代方案）
  - `security.md`（私密披露流程 → security@pangu.dev）
- 标签：`P0` `P1` `P2` `P3` `regression` `perf` `security` `compat`
- Triage SLA：P0 24h / P1 1w / P2 1mo / P3 backburner

---

## 五、风险登记与应对

| ID | 风险 | 概率 | 影响 | 等级 | 应对 |
|:---|:---|:---:|:---:|:---:|:---|
| R-01 | OPT-1 修复后外部嵌入 API 实际仍不可用 | 中 | 中 | 🟡 | 兜底 ONNX；CI 注入 mock 后端覆盖 |
| R-02 | v0.3 多租户破坏现有 v0.2 数据格式 | 中 | 高 | 🟠 | 引入 `tenant_id` 字段并**保留兼容**读取 |
| R-03 | SQLite WAL 在网络文件系统（NFS）不可用 | 低 | 中 | 🟢 | 文档明示「仅本地 FS」；CI 跳过 NFS 路径 |
| R-04 | 端到端加密引入 KDF 影响冷启动 | 中 | 低 | 🟡 | 预派生 + 缓存；KDF 改 Argon2id with low mem |
| R-05 | CI 矩阵（aarch64 + Python 3.10）hnswlib wheel 缺失 | 高 | 中 | 🟠 | 单独 mock 分支；条件依赖 `extras_require` |
| R-06 | v0.9 → v1.0 期间发现 P0 阻塞 | 中 | 高 | 🟠 | v0.9 RC 冻结 4 周，仅修 blocker |
| R-07 | 真实 LLM 套件需 key 跳过导致覆盖率虚高 | 高 | 中 | 🟠 | CI 必填 fake key（仅校验 mock 路径）|
| R-08 | 性能基线（aarch64 8c）硬件差异 | 中 | 低 | 🟢 | 发布 2 份基线：aarch64 / x86_64 |

**风险等级**：🟢 低 / 🟡 中 / 🟠 高 / 🔴 严重

---

## 六、人员与角色

| 角色 | 占比 | 职责 |
|:---|:---:|:---|
| Tech Lead | 30% | 架构、PR 评审、对外沟通 |
| 后端 ×1 | 100% | 主要开发 |
| 安全 ×0.5 | 兼职 | bandit / 鉴权 / 加密 |
| DevOps ×0.5 | 兼职 | CI / 容器 / 监控 |
| QA ×0.5 | 兼职 | 接口契约 / 兼容性矩阵 |

---

## 七、发布检查清单（每次 GA 必走）

- [ ] 所有 P0/P1 关闭
- [ ] 测试通过率 ≥ 99%（真实 LLM skip 除外）
- [ ] bandit HIGH = 0
- [ ] pip-audit / OSV 无 HIGH CVE
- [ ] 性能基线 ±5%
- [ ] CHANGELOG.md 更新
- [ ] `docs/BREAKING.md`（如适用）
- [ ] Docker 镜像构建通过（linux/amd64 + linux/arm64）
- [ ] 文档站点（mkdocs）已部署
- [ ] `git tag -s vX.Y.Z -m "..."`
- [ ] GitHub Release 附 `perf.json` / `test_report.md` 摘要

---

## 八、度量指标（北极星）

| 指标 | v0.1.0 | v1.0.0 目标 |
|:---|:---:|:---:|
| 测试通过率 | 96.2% | 100% |
| 平均 P95 嵌入延迟 | 12 ms | ≤ 5 ms |
| 并发读吞吐 | 127 ops/s | ≥ 5 000 ops/s |
| MTTR（Mean Time To Repair）| n/a | ≤ 4 h |
| 安全评级 | 7.0 / 10 | ≥ 9.5 / 10 |
| 兼容性矩阵 | 1/4 | 6/6 |
| 周发版成功率 | n/a | ≥ 90% |

---

## 九、变更冻结（Change Freeze）

- **每版本 RC 标签后 7 天**：仅允许 blocker 修复
- **每 GA 标签后 14 天**：仅允许 hotfix
- **公开 API**：冻结 4 周后允许新增（不可删除/重命名）

---

## 十、附录：标签与命名

- 主版本：`v0.1.0`
- 候选：`v0.2.0-rc.1`
- 预发布：`v0.2.0-beta.1`
- 热修：`v0.1.1-hotfix.1`
- 分支：`main`（稳定）/ `develop`（活跃）/ `feature/*` / `hotfix/*`
