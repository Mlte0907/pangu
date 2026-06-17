"""V3 模块测试 H — onnx_embedder / proactive / reconsolidation / sanitizer /
streaming_index / synonyms / vector_index / verification / versioning /
warmup / wikilink / working_memory"""

import os
import tempfile
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from pangu.core.palace import Drawer
from pangu.core.config import PanguConfig


def _drawer(id="t1", content="test content", wing="test", importance=3.0, tags=None):
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or [])


def _config():
    return PanguConfig.load()


# ── onnx_embedder ──

from pangu.memory.onnx_embedder import ONNXEmbedder, get_onnx_embedder, reset_onnx_embedder


class TestONNXEmbedder:
    def test_init(self):
        e = ONNXEmbedder()
        assert e.embedding_dim == 384
        assert e.max_length == 128
        assert not e.is_loaded

    def test_empty_text(self):
        e = ONNXEmbedder()
        vec = e.embed("")
        assert vec is not None
        assert len(vec) == 384
        assert all(v == 0.0 for v in vec)

    def test_embed_batch_empty(self):
        e = ONNXEmbedder()
        assert e.embed_batch([]) == []

    def test_stats(self):
        e = ONNXEmbedder()
        s = e.get_stats()
        assert "model_loaded" in s
        assert "infer_count" in s
        assert s["_realtime_check"] is True

    def test_get_stats_after_embed(self):
        e = ONNXEmbedder()
        e.embed("")
        s = e.get_stats()
        assert s["avg_infer_ms"] == 0.0

    def test_singleton(self):
        reset_onnx_embedder()
        e1 = get_onnx_embedder()
        e2 = get_onnx_embedder()
        assert e1 is e2
        reset_onnx_embedder()

    def test_warmup(self):
        e = ONNXEmbedder()
        # warmup 不应崩溃（模型可能不可用，返回 0）
        count = e.warmup(["hello"])
        assert count >= 0


# ── proactive ──

from pangu.memory.proactive import ProactiveEngine, ProactiveMemory, get_proactive_engine


class TestProactiveEngine:
    def test_init(self):
        e = ProactiveEngine(config=_config())
        assert e._context_window == 10

    def test_update_context(self):
        e = ProactiveEngine(config=_config())
        for i in range(15):
            e.update_context(f"msg {i}")
        assert len(e._context_history) == 10
        assert e._context_history[-1] == "msg 14"

    def test_predict_empty(self):
        e = ProactiveEngine(config=_config())
        assert e.predict("", [_drawer()]) == []
        assert e.predict("hello", []) == []

    def test_predict_with_drawers(self):
        e = ProactiveEngine(config=_config())
        drawers = [_drawer(id="d1", content="python programming tips", tags=["python"])]
        result = e.predict("python tips", drawers)
        assert isinstance(result, list)
        assert len(result) <= 5

    def test_predict_relevance(self):
        e = ProactiveEngine(config=_config())
        d1 = _drawer(id="d1", content="python machine learning tutorial", tags=["python"])
        d2 = _drawer(id="d2", content="cooking recipe for pasta", tags=["food"])
        result = e.predict("python machine learning", [d1, d2])
        if result:
            assert result[0].memory_id == "d1"

    def test_stats(self):
        e = ProactiveEngine(config=_config())
        s = e.get_stats()
        assert "hits" in s
        assert "hit_rate" in s
        assert s["hit_rate"] == 0.0

    def test_singleton(self):
        import pangu.memory.proactive as pm
        pm._proactive_engine = None
        e1 = get_proactive_engine(_config())
        e2 = get_proactive_engine(_config())
        assert e1 is e2
        pm._proactive_engine = None


# ── reconsolidation ──

from pangu.memory.reconsolidation import ReconsolidationEngine, ResonanceEngine


