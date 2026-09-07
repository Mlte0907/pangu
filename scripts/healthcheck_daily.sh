#!/usr/bin/env bash
# 盘古每日健康巡检（无 root 的轻量监控方案，替代 Prometheus 部署）
# 检查：服务存活 / 认证有效性 / 数据完整性 / 备份时效 / 磁盘空间
# 由 cron 每日 08:00 执行，异常输出 ALERT 标记便于 grep
set -uo pipefail

LOG="/home/xiaoxin/backup/pangu/healthcheck.log"
API_KEY=$(python3 -c "import json; print(json.load(open('/home/xiaoxin/.pangu/config.json'))['api_key'])" 2>/dev/null)
ts() { date '+%F %T'; }
ALERTS=0

echo "[$(ts)] === 盘古每日巡检 ===" >> "$LOG"

# 1. 服务存活 + 响应时间
HEALTH=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 5 http://127.0.0.1:19529/health 2>/dev/null)
CODE=${HEALTH%% *}; TTIME=${HEALTH##* }
if [ "$CODE" = "200" ]; then
    echo "[$(ts)] OK   /health 200 (${TTIME}s)" >> "$LOG"
else
    echo "[$(ts)] ALERT /health 异常: $HEALTH" >> "$LOG"; ALERTS=$((ALERTS+1))
fi

# 2. 认证冒烟：无 key 必须 401，带 key 必须 200
NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:19529/api/v2/memories 2>/dev/null)
WITHAUTH=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $API_KEY" http://127.0.0.1:19529/api/v2/memories 2>/dev/null)
if [ "$NOAUTH" = "401" ] && [ "$WITHAUTH" = "200" ]; then
    echo "[$(ts)] OK   认证边界正常 (无key=$NOAUTH 带key=$WITHAUTH)" >> "$LOG"
else
    echo "[$(ts)] ALERT 认证异常! 无key=$NOAUTH 带key=$WITHAUTH (期望 401/200)" >> "$LOG"; ALERTS=$((ALERTS+1))
fi

# 3. 记忆数据 JSON 完整性（曾发生并发写入损坏，静默带病运行半月）
for f in /home/xiaoxin/.pangu/palace/drawers.json /home/xiaoxin/.pangu/pangu.db/v2_memories/drawers.json; do
    if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
        echo "[$(ts)] OK   JSON 完整: $f" >> "$LOG"
    else
        echo "[$(ts)] ALERT JSON 损坏: $f" >> "$LOG"; ALERTS=$((ALERTS+1))
    fi
done

# 4. 备份时效（>25 小时视为过期）
LATEST=$(ls -1t /home/xiaoxin/backup/pangu/pangu_backup_*.tar.gz 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    AGE_H=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
    if [ "$AGE_H" -le 25 ]; then
        echo "[$(ts)] OK   备份新鲜: ${LATEST##*/} (${AGE_H}h 前)" >> "$LOG"
    else
        echo "[$(ts)] ALERT 备份过期: 最近一份已 ${AGE_H} 小时" >> "$LOG"; ALERTS=$((ALERTS+1))
    fi
else
    echo "[$(ts)] ALERT 无任何备份文件!" >> "$LOG"; ALERTS=$((ALERTS+1))
fi

# 5. 磁盘空间（>85% 报警）
DISK_PCT=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "$DISK_PCT" -le 85 ]; then
    echo "[$(ts)] OK   磁盘使用 ${DISK_PCT}%" >> "$LOG"
else
    echo "[$(ts)] ALERT 磁盘使用 ${DISK_PCT}% 超过 85%" >> "$LOG"; ALERTS=$((ALERTS+1))
fi

# 6. 服务状态（用户级 systemd）
SVC=$(systemctl --user is-active pangu-api.service 2>/dev/null)
if [ "$SVC" = "active" ]; then
    echo "[$(ts)] OK   pangu-api 用户级服务 active" >> "$LOG"
else
    echo "[$(ts)] ALERT 服务状态: $SVC" >> "$LOG"; ALERTS=$((ALERTS+1))
fi

if [ "$ALERTS" -gt 0 ]; then
    echo "[$(ts)] ALERT 巡检发现 $ALERTS 项异常，请人工检查！" >> "$LOG"
else
    echo "[$(ts)] 全部通过 (6/6)" >> "$LOG"
fi

# 日志滚动：保留最近 2000 行
tail -2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
