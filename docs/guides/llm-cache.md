# LLM 响应缓存

> 双级缓存架构：内存 LRU + 持久化 SQLite，重启不丢，命中率透明可观测。

## 概述

盘古的 LLM 引擎内置了一套完整的企业级缓存体系，覆盖写入、查询、维护、预热、监控全链路。

## 缓存架构

```
LLM 调用 chat(messages)
       │
       ▼
  ① 计算请求指纹（SHA-256 of messages+model+params）
       │
       ├──→ ② 内存 LRU 缓存（默认 128 条，O(1) 访问）
       │         │
       │         └─ 命中 → 直接返回（hit_count++）
       │         └─ 未命中 ↓
       │
       └──→ ③ 持久化 SQLite 缓存（默认 100MB / 7天 TTL）
                 │
                 └─ 命中 → 写回内存 + 返回（disk_hit++）
                 └─ 未命中 ↓
       │
       ▼
  ④ 实际调用 LLM API
       │
       ├──→ 写入内存缓存（同步）
       ├──→ 异步节流写入 SQLite（默认每 10 次 flush）
       └──→ 更新 Prometheus 指标
```

## 核心特性

- **双级缓存**：内存 LRU（速度） + 磁盘 SQLite（持久化、跨重启）
- **智能淘汰**：LRU + 命中率加权，长期不访问自动清理
- **写入节流**：高频调用时不频繁 flush SQLite，平衡性能与可靠性
- **TTL 过期**：默认 7 天过期，可配置
- **磁盘限额**：默认 100MB，超限触发 LRU 清理
- **缓存预热**：启动时自动批量填充热点 prompt
- **完整审计**：每次预热 / VACUUM 都有结构化日志
- **Prometheus 全指标**：12 个核心指标 + 4 个高级告警

## 配置

所有配置通过 `~/.pangu/config.json` 和环境变量管理。

| 配置 | 环境变量 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `llm_cache_enabled` | `PANGU_LLM_CACHE_ENABLED` | `true` | 总开关 |
| `llm_cache_max` | `PANGU_LLM_CACHE_MAX` | `128` | 内存 LRU 容量 |
| `llm_cache_persist` | `PANGU_LLM_CACHE_PERSIST` | `true` | 启用持久化 |
| `llm_cache_persist_path` | `PANGU_LLM_CACHE_PERSIST_PATH` | `~/.pangu/llm_cache.db` | SQLite 路径 |
| `llm_cache_ttl_days` | `PANGU_LLM_CACHE_TTL_DAYS` | `7` | 过期时间（天） |
| `llm_cache_max_disk_mb` | `PANGU_LLM_CACHE_MAX_DISK_MB` | `100` | 磁盘限额（MB） |
| `llm_cache_write_throttle` | `PANGU_LLM_CACHE_WRITE_THROTTLE` | `10` | 每 N 次写一次盘 |
| `llm_cache_warmup_on_start` | `PANGU_LLM_CACHE_WARMUP_ON_START` | `false` | 启动时自动预热 |
| `llm_cache_warmup_prompts` | - | `[]` | 预热 prompt 列表（JSON） |
| `llm_cache_vacuum_on_start` | `PANGU_LLM_CACHE_VACUUM_ON_START` | `false` | 启动时自动 VACUUM |
| `llm_cache_vacuum_interval_hours` | `PANGU_LLM_CACHE_VACUUM_INTERVAL_HOURS` | `0` | 周期 VACUUM（0=禁用） |

## CLI 使用

```bash
# 缓存统计
pangu llm-cache-stats

# 导出 Prometheus 指标
pangu llm-cache-metrics

# 查看访问最频繁的缓存条目
pangu llm-cache-top --limit 10

# 清空缓存
pangu llm-cache-clear --memory --persistent

# 预热缓存（从 JSON 文件）
pangu llm-cache-warmup --file prompts.json --concurrency 3

# 查看预热审计日志
pangu llm-cache-warmup-log --limit 20

# VACUUM 释放 SQLite 碎片
pangu llm-cache-vacuum
```

## MCP 工具

