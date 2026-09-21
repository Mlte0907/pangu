#!/usr/bin/env bash
# 盘古记忆系统 — 一键安装脚本
# ============================================================
# 解决当前安装流程的三个痛点（实测依据见 docs/OPTIMIZATION.md）：
#
#   1. README 宣称依赖装完"约 20 秒"，实际冷缓存需 8 分 10 秒（56 包 /
#      223 MB），用户容易以为卡死而中断，导致"缓存涨了但包没装上"。
#      → 本脚本分阶段显示进度与耗时预期。
#
#   2. ONNX 模型（23 MB）在首次启动时才下载，失败会**静默降级到 hash
#      向量**——服务照常启动、检索照常返回，但结果完全没有语义。
#      → 本脚本在安装阶段预下载并**明确报错**，绝不静默继续。
#
#   3. 端口 19529（MCP/REST，DSH 插件需要）与 8866（Web 界面）是两个不同
#      的服务。此前 19529 没有 CLI 入口，用户无从得知怎么起它。
#      → 本脚本安装 systemd 用户服务托管 19529，并在结尾说明区别。
#        （v0.1.3 起 also 支持 `pangu serve --api` 手动起 19529。）
#
# 用法：
#   ./install.sh                    # 默认：装依赖 + 预下载模型 + systemd 服务
#   ./install.sh --no-service       # 不装 systemd 服务（仅装到目录）
#   ./install.sh --dsh-plugin       # 额外安装 DSH 插件（从独立仓库拉取，可选）
#   ./install.sh --port 19529       # 指定端口
#   ./install.sh --host 0.0.0.0     # 手动指定监听地址（一般不用给：见下）
#   ./install.sh --host 127.0.0.1   #（仅本机）
#
# 监听地址默认**自动判定**，小白不用选：
#   · 本机自用（有图形会话、非 SSH 安装）→ 只监听 127.0.0.1，最安全、端口不外露
#   · 服务器/局域网主机（SSH 安装 / 云主机 metadata / 无图形会话）
#     → 监听 0.0.0.0，卡片自动给出公网 IP（探测不到则给网卡 IP）
#   · 想覆盖判定就用 --host：0.0.0.0 对所有网卡 / 127.0.0.1 仅本机
#   公网暴露务必配 nginx+TLS，并在云安全组限制来源 IP。
#   ./install.sh --model-only       # 仅预下载模型（已装好依赖时用）
#   ./install.sh --offline-model /path/to/model_quantized.onnx,/path/to/tokenizer.json
#                                   # 从本地文件装模型（内网/弱网）
#   ./install.sh --server           # 仅启动 API 服务（不安装，需先装好）
#   ./install.sh --uninstall        # 卸载 systemd 服务（保留数据目录）
#   ./install.sh --uninstall --remove-data
#                                   # 卸载并清空数据目录（**不可逆**：凭据会重新生成）
#                                   #   想从零重装：再加一句 rm -rf ~/pangu 删掉代码
#
#   PANGU_NO_UV=1 ./install.sh      # 不自动安装 uv（改用 pip3，慢很多）
#                                     默认会在缺少 uv 时自动装一个到 ~/.local/bin
#                                     （不改你的 shell 配置）；装依赖因此从 8-15 分钟
#                                     降到约 20 秒。
#
# 幂等：可重复执行，已完成的步骤会跳过。

set -euo pipefail

# ── 自举：curl|bash 时本文件不在仓库里，先取得仓库再执行自己 ──
#
# ⚠ 必须写成 `${BASH_SOURCE[0]:-}`：`curl … | bash` 时脚本来自 stdin，
#    BASH_SOURCE[0] **未设置**，而上面开了 `set -u` —— 裸引用会立刻以
#    "unbound variable" 退出（curl 随之报 (23) 写管道失败），表现为
#    "一条命令安装完全没反应、没有任何输出"。2026-09-22 云端实测踩到。
SELF="${BASH_SOURCE[0]:-}"
SELF_DIR=""
if [ -n "$SELF" ]; then
  SELF_DIR="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd || true)"
fi

# 取代码：首选 git（增量、可 pull），失败或没有 git 时回退 GitHub tarball。
#
# 为什么必须回退：`git clone https://github.com/...` 走的是 **github.com:443**，
# 国内网络下经常被阻断/超时（本机实测：连不通，133 秒后才报错），
# 而 **codeload.github.com** 同一网络下通常可达（实测 200）。
# 只判断"有没有 git"是不够的 —— 有 git 但拉不动，一样装不上。
_fetch_tarball() {
  local dest="$1"
  echo "    改用 tarball 下载（带进度条，约 5-10 MB）…"
  mkdir -p "$dest"
  local tmp
  tmp="$(mktemp -t pangu-XXXXXX.tgz)"
  curl -fL --progress-bar --max-time 600 -o "$tmp" \
    https://codeload.github.com/Mlte0907/pangu/tar.gz/refs/heads/master \
    || { echo "错误: 下载失败（codeload.github.com 也不通？）" >&2; rm -f "$tmp"; return 1; }
  tar -xzf "$tmp" -C "$dest" --strip-components=1 \
    || { echo "错误: 解压失败（$tmp）" >&2; rm -f "$tmp"; return 1; }
  rm -f "$tmp"
  return 0
}

