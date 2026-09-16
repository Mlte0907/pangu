"""P1-3 阶段 3：Wiki 租户化回归测试。

隔离轴与记忆/KG 完全一致：`metadata.tenant_id`（本租户）或 `metadata.visibility='public'`
（有意共享）；作用域为空（CLI/后台/admin）＝全库视角。

本测试锁定：作用域读（8 个读入口）、写归属、**同 id 不覆盖别租户**、
改/删/加链不越权、以及最容易漏的 **LLM 上下文泄漏**（auto_generate_page 会把"已有页面"
送给模型，那里不过滤就是把别人的标题摘要外发）。
"""

import asyncio
import pathlib
import tempfile

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import WikiPage
from pangu.memory.layers import reset_tenant_scope, set_tenant_scope
from pangu.wiki.engine import WikiEngine


def _mk_engine(td: str) -> WikiEngine:
    cfg = PanguConfig()
    cfg.base_dir = pathlib.Path(td)
    cfg.db_path = pathlib.Path(td)
    cfg.wiki_path = str(pathlib.Path(td) / "wiki")
    cfg.ensure_dirs()
    return WikiEngine(cfg)


def _page(pid: str, title: str, wing: str = "tech", metadata: dict | None = None) -> WikiPage:
    p = WikiPage(id=pid, title=title, wing=wing, content=f"{title} 的内容")
    if metadata:
        p.metadata = dict(metadata)
    return p


@pytest.fixture
def engine():
    with tempfile.TemporaryDirectory() as td:
        yield _mk_engine(td)


class _StubLLM:
    """最小 LLM 桩：记录被送进模型的"已有页面"上下文。"""

    def __init__(self):
        self.seen_context: list = []
        self.seen_all: list = []

    async def generate_wiki_page(self, title, memories, existing_pages):
        self.seen_context = list(existing_pages)
        return {"title": title, "content": "生成的内容", "summary": "生成摘要", "tags": []}

    async def detect_links(self, page, all_pages):
        self.seen_all = list(all_pages)
        return []


def test_write_stamps_tenant(engine):
    """写入落当前租户归属（读回用全库视角，避免"自己看自己"的假阳性）。"""
    token = set_tenant_scope("dsh")
    try:
        engine.create_page(_page("w1", "盘古部署"))
    finally:
        reset_tenant_scope(token)
    assert engine.get_page("w1").metadata["tenant_id"] == "dsh"
    assert engine.get_page("w1").metadata.get("visibility", "private") == "private"


def test_read_paths_are_scoped(engine):
    """8 个读入口都要按作用域裁剪。"""
    token = set_tenant_scope("other")
    try:
        engine.create_page(_page("other1", "别家的页面"))
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("other1") is None
        assert engine.get_page_by_title("别家的页面") is None
        assert engine.list_pages() == []
        assert engine.get_backlinks("other1") == []
        assert engine.export_graph() == {"nodes": [], "edges": []}
        assert engine.stats()["total_pages"] == 0
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("other")
    try:
        assert engine.get_page("other1") is not None
    finally:
        reset_tenant_scope(token)


def test_public_visible_to_all_tenants(engine):
    token = set_tenant_scope("other")
    try:
        engine.create_page(_page("pub1", "公共页面", metadata={"visibility": "public"}))
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("pub1") is not None
        assert [p.id for p in engine.list_pages()] == ["pub1"]
    finally:
        reset_tenant_scope(token)


def test_no_scope_sees_all(engine):
    for tenant, pid in (("dsh", "a"), ("other", "b")):
        token = set_tenant_scope(tenant)
        try:
            engine.create_page(_page(pid, f"页面 {pid}"))
        finally:
            reset_tenant_scope(token)
    assert sorted(p.id for p in engine.list_pages()) == ["a", "b"]


def test_same_id_does_not_overwrite_other_tenant(engine):
    """★ 索引以 id 为键 —— 同 id 直接赋值就是跨租户覆盖，必须另起后缀共存。"""
    token = set_tenant_scope("dsh")
    try:
        engine.create_page(_page("dup", "dsh 的页面"))
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("other")
    try:
        created = engine.create_page(_page("dup", "other 的页面"))
        assert created.id != "dup", "同 id 冲突时应另起后缀"
        assert engine.get_page("dup") is None, "不能覆盖 dsh 那份"
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("dup").title == "dsh 的页面", "dsh 那份必须原样保留"
    finally:
        reset_tenant_scope(token)


def test_update_and_delete_guard(engine):
    """★ public 只是可读，不等于可写：别人既改不了也删不了。"""
    token = set_tenant_scope("dsh")
    try:
        engine.create_page(_page("mine", "我的页面"))
        engine.create_page(_page("shared", "公开页面", metadata={"visibility": "public"}))
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("other")
    try:
        with pytest.raises(ValueError):
            engine.update_page(_page("mine", "被篡改"))
        with pytest.raises(ValueError):
            engine.update_page(_page("shared", "公开页被篡改"))
        assert engine.delete_page("mine") is False
        assert engine.delete_page("shared") is False
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("mine").title == "我的页面"
        assert engine.get_page("shared").title == "公开页面"
    finally:
        reset_tenant_scope(token)


def test_links_do_not_cross_tenants(engine):
    """加链是**双向写**：拿别人的页面做目标就是往别人页面里塞反链。"""
    token = set_tenant_scope("dsh")
    try:
        engine.create_page(_page("dsh-a", "A"))
        engine.create_page(_page("dsh-b", "B"))
        engine.create_page(_page("dsh-pub", "P", metadata={"visibility": "public"}))
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("other")
    try:
        engine.create_page(_page("oth-a", "OA"))
        assert engine.add_link("oth-a", "dsh-pub") is False, "不得往别人的页面写反链"
        assert engine.add_link("oth-a", "dsh-a") is False, "别人的私有页面也不可见"
        assert engine.get_page("oth-a").linked_pages == []
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("dsh-pub").linked_pages == [], "dsh 的页面不得被改动"
        assert engine.add_link("dsh-a", "dsh-b") is True, "本租户内加链要正常"
        assert "dsh-b" in engine.get_page("dsh-a").linked_pages
        assert [p.id for p in engine.get_backlinks("dsh-b")] == ["dsh-a"], "反向链接应指向链接者"
    finally:
        reset_tenant_scope(token)


def test_llm_context_is_scoped(engine):
    """★ 隐蔽泄漏面：送给 LLM 的"已有页面"上下文不得含别租户的标题/摘要。"""
    token = set_tenant_scope("other")
    try:
        engine.create_page(_page("x", "别家的机密主题", wing="tech"))
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh")
    try:
        engine.create_page(_page("y", "我家的主题", wing="tech"))
        llm = _StubLLM()
        asyncio.run(engine.auto_generate_page(llm, "新页面", "tech", []))
        titles = [p["title"] for p in llm.seen_context]
        assert "我家的主题" in titles
        assert "别家的机密主题" not in titles, "别租户的页面标题不得进入 LLM 上下文"
        assert all("机密" not in p["title"] for p in llm.seen_all)
    finally:
        reset_tenant_scope(token)


def test_legacy_page_without_tenant_is_invisible_and_safe(engine):
    """旧页面（无归属）安全默认：任何租户都看不到，只有全库视角能看到 —— 待一次性回填。"""
    engine.create_page(_page("legacy", "历史页面"))
    token = set_tenant_scope("dsh")
    try:
        assert engine.get_page("legacy") is None
    finally:
        reset_tenant_scope(token)
    assert engine.get_page("legacy") is not None, "全库视角（CLI/后台）应能看到无主页面"
