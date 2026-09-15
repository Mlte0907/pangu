# P0-1 实施蓝图 — 冲突治理 → supersede → 检索标记

> **文档目的**：把 P0-1 五项改动精确到 file:line，工程师照搬即可，无需自行勘察。
> 配套验证脚本：`tests/test_p0_1_supersede.py`（must-block / must-allow / 异常 / 注入验证四件套）。
>
> **上游依据**：`docs/PLAN-v0.3.0.md:126-143` P0-1 章节。
> **上下文规则**：`pangu/AGENTS.md` 已规定测试隔离（conftest 的 PANGU_BASE_DIR / PANGU_CACHE_DIR / monkeypatch）。
>
> **编写**：researcher 任务 t1（attempt a433c846-…）
> **状态**：完整、已校对行号；待工程师按表逐项落实。

---

## 0. 现状（已勘察，逐行核对）

### 0.1 关键现状 1：drawer_storage / MemoryStack 都没有 `update` 接口

| 组件 | 接口 | 备注 |
|---|---|---|
| `pangu/memory/drawer_storage.py:46-52`（`DrawerStorage` 基类） | `load / save / close` | 没有 `update(id, drawer)` |
| `pangu/memory/drawer_storage.py:100-119`（`JsonDrawerStorage.save`） | 全表 `json.dump + os.replace` | 原子写，但**全量** |
| `pangu/memory/drawer_storage.py:252-303`（`SqliteDrawerStorage.save`） | `DELETE FROM drawers` + 批量 `INSERT` | 同上，全量 |
| `pangu/memory/drawer_storage.py:305-356`（`save_incremental`） | 按 id 集合删 + 插 | **结构上是 update，但只对一组 id 调用** |
| `pangu/memory/layers.py:549-555`（`MemoryStack.add_drawer`） | `append`（不去重！） | 直接 `add_drawer(已存在的 id)` 会产生重复行 |
| `pangu/memory/layers.py:617-650`（`remove_drawer / remove_drawers`） | 过滤后 `_save_drawers` | 也不更新指定 id 的内容 |

**结论**：**没有** `update(id, drawer)` 或 `update_drawer(drawer)` 接口。

**！冲突标注**：`pangu/api/routes_memory.py:514` 的现有 `update_memory` 用 `stack.add_drawer(drawer)` 实现"更新"，但 `add_drawer` 不去重 → 该接口会**产生重复行**（这是个独立潜伏 bug，不在 P0-1 范围内）。

**对策**（见 §1.2）：**新增 `MemoryStack.update_drawer(drawer)`**，复用 `save_incremental` 的思路（按 id 替换）。**需要把 `pangu/memory/layers.py` 加入 t2 的 inScope**——这是当前任务范围缺口，已在 §6 风险处明确。

### 0.2 关键现状 2：`_detect_conflicts` 只在 NEW drawer 写 `conflicts`，OLD drawer 不动

`pangu/memory/ingestion.py:265-284`：

```python
def _detect_conflicts(drawer: Drawer, existing_drawers: list[Drawer], item_id: str) -> None:
    if existing_drawers and len(existing_drawers) >= CONFLICT_MIN_EXISTING:
        try:
            from pangu.memory.conflict import ConflictDetector
            detector = ConflictDetector()
            conflicts = detector.detect_conflicts([drawer] + existing_drawers[-CONFLICT_LOOKBACK:])
            if conflicts:
                drawer.metadata["conflicts"] = [
                    {
                        "id": c.id,
                        "severity": c.severity.value,
                        "with": c.memory_a if c.memory_b == item_id else c.memory_b,
                    }
                    for c in conflicts[:CONFLICT_MAX_REPORT]
                ]
        except Exception as e:
            logger.debug(f"Conflict detection skipped: {e}")
```

→ 只在 `drawer`（新）metadata 写 conflicts。**OLD drawer 完全不动**。这就是为什么"先写 A → 再写 ¬A"之后，检索两条都返回且无法分辨新旧。

### 0.3 关键现状 3：`versioning.record_version` 当前零调用方

`grep -rn "record_version\|get_version_control" pangu/pangu/ pangu/tests/` 实际输出：

```
pangu/pangu/memory/versioning.py:40   def record_version(...)
pangu/pangu/memory/versioning.py:146  def get_version_control(...)
```

**除自身外零调用方**（layered-state 闲置模块）。需要从 `_detect_conflicts` 或 `remember` 接线。

### 0.4 关键现状 4：`hybrid_search._build_results` 没有 superseded 字段

`pangu/pangu/memory/hybrid_search.py:191-219` 返回的每条结果只有：
```python
{
    "id": mid,
    "content": d.content,
    "wing": d.wing,
    "room": d.room,
    "importance": d.importance,
    "tags": d.tags,
    "created_at": d.created_at,
    "rrf_score": ...,
    "fts_rank": ...,
    "vector_rank": ...,
    "kg_rank": ...,
}
```

→ 没有 `superseded` / `superseded_by` 字段，客户端无据判断新旧。

