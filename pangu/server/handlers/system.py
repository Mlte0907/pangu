"""盘古 MCP Handler — system (44 tools)"""

import json
from datetime import datetime, timedelta

TOOLS = [
    {"name": "pangu_stats", "description": "\u83b7\u53d6\u7cfb\u7edf\u7edf\u8ba1"},
    {"name": "pangu_graph", "description": "\u5bfc\u51fa\u77e5\u8bc6\u56fe\u8c31"},
    {"name": "pangu_identity", "description": "\u83b7\u53d6/\u8bbe\u7f6e AI \u8eab\u4efd"},
    {
        "name": "pangu_system_health",
        "description": "\u6df1\u5ea6\u7cfb\u7edf\u5065\u5eb7\u68c0\u67e5\uff08DB/\u7ed3\u6784/\u5d4c\u5165/\u7edf\u8ba1\uff09",
    },
    {"name": "pangu_system_metrics", "description": "\u83b7\u53d6 Prometheus \u683c\u5f0f\u7cfb\u7edf\u6307\u6807"},
    {"name": "pangu_config_get", "description": "\u83b7\u53d6\u5f53\u524d\u914d\u7f6e"},
    {"name": "pangu_config_set", "description": "\u66f4\u65b0\u914d\u7f6e\u9879"},
    {"name": "pangu_config_reload", "description": "\u70ed\u66f4\u65b0\u914d\u7f6e"},
    {"name": "pangu_schema_version", "description": "\u83b7\u53d6\u6570\u636e\u5e93 schema \u7248\u672c"},
    {"name": "pangu_schema_migrations", "description": "\u5217\u51fa\u6240\u6709\u8fc1\u79fb\u7248\u672c"},
    {"name": "pangu_api_server_start", "description": "\u542f\u52a8 REST API \u670d\u52a1\u5668"},
    {"name": "pangu_graph_infer", "description": "\u57fa\u4e8e\u77e5\u8bc6\u56fe\u8c31\u63a8\u7406"},
    {"name": "pangu_graph_contradictions", "description": "\u68c0\u6d4b\u56fe\u4e2d\u7684\u77db\u76fe\u5173\u7cfb"},
    {"name": "pangu_graph_causal_chain", "description": "\u56e0\u679c\u94fe\u5206\u6790"},
    {"name": "pangu_graph_temporal", "description": "\u65f6\u5e8f\u63a8\u7406"},
    {"name": "pangu_graph_analogy", "description": "\u7c7b\u6bd4\u68c0\u6d4b"},
    {"name": "pangu_graph_visualize", "description": "\u63a8\u7406\u8fc7\u7a0b\u53ef\u89c6\u5316"},
    {"name": "pangu_graph_entity", "description": "\u83b7\u53d6\u5b9e\u4f53\u4fe1\u606f"},
    {"name": "pangu_graph_path", "description": "\u67e5\u627e\u5b9e\u4f53\u95f4\u8def\u5f84"},
    {"name": "pangu_graph_quality", "description": "\u8bc4\u4f30\u56fe\u8c31\u8d28\u91cf"},
    {"name": "pangu_graph_stats", "description": "\u56fe\u8c31\u7edf\u8ba1"},
    {"name": "pangu_project_create", "description": "\u521b\u5efa\u9879\u76ee"},
    {"name": "pangu_project_switch", "description": "\u5207\u6362\u9879\u76ee"},
    {"name": "pangu_project_list", "description": "\u5217\u51fa\u6240\u6709\u9879\u76ee"},
    {"name": "pangu_project_active", "description": "\u83b7\u53d6\u5f53\u524d\u9879\u76ee"},
    {"name": "pangu_project_save", "description": "\u4fdd\u5b58\u8bb0\u5fc6\u5230\u5f53\u524d\u9879\u76ee"},
    {"name": "pangu_project_load", "description": "\u52a0\u8f7d\u9879\u76ee\u8bb0\u5fc6"},
    {"name": "pangu_project_search", "description": "\u8de8\u9879\u76ee\u641c\u7d22"},
    {"name": "pangu_project_merge", "description": "\u5408\u5e76\u9879\u76ee"},
    {"name": "pangu_project_delete", "description": "\u5220\u9664\u9879\u76ee"},
    {"name": "pangu_project_stats", "description": "\u9879\u76ee\u7edf\u8ba1"},
    {"name": "pangu_audit_log", "description": "\u8bb0\u5f55\u5ba1\u8ba1\u65e5\u5fd7"},
    {"name": "pangu_audit_query", "description": "\u67e5\u8be2\u5ba1\u8ba1\u65e5\u5fd7"},
    {"name": "pangu_audit_stats", "description": "\u64cd\u4f5c\u7edf\u8ba1"},
    {"name": "pangu_access_patterns", "description": "\u8bbf\u95ee\u6a21\u5f0f\u5206\u6790"},
    {"name": "pangu_security_summary", "description": "\u5b89\u5168\u6458\u8981"},
    {"name": "pangu_plugin_list", "description": "\u5217\u51fa\u6240\u6709\u63d2\u4ef6"},
    {"name": "pangu_plugin_enable", "description": "\u542f\u7528\u63d2\u4ef6"},
    {"name": "pangu_plugin_disable", "description": "\u7981\u7528\u63d2\u4ef6"},
    {"name": "pangu_plugin_config", "description": "\u83b7\u53d6\u63d2\u4ef6\u914d\u7f6e"},
    {"name": "pangu_plugin_discover", "description": "\u53d1\u73b0\u5e76\u52a0\u8f7d\u81ea\u5b9a\u4e49\u63d2\u4ef6"},
    {"name": "pangu_version_history", "description": "\u83b7\u53d6\u8bb0\u5fc6\u53d8\u66f4\u5386\u53f2"},
    {"name": "pangu_version_compare", "description": "\u6bd4\u8f83\u4e24\u4e2a\u7248\u672c\u7684\u5dee\u5f02"},
    {
        "name": "pangu_graph_visualize_web",
        "description": "\u751f\u6210\u77e5\u8bc6\u56fe\u8c31\u53ef\u89c6\u5316\u9875\u9762URL",
    },
]

