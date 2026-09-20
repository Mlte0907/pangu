"""盘古 MCP HTTP 传输层 — 支持 SSE + StreamableHTTP 远程访问"""

import asyncio
import json
import logging
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from pangu import __version__

logger = logging.getLogger("pangu.mcp.http")


def _inject_identity(msg: dict, request: Request):
    """P1-3 阶段 1.4 + 阶段 3：从 X-API-Key 解析身份，注入 MCP 请求上下文

    凭据可来自 X-API-Key，或 Authorization: Bearer <key>（兼容其他 MCP 客户端）。
    支持盘古钥匙（pgk_*）和平台接入 Token（pgp_*）。

    - 有凭据 → 查钥匙表/平台Token表 → {key_id, room, scope} 注入 msg["_identity"]
    - 无凭据 → 放行（mcp_require_auth=false 时）或 401（true 时）
    """
    api_key = (request.headers.get("X-API-Key") or "").strip()
    if not api_key:
        # 兼容 Authorization: Bearer <key>
        auth = request.headers.get("Authorization") or ""
        if auth[:7].lower() == "bearer ":
            api_key = auth[7:].strip()
    if not api_key:
        # 无凭据：检查 mcp_require_auth
        from pangu.core.config import PanguConfig

        config = PanguConfig.load()
        if config.mcp_require_auth:
            msg["_auth_error"] = "无凭据，mcp_require_auth=true 时需要 X-API-Key"
            msg["_auth_code"] = 401
        return

    # ── 静态 API Key 优先校验 ──
    # api_key 可能恰好以 pgk_ 开头（单人部署常见），若不先校验，会被下方
    # 盘古钥匙分支拦截并返回"无效的盘古钥匙"——永远走不到 api_key 比较路径。
    import hmac as _hmac

    from pangu.core.config import PanguConfig

    _cfg = PanguConfig.load()
    if _cfg.api_key and _hmac.compare_digest(api_key, _cfg.api_key):
        msg["_identity"] = {"key_id": "api_key_user", "room": "", "scope": "readwrite", "clearance": 0}
        return

    # ── 盘古钥匙（pgk_*）──
    if api_key.startswith("pgk_"):
        try:
            from pangu.keys import KeyManager

            km = KeyManager()
            identity = km.verify(api_key)
            if identity:
                msg["_identity"] = identity
                logger.debug(f"MCP identity: {identity['key_id']} room={identity['room']}")
            else:
                from pangu.core.config import PanguConfig

                config = PanguConfig.load()
                if config.mcp_require_auth:
                    msg["_auth_error"] = "无效的盘古钥匙"
                    msg["_auth_code"] = 401
                else:
                    logger.warning("MCP: invalid pangu key, proceeding as anonymous")
        except Exception as e:
            logger.debug(f"MCP identity parse failed: {e}")
        return

    # ── 平台接入 Token（pgp_*）──
    if api_key.startswith("pgp_"):
        try:
            from pangu.api.platform_tokens import get_platform_token_manager

            ptm = get_platform_token_manager()
            ident = ptm.verify(api_key)
            if ident:
                # 平台 Token → 统一身份格式，platform 作为 room
                msg["_identity"] = {
                    "key_id": ident.get("token_id", ""),
                    "room": ident.get("platform", ""),
                    "scope": "readwrite",
                    "clearance": 0,
                }
                logger.debug(f"MCP platform identity: {ident['token_id']} platform={ident['platform']}")
            else:
                from pangu.core.config import PanguConfig

                config = PanguConfig.load()
                if config.mcp_require_auth:
                    msg["_auth_error"] = "无效的平台接入 Token"
                    msg["_auth_code"] = 401
                else:
                    logger.warning("MCP: invalid platform token, proceeding as anonymous")
        except Exception as e:
            logger.debug(f"MCP platform token parse failed: {e}")
        return

    # ── 其他凭据格式 ──
    # 再查一次静态 api_key（上面的 pgk_ 分支可能因 compare_digest 不匹配而跳过）
    if _cfg.api_key and _hmac.compare_digest(api_key, _cfg.api_key):
        msg["_identity"] = {"key_id": "api_key_user", "room": "", "scope": "readwrite", "clearance": 0}
        return

    try:
        from pangu.keys import KeyManager

        km = KeyManager()
        identity = km.verify(api_key)
        if identity:
            msg["_identity"] = identity
            logger.debug(f"MCP identity: {identity['key_id']} room={identity['room']}")
        else:
            from pangu.core.config import PanguConfig

            config = PanguConfig.load()
            if config.mcp_require_auth:
                msg["_auth_error"] = "无效的 API Key"
                msg["_auth_code"] = 401
            else:
                logger.warning("MCP: invalid API key, proceeding as anonymous")
    except Exception as e:
        logger.debug(f"MCP identity parse failed: {e}")


