# 配置参考

所有配置通过环境变量注入，**前缀 `PANGU_`**。

## 路径

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_BASE_DIR` | `~/.pangu` | 数据根目录 |
| `PANGU_PALACE_PATH` | | 宫殿结构路径 |
| `PANGU_DB_PATH` | `.` | 数据库目录 |
| `PANGU_BACKUP_DIR` | `.` | 备份目录 |

## 服务

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_HOST` | `0.0.0.0` | 监听地址（生产建议 `127.0.0.1` + 反代）|
| `PANGU_PORT` | `19528` | 端口 |
| `PANGU_WEB_HOST` | `127.0.0.1` | 仪表盘 |
| `PANGU_WEB_PORT` | `8866` |  |
| **`PANGU_API_KEY`** | `""` | **空 = 禁用鉴权；设置后强制 X-API-Key 头**|

## LLM

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `ollama` / `fuxi` |
| `PANGU_LLM_MODEL` | `gpt-4o` | 主模型 |
| `PANGU_LLM_API_KEY` | `""` | 必需 |
| `PANGU_LLM_BASE_URL` | `""` | 留空走官方；自部署指向服务地址 |
| `PANGU_LLM_MAX_RETRIES` | `3` | 失败重试次数 |
| `PANGU_LLM_RETRY_DELAY` | `2.0` | 秒 |

## LLM 响应缓存

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_LLM_CACHE_ENABLED` | `true` | 总开关 |
| `PANGU_LLM_CACHE_MAX` | `128` | 内存 LRU 条数 |
| `PANGU_LLM_CACHE_PERSIST` | `true` | 持久化到 SQLite |
| `PANGU_LLM_CACHE_TTL_DAYS` | `7` | 过期时间 |
| `PANGU_LLM_CACHE_MAX_DISK_MB` | `100` | 磁盘上限 |
| `PANGU_LLM_CACHE_WARMUP_ON_START` | `false` | 启动时预热 |
| `PANGU_LLM_CACHE_VACUUM_ON_START` | `false` | 启动时 VACUUM |

## 嵌入

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | |
| `PANGU_EMBEDDING_DIM` | `384` | |
| `PANGU_EMBED_CACHE_MAX` | `256` | LRU |
| **`PANGU_EMBED_API_URL`** | `""` | **外部嵌入 API**（Ollama/vLLM） |
| `PANGU_EMBED_API_MODEL` | `""` | API 端的模型名 |
| `PANGU_EMBED_FAIL_THRESHOLD` | `3` | 切到 ONNX 的失败次数 |

## ONNX 本地嵌入

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_ONNX_ENABLED` | `true` | 启用 ONNX 加速 |
| `PANGU_ONNX_MODEL_ID` | `Xenova/all-MiniLM-L6-v2` | HF 模型 ID |
| `PANGU_ONNX_QUANTIZED` | `true` | INT8 量化 |
| `PANGU_ONNX_MAX_LENGTH` | `128` | 序列长度 |
| `PANGU_ONNX_MIRROR_BASE` | `https://hf-mirror.com` | 国内镜像 |

## 记忆栈

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_L1_MAX_DRAWERS` | `15` | L1 摘要上限 |
| `PANGU_L1_MAX_CHARS` | `3200` | L1 总字符数 |
| `PANGU_L2_DEFAULT_RESULTS` | `10` | L2 默认返回数 |
| `PANGU_L3_DEFAULT_RESULTS` | `5` | L3 默认返回数 |
| `PANGU_DEFAULT_CONTEXT_BUDGET` | `1000` | 注入 Agent 的总 token 预算 |

## 衰减

| 变量 | 默认 |
|:---|:---|
| `PANGU_DECAY_BASE` | `0.95` |
| `PANGU_NIGHT_DECAY_FACTOR` | `0.5` |
| `PANGU_TOUCH_BOOST_SHORT` | `1.35` |
| `PANGU_TOUCH_BOOST_LONG` | `1.06` |
| `PANGU_DECAY_FLOOR` | `0.15` |

## 示例 .env

```bash
# ~/.pangu/.env 或 /etc/pangu.env
PANGU_API_KEY=4f8c2e91-6d3a-4a7f-b9e1-2c5d8e0a3b6f
PANGU_LLM_PROVIDER=fuxi
PANGU_LLM_API_KEY=jinlange-fuxi-2026
PANGU_LLM_BASE_URL=http://localhost:19528/anthropic
PANGU_LLM_MODEL=glm-5.1
PANGU_ONNX_ENABLED=true
PANGU_LLM_CACHE_WARMUP_ON_START=true
```
