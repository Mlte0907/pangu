"""pytest session-level fixtures

解决离线环境下 sentence-transformers 模型下载超时问题：
使用 mock SentenceTransformer 避免网络请求，session 级别确保所有测试受益。
"""

import hashlib

import numpy as np
import pytest

_VEC_DIM = 384  # all-MiniLM-L6-v2 向量维度


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
