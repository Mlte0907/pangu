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
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from pangu.core.palace import Drawer
from pangu.memory.embedding import get_embedding_service

logger = logging.getLogger("pangu.memory.ingestion")

# Constants
IMPORTANCE_SCALE = 5.0  # 盘古 importance 使用 0-5 范围
SIMILARITY_THRESHOLD = 0.92  # 语义相似度阈值（精确重复）
SUPERSEDE_THRESHOLD = 0.65  # 替代阈值：同一主题但新内容更丰富时放行（旧的标记替代）
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


def _get_default_storage():
    """根据全局权威 config 拿到默认 JsonDrawerStorage。"""

    try:
        from pathlib import Path

        from pangu.core.config import PanguConfig
        from pangu.memory.drawer_storage import JsonDrawerStorage

        cfg = PanguConfig.load().authoritative_memory_config()
        path = Path(cfg.palace_path) / "drawers.json"
        return JsonDrawerStorage(str(path))
    except Exception as e:
        return None


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
) -> tuple[Drawer | None, str | None, str | None]:
    """去重与相似度检测。

    返回三元组 (dup_drawer, fused_id, supersede_id)：
      - dup_drawer: 完全重复的旧 drawer → remember() 拒绝写入、给旧的加一把分
      - fused_id: 旧 drawer 被融合改写过（历史行为，现已弃用，保留兼容）
      - supersede_id: 语义相似但新内容更丰富 → remember() 正常写入新记忆，
                       旧 drawer 应标记为"已被替代"（不修改旧内容）

    2026-09-20 重写语义相似分支：旧版"融合"会直接把旧记忆内容覆盖掉，
    导致用户丢失原始记录（例如：旧记忆是猜测、新记忆拿证据纠正，融合后
    猜测的内容就没了）。新逻辑：新内容更丰富则放行写入并建立替代关系，
    旧记忆原文不被改动，通过 metadata.superseded_by 保留完整历史。
    """
    # 1) 精确内容重复 → 拒绝写入
    for d in existing_drawers:
        if d.content == raw_text and d.wing == wing:
            logger.debug(f"Exact duplicate found: {d.id[:8]}")
            return d, None, None

    # 2) 语义相似度检测
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
                if score > SUPERSEDE_THRESHOLD and score > best_score:
                    best_score = score
                    best_drawer = d
            except Exception:
                continue

        if best_drawer is not None:
            # 精确内容重复
            if best_drawer.content == raw_text:
                logger.debug(f"Exact duplicate found: {best_drawer.id[:8]}")
                return best_drawer, None, None

            # 语义相似 → 判断谁更丰富
            # 不再融合（不改写旧内容）。新内容明显更丰富时放行写入，旧的标记为
            # "已被替代"；否则视为重复，拒绝写入。
            #
            # 丰富度计算：信息量 = 内容长度 × (1 + 0.5 × 新增关键词比例)。
            # 例如：旧记忆是猜测（50字），新记忆拿证据纠正（120字 + 30%新词）
            # → 旧=50，新≈120×1.15=138 → 新是旧的 2.76 倍 → 放行。
            old_words = set(best_drawer.content.lower().split()) if best_drawer.content else set()
            new_words = set(raw_text.lower().split()) if raw_text else set()
            new_ratio = len(new_words - old_words) / max(len(old_words), 1) if old_words else 1.0
            informativeness_new = len(raw_text) * (1 + 0.5 * new_ratio)
            informativeness_old = len(best_drawer.content) if best_drawer.content else 1

            if informativeness_new > informativeness_old * 1.3:
                # 新内容明显更丰富 → 放行写入 + 标记旧的为"已替代"
                # 不返回 dup/fused，走正常创建流程；调用方在创建后建立 supersede 关系
                logger.info(
                    f"Memory supersede candidate: score={best_score:.3f}, "
                    f"old={best_drawer.id[:8]} new is {informativeness_new / informativeness_old:.1f}x richer"
                )
                return None, None, best_drawer.id
            else:
                # 内容差不多 → 重复，拒绝写入
                logger.info(
                    f"Memory duplicate rejected: score={best_score:.3f}, "
                    f"not significantly richer (new={informativeness_new:.0f} vs old={informativeness_old:.0f})"
                )
                return best_drawer, None, None

    # 3) 文本相似度降级去重
    if len(raw_text) >= MIN_TEXT_LENGTH_FOR_DEDUP:
        for d in existing_drawers:
            if d.wing != wing or len(d.content) < MIN_CONTENT_LENGTH:
                continue
            if abs(len(raw_text) - len(d.content)) > MAX_LENGTH_DIFF_FOR_DEDUP:
                continue
            overlap = sum(1 for a, b in zip(raw_text, d.content, strict=False) if a == b)
            len_norm = max(len(raw_text), len(d.content))
            if overlap / len_norm > TEXT_OVERLAP_THRESHOLD:
                return d, None, None

    return None, None, None


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


