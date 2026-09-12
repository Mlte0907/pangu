"""盘古 — 嵌入后端降级可见性测试（v0.1.3 P0）

## 为什么需要这个文件

`EmbeddingService` 是三级降级链：远程 API → ONNX → hash 向量。

问题在于**最后一级的 hash 向量是"合法"的**：

- 它是 384 维（`embedding_dim`），与 ONNX 输出同形状；
- 它 truthy，`if vec:` 成立，`len(vec) > 0` 恒真；
- 它 L2 归一化过，余弦相似度算得出来，不会 NaN；
- `embed()` 不抛异常、不返回 None。

于是**任何"看向量是否有效"的检查都判定为健康**，而实际语义能力为零：

| 文本对 | hash 向量余弦 | 应有语义 |
| --- | --- | --- |
| (猫, dog) | 0.0000 | 相近（都是动物） |
| (猫, 猫咪) | 0.7071 | 极高（同义词）— 此处纯属字符巧合 |
| (股票, 股市) | 0.5000 | 高（近义）— 同样是字符巧合 |
| (猫, 股市) | 0.0000 | 无关 |

后果：服务照常启动、检索照常返回结果，用户拿到一个**"能跑但结果是错的"**
系统，且极难察觉——日志里只有一条 Download failed 一闪而过。

本文件锁定的正是这个行为：**降级必须可见**。

## 测试策略

不依赖真实 ONNX 下载（CI 上网络不可靠），而是用
`PANGU_ONNX_ENABLED=false` 或注入一个失败的 `_onnx` 来确定性地制造降级，
再断言 `active_backend` / `is_degraded` / `/health` 都如实反映。
"""

import pytest

from pangu.core.config import PanguConfig


@pytest.fixture
def degraded_service(monkeypatch):
    """构造一个必然降级到 hash 的 EmbeddingService

    用 `onnx_enabled=False` 而非"让下载失败"，因为前者不依赖网络、
    确定性高，且最终都落到同一个 `_local_embed()` 分支。
    """
    from pangu.memory.embedding import EmbeddingService

    monkeypatch.setenv("PANGU_ONNX_ENABLED", "false")
    cfg = PanguConfig()
    assert cfg.onnx_enabled is False, "环境变量未生效，测试前提不成立"
    svc = EmbeddingService(cfg)
    return svc


class TestDegradationIsVisible:
    """降级状态必须可被程序读取——这是 v0.1.3 修的核心缺陷"""

    def test_hash_vector_looks_valid(self, degraded_service):
        """先确认缺陷前提：hash 向量**看起来完全正常**

        这条测试是其余断言的意义所在——如果 hash 向量一眼就能看出坏了，
        那这个 P0 根本不存在。
        """
        vec = degraded_service.embed("测试文本")
        assert vec is not None, "hash 向量不应为 None（这正是它隐蔽的原因）"
        assert len(vec) == degraded_service.config.embedding_dim
        assert any(v != 0.0 for v in vec), "hash 向量非零，通过所有'有效性'检查"

    def test_naive_validity_check_cannot_detect(self, degraded_service):
        """旧判据（本项目曾用的写法）无法发现降级

        对应修复前的 `health.py`: `"ok" if test_vec and len(test_vec) > 0`。
        """
        vec = degraded_service.embed("测试文本")
        naive_ok = bool(vec) and len(vec) > 0
        assert naive_ok is True, "旧判据必然判为健康——这就是静默降级的根因"
        # 而真实状态是降级
        assert degraded_service.is_degraded is True

    def test_active_backend_is_hash(self, degraded_service):
        """实际后端应被如实记录为 hash"""
        degraded_service.embed("测试文本")
        assert degraded_service.active_backend == "hash"
        assert degraded_service.is_degraded is True

    def test_degraded_reason_is_populated(self, degraded_service):
        """必须能说出**为什么**降级，否则用户无从修复"""
        degraded_service.embed("测试文本")
        reason = degraded_service.stats.get("degraded_reason")
        assert reason, "降级原因不得为空"
        assert "onnx" in reason.lower() or "ONNX" in reason

    def test_stats_exposes_backend(self, degraded_service):
        """stats 需暴露后端与降级标志（供 /health 与监控消费）"""
        degraded_service.embed("测试文本")
        stats = degraded_service.stats
        assert stats["active_backend"] == "hash"
        assert stats["degraded"] is True

    def test_logs_error_once(self, degraded_service, caplog):
        """降级必须打 ERROR 级日志，且**只打一次**（避免刷屏掩盖其它日志）"""
        import logging

        with caplog.at_level(logging.ERROR, logger="pangu.memory.embed"):
            for _ in range(5):
                degraded_service.embed(f"文本-{_}")
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert errors, "降级未产生任何 ERROR 日志"
        assert len(errors) == 1, f"降级日志应只打一次，实际 {len(errors)} 次"


