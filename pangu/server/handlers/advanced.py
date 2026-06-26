"""盘古 MCP Handler — advanced (121 tools)"""

import json
import time

from ...memory.adaptive_params import get_adaptive_engine
from ...memory.attention import AttentionStrategy, get_attention_system
from ...memory.differential_privacy import DifferentialPrivacy
from ...memory.fts_search import holographic_search
from ...memory.hologram import get_holographic_encoder
from ...memory.judge import get_memory_judge
from ...memory.reconsolidation import ReconsolidationEngine, ResonanceEngine
from ...memory.streaming_index import StreamingIndexer
from ...memory.verification import VerificationLoop
from ...memory.working_memory import WMItem, get_working_memory

TOOLS = [
    {"name": "pangu_create_tunnel", "description": "\u521b\u5efa\u8de8 Wing \u96a7\u9053"},
    {"name": "pangu_list_tunnels", "description": "\u5217\u51fa\u96a7\u9053"},
    {"name": "pangu_find_tunnels", "description": "\u67e5\u627e Wing \u95f4\u96a7\u9053"},
    {
        "name": "pangu_cognitive_loop",
        "description": "\u8fd0\u884c\u4e00\u6b21\u8ba4\u77e5\u5faa\u73af\uff08observe\u2192think\u2192evaluate\u2192act\uff09",
    },
    {"name": "pangu_cognitive_stats", "description": "\u83b7\u53d6\u8ba4\u77e5\u5faa\u73af\u7edf\u8ba1"},
    {
        "name": "pangu_metacognition_monitor",
        "description": "\u7cfb\u7edf\u7ea7\u5065\u5eb7\u76d1\u6d4b\uff08\u7b56\u7565\u8868\u73b0\u3001\u89c2\u5bdf\u6570\u636e\u3001\u5efa\u8bae\uff09",
    },
    {
        "name": "pangu_metacognition_reconfig",
        "description": "\u81ea\u91cd\u6784\u68c0\u6d4b\uff08\u4f4e\u6548\u7b56\u7565\u3001\u672a\u4f7f\u7528\u7b56\u7565\u3001\u5f02\u5e38\u6a21\u5757\uff09",
    },
    {
        "name": "pangu_worldmodel_forecast",
        "description": "\u57fa\u4e8e\u5f53\u524d\u72b6\u6001\u9884\u6d4b\u672a\u6765\u60c5\u666f",
    },
    {
        "name": "pangu_worldmodel_plan",
        "description": "\u4e3a\u6307\u5b9a\u60c5\u666f\u751f\u6210\u5e94\u5bf9\u8ba1\u5212",
    },
    {"name": "pangu_worldmodel_match", "description": "\u5c06\u4e8b\u4ef6\u4e0e\u9884\u6d4b\u60c5\u666f\u5339\u914d"},
    {"name": "pangu_worldmodel_stats", "description": "\u83b7\u53d6\u4e16\u754c\u6a21\u578b\u7edf\u8ba1"},
    {
        "name": "pangu_holographic_encode",
        "description": "\u5c06\u8bb0\u5fc6\u7f16\u7801\u4e3a\u5168\u606f\u6295\u5f71\uff085\u7ef4\uff09",
    },
    {"name": "pangu_holographic_search", "description": "\u5168\u606f\u8de8\u7ef4\u5ea6\u878d\u5408\u68c0\u7d22"},
    {
        "name": "pangu_judge_memory",
        "description": "LLM\u5224\u65ad\u8bb0\u5fc6\u4ef7\u503c(A/B/C\u4e09\u7ea7\u5206\u7c7b)",
    },
    {"name": "pangu_judge_stats", "description": "\u83b7\u53d6\u5224\u65ad\u7edf\u8ba1"},
    {"name": "pangu_adaptive_params", "description": "\u83b7\u53d6/\u8c03\u6574\u81ea\u9002\u5e94\u53c2\u6570"},
    {
        "name": "pangu_adaptive_evaluate",
        "description": "\u6839\u636e\u7cfb\u7edf\u7edf\u8ba1\u8bc4\u4f30\u5e76\u8c03\u6574\u53c2\u6570",
    },
    {"name": "pangu_wm_push", "description": "\u63a8\u5165\u5de5\u4f5c\u8bb0\u5fc6\u9879"},
    {"name": "pangu_wm_get", "description": "\u83b7\u53d6\u5de5\u4f5c\u8bb0\u5fc6\u9879"},
    {"name": "pangu_wm_stats", "description": "\u83b7\u53d6\u5de5\u4f5c\u8bb0\u5fc6\u7edf\u8ba1"},
    {"name": "pangu_wm_clear", "description": "\u6e05\u7a7a\u5de5\u4f5c\u8bb0\u5fc6"},
    {
        "name": "pangu_reconsolidate",
        "description": "\u518d\u5de9\u56fa\u8bb0\u5fc6\uff08\u5237\u65b0\u8870\u51cf\u5206\u6570\uff09",
    },
    {
        "name": "pangu_find_resonance",
        "description": "\u53d1\u73b0\u60c5\u611f/\u8bed\u4e49\u5171\u9e23\u7684\u8bb0\u5fc6\u5bf9",
    },
    {"name": "pangu_cross_wing_resonance", "description": "\u53d1\u73b0\u8de8Wing\u7684\u77e5\u8bc6\u5171\u9e23"},
    {"name": "pangu_attention_state", "description": "\u83b7\u53d6\u5f53\u524d\u6ce8\u610f\u529b\u72b6\u6001"},
    {"name": "pangu_attention_switch", "description": "\u5207\u6362\u6ce8\u610f\u529b\u7b56\u7565"},
    {"name": "pangu_attention_ab_test", "description": "\u542f\u52a8\u6ce8\u610f\u529b\u7b56\u7565A/B\u6d4b\u8bd5"},
    {"name": "pangu_streaming_index", "description": "\u589e\u91cf\u7d22\u5f15\u65b0\u8bb0\u5fc6"},
    {"name": "pangu_streaming_stats", "description": "\u83b7\u53d6\u6d41\u5f0f\u7d22\u5f15\u7edf\u8ba1"},
    {"name": "pangu_verify", "description": "\u8fd0\u884c\u5b8c\u6574\u9a8c\u8bc1\u5faa\u73af"},
    {"name": "pangu_verify_phase", "description": "\u8fd0\u884c\u5355\u4e2a\u9a8c\u8bc1\u9636\u6bb5"},
    {"name": "pangu_privacy_stats", "description": "\u83b7\u53d6\u9690\u79c1\u9884\u7b97\u7edf\u8ba1"},
    {"name": "pangu_privatize_count", "description": "\u9690\u79c1\u5316\u8ba1\u6570\u7ed3\u679c"},
    {
        "name": "pangu_autonomous_analyze",
        "description": "\u5206\u6790\u4efb\u52a1\u590d\u6742\u5ea6\u5e76\u63a8\u8350\u80fd\u529b",
    },
    {
        "name": "pangu_neural_stats",
        "description": "\u83b7\u53d6\u6d77\u9a6c\u4f53-\u65b0\u76ae\u5c42\u53cc\u7cfb\u7edf\u7edf\u8ba1",
    },
    {
        "name": "pangu_neural_sleep",
        "description": "\u89e6\u53d1\u795e\u7ecf\u7761\u7720\u5de9\u56fa\uff08\u6d77\u9a6c\u4f53\u2192\u65b0\u76ae\u5c42\u91cd\u64ad\uff09",
    },
    {
        "name": "pangu_neural_spreading",
        "description": "\u57fa\u4e8e\u79cd\u5b50\u8bb0\u5fc6\u6267\u884c\u6fc0\u6d3b\u6269\u6563\uff0c\u627e\u5230\u5173\u8054\u8bb0\u5fc6",
    },
    {
        "name": "pangu_neural_inhibition",
        "description": "\u5bf9\u4e00\u7ec4\u8bb0\u5fc6\u6267\u884c\u7ade\u4e89\u6291\u5236\uff0c\u8fd4\u56de\u6709\u6548\u6fc0\u6d3b\u503c",
    },
    {
        "name": "pangu_neural_decay",
        "description": "\u5bf9\u6240\u6709\u795e\u7ecf\u8bb0\u5fc6\u5e94\u7528\u4e2a\u6027\u5316\u8870\u51cf",
    },
    {"name": "pangu_multi_register", "description": "\u6ce8\u518cAgent\u5230\u534f\u4f5c\u8bb0\u5fc6\u7a7a\u95f4"},
    {"name": "pangu_multi_write", "description": "\u5199\u5165\u591aAgent\u5171\u4eab\u8bb0\u5fc6"},
    {"name": "pangu_multi_read", "description": "\u8bfb\u53d6Agent\u53ef\u89c1\u7684\u8bb0\u5fc6"},
    {"name": "pangu_multi_agents", "description": "\u83b7\u53d6\u6240\u6709\u5df2\u6ce8\u518cAgent"},
    {"name": "pangu_generate_ideas", "description": "\u57fa\u4e8e\u8bb0\u5fc6\u751f\u6210\u65b0\u60f3\u6cd5"},
    {"name": "pangu_generate_novel", "description": "\u751f\u6210\u539f\u521b\u60f3\u6cd5"},
    {"name": "pangu_agent_register", "description": "\u6ce8\u518c Agent"},
    {"name": "pangu_agent_share", "description": "Agent \u95f4\u5171\u4eab\u77e5\u8bc6"},
    {"name": "pangu_collaborative_reason", "description": "\u534f\u4f5c\u63a8\u7406"},
    {"name": "pangu_agent_stats", "description": "\u83b7\u53d6 Agent \u7edf\u8ba1"},
    {"name": "pangu_synthesize", "description": "\u6309\u4e3b\u9898\u7efc\u5408\u77e5\u8bc6"},
    {"name": "pangu_find_contradictions", "description": "\u68c0\u6d4b\u77db\u76fe\u4fe1\u606f"},
    {"name": "pangu_core_insights", "description": "\u63d0\u53d6\u6838\u5fc3\u6d1e\u5bdf"},
    {"name": "pangu_auto_learn", "description": "\u6267\u884c\u81ea\u4e3b\u5b66\u4e60\u5faa\u73af"},
    {"name": "pangu_arch_analyze", "description": "\u5206\u6790\u8bb0\u5fc6\u67b6\u6784"},
    {"name": "pangu_arch_suggest", "description": "\u67b6\u6784\u91cd\u6784\u5efa\u8bae"},
    {"name": "pangu_cold_hot", "description": "\u51b7\u70ed\u5206\u79bb\u5efa\u8bae"},
    {"name": "pangu_arch_stats", "description": "\u67b6\u6784\u7edf\u8ba1"},
    {"name": "pangu_qa", "description": "\u57fa\u4e8e\u8bb0\u5fc6\u7684\u667a\u80fd\u95ee\u7b54"},
    {"name": "pangu_qa_batch", "description": "\u6279\u91cf\u667a\u80fd\u95ee\u7b54"},
    {"name": "pangu_qa_stats", "description": "\u95ee\u7b54\u7edf\u8ba1"},
    {
        "name": "pangu_inject_context",
        "description": "\u4e3a\u6587\u672c\u6ce8\u5165\u76f8\u5173\u8bb0\u5fc6\u4e0a\u4e0b\u6587",
    },
    {"name": "pangu_update_context", "description": "\u589e\u91cf\u66f4\u65b0\u4e0a\u4e0b\u6587"},
    {"name": "pangu_current_context", "description": "\u83b7\u53d6\u5f53\u524d\u4e0a\u4e0b\u6587\u7f13\u51b2"},
    {"name": "pangu_injection_stats", "description": "\u4e0a\u4e0b\u6587\u6ce8\u5165\u7edf\u8ba1"},
    {
        "name": "pangu_evaluate_forgetting",
        "description": "\u8bc4\u4f30\u6240\u6709\u8bb0\u5fc6\u7684\u9057\u5fd8\u4ef7\u503c",
    },
    {
        "name": "pangu_auto_forget",
        "description": "\u81ea\u52a8\u6267\u884c\u9057\u5fd8\uff08\u5f52\u6863+\u6e05\u7406\uff09",
    },
    {"name": "pangu_get_archive", "description": "\u83b7\u53d6\u5f52\u6863\u8bb0\u5fc6"},
    {"name": "pangu_consolidate", "description": "\u6267\u884c\u667a\u80fd\u8bb0\u5fc6\u5de9\u56fa"},
    {"name": "pangu_merge_candidates", "description": "\u67e5\u627e\u53ef\u5408\u5e76\u8bb0\u5fc6"},
    {"name": "pangu_resolve_conflicts", "description": "\u53d1\u73b0\u5e76\u89e3\u51b3\u77db\u76fe\u8bb0\u5fc6"},
    {"name": "pangu_extract_keywords", "description": "\u63d0\u53d6\u5173\u952e\u8bcd"},
    {"name": "pangu_build_graph", "description": "\u4ece\u8bb0\u5fc6\u6784\u5efa\u77e5\u8bc6\u56fe\u8c31"},
    {"name": "pangu_verify_backup", "description": "\u9a8c\u8bc1\u5907\u4efd\u5b8c\u6574\u6027"},
    {"name": "pangu_event_emit", "description": "\u53d1\u5e03\u8bb0\u5fc6\u4e8b\u4ef6"},
    {"name": "pangu_event_history", "description": "\u67e5\u8be2\u4e8b\u4ef6\u5386\u53f2"},
    {"name": "pangu_event_stats", "description": "\u4e8b\u4ef6\u7edf\u8ba1"},
    {"name": "pangu_event_webhook_add", "description": "\u6dfb\u52a0 Webhook"},
    {"name": "pangu_event_save", "description": "\u6301\u4e45\u5316\u4e8b\u4ef6\u5386\u53f2"},
    {"name": "pangu_index_build", "description": "\u6784\u5efa\u6240\u6709\u7d22\u5f15"},
    {"name": "pangu_index_search", "description": "\u901a\u8fc7\u7d22\u5f15\u641c\u7d22"},
    {"name": "pangu_index_recommend", "description": "\u7d22\u5f15\u63a8\u8350"},
    {"name": "pangu_index_health", "description": "\u7d22\u5f15\u5065\u5eb7\u68c0\u67e5"},
    {"name": "pangu_index_cleanup", "description": "\u6e05\u7406\u65e0\u6548\u7d22\u5f15"},
    {"name": "pangu_cache_stats", "description": "\u7f13\u5b58\u7edf\u8ba1"},
    {"name": "pangu_cache_cleanup", "description": "\u6e05\u7406\u8fc7\u671f\u7f13\u5b58"},
    {"name": "pangu_cache_invalidate", "description": "\u5931\u6548\u7f13\u5b58"},
    {"name": "pangu_diff_content", "description": "\u5bf9\u6bd4\u4e24\u6bb5\u5185\u5bb9\u5dee\u5f02"},
    {"name": "pangu_diff_batch", "description": "\u6279\u91cf\u5dee\u5f02\u5bf9\u6bd4"},
    {"name": "pangu_diff_similarity", "description": "\u8ba1\u7b97\u8bb0\u5fc6\u76f8\u4f3c\u5ea6\u77e9\u9635"},
    {"name": "pangu_diff_stats", "description": "\u5dee\u5f02\u7edf\u8ba1"},
    {"name": "pangu_visualize_graph", "description": "\u53ef\u89c6\u5316\u77e5\u8bc6\u56fe\u8c31"},
    {"name": "pangu_visualize_network", "description": "\u53ef\u89c6\u5316\u8bb0\u5fc6\u7f51\u7edc"},
    {"name": "pangu_visualize_stats", "description": "\u53ef\u89c6\u5316\u7edf\u8ba1\u4fe1\u606f"},
    {"name": "pangu_detect_patterns", "description": "\u68c0\u6d4b\u7528\u6237\u884c\u4e3a\u6a21\u5f0f"},
    {"name": "pangu_popular_queries", "description": "\u83b7\u53d6\u70ed\u95e8\u67e5\u8be2"},
    {"name": "pangu_frequent_memories", "description": "\u83b7\u53d6\u9891\u7e41\u8bbf\u95ee\u7684\u8bb0\u5fc6"},
    {"name": "pangu_comment_add", "description": "\u6dfb\u52a0\u8bb0\u5fc6\u8bc4\u8bba"},
    {"name": "pangu_comment_list", "description": "\u83b7\u53d6\u8bb0\u5fc6\u8bc4\u8bba\u5217\u8868"},
    {"name": "pangu_vote", "description": "\u5bf9\u8bb0\u5fc6\u6295\u7968"},
    {"name": "pangu_vote_stats", "description": "\u83b7\u53d6\u8bb0\u5fc6\u6295\u7968\u7edf\u8ba1"},
    {
        "name": "pangu_dream_cycle",
        "description": "\u8fd0\u884c\u4e00\u6b21\u68a6\u5883\u5de9\u56fa\u5468\u671f\uff08fetch\u2192dedup\u2192link\u2192decay\u2192distill\uff09",
    },
    {"name": "pangu_dream_stats", "description": "\u83b7\u53d6\u68a6\u5883\u5de9\u56fa\u7edf\u8ba1"},
    {
        "name": "pangu_curiosity_explore",
        "description": "\u8fd0\u884c\u597d\u5947\u5fc3\u63a2\u7d22\uff08\u53d1\u73b0\u77e5\u8bc6\u7a7a\u767d\uff09",
    },
    {
        "name": "pangu_curiosity_gaps",
        "description": "\u53d1\u73b0\u77e5\u8bc6\u7a7a\u767d\u5e76\u751f\u6210\u63a2\u7d22\u5efa\u8bae",
    },
    {
        "name": "pangu_persona_identity",
        "description": "\u83b7\u53d6\u7cfb\u7edf\u8eab\u4efd\u548c\u4eba\u683c\u7279\u8d28",
    },
    {"name": "pangu_persona_values", "description": "\u83b7\u53d6\u7cfb\u7edf\u4ef7\u503c\u89c2\u548c\u539f\u5219"},
    {"name": "pangu_persona_health", "description": "\u7cfb\u7edf\u7efc\u5408\u5065\u5eb7\u5ea6\u68c0\u67e5"},
    {
        "name": "pangu_autonomous_tick",
        "description": "\u68c0\u67e5\u662f\u5426\u9700\u8981\u8fd0\u884c\u81ea\u4e3b\u7ef4\u62a4\u5468\u671f",
    },
    {
        "name": "pangu_autonomous_run",
        "description": "\u8fd0\u884c\u4e00\u6b21\u81ea\u4e3b\u8bb0\u5fc6\u7ba1\u7406\u5468\u671f\uff08\u878d\u5408/\u538b\u7f29/\u8870\u51cf/\u9057\u5fd8/\u63a2\u7d22\uff09",
    },
    {
        "name": "pangu_autonomous_status",
        "description": "\u67e5\u770b\u81ea\u4e3b\u5f15\u64ce\u72b6\u6001\u548c\u4efb\u52a1\u8c03\u5ea6",
    },
    {
        "name": "pangu_agent_activity",
        "description": "\u67e5\u770bAgent\u6d3b\u52a8\u6d41\uff08\u8bfb\u5199\u8bb0\u5f55\uff09",
    },
    {
        "name": "pangu_agent_search",
        "description": "Agent\u611f\u77e5\u641c\u7d22\uff08\u4ec5\u641c\u7d22\u8be5Agent\u53ef\u89c1\u7684\u8bb0\u5fc6\uff09",
    },
    {"name": "pangu_agent_transfer", "description": "\u8de8Agent\u8bb0\u5fc6\u8f6c\u79fb"},
    {"name": "pangu_git_commit", "description": "\u8bb0\u5f55\u6700\u8fd1\u4e00\u6b21 git commit \u5230\u8bb0\u5fc6"},
    {"name": "pangu_git_push", "description": "\u8bb0\u5f55 git push \u64cd\u4f5c"},
    {"name": "pangu_git_recent", "description": "\u67e5\u770b\u6700\u8fd1\u7684 git \u64cd\u4f5c\u8bb0\u5f55"},
    {"name": "pangu_git_stats", "description": "\u67e5\u770b git \u64cd\u4f5c\u7edf\u8ba1"},
    {"name": "pangu_inject_stats", "description": "\u67e5\u770b\u6ce8\u5165\u7edf\u8ba1"},
    {"name": "pangu_cache_stats", "description": "\u67e5\u770b\u641c\u7d22\u7f13\u5b58\u7edf\u8ba1"},
    {"name": "pangu_cache_clear", "description": "\u6e05\u7a7a\u641c\u7d22\u7f13\u5b58"},
    {"name": "pangu_error_recent", "description": "\u67e5\u770b\u6700\u8fd1\u7684\u9519\u8bef\u65e5\u5fd7"},
]

