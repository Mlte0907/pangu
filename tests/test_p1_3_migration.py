"""导入/导出链路回归（2026-09-19）。

背景：export_all 写出 memories/wiki/knowledge_graph/palace/identity，但
import_from_file 此前只认 memories/wiki_pages/identity —— KG 被静默丢弃
（与当初"备份漏 KG"同族问题）。本组测试锁住：全字段往返 / merge 幂等 /
KG 往返 / palace 显式报告跳过。
"""

import json
import pathlib
import sqlite3

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.knowledge_graph import KnowledgeGraph
from pangu.memory.layers import MemoryStack
from pangu.memory.migration import MemoryExporter, MemoryImporter


@pytest.fixture()
def env(tmp_path):
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()
    ms = MemoryStack(cfg)
    ms.add_drawers(
        [
            Drawer(
                id="t1",
                content="往返测试内容",
                wing="w",
                room="r",
                hall="h",
                importance=4.0,
                tags=["x"],
                metadata={"tenant_id": "dsh", "decay_score": 0.7},
            )
        ]
    )
    return cfg, ms


def test_export_uses_full_fields(env, tmp_path):
    """导出必须用 to_dict 全字段（备份引擎当初栽在手挑 7 字段上）。"""
    cfg, _ = env
    out = MemoryExporter(cfg).export_all(str(tmp_path / "exp.json"))
    raw = json.loads(pathlib.Path(out).read_text())
    assert set(raw["memories"][0].keys()) == set(Drawer.__dataclass_fields__)
    assert raw["memories"][0]["metadata"]["tenant_id"] == "dsh"


def test_import_merge_is_idempotent(env, tmp_path):
    """同一文件 merge=True 导入两次，不得产生重复记忆。"""
    cfg, _ = env
    out = MemoryExporter(cfg).export_all(str(tmp_path / "exp.json"))
    imp = MemoryImporter(cfg)
    imp.import_from_file(out, merge=True)
    imp.import_from_file(out, merge=True)
    ids = [d.id for d in MemoryStack(cfg).get_drawers()]
    assert ids.count("t1") == 1, f"重复导入产生重复: {ids}"


def test_import_preserves_metadata(env, tmp_path):
    cfg, _ = env
    out = MemoryExporter(cfg).export_all(str(tmp_path / "exp.json"))
    MemoryImporter(cfg).import_from_file(out, merge=True)
    d = [x for x in MemoryStack(cfg).get_drawers() if x.id == "t1"][0]
    assert d.metadata.get("tenant_id") == "dsh"
    assert d.metadata.get("decay_score") == 0.7
    assert d.hall == "h"


def test_import_restores_knowledge_graph(env, tmp_path):
    """KG 导入往返：此前被静默丢弃。"""
    cfg, _ = env
    kg = KnowledgeGraph(cfg)
    kg.add_entity(id="Python", name="Python", entity_type="technology", description="语言")
    kg.add_entity(id="盘古", name="盘古", entity_type="system")
    kg.add_relation(id="r1", subject_id="盘古", predicate="depends_on", object_id="Python")

    out = MemoryExporter(cfg).export_all(str(tmp_path / "exp.json"))

    kgp = pathlib.Path(cfg.palace_path) / "knowledge_graph.db"
    c = sqlite3.connect(str(kgp))
    c.execute("DELETE FROM entities_all")
    c.execute("DELETE FROM relations_all")
    c.commit()
    c.close()

    stats = MemoryImporter(cfg).import_from_file(out, merge=True)
    c = sqlite3.connect(str(kgp))
    e = c.execute("SELECT COUNT(*) FROM entities_all").fetchone()[0]
    r = c.execute("SELECT COUNT(*) FROM relations_all").fetchone()[0]
    c.close()
    assert (e, r) == (2, 1)
    assert stats["entities_imported"] == 2
    assert "knowledge_graph_error" not in stats


def test_import_reports_palace_skip(env, tmp_path):
    """palace 无导入实现，但必须显式报告跳过，不许静默。"""
    cfg, _ = env
    out = MemoryExporter(cfg).export_all(str(tmp_path / "exp.json"))
    stats = MemoryImporter(cfg).import_from_file(out, merge=True)
    assert "palace_skipped" in stats
