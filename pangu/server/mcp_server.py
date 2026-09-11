"""盘古 MCP 服务器 — 为 AI Agent 提供记忆工具接口
==================================================
盘古定位为专业的记忆系统（智能体的大脑组件），
MCP 工具只提供记忆的存储、检索、组织和管理功能。
不包含 Agent 执行功能（问答、对话、任务执行等）。

上层 Agent 框架通过 MCP 调用这些工具获取记忆数据后，
自行完成推理、决策和行动。"""

import asyncio
import json
import logging
import sys
import time

from ..core.config import PanguConfig
from ..core.llm import LLMEngine
from ..core.palace import Palace
from ..memory.knowledge_graph import KnowledgeGraph
from ..memory.layers import MemoryStack
from ..search.engine import HybridSearch
from ..wiki.engine import WikiEngine

logger = logging.getLogger("pangu.mcp_server")


class MCPServer:
    """MCP 协议服务器 — 35 个记忆工具"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._palace = None
        self._memory = None
        self._knowledge_graph = None
        self._wiki = None
        self._search = None
        self._llm = None
        self._persistent_cache = None
        self._warmup_task: asyncio.Task | None = None
        self._vacuum_task: asyncio.Task | None = None
        self._periodic_vacuum_task: asyncio.Task | None = None

        # 加载实验模块（根据 config.exposure.enabled_experiments）
        from .handlers import load_experimental_tools

        load_experimental_tools(self.config)

        # 启动期预热：llm_cache_warmup_on_start=True 且配置了 prompts 时，
        # 在构造阶段就把缓存预热调度为后台任务。
        #
        # 此前只在 `llm` property 内惰性调度，结果是「启动预热」名不副实：
        # 若服务启动后一直没人用到 LLM，预热永远不会发生，首次真实请求要
        # 承担全部冷启动延迟——而这正是该配置项要消除的问题。
        # 调度内部自带事件循环检测（无 loop 时安全跳过），且对已调度的情况
        # 幂等，因此在同步上下文构造对象也不会出问题。
        self._maybe_schedule_warmup()

    @property
    def palace(self):
        if self._palace is None:
            self._palace = Palace(self.config.palace_path)
        return self._palace

    @property
    def memory(self):
        if self._memory is None:
            # F3 修复（t8）：与 API 侧权威存储对齐——以 v2/chromadb 主目录
            # （pangu.db/v2_memories）为读写源，把 v1 palace/drawers.json
            # 作为只读合并源，使 list/search/stats 视图与 API 一致。
            # （此前 MemoryStack(self.config) 只读 palace，导致 MCP 侧
            # 维护/统计工具看不到真实存量——t8 补充修复项 F3。）
            from pathlib import Path

            v2_cfg = PanguConfig()
            v2_dir = Path(self.config.db_path) / "v2_memories"
            v2_dir.mkdir(parents=True, exist_ok=True)
            v2_cfg.palace_path = str(v2_dir)
            v2_cfg.identity_path = str(v2_dir / "identity.json")
            v2_cfg.wiki_path = str(v2_dir / "wiki.json")
            v1_drawers = Path(self.config.palace_path) / "drawers.json"
            extra = [v1_drawers] if v1_drawers.exists() else []
            self._memory = MemoryStack(config=v2_cfg, extra_drawers_files=extra)
        return self._memory

    @property
    def knowledge_graph(self):
        if self._knowledge_graph is None:
            self._knowledge_graph = KnowledgeGraph(self.config)
        return self._knowledge_graph

    @property
    def wiki(self):
        if self._wiki is None:
            self._wiki = WikiEngine(self.config)
        return self._wiki

    @property
    def search(self):
        if self._search is None:
            self._search = HybridSearch(self.config)
        return self._search

    @property
    def llm(self):
        if self._llm is None:
            self._llm = LLMEngine(self.config)
            self._persistent_cache = self._llm._persistent_cache
            self._maybe_schedule_warmup()
            self._maybe_schedule_vacuum()
        return self._llm

    def _ensure_initialized(self):
        """确保核心组件已初始化（首次调用时触发）"""
        _ = self.palace
        _ = self.memory
        _ = self.knowledge_graph
        _ = self.wiki
        _ = self.search
        _ = self.llm

    def invalidate_config_dependents(self) -> list[str]:
        """丢弃缓存中依赖 config 的组件，使其按新 config 惰性重建。

        背景（T6-F2 修复）：`pangu_config_reload` / `pangu_config_set` 只替换
        `server.config` 引用，但 `llm` / `search` / `wiki` 等属性在首次访问时已把
        **旧 config 对象**存进各自实例（如 `LLMEngine(self.config)`）。
        仅替换 `self.config` 不会影响这些已构造的对象——表现为「设置里改了
        LLM 模型/Key，保存后仍然用旧值」，且无任何报错。

        `memory` 与 `palace` 不在此列：它们的抽屉数据是长期状态，
        重建代价高且与 LLM 配置无关；其内部 config 已按需读取。

        Returns:
            实际被丢弃的缓存组件名（用于回执与排障）。
        """
        dropped: list[str] = []
        for attr in ("_llm", "_search", "_wiki"):
            if getattr(self, attr, None) is not None:
                setattr(self, attr, None)
                dropped.append(attr.lstrip("_"))
        # 持久化缓存句柄由 _llm 派生，必须同步清掉，否则
        # persistent_cache 属性会继续返回旧 engine 的缓存对象。
        if self._persistent_cache is not None:
            self._persistent_cache = None
            dropped.append("persistent_cache")
        return dropped

    def _maybe_schedule_warmup(self) -> None:
        """在事件循环可用时把缓存预热调度为后台任务

        行为：
        - 配置 llm_cache_warmup_on_start=False → 跳过
        - 配置 llm_cache_warmup_prompts 为空 → 跳过
        - 无运行中的事件循环（如单元测试中） → 跳过
        - 已调度过 → 跳过（幂等：__init__ 与 llm property 都会调用本方法）
        """
        if not getattr(self.config, "llm_cache_warmup_on_start", False):
            return
        if not getattr(self.config, "llm_cache_warmup_prompts", []):
            return
        if self._warmup_task is not None:
            # 幂等保护。同时防止重入：下面要访问 self.llm，而 llm property
            # 内部又会回调本方法，若无此短路会无限递归。
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（同步上下文或测试），跳过
            return
        self._warmup_task = loop.create_task(
            self.llm.auto_warmup_on_start(),
            name="pangu-llm-cache-warmup",
        )

    async def await_warmup(self) -> dict | None:
        """等待预热任务完成（用于 graceful shutdown）"""
        if self._warmup_task is None:
            return None
        try:
            return await self._warmup_task
        except Exception:
            return {"error": "warmup failed"}

    def _maybe_schedule_vacuum(self) -> None:
        """在事件循环可用时调度自动 VACUUM / 周期 VACUUM 后台任务

        行为：
        - llm_cache_vacuum_on_start=True → 启动时立即跑一次
        - llm_cache_vacuum_interval_hours > 0 → 周期执行
        - 无事件循环 → 跳过
        """
        if self._persistent_cache is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        # 启动时立即一次
        if getattr(self.config, "llm_cache_vacuum_on_start", False):
            self._vacuum_task = loop.create_task(
                self._run_vacuum(),
                name="pangu-llm-cache-vacuum-once",
            )
        # 周期任务
        interval = getattr(self.config, "llm_cache_vacuum_interval_hours", 0.0)
        if interval > 0:
            self._periodic_vacuum_task = loop.create_task(
                self.llm.start_periodic_vacuum(interval),
                name="pangu-llm-cache-vacuum-periodic",
            )

    async def _run_vacuum(self) -> dict:
        """包装 auto_vacuum_on_start 为 async"""
        return self.llm.auto_vacuum_on_start()

    # ── 工具定义（从 handlers 模块加载） ──

    @property
    def tools(self) -> list[dict]:
        from .handlers import TOOLS
        from .exposure import get_exposure_filter

        return get_exposure_filter(self.config).apply(TOOLS)

    # ── 工具调用（handler 字典路由） ──

    async def call_tool(self, tool_name: str, arguments: dict, request: dict = None) -> str:
        """调用工具并返回结果

        内部异常不再在此吞掉：交由上层 tools/call 统一捕获、
        写入错误统计（ErrorMonitor）并返回错误 JSON（见 R1-C）。
        """
        self._ensure_initialized()
        drawers = self.memory.get_drawers()

        from .exposure import get_exposure_filter
        from .handlers import HANDLERS

        # 先判存在、再判暴露。
        #
        # 顺序很关键：HANDLERS 里存在但未被任何模块登记的工具（测试注入、
        # 第三方扩展注册）若先走暴露面检查，会被判 code=1002「不在当前暴露面」——
        # 而真实原因是它不属于任何模块，报错信息完全指错方向，极难排查。
        handler = HANDLERS.get(tool_name)
        if handler is None:
            return json.dumps({"code": 1001, "error": f"未知工具: {tool_name}"})

        # 暴露面前置校验：未暴露工具返回 code=1002 结构化错误
        allowed, error_json = get_exposure_filter(self.config).check_callable(tool_name)
        if not allowed:
            return error_json

        return await handler(self, drawers, arguments)

    # ── MCP 协议 ──

    async def handle_request(self, request: dict) -> dict:
        """处理 MCP JSON-RPC 请求"""
        method = request.get("method", "")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "pangu", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.tools},
            }

        elif method == "tools/call":
            tool_name = request.get("params", {}).get("name", "")
            arguments = request.get("params", {}).get("arguments", {})
            # 传递完整request以便handler可以访问params
            t0 = time.time()
            error_msg = None
            try:
                result = await self.call_tool(tool_name, arguments, request)
                # 成功调用同样计入事件总线统计（不增长 total_errors）
                try:
                    from ..memory.error_monitor import get_error_monitor

                    get_error_monitor(self.config).record_success(tool_name)
                except Exception as _rec_err:
                    logger.debug(f"record_success 失败: {_rec_err}")
            except Exception as e:
                error_msg = str(e)
                # R1-C：工具级异常统一捕获并回写错误统计（ErrorMonitor）
                try:
                    from ..memory.error_monitor import get_error_monitor

                    get_error_monitor(self.config).record_error(tool_name, error_msg, severity="error")
                except Exception as _rec_err:
                    logger.debug(f"record_error 失败: {_rec_err}")
                result = json.dumps(
                    {"code": 5000, "error": error_msg, "tool": tool_name, "severity": "error"},
                    ensure_ascii=False,
                )
            finally:
                # 服务端透明采集：无论成功失败，都发布到事件总线，由 SelfImproveWorker
                # 决定是否提炼为记忆。客户端无感知。
                try:
                    from pangu.memory.self_improve import emit_tool_invocation

                    duration_ms = int((time.time() - t0) * 1000)
                    payload_result = None if error_msg else result
                    emit_tool_invocation(
                        tool_name=tool_name,
                        arguments=arguments,
                        result=payload_result,
                        success=error_msg is None,
                        source="mcp_stdio" if not getattr(self, "_http_mode", False) else "mcp_http",
                        extra={
                            "duration_ms": duration_ms,
                            "error": error_msg,
                        },
                    )
                except Exception as _e:
                    logger.debug(f"emit_tool_invocation 失败: {_e}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }

        elif method == "notifications/initialized":
            return None  # 无需响应

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"未知方法: {method}"},
            }

    async def run_stdio(self) -> None:
        """通过 stdio 运行 MCP 服务器"""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line.strip())
                response = await self.handle_request(request)

                if response:
                    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError:
                continue
            except EOFError:
                break

        if self._llm is not None:
            await self.llm.close()
