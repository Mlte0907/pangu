"""盘古 — 记忆摄入管道（从伏羲 v1.5.6 移植，适配盘古数据模型）

核心特性：
1. 统一记忆摄入入口 remember()
2. 自动去重（精确匹配 + 语义相似度）
3. 记忆融合（相似记忆合并增强）
4. 全息编码集成
5. Wikilink 实体链接提取
6. 自动创建缺失的 Wing/Room
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from pangu.core.palace import Drawer
from pangu.memory.embedding import get_embedding_service

logger = logging.getLogger("pangu.memory.ingestion")

_fusion_stats: dict[str, Any] = {"count": 0, "by_drawer": {}}


def _embed_text(text: str) -> list[float] | None:
    """ONNX 优先嵌入，保证语义向量质量"""
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        if onnx.is_available:
            vec = onnx.embed(text)
            if vec and len(vec) > 0:
                return vec
    except Exception as e:
        logger.debug(f"ONNX embed failed: {e}")

    # ONNX 不可用时降级到 embedding service（API→hash）
    try:
        embed_svc = get_embedding_service()
        return embed_svc.embed(text)
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    """余弦相似度"""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    a_trunc = a[:n]
    b_trunc = b[:n]
    dot = sum(x * y for x, y in zip(a_trunc, b_trunc, strict=False))
    norm_a = sum(x * x for x in a_trunc) ** 0.5
    norm_b = sum(x * x for x in b_trunc) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def remember(
    raw_text: str,
    wing: str = "default",
    room: str = "general",
    importance: float = 0.5,
    tags: list | None = None,
    source: str = "direct",
    confidence: float | None = None,
    created_by: str = "system",
    author: str = "",  # 新增：记录写入者 agent_id
    facts: str = "",
    emotional_valence: float = 0.0,
    existing_drawers: list[Drawer] | None = None,
    _skip_index_update: bool = False,
) -> tuple[str, Drawer]:
    """摄入一条记忆。

    流程：
    1. 脱敏检查
    2. 去重检查（精确匹配 + 语义相似度）
    3. 记忆融合检查
    4. 创建 Drawer 并生成向量嵌入
    5. 全息编码
    6. Wikilink 实体链接提取

    Args:
        raw_text: 原始文本
        wing: 所属 Wing
        room: 所属 Room
        importance: 重要性 (0.0-1.0)
        tags: 标签列表
        source: 来源标识
        confidence: 置信度
        created_by: 创建者
        facts: 事实摘要
        emotional_valence: 情感值 (-1.0 ~ 1.0)
        existing_drawers: 已有记忆列表（用于去重）

    Returns:
        (item_id, Drawer) — 新创建或已存在的 Drawer
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text is required")
    if not isinstance(importance, (int, float)) or importance < 0.0 or importance > 1.0:
        raise ValueError(f"importance must be between 0.0 and 1.0, got {importance}")
    if confidence is None:
        confidence = 1.0
    tags = tags or []

    # 脱敏处理
    try:
        from pangu.memory.sanitizer import MemorySanitizer
        raw_text, _ = MemorySanitizer.sanitize(raw_text, level="standard")
    except Exception:
        pass

    # 加密处理（可选）
    stored_text = raw_text
    try:
        from pangu.memory.encryption import is_enabled, encrypt
        if is_enabled():
            stored_text = encrypt(raw_text)
    except Exception:
        pass

    # 去重检查
    if existing_drawers:
        existing = _find_duplicate(raw_text, wing, room, existing_drawers)
        if existing:
            _boost_existing(existing)
            return existing.id, existing

    # 检查记忆融合
    if existing_drawers:
        fused_id = _check_memory_fusion(raw_text, wing, room, existing_drawers)
        if fused_id:
            for d in existing_drawers:
                if d.id == fused_id:
                    return fused_id, d

    # 创建新记忆
    item_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    drawer = Drawer(
        id=item_id,
        content=stored_text,
        wing=wing,
        room=room,
        importance=importance * 5.0,  # 盘古 importance 使用 0-5 范围
        emotional_weight=emotional_valence,
        tags=tags,
        author=author,  # 新增：记录写入者 agent_id
        created_at=now,
        metadata={
            "source": source,
            "confidence": confidence,
            "created_by": created_by,
            "facts": facts,
            "emotional_valence": emotional_valence,
            "memory_status": "active",  # active / stale / conflicted / verified
        },
    )

    # 生成向量嵌入（ONNX 优先，保证语义向量质量）
    try:
        vec = _embed_text(raw_text)
        if vec and not all(abs(v) < 1e-6 for v in vec):
            drawer.metadata["embedding"] = vec[:384] if len(vec) > 384 else vec
    except Exception as e:
        logger.debug(f"Embedding generation skipped: {e}")

    # 全息编码
    try:
        _encode_hologram(item_id, raw_text, now, wing, emotional_valence, source, created_by, tags)
    except Exception as e:
        logger.debug(f"Holographic encoding skipped: {e}")

    # Wikilink 实体链接提取
    try:
        from pangu.memory.wikilink import extract_entity_links
        links = extract_entity_links(raw_text, item_id, existing_drawers or [])
        if links:
            drawer.metadata["wikilinks"] = links
    except Exception as e:
        logger.debug(f"Wikilink extraction skipped: {e}")

    # 写入后触发向量索引更新
    if not _skip_index_update:
        try:
            from pangu.memory.vector_index import get_vector_index
            idx = get_vector_index()
            emb = drawer.metadata.get("embedding")
            if emb:
                idx.add(emb, item_id)
                logger.debug(f"Vector index updated: added {item_id[:8]}")
        except Exception as e:
            logger.debug(f"Vector index update skipped: {e}")

    # 神经记忆编码（海马体-新皮层双系统）
    try:
        from pangu.memory.neural_memory import get_neural_engine
        engine = get_neural_engine()
        engine.encode(drawer)
        logger.debug(f"Neural encoding: {item_id[:8]}")
    except Exception as e:
        logger.debug(f"Neural encoding skipped: {e}")

    # 自动冲突检测（仅在有足够已有记忆时执行）
    if existing_drawers and len(existing_drawers) >= 3:
        try:
            from pangu.memory.conflict import ConflictDetector
            detector = ConflictDetector()
            conflicts = detector.detect_conflicts([drawer] + existing_drawers[-20:])
            if conflicts:
                drawer.metadata["conflicts"] = [
                    {"id": c.id, "severity": c.severity.value, "with": c.memory_a if c.memory_b == item_id else c.memory_b}
                    for c in conflicts[:3]
                ]
                logger.info(f"Conflict detected for {item_id[:8]}: {len(conflicts)} conflicts")
        except Exception as e:
            logger.debug(f"Conflict detection skipped: {e}")

    logger.info(f"Remembered: {item_id[:8]} in wing={wing}, room={room}, importance={importance}")
    return item_id, drawer


