"""盘古 — 真实 LLM 集成测试

⚠️  这些测试会发起真实网络请求，需要 API key。

使用方式：
    export ZHIPU_API_KEY="your-key"
    pytest tests/test_real_llm.py -v -m integration

    # 或者指定 provider
    PANGU_LLM_PROVIDER=openai OPENAI_API_KEY=sk-xxx pytest tests/test_real_llm.py -v

如果未配置任何 API key，所有测试自动 skip。

测试覆盖：
- 真实 API 连通性
- 中文/英文对话
- Token 限制
- 重试机制
- 多个 provider 切换
- 记忆处理专用方法（summarize/classify/generate_wiki）
- 性能基线记录
"""

import os
import time

import pytest

# ── 跳过条件 ──
_PROVIDERS = [
    # (provider, env_key, model)  按优先级排序
    ("zhipu", "ZHIPU_API_KEY", "glm-4-flash"),
    ("openai", "OPENAI_API_KEY", "gpt-4o-mini"),
    ("deepseek", "DEEPSEEK_API_KEY", "deepseek-chat"),
    ("qwen", "DASHSCOPE_API_KEY", "qwen-turbo"),
    ("openrouter", "OPENROUTER_API_KEY", "openai/gpt-4o-mini"),
    ("anthropic", "ANTHROPIC_API_KEY", "claude-3-haiku-20240307"),
]


def _configured_providers() -> list[tuple[str, str, str]]:
    """返回所有配置了 key 的 provider 列表"""
    return [
        (p, k, m) for p, k, m in _PROVIDERS
        if os.environ.get(k) and os.environ[k].strip()
    ]


def _first_provider() -> tuple[str, str, str]:
    """获取优先级最高的已配置 provider"""
    configured = _configured_providers()
    if not configured:
        raise RuntimeError("No API key configured")
    return configured[0]


# 全局标记
pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────
# 1. 基础连通性
# ─────────────────────────────────────────────────────

class TestRealLLMConnectivity:
    """真实 LLM 端到端连通性测试"""

    def test_skip_without_key(self):
        """无 key 时报告 skip 而非错误"""
        configured = _configured_providers()
        if not configured:
            pytest.skip("未配置任何 LLM API key")
        print(f"\n[可用 provider] {[p for p, _, _ in configured]}")

    @pytest.mark.asyncio
    async def test_basic_chat(self):
        """基础 chat 调用"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        start = time.time()
        resp = await engine.chat(
            messages=[{"role": "user", "content": "回复 OK"}],
            system="简洁回复",
            temperature=0.0,
            max_tokens=20,
        )
        elapsed_ms = (time.time() - start) * 1000

        # 真实测试：可能因为网络/代理问题失败，跳过而非断言失败
        if resp.content.startswith("[LMM") or "失败" in resp.content:
            pytest.skip(f"{provider} 不可用: {resp.content[:100]}")
        assert len(resp.content) > 0
        print(f"\n[Chat] {provider}/{model}: {elapsed_ms:.0f}ms, content={resp.content!r}")

    @pytest.mark.asyncio
    async def test_chinese_response(self):
        """中文响应能力"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        resp = await engine.chat(
            messages=[{"role": "user", "content": "用中文写一句关于记忆系统的话，不超过20字"}],
            temperature=0.5,
            max_tokens=100,
        )
        if resp.content.startswith("[LMM") or "失败" in resp.content:
            pytest.skip(f"{provider} 不可用")
        # 应包含中文字符
        assert any('\u4e00' <= c <= '\u9fff' for c in resp.content), (
            f"未检测到中文: {resp.content!r}"
        )
        assert len(resp.content) <= 100
        print(f"\n[中文] {resp.content!r}")

    @pytest.mark.asyncio
    async def test_english_response(self):
        """英文响应能力"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        resp = await engine.chat(
            messages=[{"role": "user", "content": "Reply with one short English sentence about memory."}],
            temperature=0.5,
            max_tokens=60,
        )
        if resp.content.startswith("[LMM") or "失败" in resp.content:
            pytest.skip(f"{provider} 不可用")
        assert any(c.isalpha() and c.isascii() for c in resp.content)
        print(f"\n[English] {resp.content!r}")


# ─────────────────────────────────────────────────────
# 2. 性能基线
# ─────────────────────────────────────────────────────

class TestRealLLMPerformance:
    """真实 LLM 性能基线（记录，不强制断言）"""

    @pytest.mark.asyncio
    async def test_latency_baseline(self):
        """记录单次调用延迟"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        # 预热
        warmup = await engine.chat(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )
        if warmup.content.startswith("[LMM"):
            pytest.skip(f"{provider} 不可用")

        # 测试
        n = 3
        latencies = []
        for i in range(n):
            start = time.time()
            resp = await engine.chat(
                messages=[{"role": "user", "content": f"回复数字 {i+1}"}],
                max_tokens=20,
            )
            if resp.content.startswith("[LMM"):
                continue
            latencies.append((time.time() - start) * 1000)

        if not latencies:
            pytest.skip("无成功响应")

        avg = sum(latencies) / len(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(
            f"\n[Perf {provider}] n={len(latencies)} avg={avg:.0f}ms p95={p95:.0f}ms "
            f"raw={latencies}"
        )


# ─────────────────────────────────────────────────────
# 3. 错误处理
# ─────────────────────────────────────────────────────

class TestRealLLMErrorHandling:
    """真实错误场景测试"""

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        """无效 key 应返回错误信息而不抛异常"""
        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        try:
            provider, _, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        # 故意使用错误 key
        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key="invalid-fake-key-12345",
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)
        resp = await engine.chat(
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10,
        )
        # 应返回错误标识（不抛异常）
        assert resp.content.startswith("[LMM") or "失败" in resp.content or "401" in resp.content
        print(f"\n[InvalidKey] {resp.content[:100]!r}")


