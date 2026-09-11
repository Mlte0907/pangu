#!/usr/bin/env bash
# 安装 dsh-pangu 插件到指定的 DSH profile
# ==========================================
# 解决两个坑：
#   1. 插件的 node_modules 被 .gitignore 忽略，克隆后不存在；而
#      lib/typert.host.mjs 会被宿主 typert-loader 自动 import，
#      缺少 zod 会导致 DSH 启动失败（ERR_MODULE_NOT_FOUND: zod）。
#   2. 仅装依赖还不够，必须让插件进入 profile 的 dependencies 与
#      dsh.profile.bundles，宿主才会加载它。
#
# 用法：
#   scripts/install_dsh_plugin.sh                  # 默认装到 web profile
#   scripts/install_dsh_plugin.sh tui              # 指定 profile
#   DSH_DIR=/path/to/deepseek-harness scripts/install_dsh_plugin.sh
#
# 幂等：可重复执行。

set -euo pipefail

PROFILE="${1:-web}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$REPO_DIR/plugins/dsh-pangu"
DSH_DIR="${DSH_DIR:-}"

echo "==> dsh-pangu 插件安装"
echo "    仓库:   $REPO_DIR"
echo "    插件:   $PLUGIN_DIR"
echo "    profile: $PROFILE"

# ── 0. 前置检查 ──
if [ ! -f "$PLUGIN_DIR/package.json" ]; then
  echo "错误: 找不到插件包 $PLUGIN_DIR/package.json" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "错误: 未找到 pnpm，请先安装（npm i -g pnpm）" >&2
  exit 1
fi

# ── 1. 安装插件自身的运行时依赖 ──
echo "==> 1/2 安装插件运行时依赖（zod 等）"
if [ -d "$PLUGIN_DIR/node_modules/zod" ]; then
  echo "    已存在，跳过。"
else
  ( cd "$PLUGIN_DIR" && pnpm install --prod )
fi

# 验证关键依赖确实可解析
if ! ( cd "$PLUGIN_DIR" && node -e "require.resolve('zod')" 2>/dev/null ); then
  echo "错误: zod 仍无法从插件目录解析，DSH 启动会失败" >&2
  exit 1
fi
echo "    ✓ zod 可解析"

# 验证 typert 清单可加载（宿主启动时会自动 import 它）
if ! ( cd "$PLUGIN_DIR" && node --input-type=module \
        -e "import('./lib/typert.host.mjs').then(()=>process.exit(0)).catch(()=>process.exit(1))" \
        2>/dev/null ); then
  echo "错误: lib/typert.host.mjs 无法加载，DSH 启动会失败" >&2
  exit 1
fi
echo "    ✓ typert 清单可加载"

# ── 2. 安装到 DSH profile ──
echo "==> 2/2 安装到 DSH profile: $PROFILE"

# 定位 dsh CLI：优先 PATH，其次从源码目录启动
# 注意：以源码方式启动时必须先 cd 到 DSH 检出目录，
# 否则 `--import tsx/esm` 无法解析 tsx（它装在 DSH 的 node_modules 里）。
DSH_CWD=""
if command -v dsh >/dev/null 2>&1; then
  echo "    使用 PATH 中的 dsh"
  dsh plugin --profile "$PROFILE" add "$PLUGIN_DIR"
elif [ -n "$DSH_DIR" ] && [ -f "$DSH_DIR/apps/cli/src/bin.ts" ]; then
  DSH_CWD="$DSH_DIR"
elif [ -f "$HOME/deepseek-harness/apps/cli/src/bin.ts" ]; then
  DSH_CWD="$HOME/deepseek-harness"
else
  echo "错误: 找不到 dsh CLI。请把 dsh 加入 PATH，或设置 DSH_DIR 指向 deepseek-harness 检出的目录。" >&2
  exit 1
fi

if [ -n "$DSH_CWD" ]; then
  echo "    使用源码方式启动 dsh（$DSH_CWD）"
  ( cd "$DSH_CWD" && node --import tsx/esm apps/cli/src/bin.ts \
      plugin --profile "$PROFILE" add "$PLUGIN_DIR" )
fi

# ── 3. 验证结果 ──
PROFILE_JSON="$HOME/.dsh/profiles/$PROFILE/package.json"
if [ -f "$PROFILE_JSON" ]; then
  python3 - "$PROFILE_JSON" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
deps = p.get('dependencies', {})
bundles = p.get('dsh', {}).get('profile', {}).get('bundles', [])
ok_dep = 'dsh-pangu' in deps
ok_bundle = 'dsh-pangu' in bundles
print(f"    {'✓' if ok_dep else '✗'} dependencies 含 dsh-pangu")
print(f"    {'✓' if ok_bundle else '✗'} dsh.profile.bundles 含 dsh-pangu")
sys.exit(0 if (ok_dep and ok_bundle) else 1)
PY
else
  echo "    警告: 未找到 $PROFILE_JSON，跳过验证" >&2
fi

echo
echo "完成。注意：cordis.patch.yml 的 HMR 在 web 实例不生效，"
echo "请重启 DSH 后插件才会真正加载。"
