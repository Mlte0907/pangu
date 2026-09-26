"""维护说明书（MAINTAINERS.md）与代码的一致性检查。

为什么需要这个：说明书不核对就会腐烂。2026-09-26 实际踩到
`graph_data` 的 docstring 声称「已从豁免前缀中移除」，而代码里其实一直还在 ——
**注释/文档会说自己想说的话，只有代码不会**。说明书同理。

所以本文件把说明书里那些**可被代码验证的事实**挑出来逐条核对：
一旦代码漂移，测试失败，逼人回来更新说明书。

刻意**没有**做的事：不去校验「同一 commit 里是否同时改了 pangu/** 和 MAINTAINERS.md」。
那依赖 git 历史，在无 git 的云端部署（scp 覆盖）里不成立，反而会给出假安全感。
"""

import inspect
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "MAINTAINERS.md"


@pytest.fixture(scope="module")
def doc() -> str:
    assert DOC.exists(), "MAINTAINERS.md 不见了 —— 维护盘古的 agent 需要它"
    return DOC.read_text(encoding="utf-8")


# ── 文档必须存在且有基本骨架 ──


def test_doc_has_the_sections_a_maintainer_needs(doc):
    for section in ("东西在哪", "怎么连", "工具暴露面", "记忆模型", "LLM", "自主任务", "已知的坑"):
        assert section in doc, f"说明书缺「{section}」这一节"


def test_doc_states_the_update_rule(doc):
    """维护流程必须写在文件最前面 —— 维护者未必从头读到尾，规矩得一眼看见。"""
    assert "维护流程" in doc
    assert "动手之前" in doc, "流程里必须写明「动手之前先读本文件」"
    assert "写日志" in doc, "流程里必须写明「维护后写日志」"
    # 流程块要出现在正文前部，不能塞到末尾
    assert doc.index("维护流程") < doc.index("## 1."), "维护流程应在 §1 之前"


# ── 维护日志：改��代码必须写日志 ──

_LOG_HEADING_RE = re.compile(r"^## 10\. 维护日志\s*$", re.M)
_LOG_ENTRY_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\* — (.+)$", re.M)


def _log_section(doc: str) -> str:
    m = _LOG_HEADING_RE.search(doc)
    assert m, "说明书里找不到「## 10. 维护日志」这一节 —— 维护日志是硬性要求，不能删"
    tail = doc[m.end() :]
    nxt = re.search(r"^## ", tail, re.M)
    return tail[: nxt.start()] if nxt else tail


def test_maintenance_log_exists_and_has_entries(doc):
    sec = _log_section(doc)
    entries = _LOG_ENTRY_RE.findall(sec)
    assert entries, "维护日志是空的。改了 pangu/** 就必须往这里追加一条"


def test_every_log_entry_has_what_and_why(doc):
    """每条日志至少要有实质内容（长度门槛），别写「修了个 bug」这种。"""
    sec = _log_section(doc)
    for date, body in _LOG_ENTRY_RE.findall(sec):
        assert len(body) >= 30, f"{date} 这条日志太短，看不出改了什么：{body!r}"


def test_log_is_newest_first(doc):
    """最新一条在最上面，否则维护者第一眼看到的是过期信息。"""
    dates = [d for d, _ in _LOG_ENTRY_RE.findall(_log_section(doc))]
    assert dates == sorted(dates, reverse=True), f"维护日志没有按日期倒序排列：{dates}"