class TestReconsolidationEngine:
    def test_init(self):
        e = ReconsolidationEngine()
        assert e._runs == 0

    def test_run_empty(self):
        e = ReconsolidationEngine()
        state = e.run([])
        assert state["boosted"] == 0
        assert state["candidates"] == 0

    def test_run_with_drawers(self):
        from datetime import datetime, timedelta
        e = ReconsolidationEngine()
        old = (datetime.now() - timedelta(days=5)).isoformat()
        drawers = [
            _drawer(id="d1", content="old memory", importance=0.5),
            _drawer(id="d2", content="recent", importance=0.8),
        ]
        for d in drawers:
            d.created_at = old
        state = e.run(drawers, min_importance=0.3, max_importance=0.7)
        assert state["candidates"] >= 1
        assert state["boosted"] >= 1
        assert state["total_runs"] == 1

    def test_stats(self):
        e = ReconsolidationEngine()
        s = e.stats()
        assert s["runs"] == 0
        assert s["total_boosted"] == 0


class TestResonanceEngine:
    def test_init(self):
        e = ResonanceEngine()
        assert e._matches_found == 0

    def test_find_resonance_no_embedder(self):
        e = ResonanceEngine()
        result = e.find_resonance([_drawer()])
        assert result == []

    def test_find_cross_wing_no_embedder(self):
        e = ResonanceEngine()
        result = e.find_cross_wing_resonance([_drawer()])
        assert result == []

    def test_stats(self):
        e = ResonanceEngine()
        s = e.stats()
        assert "matches_found" in s


# ── sanitizer ──

from pangu.memory.sanitizer import MemorySanitizer


class TestMemorySanitizer:
    def test_sanitize_clean_text(self):
        text = "This is a normal sentence."
        result, redactions = MemorySanitizer.sanitize(text)
        assert result == text
        assert redactions == {}

    def test_sanitize_email(self):
        text = "Contact me at user@example.com"
        result, redactions = MemorySanitizer.sanitize(text, level="standard")
        assert "user@example.com" not in result
        assert "[EMAIL]" in result
        assert "email" in redactions

    def test_sanitize_script_tag(self):
        text = '<script>alert("xss")</script>Hello'
        result, redactions = MemorySanitizer.sanitize(text)
        assert "<script>" not in result
        assert "script_tag" in redactions

    def test_sanitize_minimal(self):
        text = "normal text with email@test.com"
        result, redactions = MemorySanitizer.sanitize(text, level="minimal")
        # minimal only removes URLs with tokens
        assert "email@test.com" in result

    def test_sanitize_strict(self):
        text = "Call 13812345678 or email test@test.com"
        result, redactions = MemorySanitizer.sanitize(text, level="strict")
        assert "13812345678" not in result
        assert "test@test.com" not in result

    def test_for_embedding(self):
        text = "Hello world"
        result = MemorySanitizer.sanitize_for_embedding(text)
        assert result == text

    def test_for_export(self):
        text = "secret password=1234567890123456"
        result = MemorySanitizer.sanitize_for_export(text)
        assert "1234567890123456" not in result

    def test_for_llm(self):
        text = "normal text"
        result = MemorySanitizer.sanitize_for_llm(text)
        assert result == text

    def test_custom_keyword(self):
        MemorySanitizer.add_custom_keyword("TOPSECRET")
        try:
            text = "The TOPSECRET project is here"
            result, redactions = MemorySanitizer.sanitize(text)
            assert "TOPSECRET" not in result
            assert "keyword:TO" in redactions
        finally:
            MemorySanitizer.remove_custom_keyword("TOPSECRET")

    def test_get_redaction_summary(self):
        s = MemorySanitizer.get_redaction_summary("user@test.com")
        assert s["level"] == "standard"
        assert s["total_redactions"] >= 1
        assert s["has_pii"] is True

    def test_phone_sanitize(self):
        text = "Call 13912345678 now"
        result, redactions = MemorySanitizer.sanitize(text, level="strict")
        assert "13912345678" not in result
        assert "phone" in redactions

    def test_id_card(self):
        text = "ID: 110101199001011234"
        result, redactions = MemorySanitizer.sanitize(text, level="strict")
        assert "110101199001011234" not in result
        assert "id_card" in redactions