### 0.5 关键现状 5：search_cache 用 query 作 key，会让"先写 → search → 再写 → search"两次返回相同结果

`pangu/pangu/memory/search_cache.py:27-29`：

```python
def _make_key(self, query: str, modalities: list = None, limit: int = 10) -> str:
    raw = f"{query}|{sorted(modalities or [])}|{limit}"
    return hashlib.md5(raw.encode()).hexdigest()
```

TTL 300s。→ 测试必须用**不同 query** 或 monkeypatch TTL=0 / `search_cache.clear()`，否则"先 search → 再写 → search"拿到的是缓存。

---

## 1. 五项改动（file:line 精确指引）

### 1.1 改动 ① — `_detect_conflicts` 改造（建立 supersedes/superseded_by 关系）

**文件**：`pangu/memory/ingestion.py`
**函数**：`_detect_conflicts`（当前 L265-284）
**调用点**：`remember()` 中 L393 调用 `_detect_conflicts(drawer, existing_drawers, item_id)`。

#### 1.1.1 改造后伪代码骨架

```python
def _detect_conflicts(drawer: Drawer, existing_drawers: list[Drawer], item_id: str, storage=None) -> None:
    """自动冲突检测 → 写 supersedes/superseded_by + 触发旧 drawer 持久化 + 记版本"""
    if not (existing_drawers and len(existing_drawers) >= CONFLICT_MIN_EXISTING):
        return
    try:
        from pangu.memory.conflict import ConflictDetector
        detector = ConflictDetector()
        conflicts = detector.detect_conflicts([drawer] + existing_drawers[-CONFLICT_LOOKBACK:])
        if not conflicts:
            return
        now = datetime.now().isoformat()

        # ① 在新 drawer 写 supersedes 列表（指向所有被取代的旧 id）
        new_supersedes: list[str] = []
        # 同时收集需要回写到旧 drawer 的 (old_id -> new_id) 对
        for c in conflicts[:CONFLICT_MAX_REPORT]:
            old_id = c.memory_a if c.memory_b == item_id else c.memory_b
            new_supersedes.append(old_id)
            # ② 旧 drawer 的 metadata 加 superseded_by
            for d in existing_drawers:
                if d.id == old_id:
                    superseded_by = d.metadata.get("superseded_by", [])
                    if not isinstance(superseded_by, list):
                        superseded_by = []
                    if item_id not in superseded_by:
                        superseded_by.append(item_id)
                    d.metadata["superseded_by"] = superseded_by
                    d.metadata["superseded_at"] = now
                    d.metadata["memory_status"] = "superseded"   # ← 关键标记，让 _build_results 一眼识别
                    # ③ 持久化旧 drawer（依赖 §1.2 的 update_drawer）
                    if storage is not None:
                        try:
                            storage.update_drawer(d)
                        except Exception as e:
                            logger.warning(f"update old drawer failed for {old_id[:8]}: {e}")
                    break
        drawer.metadata["supersedes"] = new_supersedes  # ← 新 drawer 的反向指针

        # 兼容旧字段（向后兼容已有调用方）
        drawer.metadata["conflicts"] = [
            {
                "id": c.id,
                "severity": c.severity.value,
                "with": c.memory_a if c.memory_b == item_id else c.memory_b,
            }
            for c in conflicts[:CONFLICT_MAX_REPORT]
        ]

        # ④ versioning.record_version 接线
        try:
            from pangu.memory.versioning import get_version_control
            vc = get_version_control()
            for old_id in new_supersedes:
                vc.record_version(
                    memory_id=old_id,
                    content=f"superseded by {item_id}",
                    change_type="superseded",
                    metadata={"by": item_id, "at": now},
                )
            vc.record_version(
                memory_id=item_id,
                content=drawer.content,
                change_type="supersede",
                metadata={"supersedes": new_supersedes, "at": now},
            )
        except Exception as e:
            logger.debug(f"Version recording skipped: {e}")

        logger.info(f"Supersede recorded for {item_id[:8]}: replaces {len(new_supersedes)} memories")
    except Exception as e:
        logger.debug(f"Conflict detection skipped: {e}")
```

#### 1.1.2 函数签名变化（向后兼容）

```python
# 旧：def _detect_conflicts(drawer: Drawer, existing_drawers: list[Drawer], item_id: str) -> None:
# 新：def _detect_conflicts(drawer: Drawer, existing_drawers: list[Drawer], item_id: str, storage=None) -> None:
```

#### 1.1.3 调用点改造（ingestion.py L393）

```python
# 旧（仅 L393）：
_detect_conflicts(drawer, existing_drawers, item_id)

# 新：把 storage 也传进去；remember() 当前签名没有 storage 参数，
# 但调用方都在 ingestion 内部（L626-632 的 ingest_batch 路径需同步），
# 因此保持"storage=None 时只写 metadata 不持久化"语义是安全的：
_detect_conflicts(drawer, existing_drawers, item_id, storage=existing_storage_or_none)
```

