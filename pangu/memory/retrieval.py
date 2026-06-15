"""盘古 — 记忆召回引擎（从伏羲 v1.5.6 移植，适配盘古数据模型）

核心特性：
1. 混合召回：向量语义 + 关键词匹配
2. Agent过滤
3. 上下文窗口召回（预算裁剪）
4. 结果缓存（可配置TTL）
5. 多维度排序（相关性/重要性/时间）
"""

import json
import logging
import threading
import time
from datetime import datetime

from pangu.core.hashing import hex_digest
from pangu.core.palace import Drawer
from pangu.memory.embedding import get_embedding_service

logger = logging.getLogger("pangu.memory.retrieval")

_recall_cache: dict = {}
_cache_lock = threading.Lock()
_cache_ttl = 60  # 1分钟缓存

# 搜索命中率统计
_search_stats: dict = {
    "total_searches": 0,
    "hits": 0,
    "misses": 0,
    "vector_hits": 0,
    "fts_hits": 0,
    "neural_hits": 0,
}


def get_search_stats() -> dict:
    """获取搜索命中率统计"""
    total = _search_stats["total_searches"]
    hits = _search_stats["hits"]
    return {
        **_search_stats,
        "hit_rate": round(hits / total, 4) if total > 0 else 0.0,
    }


def _record_search(hit: bool, method: str = "") -> None:
    """记录搜索结果"""
    _search_stats["total_searches"] += 1
    if hit:
        _search_stats["hits"] += 1
        if method == "vector":
            _search_stats["vector_hits"] += 1
        elif method == "fts":
            _search_stats["fts_hits"] += 1
        elif method == "neural":
            _search_stats["neural_hits"] += 1
    else:
        _search_stats["misses"] += 1


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


