"""盘古 REST API 路由 — /api/v2/tools（通用 MCP 工具网关）

任何 HTTP 客户端可通过 POST /api/v2/tools/{tool_name} 调用全部 367 个 MCP 工具。
"""
import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("pangu.api.tools")
router = APIRouter()


class ToolCallRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


class BatchToolCallRequest(BaseModel):
    calls: list[dict] = Field(
        default_factory=list,
        description="批量调用列表，每项 {name, arguments}",
    )


_cached_server = None

def _get_server():
    global _cached_server
    if _cached_server is not None:
        return _cached_server
    from pangu.server.mcp_server import MCPServer
    from pangu.core.config import PanguConfig
    config = PanguConfig.load()
    config.ensure_dirs()
    _cached_server = MCPServer(config)
    return _cached_server


def reset_server():
    """清除缓存的 MCPServer（写操作后调用）"""
    global _cached_server
    _cached_server = None


@router.get("/tools")
async def list_tools():
    """列出所有可用的 MCP 工具"""
    try:
        server = _get_server()
        tools = server.tools
        return {
            "code": 0,
            "data": {
                "total": len(tools),
                "tools": [
                    {"name": t["name"], "description": t.get("description", "")}
                    for t in tools
                ],
            },
        }
    except Exception as e:
        return {"code": 500, "error": str(e)}


@router.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """获取单个工具的详细信息"""
    try:
        server = _get_server()
        tool = next((t for t in server.tools if t["name"] == tool_name), None)
        if not tool:
            return {"code": 404, "error": f"工具 {tool_name} 不存在"}
        return {"code": 0, "data": tool}
    except Exception as e:
        return {"code": 500, "error": str(e)}


@router.post("/tools/{tool_name}")
async def call_tool(tool_name: str, req: ToolCallRequest = None):
    """调用单个 MCP 工具"""
    arguments = req.arguments if req else {}
    try:
        server = _get_server()
        request = {
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        result = await server.handle_request(request)

        if "error" in result:
            return {"code": result["error"].get("code", 500), "error": result["error"].get("message", "unknown")}

        content = result.get("result", {}).get("content", [])
        text = content[0].get("text", "") if content else ""

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = text

        return {"code": 0, "data": data}
    except Exception as e:
        logger.error(f"Tool call error: {tool_name}: {e}", exc_info=True)
        return {"code": 500, "error": str(e)}
