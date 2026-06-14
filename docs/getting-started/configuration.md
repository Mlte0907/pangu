# 配置

盘古支持三种配置方式，按优先级：

1. 环境变量（`PANGU_*` 前缀）
2. `.env` 文件
3. 命令行参数

## 环境变量

```bash
# 基础
export PANGU_HOST=0.0.0.0
export PANGU_PORT=19528
export PANGU_API_KEY=your-secret-key

# LLM
export PANGU_LLM_PROVIDER=openai
export PANGU_LLM_MODEL=gpt-4o-mini
export PANGU_LLM_API_KEY=sk-xxxxx

# 嵌入
export PANGU_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
export PANGU_EMBEDDING_DIM=384

# 衰减
export PANGU_DECAY_BASE=0.95
export PANGU_DECAY_FLOOR=0.15
```

## .env 文件

创建 `.env`：

```env
PANGU_HOST=0.0.0.0
PANGU_PORT=19528
PANGU_LLM_PROVIDER=openai
PANGU_LLM_API_KEY=sk-xxxxx
PANGU_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## 完整配置项

### 服务
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_HOST` | `0.0.0.0` | API 监听地址 |
| `PANGU_PORT` | `19528` | API 端口 |
| `PANGU_WEB_HOST` | `127.0.0.1` | Web 监听地址 |
| `PANGU_WEB_PORT` | `8866` | Web 端口 |
| `PANGU_API_KEY` | (空) | API 鉴权密钥 |

### LLM
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_LLM_PROVIDER` | `openai` | 提供商 |
| `PANGU_LLM_MODEL` | `gpt-4o` | 模型名 |
| `PANGU_LLM_API_KEY` | (空) | API 密钥 |
| `PANGU_LLM_BASE_URL` | (空) | 自定义网关 |
| `PANGU_LLM_MAX_RETRIES` | `3` | 最大重试 |
| `PANGU_LLM_FALLBACK_MODELS` | `[]` | 回退模型列表 |

### 嵌入
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | 模型 |
| `PANGU_EMBEDDING_DIM` | `384` | 维度 |
| `PANGU_EMBED_CACHE_MAX` | `256` | 缓存条目 |

### 衰减
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_DECAY_BASE` | `0.95` | 基础衰减率 |
| `PANGU_DECAY_FLOOR` | `0.15` | 衰减下限 |
| `PANGU_NIGHT_DECAY_FACTOR` | `0.5` | 夜间加速 |
| `PANGU_TOUCH_BOOST_SHORT` | `1.35` | 短时访问加成 |
| `PANGU_TOUCH_BOOST_LONG` | `1.06` | 长时访问加成 |

### 工作记忆
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_WM_CAPACITY` | `40` | 槽位容量（Miller 7±2 × 3） |
| `PANGU_WM_CAPACITY_ADAPTIVE` | `True` | 动态调整 |

### 监控
| 项 | 默认 | 说明 |
|:---|:---|:---|
| `PANGU_PROMETHEUS_ENABLED` | `True` | 启用 Prometheus |
| `PANGU_METRICS_PATH` | `/metrics` | 指标端点 |
| `PANGU_HEALTH_PATH` | `/health` | 健康检查端点 |

## 热更新

通过 MCP 工具动态修改配置：

```python
# 远程更新
pangu_config_set(key="decay_base", value=0.9)
pangu_config_reload()
```
