"""盘古 FastAPI 服务器工厂（伏羲移植）"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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
from pangu.core.config import config
from pangu.store.migrations import init_db

logger = logging.getLogger("pangu.api.server")


def create_app() -> FastAPI:
    """创建 FastAPI 应用（伏羲移植版）"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
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
            logger.info(f"Warmup complete: {warmup['total']:.0f}ms (jieba={warmup['jieba']:.0f}ms, onnx={warmup['onnx']:.0f}ms, fts={warmup['fts_index']:.0f}ms)")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")

        # 自主记忆管理：检查是否需要运行维护周期
        try:
            from pangu.memory.autonomous import get_autonomous_engine
            engine = get_autonomous_engine(config)
            tick = engine.tick()
            if tick["should_run"]:
                logger.info(f"Autonomous maintenance: {len(tick['pending_tasks'])} tasks pending, running...")
                cycle = engine.run_cycle()
                logger.info(f"Autonomous cycle: {cycle.tasks_run} ran, {cycle.tasks_skipped} skipped, {cycle.tasks_failed} failed, {cycle.total_duration_ms:.0f}ms")
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

        logger.info("盘古 server started")
        yield

        # 停止后台调度器
        try:
            from pangu.memory.autonomous import get_scheduler
            get_scheduler().stop()
        except Exception:
            pass

        # 关闭
        logger.info("盘古 server stopped")

    app = FastAPI(
        title="盘古 v3.0",
        description="盘古 — LMM+Wiki 超智能记忆系统 (伏羲增强版)",
        version="3.0.0",
        lifespan=lifespan,
    )

    # CORS
    _cors_origins = (
        config.cors_origins
        if hasattr(config, "cors_origins") and config.cors_origins
        else [
            "http://localhost:19528", "http://127.0.0.1:19528",
            "http://localhost:8866", "http://127.0.0.1:8866",
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
                    status_code=429,
                    content={"error": "Rate limit exceeded", "retry_after": self.window}
                )
                await response(scope, receive, send)
                return

            # 记录请求
            self._requests.setdefault(client_ip, []).append(now)
            await self.app(scope, receive, send)

    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)

    # ── Block /docs from external access ──
    # 白名单：localhost / 127.0.0.1 / ::1 / starlette TestClient 内置的 testclient 哨兵
    _docs_allowed_clients = frozenset({"127.0.0.1", "localhost", "::1", "testclient"})

    class _BlockDocsMiddleware:
        """纯 ASGI 中间件：阻止外部访问 /docs 和 /openapi.json"""
        _ALLOWED = _docs_allowed_clients

        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] == "http":
                path = scope.get("path", "")
                if path in ("/docs", "/openapi.json"):
                    client = scope.get("client")
                    host = client[0] if client else ""
                    if host not in self._ALLOWED:
                        response = JSONResponse(
                            status_code=403,
                            content={"error": "Forbidden", "detail": "Documentation not accessible externally"},
                        )
                        await response(scope, receive, send)
                        return
            await self.app(scope, receive, send)

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

    app.add_middleware(_BlockDocsMiddleware)
    app.add_middleware(_MetricsMiddleware)

    # ── 双鉴权初始化（API Key + JWT） ──
    jwt_secret: str = config.jwt_secret
    # 只有当用户显式配置（jwt_users 非空 或 jwt_default_password 非默认值）时才生成密钥
    # 这样默认部署（不配 PANGU_API_KEY 也无 JWT 配置）下不强制鉴权，保持向后兼容
    jwt_explicitly_enabled = bool(config.jwt_users) or config.jwt_default_password != "pangu-admin"
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
    app.state.auth_enabled = bool(config.api_key or jwt_secret)

    # ── 鉴权中间件：API Key 或 JWT 二选一通过 ──
    class _AuthMiddleware:
        """双鉴权中间件：支持 X-API-Key + Authorization: Bearer <jwt>。

        启用条件：config.api_key 非空 或 jwt_secret 非空。
        公开端点始终豁免：/、/health*、/metrics、/docs、/openapi.json、/api/v2/auth/*。
        """
        _EXEMPT_PATHS = {"/", "/health", "/health/deep", "/metrics", "/docs", "/openapi.json", "/redoc"}
        _EXEMPT_EXACT = {"/api/v2/auth/login", "/api/v2/auth/refresh"}
        _EXEMPT_PREFIXES = ("/docs", "/redoc")

        def __init__(self, app: ASGIApp):
            self.app = app
            self.api_key = config.api_key or ""
            self.secret = jwt_secret
            self.algorithm = config.jwt_algorithm
            self.user_store = user_store
            self.enabled = bool(self.api_key or self.secret)

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http" or not self.enabled:
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            if (
                path in self._EXEMPT_PATHS
                or path in self._EXEMPT_EXACT
                or any(path.startswith(p) for p in self._EXEMPT_PREFIXES)
            ):
                await self.app(scope, receive, send)
                return

            # 归一化 headers
            headers: dict[str, str] = {}
            for k, v in scope.get("headers", []):
                try:
                    headers[k.decode("latin-1").lower()] = v.decode("latin-1", errors="ignore")
                except Exception:
                    continue

            result = verify_credentials(
                headers=headers,
                api_key=self.api_key,
                secret=self.secret,
                algorithm=self.algorithm,
                user_store=self.user_store,
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

    # MCP HTTP 传输层（SSE + StreamableHTTP）
    from pangu.api.mcp_http import mcp_http_routes
    for route in mcp_http_routes:
        app.routes.insert(0, route)

    # 健康检查
    @app.get("/health")
    async def health():
        from pangu.observability.health import quick_health_check
        return {"code": 0, "message": "ok", "data": quick_health_check()}

    @app.get("/health/deep")
    async def deep_health():
        from pangu.observability.health import deep_health_check
        return {"code": 0, "message": "ok", "data": deep_health_check()}

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
                "version": "3.0.0",
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
            "memories", "read",
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
            claims = verify_token(req.refresh_token, jwt_secret, expected_type=TOKEN_TYPE_REFRESH, algorithm=config.jwt_algorithm)
        except TokenExpiredError:
            return JSONResponse(status_code=401, content={"code": 401, "message": "Refresh token expired", "data": None})
        except TokenInvalidError as e:
            return JSONResponse(status_code=401, content={"code": 401, "message": str(e.message), "data": None})

        if user_store.is_revoked(claims.jti):
            return JSONResponse(status_code=401, content={"code": 401, "message": "Refresh token revoked", "data": None})

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
                claims = verify_token(req.refresh_token, jwt_secret, expected_type=TOKEN_TYPE_REFRESH, algorithm=config.jwt_algorithm)
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
        import numpy as np

        inputs = [req.input] if isinstance(req.input, str) else req.input
        if not inputs:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "input must be non-empty", "type": "invalid_request_error"}},
            )

        try:
            from pangu.memory.embedding import EmbeddingService
            from pangu.core.config import PanguConfig
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
            data.append({
                "object": "embedding",
                "index": i,
                "embedding": vec if req.encoding_format == "float" else _b64_encode(vec),
            })

        return {
            "object": "list",
            "data": data,
            "model": "onnx-embedding",
            "usage": {"prompt_tokens": sum(len(t.split()) for t in inputs), "total_tokens": 0},
        }

    def _b64_encode(vec: list[float]) -> str:
        import base64, struct
        raw = struct.pack(f"<{len(vec)}f", *vec)
        return base64.b64encode(raw).decode()

    # 仪表盘
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/health")

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        from fastapi.responses import HTMLResponse
        dashboard_path = Path(__file__).parent.parent / "ui" / "templates" / "dashboard.html"
        if dashboard_path.exists():
            return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)

    @app.get("/performance", include_in_schema=False)
    async def performance():
        from fastapi.responses import HTMLResponse
        perf_path = Path(__file__).parent.parent / "ui" / "templates" / "performance.html"
        if perf_path.exists():
            return HTMLResponse(content=perf_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Performance page not found</h1>", status_code=404)

    # ── WebSocket 实时通知 ──

    from fastapi import WebSocket

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
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
