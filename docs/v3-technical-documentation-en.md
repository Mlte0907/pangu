# Pangu v3.0 Technical Documentation

> Version: v3.0 | Date: 2026-06-19 | Modules: 108 | MCP Tools: 368 | Tests: 884 | LOC: 30K+

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core Modules](#3-core-modules)
4. [v3.0 New Modules](#4-v30-new-modules)
5. [MCP Tools](#5-mcp-tools)
6. [API Reference](#6-api-reference)
7. [Configuration](#7-configuration)
8. [Deployment](#8-deployment)
9. [Performance](#9-performance)
10. [Testing](#10-testing)

---

## 1. Overview

Pangu (盘古) is a dedicated memory system ("brain component") for AI Agent frameworks. It provides memory storage, retrieval, organization, classification, and knowledge crystallization via MCP protocol.

### Version History

| Version | Commits | MCP Tools | Modules | Code | Tests |
|:---|:---|:---|:---|:---|:---|
| v1.0 | ~20 | ~30 | ~15 | ~5K | ~30 |
| v2.0 | 68 | 177 | 63 | 22,832 | 153 |
| **v3.0** | **137** | **368** | **108** | **30K+** | **884** |

### Key Metrics

| Metric | Value |
|:---|:---|
| Search Latency | 0.01ms median |
| Embedding Latency | 0.00ms (ONNX cached) |
| QPS | 936 |
| Cold Query Warmup | 1017ms → 32ms (31.8x) |
| Code Quality | 97.8/100 |
| Warnings | 0 |

---

## 2. Architecture

### 4-Layer Memory Stack

```
L0 Identity (~100 tokens)    ─── Always loaded, defines "who am I"
L1 Summary   (~500-800 tok)  ─── Always loaded, key memory summary
L2 On-demand (~200-500 tok)  ─── Topic-triggered loading
L3 Deep Search (unlimited)   ─── Explicit full-text semantic search
```

### 3-Tier Embedding

| Tier | Method | Latency | Cost |
|:---|:---|:---|:---|
| 1 | ONNX Local (MiniLM-L6, 384-dim) | ~0ms (cached) | Free |
| 2 | API (Ollama) | ~50ms | Low |
| 3 | Hash Vector | ~0ms | Free |

### Hybrid Search (FTS + Vector RRF)

```
FTS (jieba tokenization) × 0.5 weight  ─┐
                                         ├─→ RRF Fusion (K=60) → Results
Vector Search (FAISS)     × 1.0 weight  ─┘
```

### Palace Structure

```
Wings (top-level) → Rooms (sub-categories) → Drawers (memory units) → Halls (cross-cutting)
```

---

## 3. Core Modules

| Module | Description | MCP Tools |
|:---|:---|:---|
| `layers.py` | 4-layer memory stack (L0-L3) | `pangu_*` |
| `retrieval.py` | Recall function with hybrid search | `pangu_recall` |
| `ingestion.py` | Memory ingestion pipeline | `pangu_add_memory` |
| `knowledge_graph.py` | Entity/relation graph | `pangu_kg_*` |
| `vector_index.py` | FAISS vector index | `pangu_vector_index_*` |
| `onnx_embedder.py` | ONNX local embedding (384-dim) | - |
| `fts_search.py` | FTS5 full-text search | `pangu_fts_search` |
| `hybrid_search.py` | FTS + Vector RRF hybrid | `pangu_hybrid_search` |
| `consolidation.py` | Memory consolidation | `pangu_consolidation_*` |
| `lifecycle.py` | Lifecycle management | `pangu_lifecycle_*` |
| `neural_memory.py` | Neural memory system | `pangu_neural_*` |
| `multi_agent.py` | Multi-agent collaboration | `pangu_multi_*` |
| `social_memory.py` | Social memory (comments/votes) | `pangu_comment_*` |
| `versioning.py` | Memory version control | `pangu_version_*` |

---

## 4. v3.0 New Modules

### Intelligent Memory Engines (31)

| Module | Description | Tools |
|:---|:---|:---|
| Self-Evolution | Self-diagnosis, evolution plan | 4 |
| Temporal Reasoning | Timeline, temporal relations | 4 |
| Semantic Compression | Tag-based compression | 3 |
| Collaborative Intelligence | Agent register/share | 4 |
| Causal Reasoning | Causal discovery, counterfactual | 5 |
| Explainable Search | Search explanation | 2 |
| Anomaly Detection | Content/stat scan | 3 |
| Knowledge Synthesis | Contradiction detection | 4 |
| Predictive Analytics | Query/forgetting prediction | 5 |
| Adaptive Architecture | Architecture analysis | 4 |
| QA Engine | Intelligent Q&A | 3 |
| Context Injection | Inject/update context | 4 |
| Adaptive Forgetting | Forgetting evaluation | 4 |
| Consolidation Intelligence | Smart consolidation | 4 |
| Memory Recommendation | Similar/timely recommendation | 5 |
| Quality Scorer | Quality assessment | 4 |
| Meta Learning | Strategy recommendation | 5 |
| Memory Distillation | Knowledge crystallization | 4 |
| Query Rewriter | Query expansion | 3 |
| Graph Builder | Auto graph construction | 5 |
| Health Monitor | 6-dimension health check | 3 |
| Backup Restore | Backup/verify/restore | 5 |
| Project Manager | Multi-project support | 10 |
| Audit Analytics | Access patterns/security | 5 |
| Sync Manager | Multi-device sync | 7 |
| Event Stream | Publish/subscribe/Webhook | 5 |
| Smart Indexing | Auto index build/search | 5 |
| Smart Cache | L1+L2 cache management | 3 |
| Unified Portal | One-stop portal | 5 |
| Memory Diff | Content comparison | 4 |
| Export/Import | 5 export + 4 import formats | 8 |

### Fuxi Cognitive Engine Migration (12)

| Module | Description | Tools |
|:---|:---|:---|
| Cognitive Loop | Observe→Think→Evaluate→Act | 2 |
| World Model | Scenario prediction, plans | 4 |
| Dream Memory | 5-step sleep consolidation | 2 |
| Curiosity | Knowledge gap discovery | 2 |
| Persona | Identity/values/health | 3 |
| Deep Emotion | Trajectory analysis | 3 |
| Debate | Multi-perspective argumentation | 2 |
| Narrative | Story generation | 3 |
| Resonance | Emotional resonance | 3 |
| Intent Prediction | Behavior patterns | 3 |
| Metacognition | System monitoring | 2 |
| Knowledge Synthesis | Cross-cluster association | 2 |

---

## 5. MCP Tools (368 total)

### Categories

| Category | Tools |
|:---|:---|
| Memory Core | Palace, CRUD, Wiki, KG, LLM, Tunnels |
| Memory Intelligence | Consolidation, Backup, Clustering, Conflict, Analysis, Fusion, Patterns |
| v3.0 Engines | Self-Evolution, Temporal, Compression, Collaboration, Causal, etc. |
| Fuxi Migration | Cognitive Loop, World Model, Dream, Curiosity, Persona, etc. |
| LLM Cache | Cache stats/top/clear/metrics/warmup |
| Production | Health check, startup validation, environment check |

---

## 6. API Reference

### REST API

| Method | Path | Description |
|:---|:---|:---|
| GET | `/health` | Health check |
| GET | `/dashboard` | Monitoring dashboard |
| GET/POST | `/api/v2/memories` | Memory CRUD |
| POST | `/api/v2/memories/search` | Search memories |
| GET | `/ws` | WebSocket real-time events |

### MCP Protocol

```python
from pangu.server.mcp_server import MCPServer
server = MCPServer()

# Add memory
server.call_tool("pangu_add_memory", {"content": "Project uses FAISS", "wing": "work"})

# Search
results = server.call_tool("pangu_search_memories", {"query": "FAISS", "limit": 5})
```

---

## 7. Configuration

### Environment Variables

| Variable | Default | Description |
|:---|:---|:---|
| `PANGU_PORT` | 19529 | Server port |
| `PANGU_LLM_PROVIDER` | openai | LLM provider |
| `PANGU_LLM_MODEL` | gpt-4o | Model name |
| `PANGU_ONNX_ENABLED` | true | ONNX local embedding |
| `PANGU_CONSOLIDATION_ENABLED` | true | Memory consolidation |
| `PANGU_EMBED_API_URL` | (empty) | Embedding API URL (empty = ONNX only) |

### Config File

Location: `~/.pangu/config.json`

```json
{
  "port": 19529,
  "llm_provider": "openai",
  "llm_model": "gpt-4o",
  "onnx_enabled": true,
  "consolidation_enabled": true
}
```

---

## 8. Deployment

### Docker (Recommended)

```bash
# Build
docker build --target runtime -t pangu:3.0.0 .

# Run with health check
docker compose up -d

# Verify
docker inspect --format='{{.State.Health.Status}}' pangu
```

### Direct

```bash
cd pangu
pip install -e .
pangu serve --host 127.0.0.1 --port 19529
```

### Health Check (Required After Deployment)

```bash
# Check all systems
curl http://127.0.0.1:19529/health
curl http://127.0.0.1:19529/dashboard
```

---

## 9. Performance

| Metric | Value |
|:---|:---|
| Search Latency (median) | 0.01ms |
| Embedding Latency (cached) | 0.00ms |
| Cold Query | 32ms (after warmup) |
| QPS | 936 |
| Memory Count | 85 |
| Vector Index Size | 1000+ |

### Warmup

On startup, Pangu automatically warms up:
- jieba tokenization dictionary
- ONNX embedding model
- FTS index
- Vector index

Cold query reduced from 1017ms → 32ms (31.8x speedup).

---

## 10. Testing

**884 tests, 0 warnings**

| Test File | Tests |
|:---|:---|
| test_core.py | 128 |
| test_v2_features.py | 17 |
| test_top_level_intelligence.py | 8 |
| test_v3_modules_a-e.py | 275 |
| test_v3_modules_f-h.py | 362 |
| test_boundary_cases.py | 94 |

```bash
# Run all tests
pytest tests/test_core.py tests/test_v2_features.py \
       tests/test_top_level_intelligence.py \
       tests/test_v3_modules_*.py \
       tests/test_boundary_cases.py
```

---

*Generated by MiMoCode | Pangu v3.0 — AI Agent Memory System*