HANDLERS = {}


def collect_stats(server, drawers: list | None = None) -> dict:
    """收集系统统计。MCP 的 pangu_stats 与管理通道 /api/v2/admin/stats 共用这一份装配
    （两处各写一遍最容易在加字段时漂移）。

    drawers: 记忆/宫殿数字据此现算。传 None ＝用全库（管理视角，请求外自然就是全库）。

    ⚠ palace.stats() 读的是 Palace 索引 —— 那是历史结构，与 drawers 已经脱节（实测
    索引里 wings=1，而 drawers 里实际有 6 个翼）。所以 wings_count/rooms_count 一律按
    drawers 现算，不能用 palace.stats() 的原始值。
    """
    stats = {
        "palace": server.palace.stats(),
        "memory": server.memory.status(),
        "wiki": server.wiki.stats(),
        "knowledge_graph": server.knowledge_graph.stats(),
    }
    scoped = drawers if drawers is not None else server.memory.get_drawers()
    apply_tenant_view(stats, scoped)
    # 密级分布（管理视角＝全库；租户视角＝自己那份）—— 便于审计"库里有没有高密级数据"
    by_class: dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0}
    for d in scoped:
        by_class[str(_coerce_classification((d.metadata or {}).get("classification")))] += 1
    stats["classification"] = by_class
    # 管线状态（入库审核 / 加密存储 / 夜间巩固）—— 「记忆管线」三格的真实数据源。
    #
    # 为什么必须在这里给：此前那三格在面板里是**硬编码**（审核写死 '—'、巩固写死 '未运行'、
    # 加密错取了高密级数），实测把 57 条待审、62 条已加密全藏了起来，还把"巩固从未运行"
    # 当装饰文案展示。口径与隔离轴共用同一份 scoped 集合 → 租户/管理视角各自自洽。
    pending = sum(1 for d in scoped if (d.metadata or {}).get("admission") == "pending_review")
    # 2026-09-20：写入加密已按 PANGU_ENCRYPTION=off 关闭、存量已迁移明文，
    # 「加密存储」格失去意义，换成「记忆毕业」数（管线语义：待审 → 毕业）。
    graduated = sum(1 for d in scoped if (d.metadata or {}).get("admission") == "graduated")
    decays = [
        float((d.metadata or {}).get("decay_score") or 0.0)
        for d in scoped
        if (d.metadata or {}).get("decay_score") is not None
    ]
    stats["pipeline"] = {
        "pending_review": pending,
        "graduated": graduated,
        "decay_average": round(sum(decays) / len(decays), 3) if decays else 0.0,
        "consolidation": consolidation_state(server),
    }
    # 7 日记忆脉搏（创建柱）：按 created_at 聚合最近 7 天（含今天），零填充、
    # 旧日→今日排列 —— dsh-pangu 概览页「7日记忆脉搏」的创建柱数据源。
    # 为什么在这里给（2026-09-23）：插件原先在自己进程里 readFileSync(palace_path/
    # drawers.json)，那条路径是**服务端**文件系统，盘古上云后跨机读必然 ENOENT、
    # 被静默吞掉 ⇒ 创建柱恒空。改为随 stats 下发，scoped 与其它区块同口径
    # （管理通道=全库，MCP=本租户）。created_at 与本聚合同为服务端本地时钟
    # （Asia/Shanghai），按日切片无时区偏差。
    today = datetime.now().date()
    daily = {(today - timedelta(days=i)).isoformat(): 0 for i in range(6, -1, -1)}
    for d in scoped:
        day = (getattr(d, "created_at", "") or "")[:10]
        if day in daily:
            daily[day] += 1
    stats["daily_creates"] = [{"date": day, "count": count} for day, count in daily.items()]
    return stats