**当前调用链调研**：
- `ingestion.py:393`（remember）— **唯一直接调用方**
- `ingestion.py:626-632`（ingest_batch 间接）— 通过 `remember` 间接调用
- 其它模块：**没有其它直接调用方**

→ 修改面**只有 ingestion.py:393**。`ingest_batch` 路径不变（参数向后兼容）。

#### 1.1.4 边界条件 / 错误处理

| 场景 | 行为 | 备注 |
|---|---|---|
| `existing_drawers` 少于 `CONFLICT_MIN_EXISTING=3` | 直接返回（已存在） | 行为不变 |
| `detect_conflicts` 抛异常 | `logger.debug` 跳过，不阻塞 remember | 已有 try/except，保留 |
| 同一条 OLD drawer 被多条 NEW 取代 | `superseded_by` 追加（list），不去重 | 设计允许链式取代：A → B → C 都存在时 B/C 都在 A 的 `superseded_by` 里 |
| `storage.update_drawer(d)` 失败 | `logger.warning`，**不抛**，remember 仍返回成功 | 落盘失败不阻塞写入路径；标记 warn 让 reviewer 看得见 |
| `_detect_conflicts` 整体 try/except 命中 | 静默 | 已有，保留 |
| OLD drawer 已被取代（再写 ¬¬A） | 仍写新 supersedes，旧 drawer 的 superseded_by 追加新 id | P0-1 范围内，不做"二次取代清理" |

---

### 1.2 改动 ② — 旧条目持久化（`MemoryStack.update_drawer` 新增）

**文件**：`pangu/memory/layers.py`
**新增函数**：紧接 `add_drawers()` 后（约 L565）

#### 1.2.1 实现

```python
def update_drawer(self, drawer: Drawer) -> bool:
    """按 id 替换抽屉内容（修复 supersede 等场景的落盘）

    复用 save_incremental 的"按 id 集合删除 + 重新插入"思路；
    不同：返回 bool 让调用方知道是否真的替换了某条记录。

    Returns:
        True — 找到了匹配的 id 并完成替换；
        False — 未找到匹配 id（无操作）。
    """
    self._drawers = self._load_drawers()
    found = False
    for i, d in enumerate(self._drawers):
        if d.id == drawer.id:
            self._drawers[i] = drawer
            found = True
            break
    if not found:
        return False
    saved = self._save_drawers()
    if saved:
        self._cache.invalidate()
        # 顺便清掉 search_cache：supsersede 写完后旧 drawer 的 metadata 变了，
        # 之前的查询结果（缓存里可能还把旧 drawer 当"未取代"返回）必须失效。
        try:
            from pangu.memory.search_cache import get_search_cache
            get_search_cache().clear()
        except Exception:
            pass
    else:
        logger.warning(f"update_drawer({drawer.id[:8]}): 内存已替换但落盘被拦截")
    return found
```

#### 1.2.2 边界条件

| 场景 | 行为 | 备注 |
|---|---|---|
| id 不在 `_drawers` | 返回 False，**不**触发 `_save_drawers` | 不写空数据，符合现有空写保护 |
| id 在 `_drawers` 但落盘被空写保护拦截 | `logger.warning`，仍返回 True | 已有保护逻辑 |
| 替换后旧 vector 索引怎么办？ | 当前实现不动 vector_index | supersede 只改 metadata，embedding 不变，索引可继续用 |
| 并发：两个 remember 同时 update 同一 drawer | `MemoryStack._save_drawers` 用 `JsonDrawerStorage` 原子写（os.replace），后写者赢 | 已满足 |

#### 1.2.3 **！需要 captain 扩展 t2 inScope**

`t2` 当前 inScope 不含 `pangu/memory/layers.py`。**强烈建议扩展**：

```
原 inScope: [..., "pangu/memory/ingestion.py", ...]
扩展为:     [..., "pangu/memory/ingestion.py", "pangu/memory/layers.py", ...]
```

仅用于新增 `update_drawer` 一个方法（约 30 行）。**回退方案**（若 captain 拒绝）：在 `_detect_conflicts` 中绕过 `MemoryStack`，直接走 `server.memory._storage`：

```python
# 回退方案（不建议）：越过 MemoryStack
storage = server.memory._storage  # 拿到 JsonDrawerStorage
all_drawers = storage.load()
for i, d in enumerate(all_drawers):
    if d.id == old_id:
        all_drawers[i] = d
storage.save(all_drawers)
```

但这**破坏了 layers.py:458-528 的空写保护**（`_save_drawers` 有 readback 校验，绕过后磁盘上旧数据可能在某些边界下被覆盖成 `[]`）。→ **强烈建议扩展 inScope**。

---

### 1.3 改动 ③ — `hybrid_search` 标注 "⚠ 已被更新"

**文件**：`pangu/memory/hybrid_search.py`
**函数**：`_build_results`（当前 L191-219）

#### 1.3.1 精确插入点（L202 之后，L218 之前）

在 L203（`d = all_ids[mid]`）之后，新增字段：

