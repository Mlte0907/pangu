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

# Constants
IMPORTANCE_SCALE = 5.0  # 盘古 importance 使用 0-5 范围
SIMILARITY_THRESHOLD = 0.92  # 语义相似度阈值
BOOST_INCREMENT = 0.25  # 重复记忆重要性提升值
MAX_IMPORTANCE = 5.0  # 最大重要性值
CONFIDENCE_INCREMENT = 0.1  # 融合时置信度增量
TEXT_OVERLAP_THRESHOLD = 0.85  # 文本相似度降级去重阈值
MIN_TEXT_LENGTH_FOR_DEDUP = 20  # 文本去重最小长度
MAX_LENGTH_DIFF_FOR_DEDUP = 5  # 文本去重长度差阈值
MIN_CONTENT_LENGTH = 10  # 内容最小长度
EMBEDDING_DIM_LIMIT = 384  # 嵌入向量维度限制
MIN_EMBEDDING_NORM = 1e-6  # 最小嵌入向量范数
CONFLICT_MIN_EXISTING = 3  # 冲突检测最小已有记忆数
CONFLICT_LOOKBACK = 20  # 冲突检测回溯记忆数
CONFLICT_MAX_REPORT = 3  # 冲突报告最大数量

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
    except Exception as e:
        logger.debug(f"Embedding service failed: {e}")
        return None


def _cosine_similarity(a: list, b: list) -> float:
    """余弦相似度（使用统一实现）"""
    from .utils import cosine_similarity

    return cosine_similarity(a, b)


def _sanitize_text(raw_text: str) -> str:
    """脱敏处理文本"""
    try:
        from pangu.memory.sanitizer import MemorySanitizer

        sanitized, _ = MemorySanitizer.sanitize(raw_text, level="standard")
        return sanitized
    except Exception as e:
        logger.debug(f"Sanitization failed: {e}")
        return raw_text


def _encrypt_text(raw_text: str) -> str:
    """加密处理文本（如果启用）"""
    try:
        from pangu.memory.encryption import encrypt, is_enabled

        if is_enabled():
            return encrypt(raw_text)
    except Exception as e:
        logger.debug(f"Encryption failed: {e}")
    return raw_text


def _dedup_and_fuse(
    raw_text: str,
    wing: str,
    room: str,
    existing_drawers: list[Drawer],
) -> tuple[Drawer | None, str | None]:
    """去重和融合检查，返回 (重复drawer, 融合id) 或 (None, None)"""
    # 精确匹配
    for d in existing_drawers:
        if d.content == raw_text and d.wing == wing:
            logger.debug(f"Exact duplicate found: {d.id[:8]}")
            return d, None

    # 语义相似度去重
    embed_svc = get_embedding_service()
    query_vec = embed_svc.embed(raw_text)
    if query_vec is not None:
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
                if score > SIMILARITY_THRESHOLD and score > best_score:
                    best_score = score
                    best_drawer = d
            except Exception:
                continue
        if best_drawer:
            logger.info(f"Semantic duplicate found: score={best_score:.3f}")
            return best_drawer, None

    # 文本相似度降级去重
    if len(raw_text) >= MIN_TEXT_LENGTH_FOR_DEDUP:
        for d in existing_drawers:
            if d.wing != wing or len(d.content) < MIN_CONTENT_LENGTH:
                continue
            if abs(len(raw_text) - len(d.content)) > MAX_LENGTH_DIFF_FOR_DEDUP:
                continue
            overlap = sum(1 for a, b in zip(raw_text, d.content, strict=False) if a == b)
            len_norm = max(len(raw_text), len(d.content))
            if overlap / len_norm > TEXT_OVERLAP_THRESHOLD:
                return d, None

    # 融合检查
    if query_vec is not None:
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
                if score > SIMILARITY_THRESHOLD and score > best_score:
                    best_score = score
                    best_drawer = d
            except Exception:
                continue
        if best_drawer is not None:
            # 融合：保留更长的内容，更新置信度
            if len(raw_text) > len(best_drawer.content):
                best_drawer.content = raw_text
            old_confidence = best_drawer.metadata.get("confidence", 1.0)
            best_drawer.metadata["confidence"] = min(1.0, old_confidence + CONFIDENCE_INCREMENT)
            best_drawer.metadata["fused_count"] = best_drawer.metadata.get("fused_count", 0) + 1
            best_drawer.metadata["fused_at"] = datetime.now().isoformat()
            _fusion_stats["count"] += 1
            _fusion_stats["by_drawer"][wing] = _fusion_stats["by_drawer"].get(wing, 0) + 1
            logger.info(f"Memory fused: {best_drawer.id[:8]} (score={best_score:.3f})")
            return None, best_drawer.id

    return None, None


