#!/usr/bin/env python3
"""盘古 — 真实 LLM 快速验证脚本

使用方式：
    # 智谱 GLM（推荐，国内便宜）
    export ZHIPU_API_KEY="your-key"
    python scripts/test_real_llm.py

    # OpenAI
    export OPENAI_API_KEY="sk-xxx"
    python scripts/test_real_llm.py

    # DeepSeek
    export DEEPSEEK_API_KEY="your-key"
    python scripts/test_real_llm.py

    # 多个 provider 同时验证
    ZHIPU_API_KEY=xxx OPENAI_API_KEY=yyy python scripts/test_real_llm.py
"""

import asyncio
import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine

PROVIDERS = [
    # (provider, env_key, model, base_url)
    ("zhipu", "ZHIPU_API_KEY", "glm-4-flash", "https://open.bigmodel.cn/api/paas/v4"),
    ("openai", "OPENAI_API_KEY", "gpt-4o-mini", "https://api.openai.com/v1"),
    ("deepseek", "DEEPSEEK_API_KEY", "deepseek-chat", "https://api.deepseek.com/v1"),
    ("qwen", "DASHSCOPE_API_KEY", "qwen-turbo", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("openrouter", "OPENROUTER_API_KEY", "openai/gpt-4o-mini", "https://openrouter.ai/api/v1"),
]


async def test_provider(provider: str, env_key: str, model: str, base_url: str) -> dict:
    """测试单个 provider"""
    api_key = os.environ.get(env_key)
    if not api_key:
        return {"provider": provider, "status": "skip", "reason": f"未配置 {env_key}"}

    print(f"\n{'='*60}")
    print(f"Provider: {provider}")
    print(f"Model:    {model}")
    print(f"Base URL: {base_url}")
    print(f"API Key:  {api_key[:8]}...{api_key[-4:]}")
    print(f"{'='*60}")

    cfg = PanguConfig(
        llm_provider=provider,
        llm_model=model,
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_max_retries=1,
    )
    engine = LLMEngine(cfg)
    result = {"provider": provider, "model": model, "tests": []}

    # 测试 1: 基础对话
    print("\n[1/4] 基础对话...")
    start = time.time()
    resp = await engine.chat(
        messages=[{"role": "user", "content": "用一句话介绍记忆系统"}],
        max_tokens=80,
    )
    test1 = {
        "name": "基础对话",
        "latency_ms": resp.latency_ms,
        "content": resp.content,
        "ok": not resp.content.startswith("[LMM") and "失败" not in resp.content,
    }
    result["tests"].append(test1)
    print(f"  ⏱️  {test1['latency_ms']:.0f}ms")
    print(f"  📝 {test1['content']!r}")

    if not test1["ok"]:
        result["status"] = "fail"
        result["error"] = resp.content
        return result

    # 测试 2: 中文能力
    print("\n[2/4] 中文能力...")
    start = time.time()
    resp = await engine.chat(
        messages=[{"role": "user", "content": "用中文总结：盘古是专业的记忆系统，专注解决 Agent 框架中普遍存在的记忆功能短板。"}],
        max_tokens=150,
    )
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in resp.content)
    test2 = {
        "name": "中文能力",
        "latency_ms": (time.time() - start) * 1000,
        "content": resp.content,
        "ok": not resp.content.startswith("[LMM") and has_chinese,
    }
    result["tests"].append(test2)
    print(f"  ⏱️  {test2['latency_ms']:.0f}ms")
    print(f"  📝 {test2['content'][:100]!r}{'...' if len(test2['content']) > 100 else ''}")

    # 测试 3: 记忆摘要（盘古专用方法）
    print("\n[3/4] 记忆摘要（summarize_memories）...")
    memories = [
        {"wing": "work", "room": "project", "content": "完成盘古 v0.1.0 的核心架构"},
        {"wing": "work", "room": "project", "content": "集成 ONNX 本地加速嵌入，CPU 推理 44ms/条"},
        {"wing": "study", "room": "ai", "content": "学习 sentence-transformers 的 ONNX 转换方法"},
    ]
    start = time.time()
    summary = await engine.summarize_memories(memories, max_summary_length=200)
    test3 = {
        "name": "记忆摘要",
        "latency_ms": (time.time() - start) * 1000,
        "content": summary,
        "ok": not summary.startswith("[LMM") and len(summary) > 10,
    }
    result["tests"].append(test3)
    print(f"  ⏱️  {test3['latency_ms']:.0f}ms")
    print(f"  📝 {summary!r}")

    # 测试 4: 分类（盘古专用方法）
    print("\n[4/4] 记忆分类（classify_memory）...")
    start = time.time()
    classification = await engine.classify_memory(
        "盘古是专业的记忆系统，专注解决 Agent 框架中普遍存在的记忆功能短板。"
    )
    test4 = {
        "name": "记忆分类",
        "latency_ms": (time.time() - start) * 1000,
        "content": str(classification),
        "ok": isinstance(classification, dict) and "hall" in classification,
    }
    result["tests"].append(test4)
    print(f"  ⏱️  {test4['latency_ms']:.0f}ms")
    print(f"  📝 {classification}")

    # 总结
    all_ok = all(t["ok"] for t in result["tests"])
    result["status"] = "ok" if all_ok else "partial"
    result["avg_latency_ms"] = engine.avg_latency_ms
    result["total_calls"] = engine._call_count

    return result


async def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          盘古 — 真实 LLM 集成测试                            ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # 检测哪些 provider 配置了 key
    configured = [
        (p, k, m, u) for p, k, m, u in PROVIDERS
        if os.environ.get(k) and os.environ[k].strip()
    ]

    if not configured:
        print("\n❌ 未配置任何 LLM API key")
        print("\n请设置以下环境变量之一：")
        for p, k, m, _ in PROVIDERS:
            print(f"  export {k}=<your-key>  # {p} ({m})")
        print("\n推荐使用智谱 GLM：")
        print("  注册: https://open.bigmodel.cn/")
        print("  新用户有免费额度")
        sys.exit(1)

    print(f"\n检测到 {len(configured)} 个 provider: {[p for p, _, _, _ in configured]}")

    # 顺序测试
    results = []
    for provider, env_key, model, base_url in configured:
        result = await test_provider(provider, env_key, model, base_url)
        results.append(result)

    # 输出总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)

    for r in results:
        if r.get("status") == "skip":
            print(f"  ⏭️  {r['provider']:12s}  SKIP  ({r.get('reason', '?')})")
            continue

        status_icon = "✅" if r.get("status") == "ok" else "❌"
        print(f"  {status_icon} {r['provider']:12s}  {r.get('status', '?').upper():8s}  "
              f"avg={r.get('avg_latency_ms', 0):.0f}ms  calls={r.get('total_calls', 0)}")

        for t in r.get("tests", []):
            test_icon = "  ✓" if t.get("ok") else "  ✗"
            print(f"     {test_icon} {t['name']:12s}  {t.get('latency_ms', 0):.0f}ms")

    # 退出码
    all_ok = all(r.get("status") == "ok" for r in results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