if [ -z "$SELF_DIR" ] || [ ! -f "$SELF_DIR/pangu/api/server.py" ]; then
  INSTALL_ROOT="${PANGU_INSTALL_DIR:-$HOME/pangu}"
  echo "==> 取得盘古代码到 $INSTALL_ROOT"

  if [ -d "$INSTALL_ROOT/.git" ] && command -v git >/dev/null 2>&1; then
    echo "    已有仓库，拉取最新版本…"
    git -C "$INSTALL_ROOT" pull --ff-only 2>/dev/null || echo "    拉取失败，用现有代码继续"
  elif command -v git >/dev/null 2>&1; then
    echo "    克隆中（git --depth 1）…"
    # 90 秒上限：github.com:443 被阻断时会**长时间无响应**（本机实测挂 133 秒），
    # 干等比失败更糟 —— 超时即回退 tarball。能正常克隆的机器远快于此。
    if command -v timeout >/dev/null 2>&1; then
      GIT_OK=$(timeout 90 git clone --depth 1 https://github.com/Mlte0907/pangu "$INSTALL_ROOT" 2>/dev/null && echo 1 || echo 0)
    else
      GIT_OK=$(git clone --depth 1 https://github.com/Mlte0907/pangu "$INSTALL_ROOT" 2>/dev/null && echo 1 || echo 0)
    fi
    if [ "$GIT_OK" != "1" ]; then
      echo "    git 克隆失败/超时（github.com:443 不通或被限速）—— 回退 tarball…"
      rm -rf "$INSTALL_ROOT"
      _fetch_tarball "$INSTALL_ROOT" || exit 1
    fi
  else
    echo "    未检测到 git —— 走 tarball 下载"
    _fetch_tarball "$INSTALL_ROOT" || exit 1
  fi

  [ -f "$INSTALL_ROOT/install.sh" ] || { echo "错误: 取得代码失败（$INSTALL_ROOT/install.sh 不存在）" >&2; exit 1; }
  echo "    ✓ 代码就绪"
  exec bash "$INSTALL_ROOT/install.sh" "$@"
fi

# ── 配置 ──
REPO_DIR="$SELF_DIR"
VENV_DIR="$REPO_DIR/.venv"
PANGU_HOME="${PANGU_HOME:-$HOME/.pangu}"
PORT="19529"
# 空 = **自动判定**（见下面的「自动判定」段）。只有用户显式 --host 才固定。
HOST=""
INSTALL_SERVICE=1
INSTALL_DSH_PLUGIN=0
MODEL_ONLY=0
REMOVE_DATA=0
OFFLINE_MODEL=""
SERVICE_NAME="pangu-api"
DO_UNINSTALL=0
SERVER_ONLY=0

# ── 输出helpers ──
c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
c_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
step()    { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()      { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn()    { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()     { printf '\n\033[31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

# ── 长耗时步骤的"心跳" ──
# 为什么需要：装依赖（pip 可能 8-15 分钟）与下模型期间屏幕长时间不动，
# 用户无法判断"在跑还是卡死了"（2026-09-22 用户反馈）。
# 这里每 10 秒打一行已用时间，至少证明进程还活着。
#
# 实现要点：后台子进程 + 标记文件控制启停（而不是把命令塞进 subshell 里跑）——
# 后者会打乱退出码与 `set -e` 语义，而这两步必须能可靠判断成败。
HEARTBEAT_FLAG=""
HEARTBEAT_PID=""
_hb_t0=0
heartbeat_start() {
  local desc="${1:-处理中}"
  _hb_t0=$(date +%s)
  HEARTBEAT_FLAG="${TMPDIR:-/tmp}/.pangu-hb.$$"
  : > "$HEARTBEAT_FLAG"
  (
    while [ -f "$HEARTBEAT_FLAG" ]; do
      sleep 10
      [ -f "$HEARTBEAT_FLAG" ] || break
      printf '    … %s 仍在进行（已用 %ss）\n' "$desc" "$(( $(date +%s) - _hb_t0 ))"
    done
  ) &
  HEARTBEAT_PID=$!
}
heartbeat_stop() {
  [ -n "$HEARTBEAT_FLAG" ] && rm -f "$HEARTBEAT_FLAG"
  if [ -n "$HEARTBEAT_PID" ]; then
    kill "$HEARTBEAT_PID" 2>/dev/null || true
    wait "$HEARTBEAT_PID" 2>/dev/null || true
  fi
  HEARTBEAT_FLAG=""
  HEARTBEAT_PID=""
}
# 异常退出（die / set -e 中断）也要把心跳收掉，否则后台子进程会一直打表
trap 'heartbeat_stop' EXIT

# ── 参数解析 ──
while [ $# -gt 0 ]; do
  case "$1" in
    --port)         PORT="${2:?--port 需要参数}"; shift 2 ;;
    --host)         HOST="${2:?--host 需要参数}"; shift 2 ;;
    --no-service)   INSTALL_SERVICE=0; shift ;;
    --dsh-plugin)   INSTALL_DSH_PLUGIN=1; shift ;;
    --model-only)   MODEL_ONLY=1; shift ;;
    --offline-model) OFFLINE_MODEL="${2:?--offline-model 需要参数}"; shift 2 ;;
    --uninstall)    DO_UNINSTALL=1; shift ;;
    --remove-data)  REMOVE_DATA=1; shift ;;
    --server)       SERVER_ONLY=1; INSTALL_SERVICE=0; shift ;;
    -h|--help)
      # 打印文件头部注释块（从第 2 行到第一处非注释行前）
      awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"
      exit 0 ;;
    *) die "未知参数: $1（用 --help 查看用法）" ;;
  esac
done

# ════════════════════════════════════════════════════════════
# 自动判定：这台机器是「本机自用」还是「给别的机器用」
# ════════════════════════════════════════════════════════════
#
# 为什么不问用户：回环 / 网卡 / 公网这套概念，小白既不懂也不该被迫选
# （2026-09-22 用户反馈：部署到云端后拿到 http://127.0.0.1:19529，而插件在
#  另一台机器上根本连不通 —— 脚本只丢一个地址却不说前提，用户无从下手；
#  反过来"给两个方案让用户选"同样是把问题推回给不懂的人）。
#
# 判定为「服务器角色」（插件很可能在别的机器上），命中任一即是：
#   ① 通过 SSH 装，且连进来的不是本机回环（排除 ssh localhost）
#   ② 云厂商 metadata 可达（169.254.169.254）—— 用网页控制台装的云主机正是这种
#   ③ 没有图形会话（台式机/笔记本有；服务器通常没有）
# 三条都不命中 ⇒ 单机自用 ⇒ 只监听回环（端口不外露，最安全）。
#
# 想覆盖判定：--host 0.0.0.0（强制对所有网卡）/ --host 127.0.0.1（强制仅本机）。
has_graphical_session() {
  [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && return 0
  # 有没有**真实**的图形会话 —— 用 loginctl 的 Type 判定。
  # 注意：不能用 `systemctl is-active graphical.target` —— 无头机器只要默认
  # target 是 graphical 它就报 active，实测本机（无 X 进程）正是如此，会把
  # 无头服务器误判成桌面（2026-09-22 测试台抓到）。
  if command -v loginctl >/dev/null 2>&1; then
    for _s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do
      case "$(loginctl show-session "$_s" -p Type --value 2>/dev/null)" in
        x11|wayland) return 0 ;;
      esac
    done
  fi
  pgrep -x Xorg >/dev/null 2>&1 && return 0
  pgrep -x Xwayland >/dev/null 2>&1 && return 0
  return 1
}

HOST_AUTO=0
SSH_REMOTE=0
ROLE_REASON="由 --host 指定"
if [ "$DO_UNINSTALL" = 1 ]; then
  # 卸载不需要监听地址，也不值得为判定花掉一次 1 秒的网络探测
  HOST="127.0.0.1"
elif [ -z "$HOST" ]; then
  HOST_AUTO=1
  ROLE="local"; ROLE_REASON="未检测到远程使用迹象（像是本机自用）"
  if [ -n "${SSH_CONNECTION:-}" ]; then
    SSH_CIP=$(echo "$SSH_CONNECTION" | awk '{print $1}')
    SSH_SIP=$(echo "$SSH_CONNECTION" | awk '{print $3}')
    if [ "$SSH_CIP" != "127.0.0.1" ] || [ "$SSH_SIP" != "127.0.0.1" ]; then
      SSH_REMOTE=1
      ROLE="server"; ROLE_REASON="通过 SSH 从 $SSH_CIP 登录安装（插件在别的机器上）"
    fi
  fi
  if [ "$ROLE" = "local" ] && command -v curl >/dev/null 2>&1; then
    META_CODE=$(curl -s -o /dev/null -m 1 -w '%{http_code}' \
      http://169.254.169.254/latest/meta-data/ 2>/dev/null || true)
    case "$META_CODE" in
      2*|3*|401|403) ROLE="server"; ROLE_REASON="检测到云主机 metadata（本机是云服务器）" ;;
    esac
  fi
  if [ "$ROLE" = "local" ] && ! has_graphical_session; then
    ROLE="server"; ROLE_REASON="没有图形会话（无头服务器）"
  fi
  if [ "$ROLE" = "server" ]; then HOST="0.0.0.0"; else HOST="127.0.0.1"; fi
  ROLE_REASON="$ROLE_REASON → 监听 $HOST"
