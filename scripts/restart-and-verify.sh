#!/usr/bin/env bash
# 盘古服务重启 + 健康探活
# 用于每次代码提交后的收尾，非零退出表示失败
set -euo pipefail

SERVICE="pangu-api"
HEALTH_URL="http://127.0.0.1:19529/health"

echo "==> 重启 $SERVICE"
systemctl --user restart "$SERVICE"

# 等待启动（最多 30 秒）
for i in $(seq 1 30); do
    sleep 1
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        echo "==> health ok (${i}s)"
        exit 0
    fi
done

echo "==> health 探活失败（30s 超时）" >&2
exit 1
