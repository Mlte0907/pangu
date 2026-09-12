# 安装

## 系统要求

- **Python >= 3.11**（`pyproject.toml` 的 `requires-python`；3.10 及以下无法安装）
- 操作系统：Linux / macOS / Windows
- 内存：至少 512 MB
- 磁盘：至少 1 GB（含 ONNX 模型与向量索引）

## 方式 1：一键脚本（推荐）

```bash
git clone https://github.com/Mlte0907/pangu.git
cd pangu
./install.sh
```

脚本会依次完成：环境检查 → 建 venv → 装依赖 → **预下载 ONNX 模型** →
初始化数据目录 → 安装 systemd 用户服务（监听 **19529**）。

常用参数：

```bash
./install.sh --no-service     # 不装 systemd 服务
./install.sh --model-only     # 仅预下载 ONNX 模型（修复嵌入降级）
./install.sh --port 19529     # 自定义端口
./install.sh --help           # 全部参数
```

> 首次安装（冷缓存）依赖下载约需 **8 分钟**（56 个包 / 223 MB），
> 其中 `onnxruntime` + `numpy` 占约 110 MB。这不是卡死，请勿中断。

## 方式 2：从源码安装

```bash
git clone https://github.com/Mlte0907/pangu.git
cd pangu
python -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

> ⚠ **本包未发布到 PyPI**，`pip install pangu` 会装到**同名的其它项目**，请勿使用。

## 方式 3：Docker

```bash
docker pull ghcr.io/mlte0907/pangu:latest
docker run -d -p 19529:19529 ghcr.io/mlte0907/pangu:latest
```

> ⚠ 镜像内的 `Dockerfile` 默认 `CMD` 是 `pangu serve`（Web UI，端口 **19528/8866**），
> **不含 `/mcp` 端点**。要接入 MCP 客户端，请用仓库的 `docker-compose.yml`
> （已配置 19529），或覆盖启动命令：
>
> ```bash
> docker run -d -p 19529:19529 ghcr.io/mlte0907/pangu:latest \
>   python -m pangu serve --api --host 0.0.0.0 --port 19529
> ```

## 验证安装

```bash
.venv/bin/python -c "import pangu; print(pangu.__version__)"
.venv/bin/pangu --help

# 服务健康（含嵌入后端状态）
curl -s http://127.0.0.1:19529/health
```

`/health` 返回 `"status":"degraded"` 时说明嵌入后端已降级为 hash 向量
（检索结果没有语义能力）。修复见 README 的「检索结果不对劲？」。

## 可选依赖

```bash
# 性能基准
uv pip install pytest-benchmark

# 高级 LLM SDK
uv pip install openai anthropic langchain

# 文档工具
uv pip install mkdocs mkdocs-material mkdocstrings[python]
```

## 下一步

- [配置](configuration.md)
- [第一个记忆](first-memory.md)
