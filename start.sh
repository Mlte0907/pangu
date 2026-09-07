#!/bin/bash
# 启动盘古 API 服务器

cd /home/xiaoxin/pangu
source .venv/bin/activate

export PANGU_HOST=127.0.0.1
export PANGU_PORT=19529

python -c "
import sys
sys.path.insert(0, '/home/xiaoxin/pangu')
import uvicorn
from pangu.api.server import create_app

app = create_app()
uvicorn.run(app, host='127.0.0.1', port=19529, log_level='info')
"
