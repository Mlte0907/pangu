"""P1-3 阶段 3：知识图谱（KG）多租户回归测试。

设计要点（对应 pangu/memory/knowledge_graph.py 的实现）：
  * 物理表 `entities_all` / `relations_all`，主键 **(id, tenant_id)** —— 同名实体在不同
    租户下各有一份；`INSERT OR REPLACE` 天然只覆盖自己那份，踩不到别人
  * 对外暴露**同名视图** entities / relations，按 current_tenant() 过滤（我的 + public；
    作用域为空＝全库视角）。读写都走视图之外的地方一律显式打基表
  * 写路径（delete/update）必须显式限定 tenant_id —— SQLite 的 UPDATE/DELETE 不会套用
    视图的 WHERE，不限定就是"删掉所有租户的那条关系"

本测试锁定：作用域读、同名实体互不覆盖、public 跨租户可见、删改不越权、
抽取继承来源记忆的租户、以及**旧库迁移**（表 → 基表+视图，数据不丢）。
"""

import pathlib
import sqlite3
import tempfile

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.knowledge_graph import KnowledgeGraph
from pangu.memory.layers import reset_tenant_scope, set_tenant_scope


def _mk_kg(td: str) -> KnowledgeGraph:
    cfg = PanguConfig()
    cfg.base_dir = pathlib.Path(td)
    cfg.db_path = pathlib.Path(td)
    cfg.palace_path = td  # KG 落在 <palace_path>/knowledge_graph.db
    cfg.ensure_dirs()
    return KnowledgeGraph(cfg)


@pytest.fixture
def kg():
    with tempfile.TemporaryDirectory() as td:
        yield _mk_kg(td)


def test_schema_is_base_table_plus_view(kg):
    """schema 形态：*_all 是表、同名的是视图（读路径收口点）。"""
    with kg._conn() as conn:
        kinds = {
            r["name"]: r["type"]
            for r in conn.execute(
                "SELECT name, type FROM sqlite_master WHERE name IN ('entities','entities_all','relations','relations_all')"
            )
        }
    assert kinds == {
        "entities": "view",
        "entities_all": "table",
        "relations": "view",
        "relations_all": "table",
    }


def test_write_stamps_tenant(kg):
    """写入落当前租户归属。"""
    token = set_tenant_scope("dsh")
    try:
        kg.add_entity("entity-abc", "Python", "technology")
    finally:
        reset_tenant_scope(token)
    with kg._conn() as conn:
        row = conn.execute("SELECT tenant_id, visibility FROM entities_all WHERE id='entity-abc'").fetchone()
    assert row["tenant_id"] == "dsh"
    # 默认档是 tenant（同租户可见），不是 private —— KG 表没有属主列，标 private 无法执行
    assert row["visibility"] == "tenant"


def test_same_entity_id_coexists_across_tenants(kg):
    """★ 同名实体各租户各一份，互不覆盖（复合主键的核心价值）。"""
    token = set_tenant_scope("dsh")
    try:
        kg.add_entity("entity-python", "Python", "technology", "dsh 版")
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("other")
    try:
        kg.add_entity("entity-python", "Python", "technology", "other 版")
        # B 只看到自己那份
        assert kg.get_entity("entity-python")["description"] == "other 版"
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        # A 的那份没有被 B 覆盖
        assert kg.get_entity("entity-python")["description"] == "dsh 版"
    finally:
        reset_tenant_scope(token)
    with kg._conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM entities_all WHERE id='entity-python'").fetchone()[0]
    assert n == 2, "同一 id 下应有两行（各租户一份）"


def test_read_is_scoped(kg):
    """读路径按作用域裁剪：看不到别租户的实体。"""
    token = set_tenant_scope("other")
    try:
        kg.add_entity("entity-secret", "SecretThing", "system")
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        assert kg.get_entity("entity-secret") is None
        assert [e["id"] for e in kg.list_entities()] == []
        assert kg.stats()["entities"] == 0
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("other")
    try:
        assert kg.get_entity("entity-secret") is not None
    finally:
        reset_tenant_scope(token)