```python
# 在 _build_results 函数体 L203 之后插入：
superseded = False
superseded_by: list[str] = []
status = d.metadata.get("memory_status") if d.metadata else None
if status == "superseded":
    superseded = True
    by = d.metadata.get("superseded_by", []) if d.metadata else []
    if isinstance(by, list):
        superseded_by = by
```

然后在 dict 里（L204-218）新增 3 个字段：

```python
# 在 results.append({...}) 的 dict 字面量里追加（建议放在 "kg_rank" 之后）：
"superseded": superseded,
"superseded_by": superseded_by,
"warning": "⚠ 已被更新" if superseded else None,
```

#### 1.3.2 完整修改后的 `_build_results`（仅供参照，不要直接覆盖）

```python
def _build_results(
    sorted_ids: list[str],
    all_ids: dict[str, Drawer],
    rrf_scores: dict[str, float],
    fts_ranks: dict[str, int],
    vector_ranks: dict[str, int],
    kg_ranks: dict[str, int],
    limit: int,
) -> list[dict]:
    """构建结果列表"""
    results = []
    for mid in sorted_ids[:limit]:
        d = all_ids[mid]
        superseded = False
        superseded_by: list[str] = []
        if d.metadata:
            status = d.metadata.get("memory_status")
            if status == "superseded":
                superseded = True
                by = d.metadata.get("superseded_by", [])
                if isinstance(by, list):
                    superseded_by = by
        results.append(
            {
                "id": mid,
                "content": d.content,
                "wing": d.wing,
                "room": d.room,
                "importance": d.importance,
                "tags": d.tags,
                "created_at": d.created_at,
                "rrf_score": round(rrf_scores[mid], 6),
                "fts_rank": fts_ranks.get(mid),
                "vector_rank": vector_ranks.get(mid),
                "kg_rank": kg_ranks.get(mid),
                "superseded": superseded,                   # ← 新增
                "superseded_by": superseded_by,             # ← 新增
                "warning": "⚠ 已被更新" if superseded else None,  # ← 新增
            }
        )
    return results
```

#### 1.3.3 边界条件

| 场景 | 行为 |
|---|---|
| `metadata` 为空 / 没有 `memory_status` | `superseded=False, warning=None`（与旧行为一致） |
| `memory_status == "superseded"` 但没有 `superseded_by` | `superseded=True, superseded_by=[]`（不报错） |
| `superseded_by` 不是 list（历史脏数据） | 用 `isinstance(by, list)` 兜底，非 list 视为 `[]` |
| ONNX/embedding 失败导致 query 没向量 | 与旧行为一致（仅 FTS 命中） |

---

### 1.4 改动 ④ — `versioning.record_version` 接线

**文件**：`pangu/memory/ingestion.py`
**位置**：**已经在 §1.1 的伪代码里嵌入**，无需独立改动。

#### 1.4.1 接线点

```python
# 在 _detect_conflicts 改造版的尾部（伪代码 §1.1.1 末尾）：
try:
    from pangu.memory.versioning import get_version_control
    vc = get_version_control()
    for old_id in new_supersedes:
        vc.record_version(
            memory_id=old_id,
            content=f"superseded by {item_id}",
            change_type="superseded",
            metadata={"by": item_id, "at": now},
        )
    vc.record_version(
        memory_id=item_id,
        content=drawer.content,
        change_type="supersede",
        metadata={"supersedes": new_supersedes, "at": now},
    )
except Exception as e:
    logger.debug(f"Version recording skipped: {e}")
```

#### 1.4.2 接线理由

- 旧 drawer 的 record_version 标记"被 X 取代"（不存原内容，节省内存）
- 新 drawer 的 record_version 标记"取代了哪些"
- 配合 §1.5 的 `pangu_get_supersede_chain` 能给出完整变更链

#### 1.4.3 边界条件

| 场景 | 行为 |
|---|---|
| `get_version_control` 抛 ImportError（理论上不会） | logger.debug 跳过 |
| `record_version` 抛异常 | 同上，整个 try/except 兜住 |
| 同一 old_id 被多次 supersede | `record_version` 内部按 version_num 累加（`versioning.py:47`），正常 |

---

### 1.5 改动 ⑤ — 新 MCP 工具 `pangu_get_supersede_chain`

**新增文件**：`pangu/server/handlers/supersede.py`
**注册文件**：`pangu/server/handlers/__init__.py`（在 L106 后或合适位置加 import + extend）

#### 1.5.1 `pangu/server/handlers/supersede.py`（新文件，建议 ~80 行）