def consolidation_state(server) -> dict:
    """夜间巩固的真实状态（面板管线第三格的数据源）。

    ⚠ 本轮排查发现：`LifecycleManager` 从来没被任何模块引用过（死代码）—— `last_run` 恒为
    0，而面板把"未运行"写成静态文案，看起来像有意为之的装饰。现在如实给字段，并补上调度
    （见 mcp_server 的夜间巩固循环）。
    """
    state = {"last_run": None, "interval_hours": 24.0, "window": "03:00–05:00", "due": True}
    try:
        from ...memory.lifecycle import LifecycleManager

        mgr = LifecycleManager(server.config)
        last = float(getattr(mgr, "_last_consolidation", 0.0) or 0.0)
        state["last_run"] = datetime.fromtimestamp(last).isoformat() if last > 0 else None
        state["interval_hours"] = float(getattr(server.config, "consolidation_interval_hours", 24.0) or 24.0)
        state["due"] = bool(mgr.needs_consolidation())
    except Exception as exc:  # 状态文件读不到不该让整个 stats 失败
        state["error"] = str(exc)[:120]
    return state


def apply_tenant_view(stats: dict, drawers: list) -> None:
    """把 memory / palace 两个区块的数字换成**调用方租户可见集合**现算的值（就地修改）。

    为什么需要：这两个区块原先直接取 server.memory.status() / server.palace.stats()，
    两者都读全库，于是面板拿到全库视角、越过 call_tool 的租户收口（实测 dsh 钥匙下
    total_memories=124，而同一进程内 pangu_analyze 已按租户报 1）。

    面板若要**全库**视角，不走 MCP 这条路，而是走管理通道 /api/v2/admin/stats
    （admin secret 鉴权，见 api/routes_keys.py 的 admin_stats）。
    """
    mem = stats.get("memory")
    if isinstance(mem, dict):
        by_wing: dict[str, int] = {}
        for d in drawers:
            wing = d.wing or "default"
            by_wing[wing] = by_wing.get(wing, 0) + 1
        mem["total_memories"] = len(drawers)
        mem["by_wing"] = by_wing
    palace = stats.get("palace")
    if isinstance(palace, dict):
        palace["wings_count"] = len({(d.wing or "default") for d in drawers})
        palace["rooms_count"] = len({((d.wing or "default"), (d.room or "general")) for d in drawers})


def _coerce_classification(value) -> int:
    """密级归一化为 int（0..3），非法值按 0 —— 与 layers 同一语义（历史数据有字符串）。"""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, min(3, value))
    try:
        return max(0, min(3, int(str(value).strip() or 0)))
    except (TypeError, ValueError):
        return 0


