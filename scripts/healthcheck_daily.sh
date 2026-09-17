#!/usr/bin/env bash
# 盘古每日健康巡检（无 root 的轻量监控方案，替代 Prometheus 部署）
# 检查：服务存活 / 认证有效性 / 数据完整性 / 备份时效 / 磁盘空间 / 服务状态
# 由 systemd user timer 每日 08:00 执行（systemd/pangu-healthcheck.{service,timer}），
# 异常输出 ALERT 标记便于 grep。
set -uo pipefail

# 日志目录曾经不存在导致整个脚本 3 处重定向失败、单元长期 failed；
# 自己建目录，避免依赖外部先创建。
LOG="${PANGU_HEALTHCHECK_LOG:-/home/xiaoxin/backup/pangu/healthcheck.log}"
mkdir -p "$(dirname "$LOG")" || { echo "无法创建日志目录: $(dirname "$LOG")" >&2; exit 1; }

# 凭据：优先新钥匙体系（~/.pangu/.mcp_key，0600），回落旧 config.json 的 api_key
API_KEY=$(cat "$HOME/.pangu/.mcp_key" 2>/dev/null | tr -d '\n')
if [ -z "$API_KEY" ]; then
    API_KEY=$(python3 -c "import json; print(json.load(open('$HOME/.pangu/config.json')).get('api_key',''))" 2>/dev/null)
fi

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

# 2. 认证冒烟：无 key 必须 401；带 key 必须 200
NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:19529/api/v2/memories 2>/dev/null)
if [ -n "$API_KEY" ]; then
    WITHAUTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "X-API-Key: $API_KEY" http://127.0.0.1:19529/api/v2/memories 2>/dev/null)
else
    WITHAUTH="(无可用钥匙)"
fi
if [ "$NOAUTH" = "401" ] && [ "$WITHAUTH" = "200" ]; then
    echo "[$(ts)] OK   认证边界正常 (无key=$NOAUTH 带key=$WITHAUTH)" >> "$LOG"
elif [ "$NOAUTH" = "200" ]; then
    # REST 面未接入钥匙体系（auth_enabled 只在旧 config.api_key/jwt_secret 非空时打开，
    # 且 /api/v2/memories 在豁免前缀里）。记 ALERT 而不是 OK，避免把洞当正常。
    echo "[$(ts)] ALERT REST 未鉴权: /api/v2/memories 无凭据返回 $NOAUTH（带key=$WITHAUTH）" >> "$LOG"
    ALERTS=$((ALERTS+1))
else
    echo "[$(ts)] ALERT 认证异常! 无key=$NOAUTH 带key=$WITHAUTH (期望 401/200)" >> "$LOG"
    ALERTS=$((ALERTS+1))
fi

# 3. 记忆数据 JSON 完整性（曾发生并发写入损坏，静默带病运行半月）
for f in "$HOME/.pangu/palace/drawers.json" "$HOME/.pangu/pangu.db/v2_memories/drawers.json"; do
    if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
        echo "[$(ts)] OK   JSON 完整: $f" >> "$LOG"
    else
        echo "[$(ts)] ALERT JSON 损坏: $f" >> "$LOG"; ALERTS=$((ALERTS+1))
    fi
done

# 4. 备份时效（>25 小时视为过期）。
#    两条来源取最新：① 全量归档 ~/backup/pangu/pangu_backup_*.tar.gz（scripts/backup_pangu.sh，
#    由 systemd/pangu-backup.timer 每日执行）；② ~/.pangu/backups 里的数据快照
#    （drawers-*/*-drawers-* 等，维护/清理动作产生）。
LATEST=""
for cand in "$HOME/backup/pangu/pangu_backup_"*.tar.gz; do
    [ -e "$cand" ] || continue
    if [ -z "$LATEST" ] || [ "$cand" -nt "$LATEST" ]; then LATEST="$cand"; fi
done
for cand in "$HOME/.pangu/backups/"*drawers*.json; do
    [ -e "$cand" ] || continue
    if [ -z "$LATEST" ] || [ "$cand" -nt "$LATEST" ]; then LATEST="$cand"; fi
done
if [ -n "$LATEST" ]; then
    AGE_H=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
    if [ "$AGE_H" -le 25 ]; then
        echo "[$(ts)] OK   备份新鲜: ${LATEST##*/} (${AGE_H}h 前)" >> "$LOG"
    else
        echo "[$(ts)] ALERT 备份过期: 最近一份 ${LATEST##*/} 已 ${AGE_H} 小时" >> "$LOG"; ALERTS=$((ALERTS+1))
    fi
else
    echo "[$(ts)] ALERT 无任何备份文件（既无 ~/backup/pangu/*.tar.gz，也无 ~/.pangu/backups 快照）!" >> "$LOG"
    ALERTS=$((ALERTS+1))
fi

# 5. 磁盘空间（>85% 报警）
DISK_PCT=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "${DISK_PCT:-100}" -le 85 ]; then
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
