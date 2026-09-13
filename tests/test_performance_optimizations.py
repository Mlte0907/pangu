"""测试性能优化效果"""

import time

import numpy as np
import pytest

from pangu.core.palace import Drawer
from pangu.memory.hybrid_search import hybrid_search
from pangu.memory.utils import cosine_similarity, cosine_similarity_batch


def _clear_search_cache():
    """清空 hybrid_search 的进程级结果缓存。

    为什么需要：hybrid_search 开头会查 search_cache（key = query|limit），
    命中就直接返回、不走搜索实现。该缓存是**进程级全局**，tests/conftest.py
    没有重置它，于是同一次 pytest 进程内，先跑的用例会把结果写进缓存，
    后跑的用例若用相同 query 就只测到一次缓存命中（实测 0.009ms vs 真实 20ms），
    性能断言随之失效。

    这里显式清空，让每个性能用例都从"真实搜索"开始计量。
    """
    from pangu.memory.search_cache import get_search_cache

    get_search_cache().clear()


def _warmup_embedder():
    """预热 ONNX embedder 单例，返回是否可用。

    为什么需要：hybrid_search 对 query 的向量化是**惰性**的
    （pangu/memory/hybrid_search.py:110 `_get_query_embedding` →
    pangu/memory/onnx_embedder.py `get_onnx_embedder()` 单例）。
    首次调用要付模型初始化成本，且该成本会落进被测的那一次墙钟里。
    实测同一段测量代码：
      - 未预热（本文件单独跑）：100 轮 min ≈ 52~54ms
      - 已预热（整文件/整套跑）：100 轮 min ≈ 8~10ms
    差值 5 倍以上，正是「整套里过、单独跑却挂」的根因。
    预热把二者拉平到同一稳态，从而无需为了让冷启动通过而放宽阈值。

    embedder 不可用时（如缺少 ONNX 运行时）静默返回 False——此时
    hybrid_search 会走降级路径，性能断言仍按原语义执行。
    """
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder

        get_onnx_embedder().embed("warmup")
        return True
    except Exception:
        return False


class TestCosineSimilarityOptimization:
    """测试余弦相似度优化"""

    def test_cosine_similarity_correctness(self):
        """测试余弦相似度正确性"""
        # 相同向量
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0)

        # 正交向量
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

        # 相反向量
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

        # 空向量
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([1.0], []) == 0.0
        assert cosine_similarity([], [1.0]) == 0.0

    def test_cosine_similarity_performance(self):
        """测试余弦相似度性能"""
        a = np.random.randn(384).tolist()
        b = np.random.randn(384).tolist()

        # 预热一次，避免把首次调用的惰性初始化计入耗时
        cosine_similarity(a, b)

        # 取多轮中的**最快一轮**，而不是均值或中位数。
        #
        # 【为什么取最小值】单轮 1000 次调用仅约 43ms，一次调度抢占就能主导
        # 整轮耗时。最小值剔除的是**外部干扰**（被抢占的轮次），保留的是真实
        # 计算成本（本机实测 best/p25/med/max 稳定在 0.0432~0.0435ms）。
        #
        # 【为什么是 20 轮】轮数越多，越有机会抓到一轮不被抢占的样本。
        #
        # 【实测依据（v0.2.x 审查，压测复现）】
        #   - load 14（1.75x 超订），**均值/中位数口径**：本用例实测 0.1636ms
        #     → 假失败（阈值 0.1）；批量用例 5.1991ms → 假失败（阈值 2）。
        #     连续 6 次运行全部 2 failed，是稳定复现、不是偶发。
        #   - load 6.6：改为 20 轮取最小值后稳定 0.0431~0.0435ms，**通过**。
        #   - load 21（24 忙循环 / 8 核 = 3x 超订）：取最小值**仍会失败**
        #     （实测 0.2583ms）。
        #
        # 【已知且接受的权衡】绝对墙钟阈值在 3x CPU 超订下必然假失败——
        # 「阈值不放宽」与「任意负载下不 flake」在数学上不可兼得。
        # 本方案的取舍：保住阈值（维持 2.3x 灵敏度，不慢性放弃保护），
        # 接受 3x 超订时失败——那种情况下测试机已被压垮，失败是合理信号。
        # 真实事故场景（19529 那次：1 次偶发、约 0.5 倍负载）本方案有效。
        #
        # 阈值保持 0.1ms 不放宽——实测 med≈max≈0.0432ms，说明这是稳定的
        # 计算量而非噪声；放宽阈值等于放弃对优化目标的保护。
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            for _ in range(1000):
                cosine_similarity(a, b)
            samples.append((time.perf_counter() - start) * 1000 / 1000)
        avg_time = min(samples)

        # 应该小于 0.1ms
        assert avg_time < 0.1, f"单次计算太慢: {avg_time:.4f}ms"

    def test_cosine_similarity_batch_performance(self):
        """测试批量余弦相似度性能"""
        query = np.random.randn(384).tolist()
        vectors = [np.random.randn(384).tolist() for _ in range(100)]

        # 预热，排除首次调用的冷启动
        cosine_similarity_batch(query, vectors, threshold=0.2)

        # 多轮取最快一轮，理由与实测数据见 test_cosine_similarity_performance
        # 的注释（load 14 下均值口径实测 5.1991ms 假失败；取最小值后通过）。
        # 阈值保持 2ms 不放宽（实测 med≈max≈0.96ms，是稳定计算量）。
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            for _ in range(100):
                results = cosine_similarity_batch(query, vectors, threshold=0.2)
            samples.append((time.perf_counter() - start) * 1000 / 100)
        avg_time = min(samples)

        # 应该小于 2ms
        assert avg_time < 2, f"批量计算太慢: {avg_time:.4f}ms"

    def test_cosine_similarity_batch_correctness(self):
        """测试批量余弦相似度正确性"""
        query = [1.0, 0.0, 0.0]
        vectors = [
            [1.0, 0.0, 0.0],  # 完全相同
            [0.0, 1.0, 0.0],  # 正交
            [-1.0, 0.0, 0.0],  # 相反
            [0.5, 0.5, 0.0],  # 45度
        ]

        results = cosine_similarity_batch(query, vectors, threshold=0.1)

        # 应该找到索引0和3
        assert len(results) == 2
        assert results[0] == (0, 1.0)
        assert results[1][0] == 3
        assert results[1][1] == pytest.approx(0.707, abs=0.01)


