"""Pangu v3.0 模块测试 — 第四批 7 个记忆子系统"""

from pangu.core.palace import Drawer


def _d(id="t1", content="test content", wing="test_wing", importance=3.0, tags=None):
    return Drawer(id=id, content=content, wing=wing, importance=importance, tags=tags or ["test"])


def _drawers(n=5):
    return [
        _d(id=f"t{i}", content=f"memory item {i} 关于开发", wing="dev", importance=2.0 + i, tags=["code", f"tag{i}"])
        for i in range(n)
    ]


# ── 1. ProjectManager ──


class TestProjectManager:
    def setup_method(self):
        from pangu.memory.project_manager import ProjectManager

        self.pm = ProjectManager()

    def test_list_projects(self):
        result = self.pm.list_projects()
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["id"] == "default"

    def test_get_active_project(self):
        self.pm.switch_project("default")
        result = self.pm.get_active_project()
        assert result["project_id"] == "default"

    def test_create_project(self):
        result = self.pm.create_project("proj_a", "Project A", "desc a")
        assert result["status"] == "created"
        assert result["project_id"] == "proj_a"
        self.pm.delete_project("proj_a")

    def test_create_duplicate_project(self):
        self.pm.create_project("proj_dup", "Dup")
        result2 = self.pm.create_project("proj_dup", "Dup2")
        assert "error" in result2
        self.pm.delete_project("proj_dup")

    def test_switch_project(self):
        self.pm.create_project("proj_s", "Switch")
        result = self.pm.switch_project("proj_s")
        assert result["switched_to"] == "proj_s"
        self.pm.switch_project("default")
        self.pm.delete_project("proj_s")

    def test_switch_nonexistent(self):
        result = self.pm.switch_project("no_such_project")
        assert "error" in result

    def test_get_project_stats(self):
        stats = self.pm.get_project_stats()
        assert "total_projects" in stats
        assert "total_memories" in stats
        assert "active_project" in stats
        assert stats["total_projects"] >= 1

    def test_save_and_load_memories(self):
        drawers = _drawers(3)
        save_result = self.pm.save_memories(drawers)
        assert save_result["saved"] == 3
        loaded = self.pm.load_memories()
        assert len(loaded) == 3

    def test_load_memories_empty(self):
        self.pm.create_project("proj_empty", "Empty")
        self.pm.switch_project("proj_empty")
        loaded = self.pm.load_memories()
        assert loaded == []
        self.pm.switch_project("default")
        self.pm.delete_project("proj_empty")

    def test_delete_project(self):
        self.pm.create_project("proj_del", "To Delete")
        result = self.pm.delete_project("proj_del")
        assert result["deleted"] == "proj_del"

    def test_delete_default_project(self):
        result = self.pm.delete_project("default")
        assert "error" in result

    def test_delete_nonexistent(self):
        result = self.pm.delete_project("no_such")
        assert "error" in result

    def test_search_cross_project(self):
        drawers = _drawers(3)
        self.pm.save_memories(drawers)
        results = self.pm.search_cross_project("开发")
        assert isinstance(results, list)

    def test_merge_project(self):
        self.pm.create_project("proj_merge_src", "Source")
        self.pm.switch_project("proj_merge_src")
        self.pm.save_memories(_drawers(2))
        self.pm.switch_project("default")
        self.pm.save_memories(_drawers(1))
        result = self.pm.merge_project("proj_merge_src", "default")
        assert "merged" in result
        assert result["merged"] >= 0
        self.pm.delete_project("proj_merge_src")


# ── 2. AuditAnalytics ──


