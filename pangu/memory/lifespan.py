"""盘古 — 生命周期管理（从伏羲 v1.5.6 移植）

核心特性：
1. 启动/关闭钩子注册
2. 后台守护线程管理
3. 事件总线自动订阅
"""

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("pangu.kernel.lifespan")


class Lifespan:
    """管理服务启动/关闭钩子"""

    def __init__(self):
        self._startup_hooks: list[Callable] = []
        self._shutdown_hooks: list[Callable] = []
        self._running = False
        self._bg_threads: list[threading.Thread] = []

    def on_startup(self, fn: Callable):
        """注册启动钩子"""
        self._startup_hooks.append(fn)
        return fn

    def on_shutdown(self, fn: Callable):
        """注册关闭钩子"""
        self._shutdown_hooks.append(fn)
        return fn

    def start(self):
        """启动生命周期"""
        logger.info("Lifespan starting...")
        for hook in self._startup_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"Startup hook failed: {e}")

        # 自动订阅 BehaviorCollector 到 EventBus（如果可用）
        try:
            from pangu.memory.event_bus import get_event_bus

            bus = get_event_bus()
            bus.start()
            logger.info("EventBus started")
        except Exception as e:
            logger.debug(f"EventBus subscription skipped: {e}")

        self._running = True

    def stop(self):
        """停止生命周期"""
        logger.info("Lifespan stopping...")
        self._running = False
        for hook in reversed(self._shutdown_hooks):
            try:
                hook()
            except Exception as e:
                logger.error(f"Shutdown hook failed: {e}")

        # 停止所有后台线程
        for thread in self._bg_threads:
            if thread.is_alive():
                thread.join(timeout=5)

    def spawn_background(
        self,
        target: Callable,
        name: str | None = None,
        interval: int | None = None,
    ):
        """启动后台守护线程

        Args:
            target: 目标函数
            name: 线程名称
            interval: 间隔秒数（如果提供，则循环执行）
        """
        if interval:

            def _looper():
                while self._running:
                    try:
                        target()
                    except Exception as e:
                        logger.error(f"Background task [{name}] error: {e}")
                    time.sleep(interval)

            thread = threading.Thread(target=_looper, name=name, daemon=True)
        else:
            thread = threading.Thread(target=target, name=name, daemon=True)

        thread.start()
        self._bg_threads.append(thread)
        return thread

    @property
    def running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {
            "running": self._running,
            "bg_threads": len(self._bg_threads),
            "startup_hooks": len(self._startup_hooks),
            "shutdown_hooks": len(self._shutdown_hooks),
        }


_lifespan: Lifespan | None = None


def get_lifespan() -> Lifespan:
    """获取全局生命周期管理器单例"""
    global _lifespan
    if _lifespan is None:
        _lifespan = Lifespan()
    return _lifespan
