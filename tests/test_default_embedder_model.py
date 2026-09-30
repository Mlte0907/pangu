"""默认嵌入模型**必须来自 config**，不能硬编码（2026-09-30 回归测试）。

这个洞的真实代价（云端实测）
--------------------------
`get_onnx_embedder()` / `ONNXEmbedder()` 的 `model_id` 默认值曾长期硬编码旧的
**纯英文** `Xenova/all-MiniLM-L6-v2`，而 `config.onnx_model_id` 早在 2026-09-19 就
换成了多语模型。于是：

* 全仓 16 处 `get_onnx_embedder()` **无参**调用（ingestion / retrieval /
  handlers/embed / hybrid_search / cluster / layers / cli…）拿到的都是英文模型；
* `get_onnx_embedder` 按参数元组缓存 ⇒ **两个 ONNX session 同时常驻**
  （云端日志两条 `ONNX model loaded`：22433KB + 115535KB）；
* `ingestion._embed_and_store` 写进 `drawer.metadata["embedding"]` 的 418 条向量
  **全是英文模型算的**，与搜索侧的多语模型不在同一空间。

中文判别力实测（本地跑两模型对比）：英文 +0.1209 vs 多语 +0.3789 —— 差 3.1 倍。

⚠ 这些断言**只查"默认怎么解析"，不加载模型** —— 加载要 113MB 权重且依赖网络，
放进单元测试会让离线环境挂起（conftest 已 mock sentence-transformers 同理）。
"""

from __future__ import annotations

import inspect

import pytest

ENGLISH_MODEL = "Xenova/all-MiniLM-L6-v2"
MULTILINGUAL_MODEL = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"


class TestOnnxDefaultModelResolution:
    def test_no_signature_hardcodes_the_old_english_model(self):
        """两个入口的默认值都不能再是硬编码的英文模型。

        这是本 bug 的**根**：默认值一旦硬编码，config 换模型它就静默跟不上。
        """
        from pangu.memory.onnx_embedder import ONNXEmbedder, get_onnx_embedder

        for func in (get_onnx_embedder, ONNXEmbedder.__init__):
            default = inspect.signature(func).parameters["model_id"].default
            assert default is None, (
                f"{func.__qualname__} 的 model_id 默认值应是 None（运行时从 config 解析），"
                f"实际是 {default!r}"
            )
            assert default != ENGLISH_MODEL

    def test_default_resolves_to_config(self, monkeypatch):
        """无参调用解析出的模型 == config.onnx_model_id。"""
        from pangu.core import config as config_mod
        from pangu.memory import onnx_embedder

        monkeypatch.setattr(config_mod.config, "onnx_model_id", MULTILINGUAL_MODEL, raising=False)
        assert onnx_embedder._default_model_id() == MULTILINGUAL_MODEL

        # 换成别的值也跟着变（证明是真读 config，不是又一层硬编码）
        monkeypatch.setattr(config_mod.config, "onnx_model_id", "some/other-model", raising=False)
        assert onnx_embedder._default_model_id() == "some/other-model"

    def test_default_falls_back_when_config_has_no_value(self, monkeypatch):
        """config 缺这个字段时退回多语模型，**不是**退回英文模型。"""
        from pangu.core import config as config_mod
        from pangu.memory import onnx_embedder

        monkeypatch.setattr(config_mod.config, "onnx_model_id", None, raising=False)
        assert onnx_embedder._default_model_id() == MULTILINGUAL_MODEL

    def test_no_arg_and_explicit_multilingual_share_one_instance(self):
        """无参调用与显式传多语模型**必须是同一个实例**。

        `get_onnx_embedder` 按参数元组缓存 ⇒ 若默认值在**算 key 之后**才解析，
        `get_onnx_embedder()` 的 key 会是 (None, ...)，与 (多语, ...) 不同 ⇒
        又多出一个 session。这正是原来"两个模型同时常驻"的机制。
        """
        from pangu.memory import onnx_embedder

        a = onnx_embedder.get_onnx_embedder()
        b = onnx_embedder.get_onnx_embedder(model_id=MULTILINGUAL_MODEL)
        assert a is b, "无参调用与显式多语模型应命中同一个缓存实例"

    def test_direct_construction_uses_resolved_model(self):
        """直接 new ONNXEmbedder()（warmup.py:45 就会）也必须拿到 config 的模型。

        顺带守住一个 2026-09-30 踩到的坑：只给 self.model_id 赋值而不回写局部变量
        model_id，会让后面拼 cache_dir 时 None.replace(...) 直接 AttributeError。
        """
        from pangu.memory.onnx_embedder import ONNXEmbedder

        inst = ONNXEmbedder()  # 不传任何参数
        assert inst.model_id == MULTILINGUAL_MODEL
        assert "all-MiniLM-L6" not in str(inst.cache_dir)


class TestSentenceTransformerFallbackModel:
    def test_embedding_model_default_is_multilingual(self):
        """ONNX 挂掉时的 fallback 也必须是多语模型。

        `embedding_model` 只在 sentence-transformers 分支用（search/embedder.py）。
        它曾一直是英文模型 —— ONNX 一挂，中文语义搜索立刻回到"从未工作过"的状态，
        而且**没有任何症状**，只是结果变差。
        """
        from pangu.core.config import PanguConfig

        cfg = PanguConfig()
        assert "all-MiniLM-L6" not in cfg.embedding_model, (
            f"fallback 模型仍是纯英文：{cfg.embedding_model}"
        )
        assert "multilingual" in cfg.embedding_model

    def test_two_backends_speak_the_same_language(self):
        """ONNX 后端与 fallback 后端必须是同一个多语模型家族（否则向量不可比）。"""
        from pangu.core.config import PanguConfig

        cfg = PanguConfig()
        assert "paraphrase-multilingual" in cfg.onnx_model_id
        assert "paraphrase-multilingual" in cfg.embedding_model


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))