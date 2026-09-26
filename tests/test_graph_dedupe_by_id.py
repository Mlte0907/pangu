"""图谱接口按 id 合并的回归测试（2026-09-26）。

锁定的缺陷（云端实证）：`entities_all` 主键是 (id, tenant_id)，同一概念按属主各存一行；
`/api/v2/graph` 走 REST 全库视角（`_TENANT_SCOPE` 默认空串 → 视图首句短路到全库），
于是一个实体被返回多份。云端实测 19 个实体返回成 33 行（default 19 + deepseek-harness 14），
每组 name/type/description 逐字节相同；边还被二次放大成 4 次（2 实体行 × 2 关系行）。

本测试只锁**读取侧**的行为。存储层的「同名实体互不覆盖」是多租户的有意设计，
由 tests/test_p1_3_kg_tenant_scope.py 负责 —— 本文件不改它，也不该改它。
"""

import pathlib
import tempfile

import pytest
from fastapi.testclient import TestClient

from pangu.core.config import PanguConfig
from pangu.memory.knowledge_graph import KnowledgeGraph


@pytest.fixture
def env(monkeypatch):
    """隔离环境：真 KG（写入同 id 不同属主的行）+ 指向它的 app。

    graph_data 走的是 `PanguConfig.load().authoritative_memory_config()`，所以必须把
    `load` 与 `authoritative_memory_config` 一起打桩，否则路由会去读真实的库（本机=空库，
    测试就会因为「拿到 0 个节点」而假绿）。
    """
    with tempfile.TemporaryDirectory() as td:
        cfg = PanguConfig()
        cfg.base_dir = pathlib.Path(td)
        cfg.db_path = pathlib.Path(td)
        cfg.palace_path = td
        cfg.api_key = ""  # 鉴权中间件随之关闭，测试只关心聚合逻辑
        cfg.ensure_dirs()

        monkeypatch.setattr(PanguConfig, "load", classmethod(lambda cls: cfg))
        monkeypatch.setattr(PanguConfig, "authoritative_memory_config", lambda self: self)

        kg = KnowledgeGraph(cfg)
        # 同一个概念写两遍、属主不同 —— 实体 id 由名字决定，故两行 id 必然相同
        for tenant in ("default", "deepseek-harness"):
            kg.add_entity("entity-http", "HTTP", "protocol", "从记忆 9ac0c5bc 提取", tenant_id=tenant)
        # 单一属主的实体，不该被误合并掉
        kg.add_entity("entity-sqlite", "SQLite", "protocol", "从记忆 9ac0c5bc 提取", tenant_id="deepseek-harness")

        yield cfg, kg


def test_fixture_really_creates_duplicate_rows(env):
    """自校验：基表里必须真的是 3 行（entity-http 两行 + entity-sqlite 一行）。

    没有这条，下面的去重断言可能在 fixture 只写进一行时**空转通过** —— 那样测的就不是
    聚合逻辑而是「本来就没有重复」。
    """
    _cfg, kg = env
    with kg._conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entities_all").fetchone()[0]
        per_id = conn.execute("SELECT COUNT(*) FROM entities_all WHERE id='entity-http'").fetchone()[0]
    assert total == 3, f"基表应有 3 行，实得 {total}"
    assert per_id == 2, f"entity-http 应有 2 行（复合主键下的同名实体），实得 {per_id}"


def _graph(env, query="limit=100"):
    cfg, _kg = env
    from pangu.api import server as server_mod

    client = TestClient(server_mod.create_app(), raise_server_exceptions=False)
    r = client.get(f"/api/v2/graph?{query}")
    assert r.status_code == 200, r.text[:200]
    return r.json()["data"]


def test_same_entity_under_two_owners_is_returned_once(env):
    ids = [n["id"] for n in _graph(env)["nodes"]]
    assert ids.count("entity-http") == 1, f"同一实体返回了 {ids.count('entity-http')} 次：{ids}"
    assert len(ids) == len(set(ids)), f"节点里有重复 id：{ids}"