async def handle_stats(server, drawers, arguments):
    """获取系统统计（记忆/宫殿两个区块按调用方租户裁剪，见 apply_tenant_view）"""
    return json.dumps(collect_stats(server, drawers), ensure_ascii=False, indent=2)


HANDLERS["pangu_stats"] = handle_stats


async def handle_graph(server, drawers, arguments):
    """导出知识图谱"""
    graph = {
        "palace": server.palace.export_structure(),
        "wiki": server.wiki.export_graph(),
        "knowledge_graph": server.knowledge_graph.export_graph(),
    }
    return json.dumps(graph, ensure_ascii=False, indent=2)


HANDLERS["pangu_graph"] = handle_graph


async def handle_identity(server, drawers, arguments):
    """获取/设置 AI 身份"""
    action = arguments.get("action", "get")
    if action == "set":
        server.memory.l0.set_identity(arguments.get("text", ""))
        return json.dumps({"status": "identity set"})
    return json.dumps({"identity": server.memory.l0.render()}, ensure_ascii=False)


HANDLERS["pangu_identity"] = handle_identity


async def handle_system_health(server, drawers, arguments):
    """深度系统健康检查（DB/结构/嵌入/统计）"""
    from ...observability.health import deep_health_check

    return json.dumps(deep_health_check(), ensure_ascii=False, indent=2)


HANDLERS["pangu_system_health"] = handle_system_health


async def handle_system_metrics(server, drawers, arguments):
    """获取 Prometheus 格式系统指标"""
    from ...observability.metrics import get_metrics_response

    content, _ = get_metrics_response()
    if isinstance(content, bytes):
        content = content.decode()
    return content


HANDLERS["pangu_system_metrics"] = handle_system_metrics


async def handle_config_get(server, drawers, arguments):
    """获取当前配置"""
    key = arguments.get("key")
    cfg = server.config
    # 密钥类字段（2026-09-20 修）：全量分支早就用 exclude 排掉了，单 key 分支没有，
    # 于是 `pangu_config_get(key="llm_api_key")` 会**明文返回** LLM Key / API Key /
    # JWT 密钥（实测）。而这些值在默认 28 工具里、且非写类，readonly 平台也能读走。
    # 平台通过审核＝本人，但 CodeBuddy/Zcode 是第三方软件，把「记忆访问权」和
    # 「你的 LLM 密钥」交给它不是一个等级的事 —— 一律脱敏为 ****。
    # 密钥的真实消费方（如 AMD 动态模型发现 autonomous._llm_endpoint）是**服务端
    # 直接读 ~/.pangu/.llm_api_key 文件**，不经过本接口，因此脱敏不影响该链路。
    _secret_keys = {"api_key", "llm_api_key", "siliconflow_key", "jwt_secret", "jwt_default_password"}
    if key:
        val = getattr(cfg, key, None)
        if key in _secret_keys:
            return json.dumps({key: "****" if val else None}, ensure_ascii=False)
        return json.dumps({key: str(val) if val is not None else None}, ensure_ascii=False)
    # 返回所有非敏感配置
    # 排除密钥类（jwt_secret 此前会明文返回 —— 拿到它可伪造 JWT 提权）
    safe = cfg.model_dump(exclude={"api_key", "llm_api_key", "siliconflow_key", "jwt_secret", "jwt_secret_file"})
    return json.dumps(safe, ensure_ascii=False, indent=2, default=str)


HANDLERS["pangu_config_get"] = handle_config_get


def _coerce_config_value(config, key, value):
    """按字段声明的类型校验/转换远程传入的原始值。

    为什么需要：pydantic 默认**不在赋值时校验**（validate_assignment=False），
    于是 `setattr(config, "exposure", {...})` 会把嵌套模型 `exposure: ExposureConfig`
    留成一个**裸 dict** —— 而暴露过滤器是按属性读的
    （`config.exposure.enabled_optional_modules`），下次 tools/list 直接
    AttributeError 崩掉。这里用 TypeAdapter 显式校验一次，顺便拦住类型不合法
    的写入（宁可不改，也不留坏配置）。

    字段不存在时原样返回，保持"未知键"的既有行为。
    """
    from pydantic import TypeAdapter

    field = type(config).model_fields.get(key)
    if field is None:
        return value
    return TypeAdapter(field.annotation).validate_python(value)


