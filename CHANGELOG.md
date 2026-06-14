# Changelog

All notable changes to Pangu will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/).

## [2.0.0] - 2026-06-14

### Added — 神经记忆系统
- **NeuralMemoryEngine**: 海马体-新皮层双系统，4 种记忆类型 (episodic/semantic/procedural/emotional) × 5 种状态
- **PersonalizedDecay**: 不同记忆类型不同遗忘曲线（语义 4.6 天半衰期 vs 情景 1.2 天）
- **Hippocampus**: 短期记忆缓冲，容量管理，竞争抑制淘汰最弱记忆
- **Neocortex**: 长期记忆存储，激活扩散（BFS），竞争抑制（Winner-Take-All）
- **SleepConsolidation**: 睡眠巩固周期，海马体→新皮层重播，情感去标记化
- **EmotionalModulator**: 杏仁核调制编码强度和检索偏好
- 接通 `remember()` 神经编码、`recall()` 激活扩散、`lifecycle` 睡眠巩固

### Added — 记忆融合自动化
- **Auto Fusion**: `lifecycle.py` 新增 `run_auto_fusion()`，按 wing+tag 分组，同主题 ≥3 条自动融合
- `FusionEngine.fuse_topic()` 接入 lifecycle，结果写入 drawers.json

### Added — 冲突检测增强
- **Auto Conflict Check**: `ingestion.py` 新记忆写入时自动检查矛盾
- **memory_status 字段**: active / stale / conflicted / verified 四种状态
- 冲突结果写入 `metadata.conflicts`

### Added — 重要性自适应
- **importance_feedback()**: 5 种反馈信号 (recall_success/miss, vote_up/down, verified)
- 信号乘数：success 1.08x, miss 0.92x, vote_up 1.05x, vote_down 0.95x, verified 1.15x
- 自动保存到 drawers.json

### Added — 跨会话记忆整合
- **CrossSessionIntegrator**: 新模块 `cross_session.py`
- 向量相似度发现跨会话关联，关键词降级
- KG 关系自动写入

### Added — 记忆压缩摘要
- **compress_memory()**: 关键句提取压缩，保留标签词和重要性关键词句子
- **Auto Compress**: lifecycle 自动压缩 >100 字未压缩记忆

### Added — 记忆验证机制
- **MemoryValidator**: 新模块 `memory_validator.py`
- 时效性检查（>90 天事实类→stale），冲突标记，压缩标记→verified

### Added — KG 自动提取
- **auto_extract_entities()**: 技术/系统/Agent/协议实体识别，动词关系提取
- lifecycle 自动执行

### Added — 混合检索
- **hybrid_search()**: 新模块 `hybrid_search.py`
- FTS + 向量 + KG 三路召回，RRF (Reciprocal Rank Fusion) 融合排序
- RRF 公式：`score(d) = Σ weight_i / (k + rank_i(d))`，k=60

### Added — FAISS 向量索引加速
- **自动切换**: <1000 条 numpy brute-force，≥1000 条 FAISS IVFFlat
- **预归一化**: 构建时归一化一次，搜索时跳过，numpy 路径 3-6x 提速
- **性能**: 1000v 0.10ms, 5000v 0.14ms, 20000v 0.22ms

### Added — MCP 工具 (13 个新工具)
- `pangu_neural_stats/sleep/spreading/inhibition/decay`
- `pangu_importance_feedback`
- `pangu_auto_fusion`
- `pangu_cross_session_links`
- `pangu_auto_compress`
- `pangu_validate_memories`
- `pangu_kg_auto_extract`
- `pangu_hybrid_search`

### Fixed
- **SleepConsolidation 共享实例**: 原创建独立 Hippocampus/Neocortex 实例，sleep 时读到空缓冲区
- **Drawer 时间戳解析**: NeuralMemory.created_at 解析 Drawer ISO 时间戳，避免立即衰减
- **记忆巩固后立即衰减**: 巩固时重置 created_at 为当前时间

### Changed
- **Version**: 1.0.0 → 2.0.0
- **测试**: 172 passed (core + integration)

## [1.0.0] - 2026-06-12

### Added
- **E2E Encryption**: Fernet (AES-128-CBC + HMAC-SHA256) for memory content at rest
- **Multi-tenancy**: agent_id namespace isolation in recall() and FTS search
- **OpenTelemetry Tracing**: OTLP/Console export with @traced decorator
- **Prometheus Metrics**: KG (entities/relations), search (latency/results), vector index (size/latency) metrics — 86 total pangu_* metrics
- **Module Integration**: clustering (6 clusters), pattern discovery (25 patterns), consolidation, dedup all verified working
- **Performance Baseline**: ONNX embed 0.002ms, vector search 0.063ms, FTS 0.006ms, concurrent 5963 ops/s
- **Auto-collection Pipeline**: cron-based collection + ONNX embedding + vector index rebuild
- **Lifecycle Automation**: consolidation + index rebuild via cron

### Fixed
- **D-001**: embedding.py field name (embed_api_url) — already correct in codebase
- **D-002**: test_bench.py KG signature — already correct in codebase
- **D-003**: MD5→blake2b in auto_collector.py and performance.py (bandit HIGH: 22→0)
- **D-006**: host default changed from 0.0.0.0 to 127.0.0.1
- **D-008**: python-multipart pinned to >=0.0.18 (CVE fix)
- **patterns.py**: Fixed Counter bug in find_association_patterns()

### Changed
- **Version**: 0.1.0 → 1.0.0
- **SQLite**: WAL mode enabled in all database modules
- **Auth**: JWT + API Key dual auth implemented (conditional on config)

### Security
- Bandit HIGH: 22 → 0
- Bandit MEDIUM: 10 (non-critical)
- Secret scan: 0 hits
- SQL injection: immune (parameterized queries)
- Path traversal: immune (404 responses)

### Performance
- ONNX embed: 0.002ms (cached)
- Vector search (25v): 0.063ms median, 0.073ms p95
- FTS search (25d): 0.006ms median
- Concurrent throughput: 5963 ops/s (exceeds v1.0 target of 5000)

## [0.1.0] - 2026-06-08

### Added
- Initial release with 4-layer memory stack (L0-L3)
- Palace metaphor (Wings/Rooms/Drawers/Halls)
- MCP server with 118 tools
- REST API with FastAPI
- CLI with typer
- ONNX local embedding (MiniLM-L6-v2)
- FTS5 full-text search + vector semantic search + RRF fusion
- Knowledge graph (SQLite)
- Wiki engine
- Persistent LLM cache (SQLite)
- Prometheus metrics
- Health checks (/health, /health/deep, /metrics)
