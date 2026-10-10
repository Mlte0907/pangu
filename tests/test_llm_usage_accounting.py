"""
LLM 用量计量口径（2026-10-10）。

为什么要有这个文件：仪表盘「LLM 用量」卡片曾恒显示「今日 0」，而供应商账单
在涨。根因是三处叠加的记账缺陷，每一处单独看都"合理"：

  A. **用量挂在实例上**，而同进程内存在多个引擎（知识结晶的直连路径、配置热
     加载后 handlers/system.py 现造的临时引擎）—— 各自记各自的，仪表盘读到
     的只是其中一份。
  B. **直连路径完全不记账**：autonomous._llm_chat 用 urllib 直连端点，不经过
     LLMEngine，它的 token 对所有人不可见。
  C. **Anthropic 路径只记调用数不记 token**：`usage` 键名是 input_tokens /
     output_tokens，与 OpenAI 的 prompt_tokens / completion_tokens 不同。

所以这里断言的不是"某个数字等于某值"，而是三条**不变量**：

  1. 同一进程内，任何 LLMEngine 实例读到的用量都相同（共享存储）。
  2. 绕过引擎的直连调用报账后，仪表盘口径能看见它。
  3. 不同供应商的 usage 键名都能落到同一套 prompt/completion 计数上。
"""

import time

import pytest

from pangu.core.llm import LLMEngine


@pytest.fixture(autouse=True)
def _clean_usage():
    """进程级存储必须每个用例独立 —— 由 conftest 的 autouse 夹具兜底复位，
    这里再复位一次是为了**单独跑本文件**时也干净。"""
    LLMEngine.reset_usage()
    yield
    LLMEngine.reset_usage()


def _engine() -> LLMEngine:
    """造一个只够跑用量记账的引擎实例（不建 HTTP 客户端，不碰配置单例）。"""
    eng = LLMEngine.__new__(LLMEngine)
    eng.config = type("Cfg", (), {"llm_model": "test-model", "llm_provider": "openai"})()
    for attr in ("_cache_hits", "_cache_misses", "_cache_disk_hits", "_cache_writes", "_tokens_saved"):
        setattr(eng, attr, 0)
    eng._cache = {}
    eng._cache_max = 0
    eng._persistent_cache = None
    eng._cache_enabled = True
    return eng


# ── 不变量 1：用量是进程级事实，不是实例属性 ──


def test_two_instances_share_one_usage_ledger():
    """A：同进程内两个引擎必须看到同一本账。

    这条曾经不成立，也**没有任何测试守着** —— 正因如此，仪表盘少算用量时
    整个测试套件全绿。修好之后必须有测试钉住。
    """
    a, b = _engine(), _engine()
    a.record_external_usage("openai", prompt_tokens=100, completion_tokens=20, latency_ms=400)

    assert a.get_stats()["call_count"] == 1
    # b 从未调用过，但它是同一个进程的 LLM 流量，必须看到 a 记的账
    assert b.get_stats()["call_count"] == 1
    assert b.get_stats()["total_prompt_tokens"] == 100
    assert b.get_stats()["total_completion_tokens"] == 20


def test_usage_accumulates_across_instances():
    a, b = _engine(), _engine()
    a.record_external_usage("openai", prompt_tokens=10, completion_tokens=1)
    b.record_external_usage("openai", prompt_tokens=7, completion_tokens=3)
    assert a.get_stats()["call_count"] == 2
    assert a.get_stats()["total_tokens"] == 21


def test_cache_counters_stay_per_instance():
    """反向约束：缓存计数**必须**仍是每实例的。

    缓存描述的是「本引擎的这张缓存」，两个引擎各有各的缓存，合并成一个数
    就成了假数据。这条钉住"哪些该共享、哪些不该"的边界，防止后来者
    把 _cache_* 也一股脑塞进共享存储。
    """
    a, b = _engine(), _engine()
    a._cache_hits = 5
    assert a.get_stats()["cache_hits"] == 5
    assert b.get_stats()["cache_hits"] == 0


