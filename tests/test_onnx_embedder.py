"""盘古 — ONNX 嵌入器测试

覆盖：
1. 基础功能（维度、归一化）
2. 语义相似度
3. 批量推理
4. 缓存命中
5. EmbeddingService 三级降级
6. 性能基线
7. 配置开关
"""

import time

import pytest


# ── 跳过条件：缺少 ONNX 时跳过大部分测试 ──
def _onnx_available():
    try:
        import onnxruntime  # noqa: F401
        from tokenizers import Tokenizer  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark_onnx = pytest.mark.skipif(
    not _onnx_available(),
    reason="onnxruntime/tokenizers 未安装",
)


# ─────────────────────────────────────────────────────
# 1. 基础功能
# ─────────────────────────────────────────────────────
class TestONNXEmbedder:
    """ONNX 嵌入器基础测试"""

    def test_availability(self):
        """检查依赖可用性"""
        from pangu.memory.onnx_embedder import _HAS_ORT, _HAS_TOKENIZERS
        assert _HAS_ORT, "onnxruntime 未安装"
        assert _HAS_TOKENIZERS, "tokenizers 未安装"

    def test_dim_config(self):
        """维度配置"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder(embedding_dim=384)
        assert emb.embedding_dim == 384
        assert emb.max_length == 128

    def test_is_loaded_false_initially(self):
        """初始化时不立即加载"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        assert emb.is_loaded is False
        assert emb._load_attempted is False

    @pytestmark_onnx
    def test_lazy_load(self):
        """懒加载：首次 embed 时才加载模型"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        assert emb.is_loaded is False
        vec = emb.embed("hello world")
        assert vec is not None
        assert emb.is_loaded is True
        assert emb._stats["model_loaded"] is True

    @pytestmark_onnx
    def test_embed_dim_and_norm(self):
        """嵌入向量维度和归一化"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder(embedding_dim=384)
        vec = emb.embed("盘古是记忆系统")
        assert vec is not None
        assert len(vec) == 384
        # L2 归一化
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-3, f"norm={norm}"

    @pytestmark_onnx
    def test_empty_text(self):
        """空文本返回零向量"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder(embedding_dim=384)
        vec = emb.embed("")
        assert vec == [0.0] * 384

    @pytestmark_onnx
    def test_similarity_chinese(self):
        """中文语义相似度"""
        import math

        from pangu.memory.onnx_embedder import ONNXEmbedder

        emb = ONNXEmbedder()

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b, strict=False)) / (
                math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9
            )

        v_weather = emb.embed("今天天气很好，适合出门")
        v_sunny = emb.embed("阳光明媚，微风轻拂")
        v_python = emb.embed("Python 是一门编程语言")

        sim_related = cos(v_weather, v_sunny)
        sim_unrelated = cos(v_weather, v_python)
        assert sim_related > sim_unrelated, (
            f"related={sim_related:.3f} 应高于 unrelated={sim_unrelated:.3f}"
        )
        assert sim_related > 0.5, f"related sim={sim_related:.3f} 过低"

    @pytestmark_onnx
    def test_similarity_english(self):
        """英文语义相似度"""
        import math

        from pangu.memory.onnx_embedder import ONNXEmbedder

        emb = ONNXEmbedder()

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b, strict=False)) / (
                math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9
            )

        v_cat = emb.embed("A cat is sitting on the mat")
        v_dog = emb.embed("A dog is lying on the rug")
        v_computer = emb.embed("How to install Ubuntu Linux")

        sim_animals = cos(v_cat, v_dog)
        sim_mixed = cos(v_cat, v_computer)
        assert sim_animals > sim_mixed, (
            f"animals={sim_animals:.3f} 应高于 mixed={sim_mixed:.3f}"
        )

    @pytestmark_onnx
    def test_cache_hit(self):
        """缓存命中"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()

        # 首次
        emb.embed("test_cache_key")
        hits_before = emb._stats["cache_hits"]
        # 第二次
        emb.embed("test_cache_key")
        hits_after = emb._stats["cache_hits"]
        assert hits_after > hits_before

    @pytestmark_onnx
    def test_batch_embed(self):
        """批量嵌入"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        texts = ["hello", "world", "盘古", "pangu"] * 4
        results = emb.embed_batch(texts)
        assert len(results) == 16
        assert all(r is not None for r in results)
        assert all(len(r) == 384 for r in results)

    @pytestmark_onnx
    def test_batch_with_cache(self):
        """批量嵌入 + 缓存混合"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        emb.embed("cached_text")
        hits_before = emb._stats["cache_hits"]
        results = emb.embed_batch(["cached_text", "new_text"])
        hits_after = emb._stats["cache_hits"]
        assert hits_after > hits_before  # 缓存命中
        assert results[0] is not None
        assert results[1] is not None

    @pytestmark_onnx
    def test_stats(self):
        """统计信息"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        emb.embed("test_a")
        emb.embed("test_b")  # 不同的文本才会触发推理
        stats = emb.get_stats()
        assert "model_loaded" in stats
        assert "infer_count" in stats
        assert "avg_infer_ms" in stats
        assert stats["infer_count"] >= 2
        assert stats["avg_infer_ms"] > 0


# ─────────────────────────────────────────────────────
# 2. EmbeddingService 集成
# ─────────────────────────────────────────────────────
class TestEmbeddingServiceONNXIntegration:
    """EmbeddingService 与 ONNX 集成测试"""

    def test_service_has_onnx(self):
        """服务初始化时挂载 ONNX"""
        from pangu.memory.embedding import EmbeddingService
        svc = EmbeddingService()
        assert svc._onnx is not None
        assert "onnx" in svc.stats

    @pytestmark_onnx
    def test_service_embed_uses_onnx(self):
        """服务 embed 在无 API 时走 ONNX"""
        from pangu.memory.embedding import EmbeddingService
        svc = EmbeddingService()
        vec = svc.embed("盘古测试")
        assert vec is not None
        assert len(vec) == 384
        # ONNX 加载已发生
        assert svc.stats["onnx"]["model_loaded"] is True

    @pytestmark_onnx
    def test_service_batch_embed(self):
        """服务批量嵌入走 ONNX"""
        from pangu.memory.embedding import EmbeddingService
        svc = EmbeddingService()
        results = svc.embed_batch(["a", "b", "c", "d"])
        assert len(results) == 4
        assert all(r is not None for r in results)

    @pytestmark_onnx
    def test_onnx_disabled(self):
        """禁用 ONNX 时回退到 hash"""
        from pangu.core.config import PanguConfig
        from pangu.memory.embedding import EmbeddingService
        cfg = PanguConfig(onnx_enabled=False)
        svc = EmbeddingService(cfg)
        vec = svc.embed("test")
        assert vec is not None
        assert len(vec) == 384
        # ONNX 不应被加载
        assert svc._onnx is None


# ─────────────────────────────────────────────────────
# 3. 性能基线（benchmark）
# ─────────────────────────────────────────────────────
class TestONNXPerformance:
    """性能测试基线（基准指标，非断言）"""

    @pytestmark_onnx
    def test_inference_speed(self, capsys):
        """推理速度（打印，不阻塞）"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        # 预热
        emb.embed("warmup")
        # 测试
        n = 50
        texts = [f"这是测试文本 {i} 用于性能基准" for i in range(n)]
        start = time.time()
        for t in texts:
            emb.embed(t)
        elapsed = (time.time() - start) * 1000
        per_text = elapsed / n
        with capsys.disabled():
            print(f"\n[ONNX Perf] {n} inferences in {elapsed:.0f}ms → {per_text:.1f}ms/text")

    @pytestmark_onnx
    def test_batch_speedup(self, capsys):
        """批处理加速比"""
        from pangu.memory.onnx_embedder import ONNXEmbedder
        emb = ONNXEmbedder()
        emb.embed("warmup")
        texts = [f"批次性能测试 {i}" for i in range(20)]

        # 单条
        start = time.time()
        for t in texts:
            emb.embed(t)
        single_ms = (time.time() - start) * 1000

        # 批量
        emb.embed_batch([f"new_{i}" for i in range(20)])  # 不命中缓存
        start = time.time()
        emb.embed_batch(texts)
        batch_ms = (time.time() - start) * 1000

        with capsys.disabled():
            print(
                f"\n[ONNX Batch] single={single_ms:.0f}ms vs batch={batch_ms:.0f}ms "
                f"speedup={single_ms / max(batch_ms, 1):.1f}x"
            )