class TestHybridSearchOptimization:
    """测试混合搜索优化"""

    def test_hybrid_search_with_embeddings(self):
        """测试带嵌入的混合搜索"""
        # 创建更现实的测试数据
        base_embedding = np.random.randn(384).tolist()
        drawers = []
        for i in range(50):
            # 创建与基础嵌入相似的向量
            noise = np.random.randn(384) * 0.1
            embedding = (np.array(base_embedding) + noise).tolist()

            drawer = Drawer(
                id=f"test_{i}",
                content=f"Test memory {i} about Python programming",
                wing="test",
                room="general",
                importance=float(i % 5),
                tags=["test"],
                created_at="2024-01-01T00:00:00",
                metadata={"embedding": embedding},
            )
            drawers.append(drawer)

        # 预热：hybrid_search 首次调用会触发惰性初始化（模型/缓存/索引构建），
        # 实测首次 168ms、后续命中缓存约 0.003ms，与负载无关。
        # 不预热则首次 168ms 对 50ms 的阈值会直接失败。
        #
        # ⚠ 预热用的 query 必须与后面计量的 query **不同**：
        # hybrid_search 有结果缓存（pangu/memory/search_cache.py:28，
        # key = (query, limit)），同 query 重复调用会命中缓存直接返回，
        # 根本走不到搜索实现。实测（缓存命中 vs 未命中）：
        #   同 query 重复: 20.3ms → 0.011 → 0.006 → 0.003ms（命中缓存）
        #   不同 query  : 168ms → 19.8 → 19.1 → 19.1ms（真实搜索）
        # 早期版本用同一 query 计量，测的其实是"缓存命中耗时"，
        # 因此注入了 2ms 延迟仍能通过——是失效断言。
        #
        # ⚠ 缓存是**进程级全局**且 conftest 未重置，因此跨测试会互相污染：
        # 若两个测试用相同字面 query，先跑的会把结果写进缓存，后跑的
        # 直接命中缓存、测到 ~0.009ms（实测），断言形同虚设。
        # 故这里先清缓存，且 query 带上本测试专属前缀。
        #
        # ⚠ **必须显式预热 embedder 单例**：hybrid_search 的 query 嵌入是
        # 惰性加载的（pangu/memory/hybrid_search.py:110 `_get_query_embedding`
        # → onnx_embedder 单例）。首次调用要付模型加载成本，导致实测：
        #   - 未预热（本文件单独跑）：100 轮 min ≈ **52~54ms**（稳定复现）
        #   - 已预热（整文件/整套跑）：100 轮 min ≈ **8~10ms**
        # 二者差 5 倍以上——这正是原断言「在整套里过、单独跑却挂」的根因。
        # 预热是消除该差异的正确手段（而不是放宽阈值）。
        _warmup_embedder()
        _clear_search_cache()
        hybrid_search("warmup_with_embeddings", drawers, limit=10)
        _clear_search_cache()

        # 取 100 轮中的**最小值**，与 L51/L65 的手法一致（why min 见下）。
        #
        # 【为什么不取平均】原实现是 10 次取平均（(end-start)*1000/10）。
        # 平均值会把被调度抢占 / CPU 降频的轮次算进去——那反映的是
        # "这台机器当时有多忙"，不是"实现有多快"。最小值剔除外扰。
        #
        # 【为什么是 100 轮而不是 20 轮】（实测，v0.2.x 返工）
        # 本机 governor=schedutil，频率在 300MHz~1.8GHz 间摆动。
        #   - 20 轮取 min：跨进程波动很大，实测 min 落在 **49.58~49.74ms**
        #     （碰巧整个进程跑在低频窗口内）。
        #   - 100 轮取 min：稳定收敛到 **19.81~20.94ms**（3 个独立进程），
        #     因为轮数够多，必然命中高频窗口。同进程内 20 轮 min 也可稳定
        #     到 ~19.8ms，证明波动来源是**进程间**频率状态而非轮间噪声。
        # ⇒ 真正的修法不是放宽阈值，而是**取足够多轮的最小值**，让观测量
        #   收敛到"这台机器满频时能跑多快"这一与负载无关的量。
        #
        # 【原 flake 证据】原「10 次取平均」整文件连跑 11 次 → **6 次失败
        # （约 55%）**，原始失败信息：AssertionError: 混合搜索太慢: 50.01ms
        # （captain 独立复现 50.20ms，整文件 5/12 失败）。
        #
        # 【阈值 125ms（HEAD 原值 50ms → 上调）】
        #
        # 真实成本（本用例条件、100 轮、空闲机器）：
        #   min=49.81ms / 中位=52.01ms，**min/中位 ≈ 0.958**
        #   （captain 独立复测 50.18 / 52.20 / 52.36ms，min/中位 0.957~0.992）
        # ⇒ 本用例单次真实成本 **50~52ms**，HEAD 的 50ms 阈值**连最小值都超**，
        #   实际裕度仅 ≈ **1.005x**，必然假失败。它与 L324 是**同一个物理成本**
        #   （一次 query 向量嵌入，与 drawer 是否带 embedding 无关），
        #   两处却给了 50ms / 100ms 两个互相矛盾的阈值——这才是根因。
        #
        # 取 125ms：对 50~52ms 成本给约 **2.4~2.5x** 余量，与 L324 的 100ms
        # 口径一致（同源成本、同量级余量）。
        # ⚠ 不放宽到 150ms：实测那会让「注入 60ms 延迟」的回归漏网
        #   （60+50=110ms < 150ms 仍通过 = 断言失效），故封顶 125ms。
        #
        # ⚠ min/中位 ≈ 0.96 ⇒ **最小值≈典型成本，min-of-100 只能剔噪，
        #   剔不掉真实成本本身**。采样手法再正确，也救不了一个低于真实成本的阈值。
        #
        # ⚠ 关于曾写入的 9.42ms：上一版注释称"整文件 100 轮 min 实测 9.42ms、
        #   对 50ms 约 5.3x 余量"。该数字**无法复现且具误导性**——
        #   onnx_embedder 有**进程级嵌入缓存**（pangu/memory/onnx_embedder.py:91
        #   `self._cache`），实测冷嵌入 137.85ms vs 命中 0.0134ms（差约 1e4 倍）。
        #   本文件靠前的用例先嵌入过同一批文本，缓存被填热后一次"搜索"里
        #   `_get_query_embedding` 只要 0.01ms（实测），整轮于是显示 6~9ms。
        #   那是**缓存命中的假快**，不是真实成本。该数字已删除。
        #   教训：性能数字必须来自实测，不能由"阈值 ÷ 余量"反推。
        samples = []
        for i in range(100):
            start = time.perf_counter()
            results = hybrid_search(f"emb perf probe {i}", drawers, limit=10)
            samples.append((time.perf_counter() - start) * 1000)
        avg_time = min(samples)

        # 护栏：防止日后有人把每轮 query 改回同一个字面量。
        # 那样第 1 轮写入 search_cache，其余轮全命中，min 会塌缩到
        # ~0.003ms 的缓存命中值，断言静默失效（本会话已踩过该坑）。
        # 真实搜索 + 嵌入路径不可能低于 0.5ms。
        assert min(samples) > 0.5, (
            f"探测值 {min(samples):.4f}ms 过低，疑似命中缓存导致 min 塌缩"
            f"（检查每轮 query 是否互不相同、search_cache 是否已清）"
        )

        # 应该小于 125ms
        assert avg_time < 125, f"混合搜索太慢: {avg_time:.2f}ms"
        # 搜索可能返回空结果（如果所有相似度都低于阈值），但这不是性能问题
        # 我们主要测试性能，不是搜索质量

    def test_hybrid_search_without_embeddings(self):
        """测试无嵌入的混合搜索"""
        drawers = []
        for i in range(50):
            drawer = Drawer(
                id=f"test_{i}",
                content=f"Test memory {i} about Python programming",
                wing="test",
                room="general",
                importance=float(i % 5),
                tags=["test"],
                created_at="2024-01-01T00:00:00",
                metadata={},
            )
            drawers.append(drawer)

        # 预热，排除首次调用的冷启动（实测首次 158.9ms，远高于这里的阈值）。
        # 同 test_hybrid_search_with_embeddings 的说明：缓存是进程级全局且
        # conftest 未重置，必须清缓存 + 用本测试专属 query，否则会命中
        # 上一个测试留下的缓存（实测可把真实 ~50ms 变成 ~0.009ms）。
        #
        # 同样必须**显式预热 embedder 单例**（见 `_warmup_embedder` 文档）：
        # 本用例虽不带 embedding 数据，但 hybrid_search 仍要向量化 **query**，
        # 未预热时该模型加载成本会计入被测墙钟（实测 52→27ms 差异）。
        _warmup_embedder()
        _clear_search_cache()
        hybrid_search("warmup_no_embeddings", drawers, limit=10)
        _clear_search_cache()

        # 取 100 轮中的最小值，理由与实测数据见
        # test_hybrid_search_with_embeddings（原 10 次取平均整文件 11 跑 6 败）。
        samples = []
        for i in range(100):
            start = time.perf_counter()
            results = hybrid_search(f"noemb perf probe {i}", drawers, limit=10)
            samples.append((time.perf_counter() - start) * 1000)
        avg_time = min(samples)

        # 阈值 100ms（HEAD 原值 20ms → 上调，依据见下）。
        #
        # 【根因：本用例的成本 = 一次 ONNX query 嵌入，约 46ms】
        # hybrid_search 无论 drawer 是否带 embedding，都要先向量化 **query**
        # （pangu/memory/hybrid_search.py:83 `_get_query_embedding(query)`）。
        # 单独计时该调用（预热后 50 次）实测 min=**43.07ms**、中位 55.12ms，
        # 即本用例的墙钟几乎全由这一次嵌入决定，与 drawer 数量无关。
        #
        # 【本用例真实成本（100 轮 min，预热后，3 次独立进程）】
        #   min=46.54 / 46.51 / 46.45ms，p10≈46.6ms，中位≈46.7ms
        #   —— 极稳定（min 与中位相差 <3%），是真实计算成本，不是噪声。
        # HEAD 的 20ms 阈值低于该成本 2.3 倍，**在任何情况下都不可能通过**。
        #
        # 【为什么取 100ms】相对实测 min(46.5ms) 留约 **2.1x 余量**：
        # 足以吸收调度抖动，又能在「查询嵌入本身退化」或「多了一次
        # 多余嵌入/搜索」这类真实回归上失败（见缺陷注入验证）。
        # 未取更大值（如 3x=150ms）是因为那会让 +60ms 级别的注入漏网。
        #
        # ⚠ 修正记录 1：本用例曾把阈值收紧到 0.5ms，依据是"稳态 0.0018ms"。
        # 那个 0.0018ms 是**缓存命中**耗时，不是真实搜索。缺陷注入在整文件
        # 运行时**未失败**，由此暴露被观测量是缓存命中；改用专属 query +
        # 清缓存后才量到真实成本。
        #
        # ⚠ 修正记录 2：曾记录"真实无嵌入搜索 16.68~16.95ms"与"整文件下
        # 4.65ms"两个数字，均**无法复现**：前者来自另一组简化 drawer 数据，
        # 后者的测量代码未预热 embedder 且受前序用例的缓存/单例状态影响。
        # 以本用例真实条件（预热 + 专属 query + 100 轮 min）复测为准 → 46.5ms。
        assert avg_time < 100, f"混合搜索太慢: {avg_time:.4f}ms"
        # 搜索可能返回空结果（如果没有匹配），但这不是性能问题


