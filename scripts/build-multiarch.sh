# 盘古 — Docker Buildx 多架构构建
# ====================================
# 使用方法：
#   1. 初始化 buildx：docker buildx create --use --name pangu-builder
#   2. 构建多架构：./scripts/build-multiarch.sh v0.1.0
#   3. 推送到镜像仓库：./scripts/build-multiarch.sh v0.1.0 --push

#!/usr/bin/env bash
set -euo pipefail

# ── 参数 ──
VERSION=${1:-"dev"}
PUSH=${2:-""}
REGISTRY=${REGISTRY:-"ghcr.io/mlte0907"}
IMAGE_NAME=${IMAGE_NAME:-"pangu"}
PLATFORMS=${PLATFORMS:-"linux/amd64,linux/arm64"}
BUILDER_NAME=${BUILDER_NAME:-"pangu-builder"}

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION}"

# ── 颜色输出 ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[BUILD]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 检查依赖 ──
if ! command -v docker &> /dev/null; then
    err "docker 未安装"
    exit 1
fi

# ── 创建 buildx builder ──
if ! docker buildx inspect "${BUILDER_NAME}" &> /dev/null; then
    log "创建 buildx builder: ${BUILDER_NAME}"
    docker buildx create --name "${BUILDER_NAME}" --driver docker-container --bootstrap
fi

docker buildx use "${BUILDER_NAME}"

# ── 构建参数 ──
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VCS_REF=$(git rev-short HEAD 2>/dev/null || echo "unknown")

BUILD_ARGS=(
    --build-arg "VERSION=${VERSION}"
    --build-arg "BUILD_DATE=${BUILD_DATE}"
    --build-arg "VCS_REF=${VCS_REF}"
    --platform "${PLATFORMS}"
    --file Dockerfile
    --tag "${FULL_IMAGE}"
    --tag "${REGISTRY}/${IMAGE_NAME}:latest"
    --label "org.opencontainers.image.version=${VERSION}"
    --label "org.opencontainers.image.created=${BUILD_DATE}"
    --label "org.opencontainers.image.revision=${VCS_REF}"
)

# ── 缓存配置 ──
CACHE_FLAGS=(
    --cache-from "type=registry,ref=${REGISTRY}/${IMAGE_NAME}:buildcache"
    --cache-to "type=registry,ref=${REGISTRY}/${IMAGE_NAME}:buildcache,mode=max"
)

# ── 推送/加载 ──
if [[ "${PUSH}" == "--push" ]]; then
    log "构建并推送: ${FULL_IMAGE} (${PLATFORMS})"
    docker buildx build "${BUILD_ARGS[@]}" "${CACHE_FLAGS[@]}" --push .
    log "✓ 镜像已推送: ${FULL_IMAGE}"
elif [[ "${PUSH}" == "--load" ]]; then
    if [[ "${PLATFORMS}" == *","* ]]; then
        err "load 模式仅支持单一架构"
        exit 1
    fi
    log "构建并加载到本地: ${FULL_IMAGE} (${PLATFORMS})"
    docker buildx build "${BUILD_ARGS[@]}" --load .
    log "✓ 镜像已加载: ${FULL_IMAGE}"
else
    log "仅构建（不推送/加载）: ${FULL_IMAGE} (${PLATFORMS})"
    docker buildx build "${BUILD_ARGS[@]}" "${CACHE_FLAGS[@]}" .
    log "✓ 构建完成"
fi

# ── 打印摘要 ──
log "═══════════════════════════════════════════════"
log "  镜像: ${FULL_IMAGE}"
log "  架构: ${PLATFORMS}"
log "  版本: ${VERSION}"
log "═══════════════════════════════════════════════"
