"""缺口 3 回归测试：judge 四问准入接入 remember()。

验证 _admission_gate 在 remember() 尾部执行，标记 metadata。
"""

import pytest

from pangu.core.palace import Drawer


def test_admission_gate_exists_in_remember():
    """remember() 必须调用 _admission_gate。"""
    import inspect

    from pangu.memory.ingestion import remember

    source = inspect.getsource(remember)
    assert "_admission_gate" in source, "remember() 未调用 _admission_gate"


def test_admission_gate_no_source_marks_pending():
    """无 source_file 且无 tags → admission = pending_review。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test1", content="测试内容", wing="test", room="t")
    _admission_gate(drawer, None, "test1")

    assert drawer.metadata.get("admission") == "pending_review"
    assert "no_source" in drawer.metadata["admission_score"]["flags"]


def test_admission_gate_with_source_passes():
    """有 source_file → 通过支撑检查。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test2", content="测试内容", wing="test", room="t", source_file="/some/file.py")
    _admission_gate(drawer, None, "test2")

    assert drawer.metadata["admission_score"]["has_source"] is True
    assert drawer.metadata["admission_score"]["passed"] is True


def test_admission_gate_low_importance():
    """importance < 0.3 → 标记 low_importance。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test3", content="测试内容", wing="test", room="t", importance=0.1, tags=["tag1"])
    _admission_gate(drawer, None, "test3")

    assert "low_importance" in drawer.metadata["admission_score"]["flags"]
    assert drawer.metadata["admission_score"]["importance"] == 0.1


def test_admission_gate_does_not_block_write():
    """admission_gate 不应抛异常（不阻塞写入方）。"""
    from pangu.memory.ingestion import _admission_gate

    # 空 drawer（无 metadata）不应崩
    drawer = Drawer(id="test4", content="", wing="test", room="t")
    _admission_gate(drawer, None, "test4")
    assert "admission_score" in drawer.metadata


def test_admission_gate_score_structure():
    """admission_score 必须包含标准字段。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test5", content="测试", wing="test", room="t", importance=0.5)
    _admission_gate(drawer, None, "test5")

    score = drawer.metadata["admission_score"]
    assert "has_source" in score
    assert "importance" in score
    assert "flags" in score
    assert "passed" in score
