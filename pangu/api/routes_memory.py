"""盘古 REST API 路由 — /api/v2/memories（伏羲移植）"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from pangu.api.abac import (
    Environment as AbacEnvironment,
)
from pangu.api.abac import (
    RequestContext as AbacRequestContext,
)
from pangu.api.abac import (
    Resource as AbacResource,
)
from pangu.api.abac import (
    Subject as AbacSubject,
)
from pangu.api.abac import (
    authorize as abac_authorize,
)
from pangu.api.abac import (
    evaluate as abac_evaluate,
)
from pangu.api.rbac import get_principal
from pangu.core.config import PanguConfig, config
from pangu.core.palace import Drawer, Palace
from pangu.memory.decay import purge_below_floor
from pangu.memory.fts_search import FTS5SearchEngine
from pangu.memory.ingestion import remember
from pangu.memory.layers import MemoryStack
from pangu.memory.retrieval import recall, recall_context

logger = logging.getLogger("pangu.api.memories")
router = APIRouter(tags=["memories"])


# ── 请求/响应模型 ──


class MemoryCreateRequest(BaseModel):
    text: str = Field(..., description="记忆文本内容")
    wing: str = Field(default="default", description="Wing 名称")
    room: str = Field(default="general", description="Room 名称")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="重要性 (0-1)")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    source: str = Field(default="direct", description="来源类型")
    author: str = Field(default="", description="写入者 agent_id")
    created_by: str = Field(default="system", description="创建者")
    # ABAC 字段
    classification: int = Field(
        default=1, ge=0, le=3, description="密级 0=public,1=internal,2=confidential,3=top_secret"
    )
    visibility: str = Field(default="tenant", description="public|tenant|private")


class MemoryUpdateRequest(BaseModel):
    text: str | None = Field(default=None, description="更新后的文本")
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = Field(default=None)
    facts: str | None = Field(default=None, description="提取的事实")


class MemoryResponse(BaseModel):
    id: str
    content: str
    wing: str
    room: str
    importance: float
    tags: list[str]
    created_at: str
    metadata: dict = Field(default_factory=dict)


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: dict | list | None = None

    @classmethod
    def ok(cls, data=None) -> dict:
        return {"code": 0, "message": "ok", "data": data}

    @classmethod
    def error(cls, code: int, message: str) -> dict:
        return {"code": code, "message": message, "data": None}


# ── ABAC 辅助函数 ──


def _memory_stack(request: Request) -> MemoryStack:
    """从 app.state 拿 MemoryStack 实例。"""
    stack = getattr(request.app.state, "memory", None)
    if stack is None:
        # P0-0 修复：兜底必须也走**权威记忆路径**（v2），与
        # server.py 的 app.state.memory 保持一致。
        #
        # 此前兜底是 `MemoryStack(config=PanguConfig())` —— 默认 config 的
        # palace_path 指向 v1，读的是空的 `palace/drawers.json`。于是同一个
        # 进程内，正常路径（app.state.memory，v2）和兜底路径（v1）会给出
        # **两个不同的答案**：接口时好时坏、列表为空，且完全不报错。
        from pangu.core.config import PanguConfig

        base = PanguConfig()
        stack = MemoryStack(
            config=base.authoritative_memory_config(),
            extra_drawers_files=base.authoritative_extra_drawers_files(),
        )
    return stack


def _authoritative_cfg() -> "PanguConfig":
    """按**当前环境**解析一份指向权威（v2）存储的 config。

    为什么不用模块级 `config` 单例：它在 `pangu.core.config` 被 import 时
    就构造好了（`config = PanguConfig()`），此后环境变化（HOME 变更、
    测试隔离、运维换库）都不会反映到它上面。线上服务因为启动时 HOME 固定，
    看不出差别；但在**测试隔离**与**同进程多库切换**场景下，
    单例会指向一个与 `_memory_stack()` 兜底路径**不同**的库，
    于是同一进程内两个接口给出两个答案——正是 P0-0 的缺陷形态。
    这里每次重新解析，与 `_memory_stack()` 保持一致。
    """
    base = PanguConfig()
    return base.authoritative_memory_config()


def _tenant_from_key(request: Request) -> dict:
    """从请求携带的**盘古钥匙**解析租户身份（与 MCP 侧同一张钥匙表）。

    REST 与 MCP 必须是同一套租户语义：租户由凭据（钥匙的 room）决定，调用方无法声明。
    返回 {"key_id", "room", "scope"}；无凭据或钥匙无效 → {}。
    """
    raw = (request.headers.get("X-API-Key") or "").strip()
    if not raw:
        auth = request.headers.get("Authorization") or ""
        if auth[:7].lower() == "bearer ":
            raw = auth[7:].strip()
    if not raw:
        return {}
    try:
        from pangu.keys import KeyManager

        return KeyManager().verify(raw) or {}
    except Exception as e:  # noqa: BLE001 — 解析失败按"无凭据"处理（下面的优先级会兜底）
        logger.debug(f"REST 租户解析失败: {e}")
        return {}


def _is_admin_request(request: Request) -> bool:
    """是否携带 admin 凭据（管理动作才允许代指定租户）。"""
    try:
        from pangu.api.routes_keys import _verify_admin

        return bool(_verify_admin(request))
    except Exception:  # noqa: BLE001
        return False


def _resolve_tenant_id(request: Request) -> str:
    """解析调用方租户。

    ★ 优先级（P1-3 阶段 3 收口；此前的实现**直接采信客户端声明的头** —— 实测带
    `x-tenant-id: dsh` 就能读到 dsh 的 124 条记忆，是跨租户旁路）：

      1. 请求携带的**盘古钥匙**（X-API-Key / Bearer）→ 钥匙的 room。权威来源，与 MCP 一致；
      2. **管理员**（admin 凭据）→ 允许用 `abac_tenant_header` 代指定租户（管理动作）；
      3. 其它情况 → **忽略**该头并告警（客户端无权声明租户）；
      4. 兜底：JWT claim 的 tenant_id → abac_default_tenant。
    """
    # 中间件若已用盘古钥匙确认身份（含租户），直接采信，避免重复查表
    principal = get_principal(request)
    if principal.method == "pangu_key" and principal.tenant:
        return principal.tenant

    ident = _tenant_from_key(request)
    if ident.get("room"):
        return ident["room"]

    hdr_name = config.abac_tenant_header
    declared = (request.headers.get(hdr_name) or "").strip()
    if declared:
        if _is_admin_request(request):
            return declared
        logger.warning(
            f"忽略客户端声明的 {hdr_name}={declared!r}：租户必须由凭据（X-API-Key）决定。"
            "管理员如需代指定租户，请携带 admin 凭据。"
        )

    principal = get_principal(request)
    if principal.method == "jwt" and principal.claims is not None:
        extra = getattr(principal.claims, "extra", {}) or {}
        return extra.get("tenant_id", config.abac_default_tenant)
    return config.abac_default_tenant


def _coerce_classification(value) -> int:
    """密级归一化为 int（0=public…3=secret），非法/字符串值按 0 处理。

    ⚠ 记忆写入路径曾把 classification 写成字符串（如 "normal"，存量 13 条），
    而这里原是 int(md.get("classification", 0)) —— 遇到这些行会 ValueError。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, min(3, value))
    try:
        return max(0, min(3, int(str(value).strip() or 0)))
    except (TypeError, ValueError):
        return 0