def _persist_supersede_update(storage, old_id: str, modified_drawer: Drawer) -> bool:
    """安全地将 modified_drawer 的更新落盘到 storage（按 id 替换）

    背景：P0-1 需把"被取代"标记写回旧 drawer 的 metadata 并落盘。
    MemoryStack 缺少 update_drawer 接口，且 t2 inScope 不含 layers.py，
    故采用 storage 直写路径，**必须**保留以下守卫避免破坏空写保护：

    1. storage 为 None 直接放弃（调用方没要求持久化）
    2. storage.last_load_ok=False 放弃（解析失败 ⇒ 假空 ⇒ 不能写回）
    3. 加载结果为空列表放弃（与 layers.py 的 _save_drawers 同义守卫）
    4. 找不到目标 id 放弃（不是错误，仅"无操作"）

    Args:
        storage: DrawerStorage 实例（JsonDrawerStorage 或 SqliteDrawerStorage）
        old_id: 被更新的 drawer id
        modified_drawer: 已带 superseded_by/superseded_at/memory_status 标记的新对象

    Returns:
        bool — True 表示真的写入了磁盘，False 表示被守卫拦截或异常
    """
    if storage is None:
        return False
    try:
        all_drawers = storage.load()
    except Exception as e:
        logger.debug(f"storage load skipped for supersede update of {old_id[:8]}: {e}")
        return False
    if not getattr(storage, "last_load_ok", True):
        logger.debug(f"storage load failed (last_load_ok=False), skip supersede update for {old_id[:8]}")
        return False
    if not all_drawers:
        logger.debug(f"storage load returned empty list, skip supersede update for {old_id[:8]}")
        return False
    found = False
    for i, d in enumerate(all_drawers):
        if d.id == old_id:
            all_drawers[i] = modified_drawer
            found = True
            break
    if not found:
        logger.debug(f"old drawer {old_id[:8]} not found in storage, skip")
        return False
    try:
        storage.save(all_drawers)
    except Exception as e:
        logger.warning(f"storage.save failed for supersede update of {old_id[:8]}: {e}")
        return False
    # 同步清掉 search_cache：旧 drawer 的 metadata 变了，旧查询结果（缓存里把旧
    # drawer 当"未取代"返回）必须失效。这是 P0-1 范围内可接受的"全表清"。
    try:
        from pangu.memory.search_cache import get_search_cache

        get_search_cache().clear()
    except Exception:
        pass
    return True


# ── 冲突 supersede 的 LLM 复核（方案 A，2026-09-27）──────────────────────
#
# 原行为：字词法一旦给出候选就**同步**把旧记忆标 superseded 移出搜索。上云实测
# 新记忆与最近 20 条能碰出 52 个候选（conf=1.0），而 CONFLICT_MAX_REPORT=3
# ⇒ 几乎每写一条记忆就静默下架 3 条旧的。
#
# 现行为：候选只登记不落锤，交给**后台线程**跑 LLM 复核，确认矛盾才下架。
# 之所以必须后台 —— 实测该 LLM 端点 avg 41.2s（2~120s），而 remember() 是同步
# 写入管道，塞进去 = 每存一条记忆卡半分钟。
#
# 三条铁律：写入零延迟 / 下架必过 LLM / LLM 出任何问题一律**不下架**（fail-open）。
LLM_REVIEW_ENABLED = True  # 一键关掉 LLM 复核 ⇒ 退化为「只检测不下架」
LLM_REVIEW_INLINE = False  # 测试专用：True = 同步跑复核（不起线程），让用例无需 sleep
LLM_REVIEW_MAX_PAIRS = CONFLICT_MAX_REPORT  # 每次写入最多复核几对（控制延迟与费用）
LLM_REVIEW_INPUT_CHARS = 2000  # 单条送入 LLM 的正文截断长度（记忆动辄数千字）
LLM_REVIEW_MAX_RETRIES = 1  # 解析失败时的额外重试次数（见 _llm_confirm_conflict）

