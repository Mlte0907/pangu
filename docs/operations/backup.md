# 备份与迁移

## 备份策略

### 1. 全量快照（推荐每日）

```bash
# 停止服务
systemctl stop pangu

# 打包
tar -czf /backup/pangu-$(date +%F).tar.gz \
    --exclude='*.lock' \
    -C /var/lib pangu

# 重启
systemctl start pangu
```

### 2. 增量导出（CLI 工具）

```bash
# 导出为 JSONL
pangu-cli backup export --output /backup/pangu-daily-$(date +%F).jsonl

# 加密（推荐）
age -p /backup/pangu-daily-2026-06-08.jsonl > /backup/pangu-daily-2026-06-08.jsonl.age
```

### 3. 仅 SQLite（小时级）

```bash
# 在线备份（不锁表）
sqlite3 ~/.pangu/cache/cache.sqlite ".backup /backup/cache-$(date +%H).sqlite"
```

## 保留策略

- 日级：保留 7 天
- 周级：保留 4 周
- 月级：保留 12 个月
- 总磁盘：不超过 50 GB

通过 `cleanup.sh` 周期清理。

## 恢复

### 全量

```bash
systemctl stop pangu
rm -rf /var/lib/pangu
tar -xzf /backup/pangu-2026-06-08.tar.gz -C /var/lib
systemctl start pangu
```

### 从 JSONL

```bash
# 导入新实例
pangu-cli backup import --input /backup/pangu-2026-06-08.jsonl

# 验证
pangu-cli memory stats
pangu-cli kg stats
```

## 跨实例迁移

```bash
# 源
pangu-cli backup export --output - | gzip > pangu.jsonl.gz

# 网络传输 + 导入
scp pangu.jsonl.gz user@new-host:
ssh user@new-host 'pangu-cli backup import --input - < pangu.jsonl.gz'
```

## 自动化

```bash
#!/bin/bash
# /etc/cron.daily/pangu-backup
set -e
systemctl stop pangu
sleep 2
tar -czf /backup/pangu-$(date +%F).tar.gz -C /var/lib pangu
systemctl start pangu
# 清理 7 天前
find /backup -name 'pangu-*.tar.gz' -mtime +7 -delete
```

## 灾难恢复 RTO/RPO

| 等级 | 场景 | RTO | RPO |
|:---|:---|:---:|:---:|
| 服务中断 | 进程崩溃 | < 1 min | 0（无丢失）|
| 主机故障 | OS 不可用 | < 10 min | < 1 天 |
| 数据损坏 | 误操作 / 攻击 | < 30 min | < 1 天 |
| 站点级灾难 | IDC 故障 | < 4 h | < 1 天 |

## 完整性校验

```bash
# 校验 archive
sha256sum -c pangu-2026-06-08.sha256

# 校验数据库
sqlite3 ~/.pangu/cache/cache.sqlite "PRAGMA integrity_check;"
```

## 注意事项

- ⚠️ 备份前必须停止服务或用 SQLite `.backup`
- ⚠️ 不要只备份 SQLite，必须包含 ChromaDB 目录
- ⚠️ 加密备份的密钥单独管理
- ⚠️ 定期演练恢复流程（建议季度）