def _drawer_to_resource(d) -> AbacResource:
    """从记忆抽屉抽取 ABAC Resource 字段。"""
    md = getattr(d, "metadata", None) or {}
    if isinstance(md, dict) is False:
        md = {}
    return AbacResource(
        type="memories",
        id=getattr(d, "id", ""),
        owner_id=md.get("owner_id", "") if isinstance(md.get("owner_id", ""), str) else "",
        tenant_id=md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default",
        classification=_coerce_classification(md.get("classification")),
        visibility=md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private",
    )


def _dict_to_resource(d: dict) -> AbacResource:
    """从 dict 形式（recall_by_ids 返回）构造 ABAC Resource。"""
    md = d.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    return AbacResource(
        type="memories",
        id=d.get("id", ""),
        owner_id=md.get("owner_id", "") if isinstance(md.get("owner_id", ""), str) else "",
        tenant_id=md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default",
        classification=_coerce_classification(md.get("classification")),
        visibility=md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private",
    )


def _abac_evaluate_subject(request: Request, action: str, resource: AbacResource):
    """按当前 principal + tenant 构造 ctx 并 evaluate。"""
    principal = get_principal(request)
    tid = _resolve_tenant_id(request)
    subject = AbacSubject.from_principal(principal, tenant_id=tid)
    # 不再用客户端声明的头覆盖 subject —— tid 已由 _resolve_tenant_id 按凭据裁决
    env = AbacEnvironment(
        client_ip=request.client.host if request.client else "",
        method=request.method,
        path=str(request.url.path),
    )
    ctx = AbacRequestContext(subject=subject, action=action, resource=resource, environment=env)
    return abac_evaluate(ctx), subject


# ── 路由 ──