fi

PANGU_DIR="$REPO_DIR"
cd "$PANGU_DIR"

# ════════════════════════════════════════════════════════════
# P1-1: 卸载模式
# ════════════════════════════════════════════════════════════
if [ "$REMOVE_DATA" = 1 ] && [ "$DO_UNINSTALL" != 1 ]; then
  # 否则会静默什么都不做，用户以为数据删了（实际没删）
  die "--remove-data 需要与 --uninstall 一起用，例如：./install.sh --uninstall --remove-data"
fi

if [ "$DO_UNINSTALL" = 1 ]; then
  printf '\033[1;31m盘古卸载\033[0m\n'

  # 停止并禁用服务
  if systemctl --user is-active "$SERVICE_NAME" >/dev/null 2>&1; then
    step "停止服务"
    systemctl --user stop "$SERVICE_NAME"
    systemctl --user disable "$SERVICE_NAME"
    ok "服务已停止并禁用"
  fi

  # 删除 unit 文件
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_FILE="$UNIT_DIR/$SERVICE_NAME.service"
  if [ -f "$UNIT_FILE" ]; then
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload 2>/dev/null || true
    ok "systemd unit 已删除"
  fi

  # 删除数据目录
  if [ "${REMOVE_DATA:-0}" = 1 ]; then
    step "删除数据目录 $PANGU_HOME"
    # 防呆：这是**不可逆**操作，绝不允许因为变量写错而清掉无关目录。
    # ① 拒绝明显的危险路径；② 要求目录里确实有盘古的特征文件。
    case "$PANGU_HOME" in
      ""|"/"|"$HOME"|"$HOME/"|"/root"|"/home"|"/usr"|"/etc")
        die "拒绝删除「$PANGU_HOME」：路径看起来不对（别指向家目录或系统目录）" ;;
    esac
    if [ -f "$PANGU_HOME/.api_key" ] || [ -f "$PANGU_HOME/config.json" ] || [ -f "$PANGU_HOME/.admin_secret" ]; then
      rm -rf "$PANGU_HOME"
      ok "数据目录已删除（凭据 / 配置 / 记忆数据一并清除，重装会生成新凭据）"
    elif [ -d "$PANGU_HOME" ]; then
      die "拒绝删除「$PANGU_HOME」：里面没有盘古数据特征文件（.api_key/config.json）"
    else
      ok "数据目录本就不存在（$PANGU_HOME）"
    fi
  elif [ -d "$PANGU_HOME" ]; then
    warn "数据目录 $PANGU_HOME 保留（重装会复用其中的凭据；要清空加 --remove-data）"
  fi

  ok "卸载完成"
  exit 0
fi

# ════════════════════════════════════════════════════════════
# P1-1: --server 模式（仅启动服务，不安装）
# ════════════════════════════════════════════════════════════
if [ "$SERVER_ONLY" = 1 ]; then
  printf '\033[1m盘古 — 启动 API 服务\033[0m\n'
  VPY="$VENV_DIR/bin/python"
  if [ ! -f "$VPY" ]; then
    die "虚拟环境不存在: $VENV_DIR（先运行 ./install.sh）"
  fi
  step "启动 pangu-api (端口 $HOST:$PORT)"
  exec "$VPY" -c "import sys; sys.path.insert(0, '$PANGU_DIR'); import uvicorn; from pangu.api.server import create_app; uvicorn.run(create_app(), host='$HOST', port=$PORT, log_level='info')"
fi

printf '\033[1m盘古记忆系统 — 安装\033[0m\n'
echo "    仓库:     $PANGU_DIR"
echo "    数据目录: $PANGU_HOME"
echo "    服务端口: $HOST:$PORT  (MCP + REST)"
if [ "$HOST_AUTO" = 1 ]; then
  echo "    监听地址: $HOST  ← 自动判定，$ROLE_REASON"
  echo "              （想改：./install.sh --host 0.0.0.0 或 --host 127.0.0.1）"
else
  echo "    监听地址: $HOST  ← $ROLE_REASON"
fi
[ "$INSTALL_SERVICE" = 1 ] && echo "    服务管理: systemctl --user $SERVICE_NAME"

# ════════════════════════════════════════════════════════════
# 0. 环境自检
# ════════════════════════════════════════════════════════════
if [ "$MODEL_ONLY" = 0 ]; then

# 开场就把"将要经历什么、大概多久"说清楚 ——
# 小白最怕的不是慢，而是"没动静、不知道还要等多久"（2026-09-22 反馈）。
c_cyan "盘古安装程序"
echo "  共 5 步：环境自检 → 建虚拟环境 → 装依赖 → 下载模型 → 装开机服务"
echo "  预计 1-3 分钟。装依赖用 uv（缺了会自动装，约 10 秒）—— 约 20 秒装完；"
echo "  万一 uv 装不上才退回 pip，那时需 8-15 分钟（会持续报进度）。"
echo "  每步都会打印进度；长时间无输出时会每 10 秒报一次已用时间。"
echo "  关键步骤失败会明确报错并停下，不会静默降级。"

step "0/5 环境自检"

