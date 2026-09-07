#!/bin/bash
# 盘古生命周期维护脚本 — 轻量版
# 仅执行巩固 + 索引重建

set -e

PANGU_DIR="/home/xiaoxin/pangu"
VENV_DIR="$PANGU_DIR/.venv"
LOG_FILE="/tmp/pangu_lifecycle.log"
LOCK_FILE="/tmp/pangu_lifecycle.lock"

# 防止并发执行
if [ -f "$LOCK_FILE" ]; then
    pid=$(cat "$LOCK_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "[$(date)] Another lifecycle running (pid=$pid), skipping" >> "$LOG_FILE"
        exit 0
    fi
fi
echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 运行生命周期
cd "$PANGU_DIR"
timeout 60 python3 -c "
import sys, os
sys.path.insert(0, '$PANGU_DIR')
os.environ['PANGU_EMBED_API_URL'] = ''

from pangu.memory.lifecycle import LifecycleManager
manager = LifecycleManager()
results = manager.on_session_end()

if results:
    print(f'[{__import__(\"datetime\").datetime.now().isoformat()}] Tasks:')
    for task, result in results.items():
        print(f'  {task}: {result.get(\"status\", result)}')
else:
    print(f'[{__import__(\"datetime\").datetime.now().isoformat()}] No tasks needed')
" >> "$LOG_FILE" 2>&1

echo "[$(date)] Lifecycle done" >> "$LOG_FILE"