class TestAuditAnalytics:
    def setup_method(self):
        from pangu.memory.audit_analytics import AuditAnalytics

        self.audit = AuditAnalytics()

    def test_log_operation(self):
        entry = self.audit.log("create", target_id="mem1", success=True)
        assert entry.operation == "create"
        assert entry.success is True

    def test_log_with_details(self):
        entry = self.audit.log("read", target_id="mem2", details={"key": "val"}, duration_ms=12.5)
        assert entry.details == {"key": "val"}
        assert entry.duration_ms == 12.5

    def test_log_operation便捷(self):
        entry = self.audit.log_operation("update", target_id="mem3")
        assert entry.operation == "update"

    def test_get_entries_empty(self):
        entries = self.audit.get_entries()
        assert entries == []

    def test_get_entries_after_log(self):
        self.audit.log("create")
        self.audit.log("delete")
        entries = self.audit.get_entries()
        assert len(entries) == 2

    def test_get_entries_filter_operation(self):
        self.audit.log("create")
        self.audit.log("read")
        self.audit.log("create")
        entries = self.audit.get_entries(operation="create")
        assert len(entries) == 2

    def test_get_entries_filter_user(self):
        self.audit.log("create", user_id="alice")
        self.audit.log("create", user_id="bob")
        entries = self.audit.get_entries(user_id="alice")
        assert len(entries) == 1

    def test_get_operation_stats_empty(self):
        stats = self.audit.get_operation_stats()
        assert stats["total_operations"] == 0
        assert stats["success_rate"] == 0.0

    def test_get_operation_stats(self):
        self.audit.log("create", duration_ms=10)
        self.audit.log("create", duration_ms=20)
        self.audit.log("delete", duration_ms=5)
        stats = self.audit.get_operation_stats()
        assert stats["total_operations"] == 3
        assert stats["operation_counts"]["create"] == 2
        assert stats["operation_counts"]["delete"] == 1

    def test_get_security_summary_empty(self):
        summary = self.audit.get_security_summary()
        assert "total_operations" in summary
        assert "risk_level" in summary
        assert summary["risk_level"] == "low"

    def test_get_security_summary(self):
        for _ in range(3):
            self.audit.log("delete")
        summary = self.audit.get_security_summary()
        assert summary["total_operations"] == 3

    def test_detect_anomalies_empty(self):
        anomalies = self.audit.detect_anomalies()
        assert anomalies == []

    def test_max_entries_limit(self):
        self.audit._max_entries = 5
        for _i in range(10):
            self.audit.log("create")
        assert len(self.audit._entries) == 5


# ── 3. SyncManager ──


class TestSyncManager:
    def setup_method(self):
        from pangu.memory.sync_manager import SyncManager

        self.sync = SyncManager()

    def test_record_change(self):
        entry = self.sync.record_change("mem1", "create", content="hello")
        assert entry.memory_id == "mem1"
        assert entry.operation == "create"
        assert entry.content_hash

    def test_record_change_empty_content(self):
        entry = self.sync.record_change("mem2", "delete")
        assert entry.content_hash == ""

    def test_get_pending_changes_empty(self):
        pending = self.sync.get_pending_changes()
        assert isinstance(pending, list)

    def test_get_pending_changes_after_record(self):
        self.sync.record_change("mem1", "create", content="data")
        pending = self.sync.get_pending_changes()
        assert len(pending) >= 1
        assert pending[-1]["memory_id"] == "mem1"

    def test_get_pending_changes_since(self):
        self.sync.record_change("mem1", "create", content="old")
        self.sync.record_change("mem2", "create", content="new")
        pending = self.sync.get_pending_changes(since="2099-01-01")
        assert pending == []

    def test_detect_conflicts_empty(self):
        conflicts = self.sync.detect_conflicts([])
        assert conflicts == []

    def test_detect_conflicts_with_local(self):
        self.sync.record_change("mem1", "update", content="local version", old_content="base")
        remote = [
            {
                "memory_id": "mem1",
                "operation": "update",
                "content_hash": "remote_hash",
                "id": "r1",
                "timestamp": "2099-01-01",
                "source": "device_b",
            }
        ]
        conflicts = self.sync.detect_conflicts(remote)
        assert isinstance(conflicts, list)

    def test_detect_conflicts_no_conflict(self):
        self.sync.record_change("mem1", "update", content="v1", old_content="v0")
        remote = [
            {
                "memory_id": "mem1",
                "operation": "update",
                "content_hash": "v1_hash",
                "id": "r1",
                "timestamp": "2099-01-01",
                "source": "device_b",
            }
        ]
        conflicts = self.sync.detect_conflicts(remote)
        assert isinstance(conflicts, list)

    def test_resolve_conflict(self):
        entry = self.sync.record_change("mem1", "update", content="x", old_content="y")
        result = self.sync.resolve_conflict(entry.change_id)
        assert "resolved_at" in result

    def test_resolve_conflict_not_found(self):
        result = self.sync.resolve_conflict("nonexistent")
        assert "error" in result

    def test_mark_synced(self):
        e1 = self.sync.record_change("mem1", "create", content="a")
        self.sync.record_change("mem2", "create", content="b")
        count = self.sync.mark_synced([e1.change_id])
        assert count == 1

    def test_get_sync_state(self):
        state = self.sync.get_sync_state()
        assert "device_id" in state
        assert "pending" in state
        assert "synced" in state

    def test_get_sync_stats(self):
        self.sync.record_change("mem1", "create", content="x")
        stats = self.sync.get_sync_stats()
        assert "total_changes" in stats
        assert stats["total_changes"] >= 1

    def test_get_change_history(self):
        self.sync.record_change("mem1", "create", content="a")
        history = self.sync.get_change_history()
        assert len(history) >= 1

    def test_get_change_history_filter(self):
        self.sync.record_change("mem1", "create", content="a")
        self.sync.record_change("mem2", "update", content="b")
        history = self.sync.get_change_history(memory_id="mem1")
        assert all(h["memory_id"] == "mem1" for h in history)


