# 安装

## 系统要求

- Python >= 3.10
- 操作系统：Linux / macOS / Windows
- 内存：至少 512MB
- 磁盘：至少 1GB（含向量索引）

## 方式 1: pip 安装（推荐）

```bash
pip install pangu
```

## 方式 2: 从源码安装

```bash
git clone https://github.com/xiaoxin/pangu.git
cd pangu
pip install -e .
```

## 方式 3: Docker

```bash
docker pull ghcr.io/xiaoxin/pangu:latest
docker run -d -p 19528:19528 ghcr.io/xiaoxin/pangu:latest
```

## 验证安装

```bash
python -c "import pangu; print(pangu.__version__)"
pangu --help
```

## 可选依赖

```bash
# 性能基准
pip install pytest-benchmark

# 高级 LLM SDK
pip install openai anthropic langchain

# 文档工具
pip install mkdocs mkdocs-material mkdocstrings[python]
```

## 下一步

- [配置](configuration.md)
- [第一个记忆](first-memory.md)
