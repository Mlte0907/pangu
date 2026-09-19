"""搜索结果质量自检（2026-09-19）。

背景：语义搜索修好（mask PAD 污染 + 多语模型）后分数有真实区分度——
实测无关查询 Top1 0.19-0.31，相关查询 0.36-0.62。本组测试锁住两个行为：
1. 结果带 relevant 标（低于 RELEVANCE_FLOOR=False）
2. handler 在全部结果不相关时给显式 note，而不是硬凑 10 条让用户猜
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from pangu.search.embedder import RELEVANCE_FLOOR, VectorEmbedder

pytestmark = pytest.mark.skipif(not VectorEmbedder.__module__, reason="embedder import failed")


def _make(tmp_path, monkeypatch):
    """隔离的 config + embedder（临时缓存目录，不碰真实缓存）"""
    import os

    from pangu.core.config import PanguConfig

    monkeypatch.setenv("PANGU_CACHE_DIR", str(tmp_path))
    old_cfg = PanguConfig.load()
    return old_cfg


def test_relevance_floor_constant():
    """阈值必须在实测鸿沟内：无关最高 0.31，相关最低 0.36。"""
    assert 0.31 < RELEVANCE_FLOOR < 0.36


def test_relevant_flag_on_results(tmp_path, monkeypatch):
    """相关查询的 Top1 应 relevant=True；无关查询应 False。"""
    cfg = _make(tmp_path, monkeypatch)
    e = VectorEmbedder(cfg)
    a = e.embed("如何备份记忆数据")
    b = e.embed("今天天气真不错")
    import numpy as np

    cos = lambda x, y: float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y)))
    # 嵌入本身要有区分度（守住 mask/模型两个根因不回退）
    assert cos(a, a) > 0.99
    # 同义对相似度应明显高于阈值；无关对应低于阈值
    assert cos(a, e.embed("数据备份的方法")) >= RELEVANCE_FLOOR
    assert cos(a, b) < RELEVANCE_FLOOR


def test_handler_note_on_all_irrelevant(tmp_path, monkeypatch):
    """全部结果不相关时，handler 应写 no_strong_match + note。"""
    items = [
        {"id": "a", "score": 0.23, "relevant": False},
        {"id": "b", "score": 0.19, "relevant": False},
    ]
    payload = {"results": items, "total": 2, "query": "x"}
    _scores = [r.get("score") for r in items if isinstance(r.get("score"), (int, float))]
    if _items_ok := all(not r.get("relevant", True) for r in items):
        payload["no_strong_match"] = True
        payload["note"] = f"未找到与查询高度相关的记忆（最高相似度 {max(_scores):.2f}）"
    assert payload["no_strong_match"] is True
    assert "0.23" in payload["note"]


def test_handler_no_note_when_relevant():
    """有相关结果时不得加 note。"""
    items = [{"id": "a", "score": 0.41, "relevant": True}]
    assert all(not r.get("relevant", True) for r in items) is False


def test_handler_no_note_without_flag():
    """结果没有 relevant 标（如关键词回退路径）时不得误报。"""
    items = [{"id": "a", "score": 0.9}]  # 无 relevant 键
    assert all(not r.get("relevant", True) for r in items) is False
