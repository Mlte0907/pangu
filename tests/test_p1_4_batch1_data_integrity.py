"""第 1 批修复的回归测试（2026-09-20）。

每个用例对应一个已复现的真实 bug，且**只断言修复后的正确行为**，
不重复测试框架本身的隔离（那由 conftest 的 `_isolate_pangu_data_dir` 负责）。

覆盖：
1. VectorIndex._normalize 按轴归一化（此前整批被一个 Frobenius 标量缩小）
2. VectorIndex._flush_pending 不产生 3-D（此前 add() 后 shape=(N,1,dim)）
3. VectorIndex.remove 真正 compact 行（此前只删 id，查询返回错误记忆）
4. VectorIndex._load 拒绝行列不一致的索引
5. MemoryConsolidator.compress_memory 返回真实摘要（此前恒 content[:100]）
6. importance_feedback / record_recall_hits 不回滚并发写入
7. FTS 索引路径跟随 base_dir（此前硬编码 ~/.pangu）
8. FTS 磁盘索引恢复 content_map（此前兜底搜索恒空）
9. SearchCache 键含作用域（此前跨身份复用）
"""

import json

import numpy as np
import pytest

from pangu.core.palace import Drawer

# ── 1/2/3/4：向量索引 ──


def test_normalize_is_per_vector():
    """批量归一化必须按最后一维；错误的整批缩放会让向量通道跌破相似度阈值。"""
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4)
    batch = np.array([[3.0, 4.0, 0.0, 0.0], [0.0, 0.0, 3.0, 4.0]], dtype=np.float32)
    out = vi._normalize(batch)
    norms = [float(np.linalg.norm(row)) for row in out]
    assert all(abs(n - 1.0) < 1e-5 for n in norms), f"每行应为单位范数，实得 {norms}"


def test_normalize_single_vector_unchanged():
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=3)
    out = vi._normalize(np.array([0.0, 3.0, 4.0], dtype=np.float32))
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


def test_normalize_handles_zero_vector():
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=2)
    out = vi._normalize(np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32))
    assert np.allclose(out[0], 0.0)
    assert abs(float(np.linalg.norm(out[1])) - 1.0) < 1e-5


def test_flush_pending_keeps_2d_shape():
    """add() 写入后索引必须是 (N, dim)，不能是 (N, 1, dim)。"""
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4)
    vi.add([1.0, 0.0, 0.0, 0.0], "a")
    vi.add([0.0, 1.0, 0.0, 0.0], "b")
    vi._flush_pending()
    assert vi._index is not None
    assert vi._index.ndim == 2, f"期望 2-D，实得 {vi._index.shape}"
    assert vi._index.shape == (2, 4)
    assert vi._ids == ["a", "b"]


def test_flush_pending_survives_reload():
    """落盘再加载，形状与 id 必须一致（此前的 3-D 会被 _load 拒绝 → 索引消失）。"""
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4, persist=True)
    vi.add([1.0, 0.0, 0.0, 0.0], "a")
    vi.add([0.0, 1.0, 0.0, 0.0], "b")
    vi._flush_pending()
    vi2 = VectorIndex(dim=4, persist=True)
    assert vi2.is_built
    assert vi2._ids == ["a", "b"]


def test_remove_compacts_rows_so_ids_stay_aligned():
    """删除 b 后查询 b 的向量不能再返回 c（此前只过滤 _ids 导致位置错位）。"""
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4, persist=True)
    vi.add_batch(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        ["a", "b", "c"],
    )
    assert vi.remove(["b"]) == 1
    assert vi._ids == ["a", "c"]
    assert vi._index.shape[0] == len(vi._ids), "向量行数必须与 id 数一致"

    # 关键回归：删除前「只过滤 _ids」会让查询 b 的向量返回 c（位置错位）。
    # 修复后 b 的向量已被真正移除，查询 b 只能得到相似度 0 的 a/c 或被过滤。
    hits = vi.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    for hid, score in hits:
        assert hid != "b", "已删除的 id 不应再出现"
        assert score < 0.999, f"不应把别的向量误报为完全匹配（{hid}={score}）"


def test_remove_missing_id_is_noop():
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4)
    vi.add_batch([[1.0, 0.0, 0.0, 0.0]], ["a"])
    assert vi.remove(["zzz"]) == 0
    assert vi._ids == ["a"]


def test_load_rejects_row_id_mismatch(tmp_path):
    """行列不一致的索引必须被拒绝加载（否则按位置取 id 会返回错误记忆）。"""
    from pangu.memory import vector_index as vimod
    from pangu.memory.vector_index import VectorIndex

    vi = VectorIndex(dim=4, persist=True)
    vi.add_batch([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], ["a", "b"])
    # 人为制造损坏：向量 2 行、ids 1 个
    np.savez(vi._index_file, vectors=vi._index, ids=np.array(["a"]))

    vi2 = VectorIndex(dim=4, persist=True)
    assert not vi2.is_built, "行列不一致的索引不应被视为可用"
    assert vi2._ids == []


# ── 5：压缩 ──