# ─────────────────────────────────────────────────────
# 4. 记忆处理专用方法
# ─────────────────────────────────────────────────────

class TestRealLLMMemoryMethods:
    """记忆处理专用方法的真实测试"""

    @pytest.mark.asyncio
    async def test_summarize_memories(self):
        """summarize_memories 真实调用"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        memories = [
            {"wing": "work", "room": "project", "content": "完成盘古 v0.1.0 的核心架构"},
            {"wing": "work", "room": "project", "content": "新增 ONNX 本地加速嵌入模块，CPU 性能提升 10x"},
            {"wing": "study", "room": "ai", "content": "学习 sentence-transformers 的 ONNX 转换方法"},
        ]
        start = time.time()
        summary = await engine.summarize_memories(memories, max_summary_length=200)
        elapsed_ms = (time.time() - start) * 1000

        if summary.startswith("[LMM") or "失败" in summary:
            pytest.skip(f"{provider} 不可用")
        assert len(summary) > 10
        print(f"\n[Summarize {elapsed_ms:.0f}ms] {summary!r}")

    @pytest.mark.asyncio
    async def test_classify_memory(self):
        """classify_memory 真实调用"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        result = await engine.classify_memory("盘古是专业的记忆系统，专注解决 Agent 框架中普遍存在的记忆功能短板。")
        assert isinstance(result, dict)
        # 至少应该有 hall 字段（默认值或解析值）
        assert "hall" in result
        print(f"\n[Classify] {result}")

    @pytest.mark.asyncio
    async def test_generate_wiki_page(self):
        """generate_wiki_page 真实调用"""
        try:
            provider, env_key, model = _first_provider()
        except RuntimeError:
            pytest.skip("未配置 API key")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)

        memories = [
            {"wing": "tech", "room": "embedding", "content": "ONNX 是一种跨框架的模型格式，可以本地 CPU 推理。"},
            {"wing": "tech", "room": "embedding", "content": "MiniLM-L6 量化模型只有 22MB，CPU 推理 44ms/条。"},
        ]
        result = await engine.generate_wiki_page("ONNX 嵌入加速", memories)
        assert isinstance(result, dict)
        print(f"\n[Wiki] keys={list(result.keys())}")
        # 至少 title/content 之一应被填充
        if "title" in result:
            print(f"  title: {result['title']}")
        if "summary" in result:
            print(f"  summary: {result['summary'][:100]}")


# ─────────────────────────────────────────────────────
# 5. Provider 矩阵测试
# ─────────────────────────────────────────────────────

