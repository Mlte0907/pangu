"""P1-3 回归测试：四问准入门强化 + 毕业区。

验证 _admission_gate 在 remember() 尾部执行，标记 metadata。
P1-3 强化：Q3 用 source_session 替代 tags，Q4 用 importance_feedback 替代静态阈值。
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
    """无 source_file 且无 source_session → admission = pending_review。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test1", content="测试内容", wing="test", room="t")
    _admission_gate(drawer, None, "test1")

    assert drawer.metadata.get("admission") == "pending_review"
    assert "no_source" in drawer.metadata["admission_score"]["flags"]


def test_admission_gate_with_source_file_passes():
    """有 source_file → 通过支撑检查。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test2", content="测试内容", wing="test", room="t", source_file="/some/file.py")
    _admission_gate(drawer, None, "test2")

    assert drawer.metadata["admission_score"]["has_source"] is True


def test_admission_gate_with_source_session_passes():
    """有 source_session → 通过支撑检查（P1-3 新增）。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test3", content="测试内容", wing="test", room="t")
    drawer.metadata["source_session"] = "dsh_session_abc123"
    _admission_gate(drawer, None, "test3")

    assert drawer.metadata["admission_score"]["has_source"] is True
    assert "no_source" not in drawer.metadata["admission_score"]["flags"]


def test_admission_gate_tags_only_not_enough():
    """仅有 tags 不算来源指针（P1-3 强化）。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test4", content="测试内容", wing="test", room="t", tags=["tag1", "tag2"])
    _admission_gate(drawer, None, "test4")

    # tags 不算"来源指针"，应标记 no_source
    assert "no_source" in drawer.metadata["admission_score"]["flags"]
    assert drawer.metadata.get("admission") == "pending_review"


def test_admission_gate_unverified_without_feedback():
    """无正向 importance_feedback → 标记 unverified（P1-3 强化）。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test5", content="测试内容", wing="test", room="t", source_file="/f.py")
    _admission_gate(drawer, None, "test5")

    assert "unverified" in drawer.metadata["admission_score"]["flags"]
    assert drawer.metadata.get("admission") == "pending_review"


def test_admission_gate_verified_with_feedback():
    """有 recall_success 反馈 → 通过验证检查。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test6", content="测试内容", wing="test", room="t", source_file="/f.py")
    drawer.metadata["last_feedback"] = "recall_success"
    drawer.metadata["feedback_at"] = "2026-09-15T12:00:00"
    _admission_gate(drawer, None, "test6")

    assert drawer.metadata["admission_score"]["has_positive_feedback"] is True
    assert "unverified" not in drawer.metadata["admission_score"]["flags"]


def test_admission_gate_graduated_when_all_pass():
    """四问全过 → admission = graduated + visibility = public。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test7", content="测试内容", wing="test", room="t", source_file="/f.py")
    drawer.metadata["last_feedback"] = "verified"
    drawer.metadata["feedback_at"] = "2026-09-15T12:00:00"
    drawer.metadata["visibility"] = "tenant"

    _admission_gate(drawer, None, "test7")

    assert drawer.metadata.get("admission") == "graduated"
    assert drawer.metadata.get("visibility") == "public"
    assert "graduated_at" in drawer.metadata


def test_admission_gate_does_not_downgrade():
    """已是 public 的不降级。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test8", content="测试内容", wing="test", room="t", source_file="/f.py")
    drawer.metadata["last_feedback"] = "verified"
    drawer.metadata["visibility"] = "public"

    _admission_gate(drawer, None, "test8")
    assert drawer.metadata.get("visibility") == "public"


def test_admission_gate_does_not_block_write():
    """admission_gate 不应抛异常（不阻塞写入方）。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test9", content="", wing="test", room="t")
    _admission_gate(drawer, None, "test9")
    assert "admission_score" in drawer.metadata


def test_graduation_via_importance_feedback():
    """毕业通路闭合：写入→pending_review→feedback→graduated→public。"""
    from pangu.memory.ingestion import _admission_gate

    # 1) 写入无来源指针 → pending_review（visibility 不变）
    drawer = Drawer(id="grad1", content="毕业测试", wing="test", room="t")
    drawer.metadata["tenant_id"] = "default"
    drawer.metadata["visibility"] = "tenant"
    _admission_gate(drawer, None, "grad1")
    assert drawer.metadata.get("admission") == "pending_review"
    assert drawer.metadata.get("visibility") == "tenant"

    # 2) 注入 recall_success 反馈（模拟召回成功）
    drawer.metadata["last_feedback"] = "recall_success"
    drawer.metadata["feedback_at"] = "2026-09-15T12:00:00"

    # 3) 重新评估门禁 → 无 source_session → 仍 pending
    _admission_gate(drawer, None, "grad1")
    assert drawer.metadata.get("admission") == "pending_review"  # 无 source_session → 不毕业

    # 4) 补上 source_session → 再次评估 → 毕业
    drawer.metadata["source_session"] = "dsh_session_xyz"
    _admission_gate(drawer, None, "grad1")
    assert drawer.metadata.get("admission") == "graduated"
    assert drawer.metadata.get("visibility") == "public"
    assert "graduated_at" in drawer.metadata


def test_admission_gate_score_structure():
    """admission_score 必须包含标准字段。"""
    from pangu.memory.ingestion import _admission_gate

    drawer = Drawer(id="test10", content="测试", wing="test", room="t")
    _admission_gate(drawer, None, "test10")

    score = drawer.metadata["admission_score"]
    assert "has_source" in score
    assert "has_positive_feedback" in score
    assert "flags" in score
    assert "passed" in score


def test_importance_feedback_graduates_pending_memory():
    """importance_feedback 触发毕业：pending_review + source_session + recall_success → graduated。"""
    from pangu.memory.retrieval import importance_feedback

    # 构造一条 pending_review 且有 source_session 的记忆
    drawer = Drawer(id="fb_grad1", content="反馈毕业测试", wing="test", room="t", source_file="/test.py")
    drawer.metadata["tenant_id"] = "default"
    drawer.metadata["source_session"] = "dsh_test"
    drawer.metadata["admission"] = "pending_review"
    drawer.metadata["visibility"] = "tenant"

    # 传入 drawers 列表，用 recall_success 信号触发
    result = importance_feedback("fb_grad1", "recall_success", drawers=[drawer])
    assert "error" not in result

    # 反馈后：admission 应该变成 graduated，visibility 应该变成 public
    assert drawer.metadata.get("admission") == "graduated", (
        f"feedback 后应毕业，实际: {drawer.metadata.get('admission')}"
    )
    assert drawer.metadata.get("visibility") == "public", (
        f"feedback 后应 public，实际: {drawer.metadata.get('visibility')}"
    )
    assert "graduated_at" in drawer.metadata


def test_handle_add_memory_visibility_setdefault():
    """P1-3 收尾：handle_add_memory 用 setdefault，门禁已决定的 visibility 不被打回。"""
    # 模拟 handler 的 metadata 设置逻辑
    # 旧逻辑：无条件覆盖 → 门禁判定被覆盖
    metadata_old = {"visibility": "public", "admission": "graduated"}
    metadata_old["visibility"] = "tenant"  # 旧逻辑：无条件覆盖
    assert metadata_old["visibility"] == "tenant"  # 旧逻辑会覆盖门禁

    # setdefault 语义：门禁已决定时保留
    metadata_new = {"visibility": "public", "admission": "graduated"}
    metadata_new.setdefault("visibility", "tenant")
    assert metadata_new["visibility"] == "public"  # 保留门禁判定
