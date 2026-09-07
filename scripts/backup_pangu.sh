#!/usr/bin/env bash
# 盘古记忆系统每日备份
# 备份 ~/.pangu 全目录到 ~/backup/pangu/，滚动保留最近 14 份，并导出近 24h 服务日志
set -euo pipefail

SRC="$HOME/.pangu"
DEST="$HOME/backup/pangu"
KEEP=14

mkdir -p "$DEST"

STAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE="$DEST/pangu_backup_${STAMP}.tar.gz"

if tar -czf "$ARCHIVE" -C "$HOME" .pangu 2>/dev/null; then
    echo "[$(date '+%F %T')] backup ok: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
else
    echo "[$(date '+%F %T')] backup FAILED" >&2
    rm -f "$ARCHIVE"
    exit 1
fi

# 滚动清理：只保留最近 KEEP 份
ls -1t "$DEST"/pangu_backup_*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

# 导出近 24h 的服务日志（journal 可能未持久化，落到文件保底）
journalctl -u pangu-api.service --since "24 hours ago" --no-pager \
    > "$DEST/pangu-api-journal_${STAMP}.log" 2>/dev/null || true
ls -1t "$DEST"/pangu-api-journal_*.log 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "[$(date '+%F %T')] rotation done (keep=$KEEP)"