HANDLERS = {}


async def handle_create_tunnel(server, drawers, arguments):
    """创建跨 Wing 隧道"""
    tunnel = server.palace.create_tunnel(
        wing_a=arguments.get("wing_a", ""),
        wing_b=arguments.get("wing_b", ""),
        room=arguments.get("room", ""),
    )
    return json.dumps(tunnel, ensure_ascii=False)


HANDLERS["pangu_create_tunnel"] = handle_create_tunnel


async def handle_list_tunnels(server, drawers, arguments):
    """列出隧道"""
    return json.dumps(server.palace.list_tunnels(), ensure_ascii=False, indent=2)


HANDLERS["pangu_list_tunnels"] = handle_list_tunnels


async def handle_find_tunnels(server, drawers, arguments):
    """查找 Wing 间隧道"""
    tunnels = server.palace.find_tunnels(
        wing_a=arguments.get("wing_a", ""),
        wing_b=arguments.get("wing_b", ""),
    )
    return json.dumps(tunnels, ensure_ascii=False, indent=2)


HANDLERS["pangu_find_tunnels"] = handle_find_tunnels


async def handle_cognitive_loop(server, drawers, arguments):
    """运行一次认知循环（observe→think→evaluate→act）"""
    from ...memory.cognitive_loop import get_cognitive_loop

    loop = get_cognitive_loop(server.config)
    result = loop.run_cycle()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_cognitive_loop"] = handle_cognitive_loop


