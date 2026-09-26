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
import subprocess
import sys

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

_LOG_HEADING_RE = re.compile(r"^## 13\. 维护日志\s*$", re.M)
_LOG_ENTRY_RE = re.compile(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\* — (.+)$", re.M)


def _log_section(doc: str) -> str:
    m = _LOG_HEADING_RE.search(doc)
    assert m, "说明书里找不到「## 13. 维护日志」这一节 —— 维护日志是硬性要求，不能删"
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
        f"请到 MAINTAINERS.md 的「## 13. 维护日志」追加一条。"
    )


# ── 说明书必须回答新维护者的四个问题 ──


def test_doc_answers_the_four_questions_a_new_maintainer_has():
    """是什么 / 怎么跑 / 有哪些功能 / 每个文件干什么 —— 缺一条就是说明书不合格。"""
    doc = DOC.read_text(encoding="utf-8")
    # 1. 是什么
    assert "## 1. 盘古是什么" in doc, "缺「盘古是什么」"
    assert "它不是什么" in doc, "要写明「不是什么」—— 这是最容易误解的地方"
    assert "主存" in doc, "要说明主存是什么（Drawer）"
    # 2. 运行模式
    assert "## 2. 运行模式" in doc, "缺「运行模式」"
    for mode in ("API 服务", "MCP over HTTP", "MCP over stdio", "CLI", "自主引擎"):
        assert mode in doc, f"运行模式缺「{mode}」"
    # 3. 功能
    assert "## 3. 功能地图" in doc, "缺「功能地图」"
    for domain in ("存取管道", "搜索", "知识", "生命周期", "质量治理", "多智能体", "多模态"):
        assert domain in doc, f"功能地图缺「{domain}」能力域"
    # 4. 每个文件
    assert "docs/FILE_INDEX.md" in doc, "必须指向逐文件索引"


def test_file_index_is_current():
    """自动生成的文件索引必须与真实目录树一致 —— 索引一旦过期就会误导人。"""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_file_index.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"文件索引已过期，请运行 scripts/gen_file_index.py：{r.stderr.strip()}"


def test_file_index_covers_the_biggest_modules():
    idx = (ROOT / "docs" / "FILE_INDEX.md").read_text(encoding="utf-8")
    n = sum(1 for line in idx.splitlines() if line.startswith("| `"))
    assert n >= 300, f"索引只有 {n} 条条目，346 个文件里很多没进去"
    for must in ("knowledge_graph.py", "layers.py", "mcp_server.py", "server.py", "llm.py"):
        assert must in idx, f"索引里找不到 {must}"


def test_manual_does_not_hardcode_the_python_version():
    """说明书不能写死 Python 版本号。

    2026-09-26 实测踩到：手册写「Python 3.13」，那是**本地** venv 的版本；
    云端 `.venv` 其实是 3.11.2，而且服务 `ExecStart` 用的就是它。
    写死版本号的文档必然腐烂 —— 改成「去哪儿核实」而不是「是多少」。
    """
    doc = DOC.read_text(encoding="utf-8")
    assert "3.13，`" not in doc and "| Python | 3.13" not in doc, (
        "说明书把 Python 版本写死成 3.13 了。云端实测是 3.11.2、本地 3.13.5，"
        "应该写「以 `.venv/bin/python -V` 为准」"
    )
    assert ".venv/bin/python -V" in doc, "应给出核实命令，而不是写死一个版本号"


def test_manual_records_the_local_vs_cloud_python_skew():
    """本地与云端 Python 版本不同这件事必须留在说明书里。

    不写下来的后果：改完本地测试绿就以为能上线，而线上跑的是另一个 Python。
    """
    doc = DOC.read_text(encoding="utf-8")
    assert "3.11.2" in doc and "3.13.5" in doc, "应记录云端/本地各自的实测版本"
    assert "测试绿不等于能上线" in doc, "要写明这个风险"


# ── AGENTS.md 必须保持精简，且它的节索引不能骗人 ──


