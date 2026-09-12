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
#   ./install.sh --dsh-plugin       # 额外安装 DSH 插件
#   ./install.sh --port 19529       # 指定端口
#   ./install.sh --model-only       # 仅预下载模型（已装好依赖时用）
#   ./install.sh --offline-model /path/to/model_quantized.onnx,/path/to/tokenizer.json
#                                   # 从本地文件装模型（内网/弱网）
#
# 幂等：可重复执行，已完成的步骤会跳过。

set -euo pipefail

# ── 配置 ──
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PANGU_HOME="${PANGU_HOME:-$HOME/.pangu}"
PORT="19529"
HOST="127.0.0.1"
INSTALL_SERVICE=1
INSTALL_DSH_PLUGIN=0
MODEL_ONLY=0
OFFLINE_MODEL=""
SERVICE_NAME="pangu-api"

# ── 输出helpers ──
c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
c_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
step()    { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()      { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn()    { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()     { printf '\n\033[31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

# ── 参数解析 ──
while [ $# -gt 0 ]; do
  case "$1" in
    --port)         PORT="${2:?--port 需要参数}"; shift 2 ;;
    --host)         HOST="${2:?--host 需要参数}"; shift 2 ;;
    --no-service)   INSTALL_SERVICE=0; shift ;;
    --dsh-plugin)   INSTALL_DSH_PLUGIN=1; shift ;;
    --model-only)   MODEL_ONLY=1; shift ;;
    --offline-model) OFFLINE_MODEL="${2:?--offline-model 需要参数}"; shift 2 ;;
    -h|--help)
      # 打印文件头部注释块（从第 2 行到第一处非注释行前）
      awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"
      exit 0 ;;
    *) die "未知参数: $1（用 --help 查看用法）" ;;
  esac
done

PANGU_DIR="$REPO_DIR"
cd "$PANGU_DIR"

printf '\033[1m盘古记忆系统 — 安装\033[0m\n'
echo "    仓库:     $PANGU_DIR"
echo "    数据目录: $PANGU_HOME"
echo "    服务端口: $HOST:$PORT  (MCP + REST)"
[ "$INSTALL_SERVICE" = 1 ] && echo "    服务管理: systemctl --user $SERVICE_NAME"

# ════════════════════════════════════════════════════════════
# 0. 环境自检
# ════════════════════════════════════════════════════════════
if [ "$MODEL_ONLY" = 0 ]; then
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

# 包管理器：uv 优先（实测冷装 8 分钟，pip 更慢）
PKG=""
if command -v uv >/dev/null 2>&1; then
  PKG="uv"; ok "包管理器: uv（快，推荐）"
elif command -v pip3 >/dev/null 2>&1; then
  PKG="pip3"; warn "包管理器: pip3 —— 未检测到 uv，安装会明显更慢"
  warn "  建议先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"
else
  die "未找到 uv 或 pip3，请先安装其一"
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
if [ "$PKG" = "uv" ]; then
  uv pip install -r "$REPO_DIR/requirements.txt" --python "$VPY"
else
  "$VPY" -m pip install --upgrade pip
  "$VPY" -m pip install -r "$REPO_DIR/requirements.txt"
fi
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
  DL_SEC=$(( $(date +%s) - DL_START ))

  if [ $DL_RC -ne 0 ] || ! grep -q "MODEL_OK" <<< "$DL_OUT"; then
    c_red ""
    c_red "════════════════════════════════════════════════════════"
    c_red " 模型下载失败 —— 安装中止"
    c_red "════════════════════════════════════════════════════════"
    echo "$DL_OUT" | sed 's/^/   /'
    cat <<'EOF'

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
            https://hf-mirror.com/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_quantized.onnx
            https://hf-mirror.com/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
          然后：
            ./install.sh --offline-model /路径/model_quantized.onnx,/路径/tokenizer.json
     3) 已经手工放好模型：把模型放到
            ~/.cache/pangu/onnx/Xenova__all-MiniLM-L6-v2/
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
fi
fi  # INSTALL_SERVICE && !MODEL_ONLY

# ════════════════════════════════════════════════════════════
# 6. 安装 DSH 插件（可选）
# ════════════════════════════════════════════════════════════
if [ "$INSTALL_DSH_PLUGIN" = 1 ]; then
step "附加：安装 DSH 插件"
if [ -x "$REPO_DIR/scripts/install_dsh_plugin.sh" ]; then
  "$REPO_DIR/scripts/install_dsh_plugin.sh" "${DSH_PROFILE:-web}"
else
  warn "未找到 scripts/install_dsh_plugin.sh，跳过"
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
      MCP:  http://$HOST:$PORT/mcp

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

$(c_yellow '【接入 DSH】')
  1. ./install.sh --dsh-plugin      （或 scripts/install_dsh_plugin.sh）
  2. 重启 DSH
  3. DSH 设置 →「盘古记忆系统」填 LLM 提供商与 API Key，点「测试连接」

$(c_yellow '【配置】')
  数据目录: $PANGU_HOME        （config.json 权限 600）
  LLM 密钥: $PANGU_HOME/.llm_api_key  （不写入 config.json，重启不丢）
  环境变量: PANGU_HOST / PANGU_PORT / PANGU_LOG_LEVEL / PANGU_ONNX_CACHE_DIR
EOF
