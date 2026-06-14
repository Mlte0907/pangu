# 盘古 v0.1.0 系统优化方案

> 配套：`reports/TEST_REPORT.md`
> 适用范围：所有后续大版本（v0.2 → v1.0+）将以本方案为基线演进
> 编写时间：2026-06-08

---

## 一、优化目标总览

| 维度 | 当前（v0.1.0）| 目标（v0.2.0）| 目标（v1.0.0）|
|:---|:---:|:---:|:---:|
| 缺陷清零 | D-001 ~ D-011 | D-001/002/003/004/005/008 关闭 | 全部关闭 + 0 P1/P2 |
| 测试通过率 | 96.2% | ≥ 99% | 100%（除 skip）|
| 性能 / 吞吐 | 127 ops/s | ≥ 1 000 ops/s（SQLite 并发）| ≥ 5 000 ops/s |
| ONNX embed 延迟 | 0.42 ms | ≤ 0.30 ms | ≤ 0.20 ms |
| 安全评级 | 7.0 | ≥ 8.5 | ≥ 9.5 |
| 兼容性 | 3.12 / aarch64 | 3.10-3.12 / linux x86_64+aarch64 | 同上 + Windows WSL2 |
| CI 时长 | - | ≤ 6 min | ≤ 4 min |
| 启动时间 | - | ≤ 3 s（冷启动）| ≤ 1.5 s |

---

## 二、按缺陷的优化措施（优先级排序）

### P1 必修

#### OPT-1 修复 embedding.py 字段名错位（D-001）
- **目标**：恢复 external LLM 嵌入 API 路径
- **步骤**：
  1. 统一 `PanguConfig.embed_api_url` → `embedding_api_url`，**或**将 `embedding.py:209,251` 改为 `embed_api_url`
  2. 二选一后全局 grep 校验
  3. 单元测试：注入 mock 后端 + 假 URL，断言 `httpx.post` 被正确调用
- **预期**：external 嵌入命中率 ≥ 50%，节省 ONNX 推理 10-20%
- **资源**：1 人日

#### OPT-2 修复 test_bench 签名错位（D-002）
- **目标**：2 个性能基准用例恢复
- **步骤**：
  1. `test_bench.py:211, 223` 改用 `KnowledgeGraph(cfg)`
  2. 加 `--junitxml` 验证
- **预期**：基准套件 21/21 全过
- **资源**：0.25 人日

### P2 应修

#### OPT-3 鉴权中间件（D-004）
- **目标**：写端点强制 API Key，读端点可选
- **步骤**：
  1. 新增 `pangu/api/middleware/auth.py`：`verify_api_key` 依赖注入
  2. 仅对 `/api/v2/memory/*` `/api/v2/drawer/*` `/api/v2/system/*` 写方法生效
  3. 写端点无 key → 401；写端点 key 错 → 403
  4. 文档 + `.env.example` 增 `PANGU_API_KEY=...`
- **预期**：bandit B104 由「无鉴权」变为「有差分」；安全评分 +0.5
- **资源**：1.5 人日

#### OPT-4 替换 urllib → httpx（D-005）
- **目标**：消除 4 处 bandit 标记
- **步骤**：
  1. 全仓 `urllib.request` / `urllib.error` 替换为 `httpx` 或 `httpx.AsyncClient`
  2. 替换超时与重试逻辑
- **预期**：bandit B310/B311 归零
- **资源**：0.5 人日

#### OPT-5 修复 MD5 全部用例（D-003）
- **目标**：消除 22 项 bandit HIGH
- **步骤**：
  1. 在 `pangu/memory/*` 引入 `_hash_chunk(content: str) -> str` 内部工具函数
  2. 内部用 `hashlib.blake2b(digest_size=16)`（更快更安全）
  3. 加 `bandit.yaml` 抑制误报，标记 B324 在「cache key generation」豁免
- **预期**：bandit HIGH 由 22 降至 0；缓存键长度保持 32 hex
- **资源**：1 人日

#### OPT-6 依赖 CVE 修复（D-008）
- **目标**：python-multipart ≥ 0.0.18
- **步骤**：
  1. `requirements.txt` / `pyproject.toml` 锁定 `python-multipart>=0.0.18`
  2. 加 Dependabot / Renovate 周更
  3. CI 中加 `pip-audit` 步骤
- **预期**：OSV 命中从 18 降至 0
- **资源**：0.5 人日

#### OPT-7 SQLite 并发与性能优化（D-009）
- **目标**：并发读 ≥ 1 000 ops/s，写入 ≤ 1 ms
- **步骤**：
  1. 启用 `PRAGMA journal_mode=WAL`（写不阻塞读）
  2. 每线程持有一个 `sqlite3.Connection`（`threading.local`）
  3. `write_throttle` 默认改为 50
  4. 引入 `PersistentCache.metrics()` 输出命中/未命中/延迟分位数
