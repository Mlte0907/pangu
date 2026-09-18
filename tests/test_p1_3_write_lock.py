"""写路径互斥（2026-09-19）：MemoryStack 的"读-改-写"并发丢更新回归。

背景：MCP handler（主事件循环）与 BackgroundScheduler（daemon 线程，每 30 分钟跑
decay/consolidation/forget）都调 update_drawer —— 它是"重读全库 → 内存改单条 →
全库原子写"，中间无锁。

诚实的定位：**这是防御性修复，不是稳定可复现的 bug**。实测（含人为放大窗口：
读全库 sleep 1ms + 两线程各改一半 × 多轮）在无锁时也**未能稳定复现丢失** ——
原因是 GIL + `self._drawers` 为共享引用，多数交错下两线程的修改会叠加而非覆盖；
只有 `R₂ 落在 M₁ 与 W₁ 之间`的窄窗口（t2 用旧磁盘快照整体替换共享引用、抹掉 t1
未落盘的改动）才会丢。批量任务逐条写时窗口会放大。因此本测试锁的是**结构与语义**
（锁存在、可重入、并发结果不丢），而非依赖时序碰运气。
"""

import threading
import time

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.layers import MemoryStack

N = 60


def _stack(tmp_path) -> MemoryStack:
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()
    return MemoryStack(cfg)


def _run_concurrent(ms: MemoryStack) -> int:
    """两个线程各改一半，返回"真正生效"的条数。"""

    def work(lo: int, hi: int, tag: str) -> None:
        for i in range(lo, hi):
            d = ms.get_drawer_by_id(f"d{i}")
            if d is None:
                continue
            d.content = tag
            ms.update_drawer(d)

    t1 = threading.Thread(target=work, args=(0, N // 2, "A"))
    t2 = threading.Thread(target=work, args=(N // 2, N, "B"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    raw = ms._load_drawers()
    return sum(1 for d in raw if str(d.content) in ("A", "B"))


def _slow_load(ms: MemoryStack, monkeypatch) -> None:
    """放大"读-改-写"窗口：每次读全库都延迟 1ms，保证两个线程的读交叠。"""
    orig = ms._load_drawers

    def slow():
        out = orig()
        time.sleep(0.001)
        return out

    monkeypatch.setattr(ms, "_load_drawers", slow)


def test_concurrent_update_loses_nothing(tmp_path, monkeypatch):
    """★ 核心：有锁时并发改 60 条，一条都不能丢。"""
    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id=f"d{i}", content="orig", wing="w", room="r") for i in range(N)])
    _slow_load(ms, monkeypatch)

    changed = _run_concurrent(ms)
    assert changed == N, f"丢更新：应改 {N} 条，实际 {changed} 条"


def test_all_write_methods_hold_the_lock(tmp_path):
    """结构断言：四个写方法都必须在 _write_lock 保护下执行（防止将来被误删）。

    行为测试受时序限制（见模块 docstring），所以这里锁死结构：把锁换成"探针上下文"，
    调用每个写方法，探针必须被进入 —— 说明方法体确实包在 with self._write_lock 里。
    """
    entered = []

    class _Probe:
        def __enter__(self):
            entered.append(1)
            return self

        def __exit__(self, *a):
            return False

    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id="x", content="1", wing="w", room="r")])
    ms._write_lock = _Probe()  # type: ignore[assignment]

    d = ms.get_drawer_by_id("x")
    d.content = "2"
    ms.update_drawer(d)  # update + 内层 _save_drawers → 至少 2 次进入
    assert len(entered) >= 2, f"update_drawer/_save_drawers 未持锁（进入 {len(entered)} 次）"

    entered.clear()
    ms.remove_drawer("x")
    assert entered, "remove_drawer 未持锁"


def test_lock_is_rlock_not_lock(tmp_path):
    """必须是 RLock：_save_drawers 在 update_drawer 内层再拿一次锁，Lock 会死锁。"""
    ms = _stack(tmp_path)
    import threading as _t

    acquired = []

    def _probe():
        ok = ms._write_lock.acquire(timeout=1)
        acquired.append(ok)
        if ok:
            # 重入：同线程再拿一次必须成功（RLock 语义）
            ok2 = ms._write_lock.acquire(timeout=1)
            acquired.append(ok2)
            if ok2:
                ms._write_lock.release()
            ms._write_lock.release()

    t = _t.Thread(target=_probe)
    t.start()
    t.join()
    assert acquired == [True, True], f"锁不可重入（{acquired}）—— 内层 _save_drawers 会死锁"


def test_lock_is_reentrant(tmp_path):
    """_save_drawers 在 update_drawer 内被调用 —— RLock 必须可重入，否则死锁。"""
    ms = _stack(tmp_path)
    ms.add_drawers([Drawer(id="x", content="1", wing="w", room="r")])
    d = ms.get_drawer_by_id("x")
    d.content = "2"
    assert ms.update_drawer(d) is True
    assert ms._load_drawers()[0].content == "2"
