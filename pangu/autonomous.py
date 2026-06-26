#!/usr/bin/env python3
"""盘古自主判断引擎 — 根据任务类型自动决定调用哪些能力（伏羲移植）

当任务涉及复杂决策时，建议使用多轨迹决策。
"""

import json
import os
import sys

import httpx

PANGU_API = os.environ.get("PANGU_API_URL", "http://localhost:8866")
PANGU_KEY = os.environ.get("PANGU_API_KEY", "")

# 能力映射场景
CAPABILITY_SCENARIOS = {
    "memory_recall": {
        "keywords": ["记忆", "之前", "上次", "过去", "历史", "记得", "检索", "查询"],
        "capability": "recall",
        "action": "search_memories",
    },
    "self_reflection": {
        "keywords": ["反思", "复盘", "回顾", "思考自己", "总结", "成长"],
        "capability": "analytics",
        "action": "analyze_patterns",
    },
    "knowledge_distill": {
        "keywords": ["知识", "概念", "理论", "理解", "解释", "原理"],
        "capability": "wiki",
        "action": "generate_wiki",
    },
    "pattern_discovery": {
        "keywords": ["模式", "规律", "趋势", "习惯", "关联"],
        "capability": "patterns",
        "action": "discover_patterns",
    },
    "conflict_resolution": {
        "keywords": ["矛盾", "冲突", "不一致", "矛盾点"],
        "capability": "conflict",
        "action": "detect_conflicts",
    },
}

# 需要深度决策的关键词
DECISION_KEYWORDS = [
    "重构",
    "重写",
    "迁移",
    "设计方案",
    "架构",
    "多个",
    "方案",
    "选择",
    "对比",
    "权衡",
    "分析",
    "评估",
    "优化",
    "改进",
    "升级",
]

# 复杂任务特征
COMPLEX_PATTERNS = [
    "多个文件",
    "跨模块",
    "多步骤",
    "涉及",
    "重构",
    "迁移",
    "重写",
    "设计",
]


def pangu_api_get(path, params=None):
    """GET 请求到盘古 API（httpx 同步客户端，支持连接复用）"""
    url = f"{PANGU_API}{path}"
    headers = {"Accept": "application/json"}
    if PANGU_KEY:
        headers["X-API-Key"] = PANGU_KEY
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, headers=headers, params=params or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


def analyze_task(task_text: str) -> dict:
    """分析任务，决定需要什么能力"""
    text = task_text.lower()

    # 1. 检查能力场景
    matched_scenarios = []
    for scenario, conf in CAPABILITY_SCENARIOS.items():
        for kw in conf["keywords"]:
            if kw in text:
                matched_scenarios.append(
                    {
                        "scenario": scenario,
                        "capability": conf["capability"],
                        "action": conf["action"],
                        "matched_keyword": kw,
                    }
                )
                break

    # 2. 复杂度分析
    decision_hits = sum(1 for kw in DECISION_KEYWORDS if kw in text)
    complex_hits = sum(1 for p in COMPLEX_PATTERNS if p in text)
    complexity = min(10, decision_hits * 2 + complex_hits * 2)
    needs_deep_decision = complexity >= 6 or decision_hits >= 2

    # 3. 记忆检索检查
    needs_memory = "记忆" in text or "记得" in text or "之前" in text

    # 4. 检查盘古服务状态
    service_status = {}
    try:
        result = pangu_api_get("/health")
        if "error" not in result:
            service_status["api"] = result.get("data", {}).get("status") == "ok"
    except Exception:
        service_status["api"] = False

    return {
        "complexity": complexity,
        "decision_hits": decision_hits,
        "complex_hits": complex_hits,
        "needs_deep_decision": needs_deep_decision,
        "needs_memory": needs_memory,
        "matched_scenarios": matched_scenarios,
        "service_status": service_status,
    }


def format_recommendation(result: dict, task: str) -> str:
    """格式化输出推荐"""
    outputs = []

    # 深度决策建议
    if result["needs_deep_decision"]:
        outputs.append(f"\033[93m💡 复杂任务检测（复杂度 {result['complexity']}/10）: 建议进行多维度分析\033[0m")

    # 能力场景匹配
    if result["matched_scenarios"]:
        outputs.append("\033[96m🎯 能力场景匹配:\033[0m")
        for m in result["matched_scenarios"]:
            outputs.append(f"   * {m['scenario']} -> {m['capability']} ({m['action']})")

    # 记忆检索建议
    if result["needs_memory"]:
        outputs.append(f'\033[96m🧠 记忆检索建议: 调用 pangu_search_memories "{task[:30]}..."\033[0m')

    # 服务状态
    if result["service_status"]:
        api_ok = result["service_status"].get("api", False)
        if api_ok:
            outputs.append("\033[92m✅ 盘古 API 服务运行中\033[0m")
        else:
            outputs.append("\033[91m❌ 盘古 API 服务不可用\033[0m")

    return "\n".join(outputs) if outputs else ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: pangu_autonomous.py <任务描述>")
        sys.exit(0)

    task_text = sys.argv[1]
    result = analyze_task(task_text)

    recommendation = format_recommendation(result, task_text)
    if recommendation:
        print(recommendation)

    # 输出 JSON 格式结果供调用者使用
    if os.environ.get("PANGU_AUTONOMOUS_JSON"):
        print(json.dumps(result, ensure_ascii=False))

    sys.exit(0)