class TestVectorIndexIntegration:
    """测试向量索引集成"""

    def test_vector_index_search(self):
        """测试向量索引搜索"""
        from pangu.memory.vector_index import get_vector_index

        vi = get_vector_index()

        # 添加测试向量：5 轮 × 100 条 → size 500（阈值 <100ms 保持不变）。
        #
        # 【实测依据】本机 governor=schedutil，频率 300MHz~1.8GHz 摆动，会让
        # add_batch 的墙钟在 8ms~133ms 间剧烈波动（3 进程各 20 轮实测：
        # min 8.02~8.17ms；**中位 72.5~74.4ms；最大 131~133ms**）。
        # 即中位数已接近 100ms 阈值且最大值直接超阈——单次计量必假失败。
        # 取多轮最小值可稳定收敛到满频窗口的 ~8ms，对 100ms 阈值约 12x 余量。
        #
        # ⚠ 为什么保持 5 轮、不提升到 100 轮（captain 建议 4 曾考虑）：
        #   本用例末尾还有 `search_time < 1` 这条**红线断言**，其成本与索引
        #   size 直接相关。把 add_batch 提到 100 轮会让 size 从 500 涨到 10000，
        #   实测（新单例、恰好 10000 条）vi.search min=**4.5210ms**、p50=8.0036ms，
        #   对 1ms 阈值裕度 **0.22x** ⇒ search 断言必然失败（实测已复现
        #   `2 failed`：本用例 + cosine）。为一个 medium 级的样本量改进
        #   去打破另一条红线断言，不划算，故**保持 5 轮**。
        #   （captain 该项本就标注"若改动成本低就做，否则记入待办"——成本不低。）
        #
        # 注：add_batch 是**追加**语义（同 id 重复添加会累加 size），
        # 故每轮用不同 id 前缀，末尾 size 断言相应为 500。
        add_samples = []
        for round_no in range(5):
            vectors = [np.random.randn(384).tolist() for _ in range(100)]
            ids = [f"vec_{round_no}_{j}" for j in range(100)]
            start = time.perf_counter()
            vi.add_batch(vectors, ids)
            add_samples.append((time.perf_counter() - start) * 1000)
        add_time = min(add_samples)

        # 测试搜索性能
        # 取 100 轮中的最小值（阈值 <1ms 保持不变），与 L51/L65/L191 手法一致。
        #
        # 【实测依据】reviewer 在负载下实测原「单次计量」对 1ms 阈值裕度仅
        # 1.55~1.61x。改为 min-of-100 后，本用例数据规模（500 条向量）下
        # vi.search 真实成本 min 稳定在 **0.1895~0.1941ms**（3 个独立进程，
        # 中位 0.206~0.220ms），对 1ms 阈值约 **5x** 余量。
        # 轮间存在真实波动（max 可达 0.87ms），说明量的是真实执行而非假快。
        # 每次用**不同的随机 query**，避免任何潜在的结果缓存影响。
        #
        # 注：`get_vector_index()` 是进程级单例（conftest 有
        # _reset_vector_index_singleton autouse fixture）。本轮是**追加**
        # 到同一单例的新索引上，非空索引，故 0.19ms 是真实搜索而非空索引假快。
        samples = []
        for _ in range(100):
            query = np.random.randn(384).tolist()
            start = time.perf_counter()
            results = vi.search(query, top_k=10)
            samples.append((time.perf_counter() - start) * 1000)
        search_time = min(samples)

        assert add_time < 100, f"添加向量太慢: {add_time:.2f}ms"
        assert search_time < 1, f"搜索太慢: {search_time:.2f}ms"
        assert len(results) == 10
        # 5 轮 × 100 条 = 500（add_batch 为追加语义，见上方说明）
        assert vi.size == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
