#!/bin/bash
# 盘古记忆系统停止脚本
#
# 支持两种运行方式：
#   1. systemd 用户服务（pangu-api.service，推荐）
#   2. 手动前台/后台启动（通过 pangu.pid 记录）
# 路径自动解析，不依赖仓库所在位置。

set -uo pipefail

PANGU_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$PANGU_DIR/pangu.pid"

# ── 1. 优先处理 systemd 用户服务 ──
if command -v systemctl >/dev/null 2>&1 \
   && systemctl --user list-unit-files pangu-api.service >/dev/null 2>&1 \
   && systemctl --user is-active --quiet pangu-api.service 2>/dev/null; then
    echo "停止 systemd 用户服务 pangu-api..."
    systemctl --user stop pangu-api.service
    echo "盘古系统已停止"
    exit 0
fi

# ── 2. 回退到 pidfile 方式 ──
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
        echo "停止盘古系统 (PID: $PID)..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "盘古系统已停止"
    else
        echo "盘古系统未运行（清理陈旧 pid 文件）"
        rm -f "$PID_FILE"
    fi
else
    echo "盘古系统未运行"
fi
