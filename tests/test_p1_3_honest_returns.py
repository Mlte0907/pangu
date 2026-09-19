"""落盘失败时的诚实返回（2026-09-19 修 BUG）。

背景：update_drawer / remove_drawer / remove_drawers 落盘失败（_save_drawers
返回 False）时仍返回成功值——调用方以为操作成功，磁盘其实没变。修复后：
失败 → 回滚内存到磁盘状态 + 返回 False/0。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.layers import MemoryStack


def _stack(tmp_path):
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()
    ms = MemoryStack(cfg)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r"), Drawer(id="b", content="B", wing="w", room="r")])
    return ms


def test_remove_drawer_returns_false_on_save_failure(tmp_path, monkeypatch):
    ms = _stack(tmp_path)
    monkeypatch.setattr(ms, "_save_drawers", lambda: False)
    assert ms.remove_drawer("a") is False
    # 内存状态回滚：磁盘上 a 仍在，重读后可见
    ids = [d.id for d in ms._load_drawers()]
    assert "a" in ids, "落盘失败后内存应回滚到磁盘状态（a 仍在）"


def test_remove_drawers_returns_zero_on_save_failure(tmp_path, monkeypatch):
    ms = _stack(tmp_path)
    monkeypatch.setattr(ms, "_save_drawers", lambda: False)
    assert ms.remove_drawers(["a", "b"]) == 0
    ids = [d.id for d in ms._load_drawers()]
    assert {"a", "b"} <= set(ids)


def test_update_drawer_returns_false_on_save_failure(tmp_path, monkeypatch):
    ms = _stack(tmp_path)
    # 用全新 Drawer：get_drawer_by_id 返回的是缓存对象的活引用，
    # 原地改会把存储层缓存一起污染（与磁盘无关的别名问题）
    d = Drawer(id="a", content="改过的内容", wing="w", room="r")
    monkeypatch.setattr(ms, "_save_drawers", lambda: False)
    assert ms.update_drawer(d) is False
    # 磁盘上内容未变
    disk = [x for x in ms._load_drawers() if x.id == "a"][0]
    assert disk.content == "A"


def test_success_path_unaffected(tmp_path):
    """正常路径行为不变（防止修过头）。"""
    ms = _stack(tmp_path)
    assert ms.remove_drawer("a") is True
    d = ms.get_drawer_by_id("b")
    d.content = "B2"
    assert ms.update_drawer(d) is True
    assert ms.remove_drawers(["b"]) == 1
