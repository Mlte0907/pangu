#!/bin/bash
# 盘古记忆系统停止脚本

PANGU_DIR="/home/xiaoxin/pangu"
PID_FILE="$PANGU_DIR/pangu.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "停止盘古系统 (PID: $PID)..."
        kill "$PID"
        rm "$PID_FILE"
        echo "盘古系统已停止"
    else
        echo "盘古系统未运行"
        rm "$PID_FILE"
    fi
else
    echo "盘古系统未运行"
fi
