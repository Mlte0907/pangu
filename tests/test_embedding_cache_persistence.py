"""盘古 — 嵌入缓存跨进程持久化测试（v0.2.0）

## 为什么需要这个文件

搜索链最贵的一步是嵌入本身。实测（ONNX all-MiniLM-L6-v2，唯一文本）：

| 条数 | 冷（需真算） | 热（缓存命中） |
| --- | --- | --- |
| 39 | 500.7 ms | 0.1 ms |
| 200 | 2395.4 ms | 0.4 ms |
| 1000 | 13777.7 ms | 1.8 ms |

约 12–14 ms/条。盘古的抽屉内容基本不变（只在写入时新增），所以
"记住已经算过的向量"是最划算的优化。

原实现有两个问题：

1. **缓存键用内置 `hash()`**（`embedder.py` 三处 `f"emb_{hash(text)}"`）。
   CPython 对 str 的 `hash()` **每进程加盐**，实测同一字符串：

       PYTHONHASHSEED=0 → -1037664797623304823
       PYTHONHASHSEED=1 → -6474410125932865851
       PYTHONHASHSEED=2 → 202728309569431982

   进程内自洽，所以缓存"看起来能用"；但键不可跨进程复现。
2. **`EmbeddingCache` 纯进程内**（`OrderedDict`，不落盘）。

两者叠加 ⇒ **每次服务重启缓存 100% 失效**，下一次搜索付全额冷成本。

本文件锁定：缓存必须跨进程存活，且**不得**复用失效的向量。

## 测试策略

跨进程是核心断言，所以不能只在同进程内测"存了能读"——那样用 `hash()`
也会通过。真正的检验是**新开一个 Python 进程**读同一份缓存文件，
见 `TestCrossProcessSurvivesRestart`。
"""

import json
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from pangu.core.config import PanguConfig
from pangu.search.embedder import EmbeddingCache, VectorEmbedder, _cache_key


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """把缓存指到临时目录，绝不碰用户真实缓存"""
    monkeypatch.setenv("PANGU_CACHE_DIR", str(tmp_path))
    return tmp_path


class TestCacheKeyIsStable:
    """缓存键必须内容寻址，不能依赖进程内状态"""

    def test_same_text_same_key(self):
        assert _cache_key("记忆") == _cache_key("记忆")

    def test_different_text_different_key(self):
        assert _cache_key("记忆") != _cache_key("记忆 ")

    def test_key_stable_across_processes(self):
        """**核心回归**：键必须跨进程一致

        用 `hash()` 时这条必然失败——它每进程加盐。
        这里真的开两个子进程各自打印键，而不是同进程内比较。
        """
        code = textwrap.dedent(
            """
            from pangu.search.embedder import _cache_key
            print(_cache_key("跨进程稳定性检验"))
            """
        )
        outs = []
        for _ in range(2):
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert r.returncode == 0, r.stderr
            outs.append(r.stdout.strip())
        assert outs[0] == outs[1], f"缓存键跨进程不一致: {outs}"

    def test_builtin_hash_would_not_be_stable(self):
        """记录事实：内置 hash() 不满足要求，防止有人"顺手简化"回去

        这条测试本身不依赖实现，只证明 `hash()` 确实每进程加盐。
        若某天它变成稳定的（CPython 未加盐），说明前提变了，应重审设计。
        """
        code = "print(hash('跨进程稳定性检验'))"
        outs = []
        for _ in range(2):
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=120,
            )
            outs.append(r.stdout.strip())
        assert outs[0] != outs[1], "内置 hash() 跨进程居然一致了——若 CPython 改了行为，需重新评估为何不直接用 hash()"


class TestDiskRoundTrip:
    """写入 → 读回"""

    def test_save_and_reload(self, tmp_path):
        f = tmp_path / "c.json"
        c1 = EmbeddingCache(cache_file=f, fingerprint="fp1")
        c1.set("k1", np.array([1.0, 2.0], dtype=np.float32))
        assert c1.save(force=True) is True

        c2 = EmbeddingCache(cache_file=f, fingerprint="fp1")
        got = c2.get("k1")
        assert got is not None
        np.testing.assert_allclose(got, [1.0, 2.0])

    def test_no_cache_file_means_pure_memory(self):
        """未指定文件时应退化为原行为，不写盘"""
        c = EmbeddingCache(cache_file=None, fingerprint="x")
        c.set("k", np.array([1.0], dtype=np.float32))
        assert c.save(force=True) is False