def test_compress_memory_keeps_key_sentences():
    """含关键词的长记忆必须保留关键词句，而不是退化成 content[:100]。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.consolidation import MemoryConsolidator

    c = MemoryConsolidator(PanguConfig.load())
    filler = "无关内容。" * 60
    key = "关键结论：必须验证路径隔离，这是重要决定。"
    d = Drawer(id="x", content=filler + key, tags=["重要"])
    out = c.compress_memory(d)
    assert key[:20] in out, f"关键词句应被保留，实得: {out[:80]}"
    assert out != d.content[:100] + "..."
    assert len(out) < len(d.content)


def test_compress_memory_short_unchanged():
    from pangu.core.config import PanguConfig
    from pangu.memory.consolidation import MemoryConsolidator

    c = MemoryConsolidator(PanguConfig.load())
    short = "短内容。"
    assert c.compress_memory(Drawer(id="s", content=short)) == short


# ── 6：召回反馈不丢并发更新 ──


def _seed(drawers_file, items):
    drawers_file.parent.mkdir(parents=True, exist_ok=True)
    drawers_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def _load(drawers_file):
    return {d["id"]: d for d in json.loads(drawers_file.read_text(encoding="utf-8"))}


def test_record_recall_hits_does_not_revert_concurrent_write():
    """命中 A 时，不得把 B 的并发改动（importance 5.0）用旧快照回滚。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.retrieval import record_recall_hits

    cfg = PanguConfig.load().authoritative_memory_config()
    f = cfg.authoritative_drawers_path

    a = Drawer(id="A", content="aaa", importance=1.0)
    b = Drawer(id="B", content="bbb", importance=1.0)
    _seed(f, [a.to_dict(), b.to_dict()])

    # 调用方持有搜索前的旧快照（B=1.0），此时并发写者已把 B 改成 5.0
    stale = [Drawer.from_dict(x) for x in json.loads(f.read_text(encoding="utf-8"))]
    disk = json.loads(f.read_text(encoding="utf-8"))
    for item in disk:
        if item["id"] == "B":
            item["importance"] = 5.0
    _seed(f, disk)

    res = record_recall_hits(["A"], drawers=stale)
    assert res.get("recorded") == 1

    after = _load(f)
    assert after["B"]["importance"] == 5.0, "并发写入的 B 不能被旧快照回滚"
    assert after["A"]["importance"] > 1.0, "命中的 A 应被增强"


def test_record_recall_hits_keeps_untouched_records():
    """未命中的记录必须原样保留（含其 metadata）。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.retrieval import record_recall_hits

    cfg = PanguConfig.load().authoritative_memory_config()
    f = cfg.authoritative_drawers_path
    a = Drawer(id="A", content="aaa", importance=1.0)
    b = Drawer(id="B", content="bbb", importance=2.0)
    b.metadata["custom_tag"] = "keep-me"
    _seed(f, [a.to_dict(), b.to_dict()])

    record_recall_hits(["A"], drawers=None)

    after = _load(f)
    assert after["B"]["importance"] == 2.0
    assert after["B"]["metadata"]["custom_tag"] == "keep-me"


def test_record_recall_hits_refuses_empty_store():
    from pangu.core.config import PanguConfig
    from pangu.memory.retrieval import record_recall_hits

    cfg = PanguConfig.load().authoritative_memory_config()
    f = cfg.authoritative_drawers_path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("[]", encoding="utf-8")

    res = record_recall_hits(["A"], drawers=None)
    assert "error" in res
    assert json.loads(f.read_text(encoding="utf-8")) == []


# ── 7/8：FTS ──


def test_fts_index_path_follows_base_dir():
    """索引路径必须在隔离目录下，不能是 ~/.pangu（否则测试/多实例互相污染）。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.fts_search import FTS5SearchEngine

    cfg = PanguConfig.load().authoritative_memory_config()
    engine = FTS5SearchEngine(cfg)
    path = engine._get_index_path()
    base = str(cfg.base_dir)
    assert str(path).startswith(base), f"索引路径 {path} 应在 base_dir {base} 之下"
    assert path.name == "fts_index.json"


def test_fts_round_trip_restores_content_map():
    """落盘再加载必须恢复 content_map，否则兜底关键词搜索恒返回空。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.fts_search import FTS5SearchEngine

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers = [
        Drawer(id="m1", content="盘古向量检索测试内容"),
        Drawer(id="m2", content="另一条不同主题的记忆"),
    ]
    e1 = FTS5SearchEngine(cfg)
    e1.build_index(drawers)
    assert e1._fts_content_map

    e2 = FTS5SearchEngine(cfg)
    e2._indexed_count = len(drawers)
    assert e2._load_index_from_disk(), "索引应能成功加载"
    assert len(e2._fts_content_map) == len(drawers), "content_map 必须一并恢复"

    scores: dict = {}
    e2._fallback_keyword_search("向量", scores)
    assert "m1" in scores, "兜底搜索应能在加载后的索引中找到内容"


def test_fts_rebuilds_when_disk_index_larger_than_store():
    """磁盘索引明显大于真实库（历史污染）时必须放行重建，而不是被收缩保护拦下。"""
    from pangu.core.config import PanguConfig
    from pangu.memory.fts_search import FTS5SearchEngine

    cfg = PanguConfig.load().authoritative_memory_config()
    engine = FTS5SearchEngine(cfg)
    path = engine._get_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"tokens": {"x": ["m1"]}, "doc_count": 5000, "built_at": "old"}),
        encoding="utf-8",
    )

    engine.build_index([Drawer(id="m1", content="小库")])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["doc_count"] == 1, "污染索引应被真实库重建，而不是继续保留"


# ── 9：搜索缓存作用域 ──


def test_search_cache_keys_are_scoped():
    """不同身份作用域不得互相命中（此前键只有 query/limit）。"""
    from pangu.memory.search_cache import SearchCache

    cache = SearchCache()
    cache.set("q", [{"id": "secret-of-tenant-a"}], limit=10, scope="tenant-a:1")
    assert cache.get("q", limit=10, scope="tenant-a:1") == [{"id": "secret-of-tenant-a"}]
    assert cache.get("q", limit=10, scope="tenant-b:1") is None


def test_search_cache_scope_changes_on_new_drawer():
    from pangu.memory.hybrid_search import _cache_scope

    d1 = Drawer(id="a", content="x")
    d2 = Drawer(id="b", content="y")
    assert _cache_scope([d1]) != _cache_scope([d1, d2])