def recall(
    query: str | None = None,
    wing: str | None = None,
    room: str | None = None,
    agent_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    min_importance: float = 0.0,
    sort_by: str = "relevance",
    use_cache: bool = True,
    vector_weight: float = 0.6,
    drawers: list[Drawer] | None = None,
) -> list[dict]:
    """召回记忆，支持多种过滤和排序策略。

    Args:
        query: 搜索查询（可选，为空则返回最近记忆）
        wing: 按 Wing 过滤
        room: 按 Room 过滤
        agent_id: 按 agent_id 过滤（多租户隔离）
        limit: 返回数量上限
        offset: 偏移量
        min_importance: 最低重要性阈值
        sort_by: 排序方式 — relevance / importance / time
        use_cache: 是否使用缓存
        vector_weight: 向量搜索权重 (0.0-1.0)
        drawers: 记忆列表（如果为None则需要外部提供）

    Returns:
        记忆字典列表，含 search_score 字段
    """
    if drawers is None:
        return []

    cache_key = None
    if use_cache and query:
        cache_key = _make_cache_key(query, wing, room, limit, offset, sort_by, min_importance, vector_weight)
        with _cache_lock:
            if cache_key in _recall_cache:
                entry = _recall_cache[cache_key]
                if time.time() - entry["ts"] < _cache_ttl:
                    return entry["data"]

    # 过滤
    filtered = list(drawers)
    if wing:
        filtered = [d for d in filtered if d.wing == wing]
    if room:
        filtered = [d for d in filtered if d.room == room]
    if agent_id:
        filtered = [d for d in filtered if d.author == agent_id]
    if min_importance > 0:
        filtered = [d for d in filtered if d.importance >= min_importance]

    if query and filtered:
        # 向量语义搜索（ONNX 优先）
        query_vec = None
        try:
            from pangu.memory.onnx_embedder import get_onnx_embedder
            onnx = get_onnx_embedder()
            if onnx.is_available:
                query_vec = onnx.embed(query)
        except Exception:
            pass
        if query_vec is None:
            try:
                embed_svc = get_embedding_service()
                query_vec = embed_svc.embed(query)
            except Exception:
                pass

        if query_vec:
            scored = []
            for d in filtered:
                stored_vec = d.metadata.get("embedding")
                if not stored_vec:
                    sim = 0.0
                else:
                    try:
                        sim = _cosine_similarity(query_vec, stored_vec)
                    except Exception:
                        sim = 0.0

                if sim < 0.25:
                    continue

                # 综合打分（神经记忆衰减）
                decay_score = _get_neural_decay_score(d)
                importance_factor = (d.importance / 5.0) * 0.6 + decay_score * 0.4
                relevance = sim * vector_weight + importance_factor * (1 - vector_weight)
                scored.append((d, relevance, sim))

            scored.sort(key=lambda x: x[1], reverse=True)
            results = [_drawer_to_dict(s[0], s[1], s[2]) for s in scored[offset : offset + limit]]
        else:
            # 关键词降级
            query_lower = query.lower()
            keyword_matches = []
            for d in filtered:
                score = 0.0
                if query_lower in d.content.lower():
                    score = 0.8
                # 标签匹配加分
                tag_match = sum(1 for t in d.tags if query_lower in t.lower())
                score += tag_match * 0.2
                if score > 0:
                    keyword_matches.append((d, score))
            keyword_matches.sort(key=lambda x: x[1], reverse=True)
            results = [_drawer_to_dict(m[0], m[1]) for m in keyword_matches[offset : offset + limit]]
    else:
        # 无查询：按排序方式返回
        if sort_by == "importance":
            filtered.sort(key=lambda d: d.importance, reverse=True)
        elif sort_by == "time":
            filtered.sort(key=lambda d: d.created_at, reverse=True)
        else:
            filtered.sort(key=lambda d: d.importance, reverse=True)
        results = [_drawer_to_dict(d) for d in filtered[offset : offset + limit]]

    # 神经激活扩散：基于命中结果扩散找到关联记忆
    if results and len(results) < limit:
        try:
            from pangu.memory.neural_memory import get_neural_engine
            engine = get_neural_engine()
            seed_ids = [r["id"] for r in results[:5]]
            activations = engine.neocortex.activate_spreading(
                seed_ids,
                decay_factor=engine.config.neural_spreading_decay,
                max_depth=engine.config.neural_spreading_depth,
            )
            existing_ids = {r["id"] for r in results}
            for mid, activation in activations:
                if mid not in existing_ids and activation > 0.1:
                    mem = engine.neocortex.get(mid)
                    if mem:
                        results.append({
                            "id": mid,
                            "content": mem.content,
                            "search_score": round(activation * 0.5, 4),
                            "source": "neural_spreading",
                        })
                        if len(results) >= limit:
                            break
        except Exception:
            pass

    if cache_key and results:
        with _cache_lock:
            if len(_recall_cache) >= 100:
                oldest = next(iter(_recall_cache))
                del _recall_cache[oldest]
            _recall_cache[cache_key] = {"ts": time.time(), "data": results}

    # 记录命中率
    if query:
        has_results = len(results) > 0
        method = ""
        if has_results:
            if any(r.get("source") == "neural_spreading" for r in results):
                method = "neural"
            elif any(r.get("search_method") == "fts" for r in results):
                method = "fts"
            else:
                method = "vector"
        _record_search(has_results, method)

    return results


def recall_by_ids(item_ids: list[str], drawers: list[Drawer]) -> list[dict]:
    """按ID批量召回"""
    if not item_ids:
        return []
    id_set = set(item_ids)
    return [_drawer_to_dict(d) for d in drawers if d.id in id_set]


