"""盘古启动预热 — 消除首次查询冷启动延迟"""
import time
import logging
from pathlib import Path

logger = logging.getLogger("pangu.warmup")


def warmup_jieba():
    """预热 jieba 分词器"""
    t0 = time.perf_counter()
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
        # 预热：强制加载词典
        jieba.cut("盘古记忆系统预热测试")
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"jieba 预热完成: {elapsed:.0f}ms")
        return elapsed
    except ImportError:
        return 0


def warmup_onnx():
    """预热 ONNX 嵌入模型"""
    t0 = time.perf_counter()
    try:
        from pangu.memory.onnx_embedder import ONNXEmbedder
        embedder = ONNXEmbedder()
        embedder.embed("预热")
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"ONNX 预热完成: {elapsed:.0f}ms")
        return elapsed
    except Exception as e:
        logger.warning(f"ONNX 预热失败: {e}")
        return 0


def warmup_fts_index():
    """预热 FTS 索引"""
    t0 = time.perf_counter()
    try:
        from pangu.memory.fts_search import FTS5SearchEngine
        from pangu.memory.layers import MemoryStack
        from pangu.core.config import PanguConfig

        config = PanguConfig.load()
        stack = MemoryStack(config)
        drawers = stack.get_drawers()

        fts = FTS5SearchEngine()
        fts.build_index(drawers)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"FTS 索引预热完成: {elapsed:.0f}ms ({len(drawers)} 条)")
        return elapsed
    except Exception as e:
        logger.warning(f"FTS 预热失败: {e}")
        return 0


def warmup_vector_index():
    """预热向量索引"""
    t0 = time.perf_counter()
    try:
        from pangu.memory.vector_index import get_vector_index
        idx = get_vector_index()
        logger.info(f"向量索引预热完成: {(time.perf_counter() - t0) * 1000:.0f}ms (size={idx.size})")
        return (time.perf_counter() - t0) * 1000
    except Exception as e:
        logger.warning(f"向量索引预热失败: {e}")
        return 0


def warmup_all():
    """预热所有组件"""
    results = {}
    results["jieba"] = warmup_jieba()
    results["onnx"] = warmup_onnx()
    results["fts_index"] = warmup_fts_index()
    results["vector_index"] = warmup_vector_index()
    results["total"] = sum(results.values())
    return results
