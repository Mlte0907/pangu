#!/usr/bin/env python3
"""自动拆分 mcp_server.py — 修复版

生成模式:
- TOOLS: 工具定义列表 (纯数据)
- HANDLERS: tool_name → async handler 函数字典
- handler函数签名: async def handler(server, drawers, arguments) -> str
- self → server, 去掉 if/elif 包装
"""
import ast
import json
import re
from pathlib import Path

SERVER = Path("/home/xiaoxin/pangu/pangu/server/mcp_server.py")
OUT = Path("/home/xiaoxin/pangu/pangu/server/handlers")

def read_source():
    return SERVER.read_text(encoding="utf-8")

def extract_tools_list(source):
    """从 tools() 方法提取工具定义"""
    tools = []
    in_tools = False
    depth = 0
    for line in source.split("\n"):
        if "def tools(self)" in line:
            in_tools = True
            depth = 0
            continue
        if not in_tools:
            continue
        if "return raw" in line:
            break
        # 提取 {"name": "pangu_xxx", "description": "xxx"} 或带 inputSchema 的
        # 用正则匹配
        m = re.search(r'\{"name":\s*"(pangu_\w+)"', line)
        if not m:
            continue
        name = m.group(1)
        # 提取 description
        d = re.search(r'"description":\s*"([^"]*)"', line)
        desc = d.group(1) if d else ""
        # 提取 inputSchema（如果有）
        schema = None
        if '"inputSchema"' in line:
            # 提取从 "inputSchema": 到行尾的内容
            idx = line.index('"inputSchema"')
            schema_str = line[idx:].split('"inputSchema":')[1].strip()
            # 去掉尾部的 }, 或 }
            schema_str = schema_str.rstrip()
            if schema_str.endswith("},"):
                schema_str = schema_str[:-1]
            elif schema_str.endswith("}"):
                pass
            try:
                schema = json.loads(schema_str)
            except:
                schema = None
        tools.append({"name": name, "description": desc, "schema": schema})
    return tools

def extract_handlers(source):
    """从 call_tool 提取 handler 代码块"""
    lines = source.split("\n")
    # 找 call_tool 起始
    start = None
    for i, line in enumerate(lines):
        if "async def call_tool(self, tool_name" in line:
            start = i
            break
    if start is None:
        return {}
    
    handlers = {}
    current_name = None
    current_lines = []
    base_indent = None
    
    for i in range(start + 1, len(lines)):
        line = lines[i]
        stripped = line.lstrip()
        
        # 匹配 if/elif tool_name == "pangu_xxx":
        m = re.match(r'(?:if|elif)\s+tool_name\s*==\s*"(pangu_\w+)"', stripped)
        if m:
            # 保存上一个 handler
            if current_name and current_lines:
                handlers[current_name] = current_lines
            current_name = m.group(1)
            current_lines = []
            base_indent = len(line) - len(stripped)
            continue
        
        if current_name is None:
            continue
        
        # 遇到 except/finally 或新的顶级语句则结束
        if stripped.startswith("except ") or stripped.startswith("finally:"):
            handlers[current_name] = current_lines
            current_name = None
            current_lines = []
            continue
        
        # 检查是否回到 call_tool 的缩进级别或遇到注释/空行后换域
        curr_indent = len(line) - len(stripped) if stripped else 999
        if stripped.startswith("return ") and curr_indent <= base_indent:
            current_lines.append(line)
            handlers[current_name] = current_lines
            current_name = None
            current_lines = []
            continue
        # 如果遇到与 if 同级的注释或空行，且当前handler已有return，结束
        if curr_indent == base_indent and stripped.startswith("#"):
            handlers[current_name] = current_lines
            current_name = None
            current_lines = []
            continue
        
        current_lines.append(line)
    
    if current_name and current_lines:
        handlers[current_name] = current_lines
    
    return handlers