# Python 版本：pyproject.toml 要求 >=3.11（注意 docs 里曾误写 3.10）
PY=""
for cand in "$VENV_DIR/bin/python" python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then
    v=$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0.0")
    major=${v%%.*}; minor=${v##*.}
    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then PY="$cand"; break; fi
  fi
done
[ -n "$PY" ] || die "未找到 Python >= 3.11。请先安装（推荐 3.12）。
   提示：uv 可一键安装 Python：uv python install 3.12"
ok "Python $("$PY" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')  ($PY)"

# 自动装 uv：官方安装脚本，装到 ~/.local/bin。
#
# 两个刻意的选择：
#  1) `UV_UNMANAGED_INSTALL` 而不是默认安装 —— 默认安装会去改用户的
#     shell 配置（追加 PATH），那属于"未经请求地动别人的环境"。这里只把
#     二进制放进 ~/.local/bin，本次运行临时加进 PATH 即可。
#  2) 失败**不作为错误**：装不上就退回 pip3，只是慢，不该因此装不成。
#
# 想跳过自动安装：`PANGU_NO_UV=1 ./install.sh`。
_try_install_uv() {
  [ "${PANGU_NO_UV:-0}" = "1" ] && return 1
  command -v curl >/dev/null 2>&1 || return 1
  echo "    未检测到 uv —— 自动安装（约 10 秒，装到 ~/.local/bin，不改你的 shell 配置）…"
  if curl -LsSf --max-time 180 https://astral.sh/uv/install.sh \
       | env UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh >/dev/null 2>&1 \
     && [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
    return 0
  fi
  echo "    uv 自动安装失败（网络？）—— 退回 pip3，速度会慢不少"
  return 1
}

# 包管理器：uv 优先。
# 实测差距悬殊：uv 装依赖约 20 秒，pip 首次要 8-15 分钟（56 包 / 223MB）。
# 所以没装 uv 时**主动装一个**，而不是让小白干等十几分钟看屏幕不动。
PKG=""
if command -v uv >/dev/null 2>&1; then
  PKG="uv"; ok "包管理器: uv（快，推荐）"
elif _try_install_uv; then
  PKG="uv"; ok "包管理器: uv（本次自动安装到 ~/.local/bin）"
elif command -v pip3 >/dev/null 2>&1; then
  PKG="pip3"; warn "包管理器: pip3 —— 安装会明显更慢（预计 8-15 分钟），中途会持续报进度"
else
  die "未找到 uv 或 pip3，请先安装其一（apt install python3-pip 或先装 uv）"
fi

# 磁盘空间：依赖 223MB + 模型 23MB + 数据目录，留 2GB 余量
AVAIL_KB=$(df -Pk "$REPO_DIR" | awk 'NR==2{print $4}')
if [ "${AVAIL_KB:-0}" -lt 2097152 ]; then
  warn "磁盘可用空间仅 $(( AVAIL_KB / 1024 )) MB，建议至少 2 GB"
else
  ok "磁盘可用 $(( AVAIL_KB / 1024 / 1024 )) GB"
fi
fi  # MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 1. 创建虚拟环境
# ════════════════════════════════════════════════════════════
if [ "$MODEL_ONLY" = 0 ]; then
step "1/5 创建虚拟环境"

if [ -x "$VENV_DIR/bin/python" ]; then
  ok "已存在 $VENV_DIR，跳过创建"
else
  if [ "$PKG" = "uv" ]; then
    uv venv "$VENV_DIR" --python "$PY"
  else
    "$PY" -m venv "$VENV_DIR"
  fi
  ok "已创建 $VENV_DIR"
fi
VPY="$VENV_DIR/bin/python"
[ -x "$VPY" ] || die "虚拟环境创建失败：$VPY 不可执行"

# ════════════════════════════════════════════════════════════
# 2. 安装依赖
# ════════════════════════════════════════════════════════════
step "2/5 安装 Python 依赖"
echo "    ⏱  首次安装需下载 56 个包 / 约 223 MB，预计 5-10 分钟。"
echo "       其中 onnxruntime (54MB) 与 numpy (55MB) 最大，请耐心等待，"
echo "       不要中断——中断会导致缓存已下载但包未装好。"

DEPS_START=$(date +%s)
heartbeat_start "安装 Python 依赖（$PKG）"
if [ "$PKG" = "uv" ]; then
  uv pip install -r "$REPO_DIR/requirements.txt" --python "$VPY"
else
  "$VPY" -m pip install --upgrade pip
  "$VPY" -m pip install -r "$REPO_DIR/requirements.txt"
fi
heartbeat_stop
DEPS_SEC=$(( $(date +%s) - DEPS_START ))
ok "依赖安装完成（耗时 ${DEPS_SEC}s）"

# 以 editable 方式安装盘古自身（提供 pangu CLI + 刷新 dist-info 元数据）
if [ "$PKG" = "uv" ]; then
  uv pip install -e "$REPO_DIR" --python "$VPY" --no-deps
else
  "$VPY" -m pip install -e "$REPO_DIR" --no-deps
fi
VER=$("$VPY" -c 'import pangu;print(pangu.__version__)' 2>/dev/null || echo "未知")
ok "盘古已安装（版本 $VER）"

# 校验 CLI 可用
if "$VPY" -m pangu.cli --help >/dev/null 2>&1; then
  ok "CLI 可用: $VENV_DIR/bin/pangu"
else
  warn "pangu CLI 调用异常，请检查依赖是否装全"
fi
fi  # MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 3. 预下载 ONNX 模型 —— 关键步骤，失败必须报错
# ════════════════════════════════════════════════════════════
step "3/5 准备 ONNX 嵌入模型"
echo "    ⏱  模型约 23 MB。此步骤如果跳过，服务启动时会静默降级到"
echo "       无语义的 hash 向量，检索结果将完全不可信。"

VPY="${VPY:-$VENV_DIR/bin/python}"
[ -x "$VPY" ] || die "找不到 $VPY，请先完成依赖安装"

# 从本地文件安装（内网/弱网）
if [ -n "$OFFLINE_MODEL" ]; then
  IFS=',' read -r M_FILE T_FILE <<< "$OFFLINE_MODEL"
  [ -f "$M_FILE" ] || die "找不到模型文件: $M_FILE"
  [ -f "$T_FILE" ] || die "找不到 tokenizer 文件: $T_FILE"
  CACHE_DIR=$("$VPY" -c "
from pangu.memory.onnx_embedder import ONNXEmbedder
from pangu.core.config import PanguConfig
print(ONNXEmbedder(cache_dir=PanguConfig.load().onnx_cache_dir or None).cache_dir)")
  mkdir -p "$CACHE_DIR"
  cp "$M_FILE" "$CACHE_DIR/model_quantized.onnx"
  cp "$T_FILE" "$CACHE_DIR/tokenizer.json"
  ok "已从本地文件安装模型到 $CACHE_DIR"
else
  # 在线下载，多源自动回退（onnx_embedder 内部已实现 hf-mirror → huggingface）
  DL_START=$(date +%s)
  heartbeat_start "下载 ONNX 模型（约 23 MB）"
  set +e
  DL_OUT=$("$VPY" - <<'PY' 2>&1
import sys
from pangu.core.config import PanguConfig
from pangu.memory.onnx_embedder import ONNXEmbedder
cfg = PanguConfig.load()
emb = ONNXEmbedder(
    cache_dir=cfg.onnx_cache_dir or None,
    model_id=cfg.onnx_model_id,
    quantized=cfg.onnx_quantized,
)
if emb._ensure_loaded():
    print("MODEL_OK", emb.cache_dir)
else:
    print("MODEL_FAIL", emb._load_error)
    sys.exit(1)
PY
)
  DL_RC=$?
  set -e
  heartbeat_stop
  DL_SEC=$(( $(date +%s) - DL_START ))

  if [ $DL_RC -ne 0 ] || ! grep -q "MODEL_OK" <<< "$DL_OUT"; then
    c_red ""
    c_red "════════════════════════════════════════════════════════"
    c_red " 模型下载失败 —— 安装中止"
    c_red "════════════════════════════════════════════════════════"
    echo "$DL_OUT" | sed 's/^/   /'
    # 动态取当前 ONNX 模型 ID 生成提示，避免 URL / 目录名随模型更换而漂移。
    # （曾硬编码旧模型 Xenova/all-MiniLM-L6-v2，2026-09-19 换多语模型后提示全错）
    MODEL_ID=$("$VPY" -c "from pangu.core.config import PanguConfig; print(PanguConfig.load().onnx_model_id)" 2>/dev/null || echo "Xenova/paraphrase-multilingual-MiniLM-L12-v2")
    MODEL_CACHE_NAME=$(echo "$MODEL_ID" | sed 's|/|__|g')
    cat <<EOF

   为什么中止而不是继续：
     缺少该模型时，盘古**不会报错**，而是静默降级到 hash 向量。
     服务照常启动、检索照常返回结果，但结果没有任何语义能力
     （实测 cos(猫, dog) = 0.0000）。你会得到一个"看起来正常
     但检索全错"的系统，且极难察觉。

   怎么办（任选其一）：
     1) 换网络后重试（可设国内镜像）：
          PANGU_ONNX_MIRROR_BASE=https://hf-mirror.com ./install.sh
     2) 手动下载后从本地安装：
          下载这两个文件（约 23MB）：
            https://hf-mirror.com/${MODEL_ID}/resolve/main/onnx/model_quantized.onnx
            https://hf-mirror.com/${MODEL_ID}/resolve/main/tokenizer.json
          然后：
            ./install.sh --offline-model /路径/model_quantized.onnx,/路径/tokenizer.json
     3) 已经手工放好模型：把模型放到
            ~/.cache/pangu/onnx/${MODEL_CACHE_NAME}/
          （需含 model_quantized.onnx 与 tokenizer.json）后重跑本脚本。
