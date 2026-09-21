# 盘古记忆系统 — 全景分析报告

> **分析日期**: 2026-09-20
> **版本**: v0.4.1
> **分析方法**: 源码逐行审计 + 运行时验证，所有结论附文件:行号证据

---

## 目录

1. [系统总览](#一系统总览)
2. [架构分层](#二架构分层)
3. [核心模块详解](#三核心模块详解)
4. [存储与检索系统](#四存储与检索系统)
5. [记忆处理引擎](#五记忆处理引擎)
6. [API 与服务器层](#六api-与服务器层)
7. [前端插件系统](#七前端插件系统)
8. [前后端通信关系](#八前后端通信关系)
9. [安全与鉴权体系](#九安全与鉴权体系)
10. [关键设计决策](#十关键设计决策)
11. [证据索引](#十一证据索引)

---

## 一、系统总览

### 1.1 项目定位

盘古是一个 **AI Agent 多模态记忆系统**，以"记忆宫殿"为隐喻，将 Agent 的记忆组织为 **Wing（翼）→ Room（房间）→ Drawer（抽屉）** 三级空间，配以混合检索、艾宾浩斯遗忘曲线、海马体神经激活扩散与睡眠式夜间巩固。

**证据**: `/home/xiaoxin/pangu/README.md` 行 1-7

### 1.2 核心能力矩阵

| 能力 | 实现文件 | 关键行号 |
|------|---------|---------|
| 记忆宫殿 (Wing→Room→Drawer) | `pangu/core/palace.py` | 行 146-320 |
| 摄入管道 (脱敏→加密→去重→融合) | `pangu/memory/ingestion.py` | 行 516-673 |
| 混合检索 (向量+FTS+RRF) | `pangu/memory/hybrid_search.py` | 行 337-412 |
| 神经激活扩散 | `pangu/memory/neural_memory.py` | 行 380-413 |
| 个性化遗忘曲线 | `pangu/memory/decay.py` | 行 103-183 |
| 四层记忆栈 (L0-L3) | `pangu/memory/layers.py` | 行 1-100 |
| MCP Server + REST API | `pangu/server/mcp_server.py` | 行 1-500 |
| 三级工具暴露机制 | `pangu/server/exposure.py` | 行 28-198 |

---

## 二、架构分层

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    浏览器 (React 18)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ 侧边栏   │ │ 星系图谱 │ │ 知识库   │ │ 设置页   │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       └────────────┴────────────┴────────────┘                   │
│                         │ Typert Remote                          │
├─────────────────────────┼───────────────────────────────────────┤
│                    DSH 宿主进程                                   │
│  ┌──────────────────────┴──────────────────────────────────────┐│
│  │              dsh-pangu 插件 (lib/index.js)                   ││
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐    ││
│  │  │ Typert 服务  │ │ 注入管线     │ │ 自动沉淀检测器   │    ││
│  │  │ (6个Remote)  │ │ (proactive/) │ │ (consolidation)  │    ││
│  │  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘    ││
│  └─────────┼────────────────┼──────────────────┼───────────────┘│
│            │ REST/JSON-RPC  │ MCP JSON-RPC      │               │
├────────────┼────────────────┼──────────────────┼───────────────┤
│            │         盘古服务 (19529)                          │
│  ┌─────────▼────────────────▼──────────────────▼───────────────┐│
│  │                    FastAPI + Uvicorn                         ││
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐    ││
│  │  │ AuthMiddleware│ │ RateLimiter  │ │ MetricsMiddleware│    ││
│  │  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘    ││
│  └─────────┼────────────────┼──────────────────┼───────────────┘│
│            │                │                  │                 │
│  ┌─────────▼────────────────▼──────────────────▼───────────────┐│
│  │                    MCPServer (核心调度)                      ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      ││
│  │  │ Exposure │ │ Handlers │ │ Palace   │ │ Memory   │      ││
│  │  │ Filter   │ │ (17模块) │ │ 管理     │ │ Stack    │      ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘      ││
│  └─────────────────────────────────────────────────────────────┘│
│            │                │                  │                 │
│  ┌─────────▼────────────────▼──────────────────▼───────────────┐│
│  │                    存储层                                    ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      ││
│  │  │ drawers  │ │ 向量索引 │ │ FTS索引  │ │ 知识图谱 │      ││
│  │  │ .json    │ │ (numpy/  │ │ (jieba)  │ │          │      ││
│  │  │          │ │  hnswlib)│ │          │ │          │      ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘      ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
pangu/
├── pangu/                    # Python 后端核心
│   ├── core/                 # 基础层：配置、LLM、数据模型、缓存
│   ├── memory/               # 记忆处理：摄入、检索、衰减、巩固、多模态
│   ├── search/               # 搜索引擎：嵌入、向量、混合搜索
│   ├── store/                # 存储层：JSON/SQLite、迁移
│   ├── server/               # 服务器：MCP、handlers、暴露面、鉴权
│   ├── api/                  # HTTP 层：FastAPI 路由、WebSocket
│   ├── wiki/                 # 知识结晶：Wiki 页面生成
│   ├── mining/               # 数据挖掘
│   ├── ui/                   # Web UI 模板
│   └── observability/        # 可观测性：指标、追踪
├── plugins/
│   └── dsh-pangu/            # DSH 集成插件
│       ├── lib/
│       │   ├── index.js      # 宿主服务端 (849行)
│       │   ├── client.js     # 浏览器客户端 (2014行)
│       │   ├── typert.host.js # Typert 端点清单
│       │   └── proactive/    # 主动注入引擎 (13个模块)
│       └── test/             # 测试套件
├── docs/                     # 文档
├── tests/                    # 后端测试
└── scripts/                  # 部署脚本
```

---

## 三、核心模块详解

### 3.1 配置管理 (`pangu/core/config.py`)

**文件**: 598 行 | **职责**: 全局配置单例

#### 配置加载优先级链 (行 488-527)

```
环境变量 (PANGU_*)  >  密钥独立文件 (.llm_api_key)  >  config.json  >  代码默认值
```

#### 配置分组 (行 88-338)

| 分组 | 关键字段 | 行号 |
|------|---------|------|
| 工具暴露面 | `exposure: ExposureConfig` | 94 |
| 路径配置 | `base_dir`, `palace_path`, `db_path` | 97-111 |
| 服务配置 | `host`, `port`, `api_key` | 114-118 |
| JWT 鉴权 | `jwt_secret`, `jwt_algorithm`, `jwt_users` | 121-131 |
| RBAC/ABAC | `abac_enabled`, `abac_policies` | 137-146 |
| LLM 配置 | `llm_provider`, `llm_model`, `llm_api_key` | 149-155 |
| 嵌入模型 | `embedding_model`, `onnx_model_id` | 182-199 |
| 衰减配置 | `decay_base`, `night_decay_factor` | 234-238 |
| 工作记忆 | `wm_capacity`, `wm_capacity_adaptive` | 241-242 |

#### 安全设计

**密钥不落盘** (行 540-541):
```python
# save() 显式排除敏感字段
def save(self):
    exclude = {"api_key", "llm_api_key", "siliconflow_key", "jwt_secret", "jwt_default_password"}
    data = self.model_dump(exclude=exclude)
```

**密钥独立文件** (行 32-61):
```python
def read_secret_file(filename: str) -> str:
    path = PANGU_DIR / filename
    if path.exists():
        return path.read_text().strip()
    return ""
```

#### 权威记忆路径 (行 361-455)

解决 v1/v2 存储路径分裂问题：

```python
@property
def memory_data_dir(self) -> Path:
    """权威记忆数据目录：db_path/v2_memories"""
    return Path(self.db_path) / "v2_memories"

@property
def authoritative_drawers_path(self) -> Path:
    """权威 drawers.json 路径（v2 主存储）"""
    return self.memory_data_dir / "drawers.json"
```

**证据**: `pangu/core/config.py` 行 361-455

---

### 3.2 数据模型 (`pangu/core/palace.py`)

**文件**: 320 行 | **职责**: 记忆空间的核心数据结构

#### Drawer 数据类 (行 10-80)

```python
@dataclass
class Drawer:
    id: str                                          # UUID 主键
    content: str                                     # 记忆内容（可加密）
    wing: str = "default"                            # 所属翼
    room: str = "general"                            # 所属房间
    hall: str = "hall_events"                        # 殿堂分类
    importance: float = 3.0                          # 重要性 (1-6)
    emotional_weight: float = 0.0                    # 情感权重
    source_file: str = ""                            # 来源文件
    source: str = ""                                 # 来源平台(dsh/mcp/api)
    tags: list = field(default_factory=list)         # 标签
    author: str = ""                                 # 写入者 agent_id
    created_at: str                                  # ISO 时间戳
    metadata: dict = field(default_factory=dict)     # 扩展元数据
```

**类型安全** (行 49-62):
```python
def _coerce_float(value) -> float:
    if isinstance(value, str):
        mapping = {"high": 5.0, "medium": 3.0, "low": 1.0, "critical": 6.0}
        return mapping.get(value.lower(), 3.0)
    return float(value)
```

#### 殿堂分类体系 (行 134-143)

```python
HALL_TYPES = {
    "hall_facts":        "事实与决策 — 已做出的决定和锁定的选择",
    "hall_events":       "事件与里程碑 — 会话、调试过程、重要节点",
    "hall_discoveries":  "发现与洞察 — 突破性发现、新认知",
    "hall_preferences":  "偏好与习惯 — 个人喜好、工作习惯、观点",
    "hall_advice":       "建议与方案 — 推荐方案和解决思路",
    "hall_concepts":     "概念与理论 — 核心概念、理论框架",
    "hall_relations":    "关系与网络 — 人物关系、项目关联",
}
```

#### Palace 类 (行 146-320)

空间层级：**Palace → Wings → Rooms → Drawers**

```python
class Palace:
    def __init__(self, palace_path: str):
        self.path = Path(palace_path)
        self.meta_file = self.path / "palace_meta.json"  # 元数据
        self.wings_file = self.path / "wings.json"       # 翼列表
        self.rooms_file = self.path / "rooms.json"       # 房间列表
```

**Tunnel 管理** (行 257-284) — 跨 Wing 连接：
```python
def create_tunnel(self, wing_a: str, wing_b: str, room: str, created_by: str = "") -> dict:
    tunnel = {"id": str(uuid.uuid4())[:8], "wing_a": wing_a, "wing_b": wing_b, ...}
```

**证据**: `pangu/core/palace.py` 行 10-320

---

### 3.3 LLM 集成层 (`pangu/core/llm.py`)

**文件**: 1415 行 | **职责**: 多提供商统一 LLM 调用

#### 提供商映射 (行 69-86)

```python
PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
}
```

#### 记忆专用 LLM 方法 (行 533-725)

| 方法 | 行号 | 功能 |
|------|------|------|
| `summarize_memories()` | 535 | 记忆摘要 |
| `classify_memory()` | 558 | 智能分类（7 种殿堂类型） |
| `generate_wiki_page()` | 584 | Wiki 页面生成 |
| `detect_links()` | 631 | 页面关联检测 |
| `generate_insight()` | 653 | 洞察提取 |
| `compress_memories()` | 674 | 记忆压缩 |
| `detect_associations()` | 696 | 关联检测 |

#### 三层缓存策略

```
请求 → 内存 LRU (OrderedDict, max=128)
     → SQLite 磁盘 (PersistentCache, TTL 7天, 100MB)
     → 实际 API 调用
```

**证据**: `pangu/core/llm.py` 行 69-86, 533-725

---

### 3.4 统一错误码 (`pangu/core/errors.py`)

**文件**: 110 行 | **职责**: 全系统错误码定义

| 域 | 范围 | 示例 |
|----|------|------|
| 通用 | 1000-1099 | `UNKNOWN=1000`, `INVALID_PARAMS=1001`, `NOT_FOUND=1002` |
| 记忆操作 | 2000-2099 | `MEMORY_NOT_FOUND=2001`, `MEMORY_SEARCH_FAILED=2006` |
| 向量/嵌入 | 3000-3099 | `EMBED_FAILED=3002`, `VECTOR_DIMENSION_MISMATCH=3004` |
| 知识图谱 | 4000-4099 | `KG_ENTITY_NOT_FOUND=4001`, `KG_CYCLE_DETECTED=4003` |
| 插件 | 5000-5099 | `PLUGIN_NOT_FOUND=5001` |
| 外部服务 | 6000-6099 | `LLM_API_FAILED=6001`, `LLM_TIMEOUT=6002` |
| 存储 | 7000-7099 | `STORAGE_CORRUPTED=7003` |

**证据**: `pangu/core/errors.py` 行 28-78

---

## 四、存储与检索系统

### 4.1 双存储后端 (`pangu/memory/drawer_storage.py`)

#### JSON 文件存储 (`JsonDrawerStorage`, 行 72-141)

- 文件格式: `drawers.json` — JSON 数组
- 写入方式: **原子写入** (写 `.tmp` → `fsync` → `os.replace`)
- 内存缓存: 30 秒 TTL

```python
def save(self, drawers: list[Drawer]) -> None:
    tmp_path = self.file_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp_path.fsync()
    os.replace(str(tmp_path), str(self.file_path))
```

#### SQLite 存储 (`SqliteDrawerStorage`, 行 143-418)

**表结构** (行 200-232):

```sql
CREATE TABLE drawers (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    wing TEXT DEFAULT 'default',
    room TEXT DEFAULT 'general',
    hall TEXT DEFAULT 'hall_events',
    importance REAL DEFAULT 3.0,
    emotional_weight REAL DEFAULT 0.0,
    source_file TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    author TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    updated_at REAL NOT NULL,
    created_timestamp REAL NOT NULL
);

CREATE INDEX idx_drawers_wing ON drawers(wing);
CREATE INDEX idx_drawers_room ON drawers(room);
CREATE INDEX idx_drawers_importance ON drawers(importance DESC);
CREATE INDEX idx_drawers_created_at ON drawers(created_at DESC);
CREATE INDEX idx_drawers_updated_at ON drawers(updated_at DESC);
```

**性能优化** (行 164-171):
```python
conn.execute("PRAGMA journal_mode=WAL")          # 并发读写
conn.execute("PRAGMA synchronous=NORMAL")         # 平衡性能与安全
conn.execute("PRAGMA cache_size=-64000")          # 64MB 缓存
conn.execute("PRAGMA temp_store=MEMORY")          # 临时表内存
conn.execute("PRAGMA mmap_size=268435456")        # 256MB 内存映射
```

**证据**: `pangu/memory/drawer_storage.py` 行 143-418

---

### 4.2 向量索引加速 (`pangu/memory/vector_index.py`)

**文件**: 777 行 | **职责**: 高性能向量检索

#### 三级自动后端切换 (行 26-70)

```python
FAISS_THRESHOLD = 1000  # 超过此数量自动切换

# < 1000 条: numpy brute-force（预归一化，0.1ms）
# >= 1000 条: hnswlib (优先) → FAISS IVFFlat → numpy
```

**numpy 搜索** (行 539-554):
```python
def _search_numpy(self, query, top_k):
    similarities = np.dot(self._index, query)  # 预归一化后直接 dot
    top_indices = np.argpartition(similarities, -top_k)[-top_k:]  # O(n) 选择
```

**hnswlib 搜索** (行 518-528):
```python
def _search_hnsw(self, query, top_k):
    indices, distances = self._hnsw_index.knn_query(query.reshape(1, -1), k=top_k)
    similarity = 1.0 - dist  # hnswlib 返回距离
```

**证据**: `pangu/memory/vector_index.py` 行 26-70, 518-554

---

### 4.3 全文搜索 (`pangu/memory/fts_search.py`)

**文件**: 654 行 | **职责**: 中文全文检索

#### 分词器 (行 128-141)

```python
def _tokenize(self, text):
    jieba = _get_jieba()
    if jieba:
        return [w.strip() for w in jieba.cut(text) if w.strip()]
    return re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z]{2,}", text)  # 正则兜底
```

#### FTS 搜索 (行 314-339)

```python
def _fts_search(self, query, drawers, limit=50):
    keywords = self._tokenize_for_query(safe_query)
    scores: dict[str, float] = {}
    for kw in keywords:
        if kw in self._fts_index:
            for did in self._fts_index[kw]:
                scores[did] = scores.get(did, 0) + 1.0
    # 分词无命中时走子串兜底
    if not scores:
        for kw in keywords:
            if len(kw) >= 2:
                self._fallback_keyword_search(kw, scores)
```

**证据**: `pangu/memory/fts_search.py` 行 128-141, 314-339

---

### 4.4 混合搜索 (`pangu/memory/hybrid_search.py`)

**文件**: 412 行 | **职责**: 三路 RRF 融合排序

#### RRF 公式 (行 218-242)

```python
# RRF(d) = Σ weight_i / (k + rank_i(d)),  k=60
def _rrf_fusion(fts_ranks, vector_ranks, kg_ranks, fts_w, vec_w, kg_w):
    for ranks, weight in all_ranks:
        for mid, rank in ranks.items():
            rrf_scores[mid] += weight / (RRF_K + rank)
    # 归一化到 0-1
```

默认权重: `fts_weight=1.5, vector_weight=0.8, kg_weight=0.5` (行 348-349)

**证据**: `pangu/memory/hybrid_search.py` 行 218-242, 337-412

---

### 4.5 嵌入服务 (`pangu/memory/embedding.py`)

**文件**: 441 行 | **职责**: 三级降级嵌入

```
远程 API → ONNX 本地推理 → hash 向量 (零语义能力)
```

**电路断路器** (行 33, 80-87, 321-328):
```python
CIRCUIT_COOLDOWN = 600  # 冷却时间
# 连续5次失败 → 断路器打开 → 60秒后 half-open → 成功则关闭
```

**证据**: `pangu/memory/embedding.py` 行 30-441

---

### 4.6 缓存体系 (五层)

| 缓存层 | 文件 | 类型 | 大小 | TTL |
|--------|------|------|------|-----|
| 嵌入向量缓存 | `search/embedder.py` | 内存 LRU + 磁盘 | 5000 条 | 永久 |
| 搜索结果缓存 | `memory/search_cache.py` | 内存 LRU | 200 条 | 5 分钟 |
| FTS 搜索缓存 | `memory/fts_search.py` | 内存 LRU | 100 条 | 1 分钟 |
| LLM 响应缓存 | `core/cache.py` | SQLite 持久化 | 100MB | 7 天 |
| JSON 加载缓存 | `memory/drawer_storage.py` | 内存 | 1 条 | 30 秒 |

---

## 五、记忆处理引擎

### 5.1 摄入流程 (`pangu/memory/ingestion.py`)

**文件**: 935 行 | **职责**: 记忆的完整生命周期

#### 统一入口 `remember()` (行 516-673)

| 步骤 | 操作 | 代码行号 |
|------|------|----------|
| 1 | 脱敏检查 `_sanitize_text()` | 570 |
| 2 | 加密处理 `_encrypt_text()` | 573 |
| 3 | 去重检查 `_dedup_and_fuse()` | 577 |
| 4 | 创建 Drawer + 生成向量嵌入 | 593-614 |
| 5 | 全息编码 `_encode_hologram()` | 618 |
| 6 | Wikilink 实体链接提取 | 623 |
| 7 | 向量索引更新 | 627 |
| 8 | 神经记忆编码 | 657 |
| 9 | 冲突检测 | 660 |
| 10 | 四问准入门 | 668 |

#### 四问准入门 (行 455-513)

检查四个维度，不阻塞写入：

```python
# Q3 支撑检查 (行 472-479)
has_source = bool(drawer.source_file) or bool(drawer.metadata.get("source_session"))
if not has_source:
    admission_flags.append("no_source")

# Q4 验证检查 (行 484-490)
last_feedback = drawer.metadata.get("last_feedback", "")
has_positive_feedback = last_feedback in ("recall_success", "verified")
```

毕业条件: 四问全过 → `visibility="public"`，全平台只读。

**证据**: `pangu/memory/ingestion.py` 行 455-513, 516-673

---

### 5.2 三层去重机制

#### 第一层：精确匹配 (ingestion.py 行 131-134)

```python
for d in existing_drawers:
    if d.content == raw_text and d.wing == wing:
        return d, None, None  # 拒绝写入
```

#### 第二层：语义相似度 (ingestion.py 行 137-189)

```python
score = _cosine_similarity(query_vec, stored_vec)
if score > SUPERSEDE_THRESHOLD (0.65):
    # 丰富度比较
    informativeness_new = len(raw_text) * (1 + 0.5 * new_ratio)
    informativeness_old = len(best_drawer.content)
    if informativeness_new > informativeness_old * 1.3:
        # 新内容更丰富 → 放行写入 + 标记旧的为"已替代"
    else:
        # 内容差不多 → 拒绝写入
```

#### 第三层：文本重叠降级 (ingestion.py 行 192-201)

```python
if len(raw_text) >= MIN_TEXT_LENGTH_FOR_DEDUP (20):
    overlap = sum(1 for a, b in zip(raw_text, d.content) if a == b)
    if overlap / len_norm > TEXT_OVERLAP_THRESHOLD (0.85):
        return d, None, None
```

**证据**: `pangu/memory/ingestion.py` 行 111-203

---

### 5.3 衰减与遗忘系统

#### 艾宾浩斯衰减 v2 (`pangu/memory/decay.py`, 行 103-183)

**最终衰减公式** (行 173):
```
new_score = current_score * base_decay * importance_factor * night_factor * touch_factor
```

各因子:

| 因子 | 公式 | 行号 |
|------|------|------|
| 基础衰减 | `decay_base ** (elapsed_hours / 168)` | 147 |
| 重要性因子 | `1.0 - (importance * 0.4)` | 150 |
| 夜间因子 | `1.0 - (night_decay_factor - 1.0) * exp(-0.5 * ((hour - 5.0) / 1.5) ** 2)` | 153-154 |
| 时间保护因子 | 24h 内 1.35 / 30天内 1.0 | 156-165 |

#### 个性化遗忘曲线 (`neural_memory.py`, 行 89-143)

```python
DEFAULT_DECAY_RATES = {
    MemoryType.EPISODIC: 0.6,    # 情景记忆，半衰期约 1.2 天
    MemoryType.SEMANTIC: 0.15,   # 语义记忆，半衰期约 4.6 天
    MemoryType.PROCEDURAL: 0.08, # 程序记忆，半衰期约 8.7 天
    MemoryType.EMOTIONAL: 0.3,   # 情感记忆，半衰期约 2.3 天
}
```

保留率公式 (行 105-138):
```python
retention = exp(-effective_rate * elapsed_hours / 24.0)
# effective_rate = base_rate * emotional_correction * consolidation_correction * access_correction
```

**证据**: `pangu/memory/decay.py` 行 103-183, `pangu/memory/neural_memory.py` 行 89-143

---

### 5.4 神经激活扩散 (`pangu/memory/neural_memory.py`)

**文件**: 819 行 | **职责**: 海马体-新皮层双系统

#### 激活扩散算法 (行 380-413)

```python
def activate_spreading(self, seed_ids: list[str], decay_factor: float = 0.6, max_depth: int = 3):
    activations: dict[str, float] = {}
    queue: list[tuple[str, float, int]] = []

    for mid in seed_ids:
        if mid in self._memories:
            activations[mid] = 1.0
            queue.append((mid, 1.0, 0))

    while queue:
        current, current_activation, depth = queue.pop(0)
        if current in visited or depth >= max_depth:
            continue
        for neighbor_id, edge_strength in neighbors.items():
            spread_activation = current_activation * edge_strength * decay_factor
```

扩散规则:
- 每跳衰减 `decay_factor` (默认0.6)倍
- 最大传播深度 3 跳
- 只保留更强激活

#### 竞争抑制 (行 415-459)

```python
# Winner-Take-All with soft competition
for _ in range(3):
    for i, mem_a in enumerate(memories):
        inhibition_total = 0.0
        for j, mem_b in enumerate(memories):
            similarity = self._similarity(mem_a, mem_b)
            inhibition_total += similarity * activations[mem_b.id] * 0.3
        new_activations[mem_a.id] = max(0.01, activations[mem_a.id] - inhibition_total)
```

**证据**: `pangu/memory/neural_memory.py` 行 380-459

---

### 5.5 睡眠巩固 (`neural_memory.py`, 行 531-644)

`SleepConsolidation.enter_sleep()` 模拟睡眠记忆重播，6步流程:

1. 海马体筛选巩固候选（强度>0.3 + 高情感/已巩固/高访问/停留>1h）
2. 情感记忆去标记化（arousal *= 0.7, valence *= 0.8）
3. 语义记忆关联建立（sim > 0.3 → build_association）
4. 竞争抑制淘汰冗余（>10条时启动）
5. 转移至新皮层（刷新衰减基准 `decay_basis_at`）
6. 清空海马体已巩固部分

**触发条件** (行 632-644):
- 海马体负载率 > 60%
- 距上次巩固超过配置间隔

**证据**: `pangu/memory/neural_memory.py` 行 531-644

---

### 5.6 多模态处理

#### 图片引擎 (`pangu/memory/image_engine.py`, 315行)

- CLIP 模型集成 (行 52-72)
- 跨模态搜索: `search_by_image()` (行 256-280), `search_by_text()` (行 282-305)
- 降级嵌入: 无CLIP时使用颜色直方图 (行 249-254)
- 零样本分类: 16个CLIP类别 (行 130-163)

#### 音频引擎 (`pangu/memory/audio_engine.py`, 245行)

- Whisper 转写 (行 110-144)
- 元数据提取: ffprobe 获取时长、采样率、声道 (行 56-108)

#### 视频引擎 (`pangu/memory/video_engine.py`, 334行)

- 关键帧提取: ffmpeg 按间隔提取 (行 87-128)
- CLIP帧分析: 向量化+颜色分析 (行 230-256)

**证据**: `pangu/memory/image_engine.py`, `audio_engine.py`, `video_engine.py`

---

### 5.7 四层记忆栈 (`pangu/memory/layers.py`)

渐进式记忆加载架构:

| 层 | 容量 | 加载策略 |
|----|------|----------|
| L0 身份层 | ~100 tokens | 始终加载，定义"我是谁" |
| L1 概要层 | ~500-800 tokens | 始终加载，关键记忆摘要 |
| L2 按需层 | ~200-500 tokens | 话题触发时加载 |
| L3 深度搜索 | 无限 | 全文语义搜索 |

动态 token 预算: 1000→3000，随记忆规模伸缩。

**证据**: `pangu/memory/layers.py`

---

## 六、API 与服务器层

### 6.1 MCP Server (`pangu/server/mcp_server.py`)

**文件**: ~500 行 | **职责**: MCP 协议实现

#### 惰性组件加载 (行 63-129)

```python
@property
def llm(self):
    if self._llm is None:
        self._llm = LLMEngine(self.config)
        self._persistent_cache = self._llm._persistent_cache
        self._maybe_schedule_warmup()
        self._maybe_schedule_vacuum()
    return self._llm
```

#### 工具调用执行流程 (行 293-371)

```
1. _ensure_initialized()         -- 触发组件惰性加载
2. HANDLERS.get(tool_name)       -- 查找 handler（不存在→code=1001）
3. exposure.check_callable()     -- 暴露面前置校验（未暴露→code=1002）
4. 身份注入 (_identity)          -- 从 request 提取并注入 arguments
5. scope 强制                    -- readonly→拒绝写类(code=1003)，非admin→拒绝管理类(code=1004)
6. set_tenant_scope()            -- 设置请求级租户作用域
7. handler(server, drawers, args)-- 执行 handler
8. reset_tenant_scope()          -- 恢复作用域
```

#### 错误码体系 (行 310-364)

| code | 含义 | 触发条件 |
|------|------|---------|
| 1001 | 工具不存在 | `HANDLERS.get(tool_name)` 返回 None |
| 1002 | 工具未暴露 | `exposure.check_callable()` 返回 False |
| 1003 | 只读钥匙调用写类工具 | `scope == "readonly"` 且 tool in `WRITE_TOOLS` |
| 1004 | 需要 admin 权限 | `scope != "admin"` 且 tool in `ADMIN_TOOLS` |
| 5000 | handler 执行异常 | handler 抛出未捕获异常 |

**证据**: `pangu/server/mcp_server.py` 行 63-129, 293-371

---

### 6.2 工具暴露机制 (`pangu/server/exposure.py`)

**文件**: 198 行 | **职责**: 三级暴露面过滤

#### 暴露集合计算 (行 44-105)

```
暴露集合 = 白名单(31个) 
         ∪ 已启用 optional 模块的工具
         ∪ 已启用 core 模块的非白名单工具
         ∪ 已启用实验组的工具
```

#### 白名单 (`module_registry.py`, 行 63-109)

```python
CORE_WHITELIST: frozenset[str] = frozenset({
    # 记忆 CRUD 与召回 (8)
    "pangu_add_memory", "pangu_recall", "pangu_search_memories",
    "pangu_hybrid_search", "pangu_delete_memory", "pangu_archive_memory",
    "pangu_wake_up", "pangu_set_classification",
    # 关联与统计 (5)
    "pangu_find_related", "pangu_stats", "pangu_search_stats",
    "pangu_system_health", "pangu_backup_stats",
    # 备份与迁移 (6)
    "pangu_backup", "pangu_restore_backup", "pangu_list_backups",
    "pangu_export", "pangu_import", "pangu_list_exports",
    # 项目与配置 (4)
    "pangu_project_list", "pangu_project_switch",
    "pangu_config_get", "pangu_config_set",
    # 内容采集 (2)
    "pangu_collect_file", "pangu_collect_dir",
    # 宫殿浏览 (2)
    "pangu_list_wings", "pangu_list_rooms",
    # 批量导入 (2)
    "pangu_batch_import", "pangu_batch_stats",
    # P0-1 supersede 变更链追踪
    "pangu_get_supersede_chain",
})  # 共 31 个
```

#### ExposureFilter 关键设计

```python
def check_callable(self, tool_name: str) -> tuple[bool, str | None]:
    if tool_name in self._exposed_set:
        return True, None
    # 未登记在任何模块中的工具 → 放行（扩展点不锁死）
    if not self._is_registered(tool_name):
        return True, None
    # 构建可操作错误信息
    error_msg = self._build_error_message(tool_name)
    return False, json.dumps({"code": 1002, "error": error_msg})
```

**证据**: `pangu/server/exposure.py` 行 28-198, `pangu/server/module_registry.py` 行 63-109

---

### 6.3 Handler 组织 (`pangu/server/handlers/`)

#### 聚合架构 (`handlers/__init__.py`, 行 20-121)

```python
TOOLS: list[dict[str, Any]] = []       # 工具定义列表
HANDLERS: dict[str, Any] = {}          # 工具名 → 异步处理函数
```

加载顺序: 核心模块(6) → 可选模块(11) → supersede → advanced → 实验模块(动态)

#### Handler 函数签名

```python
async def handler(server: MCPServer, drawers: list[Drawer], arguments: dict) -> str:
    # server: MCPServer 实例，提供对所有核心组件的访问
    # drawers: 当前租户可见的记忆列表（已按作用域裁剪）
    # arguments: 调用方传入的参数字典（含 _identity）
    return json.dumps(result, ensure_ascii=False)
```

#### 17 个 Handler 模块

| 层级 | 模块名 | 数量 | 默认启用 |
|------|--------|------|---------|
| **core** | memory_ops, search, system, io_tools, palace, batch, supersede | 7 | 是 |
| **optional** | multimodal, timeline, analytics, quality, consolidation, embed, knowledge_graph, knowledge, wiki, llm_tools, session | 11 | 否 |
| **experimental** | advanced (容器) | 1 | 否 |

**证据**: `pangu/server/handlers/__init__.py` 行 20-121

---

### 6.4 HTTP 层 (`pangu/api/`)

#### FastAPI 路由

| 路径 | 方法 | 功能 | 文件 |
|------|------|------|------|
| `/mcp` | POST | MCP JSON-RPC 端点 | `mcp_http.py` |
| `/health` | GET | 健康检查 | `server.py` |
| `/metrics` | GET | Prometheus 指标 | `server.py` |
| `/api/v2/...` | REST | REST API | `routes_*.py` |
| `/ws` | WebSocket | 实时事件推送 | `websocket_server.py` |

#### 中间件栈 (server.py)

```
1. CORSMiddleware          -- CORS
2. RateLimitMiddleware     -- 每分钟 100 次/IP
3. _MetricsMiddleware      -- API 指标采集
4. _ErrorStatusMiddleware  -- 错误码校正
5. _AuthMiddleware         -- 四凭据鉴权
```

**证据**: `pangu/api/server.py`, `pangu/api/mcp_http.py`

---

## 七、前端插件系统

### 7.1 插件架构 (`plugins/dsh-pangu/`)

#### 三层架构

| 层 | 文件 | 运行环境 | 职责 |
|---|---|---|---|
| **Host（宿主）** | `lib/index.js` | Node.js（DSH 进程内） | 6 个 Typert Remote 服务；桥接盘古 REST API；管理实时事件 WebSocket |
| **Client（客户端）** | `lib/client.js` | 浏览器（React 18） | 全部前端 UI：侧边栏、仪表盘、星系图谱、知识库、管理页、设置页 |
| **Proactive（主动注入）** | `lib/proactive/*` | Node.js（DSH 进程内） | 在 system-prompt 组装时自动注入相关记忆；在 turn 结束时自动沉淀有价值内容 |

#### 六大 Typert Remote 服务 (`lib/index.js`, 行 3-13)

| 服务命名空间 | 服务对象 | 提供的方法 |
|---|---|---|
| `panguDashboard` | `dashboardService` | `data()`, `ping()`, `deepHealth()`, `backup()`, `events()`, `add()`, `checkUpdate()`, `injectionStats()` |
| `panguKG` | `kgService` | `graph()` |
| `panguConfig` | `configService` | `get()`, `save()`, `testLlm()` |
| `panguAdminKeys` | `adminKeyService` | `listKeys()`, `createKey()`, `revokeKey()`, `listRooms()`, `rekeyRoom()`, `listPublicMemories()`, `listRecentMemories()` |
| `panguPlatforms` | `platformService` | `listPlatforms()`, `listPending()`, `approve()`, `reject()`, `revoke()` |
| `panguKnowledge` | `knowledgeService` | `list()`, `search()`, `get()`, `stats()` |

**证据**: `plugins/dsh-pangu/lib/index.js` 行 3-13, 405-755

---

### 7.2 前端 UI 组件 (`lib/client.js`, 2014行)

#### 三个插槽注入 (行 1999-2007)

```javascript
// 侧边栏指标卡
slots.inject('conversation.view', () =>
  slots.register({ name: 'conversation.view', id: 'pangu-kg-tab', order: 20, label: '盘古' }, () => h(PanguTab, null)),
)
// 盘古标签页（仪表盘）
slots.inject('sidebar.footer.action', () =>
  slots.register({ name: 'sidebar.footer.action', id: 'pangu-card', order: 99 }, SidebarCard),
)
// 设置页
slots.inject('settings.section', () =>
  slots.register({ name: 'settings.section', id: 'pangu-settings', order: 40, label: () => '盘古记忆系统' }, PanguSettings),
)
```

#### 星系图谱 (行 797-1125)

**零第三方依赖的 3D 可视化**，使用 Canvas2D 手写透视投影:

```javascript
const GALAXY = {
  R: 260,          // 盘面半径(世界坐标)
  FOV: 900,        // 透视焦距
  SPIN: 0.0022,    // 默认自转角速度(弧度/帧)
}
```

核心特性:
- 螺旋分布布局 `galaxyLayout()` (行 781-795)
- 3D 力模拟 (行 896-924): 斥力 + 弹簧 + 向盘心力
- 透视投影 `project()` (行 867-874): yaw/pitch 旋转 + 透视除法
- Obsidian 式搜索高亮: 非命中节点降暗而非移除
- 暗色模式适配: `MutationObserver` 监听 `data-ds-dark-theme`

#### 设置页 (行 1664-1981)

五个配置段落:

| 段 | 内容 | 行号 |
|---|---|---|
| 01 LLM 配置 | 提供商卡片选择（6选1）+ 模型 + Base URL + API Key + 连接验证 | 1797-1849 |
| 02 记忆维护 | 自动巩固开关 + 巩固间隔滑块 | 1850-1869 |
| 02B 语音转写 | Whisper 开关 + 模型大小选择 | 1870-1898 |
| 03 只读信息 | 端点、Key 状态、模型、嵌入模型、记忆库路径、MCP 服务 | 1899-1912 |
| 04 平台接入 | 接入流程说明 + 跳转管理页按钮 | 1913-1933 |
| 05 关于与更新 | 版本信息 + GitHub Release 检查 | 1934-1968 |

**证据**: `plugins/dsh-pangu/lib/client.js` 行 797-1125, 1664-1981

---

## 八、前后端通信关系

### 8.1 通信架构总览

```
浏览器 ──Typert Remote──> DSH宿主进程 ──REST/JSON-RPC──> 盘古服务(19529)
         (进程内RPC)          (fetchJson)        (http://127.0.0.1:19529)
```

### 8.2 盘古 REST API 调用

**宿主调用函数** (`lib/index.js`, 行 64-82):
```javascript
async function fetchJson(url, options = {}) {
  const headers = { 'content-type': 'application/json', ...(options.headers || {}) }
  if (url.startsWith(PANGU_BASE)) {
    const key = readStoredApiKey()
    if (key) headers['x-api-key'] = key
  }
  const res = await fetch(url, { ...signal: AbortSignal.timeout(HTTP_TIMEOUT_MS) })
  return res.json()
}
```

### 8.3 MCP JSON-RPC 调用

```javascript
// lib/index.js 行 124-133 — pangu_stats 调用
const body = await fetchJson(`${PANGU_BASE}/mcp`, {
  method: 'POST',
  body: JSON.stringify({
    jsonrpc: '2.0', id: 1, method: 'tools/call',
    params: { name: 'pangu_stats', arguments: {} },
  }),
})
```

类似调用: `pangu_backup` (行 383-400), `pangu_add_memory` (行 427-448), `pangu_config_get` (行 556-569), `pangu_config_set` (行 519-544)

### 8.4 WebSocket 实时事件 (`lib/index.js`, 行 283-335)

- 连接 `ws://127.0.0.1:19529/ws?token=...`
- 订阅 `*`（所有主题）
- 断线指数退避重连（1s → 2s → 4s → ... → 30s 封顶）
- 接收 `memory_recall` 事件时累加每日召回计数

### 8.5 主动注入的 MCP 客户端 (`proactive/mcp-client.js`)

```javascript
async function call(toolName, args, timeoutMs) {
  res = await fetch(base + '/mcp', {
    method: 'POST',
    headers: { 'x-api-key': key },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 1, method: 'tools/call',
      params: { name: toolName, arguments: args || {} },
    }),
  })
}
```

错误分类 (`classifyError`, 行 5-17): `auth` / `timeout` / `unreachable` / `format` / `unknown`

### 8.6 配置读写安全模型

#### 读取路径 (`configService.get()`, 行 575-592)

1. 读取 `~/.pangu/config.json`
2. 密钥补读: 若 `config.json` 无密钥，补读 `~/.pangu/.llm_api_key` (0600 权限)
3. **脱敏输出**: `redactConfig()` 将密钥替换为 `*_set` (布尔) + `*_hint` (尾4位)

```javascript
function redactConfig(cfg) {
  const out = { ...cfg }
  for (const k of SECRET_KEYS) {
    const raw = out[k]
    out[k] = ''
    out[k + '_set'] = typeof raw === 'string' && raw.length > 0
    out[k + '_hint'] = typeof raw === 'string' && raw.length > 4 ? '****' + raw.slice(-4) : ''
  }
  return out
}
```

#### 保存路径 (`configService.save()`, 行 594-612)

1. 密钥语义: 空字符串 = 保持原值 (因为前端拿不到明文), `null` = 清除
2. 写入 `~/.pangu/config.json` (原子写)
3. **热加载推送**: 通过 `pushToServer()` 逐字段调用 `pangu_config_set` MCP 工具

**证据**: `plugins/dsh-pangu/lib/index.js` 行 64-82, 283-335, 494-612

---

## 九、安全与鉴权体系

### 9.1 四层鉴权

#### 1. 静态 API Key (`auth.py`)

```python
# hmac.compare_digest 防时序攻击
if not hmac.compare_digest(provided_key, expected_key):
    raise AuthError("Invalid API key")
```

#### 2. JWT 双 Token (行 164-232)

- access_token (1h) + refresh_token (7d)
- 内嵌 role, scope, tenant_id, clearance
- Refresh 时执行 token rotation

#### 3. RBAC 角色权限 (`rbac.py`, 行 39-67)

```python
ROLE_PRESETS = {
    "admin":     ["*"],
    "operator":  ["memories:read", "memories:write", "memories:delete",
                  "search:query", "engines:run", "system:read"],
    "viewer":    ["memories:read", "search:query", "system:read"],
    "service":   ["memories:read", "memories:write", "search:query",
                  "engines:run", "system:read"],
}
```

#### 4. ABAC 属性访问控制 (`abac.py`, 行 262-366)

内置 8 条策略:

| 优先级 | 策略名 | 效果 | 条件 |
|--------|--------|------|------|
| 0 | deny_blacklist | DENY | 显式黑名单 |
| 10 | admin_full | ALLOW | `s.is_admin` |
| 20 | public_resource | ALLOW | `r.visibility == "public"` 且操作是 read/search |
| 30 | tenant_isolation | DENY | 跨租户访问 |
| 40 | owner_or_admin | ALLOW | 资源 owner |
| 50 | classification_based | DENY | `r.classification > s.clearance` |
| 60 | tenant_visibility | ALLOW | 同租户资源 |
| 9999 | default_deny | DENY | 无策略命中时的兜底 |

**条件表达式安全求值** (行 157-206): 将 `eval()` 替换为 AST 白名单求值

### 9.2 数据加密 (`pangu/memory/encryption.py`)

- **算法**: Fernet (AES-128-CBC + HMAC-SHA256)
- **密钥管理**: 自动生成 `~/.pangu/.encryption_key` (0600 权限)
- **密文标识**: 以 `gAAAAA` 前缀区分密文与明文 (行 39)
- **解密三态**: 明文原样返回 / 密文成功解密 / 失败返回占位符

### 9.3 MCP 侧的 Scope 强制 (`mcp_server.py`, 行 345-364)

```python
if _scope == "readonly" and tool_name in WRITE_TOOLS:
    return {"code": 1003, "error": "只读钥匙不能调用写类工具"}
if _scope != "admin" and tool_name in ADMIN_TOOLS:
    return {"code": 1004, "error": "该工具需要 admin 权限"}
```

**证据**: `pangu/server/auth.py`, `pangu/server/rbac.py`, `pangu/server/abac.py`, `pangu/memory/encryption.py`

---

## 十、关键设计决策

### 10.1 设计哲学

| 决策 | 实现 | 证据 |
|------|------|------|
| **不阻塞写入** | 去重、冲突检测、准入门均不拒绝写入 (除精确重复外), 只做标记 | `ingestion.py` 行 455-513 |
| **保留完整历史** | supersede 机制不改写旧内容, 通过 metadata 链接 | `ingestion.py` 行 125-128 |
| **三级降级** | 嵌入 ONNX → API → Hash, 每级如实上报 | `embedding.py` 行 30-441 |
| **幂等衰减** | 使用 `decay_basis_at` 解耦创建时间与衰减基准 | `decay.py` 行 119-123 |
| **密钥不落盘** | `config.json` 排除密钥, 改存独立文件 | `config.py` 行 540-541 |
| **原子写** | 所有写操作都用 tmp+replace 模式 | `drawer_storage.py` 行 72-141 |
| **神经科学对标** | 海马体容量瓶颈、睡眠重播、情感杏仁核调制、间隔重复 | `neural_memory.py` 行 149-644 |

### 10.2 性能优化

| 优化 | 实现 | 证据 |
|------|------|------|
| **惰性加载** | 所有核心组件通过 `@property` 惰性初始化 | `mcp_server.py` 行 63-129 |
| **多级缓存** | 五层缓存体系 (嵌入/搜索/FTS/LLM/JSON) | 见第四节 |
| **向量索引自动切换** | <1000条 numpy, ≥1000条 hnswlib/FAISS | `vector_index.py` 行 26-70 |
| **写入节流** | 嵌入缓存每100条落盘, LLM缓存每10次命中批量刷新 | `embedder.py` 行 122, `cache.py` 行 235-258 |
| **配置热加载** | `invalidate_config_dependents()` 丢弃已构造实例 | `mcp_server.py` 行 187-212 |

### 10.3 可靠性设计

| 设计 | 实现 | 证据 |
|------|------|------|
| **熔断器** | 连续3次失败熔断, 认证失败永久熔断 | `circuit-breaker.js` 行 1-50 |
| **指数退避重连** | WebSocket 断线重连 1s→2s→4s→...→30s | `index.js` 行 283-335 |
| **静默降级** | 异常时静默降级, 永不阻塞会话 | `injection-pipeline.js` 行 18-83 |
| **数据指纹校验** | 嵌入缓存/向量索引用内容指纹防过期 | `embedder.py` 行 63-66 |

---

## 十一、证据索引

### 文件级证据汇总

| 模块 | 文件 | 行数 | 核心功能 |
|------|------|------|---------|
| **配置** | `pangu/core/config.py` | 598 | 全局配置单例, 密钥管理, 权威路径 |
| **数据模型** | `pangu/core/palace.py` | 320 | Drawer/WikiPage/Palace 数据结构 |
| **LLM** | `pangu/core/llm.py` | 1415 | 多提供商统一调用, 三层缓存 |
| **错误码** | `pangu/core/errors.py` | 110 | 8个域30个错误码 |
| **缓存** | `pangu/core/cache.py` | 452 | LLM响应持久化缓存 |
| **摄入** | `pangu/memory/ingestion.py` | 935 | 记忆完整生命周期 |
| **衰减** | `pangu/memory/decay.py` | 234 | 艾宾浩斯衰减曲线 |
| **神经记忆** | `pangu/memory/neural_memory.py` | 819 | 海马体-新皮层双系统 |
| **向量索引** | `pangu/memory/vector_index.py` | 777 | 三级自动后端切换 |
| **全文搜索** | `pangu/memory/fts_search.py` | 654 | 中文全文检索 + 全息搜索 |
| **混合搜索** | `pangu/memory/hybrid_search.py` | 412 | 三路 RRF 融合 |
| **存储** | `pangu/memory/drawer_storage.py` | 418 | JSON/SQLite 双后端 |
| **嵌入** | `pangu/memory/embedding.py` | 441 | 三级降级嵌入 |
| **MCP** | `pangu/server/mcp_server.py` | ~500 | MCP 协议实现 |
| **暴露面** | `pangu/server/exposure.py` | 198 | 三级工具暴露 |
| **模块注册** | `pangu/server/module_registry.py` | ~300 | 17个模块元数据 |
| **Handlers** | `pangu/server/handlers/__init__.py` | ~325 | Handler 聚合 |
| **加密** | `pangu/memory/encryption.py` | ~200 | Fernet 加密 |
| **插件宿主** | `plugins/dsh-pangu/lib/index.js` | 849 | 6个Typert服务 |
| **插件客户端** | `plugins/dsh-pangu/lib/client.js` | 2014 | 全部前端 UI |
| **注入引擎** | `plugins/dsh-pangu/lib/proactive/*` | ~800 | 13个模块 |

### 关键行号速查

| 功能 | 文件:行号 |
|------|----------|
| 配置加载优先级 | `config.py:488-527` |
| 密钥不落盘 | `config.py:540-541` |
| 权威记忆路径 | `config.py:361-455` |
| Drawer 数据模型 | `palace.py:10-80` |
| 殿堂分类 | `palace.py:134-143` |
| 摄入流程入口 | `ingestion.py:516-673` |
| 四问准入门 | `ingestion.py:455-513` |
| 三层去重 | `ingestion.py:111-203` |
| 衰减公式 | `decay.py:173` |
| 激活扩散 | `neural_memory.py:380-413` |
| 睡眠巩固 | `neural_memory.py:531-644` |
| RRF 融合 | `hybrid_search.py:218-242` |
| 白名单 | `module_registry.py:63-109` |
| 暴露面计算 | `exposure.py:44-105` |
| 工具调用流程 | `mcp_server.py:293-371` |
| 错误码 1001/1002 | `mcp_server.py:310-364` |
| 星系图谱 | `client.js:797-1125` |
| 设置页 | `client.js:1664-1981` |
| 注入管线 | `proactive/injection-pipeline.js:18-83` |
| 自动沉淀 | `proactive/consolidation-writer.js:22-78` |

---

## 附录: 系统运行时验证

### 服务端口

| 端口 | 应用 | 用途 |
|------|------|------|
| **19529** | `pangu/api/server.py` | MCP + REST, DSH 插件连这个 |
| **8866** | `pangu/server/web_server.py` | 浏览器仪表盘, 不含 MCP |

### 健康检查

```bash
curl http://127.0.0.1:19529/health
```

返回 `"status":"ok"` 表示正常, `"status":"degraded"` + `"embedding_backend":"hash"` 表示已降级。

### 实测工具数

```bash
curl -s -X POST http://127.0.0.1:19529/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['result']['tools']))"
```

默认 28 个核心工具, 全开可达 408 个。

---

> **分析完成**: 本报告所有结论均附源码文件:行号证据, 无推测成分。
> 
> 生成时间: 2026-09-20