```python
"""盘古 MCP Handler — supersede (1 tool)
追踪 P0-1 supersede 关系的变更链
"""

import json

TOOLS = [
    {
        "name": "pangu_get_supersede_chain",
        "description": "获取某条记忆的 supersede 变更链（含 supersedes / superseded_by 与 versioning 历史）",
    },
]

HANDLERS = {}


async def handle_get_supersede_chain(server, drawers, arguments):
    """获取记忆的 supersede 链

    Input:
      {
        "memory_id": "<必填>",   # 任意方向都可：可传入旧 id 或新 id
        "direction": "both" | "forward" | "backward"  # 默认 both
      }

    Output:
      {
        "memory_id": "<入参 id>",
        "found": true | false,
        "chain": [                  # supersede 关系链（按时间排序）
          {"id": ..., "content_preview": ..., "created_at": ..., "role": "root|old|new",
           "supersedes": [...], "superseded_by": [...]}
        ],
        "versions": [               # 来自 versioning 引擎
          {"version": int, "change_type": str, "timestamp": str,
           "metadata": {...}}
        ],
        "depth": int                # 链上节点数（不含当前节点）
      }
    """
    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "memory_id is required"}, ensure_ascii=False)

    direction = arguments.get("direction", "both")
    if direction not in ("both", "forward", "backward"):
        direction = "both"

    target = server.memory.get_drawer_by_id(memory_id)
    if target is None:
        return json.dumps(
            {"memory_id": memory_id, "found": False, "chain": [], "versions": [], "depth": 0},
            ensure_ascii=False,
        )

    # BFS：forward = 沿 superseded_by 追新；backward = 沿 supersedes 追旧
    visited: set[str] = {memory_id}
    chain_nodes: list[dict] = []

    def _to_node(d, role):
        meta = d.metadata or {}
        return {
            "id": d.id,
            "content_preview": (d.content or "")[:80],
            "created_at": d.created_at,
            "role": role,
            "supersedes": meta.get("supersedes", []),
            "superseded_by": meta.get("superseded_by", []),
        }

    chain_nodes.append(_to_node(target, "root"))

    # backward: 沿 supersedes 找更早的版本
    if direction in ("both", "backward"):
        queue = list((target.metadata or {}).get("supersedes", []))
        while queue:
            old_id = queue.pop(0)
            if old_id in visited:
                continue
            visited.add(old_id)
            old_d = server.memory.get_drawer_by_id(old_id)
            if old_d is None:
                continue
            chain_nodes.append(_to_node(old_d, "old"))
            queue.extend((old_d.metadata or {}).get("supersedes", []))

    # forward: 沿 superseded_by 找更新的版本
    if direction in ("both", "forward"):
        queue = list((target.metadata or {}).get("superseded_by", []))
        while queue:
            new_id = queue.pop(0)
            if new_id in visited:
                continue
            visited.add(new_id)
            new_d = server.memory.get_drawer_by_id(new_id)
            if new_d is None:
                continue
            chain_nodes.append(_to_node(new_d, "new"))
            queue.extend((new_d.metadata or {}).get("superseded_by", []))

    # versions from versioning 引擎
    versions: list[dict] = []
    try:
        from ...memory.versioning import get_version_control
        vc = get_version_control()
        for v in vc.get_versions(memory_id):
            versions.append(
                {
                    "version": v.version,
                    "change_type": v.change_type,
                    "timestamp": v.timestamp,
                    "metadata": v.metadata,
                }
            )
        # 顺带把链上每个 id 的 version 也带上
        for n in chain_nodes:
            for v in vc.get_versions(n["id"]):
                versions.append(
                    {
                        "memory_id": n["id"],
                        "version": v.version,
                        "change_type": v.change_type,
                        "timestamp": v.timestamp,
                        "metadata": v.metadata,
                    }
                )
    except Exception:
        pass

    return json.dumps(
        {
            "memory_id": memory_id,
            "found": True,
            "chain": chain_nodes,
            "versions": versions,
            "depth": len(chain_nodes) - 1,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_get_supersede_chain"] = handle_get_supersede_chain
```

#### 1.5.2 `pangu/server/handlers/__init__.py` 注册

在 L106（`from . import wiki`）后追加：

```python
from . import supersede

TOOLS.extend(supersede.TOOLS)
HANDLERS.update(supersede.HANDLERS)
```

并把 `pangu_get_supersede_chain` 加进 `_TOOL_SCHEMAS`（L224-289）的精确参数 schema：

```python
"pangu_get_supersede_chain": {
    "type": "object",
    "properties": {
        "memory_id": {"type": "string", "description": "记忆 id（必填）"},
        "direction": {
            "type": "string",
            "enum": ["both", "forward", "backward"],
            "description": "追踪方向，默认 both",
            "default": "both",
        },
    },
    "required": ["memory_id"],
},
```

#### 1.5.3 边界条件 / 错误处理

| 场景 | 返回 |
|---|---|
| `memory_id` 缺失 | `{"code": 2002, "error": "memory_id is required"}` |
| `memory_id` 不存在 | `{"memory_id": ..., "found": false, "chain": [], "depth": 0}` |
| `direction` 非法值 | 回退到 `"both"` |
| BFS 出现环（理论上不应有，但防御） | `visited` 集合去重，**不死循环** |
| 链上某 id 在 storage 里被删了 | `get_drawer_by_id` 返回 None，`continue` 跳过 |
| `versioning.get_version_control` 抛异常 | try/except 兜住，`versions=[]` 不阻断 chain |

---

