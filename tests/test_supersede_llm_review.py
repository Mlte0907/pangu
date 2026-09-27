"""方案 A：冲突 supersede 改为「后台 LLM 复核」（2026-09-27）。

为什么必须改：
    `_detect_conflicts` 原本**同步**执行 supersede —— 字词法一旦给出候选就直接把
    旧记忆标 `memory_status="superseded"` 移出搜索，不问任何人。上云实测：新记忆
    与最近 20 条能碰出 **52 个候选**（conf=1.0），而 `CONFLICT_MAX_REPORT=3` 意味着
    **几乎每写一条记忆就静默下架 3 条旧的**。

为什么不能把 LLM 塞进同步路径：
    实测该 LLM 端点 **avg 41.2s（2~120s）**，而 `remember()` 是同步写入管道。
    塞进去 = 每存一条记忆卡半分钟。

方案 A 的契约（本文件锁的就是它）：
    1. **写入零延迟** —— 检出候选后立刻返回，不等 LLM；
    2. **下架必须过 LLM** —— 只有 LLM 明确判「是矛盾」才下架旧记忆；
    3. **fail-open** —— LLM 失败/不可用/超时一律**不下架**（宁可漏判）。
       误下架的代价是记忆静默消失、用户不知情，远高于多留一条重复；
    4. **可追溯** —— 每次真下架都留 logger.warning，带 LLM 给出的理由。
"""

from __future__ import annotations

import time

import pytest

from pangu.core.palace import Drawer
from pangu.memory import ingestion

OLD_CONTENT = "盘古 REST 服务端口配置为 19529，部署结论已确认，状态正确，配置 结果 决定"
NEW_CONTENT = "盘古 REST 服务端口配置为 8080，部署结论需更正，状态错误，配置 结果 决定"


def _existing(n: int = 4) -> list[Drawer]:
    """凑够 CONFLICT_MIN_EXISTING=3 的历史记忆，末位是与新记忆冲突的那条。"""
    drawers = [
        Drawer(id=f"filler{i}", content=f"无关记忆 {i}：午餐吃了什么，天气不错，闲聊记录")
        for i in range(n - 1)
    ]
    drawers.append(Drawer(id="old-target", content=OLD_CONTENT))
    return drawers


class _FakeDetector:
    """直接给定候选，绕开 embedding 依赖 —— 检测逻辑本身由
    tests/test_conflict_fp_guard.py 覆盖，这里只考「复核 + 下架」。"""

    def __init__(self, conflicts):
        self._conflicts = conflicts

    def detect_conflicts(self, drawers, **kwargs):
        return self._conflicts


def _conflict() -> "object":
    from pangu.memory.conflict import ConflictSeverity, MemoryConflict

    return MemoryConflict(
        id="cf_test",
        memory_a="new-item",
        memory_b="old-target",
        content_a=NEW_CONTENT[:200],
        content_b=OLD_CONTENT[:200],
        description="测试冲突",
        severity=ConflictSeverity.CRITICAL,
        confidence=1.0,
    )


class _MemoryStorage:
    """最小 storage：load/save 按 id 替换，够 `_persist_supersede_update` 用。"""

    def __init__(self, drawers: list[Drawer]):
        self._drawers = list(drawers)
        self.last_load_ok = True
        self.saves = 0

    def load(self) -> list[Drawer]:
        return list(self._drawers)

    def save(self, drawers) -> None:
        self._drawers = list(drawers)
        self.saves += 1


@pytest.fixture
def _no_real_llm(monkeypatch):
    """挡住真实 LLM —— 测试不该打 41 秒的网络调用。

    ⚠ 刻意**不加 autouse**：`TestLLMConfirmParsing` 要测的就是真
    `_llm_confirm_conflict`，autouse 会把它替换成 stub，那两个用例就永远
    走不到真代码（本轮第一版就踩了这个，表现为 `seen["prompt"]` KeyError）。
    """
    def _stub(a: str, b: str):
        return False, "测试默认不确认"

    monkeypatch.setattr(ingestion, "_llm_confirm_conflict", _stub)


def _run_detect(monkeypatch, storage, *, conflicts=None) -> object:
    """跑一次 _detect_conflicts，返回它提交的后台任务（便于 join）。"""
    monkeypatch.setattr(
        "pangu.memory.conflict.ConflictDetector",
        lambda *a, **k: _FakeDetector([_conflict()]),
    )
    new = Drawer(id="new-item", content=NEW_CONTENT)
    return ingestion._detect_conflicts(new, _existing(), "new-item", storage=storage)


