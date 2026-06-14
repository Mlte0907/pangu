# 模块总览

```
pangu/
├── api/            # FastAPI 服务器、路由、依赖
│   ├── server.py       # create_app() 工厂
│   └── routes_memory.py
├── core/           # 核心抽象
│   ├── config.py       # PanguConfig (pydantic-settings)
│   ├── cache.py        # PersistentLLMCache (LRU + SQLite)
│   ├── llm.py          # LLMEngine（多 provider）
│   └── palace.py       # Palace 抽象（Wing/Room/Drawer）
├── memory/
│   ├── embedding.py    # 3 级退化嵌入
│   ├── onnx_embedder.py
│   ├── working_memory.py
│   ├── sanitizer.py    # 注入清洗
│   └── memory_stack.py # 4 层栈
├── knowledge_graph.py  # 三元组 + 双向游走
├── search/
│   ├── engine.py       # semantic / lexical / hybrid
│   └── embedder.py
├── server/
│   └── mcp_server.py   # JSON-RPC over stdio/HTTP
├── store/              # ChromaDB + SQLite
├── observability/      # metrics / health
├── wiki/               # Wiki 引擎
├── migration/          # export / import
└── cli.py              # typer 入口
```

## 关键约定

- **配置**：所有可调参数走 `PanguConfig`，环境变量前缀 `PANGU_`
- **路径**：默认 `~/.pangu/`，可通过 `PANGU_BASE_DIR` 覆盖
- **错误**：用 `pangu.core.exceptions.PanguError` 及子类
- **日志**：`logger = logging.getLogger("pangu.<module>")`
- **类型**：公开 API 全量 type hint；内部可用 `Any`

## 扩展点

| 扩展点 | 协议 | 入口 |
|:---|:---|:---|
| LLM Provider | `class LLMProvider(Protocol)` | `pangu.core.llm` |
| 嵌入后端 | `class Embedder(Protocol)` | `pangu.memory.embedding` |
| 检索后端 | `class SearchEngine(Protocol)` | `pangu.search.engine` |
| MCP 工具 | 装饰器 `@mcp_tool` | `pangu.server.mcp_server` |
| REST 路由 | FastAPI router | `pangu.api.routes_*` |
| 衰减策略 | `class DecayStrategy(Protocol)` | `pangu.core.decay` |

## 数据流关键节点

### 写入

```
HTTP POST /api/v2/memories
   ↓
Sanitizer.sanitize(content)
   ↓
LLMEngine.summarize (异步, LRU+SQLite 缓存)
   ↓
EmbeddingService.embed (3 级退化)
   ↓
MemoryStack.add_drawer
   ├── L1 摘要更新
   ├── L2 写入 + ChromaDB
   └── KnowledgeGraph.upsert
   ↓
200 OK
```

### 检索

```
POST /api/v2/memories/search {q, top_k, mode}
   ↓
SearchEngine.query
   ├── semantic:  query embed → ChromaDB search
   ├── lexical:   SQLite FTS5
   └── hybrid:    rrf 融合
   ↓
L1 摘要注入
   ↓
Drawer 排序 + 重要性加权
   ↓
200 OK
```
