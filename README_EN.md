# Pangu v3.0 — AI Agent Memory System

> The "brain component" for AI agents, focused on solving common memory function shortcomings in Agent frameworks.

Pangu is not a complete Agent framework, but a dedicated memory intelligence system focused on core memory functions: storage, retrieval, organization, classification, knowledge crystallization, and human-like memory intelligence. It provides memory services to upper-level Agents through the MCP protocol.

| Metric | Value | Metric | Value |
|:---|:---|:---|:---|
| Version | v3.0 | Port | 19529 |
| Git Commits | 123 | Tech Stack | Python 3.12, ONNX, FAISS, SQLite |
| Test Cases | 884 | Runtime Data | `~/.pangu/` |
| MCP Tools | 359 | Modules | 106 |
| Lines of Code | 30K+ | License | MIT |

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│              Upper Agent (Claude Code / Gemini CLI)         │
└─────────────────────────┬─────────────────────────────────┘
                          │ MCP Protocol / REST API / WebSocket
                          ▼
┌───────────────────────────────────────────────────────────┐
│                    Pangu v3.0 Memory System                │
│                                                           │
│  ┌──────────────────────────────────────────────────┐     │
│  │             4-Layer Memory Stack (L0-L3)          │     │
│  │  L0 Identity │ L1 Summary │ L2 On-demand │ L3     │     │
│  │  ~100 tok    │ ~500-800   │ ~200-500     │ Unlimited│    │
│  │  Always On   │ Always On  │ Topic-trigger│ Explicit │    │
│  └──────────────────────────────────────────────────┘     │
│                                                           │
│  Palace Structure  Wiki Engine  Knowledge Graph  E2E Enc  │
│  Neural Memory     Hybrid Search Knowledge Crystallize    │
│  Self-Evolution    Causal Reason  Meta-Learning  Collab   │
│  Predictive        Anomaly Det   Unified Portal  Events   │
│  Version Control   Audit         Multi-project  Prod Hard │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │  SQLite   │  │   FAISS  │  │   ONNX   │                │
│  │ WAL Persist│  │ Vector Idx│  │ Local Emb│                │
│  └──────────┘  └──────────┘  └──────────┘                │
└───────────────────────────────────────────────────────────┘
```

## Core Features

| Feature | Description |
|:---|:---|
| **4-Layer Memory Stack** | L0 Identity / L1 Summary / L2 On-demand / L3 Deep Search, progressive loading |
| **Palace Structure** | Wing space → Room page → Drawer memory unit, Hall concept classification |
| **Hybrid Search** | FTS + Vector + KG triple recall, RRF fusion ranking |
| **ONNX Local Embedding** | MiniLM-L6 quantized inference, 0.002ms/item, zero API cost |
| **FAISS Vector Index** | Auto-switch at ≥1000 items, 0.22ms for 20K items |
| **SQLite Persistence** | WAL mode, knowledge graph / LLM cache / social data |
| **E2E Encryption** | Fernet AES-128-CBC + HMAC-SHA256 |
| **Multi-tenant Isolation** | agent_id namespace isolation, different Agents invisible to each other |
| **OpenTelemetry** | OTLP/Console distributed tracing, @traced decorator |
| **Prometheus** | 86 pangu_* metrics, Grafana dashboard compatible |
| **WebSocket** | Real-time memory event stream, topic subscription, 30s heartbeat |
| **LLM Multi-backend** | OpenAI / Anthropic / Ollama / OpenRouter / DeepSeek / Zhipu / Tongyi |
| **LLM Cache** | Memory LRU + SQLite dual-level cache, survives restarts |
| **Multi-Agent Collab** | private/shared/public 3-level permissions, comments/votes |
| **Knowledge Crystallization** | LLM-driven Wiki auto-generation, smart linking |
| **Security** | Bandit HIGH: 22→0, parameterized queries, blake2b hashing |
| **Plugin System** | Plugin registration/discovery, hook mechanism, 3 built-in plugins |

## v3.0 New Modules (43)

### Intelligent Memory Engines (31)

| Module | Description | Tools | Module | Description | Tools |
|:---|:---|:---|:---|:---|:---|
| Self-Evolution | Self-diagnosis, evolution plan, perf trends | 4 | Causal Reasoning | Causal discovery, counterfactual, root cause | 5 |
| Temporal Reasoning | Timeline, temporal relations, time query | 4 | Explainable Search | Search explanation, query suggestions | 2 |
| Semantic Compression | Tag-based compression, importance reassessment | 3 | Anomaly Detection | Content/stat anomaly scan | 3 |
| Collaborative Intelligence | Agent register/share, collaborative reasoning | 4 | Knowledge Synthesis | Contradiction detection, core insights | 4 |
| Predictive Analytics | Query/forgetting prediction, hot topics | 4 | Adaptive Architecture | Architecture analysis, hot/cold separation | 4 |
| QA Engine | QA engine, batch queries | 3 | Context Injection | Inject/update/query context | 4 |
| Adaptive Forgetting | Forgetting evaluation, auto-archive | 4 | Consolidation Intelligence | Smart consolidation, merge, conflict resolution | 4 |
| Memory Recommendation | Similar/timely recommendation, feedback | 5 | Quality Scorer | Quality assessment, batch fix | 4 |
| Meta Learning | Observe, strategy recommendation, auto-tune | 5 | Memory Distillation | Distillation, keyword extraction | 4 |
| Query Rewriter | Query rewrite, suggestions | 3 | Graph Builder | Graph construction, entity/path | 5 |
| Health Monitor | Health trend, statistics | 3 | Backup Restore | Backup/verify/restore | 5 |
| Multi-project | Project create/switch/search/merge | 10 | Audit Analytics | Log/access patterns/security summary | 5 |
| Multi-device Sync | Sync/conflict resolution | 6 | Event Stream | Publish/subscribe/Webhook | 4 |
| Smart Indexing | Index build/search/recommend | 5 | Smart Cache | Cache stats/cleanup/invalidation | 3 |
| Unified Portal | Write/search/panorama view | 5 | Memory Diff | Diff/similarity/stats | 4 |
| Production Hardening | Environment check, startup validation | 2 | | | |

### Fuxi Cognitive Engine Migration (12)

| Module | Description | Tools | Module | Description | Tools |
|:---|:---|:---|:---|:---|:---|
| Cognitive Loop | Observe→Think→Evaluate→Act cycle | 2 | Deep Emotion | Trajectory analysis, mixed emotion decomposition | 3 |
| World Model | Scenario prediction, plan generation | 4 | Debate Engine | Multi-perspective argumentation, 4D scoring | 2 |
| Dream Memory | 5-step sleep consolidation | 2 | Narrative Engine | Story generation, theme extraction | 3 |
| Curiosity | Knowledge gap discovery | 2 | Resonance Engine | Emotional resonance matching | 3 |
| Persona Engine | Identity/values/health | 3 | Intent Prediction | Behavior patterns, task chain | 3 |
| Metacognition Enhanced | System monitoring, self-reconfig | 2 | Knowledge Synthesis Enhanced | Cross-cluster association, gap detection | 2 |

## Quick Start

### Installation

```bash
cd pangu
pip install -e .
pangu init
```

### Configure LLM

```bash
# OpenAI
export OPENAI_API_KEY="sk-xxx"
pangu init --force