# ── 4. MemoryEventStream ──


class TestMemoryEventStream:
    def setup_method(self):
        from pangu.memory.memory_events import MemoryEventStream

        self.stream = MemoryEventStream()

    def test_emit(self):
        event = self.stream.emit("memory.write", memory_id="m1", data={"content": "hi"})
        assert event.event_type == "memory.write"
        assert event.memory_id == "m1"

    def test_emit_empty_data(self):
        event = self.stream.emit("memory.delete", memory_id="m2")
        assert event.data == {}

    def test_get_history_empty(self):
        history = self.stream.get_history()
        assert history == []

    def test_get_history_after_emit(self):
        self.stream.emit("memory.write")
        self.stream.emit("memory.delete")
        history = self.stream.get_history()
        assert len(history) == 2

    def test_get_history_filter_type(self):
        self.stream.emit("memory.write")
        self.stream.emit("memory.delete")
        self.stream.emit("memory.write")
        history = self.stream.get_history(event_type="memory.write")
        assert len(history) == 2

    def test_get_history_limit(self):
        for _i in range(10):
            self.stream.emit("memory.write")
        history = self.stream.get_history(limit=3)
        assert len(history) == 3

    def test_get_stats(self):
        self.stream.emit("memory.write")
        self.stream.emit("memory.write")
        self.stream.emit("memory.delete")
        stats = self.stream.get_stats()
        assert stats["total_events"] == 3
        assert stats["event_counts"]["memory.write"] == 2

    def test_subscribe_and_emit(self):
        received = []
        sub_id = self.stream.subscribe("memory.write", lambda e: received.append(e))
        self.stream.emit("memory.write", memory_id="m1")
        assert len(received) == 1
        assert received[0].memory_id == "m1"
        self.stream.unsubscribe(sub_id)

    def test_subscribe_wrong_type(self):
        received = []
        sub_id = self.stream.subscribe("memory.delete", lambda e: received.append(e))
        self.stream.emit("memory.write")
        assert len(received) == 0
        self.stream.unsubscribe(sub_id)

    def test_unsubscribe(self):
        sub_id = self.stream.subscribe("memory.write", lambda e: None)
        assert self.stream.unsubscribe(sub_id) is True
        assert self.stream.unsubscribe("nonexistent") is False

    def test_emit_memory_write(self):
        event = self.stream.emit_memory_write("m1", content="hello world", wing="test")
        assert event.event_type == "memory.write"
        assert event.data["wing"] == "test"

    def test_emit_memory_search(self):
        event = self.stream.emit_memory_search("query", result_count=5)
        assert event.event_type == "memory.search"
        assert event.data["result_count"] == 5

    def test_add_webhook(self):
        result = self.stream.add_webhook("http://example.com", ["memory.write"])
        assert result["status"] == "registered"

    def test_remove_webhook(self):
        self.stream.add_webhook("http://example.com", ["memory.write"])
        assert self.stream.remove_webhook("http://example.com") is True
        assert self.stream.remove_webhook("http://nope.com") is False

    def test_wildcard_subscribe(self):
        received = []
        sub_id = self.stream.subscribe("*", lambda e: received.append(e))
        self.stream.emit("memory.write")
        self.stream.emit("memory.delete")
        assert len(received) == 2
        self.stream.unsubscribe(sub_id)


# ── 5. SmartIndexingEngine ──


class TestSmartIndexingEngine:
    def setup_method(self):
        from pangu.memory.smart_indexing import SmartIndexingEngine

        self.engine = SmartIndexingEngine()

    def test_build_all_indexes_empty(self):
        result = self.engine.build_all_indexes([])
        assert result["total_indexes"] == 0

    def test_build_all_indexes(self):
        drawers = _drawers(5)
        result = self.engine.build_all_indexes(drawers)
        assert result["total_indexes"] > 0
        assert "hot_words" in result
        assert "tags" in result
        assert "wings" in result

    def test_build_hot_word_index(self):
        drawers = _drawers(3)
        result = self.engine.build_hot_word_index(drawers)
        assert "hot_words_indexed" in result

    def test_build_tag_index(self):
        drawers = _drawers(3)
        result = self.engine.build_tag_index(drawers)
        assert "tag_indexes" in result
        assert result["unique_tags"] >= 1

    def test_build_wing_index(self):
        drawers = _drawers(3)
        result = self.engine.build_wing_index(drawers)
        assert "wing_indexes" in result

    def test_search_index_empty(self):
        results = self.engine.search_index("nothing")
        assert results == []

    def test_search_index_after_build(self):
        self.engine.build_all_indexes(_drawers(5))
        results = self.engine.search_index("tag")
        assert isinstance(results, list)

    def test_get_index_health_empty(self):
        health = self.engine.get_index_health()
        assert health["total_indexes"] == 0
        assert health["health"] in ("good", "needs_cleanup")

    def test_get_index_health(self):
        self.engine.build_all_indexes(_drawers(5))
        health = self.engine.get_index_health()
        assert health["total_indexes"] > 0

    def test_cleanup_indexes(self):
        self.engine.build_all_indexes(_drawers(3))
        removed = self.engine.cleanup_indexes()
        assert removed >= 0

    def test_log_query(self):
        self.engine.log_query("test query", ["m1", "m2"])
        stats = self.engine.get_smart_index_stats()
        assert stats["query_log_size"] >= 1

    def test_recommend_indexes(self):
        for _ in range(3):
            self.engine.log_query("热门词汇")
        recs = self.engine.recommend_indexes(_drawers(3))
        assert isinstance(recs, list)