EOF
    exit 1
  fi
  ok "模型就绪（耗时 ${DL_SEC}s）: $(echo "$DL_OUT" | grep MODEL_OK | awk '{print $2}')"
fi

# 复验：模型可用且维度正确
# 注意：ONNXEmbedder 是**惰性加载**的——EmbeddingService 构造时只创建对象
# （embedding.py:64-65 的 _init_onnx_embedder），模型在首次 embed() 时才加载。
# 所以必须先调一次 embed()，否则 model_loaded 恒为 False（曾因此误报失败）。
"$VPY" - <<'PY' || die "模型复验失败"
import sys
from pangu.core.config import PanguConfig
from pangu.memory.embedding import EmbeddingService
svc = EmbeddingService(PanguConfig.load())
v = svc.embed("盘古")          # 触发惰性加载
st = svc.stats.get("onnx", {})  # stats 是 @property，不是方法
if not st.get("model_loaded"):
    print("    模型复验失败: model_loaded=False，服务将降级到 hash 向量", file=sys.stderr)
    sys.exit(1)
assert v is not None and len(v) == 384, f"向量维度异常: {len(v) if v else None}"
print(f"    复验通过: ONNX 已加载，向量维度 {len(v)}")
PY
ok "模型验证通过（ONNX 真实加载，非降级）"

# ════════════════════════════════════════════════════════════
# 4. 初始化数据目录
# ════════════════════════════════════════════════════════════
if [ "$MODEL_ONLY" = 0 ]; then
step "4/5 初始化数据目录"
if [ -f "$PANGU_HOME/config.json" ]; then
  ok "已存在 $PANGU_HOME/config.json，跳过初始化"
else
  "$VPY" -m pangu.cli init --path "$PANGU_HOME"
  ok "已初始化 $PANGU_HOME"
fi
fi  # MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 4b. 生成凭据 + DSH 填写卡
# ════════════════════════════════════════════════════════════
if [ "$MODEL_ONLY" = 0 ]; then
step "4b/5 生成凭据"

VPY="${VPY:-$VENV_DIR/bin/python}"

# ── REST 主密钥 与 admin 管理密钥：**共用同一把**（2026-09-21 决定）──
# 服务端这两把钥匙是两套独立校验：
#   .api_key      → config.api_key      （X-API-Key：MCP + 数据面）
#   .admin_secret → admin_auth.verify_admin() 比对（X-Admin-Key：管理面）
# 对单人部署而言两者隔离的边际价值很低（平台令牌审核通过即全权），却让新用户
# 在设置页要填两次、多一个出错点。故这里**生成同一个值**写进两个文件：
# 于是插件设置页只需填一处「盘古凭据」，管理面复用它（见 lib/index.js
# 的 readAdminSecret）；服务端代码与校验逻辑不变。
# 已存在任一文件时**复用它的值**（升级场景不能改已生效的凭据 —— 服务端 env 里
# 那把也要跟着变，很容易漏改，会直接把用户踢下线）。
API_KEY_FILE="$PANGU_HOME/.api_key"
ADMIN_SECRET_FILE="$PANGU_HOME/.admin_secret"
SHARED_SECRET=""
if [ -s "$API_KEY_FILE" ]; then
  SHARED_SECRET="$(cat "$API_KEY_FILE")"
  ok ".api_key 已存在，复用它作为共用凭据"
elif [ -s "$ADMIN_SECRET_FILE" ]; then
  SHARED_SECRET="$(cat "$ADMIN_SECRET_FILE")"
  ok ".admin_secret 已存在，复用它作为共用凭据"
else
  SHARED_SECRET=$("$VPY" -c "import secrets; print(secrets.token_urlsafe(32))")
  ok "已生成共用凭据（REST 主密钥 = 管理密钥）"
fi
for _cred_file in "$API_KEY_FILE" "$ADMIN_SECRET_FILE"; do
  if [ -s "$_cred_file" ]; then
    continue
  fi
  printf '%s' "$SHARED_SECRET" > "$_cred_file"
  chmod 600 "$_cred_file"
  ok "$(basename "$_cred_file") 已写入（权限 600）"
done
unset SHARED_SECRET

# 两者都已存在但值不同（例如老部署）：**不擅自改动**，只提示怎么统一。
if [ -s "$API_KEY_FILE" ] && [ -s "$ADMIN_SECRET_FILE" ] \
  && [ "$(cat "$API_KEY_FILE")" != "$(cat "$ADMIN_SECRET_FILE")" ]; then
  warn "REST 主密钥与管理密钥当前不是同一把（保留原样，未改动任何文件）"
  warn "  想把它们统一：在 DSH 设置页把两处填成同一个值即可"
fi

# 生成 pangu.env 给 systemd EnvironmentFile 用
PANGU_ENV="$PANGU_HOME/pangu.env"
if [ -f "$PANGU_ENV" ]; then
  ok "pangu.env 已存在，跳过"
else
  {
    echo "PANGU_API_KEY=$(cat "$API_KEY_FILE")"
    if [ "$PANGU_HOME" != "$HOME/.pangu" ]; then
      echo "PANGU_BASE_DIR=$PANGU_HOME"
    fi
  } > "$PANGU_ENV"
  chmod 600 "$PANGU_ENV"
  ok "pangu.env 已生成（权限 600）"
fi
fi  # MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 5. systemd 用户服务
# ════════════════════════════════════════════════════════════
if [ "$INSTALL_SERVICE" = 1 ] && [ "$MODEL_ONLY" = 0 ]; then
step "5/5 安装 systemd 用户服务（端口 $PORT）"

if ! command -v systemctl >/dev/null 2>&1; then
  warn "未检测到 systemctl（容器环境常见），跳过服务安装"
  warn "  手动启动：./start.sh"
