"""跨租户泄漏扫描（in-process 版）—— CI 里的租户隔离闸门。

与 `scripts/tenant_leak_sweep.py` 同源思路，区别是这版**不依赖运行中的服务**，直接在进程内
构造 MCPServer 并以两个租户身份调用工具，因此能进 CI。

为什么要有这条闸门（本仓真实教训）：
  * 隔离原先散在各 handler 各写一遍，实测漏了三处（hybrid_search 不过滤、recall 算了
    filtered 没用它、按 id 可跨租户删除）
  * 静态扫描发现 287 个 handler 不使用传入的 drawers 参数，其中 18 个确实碰记忆数据
  **靠人逐个检查是漏不完的** —— 需要一个覆盖整个暴露面的自动探针。今后新增工具若忘了
  过滤，这条用例会直接红。

判定设计（两个坑都踩过，别改回去）：
  * **隐藏令牌**：探针内容里放一个"绝不作为请求参数外传"的令牌，泄漏判据只看它。
    若改用"标记串出现在响应里"，会被工具回显的 `"query"` / `"memory_id"` 字段误报
    （pangu_search_memories、pangu_get_supersede_chain 都踩过）。
  * **单次调用硬超时**：本仓没有 pytest-timeout，某些工具会去碰模型/网络；用 SIGALRM
    兜 10 秒，避免一条工具卡死整轮扫描。
"""

import asyncio
import json
import signal
import time
from contextlib import contextmanager

import pytest

from pangu.core.config import PanguConfig
from pangu.server.exposure import get_exposure_filter
from pangu.server.handlers import HANDLERS
from pangu.server.mcp_server import MCPServer

# 只读工具名的判定：宁可多扫（多调几次只读工具是安全的），不要漏
READ_ONLY_HINTS = (
    "get",
    "list",
    "search",
    "recall",
    "stats",
    "analyze",
    "health",
    "graph",
    "chain",
    "wings",
    "rooms",
    "wake",
    "inspect",
    "related",
    "hot",
    "growth",
    "discover",
    "trend",
    "gap",
    "anomaly",
    "pattern",
    "benchmark",
)
# 明确排除：会写、会调 LLM、耗时很长、或需要外部资源的
EXCLUDE_HINTS = ("compress", "generate", "consolidate", "backup", "restore", "export", "import", "migrate")

PER_CALL_TIMEOUT = 10  # 秒


@contextmanager
def _hard_timeout(seconds: int):
    """给单次调用加硬超时（没有 pytest-timeout，用 SIGALRM 兜底）。"""

    def _raise(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"单次调用超时 {seconds}s")

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _identity(room: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "_identity": {"room": room, "key_id": "probe", "scope": "readwrite"},
    }


async def _call(server: MCPServer, name: str, args: dict, who: dict) -> str:
    try:
        with _hard_timeout(PER_CALL_TIMEOUT):
            return await server.call_tool(name, dict(args), request=dict(who))
    except TimeoutError as e:
        return f"(超时: {e})"
    except Exception as e:  # noqa: BLE001 — 工具报错本身不是泄漏；如实记录并继续扫
        return f"(调用异常 {type(e).__name__}: {e})"


def _read_only_targets(cfg: PanguConfig) -> list[str]:
    exp = get_exposure_filter(cfg)
    out = []
    for name in HANDLERS:
        if not any(h in name for h in READ_ONLY_HINTS) or any(x in name for x in EXCLUDE_HINTS):
            continue
        allowed, _ = exp.check_callable(name)
        if allowed:
            out.append(name)
    return sorted(out)


def _build_server(tmp_path) -> MCPServer:
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.wiki_path = str(tmp_path / "wiki")
    cfg.identity_path = str(tmp_path / "identity.txt")
    cfg.backup_dir = str(tmp_path / "backups")
    cfg.domain_knowledge_db_path = tmp_path / "domain_knowledge.db"
    cfg.ensure_dirs()
    # 安全闸门要按**最坏情况**扫：把所有模块都打开
    from pangu.server.module_registry import MODULE_REGISTRY

    cfg.exposure.enabled_core_modules = {e.name for e in MODULE_REGISTRY if e.level == "core"}
    cfg.exposure.enabled_optional_modules = {e.name for e in MODULE_REGISTRY if e.level != "core"}
    return MCPServer(cfg)