| 工具 | 说明 |
|:---|:---|
| `pangu_llm_cache_stats` | 完整统计（命中、未命中、token、成本、磁盘） |
| `pangu_llm_cache_top` | Top-N 热点条目 |
| `pangu_llm_cache_clear` | 清空缓存 |
| `pangu_llm_cache_metrics` | Prometheus 指标导出 |
| `pangu_llm_cache_warmup` | 手动预热 |
| `pangu_llm_cache_warmup_log` | 预热审计记录 |
| `pangu_llm_cache_vacuum` | 立即执行 VACUUM 释放碎片 |
| `pangu_llm_cache_config` | 查看当前缓存配置 |

## 缓存预热

### 配置预热 prompt

`~/.pangu/config.json` 中配置：

```json
{
  "llm_cache_warmup_on_start": true,
  "llm_cache_warmup_prompts": [
    {
      "messages": [{"role": "user", "content": "你好"}],
      "temperature": 0.7,
      "max_tokens": 256
    },
    {
      "system": "你是盘古记忆系统的助手。",
      "messages": [{"role": "user", "content": "自我介绍"}],
      "temperature": 0.3
    }
  ]
}
```

### 预热行为

- **skip_existing**: 跳过已缓存的 prompt（避免重复调用）
- **并发控制**: 默认并发 3，防止触发 rate limit
- **审计日志**: 每次预热写入 `~/.pangu/logs/llm_cache_warmup.log`

## VACUUM 维护

SQLite 在大量删除/更新后会产生碎片。盘古提供三种 VACUUM 方式：

### 手动

```bash
pangu llm-cache-vacuum
```

### 启动时自动

```json
{
  "llm_cache_vacuum_on_start": true
}
```

### 周期执行

```json
{
  "llm_cache_vacuum_interval_hours": 24
}
```

每次 VACUUM 会写入审计日志：

```json
{"ts": 1717850000.123, "event": "llm_cache_vacuum", "interval_hours": 24,
 "before_bytes": 1048576, "after_bytes": 891289, "freed_bytes": 157287,
 "duration_ms": 42.7, "skipped": false}
```

## 监控指标

### Prometheus 指标

| 指标 | 类型 | 说明 |
|:---|:---|:---|
| `pangu_llm_calls_total` | counter | 实际 LLM 调用次数 |
| `pangu_llm_cache_hits_total` | counter | 总缓存命中次数 |
| `pangu_llm_cache_memory_hits_total` | counter | 内存 LRU 命中 |
| `pangu_llm_cache_disk_hits_total` | counter | 持久化命中 |
| `pangu_llm_cache_misses_total` | counter | 缓存未命中 |
| `pangu_llm_cache_hit_rate` | gauge | 缓存命中率（%） |
| `pangu_llm_prompt_tokens_total` | counter | 输入 token 累计 |
| `pangu_llm_completion_tokens_total` | counter | 输出 token 累计 |
| `pangu_llm_cost_usd_total` | counter | 估算成本（USD） |
| `pangu_llm_cache_writes_total` | counter | 持久化写入次数 |
| `pangu_llm_persistent_cache_entries` | gauge | 持久化条目数 |
| `pangu_llm_persistent_cache_bytes` | gauge | 持久化占用字节数 |

### Grafana 大盘

- **`pangu-llm-cache.json`** — 独立 LLM 缓存大盘（22 个面板）
- **`pangu-overview.json`** — 总览大盘新增 3 个 LLM 缓存面板

### 告警规则

| 告警 | 严重度 | 触发条件 |
|:---|:---|:---|
| `PanguLLMCacheLowHitRate` | warning | 命中率 < 30% 持续 10m |
| `PanguLLMCacheDisabled` | warning | > 100 次调用 0 命中 |
| `PanguLLMHighCost` | warning | 1 小时成本 > $5 |
| `PanguLLMCacheDiskNearFull` | warning | 磁盘占用 > 90% |
| `PanguLLMCacheDiskCritical` | critical | 磁盘占用 > 98% |

详见 [告警规则配置](../../../monitoring/alerts.yml)。
