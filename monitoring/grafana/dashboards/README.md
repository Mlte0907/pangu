# 盘古 Grafana 监控大盘使用指南

本文档介绍如何导入和使用盘古（Pangu）项目的 2 个 Grafana 监控大盘。

---

## 1. 前置条件

- **Grafana** 已部署并可访问
- **Prometheus** 已部署，且 `pangu` 服务的 `/metrics` 端点正在被采集（参见 `monitoring/prometheus.yml`）
- Prometheus 数据源已在 Grafana 中配置，名称为 `Prometheus`，URL 指向 `http://prometheus:9090`

### Prometheus 数据源配置（自动部署）

通过 provisioning 文件可自动创建数据源，无需手动操作：

```yaml
# monitoring/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

如需手动添加数据源：
1. 进入 **Configuration → Data Sources → Add data source**
2. 选择 **Prometheus**
3. URL 填写 `http://prometheus:9090`
4. 点击 **Save & Test**

---

## 2. 如何导入大盘

### 方式 A：Provisioning 自动导入（推荐）

将 JSON 文件放入 Grafana provisioning 目录即可自动加载：

```bash
# 将大盘文件复制到 provisioning 目录
cp monitoring/grafana/dashboards/*.json /var/lib/grafana/dashboards/

# Grafana 会按以下配置自动扫描（每 30 秒检查一次）
# monitoring/grafana/provisioning/dashboards/pangu.yml
```

Provisioning 配置内容：

```yaml
apiVersion: 1

providers:
  - name: "盘古"
    folder: ""
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

### 方式 B：通过 Grafana UI 手动导入

1. 进入 Grafana，点击左侧菜单 **Dashboards → Import**
2. 点击 **Upload JSON file**，选择 `pangu-llm-cache.json` 或 `pangu-overview.json`
3. 在 **Prometheus** 下拉框中选择已配置的 Prometheus 数据源
4. 点击 **Import**

### 方式 C：通过 API 导入

```bash
# 导入 LLM 缓存大盘
curl -X POST http://<grafana-host>:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_KEY>" \
  -d @monitoring/grafana/dashboards/pangu-llm-cache.json

# 导入总览大盘
curl -X POST http://<grafana-host>:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_KEY>" \
  -d @monitoring/grafana/dashboards/pangu-overview.json