def test_total_entities_counts_distinct_ids(env):
    """total_entities 此前是 len(entities)，即含重复行的行数，仪表盘会显示虚高。"""
    data = _graph(env)
    assert data["total_entities"] == len(data["nodes"]) == 2, data["total_entities"]


def test_limit_is_not_eaten_by_duplicate_rows(env):
    """合并必须发生在截断之前：否则重复行会吃掉 limit 名额。"""
    assert len(_graph(env, "limit=2")["nodes"]) == 2


def test_edges_are_not_amplified(env):
    """边的 4 倍放大来自「按重复后的实体行逐行查关系」。"""
    _cfg, kg = env
    for tenant in ("default", "deepseek-harness"):
        kg.add_relation("rel-1", "entity-http", "depends_on", "entity-sqlite", tenant_id=tenant)
    keys = [(e["source"], e["target"], e["predicate"]) for e in _graph(env)["edges"]]
    assert len(keys) == len(set(keys)), f"边重复了：{keys}"
    assert len(keys) == 1, f"应只剩一条关系，实得 {keys}"


def test_memory_count_counts_plaintext_not_ciphertext(env, monkeypatch):
    """memory_count 必须数**明文**。

    记忆在盘古里是 Fernet 密文落库（content 以 `gAAAAA` 开头）。首版实现直接在
    `drawer.content` 上做子串匹配，等于在密文里数 —— 数字看着合理实则随机（云端实测
    'mcp' 在密文中偶然出现 16 次，于是 MCP 报了 16 而其余全 0）。本测试用一条明文记忆
    锁住正确行为：明文里出现 HTTP 就必须 ≥1。
    """
    cfg, _kg = env
    from pangu.core.palace import Drawer

    d = Drawer(id="mem-plain-1", content="我们把服务挂在 uvicorn 上面，前面用 nginx 收口。", wing="tech", room="general")
    monkeypatch.setattr(
        "pangu.memory.layers.MemoryStack.get_drawers", lambda self, *a, **k: [d], raising=False
    )
    node = next(n for n in _graph(env)["nodes"] if n["name"] == "HTTP")
    # 这条明文里没有 HTTP，计数应为 0；关键是它不能因为「密文/明文搞混」而虚高
    assert node["memory_count"] == 0, node

    d2 = Drawer(id="mem-plain-2", content="排查 HTTP 超时，最终定位到连接池耗尽。", wing="tech", room="general")
    monkeypatch.setattr(
        "pangu.memory.layers.MemoryStack.get_drawers", lambda self, *a, **k: [d2], raising=False
    )
    node = next(n for n in _graph(env)["nodes"] if n["name"] == "HTTP")
    assert node["memory_count"] == 1, node


def test_memory_count_is_a_real_int_not_missing_field(env):
    """entities_all 无 memory_count 列，此前该字段恒 0；现在必须由 _kg_source_counts 现算。"""
    for n in _graph(env)["nodes"]:
        assert isinstance(n["memory_count"], int), n


def test_entity_name_with_padding_still_matches(env, monkeypatch):
    """实体名可能带首尾空格（云端实测 ' sentence-transformers'），匹配前要 strip。"""
    from pangu.core.palace import Drawer
    from pangu.memory.layers import MemoryStack

    _cfg, kg = env
    kg.add_entity(
        "entity-st", " sentence-transformers ", "technology", "从记忆 8dabb4bd 提取", tenant_id="default"
    )
    d = Drawer(id="m1", content="部署 sentence-transformers 做向量化。", wing="tech", room="general")
    monkeypatch.setattr(MemoryStack, "get_drawers", lambda self, *a, **k: [d], raising=False)
    node = next(n for n in _graph(env)["nodes"] if "sentence" in n["name"])
    assert node["memory_count"] == 1, node


def test_entity_type_filter_still_applies(env):
    _cfg, kg = env
    kg.add_entity("entity-fastapi", "FastAPI", "framework", "从记忆 mem_tech 提取", tenant_id="default")
    names = [n["name"] for n in _graph(env, "limit=100&entity_type=framework")["nodes"]]
    assert names == ["FastAPI"], names
