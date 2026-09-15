"""P2-1 Step 2 回归测试：advanced_reasoning 接入。

## 背景

`pangu/memory/advanced_reasoning.py` 有 4 个完整实现的高级推理能力
（因果链 / 趋势预测 / 异常检测 / 知识缺口），但从未被任何生产路径调用。
Step 2 把它接入 `handlers/analytics.py`（4 个工具）+ `autonomous.py`（2 个任务）。

## 接入前发现的真实 bug（被测试假绿掩盖）

`advanced_reasoning.py:517` 的 `_detect_content_anomalies` 用了 `d.title`，
但 `Drawer`（`core/palace.py:11-25`）**没有** title 字段（title 属于 WikiPage）。
真实数据上 `detect_anomalies()` 100% 抛 `AttributeError`。
`tests/test_v3_modules_f.py` 的 `try/except AttributeError: pass` 把它吞掉了，
于是 12/12 测试全绿而生产路径完全不可用。

本文件钉住三类断言：
  - must-block：`detect_anomalies` 在**有内容**的记忆上不得抛 AttributeError；
  - 行为正确：内容长度异常真的能被检出（且去掉 outlier 后消失）；
  - 接入存在：4 个工具已注册、2 个 autonomous 任务已在调度规则里。
"""

from datetime import datetime, timedelta

import pytest

from pangu.core.palace import Drawer
from pangu.memory.advanced_reasoning import AdvancedReasoning


def _d(id: str, content: str = "x", tags=None, hours: float = 0) -> Drawer:
    base = datetime(2025, 1, 1, 0, 0, 0)
    return Drawer(
        id=id,
        content=content,
        wing="w",
        room="r",
        tags=tags or [],
        created_at=(base + timedelta(hours=hours)).isoformat(),
    )


# ── Bug 回归：d.title AttributeError ──────────────────────────────


def test_detect_anomalies_does_not_raise_on_real_drawers():
    """must-block：有内容的记忆上 detect_anomalies 不得抛 AttributeError。

    这是接入前的真实缺陷：`_detect_content_anomalies` 用 `d.title`，
    而 Drawer 无该字段。此断言若失败，说明 bug 回归了。
    """
    drawers = [_d(f"d{i}", content="普通长度内容" * 3, hours=i) for i in range(10)]
    engine = AdvancedReasoning()
    # 关键：不包 try/except —— 让 AttributeError 直接暴露
    alerts = engine.detect_anomalies(drawers)
    assert isinstance(alerts, list)


def test_content_length_anomaly_is_detected():
    """行为正确：异常长的那条必须被 content_length 通道检出。"""
    drawers = [_d(f"d{i}", content="short", hours=i) for i in range(20)]
    drawers.append(_d("outlier", content="x" * 500, hours=25))
    engine = AdvancedReasoning()
    alerts = engine.detect_anomalies(drawers)
    content_alerts = [a for a in alerts if a.anomaly_type == "content_length"]
    assert len(content_alerts) >= 1, f"应检出 outlier 的长度异常，实际: {alerts}"
    assert any("outlier" in a.evidence for a in content_alerts)


def test_no_content_length_anomaly_without_outlier():
    """反向断言：去掉 outlier 后，长度异常应消失（证明是长度通道在起作用）。"""
    drawers = [_d(f"d{i}", content="short", hours=i) for i in range(20)]
    engine = AdvancedReasoning()
    alerts = engine.detect_anomalies(drawers)
    content_alerts = [a for a in alerts if a.anomaly_type == "content_length"]
    assert content_alerts == [], f"无 outlier 时不应有长度异常，实际: {content_alerts}"


# ── 接入存在性：工具与任务已注册 ──────────────────────────────────


def test_analytics_registers_four_advanced_tools():
    """4 个高级推理工具必须注册在 analytics handler 里。"""
    from pangu.server.handlers import analytics

    names = {t["name"] for t in analytics.TOOLS}
    expected = {
        "pangu_advanced_causal_chains",
        "pangu_advanced_trends",
        "pangu_advanced_anomalies",
        "pangu_advanced_knowledge_gaps",
    }
    missing = expected - names
    assert not missing, f"缺少工具: {missing}"
    # 且必须有对应 handler（TOOLS 里有但 HANDLERS 里没有 = 死工具）
    for n in expected:
        assert n in analytics.HANDLERS, f"工具 {n} 未注册 handler"


def test_advanced_tool_names_do_not_collide():
    """新工具名不得与既有工具重名（analytics 已有 growth_trend/anomaly_detect 等）。"""
    from pangu.server.handlers import analytics

    names = [t["name"] for t in analytics.TOOLS]
    advanced = [n for n in names if n.startswith("pangu_advanced_")]
    assert len(advanced) == len(set(advanced)), f"advanced 工具重名: {advanced}"


def test_autonomous_registers_two_new_tasks():
    """2 个新 autonomous 任务必须在 SCHEDULE_RULES 且可直接执行。"""
    from pangu.memory.autonomous import SCHEDULE_RULES, AutonomousMemoryEngine

    assert "anomaly_detection" in SCHEDULE_RULES, "anomaly_detection 未进调度规则"
    assert "knowledge_gaps" in SCHEDULE_RULES, "knowledge_gaps 未进调度规则"

    engine = AutonomousMemoryEngine()
    assert hasattr(engine, "_task_anomaly_detection")
    assert hasattr(engine, "_task_knowledge_gaps")

    drawers = [_d(f"d{i}", content="普通内容", hours=i) for i in range(10)]
    r1 = engine._task_anomaly_detection(drawers)
    assert r1.status == "success", f"anomaly_detection 失败: {r1.details}"
    assert "total_alerts" in r1.details

    r2 = engine._task_knowledge_gaps(drawers)
    assert r2.status == "success", f"knowledge_gaps 失败: {r2.details}"
    assert "total_gaps" in r2.details


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("discover_causal_chains", {"min_support": 3}),
        ("predict_trends", {}),
        ("detect_anomalies", {}),
        ("identify_knowledge_gaps", {}),
    ],
)
def test_all_public_methods_return_lists(method, kwargs):
    """4 个公开方法都必须返回 list（handler 依赖这一点做 limit 切片）。"""
    drawers = [_d(f"d{i}", content="内容" * (i + 1), tags=["t"], hours=i) for i in range(12)]
    engine = AdvancedReasoning()
    result = getattr(engine, method)(drawers, **kwargs)
    assert isinstance(result, list), f"{method} 应返回 list，实际 {type(result)}"