# ── 6. CacheManager ──


class TestCacheManager:
    def setup_method(self):
        from pangu.memory.smart_cache import CacheManager

        self.cache = CacheManager()

    def test_set_and_get(self):
        self.cache.set("k1", "value1")
        assert self.cache.get("k1") == "value1"

    def test_get_missing(self):
        assert self.cache.get("nonexistent") is None

    def test_set_overwrite(self):
        self.cache.set("k1", "old")
        self.cache.set("k1", "new")
        assert self.cache.get("k1") == "new"

    def test_invalidate(self):
        self.cache.set("k1", "v1")
        self.cache.invalidate("k1")
        assert self.cache.get("k1") is None

    def test_invalidate_nonexistent(self):
        self.cache.invalidate("nope")
        assert True

    def test_get_stats(self):
        stats = self.cache.get_stats()
        assert "combined_hit_rate" in stats
        assert "l1" in stats
        assert "l2" in stats

    def test_get_stats_after_ops(self):
        self.cache.set("k1", "v1")
        self.cache.get("k1")
        self.cache.get("miss")
        stats = self.cache.get_stats()
        assert stats["combined_hit_rate"] > 0

    def test_l1_hit(self):
        self.cache.set("k1", "v1")
        self.cache.get("k1")
        stats = self.cache.get_stats()
        assert stats["l1_hit_rate"] > 0

    def test_l2_hit(self):
        self.cache.set("k1", "v1")
        self.cache._l1.clear()
        self.cache.get("k1")
        stats = self.cache.get_stats()
        assert stats["l2_hit_rate"] > 0

    def test_ttl_expiry(self):
        self.cache.set("k1", "v1", ttl=0)
        import time

        time.sleep(0.01)
        assert self.cache.get("k1") is None


# ── 7. MemoryPortal ──


class TestMemoryPortal:
    def setup_method(self):
        from pangu.memory.portal import MemoryPortal

        self.portal = MemoryPortal()

    def test_system_panorama_empty(self):
        result = self.portal.system_panorama([])
        assert result["total_memories"] == 0
        assert result["wing_distribution"] == {}

    def test_system_panorama(self):
        drawers = _drawers(5)
        result = self.portal.system_panorama(drawers)
        assert result["total_memories"] == 5
        assert "wing_distribution" in result
        assert result["unique_tags"] >= 1
        assert result["avg_importance"] > 0
        assert "timestamp" in result

    def test_system_panorama_top_tags(self):
        drawers = _drawers(10)
        result = self.portal.system_panorama(drawers)
        assert len(result["top_tags"]) <= 10
        assert all("tag" in t and "count" in t for t in result["top_tags"])

    def test_get_smart_summary_empty(self):
        summary = self.portal.get_smart_summary([])
        assert "盘古记忆系统状态" in summary
        assert "记忆: 0条" in summary

    def test_get_smart_summary(self):
        drawers = _drawers(3)
        summary = self.portal.get_smart_summary(drawers)
        assert "盘古记忆系统状态" in summary
        assert "记忆: 3条" in summary

    def test_get_smart_summary_multiple_wings(self):
        d1 = _d("w1", "content a", wing="research")
        d2 = _d("w2", "content b", wing="dev")
        summary = self.portal.get_smart_summary([d1, d2])
        assert "领域: 2个" in summary

    def test_smart_write(self):
        drawers = _drawers(3)
        result = self.portal.smart_write(drawers, "test memory content", wing="test", tags=["alpha", "beta"])
        assert result["created"]
        assert result["wing"] == "test"
        assert "alpha" in result["tags"]
        assert "event_emitted" in result["auto_actions"]
        assert "index_updated" in result["auto_actions"]

    def test_smart_write_auto_tags(self):
        result = self.portal.smart_write([], "这是一个关于测试的记忆内容")
        assert len(result["tags"]) >= 1
        assert result["created"]
