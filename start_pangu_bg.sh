#!/bin/bash
# 盘古记忆系统后台启动脚本

set -e

PANGU_DIR="/home/xiaoxin/pangu"
VENV_DIR="$PANGU_DIR/.venv"
LOG_DIR="$PANGU_DIR/logs"
PID_FILE="$PANGU_DIR/pangu.pid"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "盘古系统已在运行 (PID: $PID)"
        exit 0
    fi
fi

# 检查虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    cd "$PANGU_DIR"
    python3 -m venv .venv
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 安装依赖
echo "检查依赖..."
pip install -q -r requirements.txt 2>/dev/null || true

# 启动盘古服务（后台）
echo "启动盘古记忆系统..."
cd "$PANGU_DIR"
nohup python -m pangu.cli mcp > "$LOG_DIR/pangu.log" 2>&1 &
echo $! > "$PID_FILE"

echo "盘古系统已启动 (PID: $(cat $PID_FILE))"
echo "日志文件: $LOG_DIR/pangu.log"