_SUPERSEDE_LOCK = threading.Lock()  # 串行化「改旧 drawer + 落盘」，避免并发写坏库

_REVIEW_PROMPT = """你是记忆冲突审计员。判断两条记忆是否构成**同一事实的相互矛盾**。

严格标准：
- 只有当两条在描述**同一个对象/属性/结论**且给出**互斥取值或相反结论**才算冲突。
- 下列一律答 no：
  a) 主题不同、各说各事；
  b) 不同对象各自的取值（不同服务的端口、不同测试套件的通过数、不同字段命名）；
  c) 同一对象的先后版本/改前改后/统计口径差异；
  d) 一条是另一条的补充、细化或不同侧面。
- 拿不准时答 no。
只输出 JSON：{{"conflicts": true/false, "reason": "不超过30字理由"}}

【新记忆】
{new}

【已有记忆】
{old}"""


def _make_llm_engine():
    """构造 LLM 引擎（单独抽出来便于测试注入假引擎）。"""
    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    return LLMEngine(PanguConfig.load().authoritative_memory_config())


def _plain_for_review(text: str) -> str:
    """送 LLM 前解密 —— 写入管道里的 content 是 Fernet 密文。

    2026-09-27 端到端实测抓到：不先解密的话，LLM 收到的是
    ``gAAAAAB…``，直接回「两条记忆为加密字符串，无法解析」⇒ 恒判 no ⇒
    **永远不下架，功能名存实亡**（虽然 fail-open 是安全的，但那样就谈不上"把关"）。

    用三态 `decrypt`：明文原样、密文解开、解不开给占位符（后者仍会让 LLM 判
    「看不懂」→ fail-open，与「旧密钥数据本就无法复核」的现实一致）。
    """
    if not text:
        return ""
    try:
        from pangu.memory.encryption import decrypt

        return decrypt(text)
    except Exception:  # noqa: BLE001 — 解密失败就原样送，交给 LLM 的 fail-open 兜底
        return text


def _ask_review_llm(prompt: str) -> tuple[bool, str, bool]:
    """单次向 LLM 提问并解析。

    Returns:
        ``(是否矛盾, 理由, 是否解析成功)`` —— 第三个值是关键：它区分
        「模型判了但格式坏」与「模型压根没法判断」，只有前者值得重试。
    """
    import asyncio
    import json as _json

    engine = _make_llm_engine()
    reply = asyncio.run(engine.chat([{"role": "user", "content": prompt}]))
    text = (getattr(reply, "content", None) or str(reply or "")).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return False, "LLM 未返回 JSON", False
    data = _json.loads(text[start : end + 1])   # JSON 非法会抛，交给上层当异常
    if not isinstance(data, dict) or "conflicts" not in data:
        return False, "LLM 返回缺少 conflicts 字段", False
    return bool(data.get("conflicts")), str(data.get("reason") or "")[:80], True