def maybe_decrypt(drawer: Drawer) -> Drawer:
    """如果启用了加密，解密 drawer 内容（不修改原始对象）"""
    try:
        from pangu.memory.encryption import is_enabled, decrypt
        if is_enabled() and drawer.content:
            decrypted = decrypt(drawer.content)
            if decrypted != drawer.content:
                new_drawer = Drawer(
                    id=drawer.id,
                    content=decrypted,
                    wing=drawer.wing,
                    room=drawer.room,
                    hall=drawer.hall,
                    importance=drawer.importance,
                    emotional_weight=drawer.emotional_weight,
                    source_file=drawer.source_file,
                    tags=drawer.tags,
                    author=drawer.author,
                    created_at=drawer.created_at,
                    metadata=drawer.metadata,
                )
                return new_drawer
    except Exception:
        pass
    return drawer


def _encode_hologram(
    item_id: str,
    raw_text: str,
    created_at: str,
    wing: str,
    emotional_valence: float,
    source: str,
    created_by: str,
    tags: list,
):
    """全息编码集成"""
    try:
        from pangu.memory.hologram import HolographicEncoder

        encoder = HolographicEncoder()
        hologram = encoder.encode(
            item_id=item_id,
            raw_text=raw_text,
            created_at=created_at,
            wing=wing,
            valence=emotional_valence,
            source_type=source,
            agent_id=created_by,
        )
        # 存储全息投影（可选）
        if hologram and hologram.projections:
            logger.debug(f"Hologram encoded for {item_id[:8]}: {list(hologram.projections.keys())}")
    except Exception as e:
        logger.debug(f"Hologram encoding failed: {e}")


def _find_duplicate(
    raw_text: str,
    wing: str,
    room: str,
    existing_drawers: list[Drawer],
    similarity_threshold: float = 0.92,
) -> Drawer | None:
    """查找重复记忆"""
    # 精确匹配
    for d in existing_drawers:
        if d.content == raw_text and d.wing == wing:
            logger.debug(f"Exact duplicate found: {d.id[:8]}")
            return d

    # 语义相似度检查
    embed_svc = get_embedding_service()
    query_vec = embed_svc.embed(raw_text)
    if query_vec is None:
        return _text_based_fallback_dedup(raw_text, wing, existing_drawers)

    best_score = 0.0
    best_drawer = None
    for d in existing_drawers:
        if d.wing != wing:
            continue
        stored_vec = d.metadata.get("embedding")
        if not stored_vec:
            continue
        try:
            score = _cosine_similarity(query_vec, stored_vec)
            if score > similarity_threshold and score > best_score:
                best_score = score
                best_drawer = d
        except Exception:
            continue

    if best_drawer:
        logger.info(f"Semantic duplicate found: score={best_score:.3f}")
        return best_drawer
    return None