@router.get("/memories")
async def list_memories(
    request: Request,
    wing: str = Query(default="default", description="Wing 名称"),
    room: str = Query(default=None, description="Room 名称"),
    author: str = Query(default=None, description="按 author 筛选"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at", description="排序字段"),
):
    """列出记忆（ABAC：按 tenant 隔离 + 公开资源可跨租户）。从 MemoryStack 读取。"""
    try:
        stack = _memory_stack(request)
        drawers = stack.get_drawers() or []
        if room:
            drawers = [d for d in drawers if getattr(d, "room", "") == room]
        # author 过滤
        if author:
            drawers = [d for d in drawers if getattr(d, "author", "") == author]
        # tenant 隔离
        tid = _resolve_tenant_id(request)
        principal = get_principal(request)
        subject = AbacSubject.from_principal(principal, tenant_id=tid)
        # 同上：subject.tenant_id 只用 _resolve_tenant_id 的裁决结果
        if not subject.is_admin:
            filtered = []
            for d in drawers:
                md = getattr(d, "metadata", None) or {}
                if not isinstance(md, dict):
                    md = {}
                vis = md.get("visibility", "private") if isinstance(md.get("visibility", "private"), str) else "private"
                d_tid = md.get("tenant_id", "default") if isinstance(md.get("tenant_id", "default"), str) else "default"
                if vis == "public" or d_tid == subject.tenant_id:
                    filtered.append(d)
            drawers = filtered
        total = len(drawers)
        drawers = drawers[offset : offset + limit]
        items = []
        for d in drawers:
            md = getattr(d, "metadata", None) or {}
            items.append(
                {
                    "id": getattr(d, "id", ""),
                    "content": getattr(d, "content", ""),
                    "wing": getattr(d, "wing", ""),
                    "room": getattr(d, "room", ""),
                    "importance": getattr(d, "importance", 0.5),
                    "tags": getattr(d, "tags", []),
                    "metadata": md if isinstance(md, dict) else {},
                    "created_at": getattr(d, "created_at", ""),
                }
            )
        return ApiResponse.ok(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "tenant_id": subject.tenant_id,
            }
        )
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories")
async def create_memory(req: MemoryCreateRequest, request: Request):
    """创建记忆（ABAC：tenant 隔离 + 密级 + 所有权 + 公开可访问性）。"""
    tid = _resolve_tenant_id(request)
    principal = get_principal(request)
    if principal.method == "anonymous":
        return ApiResponse.error(401, "Authentication required")
    resource = AbacResource(
        type="memories",
        id="",
        owner_id=principal.user_id,
        tenant_id=tid,
        classification=req.classification,
        visibility=req.visibility,
    )
    decision, subject = _abac_evaluate_subject(request, "write", resource)
    if not decision.allowed:
        return ApiResponse.error(403, f"ABAC deny: {decision.reason}")

    item_id, drawer = remember(
        raw_text=req.text,
        wing=req.wing,
        room=req.room,
        importance=req.importance,
        tags=req.tags,
        source=req.source,
        author=req.author,
        created_by=req.created_by,
    )
    if drawer is not None:
        drawer.metadata = dict(drawer.metadata or {})
        drawer.metadata.update(
            {
                "owner_id": principal.user_id,
                "tenant_id": subject.tenant_id,
                "classification": req.classification,
                "visibility": req.visibility,
            }
        )
        try:
            stack = _memory_stack(request)
            stack.add_drawer(drawer)
        except Exception as e:
            logger.warning(f"add_drawer failed: {e}")
    return ApiResponse.ok(
        {
            "id": item_id,
            "content": drawer.content if drawer else req.text,
            "wing": req.wing,
            "room": req.room,
            "tenant_id": subject.tenant_id,
            "owner_id": principal.user_id,
            "policy": decision.policy,
        }
    )


