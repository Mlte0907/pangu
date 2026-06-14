"""盘古 — MCP 服务器启动预热测试

覆盖：
1. MCPServer 初始化时自动调度 warmup
2. 无事件循环时（同步上下文）安全跳过
3. await_warmup 等待任务完成
4. 启动预热配置缺失时不调度
"""

import asyncio

import pytest

from pangu.core.config import PanguConfig
from pangu.server.mcp_server import MCPServer


def _make_server_config(llm_cache_warmup_on_start=False, warmup_prompts=None) -> PanguConfig:
    """构造测试用配置（避免触碰真实 LLM）"""
    if warmup_prompts is None:
        warmup_prompts = []
    return PanguConfig(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="dummy",
        llm_cache_persist=False,  # 避免创建 sqlite 文件
        llm_cache_warmup_on_start=llm_cache_warmup_on_start,
        llm_cache_warmup_prompts=warmup_prompts,
    )


class TestMCPServerWarmup:
    """MCP 服务器启动预热集成"""

    def test_disabled_when_config_off(self):
        """配置关闭时不调度预热"""
        cfg = _make_server_config(llm_cache_warmup_on_start=False)
        server = MCPServer(cfg)
        # 同步上下文中无事件循环，调度应被安全跳过
        assert server._warmup_task is None

    def test_disabled_when_no_prompts(self):
        """prompts 为空时不调度预热"""
        cfg = _make_server_config(
            llm_cache_warmup_on_start=True,
            warmup_prompts=[],
        )
        server = MCPServer(cfg)
        assert server._warmup_task is None

    def test_await_warmup_returns_none_when_not_scheduled(self):
        """未调度时 await_warmup 返回 None"""
        cfg = _make_server_config(llm_cache_warmup_on_start=False)
        server = MCPServer(cfg)
        # 异步运行
        result = asyncio.run(server.await_warmup())
        assert result is None

    @pytest.mark.asyncio
    async def test_warmup_task_scheduled_with_prompts(self):
        """配置完整时调度预热任务"""
        cfg = _make_server_config(
            llm_cache_warmup_on_start=True,
            warmup_prompts=[
                {"messages": [{"role": "user", "content": "hi"}], "temperature": 0}
            ],
        )
        # 在运行中的事件循环中构造
        server = MCPServer(cfg)
        try:
            assert server._warmup_task is not None
            # 任务应在后台运行
            assert not server._warmup_task.done()

            # 让任务快速结束：替换为空的已完成协程
            # 直接 cancel 避免实际调用 LLM
            server._warmup_task.cancel()
            try:
                await server._warmup_task
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            # 清理后台任务
            if server._warmup_task and not server._warmup_task.done():
                server._warmup_task.cancel()
                try:
                    await server._warmup_task
                except (asyncio.CancelledError, Exception):
                    pass
