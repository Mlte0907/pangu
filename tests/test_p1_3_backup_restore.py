"""备份/恢复真落盘回归（2026-09-19）。

背景：备份/恢复此前是半成品 ——
  - restore() 只把 JSON 读出来塞进返回值（handler 侧再 pop 掉），磁盘毫无变化，
    调用方却拿到 success=True / restored_count=N（假成功）
  - _serialize_drawers 只存 7 字段，丢 room/hall/metadata（租户/密级/衰减分）
  - restore_by_filter 只统计不落盘
  - backup_incremental 三个分支都走全量（已改为诚实标注）

验证一律**直接读磁盘文件**（绕过 MemoryStack/JsonDrawerStorage 两层各 30s 缓存），
否则会被缓存骗成"没恢复"。
"""

import json
import pathlib

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.backup_restore import BackupRestoreEngine
from pangu.memory.layers import MemoryStack


def _setup(tmp_path):
    cfg = PanguConfig()
    cfg.base_dir = tmp_path
    cfg.db_path = tmp_path
    cfg.palace_path = str(tmp_path / "palace")
    cfg.ensure_dirs()
    ms = MemoryStack(cfg)
    be = BackupRestoreEngine(cfg, backup_dir=str(tmp_path / "bk"))
    return cfg, ms, be


def _disk_ids(ms) -> list[str]:
    """直接读磁盘（绕开两层缓存）—— 验证落盘的唯一可信口径。"""
    raw = json.loads(ms._drawers_file.read_text())
    return sorted(d["id"] for d in raw)


def _full_drawer(did="f1") -> Drawer:
    return Drawer(
        id=did,
        content="全字段",
        wing="w2",
        room="r2",
        hall="h2",
        importance=4.5,
        emotional_weight=1.5,
        source_file="src.md",
        tags=["t1"],
        author="agent",
        metadata={"tenant_id": "dsh", "classification": 1, "decay_score": 0.8},
    )


def test_backup_stores_all_fields(tmp_path):
    """备份必须存 Drawer 的全部字段（旧实现丢 room/hall/metadata）。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([_full_drawer()])
    info = be.backup(ms.get_drawers(), "全字段")
    raw = json.loads((pathlib.Path(tmp_path) / "bk" / f"{info.backup_id}.json").read_text())
    assert raw["version"] == 2
    item = raw["drawers"][0]
    assert set(item.keys()) == set(Drawer.__dataclass_fields__)
    assert item["metadata"]["tenant_id"] == "dsh"


def test_restore_really_writes_to_disk(tmp_path):
    """★ 核心：restore 后磁盘真的变回来（旧实现是假成功）。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r"), Drawer(id="b", content="B", wing="w", room="r")])
    info = be.backup(ms.get_drawers(), "t")

    ms.remove_drawer("a")
    d = ms.get_drawer_by_id("b")
    d.content = "改坏"
    ms.update_drawer(d)
    assert _disk_ids(ms) == ["b"]

    r = be.restore(info.backup_id, memory=ms)
    assert r["success"] is True and r["restored_count"] == 2
    assert _disk_ids(ms) == ["a", "b"]  # 磁盘口径
    assert ms.get_drawer_by_id("b").content == "B"


def test_restore_dry_run_does_not_write(tmp_path):
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    info = be.backup(ms.get_drawers(), "t")
    ms.remove_drawer("a")

    r = be.restore(info.backup_id, memory=ms, dry_run=True)
    assert r["success"] is True and r["dry_run"] is True and r["would_restore"] == 1
    assert _disk_ids(ms) == []


def test_restore_rejects_empty_backup(tmp_path):
    """空备份恢复 == 清库，必须拒绝。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    empty = be.backup([], "空")
    r = be.restore(empty.backup_id, memory=ms)
    assert r["success"] is False and "空" in r["error"]
    assert _disk_ids(ms) == ["a"]  # 未被清库


def test_restore_rejects_tampered_backup(tmp_path):
    """被改动的备份 checksum 不匹配，不许覆盖现库。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    info = be.backup(ms.get_drawers(), "t")
    f = pathlib.Path(tmp_path) / "bk" / f"{info.backup_id}.json"
    data = json.loads(f.read_text())
    data["drawers"][0]["content"] = "篡改"
    f.write_text(json.dumps(data))

    r = be.restore(info.backup_id, memory=ms)
    assert r["success"] is False and "校验" in r["error"]


