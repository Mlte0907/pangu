"""`pangu_search_memories` 的检索状态与收据（2026-09-28，借鉴 DSH-KRouter）。

改造动机：KRouter 的 README/PROTOCOL 反复强调 *"Neighbor cite is a failure"*
—— 未命中就明说 miss 并给 hints，**不许装作有答案**。盘古此前只有
`no_strong_match` 一个零散标记，调用方无法系统地区分「命中 / 弱命中 / 没命中」，
也拿不到可核对的分数与阈值。

本文件锁三件事：
  1. `retrieval_status` 三态判定正确（含阈值边界 0.32）；
  2. `weak` / `miss` 必须给 `hints` + `hints_note`，`hit` **不给**（避免误当答案）；
  3. `receipt` 字段齐全且**可核对**（top_score / threshold / results / channels），
     且新增字段**不得破坏**老的 `results`/`total`/`query`/`no_strong_match`。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from pangu.server.handlers.memory_ops import (
    STRONG_MATCH_THRESHOLD,
    handle_search_memories,
)


class _FakeSearch:
    """与真实 `search/engine.HybridSearch.search` 一致：**返回 list**。

    handler 对 list 会补 `query` 字段（memory_ops.py:353-357 的
    `if isinstance(results, list)` 分支）；返回 dict 会走另一分支、丢掉 query。
    """

    def __init__(self, results):
        self._results = results
        self.calls = 0

    def search(self, query, drawers, wing=None, room=None, n_results=10):
        self.calls += 1
        return list(self._results)


class _FakeMemory:
    def __init__(self):
        self.accessed: list = []

    def record_access(self, ids):
        self.accessed.extend(ids)


class _FakeServer:
    def __init__(self, results):
        self.search = _FakeSearch(results)
        self.memory = _FakeMemory()


def _item(
    i: int,
    score: float = 0.5,
    relevant: bool = True,
    relevance: float | None = None,
    fts_rank: int | None = None,
) -> dict:
    """构造一条搜索结果。

    ⚠ `score` 是**归一化的 rrf_score**（第一名恒 1.0，不能当判据）；
    `relevance` 才是**原始余弦相似度**，`retrieval_status` 靠它判定；
    `fts_rank` 用于「无向量相似度时的字面命中」降级判定。
    """
    return {
        "id": f"m{i}",
        "content": f"记忆内容 {i}",
        "wing": "技术",
        "room": "general",
        "importance": 3.0,
        "created_at": "2026-09-28T00:00:00",
        "score": score,
        "relevance": relevance,
        "relevant": relevant,
        "fts_rank": fts_rank,
        "source": "semantic" if i % 2 else "lexical",
    }


def _run(results, query="llmDaily 根因") -> dict:
    """跑一次 handler，返回解析后的 payload。"""
    srv = _FakeServer(results)
    drawers = []  # 预过滤用不到，交空即可
    out = asyncio.run(
        handle_search_memories(srv, drawers, {"query": query, "limit": 10})
    )
    return json.loads(out)


class TestRetrievalStatus:
    """① 三态判定 —— 让「没命中」成为一等公民。判据是 relevance（原始 sim）。"""

    def test_hit_when_relevance_meets_threshold(self):
        p = _run([_item(1, relevance=0.61), _item(2, relevance=0.45)])
        assert p["retrieval_status"] == "hit", p["retrieval_status"]

    def test_weak_when_relevance_below_threshold(self):
        p = _run([_item(1, relevance=0.19), _item(2, relevance=0.31)])
        assert p["retrieval_status"] == "weak", p["retrieval_status"]

    def test_miss_when_no_results(self):
        p = _run([])
        assert p["retrieval_status"] == "miss", p["retrieval_status"]

    @pytest.mark.parametrize(
        "rel,expect",
        [(STRONG_MATCH_THRESHOLD, "hit"),                    # 恰好等于阈值 ⇒ 算命中
         (STRONG_MATCH_THRESHOLD - 0.01, "weak")],           # 低于 ⇒ 弱
    )
    def test_threshold_boundary_is_inclusive(self, rel, expect):
        p = _run([_item(1, relevance=rel)])
        assert p["retrieval_status"] == expect, f"{rel} → {p['retrieval_status']}"

    def test_normalized_score_cannot_fake_a_hit(self):
        """★ 归一化分数第一名恒为 1.0 —— 必须证明它**骗不过**状态判定。

        2026-09-28 实测事故：拿 score(=1.0) 比 0.32 阈值，导致「蓝鲸迁徙/量子隧穿」
        这种风马牛不相及的查询也判 hit。relevance 低就必须 weak，哪怕 score 满分。
        """
        p = _run([_item(1, score=1.0, relevance=0.11)])
        assert p["retrieval_status"] == "weak", (
            f"score=1.0 但 relevance=0.11，应判 weak，实际 {p['retrieval_status']}"
        )
        assert p["receipt"]["top_score"] == 1.0          # 回显归一化分
        assert p["receipt"]["top_relevance"] == 0.11     # 判据是它

    def test_lexical_hit_without_vectors_counts_as_hit(self):
        """无向量相似度但 FTS 命中 ⇒ 算 hit（确定性字面召回本身就是有效答案）。"""
        p = _run([_item(1, relevance=None, fts_rank=1)])
        assert p["retrieval_status"] == "hit", p["retrieval_status"]

    def test_no_vector_and_no_fts_is_weak(self):
        """既无向量相似度、又无字面命中 ⇒ weak，不能冒充 hit。"""
        p = _run([_item(1, relevance=None, fts_rank=None)])
        assert p["retrieval_status"] == "weak", p["retrieval_status"]


class TestHints:
    """② hints 只在没命中时给，且必须声明「这是线索不是答案」。"""

    def test_weak_carries_hints(self):
        p = _run([_item(1, relevance=0.22), _item(2, relevance=0.18)])
        assert p["retrieval_status"] == "weak"
        assert p.get("hints"), "weak 必须给 hints"
        assert p.get("hints_note"), "hints 必须附说明，防止被当成答案"
        assert "线索" in p["hints_note"]
        assert len(p["hints"]) <= 5

    def test_hit_has_no_hints(self):
        """命中时不许给 hints —— 否则调用方可能拿线索当答案。"""
        p = _run([_item(1, relevance=0.88)])
        assert p["retrieval_status"] == "hit"
        assert "hints" not in p, "hit 不该带 hints"
        assert "hints_note" not in p

    def test_miss_still_returns_receipt(self):
        p = _run([])
        assert p["retrieval_status"] == "miss"
        assert p["receipt"]["results"] == 0
        # 空结果时 hints 允许缺省或为空，但状态必须是 miss 而非 hit
        assert p["retrieval_status"] != "hit"


class TestReceipt:
    """③ receipt 要能被调用方核对（可审计）。"""

    def test_receipt_fields_complete(self):
        p = _run([_item(1, relevance=0.77), _item(2, relevance=0.50)])
        r = p["receipt"]
        for key in ("queried_at", "top_score", "top_relevance", "threshold",
                    "results", "channels", "elapsed_ms"):
            assert key in r, f"receipt 缺 {key}: {sorted(r)}"

    def test_receipt_top_relevance_is_the_judgement_metric(self):
        """top_relevance 才是判据（原始 sim）；top_score 只是归一化排序分。"""
        p = _run([_item(1, score=1.0, relevance=0.41), _item(2, score=0.6, relevance=0.29)])
        r = p["receipt"]
        assert r["top_relevance"] == pytest.approx(0.41, abs=1e-4)
        assert r["top_score"] == pytest.approx(1.0, abs=1e-4)
        assert r["top_relevance"] != r["top_score"], "两个分数必须能区分开"

    def test_receipt_top_score_is_actual_max(self):
        p = _run([_item(1, score=0.42), _item(2, score=0.93), _item(3, score=0.11)])
        assert p["receipt"]["top_score"] == pytest.approx(0.93, abs=1e-4)

    def test_receipt_threshold_matches_constant(self):
        p = _run([_item(1, relevance=0.9)])
        assert p["receipt"]["threshold"] == STRONG_MATCH_THRESHOLD == 0.32

    def test_receipt_results_matches_returned_count(self):
        items = [_item(i, 0.5) for i in range(4)]
        p = _run(items)
        assert p["receipt"]["results"] == 4
        assert p["total"] == 4
        assert len(p["results"]) == 4

    def test_receipt_channels_lists_sources(self):
        p = _run([_item(1, 0.9), _item(2, 0.9)])   # 1→semantic, 0→lexical 交替
        assert set(p["receipt"]["channels"]) <= {"semantic", "lexical"}


class TestBackwardCompatibility:
    """④ 新字段不得破坏老契约 —— 下游仍读 results/total/query/no_strong_match。"""

    def test_old_fields_preserved(self):
        p = _run([_item(1, 0.7)], query="部署方式")
        assert p["query"] == "部署方式"
        assert isinstance(p["results"], list)
        assert p["total"] == 1

    def test_no_strong_match_still_set_when_all_irrelevant(self):
        """老标记 no_strong_match 必须继续存在（2026-09-19 引入，别丢）。"""
        p = _run([_item(1, 0.5, relevant=False), _item(2, 0.4, relevant=False)])
        assert p.get("no_strong_match") is True
        assert "note" in p
        assert "可信阈值" in p["note"]

    def test_scores_absent_does_not_crash(self):
        """没有 score 字段时不能因为 max([]) 把整段吞掉。"""
        bare = [{"id": "x", "content": "无分数", "wing": "w", "room": "r",
                 "created_at": "2026-09-28", "relevant": False}]
        p = _run(bare)
        assert p["retrieval_status"] in ("weak", "miss")
        assert "receipt" in p
        assert p["receipt"]["top_score"] == 0.0