def recall_context(
    wing: str | None = None,
    budget: int = 10,
    drawers: list[Drawer] | None = None,
) -> list[dict]:
    """召回上下文窗口内的记忆（用于LLM上下文组装）

    优选高重要性+近期更新的记忆。
    """
    if drawers is None:
        return []

    filtered = list(drawers)
    if wing:
        filtered = [d for d in filtered if d.wing == wing]

    # 综合评分：重要性 * 0.4 + 衰减分 * 0.3 - 时间衰减 * 0.3
    scored = []
    for d in filtered:
        decay_score = _get_neural_decay_score(d)
        score = (d.importance / 5.0) * 0.4 + decay_score * 0.6
        scored.append((d, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [_drawer_to_dict(d, s) for d, s in scored[:budget]]


def _get_neural_decay_score(drawer: Drawer) -> float:
    """用神经记忆的个性化遗忘曲线计算衰减分数"""
    try:
        from pangu.memory.neural_memory import PersonalizedDecay, NeuralMemory, MemoryType
        decay = PersonalizedDecay()

        # 从 Drawer 推断记忆类型
        tags_lower = [t.lower() for t in drawer.tags] if drawer.tags else []
        if any(t in tags_lower for t in ["decision", "fact", "concept"]):
            mtype = MemoryType.SEMANTIC
        elif any(t in tags_lower for t in ["event", "milestone"]):
            mtype = MemoryType.EPISODIC
        elif any(t in tags_lower for t in ["preference", "advice"]):
            mtype = MemoryType.PROCEDURAL
        elif drawer.emotional_weight and abs(drawer.emotional_weight) > 0.5:
            mtype = MemoryType.EMOTIONAL
        else:
            mtype = MemoryType.EPISODIC

        # 解析 created_at
        try:
            created_ts = datetime.fromisoformat(drawer.created_at).timestamp()
        except (ValueError, TypeError):
            created_ts = time.time()

        mem = NeuralMemory(
            id=drawer.id,
            content=drawer.content,
            memory_type=mtype,
            strength=drawer.importance / 5.0,
            created_at=created_ts,
            access_count=drawer.metadata.get("access_count", 0),
        )
        return decay.retention(mem)
    except Exception:
        # 降级到简单衰减
        try:
            days_old = (datetime.now() - datetime.fromisoformat(drawer.created_at)).total_seconds() / 86400
            return max(0.0, 1.0 - days_old / 365)
        except Exception:
            return 0.5


def _drawer_to_dict(drawer: Drawer, score: float = 0.0, vec_score: float = 0.0) -> dict:
    """将 Drawer 转换为字典（自动解密内容）"""
    content = drawer.content
    if content and content.startswith("gAAAAAB"):
        try:
            from pangu.memory.encryption import decrypt
            content = decrypt(content)
        except Exception:
            pass
    return {
        "id": drawer.id,
        "content": content,
        "wing": drawer.wing,
        "room": drawer.room,
        "importance": drawer.importance,
        "tags": drawer.tags,
        "created_at": drawer.created_at,
        "emotional_weight": drawer.emotional_weight,
        "score": round(score, 4),
        "search_score": round(score, 4),
        "vector_score": round(vec_score, 4),
        "metadata": drawer.metadata,
    }


def _make_cache_key(*args) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hex_digest(raw)


def importance_feedback(drawer_id: str, signal: str, drawers: list[Drawer] | None = None) -> dict:
    """记忆重要性反馈 — 根据使用信号动态调整 importance

    Args:
        drawer_id: 记忆 ID
        signal: 反馈信号 — recall_success / recall_miss / vote_up / vote_down / verified
        drawers: 记忆列表（为 None 时从 drawers.json 加载）

    Returns:
        调整结果
    """
    SIGNAL_MULTIPLIERS = {
        "recall_success": 1.08,   # 召回成功 +8%
        "recall_miss": 0.92,      # 召回失败 -8%
        "vote_up": 1.05,          # 投票好评 +5%
        "vote_down": 0.95,        # 投票差评 -5%
        "verified": 1.15,         # 验证通过 +15%
    }
    multi = SIGNAL_MULTIPLIERS.get(signal)
    if multi is None:
        return {"error": f"unknown signal: {signal}"}

    if drawers is None:
        from pathlib import Path
        from pangu.core.config import PanguConfig
        cfg = PanguConfig.load()
        drawers_file = Path(cfg.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return {"error": "no memories"}
        with open(drawers_file, encoding="utf-8") as f:
            drawers = [Drawer.from_dict(d) for d in json.load(f)]

    target = None
    for d in drawers:
        if d.id == drawer_id:
            target = d
            break

    if not target:
        return {"error": f"memory not found: {drawer_id}"}

    old_imp = target.importance
    target.importance = max(0.5, min(5.0, target.importance * multi))
    target.metadata["last_feedback"] = signal
    target.metadata["feedback_at"] = datetime.now().isoformat()

    # 保存回 drawers.json
    try:
        from pathlib import Path
        from pangu.core.config import PanguConfig
        cfg = PanguConfig.load()
        drawers_file = Path(cfg.palace_path) / "drawers.json"
        with open(drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {
        "id": drawer_id,
        "signal": signal,
        "old_importance": round(old_imp, 3),
        "new_importance": round(target.importance, 3),
    }


def clear_recall_cache():
    """清除召回缓存"""
    global _recall_cache
    with _cache_lock:
        _recall_cache.clear()
    logger.debug("Recall cache cleared")