def test_public_visible_to_all_tenants(kg):
    """visibility='public' 是唯一的跨租户可见通道（有意共享）。"""
    token = set_tenant_scope("other")
    try:
        kg.add_entity("entity-shared", "Shared", "protocol")
        with kg._conn() as conn:
            conn.execute("UPDATE entities_all SET visibility='public' WHERE id='entity-shared'")
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        assert kg.get_entity("entity-shared") is not None
    finally:
        reset_tenant_scope(token)


def test_no_scope_sees_all(kg):
    """作用域为空（CLI/后台/admin）＝全库视角，行为与改造前一致。"""
    for tenant in ("dsh", "other"):
        token = set_tenant_scope(tenant)
        try:
            kg.add_entity(f"entity-{tenant}", tenant, "system")
        finally:
            reset_tenant_scope(token)
    assert sorted(e["id"] for e in kg.list_entities()) == ["entity-dsh", "entity-other"]


def test_delete_and_update_do_not_cross_tenants(kg):
    """★ 写路径不越权：别租户的实体删不掉、关系改不了。"""
    token = set_tenant_scope("other")
    try:
        kg.add_entity("entity-victim", "Victim", "system")
        kg.add_entity("entity-a", "A", "system")
        kg.add_relation("rel-1", "entity-a", "depends_on", "entity-victim")
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh")
    try:
        assert kg.delete_entity("entity-victim") is False, "跨租户删除必须失败"
        assert kg.delete_relation("rel-1") is False
        assert kg.invalidate_relation("rel-1") is False
    finally:
        reset_tenant_scope(token)

    with kg._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entities_all WHERE id='entity-victim'").fetchone()[0] == 1
        row = conn.execute("SELECT valid_until FROM relations_all WHERE id='rel-1'").fetchone()
    assert row is not None and row["valid_until"] is None, "别租户的关系不得被改动"


def test_relations_are_scoped(kg):
    """关系同样按作用域隔离。"""
    token = set_tenant_scope("other")
    try:
        kg.add_entity("e1", "E1", "system")
        kg.add_entity("e2", "E2", "system")
        kg.add_relation("rel-x", "e1", "depends_on", "e2")
        assert kg.get_relation("rel-x") is not None
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("dsh")
    try:
        assert kg.get_relation("rel-x") is None
        assert kg.query_relations() == []
    finally:
        reset_tenant_scope(token)


def test_extraction_inherits_source_tenant(kg):
    """★ 抽取继承来源记忆的租户 —— 后台任务里没有请求作用域，也必须落对归属。"""
    d = Drawer(id="mem_dsh_0001", content="盘古用 Python 与 ONNX 部署，走 MCP 协议", wing="w", room="r")
    d.metadata = {"tenant_id": "dsh"}
    assert kg.auto_extract_entities([d], max_drawers=1)["entities_added"] > 0

    token = set_tenant_scope("dsh")
    try:
        ids = [e["id"] for e in kg.list_entities()]
    finally:
        reset_tenant_scope(token)
    assert ids, "抽取出的实体应归属 dsh、对 dsh 可见"

    token = set_tenant_scope("other")
    try:
        assert kg.list_entities() == [], "别租户不该看到 dsh 抽取出的知识"
    finally:
        reset_tenant_scope(token)


