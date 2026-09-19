"""盘古 MCP Handler — memory_ops (4 tools)"""

import json
import uuid

from ...core.palace import Drawer

TOOLS = [
    {
        "name": "pangu_add_memory",
        "description": "添加记忆片段。⚠️ 强制：完成有意义的工作后必须调用此工具记录学到了什么、踩了什么坑、下次怎么做。不记录 = 白做。",
    },
    {
        "name": "pangu_search_memories",
        "description": "搜索记忆。⚠️ 强制：每次收到用户消息后必须先调用此工具搜索相关历史，再执行任务。不搜索 = 可能重复踩坑。",
    },
    {"name": "pangu_recall", "description": "按 Wing/Room 回忆记忆"},
    {"name": "pangu_wake_up", "description": "获取 L0+L1 唤醒上下文"},
    {
        "name": "pangu_delete_memory",
        "description": "按 memory_id 硬删除记忆（不可逆，本地自动备份）",
    },
    {
        "name": "pangu_archive_memory",
        "description": "按 memory_id 归档记忆（移出正常搜索/recall，可经 pangu_get_archive 查看）",
    },
    {
        "name": "pangu_set_classification",
        "description": "调整已有记忆的密级（0=公开/1=内部/2=机密/3=绝密）—— 解密级与升级的唯一通道。只能改本租户、且自己当前读得到的记忆；目标密级会被钳到调用方自身的 clearance。",
    },
    {
        "name": "pangu_set_source",
        "description": "给记忆补来源指针（source_file / source_session）—— 解「缺来源」导致的准入死结（毕业要求有来源，缺来源的记忆被召回验证过也永远毕不了业）。补上后重新过准入门：满足条件即自动毕业进全平台只读区。只能改本租户、且自己读得到的记忆；已有来源不覆盖（只补不删）。支持单条 memory_id 或批量 memory_ids。",
    },
]

HANDLERS = {}