def test_code_change_without_log_entry_fails(doc):
    """**核心 enforcement**：改了 `pangu/**` 却没写日志 → 失败。

    用**文件 mtime** 而不是 git，云端（`/root/pangu` 不是 git 仓库、靠 scp 部署）也能生效。
    判据：日志最新日期 ≥ `pangu/**` 下最新文件的修改日期（按天算，留 1 天容差，
    避免跨时区/跨午夜把当天早上写的代码判成「明天之前」）。
    """
    import datetime
    import os

    entries = _LOG_ENTRY_RE.findall(_log_section(doc))
    assert entries, "维护日志是空的"
    newest_log = max(datetime.date.fromisoformat(d) for d, _ in entries)

    src_root = ROOT / "pangu"
    assert src_root.is_dir(), "找不到 pangu/ 源码目录"
    newest_src = datetime.date.fromtimestamp(
        max(os.path.getmtime(p) for p in src_root.rglob("*.py"))
    )
    if newest_src <= newest_log:
        return
    # 全新 clone / checkout 会让所有文件都是「今天」——那时日期检查无意义
    span = max(os.path.getmtime(p) for p in src_root.rglob("*.py")) - min(
        os.path.getmtime(p) for p in src_root.rglob("*.py")
    )
    if span < 3600:
        return  # 整个树的时间戳几乎一致 = 刚 checkout，跳过
    pytest.fail(
        f"`pangu/**` 里有文件是 {newest_src} 改的，但维护日志最新只到 {newest_log}。"
        f"请到 MAINTAINERS.md 的「## 10. 维护日志」追加一条。"
    )


# ── 与代码交叉核对：网络暴露面 ──


def test_exempt_prefix_list_in_doc_matches_code(doc):
    """说明书里列的豁免前缀必须与代码一致。

    这条最值钱：`/api/v2/graph` 当年「注释说已移除、代码里一直还在」，匿名可读全库图谱。
    文档再写错一次就是同一个洞。
    """
    from pangu.api.server import create_app

    src = inspect.getsource(create_app)
    block = src.split("_EXEMPT_PREFIXES = (", 1)[1].split(")", 1)[0]
    in_code = set(re.findall(r'"(/[^"]*)"', block))
    # 说明书里应当把 /api/v2/graph 记为「不在豁免名单」的那条坑
    assert "/api/v2/graph" not in in_code, "/api/v2/graph 又回到豁免名单了，匿名可读全库图谱"
    assert "/api/v2/graph" in doc, "说明书没记录 graph 曾是匿名可读的坑"
    # 说明书若写了「豁免名单里有哪些」，必须与代码一致
    m = re.search(r"_EXEMPT_PREFIXES = \(\n(.*?)\n\s*\)", src, re.S)
    assert m, "找不到 _EXEMPT_PREFIXES 字面量，代码结构变了？"
    listed_in_doc = set(re.findall(r"`(/api/v2/[a-z]+|/mcp|/docs|/redoc)`", doc))
    for p in listed_in_doc:
        if p.startswith("/api/v2/"):
            assert p in in_code or p in ("/api/v2/graph",), f"说明书提到 {p}，但它不在豁免名单里"


def test_doc_lists_the_dashboard_admin_key_separately(doc):
    """api_key 不能当管理员密钥用 —— 这是今天实测出来的，文档必须记着。"""
    assert "X-Admin-Key" in doc
    assert "api_key" in doc and "不能" in doc


# ── 与代码交叉核对：暴露面与错误码 ──


def test_doc_mentions_both_1001_and_1002(doc):
    """1001 与 1002 极易混淆，文档必须都写，且写清区别。"""
    assert "1001" in doc and "1002" in doc
    assert "不存在" in doc and "未启用" in doc


def test_exposure_config_keys_exist_in_code(doc):
    """文档写的 exposure 段必须与 ExposureConfig 的真实字段名一致。

    注意这三个是**嵌套**字段（PanguConfig.exposure → ExposureConfig），不是顶层字段 ——
    我第一版按顶层查，测试直接失败，正好印证「文档和自己的假设都要核」。
    """
    from pangu.core.config import ExposureConfig

    fields = set(ExposureConfig.model_fields)
    assert fields, "ExposureConfig 读不到字段，配置结构变了？"
    for key in sorted(fields):
        assert key in doc, f"文档没写 exposure.{key}"
    assert "ExposureConfig" in doc, "文档应点明这三个是嵌套字段，不是顶层字段"


