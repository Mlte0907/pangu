#!/usr/bin/env bash
# 将盘古 API 切换到用户级 systemd 服务
#
# 两种情形：
#   A. 有 sudo：停用旧的系统级服务 + 开启 linger（重启后免登录自启）
#   B. 无 sudo（容器受限环境，如 no_new_privs）：跳过所有需要提权的步骤，
#      直接在当前用户会话中启用服务。服务可正常启停；仅"机器重启后自启"
#      需要 linger，当前登录会话内不受影响。
#
# 不依赖仓库所在路径，用户级服务单元由本脚本按实际路径生成。

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/pangu-api.service"
PORT="${PANGU_PORT:-19529}"
PYTHON="$REPO_DIR/.venv/bin/python"

echo "==> 盘古用户级服务安装"
echo "    仓库: $REPO_DIR"

# ── 0. 前置检查 ──
if [ ! -x "$PYTHON" ]; then
  echo "错误: 未找到虚拟环境 $PYTHON" >&2
  echo "      请先创建并安装依赖：" >&2
  echo "        uv venv --python 3.12 .venv" >&2
  echo "        uv pip install --python .venv/bin/python -r requirements.txt" >&2
  exit 1
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "错误: 当前环境没有可用的 systemd 用户实例（DBUS 未就绪）。" >&2
  echo "      可改用前台方式运行：$REPO_DIR/start.sh" >&2
  exit 1
fi

# ── 1. 生成服务单元 ──
echo "==> 1/4 写入服务单元"
mkdir -p "$UNIT_DIR" "$REPO_DIR/.deploy-logs"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Pangu Memory System API (盘古记忆系统)
Documentation=https://github.com/Mlte0907/pangu
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PANGU_HOST=127.0.0.1
Environment=PANGU_PORT=$PORT
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON -c "import sys; sys.path.insert(0, '$REPO_DIR'); import uvicorn; from pangu.api.server import create_app; uvicorn.run(create_app(), host='127.0.0.1', port=$PORT, log_level='info')"
Restart=on-failure
RestartSec=5
StandardOutput=append:$REPO_DIR/.deploy-logs/pangu-api.log
StandardError=append:$REPO_DIR/.deploy-logs/pangu-api.log

[Install]
WantedBy=default.target
EOF
echo "    ✓ $UNIT_FILE"

# ── 2. 处理旧的系统级服务（仅在有 sudo 时） ──
echo "==> 2/4 检查系统级服务"
HAVE_SUDO=0
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  HAVE_SUDO=1
  if systemctl list-unit-files pangu-api.service >/dev/null 2>&1; then
    echo "    停用系统级 pangu-api.service"
    sudo systemctl disable --now pangu-api.service || true
  else
    echo "    无系统级服务，跳过"
  fi
else
  echo "    ⚠ 无免密 sudo（受限环境），跳过系统级操作"
fi

# ── 3. 启用并启动用户级服务 ──
echo "==> 3/4 启用用户级服务"
systemctl --user daemon-reload
systemctl --user enable --now pangu-api.service
sleep 3

# ── 4. linger（重启自启，需要 sudo） ──
echo "==> 4/4 配置重启自启"
if [ "$HAVE_SUDO" = "1" ]; then
  if loginctl enable-linger "$USER" 2>/dev/null; then
    echo "    ✓ 已开启 linger，重启后免登录自启"
  else
    echo "    ⚠ linger 开启失败，服务仅在登录会话中运行"
  fi
else
  echo "    ⚠ 无 sudo，未开启 linger。服务在当前登录会话中正常运行，"
  echo "      但机器重启后需重新登录（或手动 systemctl --user start）才会自启。"
fi

# ── 5. 验证 ──
echo
echo "==> 验证"
systemctl --user is-active pangu-api.service
if ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo "端口 $PORT: 监听中"
else
  echo "端口未监听!" >&2
  exit 1
fi
if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null; then
  echo "health: OK"
else
  echo "health 检查失败" >&2
  exit 1
fi
echo
echo "切换完成：监听 127.0.0.1:$PORT"
echo "日志：$REPO_DIR/.deploy-logs/pangu-api.log"