- **预期**：写 ≤ 1 ms、读 ≤ 0.5 ms、并发 ≥ 1 k ops/s
- **资源**：2 人日

### P3 建议修

#### OPT-8 host 默认改 127.0.0.1（D-006）
- **步骤**：`PanguConfig.host` 默认 `"127.0.0.1"`；通过 `PANGU_HOST=0.0.0.0` 显式开启
- **资源**：0.1 人日

#### OPT-9 全局异常信封（D-007）
- **步骤**：在 `create_app()` 注册 `exception_handler(HTTPException)`，统一为 `{code,message,data}`；404 → `code=40400`
- **资源**：0.5 人日

#### OPT-10 hnswlib 缺失（D-010）
- **步骤**：`pyproject.toml` 显式声明 `hnswlib>=0.7`（条件依赖 aarch64 wheel 不可用时降级）；CI 验证两种路径
- **资源**：0.5 人日

#### OPT-11 random → seeded RNG（D-011）
- **步骤**：`attention.py:113` 改用 `numpy.random.default_rng(seed)`；需评估是否影响功能
- **资源**：0.25 人日

#### OPT-12 低危清理（B110/B112/B603/B607）
- **步骤**：批量把 `try: ... except: pass` 改为 `except SpecificError: logger.debug(...)`；subprocess 调用补绝对路径
- **资源**：1 人日

---

## 三、性能优化专项（独立于缺陷修复）

| 项目 | 当前 | 目标 | 措施 |
|:---|:---:|:---:|:---|
| 嵌入器冷启动 | 数百 ms | ≤ 200 ms | 进程内 ONNX session 池；预加载 model |
| LLM 缓存命中 | 未知 | ≥ 60% | 默认 `write_throttle=10`；TTL 7 → 30 天 |
| 记忆抽屉读取 | 1.55 ms / 100 条 | ≤ 0.5 ms / 1000 条 | SQLite WAL + 倒排索引 |
| 知识图谱查询 | 未知 | 1k 实体 p99 ≤ 50 ms | 引入边类型二级索引 |
| 搜索混合 | 网络依赖 | 离线可用 | 用 ONNX embedder 替代 st 远程模型 |

---

## 四、资源需求

| 阶段 | 人日 | 关键人员 | 时间窗 |
|:---|---:|:---|:---|
| P1 必修（OPT-1,2）| 1.25 | 后端 ×1 | 1 周内 |
| P2 应修（OPT-3,4,5,6,7）| 5.5 | 后端 ×1，安全 ×0.5 | 2-3 周 |
| P3 建议（OPT-8,9,10,11,12）| 2.35 | 后端 ×1 | 4-5 周 |
| 性能专项 | 5 | 后端 ×1，算法 ×0.5 | 4-6 周 |
| CI/测试基建 | 3 | DevOps ×0.5，后端 ×0.5 | 1-2 周 |
| **合计** | **~17 人日** | 1-2 人 | **6 周** |

外部资源：无（不开新服务器；CI 沿用 GitHub Actions 免费层）

---

## 五、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|:---|:---:|:---:|:---|
| OPT-1 字段名改后外部 API 实际仍不可用 | 中 | 低 | 兜底 ONNX 仍工作；不影响主路径 |
| OPT-5 blake2b 改变键值导致缓存全部失效 | 高 | 中 | 在 `PersistentCache` 中加 `key_algo` 配置；首次启动空池自然恢复 |
| OPT-7 WAL 模式与现有 fixture 冲突 | 低 | 中 | 单元测试改为独立 db_path；CI 用 tmp_path |
| hnswlib aarch64 wheel 缺失 | 中 | 中 | 提供 `pip install --no-deps pangu-core` 路径；文档明示 |
| OPT-3 鉴权影响 MCP | 中 | 高 | MCP 通过本地 socket 不走 HTTP，无需 key；CI 覆盖该路径 |

---

## 六、验证机制

1. **单元 / 集成**：每 OPT 完成后跑 `pytest`，通过率 ≥ 99%
2. **性能回归**：`tests/manual_perf.py` 自动比较基线；性能降低 > 5% 报警
3. **安全回归**：`bandit -r pangu` HIGH = 0；`pip-audit` 无 HIGH CVE
4. **CI 矩阵**：Python 3.10 / 3.11 / 3.12 × linux x86_64 + linux aarch64

---

## 七、不在本次范围（v2.x 候选）

- 分布式部署 / 多副本一致性
- 端到端加密静态数据
- 多租户隔离
- Web UI（推荐 React + 实时仪表盘）
- 联邦学习 / 跨实例知识合并
