#!/usr/bin/env bash
# 盘古晚间自检套件（守护①）：健康快照 + 修复回归 + 备份验证
# 用法: 每日 cron 03:30 或手动运行; 输出写入 ~/backup/pangu/guard/ 并生成摘要
set -uo pipefail
OUT=~/backup/pangu/guard
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$OUT/guard_${STAMP}.log"
exec >"$LOG" 2>&1
MCP=http://127.0.0.1:19529/mcp
echo "=== $(date '+%F %T') 盘古晚间自检开始 ==="

# 1. 服务健康
if curl -fs http://127.0.0.1:19529/health >/dev/null 2>&1; then echo "HEALTH: ok"; else echo "HEALTH: FAIL"; fi

# 2. 修复回归：4 个 NameError 工具应返回正常 JSON（R1 守卫）
for t in pangu_cluster_by_tags pangu_cluster_by_time pangu_hierarchical_cluster pangu_dedup_results; do
  r=$(curl -s -X POST "$MCP" -H "Content-Type: application/json" \
      -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$t\",\"arguments\":{\"query\":\"guard\"}}}")
  if echo "$r" | grep -q '"error"'; then echo "REGRESSION: $t"; else echo "OK: $t"; fi
done

# 3. 记忆量 + 健康分
python3 - "$MCP" <<'PY'
import json, sys, urllib.request, re
mcp=sys.argv[1]
def call(name, args={}):
    b={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}}
    req=urllib.request.Request(mcp, data=json.dumps(b).encode(), headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))
try:
    st=call("pangu_stats")["result"]["content"][0]["text"]
    m=re.search(r'"total_memories"?\s*[: ]+(\d+)', st)
    print("MEMORIES:", m.group(1) if m else "?")
    h=call("pangu_health_check")["result"]["content"][0]["text"]
    s=re.search(r'overall_score"?\s*[: ]+([\d.]+)', h)
    print("HEALTH_SCORE:", s.group(1) if s else "?")
except Exception as e:
    print("STATS_FAIL:", e)
PY

# 4. 备份验证（最新一份存在且非空）
LATEST=$(ls -1t ~/backup/pangu/pangu_backup_*.tar.gz 2>/dev/null | head -1)
if [ -n "$LATEST" ] && [ -s "$LATEST" ]; then echo "BACKUP: ok $(basename "$LATEST")"; else echo "BACKUP: MISSING"; fi

echo "=== $(date '+%F %T') 自检完成 ==="
# 保留最近 30 份
ls -1t "$OUT"/guard_*.log 2>/dev/null | tail -n +31 | xargs -r rm -f