# ─────────────────────────────────────────────────────
# 4. 全局单例与配置
# ─────────────────────────────────────────────────────
class TestGlobalSingleton:
    """全局单例与配置切换"""

    def test_get_onnx_embedder_singleton(self):
        """全局单例"""
        from pangu.memory.onnx_embedder import get_onnx_embedder, reset_onnx_embedder
        reset_onnx_embedder()
        e1 = get_onnx_embedder()
        e2 = get_onnx_embedder()
        assert e1 is e2

    def test_reset_clears_singleton(self):
        """reset_onnx_embedder 清除单例"""
        from pangu.memory.onnx_embedder import get_onnx_embedder, reset_onnx_embedder
        e1 = get_onnx_embedder()
        reset_onnx_embedder()
        e2 = get_onnx_embedder()
        assert e1 is not e2

    def test_config_onnx_fields(self):
        """配置字段存在"""
        from pangu.core.config import PanguConfig
        cfg = PanguConfig()
        assert hasattr(cfg, "onnx_enabled")
        assert hasattr(cfg, "onnx_model_id")
        assert hasattr(cfg, "onnx_quantized")
        assert hasattr(cfg, "onnx_max_length")
        assert hasattr(cfg, "onnx_mirror_base")
        assert cfg.onnx_enabled is True
        assert cfg.onnx_model_id == "Xenova/all-MiniLM-L6-v2"
        assert cfg.onnx_mirror_base == "https://hf-mirror.com"

    def test_config_env_override(self, monkeypatch):
        """环境变量覆盖"""
        from pangu.core.config import PanguConfig
        monkeypatch.setenv("PANGU_ONNX_ENABLED", "false")
        monkeypatch.setenv("PANGU_ONNX_MAX_LENGTH", "256")
        cfg = PanguConfig()
        assert cfg.onnx_enabled is False
        assert cfg.onnx_max_length == 256
