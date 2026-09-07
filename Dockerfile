# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────────────────────
# 盘古 — 多阶段 Dockerfile
# ==============================================================
# 阶段：
#   builder     — 编译依赖到 /wheels（一次性）
#   runtime     — 最小化运行时（默认 ~350MB）
#   runtime-slim — Alpine 超小镜像（~180MB，不含 GPU/CPU 优化）
#   dev         — 开发镜像（含测试/lint/构建工具）
#   docs        — mkdocs 构建环境（仅构建文档）
#
# 构建示例：
#   # 默认（runtime，最常见）
#   docker buildx build --platform linux/amd64,linux/arm64 -t pangu:3.0.0 .
#
#   # Alpine 小镜像
#   docker buildx build --target runtime-slim -t pangu:slim .
#
#   # 开发镜像（含 pytest/ruff/bandit）
#   docker buildx build --target dev -t pangu:dev .
#
#   # 仅构建文档
#   docker buildx build --target docs -o out=./site .
# ──────────────────────────────────────────────────────────────

ARG PYTHON_VERSION=3.12
ARG UID=1000
ARG GID=1000

# ==============================================================
# 阶段 0：通用基础镜像（多架构）
# ==============================================================
FROM --platform=$BUILDPLATFORM python:${PYTHON_VERSION}-slim AS base

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 一次性安装系统依赖（层缓存友好）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
        && rm -rf /var/lib/apt/lists/* \
        && apt-get clean

# ==============================================================
# 阶段 1：依赖构建
# ==============================================================
FROM base AS builder

ARG TARGETPLATFORM
ARG BUILDPLATFORM
RUN echo "🐍 Building on $BUILDPLATFORM for $TARGETPLATFORM"

# 编译工具（构建期需要，运行期不需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 先复制依赖清单，最大化层缓存
COPY requirements.txt requirements-dev.txt* ./

# 升级 pip + 准备 wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip wheel setuptools

# 编译所有 wheel 到 /wheels（含可选 ONNX 等）
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r requirements.txt

# ==============================================================
# 阶段 2：运行时（默认目标）
# ==============================================================
FROM base AS runtime

ARG VERSION=0.1.0
ARG BUILD_DATE
ARG VCS_REF
ARG TARGETARCH

# OCI 标准元数据
LABEL org.opencontainers.image.title="盘古" \
      org.opencontainers.image.description="LMM+Wiki 超智能记忆系统" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.architecture="${TARGETARCH}" \
      org.opencontainers.image.source="https://github.com/xiaoxin/pangu" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Pangu Team" \
      maintainer="xiaoxin"

# 创建非 root 用户
RUN groupadd --system --gid ${GID:-1000} pangu \
    && useradd --system --uid ${UID:-1000} --gid pangu --create-home pangu

# 从 builder 复制 wheels 并安装
COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels pangu \
    && rm -rf /wheels

# 验证最终镜像的架构
RUN python -c "import platform; print(f'✅ Running on {platform.machine()} ({platform.system()})')"

WORKDIR /app

# 复制应用代码
COPY --chown=pangu:pangu pangu/ ./pangu/
COPY --chown=pangu:pangu pyproject.toml setup.py README.md LICENSE ./

# 数据目录
RUN mkdir -p /data/palace /data/wiki /data/identity /data/backup /data/logs \
    && chown -R pangu:pangu /data /app

USER pangu

# 暴露端口（盘古主服务 + 旧版 Web 兼容）
EXPOSE 19528 8866

# 环境变量
ENV PANGU_BASE_DIR=/data \
    PANGU_PALACE_PATH=/data/palace \
    PANGU_WIKI_PATH=/data/wiki \
    PANGU_IDENTITY_PATH=/data/identity \
    PANGU_BACKUP_DIR=/data/backup \
    PANGU_LOG_DIR=/data/logs \
    PANGU_HOST=0.0.0.0 \
    PANGU_PORT=19528 \
    PANGU_WEB_HOST=0.0.0.0 \
    PANGU_WEB_PORT=8866

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:19528/health || exit 1

# tini 收僵尸进程
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "pangu", "serve", "--host", "0.0.0.0", "--port", "19528"]

# ==============================================================
# 阶段 2b：Alpine 超小镜像（不含 ONNX 优化）
# ==============================================================
FROM python:${PYTHON_VERSION}-alpine AS runtime-slim

RUN apk add --no-cache \
        ca-certificates \
        curl \
        tini \
        && addgroup -S -g ${GID:-1000} pangu \
        && adduser -S -u ${UID:-1000} -G pangu pangu

# 复制 wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels pangu \
    && rm -rf /wheels

# 需要在 Alpine 上重编译 numpy 等 C 扩展
RUN apk add --no-cache --virtual .pangu-run-deps \
        libstdc++ libgomp \
    && rm -rf /var/cache/apk/*

WORKDIR /app
COPY --chown=pangu:pangu pangu/ ./pangu/
COPY --chown=pangu:pangu pyproject.toml setup.py README.md LICENSE ./

RUN mkdir -p /data/palace /data/wiki /data/identity /data/backup /data/logs \
    && chown -R pangu:pangu /data /app

USER pangu
EXPOSE 19528

ENV PANGU_BASE_DIR=/data \
    PANGU_HOST=0.0.0.0 \
    PANGU_PORT=19528

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:19528/health || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "-m", "pangu", "serve", "--host", "0.0.0.0", "--port", "19528"]

# ==============================================================
# 阶段 3：开发镜像（含测试/lint/构建工具）
# ==============================================================
FROM builder AS dev

# 复制 dev 依赖
COPY requirements-dev.txt* ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r requirements-dev.txt 2>/dev/null || true

# 安装 dev 工具链
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels \
        pytest \
        pytest-asyncio \
        pytest-cov \
        ruff \
        bandit \
        pip-audit \
        mkdocs \
        mkdocs-material \
    && rm -rf /wheels

# 安装 dev 包
RUN pip install --no-cache-dir -e .

WORKDIR /app

# 暴露调试端口（可选）
EXPOSE 19528 5678

# 默认进入交互 shell
CMD ["/bin/bash"]

# ==============================================================
# 阶段 4：文档构建（mkdocs）
# ==============================================================
FROM builder AS docs

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir mkdocs mkdocs-material

WORKDIR /docs
COPY mkdocs.yml ./
COPY docs/ ./docs/

# 构建静态站点到 /site（CI 用）
RUN mkdocs build --strict

# 运行时：使用 nginx 提供静态文件
FROM nginx:1.27-alpine AS docs-serve
COPY --from=docs /docs/site/ /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