def classify_tool(name):
    """将工具归入模块"""
    base = name.replace("pangu_", "")
    
    # 精确匹配
    RULES = [
        # Palace
        (["list_wings", "create_wing", "list_rooms", "create_room"], "palace"),
        # Memory
        (["add_memory", "search_memories", "recall", "wake_up"], "memory_ops"),
        # Wiki
        (["list_wiki_pages", "get_wiki_page", "create_wiki_page", "auto_generate_wiki"], "wiki"),
        # KG
        (["kg_add_entity", "kg_add_relation", "kg_query", "kg_neighbors", 
          "kg_auto_extract", "kg_cross_domain", "kg_similar_patterns"], "knowledge_graph"),
        # Search
        (["fts_", "hybrid_", "natural_query", "conversational_search", "memory_insights",
          "cluster_by_tags", "cluster_by_time", "hierarchical_cluster", "dedup_results",
          "explain_search", "search_suggestions", "rewrite_query", "suggest_queries",
          "rewrite_stats", "search_analytics_", "realtime_stats", "realtime_history",
          "rerank", "search_explain", "search_stats", "search_memories",
          "find_related", "cluster_memories", "recommend"], "search"),
        # LLM
        (["summarize", "classify", "insight", "llm_cache_", "debate_", "narrative_",
          "deep_emotion_"], "llm_tools"),
        # Timeline
        (["build_timeline", "find_causal_links", "event_chains", "timeline_query",
          "timeline_replay", "topic_replay", "highlight_reel",
          "temporal_", "causal_", "counterfactual", "root_cause"], "timeline"),
        # Quality
        (["detect_conflicts", "check_pair", "find_duplicates", "merge_duplicates",
          "similarity_check", "sanitize", "sanitize_check", "enhanced_contradictions",
          "trajectory_", "compress_by_tags", "reassess_importance", "compression_stats",
          "assess_quality", "batch_assess", "auto_fix", "quality_stats",
          "detect_duplicates", "quality_analyze", "quality_fix"], "quality"),
        # Analytics
        (["analyze", "health_check", "anomaly_detect", "growth_trend", "discover_patterns",
          "pattern_insights", "analyze_emotion", "emotion_stats", "predict_emotion",
          "recommend_interaction", "discover_knowledge", "generate_hypotheses",
          "learning_stats", "self_diagnose", "evolution_plan", "performance_trend",
          "evolution_stats", "predict_queries", "predict_forgetting", "hot_topics",
          "predictive_stats", "meta_observe", "meta_recommend", "meta_tune",
          "meta_insights", "meta_stats", "anomaly_scan", "anomaly_content",
          "anomaly_stats", "health_trend", "health_stats", "health_report",
          "benchmark", "error_stats", "dashboard_status"], "analytics"),
        # Consolidation
        (["consolidation_", "find_forgotten", "compress_memories", "detect_associations",
          "memory_importance", "fuse_topic", "progressive_summarize", "crystallize_knowledge",
          "importance_feedback", "auto_fusion", "validate_memories",
          "reconsolidation_", "resonance_", "distill_", "knowledge_synthesis",
          "synthesis_", "intent_", "creative_", "context_", "auto_inject",
          "forget_", "proactive_", "knowledge_drift"], "consolidation"),
        # IO
        (["export", "import", "backup", "list_backups", "restore_backup",
          "collect_file", "collect_dir", "collect_all", "collect_stats",
          "feishu_", "watch_", "env_check", "startup_validate",
          "auto_collect", "list_exports", "export_stats"], "io_tools"),
        # System
        (["stats", "graph", "identity", "system_health", "system_metrics",
          "config_", "schema_", "api_server_", "audit_", "access_patterns",
          "security_summary", "architecture_", "plugin_", "version_",
          "project_", "api_server_start"], "system"),
        # Embed
        (["onnx_", "embed_", "vector_index_"], "embed"),
        # Batch
        (["batch_scan", "batch_import", "batch_stats"], "batch"),
        # Multimodal
        (["ingest_", "image_", "video_", "audio_", "multimodal_",
          "content_extract", "summary_by_topic", "summary_timeline"], "multimodal"),
        # Session
        (["session_", "cross_session_", "auto_compress", "sync_",
          "event_stream_", "portal_", "git_hook", "autopilot_"], "session"),
    ]
    
    for prefixes, mod in RULES:
        for p in prefixes:
            if base.startswith(p.rstrip("_")) or base == p.rstrip("_"):
                return mod
            if p.endswith("_") and base.startswith(p):
                return mod
    
    return "advanced"

def clean_handler(code_lines, if_indent):
    """清理 handler 代码: 去掉 if/elif 行, 调整缩进, self→server
    处理 try/except 块: 保留内部代码但去 try/except 包装
    """
    # 第一遍: 找到 body 最小缩进
    body_indent = 999
    for line in code_lines:
        stripped = line.lstrip()
        if not stripped:
            continue
        if re.match(r'(?:if|elif)\s+tool_name\s*==', stripped):
            continue
        if stripped.startswith("try:") or stripped.startswith("except") or stripped.startswith("finally:"):
            continue
        curr = len(line) - len(stripped)
        if curr < body_indent:
            body_indent = curr
    
    if body_indent == 999:
        body_indent = if_indent + 4
    
    # 第二遍: 处理 try/except 块
    # 追踪 try 块缩进, 对 try 内部代码去一级缩进
    result = []
    in_try = False
    try_indent = 0
    for line in code_lines:
        stripped = line.lstrip()
        if not stripped:
            result.append("")
            continue
        
        # 跳过 if/elif 行
        if re.match(r'(?:if|elif)\s+tool_name\s*==', stripped):
            continue
        # 跳过 call_tool 的 else 兜底
        if stripped.startswith("else:") and "未知工具" in "".join(code_lines):
            break
        if "未知工具" in stripped or "未知方法" in stripped:
            break
        
        curr_indent = len(line) - len(stripped)
        
        # 检测 try: 行
        if stripped == "try:" or stripped.startswith("try:"):
            in_try = True
            try_indent = curr_indent
            continue
        
        # 检测 except/finally 行 (关闭 try 块)
        if stripped.startswith("except") or stripped.startswith("finally:"):
            in_try = False
            continue
        
        # 如果在 try 块内, 去掉 try 的一级缩进 (4空格)
        effective_indent = curr_indent
        if in_try and curr_indent > try_indent:
            effective_indent = curr_indent - 4  # 去掉 try 的一级
        
        # 归一化到函数体 (4空格)
        new_indent = max(0, 4 + (effective_indent - body_indent))
        
        # self → server
        new_line = " " * new_indent + stripped.replace("self.", "server.")
        
        # 延迟导入语句: 强制到4空格
        if stripped.startswith("from ") or stripped.startswith("import "):
            new_line = "    " + stripped
        
        result.append(new_line)
    
    return result

