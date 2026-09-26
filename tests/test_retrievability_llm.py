"""可检索性体检的 LLM 阶段（2026-09-26）。

规则版实测失效：它问「记忆能否用自身特征词搜到自己」，而立项动机那条记忆
（dsh-remote-x 上线记录里埋着云端 SSH 访问方式）**用自己的词确实搜得到自己**，
所以被判为可检索。详见 memory/retrievability.py 模块 docstring。

LLM 阶段换了个问法：让 LLM 挑出「与自身主题无关、但独立来看仍关键」的事实
（访问方式/端口/路径/命令/凭据位置），再针对**那个事实**去搜。这才对得上真实失败。

本测试不调真 LLM（那要网络与密钥），只锁：解析契约、降级行为、以及「LLM 阶段失败
不得影响规则阶段」这条硬要求。
"""

import json



from pangu.memory.retrievability import audit_retrievability_llm


class _Resp:
    def __init__(self, content):
        self.content = content
        self.model = "stub"
        self.usage = {}


def test_llm_stage_degrades_when_llm_unavailable(monkeypatch):
    """LLM 挂掉/超时/返回垃圾时，阶段要返回可序列化的降级结果，而不是抛异常。

    因为自主任务里它已经被 try 包住，但**测试也该钉住它自己不会炸**。
    """
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.memory import retrievability as R

    async def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr("pangu.core.llm.LLMEngine.chat", boom)

    class _Empty:
        def get_drawers(self):
            return []

    monkeypatch.setattr("pangu.memory.layers.MemoryStack", lambda config=None: _Empty())

    cfg = PanguConfig()
    out = asyncio.run(audit_retrievability_llm(cfg, max_memories=3))
    json.dumps(out)  # 不抛异常即可
    assert "buried_facts" in out


def test_llm_stage_returns_empty_on_empty_store(monkeypatch):
    import asyncio

    from pangu.core.config import PanguConfig

    class _Empty:
        def get_drawers(self):
            return []

    monkeypatch.setattr("pangu.memory.layers.MemoryStack", lambda config=None: _Empty())
    out = asyncio.run(audit_retrievability_llm(PanguConfig(), max_memories=3))
    assert out["checked"] == 0


def test_extract_parses_json_and_keeps_only_wellformed(monkeypatch):
    """解析契约：只保留同时有 fact 和 query 的条目，且按 id 归组。"""
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.memory.retrievability import _llm_extract_incidental_facts

    payload = {
        "items": [
            {
                "id": "m1",
                "facts": [
                    {"fact": "云端 SSH 走 id_rsa_113", "query": "云端服务器怎么连"},
                    {"fact": "缺 query 的应被丢弃"},
                    {"query": "缺 fact 的应被丢弃"},
                    "垃圾行",
                ],
            },
            {"id": "m2", "facts": []},
            {"facts": [{"fact": "a", "query": "b"}]},  # 无 id，应被丢弃
        ]
    }

    async def fake_chat(self, messages, **kw):
        return _Resp(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr("pangu.core.llm.LLMEngine.chat", fake_chat)

    out = asyncio.run(_llm_extract_incidental_facts(PanguConfig(), [{"id": "m1", "head": "x"}]))
    assert set(out) == {"m1"}, out
    assert len(out["m1"]) == 1
    assert out["m1"][0]["query"] == "云端服务器怎么连"


def test_extract_survives_markdown_wrapped_json(monkeypatch):
    """模型常把 JSON 包在 ```json 里，_extract_json 负责剥壳 —— 这里确认接得上。"""
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.memory.retrievability import _llm_extract_incidental_facts

    body = '```json\n{"items":[{"id":"m1","facts":[{"fact":"F","query":"Q"}]}]}\n```'

    async def fake_chat(self, messages, **kw):
        return _Resp(body)

    monkeypatch.setattr("pangu.core.llm.LLMEngine.chat", fake_chat)
    out = asyncio.run(_llm_extract_incidental_facts(PanguConfig(), [{"id": "m1", "head": "x"}]))
    assert out.get("m1", [{}])[0].get("query") == "Q"


def test_extract_returns_empty_on_garbage_output(monkeypatch):
    """模型输出完全不是 JSON 时返回空 dict（= 本阶段无产出），不抛。"""
    import asyncio

    from pangu.core.config import PanguConfig
    from pangu.memory.retrievability import _llm_extract_incidental_facts

    async def fake_chat(self, messages, **kw):
        return _Resp("我无法完成这个任务")

    monkeypatch.setattr("pangu.core.llm.LLMEngine.chat", fake_chat)
    out = asyncio.run(_llm_extract_incidental_facts(PanguConfig(), [{"id": "m1", "head": "x"}]))
    assert out == {}


def test_task_llm_failure_does_not_fail_whole_task():
    """硬要求：LLM 阶段出错，retrievability 任务整体仍应是 success。

    否则一次 LLM 抖动就会让整个体检任务变 failed、报告不更新。
    """
    import inspect

    from pangu.memory.autonomous import AutonomousMemoryEngine

    src = inspect.getsource(AutonomousMemoryEngine._task_retrievability)
    assert src.count("except Exception") >= 2, "LLM 阶段必须有独立的 except"
    assert 'status="failed"' in src, "外层仍需在规则阶段也失败时才 failed"
    # LLM 降级后仍要写报告
    assert src.index("save_report") < src.index('status="failed"'), "报告应在最终判 failed 之前写"