# ── streaming_index ──

from pangu.memory.streaming_index import StreamingIndexer


class TestStreamingIndexer:
    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx_dir = os.path.join(tmpdir, "idx")
            si = StreamingIndexer(index_dir=idx_dir)
            assert si._total_indexed == 0

    def test_scan_new(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            drawers = [_drawer(id="a"), _drawer(id="b")]
            new = si.scan_new(drawers)
            assert len(new) == 2

    def test_scan_new_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            d = _drawer(id="x")
            si.index([d])
            assert si.scan_new([d]) == []

    def test_index_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            state = si.index([])
            assert state["status"] == "idle"
            assert state["indexed"] == 0

    def test_index_with_drawers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            drawers = [_drawer(id="d1"), _drawer(id="d2")]
            state = si.index(drawers)
            assert state["status"] == "completed"
            assert state["indexed"] == 2
            assert state["total_indexed"] == 2

    def test_merge_wal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            si.index([_drawer(id="m1")])
            count = si.merge_wal()
            assert count >= 1

    def test_rebuild_from_wal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            si.index([_drawer(id="r1"), _drawer(id="r2")])
            si.merge_wal()
            si._indexed_ids.clear()
            restored = si.rebuild_from_wal()
            assert restored >= 1

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            si = StreamingIndexer(index_dir=tmpdir)
            s = si.stats()
            assert "indexed_ids" in s
            assert "wal_size_bytes" in s


# ── synonyms ──

from pangu.memory.synonyms import expand_synonyms, get_synonyms, SYNONYM_MAP


class TestSynonyms:
    def test_expand_synonyms_empty(self):
        result = expand_synonyms("")
        assert isinstance(result, list)

    def test_expand_synonyms_known_word(self):
        result = expand_synonyms("python")
        assert len(result) >= 2
        assert "py" in result or "python" in result

    def test_expand_synonyms_unknown_word(self):
        result = expand_synonyms("xyzunknown123")
        assert "xyzunknown123" in result

    def test_get_synonyms_known(self):
        syns = get_synonyms("python")
        assert isinstance(syns, list)
        assert len(syns) >= 1

    def test_get_synonyms_reverse(self):
        syns = get_synonyms("py")
        assert isinstance(syns, list)

    def test_get_synonyms_unknown(self):
        syns = get_synonyms("qwerty999")
        assert syns == []

    def test_synonym_map_not_empty(self):
        assert len(SYNONYM_MAP) > 50

    def test_expand_multi_word(self):
        result = expand_synonyms("python rust")
        assert len(result) >= 2


# ── vector_index ──

from pangu.memory.vector_index import VectorIndex, get_vector_index


class TestVectorIndex:
    def _make_vi(self, dim=4):
        import tempfile, os
        tmpdir = tempfile.mkdtemp()
        os.environ['PANGU_CACHE_DIR'] = tmpdir
        vi = VectorIndex(dim=dim)
        os.environ.pop('PANGU_CACHE_DIR', None)
        return vi

    def test_init(self):
        vi = self._make_vi()
        assert vi.dim == 4
        assert vi.size == 0

    def test_build_empty(self):
        vi = self._make_vi()
        assert vi.build([], []) is False

    def test_build_mismatch(self):
        vi = self._make_vi()
        assert vi.build([[1, 2, 3]], ["a", "b"]) is False

    def test_build_and_search(self):
        vi = self._make_vi()
        vectors = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]
        ids = ["a", "b", "c"]
        assert vi.build(vectors, ids) is True
        assert vi.size == 3

        results = vi.search([1, 0, 0, 0], top_k=2)
        assert len(results) >= 1
        assert results[0][0] == "a"

    def test_add_single(self):
        vi = self._make_vi()
        vi.add([1, 0, 0, 0], "x")
        assert vi.size == 1

    def test_add_batch(self):
        vi = self._make_vi()
        count = vi.add_batch([[1, 0, 0, 0], [0, 1, 0, 0]], ["a", "b"])
        assert count == 2
        assert vi.size == 2

    def test_add_batch_mismatch(self):
        vi = self._make_vi()
        assert vi.add_batch([[1, 0, 0, 0]], ["a", "b"]) == 0

    def test_search_empty(self):
        vi = self._make_vi()
        results = vi.search([1, 0, 0, 0])
        assert isinstance(results, list)

    def test_clear(self):
        vi = VectorIndex(dim=4)
        vi.build([[1, 0, 0, 0]], ["a"])
        vi.clear()
        assert not vi.is_built
        assert vi.size == 0

    def test_stats(self):
        vi = VectorIndex(dim=4)
        s = vi.stats()
        assert "backend" in s
        assert "size" in s
        assert "dim" in s

    def test_search_batch(self):
        vi = VectorIndex(dim=4)
        vi.build([[1, 0, 0, 0], [0, 1, 0, 0]], ["a", "b"])
        results = vi.search_batch([[1, 0, 0, 0]], top_k=1)
        assert len(results) == 1
        assert len(results[0]) >= 1

    def test_singleton(self):
        import pangu.memory.vector_index as vi_mod
        vi_mod._vector_index = None
        v1 = get_vector_index()
        v2 = get_vector_index()
        assert v1 is v2
        vi_mod._vector_index = None