## 2. 测试清单（`tests/test_p0_1_supersede.py`，新文件）

> 测试隔离已由 `pangu/tests/conftest.py:32-148` 处理（autouse fixtures 隔离 PANGU_BASE_DIR / PANGU_CACHE_DIR / 单例）。
> 不需要再 monkeypatch home；不需要清 production data。
>
> ⚠ **必须**：测试中**使用唯一 query**（例如带 uuid 后缀），否则 search_cache（300s TTL）会让"先 search → 再写 → search"两次拿到同一缓存（详见 §0.5）。

### 2.1 必须阻止的（must-block）

| 用例名 | 准备 | 操作 | 断言 |
|---|---|---|---|
| `test_supersede_writes_metadata_to_old_drawer` | 用 `remember()` 写 A | 再写 ¬A | `get_drawer_by_id(A_id).metadata["superseded_by"]` 包含 ¬A 的 id；`memory_status == "superseded"` |
| `test_supersede_persists_old_drawer_to_storage` | 同上 | `JsonDrawerStorage(...).load()` | 重载出来的 OLD drawer metadata 与 `get_drawer_by_id` 一致（说明 update_drawer 真正落盘） |
| `test_supersede_new_drawer_has_supersedes_list` | 同上 | `drawer.metadata["supersedes"]` | 包含 A 的 id |
| `test_hybrid_search_marks_superseded` | 同上 | `hybrid_search(query, drawers, config, limit=10)` | 返回列表里 OLD id 的 `superseded==True, warning=="⚠ 已被更新", superseded_by` 含新 id；NEW id 的 `superseded==False` |
| `test_hybrid_search_results_sorted_newer_first` | 同上 | 同上 | NEW id 的 rrf_score >= OLD id（不一定强排序，但若 NEW 命中 ≥1 路通常排前） |
| `test_versioning_records_supersede` | 同上 | `get_version_control().get_versions(OLD_id)` | 至少 1 条 `change_type=="superseded"`；`NEW_id` 至少 1 条 `change_type=="supersede"` |
| `test_pangu_get_supersede_chain_tool` | 同上 | 通过 MCP handler 模拟调用（直接 import handlers.supersede） | 返回 `found=True`, chain 长度 ≥ 2（root + old 或 root + new），versions 非空 |

### 2.2 必须放行的（must-allow）

| 用例名 | 操作 | 断言 |
|---|---|---|
| `test_remember_without_conflict_unaffected` | 单条 write，无冲突 | drawer.metadata **不**含 `supersedes`；下一次 search 该条 `superseded==False` |
| `test_multiple_old_drawers_superseded_by_one_new` | 写 A1 / A2 / A3 三条互斥，再写 ¬All | A1/A2/A3 的 `superseded_by` 都含 ¬All 的 id；¬All 的 `supersedes` 含 3 个 id |
| `test_chain_supersede_A_to_B_to_C` | 写 A → 写 B（取代 A）→ 写 C（取代 B） | B.superseded_by 含 C.id；A.superseded_by 含 B.id；B.supersedes 含 A.id；C.supersedes 含 B.id |
| `test_get_supersede_chain_backward_forward` | 写 A → B → C | `handle_get_supersede_chain(memory_id=B)` 返回 chain 含 A(old)/B(root)/C(new)；`direction=forward` 只返 B+C；`direction=backward` 只返 A+B |
| `test_get_supersede_chain_nonexistent` | 调 memory_id=INVALID | 返回 `found=False`, 不抛异常 |
| `test_search_cache_cleared_after_update` | 写 A → search(q) → 写 ¬A → search(q)（不同 query 或 monkeypatch TTL=0） | 第二次 search 看到 ¬A 并把 A 标 superseded（**注意**：用唯一 query 避缓存） |

### 2.3 异常 / 边界（异常）

| 用例名 | 准备 | 断言 |
|---|---|---|
| `test_supersede_with_fewer_than_min_existing` | existing_drawers 长度 < CONFLICT_MIN_EXISTING=3 | `_detect_conflicts` 不调用 detector，metadata 不写 supersedes |
| `test_storage_update_failure_does_not_block_remember` | monkeypatch `MemoryStack.update_drawer` 抛 RuntimeError | `remember()` 仍正常返回 item_id；新 drawer metadata 有 supersedes；OLD drawer metadata **不**更新（已被打断），但**不抛**到调用方 |
| `test_detect_conflict_exception_swallowed` | monkeypatch `ConflictDetector.detect_conflicts` 抛 RuntimeError | `remember()` 不抛；新 drawer 无 conflicts/supersedes metadata |
| `test_chain_with_cycle_in_metadata` | 手工构造 A.supersedes=[B.id]、B.supersedes=[A.id]（互指） | handle 不死循环；visited 集合生效 |
| `test_chain_with_missing_linked_drawer` | A.supersedes=[ghost_id]；ghost_id 不存在 | handle 跳过 ghost，chain 长度合理 |

### 2.4 注入验证（regression 守护）

