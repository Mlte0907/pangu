# 监控与可观测性

## 健康检查

### 快速

```bash
curl http://127.0.0.1:19529/health
```

返回：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "healthy",
    "uptime_s": 3600,
    "version": "0.1.0",
    "components": {
      "db": "ok",
      "cache": "ok",
      "embedder": "ok"
    }
  }
}
```

### 深度

```bash
curl http://127.0.0.1:19529/health/deep
```

会探测：ChromaDB 连通 / SQLite 写权限 / 嵌入器可推理 / 知识图谱完整性。

## Prometheus 指标

`GET /metrics` 暴露：

| 指标 | 类型 | 标签 |
|:---|:---|:---|
| `pangu_api_requests_total` | counter | method, path, status |
| `pangu_api_latency_seconds` | histogram | method, path |
| `pangu_llm_calls_total` | counter | provider, model, status |
| `pangu_llm_tokens_total` | counter | provider, model, direction |
| `pangu_llm_cache_hits_total` | counter | layer (memory/disk) |
| `pangu_llm_cache_misses_total` | counter | |
| `pangu_embed_calls_total` | counter | backend (api/onnx/hash), status |
| `pangu_embed_latency_seconds` | histogram | backend |
| `pangu_memory_drawers_total` | gauge | layer (L0/L1/L2/L3) |
| `pangu_memory_importance_avg` | gauge | layer |
| `pangu_kg_entities_total` | gauge | |
| `pangu_kg_relations_total` | gauge | predicate |
| `pangu_disk_bytes` | gauge | path |
| `pangu_process_uptime_seconds` | gauge | |

### 抓取配置（prometheus.yml）

```yaml
scrape_configs:
  - job_name: pangu
    metrics_path: /metrics
    static_configs:
      - targets: ['127.0.0.1:19529']
    scrape_interval: 15s
```

### Grafana 推荐面板

- API P50 / P95 / P99 延迟
- LLM 调用成功率 / 缓存命中率
- 嵌入器后端占比（api/onnx/hash）
- 记忆层容量趋势
- 知识图谱增长

## 日志

### 格式

```json
{
  "ts": "2026-06-08T15:30:00.123+08:00",
  "level": "INFO",
  "logger": "pangu.api.server",
  "msg": "Memory added",
  "drawer_id": "d_2026-06-08_a1b2c3",
  "agent_id": "agent-001",
  "took_ms": 18
}
```

### 级别

- `DEBUG` 详细，含 SQL / 内部状态
- `INFO` 关键事件（写入、检索、错误）
- `WARNING` 降级、重试
- `ERROR` 异常但服务可用
- `CRITICAL` 服务不可用

通过 `PANGU_LOG_LEVEL=DEBUG` 控制。

## 追踪（v0.3+）

- OpenTelemetry 协议
- span 维度：HTTP / LLM / Embed / Storage
- exporter: OTLP / Jaeger

## 审计

- 所有写入操作记录到 `audit.log`（包含 agent_id、drawer_id、ip、ts）
- 保留 90 天
- 通过 `pangu-cli audit query` 检索

## 告警规则示例

```yaml
# alerts.yml
groups:
  - name: pangu
    rules:
      - alert: PanguHighLatency
        expr: histogram_quantile(0.95, pangu_api_latency_seconds) > 1
        for: 5m
        labels: {severity: warning}
      - alert: PanguLLMErrors
        expr: rate(pangu_llm_calls_total{status!="ok"}[5m]) > 0.1
        for: 5m
        labels: {severity: critical}
      - alert: PanguDiskFull
        expr: pangu_disk_bytes / 1024^3 > 8
        for: 10m
        labels: {severity: warning}
```