def _llm_confirm_conflict(new_content: str, old_content: str) -> tuple[bool, str]:
    """让 LLM 判断这对是否**真的**矛盾。

    Returns:
        ``(确认冲突, 理由)``。**任何异常一律返回 (False, ...)** —— fail-open：
    误下架的代价（记忆静默消失、用户不知情）远高于多留一条重复记忆。

    两条路径分开处理（2026-09-28 三模型盲测发现）：
    * **格式解析失败 → 重试 `LLM_REVIEW_MAX_RETRIES` 次**。盲测 135 次作答里有
      **5 次（3.7%）**返回的不是合法 JSON，当时直接 fail-open 判「不矛盾」。其中
      两题表面是「三票一致」、实际 2/3 票是降级票 —— **靠运气答对**。若某道真冲突
      题撞上 2 次降级，就会漏判放走重复记忆。重试是低成本的止血。
    * **调用异常（网络/超时/配置）→ 不重试**。这类通常是系统性的，重试只是白等
      一次 41 秒，仍按 fail-open 返回。

    ⚠ 不要用 ``str.format()`` 填 prompt：模板里的 JSON 示例 ``{"conflicts": ...}``
    会被当成格式化占位符抛 ``KeyError: '"conflicts"'``（2026-09-27 实测踩过）。
    """
    new_content = _plain_for_review(new_content)
    old_content = _plain_for_review(old_content)
    prompt = _REVIEW_PROMPT.replace("{new}", (new_content or "")[:LLM_REVIEW_INPUT_CHARS]).replace(
        "{old}", (old_content or "")[:LLM_REVIEW_INPUT_CHARS]
    )

    last_reason = ""
    for attempt in range(LLM_REVIEW_MAX_RETRIES + 1):
        try:
            ok, reason, parsed = _ask_review_llm(prompt)
        except Exception as e:  # noqa: BLE001 — fail-open 是这里的硬要求
            logger.warning(f"冲突 LLM 复核失败（按不冲突处理，不下架）: {type(e).__name__}: {e}")
            return False, f"复核失败: {type(e).__name__}"
        if parsed:
            if attempt:
                logger.info(f"冲突复核第 {attempt + 1} 次才拿到合法 JSON（已重试 {attempt} 次）")
            return ok, reason
        last_reason = reason
        if attempt < LLM_REVIEW_MAX_RETRIES:
            logger.warning(
                f"冲突复核第 {attempt + 1} 次输出无法解析，重试: {reason}"
            )

    return False, f"{last_reason}（已重试 {LLM_REVIEW_MAX_RETRIES} 次仍失败，按不冲突处理）"


def _apply_supersede(
    confirmed: list[tuple[str, str]],
    drawer: Drawer,
    existing_drawers: list[Drawer],
    item_id: str,
    storage=None,
) -> None:
    """执行已经被 LLM 确认的下架（原 `_detect_conflicts` 的同步执行段，抽出来复用）。

    Args:
        confirmed: ``[(被取代的旧 id, LLM 给出的理由), ...]``
    """
    now = datetime.now().isoformat()
    new_supersedes: list[str] = []
    for old_id, reason in confirmed:
        new_supersedes.append(old_id)
        for d in existing_drawers:
            if d.id == old_id:
                superseded_by = d.metadata.get("superseded_by", []) if d.metadata else []
                if not isinstance(superseded_by, list):
                    superseded_by = []
                if item_id not in superseded_by:
                    superseded_by.append(item_id)
                if d.metadata is None:
                    d.metadata = {}
                d.metadata["superseded_by"] = superseded_by
                d.metadata["superseded_at"] = now
                d.metadata["memory_status"] = "superseded"
                try:
                    _persist_supersede_update(storage, old_id, d)
                except Exception as e:
                    logger.warning(f"update old drawer failed for {old_id[:8]}: {e}")
                # ⚠ 每次真下架都留痕：静默下架正是这次事故最难查的地方
                logger.warning(
                    f"Supersede applied（LLM 复核确认）: {old_id[:8]} 被 {item_id[:8]} 取代"
                    f" —— LLM 理由: {reason}"
                )
                break

    if drawer.metadata is None:
        drawer.metadata = {}
    drawer.metadata["supersedes"] = new_supersedes
    drawer.metadata.pop("conflict_candidates", None)  # 候选已被消化

    # versioning 记录（与旧行为一致，供 pangu_get_supersede_chain 追链）
    try:
        from pangu.memory.versioning import get_version_control

        vc = get_version_control()
        for old_id in new_supersedes:
            try:
                vc.record_version(
                    memory_id=old_id,
                    content=f"superseded by {item_id}",
                    change_type="superseded",
                    metadata={"by": item_id, "at": now},
                )
            except Exception as e:
                logger.debug(f"record_version superseded skipped for {old_id[:8]}: {e}")
        try:
            vc.record_version(
                memory_id=item_id,
                content=drawer.content,
                change_type="supersede",
                metadata={"supersedes": new_supersedes, "at": now},
            )
        except Exception as e:
            logger.debug(f"record_version supersede skipped for {item_id[:8]}: {e}")
    except Exception as e:
        logger.debug(f"Version recording skipped: {e}")

    logger.info(f"Supersede recorded for {item_id[:8]}: replaces {len(new_supersedes)} memories")