def gen_tools_dict(tools):
    """生成 TOOLS 列表"""
    lines = ["TOOLS = ["]
    for t in tools:
        name = t["name"]
        desc = t["description"]
        if t["schema"]:
            # 用 repr 生成安全的字符串
            schema_json = json.dumps(t["schema"], ensure_ascii=False)
            lines.append(f'    {{"name": {json.dumps(name)}, "description": {json.dumps(desc)}, "inputSchema": {schema_json}}},')
        else:
            lines.append(f'    {{"name": {json.dumps(name)}, "description": {json.dumps(desc)}}},')
    lines.append("]")
    return "\n".join(lines)

def main():
    source = read_source()
    all_tools = extract_tools_list(source)
    all_handlers = extract_handlers(source)
    
    print(f"Tools: {len(all_tools)}, Handlers: {len(all_handlers)}")
    
    # 分组
    modules = {}
    for t in all_tools:
        mod = classify_tool(t["name"])
        if mod not in modules:
            modules[mod] = {"tools": [], "handlers": {}}
        modules[mod]["tools"].append(t)
        if t["name"] in all_handlers:
            modules[mod]["handlers"][t["name"]] = all_handlers[t["name"]]
    
    # 生成文件
    OUT.mkdir(parents=True, exist_ok=True)
    
    for mod_name, data in sorted(modules.items(), key=lambda x: -len(x[1]["tools"])):
        tools = data["tools"]
        handlers = data["handlers"]
        
        content = []
        content.append(f'"""盘古 MCP Handler — {mod_name} ({len(tools)} tools)"""')
        content.append("import json\n")
        content.append(gen_tools_dict(tools))
        content.append("")
        content.append("HANDLERS = {}")
        
        for t in tools:
            name = t["name"]
            desc = t["description"]
            func_name = "handle_" + name.replace("pangu_", "").replace("-", "_")
            
            if name in handlers:
                # 有 handler 代码
                code = clean_handler(handlers[name], 12)  # if/elif 在 try 内, 缩进12空格
                content.append(f"")
                content.append(f'async def {func_name}(server, drawers, arguments):')
                content.append(f'    """{desc}"""')
                if code:
                    content.append("\n".join(code))
                else:
                    content.append('    return json.dumps({{"error": "not implemented"}})')
                content.append(f'HANDLERS[{json.dumps(name)}] = {func_name}')
            else:
                # 只有工具定义，无 handler（不应该发生，但保险）
                content.append(f"")
                content.append(f'async def {func_name}(server, drawers, arguments):')
                content.append(f'    """{desc}"""')
                content.append(f'    return json.dumps({{"error": "handler not found for {name}"}})')
                content.append(f'HANDLERS[{json.dumps(name)}] = {func_name}')
        
        file_path = OUT / f"{mod_name}.py"
        file_path.write_text("\n".join(content), encoding="utf-8")
        print(f"  {mod_name}.py: {len(tools)} tools ({len(handlers)} with handlers)")
    
    # __init__.py
    init_content = ['"""盘古 MCP Handler 路由"""', '', 'TOOLS = []', 'HANDLERS = {}', '']
    for mod_name in sorted(modules.keys()):
        init_content.append(f"from . import {mod_name}")
        init_content.append(f"TOOLS.extend({mod_name}.TOOLS)")
        init_content.append(f"HANDLERS.update({mod_name}.HANDLERS)")
    init_content.append(f"")
    init_content.append(f"TOTAL_TOOLS = len(TOOLS)")
    init_content.append(f"TOTAL_HANDLERS = len(HANDLERS)")
    (OUT / "__init__.py").write_text("\n".join(init_content), encoding="utf-8")
    
    print(f"\nGenerated {len(modules)} modules")

if __name__ == "__main__":
    main()
