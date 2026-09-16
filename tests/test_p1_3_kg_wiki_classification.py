"""KG / wiki 的**密级轴** —— 第二条正交判据，与记忆层 metadata_readable 同规则。

背景：记忆（layers）在上一轮已落地密级轴，但 KG 与 wiki 只有租户轴。那会留下一条旁路：
「从机密记忆里抽出实体、落进公开图谱」—— 租户挡住了，密级却漏了。本轮补齐，三个域
的判据必须一致（租户轴 AND 密级轴；全库视角短路放行）。

判定规则（与 layers.metadata_readable 逐字同构）：
  - 全库视角（current_tenant() == ''）＝系统自身 → 不过滤
  - 否则：租户轴 AND (classification <= 调用方 clearance)
"""

import sqlite3

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer, WikiPage
from pangu.memory.knowledge_graph import KnowledgeGraph
from pangu.memory.layers import reset_tenant_scope, set_tenant_scope
from pangu.wiki.engine import WikiEngine


@pytest.fixture
def cfg(tmp_path):
    """完全隔离的临时库（不许碰到生产库 —— 见 conftest 的硬守卫）。"""
    c = PanguConfig()
    c.base_dir = tmp_path
    c.db_path = tmp_path
    c.palace_path = str(tmp_path / "v2m")
    c.wiki_path = str(tmp_path / "wiki")
    (tmp_path / "v2m").mkdir(parents=True, exist_ok=True)
    c.ensure_dirs()
    return c


def _kg_view_names(kg, tenant, clearance):
    """走**视图**读（KG 的判据写在视图里），等价于各读方法看到的集合。"""
    tok = set_tenant_scope(tenant, "key_x", clearance)
    try:
        conn = sqlite3.connect(kg.db_path)
        conn.create_function("current_tenant", 0, lambda: tenant)
        conn.create_function("current_key_id", 0, lambda: "key_x")
        conn.create_function("current_clearance", 0, lambda: clearance)
        return {r[0] for r in conn.execute("SELECT name FROM entities")}
    finally:
        reset_tenant_scope(tok)


def test_kg_classification_blocks_low_clearance(cfg):
    """密级轴生效：clearance 不够就读不到（与租户轴合取）。"""
    kg = KnowledgeGraph(cfg)
    tok = set_tenant_scope("dsh", "k3", 3)  # 自身 clearance=3 才能落高密级
    try:
        kg.add_entity("e0", "公开实体", "system", "d", classification=0)
        kg.add_entity("e2", "机密实体", "system", "d", classification=2)
        kg.add_entity("e3", "绝密实体", "system", "d", classification=3)
    finally:
        reset_tenant_scope(tok)

    assert _kg_view_names(kg, "dsh", 3) == {"公开实体", "机密实体", "绝密实体"}
    assert _kg_view_names(kg, "dsh", 2) == {"公开实体", "机密实体"}
    assert _kg_view_names(kg, "dsh", 0) == {"公开实体"}


def test_kg_write_clamped_to_caller_clearance(cfg):
    """低密级调用方不能把数据标成绝密 —— 与记忆写入同一策略。"""
    kg = KnowledgeGraph(cfg)
    tok = set_tenant_scope("dsh", "k0", 0)
    try:
        kg.add_entity("e9", "越权标密", "system", "d", classification=3)
    finally:
        reset_tenant_scope(tok)
    conn = sqlite3.connect(kg.db_path)
    got = conn.execute("SELECT classification FROM entities_all WHERE id='e9'").fetchone()[0]
    assert got == 0


def test_kg_extract_inherits_source_classification(cfg):
    """抽取**继承**来源记忆的密级（不钳制）—— 否则机密记忆会漏进公开图谱。"""
    kg = KnowledgeGraph(cfg)
    d = Drawer(id="m1", content="盘古 使用 MCP 协议部署", wing="w", room="r")
    d.metadata = {"tenant_id": "dsh", "classification": 3}
    kg.auto_extract_entities([d], max_drawers=1)

    conn = sqlite3.connect(kg.db_path)
    rows = dict(conn.execute("SELECT name, classification FROM entities_all").fetchall())
    assert rows, "抽取应至少产出一条实体"
    assert set(rows.values()) == {3}, f"继承失败（被钳制成公开了）：{rows}"


def test_kg_full_view_ignores_classification(cfg):
    """全库视角不受密级影响 —— 否则后台维护会看不见自己的高密级数据。"""
    kg = KnowledgeGraph(cfg)
    tok = set_tenant_scope("dsh", "k3", 3)
    try:
        kg.add_entity("e3", "绝密实体", "system", "d", classification=3)
    finally:
        reset_tenant_scope(tok)
    conn = sqlite3.connect(kg.db_path)
    conn.create_function("current_tenant", 0, lambda: "")
    conn.create_function("current_key_id", 0, lambda: "")
    conn.create_function("current_clearance", 0, lambda: 0)
    assert {r[0] for r in conn.execute("SELECT name FROM entities")} == {"绝密实体"}


def _mk_page(we, pid, title, cls, tenant, key, clearance):
    tok = set_tenant_scope(tenant, key, clearance)
    try:
        p = WikiPage(id=pid, title=title, content="内容", summary="s", wing="w", tags=[])
        p.metadata = {"tenant_id": tenant, "classification": cls}
        return we.create_page(p)
    finally:
        reset_tenant_scope(tok)


def _wiki_titles(we, tenant, clearance):
    tok = set_tenant_scope(tenant, "key_x", clearance)
    try:
        return {p.title for p in we.visible_pages()}
    finally:
        reset_tenant_scope(tok)


def test_wiki_classification_blocks_low_clearance(cfg):
    """wiki 复用记忆层的 metadata_readable —— 租户轴与密级轴同时生效。"""
    we = WikiEngine(cfg)
    _mk_page(we, "p0", "公开页", 0, "dsh", "k3", 3)
    _mk_page(we, "p3", "绝密页", 3, "dsh", "k3", 3)

    assert _wiki_titles(we, "dsh", 3) == {"公开页", "绝密页"}
    assert _wiki_titles(we, "dsh", 0) == {"公开页"}


def test_wiki_write_clamped_to_caller_clearance(cfg):
    we = WikiEngine(cfg)
    got = _mk_page(we, "p9", "越权标密", 3, "dsh", "k0", 0)
    assert got.metadata.get("classification") == 0