def _create_drawer(
    item_id: str,
    stored_text: str,
    wing: str,
    room: str,
    importance: float,
    tags: list,
    author: str,
    now: str,
    source: str,
    confidence: float,
    created_by: str,
    facts: str,
    emotional_valence: float,
) -> Drawer:
    """创建新的 Drawer 对象"""
    return Drawer(
        id=item_id,
        content=stored_text,
        wing=wing,
        room=room,
        importance=importance * IMPORTANCE_SCALE,
        emotional_weight=emotional_valence,
        tags=tags,
        author=author,
        created_at=now,
        metadata={
            "source": source,
            "confidence": confidence,
            "created_by": created_by,
            "facts": facts,
            "emotional_valence": emotional_valence,
            "memory_status": "active",
        },
    )


def _embed_and_store(drawer: Drawer, raw_text: str) -> None:
    """生成向量嵌入并存储到 drawer"""
    try:
        vec = _embed_text(raw_text)
        if vec and not all(abs(v) < MIN_EMBEDDING_NORM for v in vec):
            drawer.metadata["embedding"] = vec[:EMBEDDING_DIM_LIMIT] if len(vec) > EMBEDDING_DIM_LIMIT else vec
    except Exception as e:
        logger.debug(f"Embedding generation skipped: {e}")


def _extract_wikilinks(
    drawer: Drawer,
    raw_text: str,
    item_id: str,
    existing_drawers: list[Drawer] | None,
) -> None:
    """提取 Wikilink 实体链接"""
    try:
        from pangu.memory.wikilink import extract_entity_links

        links = extract_entity_links(raw_text, item_id, existing_drawers or [])
        if links:
            drawer.metadata["wikilinks"] = links
    except Exception as e:
        logger.debug(f"Wikilink extraction skipped: {e}")


def _index_vector(drawer: Drawer, item_id: str) -> None:
    """更新向量索引"""
    try:
        from pangu.memory.vector_index import get_vector_index

        idx = get_vector_index()
        emb = drawer.metadata.get("embedding")
        if emb:
            idx.add(emb, item_id)
            logger.debug(f"Vector index updated: added {item_id[:8]}")
    except Exception as e:
        logger.debug(f"Vector index update skipped: {e}")


def _neural_encode(drawer: Drawer, item_id: str) -> None:
    """神经记忆编码"""
    try:
        from pangu.memory.neural_memory import get_neural_engine

        engine = get_neural_engine()
        engine.encode(drawer)
        logger.debug(f"Neural encoding: {item_id[:8]}")
    except Exception as e:
        logger.debug(f"Neural encoding skipped: {e}")


def _detect_conflicts(drawer: Drawer, existing_drawers: list[Drawer], item_id: str) -> None:
    """自动冲突检测"""
    if existing_drawers and len(existing_drawers) >= CONFLICT_MIN_EXISTING:
        try:
            from pangu.memory.conflict import ConflictDetector

            detector = ConflictDetector()
            conflicts = detector.detect_conflicts([drawer] + existing_drawers[-CONFLICT_LOOKBACK:])
            if conflicts:
                drawer.metadata["conflicts"] = [
                    {
                        "id": c.id,
                        "severity": c.severity.value,
                        "with": c.memory_a if c.memory_b == item_id else c.memory_b,
                    }
                    for c in conflicts[:CONFLICT_MAX_REPORT]
                ]
                logger.info(f"Conflict detected for {item_id[:8]}: {len(conflicts)} conflicts")
        except Exception as e:
            logger.debug(f"Conflict detection skipped: {e}")


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
    raw_text = _sanitize_text(raw_text)

    # 加密处理（可选）
    stored_text = _encrypt_text(raw_text)

    # 去重和融合检查
    if existing_drawers:
        duplicate, fused_id = _dedup_and_fuse(raw_text, wing, room, existing_drawers)
        if duplicate:
            _boost_existing(duplicate)
            return duplicate.id, duplicate
        if fused_id:
            for d in existing_drawers:
                if d.id == fused_id:
                    return fused_id, d

    # 创建新记忆
    item_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    drawer = _create_drawer(
        item_id=item_id,
        stored_text=stored_text,
        wing=wing,
        room=room,
        importance=importance,
        tags=tags,
        author=author,
        now=now,
        source=source,
        confidence=confidence,
        created_by=created_by,
        facts=facts,
        emotional_valence=emotional_valence,
    )

    # 生成向量嵌入（ONNX 优先，保证语义向量质量）
    _embed_and_store(drawer, raw_text)

    # 全息编码
    try:
        _encode_hologram(item_id, raw_text, now, wing, emotional_valence, source, created_by, tags)
    except Exception as e:
        logger.debug(f"Holographic encoding skipped: {e}")

    # Wikilink 实体链接提取
    _extract_wikilinks(drawer, raw_text, item_id, existing_drawers)

    # 写入后触发向量索引更新
    if not _skip_index_update:
        _index_vector(drawer, item_id)

    # 神经记忆编码（海马体-新皮层双系统）
    _neural_encode(drawer, item_id)

    # 自动冲突检测
    _detect_conflicts(drawer, existing_drawers, item_id)

    logger.info(f"Remembered: {item_id[:8]} in wing={wing}, room={room}, importance={importance}")
    return item_id, drawer