async def handle_config_set(server, drawers, arguments):
    """更新配置项（设置后同步落盘持久化，避免 reload 丢失——T6-F1 修复）"""
    key = arguments.get("key", "")
    value = arguments.get("value")

    # 保护名单（2026-09-19 补）：此前只查 hasattr(config, key) 就放行 —— 而 config 上
    # 存在 base_dir/db_path/palace_path（改存储路径）、jwt_secret（伪造 JWT 提权）、
    # host/port（改监听）等属性，等于任何有效钥匙都能把它们改掉（含 readonly）。
    # 这些项没有"远程修改"的正当需求（改它们应当 SSH 到机器上用 CLI），一律拒绝。
    # 不拦 url 类（llm_base_url 是文档明确支持的配置途径、feishu_webhook_url 是功能项，
    # 且持钥匙者本就能读数据，增量风险有限）。
    # 精确规则（不做裸子串匹配 —— "imp-ort-ance_decay_rate" 含 "port" 会被误伤，
    # 实测 importance_decay_rate 被第一版规则错拦，靠单测抓出）：
    def _protected(name: str) -> bool:
        k = (name or "").lower()
        if "jwt" in k or "secret" in k or k == "api_key":
            return True  # jwt_* 整族（含 default_password/roles/users）与密钥类
        if k in ("host", "port") or k.endswith(("_host", "_port")):
            return True  # 监听地址/端口（改它 = 改服务可达性）
        return "_path" in k or "_dir" in k or k.endswith(("path", "dir"))

    if key and _protected(key):
        return json.dumps(
            {"error": f"该配置项受保护，禁止远程修改: {key}（请到机器上用 CLI 修改）"},
            ensure_ascii=False,
        )
    if key and hasattr(server.config, key):
        # 密钥字段走独立文件的持久化路径（config.json 有意排除它们），
        # 否则通过设置页写入的 Key 只存在于内存，重启即丢。
        secret_keys = {"llm_api_key", "api_key", "siliconflow_key"}
        if key in secret_keys:
            try:
                if key == "llm_api_key":
                    server.config.save_llm_api_key(str(value or ""))
                else:
                    setattr(server.config, key, value)
                    from ...core.config import write_secret_file

                    write_secret_file(str(server.config.base_dir / f".{key}"), str(value or ""))
            except Exception:
                setattr(server.config, key, value)
        else:
            # 先按字段类型校验（见 _coerce_config_value）：值不合法就拒绝写入，
            # 而不是把坏配置落盘（例如 exposure 写成裸 dict 会让 tools/list 崩）。
            try:
                value = _coerce_config_value(server.config, key, value)
            except Exception as e:
                return json.dumps(
                    {"error": f"配置值不合法: {key}（{e}）"},
                    ensure_ascii=False,
                )
            setattr(server.config, key, value)
            try:
                server.config.save()
            except Exception:
                pass
        # T6-F2：失效依赖 config 的缓存组件，否则 llm / search / wiki
        # 仍持有旧 config 对象，改动不生效且无任何报错。
        # 调用做防御：这一点是「优化」而非「正确性前提」，持最小接口的
        # server 实现（测试桩、嵌入式调用）不应因此直接崩溃。
        invalidate = getattr(server, "invalidate_config_dependents", None)
        dropped = invalidate() if callable(invalidate) else []
        # 密钥类字段不回显明文（响应会进入调用方会话/日志）
        shown = "****" if key in secret_keys else str(value)
        return json.dumps(
            {"status": "updated", "key": key, "value": shown, "persisted": True, "invalidated": dropped},
            ensure_ascii=False,
        )
    return json.dumps({"error": f"unknown config key: {key}"})


HANDLERS["pangu_config_set"] = handle_config_set


