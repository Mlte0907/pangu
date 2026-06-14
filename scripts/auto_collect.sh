#!/bin/bash
# 盘古自动采集脚本 — 采集 + 嵌入

set -e

PANGU_DIR="/home/xiaoxin/pangu"
VENV_DIR="$PANGU_DIR/.venv"
LOG_FILE="/tmp/pangu_auto_collect.log"

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

cd "$PANGU_DIR"

# 1. 快速采集新记忆
timeout 60 python scripts/fast_collect.py >> "$LOG_FILE" 2>&1

# 2. 为所有未嵌入的记忆生成向量
timeout 120 python scripts/embed_all.py >> "$LOG_FILE" 2>&1

echo "[$(date)] 采集+嵌入完成" >> "$LOG_FILE"