async def handle_add_memory(server, drawers, arguments):
    """添加记忆片段（P0-1 缺口 2：接入 remember() 管道）

    修复前：直接创建 Drawer + add_drawer()，绕过脱敏/去重/冲突检测。
    修复后：走 remember() 全管道，与 REST 通道行为一致。
    """
    from ...memory.ingestion import remember
    from ...memory.layers import _coerce_classification, clamp_classification, current_clearance

    # P1-3：身份提取必须在 remember() 之前（admission_gate Q3 检查 source_session）
    identity = arguments.get("_identity", {})

    # remember() 的契约是 0.0–1.0（旧默认 3.0 属 1–5 量纲，会让写入 100% 失败）
    importance = arguments.get("importance", 0.5)
    if not isinstance(importance, (int, float)):
        importance = Drawer._coerce_float(importance, 0.5)

    # 溯源指针：调用方传了 source_session 就用；没传就从身份回退（key_id + room）
    # 保证 admission_gate Q3"支撑"检查不会因缺溯源而卡死毕业通路
    source_session = arguments.get("source_session", "")
    if not source_session and identity:
        source_session = f"key:{identity.get('key_id', 'unknown')}@{identity.get('room', 'unknown')}"

    # 走 remember() 全管道（脱敏 → 去重 → 冲突检测 → supersede → 版本链）
    item_id, drawer = remember(
        raw_text=arguments.get("content", ""),
        wing=arguments.get("wing", "default"),
        room=arguments.get("room", "general"),
        importance=importance,
        tags=arguments.get("tags", []),
        source="mcp",
        created_by="mcp",
        source_session=source_session,
    )

    # 设置 MCP 特有的 metadata（owner_id / tenant_id 等）
    if drawer is not None:
        drawer.metadata = dict(drawer.metadata or {})
        drawer.metadata["owner_id"] = arguments.get("owner_id", "mcp_user")
        drawer.metadata["tenant_id"] = identity.get("room", arguments.get("tenant_id", "default"))
        # 密级是**数值** 0=public…3=secret（与 ABAC 的 Resource.classification 同一套）。
        # 此前默认写成字符串 "normal"，而 REST/ABAC 侧按 int 读取 → 遇到这些行会 ValueError。
        #
        # 钳制：写入方标定的密级**不得超过自己的 clearance**（否则低密级调用方能把数据
        # 标成绝密，谁都读不了 —— 等于自锁）。超限部分静默收敛到自身密级并告警。
        requested = _coerce_classification(arguments.get("classification", 0))
        granted = clamp_classification(requested)
        if granted != requested:
            logger.warning(f"密级 {requested} 超过调用方 clearance {current_clearance()}，已钳制为 {granted}")
        drawer.metadata["classification"] = granted
        # P1-3 收尾：用 setdefault 语义，门禁已决定 visibility 时以门禁为准。
        #
        # 默认值是 "tenant" 而不是 "private" —— 二者在 api/abac.py 里是**两档**：
        #   tenant  = 同租户（房间）可见，同屋的多把钥匙互相可见 ← MCP 写入的合理默认
        #   private = 仅属主那把钥匙可见（需要 owner_key_id 判据）
        #   public  = 所有租户可见（毕业区）
        # 曾经把这三档误读成"命名不一致"，这里写清楚，别再合并。
        drawer.metadata.setdefault("visibility", arguments.get("visibility", "tenant"))
        # private 档的判据来源：记住写入方是哪把钥匙
        if identity.get("key_id"):
            drawer.metadata.setdefault("owner_key_id", identity["key_id"])
        # P1-3：remember() 不落盘（只创建 Drawer 对象），handler 的 add_drawer 才是唯一落盘点

        # ── 记忆进化（2026-09-20 修）：必须在 add_drawer **之前**完成，
        # 因为 add_drawer 是唯一落盘点 —— 落在它之后设的 source/quality 不写盘。
        # 且旧记忆替换必须作用在**真实 Drawer 对象**上并 update_drawer 落盘，
        # 此前 related 来自 d.to_dict() 副本，改副本等于空转（实测：快照生成了、
        # 但旧记忆的 version/quality 全未变化）。
        try:
            from ...memory.evolution import get_memory_evolution

            evolution = get_memory_evolution()

            # 来源平台：优先身份里的 platform，其次 room，最后 mcp
            drawer.source = identity.get("platform", "") or identity.get("room", "") or "mcp"

            new_quality = evolution.evaluate_memory_quality(drawer.to_dict())

            all_drawers = server.memory._drawers if hasattr(server.memory, "_drawers") else []
            related_payload = [d.to_dict() for d in all_drawers]
            related = evolution.find_related_memories(drawer.to_dict(), related_payload)

            by_id = {d.id: d for d in all_drawers}
            replaced_count = 0
            for old_mem in related:
                old_quality = evolution.evaluate_memory_quality(old_mem)
                # 每次写入最多替换 1 条，避免一次写入触发最多 5 条快照（无界增长）
                if replaced_count >= 1:
                    break
                if not evolution.should_replace(new_quality, old_quality):
                    continue
                old_id = old_mem.get("id", "")
                target = by_id.get(old_id)
                if target is None:
                    continue
                evolution.save_snapshot(
                    old_mem,
                    replaced_by=drawer.id,
                    reason=f"新记忆质量({new_quality:.2f})优于旧记忆({old_quality:.2f})",
                )
                # 真实对象：版本 +1、记录质量分与替换者，然后落盘
                target.metadata = dict(target.metadata or {})
                target.metadata["version"] = int(target.metadata.get("version", 1)) + 1
                target.metadata["quality_score"] = round(new_quality, 4)
                target.metadata["replaced_by"] = drawer.id
                server.memory.update_drawer(target)
                replaced_count += 1
                logger.info(f"记忆进化: {old_id} v{target.metadata['version']} 由 {drawer.id} 续写")

            drawer.metadata["quality_score"] = round(new_quality, 4)
            drawer.metadata["version"] = 1
            drawer.metadata["snapshot_count"] = evolution.get_snapshot_count(drawer.id)
        except Exception as e:
            logger.debug(f"记忆进化失败（不影响写入）: {e}")

        server.memory.add_drawer(drawer)

    try:
        from ...memory.autonomous import on_memory_written

        on_memory_written()
    except Exception:
        pass
    try:
        from ...memory.memory_events import get_event_stream

        get_event_stream(server.config).emit_memory_write(item_id, drawer.content, drawer.wing)
    except Exception:
        pass

    return json.dumps(
        {
            "drawer_id": item_id,
            "wing": drawer.wing,
            "room": drawer.room,
            "supersedes": drawer.metadata.get("supersedes", []),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_add_memory"] = handle_add_memory


async def handle_search_memories(server, drawers, arguments):
    """搜索记忆（P1-3 阶段 2.2：按 metadata.tenant_id 过滤 + public 毕业区）"""
    query = arguments.get("query", "")
    wing = arguments.get("wing")
    room = arguments.get("room")

    # P1-3 阶段 2.2：有身份时预过滤 drawers（隔离轴是 metadata.tenant_id，不是 Drawer.room）
    identity = arguments.get("_identity", {})
    if identity:
        identity_room = identity.get("room", "")
        filtered = [
            d
            for d in drawers
            if (
                (d.metadata or {}).get("tenant_id", "") == identity_room
                or (d.metadata or {}).get("visibility", "") == "public"
            )
        ]
        drawers = filtered

    from time import perf_counter as _perf_counter

    _t0 = _perf_counter()
    results = server.search.search(query, drawers, wing=wing, room=room)
    try:
        from ...memory.encryption import decrypt

        items = results.get("results", results) if isinstance(results, dict) else results
        if isinstance(items, list):
            for r in items:
                if isinstance(r, dict):
                    for key in ("content", "highlighted"):
                        c = r.get(key, "")
                        if c and c.startswith("gAAAAAB"):
                            try:
                                r[key] = decrypt(c)
                            except Exception:
                                pass
    except Exception:
        pass
    # 统一返回格式：{"results": [...], "total": N}
    if isinstance(results, list):
        payload = {"results": results, "total": len(results), "query": query}
    else:
        payload = results

    # 结果质量自检（2026-09-19）：语义搜索修好打分后，无关查询的 Top1 只有
    # 0.19-0.31（相关查询 0.36+）。若全部低于阈值，显式告诉调用方"没有高度
    # 相关的记忆"——而不是硬凑 10 条不相关的让它猜。结果照常返回供参考。
    try:
        _items = payload.get("results", []) if isinstance(payload, dict) else []
        _scores = [r.get("score") for r in _items if isinstance(r, dict) and isinstance(r.get("score"), (int, float))]
        if _items and all(not r.get("relevant", True) for r in _items if isinstance(r, dict)):
            payload["no_strong_match"] = True
            payload["note"] = (
                f"未找到与查询高度相关的记忆（最高相似度 {max(_scores):.2f}，"
                f"低于可信阈值 0.32）；以下为最接近的条目，仅供参考"
            )
    except Exception:
        pass

    # 访问反馈（2026-09-19 接线）：命中即记 access_count/last_accessed ——
    # 衰减任务的 touch 因子读 last_accessed（常用记忆不再衰减）、自适应遗忘读
    # access_count（常用记忆不被归档）。此前 access_count 全仓无写入方，
    # "使用信号"完全断裂。批量一次落盘（record_access 走 update_drawers_bulk）。
    try:
        _hit_ids = [
            r["id"]
            for r in (payload.get("results", []) if isinstance(payload, dict) else [])
            if isinstance(r, dict) and r.get("id") and r.get("relevant", True)
        ]
        if _hit_ids:
            server.memory.record_access(_hit_ids)
    except Exception:
        pass

    # 搜索分析（2026-09-19 接线）：SearchAnalytics 的 log_search 与 4 个分析工具
    # （热门查询/空搜索/慢搜索）早就实现，但记录端从未被调用 —— analytics 文件
    # 一直为空，分析工具全部返回空数据。这里接入主搜索入口。
    try:
        from ...memory.search_analytics import get_search_analytics

        _n = len(payload.get("results", [])) if isinstance(payload, dict) else 0
        get_search_analytics().log_search(
            query,
            _n,
            (_perf_counter() - _t0) * 1000,
            user_id=(identity.get("room") if isinstance(identity, dict) else "") or "default",
        )
    except Exception:
        pass

    return json.dumps(payload, ensure_ascii=False, default=str)


HANDLERS["pangu_search_memories"] = handle_search_memories


async def handle_recall(server, drawers, arguments):
    """按 Wing/Room 回忆记忆（P1-3 阶段 2.2：按 metadata.tenant_id 过滤）"""
    wing = arguments.get("wing")
    room = arguments.get("room")

    # P1-3 阶段 2.2：有身份时预过滤 drawers
    identity = arguments.get("_identity", {})
    if identity:
        identity_room = identity.get("room", "")
        filtered = [
            d
            for d in drawers
            if (
                (d.metadata or {}).get("tenant_id", "") == identity_room
                or (d.metadata or {}).get("visibility", "") == "public"
            )
        ]
        drawers = filtered

    # 必须把过滤后的集合传进去：recall 默认只读自身存储，不传等于隔离空转
    result = server.memory.recall(wing=wing, room=room, drawers=drawers)

    # 发布召回事件（/ws）—— 面板「7 日脉搏」的召回序列按天计数依赖它。
    # 盘古只存每条记忆的 access_count 累计值，没有"哪天召回了几次"的历史（events 目录为空），
    # 事件是唯一可聚合的来源。观测用途，失败不影响召回结果本身。
    try:
        from ...memory.realtime import get_connection_manager

        await get_connection_manager().emit(
            "memory_recall",
            {"wing": wing or "", "room": room or ""},
        )
    except Exception:
        pass

    # 记忆内容在盘上是加密的（Fernet，密文以 gAAAAAB 开头）。search 路径会逐条解密，
    # 而 recall 直接把这些密文拼进 Markdown 返回 —— 调用方拿到的是不可读的乱码
    # （实测 dsh 钥匙 recall 出 [general] gAAAAABqqp5v4dO3…）。这里做同样的解密。
    try:
        import re as _re

        from ...memory.encryption import decrypt

        def _decrypt_match(m: "_re.Match[str]") -> str:
            try:
                return decrypt(m.group(0))
            except Exception:
                return m.group(0)

        result = _re.sub(r"gAAAAAB[\w\-=]+", _decrypt_match, result)
    except Exception:
        pass

    return result


HANDLERS["pangu_recall"] = handle_recall


async def handle_wake_up(server, drawers, arguments):
    """获取 L0+L1 唤醒上下文"""
    wing = arguments.get("wing")
    return server.memory.wake_up(wing=wing)


HANDLERS["pangu_wake_up"] = handle_wake_up


async def handle_delete_memory(server, drawers, arguments):
    """硬删除记忆（按 memory_id，自动备份 + 向量索引同步，R4-B）"""
    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "参数缺失: memory_id 为必填"}, ensure_ascii=False)
    drawer = server.memory.get_drawer_by_id(memory_id)
    if not drawer:
        return json.dumps({"code": 2001, "error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)
    removed = server.memory.remove_drawer(memory_id)
    if not removed:
        return json.dumps({"code": 2004, "error": f"删除失败: {memory_id}"}, ensure_ascii=False)
    return json.dumps({"status": "removed", "memory_id": memory_id, "removed": True}, ensure_ascii=False)


HANDLERS["pangu_delete_memory"] = handle_delete_memory


async def handle_archive_memory(server, drawers, arguments):
    """归档记忆（按 memory_id：持久化归档 → 从正常搜索/recall 排除，R4-C）"""
    from ...memory.adaptive_forgetting import get_forgetting

    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "参数缺失: memory_id 为必填"}, ensure_ascii=False)
    drawer = server.memory.get_drawer_by_id(memory_id)
    if not drawer:
        return json.dumps({"code": 2001, "error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)

    af = get_forgetting(server.config)
    entry = af.archive_memory(drawer)
    removed = server.memory.remove_drawer(memory_id)
    if not removed:
        return json.dumps({"code": 2004, "error": f"归档失败: {memory_id}"}, ensure_ascii=False)

    return json.dumps(
        {
            "status": "archived",
            "memory_id": memory_id,
            "archived_at": entry["archived_at"],
            "wing": entry["wing"],
            "room": entry["room"],
            "archive_count": af.get_forgetting_stats().get("archive_size", len(af.get_archive(limit=10**6))),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_archive_memory"] = handle_archive_memory


async def handle_set_classification(server, drawers, arguments):
    """调整已有记忆的密级（解密级 / 升级）—— **密级变更的唯一通道**。

    为什么需要专门通道：此前已有记忆要调低密级，只能用高密级钥匙把整条重写一遍（会丢
    supersede 链、访问计数等派生信息），或走系统视角（绕过鉴权）。

    权限模型（三条，缺一不可）：

    1. **读得到**：先按当前作用域读，`get_drawer_by_id` 已受租户轴 + 密级轴双重保护，
       读不到＝不存在。所以低密级调用方**够不着**高密级记忆 —— 不能解密级自己看不见的
       东西（否则"猜 id"就能把别人的机密数据刷成公开）。
    2. **是自己的**：只能改本租户的（作用域为空＝系统/admin，跳过）。否则 A 能读到 B 的
       public 记忆，就能把 B 的数据再降级 —— 那是越权。
    3. **钳到自身 clearance**：不能一步标成绝密（与写入同策略）。解密级天然满足本条：
       能读到说明 clearance >= 当前密级 >= 目标密级。
    """
    from ...memory.layers import (
        _coerce_classification,
        clamp_classification,
        current_clearance,
        current_tenant,
    )

    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps({"code": 2002, "error": "参数缺失: memory_id 为必填"}, ensure_ascii=False)
    if arguments.get("classification") is None:
        return json.dumps(
            {
                "code": 2002,
                "error": "参数缺失: classification 为必填（0=公开/1=内部/2=机密/3=绝密）",
            },
            ensure_ascii=False,
        )

    drawer = server.memory.get_drawer_by_id(memory_id)
    if not drawer:
        return json.dumps({"code": 2001, "error": f"记忆不存在: {memory_id}"}, ensure_ascii=False)

    tenant = current_tenant()
    if tenant and (drawer.metadata or {}).get("tenant_id", "") != tenant:
        return json.dumps(
            {"code": 2003, "error": f"无权修改该记忆的密级（不属于本租户）: {memory_id}"},
            ensure_ascii=False,
        )

    requested = _coerce_classification(arguments.get("classification"))
    old = _coerce_classification((drawer.metadata or {}).get("classification"))
    new = clamp_classification(requested)  # 钳到自身 clearance

    drawer.metadata = dict(drawer.metadata or {})
    drawer.metadata["classification"] = new
    # update_drawer 是单条替换（内部以 _load_drawers() 全库快照为基底），
    # 不会把租户裁剪后的列表整份写回 —— 写路径安全的既有保证。
    if not server.memory.update_drawer(drawer):
        return json.dumps({"code": 2004, "error": f"密级更新失败: {memory_id}"}, ensure_ascii=False)

    # 审计：密级变更是敏感操作（尤其解密级＝把数据变公开），必须留痕。
    # 留痕失败不阻断主流程 —— 它是"最好有"，不能因此让功能不可用。
    try:
        from ...memory.audit_analytics import get_audit

        get_audit(server.config).log("set_classification", memory_id)
    except Exception:
        pass

    return json.dumps(
        {
            "status": "updated",
            "memory_id": memory_id,
            "classification": new,
            "previous": old,
            "direction": "declassify" if new < old else ("escalate" if new > old else "unchanged"),
            "clamped": new != requested,
            "caller_clearance": current_clearance(),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_set_classification"] = handle_set_classification


async def handle_set_source(server, drawers, arguments):
    """给记忆补来源指针（source_file / source_session）—— 解「缺来源」的准入死结。

    为什么需要：毕业（admission=graduated → visibility=public 进全平台只读区）要求
    has_source 与 has_positive_feedback **同时**成立；缺来源的记忆即使被召回验证过也
    永远毕不了业 —— 面板上那 16 条实证死结（把"待验证"数字永远占住）。此前只能重写
    整条记忆（丢 supersede 链/访问计数等派生信息）。

    权限模型（与 pangu_set_classification 一致的三条）：
    1. **读得到**：get_drawer_by_id 已受租户轴 + 密级轴双重保护，读不到＝不存在；
    2. **是自己的**：只能改本租户（作用域为空＝系统/admin，跳过）；
    3. **只补不删**：只允许「从无到有」，不覆盖已有来源 —— 否则可以拿它伪造来历。

    补上后**重新过准入门**（复用 ingestion._admission_gate 单点判定）：若此刻四问全过
    （有来源 + 有正向反馈）则自动毕业；仍缺反馈的保持 pending_review（等使用信号）。
    """
    from ...memory.ingestion import _admission_gate
    from ...memory.layers import current_tenant

    mem_ids = arguments.get("memory_ids") or []
    mem_id = arguments.get("memory_id", "")
    if mem_ids:
        if not isinstance(mem_ids, list):
            return json.dumps({"code": 2002, "error": "参数错误: memory_ids 应为数组"}, ensure_ascii=False)
        ids = [str(x) for x in mem_ids if x][:200]  # 单次上限 200 条
    elif mem_id:
        ids = [str(mem_id)]
    else:
        ids = []
    if not ids:
        return json.dumps(
            {"code": 2002, "error": "参数缺失: memory_id 或 memory_ids 至少给一个"},
            ensure_ascii=False,
        )

    src_file = str(arguments.get("source_file") or "").strip()
    src_session = str(arguments.get("source_session") or "").strip()
    if not src_file and not src_session:
        return json.dumps(
            {"code": 2002, "error": "参数缺失: source_file 或 source_session 至少给一个"},
            ensure_ascii=False,
        )

    tenant = current_tenant()
    results = []
    for mid in ids:
        drawer = server.memory.get_drawer_by_id(mid)
        if not drawer:
            results.append({"memory_id": mid, "code": 2001, "error": "记忆不存在"})
            continue
        if tenant and (drawer.metadata or {}).get("tenant_id", "") != tenant:
            results.append({"memory_id": mid, "code": 2003, "error": "无权修改（不属于本租户）"})
            continue

        drawer.metadata = dict(drawer.metadata or {})
        before = {
            "source_file": drawer.source_file or None,
            "source_session": drawer.metadata.get("source_session") or None,
            "admission": drawer.metadata.get("admission"),
        }
        filled, skipped = [], []
        if src_file:
            if not drawer.source_file:
                drawer.source_file = src_file
                filled.append("source_file")
            else:
                skipped.append("source_file")  # 只补不覆盖
        if src_session:
            if not drawer.metadata.get("source_session"):
                drawer.metadata["source_session"] = src_session
                filled.append("source_session")
            else:
                skipped.append("source_session")

        if not filled:
            results.append({"memory_id": mid, "status": "unchanged", "skipped": skipped, "before": before})
            continue

        # 重新过准入门（单点复用）：满足四问 → admission=graduated + visibility=public
        _admission_gate(drawer, None, mid)
        after_admission = drawer.metadata.get("admission")
        # update_drawer 是单条替换（内部以 _load_drawers() 全库快照为基底），写路径安全
        if not server.memory.update_drawer(drawer):
            results.append({"memory_id": mid, "code": 2004, "error": "写回失败"})
            continue

        # 审计：来源指针是毕业判据的一部分（改它 = 影响可见性），留痕；失败不阻断
        try:
            from ...memory.audit_analytics import get_audit

            get_audit(server.config).log("set_source", mid)
        except Exception:
            pass

        results.append(
            {
                "memory_id": mid,
                "status": "updated",
                "filled": filled,
                "skipped": skipped,
                "admission": after_admission,
                "graduated": after_admission == "graduated",
                "before": before,
            }
        )

    updated = sum(1 for r in results if r.get("status") == "updated")
    graduated = sum(1 for r in results if r.get("graduated"))
    return json.dumps(
        {
            "status": "ok" if updated else "noop",
            "total": len(results),
            "updated": updated,
            "graduated": graduated,
            "results": results,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_set_source"] = handle_set_source
