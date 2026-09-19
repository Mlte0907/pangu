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
import os
import threading
import time
from datetime import datetime
from typing import Any

from pangu.core.hashing import hex_digest
from pangu.core.palace import Drawer
from pangu.memory.embedding import get_embedding_service
from pangu.memory.utils import LRUCache

logger = logging.getLogger("pangu.memory.retrieval")

_recall_cache = LRUCache(max_size=100, ttl_seconds=60)

# 搜索命中率统计
_search_stats: dict = {
    "total_searches": 0,
    "hits": 0,
    "misses": 0,
    "vector_hits": 0,
    "fts_hits": 0,
    "neural_hits": 0,
    "cache_hits": 0,
    "cache_misses": 0,
}

# 搜索历史（最近 50 条）
_search_history: list[dict] = []
_search_history_max = 50

# 向量搜索缓存（query → embedding + timestamp）
_vector_cache = LRUCache(max_size=1000, ttl_seconds=3600)


def get_search_stats() -> dict:
    """获取搜索命中率统计"""
    total = _search_stats["total_searches"]
    hits = _search_stats["hits"]
    return {
        **_search_stats,
        "hit_rate": round(hits / total, 4) if total > 0 else 0.0,
    }


def get_search_history(limit: int = 10) -> list[dict]:
    """获取搜索历史"""
    return _search_history[-limit:]


def _record_search(hit: bool, method: str = "", query: str = "", result_count: int = 0) -> None:
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

    # 记录搜索历史
    if query:
        entry = {
            "query": query,
            "hit": hit,
            "method": method,
            "result_count": result_count,
            "timestamp": time.time(),
        }
        _search_history.append(entry)
        if len(_search_history) > _search_history_max:
            _search_history.pop(0)


def _safe_execute(func, default=None, error_msg: str = "") -> Any:
    """安全执行函数，捕获异常并返回默认值"""
    try:
        return func()
    except Exception as e:
        logger.warning(f"{error_msg}: {e}")
        return default


def _cosine_similarity(a: list, b: list) -> float:
    """余弦相似度（委托给统一实现）"""
    from .utils import cosine_similarity

    return cosine_similarity(a, b)


def _try_onnx_embed(query: str) -> list[float] | None:
    """尝试 ONNX 嵌入"""
    try:
        from pangu.memory.onnx_embedder import get_onnx_embedder

        onnx = get_onnx_embedder()
        if onnx.is_available:
            return onnx.embed(query)
    except Exception:
        pass
    return None


def _try_service_embed(query: str) -> list[float] | None:
    """尝试 embedding service 嵌入"""
    try:
        embed_svc = get_embedding_service()
        return embed_svc.embed(query)
    except Exception:
        return None


def _embed_query_vec(query: str) -> list[float] | None:
    """获取查询向量（ONNX 优先，降级到 embedding service）"""
    query_vec = None
    cache_key = f"vec_{query}"
    cached_vec = _vector_cache.get(cache_key)
    if cached_vec is not None:
        query_vec = cached_vec
    if query_vec is None:
        query_vec = _try_onnx_embed(query)
    if query_vec is None:
        query_vec = _try_service_embed(query)
    if query_vec:
        _vector_cache.set(cache_key, query_vec)
    return query_vec


def _search_vectors_bruteforce(query_vec: list[float], drawers: list[Drawer]) -> dict[str, float]:
    """降级：逐条遍历向量搜索"""
    vec_results = {}
    for d in drawers:
        stored_vec = d.metadata.get("embedding")
        if not stored_vec:
            continue
        try:
            sim = _cosine_similarity(query_vec, stored_vec)
        except Exception:
            sim = 0.0
        if sim >= 0.65:
            vec_results[d.id] = sim
    return vec_results


def _vector_search_with_index(query_vec: list[float], drawers: list[Drawer]) -> dict[str, float]:
    """使用 VectorIndex 加速搜索，降级到 brute-force"""
    vec_results = {}
    try:
        from pangu.memory.vector_index import get_vector_index

        idx = get_vector_index()
        if idx.is_built and idx.size > 0:
            search_results = idx.search(query_vec, top_k=min(len(drawers), 100))
            valid_ids = {d.id for d in drawers}
            for did, sim in search_results:
                if did in valid_ids and sim >= 0.65:
                    vec_results[did] = sim
        else:
            vec_results = _search_vectors_bruteforce(query_vec, drawers)
    except Exception:
        vec_results = _search_vectors_bruteforce(query_vec, drawers)
    return vec_results