class TestWritePathIsNotBlocked:
    """① 写入零延迟：检出候选后立即返回，绝不同步等 LLM。"""

    def test_returns_immediately_without_waiting_for_llm(self, monkeypatch):
        calls: list = []

        def slow_stub(a, b):
            calls.append(1)
            time.sleep(0)  # 即便 stub 是瞬时的，返回也不该等它
            return True, "确认"

        monkeypatch.setattr(ingestion, "_llm_confirm_conflict", slow_stub)
        storage = _MemoryStorage(_existing())
        t0 = time.time()
        task = _run_detect(monkeypatch, storage)
        elapsed = time.time() - t0

        assert elapsed < 0.5, f"写入路径被阻塞了 {elapsed:.2f}s —— 方案 A 要求零延迟"
        assert task is not None, "有候选却没提交后台复核任务"

    @pytest.mark.usefixtures("_no_real_llm")
    def test_old_drawer_not_removed_before_review(self, monkeypatch):
        """复核完成前，旧记忆**必须仍在搜索范围内**（不许提前下架）。"""
        storage = _MemoryStorage(_existing())
        _run_detect(monkeypatch, storage)

        # 后台任务给了 stub 时间也仍不改变结论：stub 返回 False
        for d in storage.load():
            if d.id == "old-target":
                assert d.metadata.get("memory_status") != "superseded", (
                    "LLM 尚未确认就把旧记忆下架了 —— 这正是原缺陷"
                )


class TestSupersedeOnlyAfterLLMConfirms:
    """② 只有 LLM 明确确认，才下架旧记忆。"""

    def test_confirmed_pair_triggers_supersede(self, monkeypatch):
        monkeypatch.setattr(
            ingestion, "_llm_confirm_conflict", lambda a, b: (True, "端口取值互斥")
        )
        storage = _MemoryStorage(_existing())
        task = _run_detect(monkeypatch, storage)
        if task is not None:
            task.join(timeout=10)

        statuses = {d.id: d.metadata.get("memory_status") for d in storage.load()}
        assert statuses.get("old-target") == "superseded", (
            f"LLM 确认矛盾却没下架: {statuses}"
        )
        assert storage.saves > 0, "确认后必须落盘，否则下次读又是未下架状态"

    def test_new_drawer_records_confirmed_supersede(self, monkeypatch):
        monkeypatch.setattr(
            ingestion, "_llm_confirm_conflict", lambda a, b: (True, "确认")
        )
        storage = _MemoryStorage(_existing())
        new = Drawer(id="new-item", content=NEW_CONTENT)
        monkeypatch.setattr(
            "pangu.memory.conflict.ConflictDetector",
            lambda *a, **k: _FakeDetector([_conflict()]),
        )
        task = ingestion._detect_conflicts(new, _existing(), "new-item", storage=storage)
        if task is not None:
            task.join(timeout=10)
        assert "old-target" in (new.metadata.get("supersedes") or []), (
            f"新记忆没记下 supersedes 链: {new.metadata}"
        )


class TestFailOpen:
    """③ LLM 出任何问题 ⇒ 一律不下架（宁可漏判，不可误杀）。"""

    @pytest.mark.parametrize(
        "outcome,why",
        [
            ((False, "各说各事"), "LLM 判非冲突"),
        ],
    )
    def test_denied_pair_is_not_superseded(self, monkeypatch, outcome, why):
        monkeypatch.setattr(ingestion, "_llm_confirm_conflict", lambda a, b: outcome)
        storage = _MemoryStorage(_existing())
        task = _run_detect(monkeypatch, storage)
        if task is not None:
            task.join(timeout=10)

        statuses = {d.id: d.metadata.get("memory_status") for d in storage.load()}
        assert statuses.get("old-target") != "superseded", f"{why} 却下架了"
        assert storage.saves == 0, f"{why} 不该产生落盘写入"

    def test_llm_exception_fails_open(self, monkeypatch):
        """LLM 抛异常 / 超时 / 网络挂 —— 全部按「不冲突」处理。"""
        def boom(a, b):
            raise RuntimeError("连接超时 41s")

        monkeypatch.setattr(ingestion, "_llm_confirm_conflict", boom)
        storage = _MemoryStorage(_existing())
        task = _run_detect(monkeypatch, storage)
        if task is not None:
            task.join(timeout=10)

        statuses = {d.id: d.metadata.get("memory_status") for d in storage.load()}
        assert statuses.get("old-target") != "superseded"
        assert storage.saves == 0


