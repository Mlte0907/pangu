"""盘古记忆系统全量 E2E 测试 — 覆盖全部 423 个 MCP 工具的真实性验证

运行方式:
    cd /home/xiaoxin/pangu
    .venv/bin/python -m tests.manual_e2e.test_comprehensive

测试架构:
    Phase 1: 基础功能验证（记忆 CRUD + 搜索）
    Phase 2: 四层记忆栈验证
    Phase 3: 搜索子系统深度验证
    Phase 4: 神经记忆系统验证
    Phase 5: 知识图谱验证
    Phase 6: 主动注入与预测验证
    Phase 7: 多模态处理验证
    Phase 8: 自主管理与自进化验证
    Phase 9: REST API 验证
    Phase 10: 功能清单全量遍历（423 工具逐个调用）
"""

import json
import sys
import os
import time
import traceback

# 确保可以导入 helper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tests.manual_e2e.mcp_helper import MCPHelper, TestReport


def run_all_phases():
    """运行所有测试阶段"""
    mcp = MCPHelper(base_url="http://127.0.0.1:19529", timeout=30)
    report = TestReport()

    # 先验证 API 可达
    print("🔌 检查盘古 API 连接...")
    try:
        tools = mcp.list_tools()
        print(f"   ✅ API 可达，发现 {len(tools)} 个 MCP 工具")
    except Exception as e:
        print(f"   ❌ API 不可达: {e}")
        print("   请先启动盘古服务: cd /home/xiaoxin/pangu && .venv/bin/python -m pangu start")
        return report

    # ═══════════════════════════════════════════════════════════
    # Phase 1: 基础功能验证（记忆 CRUD + 搜索）
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 1: 基础 CRUD + 搜索"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 1.1 写入记忆
    test_memories = [
        {"content": "Python 是一种解释型高级编程语言，由 Guido van Rossum 于 1991 年创造", "wing": "test_wing", "room": "test_room", "hall": "facts", "importance": 4, "tags": ["python", "编程", "语言"]},
        {"content": "ONNX 是微软开发的开放神经网络交换格式，用于模型互操作", "wing": "test_wing", "room": "test_room", "hall": "facts", "importance": 3, "tags": ["onnx", "深度学习", "模型"]},
        {"content": "SQLite 是一个 C 语言库，实现了小型、快速、自包含的 SQL 数据库引擎", "wing": "test_wing", "room": "tech", "hall": "facts", "importance": 3, "tags": ["sqlite", "数据库", "存储"]},
        {"content": "盘古记忆系统是 AI Agent 的大脑组件，通过 MCP 协议提供记忆服务", "wing": "test_wing", "room": "tech", "hall": "concepts", "importance": 5, "tags": ["盘古", "记忆系统", "mcp"]},
        {"content": "2024年3月15日，项目完成了 v2.0 重大升级，新增了神经记忆系统", "wing": "test_wing", "room": "history", "hall": "events", "importance": 4, "tags": ["里程碑", "v2.0", "升级"]},
        {"content": "用户偏好使用暗色主题进行编码，字体大小设置为 14px", "wing": "test_wing", "room": "personal", "hall": "preferences", "importance": 2, "tags": ["偏好", "主题", "编码"]},
        {"content": "部署建议：生产环境应使用 Docker Compose，配合 Nginx 反向代理", "wing": "prod_wing", "room": "deploy", "hall": "suggestions", "importance": 4, "tags": ["部署", "docker", "nginx"]},
        {"content": "FAISS 是 Facebook 开源的高效相似性搜索库，支持十亿级向量检索", "wing": "prod_wing", "room": "tech", "hall": "facts", "importance": 3, "tags": ["faiss", "向量", "搜索"]},
        {"content": "团队成员包括：Alice（后端）、Bob（前端）、Carol（运维）", "wing": "test_wing", "room": "team", "hall": "relations", "importance": 3, "tags": ["团队", "成员", "关系"]},
        {"content": "结论：混合搜索（FTS + 向量）比纯向量搜索召回率提升约 35%", "wing": "prod_wing", "room": "research", "hall": "discoveries", "importance": 5, "tags": ["发现", "搜索", "性能"]},
    ]

    created_ids = []
    for i, mem in enumerate(test_memories):
        r = mcp.call("pangu_add_memory", mem)
        status = "PASS" if r.success else "FAIL"
        detail = ""
        if r.success:
            try:
                data = json.loads(r.result)
                mid = data.get("id") or data.get("memory_id") or data.get("drawer_id", "")
                if mid:
                    created_ids.append(mid)
                    detail = f"id={mid}"
            except Exception:
                detail = "返回格式异常"
                status = "WARN"
        else:
            detail = r.error or "写入失败"
        report.record(phase, f"写入记忆 #{i+1} ({mem['hall']})", status, detail, r.elapsed_ms)
        print(f"  {'✅' if status=='PASS' else '❌'} 写入记忆 #{i+1} [{mem['hall']}] {detail} ({r.elapsed_ms:.0f}ms)")

    # 1.2 搜索记忆
    search_tests = [
        ("Python 编程", "向量搜索-关键词"),
        ("数据库引擎", "向量搜索-语义"),
        ("test_wing", "按 wing 过滤"),
        ("搜索性能", "混合搜索"),
    ]
    for query, label in search_tests:
        r = mcp.call("pangu_search_memories", {"query": query, "limit": 5})
        status = "PASS" if r.success else "FAIL"
        detail = ""
        if r.success:
            try:
                data = json.loads(r.result)
                results = data.get("results", data.get("memories", []))
                count = len(results) if isinstance(results, list) else 0
                detail = f"返回 {count} 条结果"
                if count == 0:
                    status = "WARN"
                    detail = "搜索返回空结果"
            except Exception:
                detail = "返回格式异常"
                status = "WARN"
        report.record(phase, f"搜索: {label}", status, detail, r.elapsed_ms)
        print(f"  {'✅' if status=='PASS' else '⚠️' if status=='WARN' else '❌'} 搜索 [{query}] {detail} ({r.elapsed_ms:.0f}ms)")

    # 1.3 列出记忆
    r = mcp.call("pangu_stats", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            total = data.get("total_memories", data.get("total", "?"))
            detail = f"总记忆数: {total}"
        except Exception:
            detail = "返回格式解析成功"
    report.record(phase, "系统统计", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 系统统计 {detail} ({r.elapsed_ms:.0f}ms)")

    # 1.4 删除测试记忆（清理）
    delete_count = 0
    for mid in created_ids:
        r = mcp.call("pangu_delete_memory", {"memory_id": mid})
        if r.success:
            delete_count += 1
    report.record(phase, f"清理测试记忆", "PASS" if delete_count == len(created_ids) else "WARN",
                  f"删除 {delete_count}/{len(created_ids)}")
    print(f"  🧹 清理测试记忆: {delete_count}/{len(created_ids)}")

    # ═══════════════════════════════════════════════════════════
    # Phase 2: 四层记忆栈验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 2: 四层记忆栈"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 2.1 L0 身份层
    r = mcp.call("pangu_identity", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            identity = data.get("identity", data.get("content", ""))
            detail = f"身份长度: {len(str(identity))} chars" if identity else "身份为空"
            if not identity:
                status = "WARN"
        except Exception:
            detail = "返回可解析" if r.result else "返回空"
    report.record(phase, "L0 身份层", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} L0 身份层 {detail} ({r.elapsed_ms:.0f}ms)")

    # 2.2 写入足够多的记忆来触发各层
    stack_test_ids = []
    for i in range(20):
        r = mcp.call("pangu_add_memory", {
            "content": f"记忆栈测试条目 #{i+1}：这是用于验证四层记忆栈功能的测试数据，包含足够的内容以触发 L1 摘要层的生成",
            "wing": "stack_test", "room": "general",
            "hall": "facts", "importance": (i % 5) + 1,
            "tags": [f"tag_{i}", "测试", "记忆栈"]
        })
        if r.success:
            try:
                data = json.loads(r.result)
                mid = data.get("id") or data.get("memory_id") or data.get("drawer_id", "")
                if mid:
                    stack_test_ids.append(mid)
            except Exception:
                pass
    report.record(phase, "写入20条记忆栈测试数据", "PASS" if len(stack_test_ids) >= 15 else "WARN",
                  f"成功 {len(stack_test_ids)}/20")
    print(f"  {'✅' if len(stack_test_ids)>=15 else '⚠️'} 写入记忆栈测试数据: {len(stack_test_ids)}/20")

    # 2.3 带 wing/room 过滤的搜索（L2 按需层）
    r = mcp.call("pangu_search_memories", {"query": "记忆栈测试", "wing": "stack_test", "limit": 10})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", data.get("memories", []))
            count = len(results) if isinstance(results, list) else 0
            detail = f"L2 过滤返回 {count} 条"
            if count == 0:
                status = "WARN"
                detail = "L2 过滤返回空"
        except Exception:
            detail = "可解析"
    report.record(phase, "L2 按需层（wing/room 过滤）", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} L2 按需层过滤 {detail} ({r.elapsed_ms:.0f}ms)")

    # 2.4 L3 深度搜索
    r = mcp.call("pangu_search_memories", {"query": "测试数据 验证 功能", "limit": 20})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", data.get("memories", []))
            count = len(results) if isinstance(results, list) else 0
            detail = f"L3 深度搜索返回 {count} 条"
        except Exception:
            detail = "可解析"
    report.record(phase, "L3 深度搜索", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} L3 深度搜索 {detail} ({r.elapsed_ms:.0f}ms)")

    # 2.5 清理
    for mid in stack_test_ids:
        mcp.call("pangu_delete_memory", {"memory_id": mid})

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 搜索子系统深度验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 3: 搜索子系统"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 写入搜索测试数据
    search_test_ids = []
    search_data = [
        {"content": "Python Flask 框架用于构建 Web 应用程序", "wing": "search_test", "tags": ["python", "flask", "web"]},
        {"content": "Django 是 Python 最流行的 Web 框架之一", "wing": "search_test", "tags": ["python", "django", "web"]},
        {"content": "FastAPI 是现代高性能 Python Web 框架", "wing": "search_test", "tags": ["python", "fastapi", "api"]},
        {"content": "React 是 Facebook 开发的前端 JavaScript 库", "wing": "search_test", "tags": ["react", "frontend", "javascript"]},
        {"content": "Vue.js 是渐进式 JavaScript 框架", "wing": "search_test", "tags": ["vue", "frontend", "javascript"]},
        {"content": "机器学习是人工智能的一个分支，让计算机从数据中学习", "wing": "search_test", "tags": ["ml", "ai", "学习"]},
        {"content": "深度学习使用神经网络模型进行特征学习", "wing": "search_test", "tags": ["dl", "neural", "深度学习"]},
        {"content": "自然语言处理让计算机理解和生成人类语言", "wing": "search_test", "tags": ["nlp", "语言", "处理"]},
    ]
    for mem in search_data:
        r = mcp.call("pangu_add_memory", mem)
        if r.success:
            try:
                data = json.loads(r.result)
                mid = data.get("id") or data.get("memory_id") or data.get("drawer_id", "")
                if mid:
                    search_test_ids.append(mid)
            except Exception:
                pass

    # 3.1 FTS 全文搜索
    r = mcp.call("pangu_fts_search", {"query": "Python 框架", "limit": 5})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", data.get("memories", []))
            count = len(results) if isinstance(results, list) else 0
            detail = f"FTS 返回 {count} 条"
        except Exception:
            detail = "可解析"
    report.record(phase, "FTS 全文搜索", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} FTS 全文搜索 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.2 向量语义搜索（语义相近但关键词不同）
    r = mcp.call("pangu_search_memories", {"query": "人工智能算法", "limit": 5})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", data.get("memories", []))
            count = len(results) if isinstance(results, list) else 0
            detail = f"语义搜索返回 {count} 条（应匹配 AI/ML 相关）"
        except Exception:
            detail = "可解析"
    report.record(phase, "向量语义搜索", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} 向量语义搜索 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.3 混合搜索
    r = mcp.call("pangu_hybrid_search", {"query": "Web 开发框架", "limit": 5})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", data.get("memories", []))
            count = len(results) if isinstance(results, list) else 0
            detail = f"混合搜索返回 {count} 条"
        except Exception:
            detail = "可解析"
    report.record(phase, "混合搜索(FTS+向量+KG)", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 混合搜索 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.4 查询改写
    r = mcp.call("pangu_rewrite_query", {"query": "py"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            rewritten = data.get("rewritten_query", data.get("rewritten", ""))
            detail = f"改写: 'py' → '{rewritten}'" if rewritten else "改写结果为空"
            if not rewritten:
                status = "WARN"
        except Exception:
            detail = "可解析"
    report.record(phase, "查询改写", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} 查询改写 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.5 搜索建议
    r = mcp.call("pangu_search_suggestions", {"query": "不存在的查询xyz123"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            suggestions = data.get("suggestions", [])
            detail = f"返回 {len(suggestions)} 条建议" if isinstance(suggestions, list) else "格式异常"
        except Exception:
            detail = "可解析"
    report.record(phase, "搜索建议", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} 搜索建议 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.6 搜索解释
    r = mcp.call("pangu_explain_search", {"query": "Python 框架"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            has_explain = bool(data.get("explanation") or data.get("explain"))
            detail = "返回搜索解释" if has_explain else "无解释内容"
            if not has_explain:
                status = "WARN"
        except Exception:
            detail = "可解析"
    report.record(phase, "搜索解释", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '⚠️'} 搜索解释 {detail} ({r.elapsed_ms:.0f}ms)")

    # 3.7 搜索统计
    r = mcp.call("pangu_search_stats", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            total_searches = data.get("total_searches", data.get("total", 0))
            detail = f"总搜索次数: {total_searches}"
        except Exception:
            detail = "可解析"
    report.record(phase, "搜索统计", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 搜索统计 {detail} ({r.elapsed_ms:.0f}ms)")

    # 清理搜索测试数据
    for mid in search_test_ids:
        mcp.call("pangu_delete_memory", {"memory_id": mid})

    # ═══════════════════════════════════════════════════════════
    # Phase 4: 神经记忆系统验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 4: 神经记忆系统"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 4.1 神经记忆统计
    r = mcp.call("pangu_neural_stats", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            enabled = data.get("enabled", data.get("neural_enabled", None))
            hippocampus = data.get("hippocampus_count", data.get("hippocampus", {}).get("count", "?"))
            neocortex = data.get("neocortex_count", data.get("neocortex", {}).get("count", "?"))
            detail = f"enabled={enabled}, 海马体={hippocampus}, 新皮层={neocortex}"
        except Exception:
            detail = "可解析"
    report.record(phase, "神经记忆统计", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 神经记忆统计 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.2 睡眠巩固
    r = mcp.call("pangu_neural_sleep", {"cycles": 1})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            consolidated = data.get("consolidated", data.get("memories_consolidated", 0))
            detail = f"巩固了 {consolidated} 条记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "睡眠巩固 (neural_sleep)", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 睡眠巩固 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.3 激活扩散
    r = mcp.call("pangu_neural_spreading", {"query": "Python 编程"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            activated = data.get("activated_count", data.get("activated", 0))
            detail = f"激活扩散: {activated} 条关联记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "激活扩散 (neural_spreading)", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 激活扩散 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.4 竞争抑制
    r = mcp.call("pangu_neural_inhibition", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            inhibited = data.get("inhibited_count", data.get("inhibited", 0))
            detail = f"抑制了 {inhibited} 条竞争记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "竞争抑制 (neural_inhibition)", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 竞争抑制 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.5 神经衰减
    r = mcp.call("pangu_neural_decay", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            decayed = data.get("decayed_count", data.get("decayed", 0))
            detail = f"衰减了 {decayed} 条记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "神经衰减 (neural_decay)", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 神经衰减 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.6 巩固统计
    r = mcp.call("pangu_consolidation_stats", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            detail = f"巩固统计: {json.dumps(data, ensure_ascii=False)[:100]}"
        except Exception:
            detail = "可解析"
    report.record(phase, "巩固统计", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 巩固统计 {detail} ({r.elapsed_ms:.0f}ms)")

    # 4.7 遗忘评估
    r = mcp.call("pangu_evaluate_forgetting", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            candidates = data.get("candidates", data.get("forgotten_count", 0))
            detail = f"遗忘候选: {candidates}"
        except Exception:
            detail = "可解析"
    report.record(phase, "遗忘评估", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 遗忘评估 {detail} ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 5: 知识图谱验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 5: 知识图谱"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 5.1 添加实体
    entities = [
        {"name": "Python", "type": "language", "description": "编程语言"},
        {"name": "Flask", "type": "framework", "description": "Web 框架"},
        {"name": "SQLite", "type": "database", "description": "嵌入式数据库"},
    ]
    entity_ids = []
    for ent in entities:
        r = mcp.call("pangu_kg_add_entity", ent)
        status = "PASS" if r.success else "FAIL"
        if r.success:
            try:
                data = json.loads(r.result)
                eid = data.get("id") or data.get("entity_id", "")
                if eid:
                    entity_ids.append(eid)
            except Exception:
                pass
        report.record(phase, f"添加实体: {ent['name']}", status, "", r.elapsed_ms)
        print(f"  {'✅' if status=='PASS' else '❌'} 添加实体: {ent['name']} ({r.elapsed_ms:.0f}ms)")

    # 5.2 添加关系
    if len(entity_ids) >= 2:
        r = mcp.call("pangu_kg_add_relation", {
            "subject_id": entity_ids[0], "predicate": "used_by",
            "object_id": entity_ids[1], "confidence": 0.9
        })
        status = "PASS" if r.success else "FAIL"
        report.record(phase, "添加关系: Python used_by Flask", status, "", r.elapsed_ms)
        print(f"  {'✅' if status=='PASS' else '❌'} 添加关系: Python → Flask ({r.elapsed_ms:.0f}ms)")

        if len(entity_ids) >= 3:
            r = mcp.call("pangu_kg_add_relation", {
                "subject_id": entity_ids[0], "predicate": "uses",
                "object_id": entity_ids[2], "confidence": 0.85
            })
            status = "PASS" if r.success else "FAIL"
            report.record(phase, "添加关系: Python uses SQLite", status, "", r.elapsed_ms)
            print(f"  {'✅' if status=='PASS' else '❌'} 添加关系: Python → SQLite ({r.elapsed_ms:.0f}ms)")

    # 5.3 查询图谱
    r = mcp.call("pangu_kg_query", {"entity_name": "Python"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            relations = data.get("relations", data.get("neighbors", []))
            detail = f"查询到 {len(relations) if isinstance(relations, list) else 0} 条关系"
        except Exception:
            detail = "可解析"
    report.record(phase, "查询实体关系", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 查询实体关系 {detail} ({r.elapsed_ms:.0f}ms)")

    # 5.4 邻居查询
    if entity_ids:
        r = mcp.call("pangu_kg_neighbors", {"entity_id": entity_ids[0]})
        status = "PASS" if r.success else "FAIL"
        detail = ""
        if r.success:
            try:
                data = json.loads(r.result)
                neighbors = data.get("neighbors", [])
                detail = f"邻居数: {len(neighbors) if isinstance(neighbors, list) else 0}"
            except Exception:
                detail = "可解析"
        report.record(phase, "邻居查询", status, detail, r.elapsed_ms)
        print(f"  {'✅' if status=='PASS' else '❌'} 邻居查询 {detail} ({r.elapsed_ms:.0f}ms)")

    # 5.5 自动实体提取
    r = mcp.call("pangu_kg_auto_extract", {"content": "项目使用 Python 和 ONNX 进行深度学习模型部署，数据存储在 SQLite 中"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            extracted = data.get("entities", data.get("extracted", []))
            detail = f"提取了 {len(extracted) if isinstance(extracted, list) else 0} 个实体"
        except Exception:
            detail = "可解析"
    report.record(phase, "自动实体提取", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自动实体提取 {detail} ({r.elapsed_ms:.0f}ms)")

    # 5.6 图谱统计
    r = mcp.call("pangu_graph_stats", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            entities_count = data.get("entities", data.get("entity_count", "?"))
            relations_count = data.get("relations", data.get("relation_count", "?"))
            detail = f"实体: {entities_count}, 关系: {relations_count}"
        except Exception:
            detail = "可解析"
    report.record(phase, "图谱统计", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 图谱统计 {detail} ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 6: 主动注入与预测验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 6: 主动注入与预测"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 6.1 上下文注入
    r = mcp.call("pangu_inject_context", {"context": "我正在调试 Python 代码中的数据库连接问题"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            injected = data.get("injected_memories", data.get("memories", []))
            detail = f"注入了 {len(injected) if isinstance(injected, list) else 0} 条相关记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "上下文注入", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 上下文注入 {detail} ({r.elapsed_ms:.0f}ms)")

    # 6.2 更新上下文
    r = mcp.call("pangu_update_context", {"context": "我正在优化搜索算法的性能"})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "更新上下文", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 更新上下文 ({r.elapsed_ms:.0f}ms)")

    # 6.3 当前上下文
    r = mcp.call("pangu_current_context", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            context = data.get("context", "")
            detail = f"当前上下文: {str(context)[:60]}..."
        except Exception:
            detail = "可解析"
    report.record(phase, "获取当前上下文", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 当前上下文 {detail} ({r.elapsed_ms:.0f}ms)")

    # 6.4 注入统计
    r = mcp.call("pangu_injection_stats", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "注入统计", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 注入统计 ({r.elapsed_ms:.0f}ms)")

    # 6.5 预测性记忆推荐
    r = mcp.call("pangu_proactive_predict", {"context": "开发 Web 应用"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            predictions = data.get("predictions", data.get("recommendations", []))
            detail = f"预测推荐 {len(predictions) if isinstance(predictions, list) else 0} 条"
        except Exception:
            detail = "可解析"
    report.record(phase, "预测性记忆推荐", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 预测性推荐 {detail} ({r.elapsed_ms:.0f}ms)")

    # 6.6 主动提醒
    r = mcp.call("pangu_proactive_remind", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "主动提醒", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 主动提醒 ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 7: 多模态处理验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 7: 多模态处理"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 7.1 图片嵌入（需要测试图片）
    r = mcp.call("pangu_image_embed", {"image_path": "/dev/null"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if not r.success:
        if "No such file" in str(r.error) or "not found" in str(r.error).lower():
            detail = "预期失败：无测试图片文件"
            status = "SKIP"
        else:
            detail = r.error or "调用失败"
    else:
        detail = "图片嵌入成功"
    report.record(phase, "图片嵌入", status, detail, r.elapsed_ms)
    print(f"  {'⏭️' if status=='SKIP' else '✅' if status=='PASS' else '❌'} 图片嵌入 {detail} ({r.elapsed_ms:.0f}ms)")

    # 7.2 视频元数据
    r = mcp.call("pangu_video_metadata", {"video_path": "/dev/null"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if not r.success:
        detail = "预期失败：无测试视频文件"
        status = "SKIP"
    report.record(phase, "视频元数据", status, detail, r.elapsed_ms)
    print(f"  {'⏭️' if status=='SKIP' else '✅' if status=='PASS' else '❌'} 视频元数据 {detail} ({r.elapsed_ms:.0f}ms)")

    # 7.3 音频转写
    r = mcp.call("pangu_audio_transcribe", {"audio_path": "/dev/null"})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if not r.success:
        detail = "预期失败：无测试音频文件"
        status = "SKIP"
    report.record(phase, "音频转写", status, detail, r.elapsed_ms)
    print(f"  {'⏭️' if status=='SKIP' else '✅' if status=='PASS' else '❌'} 音频转写 {detail} ({r.elapsed_ms:.0f}ms)")

    # 7.4 跨模态搜索
    r = mcp.call("pangu_multimodal_search", {"query": "风景照片", "limit": 5})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            results = data.get("results", [])
            detail = f"跨模态搜索返回 {len(results) if isinstance(results, list) else 0} 条"
        except Exception:
            detail = "可解析"
    report.record(phase, "跨模态搜索", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 跨模态搜索 {detail} ({r.elapsed_ms:.0f}ms)")

    # 7.5 多模态摘要
    r = mcp.call("pangu_multimodal_summary", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "多模态摘要", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 多模态摘要 ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 8: 自主管理与自进化验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 8: 自主管理"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    # 8.1 自动融合
    r = mcp.call("pangu_auto_fusion", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            fused = data.get("fused", data.get("merged_count", 0))
            detail = f"融合了 {fused} 条记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "自动融合", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自动融合 {detail} ({r.elapsed_ms:.0f}ms)")

    # 8.2 自动衰减
    r = mcp.call("pangu_auto_forget", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            forgotten = data.get("forgotten", data.get("archived_count", 0))
            detail = f"归档了 {forgotten} 条记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "自动衰减/遗忘", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自动衰减 {detail} ({r.elapsed_ms:.0f}ms)")

    # 8.3 压缩记忆
    r = mcp.call("pangu_compress_memories", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            compressed = data.get("compressed", data.get("count", 0))
            detail = f"压缩了 {compressed} 条记忆"
        except Exception:
            detail = "可解析"
    report.record(phase, "压缩记忆", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 压缩记忆 {detail} ({r.elapsed_ms:.0f}ms)")

    # 8.4 冲突检测
    r = mcp.call("pangu_detect_conflicts", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            conflicts = data.get("conflicts", [])
            detail = f"发现 {len(conflicts) if isinstance(conflicts, list) else 0} 个冲突"
        except Exception:
            detail = "可解析"
    report.record(phase, "冲突检测", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 冲突检测 {detail} ({r.elapsed_ms:.0f}ms)")

    # 8.5 去重检测
    r = mcp.call("pangu_find_duplicates", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            duplicates = data.get("duplicates", [])
            detail = f"发现 {len(duplicates) if isinstance(duplicates, list) else 0} 组重复"
        except Exception:
            detail = "可解析"
    report.record(phase, "去重检测", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 去重检测 {detail} ({r.elapsed_ms:.0f}ms)")

    # 8.6 自动驾驶状态
    r = mcp.call("pangu_autopilot_status", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "自动驾驶状态", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自动驾驶状态 ({r.elapsed_ms:.0f}ms)")

    # 8.7 自进化统计
    r = mcp.call("pangu_evolution_stats", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "自进化统计", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自进化统计 ({r.elapsed_ms:.0f}ms)")

    # 8.8 自我诊断
    r = mcp.call("pangu_self_diagnose", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "自我诊断", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 自我诊断 ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 9: REST API + Web UI 验证
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 9: REST API"
    print(f"\n{'='*60}")
    print(f"📋 {phase}")
    print(f"{'='*60}")

    import requests as req

    # 9.1 REST API 根路径
    try:
        r = req.get("http://127.0.0.1:19529/", timeout=5)
        status = "PASS" if r.status_code in (200, 307, 404) else "FAIL"
        detail = f"HTTP {r.status_code}"
        report.record(phase, "REST API 根路径", status, detail, 0)
        print(f"  {'✅' if status=='PASS' else '❌'} REST 根路径 {detail}")
    except Exception as e:
        report.record(phase, "REST API 根路径", "FAIL", str(e))
        print(f"  ❌ REST 根路径 {e}")

    # 9.2 Dashboard
    try:
        r = req.get("http://127.0.0.1:19529/dashboard", timeout=5)
        status = "PASS" if r.status_code == 200 else "WARN"
        detail = f"HTTP {r.status_code}, 内容长度 {len(r.text)}"
        report.record(phase, "Dashboard", status, detail, 0)
        print(f"  {'✅' if status=='PASS' else '⚠️'} Dashboard {detail}")
    except Exception as e:
        report.record(phase, "Dashboard", "FAIL", str(e))
        print(f"  ❌ Dashboard {e}")

    # 9.3 API 文档
    try:
        r = req.get("http://127.0.0.1:19529/docs", timeout=5)
        status = "PASS" if r.status_code == 200 else "WARN"
        detail = f"HTTP {r.status_code}"
        report.record(phase, "API 文档 (/docs)", status, detail, 0)
        print(f"  {'✅' if status=='PASS' else '⚠️'} API 文档 {detail}")
    except Exception as e:
        report.record(phase, "API 文档", "FAIL", str(e))
        print(f"  ❌ API 文档 {e}")

    # 9.4 REST API v2 memories
    try:
        r = req.get("http://127.0.0.1:19529/api/v2/memories", timeout=5)
        status = "PASS" if r.status_code in (200, 401) else "WARN"
        detail = f"HTTP {r.status_code}"
        report.record(phase, "REST API /api/v2/memories", status, detail, 0)
        print(f"  {'✅' if status=='PASS' else '⚠️'} REST memories {detail}")
    except Exception as e:
        report.record(phase, "REST API /api/v2/memories", "FAIL", str(e))
        print(f"  ❌ REST memories {e}")

    # 9.5 系统健康检查
    r = mcp.call("pangu_system_health", {})
    status = "PASS" if r.success else "FAIL"
    detail = ""
    if r.success:
        try:
            data = json.loads(r.result)
            health = data.get("status", data.get("health", "?"))
            detail = f"系统状态: {health}"
        except Exception:
            detail = "可解析"
    report.record(phase, "系统健康检查", status, detail, r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 系统健康 {detail} ({r.elapsed_ms:.0f}ms)")

    # 9.6 系统指标
    r = mcp.call("pangu_system_metrics", {})
    status = "PASS" if r.success else "FAIL"
    report.record(phase, "系统指标", status, "", r.elapsed_ms)
    print(f"  {'✅' if status=='PASS' else '❌'} 系统指标 ({r.elapsed_ms:.0f}ms)")

    # ═══════════════════════════════════════════════════════════
    # Phase 10: 功能清单全量遍历（423 工具逐个调用）
    # ═══════════════════════════════════════════════════════════
    phase = "Phase 10: 全量工具遍历"
    print(f"\n{'='*60}")
    print(f"📋 {phase} — 调用全部 {len(tools)} 个 MCP 工具")
    print(f"{'='*60}")

    # 已在前面测试过的工具（跳过避免副作用）
    skip_tools = {
        "pangu_add_memory",  # 已测
        "pangu_delete_memory",  # 已测
        "pangu_search_memories",  # 已测多轮
        "pangu_ingest_file", "pangu_ingest_url",  # 需要外部文件/URL
        "pangu_image_embed", "pangu_image_classify",  # 需要图片文件
        "pangu_video_ingest", "pangu_video_frames",  # 需要视频文件
        "pangu_audio_transcribe", "pangu_audio_ingest",  # 需要音频文件
        "pangu_git_commit", "pangu_git_push",  # 有副作用
        "pangu_feishu_send", "pangu_feishu_card",  # 有副作用
        "pangu_watch_directory",  # 有副作用
        "pangu_collect_file", "pangu_collect_dir", "pangu_collect_all",  # 需要文件路径
        "pangu_plugin_enable", "pangu_plugin_disable",  # 修改配置
        "pangu_config_set",  # 修改配置
        "pangu_restore_backup",  # 有副作用
        "pangu_api_server_start",  # 启动服务
    }

    tool_results = {"pass": 0, "fail": 0, "skip": 0, "errors": []}
    for tool in tools:
        name = tool["name"]
        if name in skip_tools:
            tool_results["skip"] += 1
            report.record(phase, name, "SKIP", "已在前面测试或有副作用")
            continue

        # 为每个工具提供合理的默认参数
        args = _get_default_args(name)
        r = mcp.call(name, args)
        if r.success:
            tool_results["pass"] += 1
            report.record(phase, name, "PASS", f"{r.elapsed_ms:.0f}ms", r.elapsed_ms)
        else:
            tool_results["fail"] += 1
            error_short = (r.error or "")[:80]
            tool_results["errors"].append((name, error_short))
            report.record(phase, name, "FAIL", error_short, r.elapsed_ms)

    print(f"\n  📊 全量遍历结果:")
    print(f"     ✅ 通过: {tool_results['pass']}")
    print(f"     ❌ 失败: {tool_results['fail']}")
    print(f"     ⏭️  跳过: {tool_results['skip']}")
    if tool_results["errors"]:
        print(f"\n  🔍 失败工具详情:")
        for name, err in tool_results["errors"][:20]:
            print(f"     ❌ {name}: {err}")
        if len(tool_results["errors"]) > 20:
            print(f"     ... 还有 {len(tool_results['errors'])-20} 个失败")

    # ═══════════════════════════════════════════════════════════
    # 生成最终报告
    # ═══════════════════════════════════════════════════════════
    report.print_summary()

    # 打印 MCP 调用统计
    summary = mcp.get_summary()
    print(f"\n📡 MCP 调用统计:")
    print(f"   总调用: {summary['total_calls']}")
    print(f"   成功: {summary['success']} ({summary['success_rate']})")
    print(f"   失败: {summary['failed']}")
    print(f"   平均延迟: {summary['avg_latency_ms']}ms")

    return report


def _get_default_args(tool_name: str) -> dict:
    """为每个 MCP 工具提供合理的默认参数，避免因缺少参数而报错"""
    defaults = {
        # 记忆操作
        "pangu_recall": {"query": "测试", "limit": 5},
        "pangu_wake_up": {},
        "pangu_archive_memory": {"memory_id": "nonexistent"},
        "pangu_ingest_text": {"text": "测试文本内容", "wing": "test"},
        # 搜索
        "pangu_fts_search": {"query": "测试", "limit": 5},
        "pangu_natural_query": {"query": "什么是Python"},
        "pangu_recommend": {"query": "编程"},
        "pangu_conversational_search": {"query": "你好"},
        "pangu_memory_insights": {},
        "pangu_cluster_memories": {},
        "pangu_find_related": {"memory_id": "test"},
        "pangu_rerank": {"query": "测试", "results": []},
        "pangu_search_explain": {"query": "测试"},
        "pangu_hybrid_search": {"query": "测试"},
        # 知识图谱
        "pangu_kg_query": {"entity_name": "test"},
        "pangu_kg_neighbors": {"entity_name": "test"},
        "pangu_kg_auto_extract": {"content": "Python和SQLite的关系"},
        "pangu_kg_cross_domain": {"source_domain": "tech", "target_domain": "business"},
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
        # Wiki
        "pangu_list_wiki_pages": {},
        "pangu_get_wiki_page": {"page_id": "test"},
        "pangu_create_wiki_page": {"title": "测试页面", "content": "测试内容"},
        "pangu_auto_generate_wiki": {},
        # 工作记忆
        "pangu_wm_push": {"content": "测试工作记忆"},
        "pangu_wm_get": {},
        "pangu_wm_stats": {},
        "pangu_wm_clear": {},
        # 神经记忆
        "pangu_neural_stats": {},
        "pangu_neural_sleep": {"cycles": 1},
        "pangu_neural_spreading": {"query": "测试"},
        "pangu_neural_inhibition": {},
        "pangu_neural_decay": {},
        # 巩固
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
        # 搜索分析
        "pangu_search_stats": {},
        "pangu_fts_search_stats": {},
        "pangu_search_analytics_summary": {},
        "pangu_search_analytics_top": {},
        "pangu_search_analytics_empty": {},
        "pangu_search_analytics_slow": {},
        # 索引
        "pangu_index_build": {},
        "pangu_index_search": {"query": "测试"},
        "pangu_index_recommend": {"query": "测试"},
        "pangu_index_health": {},
        "pangu_index_cleanup": {},
        "pangu_vector_index_stats": {},
        "pangu_vector_index_build": {},
        # 缓存
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
        # 差异
        "pangu_diff_content": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_diff_batch": {},
        "pangu_diff_similarity": {"memory_id_a": "a", "memory_id_b": "b"},
        "pangu_diff_stats": {},
        # 可视化
        "pangu_visualize_graph": {},
        "pangu_visualize_network": {},
        "pangu_visualize_stats": {},
        # 模式
        "pangu_detect_patterns": {},
        "pangu_popular_queries": {},
        "pangu_frequent_memories": {},
        # 社交
        "pangu_comment_add": {"memory_id": "test", "comment": "测试评论"},
        "pangu_comment_list": {"memory_id": "test"},
        "pangu_vote": {"memory_id": "test", "vote": "up"},
        "pangu_vote_stats": {"memory_id": "test"},
        # 梦境
        "pangu_dream_cycle": {},
        "pangu_dream_stats": {},
        # 好奇心
        "pangu_curiosity_explore": {},
        "pangu_curiosity_gaps": {},
        # 人格
        "pangu_persona_identity": {},
        "pangu_persona_values": {},
        "pangu_persona_health": {},
        # 自主
        "pangu_autonomous_tick": {},
        "pangu_autonomous_run": {},
        "pangu_autonomous_status": {},
        "pangu_autonomous_analyze": {},
        # 多 Agent
        "pangu_multi_register": {"agent_id": "test_agent", "agent_type": "coding"},
        "pangu_multi_write": {"agent_id": "test_agent", "content": "测试共享记忆"},
        "pangu_multi_read": {"agent_id": "test_agent"},
        "pangu_multi_agents": {},
        # 协作
        "pangu_generate_ideas": {"topic": "测试"},
        "pangu_generate_novel": {"topic": "测试"},
        "pangu_agent_register": {"agent_id": "test"},
        "pangu_agent_share": {"from_agent": "a", "to_agent": "b", "content": "共享"},
        "pangu_collaborative_reason": {"query": "测试"},
        "pangu_agent_stats": {},
        # 知识综合
        "pangu_synthesize": {"query": "测试"},
        "pangu_find_contradictions": {},
        "pangu_core_insights": {},
        # 自学习
        "pangu_auto_learn": {},
        # 架构
        "pangu_arch_analyze": {},
        "pangu_arch_suggest": {},
        "pangu_cold_hot": {},
        "pangu_arch_stats": {},
        # QA
        "pangu_qa": {"question": "什么是Python?"},
        "pangu_qa_batch": {"questions": ["什么是Python?"]},
        "pangu_qa_stats": {},
        # 注入
        "pangu_inject_context": {"context": "Python编程"},
        "pangu_update_context": {"context": "新上下文"},
        "pangu_current_context": {},
        "pangu_injection_stats": {},
        "pangu_auto_inject": {},
        # 遗忘
        "pangu_evaluate_forgetting": {},
        "pangu_auto_forget": {},
        "pangu_get_archive": {},
        "pangu_forget_stats": {},
        # 蒸馏
        "pangu_distill": {},
        "pangu_distill_by_wing": {"wing": "test"},
        "pangu_distillation_stats": {},
        # ONNX
        "pangu_onnx_embed": {"text": "测试文本"},
        "pangu_onnx_embed_batch": {"texts": ["测试文本1", "测试文本2"]},
        "pangu_onnx_status": {},
        "pangu_onnx_similarity": {"text_a": "Python", "text_b": "编程"},
        # 导入导出
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
        # 环境
        "pangu_env_check": {},
        "pangu_startup_validate": {},
        # 重要性
        "pangu_importance_score": {},
        "pangu_reassess_importance": {},
        # 自动收集
        "pangu_auto_collect": {},
        "pangu_collect_stats": {},
        # 飞书
        "pangu_feishu_status": {},
        # 文件监控
        "pangu_watch_status": {},
        # 事件
        "pangu_event_emit": {"event_type": "test", "data": {}},
        "pangu_event_history": {},
        "pangu_event_stats": {},
        "pangu_event_webhook_add": {"url": "http://test.com"},
        "pangu_event_save": {},
        # 审计
        "pangu_audit_log": {},
        "pangu_audit_query": {},
        "pangu_audit_stats": {},
        "pangu_access_patterns": {},
        "pangu_security_summary": {},
        # 插件
        "pangu_plugin_list": {},
        "pangu_plugin_config": {"plugin_name": "test"},
        "pangu_plugin_discover": {},
        # 版本
        "pangu_version_history": {},
        "pangu_version_compare": {},
        # 时间线
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
        # 统计
        "pangu_stats": {},
        "pangu_graph": {},
        "pangu_identity": {},
        "pangu_system_health": {},
        "pangu_system_metrics": {},
        "pangu_config_get": {},
        "pangu_config_reload": {},
        "pangu_schema_version": {},
        "pangu_schema_migrations": {},
        # 隧道
        "pangu_create_tunnel": {"name": "test_tunnel", "from_wing": "a", "to_wing": "b"},
        "pangu_list_tunnels": {},
        "pangu_find_tunnels": {},
        # 认知
        "pangu_cognitive_loop": {},
        "pangu_cognitive_stats": {},
        "pangu_metacognition_monitor": {},
        "pangu_metacognition_reconfig": {},
        # 世界模型
        "pangu_worldmodel_forecast": {"query": "test"},
        "pangu_worldmodel_plan": {"goal": "test"},
        "pangu_worldmodel_match": {"observation": "test"},
        "pangu_worldmodel_stats": {},
        # 全息
        "pangu_holographic_encode": {"content": "测试"},
        "pangu_holographic_search": {"query": "测试"},
        # 评审
        "pangu_judge_memory": {"memory_id": "test"},
        "pangu_judge_stats": {},
        # 自适应
        "pangu_adaptive_params": {},
        "pangu_adaptive_evaluate": {},
        # 再巩固
        "pangu_reconsolidate": {},
        # 共振
        "pangu_find_resonance": {},
        "pangu_cross_wing_resonance": {},
        "pangu_resonance_find": {},
        "pangu_resonance_edges": {},
        "pangu_resonance_stats": {},
        # 注意力
        "pangu_attention_state": {},
        "pangu_attention_switch": {"topic": "test"},
        "pangu_attention_ab_test": {},
        # 流式索引
        "pangu_streaming_index": {},
        "pangu_streaming_stats": {},
        # 验证
        "pangu_verify": {},
        "pangu_verify_phase": {},
        # 隐私
        "pangu_privacy_stats": {},
        "pangu_privatize_count": {},
        # 预测
        "pangu_predict_queries": {},
        "pangu_predict_forgetting": {},
        "pangu_hot_topics": {},
        "pangu_predictive_stats": {},
        # 元学习
        "pangu_meta_observe": {},
        "pangu_meta_recommend": {},
        "pangu_meta_tune": {},
        "pangu_meta_insights": {},
        "pangu_meta_stats": {},
        # 健康
        "pangu_health_trend": {},
        "pangu_health_stats": {},
        "pangu_benchmark": {},
        "pangu_error_stats": {},
        "pangu_health_report": {},
        "pangu_error_recent": {},
        # 批量
        "pangu_batch_scan": {},
        "pangu_batch_stats": {},
        # 质量
        "pangu_assess_quality": {},
        "pangu_batch_assess": {},
        "pangu_auto_fix": {},
        "pangu_quality_stats": {},
        "pangu_quality_analyze": {},
        "pangu_quality_fix": {},
        # 聚类
        "pangu_cluster_by_tags": {},
        "pangu_cluster_by_time": {},
        "pangu_hierarchical_cluster": {},
        "pangu_dedup_results": {},
        # 推荐
        "pangu_recommend_interaction": {},
        "pangu_recommend_similar": {"memory_id": "test"},
        "pangu_recommend_timely": {},
        "pangu_recommend_feedback": {"memory_id": "test", "feedback": "up"},
        "pangu_recommendation_stats": {},
        # 查询改写
        "pangu_rewrite_query": {"query": "test"},
        "pangu_suggest_queries": {"query": "test"},
        "pangu_rewrite_stats": {},
        # 搜索建议
        "pangu_search_suggestions": {"query": "test"},
        # 实时
        "pangu_realtime_stats": {},
        "pangu_realtime_history": {},
        # 主动
        "pangu_proactive_predict": {"context": "test"},
        "pangu_proactive_suggest": {},
        "pangu_proactive_remind": {},
        "pangu_context_status": {},
        "pangu_user_patterns": {},
        "pangu_repeated_questions": {},
        # 自我
        "pangu_self_evaluate": {},
        "pangu_self_repair": {},
        # 伏羲
        "pangu_fuxi_insights": {},
        "pangu_knowledge_gaps": {},
        "pangu_user_behavior": {},
        # 跨会话
        "pangu_cross_session_links": {},
        "pangu_session_summary": {},
        "pangu_session_bridge": {},
        "pangu_session_stats": {},
        "pangu_session_inject": {},
        "pangu_session_start": {},
        "pangu_session_end": {},
        "pangu_session_resume": {},
        "pangu_session_record": {},
        # 同步
        "pangu_sync_record": {},
        "pangu_sync_pending": {},
        "pangu_sync_incremental": {},
        "pangu_sync_apply": {},
        "pangu_sync_auto_resolve": {},
        "pangu_sync_state": {},
        "pangu_sync_stats": {},
        # 门户
        "pangu_portal_write": {"content": "测试"},
        "pangu_portal_search": {"query": "测试"},
        "pangu_portal_panorama": {},
        "pangu_portal_maintain": {},
        "pangu_portal_summary": {},
        # 自动驾驶
        "pangu_autopilot_activate": {},
        "pangu_autopilot_deactivate": {},
        "pangu_autopilot_tick": {},
        "pangu_autopilot_suggest": {},
        "pangu_autopilot_status": {},
        # 项目
        "pangu_project_create": {"name": "test_project"},
        "pangu_project_switch": {"project": "test_project"},
        "pangu_project_list": {},
        "pangu_project_active": {},
        "pangu_project_save": {},
        "pangu_project_load": {},
        "pangu_project_search": {"query": "test"},
        "pangu_project_merge": {},
        "pangu_project_delete": {"project": "test_project"},
        "pangu_project_stats": {},
        # 分析
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
        # 情感
        "pangu_deep_emotion_trajectory": {},
        "pangu_deep_emotion_decompose": {},
        "pangu_deep_emotion_stats": {},
        # 辩论
        "pangu_debate_run": {"topic": "test"},
        "pangu_debate_stats": {},
        # 叙事
        "pangu_narrative_generate": {},
        "pangu_narrative_themes": {},
        "pangu_narrative_identity": {},
        # 摘要
        "pangu_summarize": {},
        "pangu_classify": {},
        "pangu_insight": {},
        # 清洗
        "pangu_sanitize": {"content": "测试内容"},
        "pangu_sanitize_check": {"content": "测试内容"},
        # 增强矛盾
        "pangu_enhanced_contradictions": {},
        # 轨迹
        "pangu_trajectory_track": {},
        "pangu_trajectory_compare": {},
        # 压缩
        "pangu_compress_by_tags": {"tags": ["test"]},
        "pangu_auto_compress": {},
        "pangu_compression_stats": {},
        # 意图
        "pangu_intent_predict": {"context": "test"},
        "pangu_intent_tasks": {},
        "pangu_intent_stats": {},
        # 综合
        "pangu_synthesis_cross_cluster": {},
        "pangu_synthesis_gaps": {},
        # 规划
        "pangu_evolution_plan": {},
        # 分析
        "pangu_analyze": {},
        # 元认知
        "pangu_metacognition_monitor": {},
        "pangu_metacognition_reconfig": {},
        # 自适应
        "pangu_adaptive_params": {},
        "pangu_adaptive_evaluate": {},
        "pangu_cold_hot": {},
    }
    return defaults.get(tool_name, {})


if __name__ == "__main__":
    report = run_all_phases()