def _review_conflicts_background(
    conflicts: list,
    drawer: Drawer,
    existing_drawers: list[Drawer],
    item_id: str,
    storage=None,
    delay: float = 0.3,
) -> None:
    """后台任务：逐对跑 LLM 复核，**只有确认矛盾的才下架**。

    Args:
        delay: 启动前的等待秒数。后台路径给 0.3s —— `remember()` 返回后由 handler
            才真正落盘新 drawer，立刻回填会扑空（`_persist_supersede_update` 找不到
            id 会静默跳过，不算错）；同步路径给 0（测试要的是确定性，不是时序仿真）。

    设计要点：全程包 try —— 后台线程的异常若逃逸只会打一条 stderr，问题照样静默。
    """
    try:
        if delay:
            time.sleep(delay)
        by_id = {d.id: d for d in existing_drawers}
        confirmed: list[tuple[str, str]] = []
        for c in conflicts[:LLM_REVIEW_MAX_PAIRS]:
            old_id = c.memory_a if c.memory_b == item_id else c.memory_b
            old = by_id.get(old_id)
            if old is None:
                continue
            try:
                ok, reason = _llm_confirm_conflict(drawer.content, old.content)
            except Exception as e:  # 双保险：stub/实现层异常也 fail-open
                ok, reason = False, f"复核异常: {type(e).__name__}"
            if ok:
                confirmed.append((old_id, reason))
            else:
                logger.info(
                    f"冲突候选未通过 LLM 复核，不下架: {item_id[:8]} vs {old_id[:8]} —— {reason}"
                )

        if not confirmed:
            logger.info(f"冲突复核结束：{len(conflicts)} 个候选全部未确认，0 条下架")
            return

        with _SUPERSEDE_LOCK:
            _apply_supersede(confirmed, drawer, existing_drawers, item_id, storage)
            # 回填已落盘的新 drawer（未落盘则跳过，_persist_supersede_update 自带守卫）
            try:
                _persist_supersede_update(storage, item_id, drawer)
            except Exception as e:
                logger.debug(f"回填新 drawer supersedes 失败: {e}")
    except Exception as e:
        logger.warning(f"conflict review task failed（不影响本次写入）: {type(e).__name__}: {e}")