@router.get("/memories/search")
async def search_memories(
    q: str = Query(..., description="搜索关键词"),
    wing: str = Query(default=None, description="限定 Wing"),
    limit: int = Query(default=10, ge=1, le=50),
    search_type: str = Query(default="fts", description="搜索类型: fts/hybrid/vector"),
):
    """搜索记忆"""

    def _do_search():
        # P0-0 修复：读**权威路径** v2（此前读 v1 → 恒返回空）。
        # 本路由无鉴权依赖、匿名可打，是"搜索恒为空"的用户可见症状来源。
        #
        # 注意这里**不用**模块级 `config` 单例：它是 import 时构造的
        # （`pangu/core/config.py` 末尾 `config = PanguConfig()`），
        # 一旦进程启动后 HOME/环境变化（或测试隔离），它就永远冻结在旧值。
        # 用 `_authoritative_cfg()` 每次按当前环境解析，行为与
        # `_memory_stack()` 的兜底路径一致。
        _cfg = _authoritative_cfg()
        _raw = PanguConfig.load_drawers_nonempty(_cfg.authoritative_drawers_path)
        if not _raw:
            return []
        from pangu.core.palace import Drawer as _Drawer

        all_drawers = [_Drawer.from_dict(d) for d in _raw]

        # B7-c：用全量建索引（不要用 wing 过滤后的子集，否则会覆盖磁盘上的全量索引）
        fts_engine = FTS5SearchEngine(_cfg)
        fts_engine.build_index(all_drawers)

        # 搜索时再按 wing 过滤
        search_drawers = all_drawers
        if wing:
            search_drawers = [d for d in all_drawers if d.wing == wing]

        fts_results = fts_engine._fts_search(q, search_drawers, limit=limit)
        drawer_map = {d.id: d for d in search_drawers}
        results = []
        for did, score in sorted(fts_results.items(), key=lambda x: x[1], reverse=True)[:limit]:
            d = drawer_map.get(did)
            if not d:
                continue
            results.append(
                {
                    "id": d.id,
                    "content": d.content,
                    "wing": d.wing,
                    "room": d.room,
                    "importance": d.importance,
                    "tags": d.tags,
                    "search_score": round(score, 4),
                }
            )
        return results

    try:
        results = await asyncio.to_thread(_do_search)
        return ApiResponse.ok(
            {
                "query": q,
                "results": results,
                "total": len(results) if results else 0,
            }
        )
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/stats")
async def get_stats():
    """获取记忆统计（含搜索、健康、token）"""
    try:
        # ⚠ 此处**刻意**保留 v1 `config.palace_path`，不要改成权威路径。
        #
        # 取证（本机独立实测，两份 palace_meta.json 都存在但内容不同）：
        #   v1 ~/.pangu/palace/palace_meta.json              1081 B  mtime 04:03
        #      20 个键，含 room_descriptions / experience_bank / memory_tiers 等
        #      真实业务状态；rooms = {'default': ['general']} ⇒ stats() rooms=1
        #   v2 ~/.pangu/pangu.db/v2_memories/palace_meta.json  166 B  mtime 05:54
        #      仅 6 个骨架键；rooms = {} ⇒ stats() rooms=0
        #
        # 判据：v1 那份是**真实存量**（1081 B、结构完整、含房间描述），
        # v2 那份是**空壳**（166 B、rooms 为空）。改读 v2 只会让
        # `rooms_count` 从 1 掉到 0，退化成假统计。
        # 与 `pangu stats` 一致：只重定向记忆栈，不动 Palace/Wiki/KG。
        palace = Palace(config.palace_path)
        stats = palace.stats()

        # 搜索统计
        try:
            from pangu.memory.retrieval import get_search_history, get_search_stats

            stats["search"] = get_search_stats()
            stats["search"]["recent_history"] = get_search_history(limit=5)
        except Exception:
            pass

        # 健康检查（P0-0 修复：必须走权威路径 v2）
        # 此前 `MemoryStack(config)` 传全局 config（v1）→ `health_check()` 读
        # 空的 v1 drawers.json → 线上实测返回
        #   {"drawers_file": {"exists": true, "size_kb": 0.0, "count": 0}, "status": "degraded"}
        # 即**健康检查因为读空库而自报降级**，是用户可见的错误状态；
        # 而同一时刻 v2 实际有 68 条。
        try:
            from pangu.memory.layers import MemoryStack

            stack = MemoryStack(config=_authoritative_cfg())
            stats["health"] = stack.health_check()
        except Exception:
            pass

        # Token 统计（P0-0 修复：token 数直接取**权威路径** v2 的内容）
        # 注：此处**不构造 MemoryStack**。早期代码在区块开头有 `stack = MemoryStack(config)`
        # 但整个区块从未使用它（token 数来自下面的 load_drawers_nonempty）——
        # 那是个读 v1 却不产生任何作用的死赋值，只会让下一个人误判这里的路径语义。
        # 已删除。
        try:
            from pangu.memory.layers import _estimate_tokens

            raw_drawers = PanguConfig.load_drawers_nonempty(_authoritative_cfg().authoritative_drawers_path)
            if raw_drawers:
                total_tokens = sum(_estimate_tokens(d.get("content", "")) for d in raw_drawers)
                stats["tokens"] = {
                    "total": total_tokens,
                    "avg_per_memory": round(total_tokens / max(len(raw_drawers), 1)),
                }
        except Exception:
            pass

        # 生命周期状态（last_consolidation）
        try:
            from pangu.memory.lifecycle import LifecycleManager

            lifecycle = LifecycleManager(config)
            stats["consolidation"] = {
                "last_consolidation": lifecycle._last_consolidation if lifecycle._last_consolidation else None,
                "last_index_rebuild": lifecycle._last_index_rebuild if lifecycle._last_index_rebuild else None,
            }
        except Exception:
            pass

        return ApiResponse.ok(stats)
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    """获取单条记忆（ABAC：按 mid 加载资源，authorize 后返回）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    md = getattr(drawer, "metadata", None) or {}
    if not isinstance(md, dict):
        md = {}
    res = _drawer_to_resource(drawer)
    decision = abac_authorize(
        "memories",
        "read",
        resource_loader=lambda ctx: res,
    )(request)
    return ApiResponse.ok(
        {
            "id": drawer.id,
            "content": drawer.content,
            "wing": drawer.wing,
            "room": drawer.room,
            "importance": drawer.importance,
            "tags": drawer.tags,
            "metadata": md,
            "created_at": getattr(drawer, "created_at", ""),
            "_policy": decision.policy,
        }
    )


@router.put("/memories/{memory_id}")
async def update_memory(memory_id: str, req: MemoryUpdateRequest, request: Request):
    """更新记忆（ABAC：owner_or_admin / admin_full）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    res = _drawer_to_resource(drawer)
    abac_authorize(
        "memories",
        "write",
        resource_loader=lambda ctx: res,
    )(request)

    drawer.content = req.text if req.text is not None else drawer.content
    if req.importance is not None:
        drawer.importance = req.importance
    if req.tags is not None:
        drawer.tags = req.tags
    if req.facts is not None:
        drawer.metadata["facts"] = req.facts
    drawer.metadata["updated_at"] = datetime.now().isoformat()
    # P0-1 缺口 2：用 update_drawer 替代 add_drawer（后者会创建重复条目）
    stack.update_drawer(drawer)
    return ApiResponse.ok(
        {
            "id": drawer.id,
            "content": drawer.content,
            "wing": drawer.wing,
            "room": drawer.room,
            "importance": drawer.importance,
            "tags": drawer.tags,
            "metadata": drawer.metadata,
        }
    )


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    """删除记忆（ABAC：owner_or_admin / admin_full）。"""
    stack = _memory_stack(request)
    drawer = stack.get_drawer_by_id(memory_id)
    if drawer is None:
        return ApiResponse.error(404, f"Memory not found: {memory_id}")
    res = _drawer_to_resource(drawer)
    decision = abac_authorize(
        "memories",
        "delete",
        resource_loader=lambda ctx: res,
    )(request)
    stack.remove_drawer(memory_id)
    return ApiResponse.ok({"id": memory_id, "deleted": True, "policy": decision.policy})