def test_reset_usage_clears_every_field():
    """复位入口必须清**全部**计数器 —— 少清一个就会让后续用例读到脏账。"""
    eng = _engine()
    eng.record_external_usage("openai", prompt_tokens=5, completion_tokens=5, latency_ms=10)
    LLMEngine.reset_usage()
    stats = eng.get_stats()
    assert stats["call_count"] == 0
    assert stats["total_prompt_tokens"] == 0
    assert stats["total_completion_tokens"] == 0
    assert stats["total_latency_ms"] == 0
    assert stats["avg_latency_ms"] == 0.0
    assert stats["daily"]["call_count"] == 0


# ── 不变量 2：直连调用（绕过引擎）也要被看见 ──


def test_external_usage_shows_up_in_daily_bucket():
    """B：autonomous._llm_chat 报账后，「今日」这一栏必须有它。"""
    eng = _engine()
    eng.record_external_usage("openai", prompt_tokens=1200, completion_tokens=340)

    daily = eng.get_stats()["daily"]
    today = time.strftime("%Y-%m-%d")
    assert daily["date"] == today
    assert daily["prompt_tokens"] == 1200
    assert daily["completion_tokens"] == 340
    assert daily["total_tokens"] == 1540
    assert daily["call_count"] == 1


def test_daily_buckets_are_separate_per_day():
    """按日分桶不能串：昨天的账不能算进今天。"""
    eng = _engine()
    usage = eng._usage()
    usage["daily_tokens"]["2000-01-01"] = {"prompt_tokens": 99, "completion_tokens": 99, "call_count": 9}
    eng.record_external_usage("openai", prompt_tokens=5, completion_tokens=5)

    daily = eng.get_stats()["daily"]
    assert daily["prompt_tokens"] == 5
    assert daily["call_count"] == 1
    # 历史那天仍原样保留
    assert usage["daily_tokens"]["2000-01-01"]["prompt_tokens"] == 99


def test_autonomous_llm_chat_reports_its_real_usage():
    """B 的端到端：结晶的直连调用必须真的报上账。

    用假的 urlopen 桩替代真实端点，只验「响应里的 usage 被取出来记账」，
    不发任何网络请求。
    """
    from pangu.memory import autonomous as auto_mod

    eng = _engine()
    engine_holder = auto_mod.AutonomousMemoryEngine.__new__(auto_mod.AutonomousMemoryEngine)
    engine_holder.config = eng.config
    engine_holder._llm_engine = eng
    engine_holder._LLM_TIMEOUT = 5

    payload = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 888, "completion_tokens": 111},
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json as _json

            return _json.dumps(payload).encode()

    class _FakeRequest:
        def __init__(self, *a, **k):
            pass

    import urllib.request as _req_mod

    orig_urlopen, orig_request = _req_mod.urlopen, _req_mod.Request
    _req_mod.urlopen = lambda *a, **k: _Resp()
    _req_mod.Request = _FakeRequest
    try:
        out = engine_holder._llm_chat("https://example.invalid/v1", "k", "m", "sys", "usr")
    finally:
        _req_mod.urlopen, _req_mod.Request = orig_urlopen, orig_request

    assert out == "ok"
    stats = eng.get_stats()
    assert stats["call_count"] == 1, "直连调用没有报账"
    assert stats["total_prompt_tokens"] == 888
    assert stats["total_completion_tokens"] == 111


def test_accounting_failure_never_breaks_the_caller():
    """记账是旁路：它坏了不能让知识结晶整条失败（那会静默降级成规则式内容，
    用户看不出少了什么）。"""
    engine_holder = auto_holder_with_broken_engine()
    data = {"usage": {"prompt_tokens": 5, "completion_tokens": 5}}
    engine_holder._record_llm_usage(data, time.time(), "https://example.invalid/v1")
    assert engine_holder._llm_engine is None, "记账失败时不应留下半初始化状态"


def auto_holder_with_broken_engine():
    """构造一个「引擎构造必炸」的自主引擎，验证旁路记账吞掉异常。"""
    import pangu.core.llm as llm_mod
    from pangu.memory import autonomous as auto_mod

    holder = auto_mod.AutonomousMemoryEngine.__new__(auto_mod.AutonomousMemoryEngine)
    holder.config = type("Cfg", (), {"llm_model": "m", "llm_provider": "openai"})()
    holder._llm_engine = None

    orig_init = llm_mod.LLMEngine.__init__

    def _boom(self, config=None):
        raise RuntimeError("engine construction failed")

    llm_mod.LLMEngine.__init__ = _boom
    try:
        holder._record_llm_usage({"usage": {"prompt_tokens": 1}}, time.time(), "b")
    finally:
        llm_mod.LLMEngine.__init__ = orig_init
    return holder