def _fts_search_task(query: str, drawers: list[Drawer], full_drawers: list[Drawer] | None = None) -> dict[str, float]:
    """FTS 搜索任务

    full_drawers: 用于建索引的全量列表（防止子集覆盖全量索引）。
                  若为 None 则用 drawers（向后兼容）。
    """
    try:
        from pangu.memory.fts_search import FTS5SearchEngine

        fts = FTS5SearchEngine()
        # B7-c：用全量建索引，搜索用子集
        fts.build_index(full_drawers if full_drawers is not None else drawers)
        return fts._fts_search(query, drawers)
    except Exception:
        return {}


def _collect_spreading_results(activations, existing_ids, engine, results, limit) -> None:
    for mid, activation in activations:
        if mid not in existing_ids and activation > 0.1:
            mem = engine.neocortex.get(mid)
            if mem:
                results.append(
                    {
                        "id": mid,
                        "content": mem.content,
                        "search_score": round(activation * 0.5, 4),
                        "source": "neural_spreading",
                    }
                )
                if len(results) >= limit:
                    break


def _expand_with_neural_spreading(results: list[dict], limit: int) -> None:
    """通过神经激活扩散扩展搜索结果"""
    if not results or len(results) >= limit:
        return
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
        _collect_spreading_results(activations, existing_ids, engine, results, limit)
    except Exception:
        pass


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
        cached = _recall_cache.get(cache_key)
        if cached is not None:
            _search_stats["cache_hits"] += 1
            return cached
        _search_stats["cache_misses"] += 1

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
        # 查询扩展（短查询 + 同义词）
        expanded_query = _expand_query(query, filtered) if len(query) < 4 else query
        try:
            from pangu.memory.synonyms import expand_synonyms

            syn_words = expand_synonyms(query)
            if syn_words:
                expanded_query = expanded_query + " " + " ".join(syn_words[:3])
        except Exception:
            pass

        # 并行搜索：向量 + FTS（使用线程池）
        RRF_K = 60
        rrf_scores: dict[str, float] = {}

        # 顺序执行（优化后）
        query_vec = _embed_query_vec(query)
        vec_results = _vector_search_with_index(query_vec, filtered) if query_vec else {}
        fts_results = _fts_search_task(expanded_query, filtered, full_drawers=drawers)

        # 向量搜索 RRF
        sorted_vec = sorted(vec_results.items(), key=lambda x: -x[1])
        for rank, (did, _) in enumerate(sorted_vec):
            rrf_scores[did] = rrf_scores.get(did, 0) + 1.0 / (RRF_K + rank + 1)

        # FTS 搜索 RRF
        for rank, (did, _) in enumerate(sorted(fts_results.items(), key=lambda x: -x[1])):
            rrf_scores[did] = rrf_scores.get(did, 0) + 0.5 / (RRF_K + rank + 1)

        # ── 排序返回（多维度综合评分） ──
        if rrf_scores:
            drawer_map = {d.id: d for d in filtered}

            def _compute_score(did: str) -> float:
                """多维度综合评分 = RRF + 神经衰减 + 重要性 + 标签"""
                d = drawer_map.get(did)
                if not d:
                    return rrf_scores.get(did, 0)

                base = rrf_scores[did]

                # 神经衰减加成（替代简单时间加成）
                try:
                    from pangu.memory.retrieval import _get_neural_decay_score

                    decay_score = _get_neural_decay_score(d)
                    decay_boost = decay_score * 0.15
                except Exception:
                    decay_boost = 0.0

                # 重要性加成：高重要性 +5%
                imp_boost = (d.importance / 5.0) * 0.05

                # 标签加成：匹配查询词的标签 +3%
                query_words = set(query.lower().split())
                tag_match = sum(1 for t in d.tags if t.lower() in query_words or query_words & set(t.lower().split()))
                tag_boost = min(tag_match * 0.03, 0.09)

                return base + decay_boost + imp_boost + tag_boost

            sorted_ids = sorted(rrf_scores.keys(), key=lambda x: -_compute_score(x))
            results = []
            for did in sorted_ids[offset : offset + limit]:
                if did in drawer_map:
                    d = drawer_map[did]
                    vec_sim = vec_results.get(did, 0.0)
                    results.append(_drawer_to_dict(d, rrf_scores[did], vec_sim, query))
        else:
            # 降级：关键词匹配
            query_lower = query.lower()
            keyword_matches = []
            for d in filtered:
                score = 0.0
                if query_lower in d.content.lower():
                    score = 0.8
                tag_match = sum(1 for t in d.tags if query_lower in t.lower())
                score += tag_match * 0.2
                if score > 0:
                    keyword_matches.append((d, score))
            keyword_matches.sort(key=lambda x: x[1], reverse=True)
            results = [_drawer_to_dict(m[0], m[1], 0.0, query) for m in keyword_matches[offset : offset + limit]]
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
    _expand_with_neural_spreading(results, limit)

    if cache_key and results:
        _recall_cache.set(cache_key, results)

    # 无结果时提供搜索建议
    if query and not results and drawers:
        suggestions = _get_search_suggestions(query, drawers)
        if suggestions:
            results = [{"id": "__suggestion__", "content": f"试试: {', '.join(suggestions)}", "suggestion": True}]

    # 记录命中率
    if query:
        has_results = len(results) > 0 and not any(r.get("suggestion") for r in results)
        method = ""
        if has_results:
            if any(r.get("source") == "neural_spreading" for r in results):
                method = "neural"
            elif any(r.get("search_method") == "fts" for r in results):
                method = "fts"
            else:
                method = "vector"
        _record_search(has_results, method, query, len(results))

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
        from pangu.memory.neural_memory import MemoryType, NeuralMemory, PersonalizedDecay

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