elif ! systemctl --user show-environment >/dev/null 2>&1; then
  warn "systemd 用户会话不可用，跳过服务安装"
  warn "  手动启动：./start.sh"
else
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_FILE="$UNIT_DIR/$SERVICE_NAME.service"
  LOG_DIR="$REPO_DIR/.deploy-logs"
  mkdir -p "$UNIT_DIR" "$LOG_DIR"

  # ⚠ 安全检查：绝不静默覆盖已存在的服务单元。
  # 一个已存在的单元可能指向**另一份安装**（另一个仓库路径/端口），
  # 直接覆盖会把别人正在跑的服务替换掉——这属于破坏性操作，必须显式确认。
  if [ -f "$UNIT_FILE" ] && ! grep -q "WorkingDirectory=$REPO_DIR\$" "$UNIT_FILE"; then
    EXISTING_DIR=$(awk -F= '/^WorkingDirectory=/{print $2}' "$UNIT_FILE")
    c_red ""
    c_red "检测到已存在的服务单元，但它指向另一份安装："
    echo "    现有单元: $UNIT_FILE"
    echo "    指向路径: ${EXISTING_DIR:-未知}"
    echo "    本次安装: $REPO_DIR"
    c_red ""
    echo "  覆盖它会停掉现有服务（可能是另一个正在运行的环境）。"
    echo "  若确实要替换，请显式确认："
    echo "      PANGU_REPLACE_SERVICE=1 ./install.sh --port $PORT"
    echo "  或先移除现有单元："
    echo "      systemctl --user disable --now $SERVICE_NAME && rm $UNIT_FILE"
    echo "  若只想装到目录而不动服务：./install.sh --no-service"
    if [ "${PANGU_REPLACE_SERVICE:-0}" != "1" ]; then
      die "已中止，未修改任何现有服务"
    fi
    warn "PANGU_REPLACE_SERVICE=1 已确认，将覆盖现有单元"
  fi

  # 路径全部由本脚本解析，不写死——用户可把仓库放在任意位置
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Pangu Memory System API (盘古记忆系统)
Documentation=https://github.com/Mlte0907/pangu
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PANGU_HOST=$HOST
Environment=PANGU_PORT=$PORT
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$PANGU_HOME/pangu.env
ExecStart=$VPY -c "import sys; sys.path.insert(0, '$REPO_DIR'); import uvicorn; from pangu.api.server import create_app; uvicorn.run(create_app(), host='$HOST', port=$PORT, log_level='info')"
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/$SERVICE_NAME.log
StandardError=append:$LOG_DIR/$SERVICE_NAME.log

[Install]
WantedBy=default.target
EOF
  ok "已写入 $UNIT_FILE"

  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  systemctl --user daemon-reload
  systemctl --user enable "$SERVICE_NAME" >/dev/null 2>&1 || warn "enable 失败（不影响本次启动）"
  systemctl --user restart "$SERVICE_NAME"
  sleep 3

  if systemctl --user is-active --quiet "$SERVICE_NAME"; then
    ok "服务已启动并设为开机自启"
  else
    warn "服务未能启动，查看日志："
    warn "  journalctl --user -u $SERVICE_NAME -n 30"
    warn "  tail -30 $LOG_DIR/$SERVICE_NAME.log"
  fi

  # 让用户级 systemd 服务在「无登录会话」与「机器重启」后仍能自启。
  # 云端（尤其 root 用户）通过 SSH 部署时，若未开 linger，机器一重启服务
  # 就不会自动拉起，表现为"昨天还好好的，今天连不上"（实测踩到）。
  if command -v loginctl >/dev/null 2>&1; then
    if loginctl enable-linger "$(id -un)" 2>/dev/null; then
      ok "已开启 linger（$(id -un)）—— 机器重启后服务自启"
    else
      warn "未开启 linger —— 机器重启后服务可能不自启，请手动执行："
      warn "  loginctl enable-linger $(id -un)"
    fi
  fi
fi
fi  # INSTALL_SERVICE && !MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 6. 安装 DSH 插件（可选）
# ════════════════════════════════════════════════════════════
# 插件自 2026-09-22 起是**独立仓库**（Mlte0907/dsh-pangu）：盘古本体不依赖它，
# 不用 DSH 的人装完上面就完事。这里按需拉取，失败只提示、不影响本体安装
# —— 插件是可选项，不该因为它拖垮主线。
if [ "$INSTALL_DSH_PLUGIN" = 1 ]; then
step "附加：安装 DSH 插件（可选）"
PLUGIN_SRC="${DSH_PANGU_SRC:-$HOME/.dsh-pangu}"
if [ -d "$PLUGIN_SRC/.git" ]; then
  git -C "$PLUGIN_SRC" pull --ff-only 2>/dev/null || warn "插件仓库拉取失败，用现有代码继续"
else
  echo "    获取插件仓库到 $PLUGIN_SRC"
  git clone --depth 1 https://github.com/Mlte0907/dsh-pangu "$PLUGIN_SRC" 2>/dev/null \
    || warn "插件仓库获取失败（网络？）"
fi
if [ -x "$PLUGIN_SRC/install.sh" ]; then
  bash "$PLUGIN_SRC/install.sh" "${DSH_PROFILE:-web}" \
    || warn "插件安装未完成，可稍后重跑：bash $PLUGIN_SRC/install.sh"
else
  warn "未取得插件，已跳过。稍后可手动安装："
  warn "  curl -fsSL https://raw.githubusercontent.com/Mlte0907/dsh-pangu/main/install.sh | bash"
fi
fi

# ════════════════════════════════════════════════════════════
# 完成 + 验证
# ════════════════════════════════════════════════════════════
step "验证安装"

HEALTH_URL="http://$HOST:$PORT/health"
if [ "$HOST" = "0.0.0.0" ]; then HEALTH_URL="http://127.0.0.1:$PORT/health"; fi

# 先验证「本次安装的代码」本身可用——不依赖服务是否在跑。
# 只探 HTTP 是不够的：端口上可能跑着**上一次**装的服务（旧进程），
# 会误报成功。所以这里直接 import 本次的 .venv 校验。
if "$VPY" -c "
import sys; sys.path.insert(0, '$REPO_DIR')
from pangu.api.server import create_app
app = create_app()
assert app.version
print(f'    代码可用: app.version={app.version}')
" 2>/dev/null; then
  ok "本次安装的代码可正常构造应用"
else
  die "本次安装的代码无法构造应用——依赖可能不完整，请检查上面的安装日志"
fi

