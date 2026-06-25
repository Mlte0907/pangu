"""盘古 MCP Handler — embed (6 tools)"""
import json

TOOLS = [
    {"name": "pangu_vector_index_stats", "description": "\u83b7\u53d6\u5411\u91cf\u7d22\u5f15\u7edf\u8ba1"},
    {"name": "pangu_vector_index_build", "description": "\u6784\u5efa\u5411\u91cf\u7d22\u5f15"},
    {"name": "pangu_onnx_embed", "description": "\u4f7f\u7528 ONNX \u672c\u5730\u63a8\u7406\u5d4c\u5165\u5355\u6761\u6587\u672c\uff08CPU \u52a0\u901f 3-10x\uff09"},
    {"name": "pangu_onnx_embed_batch", "description": "ONNX \u6279\u91cf\u5d4c\u5165\u591a\u6761\u6587\u672c"},
    {"name": "pangu_onnx_status", "description": "\u83b7\u53d6 ONNX \u5d4c\u5165\u5668\u72b6\u6001\uff08\u6a21\u578b/\u7f13\u5b58/\u6027\u80fd\uff09"},
    {"name": "pangu_onnx_similarity", "description": "\u4f7f\u7528 ONNX \u8ba1\u7b97\u4e24\u6761\u6587\u672c\u7684\u4f59\u5f26\u76f8\u4f3c\u5ea6"},
]

HANDLERS = {}

async def handle_vector_index_stats(server, drawers, arguments):
    """获取向量索引统计"""
    idx = get_vector_index()
    return json.dumps(idx.stats(), ensure_ascii=False, indent=2)

HANDLERS["pangu_vector_index_stats"] = handle_vector_index_stats

async def handle_vector_index_build(server, drawers, arguments):
    """构建向量索引"""
    from pangu.memory.onnx_embedder import get_onnx_embedder
    embedder = get_onnx_embedder()
    idx = get_vector_index()
    success = idx.build_from_drawers(drawers, embedder=embedder,
                                      min_count=arguments.get("min_count", 1))
    return json.dumps({
        "status": "built" if success else "skipped",
        "stats": idx.stats(),
    }, ensure_ascii=False)

HANDLERS["pangu_vector_index_build"] = handle_vector_index_build

async def handle_onnx_embed(server, drawers, arguments):
    """使用 ONNX 本地推理嵌入单条文本（CPU 加速 3-10x）"""
    from pangu.memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    # 尝试从多个位置获取text参数
    params = request.get("params", {}) if isinstance(request, dict) else {}
    text = arguments.get("text") or params.get("text") or params.get("arguments", {}).get("text") or ""
    if not text:
        # 尝试从工具名提取（最后手段）
        text = tool_name.split("_")[-1] if "_" in tool_name else "test"
    vec = emb.embed(text)
    return json.dumps({
        "text": text,
        "dim": len(vec) if vec else 0,
        "vector": vec,
        "source": "onnx" if emb.is_loaded else "unavailable",
    }, ensure_ascii=False)

HANDLERS["pangu_onnx_embed"] = handle_onnx_embed

async def handle_onnx_embed_batch(server, drawers, arguments):
    """ONNX 批量嵌入多条文本"""
    from pangu.memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    texts = arguments.get("texts", [])
    results = emb.embed_batch(texts)
    return json.dumps({
        "count": len(results),
        "dim": emb.embedding_dim,
        "vectors": results,
        "source": "onnx" if emb.is_loaded else "unavailable",
    }, ensure_ascii=False)

HANDLERS["pangu_onnx_embed_batch"] = handle_onnx_embed_batch

async def handle_onnx_status(server, drawers, arguments):
    """获取 ONNX 嵌入器状态（模型/缓存/性能）"""
    from pangu.memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    return json.dumps(emb.get_stats(), ensure_ascii=False, indent=2, default=str)

HANDLERS["pangu_onnx_status"] = handle_onnx_status

async def handle_onnx_similarity(server, drawers, arguments):
    """使用 ONNX 计算两条文本的余弦相似度"""
    import math as _math

    from pangu.memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    text_a = arguments.get("text_a", "")
    text_b = arguments.get("text_b", "")
    va = emb.embed(text_a)
    vb = emb.embed(text_b)
    if va is None or vb is None:
        sim = None
    else:
        dot = sum(x * y for x, y in zip(va, vb, strict=False))
        na = _math.sqrt(sum(x * x for x in va))
        nb = _math.sqrt(sum(y * y for y in vb))
        sim = dot / (na * nb + 1e-9)
    return json.dumps({
        "text_a": text_a,
        "text_b": text_b,
        "cosine_similarity": sim,
        "source": "onnx" if emb.is_loaded else "unavailable",
    }, ensure_ascii=False)

HANDLERS["pangu_onnx_similarity"] = handle_onnx_similarity