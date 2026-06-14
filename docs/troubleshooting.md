# 故障排除

## 启动失败

### `port 19528 already in use`

```bash
lsof -i :19528
# 或
fuser -k 19528/tcp
```

### `Permission denied` 写入 `~/.pangu/`

```bash
chown -R $USER:$USER ~/.pangu
# 或指定其他目录
PANGU_BASE_DIR=/tmp/pangu pangu-server
```

### `ModuleNotFoundError: pangu`

```bash
# 重新安装
pip install -e ".[dev]"
```

## LLM 调用失败

### `LLM API call failed: 401`

- 检查 `PANGU_LLM_API_KEY`
- 部分代理要求 `PANGU_LLM_BASE_URL` 含 `/v1` 后缀

### `Circuit breaker OPEN`

连续 5 次失败后熔断 60s。查看日志确认错误根因：
```bash
journalctl -u pangu | grep -i "embed\|llm"
```

### ONNX 模型下载失败

```bash
# 切换到国内镜像
PANGU_ONNX_MIRROR_BASE=https://hf-mirror.com

# 或完全离线（提前下载）
export HF_HUB_OFFLINE=1
```

## 性能问题

### 检索慢 (> 200ms)

- 检查 `EXPLAIN ANALYZE` 知识图谱查询
- 增大 `PANGU_LLM_CACHE_MAX`
- 启用 ONNX（已默认）

### 内存占用高

- 减少 `PANGU_LLM_CACHE_MAX`
- 减小 `PANGU_LLM_CACHE_MAX_DISK_MB`
- 周期 VACUUM

### 磁盘满

```bash
# 查看占用
du -sh ~/.pangu/*

# 清缓存
pangu-cli cache clear --all

# VACUUM
pangu-cli cache vacuum
```

## 数据问题

### 抽屉找不到

1. 检查 agent_id 是否匹配
2. 查 `memory search` 确认是否被衰减
3. 用 `pangu-cli memory list --tag <tag>` 过滤

### 数据损坏

```bash
# 1. 停止服务
systemctl stop pangu

# 2. 检查 SQLite 完整性
sqlite3 ~/.pangu/cache/cache.sqlite "PRAGMA integrity_check;"

# 3. 尝试修复
sqlite3 ~/.pangu/cache/cache.sqlite ".recover" > recovered.sql
mv recovered.sql ~/.pangu/cache/cache.sqlite

# 4. 重启
systemctl start pangu
```

### 完全重置（**会丢数据**）

```bash
systemctl stop pangu
rm -rf ~/.pangu
systemctl start pangu
```

## 监控告警

| 指标 | 阈值 | 处置 |
|:---|:---|:---|
| `pangu_api_latency_seconds{quantile="0.95"}` | > 1s | 查慢日志 |
| `pangu_llm_errors_total` 5min 增量 | > 10 | 检查 LLM 服务 |
| 磁盘使用 | > 80% | 清缓存 / 扩盘 |
| 内存 | > 1.5GB | 调 LRU 上限 |

## 调试开关

```bash
# 详细日志
PANGU_LOG_LEVEL=DEBUG pangu-server

# 仅 SQL
PANGU_LOG_LEVEL=INFO PANGU_SQL_ECHO=1 pangu-server
```

## 联系方式

- GitHub Issues（首选）
- 安全问题：security@pangu.dev
- 紧急：参见 ROADMAP 中的人员联系