class TestNoFalsePositive:
    """反向保证：ONNX 正常时不得误报降级"""

    def test_onnx_backend_reported_when_available(self):
        """ONNX 可用时应报 onnx，而非 hash"""
        from pangu.memory.onnx_embedder import get_onnx_embedder

        emb = get_onnx_embedder()
        if not emb._ensure_loaded():
            pytest.skip("ONNX 模型不可用（CI 冷缓存/网络受限），无法验证正常路径")

        from pangu.memory.embedding import EmbeddingService

        svc = EmbeddingService(PanguConfig())
        svc.embed("测试文本")
        assert svc.active_backend == "onnx"
        assert svc.is_degraded is False
        assert "degraded_reason" not in svc.stats


class TestHealthReportsDegraded:
    """端到端：/health 必须把降级暴露出来"""

    def test_deep_health_reports_degraded(self, degraded_service, monkeypatch):
        """降级时 deep_health_check 的 embedding 段应为 degraded 而非 ok"""
        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", degraded_service)

        from pangu.observability.health import deep_health_check

        result = deep_health_check()
        emb = result["checks"]["embedding"]
        assert emb["status"] == "degraded", f"应报 degraded，实际 {emb['status']}"
        assert emb["backend"] == "hash"
        assert "error" in emb, "降级时应给出可读原因"

    def test_deep_health_overall_degraded(self, degraded_service, monkeypatch):
        """总体 status 也应为 degraded（而非 ok）"""
        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", degraded_service)

        from pangu.observability.health import deep_health_check

        assert deep_health_check()["status"] == "degraded"

    def test_stats_read_after_embed(self, degraded_service, monkeypatch):
        """回归：stats 必须在 embed() **之后**读取

        `stats` 是 property，每次调用重建 dict。若在 embed() 前读取，
        会拿到 active_backend="unknown" 的初始快照，导致降级永远测不出来。
        这个顺序曾经写反过（health.py），故加测试锁死。
        """
        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", degraded_service)

        from pangu.observability.health import _check_embedding_health

        result = _check_embedding_health()
        assert result["backend"] != "unknown", (
            "backend 为 unknown 说明 stats 在 embed() 之前被读取——顺序反了会永远检测不到降级"
        )
        assert result["status"] == "degraded"


class TestPartialDegradationIsVisible:
    """**部分**降级也必须可观测

    比整批降级更隐蔽的情形：`embed_batch()` 里 ONNX 只对一部分文本失败，
    其余正常。此时后端仍是 `onnx`（因为整体可用），但返回的向量里
    混着 hash 补位——**部分无语义**。若只看 `active_backend`，
    这种情况完全不可见，属于同一类"静默错误"。
    """

    def test_partial_fill_counts_and_warns(self, monkeypatch, caplog):
        import logging

        import pangu.memory.embedding as em

        # 构造：ONNX 可用，但只对偶数下标成功，奇数返回 None → 被 hash 补位
        class FlakyONNX:
            is_available = True

            def embed_batch(self, texts):
                return [([0.1] * 384 if i % 2 == 0 else None) for i in range(len(texts))]

            def get_stats(self):
                return {"model_loaded": True}

        svc = em.EmbeddingService(PanguConfig())
        svc._onnx = FlakyONNX()
        svc._api_url = None  # 确保不走远程 API 分支

        with caplog.at_level(logging.WARNING):
            out = svc.embed_batch(["a", "b", "c", "d"])

        assert len(out) == 4
        assert all(v is not None for v in out), "补位后每条都应向量"
        # 后端整体仍可用 → 保持 onnx，不能谎报 hash
        assert svc.active_backend == "onnx"
        # 但部分补位必须被计数 + 告警，否则这种降级无人知晓
        assert svc.partial_hash_vectors == 2, f"应有 2 条 hash 补位，实际 {svc.partial_hash_vectors}"
        assert svc.stats.get("partial_hash_vectors") == 2
        assert any("hash" in r.message for r in caplog.records), "部分降级应打 WARNING"


