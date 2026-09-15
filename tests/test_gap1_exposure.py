"""缺口 1 回归测试：核心链路工具必须出现在 tools/list。

防止 P0-0 同型问题：工具已注册在 HANDLERS，但暴露面过滤把它挡掉了，
导致"建了但静默不可达"。
"""

import pytest

# 核心链路工具清单（必须在默认暴露面内）
# 这些工具是 P0-0/P0-1/P2-1 接入的核心功能，不能被暴露面过滤挡住
MUST_BE_EXPOSED = [
    # P0-1 supersede 变更链追踪（缺口 1 要求必须在默认暴露面）
    "pangu_get_supersede_chain",
]


def test_core_tools_in_module_registry():
    """MUST_BE_EXPOSED 中的工具必须在 module_registry 的某个模块中注册。"""
    from pangu.server.module_registry import MODULE_REGISTRY

    all_tools = set()
    for entry in MODULE_REGISTRY:
        all_tools.update(entry.tool_names)

    for tool in MUST_BE_EXPOSED:
        assert tool in all_tools, (
            f"核心工具 '{tool}' 未在 module_registry 中注册。已注册模块: {[e.name for e in MODULE_REGISTRY]}"
        )


def test_core_tools_in_core_whitelist():
    """MUST_BE_EXPOSED 中的工具必须在 CORE_WHITELIST 中（默认暴露）。"""
    from pangu.server.module_registry import CORE_WHITELIST

    for tool in MUST_BE_EXPOSED:
        assert tool in CORE_WHITELIST, (
            f"核心工具 '{tool}' 不在 CORE_WHITELIST 中，不会默认暴露。CORE_WHITELIST 共 {len(CORE_WHITELIST)} 个工具"
        )


def test_core_tools_appear_in_tools_list():
    """MUST_BE_EXPOSED 中的工具必须出现在 tools/list 返回中（端到端验证）。"""
    import json
    import urllib.request

    try:
        req = urllib.request.Request(
            "http://127.0.0.1:19529/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                }
            ).encode(),
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tool_names = {t["name"] for t in data["result"]["tools"]}
    except Exception:
        pytest.skip("服务未运行，跳过端到端验证")

    for tool in MUST_BE_EXPOSED:
        assert tool in tool_names, (
            f"核心工具 '{tool}' 未出现在 tools/list 中（端到端）。当前暴露 {len(tool_names)} 个工具"
        )
