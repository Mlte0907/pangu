"""可检索性体检（memory/retrievability.py）的回归测试。

体检要解决的是 2026-09-26 实际踩到的坑：重要信息存在于记忆里，但**埋在主题不相干
的另一条记忆中**，按内容去搜搜不到（用户原话「云端盘古可以从宿主机连上，这条我在
别的会话说过，你没找到」）。搜索排序救不了，knowledge_gaps 也不是这个方向。

本测试锁：
  1. 探针查询必须用**有区分度的词**（稀有/标识符），不能用到处都是的词；
  2. IPv4 不能被切成碎片（踩过：没有 IPv4 分支时 "113.45.134.86" 被切成 "113"）；
  3. 密文内容必须先解密，且解密失败要跳过而不是把密文当明文；
  4. 体检结果可序列化、能存能读；
  5. 任务已接进调度，且报告经 get_status() 暴露。
"""

import json
import pathlib
import tempfile
from collections import Counter

import pytest

from pangu.memory.retrievability import (
    _plaintext,
    _tokenize,
    audit_retrievability,
    build_probe_query,
    load_report,
    report_path,
    save_report,
)


class _FakeDrawer:
    def __init__(self, did, content, importance=1.0, vis="public", tags=None):
        self.id = did
        self.content = content
        self.importance = importance
        self.tags = tags or []
        self.metadata = {"visibility": vis, "tenant_id": "x"}
        self.wing = "tech"
        self.room = "general"


# ── 探针查询 ──


def test_probe_prefers_rare_terms():
    """常见词做不出有区分度的查询 —— 要挑语料里稀有的。"""
    df = Counter({"ssh": 80, "gradle": 2, "MCP": 90})
    q = build_probe_query("用 gradle 构建，ssh 连不上", df)
    assert "gradle" in q, q
    assert q.split().index("gradle") == 0, f"最稀有的应排最前：{q}"


def test_probe_keeps_ipv4_intact():
    """踩过的坑：没有 IPv4 分支时 IP 被切成 "113"，拼进查询反而拉低相关性。"""
    q = build_probe_query("连 113.45.134.86 的 19529 端口", Counter({"113": 1, "19529": 5}))
    assert "113.45.134.86" in q, f"IPv4 必须完整：{q}"
    assert "113" not in q.split(), f"不该出现 IP 碎片作为独立词：{q}"


def test_probe_handles_ip_with_port():
    q = build_probe_query("端点 http://113.45.134.86:19529/mcp", Counter())
    assert "113.45.134.86:19529" in q, q


def test_probe_returns_empty_when_no_distinctive_terms():
    """全是常见中文、没有标识符时应返回空串（该条跳过），而不是造个没用的查询。"""
    assert build_probe_query("这段全是中文描述，没有专有名词", Counter()) == ""


def test_tokenize_skips_short_and_stopwords():
    toks = _tokenize("a SSH b the MCP of c")
    assert "SSH" in toks and "MCP" in toks
    assert "a" not in toks and "the" not in toks and "of" not in toks


# ── 密文处理 ──


def test_plaintext_passes_through_non_ciphertext():
    assert _plaintext(_FakeDrawer("d", "明文内容")) == "明文内容"


def test_plaintext_decrypts_fernet(monkeypatch):
    """库里的 content 是 Fernet 密文（gAAAAA 开头），不解密就分词必然失败。"""
    seen = {}

    def fake_decrypt(c):
        seen["called"] = c
        return "解密后的内容 SSH 113.45.134.86"

    monkeypatch.setattr("pangu.memory.retrievability.decrypt", fake_decrypt)
    got = _plaintext(_FakeDrawer("d", "gAAAAAxxxxx"))
    assert got.startswith("解密后的内容")
    assert seen["called"].startswith("gAAAAA")


def test_plaintext_skips_on_decrypt_failure(monkeypatch):
    """解密失败要返回空串让该条跳过 —— 把密文当明文是 2026-09-19 修过的同类坑。"""
    monkeypatch.setattr(
        "pangu.memory.retrievability.decrypt", lambda c: (_ for _ in ()).throw(ValueError("bad key"))
    )
    assert _plaintext(_FakeDrawer("d", "gAAAAAxxxxx")) == ""


# ── 报告存取 ──


def test_report_roundtrip(tmp_path):
    from pangu.core.config import PanguConfig

    cfg = PanguConfig()
    cfg.palace_path = str(tmp_path)
    rep = {"checked": 3, "buried_count": 1, "buried": [{"id": "x", "head": "h", "probe_query": "q"}]}
    save_report(cfg, rep)
    assert report_path(cfg).exists()
    assert load_report(cfg) == rep


def test_load_report_returns_none_when_missing(tmp_path):
    from pangu.core.config import PanguConfig

    cfg = PanguConfig()
    cfg.palace_path = str(tmp_path)
    assert load_report(cfg) is None


def test_load_report_tolerates_corrupt_file(tmp_path):
    """报告文件损坏不该拖垮 status 接口。"""
    from pangu.core.config import PanguConfig

    cfg = PanguConfig()
    cfg.palace_path = str(tmp_path)
    p = report_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ 这不是合法 json", encoding="utf-8")
    assert load_report(cfg) is None


def test_audit_report_is_json_serializable(tmp_path):
    """TaskResult.details 与接口响应都要能 JSON 化。"""
    from pangu.core.config import PanguConfig
    from pangu.core.palace import Drawer

    cfg = PanguConfig()
    cfg.base_dir = pathlib.Path(tmp_path)
    cfg.db_path = pathlib.Path(tmp_path)
    cfg.palace_path = str(tmp_path)
    cfg.ensure_dirs()

    rep = audit_retrievability(cfg, max_memories=5, top_n=3)
    json.dumps(rep)  # 不抛异常即通过
    assert "checked" in rep and "buried" in rep
    assert isinstance(rep.get("duration_ms"), (int, float))


# ── 接线 ──


def test_task_is_registered_in_schedule():
    from pangu.memory.autonomous import SCHEDULE_RULES

    assert "retrievability" in SCHEDULE_RULES, "新任务没进调度表，永远不会被执行"
    assert SCHEDULE_RULES["retrievability"]["interval_hours"] >= 1


def test_task_is_dispatched_in_cycle():
    """注册表有 ≠ 会执行：调度处必须真的 append。"""
    import inspect

    from pangu.memory.autonomous import AutonomousMemoryEngine

    src = inspect.getsource(AutonomousMemoryEngine.run_cycle)
    assert '"retrievability"' in src, "调度处没接 retrievability，任务挂了不会被调用"
    assert "_task_retrievability" in src


def test_status_exposes_retrievability():
    """报告要有正常出口，否则跑完就没人看得见。"""
    import inspect

    from pangu.memory.autonomous import AutonomousMemoryEngine

    src = inspect.getsource(AutonomousMemoryEngine.get_status)
    assert "retrievability" in src, "get_status 没暴露体检结果"
    assert "load_report" in src


def test_new_task_does_not_break_existing_schedule():
    """加任务不能改动其它任务的规则。"""
    from pangu.memory.autonomous import SCHEDULE_RULES

    for name, hours in (
        ("consolidation", 24),
        ("readmission", 6),
        ("kg_enrichment", 6),
        ("crystallize", 12),
        ("knowledge_gaps", 12),
    ):
        assert name in SCHEDULE_RULES, f"{name} 不见了"