# ── verification ──

from pangu.memory.verification import VerificationLoop, VerificationResult


class TestVerificationLoop:
    def test_init(self):
        vl = VerificationLoop(project_path="/tmp")
        assert vl.project_path == "/tmp"

    def test_run_build(self):
        vl = VerificationLoop(project_path="/tmp")
        r = vl.run_build()
        assert isinstance(r, VerificationResult)
        assert r.phase == "build"

    def test_run_type_check(self):
        vl = VerificationLoop(project_path="/tmp")
        r = vl.run_type_check()
        assert r.phase == "type_check"

    def test_run_lint(self):
        vl = VerificationLoop(project_path="/tmp")
        r = vl.run_lint()
        assert r.phase == "lint"

    def test_run_security_scan(self):
        vl = VerificationLoop(project_path="/tmp")
        r = vl.run_security_scan()
        assert r.phase == "security"

    def test_run_diff_review(self):
        vl = VerificationLoop(project_path="/tmp")
        r = vl.run_diff_review()
        assert r.phase == "diff_review"

    def test_verification_result_dataclass(self):
        r = VerificationResult(phase="test", passed=True, output="ok")
        assert r.warnings == 0
        assert r.errors == 0


# ── versioning ──

from pangu.memory.versioning import MemoryVersionControl, MemoryVersion, get_version_control