| 用例名 | 操作 | 期望 |
|---|---|---|
| `test_injection_disable_detect_conflicts` | monkeypatch `pangu.memory.ingestion._detect_conflicts` 为 no-op | `test_supersede_writes_metadata_to_old_drawer` **必须失败**（确认没有这段逻辑 supersede 就断了） |
| `test_injection_disable_hybrid_warning` | 把 `_build_results` 里 `warning` 字段删掉 | `test_hybrid_search_marks_superseded` **必须失败** |
| `test_injection_disable_storage_update` | monkeypatch `MemoryStack.update_drawer` 抛 NotImplementedError | `test_supersede_persists_old_drawer_to_storage` **必须失败** |
| `test_injection_disable_chain_handler` | 把 handlers/__init__.py 的 supersede 注册去掉 | `test_pangu_get_supersede_chain_tool` **必须失败**（handler 缺失 → KeyError） |

---

## 3. 测试关键脚手架要点（避免常见坑）

### 3.1 写完数据后必须 reload 才能验证持久化

```python
def test_supersede_persists_old_drawer_to_storage(tmp_path, monkeypatch):
    # 已经由 conftest 隔离 tmp_path 到 PANGU_BASE_DIR / PANGU_DB_PATH
    from pangu.memory.layers import MemoryStack
    from pangu.memory.ingestion import remember
    from pangu.core.config import PanguConfig

    config = PanguConfig.load()
    stack = MemoryStack(config=config)

    # 1) 写 A
    old_id, _ = remember("原始事实 X", wing="test", room="t", importance=0.5)
    # conftest 已 autouse 隔离，直接用全局单例即可；不需要重建 stack。

    # 2) 写 ¬A（需 CONFLICT_MIN_EXISTING=3 条已有 → 再写 2 条 filler）
    remember("填充 1", wing="test", room="t", importance=0.3)
    remember("填充 2", wing="test", room="t", importance=0.3)
    new_id, _ = remember("原始事实 X 是错误的，正确是 ¬X", wing="test", room="t", importance=0.7)

    # 3) 从磁盘重载（模拟重启），确保 update_drawer 真的写盘了
    from pangu.memory.drawer_storage import JsonDrawerStorage
    storage = JsonDrawerStorage(str(config.palace_path / "drawers.json"))
    on_disk = {d.id: d for d in storage.load()}
    assert new_id in on_disk
    assert old_id in on_disk
    assert on_disk[old_id].metadata.get("memory_status") == "superseded"
    assert on_disk[new_id].metadata.get("supersedes") == [old_id]
```

### 3.2 search_cache 必须避坑（最常见的 flaky 原因）

```python
# 选项 A：用唯一 query（推荐）
import uuid
q = f"原始事实 X-{uuid.uuid4().hex[:8]}"

# 选项 B：monkeypatch TTL=0
from pangu.memory import search_cache
monkeypatch.setattr(search_cache._cache, "_ttl", 0) if search_cache._cache else None
# 或更彻底：
from pangu.memory.search_cache import get_search_cache
get_search_cache().clear()
```

### 3.3 验证 hybrid_search 标注（必须直连 `_build_results`，或清缓存后再走 hybrid_search）

```python
def test_hybrid_search_marks_superseded():
    # ... 写 A / 填充 / 写 ¬A（与 §3.1 同）

    # 用 hybrid_search 走真实路径
    from pangu.memory.hybrid_search import hybrid_search
    from pangu.memory.search_cache import get_search_cache
    get_search_cache().clear()  # 必清

    config = PanguConfig.load()
    drawers = MemoryStack(config).get_drawers()
    results = hybrid_search(q, drawers, config=config, limit=20)
    by_id = {r["id"]: r for r in results}

    assert by_id[new_id]["superseded"] is False
    assert by_id[new_id]["warning"] is None
    if old_id in by_id:
        assert by_id[old_id]["superseded"] is True
        assert by_id[old_id]["warning"] == "⚠ 已被更新"
        assert new_id in by_id[old_id]["superseded_by"]
```

### 3.4 验证 MCP 工具（不需要起 server，直接调 handler）

```python
import asyncio
from pangu.server.handlers.supersede import handle_get_supersede_chain

class _FakeServer:
    class memory:
        @staticmethod
        def get_drawer_by_id(mid):
            from pangu.memory.layers import MemoryStack
            from pangu.core.config import PanguConfig
            return MemoryStack(PanguConfig.load()).get_drawer_by_id(mid)
    config = None

async def _run(mid):
    return await handle_get_supersede_chain(_FakeServer(), [], {"memory_id": mid})

result = json.loads(asyncio.run(_run(old_id)))
assert result["found"] is True
assert any(n["role"] == "old" for n in result["chain"])
```

---

## 4. 端到端验证（verify 段）

t2.verify 列了 4 条命令。补充说明：

### 4.1 pytest 全量

```bash
cd /home/xiaoxin/pangu && .venv/bin/python -m pytest tests/ -q
```

预期：基线 + 新测试全部通过。**0 failed** 是 reviewer 验收红线。

### 4.2 ruff 双检

