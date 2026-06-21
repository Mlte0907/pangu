"""盘古 MCP HTTP 传输层 — 支持 SSE + StreamableHTTP 远程访问"""
import asyncio
import json
import logging
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

logger = logging.getLogger("pangu.mcp.http")


async def _mcp_handle(request: Request) -> Response:
    """处理 MCP JSON-RPC 请求"""
    try:
        body = await request.body()
        msg = json.loads(body) if body else {}
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    session_id = request.headers.get("mcp-session-id") or request.query_params.get("session_id", str(uuid.uuid4()))

    try:
        from pangu.api.routes_tools import _get_server
        server = _get_server()
        response = await server.handle_request(msg)
        if response is None:
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}

        resp = JSONResponse(response)
        resp.headers["mcp-session-id"] = session_id
        resp.headers["Accept"] = "application/json, text/event-stream"
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
    Route("/mcp", _mcp_handle, methods=["POST"]),
    Route("/", _mcp_handle, methods=["POST"]),
    # SSE — 标准路径
    Route("/sse", _mcp_sse, methods=["GET"]),
    Route("/messages", _mcp_messages, methods=["POST"]),
]
