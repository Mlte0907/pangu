"""盘古 REST API 路由 — /api/v2/tools（通用 MCP 工具网关）

任何 HTTP 客户端可通过 POST /api/v2/tools/{tool_name} 调用全部 367 个 MCP 工具。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Any

logger = logging.getLogger("pangu.api.tools")
router = APIRouter()


class ToolCallRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


class BatchToolCallRequest(BaseModel):
    calls: list[dict] = Field(
        default_factory=list,
        description="批量调用列表，每项 {name, arguments}",
    )


@router.get("/tools")
async def list_tools():
    """列出所有可用的 MCP 工具"""
    try:
        from pangu.server.mcp_server import MCPServer
        from pangu.core.config import PanguConfig
        config = PanguConfig.load()
        config.ensure_dirs()
        server = MCPServer(config)
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
        from pangu.server.mcp_server import MCPServer
        from pangu.core.config import PanguConfig
        config = PanguConfig.load()
        config.ensure_dirs()
        server = MCPServer(config)
        tool = next((t for t in server.tools if t["name"] == tool_name), None)
        if not tool:
            return {"code": 404, "error": f"工具 {tool_name} 不存在"}
        return {"code": 0, "data": tool}
    except Exception as e:
        return {"code": 500, "error": str(e)}


@router.post("/tools/{tool_name}")
async def call_tool(tool_name: str, req: ToolCallRequest = None):
    """调用单个 MCP 工具

    Example:
        POST /api/v2/tools/pangu_search_memories
        {"arguments": {"query": "Python", "limit": 5}}
    """
    arguments = req.arguments if req else {}
    try:
        from pangu.server.mcp_server import MCPServer
        from pangu.core.config import PanguConfig
        config = PanguConfig.load()
        config.ensure_dirs()
        server = MCPServer(config)

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