def _detect_conflicts(
    drawer: Drawer,
    existing_drawers: list[Drawer],
    item_id: str,
    storage=None,
) -> None:
    """自动冲突检测 → 登记候选 → **后台 LLM 复核** → 确认才下架（P0-1 + 方案 A）

    2026-09-27 改：原来在这里**同步**把候选对应的旧记忆标 superseded 移出搜索。
    上云实测新记忆与最近 20 条能碰出 52 个候选（conf=1.0），而
    `CONFLICT_MAX_REPORT=3` ⇒ 几乎每写一条记忆就静默下架 3 条旧的。事故形态是
    用户写完记忆才发现某条搜不到了，且无人告知。

    现在的流程：

    1. 检出候选（字词法 + 相似度闸门，见 conflict.py）；
    2. 候选只写进新 drawer 的 `metadata.conflict_candidates`，**不下架**；
    3. 提交后台线程跑 LLM 复核（实测 avg 41.2s，同步等会把写入卡半分钟）；
    4. 只有 LLM 明确判「是同一事实的矛盾」才执行下架 ——
       `_apply_supersede` 写 `superseded_by` / `superseded_at` /
       `memory_status="superseded"`、落盘、记 versioning；
    5. **LLM 出任何问题一律不下架**（fail-open）：误下架的代价是记忆静默消失，
       远高于多留一条重复。

    两个开关：
        * `LLM_REVIEW_ENABLED=False` ⇒ 只登记不下架（一键回退到更保守的行为）；
        * `LLM_REVIEW_INLINE=True` ⇒ 同步跑复核、不起线程（**仅测试用**，
          让用例拿到确定性而不是时序仿真）。

    Returns:
        提交的后台线程；无候选 / 复核关闭 / 同步模式 / 出异常时返回 ``None``。
        调用方 `remember()` 不关心返回值。

    签名变更（向后兼容）：
        新增 storage=None。旧调用方 _detect_conflicts(d, ex, item) 不传 storage
        时，仅更新内存中的 drawer.metadata，不落盘；落盘由调用方（如 stack.add_drawer）
        通过 storage 完成。生产代码路径不感知本函数。
    """
    if not (existing_drawers and len(existing_drawers) >= CONFLICT_MIN_EXISTING):
        return None
    try:
        from pangu.memory.conflict import ConflictDetector

        detector = ConflictDetector()
        conflicts = detector.detect_conflicts([drawer] + existing_drawers[-CONFLICT_LOOKBACK:])
        if not conflicts:
            return None

        # ── 候选只登记，不落锤（方案 A）──────────────────────────────
        # 老行为在这里**同步**把旧记忆标 superseded 移出搜索：字词法误判一下就变成
        # 「记忆静默消失、用户不知情」。现在候选挂到新 drawer 上，交后台 LLM 复核，
        # 写入路径一行都不等（LLM 实测 avg 41.2s，同步等 = 每存一条卡半分钟）。
        candidates: list[str] = []
        for c in conflicts[:CONFLICT_MAX_REPORT]:
            old_id = c.memory_a if c.memory_b == item_id else c.memory_b
            candidates.append(old_id)

        if drawer.metadata is None:
            drawer.metadata = {}
        # 兼容旧字段：保留原 conflicts 列表（API/handler 不感知 supersede）
        drawer.metadata["conflicts"] = [
            {
                "id": c.id,
                "severity": c.severity.value,
                "with": c.memory_a if c.memory_b == item_id else c.memory_b,
            }
            for c in conflicts[:CONFLICT_MAX_REPORT]
        ]
        drawer.metadata["conflict_candidates"] = candidates

        if not LLM_REVIEW_ENABLED:
            # 一键关掉 ⇒ 退化成「只检测不下架」，比老行为安全，比新行为保守
            logger.info(
                f"检测到 {len(candidates)} 个冲突候选，LLM 复核已关闭 ⇒ 仅登记不下架"
            )
            return None

        logger.info(
            f"检测到 {len(candidates)} 个冲突候选，已提交后台 LLM 复核（写入不等待）"
        )
        if LLM_REVIEW_INLINE:
            # 测试路径：同步跑，不 sleep、不起线程 —— 用例拿到确定性而非时序仿真
            _review_conflicts_background(
                list(conflicts), drawer, existing_drawers, item_id, storage, delay=0.0
            )
            return None
        task = threading.Thread(
            target=_review_conflicts_background,
            args=(list(conflicts), drawer, existing_drawers, item_id, storage),
            name="pangu-conflict-review",
            daemon=True,
        )
        task.start()
        return task
    except Exception as e:
        logger.debug(f"Conflict detection skipped: {e}")
        return None