def _expand_query(query: str, drawers: list[Drawer]) -> str:
    """短查询自动扩展关键词（基于已有记忆的标签）"""
    if len(query) >= 4 or not drawers:
        return query

    # 提取所有标签
    all_tags = set()
    for d in drawers:
        all_tags.update(t.lower() for t in d.tags if t)

    # 找与查询词相关的标签
    expanded = [query]
    for tag in all_tags:
        if query.lower() in tag or tag in query.lower():
            expanded.append(tag)
        elif len(query) >= 2 and any(c in tag for c in query):
            expanded.append(tag)

    return " ".join(expanded[:3]) if len(expanded) > 1 else query


def _get_search_suggestions(query: str, drawers: list[Drawer], max_suggestions: int = 3) -> list[str]:
    """基于已有记忆生成搜索建议"""
    if not drawers or not query:
        return []

    # 提取所有标签和关键词
    all_tags = set()
    all_keywords = set()
    for d in drawers:
        all_tags.update(t.lower() for t in d.tags if t)
        # 从内容提取关键词（取前 3 个词）
        words = [w.lower() for w in d.content.split() if len(w) >= 2]
        all_keywords.update(words[:3])

    # 合并标签和关键词
    candidates = all_tags | all_keywords

    # 找与查询词相关的建议
    query_lower = query.lower()
    suggestions = []
    for cand in candidates:
        # 精确匹配
        if cand == query_lower:
            continue
        # 包含匹配
        if query_lower in cand or cand in query_lower:
            suggestions.append(cand)
        # 字符重叠匹配
        elif len(query_lower) >= 2 and len(cand) >= 2:
            overlap = sum(1 for c in query_lower if c in cand)
            if overlap / max(len(query_lower), len(cand)) > 0.5:
                suggestions.append(cand)

    # 去重并限制数量
    seen = set()
    unique = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:max_suggestions]


def _highlight_content(content: str, query: str) -> str:
    """在内容中标记匹配关键词"""
    if not query or not content:
        return content
    keywords = query.lower().split()
    highlighted = content
    for kw in keywords:
        if len(kw) >= 2 and kw in highlighted.lower():
            import re

            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            highlighted = pattern.sub(f"**{kw}**", highlighted)
    return highlighted