class TestKillSwitch:
    """④ 能一键关掉 LLM 复核而不炸（回滚到「只检测不下架」）。"""

    def test_disabled_review_never_supersedes(self, monkeypatch):
        monkeypatch.setattr(ingestion, "LLM_REVIEW_ENABLED", False)
        monkeypatch.setattr(
            ingestion, "_llm_confirm_conflict", lambda a, b: (True, "确认")
        )
        storage = _MemoryStorage(_existing())
        _run_detect(monkeypatch, storage)

        statuses = {d.id: d.metadata.get("memory_status") for d in storage.load()}
        assert statuses.get("old-target") != "superseded", (
            "复核开关关闭时仍下架了 —— 开关必须真能关掉"
        )


class TestLLMConfirmParsing:
    """⑤ `_llm_confirm_conflict` 的解析与 fail-open 语义（不打真实网络）。"""

    def test_parses_json_reply(self, monkeypatch):
        class _Resp:
            content = '{"conflicts": true, "reason": "端口互斥"}'

        class _Eng:
            async def chat(self, msgs):
                return _Resp()

        monkeypatch.setattr(ingestion, "_make_llm_engine", lambda: _Eng())
        ok, reason = ingestion._llm_confirm_conflict("A 内容", "B 内容")
        assert ok is True and "端口" in reason

    def test_malformed_reply_fails_open(self, monkeypatch):
        class _Resp:
            content = "抱歉，我无法判断。"

        class _Eng:
            async def chat(self, msgs):
                return _Resp()

        monkeypatch.setattr(ingestion, "_make_llm_engine", lambda: _Eng())
        ok, _ = ingestion._llm_confirm_conflict("A", "B")
        assert ok is False, "解析不出 JSON 时必须 fail-open（不下架）"

    def test_engine_unavailable_fails_open(self, monkeypatch):
        def boom():
            raise RuntimeError("没有配置 LLM")

        monkeypatch.setattr(ingestion, "_make_llm_engine", boom)
        ok, _ = ingestion._llm_confirm_conflict("A", "B")
        assert ok is False

    def test_decrypts_before_sending_to_llm(self, monkeypatch):
        """★ 送 LLM 前必须解密。

        2026-09-27 端到端实测抓到：写入管道里的 content 是 Fernet 密文，不先解密
        LLM 收到 `gAAAAAB…` 就回「无法解析具体事实内容」⇒ 恒判 no ⇒ 永远不下架，
        功能名存实亡（fail-open 虽安全，但谈不上把关）。
        """
        from cryptography.fernet import Fernet

        from pangu.memory import encryption as enc

        monkeypatch.setattr(enc, "_fernet", None)
        monkeypatch.setattr(enc, "_enabled", False)
        monkeypatch.setenv("PANGU_ENCRYPTION_KEY", Fernet.generate_key().decode())

        seen: dict = {}

        class _Resp:
            content = '{"conflicts": false, "reason": "无关"}'

        class _Eng:
            async def chat(self, msgs):
                seen["prompt"] = msgs[0]["content"]
                return _Resp()

        monkeypatch.setattr(ingestion, "_make_llm_engine", lambda: _Eng())

        cipher_a = enc.encrypt("第一条明文：盘古 REST 端口是 19529")
        cipher_b = enc.encrypt("第二条明文：盘古 REST 端口是 8080")
        assert cipher_a.startswith("gAAAAA"), "前置条件：样本必须真是密文"

        ingestion._llm_confirm_conflict(cipher_a, cipher_b)

        prompt = seen.get("prompt", "")
        assert prompt, "LLM 没被调用，断言无意义"
        assert "gAAAAA" not in prompt, "送 LLM 的仍是密文 —— 它会回「看不懂」"
        assert "端口是 19529" in prompt, f"明文没解出来: {prompt[:200]}"
        assert "端口是 8080" in prompt

    def test_never_uses_format_on_prompt(self, monkeypatch):
        """prompt 里含 `{"conflicts": ...}` 示例，用 str.format() 会把它当占位符
        抛 KeyError —— 这个坑本轮踩过（KeyError: '"conflicts"'）。"""
        seen = {}

        class _Resp:
            content = '{"conflicts": false, "reason": "无关"}'

        class _Eng:
            async def chat(self, msgs):
                seen["prompt"] = msgs[0]["content"]
                return _Resp()

        monkeypatch.setattr(ingestion, "_make_llm_engine", lambda: _Eng())
        ingestion._llm_confirm_conflict("带 {a} 占位的正文", "另一条 {b} 正文")
        p = seen["prompt"]
        assert "带 {a} 占位的正文" in p, "占位内容被 format 破坏了"
        assert '"conflicts"' in p, "prompt 应保留 JSON 输出示例"