async def _mcp_handle(request: Request) -> Response:
    """处理 MCP JSON-RPC 请求（StreamableHTTP + SSE 传输）"""
    if request.method == "GET":
        accept = request.headers.get("accept", "")
        session_id = str(uuid.uuid4())

        if "text/event-stream" in accept:
            root_path = request.scope.get("root_path", "")
            message_url = f"{root_path}/messages?session_id={session_id}"

            async def event_stream():
                endpoint_data = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": "pangu", "version": __version__},
                            "capabilities": {"tools": {}},
                            "endpoints": {"mcp": message_url},
                        },
                    }
                )
                yield f"event: endpoint\ndata: {message_url}\n\n"
                yield f"event: message\ndata: {endpoint_data}\n\n"
                try:
                    while True:
                        await asyncio.sleep(30)
                        yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    pass

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "mcp-session-id": session_id,
                },
            )

        resp = JSONResponse(
            {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "pangu", "version": __version__},
                    "capabilities": {"tools": {}},
                },
            }
        )
        resp.headers["mcp-session-id"] = session_id
        return resp

    try:
        body = await request.body()
        msg = json.loads(body) if body else {}
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    session_id = request.headers.get("mcp-session-id") or request.query_params.get("session_id", str(uuid.uuid4()))

    # P1-3 阶段 1.4：MCP 身份解析（X-API-Key → 钥匙表 → context）
    # 有凭据时识别房间并按 scope 限制；无凭据时放行（默认行为）
    _inject_identity(msg, request)

    # P1-3 阶段 1.4：mcp_require_auth 检查
    if "_auth_error" in msg:
        code = msg.pop("_auth_code", 401)
        error_msg = msg.pop("_auth_error")
        return JSONResponse(
            {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": code, "message": error_msg}},
            status_code=code,
        )

    try:
        from pangu.api.routes_tools import _get_server

        server = _get_server()
        response = await server.handle_request(msg)
        if response is None:
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        accept = request.headers.get("accept", "")
        if "text/event-stream" in accept:
            event_data = json.dumps(response, ensure_ascii=False)

            async def sse_response():
                yield f"event: message\ndata: {event_data}\n\n"

            return StreamingResponse(
                sse_response(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "mcp-session-id": session_id,
                },
            )

        resp = JSONResponse(response)
        resp.headers["mcp-session-id"] = session_id
        return resp
    except Exception as e:
        logger.error(f"MCP POST error: {e}", exc_info=True)
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}},
            status_code=500,
        )


async def _mcp_sse(request: Request) -> StreamingResponse:
    """SSE 长连接端点"""
    session_id = str(uuid.uuid4())
    root_path = request.scope.get("root_path", "")
    message_url = f"{root_path}/messages?session_id={session_id}"

    async def event_stream():
        yield f"event: endpoint\ndata: {message_url}\n\n"
        try:
            while True:
                await asyncio.sleep(30)
                yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _mcp_messages(request: Request) -> Response:
    """SSE 消息接收端点"""
    return await _mcp_handle(request)


mcp_http_routes = [
    # StreamableHTTP — 标准路径
    Route("/mcp", _mcp_handle, methods=["GET", "POST"]),
    Route("/", _mcp_handle, methods=["POST"]),
    # SSE — 标准路径
    Route("/sse", _mcp_sse, methods=["GET"]),
    Route("/messages", _mcp_messages, methods=["POST"]),
]
