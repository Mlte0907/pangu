# MCP 工具参考

盘古通过 MCP 协议暴露 **80+ 工具**。本文档列出全部工具及其参数。

## 分类索引

- [Palace 管理](#palace-管理)
- [记忆操作](#记忆操作)
- [Wiki 操作](#wiki-操作)
- [知识图谱](#知识图谱)
- [LMM 处理](#lmm-处理)
- [伏羲移植模块](#伏羲移植模块)
- [服务器管理](#服务器管理)

---

## Palace 管理

### pangu_list_wings

列出所有空间。

**参数**：无

**返回**：
```json
{
  "wings": [{"name": "tech", "rooms_count": 5, "drawers_count": 100}]
}
```

### pangu_create_wing

创建新空间。

**参数**：
- `name` (str, 必填): 空间名
- `description` (str, 可选): 描述

### pangu_list_rooms

列出空间中的房间。

**参数**：
- `wing` (str, 必填): 空间名

### pangu_create_room

创建新房间。

**参数**：
- `wing` (str, 必填): 所属空间
- `name` (str, 必填): 房间名

---

## 记忆操作

### pangu_add_memory

写入记忆。

**参数**：
- `content` (str, 必填): 记忆内容
- `wing` (str, 默认 "default"): 空间
- `room` (str, 默认 "general"): 房间
- `importance` (float, 0-1, 默认 0.5): 重要度
- `tags` (list[str], 可选): 标签
- `source` (str, 可选): 来源

**返回**：
```json
{"id": "drawer_xxxxx", "wing": "tech", "room": "python"}
```

### pangu_search_memories

搜索记忆。

**参数**：
- `query` (str, 必填): 搜索关键词
- `wing` (str, 可选): 限定空间
- `limit` (int, 1-50, 默认 10): 返回数量
- `search_type` (str, "hybrid"|"fts"|"vector"): 搜索类型

**返回**：
```json
{
  "query": "Python",
  "results": [{"id": "...", "content": "...", "score": 0.92}],
  "total": 5
}
```

### pangu_recall

唤醒上下文（4 层记忆栈）。

**参数**：
- `token_budget` (int, 默认 2000): token 预算

**返回**：
```json
{
  "L0": "我是盘古，专业的记忆系统",
  "L1": "用户最近关注：...",
  "L2": [...],
  "L3": [...],
  "token_used": 1500
}
```

### pangu_wake_up

会话启动时调用，返回注入上下文的全部内容。

---

## Wiki 操作

### pangu_list_wiki_pages

列出所有 Wiki 页面。

### pangu_get_wiki_page

获取 Wiki 页面。

**参数**：
- `title` (str, 必填): 页面标题

### pangu_create_wiki_page

创建 Wiki 页面。

**参数**：
- `title` (str, 必填)
- `content` (str, 必填): Markdown 内容
- `tags` (list[str], 可选)
- `linked_pages` (list[str], 可选): 关联页面

### pangu_auto_generate_wiki

从记忆自动生成 Wiki 页面。

**参数**：
- `title` (str, 必填)
- `memory_ids` (list[str], 必填): 使用的记忆 ID
- `use_llm` (bool, 默认 true): 是否使用 LLM

---

## 知识图谱

### pangu_kg_add_entity

添加实体。

**参数**：
- `name` (str, 必填)
- `entity_type` (str, 必填): person/place/concept/...
- `attributes` (dict, 可选)

### pangu_kg_add_relation

添加关系。

**参数**：
- `from_entity` (str, 必填)
- `to_entity` (str, 必填)
- `relation_type` (str, 必填)
- `weight` (float, 0-1, 默认 0.5)

### pangu_kg_query

图谱查询（BFS 路径）。

**参数**：
- `from_entity` (str, 必填)
- `to_entity` (str, 可选)
- `max_depth` (int, 默认 3)

### pangu_kg_neighbors

获取邻居。

**参数**：
- `entity` (str, 必填)
- `depth` (int, 默认 1)

---

## LMM 处理

### pangu_summarize

总结记忆。

**参数**：
- `memory_ids` (list[str], 必填)
- `max_length` (int, 默认 500)

### pangu_classify

分类记忆。

**参数**：
- `content` (str, 必填)
- `categories` (list[str], 可选)

**返回**：
```json
{
  "hall": "hall_facts",
  "importance": 4,
  "tags": ["python", "llm"]
}
```

### pangu_insight

提取洞察。

**参数**：
- `memory_ids` (list[str], 必填)

---

## 伏羲移植模块

### pangu_fts_search

FTS5 混合搜索（RRF 融合）。

**参数**：
- `query` (str, 必填)
- `wing` / `room` / `limit` / `vector_weight`

### pangu_holographic_encode

将记忆编码为 5 维投影。

### pangu_holographic_search

全息跨维度融合检索。

### pangu_judge_memory

LLM A/B/C 三级价值判断。

### pangu_wm_push / pangu_wm_get / pangu_wm_stats / pangu_wm_clear

工作记忆操作。

### pangu_sanitize

3 级记忆脱敏。

### pangu_reconsolidate

再巩固记忆。

### pangu_find_resonance / pangu_cross_wing_resonance

情感/语义共鸣发现。

### pangu_distill_knowledge / pangu_distill_causal_chains

知识蒸馏。

### pangu_attention_state / pangu_attention_switch

注意力系统管理。

### pangu_verify / pangu_verify_phase

6 阶段质量验证。

### pangu_privacy_stats / pangu_privatize_count

差分隐私。

---

## 服务器管理

### pangu_system_health

深度健康检查（DB/嵌入/统计）。

### pangu_system_metrics

Prometheus 格式指标。

### pangu_config_get / pangu_config_set / pangu_config_reload

配置管理（支持热更新）。

### pangu_schema_version / pangu_schema_migrations

数据库 schema 迁移管理。

### pangu_autonomous_analyze

任务复杂度分析。

### pangu_api_server_start

启动 API 服务器。

---

## 完整列表

工具总数：**80+**

详见 [mcp_server.py](../../pangu/server/mcp_server.py)。