```bash
~/.local/bin/uv tool run ruff@latest check pangu/ tests/
~/.local/bin/uv tool run ruff@latest format --check pangu/ tests/
```

预期：全绿。注意 `pangu/server/handlers/supersede.py` 是新文件，必须通过 ruff。

### 4.3 注入验证（t2 已要求，t3 也要独立跑一次）

```bash
# 1) 备份
cp pangu/pangu/memory/ingestion.py /tmp/ingestion.py.bak
# 2) 把 _detect_conflicts 整体注释 / 替换为 pass
# 3) 跑测试，必须失败
.venv/bin/python -m pytest tests/test_p0_1_supersede.py -q
# 4) 恢复
cp /tmp/ingestion.py.bak pangu/pangu/memory/ingestion.py
# 5) 复跑，必须通过
.venv/bin/python -m pytest tests/test_p0_1_supersede.py -q
```

### 4.4 端到端 MCP 调用（pangu_get_supersede_chain + 3 个相关工具）

```bash
# 假设已有 memory_id，写入：A → filler×2 → ¬A；最后查 chain
# 用上面 verify 段给的 curl 模板（pangu/api/server.py:612 streamable-HTTP）
curl -s -X POST http://127.0.0.1:19529/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pangu_get_supersede_chain","arguments":{"memory_id":"<OLD_id>"}}}'
```

预期：返回 `found: true, chain 含 ≥2 节点, versions 非空`。

---

## 5. 文件改动清单（一图看完）

| # | 文件 | 改动类型 | 行数估计 |
|---|---|---|---|
| 1 | `pangu/memory/ingestion.py` | 改造 `_detect_conflicts`（§1.1） | ~50 行（含注释） |
| 2 | `pangu/memory/layers.py` | **新增** `MemoryStack.update_drawer`（§1.2） | ~30 行（**需 inScope 扩展**） |
| 3 | `pangu/memory/hybrid_search.py` | `_build_results` 加 superseded 字段（§1.3） | ~10 行 |
| 4 | `pangu/memory/versioning.py` | 无改动（接线在 ingestion.py，§1.4） | 0 |
| 5 | `pangu/server/handlers/supersede.py` | **新增文件**（§1.5） | ~110 行 |
| 6 | `pangu/server/handlers/__init__.py` | 注册 supersede handler（§1.5.2） | ~5 行 |
| 7 | `tests/test_p0_1_supersede.py` | **新增文件**（§2） | ~350 行 |

合计 **~555 行** 改动 / 新增。

---

## 6. 风险 / 待 captain 决策

### 6.1 **必须**扩展 t2 inScope（**最高优先级**）

t2 当前 inScope：
```
pangu/memory/ingestion.py
pangu/memory/hybrid_search.py
pangu/memory/versioning.py
pangu/server/handlers/supersede.py
pangu/server/handlers/__init__.py
tests/test_p0_1_supersede.py
```

**缺少** `pangu/memory/layers.py`（§1.2 的 `update_drawer`）。

**建议扩展为**：
```
..., "pangu/memory/layers.py", ...
```

仅限新增 `update_drawer` 一个方法。

**回退方案**（若拒绝扩展）：见 §1.2.3 末尾的"越过 MemoryStack" hack（**强烈不建议**：破坏空写保护）。

### 6.2 已有潜伏 bug（不在 P0-1 范围）

- `pangu/api/routes_memory.py:514` 用 `stack.add_drawer(drawer)` 做更新 → 实际产生重复行
- 该 bug 修复**不**在 t2 inScope 内（routes_memory.py 是 outOfScope）
- 若 reviewer 在 t3 阶段发现，可单独建 P1-X 修

### 6.3 缓存与时序

- `MemoryStack.update_drawer` 末尾 `get_search_cache().clear()` 是**全表清**（搜结果缓存只有 ~200 条，不敏感）。也可改为更精确的 key-by-query 失效，但实现复杂度不值。
- `versioning._versions` 是**进程内**字典（`versioning.py:37`），重启即丢。P0-1 范围内不持久化（与现有架构一致）。

### 6.4 无回归影响

- `_detect_conflicts` 的 try/except 已在（L283-284），即使 §1.1 的所有改动整体抛异常也不会阻塞 `remember()`
- `_build_results` 仅追加 3 个字段，老调用方读 `result["id"]`/`result["content"]` 不受影响
- 新 MCP 工具 `pangu_get_supersede_chain` 是独立模块，老 tools/list 不丢
- `pangu_detect_conflicts` 行为不变（仍按冲突检测返回，不带 supersede 语义）

---

## 7. 验证完成判据

t1 完成 = 本文件存在 + 5 段改造方案 + 测试清单 + 风险标注。 ✅
t2 完成 = 上述 7 个文件改动 + pytest 0 failed + ruff 双绿 + 注入验证 4 条全过。
t3 完成 = 独立跑 §4 的全部 verify 段；production data 未污染。

---

**结束**。工程师可照 §1 逐项落实；如遇范围问题先回 §6.1。