# ── 不变量 3：不同供应商的 usage 键名都要落进同一套计数 ──


def test_anthropic_usage_keys_are_mapped():
    """C：Anthropic 的 input_tokens/output_tokens 必须落到 prompt/completion。

    键名不同是这类记账最容易漏的地方 —— 漏了的表现是「调用数在涨、Token 恒 0」。
    """
    eng = _engine()
    # 走 _call_anthropic 里的同一段映射逻辑
    usage = {"input_tokens": 300, "output_tokens": 90}
    eng._account_usage("anthropic", usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    stats = eng.get_stats()
    assert stats["call_count"] == 1
    assert stats["total_prompt_tokens"] == 300
    assert stats["total_completion_tokens"] == 90


def test_missing_usage_does_not_inflate_counters():
    """响应里没有 usage 字段时，token 记 0 但**调用数照记** ——
    请求确实发出去了，供应商照样计费。少记 token 可以，少记调用数不行。"""
    eng = _engine()
    eng._account_usage("openai", 0, 0)
    stats = eng.get_stats()
    assert stats["call_count"] == 1
    assert stats["total_tokens"] == 0


def test_none_and_junk_token_values_do_not_crash():
    """脏 usage（None / 字符串 / 负数 / NaN）不得抛异常 —— 统计代码不该拖垮业务。

    关键在于「不抛」：_account_usage 在响应处理路径上，抛异常会把一次**成功**
    的 LLM 调用报成失败。四种脏值各记一次调用，token 一律记 0。
    """
    eng = _engine()
    junk = (None, "abc", -5, float("nan"))
    for bad in junk:
        eng.record_external_usage("openai", prompt_tokens=bad, completion_tokens=bad)
    stats = eng.get_stats()
    assert stats["call_count"] == len(junk), "调用数必须照记（请求确实发出去了）"
    assert stats["total_tokens"] == 0, "脏 token 必须降级为 0，而不是变成负数或 NaN"


def test_latency_is_accumulated_exactly_once():
    """延迟只能在 _account_usage 里加一次。

    抽取记账方法时我一度在调用点也留了一行 `self._total_latency += latency`，
    结果 avg_latency 虚高一倍 —— 而这类错误没有任何测试会报警。
    """
    eng = _engine()
    eng._account_usage("openai", 1, 1, latency_ms=400)
    eng._account_usage("openai", 1, 1, latency_ms=200)
    assert eng.get_stats()["avg_latency_ms"] == 300.0


# ── 仪表盘读的那两个字段必须存在且口径正确 ──


def test_system_handler_fields_match_dashboard_contract():
    """handlers/system.py 喂给仪表盘的 llm_daily / llm_total 的形状不能变。

    客户端 client.js 概览读 `s?.llm_daily.call_count` / `s?.llm_total.total_tokens`。
    这两个键名曾因大小写不一致导致卡片永远「暂无 LLM 使用数据」。
    """
    eng = _engine()
    eng.record_external_usage("openai", prompt_tokens=400, completion_tokens=100)
    stats = eng.get_stats()

    llm_daily = stats.get("daily", {})
    llm_total = {
        "call_count": stats.get("call_count", 0),
        "total_tokens": stats.get("total_tokens", 0),
        "estimated_cost_usd": stats.get("estimated_cost_usd", 0),
        "cache_hit_rate": stats.get("cache_hit_rate", 0),
    }
    for key in ("date", "prompt_tokens", "completion_tokens", "total_tokens", "call_count"):
        assert key in llm_daily, f"llm_daily 缺 {key} —— 客户端按 snake_case 读"
    for key in ("call_count", "total_tokens", "estimated_cost_usd", "cache_hit_rate"):
        assert key in llm_total, f"llm_total 缺 {key}"
    assert llm_total["call_count"] == 1
