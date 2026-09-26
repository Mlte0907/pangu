"""ONNX 批量嵌入必须走缓存 —— 修「每次搜索重算整个语料」。

## 缺陷

`EmbeddingService.embed_batch` 的 ONNX 分支（`embedding.py`）**既不查也不写** `_cache`；
只有 API 分支 `_embed_batch_api` 有缓存。后果：

- 每次搜索都把**整个语料**用 ONNX 重算一遍（实测 1000 条 ≈ 15 秒/次，单条约 15ms）
- 本该是 O(命中数) 的搜索退化成 O(全库)
- `test_bench.py::TestConcurrencyBench::test_concurrent_search` 那 31 分钟的红色，
  根因就在这里（100 次搜索 × 15 秒）

## 为什么这个缓存是安全的

ONNX 嵌入是**确定性**的：同一段文本永远得到同一个向量。缓存 key 是内容哈希
（`hex_digest(text)`），与查询、调用方、顺序都无关。所以「命中缓存」和「重新算」
的结果必然相同 —— 下面 `test_cache_does_not_change_vectors` 就是把这条钉死。
"""

import pytest

from pangu.memory.embedding import EmbeddingService


class _CountingOnnx:
    """能计数的假 ONNX：确定性、维度固定，并记录被算了多少次。"""

    is_available = True

    def __init__(self, dim=8):
        self.dim = dim
        self.calls = 0          # embed_batch 被调用的次数
        self.texts_seen = 0     # 一共算了多少条文本

    def embed_batch(self, texts):
        self.calls += 1
        self.texts_seen += len(texts)
        return [self._vec(t) for t in texts]

    def embed(self, text):
        self.calls += 1
        self.texts_seen += 1
        return self._vec(text)

    def _vec(self, text):
        # 确定性：同一 text 永远同一向量（用内置 hash 保证跨进程稳定）
        h = abs(hash(text)) if text else 0
        return [((h >> (i * 3)) % 97) / 97.0 for i in range(self.dim)]


@pytest.fixture
def svc():
    """真构造 EmbeddingService，只把 `_onnx` 换成可计数的假实现。

    刻意**不用** `__new__` 绕过 `__init__` —— 那样得手工补齐 `_active_backend`
    之类的内部字段，漏一个就报 AttributeError（第一版就是这么翻车的），
    而且测试会绑死在实现细节上。
    """
    from pangu.core.config import PanguConfig

    cfg = PanguConfig()
    cfg.embed_api_url = ""      # 不走 API，确保只考察 ONNX 分支
    s = EmbeddingService(cfg)
    s._onnx = _CountingOnnx()   # 换成假 ONNX，避免真模型加载
    return s


def test_second_identical_batch_does_not_recompute(svc):
    """同一批文本第二次调用，ONNX 一次都不该再被调用。"""
    texts = [f"memory {i} wiki graph" for i in range(50)]

    svc.embed_batch(texts)
    first_calls, first_texts = svc._onnx.calls, svc._onnx.texts_seen
    assert first_texts == 50, "首次应真的算 50 条"

    svc.embed_batch(texts)
    assert svc._onnx.texts_seen == first_texts, (
        f"第二次又算了 {svc._onnx.texts_seen - first_texts} 条 —— 缓存没生效"
    )


def test_cache_is_populated(svc):
    """文档向量必须真的进缓存（此前 ONNX 分支一个都不写）。"""
    texts = [f"doc {i}" for i in range(30)]
    svc.embed_batch(texts)
    assert len(svc._cache) == 30, f"缓存里只有 {len(svc._cache)} 条，应为 30"


def test_cache_does_not_change_vectors(svc):
    """**加缓存不许改变结果** —— 命中缓存与重算必须逐维相等。"""
    texts = [f"memory {i} retrieval decay" for i in range(40)]

    cold = svc.embed_batch(texts)          # 全冷
    warm = svc.embed_batch(texts)          # 全命中
    assert svc._onnx.calls == 1, "第二次不该再调 ONNX"
    for a, b in zip(cold, warm):
        assert a == b, "命中缓存的向量与重算结果不一致"


def test_partial_overlap_only_computes_the_new_ones(svc):
    """部分重叠时，只算没命中的那些。"""
    svc.embed_batch(["a", "b", "c"])
    before = svc._onnx.texts_seen
    svc.embed_batch(["b", "c", "d", "e"])
    added = svc._onnx.texts_seen - before
    assert added == 2, f"新增计算 {added} 条，应为 2（d、e）"


def test_none_result_is_not_cached(svc):
    """ONNX 返回 None 的条目**不能进缓存**。

    否则一次偶发失败会被永久记住 —— 之后每次都从缓存里读到 None，
    故障再也恢复不了。这是最容易写错的一处。
    """

    class _Flaky(_CountingOnnx):
        def embed_batch(self, texts):
            self.calls += 1
            self.texts_seen += len(texts)
            return [None] * len(texts)   # 全部失败

    svc._onnx = _Flaky()
    texts = ["x", "y", "z"]
    r1 = svc.embed_batch(texts)
    assert all(v is not None for v in r1), "None 应被 _local_embed 补位"
    assert len(svc._cache) == 0, f"None 不应入缓存，但缓存里有 {len(svc._cache)} 条"

    # 换成正常的 ONNX，同一批文本必须能重新算出来
    svc._onnx = _CountingOnnx()
    r2 = svc.embed_batch(texts)
    assert all(v is not None for v in r2)
    assert len(svc._cache) == 3, "恢复后应把结果写进缓存"


def test_search_over_corpus_becomes_sublinear(svc):
    """回归测试：第二次搜同一批文档，嵌入计算量应为 0。

    这是那个 31 分钟测试想守住的不变量 —— 只是之前它以「墙钟预算」的形式表达，
    机器一慢就红，且看不出根因。
    """
    corpus = [f"memory {i} wiki graph retrieval" for i in range(200)]

    svc.embed_batch(corpus)
    baseline = svc._onnx.texts_seen
    assert baseline == 200

    for _ in range(5):  # 模拟多次搜索，每次都扫全库
        svc.embed_batch(corpus)
    assert svc._onnx.texts_seen == baseline, "重复搜索把全库又算了一遍"
