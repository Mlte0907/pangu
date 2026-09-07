#!/usr/bin/env bash
# 一键将盘古 API 从系统级服务切换到用户级加固服务
# 需要输入一次 sudo 密码（停用旧的系统级服务 + 开启 linger 免登录自启）
set -euo pipefail

echo "==> 1/4 停用旧的系统级服务 (需要 sudo)"
sudo systemctl disable --now pangu-api.service
sleep 2

echo "==> 2/4 启动用户级加固服务"
systemctl --user daemon-reload
systemctl --user enable --now pangu-api.service
sleep 3

echo "==> 3/4 开启 linger（重启后免登录自启，需要 sudo）"
sudo loginctl enable-linger xiaoxin

echo "==> 4/4 验证"
systemctl --user is-active pangu-api.service
ss -tlnp | grep 19529 || { echo "端口未监听!"; exit 1; }
curl -sf http://127.0.0.1:19529/health > /dev/null && echo "health: OK"
echo "切换完成：监听 127.0.0.1:19529，MemoryMax=300M"