# 验证嵌入后端**真的可用**，而不只是"文件存在"。
# 为什么必须实测：ONNX 模型文件在、但加载失败时，embed() 会静默降级为
# hash 向量——合法、非零、384 维，一切检查都通过，但检索结果**没有语义能力**。
# 这是本项目最隐蔽的缺陷（v0.1.3 修），所以安装收尾必须断言真实后端。
BACKEND=$("$VPY" -c "
import sys; sys.path.insert(0, '$REPO_DIR')
from pangu.core.config import PanguConfig
from pangu.memory.embedding import EmbeddingService
svc = EmbeddingService(PanguConfig.load())
svc.embed('安装后验证')
print(svc.active_backend)
" 2>/dev/null || echo "ERROR")

if [ "$BACKEND" = "onnx" ]; then
  ok "嵌入后端: onnx（语义检索可用）"
elif [ "$BACKEND" = "api" ]; then
  ok "嵌入后端: api（远程嵌入服务）"
elif [ "$BACKEND" = "hash" ]; then
  warn "嵌入后端降级为 hash —— 检索结果将**没有语义能力**（相同含义的文本不会相近）"
  warn "  原因通常是 ONNX 模型未能加载。请重跑步骤 3/5 预下载模型："
  warn "    $REPO_DIR/install.sh --model-only"
  warn "  或配置 embed_api_url 使用远程嵌入服务。"
else
  warn "无法确定嵌入后端（$BACKEND）—— 请运行 ./install.sh 检查，或手动执行："
  warn "    cd $REPO_DIR && .venv/bin/python -c 'from pangu.memory.embedding import get_embedding_service as g; s=g(); s.embed(\"x\"); print(s.active_backend)'"
fi

if [ "$INSTALL_SERVICE" = 1 ]; then
  RESP=$(curl -s --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "")
  if [ -n "$RESP" ]; then
    ok "服务健康: $RESP"
    # /health 现在会报 degraded —— 不要让用户在一堆绿字里错过它
    case "$RESP" in
      *'"status":"degraded"'*|*'"status": "degraded"'*)
        warn "  ↑ 但 /health 报 degraded：嵌入后端降级，检索质量不可信"
        ;;
    esac
  else
    warn "无法访问 $HEALTH_URL —— 服务可能未启动"
    warn "  手动启动：./start.sh"
  fi
else
  warn "已跳过 systemd 服务安装（--no-service），未部署常驻服务"
  warn "  手动启动：./start.sh  （监听 $HOST:$PORT）"
fi

# ── 组装「盘古服务地址」──
# 目标：**照抄就能连上**。所以给"实际可达的那个地址"，并把"插件恰好就在同一台
# 机器上"的可能一并列出（回环地址永远有效）。
# 不假定用户绑了域名 —— 云端新用户很可能只用公网 IP 直连。
# hostname -I 在公有云上返回的是**内网 IP**（172.x），直接印出去等于没说，
# 所以依次尝试：SSH 连接到的地址 → 公网 IP 探测 → 网卡 IPv4（局域网部署时正确）。
LAN_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -m1 -E '^[0-9]+\.' || true)
if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  ACCESS_IP=""
  # ① SSH 登录时连接到的服务端地址（公有云上通常就是公网 IP）
  if [ -n "${SSH_CONNECTION:-}" ]; then
    ACCESS_IP=$(echo "$SSH_CONNECTION" | awk '{print $3}')
    [ "$ACCESS_IP" = "127.0.0.1" ] && ACCESS_IP=""
  fi
  # ①.5 云厂商 metadata 里的公网 IP。
  # 为什么需要：从**网页控制台**装的云主机拿不到 SSH_CONNECTION，而 hostname -I
  # 给的是 VPC 内网 IP（172.x/10.x），填进插件根本连不上。各家字段名不同，逐个试。
  if [ -z "$ACCESS_IP" ] && command -v curl >/dev/null 2>&1; then
    for _p in /latest/meta-data/public-ipv4 /latest/meta-data/eipv4 /latest/meta-data/publicIpv4 /latest/meta-data/public-ip; do
      _v=$(curl -s -m 1 "http://169.254.169.254$_p" 2>/dev/null || true)
      case "$_v" in
        [0-9]*.[0-9]*.[0-9]*.[0-9]*) ACCESS_IP="$_v"; break ;;
      esac
    done
  fi
  # ② 探测出口公网 IP（3 秒超时，失败不影响安装）
  if [ -z "$ACCESS_IP" ] && command -v curl >/dev/null 2>&1; then
    ACCESS_IP=$(curl -s --max-time 3 https://api.ipify.org 2>/dev/null || true)
  fi
  # ③ 兜底：网卡 IPv4（局域网主机部署时这就是对的答案）
  [ -n "$ACCESS_IP" ] || ACCESS_IP="$LAN_IP"
  [ -n "$ACCESS_IP" ] || ACCESS_IP="<这台机器的IP>"
  ACCESS_ADDR="http://$ACCESS_IP:$PORT"

  # 附上其它同样可用的地址（插件在同机/同网段时更省事）
  ACCESS_ALT_BLOCK=""
  [ "$ACCESS_IP" != "127.0.0.1" ] && \
    ACCESS_ALT_BLOCK="$ACCESS_ALT_BLOCK"$'\n'"                 本机自用：http://127.0.0.1:$PORT"
  if [ -n "$LAN_IP" ] && [ "$LAN_IP" != "$ACCESS_IP" ]; then
    ACCESS_ALT_BLOCK="$ACCESS_ALT_BLOCK"$'\n'"                 局域网内：http://$LAN_IP:$PORT"
  fi
  ACCESS_ALT_BLOCK="$ACCESS_ALT_BLOCK"$'\n'"                 或 https://你的域名    # 若已用 nginx+TLS 绑域名，改填这个"

  # 探测到内网 IP 时（VPC / 家庭局域网 / ipify 不通）明说一句，免得用户以为算错了
  case "$ACCESS_IP" in
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) PRIVATE_IP=1 ;;
  esac
else
  ACCESS_ADDR="http://$HOST:$PORT"
  # 本机自用（只监听回环）是最安全的形态：给一句"以后要给别的机器用怎么办"就够
  ACCESS_ALT_BLOCK=$'\n'"                 （本机自用，只监听回环；要给别的机器用：重跑 ./install.sh --host 0.0.0.0）"
  # 只有「明显是服务器却强制回环」时才展开详细说明：显式指定的，或经 SSH 装的
  # （用 SSH_REMOTE 而不是裸 SSH_CONNECTION —— 后者在 `ssh localhost` 时也为真，
  #   会给本机自用的用户加一段没用的说明）
  if [ "$HOST_AUTO" = 0 ] || [ "$SSH_REMOTE" = 1 ]; then
    REMOTE_HINT=1
  fi
fi

# 卡片里的地址块（单变量拼接，避免多出一行空行）
CARD_ADDR="盘古服务地址   : $ACCESS_ADDR$ACCESS_ALT_BLOCK"
if [ -n "${PRIVATE_IP:-}" ]; then
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_yellow "                 ⚠ 上面是**内网地址**（这台机器没有公网 IP）：跨公网访问请改填公网 IP 或域名")"
fi
if [ -n "${REMOTE_HINT:-}" ]; then
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_yellow "                 ⚠ 只监听本机回环 —— DSH 插件装在别的机器上时，上面这个地址连不通。二选一：")"
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_green  "                 ▸ 推荐（最安全）：在**运行 DSH 的那台电脑**上执行，然后上面地址照填")"
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_green  "                     ssh -N -L $PORT:127.0.0.1:$PORT ${USER:-root}@<这台服务器的公网IP或域名>")"
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_yellow "                 ▸ 或让插件直连：在这台服务器上重跑 ./install.sh --host 0.0.0.0")"
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_yellow "                     （会自动探测公网 IP 并改写本卡片；公网暴露务必配 nginx+TLS，")"
  CARD_ADDR="$CARD_ADDR"$'\n'"$(c_yellow "                       并在云安全组放行 $PORT、限制来源 IP）")"