# Ollama (local)
export PANGU_LLM_PROVIDER=ollama
export PANGU_LLM_MODEL=qwen2.5:7b
pangu init --force
```

### Start Service

```bash
pangu mcp          # MCP server (port 19529)
pangu serve        # Web UI (port 8866)
pangu api          # API server
```

### CLI Commands

```bash
pangu search "keyword"           # Search memories
pangu wake-up                    # Get wake-up context
pangu recall --wing work         # Recall by wing
pangu consolidate                # Consolidation status
pangu forget --dry-run           # Preview forgetting
pangu stats                      # System statistics
```

### MCP Tool Usage

```python
from pangu.server.mcp_server import MCPServer
server = MCPServer()

# Add memory
server.call_tool("pangu_add_memory", {"content": "Project uses FAISS", "wing": "work"})

# Search
results = server.call_tool("pangu_search_memories", {"query": "FAISS", "limit": 5})

# Recall
context = server.call_tool("pangu_wake_up", {})
```

## Performance

| Metric | Value | Metric | Value |
|:---|:---|:---|:---|
| ONNX Single Embed | 0.002ms | FTS Search (25d) | 0.006ms |
| ONNX Model Size | ~22MB | Vector Search (25v) | 0.063ms |
| Model | MiniLM-L6 (384-dim) | Hybrid Search | 3.7ms |
| Batch Encode | 3-5x speedup | Concurrent Throughput | 5963 ops/s |

## Testing

**884 tests all passing**

| Category | Count | Category | Count |
|:---|:---|:---|:---|
| Core Unit Tests | 128 | v2 Feature Tests | 17 |
| Intelligence Tests | 8 | v3.0 Module Tests | 275 |
| Boundary Tests | 94 | Fuxi Migration Tests | 49 |
| Performance Tests | 8 | Regression Tests | 26 |

## Configuration

| Config | Env Var | Default | Description |
|:---|:---|:---|:---|
| `port` | `PANGU_PORT` | `19529` | MCP/API port |
| `llm_provider` | `PANGU_LLM_PROVIDER` | `openai` | LLM provider |
| `llm_model` | `PANGU_LLM_MODEL` | `gpt-4o` | Model name |
| `onnx_enabled` | `PANGU_ONNX_ENABLED` | `true` | ONNX local embedding |

## API

| Method | Path | Description |
|:---|:---|:---|
| GET | `/health` | Health check |
| GET | `/dashboard` | Monitoring dashboard |
| GET/POST | `/api/v2/memories` | Memory CRUD |
| POST | `/api/v2/memories/search` | Search memories |
| GET | `/ws` | WebSocket real-time events |

## Deployment

```bash
# systemd
sudo systemctl enable pangu
sudo systemctl start pangu

# Docker
docker compose up -d
```

## License

MIT
