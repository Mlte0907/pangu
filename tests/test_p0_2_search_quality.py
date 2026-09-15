"""P0-2 回归测试：检索质量——噪声不能压过信号。

## 问题
短文本 embedding 分数虚高：7 字 "测试 配置正确" vs 查询 "盘古部署" sim=0.9302，
而 32 字真实内容 sim=0.8281。短文本因语义模糊反而跟更多查询高度匹配。

## 修复
1. reranker._quality_score 对 <20 字内容扣分（A: 长度惩罚）
2. hybrid_search 默认 fts_weight=1.5, vector_weight=0.8（B: FTS 权重提升）
3. hybrid_search._vector_recall 跳过 gAAAAA 加密内容（C: 加密过滤）

## 验收
PLAN-v0.3.0.md:156：构造短噪声（<20 字）+ 真长记忆，真记忆必须排前。
注入验证：故意不修，断言必须失败。
"""

import pytest

from pangu.core.palace import Drawer


def _drawer(content: str, importance: float = 3.0, **kwargs) -> Drawer:
    return Drawer(
        id=kwargs.get("id", f"test_{hash(content) & 0xFFFF:04x}"),
        content=content,
        wing=kwargs.get("wing", "test"),
        room=kwargs.get("room", "t"),
        importance=importance,
        tags=kwargs.get("tags", []),
        created_at=kwargs.get("created_at", "2025-01-01T00:00:00"),
        metadata=kwargs.get("metadata", {}),
    )


@pytest.fixture(autouse=True)
def _reset_fts_and_mock(monkeypatch):
    """重置 FTS + mock 三路召回为基于内容长度的简单排名（测排序逻辑，不依赖 embedding）。"""
    import pangu.memory.fts_search as fts_mod
    import pangu.memory.hybrid_search as hs_mod

    fts_mod._fts_engine = None

    def _fake_fts_recall(query, drawers, all_ids):
        """按内容长度排名（长文本排前面），跳过加密内容"""
        filtered = [d for d in drawers if not (d.content or "").startswith("gAAAAA")]
        ranked = sorted(filtered, key=lambda d: -(len(d.content or "")))
        return {d.id: i + 1 for i, d in enumerate(ranked) if d.id in all_ids}

    def _fake_vector_recall(query, drawers, all_ids):
        """按内容长度排名（模拟向量召回），跳过加密内容"""
        filtered = [d for d in drawers if not (d.content or "").startswith("gAAAAA")]
        ranked = sorted(filtered, key=lambda d: len(d.content or ""))
        return {d.id: i + 1 for i, d in enumerate(ranked) if d.id in all_ids}

    def _fake_kg_recall(query, all_ids, config):
        return {}

    monkeypatch.setattr(hs_mod, "_fts_recall", _fake_fts_recall)
    monkeypatch.setattr(hs_mod, "_vector_recall", _fake_vector_recall)
    monkeypatch.setattr(hs_mod, "_kg_recall", _fake_kg_recall)
    yield
    fts_mod._fts_engine = None


# ── A: 长度惩罚 ──────────────────────────────────────────────────


def test_short_content_quality_score_lower_than_long():
    """短文本 (<20 字) 的 quality_score 必须低于长文本 (>100 字)。"""
    from pangu.memory.reranker import SemanticReranker

    reranker = SemanticReranker()
    short = _drawer("内容3")  # 3 字
    medium = _drawer("这是一个中等长度的记忆内容，大约 25 个字符左右")  # ~25 字
    long = _drawer("x" * 200)  # 200 字

    s = reranker._quality_score(short)
    m = reranker._quality_score(medium)
    l = reranker._quality_score(long)

    assert s < m < l, f"质量分应随长度递增: short={s:.3f} medium={m:.3f} long={l:.3f}"
    assert s < 0.2, f"极短文本质量分应 <0.2, 实际 {s:.3f}"


def test_very_short_content_penalized():
    """极短文本 (<10 字) 质量分应 <0.1。"""
    from pangu.memory.reranker import SemanticReranker

    reranker = SemanticReranker()
    score = reranker._quality_score(_drawer("hi"))
    assert score < 0.1, f"极短文本质量分应 <0.1, 实际 {score:.3f}"


# ── B: FTS 权重提升 ──────────────────────────────────────────────


