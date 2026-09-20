"""卫生类修复的回归测试（2026-09-20）。

1. ABAC 条件求值不再可逃逸（AST 白名单）
2. config.json 的 api_key 不再覆盖进程内显式设置的密钥
3. palace_meta 迁移写为原子写 + 损坏可容错
4. LLM 缓存 hit_count 不再系统性少记
5. EmbeddingCache 并发安全
6. FTS 索引/查询共用同一分词器（无空格中文可召回）
7. SqliteDrawerStorage 不重置 created_timestamp
"""

import numpy as np
import pytest

from pangu.core.palace import Drawer


# ── 1：ABAC 沙箱 ──


def _abac_ctx():
    from pangu.api.abac import Environment, RequestContext, Resource, Subject

    return RequestContext(
        subject=Subject(user_id="u", role="service", tenant_id="t", clearance=2),
        action="read",
        resource=Resource(type="memories", tenant_id="t"),
        environment=Environment(),
    )


@pytest.mark.parametrize(
    "expr",
    [
        "().__class__.__bases__[0].__subclasses__() and True",
        "s.__class__.__mro__",
        "__import__('os')",
        "open('/etc/passwd').read()",
        "().__class__.__bases__[0].__subclasses__()[0].__init__.__globals__",
    ],
)
def test_abac_rejects_escape_expressions(expr):
    from pangu.api.abac import Effect, Rule

    assert Rule(effect=Effect.ALLOW, condition=expr).matches(_abac_ctx()) is False


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("act == 'read'", True),
        ("s.tenant_id == r.tenant_id", True),
        ("s.clearance >= 2 and act in ('read', 'search')", True),
        ("s.role == 'admin'", False),
        ("r.visibility == 'public'", False),
    ],
)
def test_abac_allows_legitimate_expressions(expr, expected):
    from pangu.api.abac import Effect, Rule

    assert Rule(effect=Effect.ALLOW, condition=expr).matches(_abac_ctx()) is expected


# ── 2：密钥不被 config.json 覆盖 ──


def test_config_json_does_not_override_api_key(tmp_path, monkeypatch):
    """进程内显式设置的 api_key 必须胜过 config.json 里的值。"""
    import json

    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"api_key": "FROM_FILE", "llm_model": "from-file-model"}), encoding="utf-8")

    from pangu.core import config as cfg_mod

    monkeypatch.setattr(cfg_mod.config, "api_key", "PROGRAMMATIC", raising=False)
    monkeypatch.setattr(cfg_mod.config, "config_path", str(cfg_file), raising=False)

    from pangu.api.server import create_app

    create_app()
    assert cfg_mod.config.api_key == "PROGRAMMATIC", "api_key 是密钥，不应被 config.json 覆盖"


# ── 3：迁移原子写 + 容错 ──


def test_palace_meta_path_follows_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PANGU_BASE_DIR", str(tmp_path / ".pangu"))
    monkeypatch.setenv("PANGU_PALACE_PATH", str(tmp_path / ".pangu" / "palace"))
    from pangu.store.migrations import _get_palace_meta_path

    p = _get_palace_meta_path()
    assert str(p).startswith(str(tmp_path)), f"palace_meta 应在隔离目录下，实得 {p}"


def test_load_meta_survives_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("PANGU_BASE_DIR", str(tmp_path / ".pangu"))
    monkeypatch.setenv("PANGU_PALACE_PATH", str(tmp_path / ".pangu" / "palace"))
    from pangu.store import migrations

    p = migrations._get_palace_meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json", encoding="utf-8")

    meta = migrations._load_meta()  # 不应抛异常
    assert isinstance(meta, dict)
    assert "name" in meta


# ── 4：LLM 缓存 hit_count ──


def test_cache_counts_all_hits_in_window(tmp_path):
    from pangu.core.cache import PersistentCache
    from pangu.core.llm import LLMResponse

    cache = PersistentCache(
        db_path=str(tmp_path / "llm.db"),
        write_throttle=10,
        ttl_days=1,
        max_disk_mb=10,
    )
    resp = LLMResponse(content="hi", model="m", provider="p", latency_ms=1.0, usage={})
    cache.put("k1", "p", "m", {"q": "x"}, resp)

    # 10 次命中正好跨过一个节流窗口（write_throttle=10）
    for _ in range(10):
        assert cache.get("k1") is not None

    # 直接查库计数，避免受 get_top_keys 的 key 截断影响
    conn = cache._get_conn()
    hit_count = conn.execute("SELECT hit_count FROM llm_cache WHERE key = 'k1'").fetchone()[0]
    assert hit_count >= 10, f"窗口内 10 次命中应全部计入，实得 {hit_count}"


# ── 5：嵌入缓存并发 ──


def test_embedding_cache_is_thread_safe():
    import threading

    from pangu.search.embedder import EmbeddingCache

    cache = EmbeddingCache(cache_file=None)
    errors: list[str] = []

    def worker(i):
        try:
            for j in range(200):
                cache.set(f"k{i}-{j}", np.random.rand(4))
                cache.get(f"k{i}-{j}")
                if j % 50 == 0:
                    cache.save(force=True)
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发访问不应抛错: {errors[:3]}"


# ── 6：FTS 分词一致 ──


def test_fts_query_tokenizer_matches_index():
    from pangu.core.config import PanguConfig
    from pangu.memory.fts_search import FTS5SearchEngine

    cfg = PanguConfig.load().authoritative_memory_config()
    engine = FTS5SearchEngine(cfg)
    drawers = [
        Drawer(id="m1", content="盘古记忆系统向量检索"),
        Drawer(id="m2", content="完全无关的另一段话"),
    ]
    engine.build_index(drawers)
    assert engine._tokenizer in ("jieba", "regex")

    # 无空格中文查询：修复前索引用整段正则、查询用 split() ⇒ 永远命中不了
    scores = engine._fts_search("向量检索", drawers)
    assert "m1" in scores, f"无空格中文查询应能召回，实得 {scores}"


def test_fts_detects_tokenizer_mismatch(monkeypatch):
    from pangu.core.config import PanguConfig
    from pangu.memory.fts_search import FTS5SearchEngine

    cfg = PanguConfig.load().authoritative_memory_config()
    engine = FTS5SearchEngine(cfg)
    engine._tokenizer = "jieba"  # 声称是 jieba 建的
    monkeypatch.setattr("pangu.memory.fts_search._get_jieba", lambda: None)
    # 当前是 regex，与索引不一致 ⇒ 返回空（走子串兜底），不产生"看似正常实则全空"
    assert engine._tokenize_for_query("盘古") == []


# ── 7：SqliteDrawerStorage 保留创建时间 ──


def test_sqlite_storage_preserves_created_timestamp(tmp_path):
    from pangu.memory.drawer_storage import SqliteDrawerStorage

    storage = SqliteDrawerStorage(str(tmp_path / "d.db"))
    d = Drawer(id="a", content="x")
    d.created_at = "2020-01-01T00:00:00"
    storage.save([d])
    ts = storage._created_ts(d)
    assert ts < 1_600_000_000, f"应解析出 2020 年的时间戳，实得 {ts}"
    storage.close()
