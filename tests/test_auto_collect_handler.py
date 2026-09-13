"""pangu_auto_collect handler 回归测试

背景（v0.2.x 审查发现的死工具）：
`pangu/server/handlers/io_tools.py` 的 handler 有**两处**互相独立的缺陷，
使 `pangu_auto_collect` 成为一个调用必炸的死工具：

1. 导入路径错误：写的是相对导入 `from ...memory.auto_collector import ...`，
   解析为 `pangu.memory.auto_collector`——该模块**从不存在**。
   auto_collector 自 v1.0.0 分层重构（commit 1122031）起就位于 `experimental/`。
2. 方法名错误：调用 `collect_from_file(...)`，但 `AutoCollector` 没有这个方法，
   只有 `collect_from_session(session_path, agent, max_messages, min_importance)`。

同一批错误也存在于 `scripts/fast_collect.py`。

这两处曾被"模块不存在"的表象掩盖（测试里用 try/except ImportError 静默跳过，
见 tests/test_v3_modules_f.py 的修复）。本文件用**不依赖 try/except 的硬断言**
锁住正确性，防止再次被静默掩盖。
"""

import json

import pytest


class _FakeServer:
    """handler 直接调用所需的最小子集"""

    def __init__(self, config):
        self.config = config


def test_auto_collect_handler_is_registered():
    """工具必须注册在 HANDLERS 与 TOOLS schema 中"""
    from pangu.server.handlers import HANDLERS, TOOLS

    assert "pangu_auto_collect" in HANDLERS
    names = {t["name"] for t in TOOLS}
    assert "pangu_auto_collect" in names


def test_auto_collect_module_import_path_is_correct():
    """experimental.auto_collector 必须真的存在且可导入

    这条断言直接锁住缺陷 1：若有人把导入路径改回 pangu.memory.auto_collector，
    本测试会红，而不是被静默跳过。
    """
    import experimental.auto_collector as mod

    assert mod.AutoCollector is not None


def test_auto_collect_class_has_collect_from_session_not_collect_from_file():
    """锁住缺陷 2：handler 调用的方法名必须真实存在

    AutoCollector 提供的是 collect_from_session，不是 collect_from_file。
    """
    from experimental.auto_collector import AutoCollector

    assert hasattr(AutoCollector, "collect_from_session")
    assert not hasattr(AutoCollector, "collect_from_file")


@pytest.mark.asyncio
async def test_auto_collect_handler_returns_result_for_missing_session_file(tmp_path):
    """对不存在的会话文件，handler 必须返回**正常结果**而非抛异常或报"不可用"

    修复前：抛 ModuleNotFoundError（pangu.memory.auto_collector 不存在）。
    修复后：返回 []（collect_from_session 对不存在的路径返回空列表）。
    """
    from pangu.core.config import PanguConfig
    from pangu.server.handlers.io_tools import handle_auto_collect

    cfg = PanguConfig(
        palace_path=str(tmp_path / "palace"),
        config_path=str(tmp_path / "config.json"),
        identity_path=str(tmp_path / "identity.txt"),
    )
    server = _FakeServer(cfg)

    raw = await handle_auto_collect(server, [], {"session_file": str(tmp_path / "nope.jsonl")})
    out = json.loads(raw)

    # 不得是"模块不可用"的错误——那正是修复前的表现
    assert not (isinstance(out, dict) and "不可用" in str(out.get("error", ""))), f"auto_collector 未被正确加载: {out}"
    # 不存在的会话文件应返回空列表
    assert out == []


@pytest.mark.asyncio
async def test_auto_collect_handler_does_not_silently_swallow_import_error(monkeypatch):
    """若 experimental.auto_collector 真的不可用，必须**明确报错**而非静默返回空

    设计决策：不可用与"没采集到"必须可区分，否则调用方无从判断功能是否失效。
    """
    import builtins

    from pangu.core.config import PanguConfig
    from pangu.server.handlers import io_tools

    cfg = PanguConfig(
        palace_path="/tmp/pangu_test_palace",
        config_path="/tmp/pangu_test_config.json",
        identity_path="/tmp/pangu_test_identity.txt",
    )
    server = _FakeServer(cfg)

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "experimental.auto_collector":
            raise ImportError("simulated experimental module unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    raw = await io_tools.handle_auto_collect(server, [], {"session_file": "/tmp/x.jsonl"})
    out = json.loads(raw)

    assert isinstance(out, dict)
    assert "error" in out
    assert "不可用" in out["error"]