async def handle_config_reload(server, drawers, arguments):
    """热更新配置（从磁盘重读，并失效依赖组件缓存）"""
    from ...core.config import PanguConfig

    new_cfg = PanguConfig.reload()
    server.config = new_cfg
    # T6-F2：必须丢弃已按旧 config 构造的实例，否则热加载只是替换了
    # server.config 引用，LLMEngine 等仍用旧值——静默失败。
    dropped = server.invalidate_config_dependents()
    return json.dumps(
        {
            "status": "reloaded",
            "llm_provider": new_cfg.llm_provider,
            "llm_model": new_cfg.llm_model,
            "invalidated": dropped,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_config_reload"] = handle_config_reload


async def handle_schema_version(server, drawers, arguments):
    """获取数据库 schema 版本"""
    from ...store.migrations import get_schema_version

    version = get_schema_version()
    return json.dumps({"schema_version": version}, ensure_ascii=False)


HANDLERS["pangu_schema_version"] = handle_schema_version


async def handle_schema_migrations(server, drawers, arguments):
    """列出所有迁移版本"""
    from ...store.migrations import get_available_migrations

    migrations = get_available_migrations()
    return json.dumps(migrations, ensure_ascii=False, indent=2)


HANDLERS["pangu_schema_migrations"] = handle_schema_migrations


async def handle_api_server_start(server, drawers, arguments):
    """启动 REST API 服务器"""
    import uvicorn

    from ...api.server import create_app

    host = arguments.get("host", server.config.host)
    port = arguments.get("port", server.config.port)
    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    # 在后台启动
    import asyncio as _asyncio

    _asyncio.create_task(server.serve())
    return json.dumps(
        {
            "status": "starting",
            "host": host,
            "port": port,
            "health_url": f"http://{host}:{port}/health",
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_api_server_start"] = handle_api_server_start


async def handle_graph_infer(server, drawers, arguments):
    """基于知识图谱推理"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.infer(query)
    summary = gr.get_reasoning_summary(result)
    return json.dumps(
        {
            "entities": len(result.entities),
            "paths": len(result.paths),
            "inferences": len(result.inferences),
            "confidence": result.confidence,
            "summary": summary,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_graph_infer"] = handle_graph_infer


async def handle_graph_contradictions(server, drawers, arguments):
    """检测图中的矛盾关系"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    contradictions = gr.detect_contradictions()
    return json.dumps(
        {
            "contradictions": contradictions,
            "count": len(contradictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_graph_contradictions"] = handle_graph_contradictions


async def handle_graph_causal_chain(server, drawers, arguments):
    """因果链分析"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    entity_id = arguments.get("entity_id", "")
    max_depth = arguments.get("max_depth", 5)
    chain = gr.causal_chain_analysis(entity_id, max_depth)
    return json.dumps({"chain": chain, "length": len(chain)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_causal_chain"] = handle_graph_causal_chain


async def handle_graph_temporal(server, drawers, arguments):
    """时序推理"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.temporal_reasoning(query)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_temporal"] = handle_graph_temporal


async def handle_graph_analogy(server, drawers, arguments):
    """类比检测"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.analogy_detection(query)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_analogy"] = handle_graph_analogy


async def handle_graph_visualize(server, drawers, arguments):
    """推理过程可视化"""
    from ...memory.graph_reasoning import GraphReasoning

    gr = GraphReasoning(server.config)
    query = arguments.get("query", "")
    result = gr.infer(query)
    visualization = gr.visualize_reasoning(result)
    return json.dumps(visualization, ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_visualize"] = handle_graph_visualize


async def handle_graph_entity(server, drawers, arguments):
    """获取实体信息"""
    from ...memory.graph_builder import get_builder

    gb = get_builder(server.config)
    name = arguments.get("name", "")
    entity = gb.get_entity(name)
    if not entity:
        return json.dumps({"error": f"Entity '{name}' not found"}, ensure_ascii=False, indent=2)
    rels = gb.get_entity_relations(name)
    return json.dumps(
        {
            "name": entity.name,
            "type": entity.entity_type,
            "confidence": entity.confidence,
            "relations": rels,
            "relation_count": len(rels),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_graph_entity"] = handle_graph_entity


async def handle_graph_path(server, drawers, arguments):
    """查找实体间路径"""
    from ...memory.graph_builder import get_builder

    from_name = arguments.get("from_name", "")
    to_name = arguments.get("to_name", "")
    if not from_name or not to_name:
        return json.dumps({"error": "from_name and to_name are required"}, ensure_ascii=False)
    gb = get_builder(server.config)
    path = gb.find_path(from_name, to_name)
    return json.dumps(
        {
            "from": from_name,
            "to": to_name,
            "path": path,
            "found": len(path) > 0,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_graph_path"] = handle_graph_path


async def handle_graph_quality(server, drawers, arguments):
    """评估图谱质量"""
    from ...memory.graph_builder import get_builder

    gb = get_builder(server.config)
    return json.dumps(gb.assess_quality(), ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_quality"] = handle_graph_quality


async def handle_graph_stats(server, drawers, arguments):
    """图谱统计"""
    from ...memory.graph_builder import get_builder

    gb = get_builder(server.config)
    return json.dumps(gb.get_graph_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_graph_stats"] = handle_graph_stats


async def handle_project_create(server, drawers, arguments):
    """创建项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(
        pm.create_project(
            arguments["project_id"],
            arguments["name"],
            arguments.get("description", ""),
        ),
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_project_create"] = handle_project_create


async def handle_project_switch(server, drawers, arguments):
    """切换项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(pm.switch_project(arguments["project_id"]), ensure_ascii=False, indent=2)


HANDLERS["pangu_project_switch"] = handle_project_switch


async def handle_project_list(server, drawers, arguments):
    """列出所有项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps({"projects": pm.list_projects()}, ensure_ascii=False, indent=2)


HANDLERS["pangu_project_list"] = handle_project_list


async def handle_project_active(server, drawers, arguments):
    """获取当前项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(pm.get_active_project(), ensure_ascii=False, indent=2)


HANDLERS["pangu_project_active"] = handle_project_active


async def handle_project_save(server, drawers, arguments):
    """保存记忆到当前项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(pm.save_memories(drawers), ensure_ascii=False, indent=2)


HANDLERS["pangu_project_save"] = handle_project_save


async def handle_project_load(server, drawers, arguments):
    """加载项目记忆"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    pid = arguments.get("project_id")
    memories = pm.load_memories(pid)
    return json.dumps({"memories": len(memories), "project": pid or pm._active_project}, ensure_ascii=False, indent=2)


HANDLERS["pangu_project_load"] = handle_project_load


async def handle_project_search(server, drawers, arguments):
    """跨项目搜索"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    results = pm.search_cross_project(arguments["query"], arguments.get("limit", 10))
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_project_search"] = handle_project_search


async def handle_project_merge(server, drawers, arguments):
    """合并项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(
        pm.merge_project(
            arguments["source_id"],
            arguments.get("target_id"),
        ),
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_project_merge"] = handle_project_merge


async def handle_project_delete(server, drawers, arguments):
    """删除项目"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(pm.delete_project(arguments["project_id"]), ensure_ascii=False, indent=2)


HANDLERS["pangu_project_delete"] = handle_project_delete


async def handle_project_stats(server, drawers, arguments):
    """项目统计"""
    from ...memory.project_manager import get_project_manager

    pm = get_project_manager(server.config)
    return json.dumps(pm.get_project_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_project_stats"] = handle_project_stats


async def handle_audit_log(server, drawers, arguments):
    """记录审计日志"""
    from ...memory.audit_analytics import get_audit

    audit = get_audit(server.config)
    entry = audit.log(arguments["operation"], arguments.get("target_id", ""))
    return json.dumps({"entry_id": entry.entry_id, "timestamp": entry.timestamp}, ensure_ascii=False, indent=2)


HANDLERS["pangu_audit_log"] = handle_audit_log


async def handle_audit_query(server, drawers, arguments):
    """查询审计日志"""
    from ...memory.audit_analytics import get_audit

    audit = get_audit(server.config)
    entries = audit.get_entries(
        arguments.get("operation"),
        arguments.get("user_id"),
        arguments.get("limit", 50),
    )
    return json.dumps({"entries": entries, "count": len(entries)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_audit_query"] = handle_audit_query


async def handle_audit_stats(server, drawers, arguments):
    """操作统计"""
    from ...memory.audit_analytics import get_audit

    audit = get_audit(server.config)
    return json.dumps(audit.get_operation_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_audit_stats"] = handle_audit_stats


async def handle_access_patterns(server, drawers, arguments):
    """访问模式分析"""
    from ...memory.audit_analytics import get_audit

    audit = get_audit(server.config)
    return json.dumps(audit.get_access_patterns(), ensure_ascii=False, indent=2)


HANDLERS["pangu_access_patterns"] = handle_access_patterns


async def handle_security_summary(server, drawers, arguments):
    """安全摘要"""
    from ...memory.audit_analytics import get_audit

    audit = get_audit(server.config)
    return json.dumps(audit.get_security_summary(), ensure_ascii=False, indent=2)


HANDLERS["pangu_security_summary"] = handle_security_summary


async def handle_plugin_list(server, drawers, arguments):
    """列出所有插件"""
    from ...plugins import get_plugin_manager

    pm = get_plugin_manager()
    return json.dumps({"plugins": pm.list_plugins(), "count": pm.plugin_count}, ensure_ascii=False, indent=2)


HANDLERS["pangu_plugin_list"] = handle_plugin_list


async def handle_plugin_enable(server, drawers, arguments):
    """启用插件"""
    from ...plugins import get_plugin_manager

    pm = get_plugin_manager()
    ok = pm.enable(arguments["name"])
    return json.dumps({"status": "enabled" if ok else "not_found"}, ensure_ascii=False, indent=2)


HANDLERS["pangu_plugin_enable"] = handle_plugin_enable


async def handle_plugin_disable(server, drawers, arguments):
    """禁用插件"""
    from ...plugins import get_plugin_manager

    pm = get_plugin_manager()
    ok = pm.disable(arguments["name"])
    return json.dumps({"status": "disabled" if ok else "not_found"}, ensure_ascii=False, indent=2)


HANDLERS["pangu_plugin_disable"] = handle_plugin_disable


async def handle_plugin_config(server, drawers, arguments):
    """获取插件配置"""
    from ...plugins import get_plugin_manager

    pm = get_plugin_manager()
    config = pm.get_config(arguments["name"])
    return json.dumps({"name": arguments["name"], "config": config}, ensure_ascii=False, indent=2)


HANDLERS["pangu_plugin_config"] = handle_plugin_config


async def handle_plugin_discover(server, drawers, arguments):
    """发现并加载自定义插件"""
    from ...plugins import get_plugin_manager

    pm = get_plugin_manager()
    path = arguments.get("path")
    count = pm.discover_plugins(path)
    return json.dumps({"discovered": count}, ensure_ascii=False, indent=2)


HANDLERS["pangu_plugin_discover"] = handle_plugin_discover


async def handle_version_history(server, drawers, arguments):
    """获取记忆变更历史"""
    from ...memory.versioning import get_version_control

    vc = get_version_control(server.config)
    memory_id = arguments.get("memory_id", "")
    history = vc.get_change_history(memory_id)
    return json.dumps({"history": history, "count": len(history)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_version_history"] = handle_version_history


async def handle_version_compare(server, drawers, arguments):
    """比较两个版本的差异"""
    from ...memory.versioning import get_version_control

    vc = get_version_control(server.config)
    memory_id = arguments.get("memory_id", "")
    v1 = arguments.get("v1", 1)
    v2 = arguments.get("v2", 2)
    diff = vc.compare_versions(memory_id, v1, v2)
    return json.dumps(diff, ensure_ascii=False, indent=2)


HANDLERS["pangu_version_compare"] = handle_version_compare


async def handle_graph_visualize_web(server, drawers, arguments):
    """生成知识图谱可视化页面URL"""
    from ...core.config import PanguConfig as _Cfg

    cfg = _Cfg.load()
    host = cfg.host if cfg.host != "0.0.0.0" else "127.0.0.1"
    url = f"http://{host}:{cfg.port}/graph"
    return json.dumps(
        {"url": url, "description": "在浏览器中打开此URL查看交互式知识图谱"}, ensure_ascii=False, indent=2
    )


HANDLERS["pangu_graph_visualize_web"] = handle_graph_visualize_web
