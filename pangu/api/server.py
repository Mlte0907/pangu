"""盘古 FastAPI 服务器工厂（伏羲移植）"""

import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from pangu import __version__
from pangu.api.abac import (
    authorize as abac_authorize,
)
from pangu.api.abac import (
    load_policies_from_config,
    register_builtin_policies,
)
from pangu.api.auth import (
    TOKEN_TYPE_REFRESH,
    AuthError,
    TokenExpiredError,
    TokenInvalidError,
    UserStore,
    issue_token_pair,
    load_or_create_secret,
    verify_credentials,
    verify_token,
)
from pangu.api.rbac import (
    ROLE_PRESETS,
    Principal,
    get_principal,
    require_scope,
    resolve_scopes,
)
from pangu.store.migrations import init_db

logger = logging.getLogger("pangu.api.server")


def _setup_logging() -> None:
    """初始化日志输出（幂等）。

    为什么必须显式做这件事：Python 的 root logger 默认 level=WARNING 且
    handler 为空，而本模块（以及 warmup / 各组件）大量使用 logger.info()。
    不配置的话这些日志会被静默丢弃，运维侧表现为"启动日志里只有 uvicorn
    的 access log，盘古自己的启动信息一条都没有"。

    这里不重复造轮子：复用 pangu/memory/production.py 里已有的
    setup_structured_logging（结构化 JSON 输出）。该类此前定义了却从未被
    调用，属于同一问题的另一半。

    配置两项均可由环境变量覆盖，默认值面向 systemd 部署：
      PANGU_LOG_LEVEL：日志级别，默认 INFO
      PANGU_LOG_FILE ：额外写入的日志文件；默认不设——由 systemd 的
        StandardOutput=append: 负责落盘，避免与 uvicorn 自己的日志写入
        同一文件时互相覆盖。

    幂等：重复调用只重设一次，避免测试里反复 create_app() 堆积 handler
    （setup_structured_logging 内部会先清空 root 的既有 handler）。
    """
    try:
        from pangu.memory.production import setup_structured_logging

        setup_structured_logging(
            level=os.environ.get("PANGU_LOG_LEVEL", "INFO"),
            log_file=os.environ.get("PANGU_LOG_FILE") or None,
        )
    except Exception as e:  # 日志配置失败不应阻断服务启动
        logging.basicConfig(level=logging.INFO)
        logger.warning(f"结构化日志配置失败，回退到 basicConfig: {e}")


def mcp_auth_exposure_warning(bind_host: str, mcp_require_auth: bool) -> str:
    """「监听地址暴露 + MCP 免鉴权」时返回可指路的警告文案（否则返回空串）。

    为什么需要：`/mcp` 默认**无凭据也放行**（mcp_require_auth=False）。只监听
    回环时这没问题（能连上就等于在本机）；一旦监听非回环地址，任何能连到该端口
    的人都能直接读写记忆 —— **且不经过平台令牌/审核那套机制**（2026-09-22 实测：
    不带任何凭据调用 pangu_search_memories，直接返回全部记忆原文）。

    纯函数（不读全局、不产生副作用），便于单测。
    """
    if mcp_require_auth:
        return ""
    host = (bind_host or "").strip()
    # 回环 = 只有本机能连，属于"能连上即身份"的信任模型；空 = 无从判断，不误报
    if host in ("", "127.0.0.1", "::1", "localhost"):
        return ""
    return (
        f"⚠ 正在监听 {host}，但 MCP 未强制鉴权：任何能连到该端口的人都能直接读写记忆，"
        "且不经过平台令牌审核。请在 ~/.pangu/config.json 中设置 mcp_require_auth: true 并重启服务。"
    )