def _decrypt_content(drawer: Drawer) -> Drawer | None:
    """解密 drawer 内容，返回新 Drawer 或 None（不需要解密时）"""
    from pangu.memory.encryption import decrypt, is_enabled

    if not is_enabled() or not drawer.content:
        return None
    decrypted = decrypt(drawer.content)
    if decrypted == drawer.content:
        return None
    return Drawer(
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


def maybe_decrypt(drawer: Drawer) -> Drawer:
    """如果启用了加密，解密 drawer 内容（不修改原始对象）"""
    try:
        result = _decrypt_content(drawer)
        if result is not None:
            return result
    except Exception as e:
        logger.debug(f"Decryption failed: {e}")
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
    similarity_threshold: float = SIMILARITY_THRESHOLD,
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
    if len(raw_text) < MIN_TEXT_LENGTH_FOR_DEDUP:
        return None
    for d in existing_drawers:
        if d.wing != wing or len(d.content) < MIN_CONTENT_LENGTH:
            continue
        if abs(len(raw_text) - len(d.content)) > MAX_LENGTH_DIFF_FOR_DEDUP:
            continue
        overlap = sum(1 for a, b in zip(raw_text, d.content, strict=False) if a == b)
        len_norm = max(len(raw_text), len(d.content))
        if overlap / len_norm > TEXT_OVERLAP_THRESHOLD:
            return d
    return None


def _boost_existing(drawer: Drawer):
    """提升已有记忆的重要性"""
    drawer.importance = min(MAX_IMPORTANCE, drawer.importance + BOOST_INCREMENT)
    drawer.metadata["boosted_at"] = datetime.now().isoformat()


def _check_memory_fusion(
    raw_text: str,
    wing: str,
    room: str,
    existing_drawers: list[Drawer],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
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
    best_drawer.metadata["confidence"] = min(1.0, old_confidence + CONFIDENCE_INCREMENT)
    best_drawer.metadata["fused_count"] = best_drawer.metadata.get("fused_count", 0) + 1
    best_drawer.metadata["fused_at"] = datetime.now().isoformat()

    _fusion_stats["count"] += 1
    _fusion_stats["by_drawer"][wing] = _fusion_stats["by_drawer"].get(wing, 0) + 1

    logger.info(f"Memory fused: {best_drawer.id[:8]} (score={best_score:.3f})")
    return best_drawer.id


def get_fusion_stats() -> dict:
    """获取融合统计"""
    return dict(_fusion_stats)


def _fill_missing_embeddings(results: list, texts: list[str]) -> list:
    """补齐批量嵌入结果中的 None 值"""
    for i, r in enumerate(results):
        if r is None:
            results[i] = _embed_text(texts[i])
    return results


def _embed_batch(texts: list[str]) -> list[list[float] | None]:
    """ONNX 批量嵌入，降级到逐条"""
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder

        onnx = get_onnx_embedder()
        if onnx.is_available:
            results = onnx.embed_batch(texts)
            return _fill_missing_embeddings(results, texts)
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
                drawer.metadata["embedding"] = emb[:EMBEDDING_DIM_LIMIT] if len(emb) > EMBEDDING_DIM_LIMIT else emb
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
            valid = [(v, i) for v, i in zip(vectors, ids, strict=False) if v]
            if valid:
                added = idx.add_batch([v for v, _ in valid], [i for _, i in valid])
                logger.debug(f"Vector index batch update: {added} vectors")
        except Exception as e:
            logger.debug(f"Vector index batch update skipped: {e}")

    return results
