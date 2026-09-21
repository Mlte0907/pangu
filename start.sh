#!/bin/bash
# 盘古记忆系统启动脚本（前台运行，排障用）
#
# 生产环境建议用 systemd 用户服务托管（崩溃自动重启 + 开机自启）：
#   systemctl --user start pangu-api
# 本脚本用于前台手动启动 / 排障。
#
# 路径自动解析，不依赖仓库所在位置；端口可用 PANGU_PORT 环境变量覆盖。

set -euo pipefail

# 仓库根目录 = 本脚本所在目录
PANGU_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PANGU_DIR"

# ── 加载安装时生成的凭据与数据目录（与 systemd 的 EnvironmentFile 对齐）──
# install.sh 会把 REST 主密钥（PANGU_API_KEY）以及自定义数据目录时的
# PANGU_BASE_DIR 写进 $PANGU_HOME/pangu.env。systemd 单元用 EnvironmentFile 读它，
# 而本脚本此前不读 —— 于是「手动启动」出来的实例没有 PANGU_API_KEY：
# 鉴权中间件因 jwt_secret 仍然开着，填写卡上刚打印出来的凭据会被服务端拒绝
# （401 无效的 API Key）。2026-09-21 修。
PANGU_HOME="${PANGU_HOME:-$HOME/.pangu}"
if [ -f "$PANGU_HOME/pangu.env" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$PANGU_HOME/pangu.env"
    set +a
fi

# 激活虚拟环境（若存在）
if [ -f "$PANGU_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PANGU_DIR/.venv/bin/activate"
else
    echo "警告: 未找到 $PANGU_DIR/.venv，将回退到 PATH 中的 python" >&2
fi

# 监听地址与端口（可用环境变量覆盖）
export PANGU_HOST="${PANGU_HOST:-127.0.0.1}"
export PANGU_PORT="${PANGU_PORT:-19529}"

PYTHON="$PANGU_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"

exec "$PYTHON" -c "
import sys
sys.path.insert(0, '${PANGU_DIR}')
import uvicorn
from pangu.api.server import create_app

app = create_app()
uvicorn.run(app, host='${PANGU_HOST}', port=int('${PANGU_PORT}'), log_level='info')
"