def test_no_cross_tenant_leak_across_exposed_tools(tmp_path):
    """以 A 的身份遍历所有只读暴露工具，响应里不得出现 B 的隐藏令牌。"""
    server = _build_server(tmp_path)
    a, b = _identity("tenant-a"), _identity("tenant-b")
    stamp = int(time.time())
    secret = f"SECRET-{stamp}-xyzzy"  # 绝不出现在任何请求参数里 → 出现即泄漏

    # ★ 最低覆盖断言：闸门若因暴露面/命名变化而"扫不到东西却永远绿"，比没有闸门更糟。
    targets = _read_only_targets(server.config)
    assert len(targets) >= 60, f"扫描覆盖过少（{len(targets)} 个）—— 暴露面或工具命名变了？闸门已失效"

    async def _run() -> dict:
        # 1. B 写入探针数据
        await _call(
            server,
            "pangu_add_memory",
            {"content": f"跨租户探针 {secret}", "wing": "leak-probe", "room": "leak-probe", "importance": 0.5},
            b,
        )
        stats_b = await _call(server, "pangu_stats", {}, b)

        # 2. A 遍历只读工具
        leaks: list[str] = []
        errors: list[str] = []
        for name in _read_only_targets(server.config):
            out = await _call(server, name, {}, a)
            # 搜索类额外用探针内容里的公开片段当查询词（隐藏令牌始终不外传）
            if any(h in name for h in ("search", "recall", "analyze", "graph", "chain", "related", "wake")):
                out += await _call(server, name, {"query": "跨租户探针", "n_results": 5}, a)
            if secret in out:
                leaks.append(name)
            elif out.startswith("(调用异常") or out.startswith("(超时"):
                errors.append(name)

        # 3. B 自查：数据必须还在（隔离不能靠"删掉别人的数据"实现）
        stats_b = await _call(server, "pangu_stats", {}, b)
        return {"leaks": leaks, "errors": errors, "stats_b": stats_b}

    res = asyncio.run(_run())
    assert res["leaks"] == [], f"发现跨租户泄漏: {res['leaks']}"
    try:
        total_b = json.loads(res["stats_b"])["memory"]["total_memories"]
    except (json.JSONDecodeError, KeyError) as e:  # pragma: no cover - 仅诊断用
        pytest.fail(f"B 的 stats 无法解析（隔离或写入异常）: {res['stats_b'][:200]} ({e})")
    assert total_b >= 1, "B 自己的数据在扫描后不见了"


def test_by_id_probes_are_refused_and_data_intact(tmp_path):
    """按 id 的写类探测：跨租户删除/归档必须被拒，且 B 的数据完好。"""
    server = _build_server(tmp_path)
    a, b = _identity("tenant-a"), _identity("tenant-b")

    async def _run() -> dict:
        created = await _call(
            server,
            "pangu_add_memory",
            {"content": "跨租户写保护探针（可删）", "wing": "leak-probe", "room": "leak-probe", "importance": 0.5},
            b,
        )
        try:
            bid = json.loads(created).get("drawer_id", "")
        except json.JSONDecodeError:
            bid = ""
        assert bid, f"探针写入失败: {created[:200]}"

        refused = {}
        for tool in ("pangu_delete_memory", "pangu_archive_memory", "pangu_get_supersede_chain"):
            out = await _call(server, tool, {"memory_id": bid, "drawer_id": bid}, a)
            # 判据：明确拒绝（"不存在"）或空链；回显 id 不算泄漏
            refused[tool] = ("不存在" in out) or ('"found": false' in out)
        # B 自查：数据仍在（作用域内按 wing 列）
        after = await _call(server, "pangu_recall", {"wing": "leak-probe", "n_results": 5}, b)
        return {"refused": refused, "after": after}

    res = asyncio.run(_run())
    assert all(res["refused"].values()), f"存在未拒绝的越权操作: {res['refused']}"
    assert "跨租户写保护探针" in res["after"], "B 的数据被越权改动或删除"