def _text_based_fallback_dedup(
    raw_text: str,
    wing: str,
    existing_drawers: list[Drawer],
) -> Drawer | None:
    """文本相似度降级去重"""
    if len(raw_text) < 20:
        return None
    for d in existing_drawers:
        if d.wing != wing or len(d.content) < 10:
            continue
        if abs(len(raw_text) - len(d.content)) > 5:
            continue
        overlap = sum(1 for a, b in zip(raw_text, d.content, strict=False) if a == b)
        len_norm = max(len(raw_text), len(d.content))
        if overlap / len_norm > 0.85:
            return d
    return None


def _boost_existing(drawer: Drawer):
    """提升已有记忆的重要性"""
    drawer.importance = min(5.0, drawer.importance + 0.25)
    drawer.metadata["boosted_at"] = datetime.now().isoformat()


def _check_memory_fusion(
    raw_text: str,
    wing: str,
    room: str,
    existing_drawers: list[Drawer],
    similarity_threshold: float = 0.92,
) -> str | None:
    """检查是否可以融合到已有记忆中"""
    embed_svc = get_embedding_service()
    query_vec = embed_svc.embed(raw_text)
    if query_vec is None:
        return None

    best_score = 0.0
    best_drawer = None
    for d in existing_drawers:
        if d.wing != wing:
            continue
        stored_vec = d.metadata.get("embedding")
        if not stored_vec:
            continue
        try:
            score = _cosine_similarity(query_vec, stored_vec)
            if score > similarity_threshold and score > best_score:
                best_score = score
                best_drawer = d
        except Exception:
            continue

    if best_drawer is None:
        return None

    # 融合：保留更长的内容，更新置信度
    if len(raw_text) > len(best_drawer.content):
        best_drawer.content = raw_text

    old_confidence = best_drawer.metadata.get("confidence", 1.0)
    best_drawer.metadata["confidence"] = min(1.0, old_confidence + 0.1)
    best_drawer.metadata["fused_count"] = best_drawer.metadata.get("fused_count", 0) + 1
    best_drawer.metadata["fused_at"] = datetime.now().isoformat()

    _fusion_stats["count"] += 1
    _fusion_stats["by_drawer"][wing] = _fusion_stats["by_drawer"].get(wing, 0) + 1

    logger.info(f"Memory fused: {best_drawer.id[:8]} (score={best_score:.3f})")
    return best_drawer.id


def get_fusion_stats() -> dict:
    """获取融合统计"""
    return dict(_fusion_stats)


def _embed_batch(texts: list[str]) -> list[list[float] | None]:
    """ONNX 批量嵌入，降级到逐条"""
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        if onnx.is_available:
            results = onnx.embed_batch(texts)
            # 补齐 None
            for i, r in enumerate(results):
                if r is None:
                    results[i] = _embed_text(texts[i])
            return results
    except Exception as e:
        logger.debug(f"ONNX batch embed failed: {e}")

    return [_embed_text(t) for t in texts]


def ingest_batch(
    texts: list[str],
    wing: str = "default",
    room: str = "general",
    existing_drawers: list[Drawer] | None = None,
) -> list[tuple[str, Drawer]]:
    """批量摄入记忆（批量 embedding + 批量向量索引更新）"""
    if not texts:
        return []

    # 批量生成 embeddings
    all_embeddings = _embed_batch(texts)

    results = []
    for i, text in enumerate(texts):
        try:
            item_id, drawer = remember(
                raw_text=text,
                wing=wing,
                room=room,
                existing_drawers=existing_drawers,
                _skip_index_update=True,
            )
            # 注入预计算的 embedding
            emb = all_embeddings[i]
            if emb:
                drawer.metadata["embedding"] = emb[:384] if len(emb) > 384 else emb
            results.append((item_id, drawer))
            if existing_drawers is not None:
                existing_drawers.append(drawer)
        except Exception as e:
            logger.warning(f"Batch ingest failed for text: {e}")

    # 批量更新向量索引
    if results:
        try:
            from pangu.memory.vector_index import get_vector_index
            idx = get_vector_index()
            vectors = [d.metadata.get("embedding") for _, d in results]
            ids = [rid for rid, _ in results]
            valid = [(v, i) for v, i in zip(vectors, ids) if v]
            if valid:
                added = idx.add_batch([v for v, _ in valid], [i for _, i in valid])
                logger.debug(f"Vector index batch update: {added} vectors")
        except Exception as e:
            logger.debug(f"Vector index batch update skipped: {e}")

    return results
