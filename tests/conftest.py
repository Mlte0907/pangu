"""pytest session-level fixtures

解决离线环境下 sentence-transformers 模型下载超时问题：
使用 mock SentenceTransformer 避免网络请求，session 级别确保所有测试受益。
"""

import hashlib

import numpy as np
import pytest

# 手工 E2E 套件排除在自动收集之外。
#
# 原因：tests/manual_e2e/test_comprehensive.py 需要两样 CI 里没有的东西——
#   1) 本地已启动的盘古服务（127.0.0.1:19529）
#   2) tests/manual_e2e/mcp_helper.py，该文件从未入库
# 而它被 `pytest tests/` 一并收集，import 失败会让整个会话在**收集阶段**中断
# （Interrupted: 1 error during collection），1300+ 个单元测试一个都跑不到。
# 这正是 CI 的 Test 工作流在 3.10/3.11/3.12 上全部失败的原因。
#
# 注意：collect_ignore 必须放在 conftest.py 里，且路径相对本文件所在目录解析。
# 写在 pyproject.toml 的 [tool.pytest.ini_options] 中不生效——那里不支持
# 相对路径（实测仍然报同一个收集错误）。
#
# 需要跑 E2E 时显式指定，绕过本排除：
#   pytest tests/manual_e2e/test_comprehensive.py
collect_ignore_glob = ["manual_e2e/*"]

_VEC_DIM = 384  # all-MiniLM-L6-v2 向量维度


@pytest.fixture(autouse=True)
def _isolate_pangu_cache(tmp_path):
    """把每个用例的盘古缓存目录指向独立临时目录。

    为什么必须做：`pangu.memory.vector_index.VectorIndex` 等组件的 `_save()`
    默认写到 `$PANGU_CACHE_DIR`（回退到 `~/.cache/pangu/`）——也就是**用户真
    实的缓存目录**。一旦某个用例用非 384 维的假向量构建索引
    （如 `VectorIndex(dim=4)` 写入 a/b 两条），磁盘上的索引就被换成错误
    维度的数据；后续用例的单例从磁盘加载它，`add_batch` 因维度不匹配
    (`np.vstack` 报错) 失败，搜索恒为空——表现为与代码无关的、只在全量跑
    时才出现的失败。

    逐用例隔离（而非 session 级）还保证任何用例改动 `PANGU_CACHE_DIR`
    都不会泄漏给下一个用例。
    """
    import os

    prev = os.environ.get("PANGU_CACHE_DIR")
    os.environ["PANGU_CACHE_DIR"] = str(tmp_path / "pangu_cache")
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PANGU_CACHE_DIR", None)
        else:
            os.environ["PANGU_CACHE_DIR"] = prev


@pytest.fixture(autouse=True)
def _reset_vector_index_singleton():
    """每个用例前后都丢弃向量索引单例，避免跨用例状态泄漏。

    单例持有已加载的索引数据与后端句柄，若不复位，前一个用例写入的
    向量会在后一个用例里被当成"已有数据"，导致 `size` 断言与搜索结果
    互相干扰（实测：`assert 200 == 100`）。
    用例**前**也要重置——污染可能在用例调用 `get_vector_index()` 之前
    就已发生。
    """

    def _reset():
        try:
            from pangu.memory import vector_index as _vi

            reset = getattr(_vi, "reset_vector_index", None)
            if callable(reset):
                reset()
            else:
                _vi._vector_index = None
        except Exception:  # noqa: BLE001
            pass

    _reset()
    yield
    _reset()


def _make_deterministic_vector(texts):
    """根据文本内容生成确定性的假嵌入向量

    不同文本 → 不同向量（可保证语义相似性测试的正确性）
    相同文本 → 相同向量（保证缓存一致性）
    """
    if isinstance(texts, str):
        texts = [texts]

    vectors = []
    for text in texts:
        # 使用 hash 种子生成确定性的假向量
        seed_val = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**31)
        rng = np.random.RandomState(seed_val)
        # L2 归一化，模拟真实的 embedding 输出
        vec = rng.randn(_VEC_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)
        vectors.append(vec)

    if len(vectors) == 1:
        return vectors[0]
    return np.array(vectors)


@pytest.fixture(scope="session", autouse=True)
def _mock_sentence_transformer():
    """Session 级别 mock：避免离线环境下载 all-MiniLM-L6-v2 模型

    盘古系统在多个模块中懒加载 VectorEmbedder → SentenceTransformer。
    在无网络环境下，SentenceTransformer("all-MiniLM-L6-v2") 会因下载超时而挂起。
    此 mock 使用基于文本 hash 的确定性假向量，保证功能逻辑测试正确。
    """

    class _MockST:
        def __init__(self, model_name="mock", device=None, cache_folder=None):
            pass

        def encode(self, text, convert_to_numpy=True, **kwargs):
            return _make_deterministic_vector(text)

    try:
        import sentence_transformers
    except ImportError:
        import types

        sentence_transformers = types.ModuleType("sentence_transformers")

    sentence_transformers.SentenceTransformer = _MockST

    # 同时 patch search.embedder 中的延迟 import 路径
    import sys

    sys.modules.setdefault("sentence_transformers", sentence_transformers)