def test_restore_makes_safety_backup(tmp_path):
    """恢复前必须留下当前状态的快照（可回滚）。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    info = be.backup(ms.get_drawers(), "t")
    ms.add_drawers([Drawer(id="extra", content="临时的", wing="w", room="r")])

    r = be.restore(info.backup_id, memory=ms)
    assert r["success"] is True
    safety_ids = [b["id"] for b in be.list_backups()]
    assert r["safety_backup"] in safety_ids  # 前置快照已在索引里
    assert "extra" not in _disk_ids(ms)  # 回滚到了备份时刻


def test_restore_by_filter_appends_without_deleting(tmp_path):
    """选择性恢复是"追加"语义：补回丢失的，不动现有的。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers(
        [
            Drawer(id="a", content="A", wing="keep", room="r"),
            Drawer(id="b", content="B", wing="lost", room="r"),
        ]
    )
    info = be.backup(ms.get_drawers(), "t")
    ms.remove_drawer("b")
    ms.add_drawers([Drawer(id="c", content="C", wing="keep", room="r")])

    r = be.restore_by_filter(info.backup_id, wing="lost", memory=ms)
    assert r["success"] is True and r["restored_count"] == 1
    assert _disk_ids(ms) == ["a", "b", "c"]  # b 回来，a/c 未动

    # 再跑一次：已存在 → 跳过，不重复
    r2 = be.restore_by_filter(info.backup_id, wing="lost", memory=ms)
    assert r2["restored_count"] == 0 and r2["skipped_existing"] == 1


def test_replace_all_refuses_empty(tmp_path):
    """replace_all 空列表必须抛错（防误清库）。"""
    _, ms, _ = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    with pytest.raises(ValueError, match="空列表"):
        ms.replace_all([])
    assert _disk_ids(ms) == ["a"]


def test_v1_backup_compat(tmp_path):
    """v1 旧备份（只有 7 字段）仍可恢复，缺字段用默认值。"""
    _, ms, be = _setup(tmp_path)
    bk = pathlib.Path(tmp_path) / "bk"
    bk.mkdir(parents=True, exist_ok=True)
    v1 = [
        {
            "id": "old",
            "content": "旧格式",
            "wing": "w",
            "importance": 3,
            "tags": [],
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]
    # 文件内容与 checksum 必须按同一份字节算（engine 侧是 json.dumps(..., ensure_ascii=False)）
    content = json.dumps(v1, ensure_ascii=False)
    (bk / "backup_v1_test.json").write_text(content)
    # 手动补索引（v1 文件没有 checksum 记录）
    import hashlib

    from pangu.memory.backup_restore import BackupInfo

    checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
    be._backup_index.append(
        BackupInfo(
            backup_id="backup_v1_test", timestamp="t", memory_count=1, size_bytes=1, checksum=checksum, description="v1"
        )
    )

    r = be.restore("backup_v1_test", memory=ms)
    assert r["success"] is True
    assert _disk_ids(ms) == ["old"]
    assert ms.get_drawer_by_id("old").room == "general"  # 默认值兜底


def test_backup_includes_assets_and_restores(tmp_path):
    """★ 新能力：KG/wiki/遗忘归档 一并备份与恢复（此前完全在备份范围之外）。

    KG 走 SQLite 在线备份 API —— 直接拷 .db 会丢掉 WAL 里未 checkpoint 的数据。
    """
    import sqlite3

    cfg, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    base = pathlib.Path(cfg.palace_path)
    base.mkdir(parents=True, exist_ok=True)

    # 造资产：KG（SQLite）+ wiki + 遗忘归档
    kg = base / "knowledge_graph.db"
    c = sqlite3.connect(str(kg))
    c.execute("CREATE TABLE entities_all (id TEXT PRIMARY KEY, name TEXT)")
    c.execute("INSERT INTO entities_all VALUES ('Python', 'Python语言')")
    c.commit()
    c.close()

    wiki = base / "wiki.json" / "wiki_index.json"
    wiki.parent.mkdir(parents=True, exist_ok=True)
    wiki.write_text('{"pages": ["p1"]}')
    arch = base.parent / "forgetting_archive.json"
    arch.write_text('[{"id": "old"}]')

    info = be.backup(ms.get_drawers(), "含资产")
    v = be.verify_backup(info.backup_id)
    assert v["format"] == "v2"
    assert {"knowledge_graph", "wiki_index", "forgetting_archive"} <= set(v["assets"])

    # 破坏三类资产
    c = sqlite3.connect(str(kg))
    c.execute("DELETE FROM entities_all")
    c.commit()
    c.close()
    wiki.write_text("{}")
    arch.unlink()

    # 恢复
    r = be.restore(info.backup_id, memory=ms)
    assert r["success"] is True
    assert r["assets_restored"]["knowledge_graph"] == "ok"

    c = sqlite3.connect(str(kg))
    n = c.execute("SELECT COUNT(*) FROM entities_all").fetchone()[0]
    c.close()
    assert n == 1, "KG 数据未恢复"
    assert "p1" in wiki.read_text()
    assert arch.exists()


def test_index_survives_corruption(tmp_path):
    """索引损坏时不清空、不覆盖（旧实现静默清零）。"""
    _, ms, be = _setup(tmp_path)
    ms.add_drawers([Drawer(id="a", content="A", wing="w", room="r")])
    be.backup(ms.get_drawers(), "t")
    idx = pathlib.Path(tmp_path) / "bk" / "index.json"
    idx.write_text("{ 坏掉的 json")

    be2 = BackupRestoreEngine(be.config, backup_dir=str(pathlib.Path(tmp_path) / "bk"))
    assert be2._backup_index == []  # 读不出 → 空，但不覆盖
    assert idx.read_text() == "{ 坏掉的 json"  # 文件原样保留