async def handle_cognitive_stats(server, drawers, arguments):
    """获取认知循环统计"""
    from ...memory.cognitive_loop import get_cognitive_loop

    loop = get_cognitive_loop(server.config)
    return json.dumps(loop.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_cognitive_stats"] = handle_cognitive_stats


async def handle_metacognition_monitor(server, drawers, arguments):
    """系统级健康监测（策略表现、观察数据、建议）"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    return json.dumps(ml.monitor_system_health(), ensure_ascii=False, indent=2)


HANDLERS["pangu_metacognition_monitor"] = handle_metacognition_monitor


async def handle_metacognition_reconfig(server, drawers, arguments):
    """自重构检测（低效策略、未使用策略、异常模块）"""
    from ...memory.meta_learning import get_meta_engine

    ml = get_meta_engine(server.config)
    return json.dumps(ml.detect_self_reconfig(), ensure_ascii=False, indent=2)


HANDLERS["pangu_metacognition_reconfig"] = handle_metacognition_reconfig


async def handle_worldmodel_forecast(server, drawers, arguments):
    """基于当前状态预测未来情景"""
    from ...memory.world_model import TOP_SCENARIOS, get_world_model

    wm_model = get_world_model(server.config)
    scenarios = wm_model.forecast()
    return json.dumps(
        {
            "scenarios_count": len(scenarios),
            "scenarios": [
                {
                    "id": s.id,
                    "trigger": s.trigger,
                    "description": s.description,
                    "probability": round(s.probability, 3),
                    "severity": round(s.severity, 3),
                    "causal_depth": len(s.causal_path),
                    "impact": s.estimated_impact,
                    "actions": s.suggested_actions,
                }
                for s in scenarios[:TOP_SCENARIOS]
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_worldmodel_forecast"] = handle_worldmodel_forecast


async def handle_worldmodel_plan(server, drawers, arguments):
    """为指定情景生成应对计划"""
    from ...memory.world_model import get_world_model

    wm_model = get_world_model(server.config)
    scenario_id = arguments.get("scenario_id", "")
    scenarios = wm_model.forecast()
    target = next((s for s in scenarios if s.id == scenario_id), None)
    if not target:
        return json.dumps({"error": f"scenario not found: {scenario_id}"})
    plan = wm_model.generate_plan(target)
    return json.dumps(
        {
            "scenario_id": plan.scenario_id,
            "description": plan.description,
            "actions": plan.suggested_actions,
            "estimated_effect": plan.estimated_effect,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_worldmodel_plan"] = handle_worldmodel_plan


async def handle_worldmodel_match(server, drawers, arguments):
    """将事件与预测情景匹配"""
    from ...memory.world_model import get_world_model

    wm_model = get_world_model(server.config)
    event_type = arguments.get("event_type", "")
    event_data = arguments.get("event_data", {})
    matched = wm_model.match_event(event_type, event_data)
    if matched:
        return json.dumps(
            {
                "matched": True,
                "scenario_id": matched.id,
                "trigger": matched.trigger,
                "probability": round(matched.probability, 3),
                "actions": matched.suggested_actions,
            },
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps({"matched": False})


HANDLERS["pangu_worldmodel_match"] = handle_worldmodel_match


async def handle_worldmodel_stats(server, drawers, arguments):
    """获取世界模型统计"""
    from ...memory.world_model import get_world_model

    wm_model = get_world_model(server.config)
    return json.dumps(wm_model.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_worldmodel_stats"] = handle_worldmodel_stats


async def handle_holographic_encode(server, drawers, arguments):
    """将记忆编码为全息投影（5维）"""
    encoder = get_holographic_encoder(server.config)
    holo = encoder.encode(
        item_id=arguments.get("item_id", f"holo_{int(time.time())}"),
        raw_text=arguments.get("raw_text", ""),
        created_at=arguments.get("created_at", ""),
        wing=arguments.get("wing", ""),
        room=arguments.get("room", ""),
        causal_summary=arguments.get("causal_summary", ""),
        source_type=arguments.get("source_type", ""),
        agent_id=arguments.get("agent_id", ""),
    )
    return json.dumps(
        {
            "item_id": holo.item_id,
            "dimensions": holo.all_dims(),
            "byte_size": holo.byte_size,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_holographic_encode"] = handle_holographic_encode


async def handle_holographic_search(server, drawers, arguments):
    """全息跨维度融合检索"""
    result = holographic_search(
        query=arguments.get("query", ""),
        drawers=drawers,
        weights=arguments.get("weights"),
        top_k=arguments.get("top_k", 10),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_holographic_search"] = handle_holographic_search


async def handle_judge_memory(server, drawers, arguments):
    """LLM判断记忆价值(A/B/C三级分类)"""
    judge = get_memory_judge(server.config)
    result = judge.evaluate(
        task_type=arguments.get("task_type", "unknown"),
        task_description=arguments.get("task_description", ""),
        output_summary=arguments.get("output_summary", ""),
        agent_id=arguments.get("agent_id", ""),
    )
    return json.dumps(
        {
            "verdict": result.verdict.value,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
            "suggested_tags": result.suggested_tags,
            "suggested_importance": result.suggested_importance,
            "suggested_wing": result.suggested_wing,
            "suggested_room": result.suggested_room,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_judge_memory"] = handle_judge_memory


async def handle_judge_stats(server, drawers, arguments):
    """获取判断统计"""
    judge = get_memory_judge(server.config)
    return json.dumps(judge.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_judge_stats"] = handle_judge_stats


async def handle_adaptive_params(server, drawers, arguments):
    """获取/调整自适应参数"""
    engine = get_adaptive_engine(server.config)
    action = arguments.get("action", "get")
    if action == "reset":
        params = engine.reset()
        return json.dumps({"status": "reset", "params": params.to_dict()}, ensure_ascii=False)
    elif action == "history":
        history = engine.get_history(limit=arguments.get("limit", 10))
        return json.dumps(history, ensure_ascii=False, indent=2)
    else:
        return json.dumps(engine.get_params().to_dict(), ensure_ascii=False, indent=2)


HANDLERS["pangu_adaptive_params"] = handle_adaptive_params


async def handle_adaptive_evaluate(server, drawers, arguments):
    """根据系统统计评估并调整参数"""
    engine = get_adaptive_engine(server.config)
    stats = arguments.get("stats", {})
    if not stats:
        stats = {
            "total_memories": len(drawers),
            "growth_rate": 0,
            "duplicate_rate": 0,
            "forget_rate": 0,
            "avg_search_score": 0.5,
        }
    params = engine.evaluate(stats)
    return json.dumps(
        {
            "params": params.to_dict(),
            "updated": bool(params.update_reason and params.update_reason != "no_change"),
            "reason": params.update_reason,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_adaptive_evaluate"] = handle_adaptive_evaluate


async def handle_wm_push(server, drawers, arguments):
    """推入工作记忆项"""
    wm = get_working_memory()
    item = WMItem(
        id=arguments.get("item_id", f"wm_{int(time.time())}"),
        content=arguments.get("content", ""),
        source=arguments.get("source", "mcp"),
        emotional_valence=arguments.get("emotional_valence", 0.0),
        urgency=arguments.get("urgency", 0.0),
        tokens=arguments.get("tokens", len(arguments.get("content", "")) // 4),
    )
    evicted = wm.push(item)
    return json.dumps(
        {
            "status": "pushed",
            "item_id": item.id,
            "evicted": evicted.id if evicted else None,
            "slots_used": len(wm.slots),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_wm_push"] = handle_wm_push


async def handle_wm_get(server, drawers, arguments):
    """获取工作记忆项"""
    wm = get_working_memory()
    item_id = arguments.get("item_id")
    if item_id:
        item = wm.get(item_id)
        if item:
            return json.dumps(
                {
                    "id": item.id,
                    "content": item.content[:200],
                    "activation": round(item.activation, 4),
                    "emotional_valence": item.emotional_valence,
                    "access_count": item.access_count,
                },
                ensure_ascii=False,
            )
        return json.dumps({"error": "item not found"})
    # 返回焦点项
    focus = wm.focus
    if focus:
        return json.dumps(
            {
                "focus": {
                    "id": focus.id,
                    "content": focus.content[:200],
                    "activation": round(focus.activation, 4),
                },
                "slots_used": len(wm.slots),
            },
            ensure_ascii=False,
        )
    return json.dumps({"slots": [], "slots_used": 0})


HANDLERS["pangu_wm_get"] = handle_wm_get


async def handle_wm_stats(server, drawers, arguments):
    """获取工作记忆统计"""
    wm = get_working_memory()
    return json.dumps(wm.stats, ensure_ascii=False, indent=2)


HANDLERS["pangu_wm_stats"] = handle_wm_stats


async def handle_wm_clear(server, drawers, arguments):
    """清空工作记忆"""
    wm = get_working_memory()
    wm.clear()
    return json.dumps({"status": "cleared"})


HANDLERS["pangu_wm_clear"] = handle_wm_clear


async def handle_reconsolidate(server, drawers, arguments):
    """再巩固记忆（刷新衰减分数）"""
    engine = ReconsolidationEngine(server.config)
    result = engine.run(
        drawers,
        min_importance=arguments.get("min_importance", 0.3),
        max_importance=arguments.get("max_importance", 0.7),
        limit=arguments.get("limit", 20),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_reconsolidate"] = handle_reconsolidate


async def handle_find_resonance(server, drawers, arguments):
    """发现情感/语义共鸣的记忆对"""
    engine = ResonanceEngine(server.config)
    matches = engine.find_resonance(
        drawers,
        limit=arguments.get("limit", 30),
        sim_threshold=arguments.get("sim_threshold", 0.7),
    )
    return json.dumps(matches, ensure_ascii=False, indent=2)


HANDLERS["pangu_find_resonance"] = handle_find_resonance


async def handle_cross_wing_resonance(server, drawers, arguments):
    """发现跨Wing的知识共鸣"""
    engine = ResonanceEngine(server.config)
    matches = engine.find_cross_wing_resonance(
        drawers,
        sim_threshold=arguments.get("sim_threshold", 0.65),
    )
    return json.dumps(matches, ensure_ascii=False, indent=2)


HANDLERS["pangu_cross_wing_resonance"] = handle_cross_wing_resonance


async def handle_attention_state(server, drawers, arguments):
    """获取当前注意力状态"""
    attn = get_attention_system()
    return json.dumps(attn.stats, ensure_ascii=False, indent=2)


HANDLERS["pangu_attention_state"] = handle_attention_state


async def handle_attention_switch(server, drawers, arguments):
    """切换注意力策略"""
    attn = get_attention_system()
    strategy_str = arguments.get("strategy", "bottom_up")
    reason = arguments.get("reason", "")
    try:
        strategy = AttentionStrategy(strategy_str)
    except ValueError:
        return json.dumps({"error": f"unknown strategy: {strategy_str}, valid: {[s.value for s in AttentionStrategy]}"})
    old, new = attn.switch(strategy, reason=reason)
    return json.dumps(
        {
            "old": old.value,
            "new": new.value,
            "reason": reason,
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_attention_switch"] = handle_attention_switch


async def handle_attention_ab_test(server, drawers, arguments):
    """启动注意力策略A/B测试"""
    attn = get_attention_system()
    action = arguments.get("action", "start")
    if action == "stop":
        result = attn.stop_ab_test()
        return json.dumps(result, ensure_ascii=False, indent=2)
    else:
        strategy_a = arguments.get("strategy_a", "bottom_up")
        strategy_b = arguments.get("strategy_b", "focus")
        sa = AttentionStrategy(strategy_a)
        sb = AttentionStrategy(strategy_b)


HANDLERS["pangu_attention_ab_test"] = handle_attention_ab_test


async def handle_streaming_index(server, drawers, arguments):
    """增量索引新记忆"""
    from ...search.embedder import VectorEmbedder

    indexer = StreamingIndexer(server.config)
    embedder = VectorEmbedder(server.config)
    result = indexer.index(drawers, embedder=embedder)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_streaming_index"] = handle_streaming_index


async def handle_streaming_stats(server, drawers, arguments):
    """获取流式索引统计"""
    indexer = StreamingIndexer(server.config)
    return json.dumps(indexer.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_streaming_stats"] = handle_streaming_stats


async def handle_verify(server, drawers, arguments):
    """运行完整验证循环"""
    loop = VerificationLoop(project_path=arguments.get("project_path", "."))
    result = loop.run_full_verification()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_verify"] = handle_verify


async def handle_verify_phase(server, drawers, arguments):
    """运行单个验证阶段"""
    phase = arguments.get("phase", "build")
    loop = VerificationLoop(project_path=arguments.get("project_path", "."))
    phase_map = {
        "build": loop.run_build,
        "type_check": loop.run_type_check,
        "lint": loop.run_lint,
        "tests": loop.run_tests,
        "security": loop.run_security_scan,
        "diff_review": loop.run_diff_review,
    }
    if phase in phase_map:
        result = phase_map[phase]()
        return json.dumps(
            {
                "phase": result.phase,
                "passed": result.passed,
                "output": result.output[:1000],
                "warnings": result.warnings,
                "errors": result.errors,
            },
            ensure_ascii=False,
        )
    return json.dumps({"error": f"unknown phase: {phase}"})


HANDLERS["pangu_verify_phase"] = handle_verify_phase


async def handle_privacy_stats(server, drawers, arguments):
    """获取隐私预算统计"""
    dp = DifferentialPrivacy(
        epsilon=arguments.get("epsilon", 1.0),
        delta=arguments.get("delta", 1e-5),
    )
    return json.dumps(dp.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_privacy_stats"] = handle_privacy_stats


async def handle_privatize_count(server, drawers, arguments):
    """隐私化计数结果"""
    dp = DifferentialPrivacy(
        epsilon=arguments.get("epsilon", 1.0),
        delta=arguments.get("delta", 1e-5),
    )
    count = arguments.get("count", 0)
    result = dp.privatize_count(count)
    return json.dumps(
        {
            "original": count,
            "privatized": result,
            "budget": dp.stats(),
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_privatize_count"] = handle_privatize_count


async def handle_autonomous_analyze(server, drawers, arguments):
    """分析任务复杂度并推荐能力"""
    from ...autonomous import analyze_task

    task = arguments.get("task", "")
    result = analyze_task(task)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_autonomous_analyze"] = handle_autonomous_analyze


async def handle_neural_stats(server, drawers, arguments):
    """获取海马体-新皮层双系统统计"""
    from ...memory.neural_memory import get_neural_engine

    engine = get_neural_engine()
    return json.dumps(engine.stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_neural_stats"] = handle_neural_stats


async def handle_neural_sleep(server, drawers, arguments):
    """触发神经睡眠巩固（海马体→新皮层重播）"""
    from ...memory.neural_memory import get_neural_engine

    engine = get_neural_engine()
    result = engine.sleep()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_neural_sleep"] = handle_neural_sleep


async def handle_neural_spreading(server, drawers, arguments):
    """基于种子记忆执行激活扩散，找到关联记忆"""
    from ...memory.neural_memory import get_neural_engine

    engine = get_neural_engine()
    seed_ids = arguments.get("seed_ids", [])
    depth = arguments.get("depth", engine.config.neural_spreading_depth)
    activations = engine.neocortex.activate_spreading(
        seed_ids,
        decay_factor=engine.config.neural_spreading_decay,
        max_depth=depth,
    )
    results = []
    for mid, act in activations[:20]:
        mem = engine.neocortex.get(mid)
        if mem:
            results.append(
                {
                    "id": mid,
                    "content": mem.content[:200],
                    "activation": round(act, 4),
                    "type": mem.memory_type.value,
                    "state": mem.state.value,
                }
            )
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_neural_spreading"] = handle_neural_spreading


async def handle_neural_inhibition(server, drawers, arguments):
    """对一组记忆执行竞争抑制，返回有效激活值"""
    from ...memory.neural_memory import get_neural_engine

    engine = get_neural_engine()
    memory_ids = arguments.get("memory_ids", [])
    activations = engine.neocortex.mutual_inhibition(memory_ids)
    return json.dumps(
        {
            "activations": {k: round(v, 4) for k, v in activations.items()},
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_neural_inhibition"] = handle_neural_inhibition


async def handle_neural_decay(server, drawers, arguments):
    """对所有神经记忆应用个性化衰减"""
    from ...memory.neural_memory import get_neural_engine

    engine = get_neural_engine()
    forgotten = engine.apply_global_decay()
    return json.dumps(
        {
            "forgotten_count": len(forgotten),
            "forgotten_ids": [m.id for m in forgotten],
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_neural_decay"] = handle_neural_decay


async def handle_multi_register(server, drawers, arguments):
    """注册Agent到协作记忆空间"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    agent_id = arguments.get("agent_id", "")
    priority = arguments.get("priority", 5)
    mam.register_agent(agent_id, priority)
    return json.dumps({"status": "registered", "agent_id": agent_id, "priority": priority}, ensure_ascii=False)


HANDLERS["pangu_multi_register"] = handle_multi_register


async def handle_multi_write(server, drawers, arguments):
    """写入多Agent共享记忆"""
    from ...memory.multi_agent import MemoryScope, get_multi_agent_memory

    mam = get_multi_agent_memory()
    agent_id = arguments.get("agent_id", "")
    content = arguments.get("content", "")
    scope_str = arguments.get("scope", "public")
    tags = arguments.get("tags", [])
    scope = MemoryScope(scope_str) if scope_str in ["private", "shared", "public"] else MemoryScope.PUBLIC
    mem = mam.write(agent_id, content, scope=scope, tags=tags)
    return json.dumps({"id": mem.id, "content": mem.content[:50], "scope": mem.scope.value}, ensure_ascii=False)


HANDLERS["pangu_multi_write"] = handle_multi_write


async def handle_multi_read(server, drawers, arguments):
    """读取Agent可见的记忆"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    agent_id = arguments.get("agent_id", "")
    tags = arguments.get("tags", None)
    results = mam.read(agent_id, tags=tags)
    return json.dumps(
        {
            "count": len(results),
            "memories": [
                {"id": m.id, "content": m.content[:50], "owner": m.owner, "scope": m.scope.value} for m in results[:10]
            ],
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_multi_read"] = handle_multi_read


async def handle_multi_agents(server, drawers, arguments):
    """获取所有已注册Agent"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    agents = mam.get_agents()
    return json.dumps({"agents": agents, "count": len(agents)}, ensure_ascii=False)


HANDLERS["pangu_multi_agents"] = handle_multi_agents


async def handle_generate_ideas(server, drawers, arguments):
    """基于记忆生成新想法"""
    from ...memory.creative_thinking import get_creative_thinking

    ct = get_creative_thinking(server.config)
    limit = arguments.get("limit", 5)
    ideas = ct.generate_ideas(drawers)
    return json.dumps(
        {
            "ideas": [
                {"title": i.title, "description": i.description, "category": i.category, "confidence": i.confidence}
                for i in ideas[:limit]
            ],
            "count": len(ideas),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_generate_ideas"] = handle_generate_ideas


async def handle_generate_novel(server, drawers, arguments):
    """生成原创想法"""
    from ...memory.creative_thinking import get_creative_thinking

    ct = get_creative_thinking(server.config)
    domain = arguments.get("domain", "")
    context = arguments.get("context", "")
    ideas = ct.generate_novel_ideas(domain, context, drawers)
    return json.dumps({"ideas": ideas, "count": len(ideas)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_generate_novel"] = handle_generate_novel


async def handle_agent_register(server, drawers, arguments):
    """注册 Agent"""
    from ...memory.collaborative_intelligence import get_collaborative

    ci = get_collaborative(server.config)
    result = ci.register_agent(
        arguments["agent_id"],
        arguments["name"],
        arguments.get("specialties", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_agent_register"] = handle_agent_register


async def handle_agent_share(server, drawers, arguments):
    """Agent 间共享知识"""
    from ...memory.collaborative_intelligence import get_collaborative

    ci = get_collaborative(server.config)
    result = ci.share_knowledge(
        arguments["from_agent"],
        arguments["to_agent"],
        arguments["knowledge_ids"],
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_agent_share"] = handle_agent_share


async def handle_collaborative_reason(server, drawers, arguments):
    """协作推理"""
    from ...memory.collaborative_intelligence import get_collaborative

    ci = get_collaborative(server.config)
    result = ci.collaborative_reasoning(
        arguments["task"],
        arguments.get("agent_ids"),
    )
    return json.dumps(
        {
            "task": result.task,
            "participants": result.participants,
            "consensus": result.consensus,
            "confidence": result.confidence,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_collaborative_reason"] = handle_collaborative_reason


async def handle_agent_stats(server, drawers, arguments):
    """获取 Agent 统计"""
    from ...memory.collaborative_intelligence import get_collaborative

    ci = get_collaborative(server.config)
    return json.dumps(ci.get_agent_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_agent_stats"] = handle_agent_stats


async def handle_synthesize(server, drawers, arguments):
    """按主题综合知识"""
    from ...memory.knowledge_synthesis import get_synthesizer

    ks = get_synthesizer(server.config)
    limit = arguments.get("limit", 10)
    insights = ks.synthesize_by_topic(drawers)
    return json.dumps(
        {
            "insights": [
                {"topic": i.topic, "summary": i.summary, "sources": i.sources, "confidence": i.confidence}
                for i in insights[:limit]
            ],
            "count": len(insights),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_synthesize"] = handle_synthesize


async def handle_find_contradictions(server, drawers, arguments):
    """检测矛盾信息"""
    from ...memory.knowledge_synthesis import get_synthesizer

    ks = get_synthesizer(server.config)
    contradictions = ks.detect_contradictions(drawers)
    return json.dumps(
        {
            "contradictions": [
                {"topic": c.topic, "claim_a": c.claim_a[:50], "claim_b": c.claim_b[:50], "severity": c.severity}
                for c in contradictions
            ],
            "count": len(contradictions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_find_contradictions"] = handle_find_contradictions


async def handle_core_insights(server, drawers, arguments):
    """提取核心洞察"""
    from ...memory.knowledge_synthesis import get_synthesizer

    ks = get_synthesizer(server.config)
    top_k = arguments.get("top_k", 10)
    insights = ks.extract_core_insights(drawers, top_k)
    return json.dumps({"insights": insights, "count": len(insights)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_core_insights"] = handle_core_insights


async def handle_auto_learn(server, drawers, arguments):
    """执行自主学习循环"""
    from ...memory.autonomous_learning import get_autonomous_learning

    al = get_autonomous_learning(server.config)
    result = al.auto_learn(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_auto_learn"] = handle_auto_learn


async def handle_arch_analyze(server, drawers, arguments):
    """分析记忆架构"""
    from ...memory.adaptive_architecture import get_architecture

    aa = get_architecture(server.config)
    return json.dumps(aa.analyze_architecture(drawers), ensure_ascii=False, indent=2)


HANDLERS["pangu_arch_analyze"] = handle_arch_analyze


async def handle_arch_suggest(server, drawers, arguments):
    """架构重构建议"""
    from ...memory.adaptive_architecture import get_architecture

    aa = get_architecture(server.config)
    suggestions = aa.suggest_restructuring(drawers)
    return json.dumps(
        {
            "suggestions": [{"action": s.action, "reason": s.reason, "priority": s.priority} for s in suggestions],
            "count": len(suggestions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_arch_suggest"] = handle_arch_suggest


async def handle_cold_hot(server, drawers, arguments):
    """冷热分离建议"""
    from ...memory.adaptive_architecture import get_architecture

    aa = get_architecture(server.config)
    result = aa.suggest_cold_hot_separation(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_cold_hot"] = handle_cold_hot


async def handle_arch_stats(server, drawers, arguments):
    """架构统计"""
    from ...memory.adaptive_architecture import get_architecture

    aa = get_architecture(server.config)
    return json.dumps(aa.get_architecture_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_arch_stats"] = handle_arch_stats


async def handle_qa(server, drawers, arguments):
    """基于记忆的智能问答"""
    from ...memory.qa_engine import get_qa_engine

    qa = get_qa_engine(server.config)
    question = arguments.get("question", "")
    result = qa.answer(question, drawers)
    return json.dumps(
        {
            "question": result.question,
            "answer": result.answer,
            "confidence": result.confidence,
            "sources": result.source_memories,
            "follow_up": result.follow_up_questions,
            "reasoning": result.reasoning_steps,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_qa"] = handle_qa


async def handle_qa_batch(server, drawers, arguments):
    """批量智能问答"""
    from ...memory.qa_engine import get_qa_engine

    qa = get_qa_engine(server.config)
    questions = arguments.get("questions", [])
    results = qa.batch_answer(questions, drawers)
    return json.dumps(
        {
            "results": [{"question": r.question, "answer": r.answer, "confidence": r.confidence} for r in results],
            "count": len(results),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_qa_batch"] = handle_qa_batch


async def handle_qa_stats(server, drawers, arguments):
    """问答统计"""
    from ...memory.qa_engine import get_qa_engine

    qa = get_qa_engine(server.config)
    return json.dumps(qa.get_qa_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_qa_stats"] = handle_qa_stats


async def handle_inject_context(server, drawers, arguments):
    """为文本注入相关记忆上下文"""
    from ...memory.context_injection import get_injection_engine

    ie = get_injection_engine(server.config)
    text = arguments.get("text", "")
    budget = arguments.get("token_budget", 500)
    result = ie.inject_context(text, drawers, budget)
    return json.dumps(
        {
            "injected_text": result.injected_text[:2000],
            "context_count": result.context_count,
            "tokens_used": result.tokens_used,
            "token_budget": result.token_budget,
            "injections": result.injection_positions,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_inject_context"] = handle_inject_context


async def handle_update_context(server, drawers, arguments):
    """增量更新上下文"""
    from ...memory.context_injection import get_injection_engine

    ie = get_injection_engine(server.config)
    text = arguments.get("text", "")
    result = ie.update_context(text, drawers)
    return json.dumps(
        {
            "context_count": result.context_count,
            "tokens_used": result.tokens_used,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_update_context"] = handle_update_context


async def handle_current_context(server, drawers, arguments):
    """获取当前上下文缓冲"""
    from ...memory.context_injection import get_injection_engine

    ie = get_injection_engine(server.config)
    context = ie.get_current_context()
    return json.dumps({"context": context, "count": len(context)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_current_context"] = handle_current_context


async def handle_injection_stats(server, drawers, arguments):
    """上下文注入统计"""
    from ...memory.context_injection import get_injection_engine

    ie = get_injection_engine(server.config)
    return json.dumps(ie.get_injection_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_injection_stats"] = handle_injection_stats


async def handle_evaluate_forgetting(server, drawers, arguments):
    """评估所有记忆的遗忘价值"""
    from ...memory.adaptive_forgetting import get_forgetting

    af = get_forgetting(server.config)
    report = af.evaluate_all(drawers)
    return json.dumps(
        {
            "total": report.total_evaluated,
            "keep": report.keep_count,
            "archive": report.archive_count,
            "compress": report.compress_count,
            "forget": report.forget_count,
            "tokens_freed": report.estimated_tokens_freed,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_evaluate_forgetting"] = handle_evaluate_forgetting


async def handle_auto_forget(server, drawers, arguments):
    """自动执行遗忘（归档+清理）"""
    from ...memory.adaptive_forgetting import get_forgetting

    af = get_forgetting(server.config)
    result = af.auto_forget(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_auto_forget"] = handle_auto_forget


async def handle_get_archive(server, drawers, arguments):
    """获取归档记忆"""
    from ...memory.adaptive_forgetting import get_forgetting

    af = get_forgetting(server.config)
    limit = arguments.get("limit", 20)
    archive = af.get_archive(limit)
    return json.dumps({"archive": archive, "count": len(archive)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_get_archive"] = handle_get_archive


async def handle_consolidate(server, drawers, arguments):
    """执行智能记忆巩固"""
    from ...memory.consolidation_intelligence import get_consolidation_intel
    from ...memory.lifecycle import LifecycleManager

    ci = get_consolidation_intel(server.config)
    report = ci.run_consolidation(drawers)
    # 同时更新 lifecycle 状态中的 last_consolidation 时间戳
    lifecycle = LifecycleManager(server.config)
    lifecycle._last_consolidation = time.time()
    lifecycle._save_state()
    return json.dumps(
        {
            "total_actions": report.total_actions,
            "merges": report.merges,
            "promotions": report.promotions,
            "resolutions": report.resolutions,
            "compressions": report.compressions,
            "avg_info_preserved": report.avg_info_preserved,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_consolidate"] = handle_consolidate


async def handle_merge_candidates(server, drawers, arguments):
    """查找可合并记忆"""
    from ...memory.consolidation_intelligence import get_consolidation_intel

    ci = get_consolidation_intel(server.config)
    candidates = ci.find_merge_candidates(drawers)
    return json.dumps(
        {
            "candidates": [
                {
                    "ids": [d.id for d in group],
                    "count": len(group),
                    "tags": list(set(t for d in group for t in d.tags))[:5],
                }
                for group in candidates
            ],
            "count": len(candidates),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_merge_candidates"] = handle_merge_candidates


async def handle_resolve_conflicts(server, drawers, arguments):
    """发现并解决矛盾记忆"""
    from ...memory.consolidation_intelligence import get_consolidation_intel

    ci = get_consolidation_intel(server.config)
    actions = ci.find_conflicts(drawers)
    return json.dumps(
        {
            "conflicts": [{"target": a.target_id, "description": a.description} for a in actions],
            "count": len(actions),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_resolve_conflicts"] = handle_resolve_conflicts


async def handle_extract_keywords(server, drawers, arguments):
    """提取关键词"""
    from ...memory.distillation import get_distiller

    d = get_distiller(server.config)
    text = arguments.get("text", "")
    top_k = arguments.get("top_k", 5)
    keywords = d.extract_keywords(text, top_k)
    return json.dumps({"keywords": keywords}, ensure_ascii=False, indent=2)


HANDLERS["pangu_extract_keywords"] = handle_extract_keywords


async def handle_build_graph(server, drawers, arguments):
    """从记忆构建知识图谱"""
    from ...memory.graph_builder import get_builder

    gb = get_builder(server.config)
    max_d = arguments.get("max_drawers", 100)
    result = gb.build_from_drawers(drawers, max_d)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_build_graph"] = handle_build_graph


async def handle_verify_backup(server, drawers, arguments):
    """验证备份完整性"""
    from ...memory.backup_restore import get_backup_engine

    be = get_backup_engine(server.config)
    return json.dumps(be.verify_backup(arguments["backup_id"]), ensure_ascii=False, indent=2)


HANDLERS["pangu_verify_backup"] = handle_verify_backup


async def handle_event_emit(server, drawers, arguments):
    """发布记忆事件"""
    from ...memory.memory_events import get_event_stream

    es = get_event_stream(server.config)
    event = es.emit(
        arguments["event_type"],
        arguments.get("memory_id", ""),
        arguments.get("data", {}),
    )
    return json.dumps(
        {"event_id": event.event_id, "type": event.event_type, "timestamp": event.timestamp},
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_event_emit"] = handle_event_emit


async def handle_event_history(server, drawers, arguments):
    """查询事件历史"""
    from ...memory.memory_events import get_event_stream

    es = get_event_stream(server.config)
    history = es.get_history(arguments.get("event_type"), arguments.get("limit", 50))
    return json.dumps({"events": history, "count": len(history)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_event_history"] = handle_event_history


async def handle_event_stats(server, drawers, arguments):
    """事件统计"""
    from ...memory.memory_events import get_event_stream

    es = get_event_stream(server.config)
    return json.dumps(es.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_event_stats"] = handle_event_stats


async def handle_event_webhook_add(server, drawers, arguments):
    """添加 Webhook"""
    from ...memory.memory_events import get_event_stream

    es = get_event_stream(server.config)
    result = es.add_webhook(arguments["url"], arguments["event_types"])
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_event_webhook_add"] = handle_event_webhook_add


async def handle_event_save(server, drawers, arguments):
    """持久化事件历史"""
    from ...memory.memory_events import get_event_stream

    es = get_event_stream(server.config)
    saved = es.save_history()
    return json.dumps({"saved": saved}, ensure_ascii=False, indent=2)


HANDLERS["pangu_event_save"] = handle_event_save


async def handle_index_build(server, drawers, arguments):
    """构建所有索引"""
    from ...memory.smart_indexing import get_smart_indexing

    si = get_smart_indexing(server.config)
    result = si.build_all_indexes(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_index_build"] = handle_index_build


async def handle_index_search(server, drawers, arguments):
    """通过索引搜索"""
    from ...memory.smart_indexing import get_smart_indexing

    si = get_smart_indexing(server.config)
    results = si.search_index(arguments["query"])
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_index_search"] = handle_index_search


async def handle_index_recommend(server, drawers, arguments):
    """索引推荐"""
    from ...memory.smart_indexing import get_smart_indexing

    si = get_smart_indexing(server.config)
    recs = si.recommend_indexes(drawers)
    return json.dumps(
        {
            "recommendations": [
                {"type": r.index_type, "key": r.key, "reason": r.reason, "priority": r.priority} for r in recs
            ],
            "count": len(recs),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_index_recommend"] = handle_index_recommend


async def handle_index_health(server, drawers, arguments):
    """索引健康检查"""
    from ...memory.smart_indexing import get_smart_indexing

    si = get_smart_indexing(server.config)
    return json.dumps(si.get_index_health(), ensure_ascii=False, indent=2)


HANDLERS["pangu_index_health"] = handle_index_health


async def handle_index_cleanup(server, drawers, arguments):
    """清理无效索引"""
    from ...memory.smart_indexing import get_smart_indexing

    si = get_smart_indexing(server.config)
    cleaned = si.cleanup_indexes()
    return json.dumps({"cleaned": cleaned, "remaining": len(si._indexes)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_index_cleanup"] = handle_index_cleanup


async def handle_cache_stats(server, drawers, arguments):
    """缓存统计"""
    from ...memory.search_cache import get_search_cache

    cache = get_search_cache()
    return json.dumps(cache.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_cache_stats"] = handle_cache_stats


async def handle_cache_cleanup(server, drawers, arguments):
    """清理过期缓存"""
    from ...memory.smart_cache import get_cache_manager

    cm = get_cache_manager(server.config)
    c1 = cm._l1.cleanup_expired()
    c2 = cm._l2.cleanup_expired()
    return json.dumps({"l1_cleaned": c1, "l2_cleaned": c2, "total": c1 + c2}, ensure_ascii=False, indent=2)


HANDLERS["pangu_cache_cleanup"] = handle_cache_cleanup


async def handle_cache_invalidate(server, drawers, arguments):
    """失效缓存"""
    from ...memory.smart_cache import get_cache_manager

    cm = get_cache_manager(server.config)
    pattern = arguments.get("pattern", "")
    c1 = cm._l1.invalidate_pattern(pattern)
    c2 = cm._l2.invalidate_pattern(pattern)
    return json.dumps({"pattern": pattern, "invalidated": c1 + c2}, ensure_ascii=False, indent=2)


HANDLERS["pangu_cache_invalidate"] = handle_cache_invalidate


async def handle_diff_content(server, drawers, arguments):
    """对比两段内容差异"""
    from ...memory.memory_diff import get_diff_engine

    de = get_diff_engine(server.config)
    diff = de.diff_content(arguments["content_a"], arguments["content_b"])
    return json.dumps(
        {
            "similarity": diff.similarity,
            "added": diff.added,
            "removed": diff.removed,
            "modified": diff.modified,
            "unchanged": diff.unchanged,
            "summary": de.generate_change_summary(diff),
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_diff_content"] = handle_diff_content


async def handle_diff_batch(server, drawers, arguments):
    """批量差异对比"""
    from ...memory.memory_diff import get_diff_engine

    de = get_diff_engine(server.config)
    results = de.batch_diff(drawers, arguments.get("reference_id"))
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_diff_batch"] = handle_diff_batch


async def handle_diff_similarity(server, drawers, arguments):
    """计算记忆相似度矩阵"""
    from ...memory.memory_diff import get_diff_engine

    de = get_diff_engine(server.config)
    matrix = de.similarity_matrix(drawers)
    return json.dumps({"size": matrix["size"], "ids": matrix["ids"]}, ensure_ascii=False, indent=2)


HANDLERS["pangu_diff_similarity"] = handle_diff_similarity


async def handle_diff_stats(server, drawers, arguments):
    """差异统计"""
    from ...memory.memory_diff import get_diff_engine

    de = get_diff_engine(server.config)
    return json.dumps(de.get_diff_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_diff_stats"] = handle_diff_stats


async def handle_visualize_graph(server, drawers, arguments):
    """可视化知识图谱"""
    from ...memory.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(server.config)
    entities = kg.list_entities()
    relations = []
    with kg._conn() as conn:
        rows = conn.execute("SELECT * FROM relations").fetchall()
        relations = [dict(r) for r in rows]
    from ...memory.visualization import get_visualizer

    viz = get_visualizer(server.config)
    return viz.visualize_graph(entities, relations)


HANDLERS["pangu_visualize_graph"] = handle_visualize_graph


async def handle_visualize_network(server, drawers, arguments):
    """可视化记忆网络"""
    from ...memory.visualization import get_visualizer

    viz = get_visualizer(server.config)
    return viz.visualize_network(drawers)


HANDLERS["pangu_visualize_network"] = handle_visualize_network


async def handle_visualize_stats(server, drawers, arguments):
    """可视化统计信息"""
    from ...memory.visualization import get_visualizer

    viz = get_visualizer(server.config)
    return viz.visualize_stats(drawers)


HANDLERS["pangu_visualize_stats"] = handle_visualize_stats


async def handle_detect_patterns(server, drawers, arguments):
    """检测用户行为模式"""
    from ...memory.adaptive_learning import get_adaptive_learning

    al = get_adaptive_learning(server.config)
    patterns = al.detect_patterns()
    return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)


HANDLERS["pangu_detect_patterns"] = handle_detect_patterns


async def handle_popular_queries(server, drawers, arguments):
    """获取热门查询"""
    from ...memory.adaptive_learning import get_adaptive_learning

    al = get_adaptive_learning(server.config)
    limit = arguments.get("limit", 10)
    return json.dumps(al.get_popular_queries(limit), ensure_ascii=False, indent=2)


HANDLERS["pangu_popular_queries"] = handle_popular_queries


async def handle_frequent_memories(server, drawers, arguments):
    """获取频繁访问的记忆"""
    from ...memory.adaptive_learning import get_adaptive_learning

    al = get_adaptive_learning(server.config)
    limit = arguments.get("limit", 10)
    return json.dumps(al.get_frequent_memories(limit), ensure_ascii=False, indent=2)


HANDLERS["pangu_frequent_memories"] = handle_frequent_memories


async def handle_comment_add(server, drawers, arguments):
    """添加记忆评论"""
    from ...memory.social_memory import SocialMemory

    sm = SocialMemory(server.config)
    memory_id = arguments.get("memory_id", "")
    author_id = arguments.get("author_id", "")
    content = arguments.get("content", "")
    comment = sm.add_comment(memory_id, author_id, content)
    return json.dumps({"id": comment.id, "memory_id": memory_id, "content": content[:50]}, ensure_ascii=False)


HANDLERS["pangu_comment_add"] = handle_comment_add


async def handle_comment_list(server, drawers, arguments):
    """获取记忆评论列表"""
    from ...memory.social_memory import SocialMemory

    sm = SocialMemory(server.config)
    memory_id = arguments.get("memory_id", "")
    comments = sm.get_comments(memory_id, top_level_only=False)
    return json.dumps(
        {
            "count": len(comments),
            "comments": [
                {"id": c.id, "author": c.author_id, "content": c.content[:50], "likes": c.likes} for c in comments[:10]
            ],
        },
        ensure_ascii=False,
    )


HANDLERS["pangu_comment_list"] = handle_comment_list


async def handle_vote(server, drawers, arguments):
    """对记忆投票"""
    from ...memory.social_memory import SocialMemory, VoteType

    sm = SocialMemory(server.config)
    memory_id = arguments.get("memory_id", "")
    user_id = arguments.get("user_id", "")
    vote_type_str = arguments.get("vote_type", "up")
    vote_type = VoteType(vote_type_str) if vote_type_str in ["up", "down", "bookmark"] else VoteType.UP
    vote = sm.vote(memory_id, user_id, vote_type)
    return json.dumps({"memory_id": memory_id, "user_id": user_id, "vote_type": vote_type.value}, ensure_ascii=False)


HANDLERS["pangu_vote"] = handle_vote


async def handle_vote_stats(server, drawers, arguments):
    """获取记忆投票统计"""
    from ...memory.social_memory import SocialMemory

    sm = SocialMemory(server.config)
    memory_id = arguments.get("memory_id", "")
    stats = sm.get_votes(memory_id)
    return json.dumps(stats, ensure_ascii=False)


HANDLERS["pangu_vote_stats"] = handle_vote_stats


async def handle_dream_cycle(server, drawers, arguments):
    """运行一次梦境巩固周期（fetch→dedup→link→decay→distill）"""
    from ...memory.dream_memory import get_dream_engine

    engine = get_dream_engine(server.config)
    result = engine.run_dream_cycle(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_dream_cycle"] = handle_dream_cycle


async def handle_dream_stats(server, drawers, arguments):
    """获取梦境巩固统计"""
    from ...memory.dream_memory import get_dream_engine

    engine = get_dream_engine(server.config)
    return json.dumps(engine.dream_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_dream_stats"] = handle_dream_stats


async def handle_curiosity_explore(server, drawers, arguments):
    """运行好奇心探索（发现知识空白）"""
    from ...memory.curiosity import get_curiosity_engine

    engine = get_curiosity_engine(server.config)
    result = engine.explore(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_curiosity_explore"] = handle_curiosity_explore


async def handle_curiosity_gaps(server, drawers, arguments):
    """发现知识空白并生成探索建议"""
    from ...memory.curiosity import get_curiosity_engine

    engine = get_curiosity_engine(server.config)
    result = engine.find_gaps(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_curiosity_gaps"] = handle_curiosity_gaps


async def handle_persona_identity(server, drawers, arguments):
    """获取系统身份和人格特质"""
    from ...memory.persona import get_persona_engine

    engine = get_persona_engine(server.config)
    return json.dumps(engine.get_identity(), ensure_ascii=False, indent=2)


HANDLERS["pangu_persona_identity"] = handle_persona_identity


async def handle_persona_values(server, drawers, arguments):
    """获取系统价值观和原则"""
    from ...memory.persona import get_persona_engine

    engine = get_persona_engine(server.config)
    return json.dumps(engine.get_values(), ensure_ascii=False, indent=2)


HANDLERS["pangu_persona_values"] = handle_persona_values


async def handle_persona_health(server, drawers, arguments):
    """系统综合健康度检查"""
    from ...memory.persona import get_persona_engine

    engine = get_persona_engine(server.config)
    result = engine.health_check(drawers)
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_persona_health"] = handle_persona_health


async def handle_autonomous_tick(server, drawers, arguments):
    """检查是否需要运行自主维护周期"""
    from ...memory.autonomous import get_autonomous_engine

    engine = get_autonomous_engine(server.config)
    result = engine.tick()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_autonomous_tick"] = handle_autonomous_tick


async def handle_autonomous_run(server, drawers, arguments):
    """运行一次自主记忆管理周期（融合/压缩/衰减/遗忘/探索）"""
    from ...memory.autonomous import get_autonomous_engine

    force = arguments.get("force", False)
    engine = get_autonomous_engine(server.config)
    cycle = engine.run_cycle(force=force)
    result = {
        "timestamp": cycle.timestamp,
        "duration_ms": cycle.total_duration_ms,
        "tasks_run": cycle.tasks_run,
        "tasks_skipped": cycle.tasks_skipped,
        "tasks_failed": cycle.tasks_failed,
        "trigger": cycle.trigger,
        "results": [
            {"name": r.name, "status": r.status, "duration_ms": r.duration_ms, "details": r.details}
            for r in cycle.results
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_autonomous_run"] = handle_autonomous_run


async def handle_autonomous_status(server, drawers, arguments):
    """查看自主引擎状态和任务调度"""
    from ...memory.autonomous import get_autonomous_engine

    engine = get_autonomous_engine(server.config)
    result = engine.get_status()
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_autonomous_status"] = handle_autonomous_status


async def handle_agent_activity(server, drawers, arguments):
    """查看Agent活动流（读写记录）"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    agent_id = arguments.get("agent_id", None)
    limit = arguments.get("limit", 20)
    feed = mam.get_activity_feed(agent_id=agent_id, limit=limit)
    return json.dumps({"count": len(feed), "feed": feed}, ensure_ascii=False, indent=2)


HANDLERS["pangu_agent_activity"] = handle_agent_activity


async def handle_agent_search(server, drawers, arguments):
    """Agent感知搜索（仅搜索该Agent可见的记忆）"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    agent_id = arguments["agent_id"]
    query = arguments["query"]
    mam.ensure_agent(agent_id)
    all_mems = mam.read(agent_id)
    query_lower = query.lower()
    results = [
        {"id": m.id, "content": m.content[:100], "owner": m.owner, "scope": m.scope.value}
        for m in all_mems
        if query_lower in (m.content or "").lower()
    ]
    return json.dumps({"count": len(results), "results": results[:10]}, ensure_ascii=False, indent=2)


HANDLERS["pangu_agent_search"] = handle_agent_search


async def handle_agent_transfer(server, drawers, arguments):
    """跨Agent记忆转移"""
    from ...memory.multi_agent import get_multi_agent_memory

    mam = get_multi_agent_memory()
    from_agent = arguments["from_agent"]
    to_agent = arguments["to_agent"]
    memory_id = arguments["memory_id"]
    mam.ensure_agent(to_agent)
    mem = mam.get(from_agent, memory_id)
    if not mem:
        return json.dumps({"error": f"Memory {memory_id} not found or not visible"}, ensure_ascii=False)
    new_mem = mam.write(to_agent, mem.content, scope="shared", tags=mem.tags, references=[mem.id])
    return json.dumps(
        {
            "transferred": True,
            "from": from_agent,
            "to": to_agent,
            "new_id": new_mem.id,
            "original_id": mem.id,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_agent_transfer"] = handle_agent_transfer


async def handle_git_commit(server, drawers, arguments):
    """记录最近一次 git commit 到记忆"""
    from ...memory.git_hook import get_git_hook

    hook = get_git_hook(server.config)
    result = hook.record_commit(arguments.get("repo_path", "."))
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_git_commit"] = handle_git_commit


async def handle_git_push(server, drawers, arguments):
    """记录 git push 操作"""
    from ...memory.git_hook import get_git_hook

    hook = get_git_hook(server.config)
    result = hook.record_push(
        arguments.get("repo_path", "."),
        remote=arguments.get("remote", "origin"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


HANDLERS["pangu_git_push"] = handle_git_push


async def handle_git_recent(server, drawers, arguments):
    """查看最近的 git 操作记录"""
    from ...memory.git_hook import get_git_hook

    hook = get_git_hook(server.config)
    result = hook.get_recent(limit=arguments.get("limit", 10))
    return json.dumps({"count": len(result), "commits": result}, ensure_ascii=False, indent=2)


HANDLERS["pangu_git_recent"] = handle_git_recent


async def handle_git_stats(server, drawers, arguments):
    """查看 git 操作统计"""
    from ...memory.git_hook import get_git_hook

    hook = get_git_hook(server.config)
    return json.dumps(hook.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_git_stats"] = handle_git_stats


async def handle_inject_stats(server, drawers, arguments):
    """查看注入统计"""
    from ...memory.context_injector import get_context_injector

    injector = get_context_injector(server.config)
    return json.dumps(injector.get_injection_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_inject_stats"] = handle_inject_stats


async def handle_cache_stats(server, drawers, arguments):
    """查看搜索缓存统计"""
    from ...memory.search_cache import get_search_cache

    cache = get_search_cache()
    return json.dumps(cache.get_stats(), ensure_ascii=False, indent=2)


HANDLERS["pangu_cache_stats"] = handle_cache_stats


async def handle_cache_clear(server, drawers, arguments):
    """清空搜索缓存"""
    from ...memory.search_cache import get_search_cache

    cache = get_search_cache()
    cache.clear()
    return json.dumps({"status": "cleared"}, ensure_ascii=False, indent=2)


HANDLERS["pangu_cache_clear"] = handle_cache_clear


async def handle_error_recent(server, drawers, arguments):
    """查看最近的错误日志"""
    from ...memory.error_monitor import get_error_monitor

    monitor = get_error_monitor(server.config)
    errors = monitor.get_errors(
        tool=arguments.get("tool"),
        limit=arguments.get("limit", 20),
    )
    return json.dumps({"count": len(errors), "errors": errors}, ensure_ascii=False, indent=2)


HANDLERS["pangu_error_recent"] = handle_error_recent
