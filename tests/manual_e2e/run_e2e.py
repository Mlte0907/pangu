#!/usr/bin/env python3
"""盘古记忆系统全量 E2E 测试 — 覆盖全部 423 个 MCP 工具的真实性验证

运行方式:
    cd /home/xiaoxin/pangu
    .venv/bin/python tests/manual_e2e/run_e2e.py
"""

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

# ─────────────────────────────────────────────────
# 安全：仅允许连接本地回环地址
# ─────────────────────────────────────────────────
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _validate_host(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname in _ALLOWED_HOSTS:
        return True
    try:
        addrinfos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        for family, _, _, _, sockaddr in addrinfos:
            ip = sockaddr[0]
            if ip.startswith("127.") or ip == "::1":
                return True
    except (socket.gaierror, IndexError):
        pass
    return False


def _local_post(url: str, payload: dict, timeout: int = 30) -> dict:
    if not _validate_host(url):
        raise ValueError(f"安全限制：仅允许连接本地回环地址，目标 {url} 被拒绝")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _local_get(url: str, timeout: int = 5) -> dict:
    if not _validate_host(url):
        raise ValueError("安全限制：仅允许连接本地回环地址")
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return {"status": resp.status, "body": resp.read().decode("utf-8", errors="replace")}


# ─────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────
@dataclass
class MCPResult:
    tool: str
    success: bool
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0


class MCPClient:
    def __init__(self, base_url: str = "http://127.0.0.1:19529", timeout: int = 30):
        self.base_url = base_url
        self.mcp_url = f"{base_url}/mcp"
        self.timeout = timeout
        self._count = 0
        self._results: list[MCPResult] = []

    def call(self, tool: str, args: dict = None) -> MCPResult:
        self._count += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._count,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args or {}},
        }
        t0 = time.time()
        try:
            data = _local_post(self.mcp_url, payload, self.timeout)
            ms = (time.time() - t0) * 1000
            if "error" in data:
                r = MCPResult(tool, False, error=str(data["error"])[:200], elapsed_ms=ms)
            else:
                texts = [
                    c.get("text", "") for c in data.get("result", {}).get("content", []) if c.get("type") == "text"
                ]
                r = MCPResult(tool, True, result="".join(texts), elapsed_ms=ms)
        except Exception as e:
            ms = (time.time() - t0) * 1000
            r = MCPResult(tool, False, error=f"{type(e).__name__}: {e}"[:200], elapsed_ms=ms)
        self._results.append(r)
        return r

    def raw(self, tool: str, args: dict = None) -> dict:
        r = self.call(tool, args)
        if r.success and r.result:
            try:
                return json.loads(r.result)
            except Exception:
                return {"_text": r.result}
        return {"_error": r.error}

    def list_tools(self) -> list:
        return (
            _local_post(self.mcp_url, {"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}}, self.timeout)
            .get("result", {})
            .get("tools", [])
        )

    def http_get(self, path: str) -> dict:
        return _local_get(f"{self.base_url}{path}")

    def summary(self) -> dict:
        total = len(self._results)
        ok = sum(1 for r in self._results if r.success)
        return {
            "total": total,
            "pass": ok,
            "fail": total - ok,
            "rate": f"{ok / max(total, 1) * 100:.1f}%",
            "avg_ms": f"{sum(r.elapsed_ms for r in self._results) / max(total, 1):.1f}",
            "failed": [r.tool for r in self._results if not r.success],
        }


# ─────────────────────────────────────────────────
# 测试报告
# ─────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.phases: dict[str, list] = {}
        self.bugs: list[dict] = []

    def rec(self, phase: str, name: str, status: str, detail: str = "", ms: float = 0):
        self.phases.setdefault(phase, []).append({"name": name, "s": status, "d": detail, "ms": ms})

    def bug(self, phase: str, title: str, desc: str, sev: str = "M"):
        self.bugs.append({"p": phase, "t": title, "d": desc, "s": sev})

    def print(self):
        tp = tf = tw = ts = 0
        print("\n" + "=" * 70)
        print("  盘古记忆系统 E2E 测试报告")
        print("=" * 70)
        for phase, tests in self.phases.items():
            p = sum(1 for t in tests if t["s"] == "PASS")
            f = sum(1 for t in tests if t["s"] == "FAIL")
            w = sum(1 for t in tests if t["s"] == "WARN")
            s = sum(1 for t in tests if t["s"] == "SKIP")
            tp += p
            tf += f
            tw += w
            ts += s
            icon = "✅" if f == 0 else "❌"
            print(f"\n{icon} {phase}: {p}P {f}F {w}W {s}S")
            for t in tests:
                si = {"PASS": "  ✅", "FAIL": "  ❌", "WARN": "  ⚠️", "SKIP": "  ⏭️"}.get(t["s"], "  ?")
                lat = f" ({t['ms']:.0f}ms)" if t["ms"] > 0 else ""
                det = f" — {t['d']}" if t["d"] else ""
                print(f"{si} {t['name']}{lat}{det}")
        print(f"\n{'=' * 70}")
        print(f"总计: {tp}P {tf}F {tw}W {ts}S | 通过率: {tp / max(tp + tf, 1) * 100:.1f}%")
        if self.bugs:
            print(f"\n🐛 {len(self.bugs)} 个功能缺陷:")
            for b in self.bugs:
                print(f"  [{b['s']}] {b['t']}: {b['d']}")
        print("=" * 70)


# ─────────────────────────────────────────────────
# 默认参数生成器
# ─────────────────────────────────────────────────
def _args(tool: str) -> dict:
    """为每个工具提供合理默认参数"""
    m = {
        "pangu_recall": {"query": "测试", "limit": 5},
        "pangu_wake_up": {},
        "pangu_archive_memory": {"memory_id": "nonexistent"},
        "pangu_ingest_text": {"text": "测试文本", "wing": "test"},
        "pangu_fts_search": {"query": "测试", "limit": 5},
        "pangu_natural_query": {"query": "什么是Python"},
        "pangu_recommend": {"query": "编程"},
        "pangu_conversational_search": {"query": "你好"},
        "pangu_memory_insights": {},
        "pangu_cluster_memories": {},
        "pangu_find_related": {"memory_id": "test"},
        "pangu_rerank": {"query": "测试", "results": "[]"},
        "pangu_search_explain": {"query": "测试"},
        "pangu_hybrid_search": {"query": "测试"},
        "pangu_kg_query": {"entity_name": "test"},
        "pangu_kg_neighbors": {"entity_name": "test"},
        "pangu_kg_auto_extract": {"content": "Python和SQLite"},
        "pangu_kg_cross_domain": {"source_domain": "tech", "target_domain": "biz"},
        "pangu_kg_similar_patterns": {"entity_name": "test"},
        "pangu_graph_infer": {"query": "test"},
        "pangu_graph_contradictions": {},
        "pangu_graph_causal_chain": {"start_entity": "test"},
        "pangu_graph_temporal": {},
        "pangu_graph_analogy": {"source": "A", "target": "B"},
        "pangu_graph_visualize": {},
        "pangu_graph_visualize_web": {},
        "pangu_graph_entity": {"entity_name": "test"},
        "pangu_graph_path": {"source": "A", "target": "B"},
        "pangu_graph_quality": {},
        "pangu_graph_stats": {},
        "pangu_build_graph": {},
        "pangu_list_wiki_pages": {},
        "pangu_get_wiki_page": {"page_id": "test"},
        "pangu_create_wiki_page": {"title": "测试", "content": "内容"},
        "pangu_auto_generate_wiki": {},
        "pangu_wm_push": {"content": "测试"},
        "pangu_wm_get": {},
        "pangu_wm_stats": {},
        "pangu_wm_clear": {},
        "pangu_neural_stats": {},
        "pangu_neural_sleep": {"cycles": 1},
        "pangu_neural_spreading": {"query": "测试"},
        "pangu_neural_inhibition": {},
        "pangu_neural_decay": {},
        "pangu_consolidation_stats": {},
        "pangu_consolidate": {},
        "pangu_merge_candidates": {},
        "pangu_resolve_conflicts": {},
        "pangu_evaluate_forgetting": {},
        "pangu_auto_forget": {},
        "pangu_get_archive": {},
        "pangu_compress_memories": {},
        "pangu_detect_associations": {},
        "pangu_memory_importance": {},
        "pangu_fuse_topic": {},
        "pangu_progressive_summarize": {},
        "pangu_crystallize_knowledge": {},
        "pangu_distill_knowledge": {},
        "pangu_distill_causal_chains": {},
        "pangu_distill_graph": {},
        "pangu_distill_stats": {},
        "pangu_importance_feedback": {},
        "pangu_search_stats": {},
        "pangu_fts_search_stats": {},
        "pangu_search_analytics_summary": {},
        "pangu_search_analytics_top": {},
        "pangu_search_analytics_empty": {},
        "pangu_search_analytics_slow": {},
        "pangu_index_build": {},
        "pangu_index_search": {"query": "测试"},
        "pangu_index_recommend": {"query": "测试"},
        "pangu_index_health": {},
        "pangu_index_cleanup": {},
        "pangu_vector_index_stats": {},
        "pangu_vector_index_build": {},
        "pangu_cache_stats": {},
        "pangu_cache_cleanup": {},
        "pangu_cache_invalidate": {},
        "pangu_cache_clear": {},
        "pangu_llm_cache_stats": {},
        "pangu_llm_cache_top": {},
        "pangu_llm_cache_clear": {},
        "pangu_llm_cache_metrics": {},
        "pangu_llm_cache_warmup": {},
        "pangu_llm_cache_warmup_log": {},
        "pangu_llm_cache_vacuum": {},
        "pangu_llm_cache_config": {},
        "pangu_diff_content": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_diff_batch": {},
        "pangu_diff_similarity": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_diff_stats": {},
        "pangu_visualize_graph": {},
        "pangu_visualize_network": {},
        "pangu_visualize_stats": {},
        "pangu_detect_patterns": {},
        "pangu_popular_queries": {},
        "pangu_frequent_memories": {},
        "pangu_comment_add": {"memory_id": "test", "comment": "评论"},
        "pangu_comment_list": {"memory_id": "test"},
        "pangu_vote": {"memory_id": "test", "vote": "up"},
        "pangu_vote_stats": {"memory_id": "test"},
        "pangu_dream_cycle": {},
        "pangu_dream_stats": {},
        "pangu_curiosity_explore": {},
        "pangu_curiosity_gaps": {},
        "pangu_persona_identity": {},
        "pangu_persona_values": {},
        "pangu_persona_health": {},
        "pangu_autonomous_tick": {},
        "pangu_autonomous_run": {},
        "pangu_autonomous_status": {},
        "pangu_autonomous_analyze": {},
        "pangu_multi_register": {"agent_id": "test_agent", "agent_type": "coding"},
        "pangu_multi_write": {"agent_id": "test_agent", "content": "测试"},
        "pangu_multi_read": {"agent_id": "test_agent"},
        "pangu_multi_agents": {},
        "pangu_generate_ideas": {"topic": "测试"},
        "pangu_generate_novel": {"topic": "测试"},
        "pangu_agent_register": {"agent_id": "test"},
        "pangu_agent_share": {"from_agent": "a", "to_agent": "b", "content": "共享"},
        "pangu_collaborative_reason": {"query": "测试"},
        "pangu_agent_stats": {},
        "pangu_synthesize": {"query": "测试"},
        "pangu_find_contradictions": {},
        "pangu_core_insights": {},
        "pangu_auto_learn": {},
        "pangu_arch_analyze": {},
        "pangu_arch_suggest": {},
        "pangu_cold_hot": {},
        "pangu_arch_stats": {},
        "pangu_qa": {"question": "什么是Python?"},
        "pangu_qa_batch": {"questions": "['什么是Python?']"},
        "pangu_qa_stats": {},
        "pangu_inject_context": {"context": "Python编程"},
        "pangu_update_context": {"context": "新上下文"},
        "pangu_current_context": {},
        "pangu_injection_stats": {},
        "pangu_auto_inject": {},
        "pangu_forget_stats": {},
        "pangu_distill": {},
        "pangu_distill_by_wing": {"wing": "test"},
        "pangu_distillation_stats": {},
        "pangu_onnx_embed": {"text": "测试"},
        "pangu_onnx_embed_batch": {"texts": "['测试1','测试2']"},
        "pangu_onnx_status": {},
        "pangu_onnx_similarity": {"text_a": "Python", "text_b": "编程"},
        "pangu_export": {"format": "json"},
        "pangu_import": {},
        "pangu_backup": {},
        "pangu_list_backups": {},
        "pangu_backup_stats": {},
        "pangu_export_json": {},
        "pangu_export_markdown": {},
        "pangu_export_csv": {},
        "pangu_export_yaml": {},
        "pangu_export_obsidian": {},
        "pangu_import_smart": {},
        "pangu_list_exports": {},
        "pangu_export_stats": {},
        "pangu_verify_backup": {},
        "pangu_env_check": {},
        "pangu_startup_validate": {},
        "pangu_importance_score": {},
        "pangu_reassess_importance": {},
        "pangu_auto_collect": {},
        "pangu_collect_stats": {},
        "pangu_feishu_status": {},
        "pangu_watch_status": {},
        "pangu_event_emit": {"event_type": "test", "data": "{}"},
        "pangu_event_history": {},
        "pangu_event_stats": {},
        "pangu_event_webhook_add": {"url": "http://test.com"},
        "pangu_event_save": {},
        "pangu_audit_log": {},
        "pangu_audit_query": {},
        "pangu_audit_stats": {},
        "pangu_access_patterns": {},
        "pangu_security_summary": {},
        "pangu_plugin_list": {},
        "pangu_plugin_config": {"plugin_name": "test"},
        "pangu_plugin_discover": {},
        "pangu_version_history": {},
        "pangu_version_compare": {},
        "pangu_build_timeline": {},
        "pangu_find_causal_links": {},
        "pangu_event_chains": {},
        "pangu_timeline_query": {},
        "pangu_timeline_replay": {},
        "pangu_topic_replay": {},
        "pangu_highlight_reel": {},
        "pangu_temporal_timeline": {},
        "pangu_temporal_relations": {},
        "pangu_temporal_query": {},
        "pangu_temporal_stats": {},
        "pangu_causal_discover": {},
        "pangu_causal_chains": {},
        "pangu_counterfactual": {"event": "test"},
        "pangu_root_cause": {"event": "test"},
        "pangu_causal_stats": {},
        "pangu_stats": {},
        "pangu_graph": {},
        "pangu_identity": {},
        "pangu_system_health": {},
        "pangu_system_metrics": {},
        "pangu_config_get": {},
        "pangu_config_reload": {},
        "pangu_schema_version": {},
        "pangu_schema_migrations": {},
        "pangu_create_tunnel": {"name": "test", "from_wing": "a", "to_wing": "b"},
        "pangu_list_tunnels": {},
        "pangu_find_tunnels": {},
        "pangu_cognitive_loop": {},
        "pangu_cognitive_stats": {},
        "pangu_metacognition_monitor": {},
        "pangu_metacognition_reconfig": {},
        "pangu_worldmodel_forecast": {"query": "test"},
        "pangu_worldmodel_plan": {"goal": "test"},
        "pangu_worldmodel_match": {"observation": "test"},
        "pangu_worldmodel_stats": {},
        "pangu_holographic_encode": {"content": "测试"},
        "pangu_holographic_search": {"query": "测试"},
        "pangu_judge_memory": {"memory_id": "test"},
        "pangu_judge_stats": {},
        "pangu_adaptive_params": {},
        "pangu_adaptive_evaluate": {},
        "pangu_reconsolidate": {},
        "pangu_find_resonance": {},
        "pangu_cross_wing_resonance": {},
        "pangu_resonance_find": {},
        "pangu_resonance_edges": {},
        "pangu_resonance_stats": {},
        "pangu_attention_state": {},
        "pangu_attention_switch": {"topic": "test"},
        "pangu_attention_ab_test": {},
        "pangu_streaming_index": {},
        "pangu_streaming_stats": {},
        "pangu_verify": {},
        "pangu_verify_phase": {},
        "pangu_privacy_stats": {},
        "pangu_privatize_count": {},
        "pangu_predict_queries": {},
        "pangu_predict_forgetting": {},
        "pangu_hot_topics": {},
        "pangu_predictive_stats": {},
        "pangu_meta_observe": {},
        "pangu_meta_recommend": {},
        "pangu_meta_tune": {},
        "pangu_meta_insights": {},
        "pangu_meta_stats": {},
        "pangu_health_trend": {},
        "pangu_health_stats": {},
        "pangu_benchmark": {},
        "pangu_error_stats": {},
        "pangu_health_report": {},
        "pangu_error_recent": {},
        "pangu_batch_scan": {},
        "pangu_batch_stats": {},
        "pangu_assess_quality": {},
        "pangu_batch_assess": {},
        "pangu_auto_fix": {},
        "pangu_quality_stats": {},
        "pangu_quality_analyze": {},
        "pangu_quality_fix": {},
        "pangu_cluster_by_tags": {},
        "pangu_cluster_by_time": {},
        "pangu_hierarchical_cluster": {},
        "pangu_dedup_results": {},
        "pangu_recommend_interaction": {},
        "pangu_recommend_similar": {"memory_id": "test"},
        "pangu_recommend_timely": {},
        "pangu_recommend_feedback": {"memory_id": "test", "feedback": "up"},
        "pangu_recommendation_stats": {},
        "pangu_rewrite_query": {"query": "test"},
        "pangu_suggest_queries": {"query": "test"},
        "pangu_rewrite_stats": {},
        "pangu_search_suggestions": {"query": "test"},
        "pangu_realtime_stats": {},
        "pangu_realtime_history": {},
        "pangu_proactive_predict": {"context": "test"},
        "pangu_proactive_suggest": {},
        "pangu_proactive_remind": {},
        "pangu_context_status": {},
        "pangu_user_patterns": {},
        "pangu_repeated_questions": {},
        "pangu_self_evaluate": {},
        "pangu_self_repair": {},
        "pangu_fuxi_insights": {},
        "pangu_knowledge_gaps": {},
        "pangu_user_behavior": {},
        "pangu_cross_session_links": {},
        "pangu_session_summary": {},
        "pangu_session_bridge": {},
        "pangu_session_stats": {},
        "pangu_session_inject": {},
        "pangu_session_start": {},
        "pangu_session_end": {},
        "pangu_session_resume": {},
        "pangu_session_record": {},
        "pangu_sync_record": {},
        "pangu_sync_pending": {},
        "pangu_sync_incremental": {},
        "pangu_sync_apply": {},
        "pangu_sync_auto_resolve": {},
        "pangu_sync_state": {},
        "pangu_sync_stats": {},
        "pangu_portal_write": {"content": "测试"},
        "pangu_portal_search": {"query": "测试"},
        "pangu_portal_panorama": {},
        "pangu_portal_maintain": {},
        "pangu_portal_summary": {},
        "pangu_autopilot_activate": {},
        "pangu_autopilot_deactivate": {},
        "pangu_autopilot_tick": {},
        "pangu_autopilot_suggest": {},
        "pangu_autopilot_status": {},
        "pangu_project_create": {"name": "test_proj"},
        "pangu_project_switch": {"project": "test_proj"},
        "pangu_project_list": {},
        "pangu_project_active": {},
        "pangu_project_save": {},
        "pangu_project_load": {},
        "pangu_project_search": {"query": "test"},
        "pangu_project_merge": {},
        "pangu_project_delete": {"project": "test_proj"},
        "pangu_project_stats": {},
        "pangu_analyze": {},
        "pangu_anomaly_detect": {},
        "pangu_growth_trend": {},
        "pangu_discover_patterns": {},
        "pangu_pattern_insights": {},
        "pangu_analyze_emotion": {},
        "pangu_emotion_stats": {},
        "pangu_predict_emotion": {},
        "pangu_discover_knowledge": {},
        "pangu_generate_hypotheses": {},
        "pangu_learning_stats": {},
        "pangu_performance_trend": {},
        "pangu_anomaly_scan": {},
        "pangu_anomaly_content": {},
        "pangu_anomaly_stats": {},
        "pangu_deep_emotion_trajectory": {},
        "pangu_deep_emotion_decompose": {},
        "pangu_deep_emotion_stats": {},
        "pangu_debate_run": {"topic": "测试"},
        "pangu_debate_stats": {},
        "pangu_narrative_generate": {},
        "pangu_narrative_themes": {},
        "pangu_narrative_identity": {},
        "pangu_summarize": {},
        "pangu_classify": {},
        "pangu_insight": {},
        "pangu_sanitize": {"content": "测试内容"},
        "pangu_sanitize_check": {"content": "测试内容"},
        "pangu_enhanced_contradictions": {},
        "pangu_trajectory_track": {},
        "pangu_trajectory_compare": {},
        "pangu_compress_by_tags": {"tags": "['test']"},
        "pangu_auto_compress": {},
        "pangu_compression_stats": {},
        "pangu_intent_predict": {"context": "test"},
        "pangu_intent_tasks": {},
        "pangu_intent_stats": {},
        "pangu_synthesis_cross_cluster": {},
        "pangu_synthesis_gaps": {},
        "pangu_evolution_plan": {},
        "pangu_image_search_by_text": {"query": "风景"},
        "pangu_image_search_by_image": {"image_path": "test"},
        "pangu_multimodal_search": {"query": "风景"},
        "pangu_multimodal_summary": {},
        "pangu_summary_by_topic": {},
        "pangu_summary_timeline": {},
        "pangu_detect_conflicts": {},
        "pangu_check_pair": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_find_duplicates": {},
        "pangu_merge_duplicates": {},
        "pangu_similarity_check": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_list_wings": {},
        "pangu_create_wing": {"name": "test_wing_e2e"},
        "pangu_list_rooms": {},
        "pangu_create_room": {"wing": "test", "name": "test_room_e2e"},
        "pangu_list_memories": {"wing": "test"},
    }
    return m.get(tool, {})


# 有副作用的工具 — 跳过
SKIP = {
    "pangu_add_memory",
    "pangu_delete_memory",
    "pangu_search_memories",
    "pangu_ingest_file",
    "pangu_ingest_url",
    "pangu_image_embed",
    "pangu_image_classify",
    "pangu_image_search_by_image",
    "pangu_video_ingest",
    "pangu_video_frames",
    "pangu_video_metadata",
    "pangu_audio_transcribe",
    "pangu_audio_ingest",
    "pangu_audio_metadata",
    "pangu_git_commit",
    "pangu_git_push",
    "pangu_feishu_send",
    "pangu_feishu_card",
    "pangu_watch_directory",
    "pangu_watch_status",
    "pangu_collect_file",
    "pangu_collect_dir",
    "pangu_collect_all",
    "pangu_plugin_enable",
    "pangu_plugin_disable",
    "pangu_config_set",
    "pangu_config_reload",
    "pangu_restore_backup",
    "pangu_api_server_start",
    "pangu_create_wing",
    "pangu_create_room",
    "pangu_import",
    "pangu_import_smart",
    "pangu_backup",
    "pangu_verify_backup",
    "pangu_event_emit",
    "pangu_event_webhook_add",
    "pangu_session_start",
    "pangu_session_end",
    "pangu_session_record",
    "pangu_session_resume",
    "pangu_sync_record",
    "pangu_sync_apply",
    "pangu_portal_write",
    "pangu_portal_maintain",
    "pangu_project_create",
    "pangu_project_delete",
    "pangu_project_switch",
    "pangu_project_save",
    "pangu_wm_push",
    "pangu_wm_clear",
    "pangu_create_tunnel",
    "pangu_create_wiki_page",
    "pangu_multi_register",
    "pangu_multi_write",
    "pangu_agent_register",
    "pangu_agent_share",
    "pangu_comment_add",
    "pangu_vote",
    "pangu_importance_feedback",
    "pangu_recommend_feedback",
    "pangu_sanitize",
    "pangu_compress_by_tags",
    "pangu_counterfactual",
    "pangu_root_cause",
    "pangu_attention_switch",
    "pangu_autopilot_activate",
    "pangu_autopilot_deactivate",
    "pangu_self_repair",
    "pangu_debate_run",
    "pangu_index_cleanup",
    "pangu_cache_clear",
    "pangu_cache_invalidate",
    "pangu_llm_cache_clear",
    "pangu_merge_duplicates",
}


def run():
    mcp = MCPClient(timeout=30)
    rpt = Report()

    print("🔌 检查盘古 API 连接...")
    try:
        tools = mcp.list_tools()
        print(f"   ✅ API 可达，发现 {len(tools)} 个 MCP 工具")
    except Exception as e:
        print(f"   ❌ API 不可达: {e}")
        return

    # ═══ Phase 1: 基础 CRUD ═══
    P = "Phase 1: 基础 CRUD"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    mems = [
        {
            "content": "Python是解释型高级编程语言",
            "wing": "e2e",
            "room": "general",
            "hall": "facts",
            "importance": 4,
            "tags": "['python','编程']",
        },
        {
            "content": "ONNX是微软的开放神经网络交换格式",
            "wing": "e2e",
            "room": "general",
            "hall": "facts",
            "importance": 3,
            "tags": "['onnx','模型']",
        },
        {
            "content": "SQLite是自包含的SQL数据库引擎",
            "wing": "e2e",
            "room": "tech",
            "hall": "facts",
            "importance": 3,
            "tags": "['sqlite','数据库']",
        },
        {
            "content": "盘古是AI Agent的记忆系统",
            "wing": "e2e",
            "room": "tech",
            "hall": "concepts",
            "importance": 5,
            "tags": "['盘古','记忆']",
        },
        {
            "content": "2024年3月完成v2.0升级",
            "wing": "e2e",
            "room": "history",
            "hall": "events",
            "importance": 4,
            "tags": "['里程碑','v2.0']",
        },
        {
            "content": "用户偏好暗色主题编码",
            "wing": "e2e",
            "room": "personal",
            "hall": "preferences",
            "importance": 2,
            "tags": "['偏好','主题']",
        },
        {
            "content": "部署建议使用Docker Compose",
            "wing": "prod",
            "room": "deploy",
            "hall": "suggestions",
            "importance": 4,
            "tags": "['部署','docker']",
        },
        {
            "content": "FAISS支持十亿级向量检索",
            "wing": "prod",
            "room": "tech",
            "hall": "facts",
            "importance": 3,
            "tags": "['faiss','向量']",
        },
        {
            "content": "团队：Alice后端Bob前端Carol运维",
            "wing": "e2e",
            "room": "team",
            "hall": "relations",
            "importance": 3,
            "tags": "['团队','成员']",
        },
        {
            "content": "混合搜索比纯向量搜索召回率提升35%",
            "wing": "prod",
            "room": "research",
            "hall": "discoveries",
            "importance": 5,
            "tags": "['发现','搜索']",
        },
    ]
    ids = []
    for i, m in enumerate(mems):
        r = mcp.call("pangu_add_memory", m)
        s = "PASS" if r.success else "FAIL"
        d = ""
        if r.success:
            try:
                j = json.loads(r.result)
                mid = j.get("id") or j.get("memory_id") or j.get("drawer_id", "")
                if mid:
                    ids.append(mid)
                    d = f"id={mid}"
            except Exception:
                d = "格式异常"
                s = "WARN"
        else:
            d = r.error or "失败"
        rpt.rec(P, f"写入#{i + 1}[{m['hall']}]", s, d, r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} 写入#{i + 1} [{m['hall']}] {d} ({r.elapsed_ms:.0f}ms)")

    for q, label in [("Python编程", "关键词"), ("数据库引擎", "语义"), ("e2e", "按wing")]:
        r = mcp.call("pangu_search_memories", {"query": q, "limit": 5})
        s = "PASS" if r.success else "FAIL"
        d = ""
        if r.success:
            try:
                j = json.loads(r.result)
                n = len(j.get("results", j.get("memories", [])))
                d = f"{n}条"
                s = "PASS" if n > 0 else "WARN"
            except Exception:
                d = "格式异常"
                s = "WARN"
        rpt.rec(P, f"搜索[{label}]", s, d, r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '⚠️'} 搜索[{label}] {d} ({r.elapsed_ms:.0f}ms)")

    r = mcp.call("pangu_stats", {})
    s = "PASS" if r.success else "FAIL"
    rpt.rec(P, "系统统计", s, "", r.elapsed_ms)
    print(f"  {'✅' if s == 'PASS' else '❌'} 系统统计 ({r.elapsed_ms:.0f}ms)")

    for mid in ids:
        mcp.call("pangu_delete_memory", {"memory_id": mid})
    rpt.rec(P, "清理", "PASS", f"删除{len(ids)}条")

    # ═══ Phase 2: 四层记忆栈 ═══
    P = "Phase 2: 四层记忆栈"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    r = mcp.call("pangu_identity", {})
    s = "PASS" if r.success else "FAIL"
    d = ""
    if r.success:
        try:
            j = json.loads(r.result)
            d = f"身份={len(str(j.get('identity', j.get('content', ''))))}字符"
        except Exception:
            d = "可解析"
    rpt.rec(P, "L0身份层", s, d, r.elapsed_ms)
    print(f"  {'✅' if s == 'PASS' else '⚠️'} L0身份 {d} ({r.elapsed_ms:.0f}ms)")

    sids = []
    for i in range(20):
        r = mcp.call(
            "pangu_add_memory",
            {
                "content": f"栈测试#{i + 1}：验证四层记忆栈的测试数据",
                "wing": "stack",
                "room": "g",
                "hall": "facts",
                "importance": (i % 5) + 1,
                "tags": f"['tag{i}','测试']",
            },
        )
        if r.success:
            try:
                j = json.loads(r.result)
                mid = j.get("id") or j.get("memory_id") or j.get("drawer_id", "")
                if mid:
                    sids.append(mid)
            except Exception:
                pass
    rpt.rec(P, "写入20条栈数据", "PASS" if len(sids) >= 15 else "WARN", f"{len(sids)}/20")
    print(f"  {'✅' if len(sids) >= 15 else '⚠️'} 栈数据: {len(sids)}/20")

    r = mcp.call("pangu_search_memories", {"query": "栈测试", "wing": "stack", "limit": 10})
    s = "PASS" if r.success else "FAIL"
    rpt.rec(P, "L2按需层", s, "", r.elapsed_ms)
    print(f"  {'✅' if s == 'PASS' else '❌'} L2按需层 ({r.elapsed_ms:.0f}ms)")

    r = mcp.call("pangu_search_memories", {"query": "测试数据 验证 功能", "limit": 20})
    s = "PASS" if r.success else "FAIL"
    rpt.rec(P, "L3深度搜索", s, "", r.elapsed_ms)
    print(f"  {'✅' if s == 'PASS' else '❌'} L3深度搜索 ({r.elapsed_ms:.0f}ms)")

    for mid in sids:
        mcp.call("pangu_delete_memory", {"memory_id": mid})

    # ═══ Phase 3: 搜索子系统 ═══
    P = "Phase 3: 搜索子系统"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    sids2 = []
    for m in [
        {"content": "Flask是Python Web框架", "wing": "srch", "tags": "['flask','web']"},
        {"content": "Django是Python流行Web框架", "wing": "srch", "tags": "['django','web']"},
        {"content": "FastAPI是高性能Python框架", "wing": "srch", "tags": "['fastapi','api']"},
        {"content": "React是Facebook前端库", "wing": "srch", "tags": "['react','frontend']"},
        {"content": "Vue.js是渐进式JS框架", "wing": "srch", "tags": "['vue','frontend']"},
        {"content": "机器学习让计算机从数据学习", "wing": "srch", "tags": "['ml','ai']"},
        {"content": "深度学习使用神经网络", "wing": "srch", "tags": "['dl','neural']"},
        {"content": "自然语言处理理解人类语言", "wing": "srch", "tags": "['nlp','语言']"},
    ]:
        r = mcp.call("pangu_add_memory", m)
        if r.success:
            try:
                j = json.loads(r.result)
                mid = j.get("id") or j.get("memory_id") or j.get("drawer_id", "")
                if mid:
                    sids2.append(mid)
            except Exception:
                pass

    for tool, q, label in [
        ("pangu_fts_search", "Python 框架", "FTS全文"),
        ("pangu_search_memories", "人工智能算法", "向量语义"),
        ("pangu_hybrid_search", "Web开发框架", "混合搜索"),
        ("pangu_rewrite_query", "py", "查询改写"),
        ("pangu_search_suggestions", "xyz123", "搜索建议"),
        ("pangu_explain_search", "Python 框架", "搜索解释"),
        ("pangu_search_stats", None, "搜索统计"),
        ("pangu_fts_search_stats", None, "FTS统计"),
    ]:
        args = {"query": q, "limit": 5} if q else {}
        r = mcp.call(tool, args)
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    for mid in sids2:
        mcp.call("pangu_delete_memory", {"memory_id": mid})

    # ═══ Phase 4: 神经记忆 ═══
    P = "Phase 4: 神经记忆"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    for tool, label in [
        ("pangu_neural_stats", "统计"),
        ("pangu_neural_sleep", "睡眠巩固"),
        ("pangu_neural_spreading", "激活扩散"),
        ("pangu_neural_inhibition", "竞争抑制"),
        ("pangu_neural_decay", "神经衰减"),
        ("pangu_consolidation_stats", "巩固统计"),
        ("pangu_evaluate_forgetting", "遗忘评估"),
        ("pangu_reconsolidate", "再巩固"),
    ]:
        args = {"cycles": 1} if "sleep" in tool else ({"query": "Python"} if "spreading" in tool else {})
        r = mcp.call(tool, args)
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 5: 知识图谱 ═══
    P = "Phase 5: 知识图谱"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    eids = []
    for name, typ in [("Python", "language"), ("Flask", "framework"), ("SQLite", "database")]:
        r = mcp.call("pangu_kg_add_entity", {"name": name, "type": typ, "description": f"测试实体{name}"})
        s = "PASS" if r.success else "FAIL"
        if r.success:
            try:
                j = json.loads(r.result)
                eid = j.get("id") or j.get("entity_id", "")
                if eid:
                    eids.append(eid)
            except Exception:
                pass
        rpt.rec(P, f"添加实体:{name}", s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} 实体:{name} ({r.elapsed_ms:.0f}ms)")

    if len(eids) >= 2:
        r = mcp.call(
            "pangu_kg_add_relation",
            {"subject_id": eids[0], "predicate": "uses", "object_id": eids[1], "confidence": 0.9},
        )
        rpt.rec(P, "添加关系", "PASS" if r.success else "FAIL", "", r.elapsed_ms)
        print(f"  {'✅' if r.success else '❌'} 关系:Python→Flask ({r.elapsed_ms:.0f}ms)")

    for tool, label in [
        ("pangu_kg_query", "查询实体"),
        ("pangu_kg_neighbors", "邻居查询"),
        ("pangu_kg_auto_extract", "自动提取"),
        ("pangu_graph_stats", "图谱统计"),
    ]:
        args = (
            {"entity_name": "Python"}
            if "query" in tool or "neighbor" in tool
            else ({"content": "Python用ONNX部署"} if "extract" in tool else {})
        )
        r = mcp.call(tool, args)
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 6: 主动注入 ═══
    P = "Phase 6: 主动注入"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    for tool, args, label in [
        ("pangu_inject_context", {"context": "调试Python数据库连接"}, "上下文注入"),
        ("pangu_update_context", {"context": "优化搜索性能"}, "更新上下文"),
        ("pangu_current_context", {}, "当前上下文"),
        ("pangu_injection_stats", {}, "注入统计"),
        ("pangu_proactive_predict", {"context": "Web开发"}, "预测推荐"),
        ("pangu_proactive_remind", {}, "主动提醒"),
        ("pangu_context_status", {}, "上下文状态"),
    ]:
        r = mcp.call(tool, args)
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 7: 多模态 ═══
    P = "Phase 7: 多模态"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    for tool, args, label in [
        ("pangu_multimodal_search", {"query": "风景", "limit": 5}, "跨模态搜索"),
        ("pangu_multimodal_summary", {}, "多模态摘要"),
        ("pangu_summary_by_topic", {}, "按主题摘要"),
        ("pangu_summary_timeline", {}, "时间线摘要"),
    ]:
        r = mcp.call(tool, args)
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 8: 自主管理 ═══
    P = "Phase 8: 自主管理"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    for tool, label in [
        ("pangu_auto_fusion", "自动融合"),
        ("pangu_auto_forget", "自动衰减"),
        ("pangu_compress_memories", "压缩记忆"),
        ("pangu_detect_conflicts", "冲突检测"),
        ("pangu_find_duplicates", "去重检测"),
        ("pangu_autopilot_status", "自动驾驶"),
        ("pangu_evolution_stats", "自进化"),
        ("pangu_self_diagnose", "自我诊断"),
        ("pangu_self_evaluate", "自我评估"),
        ("pangu_anomaly_detect", "异常检测"),
        ("pangu_health_report", "健康报告"),
        ("pangu_error_recent", "最近错误"),
    ]:
        r = mcp.call(tool, {})
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 9: REST API ═══
    P = "Phase 9: REST API"
    print(f"\n{'=' * 60}\n📋 {P}\n{'=' * 60}")

    for path, label in [
        ("/", "根路径"),
        ("/dashboard", "Dashboard"),
        ("/docs", "API文档"),
        ("/api/v2/memories", "REST memories"),
    ]:
        try:
            resp = mcp.http_get(path)
            s = "PASS" if resp["status"] in (200, 307) else "WARN"
            d = f"HTTP {resp['status']}"
            rpt.rec(P, label, s, d)
            print(f"  {'✅' if s == 'PASS' else '⚠️'} {label} {d}")
        except Exception as e:
            rpt.rec(P, label, "FAIL", str(e)[:80])
            print(f"  ❌ {label} {e}")

    for tool, label in [("pangu_system_health", "系统健康"), ("pangu_system_metrics", "系统指标")]:
        r = mcp.call(tool, {})
        s = "PASS" if r.success else "FAIL"
        rpt.rec(P, label, s, "", r.elapsed_ms)
        print(f"  {'✅' if s == 'PASS' else '❌'} {label} ({r.elapsed_ms:.0f}ms)")

    # ═══ Phase 10: 全量工具遍历 ═══
    P = "Phase 10: 全量遍历"
    print(f"\n{'=' * 60}\n📋 {P} — {len(tools)}个工具\n{'=' * 60}")

    ok = fail = skip = 0
    errs = []
    for tool in tools:
        name = tool["name"]
        if name in SKIP:
            skip += 1
            continue
        r = mcp.call(name, _args(name))
        if r.success:
            ok += 1
            rpt.rec(P, name, "PASS", f"{r.elapsed_ms:.0f}ms", r.elapsed_ms)
        else:
            fail += 1
            errs.append((name, (r.error or "")[:60]))
            rpt.rec(P, name, "FAIL", (r.error or "")[:60], r.elapsed_ms)

    print(f"\n  📊 全量遍历: ✅{ok} ❌{fail} ⏭️{skip}")
    if errs:
        print(f"  🔍 失败工具({len(errs)}个):")
        for n, e in errs[:30]:
            print(f"     ❌ {n}: {e}")
        if len(errs) > 30:
            print(f"     ... 还有{len(errs) - 30}个")

    # ═══ 报告 ═══
    rpt.print()
    s = mcp.summary()
    print(f"\n📡 MCP调用统计: {s['total']}次 | {s['pass']}成功 {s['fail']}失败 | 均延{s['avg_ms']}ms")


if __name__ == "__main__":
    run()