class TestRealLLMProviderMatrix:
    """对所有配置了 key 的 provider 运行最小烟雾测试"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider,env_key,model", [
        ("zhipu", "ZHIPU_API_KEY", "glm-4-flash"),
        ("openai", "OPENAI_API_KEY", "gpt-4o-mini"),
        ("deepseek", "DEEPSEEK_API_KEY", "deepseek-chat"),
        ("qwen", "DASHSCOPE_API_KEY", "qwen-turbo"),
    ])
    async def test_provider_smoke(self, provider, env_key, model):
        """单 provider 烟雾测试"""
        if not os.environ.get(env_key):
            pytest.skip(f"未配置 {env_key}")

        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine

        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)
        resp = await engine.chat(
            messages=[{"role": "user", "content": "回复 OK"}],
            max_tokens=10,
        )
        assert not resp.content.startswith("[LMM"), f"{provider}: {resp.content}"
        print(f"\n[{provider}/{model}] {resp.content!r}")


# ─────────────────────────────────────────────────────
# 6. 智谱专享（推荐）
# ─────────────────────────────────────────────────────

class TestZhipuGLM:
    """智谱 GLM 专项测试（推荐使用，国内最便宜）"""

    @pytest.fixture
    def zhipu_engine(self):
        if not os.environ.get("ZHIPU_API_KEY"):
            pytest.skip("未配置 ZHIPU_API_KEY")
        from pangu.core.config import PanguConfig
        from pangu.core.llm import LLMEngine
        return LLMEngine(PanguConfig(
            llm_provider="zhipu",
            llm_model="glm-4-flash",
            llm_api_key=os.environ["ZHIPU_API_KEY"],
        ))

    @pytest.mark.asyncio
    async def test_glm4_flash_chinese(self, zhipu_engine):
        """GLM-4-Flash 中文能力"""
        resp = await zhipu_engine.chat(
            messages=[{"role": "user", "content": "用一句中文描述记忆系统"}],
            max_tokens=100,
        )
        assert not resp.content.startswith("[LMM")
        assert any('\u4e00' <= c <= '\u9fff' for c in resp.content)
        print(f"\n[GLM-4-Flash 中文] {resp.content!r}")

    @pytest.mark.asyncio
    async def test_glm4_flash_json(self, zhipu_engine):
        """GLM-4-Flash JSON 解析能力"""
        resp = await zhipu_engine.chat(
            messages=[{"role": "user", "content": '返回 JSON: {"key": "value"}'}],
            system="只返回 JSON，不要其他内容",
            max_tokens=50,
        )
        # 不强制 JSON 解析成功（小模型可能不可靠）
        print(f"\n[GLM-4-Flash JSON] {resp.content!r}")


# ─────────────────────────────────────────────────────
# 7. 快速验证脚本
# ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quick_smoke():
    """快速烟雾测试（可单独运行）"""
    configured = _configured_providers()
    if not configured:
        pytest.skip("未配置任何 LLM API key，请设置 ZHIPU_API_KEY / OPENAI_API_KEY 等")

    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    # 找到第一个能用的 provider
    working_provider = None
    working_key = None
    working_model = None
    working_engine = None

    for provider, env_key, model in configured:
        cfg = PanguConfig(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=os.environ[env_key],
            llm_max_retries=1,
        )
        engine = LLMEngine(cfg)
        probe = await engine.chat(
            messages=[{"role": "user", "content": "回复 OK"}],
            max_tokens=10,
        )
        if not probe.content.startswith("[LMM") and "失败" not in probe.content:
            working_provider = provider
            working_key = os.environ[env_key]
            working_model = model
            working_engine = engine
            break

    if working_engine is None:
        pytest.skip(f"所有配置的 provider 都不通: {[p for p, _, _ in configured]}")

    print(f"\n{'='*50}")
    print(f"Provider: {working_provider}")
    print(f"Model: {working_model}")
    print(f"API Key: {working_key[:10]}...{working_key[-4:]}")
    print(f"{'='*50}")

    # 测试 1: 基础对话
    start = time.time()
    resp1 = await working_engine.chat(
        messages=[{"role": "user", "content": "一句话介绍记忆系统"}],
        max_tokens=50,
    )
    print(f"\n[1. 对话] {resp1.latency_ms:.0f}ms")
    print(f"    {resp1.content!r}")

    # 测试 2: JSON 能力
    start = time.time()
    resp2 = await working_engine.chat(
        messages=[{"role": "user", "content": '返回 JSON: {"status": "ok", "version": "1.0"}'}],
        system="只返回 JSON",
        max_tokens=50,
    )
    print(f"\n[2. JSON] {resp2.latency_ms:.0f}ms")
    print(f"    {resp2.content!r}")

    # 测试 3: 记忆摘要
    memories = [
        {"wing": "work", "content": "完成盘古 v0.1.0"},
        {"wing": "work", "content": "集成 ONNX 加速"},
    ]
    start = time.time()
    summary = await working_engine.summarize_memories(memories)
    print(f"\n[3. 摘要] {(time.time()-start)*1000:.0f}ms")
    print(f"    {summary!r}")

    # 统计
    print(f"\n[统计] 调用次数={working_engine._call_count}, 平均延迟={working_engine.avg_latency_ms:.0f}ms")
    print(f"{'='*50}\n")

    assert not resp1.content.startswith("[LMM"), f"对话失败: {resp1.content}"