def create_app() -> FastAPI:
    """创建 FastAPI 应用（伏羲移植版）"""
    from pangu.core.config import PanguConfig as _Cfg
    from pangu.core.config import config as _orig_cfg

    _loaded = _Cfg.load()
    _loaded.config_path = getattr(_loaded, "config_path", "")
    # 暴露且免鉴权 ⇒ 启动时大喊一声。install.sh 走的路由会在装的时候直接把
    # mcp_require_auth 写成 true；这里是给手工 `pangu serve --host 0.0.0.0` 的兜底。
    _mcp_warn = mcp_auth_exposure_warning(
        os.environ.get("PANGU_HOST", ""), getattr(_loaded, "mcp_require_auth", False)
    )
    if _mcp_warn:
        logger.warning(_mcp_warn)
    # 用配置文件的值替换全局单例，使整个模块统一使用 config.json 的内容。
    #
    # 关键：只覆盖 config.json 里**显式写明的**字段，而不是无差别地铺一层
    # `_loaded` 的全部字段。原因：`_Cfg.load()` 返回的是一个「磁盘 JSON +
    # 环境变量 + 字段默认值」三者合成的完整对象，其中字段默认值会盖掉
    # 调用方刚刚在进程内设好的值。不加这层过滤时，会出现两类难以排查的问题：
    #   1) 测试用 monkeypatch 设好的 api_key / jwt_default_password 被默认值
    #      清空，鉴权随即失效（无 Key 也能 200、登录恒 401）
    #      —— 见 tests/test_auth.py::TestHTTPAuth；
    #   2) 测试用 PANGU_* 环境变量配置的 jwt_users / abac_user_attrs 被默认值
    #      覆盖，RBAC/ABAC 联调全部失败
    #      —— 见 tests/test_e2e_rbac_abac.py。
    # 保留语义：config.json 里写了的字段以文件为准（运维期望）；
    # 没写的字段不干预进程内现值（环境变量与程序化设置的期望）。
    #
    # ⚠ 但路径类字段必须让位给显式环境变量（否则测试会写进生产库）：
    #   上面的规则有一条被忽视的推论——`~/.pangu/config.json` 里通常**显式
    #   写着** `db_path` / `base_dir`（它们是盘的落点，运维会写死）。于是
    #   任何"用 PANGU_DB_PATH 指向 tmp 来隔离测试"的尝试都会被这里覆盖回
    #   生产路径，而 `pangu/api/server.py:557` 正是用
    #   `Path(config.db_path) / "v2_memories"` 定位 MemoryStack 的存储。
    #   实测后果：跑一条 `test_cross_tenant_list_isolated` 就让用户真实库
    #   drawers 从 108 → 111（+3），整个套件一轮从 69 → 108；而且真实库里
    #   累积的历史记录（含 visibility='public' 的其它租户记录，
    #   routes_memory.py:201 按设计允许其跨租户可见）会破坏"隔离库中只有
    #   本次写入"这一前置条件，表现为跨租户断言随机失败。
    #
    # 因此：只要调用方**显式**通过环境变量指定了路径字段，就以环境变量为准。
    # 这与 pydantic-settings 的常规优先级一致（env > 配置文件默认），
    # 也不影响运维语义——运维在 config.json 里写的值，在没有环境变量覆盖时
    # 依然完全生效（本机生产部署即如此，未设 PANGU_DB_PATH）。
    _ENV_OVERRIDABLE_PATHS = (
        "db_path",
        "base_dir",
        "palace_path",
        "identity_path",
        "wiki_path",
        "backup_dir",
        "domain_knowledge_db_path",
    )
    # 密钥类字段同理不得被文件覆盖（2026-09-20 修）：
    # config.json 里通常**显式写着 `api_key`**（本机就是如此）。而密钥的权威来源
    # 按安全性应是「环境变量 / 进程内显式设置」——它们绝不该被一个磁盘文件里的
    # 旧值盖掉。此前不排除它们，导致：
    #   1) 测试里 monkeypatch 的 api_key 被 config.json 的真值覆盖 → 带测试钥匙的
    #      请求 401（tests/test_auth.py::TestHTTPAuth::test_api_key_passes 长期红）；
    #   2) 更实际的后果：运维把 API Key 从「环境变量」切换为只更新环境变量时，
    #      config.json 里的旧 Key 会继续生效，形成"改了没生效/旧 Key 仍可用"。
    # 与 `PanguConfig.save()` 的 exclude 一致：密钥不落 config.json，也就不该从它读。
    #
    # ⚠ 但环境变量里的密钥仍需生效：PanguConfig.load() 已经把环境变量值
    # 加载进 _loaded，跳过 _SECRET_FIELDS 会连环境变量的值也丢掉。
    # 解法：跳过文件值，但**保留环境变量值**。
    _SECRET_FIELDS = {"api_key", "llm_api_key", "siliconflow_key", "jwt_secret"}
    _SENSITIVE_ENV_MAP = {
        "api_key": "PANGU_API_KEY",
        "llm_api_key": "PANGU_LLM_API_KEY",
        "siliconflow_key": "PANGU_SILICONFLOW_KEY",
        "jwt_secret": "PANGU_JWT_SECRET",
    }
    _env_pinned: set[str] = set()
    for _name in _ENV_OVERRIDABLE_PATHS:
        if os.environ.get(f"PANGU_{_name.upper()}"):
            _env_pinned.add(_name)

    _json_keys: set[str] = set()
    _cfg_path = getattr(_loaded, "config_path", "") or os.path.expanduser("~/.pangu/config.json")
    try:
        if os.path.exists(_cfg_path):
            with open(_cfg_path, encoding="utf-8") as _f:
                _json_keys = set(json.load(_f).keys())
    except (json.JSONDecodeError, OSError):
        _json_keys = set()

    # Pydantic V2.11 起，在**实例**上访问 model_fields 已弃用（V3 移除）：
    # 字段定义属于类，应从类上取（type(x).model_fields）。
    for _field in type(_loaded).model_fields:
        if _field not in _json_keys:
            continue
        if _field in _env_pinned:
            # 环境变量显式指定了该路径字段，跳过文件覆盖
            continue
        if _field in _SECRET_FIELDS:
            # 密钥字段：进程内现值（环境变量/显式设置/密钥文件）优先于 config.json
            continue
        try:
            setattr(_orig_cfg, _field, getattr(_loaded, _field))
        except Exception:
            pass
    # 环境变量中的密钥：跳过文件值，但保留环境变量值
    for _field, _env in _SENSITIVE_ENV_MAP.items():
        if os.environ.get(_env):
            try:
                setattr(_orig_cfg, _field, getattr(_loaded, _field))
            except Exception:
                pass
    config = _orig_cfg

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
        # 必须在此处初始化日志：此前 create_app 全程没有任何 logging 配置，
        # 而 Python 的 root logger 默认级别是 WARNING 且无 handler，导致
        # 下面所有 logger.info(...) 被静默丢弃——包括预热耗时、MCPServer
        # 预加载、自主维护周期等启动关键信息，在 .deploy-logs 里完全看不到
        # （例如"向量索引预热完成: Nms"这条，本来是排查向量冷启动的唯一线索）。
        # PANGU_LOG_LEVEL / PANGU_LOG_FILE 可覆盖默认值；默认只写 stdout，
        # 由 systemd 的 StandardOutput=append: 落盘，避免与 uvicorn 的
        # 日志文件写入互相干扰。
        _setup_logging()
        logger.info(f"盘古 v3.0 starting on {config.host}:{config.port}")
        init_db()
        config.ensure_dirs()

        # 启动工作记忆持久化
        try:
            from pangu.memory.working_memory import get_working_memory

            wm = get_working_memory()
            wm.restore_checkpoint()
            wm.start_auto_checkpoint()
        except Exception as e:
            logger.warning(f"Working memory init failed: {e}")

        # 预热组件（消除冷查询延迟）
        try:
            from pangu.memory.warmup import warmup_all

            warmup = warmup_all()
            # 不要逐个硬编码字段名——此前只列了 jieba/onnx/fts_index，
            # 漏掉了 vector_index，恰好是排查向量冷启动时最该看的那个数。
            # 改为遍历 warmup_all() 的返回值，新增阶段会自动出现在日志里。
            _detail = ", ".join(f"{k}={v:.0f}ms" for k, v in warmup.items() if k != "total")
            logger.info(f"Warmup complete: {warmup.get('total', 0):.0f}ms ({_detail})")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")

        # 嵌入后端体检：若降级到 hash 向量，检索结果**没有语义能力**却照常返回，
        # 必须让这件事可见（此前它完全静默，是 v0.1.3 修的 P0 之一）。
        #
        # ⚠ 不要指望 warmup 已经确定后端状态：`warmup_onnx()`（warmup.py:31）
        # 构造的是**另一个** `ONNXEmbedder()` 实例，与这里的 EmbeddingService
        # 单例无关，因此单例的 `_active_backend` 仍是 "unknown"。
        # 实测踩过：体检报 "unknown（正常）"，把未确定当成了健康。
        # 所以这里**自己触发一次嵌入**来确定状态，绝不把 unknown 当正常。
        try:
            from pangu.memory.embedding import get_embedding_service

            _es = get_embedding_service()
            _es.embed("启动体检")  # 触发惰性加载，确定 active_backend
            _backend = _es.active_backend

            if _backend == "unknown":
                # 仍未确定 = 探针失效，必须报出来而不是当成正常
                logger.warning(
                    "启动体检：嵌入后端状态未能确定（active_backend=unknown）。"
                    "这本身可能是缺陷，请检查 get_embedding_service() 与嵌入路径。"
                )
            elif _es.is_degraded:
                logger.error(
                    "启动体检：嵌入后端 = %s（降级），检索结果无语义能力。原因: %s",
                    _backend,
                    _es.stats.get("degraded_reason", "未知"),
                )
                if not getattr(config, "allow_hash_fallback", False):
                    logger.error(
                        "PANGU_ALLOW_HASH_FALLBACK 未开启：请安装 ONNX 模型"
                        "（./install.sh 会预下载）或配置 embed_api_url。"
                        "确认要在无语义能力下继续运行，请设 PANGU_ALLOW_HASH_FALLBACK=1。"
                    )
            else:
                logger.info(f"启动体检：嵌入后端 = {_backend}")
        except Exception as e:
            logger.warning(f"Embedding health probe failed: {e}")

        # 加密体检（2026-09-19）：确认已有密文还能解开。
        # 典型故障：换机器/重装时丢了 ~/.pangu/.encryption_key，新密钥生成后旧密文
        # 全部不可解 —— 旧行为是静默返回密文，用户只看得到 gAAAAAB… 乱码查不到原因。
        try:
            import json as _json
            from pathlib import Path as _Path

            from pangu.memory import encryption as _enc

            sample = None
            _drawers_file = _Path(config.palace_path) / "drawers.json"
            if _drawers_file.exists():
                for _item in _json.loads(_drawers_file.read_text()):
                    _c = str((_item or {}).get("content") or "")
                    if _c.startswith("gAAAAA"):
                        sample = _c
                        break
            _verdict = _enc.self_check(sample)
            if not _verdict["enabled"]:
                logger.error(f"启动体检：加密不可用 —— {_verdict['error']}（新数据将以明文写入）")
            elif _verdict["sample_ok"] is False:
                logger.error(
                    "启动体检：**已有密文无法解密**（密钥不匹配）—— 旧加密记忆将显示为占位符。"
                    "检查 ~/.pangu/.encryption_key 与 PANGU_ENCRYPTION_KEY 是否与加密时一致"
                )
            else:
                logger.info(
                    f"启动体检：加密可用（{_verdict['keys']} 把密钥，"
                    f"样本解密 {'通过' if _verdict['sample_ok'] else '无密文样本'}）"
                )
        except Exception as e:
            logger.warning(f"Encryption health probe failed: {e}")

        # 预加载 MCPServer 实例（避免每次请求重建）
        try:
            from pangu.api.routes_tools import _get_server

            _get_server()
            logger.info("MCPServer instance preloaded")
        except Exception as e:
            logger.warning(f"MCPServer preload failed: {e}")

        # 自主记忆管理：检查是否需要运行维护周期
        try:
            from pangu.memory.autonomous import get_autonomous_engine

            engine = get_autonomous_engine(config)
            tick = engine.tick()
            if tick["should_run"]:
                logger.info(f"Autonomous maintenance: {len(tick['pending_tasks'])} tasks pending, running...")
                cycle = engine.run_cycle()
                logger.info(
                    f"Autonomous cycle: {cycle.tasks_run} ran, {cycle.tasks_skipped} skipped, {cycle.tasks_failed} failed, {cycle.total_duration_ms:.0f}ms"
                )
            else:
                logger.info("Autonomous maintenance: all tasks up to date")
        except Exception as e:
            logger.warning(f"Autonomous engine init failed: {e}")

        # 启动后台自主调度器（每 30 分钟自动检查维护）
        try:
            from pangu.memory.autonomous import get_scheduler

            scheduler = get_scheduler(config)
            scheduler.start()
        except Exception as e:
            logger.warning(f"Autonomous scheduler start failed: {e}")

        # 激活事件总线→WebSocket 桥接
        try:
            from pangu.memory.realtime_bridge import setup_bridge

            setup_bridge()
        except Exception as e:
            logger.warning(f"Realtime bridge setup failed: {e}")

        logger.info("盘古 server started")
        yield

        # 停止后台调度器
        try:
            from pangu.memory.autonomous import get_scheduler

            get_scheduler().stop()
        except Exception:
            pass

        # 关停时把嵌入缓存落盘。
        #
        # ⚠ 必须 flush **搜索链实际在用的那个** VectorEmbedder。
        # 这里若新构造一个 `VectorEmbedder(config)`，它自带一个空缓存，
        # flush 等于什么都没写（还静默返回 False）——看起来做了事，实则丢数据。
        # 活实例挂在 MCPServer.search.semantic._embedder 上（engine.py:21）。
        # 平时每 100 条新增才自动写一次，最后不足 100 条的那批只能靠这里。
        try:
            from pangu.api.routes_tools import _get_server

            _srv = _get_server()
            _sem = getattr(getattr(_srv, "search", None), "semantic", None)
            _emb = getattr(_sem, "_embedder", None)
            if _emb is not None and _emb.flush_cache():
                logger.info("嵌入缓存已落盘")
        except Exception as e:
            logger.warning(f"Embedding cache flush failed: {e}")

        # 关闭
        logger.info("盘古 server stopped")

    app = FastAPI(
        title="盘古 v0.1 — AI Agent 多模态记忆系统",
        description="421个MCP工具 + 4种模态输入（文本/图片/视频/音频）+ 跨模态搜索 + 自主管理",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    _cors_origins = (
        config.cors_origins
        if hasattr(config, "cors_origins") and config.cors_origins
        else [
            "http://localhost:19528",
            "http://127.0.0.1:19528",
            "http://localhost:8866",
            "http://127.0.0.1:8866",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["X-API-Key", "X-Agent-ID", "Content-Type", "Accept", "Accept-Version", "Accept-Encoding"],
    )

    # ── 速率限制 ──
    class RateLimitMiddleware:
        """速率限制中间件 — 每分钟最多 100 次请求"""

        def __init__(self, app: ASGIApp, max_requests: int = 100, window_seconds: int = 60):
            self.app = app
            self.max_requests = max_requests
            self.window = window_seconds
            self._requests: dict[str, list[float]] = {}

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            # 获取客户端 IP
            client = scope.get("client", ("unknown", 0))
            client_ip = client[0] if client else "unknown"
            now = time.time()

            # 清理过期请求
            if client_ip in self._requests:
                self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < self.window]

            # 检查速率限制
            if len(self._requests.get(client_ip, [])) >= self.max_requests:
                response = JSONResponse(
                    status_code=429, content={"error": "Rate limit exceeded", "retry_after": self.window}
                )
                await response(scope, receive, send)
                return

            # 记录请求
            self._requests.setdefault(client_ip, []).append(now)
            await self.app(scope, receive, send)

    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

    # /docs 已对所有客户端开放（认证关闭时）

    # ── API 指标中间件 ──
    class _MetricsMiddleware:
        """纯 ASGI 中间件：记录 API 指标"""

        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            start = time.time()
            status_code = 200

            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 200)
                await send(message)

            await self.app(scope, receive, send_wrapper)

            try:
                from pangu.observability.metrics import record_api_request

                method = scope.get("method", "GET")
                path = scope.get("path", "")
                record_api_request(method, path, status_code, time.time() - start)
            except Exception:
                pass

    app.add_middleware(_MetricsMiddleware)

    # ── 错误码校正中间件（2026-09-20）────────────────────────────────
    # 全仓大量路由用 `return {"error": ..., "code": 401}` / `ApiResponse.error(403, ...)`
    # 表达失败，但 FastAPI 会把普通 dict 序列化成 **HTTP 200** —— 于是鉴权失败、
    # 资源不存在在传输层都"成功"。前端（dsh `adminFetch`）只看 res.json() 不看
    # status，错误被 `catch(_){}` 静默吞掉，表现为"点了没反应"。全局异常处理器
    # 也管不到这些**正常返回**的错误体。
    # 这里做一层收口：响应体是 {"code": <4xx/5xx>, ...} 形态且 HTTP 仍是 200 时，
    # 把状态码校正为对应值（仅 4xx/5xx 语义的 code，其它业务码不动）。
    _CODE_TO_HTTP = {401, 403, 404, 405, 409, 422, 429, 500, 502, 503}

    class _ErrorStatusMiddleware:
        """把 `{"code": 4xx/5xx}` 的错误响应体校正为真实 HTTP 状态码。"""

        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            start_message: dict | None = None
            body_chunks: list[bytes] = []

            async def send_wrapper(message):
                nonlocal start_message
                if message["type"] == "http.response.start":
                    start_message = message
                    return  # 先缓存，等 body 攒齐再决定状态码
                if message["type"] == "http.response.body":
                    body_chunks.append(message.get("body", b""))
                    if message.get("more_body"):
                        return
                    body = b"".join(body_chunks)
                    new_status = None
                    try:
                        if start_message and start_message.get("status", 200) == 200 and body:
                            import json as _json

                            parsed = _json.loads(body.decode("utf-8", "ignore"))
                            if isinstance(parsed, dict):
                                code = parsed.get("code")
                                if isinstance(code, int) and code in _CODE_TO_HTTP and code >= 400:
                                    new_status = code
                    except Exception:
                        new_status = None
                    if new_status is not None and start_message is not None:
                        start_message = dict(start_message)
                        start_message["status"] = new_status
                    if start_message is not None:
                        await send(start_message)
                    await send({"type": "http.response.body", "body": body, "more_body": False})
                    return
                await send(message)

            await self.app(scope, receive, send_wrapper)

    app.add_middleware(_ErrorStatusMiddleware)

    # ── 双鉴权初始化（API Key + JWT） ──
    jwt_secret: str = config.jwt_secret
    # JWT 只在**用户显式配置**时才启用：显式给了 jwt_users，或显式设了
    # jwt_default_password。默认密码是空串（config.py:130），此前这里却拿
    # `!= "pangu-admin"` 当"非默认"判据 —— 空串 != "pangu-admin" 恒为真，
    # 于是全新部署也会自动生成 JWT 密钥，而 UserStore 又因密码为空不建 admin 用户，
    # 结果是「鉴权开着但谁也登不进来」的 REST 锁死。判据必须与真实默认值一致。
    jwt_explicitly_enabled = bool(config.jwt_users) or bool(config.jwt_default_password)
    if not jwt_secret and jwt_explicitly_enabled:
        try:
            jwt_secret = load_or_create_secret(config.jwt_secret_file)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"无法加载 JWT 密钥：{e}，JWT 鉴权被禁用")
            jwt_secret = ""

    # 构建用户表：先看 jwt_users，再回落到 default
    user_dict: dict[str, str] = {}
    if config.jwt_users:
        user_dict.update(config.jwt_users)
    elif jwt_secret:  # 仅在 JWT 实际启用时添加 default user
        user_dict[config.jwt_default_user] = config.jwt_default_password

    user_store = UserStore(user_dict) if user_dict else UserStore({})

    # ── 角色 → 权限映射 ──
    role_map: dict[str, list[str]] = dict(ROLE_PRESETS)
    if config.jwt_roles:
        role_map.update(config.jwt_roles)

    def _resolve_user_role(username: str) -> str:
        """按 username → jwt_user_roles → jwt_default_role 解析角色。"""
        return config.jwt_user_roles.get(username, config.jwt_default_role)

    def _resolve_user_scopes(username: str) -> tuple[str, str]:
        role = _resolve_user_role(username)
        scopes = resolve_scopes(role, role_map=role_map)
        return role, " ".join(sorted(scopes))

    def _resolve_user_abac_attrs(username: str) -> dict:
        """从 abac_user_attrs 读取用户的 ABAC 属性。"""
        return dict(config.abac_user_attrs.get(username, {}))

    # ── 初始化 ABAC 策略引擎 ──
    if config.abac_enabled:
        register_builtin_policies()
        if config.abac_policies:
            load_policies_from_config(config.abac_policies)

    # 缓存到 app.state 供路由访问
    app.state.jwt_secret = jwt_secret
    app.state.jwt_algorithm = config.jwt_algorithm
    app.state.user_store = user_store
    app.state.role_map = role_map
    # 钥匙系统启用（mcp_require_auth）时 REST 网关同样上锁 —— 一套凭据（pgk_）管
    # MCP 与 REST 两扇门，避免"MCP 锁了、REST 还开着"的绕行面。
    app.state.auth_enabled = bool(config.api_key or jwt_secret or getattr(config, "mcp_require_auth", False))

    # ── 鉴权中间件：盘古钥匙（pgk_）/ API Key / JWT 三选一通过 ──
    class _AuthMiddleware:
        """网关粗粒度鉴权。

        启用条件：config.api_key 非空、jwt_secret 非空，或钥匙系统启用
        （mcp_require_auth=true）——三种情况下数据面路由都必须带凭据。
        公开端点仅限探针与文档：/、/health*、/metrics、/docs、/openapi.json、
        /api/v2/auth/*（登录本身）。/api/v2/admin/* 走自己的 X-Admin-Key
        自保护（0600 secret，常量时间比对），不在网关重复设卡。
        """

        _EXEMPT_PATHS = {
            "/",
            "/health",
            "/health/deep",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        }
        _EXEMPT_EXACT = {"/api/v2/auth/login", "/api/v2/auth/refresh", "/api/v2/platforms/request"}
        # 2026-09-26：/api/v2/graph 从豁免前缀中移除。此前它**同时**满足「在豁免名单里」
        # 与「路由内无任何自身校验」两个条件 → 网关不查凭据、路由自己也不查，实测匿名请求
        # 返回 200 + 全量图谱（nodes 33 / edges 14），平台 token 同样畅通。这条同时破坏了
        # 两条用户设定：① FastAPI 只给仪表盘/管理员，② 平台无法用 token 走 FastAPI 取数据。
        # 同名单里的 /api/v2/admin 与 /api/v2/{platforms,dashboard} 仍在豁免中是**安全的** ——
        # 它们都在路由内自己校验了 admin（admin_auth.verify_admin），网关豁免只是省一次重复
        # 校验。graph 没有这层自保护，所以必须由网关兜住。
        _EXEMPT_PREFIXES = (
            "/docs",
            "/redoc",
            "/api/v2/admin",
            "/api/v2/platforms",
            "/api/v2/dashboard",
            "/mcp",
        )

        def __init__(self, app: ASGIApp):
            self.app = app
            # api_key 不在 __init__ 时缓存——PanguConfig.load() 可能在中间件
            # 构造后才从环境变量/密钥文件加载完成，缓存会拿到空字符串。
            # 改为每次请求时动态读取 config.api_key（开销可忽略）。
            self.secret = jwt_secret
            self.algorithm = config.jwt_algorithm
            self.user_store = user_store
            self.enabled = bool(config.api_key or self.secret or getattr(config, "mcp_require_auth", False))

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http" or not self.enabled:
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            _exempt = (
                path in self._EXEMPT_PATHS
                or path in self._EXEMPT_EXACT
                or any(path.startswith(p) for p in self._EXEMPT_PREFIXES)
            )

            # 归一化 headers（豁免路径也需要，用于尽力解析身份）
            headers: dict[str, str] = {}
            for k, v in scope.get("headers", []):
                try:
                    headers[k.decode("latin-1").lower()] = v.decode("latin-1", errors="ignore")
                except Exception:
                    continue

            if _exempt:
                # 豁免路径不拦截请求，但仍**尽力解析**凭据并注入身份。
                try:
                    _res = verify_credentials(
                        headers=headers,
                        api_key=config.api_key,
                        secret=self.secret,
                        algorithm=self.algorithm,
                        user_store=self.user_store,
                        require_auth=bool(getattr(config, "mcp_require_auth", False)),
                    )
                    if _res.ok and _res.method == "jwt" and _res.claims:
                        scope["state"] = scope.get("state", {})
                        scope["state"]["auth"] = {
                            "method": _res.method,
                            "user_id": _res.user_id,
                            "claims": _res.claims,
                        }
                    elif _res.ok and _res.method == "api_key":
                        scope["state"] = scope.get("state", {})
                        scope["state"]["auth"] = {"method": _res.method, "user_id": "api_key_user"}
                    elif _res.ok and _res.method == "pangu_key":
                        # 盘古钥匙：把租户一起注入，路由无需再查一次钥匙表
                        scope["state"] = scope.get("state", {})
                        scope["state"]["auth"] = {
                            "method": _res.method,
                            "user_id": _res.user_id,
                            "tenant": _res.tenant,
                            "key_id": _res.key_id,
                            "clearance": _res.clearance,
                        }
                    elif _res.ok and _res.method == "platform_token":
                        # 平台接入 Token：把平台信息一起注入
                        scope["state"] = scope.get("state", {})
                        scope["state"]["auth"] = {
                            "method": _res.method,
                            "user_id": _res.user_id,
                            "tenant": _res.tenant,
                            "key_id": _res.key_id,
                            "clearance": _res.clearance,
                        }
                except Exception:
                    pass
                await self.app(scope, receive, send)
                return

            result = verify_credentials(
                headers=headers,
                api_key=config.api_key,
                secret=self.secret,
                algorithm=self.algorithm,
                user_store=self.user_store,
                require_auth=bool(getattr(config, "mcp_require_auth", False)),
            )

            if not result.ok:
                # 暴露 WWW-Authenticate 引导客户端
                response = JSONResponse(
                    status_code=401,
                    content={"code": 401, "message": result.reason or "Unauthorized", "data": None},
                    headers={"WWW-Authenticate": 'Bearer realm="pangu"'},
                )
                await response(scope, receive, send)
                return

            # 注入请求主体，便于路由读取身份
            if result.method == "jwt" and result.claims:
                scope["state"] = scope.get("state", {})
                scope["state"]["auth"] = {
                    "method": result.method,
                    "user_id": result.user_id,
                    "claims": result.claims,
                }
            elif result.method == "api_key":
                scope["state"] = scope.get("state", {})
                scope["state"]["auth"] = {"method": result.method, "user_id": "api_key_user"}
            elif result.method == "pangu_key":
                scope["state"] = scope.get("state", {})
                scope["state"]["auth"] = {
                    "method": result.method,
                    "user_id": result.user_id,
                    "tenant": result.tenant,
                    "key_id": result.key_id,
                    "clearance": result.clearance,
                }
            elif result.method == "platform_token":
                scope["state"] = scope.get("state", {})
                scope["state"]["auth"] = {
                    "method": result.method,
                    "user_id": result.user_id,
                    "tenant": result.tenant,
                    "key_id": result.key_id,
                    "clearance": result.clearance,
                }

            await self.app(scope, receive, send)

    app.add_middleware(_AuthMiddleware)

    # ── 业务存储：v2 路由用 MemoryStack 持久化 ──
    from pangu.core.config import PanguConfig
    from pangu.memory.layers import MemoryStack

    def _build_memory_store() -> MemoryStack:
        """从配置构造 MemoryStack（不强制启用 LLM）。"""
        # 复用全局 config，但把路径指向独立的 v2 目录
        v2_cfg = PanguConfig()
        v2_dir = Path(config.db_path) / "v2_memories"
        v2_dir.mkdir(parents=True, exist_ok=True)
        v2_cfg.palace_path = str(v2_dir)
        v2_cfg.identity_path = str(v2_dir / "identity.json")
        v2_cfg.wiki_path = str(v2_dir / "wiki.json")
        return MemoryStack(config=v2_cfg)

    app.state.memory = _build_memory_store()

    # 全局异常处理器
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            # 若 detail 已是 envelope 格式（dict 含 code/message/data），直接展开
            if isinstance(exc.detail, dict) and "code" in exc.detail:
                return JSONResponse(
                    status_code=exc.status_code,
                    content=exc.detail,
                    headers=getattr(exc, "headers", None) or {},
                )
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.status_code, "message": str(exc.detail), "data": None},
                headers=getattr(exc, "headers", None) or {},
            )
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        return JSONResponse(status_code=500, content={"code": 500, "message": "Internal server error", "data": None})

    # 全局 404 / 405 等 HTTP 异常（路由未命中也走统一 envelope）
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """统一 HTTP 异常响应（404 / 405 / 500 等）。若 detail 是 envelope dict 则保留 data。"""
        headers = getattr(exc, "headers", None) or {}
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": str(exc.detail) if exc.detail else "HTTP Error",
                "data": None,
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """请求体验证失败：400 + 统一 envelope"""
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "message": "Validation Error",
                "data": {"errors": exc.errors()},
            },
        )

    # 注册路由
    from pangu.api.routes_memory import router as mem_router

    app.include_router(mem_router, prefix="/api/v2")

    # 任务状态同步路由
    from pangu.api.routes_tasks import router as task_router

    app.include_router(task_router, prefix="/api/v2")

    # MCP 工具网关
    from pangu.api.routes_tools import router as tools_router

    app.include_router(tools_router, prefix="/api/v2")

    # 钥匙管理（admin 端点，不进豁免清单）
    from pangu.api.routes_keys import router as keys_router

    app.include_router(keys_router, prefix="/api/v2")

    # 平台接入审核（新机制）
    from pangu.api.routes_platforms import router as platforms_router

    app.include_router(platforms_router, prefix="/api/v2")

    # 仪表盘（统计、管理、展示）
    from pangu.api.routes_dashboard import router as dashboard_router

    app.include_router(dashboard_router, prefix="/api/v2")

    # 批量工具调用（直接注册到 app 避免被 {tool_name} 截获）
    from pangu.api.routes_tools import BatchToolCallRequest

    @app.post("/api/v2/tools-batch")
    async def tools_batch(req: BatchToolCallRequest):
        results = []
        try:
            from pangu.api.routes_tools import _get_server

            srv = _get_server()
            for call in req.calls[:20]:
                name = call.get("name", "")
                args = call.get("arguments", {})
                try:
                    r = await srv.handle_request({"method": "tools/call", "params": {"name": name, "arguments": args}})
                    content = r.get("result", {}).get("content", [])
                    text = content[0].get("text", "") if content else ""
                    try:
                        data = json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        data = text
                    results.append({"name": name, "code": 0, "data": data})
                except Exception as e:
                    results.append({"name": name, "code": 500, "error": str(e)})
            return {"code": 0, "data": {"total": len(results), "results": results}}
        except Exception as e:
            return {"code": 500, "error": str(e)}

    # MCP HTTP 传输层（SSE + StreamableHTTP）
    from pangu.api.mcp_http import mcp_http_routes

    for route in mcp_http_routes:
        app.routes.insert(0, route)

    # 健康检查
    @app.get("/health", tags=["系统"])
    async def health():
        """健康检查 — 返回服务状态和版本"""
        from pangu.observability.health import quick_health_check

        return {"code": 0, "message": "ok", "data": quick_health_check()}

    @app.get("/health/deep")
    async def deep_health():
        from pangu.observability.health import deep_health_check

        return {"code": 0, "message": "ok", "data": deep_health_check(config=config)}

    # Prometheus 指标
    @app.get("/metrics")
    async def metrics():
        from pangu.observability.metrics import get_metrics_response, update_llm_metrics

        # 同步 LLM 引擎统计到 Prometheus 指标
        try:
            from pangu.core.config import PanguConfig
            from pangu.core.llm import LLMEngine

            llm_engine = LLMEngine(PanguConfig())
            update_llm_metrics(llm_engine)
        except Exception:
            pass
        content, media_type = get_metrics_response()
        from fastapi.responses import Response

        return Response(content=content, media_type=media_type)

    # 自主引擎状态
    @app.get("/api/v2/autonomous/status")
    async def autonomous_status():
        try:
            from pangu.memory.autonomous import get_autonomous_engine, get_scheduler

            engine = get_autonomous_engine(config)
            scheduler = get_scheduler()
            status = engine.get_status()
            status["scheduler"] = scheduler.get_status()
            return {"code": 0, "data": status}
        except Exception as e:
            return {"code": 500, "error": str(e)}

    # 系统信息
    @app.get("/api/v2/system/info")
    async def system_info():
        from pangu.observability.health import quick_health_check

        return {
            "code": 0,
            "message": "ok",
            "data": {
                "name": "盘古",
                "version": __version__,
                "health": quick_health_check(),
                "config": {
                    "host": config.host,
                    "port": config.port,
                    "backend": config.backend,
                    "llm_provider": config.llm_provider,
                    "embedding_model": config.embedding_model,
                },
                "auth": {
                    "enabled": app.state.auth_enabled,
                    "api_key_configured": bool(config.api_key),
                    "jwt_configured": bool(jwt_secret),
                    "jwt_algorithm": config.jwt_algorithm,
                    "user_count": len(user_store.list_users()),
                    "roles_configured": sorted(set(list(role_map.keys()) + list(config.jwt_user_roles.values()))),
                },
            },
        }

    # ─────────────────────────────────────────
    # RBAC 演示：受保护的资源端点
    # ─────────────────────────────────────────
    @app.get("/api/v2/rbac/whoami")
    async def rbac_whoami(request: Request):
        """返回当前 Principal（验证 RBAC 集成）。"""
        principal = get_principal(request)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "user_id": principal.user_id,
                "method": principal.method,
                "role": principal.role,
                "scopes": sorted(principal.scopes),
                "is_admin": principal.is_admin(),
            },
        }

    @app.get("/api/v2/rbac/admin-only")
    async def rbac_admin_only(_: Principal = Depends(require_scope("admin:*"))):  # noqa: B008
        """示例：admin 专属端点。"""
        return {"code": 0, "message": "ok", "data": {"ok": True}}

    # ─────────────────────────────────────────
    # ABAC 演示：受多租户/密级控制
    # ─────────────────────────────────────────
    @app.get("/api/v2/abac/whoami")
    async def abac_whoami(request: Request):
        """返回当前 subject 属性。"""
        from pangu.api.abac import Subject

        principal = get_principal(request)
        tenant_id = request.headers.get(config.abac_tenant_header, "") or config.abac_default_tenant
        subject = Subject.from_principal(principal, tenant_id=tenant_id)
        if request.headers.get(config.abac_tenant_header):
            subject.tenant_id = request.headers.get(config.abac_tenant_header)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "user_id": subject.user_id,
                "role": subject.role,
                "tenant_id": subject.tenant_id,
                "department": subject.department,
                "clearance": subject.clearance,
                "groups": sorted(subject.groups),
                "is_admin": subject.is_admin,
            },
        }

    @app.get("/api/v2/abac/tenants/{tenant_id}/memories/{mid}")
    async def abac_tenant_memory(
        tenant_id: str,
        mid: str,
        request: Request,
    ):
        """ABAC 演示：访问指定租户的记忆。需通过 tenant_isolation 等策略。"""
        # 手动构造依赖（避免 lambda 在 Depends 求值时无法捕获 path 参数）
        from pangu.api.abac import Resource as AbacResource

        decision = abac_authorize(
            "memories",
            "read",
            resource_loader=lambda ctx: AbacResource(
                type="memories",
                id=mid,
                owner_id="",
                tenant_id=tenant_id,
                classification=1,
                visibility="tenant",
            ),
        )(request)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "memory_id": mid,
                "tenant_id": tenant_id,
                "policy": decision.policy,
                "reason": decision.reason,
            },
        }

    # ─────────────────────────────────────────
    # 鉴权路由：/api/v2/auth/*
    # 公开端点，已在 _AuthMiddleware 豁免列表中
    # ─────────────────────────────────────────
    from pydantic import BaseModel, Field

    class LoginRequest(BaseModel):
        username: str = Field(..., min_length=1, max_length=64)
        password: str = Field(..., min_length=1, max_length=256)

    class RefreshRequest(BaseModel):
        refresh_token: str = Field(..., min_length=10)

    class LogoutRequest(BaseModel):
        refresh_token: str = ""  # 可选：同时撤销 refresh token

    def _get_auth(request: Request) -> dict:
        """从 ASGI scope 提取由中间件注入的鉴权信息。"""
        return request.scope.get("state", {}).get("auth", {}) or {}

    @app.post("/api/v2/auth/login")
    async def auth_login(req: LoginRequest):
        """账号密码登录，颁发 access + refresh token 对。token 内嵌 role + scope。"""
        if not jwt_secret:
            return JSONResponse(
                status_code=503,
                content={"code": 503, "message": "JWT not configured on server", "data": None},
            )
        if not user_store.verify(req.username, req.password):
            # 通用错误，避免泄露用户存在性
            return JSONResponse(
                status_code=401,
                content={"code": 401, "message": "Invalid username or password", "data": None},
            )
        role, scope_str = _resolve_user_scopes(req.username)
        abac_attrs = _resolve_user_abac_attrs(req.username)
        pair = issue_token_pair(
            user_id=req.username,
            secret=jwt_secret,
            access_ttl=config.jwt_access_ttl,
            refresh_ttl=config.jwt_refresh_ttl,
            algorithm=config.jwt_algorithm,
            scope=scope_str,
            role=role,
            tenant_id=abac_attrs.get("tenant_id", config.abac_default_tenant),
            department=abac_attrs.get("department", ""),
            clearance=int(abac_attrs.get("clearance", 0)),
            groups=abac_attrs.get("groups", []),
        )
        return {"code": 0, "message": "ok", "data": {**pair, "username": req.username}}

    @app.post("/api/v2/auth/refresh")
    async def auth_refresh(req: RefreshRequest):
        """用 refresh token 换取新 access token。保持原 role/scope。"""
        if not jwt_secret:
            return JSONResponse(
                status_code=503,
                content={"code": 503, "message": "JWT not configured on server", "data": None},
            )
        try:
            claims = verify_token(
                req.refresh_token, jwt_secret, expected_type=TOKEN_TYPE_REFRESH, algorithm=config.jwt_algorithm
            )
        except TokenExpiredError:
            return JSONResponse(
                status_code=401, content={"code": 401, "message": "Refresh token expired", "data": None}
            )
        except TokenInvalidError as e:
            return JSONResponse(status_code=401, content={"code": 401, "message": str(e.message), "data": None})

        if user_store.is_revoked(claims.jti):
            return JSONResponse(
                status_code=401, content={"code": 401, "message": "Refresh token revoked", "data": None}
            )

        # 旋转 refresh：撤销旧 jti，颁发新对（保持原 role/scope + ABAC 属性）
        user_store.revoke(claims.jti)
        role, scope_str = _resolve_user_scopes(claims.sub)
        abac_attrs = _resolve_user_abac_attrs(claims.sub)
        pair = issue_token_pair(
            user_id=claims.sub,
            secret=jwt_secret,
            access_ttl=config.jwt_access_ttl,
            refresh_ttl=config.jwt_refresh_ttl,
            algorithm=config.jwt_algorithm,
            scope=scope_str,
            role=role,
            tenant_id=abac_attrs.get("tenant_id", config.abac_default_tenant),
            department=abac_attrs.get("department", ""),
            clearance=abac_attrs.get("clearance", 0),
            groups=abac_attrs.get("groups", []),
        )
        return {"code": 0, "message": "ok", "data": pair}

    @app.get("/api/v2/auth/me")
    async def auth_me(request: Request):
        """从当前请求的 JWT 中提取身份信息。"""
        if not jwt_secret:
            return JSONResponse(
                status_code=503,
                content={"code": 503, "message": "JWT not configured on server", "data": None},
            )
        auth_info = _get_auth(request)
        if not auth_info or auth_info.get("method") != "jwt":
            return JSONResponse(
                status_code=401,
                content={"code": 401, "message": "Bearer token required", "data": None},
                headers={"WWW-Authenticate": 'Bearer realm="pangu"'},
            )
        claims = auth_info["claims"]
        principal = get_principal(request)
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "username": claims.sub,
                "jti": claims.jti,
                "iat": claims.iat,
                "exp": claims.exp,
                "scope": claims.scope,
                "role": principal.role,
                "scopes": sorted(principal.scopes),
            },
        }

    @app.post("/api/v2/auth/logout")
    async def auth_logout(request: Request, req: LogoutRequest):  # noqa: B008
        """撤销当前 access token（以及可选的 refresh token）。"""
        if not jwt_secret:
            return JSONResponse(
                status_code=503,
                content={"code": 503, "message": "JWT not configured on server", "data": None},
            )
        revoked = 0
        auth_info = _get_auth(request)
        if auth_info and auth_info.get("claims"):
            user_store.revoke(auth_info["claims"].jti)
            revoked += 1
        if req.refresh_token:
            try:
                claims = verify_token(
                    req.refresh_token, jwt_secret, expected_type=TOKEN_TYPE_REFRESH, algorithm=config.jwt_algorithm
                )
                user_store.revoke(claims.jti)
                revoked += 1
            except AuthError:
                pass
        return {"code": 0, "message": "ok", "data": {"revoked": revoked}}

    # ─────────────────────────────────────────
    # OpenAI 兼容：/v1/embeddings（供 openclaw memory search 使用）
    # ─────────────────────────────────────────
    from pydantic import BaseModel, Field

    class EmbeddingRequest(BaseModel):
        input: str | list[str] = Field(..., description="输入文本或文本列表")
        model: str = Field(default="onnx-embedding", description="嵌入模型名称（保留字段，实际固定用 ONNX）")
        encoding_format: str = Field(default="float", description="返回格式：float / base64")

    class EmbeddingResponse(BaseModel):
        object: str = "list"
        data: list[dict]
        model: str
        usage: dict

    @app.post("/v1/embeddings")
    async def v1_embeddings(req: EmbeddingRequest):
        """OpenAI 兼容的 Embedding 端点。

        供 openclaw memorySearch.provider=openai-compatible 调用。
        内部使用 Pangu ONNX 本地嵌入器，无需外部 API key。
        """

        inputs = [req.input] if isinstance(req.input, str) else req.input
        if not inputs:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "input must be non-empty", "type": "invalid_request_error"}},
            )

        try:
            from pangu.core.config import PanguConfig
            from pangu.memory.embedding import EmbeddingService

            svc = EmbeddingService(PanguConfig())
        except Exception as e:
            logger.warning(f"ONNX embedder unavailable, using hash fallback: {e}")
            # fallback：hash 向量（1536 维）
            dim = 1536
            results = []
            for text in inputs:
                h = __import__("hashlib", fromlist=["blake2b"]).blake2b(text.encode(), digest_size=dim // 8).digest()
                vec = [b / 255.0 for b in h]
                results.append(vec)
        else:
            # 正常路径：用 EmbeddingService
            results = []
            for text in inputs:
                vec = svc.embed(text)  # list or numpy array
                results.append(vec if isinstance(vec, list) else vec.tolist())

        data = []
        for i, vec in enumerate(results):
            data.append(
                {
                    "object": "embedding",
                    "index": i,
                    "embedding": vec if req.encoding_format == "float" else _b64_encode(vec),
                }
            )

        return {
            "object": "list",
            "data": data,
            "model": "onnx-embedding",
            "usage": {"prompt_tokens": sum(len(t.split()) for t in inputs), "total_tokens": 0},
        }

    def _b64_encode(vec: list[float]) -> str:
        import base64
        import struct

        raw = struct.pack(f"<{len(vec)}f", *vec)
        return base64.b64encode(raw).decode()

    # 仪表盘
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/health")

    # ── 知识图谱 API ──

    def _kg_row_rank(row: dict) -> tuple:
        """同名实体多行时挑哪一行留下：created_at 新者优先。

        复合主键 (id, tenant_id) 让同一概念按属主各存一行，读取侧必须挑一行代表。
        挑「更新的那条」而不是「任意一条」：归属改写这类操作会重跑抽取并刷新 created_at，
        新行才是当前真相（云端实测重复两组的 created_at 相差 4 天）。
        """
        return (str(row.get("created_at") or ""),)

    def _kg_source_counts(names: list[str]) -> dict[str, int]:
        """数出每个实体名出现在多少条记忆里。

        为什么现算：`entities_all` 建表时**没有** memory_count 列，而 graph 一直在读它，
        于是仪表盘上每个实体的「记忆数」恒为 0（会被读成「没有任何记忆提到它」）。
        这里按抽取器**同一个判定**重数一遍（knowledge_graph.auto_extract_entities 用的就是
        `kw.lower() in content.lower()`），所以数字与「盘古认为哪些记忆提到了它」一致。

        ⚠ 必须先解密：记忆在盘古里是 **Fernet 密文落库**（content 以 `gAAAAA` 开头）。
        直接在 `drawer.content` 上做子串匹配是在密文里数 —— 数字看着合理、实则随机
        （首次实现就踩到：密文里 'mcp' 偶然出现 16 次，于是 MCP 报了 16 而其余全 0）。
        解密写法照抄 search/engine.py 的既有范式：先判前缀再 decrypt，失败则跳过该条。

        单趟扫描 + 预算上限：O(记忆数 × 实体数) 次子串判断，超过预算就整体放弃、退回 0，
        避免大图谱把接口拖死（云端 19 实体 × 272 记忆 ≈ 5 千次，Fernet 解密 272 条为毫秒级）。
        """
        if not names:
            return {}
        try:
            drawers = app.state.memory.get_drawers() or []
        except Exception:  # noqa: BLE001 — 拿不到记忆就只影响这一个字段，不该让整图谱 500
            return {}
        budget = 5_000_000
        if len(drawers) * len(names) > budget:
            logger.warning("graph: 实体×记忆 组合数超预算，跳过 memory_count 统计")
            return {}
        lowered = [(n, str(n).strip().lower()) for n in names if n and str(n).strip()]
        counts = dict.fromkeys(names, 0)
        if not lowered:
            return counts
        for d in drawers:
            content = getattr(d, "content", "") or ""
            if isinstance(content, str) and content.startswith("gAAAAA"):
                try:
                    from pangu.memory.encryption import decrypt

                    content = decrypt(content)
                except Exception:  # noqa: BLE001 — 密钥不匹配/数据损坏：跳过这条，不猜
                    continue
            content = str(content).lower()
            if not content:
                continue
            for name, low in lowered:
                if low in content:
                    counts[name] += 1
        return counts

    @app.get("/api/v2/graph")
    async def graph_data(entity_type: str = None, limit: int = 100):
        """知识图谱数据。

        鉴权：2026-09-20 的注释曾写「已从豁免前缀中移除」——**当时并没有真移除**，
        `/api/v2/graph` 一直留在 `_EXEMPT_PREFIXES` 里，而本路由自身也没有任何校验，
        于是网关与路由两层都不设卡：实测匿名请求返回 200 + 全量图谱。2026-09-26 才真正
        从豁免前缀摘掉（见该处注释）。同名单里的 admin/platforms/dashboard 不受影响，
        它们在路由内自己校验 admin。

        按 id 聚合（2026-09-26）：`entities_all` 主键是 **(id, tenant_id)**，同一概念在
        不同属主下各有一行，而本路由走 REST 全库视角（`_TENANT_SCOPE` 默认空串 → 视图
        首句 `current_tenant()=''` 短路到全库），于是同一个实体会随属主数返回多份。
        云端实测：19 个实体被返回成 33 行（`default` 19 行 + `deepseek-harness` 14 行），
        每组的 name/type/description 逐字节相同。成因是一次性把记忆归属从 `default`
        整体改写成按平台分之后，下一轮抽取对同一 id 换了属主 → `INSERT OR REPLACE`
        变成 INSERT（见 knowledge_graph.add_entity 的说明）。

        这里按 id 合并成一份，**不动存储层**（多租户「同名实体互不覆盖」是有意设计，
        tests/test_p1_3_kg_tenant_scope.py 锁定）。同一 id 有多行时取 created_at 最新的那条。
        """
        try:
            from pangu.core.config import PanguConfig as _Cfg
            from pangu.memory.knowledge_graph import KnowledgeGraph

            # 2026-09-21：用权威配置 —— KnowledgeGraph 读 palace_path 下的
            # knowledge_graph.db，而权威 KG 在 v2 目录；普通 load() 的 palace_path
            # 指向 v1（云端实测：stats 报 19 实体、graph 返回 0）。
            cfg = _Cfg.load().authoritative_memory_config()
            kg = KnowledgeGraph(cfg)
            # 先按 id 合并再截断：否则 limit 会被重复行吃掉一半名额
            # （limit=100 实际只放得下 50 个不同实体）。
            merged: dict[str, dict] = {}
            for e in kg.list_entities(entity_type):
                cur = merged.get(e["id"])
                if cur is None or _kg_row_rank(e) > _kg_row_rank(cur):
                    merged[e["id"]] = e
            entities = list(merged.values())[:limit]
            src_counts = _kg_source_counts([e.get("name", "") for e in entities])

            edges = []
            seen_rel: set[tuple] = set()
            # 边构建范围随 limit 放宽(默认仍从 50 起),避免大图谱只剩孤岛节点
            edge_sources = min(len(entities), max(50, limit // 3))
            # 按**合并后**的实体逐个查：此前按重复行逐行查，同一条关系会被 append 两次，
            # 而 relations_all 同样是 (id, tenant_id) 复合主键、query_relations 也不去重
            # → 实测同一条边出现 4 次（2 实体行 × 2 关系行）。
            for e in entities[:edge_sources]:
                for r in kg.query_relations(subject_id=e["id"]):
                    key = (r["subject_id"], r["object_id"], r.get("predicate", ""))
                    if key in seen_rel:
                        continue
                    seen_rel.add(key)
                    edges.append(
                        {
                            "source": r["subject_id"],
                            "target": r["object_id"],
                            "predicate": r.get("predicate", ""),
                            "confidence": r.get("confidence", 1.0),
                        }
                    )
            nodes = [
                {
                    "id": e["id"],
                    "name": e["name"],
                    "type": e.get("type", "default"),
                    # entities_all 没有 memory_count 列（knowledge_graph.py 建表语句），
                    # 此前这里读不到就是 0，仪表盘上每个实体的「记忆数」恒为 0。
                    # 改为按抽取器同一判定现算（见 _kg_source_counts，注意要先解密）。
                    "memory_count": src_counts.get(e.get("name", ""), 0),
                    "description": e.get("description", ""),
                }
                for e in entities
            ]
            return {"code": 0, "data": {"nodes": nodes, "edges": edges, "total_entities": len(nodes)}}
        except Exception as e:
            return {"code": 500, "error": str(e)}

    # ── WebSocket 实时通知 ──

    from fastapi import WebSocket

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = ""):
        """实时通知。

        认证(SEC-004)：auth_enabled（config.api_key / jwt_secret 非空，或
        mcp_require_auth=true）时，要求 query 参数 token 为 api_key（常量时间
        比对）、有效 JWT 或有效盘古钥匙（pgk_）；未通过则在握手阶段以 1008 拒绝。
        auth 未启用时放行(本机部署)。
        """
        auth_enabled = bool(config.api_key or jwt_secret or getattr(config, "mcp_require_auth", False))
        if auth_enabled:
            token_ok = False
            if token:
                if config.api_key and hmac.compare_digest(token, config.api_key):
                    token_ok = True
                elif token.startswith("pgk_"):
                    try:
                        from pangu.keys import KeyManager

                        token_ok = bool(KeyManager().verify(token))
                    except Exception:
                        token_ok = False
                else:
                    try:
                        verify_token(token, jwt_secret, algorithm=config.jwt_algorithm)
                        token_ok = True
                    except Exception:
                        token_ok = False
            if not token_ok:
                await websocket.close(code=1008)
                return
        await websocket.accept()
        from ..memory.realtime import get_connection_manager

        mgr = get_connection_manager()
        client_id = f"client_{id(websocket)}"
        mgr.connect(client_id, websocket)

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data) if data.startswith("{") else {"action": data}

                action = msg.get("action", "")
                if action == "subscribe":
                    topic = msg.get("topic", "*")
                    mgr.subscribe(client_id, topic)
                    await websocket.send_text(json.dumps({"type": "subscribed", "topic": topic}))
                elif action == "unsubscribe":
                    topic = msg.get("topic")
                    mgr.unsubscribe(client_id, topic)
                    await websocket.send_text(json.dumps({"type": "unsubscribed", "topic": topic}))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
        except Exception:
            pass
        finally:
            mgr.disconnect(client_id)

    logger.info("盘古 app created with all routes")
    return app