```

---

## 3. 大盘说明

### 3.1 盘古 — LLM 缓存大盘 (`pangu-llm-cache.json`)

**专用 LLM 缓存监控大盘**，共 22 个面板，覆盖缓存性能、成本、延迟等全维度指标。

| 面板 ID | 面板名称 | 类型 | 说明 |
|:---:|---|---|---|
| 1 | 缓存命中率 | Stat | LLM 响应缓存命中率（0-100%），带红/橙/黄/绿阈值 |
| 2 | 节省成本 (USD) | Stat | 通过缓存节省的 LLM 调用成本估算 |
| 3 | 调用次数/分钟 | Stat | 实际 LLM API 调用速率（缓存未命中） |
| 4 | P95 延迟 (ms) | Stat | 按 provider/model 拆分的 P95 延迟 |
| 5 | 缓存命中率时间线 | Time Series | 按 provider/model 拆分的命中率趋势 |
| 6 | 缓存命中数（按层） | Time Series | 内存层 vs 磁盘层 命中数（堆叠图） |
| 7 | 缓存来源分布 | Pie Chart | 内存 vs 磁盘命中占比 |
| 8 | Token 使用量 | Time Series | 按 type（prompt/completion）拆分的 token 消耗 |
| 9 | 成本累积 | Time Series | 按 provider 聚合的累计成本 |
| 10 | 内存缓存大小 | Bar Gauge | LRU 内存缓存当前条目数（阈值：100/120） |
| 11 | 持久化缓存大小 | Bar Gauge | SQLite 磁盘缓存条目数 |
| 12 | 磁盘占用 (MB) | Gauge | 持久化缓存磁盘占用（阈值：50MB/90MB） |
| 13 | LLM 调用延迟热力图 | Heatmap | 按时间分桶的延迟分布 |
| 14 | Provider / Model 性能对比 | Table | 按 provider/model 聚合的关键指标 |
| 15 | 累计命中次数 | Time Series | 持久化缓存的累计命中数（重启后保持） |
| 16 | Provider/Model 命中率拆分 | Time Series | 按 provider/model 拆分缓存命中率 |
| 17 | Provider 调用量分布 | Bar Chart | 按 provider 聚合的累计 LLM 调用次数 |
| 18 | 缓存写入速率 (ops/s) | Time Series | 持久化缓存的写入速率（节流后） |
| 19 | 累计节省 Token | Stat | 通过缓存命中累计节省的 token 数 |
| 20 | 磁盘使用率 | Gauge | 持久化缓存磁盘占用百分比（阈值：60%/80%/95%） |
| 21 | 每次调用成本 (USD) | Time Series | LLM 实际调用成本速率 |
| 22 | Provider 健康度总览 | Table | 每个 provider 的核心指标一览（调用量、命中率、延迟、成本） |

**默认时间范围**: 最近 6 小时（`now-6h` → `now`），自动刷新间隔 10 秒。

### 3.2 盘古 — 记忆系统总览 (`pangu-overview.json`)

**全局总览大盘**，覆盖盘古系统的服务状态、记忆系统、引擎、嵌入服务等核心指标，并新增了 5 个 LLM 缓存面板（面板 11-17）。

| 面板 ID | 面板名称 | 说明 |
|:---:|---|---|
| 1 | 服务状态 | 盘古 API UP/DOWN 状态 |
| 2 | 活跃记忆数 | 当前活跃记忆条目数 |
| 3 | API QPS | 每秒请求数 |
| 4 | P95 延迟 (s) | API 端点 P95 响应时间 |
| 5 | 记忆写入速率 | 按 wing 分类的记忆创建速率 |
| 6 | API 请求速率 (按状态码) | 按 HTTP 状态码拆分的请求速率 |
| 7 | 引擎运行耗时 P50/P95/P99 | 各引擎的延迟分位数 |
| 8 | 嵌入 API 延迟 + 成功率 | 嵌入服务 P95 延迟和成功率 |
| 9 | 引擎错误率 | 各引擎的错误速率 |
| 10 | Top 10 慢 API 端点 | 最慢的 10 个 API 路径 |
| **11** | **LLM 缓存命中率** | 所有 LLM 调用的平均缓存命中率 |
| **12** | **LLM 缓存条目** | 内存+磁盘总条目数 |
| **13** | **累计成本 (USD)** | 所有 LLM 调用的累计估算成本 |
| **14** | **LLM 缓存命中 vs 实际调用** | 缓存命中速率 vs 实际 API 调用速率对比 |
| **15** | **节省 Token (累计)** | 通过缓存命中累计节省的 token 数 |
| **16** | **持久化缓存磁盘占用** | SQLite 缓存文件大小（MB） |
| **17** | **节省成本速率 (USD/h)** | 通过缓存命中按小时估算的节省成本 vs 实际成本 |

**默认时间范围**: 最近 1 小时（`now-1h` → `now`），自动刷新间隔 10 秒。

---

## 4. 数据源配置

两个大盘均内置了 `datasource` 模板变量：

| 变量名 | 类型 | 查询值 | 默认值 |
|---|---|---|---|
| `datasource` | datasource | `prometheus` | `Prometheus` |

如果在 UI 中切换数据源，大盘会自动使用所选数据源查询指标。

### 核心指标速查

| 指标名 | 类型 | 说明 |
|---|---|---|
| `pangu_llm_cache_hit_rate` | Gauge | 缓存命中率（%） |
| `pangu_llm_calls_total` | Counter | LLM 调用总次数 |
| `pangu_llm_cache_hits_total` | Counter | 缓存命中总次数（带 `layer` 标签） |
| `pangu_llm_cost_usd_total` | Counter | 累计成本（USD） |
| `pangu_llm_latency_seconds_bucket` | Histogram | 延迟分布 |
| `pangu_llm_tokens_total` | Counter | Token 消耗（带 `type` 标签） |
| `pangu_llm_cache_size` | Gauge | 缓存条目数（带 `layer` 标签） |
| `pangu_llm_cache_bytes` | Gauge | 磁盘缓存占用（字节） |
| `pangu_llm_memory_cache_size` | Gauge | 内存缓存条目数 |
| `pangu_llm_persistent_cache_bytes` | Gauge | 持久化缓存磁盘占用（字节） |
| `pangu_llm_persistent_cache_max_bytes` | Gauge | 持久化缓存最大容量（字节） |

---

## 5. 大盘变量与筛选

当前大盘支持通过内置的 `datasource` 变量切换数据源。各面板中的 `provider` 和 `model` 维度通过 Prometheus 指标的标签自动拆分（`{{provider}}/{{model}}`），无需额外配置筛选器。

如需添加 provider/model 筛选变量，可在 Grafana 中编辑大盘，进入 **Dashboard settings → Variables → Add variable**，示例配置：

```
Name:        provider
Type:        Query
Data source: Prometheus
Query:       label_values(pangu_llm_calls_total, provider)
Multi-value: ✓
Include All: ✓
```

---

## 6. 告警集成

Grafana 大盘与 Prometheus 告警规则（`monitoring/alerts.yml`）配合使用。大盘提供可视化，告警规则提供主动通知。

### LLM 缓存相关告警规则

| 告警名称 | 触发条件 | 严重级别 | 说明 |
|---|---|---|---|
| `PanguLLMCacheLowHitRate` | `pangu_llm_cache_hit_rate < 30` 持续 10 分钟 | warning | 缓存命中率偏低（<30%） |
| `PanguLLMCacheDisabled` | >100 次调用 0 命中，持续 5 分钟 | warning | 缓存完全未生效 |
| `PanguLLMHighCost` | 1 小时累计成本 > $5，持续 30 分钟 | warning | LLM 成本过高 |
| `PanguLLMPersistentCacheLarge` | 持久化缓存 > 100MB，持续 30 分钟 | info | 磁盘占用过大 |
| `PanguLLMSlowCalls` | P95 延迟 > 10s，持续 5 分钟 | warning | LLM 调用过慢 |
| `PanguLLMCacheDiskNearFull` | 磁盘占用率 > 90%，持续 15 分钟 | warning | 持久化缓存即将写满 |
| `PanguLLMCacheDiskCritical` | 磁盘占用率 > 98%，持续 5 分钟 | critical | 磁盘即将写满 |
| `PanguLLMMemoryCacheExhausted` | 内存缓存条目数触顶，持续 10 分钟 | info | 内存 LRU 缓存已满 |
| `PanguLLMCacheWritesFailure` | 有调用但 0 写入，持续 10 分钟 | warning | 持久化缓存写入异常 |
| `PanguLLMCacheHighLatency` | 缓存查找 P95 > 50ms，持续 5 分钟 | warning | 缓存查找过慢 |
| `PanguLLMWarmupNoRecords` | 预热超 24 小时未成功，持续 5 分钟 | info | 启动预热失败 |

### 其他系统告警

| 告警组 | 包含规则 |
|---|---|
| `pangu_api_alerts` | API 不可用、5xx 错误率 >5%、P95 响应 >1s |
| `pangu_memory_alerts` | 记忆增长 >100/分钟、搜索错误率过高 |
| `pangu_embedding_alerts` | 嵌入服务全失败、P95 延迟 >2s |
| `pangu_engine_alerts` | 引擎错误率飙升、引擎运行超时（P99 >30s） |

### 告警规则加载

告警规则在 `monitoring/prometheus.yml` 中引用：

```yaml
rule_files:
  - "alerts.yml"
```

确保 `alerts.yml` 与 `prometheus.yml` 在同一目录，或 Prometheus 启动参数指定了正确的 `--rule-files` 路径。

---

## 7. Docker Compose 一键部署

如果使用 `docker-compose.yml` 部署完整监控栈，大盘会通过 provisioning 自动加载：

```bash
# 确保目录结构正确
monitoring/
├── prometheus.yml
├── alerts.yml
└── grafana/
    ├── provisioning/
    │   ├── datasources/prometheus.yml
    │   └── dashboards/pangu.yml
    └── dashboards/
        ├── pangu-llm-cache.json
        └── pangu-overview.json

# 启动服务
docker compose up -d
```

启动后访问 `http://<host>:3000`，在 **Dashboards** 列表中即可看到：
- **盘古 — LLM 缓存大盘**
- **盘古 — 记忆系统总览**