class TestMemoryVersionControl:
    def test_init(self):
        vc = MemoryVersionControl(config=_config())
        assert vc._max_versions == 10

    def test_record_version(self):
        vc = MemoryVersionControl(config=_config())
        v = vc.record_version("m1", "initial content", change_type="create")
        assert v.version == 1
        assert v.content == "initial content"
        assert v.change_type == "create"

    def test_record_multiple(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "v1")
        vc.record_version("m1", "v2")
        vc.record_version("m1", "v3")
        versions = vc.get_versions("m1")
        assert len(versions) == 3
        assert versions[-1].content == "v3"

    def test_max_versions(self):
        vc = MemoryVersionControl(config=_config())
        vc._max_versions = 3
        for i in range(5):
            vc.record_version("m1", f"v{i}")
        versions = vc.get_versions("m1")
        assert len(versions) == 3
        assert versions[0].content == "v2"

    def test_get_latest_version(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "old")
        vc.record_version("m1", "new")
        latest = vc.get_latest_version("m1")
        assert latest.content == "new"

    def test_get_latest_version_empty(self):
        vc = MemoryVersionControl(config=_config())
        assert vc.get_latest_version("nonexistent") is None

    def test_get_version(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "content")
        v = vc.get_version("m1", 1)
        assert v is not None
        assert v.version == 1

    def test_compare_versions(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "hello world")
        vc.record_version("m1", "hello universe")
        diff = vc.compare_versions("m1", 1, 2)
        assert diff["content_changed"] is True
        assert "similarity" in diff

    def test_compare_nonexistent(self):
        vc = MemoryVersionControl(config=_config())
        diff = vc.compare_versions("x", 1, 2)
        assert "error" in diff

    def test_rollback(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "original")
        vc.record_version("m1", "modified")
        rolled = vc.rollback("m1", 1)
        assert rolled is not None
        assert rolled.change_type == "rollback"
        assert rolled.content == "original"

    def test_rollback_nonexistent(self):
        vc = MemoryVersionControl(config=_config())
        assert vc.rollback("x", 1) is None

    def test_get_change_history(self):
        vc = MemoryVersionControl(config=_config())
        vc.record_version("m1", "v1", change_type="create")
        vc.record_version("m1", "v2", change_type="update")
        history = vc.get_change_history("m1")
        assert len(history) == 2
        assert history[0]["change_type"] == "create"

    def test_singleton(self):
        import pangu.memory.versioning as vm
        vm._version_control = None
        v1 = get_version_control(_config())
        v2 = get_version_control(_config())
        assert v1 is v2
        vm._version_control = None


# ── warmup ──

from pangu.memory.warmup import (
    warmup_jieba,
    warmup_onnx,
    warmup_fts_index,
    warmup_vector_index,
    warmup_all,
)


class TestWarmup:
    def test_warmup_jieba(self):
        ms = warmup_jieba()
        assert ms >= 0

    def test_warmup_onnx(self):
        ms = warmup_onnx()
        assert ms >= 0

    def test_warmup_fts_index(self):
        ms = warmup_fts_index()
        assert ms >= 0

    def test_warmup_vector_index(self):
        ms = warmup_vector_index()
        assert ms >= 0

    def test_warmup_all(self):
        results = warmup_all()
        assert "jieba" in results
        assert "onnx" in results
        assert "total" in results
        assert results["total"] >= 0


# ── wikilink ──

from pangu.memory.wikilink import (
    parse_wikilinks,
    resolve_wikilink_to_item,
    extract_entity_links,
    get_wikilink_stats,
    WikilinkMatch,
)


class TestWikilink:
    def test_parse_simple(self):
        matches = parse_wikilinks("See [[Page Title]] for details")
        assert len(matches) == 1
        assert matches[0].target == "Page Title"
        assert matches[0].display == "Page Title"

    def test_parse_with_display(self):
        matches = parse_wikilinks("See [[Page|Custom Display]] here")
        assert len(matches) == 1
        assert matches[0].target == "Page"
        assert matches[0].display == "Custom Display"

    def test_parse_qualified(self):
        matches = parse_wikilinks("See [[wiki:Page Title]] here")
        assert len(matches) == 1
        assert "wiki:Page Title" in matches[0].target

    def test_parse_empty(self):
        assert parse_wikilinks("") == []
        assert parse_wikilinks("no links here") == []

    def test_parse_multiple(self):
        matches = parse_wikilinks("[[A]] and [[B]] and [[C]]")
        assert len(matches) == 3

    def test_resolve_to_item(self):
        drawers = [_drawer(id="d1", content="Python is great"), _drawer(id="d2", content="Rust is fast")]
        result = resolve_wikilink_to_item("Python", drawers)
        assert result == "d1"

    def test_resolve_no_match(self):
        drawers = [_drawer(id="d1", content="Python")]
        result = resolve_wikilink_to_item("Java", drawers)
        assert result is None

    def test_extract_entity_links(self):
        drawers = [_drawer(id="d1", content="Python programming")]
        edges = extract_entity_links("I love [[Python]]", "src", drawers)
        assert len(edges) == 1
        assert edges[0]["target_id"] == "d1"
        assert edges[0]["edge_type"] == "mentions"

    def test_extract_no_links(self):
        edges = extract_entity_links("no links", "src", [])
        assert edges == []

    def test_get_wikilink_stats(self):
        s = get_wikilink_stats("Hello [[World]] and [[Foo]]")
        assert s["total"] == 2
        assert len(s["links"]) == 2

    def test_get_wikilink_stats_empty(self):
        s = get_wikilink_stats("no links")
        assert s["total"] == 0