def _drawer_to_dict(drawer: Drawer, score: float = 0.0, vec_score: float = 0.0, query: str = "") -> dict:
    """将 Drawer 转换为字典（自动解密 + 高亮）"""
    content = drawer.content
    if content and content.startswith("gAAAAAB"):
        try:
            from pangu.memory.encryption import decrypt

            content = decrypt(content)
        except Exception:
            pass
    highlighted = _highlight_content(content, query) if query else content
    return {
        "id": drawer.id,
        "content": content,
        "highlighted": highlighted,
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
        "recall_success": 1.08,  # 召回成功 +8%
        "recall_miss": 0.92,  # 召回失败 -8%
        "vote_up": 1.05,  # 投票好评 +5%
        "vote_down": 0.95,  # 投票差评 -5%
        "verified": 1.15,  # 验证通过 +15%
    }
    multi = SIGNAL_MULTIPLIERS.get(signal)
    if multi is None:
        return {"error": f"unknown signal: {signal}"}

    if drawers is None:
        from pangu.core.config import PanguConfig

        # P0-0（B4）：读**权威记忆路径**（v2），此前硬编码 v1 palace/drawers.json，
        # 导致反馈永远作用在空库上（读不到真实记忆）。
        cfg = PanguConfig.load().authoritative_memory_config()
        drawers = [Drawer.from_dict(d) for d in PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)]

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

    # P1-3 毕业通路闭合：反馈更新后重新评估四问门禁
    # 如果之前是 pending_review，现在有了正向反馈，可能可以毕业
    if target.metadata.get("admission") == "pending_review":
        has_source = bool(target.source_file) or bool(target.metadata.get("source_session"))
        has_positive = target.metadata.get("last_feedback") in ("recall_success", "verified")
        if has_source and has_positive:
            target.metadata["admission"] = "graduated"
            if target.metadata.get("visibility", "private") != "public":
                target.metadata["visibility"] = "public"
                target.metadata["graduated_at"] = datetime.now().isoformat()

    # 保存回**权威路径**（与上面读取同源）。
    #
    # P0-0（B4）：这里此前是 `Path(cfg.palace_path) / "drawers.json"`（v1）
    # 且外面包着 `except Exception: pass`。两个缺陷叠加造成**生产污染**：
    # 调用方传入 `drawers=[...]` 时，函数会无条件把**整个列表**写进 v1 生产库
    # —— 实测测试数据 `fb_min` 就是这样落进 `~/.pangu/palace/drawers.json` 的。
    #
    # F1/F3（子集覆盖全集）：即使路径修对了，**"把调用方传入的列表当全量写回"
    # 本身就是错的**。本函数的语义是"调整某条记忆的重要性"，不是"用给定列表
    # 替换整个库"。测试里 `drawers=[drawer]`（仅 1 条）因此会把权威库清成 1 条
    # —— 这正是 P0-0 事故中 v2 被清空的**直接机制**（402 字节的 fb_min）。
    # 修法（2026-09-20 二次收紧）：以**磁盘全量**为基底，只把**本次真正改过的 id**
    # 合并回去。此前是"把调用方列表里出现的每个 id 都覆盖"——调用方列表通常是
    # 搜索前加载的旧快照，会把并发写者（衰减/巩固/另一请求）的改动整体回滚。
    # 实测：并发把 B 的 importance 改成 5.0 后，本函数用旧快照把它退回 1.0。
    try:
        from pangu.core.config import PanguConfig
        from pangu.memory.layers import drawers_io_lock

        cfg = PanguConfig.load().authoritative_memory_config()
        drawers_file = cfg.authoritative_drawers_path

        with drawers_io_lock():
            # 空写保护：内存里是空列表时绝不覆盖磁盘（同 MemoryStack 的守卫语义）
            if not drawers and PanguConfig.load_drawers_nonempty(drawers_file):
                logger.warning(f"importance_feedback({drawer_id}): 内存列表为空但磁盘有记录，已跳过落盘（防止空库误写）")
                return {"error": "refused to overwrite non-empty store with empty list"}

            disk_items = PanguConfig.load_drawers_nonempty(drawers_file)
            if not disk_items:
                logger.warning(f"importance_feedback({drawer_id}): 磁盘为空，已跳过落盘（防止清库）")
                return {"error": "refused to write empty store"}

            # 只对目标 id 做替换，其余记录一律保留磁盘现值
            touched = {d.id: d.to_dict() for d in drawers}
            merged: list = []
            replaced = False
            for item in disk_items:
                _id = item.get("id")
                if _id in touched:
                    merged.append(touched[_id])
                    replaced = True
                else:
                    merged.append(item)
            if not replaced:
                logger.warning(f"importance_feedback({drawer_id}): 磁盘上未找到该 id，已跳过落盘")
                return {"error": "target id not found on disk", "id": drawer_id}

            tmp_file = drawers_file.with_suffix(".json.tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, drawers_file)
    except Exception as e:
        # 不再静默吞掉：落盘失败必须让调用方看见（此前 `pass` 掩盖了污染与失败）
        logger.error(f"importance_feedback({drawer_id}): 保存失败: {e}")
        return {"error": f"save failed: {e}", "id": drawer_id, "signal": signal}

    clear_recall_cache()

    return {
        "id": drawer_id,
        "signal": signal,
        "old_importance": round(old_imp, 3),
        "new_importance": round(target.importance, 3),
    }


def record_recall_hits(hit_ids: list[str], drawers: list[Drawer] | None = None) -> dict:
    """批量记录「召回命中」= recall_success 验证信号（2026-09-20 新增）。

    为什么需要：毕业准入门 Q4 的验证信号（last_feedback=recall_success/verified）
    此前只有 MCP 工具 pangu_importance_feedback 一个入口 —— MCP 客户端下线后反馈
    永远无法产生，pending_review 只进不出（实测积压 76 条无人毕业）。搜索命中本身
    就是「成功召回」，由盘古自己记录，不再依赖调用方上报。

    落盘语义与 importance_feedback 一致：以磁盘全量为基础，**只回写命中的 id**；
    绝不用调用方传入的旧快照覆盖其它记录（那会把并发写者的改动整体回滚，
    实测把并发改成的 importance=5.0 退回 1.0）。
    """
    if not hit_ids:
        return {"recorded": 0}

    hit_set = set(hit_ids)
    now = datetime.now().isoformat()

    # 磁盘全量为基底：命中项从磁盘现值上改，未命中的记录一律不动。
    from pangu.core.config import PanguConfig
    from pangu.memory.layers import drawers_io_lock

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers_file = cfg.authoritative_drawers_path

    with drawers_io_lock():
        disk_items = PanguConfig.load_drawers_nonempty(drawers_file)
        if not disk_items:
            return {"recorded": 0, "error": "refused to write empty store"}

        recorded = 0
        merged: list = []
        for item in disk_items:
            _id = item.get("id")
            if _id not in hit_set:
                merged.append(item)
                continue
            target = Drawer.from_dict(item)
            target.metadata = dict(target.metadata or {})
            recorded += 1
            target.importance = max(0.5, min(5.0, target.importance * 1.08))
            target.metadata["last_feedback"] = "recall_success"
            target.metadata["feedback_at"] = now
            # 毕业通路闭合：与 importance_feedback 相同的复判逻辑
            if target.metadata.get("admission") == "pending_review":
                has_source = bool(target.source_file) or bool(target.metadata.get("source_session"))
                if has_source:
                    target.metadata["admission"] = "graduated"
                    if target.metadata.get("visibility", "private") != "public":
                        target.metadata["visibility"] = "public"
                        target.metadata["graduated_at"] = now
            merged.append(target.to_dict())

        if not recorded:
            return {"recorded": 0}

        try:
            tmp_file = drawers_file.with_suffix(".json.tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, drawers_file)
        except Exception as e:
            logger.error(f"record_recall_hits: 保存失败: {e}")
            return {"recorded": recorded, "error": f"save failed: {e}"}

    clear_recall_cache()
    return {"recorded": recorded}


def clear_recall_cache():
    """清除召回缓存"""
    _recall_cache.clear()
    logger.debug("Recall cache cleared")