def test_agents_md_section_index_points_at_real_sections():
    """AGENTS.md 的「看哪节」必须指向**真实存在**的节号。

    2026-09-26 实际踩到：手册插入三节（全部右移）后，AGENTS.md 的索引表没跟着改，
    于是索引把读者指到错误的节 —— **索引错了比没有索引更糟**。
    """
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    real = {int(m.group(1)): m.group(2).strip() for m in re.finditer(r"^## (\d+)\.\s*(.+)$", doc, re.M)}
    assert real, "说明书里连一个 `## N. 标题` 都没有，索引无从谈起"

    # 索引写在表格里，每行形如 `| 说明…… | §N 标题文字 |`
    # 只认表格行：正文里的散文引用（如「§0 四条认知错误、§10 已知坑）。」）不是索引。
    table = "\n".join(l for l in agents.splitlines() if l.lstrip().startswith("|"))
    pairs = re.findall(r"§(\d+)\s+([^|｜\n]+)", table)
    assert len(pairs) >= 8, f"AGENTS.md 的表格里只解析出 {len(pairs)} 条「§N 标题」索引，格式可能坏了"

    bad_number, bad_title = [], []
    for num, title in pairs:
        n, want = int(num), title.strip()
        if n not in real:
            bad_number.append(f"§{n}")
        elif not (real[n].startswith(want) or want.startswith(real[n])):
            # 允许索引用短标题、说明书带括号后缀；但不能张冠李戴（§10 ≠ 维护日志）
            bad_title.append(f"§{n} 索引写「{want}」，实际是「{real[n]}」")
    assert not bad_number, (
        f"AGENTS.md 引用了不存在的节 {bad_number}；说明书现有编号 {sorted(real)}"
    )
    assert not bad_title, "AGENTS.md 的节索引与说明书标题对不上：\n  " + "\n  ".join(bad_title)


def test_agents_md_stays_slim():
    """AGENTS.md 必须保持精简 —— 它被**自动注入每个会话**，篇幅一大就稀释注意力。

    2026-09-26 用户明确提出这个问题：AGENTS.md 变长会影响判断，应该做索引。
    所以细节全搬进 MAINTAINERS.md，这里只留硬规则 + 速查 + 章节索引 + 两条教训。
    预算 4KB 是刻意紧的。
    """
    agents = ROOT / "AGENTS.md"
    assert agents.exists(), "AGENTS.md 不见了"
    size = agents.stat().st_size
    assert size <= 4096, (
        f"AGENTS.md {size} 字节，超过 4KB 预算。细节搬进 MAINTAINERS.md，AGENTS.md 只留索引。"
    )


def test_agents_md_is_an_index_not_a_manual():
    """AGENTS.md 必须指向说明书，而不是把说明书内容抄一遍。"""
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "MAINTAINERS.md" in text, "AGENTS.md 必须引用 MAINTAINERS.md"
    assert "FILE_INDEX.md" in text, "AGENTS.md 应指向自动生成的文件索引"
    for moved in ("pip install -e", "dsh-brake", "invalidate_config_dependents", "fail2ban"):
        assert moved not in text, f"`{moved}` 属于说明书细节，不该留在被逐会话注入的 AGENTS.md"


def test_manual_absorbed_the_old_agents_content():
    """从 AGENTS.md 迁走的内容必须真的在说明书里，不能凭空丢失。"""
    doc = DOC.read_text(encoding="utf-8")
    for topic, needle in (
        ("行为规则", "会话开始先查记忆"),
        ("配置热加载", "invalidate_config_dependents"),
        ("容器约束", "no_new_privs"),
        ("死亡循环预防", "dsh-brake"),
        ("环境表", "0.0.0.0:19529"),
    ):
        assert needle in doc, f"AGENTS.md 迁出的「{topic}」在说明书里找不到（关键字 {needle}）"


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
    section = re.search(r"## 9\. 自主任务(.*?)(?=\n## )", doc, re.S)
    assert section, "说明书里找不到「## 9. 自主任务」这一节"
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