# ── working_memory ──

from pangu.memory.working_memory import WorkingMemory, WMItem, get_working_memory


class TestWorkingMemory:
    def test_init(self):
        wm = WorkingMemory(capacity=5)
        assert wm.capacity == 5
        assert len(wm.slots) == 0

    def test_push_and_get(self):
        wm = WorkingMemory(capacity=5)
        item = WMItem(id="w1", content="hello")
        wm.push(item)
        assert len(wm.slots) == 1
        retrieved = wm.get("w1")
        assert retrieved is not None
        assert retrieved.content == "hello"

    def test_push_evicts(self):
        wm = WorkingMemory(capacity=2)
        wm.push(WMItem(id="a", content="a", activation=0.1))
        wm.push(WMItem(id="b", content="b", activation=0.1))
        evicted = wm.push(WMItem(id="c", content="c"))
        assert evicted is not None
        assert len(wm.slots) == 2

    def test_push_existing(self):
        wm = WorkingMemory(capacity=3)
        wm.push(WMItem(id="x", content="old"))
        wm.push(WMItem(id="x", content="new"))
        assert len(wm.slots) == 1
        assert wm.get("x").content == "new"

    def test_focus(self):
        wm = WorkingMemory(capacity=3)
        wm.push(WMItem(id="a", content="a", activation=0.3))
        wm.push(WMItem(id="b", content="b", activation=0.9))
        assert wm.focus.id == "b"

    def test_focus_empty(self):
        wm = WorkingMemory(capacity=3)
        assert wm.focus is None

    def test_usage(self):
        wm = WorkingMemory(capacity=5)
        assert wm.usage() == 0.0
        wm.push(WMItem(id="a", content="a"))
        assert wm.usage() == 0.2

    def test_decay_tick(self):
        wm = WorkingMemory(capacity=3)
        wm.push(WMItem(id="a", content="a", activation=1.0))
        wm.decay_tick(dt=1.0)
        assert wm.get("a").activation < 1.0

    def test_clear(self):
        wm = WorkingMemory(capacity=3)
        wm.push(WMItem(id="a", content="a"))
        wm.clear()
        assert len(wm.slots) == 0
        assert wm._total_tokens == 0

    def test_context(self):
        wm = WorkingMemory(capacity=5)
        wm.push(WMItem(id="a", content="hello world"))
        ctx = wm.context
        assert "hello world" in ctx

    def test_stats(self):
        wm = WorkingMemory(capacity=5)
        s = wm.stats
        assert "capacity" in s
        assert "slots_used" in s
        assert s["capacity"] == 5

    def test_token_budget(self):
        wm = WorkingMemory(capacity=10, token_budget=100)
        wm.push(WMItem(id="a", content="a", tokens=30))
        wm.push(WMItem(id="b", content="b", tokens=30))
        assert wm._total_tokens == 60
        assert wm.token_usage == 0.6

    def test_get_nonexistent(self):
        wm = WorkingMemory(capacity=3)
        assert wm.get("nonexistent") is None

    def test_wm_item_touch(self):
        item = WMItem(id="x", content="x")
        old_access = item.last_access
        old_count = item.access_count
        item.touch()
        assert item.access_count == old_count + 1
        assert item.last_access >= old_access

    def test_singleton(self):
        import pangu.memory.working_memory as wmm
        wmm._wm_instance = None
        w1 = get_working_memory()
        w2 = get_working_memory()
        assert w1 is w2
        wmm._wm_instance = None
