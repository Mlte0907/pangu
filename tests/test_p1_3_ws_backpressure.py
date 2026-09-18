"""事件推送背压回归（2026-09-19）。

两个实测确认的问题：

1. **跨线程投递静默失败**：`bridge_emit` 在 emit 所在线程里 `asyncio.get_event_loop()`，
   后台维护线程（BackgroundScheduler）没有 loop —— Python 3.12 直接抛
   RuntimeError("There is no current event loop in thread ...")，再被
   `except Exception: pass` 吞掉：后台事件永远推不到 WebSocket。（实测复现）
   修复：启动时捕获主循环 + 主线程 id；同线程 ensure_future，跨线程
   run_coroutine_threadsafe。

2. **慢客户端队头阻塞**：`ConnectionManager.emit` 裸 `await ws.send_text`，一个僵死
   连接会挂住整轮广播，后面的客户端全部收不到。修复：每连接 wait_for 超时（2s），
   超时即摘除。
"""

import asyncio
import threading

import pytest

from pangu.memory import realtime_bridge as rb
from pangu.memory.realtime import ConnectionManager


@pytest.fixture(autouse=True)
def _reset_bridge_globals():
    """bridge 用模块级 _main_loop/_main_thread_id —— 测试间必须复位。"""
    old = (rb._main_loop, rb._main_thread_id, rb._bridge_active)
    yield
    rb._main_loop, rb._main_thread_id, rb._bridge_active = old


class FakeWS:
    def __init__(self, delay: float = 0, fail: bool = False):
        self.sent: list[str] = []
        self.delay = delay
        self.fail = fail

    async def send_text(self, message: str) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(message)


# ── ① 跨线程投递 ──


def test_schedule_inside_loop_thread():
    """主循环线程内：ensure_future 即可，事件应送达。"""

    async def main():
        got = []

        class M:
            async def emit(self, t, d):
                got.append(t)
                return 1

        rb._main_loop = asyncio.get_running_loop()
        rb._main_thread_id = threading.get_ident()
        assert rb._schedule(M().emit("evt", {})) is True
        await asyncio.sleep(0.05)
        return got

    assert asyncio.run(main()) == ["evt"]


def test_schedule_from_background_thread():
    """★ 核心回归：后台线程投递必须真的送达（旧实现在这里静默丢事件）。"""

    async def main():
        got = []

        class M:
            async def emit(self, t, d):
                got.append((t, d))
                return 1

        rb._main_loop = asyncio.get_running_loop()
        rb._main_thread_id = threading.get_ident()  # 主线程 = 当前

        t = threading.Thread(target=lambda: rb._schedule(M().emit("bg.evt", {"x": 1})))
        t.start()
        t.join()
        await asyncio.sleep(0.05)
        return got

    got = asyncio.run(main())
    assert got == [("bg.evt", {"x": 1})], "后台线程投递的事件没送到（旧 bug 复活）"


def test_schedule_without_loop_returns_false():
    """没有运行中主循环（测试/CLI）：返回 False 并关闭协程，不产生 never-awaited 警告。"""

    async def never():
        return 1

    rb._main_loop = None
    rb._main_thread_id = threading.get_ident()
    assert rb._schedule(never()) is False


# ── ② 慢客户端（队头阻塞）──


def test_emit_times_out_slow_client_and_keeps_others():
    """★ 一个僵死连接不能拖住其他客户端。"""

    async def main():
        mgr = ConnectionManager()
        mgr._send_timeout = 0.1
        slow, fast = FakeWS(delay=10), FakeWS()
        mgr.connect("slow", slow)
        mgr.connect("fast", fast)
        mgr.subscribe("slow", "evt")
        mgr.subscribe("fast", "evt")

        n = await mgr.emit("evt", {"k": "v"})
        return n, len(fast.sent), "slow" in mgr._connections

    n, fast_n, slow_still_there = asyncio.run(main())
    assert fast_n == 1, "快客户端没收到消息"
    assert n == 1
    assert slow_still_there is False, "超时的慢连接应被摘除"


def test_emit_disconnects_failing_client():
    """发送抛异常的连接被摘除，其他连接不受影响。"""

    async def main():
        mgr = ConnectionManager()
        bad, good = FakeWS(fail=True), FakeWS()
        mgr.connect("bad", bad)
        mgr.connect("good", good)
        mgr.subscribe("bad", "evt")
        mgr.subscribe("good", "evt")
        n = await mgr.emit("evt", {})
        return n, "bad" in mgr._connections, len(good.sent)

    n, bad_there, good_n = asyncio.run(main())
    assert n == 1 and bad_there is False and good_n == 1