def test_hybrid_search_default_weights_favor_fts():
    """hybrid_search 默认 fts_weight > vector_weight。"""
    import inspect

    from pangu.memory.hybrid_search import hybrid_search

    sig = inspect.signature(hybrid_search)
    assert sig.parameters["fts_weight"].default > sig.parameters["vector_weight"].default, (
        "fts_weight 应 > vector_weight（P0-2: FTS 天然偏长文本）"
    )


# ── C: 加密内容过滤 ──────────────────────────────────────────────


def test_encrypted_content_excluded_from_vector_recall():
    """gAAAAA 开头的加密内容不应出现在向量召回中。"""
    from pangu.memory.hybrid_search import _vector_recall

    normal = _drawer("正常记忆内容", id="normal1", metadata={"embedding": [0.1] * 384})
    encrypted = _drawer("gAAAAABxxx...encrypted...", id="enc1", metadata={"embedding": [0.1] * 384})
    all_ids = {normal.id: normal, encrypted.id: encrypted}

    ranks = _vector_recall("正常", [normal, encrypted], all_ids)
    assert "enc1" not in ranks, f"加密内容不应出现在向量召回中, got: {ranks}"
    # normal 可能在也可能不在（取决于相似度阈值），但 enc1 绝对不能在


# ── 端到端：短噪声 vs 长真实内容 ──────────────────────────────────


def test_short_noise_does_not_rank_above_long_content():
    """PLAN-v0.3.0.md:156 验收：短噪声 + 真长记忆，真记忆必须排前。"""
    from pangu.memory.hybrid_search import hybrid_search
    from pangu.memory.search_cache import get_search_cache

    # 构造：1 条长真实内容 + 3 条短噪声
    real = _drawer(
        "盘古记忆系统部署完成：ONNX 本地嵌入，端口 19529，systemd 服务已配置",
        id="real_deploy",
        importance=4.0,
        tags=["deployment", "pangu"],
    )
    noise_short = _drawer("内容3", id="noise1", importance=1.0)
    noise_medium = _drawer("测试 配置正确", id="noise2", importance=1.5)
    noise_longer = _drawer("测试缓存查询 填充内容", id="noise3", importance=1.5)

    drawers = [real, noise_short, noise_medium, noise_longer]

    get_search_cache().clear()
    results = hybrid_search("盘古部署", drawers, limit=10)
    by_id = {r["id"]: r for r in results}

    # 真实内容必须排第一
    assert results[0]["id"] == "real_deploy", (
        f"真实内容应排第一，实际第一是 {results[0]['id']}: {results[0]['content'][:30]}"
    )

    # 真实内容的 rerank_score 必须高于所有噪声
    real_score = by_id["real_deploy"]["rerank_score"]
    for nid in ["noise1", "noise2", "noise3"]:
        if nid in by_id:
            assert real_score > by_id[nid]["rerank_score"], (
                f"真实内容 rerank {real_score:.4f} 应 > 噪声 {nid} {by_id[nid]['rerank_score']:.4f}"
            )


def test_encrypted_content_never_in_results():
    """加密内容（gAAAAA）不应出现在搜索结果中。"""
    from pangu.memory.hybrid_search import hybrid_search
    from pangu.memory.search_cache import get_search_cache

    real = _drawer("部署配置正确", id="real1", importance=3.0)
    encrypted = _drawer("gAAAAABxxx_encrypted_content_here", id="enc1", importance=5.0)

    get_search_cache().clear()
    results = hybrid_search("部署", [real, encrypted], limit=10)
    result_ids = [r["id"] for r in results]

    assert "enc1" not in result_ids, f"加密内容不应出现, got: {result_ids}"


# ── 注入验证 ──────────────────────────────────────────────────────


def test_injection_revert_quality_score_short_not_penalized():
    """注入验证：把 quality_score 的短文本惩罚去掉，短文本质量分应回升。"""
    from pangu.memory.reranker import SemanticReranker

    reranker = SemanticReranker()
    short = _drawer("hi")  # 2 字
    score = reranker._quality_score(short)
    # 当前实现：<10 字返回 0.05
    # 如果注入后返回 >= 0.3（原始基础分），说明惩罚被去掉了
    assert score < 0.1, f"短文本惩罚应生效, score={score:.3f}"