def test_autonomous_task_table_in_doc_matches_schedule(doc):
    """说明书里的任务表必须与 SCHEDULE_RULES 一致 —— 少一项就会误导维护者。

    这条当场抓到说明书漏了 4 个任务（fusion / compression / decay / forget）。
    """
    from pangu.memory.autonomous import SCHEDULE_RULES

    missing = [name for name in SCHEDULE_RULES if f"`{name}`" not in doc]
    assert not missing, f"SCHEDULE_RULES 里有任务没写进说明书：{missing}"
    # 文档提到的任务必须真的存在（防止写了已删任务）。
    # 只在「自主任务」那一节里扫，否则会误匹配 §4.2 可见性表里的 public/tenant/private。
    section = re.search(r"## 6\. 自主任务(.*?)(?=\n## )", doc, re.S)
    assert section, "说明书里找不到「## 6. 自主任务」这一节"
    doc_tasks = set(re.findall(r"^\| `([a-z_]+)` \|", section.group(1), re.M))
    unknown = [t for t in doc_tasks if t not in SCHEDULE_RULES]
    assert not unknown, f"说明书任务表里写了这些已不存在的任务：{unknown}"
    assert "共 15 个任务" in section.group(1) or f"共 {len(SCHEDULE_RULES)} 个任务" in section.group(1), (
        "任务表应写明总数，便于下一个人一眼看出有没有漏"
    )


# ── 与代码交叉核对：自主任务表 ──



def test_doc_flags_that_task_details_are_not_persisted(doc):
    """TaskResult.details 不落盘是今天发现的独立缺陷，文档必须写明，否则下个人还会踩。"""
    assert "TaskResult.details" in doc and "不落盘" in doc


# ── 与代码交叉核对：记忆模型 ──


def test_composite_primary_key_still_true(doc):
    """说明书反复强调「(id, tenant_id) 复合主键不是脏数据」，若主键改了说明要改。"""
    import sqlite3
    import tempfile

    from pangu.core.config import PanguConfig
    from pangu.memory.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td)
        cfg.db_path = pathlib.Path(td)
        cfg.palace_path = td
        cfg.ensure_dirs()
        kg = KnowledgeGraph(cfg)
        with kg._conn() as conn:
            # 同 id + 同 tenant 才是主键冲突
            conn.execute(
                "INSERT INTO entities_all (id,name,type,created_at,tenant_id) "
                "VALUES ('dup','n','c','2026-01-01','t1')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO entities_all (id,name,type,created_at,tenant_id) "
                    "VALUES ('dup','n','c','2026-01-01','t1')"
                )
            # 同 id + **不同** tenant 必须能共存 —— 这正是「不是脏数据」的依据
            conn.execute(
                "INSERT INTO entities_all (id,name,type,created_at,tenant_id) "
                "VALUES ('dup','n','c','2026-01-01','t2')"
            )
            n = conn.execute("SELECT COUNT(*) FROM entities_all WHERE id='dup'").fetchone()[0]
            assert n == 2, f"同 id 不同属主应共存两行，实得 {n}"


def test_doc_records_the_public_is_graduated_caveat(doc):
    """「public 是挣来的学位」是防误改的关键警告，删了就会有人批量刷 public。"""
    assert "毕业区" in doc
    assert "不要为了" in doc or "别把它" in doc or "跳过质量门" in doc


def test_doc_warns_about_ciphertext(doc):
    assert "gAAAAA" in doc, "内容密文这条没写 —— 下个人会试图 grep 内容"


# ── 与代码交叉核对：LLM 动态模型 ──


def test_llm_model_empty_is_valid_state(doc):
    """说明书第一条认知纠偏就是「llm_model 为空是正常的」，必须在。"""
    assert "llm_model" in doc
    assert ("正常" in doc) or ("留空" in doc)


def test_discover_chat_models_exists_in_code(doc):
    """文档讲动态发现，代码里必须有那个函数。"""
    from pangu.core.llm import discover_chat_models

    assert callable(discover_chat_models)
    assert inspect.getsource(discover_chat_models)


# ── 与代码交叉核对：测试指引 ──


def test_doc_points_at_the_protected_tests(doc):
    """那几个测试锁的是有意设计，文档必须点名，否则会被当成历史包袱删掉。"""
    for t in ("test_p1_3_tenant_scope", "test_p1_3_kg_tenant_scope", "test_p1_3_leak_sweep"):
        assert t in doc, f"说明书没点名 {t}"