class TestHashVectorHasNoSemantics:
    """记录 hash 向量"无语义能力"这一事实，防止有人误以为它能兜底"""

    @staticmethod
    def _cos(a, b):
        import numpy as np

        a, b = np.array(a), np.array(b)
        n = np.linalg.norm(a) * np.linalg.norm(b)
        return float(a @ b / n) if n else 0.0

    def test_synonyms_are_not_similar(self, degraded_service):
        """同义词不应表现出高相似——hash 是字符级的，不懂含义

        注：(猫, 猫咪) 的 cos 约 0.7071 是**共享汉字"猫"**造成的字符巧合，
        不是语义理解。这里选一对**无共同字符**的同义词来证伪语义能力。
        """
        v1 = degraded_service.embed("汽车")
        v2 = degraded_service.embed("轿车")
        # 没有共享字符时，hash 向量几乎正交
        assert abs(self._cos(v1, v2)) < 0.5, "若此处相似度高，说明 hash 向量碰巧有语义——那本文件的立论需要重新审视"

    def test_unrelated_may_collide(self, degraded_service):
        """无关词可能因字符碰撞而"相似"——这正是无语义的证据"""
        # (股票, 股市) 共享"股"字 → 0.5，但共享字符不代表同义
        v1 = degraded_service.embed("股票")
        v2 = degraded_service.embed("股市")
        cos = self._cos(v1, v2)
        # 这里不断言具体数值（会随 embedding_dim 漂移），
        # 只断言"相似度由字符共享驱动"这一事实可被观察到
        assert cos > 0.0, "共享字符应产生非零相似度"


class TestAllowHashFallbackConfig:
    """`PANGU_ALLOW_HASH_FALLBACK`：默认拒绝降级"""

    def test_default_is_false(self):
        """默认必须是不允许——静默降级是错的，要显式 opt-in"""
        assert PanguConfig().allow_hash_fallback is False

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PANGU_ALLOW_HASH_FALLBACK", "1")
        assert PanguConfig().allow_hash_fallback is True


class TestQuickHealthReflectsDegradation:
    """`/health`（quick）也必须反映降级

    为什么单独测：`quick_health_check()` 是监控系统轮询的**便宜端点**。
    它修复前无条件返回 `"status": "ok"`——即使用户只轮询这个端点，
    也永远看不到降级。deep 检查再准也没用，因为没人轮询它。
    """

    def test_quick_health_degraded(self, degraded_service, monkeypatch):
        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", degraded_service)
        degraded_service.embed("先确定状态")  # 模拟启动体检已跑过

        from pangu.observability.health import quick_health_check

        r = quick_health_check()
        assert r["status"] == "degraded", f"quick health 应报 degraded，实际 {r['status']}"
        assert r["embedding_backend"] == "hash"
        assert r["embedding_degraded"] is True

    def test_quick_health_ok_when_healthy(self, monkeypatch):
        """反向：正常时必须是 ok，不能把 unknown/正常误判为降级"""
        from pangu.memory.embedding import EmbeddingService

        svc = EmbeddingService(PanguConfig())
        svc.embed("通常")
        if svc.active_backend == "hash":
            pytest.skip("本环境 ONNX 不可用，无法验证正常路径")

        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", svc)

        from pangu.observability.health import quick_health_check

        r = quick_health_check()
        assert r["status"] == "ok"
        assert r["embedding_backend"] == svc.active_backend
        assert "embedding_degraded" not in r

    def test_quick_health_is_cheap(self, monkeypatch):
        """quick 检查不得触发真实嵌入（它被设计为 <10ms 的低成本探针）"""
        calls = []

        class _Stub:
            active_backend = "onnx"

            def embed(self, text):
                calls.append(text)
                return [0.0] * 384

        import pangu.memory.embedding as em

        monkeypatch.setattr(em, "_embed_service", _Stub())

        from pangu.observability.health import quick_health_check

        quick_health_check()
        assert not calls, "quick_health_check 不应触发嵌入（会拖慢监控轮询）"