@router.get("/memories/context")
async def get_context(
    drawer_id: str = Query(default="default", description="抽屉 ID"),
    budget: int = Query(default=2000, ge=100, le=10000),
):
    """获取上下文记忆"""
    try:
        context = recall_context(budget=budget)
        return ApiResponse.ok(
            {
                "context": context,
                "budget": budget,
                "item_count": len(context) if context else 0,
            }
        )
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories/decay")
async def trigger_decay():
    """触发记忆衰减"""
    try:
        from pangu.memory.decay import decay_batch

        all_drawers = recall()
        if all_drawers:
            drawers = [Drawer.from_dict(d) for d in all_drawers]
            result = decay_batch(drawers)
            return ApiResponse.ok(result)
        return ApiResponse.ok({"decayed": 0, "message": "no memories to decay"})
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.post("/memories/purge")
async def purge_low_memories(threshold: float = Query(default=0.15, ge=0.0, le=1.0)):
    """清除低于阈值的记忆"""
    try:
        all_drawers = recall()
        if all_drawers:
            drawers = [Drawer.from_dict(d) for d in all_drawers]
            result = purge_below_floor(drawers, threshold)
            return ApiResponse.ok(result)
        return ApiResponse.ok({"purged": 0})
    except Exception as e:
        return ApiResponse.error(500, str(e))


@router.get("/memories/export")
async def export_memories(
    wing: str = Query(default=None),
    format: str = Query(default="json"),
):
    """导出记忆数据"""
    try:
        results = recall(wing=wing)
        return ApiResponse.ok(
            {
                "format": format,
                "items": results,
                "total": len(results) if results else 0,
                "exported_at": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        return ApiResponse.error(500, str(e))
