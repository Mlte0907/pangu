# 模块总览

```
pangu/
├── api/                    # FastAPI 服务器、路由
│   ├── server.py           # create_app() 工厂
│   ├── routes_memory.py    # 记忆 CRUD API
│   ├── routes_tasks.py     # 任务管理 API (SQLite)
│   ├── routes_tags.py      # 标签管理 API (SQLite)
│   ├── auth.py             # JWT + API Key 鉴权 (SQLite)
│   └── rbac.py             # RBAC 权限控制
├── core/                   # 核心抽象
│   ├── config.py           # PanguConfig (pydantic-settings)
│   ├── cache.py            # PersistentLLMCache (LRU + SQLite)
│   ├── llm.py              # LLMEngine（多 provider）
│   └── palace.py           # Palace 抽象（Wing/Room/Drawer）
├── memory/                 # 记忆系统核心
│   ├── ingestion.py        # remember() 核心写入路径
│   ├── retrieval.py        # recall() 核心检索路径
│   ├── layers.py           # 4 层记忆栈 (L0-L3)
│   ├── embedding.py        # 3 级退化嵌入 (API→ONNX→hash)
│   ├── onnx_embedder.py    # ONNX 本地推理
│   ├── vector_index.py     # 向量索引 (numpy/hnswlib/FAISS)
│   ├── fts_search.py       # FTS5 全文搜索 (jieba 分词)
│   ├── hybrid_search.py    # FTS+Vector+KG RRF 混合搜索
│   ├── neural_memory.py    # 海马体-新皮层双系统
│   ├── knowledge_graph.py  # 知识图谱 (实体+关系)
│   ├── graph_reasoning.py  # 图推理引擎
│   ├── proactive.py        # 预测性记忆
│   ├── versioning.py       # 记忆版本控制
│   ├── visualization.py    # 记忆可视化
│   ├── importance_scorer.py # ML 重要性评分
│   ├── conflict.py         # 冲突检测
│   ├── memory_validator.py # 记忆验证
│   ├── cross_session.py    # 跨会话整合
│   ├── synonyms.py         # 同义词扩展
│   ├── cluster.py          # 搜索聚类
│   ├── consolidation.py    # 记忆巩固
│   ├── decay.py            # 记忆衰减
│   ├── fusion.py           # 记忆融合
│   ├── lifecycle.py        # 生命周期管理
│   ├── encryption.py       # E2E 加密 (Fernet)
│   ├── multi_agent.py      # 多 Agent 协作
│   ├── social_memory.py    # 社交记忆 (评论/投票)
│   ├── working_memory.py   # 工作记忆 (Miller 7±2)
│   ├── adaptive_params.py  # 自适应参数
│   ├── attention.py        # 注意力系统
│   ├── event_bus.py        # 事件总线
│   ├── distill_enhanced.py # 知识蒸馏
│   └── sanitizer.py        # 记忆脱敏
├── server/
│   └── mcp_server.py       # MCP 工具 (80+ 个)
├── store/                  # 数据持久化
├── observability/          # metrics / health / tracing
├── wiki/                   # Wiki 引擎
├── mining/                 # 记忆挖掘
├── hooks/                  # 钩子系统
├── plugins/                # 插件系统
└── cli.py                  # CLI 入口
```

## 关键约定

- **配置**：所有可调参数走 `PanguConfig`，环境变量前缀 `PANGU_`
- **路径**：默认 `~/.pangu/`，数据文件：drawers.json, knowledge_graph.db, tasks.db, users.db, social.db, tags.db
- **日志**：`logger = logging.getLogger("pangu.<module>")`
- **类型**：公开 API 全量 type hint
- **持久化**：SQLite WAL 模式 + check_same_thread=False

## 数据流

### 写入 (remember())
```
raw_text → Sanitizer → Encryption → Dedup Check → Fusion Check
    → Drawer 创建 → ONNX Embedding → Vector Index → Neural Encoding
    → Conflict Detection → Persistence (drawers.json)
```

### 检索 (recall())
```
query → Query Expansion + Synonyms → Vector Search (hnswlib/FAISS)
    → FTS Search (jieba) → RRF Fusion → Neural Spreading
    → Score: sim*0.6 + (importance*0.6 + decay*0.4)*0.4
    → Token Budget Truncation → Auto Decrypt → Return
```

## 性能基线

| 指标 | 值 |
|---|---|
| ONNX 嵌入 | 0.002ms (cached) |
| VectorIndex 搜索 | 0.13ms (hnswlib) |
| FTS 搜索 | 0.01ms |
| recall() 缓存后 | 0.1ms |
| cosine similarity | numpy 向量化 |
