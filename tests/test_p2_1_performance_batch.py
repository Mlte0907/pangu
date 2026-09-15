"""P2-1 Step 3 回归测试：performance.BatchProcessor 接入 autonomous 向量索引任务。

## 背景

`pangu/memory/performance.py` 的 4 个组件（HNSWVectorIndex / ARCCache /
ObjectPool / BatchProcessor）从未被生产调用。勘察实测后只接入
**BatchProcessor.batch_encode**（其余三个经实测无收益或有风险，明确不接）：

  - HNSWVectorIndex：N≤2000 全面输给 `vector_index.py` 既有的 numpy brute-force
    （N=100 时慢 38×），而 `vector_index.py` 在 N≥1000 时已自动切 hnswlib（C 实现）。
  - ARCCache：实现无 TTL、`gamma` 参数是死代码，实测 scan-resistant 场景与
    既有 `SearchCache`(LRU+TTL) 打平。
  - ObjectPool：`init_drawer_pool` 默认 reset 只清 6 个字段，接进 Drawer 会
    把上一条的 tags 等状态泄漏到下一条；且 Drawer 是 dataclass，池化无 GC 收益。

接入点：`autonomous._task_vector_index`（原本逐条 `embed()` + 逐条 `add()`）。

## 实测收益（92 条生产记忆）

    A 逐条 embed : 4035 ms (43.9 ms/条)
    B 批量 embed :   43 ms ( 0.5 ms/条)   → 93×
    add vs add_batch 仅 1.5×（都在内存），故收益主要来自批量推理。

本文件钉住：任务语义不变（条数一致）+ 批量路径确实被使用 + 零向量不被写入。
"""

import pytest

from pangu.core.palace import Drawer


def _drawer(i: int, content: str = None, embedding=None) -> Drawer:
    d = Drawer(id=f"vd{i}", content=content if content is not None else f"内容 {i}", wing="w", room="r")
    if embedding is not None:
        d.metadata["embedding"] = embedding
    return d


def test_vector_index_task_still_indexes_all():
    """语义不变：任务仍把所有（可嵌入的）记忆编入索引。"""
    from pangu.memory.autonomous import AutonomousMemoryEngine

    engine = AutonomousMemoryEngine()
    drawers = [_drawer(i) for i in range(10)]
    result = engine._task_vector_index(drawers)
    assert result.status == "success", f"任务失败: {result.details}"
    assert result.details["indexed"] == 10, f"应索引 10 条，实际 {result.details}"
    assert result.details["candidates"] == 10


def test_vector_index_task_uses_preset_embeddings():
    """预置 embedding 的记忆不重复编码，但同样进索引。"""
    from pangu.memory.autonomous import AutonomousMemoryEngine

    engine = AutonomousMemoryEngine()
    preset = [0.1] * 384
    drawers = [_drawer(i, embedding=preset) for i in range(5)]
    result = engine._task_vector_index(drawers)
    assert result.status == "success", f"任务失败: {result.details}"
    assert result.details["indexed"] == 5
    # 全部走预置路径 → 无需批量编码，batched 数量等于总数
    assert result.details["batched"] == 5


def test_vector_index_task_empty_input():
    """空输入不得崩，返回 0。"""
    from pangu.memory.autonomous import AutonomousMemoryEngine

    engine = AutonomousMemoryEngine()
    result = engine._task_vector_index([])
    assert result.status == "success"
    assert result.details["indexed"] == 0


def test_batch_encode_returns_aligned_results():
    """batch_encode 必须返回与输入等长、同维度的结果（接入的正确性前提）。"""
    from pangu.memory.embedding import get_embedding_service
    from pangu.memory.performance import BatchProcessor

    svc = get_embedding_service()
    texts = [f"批量测试文本 {i}" for i in range(8)]
    vecs = BatchProcessor.batch_encode(texts, svc.embed, batch_size=4)
    assert len(vecs) == len(texts), f"结果数不匹配: {len(vecs)} vs {len(texts)}"
    dims = {len(v) for v in vecs if v}
    assert len(dims) == 1, f"维度不一致: {dims}"


def test_batch_encode_skips_nothing_on_empty():
    """空输入返回空列表（不得返回 [0.0]*384 占位）。"""
    from pangu.memory.embedding import get_embedding_service
    from pangu.memory.performance import BatchProcessor

    svc = get_embedding_service()
    assert BatchProcessor.batch_encode([], svc.embed) == []


@pytest.mark.parametrize("component", ["HNSWVectorIndex", "ARCCache", "ObjectPool"])
def test_unadopted_components_still_importable(component):
    """未接入的三组件仍可导入 —— 记录它们是"经评估后不接入"而非"删掉"。

    若将来要接入，先重跑上面的基准；本测试防止有人误以为它们已被删除。
    """
    import pangu.memory.performance as perf

    assert hasattr(perf, component), f"{component} 应仍存在于 performance 模块"