def test_legacy_db_migration_keeps_rows():
    """★ 旧库（entities/relations 是**表**）迁移：数据不丢、变成基表+视图、归属留空（无主）。"""
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "knowledge_graph.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE entities (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                                   description TEXT DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE relations (id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL,
                                    object_id TEXT NOT NULL, valid_from TEXT, valid_until TEXT,
                                    confidence REAL DEFAULT 1.0, source TEXT DEFAULT '', created_at TEXT NOT NULL);
            INSERT INTO entities VALUES ('FAISS','FAISS','technology','旧数据','2026-01-01T00:00:00');
            INSERT INTO relations VALUES ('r1','FAISS','depends_on','FAISS',NULL,NULL,1.0,'','2026-01-01T00:00:00');
        """)
        conn.commit()
        conn.close()

        kg = _mk_kg(td)
        with kg._conn() as c:
            kinds = {
                r["name"]: r["type"]
                for r in c.execute(
                    "SELECT name, type FROM sqlite_master WHERE name IN ('entities','entities_all','relations','relations_all')"
                )
            }
            ent = c.execute("SELECT id, tenant_id, visibility FROM entities_all").fetchall()
            rel = c.execute("SELECT id, tenant_id FROM relations_all").fetchall()
        assert kinds == {"entities": "view", "entities_all": "table", "relations": "view", "relations_all": "table"}
        # 迁移路径补 visibility 时的默认档是 tenant（同租户可见）—— 老数据不该被收紧成 private
        assert [(r["id"], r["tenant_id"], r["visibility"]) for r in ent] == [("FAISS", "", "tenant")]
        assert [r["id"] for r in rel] == ["r1"]
        # 无主数据（''）对任何租户都不可见，只有全库视角能看到 —— 安全默认
        token = set_tenant_scope("dsh")
        try:
            assert kg.get_entity("FAISS") is None
        finally:
            reset_tenant_scope(token)
        assert kg.get_entity("FAISS") is not None


def test_write_stamps_owner_key(kg):
    """写入落 owner_key_id（private 档的判据来源）。"""
    token = set_tenant_scope("dsh", "key_owner")
    try:
        kg.add_entity("entity-owned", "Owned", "system")
    finally:
        reset_tenant_scope(token)
    with kg._conn() as conn:
        row = conn.execute("SELECT owner_key_id FROM entities_all WHERE id='entity-owned'").fetchone()
    assert row["owner_key_id"] == "key_owner"


def test_private_entity_visible_only_to_owner_key(kg):
    """★ private 档：同租户的**另一把钥匙也看不到**（视图里靠 current_key_id() 判定）。"""
    token = set_tenant_scope("dsh", "key_owner")
    try:
        kg.add_entity("entity-priv", "Priv", "system")
    finally:
        reset_tenant_scope(token)
    with kg._conn() as conn:
        conn.execute("UPDATE entities_all SET visibility='private' WHERE id='entity-priv'")

    token = set_tenant_scope("dsh", "key_owner")
    try:
        assert kg.get_entity("entity-priv") is not None, "属主钥匙应可见"
    finally:
        reset_tenant_scope(token)

    token = set_tenant_scope("dsh", "key_sibling")
    try:
        assert kg.get_entity("entity-priv") is None, "同租户的别的钥匙不得可见"
        assert [e["id"] for e in kg.list_entities()] == []
    finally:
        reset_tenant_scope(token)


def test_private_without_owner_falls_back_to_tenant(kg):
    """历史兼容：private 但没记属主 → 按 tenant 档（收紧会让老数据凭空消失）。"""
    token = set_tenant_scope("dsh", "key_any")
    try:
        kg.add_entity("entity-legacy", "Legacy", "system")
    finally:
        reset_tenant_scope(token)
    with kg._conn() as conn:
        conn.execute("UPDATE entities_all SET visibility='private', owner_key_id='' WHERE id='entity-legacy'")

    token = set_tenant_scope("dsh", "key_any")
    try:
        assert kg.get_entity("entity-legacy") is not None
    finally:
        reset_tenant_scope(token)
    token = set_tenant_scope("other", "key_any")
    try:
        assert kg.get_entity("entity-legacy") is None, "别租户仍看不到"
    finally:
        reset_tenant_scope(token)


def test_migration_adds_owner_column():
    """旧库（已迁移过的 *_all）也要幂等补上 owner_key_id 列。"""
    import pathlib
    import sqlite3
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "knowledge_graph.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE entities_all (id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
                description TEXT DEFAULT '', created_at TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL DEFAULT 'tenant',
                PRIMARY KEY (id, tenant_id));
            CREATE TABLE relations_all (id TEXT NOT NULL, subject_id TEXT NOT NULL, predicate TEXT NOT NULL,
                object_id TEXT NOT NULL, valid_from TEXT, valid_until TEXT, confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT '', created_at TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL DEFAULT 'tenant',
                PRIMARY KEY (id, tenant_id));
        """)
        conn.commit()
        conn.close()
        kg = _mk_kg(td)
        with kg._conn() as c:
            ent_cols = {r["name"] for r in c.execute("PRAGMA table_info(entities_all)")}
            rel_cols = {r["name"] for r in c.execute("PRAGMA table_info(relations_all)")}
            view_sql = c.execute("SELECT sql FROM sqlite_master WHERE name='entities'").fetchone()["sql"]
        assert "owner_key_id" in ent_cols and "owner_key_id" in rel_cols
        assert "current_key_id" in view_sql, "视图定义应已升级到三档（含 private 判据）"
