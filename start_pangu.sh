#!/bin/bash
# 盘古记忆系统启动脚本

set -e

PANGU_DIR="/home/xiaoxin/pangu"
VENV_DIR="$PANGU_DIR/.venv"

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

# 启动盘古服务
echo "启动盘古记忆系统..."
cd "$PANGU_DIR"
python -m pangu.cli mcp
