#!/usr/bin/env bash
# OpenCode Go 用量 + 盘古 LLM 调用监测（每日）
# 抓取: OpenCode Go 订阅用量(rolling/weekly/monthly) + 盘古激活状态 + LLM 工具证据
set -uo pipefail
OUT=~/backup/pangu/guard
STAMP=$(date +%Y%m%d)
LOG="$OUT/usage_${STAMP}.log"
MCP=http://127.0.0.1:19529/mcp
KEY=$(python3 -c "import yaml; print(yaml.safe_load(open('/home/xiaoxin/.dsh/.credentials.yaml'))['refs']['OPENCODE_GO_API_KEY'])" 2>/dev/null)
{
echo "=== $(date '+%F %T') 用量监测 ==="
# 1. OpenCode Go 订阅用量
if [ -n "$KEY" ]; then
  U=$(curl -s -m 15 "https://opencode.ai/zen/go/v1/usage" -H "Authorization: Bearer $KEY" 2>/dev/null)
  echo "$U" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)['usage']
    for k in ('rolling','weekly','monthly'):
        v=d.get(k,{})
        print(f'  {k}: {v.get(\"percent\",\"?\")}% status={v.get(\"status\",\"?\")} 重置={v.get(\"resetsAt\",\"?\")}')
    # 预警: 任一度量超80%
    alert=[k for k in d if d[k].get('percent',0)>=80]
    print('  ALERT:' + (' '.join(alert) if alert else 'none'))
except Exception as e:
    print('  usage 解析失败:', e)
"
else echo "  WARN: OPENCODE_GO_API_KEY 无法读取"; fi
# 2. 盘古 LLM 配置复核（确认仍是 OpenCode Go 通道）
python3 -c "
import json
c=json.load(open('/home/xiaoxin/.pangu/config.json'))
print(f'  盘古LLM: {c.get(\"llm_provider\")}/{c.get(\"llm_model\")}/{c.get(\"llm_base_url\")}')
"
# 3. 盘古健康（资费数据的前提是服务在）
curl -s http://127.0.0.1:19529/health >/dev/null 2>&1 && echo "  pangu-api: ok" || echo "  pangu-api: DOWN"
echo "=== $(date '+%F %T') 监测完成 ==="
} >> "$LOG" 2>&1
# 保留 60 天
ls -1t "$OUT"/usage_*.log 2>/dev/null | tail -n +61 | xargs -r rm -f
