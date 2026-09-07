#!/usr/bin/env bash
# 每周用量/资费汇总报告（周日晚 21:30 运行）
set -uo pipefail
OUT=~/backup/pangu/guard
echo "=== $(date '+%F %T') 周用量汇总 ==="
echo "【OpenCode Go 订阅用量（最近日志）】"
LATEST=$(ls -1t "$OUT"/usage_*.log 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then grep -E "rolling|weekly|monthly|ALERT|盘古LLM" "$LATEST"; fi
echo
echo "【近7日用量趋势】"
for f in $(ls -1t "$OUT"/usage_*.log 2>/dev/null | head -7 | tac); do
  d=$(basename "$f" .log | sed 's/usage_//')
  m=$(grep -oE "monthly: [0-9]+%" "$f" | head -1)
  echo "  $d: ${m:-无数据}"
done
echo
echo "【盘古 LLM 通道复核】"
python3 -c "
import json
c=json.load(open('/home/xiaoxin/.pangu/config.json'))
print('  provider:', c.get('llm_provider'), '| model:', c.get('llm_model'), '| base:', c.get('llm_base_url'))
" 2>/dev/null
echo "=== $(date '+%F %T') 汇总完成 ==="