class TestInvalidationIsSafe:
    """失效的向量**绝不能**被复用——这是正确性问题，不是性能问题"""

    def test_fingerprint_mismatch_discards(self, tmp_path):
        """换模型/维度后旧缓存必须整体作废

        向量只有在模型、维度、量化方式一致时才可混用。若不校验，
        旧向量会被当成有效结果直接返回，静默给出错误相似度且不报错。

        ⚠ 这里必须用**同一个**对象写盘：写法和读法分属两个实例时，
        很容易写成"空对象存盘 → 读回 0 条"，那样断言恒真、
        把指纹校验删掉也照样通过（我第一版就是这么写错的）。
        所以额外断言"同一指纹读回时**确实拿到 1 条**"，
        以证明文件里真的有数据可作废。
        """
        f = tmp_path / "c.json"
        c = EmbeddingCache(cache_file=f, fingerprint="fpA")
        c.set("k", np.array([1.0], dtype=np.float32))
        assert c.save(force=True) is True

        # 前置条件：同指纹必须读得到，证明文件里真有数据
        same = EmbeddingCache(cache_file=f, fingerprint="fpA")
        assert len(same) == 1, "前置条件不成立：文件里没有数据，本测试会变成空断言"

        other = EmbeddingCache(cache_file=f, fingerprint="fpB")
        assert len(other) == 0, "指纹不符时旧缓存必须作废"

    def test_format_version_mismatch_discards(self, tmp_path):
        f = tmp_path / "c.json"
        c = EmbeddingCache(cache_file=f, fingerprint="fp")
        c.set("k", np.array([1.0], dtype=np.float32))
        c.save(force=True)

        blob = json.loads(f.read_text())
        blob["version"] = EmbeddingCache.FORMAT_VERSION + 999
        f.write_text(json.dumps(blob))

        assert len(EmbeddingCache(cache_file=f, fingerprint="fp")) == 0

    def test_corrupt_file_does_not_break_startup(self, tmp_path):
        """缓存损坏绝不能阻止服务启动——它只是缓存"""
        f = tmp_path / "c.json"
        f.write_text("{ 这不是合法 JSON")
        c = EmbeddingCache(cache_file=f, fingerprint="fp")  # 不应抛异常
        assert len(c) == 0

    def test_fingerprint_covers_model_and_dim(self):
        """指纹必须对模型与维度敏感"""
        a = VectorEmbedder(PanguConfig())
        cfg = PanguConfig()
        cfg.embedding_dim = 768
        b = VectorEmbedder(cfg)
        cfg2 = PanguConfig()
        cfg2.embedding_model = "another-model"
        c = VectorEmbedder(cfg2)

        fps = {a._cache_fingerprint(), b._cache_fingerprint(), c._cache_fingerprint()}
        assert len(fps) == 3, "不同模型/维度必须产出不同指纹"


class TestCrossProcessSurvivesRestart:
    """**本文件的核心**：模拟服务重启后缓存仍生效

    只断言"同进程存了能读"是不够的——那种测试用 `hash()` 也会通过。
    真正的检验是开一个**全新进程**，看它能否命中上一个进程写下的向量。
    """

    def test_restart_hits_cache(self, cache_dir):
        # 子进程 A：嵌入并落盘
        write_code = textwrap.dedent(
            """
            from pangu.core.config import PanguConfig
            from pangu.search.embedder import VectorEmbedder
            emb = VectorEmbedder(PanguConfig.load())
            for t in ["重启前文本一", "重启前文本二", "重启前文本三"]:
                emb.embed(t)
            print("saved", emb.flush_cache(), len(emb._cache))
            """
        )
        ra = subprocess.run([sys.executable, "-c", write_code], capture_output=True, text=True, timeout=600)
        assert ra.returncode == 0, ra.stderr
        assert "saved True 3" in ra.stdout, ra.stdout

        # 子进程 B（模拟重启）：应全部命中，且一次真算都不发生
        read_code = textwrap.dedent(
            """
            from pangu.core.config import PanguConfig
            from pangu.search.embedder import VectorEmbedder
            emb = VectorEmbedder(PanguConfig.load())
            loaded = len(emb._cache)
            for t in ["重启前文本一", "重启前文本二", "重启前文本三"]:
                emb.embed(t)
            s = emb.cache_stats()
            print("loaded", loaded, "hits", s["hits"], "misses", s["misses"])
            """
        )
        rb = subprocess.run([sys.executable, "-c", read_code], capture_output=True, text=True, timeout=600)
        assert rb.returncode == 0, rb.stderr
        assert "loaded 3" in rb.stdout, f"重启后未加载到缓存: {rb.stdout}"
        assert "hits 3 misses 0" in rb.stdout, f"重启后仍有未命中: {rb.stdout}"


class TestWriteAmplificationIsBounded:
    """写盘要节流：不能每嵌入一条就序列化整个缓存"""

    def test_not_every_set_triggers_write(self, tmp_path):
        f = tmp_path / "c.json"
        c = EmbeddingCache(cache_file=f, fingerprint="fp")
        for i in range(50):
            c.set(f"k{i}", np.array([float(i)], dtype=np.float32))
            c.save()
        assert not f.exists(), "50 条就写盘了——写放大没有节流"

    def test_force_always_writes(self, tmp_path):
        f = tmp_path / "c.json"
        c = EmbeddingCache(cache_file=f, fingerprint="fp")
        c.set("k", np.array([1.0], dtype=np.float32))
        assert c.save(force=True) is True
        assert f.exists()

    def test_lru_eviction_respects_max_size(self):
        c = EmbeddingCache(max_size=3, cache_file=None, fingerprint="fp")
        for i in range(5):
            c.set(f"k{i}", np.array([float(i)], dtype=np.float32))
        assert len(c) == 3
        assert c.get("k0") is None, "最旧的应被淘汰"
        assert c.get("k4") is not None


class TestVecEmbedderIntegration:
    """集成：VectorEmbedder.embed/embed_batch 走的是同一份缓存"""

    def test_embed_batch_populates_and_reuses(self, cache_dir):
        emb = VectorEmbedder(PanguConfig())
        texts = ["集成测试甲", "集成测试乙"]
        first = emb.embed_batch(texts)
        assert first.shape[0] == 2

        before = emb.cache_stats()["hits"]
        second = emb.embed_batch(texts)
        after = emb.cache_stats()["hits"]
        assert after - before == 2, "第二次批量嵌入没有命中缓存"
        np.testing.assert_allclose(first, second)

    def test_env_var_disables_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PANGU_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("PANGU_EMBEDDING_CACHE", "0")
        emb = VectorEmbedder(PanguConfig())
        assert emb._cache._cache_file is None
        emb.embed("禁用持久化")
        emb.flush_cache()
        assert not (tmp_path / "embedding_cache.json").exists()