fi

# 「远程访问」说明块：只在**明显是服务器却仍监听回环**时给出
# （显式 --host 127.0.0.1，或经 SSH 安装）。自动判定成本机自用的情况不展开，
# 免得给单机用户加噪音 —— 卡片上那一句"要给别的机器用怎么办"已经够用。
REMOTE_NOTES=""
if [ "$HOST" = "127.0.0.1" ] \
   && { [ "$HOST_AUTO" = 0 ] || [ "$SSH_REMOTE" = 1 ]; }; then
  REMOTE_NOTES=$'\n'"$(c_yellow "【远程访问】本服务只监听 127.0.0.1（本机回环）")"
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"  若 DSH 插件装在**别的电脑**上，卡片里的 127.0.0.1 指的是这台服务器自己，连不通。二选一："
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"  ▸ 推荐：SSH 隧道（不暴露端口、无需证书）—— 在**运行 DSH 的那台电脑**上执行："
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"$(c_green "      ssh -N -L $PORT:127.0.0.1:$PORT ${USER:-root}@<这台服务器的公网IP或域名>")"
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"    之后 DSH 设置页「盘古服务地址」照填 http://127.0.0.1:$PORT 即可（加 -f 可后台常驻）。"
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"  ▸ 或让插件直连：在这台服务器上重跑  ./install.sh --host 0.0.0.0"
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"    脚本会把卡片地址改成探测到的公网 IP。公网暴露**必须**同时做："
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"      · nginx + TLS 反代（推荐），或用云安全组把 $PORT 只放行你的来源 IP"
  REMOTE_NOTES="$REMOTE_NOTES"$'\n'"      · 内置 API Key 只防误连，不防针对性攻击"
fi

# 绑全网卡时的安全提示：这条路是"给别的机器用"的默认选择，必须把代价说清楚。
# 云主机不放行安全组 → 服务 active 但插件连不上，是小白最常见的卡点。
BIND_NOTES=""
if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  BIND_NOTES=$'\n'"$(c_yellow "【已监听所有网卡（$HOST）—— 别的机器可以直连】")"
  BIND_NOTES="$BIND_NOTES"$'\n'"  · **云主机：安全组必须放行 $PORT**（默认全封；不放行则服务正常但插件连不上）"
  BIND_NOTES="$BIND_NOTES"$'\n'"  · 暴露到公网：建议前面加 nginx+TLS —— 明文 HTTP 下 API Key 会裸奔"
  BIND_NOTES="$BIND_NOTES"$'\n'"  · 只想本机用（更安全）：重跑 ./install.sh --host 127.0.0.1"
fi

# 凭据块：只列**要填到设置页的那一条**。
# 4b 已保证 .api_key 与 .admin_secret 同值，而插件设置页只有一个凭据字段，
# 所以卡片只列「盘古凭据」；两个文件不同（早期部署）时才额外给一行服务端修正提示
# —— 那种情况下插件管理面会 401（见 lib/index.js 的 adminFetch）。
CARD_CRED="盘古凭据       : $(cat "$PANGU_HOME/.api_key" 2>/dev/null || echo '<未生成>')"
if [ -s "$PANGU_HOME/.api_key" ] && [ -s "$PANGU_HOME/.admin_secret" ] \
  && [ "$(cat "$PANGU_HOME/.api_key")" != "$(cat "$PANGU_HOME/.admin_secret")" ]; then
  CARD_CRED="$CARD_CRED"$'\n'"$(c_yellow '管理密钥       : —— 与上面不同（早期部署），插件管理面会 401')"
  CARD_CRED="$CARD_CRED"$'\n'"$(c_yellow "  在服务端执行这行即可统一：")"
  CARD_CRED="$CARD_CRED"$'\n'"$(c_yellow "    printf '%s' '$(cat "$PANGU_HOME/.api_key")' > \$HOME/.pangu/.admin_secret")"
fi

cat <<EOF

$(c_green '════════════════════════════════════════════════════════')
$(c_green ' 安装完成')
$(c_green '════════════════════════════════════════════════════════')

$(c_yellow '【重要】盘古有两个不同的服务，别搞混：')

  端口 $PORT  ← 本次安装的 API 服务$(if [ "$INSTALL_SERVICE" = 1 ]; then echo '（已由 systemd 托管）'; else echo '（尚未部署为服务，需手动启动）'; fi)
      应用: pangu/api/server.py
      用途: MCP + REST 接口，DSH 插件连的是这个
      启动: systemctl --user start $SERVICE_NAME   （或 ./start.sh）
      验证: curl $HEALTH_URL
      MCP:  $ACCESS_ADDR/mcp

  端口 8866  ← 另一个服务（人类可读的 Web 界面）
      应用: pangu/server/web_server.py
      用途: 浏览器里看的仪表盘，**不含 MCP 接口**
      启动: .venv/bin/pangu serve
      注意: 它不能替代 $PORT，DSH 插件连它没用

$(c_yellow '【常用命令】')
  服务:  systemctl --user {start|stop|restart|status} $SERVICE_NAME
  日志:  tail -f $REPO_DIR/.deploy-logs/$SERVICE_NAME.log
  统计:  .venv/bin/pangu stats
  搜索:  .venv/bin/pangu search "关键词"
  帮助:  .venv/bin/pangu --help      ← 有 30+ 子命令，README 未提及

$(c_yellow '【接入 DSH（可选）】')
  1. ./install.sh --dsh-plugin            （会拉取独立仓库 ~/.dsh-pangu 并安装）
     或直接: curl -fsSL https://raw.githubusercontent.com/Mlte0907/dsh-pangu/main/install.sh | bash
  2. 重启 DSH
  3. DSH 设置 →「盘古记忆系统」填 LLM 提供商与 API Key，点「测试连接」

$(c_yellow '【配置】')
  数据目录: $PANGU_HOME        （config.json 权限 600）
  LLM 密钥: $PANGU_HOME/.llm_api_key  （不写入 config.json，重启不丢）
  环境变量: PANGU_HOST / PANGU_PORT / PANGU_LOG_LEVEL / PANGU_ONNX_CACHE_DIR

$REMOTE_NOTES
$BIND_NOTES

$(c_cyan '──────────── DSH 插件填写卡（复制到 DSH 设置页）────────────')
$(c_green "$CARD_ADDR")
$(c_green "$CARD_CRED")
$(c_cyan '──────────────────────────────────────────────────────────────────')
$(c_yellow 'LLM 三项（模型/端点/Key）在 DSH 设置页「01 LLM 配置」里填')
$(c_yellow '↑ 以上凭据只显示一次，请立即保存')
EOF