def _admission_gate(drawer: Drawer, existing_drawers: list[Drawer] | None, item_id: str) -> None:
    """四问准入门（不阻塞写入，只标记）—— P1-3 强化版

    四问：
    1. 重复：由 remember() 前部的 _dedup_and_fuse 处理（已在上游）
    2. 冲突：由 _detect_conflicts 处理（P0-1，已在上游）
    3. 支撑：缺来源指针 → pending_review（source_file / source_session 任一有即通过）
    4. 验证：importance_feedback 信号 → recall_success/verified = 通过；无正向信号 = pending_review

    毕业区：四问全过 → visibility="public"（全平台只读）
    所有判定不阻塞写入方。
    """
    if drawer.metadata is None:
        drawer.metadata = {}

    admission_flags = []

    # Q3 支撑检查：缺来源指针 → C 类待复盘
    # P1-3 强化：tags 不算"来源指针"（自动沉淀的记忆全带 tags，会全部放行）
    # 只检查 source_file 和 source_session
    has_source = bool(drawer.source_file) or bool(drawer.metadata.get("source_session"))
    if not has_source:
        admission_flags.append("no_source")
        drawer.metadata["admission"] = "pending_review"
        drawer.metadata["admission_reason"] = "缺来源指针（无 source_file 和 source_session）"

    # Q4 验证检查：importance_feedback 信号作为真实验证代理
    # P1-3 强化：静态 importance 阈值不是"验证过吗"
    # 检查 metadata.last_feedback 是否为正向信号（recall_success / verified）
    last_feedback = drawer.metadata.get("last_feedback", "")
    has_positive_feedback = last_feedback in ("recall_success", "verified")
    if not has_positive_feedback:
        admission_flags.append("unverified")
        if "admission" not in drawer.metadata:
            drawer.metadata["admission"] = "pending_review"
            drawer.metadata["admission_reason"] = "未被召回验证（无正向 importance_feedback）"

    # 毕业区判定：四问全过 → visibility="public"
    # P1-3：毕业区记忆全平台只读（ABAC public_resource 策略已保证 read/search 放行）
    all_passed = len(admission_flags) == 0
    if all_passed:
        drawer.metadata["admission"] = "graduated"
        # 只在当前不是 public 时才改（不降级）
        current_vis = drawer.metadata.get("visibility", "private")
        if current_vis != "public":
            drawer.metadata["visibility"] = "public"
            drawer.metadata["graduated_at"] = datetime.now().isoformat()

    # 记录准入分数（供后续仪表盘/统计使用）
    drawer.metadata["admission_score"] = {
        "has_source": has_source,
        "has_positive_feedback": has_positive_feedback,
        "last_feedback": last_feedback,
        "flags": admission_flags,
        "passed": all_passed,
    }

    if admission_flags:
        logger.debug(f"Admission gate {item_id[:8]}: flags={admission_flags}")


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
    source_session: str = "",  # P1-3：来源会话 ID（dsh/zcode/workbuddy）
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
    # 契约：importance ∈ [0.0, 1.0]（tests/test_ingestion.py 与
    # tests/test_v3_modules_g.py 都断言越界必须抛错）。调用方一律不得传 1–5
    # 旧量纲 —— handler 与插件的默认值已同步改为 0.5。
    if not isinstance(importance, (int, float)) or importance < 0.0 or importance > 1.0:
        raise ValueError(f"importance must be between 0.0 and 1.0, got {importance}")
    if confidence is None:
        confidence = 1.0
    tags = tags or []

    # 脱敏处理
    raw_text = _sanitize_text(raw_text)

    # 加密处理（可选）
    stored_text = _encrypt_text(raw_text)

    # 去重和相似度检测
    if existing_drawers:
        duplicate, fused_id, supersede_id = _dedup_and_fuse(raw_text, wing, room, existing_drawers)
        if duplicate:
            _boost_existing(duplicate)
            return duplicate.id, duplicate
        if fused_id:
            for d in existing_drawers:
                if d.id == fused_id:
                    return fused_id, d
        # supersede_id: 新记忆更丰富，正常写入；这里只记录，创建后标记旧的为"已替代"
    else:
        supersede_id = None

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

    # P1-3：来源会话 ID（供 admission_gate Q3 检查用）
    if source_session:
        drawer.metadata["source_session"] = source_session

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

    # 语义相似 → 旧记忆标记为"已替代"（不改写旧内容）
    if supersede_id and existing_drawers:
        try:
            for d in existing_drawers:
                if d.id == supersede_id:
                    superseded_by = d.metadata.get("superseded_by", []) if d.metadata else []
                    if not isinstance(superseded_by, list):
                        superseded_by = []
                    if item_id not in superseded_by:
                        superseded_by.append(item_id)
                    if d.metadata is None:
                        d.metadata = {}
                    d.metadata["superseded_by"] = superseded_by
                    d.metadata["superseded_at"] = now
                    d.metadata["memory_status"] = "superseded"
                    try:
                        _persist_supersede_update(_get_default_storage(), supersede_id, d)
                    except Exception as e:
                        logger.warning(f"supersede update failed for {supersede_id[:8]}: {e}")
                    if drawer.metadata is None:
                        drawer.metadata = {}
                    drawer.metadata["supersedes"] = [supersede_id]
                    logger.info(f"Memory superseded: {supersede_id[:8]} by {item_id[:8]}")
                    break
        except Exception as e:
            logger.debug(f"Supersede marking skipped: {e}")

    # 神经记忆编码（海马体-新皮层双系统）
    _neural_encode(drawer, item_id)

    # 自动冲突检测（含 P0-1 supersede 关系建立与旧 drawer 持久化）
    _detect_conflicts(drawer, existing_drawers, item_id, storage=_get_default_storage())

    # P0-1 缺口 3：四问准入门（不阻塞写入，只标记）
    # 1. 重复：dedup 已在 remember() 前部处理（_dedup_and_fuse）
    # 2. 冲突：_detect_conflicts 已处理（P0-1）
    # 3. 支撑：缺来源指针 → 挂起（C 类待复盘）
    # 4. 验证：importance 作代理计数
    try:
        _admission_gate(drawer, existing_drawers, item_id)
    except Exception as e:
        logger.debug(f"Admission gate skipped: {e}")

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
