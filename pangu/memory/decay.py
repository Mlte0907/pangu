"""盘古 — 增强衰减引擎（从伏羲 v1.5.6 移植，适配盘古数据模型）

在盘古现有 consolidation.py 的基础上，增加伏羲的精细衰减特性：
1. 夜间衰减因子（模拟睡眠中的记忆巩固）
2. 批量处理（避免一次性加载所有记忆）
3. 清除候选（低于阈值的记忆标记为可清除）
4. 艾宾浩斯衰减曲线 v2（含重要性和时间保护）
"""

import logging
import math
from datetime import datetime

from pangu.core.palace import Drawer

logger = logging.getLogger("pangu.memory.decay")


def decay_batch(
    drawers: list[Drawer],
    min_idle_hours: float = 0.5,
    decay_base: float = 0.95,
    decay_floor: float = 0.15,
    touch_boost_short: float = 1.35,
    touch_boost_long: float = 1.06,
    night_decay_factor: float = 1.2,
    dry_run: bool = False,
) -> dict:
    """批量衰减处理。

    Args:
        drawers: 记忆列表
        min_idle_hours: 最小空闲时间（小时），低于此时间不衰减
        decay_base: 基础衰减率（每周）
        decay_floor: 衰减底限
        touch_boost_short: 短期增益（24h内）
        touch_boost_long: 长期保护（30天后）
        night_decay_factor: 夜间衰减因子
        dry_run: 是否仅模拟

    Returns:
        衰减统计
    """
    now = datetime.now()
    decayed = 0
    strengthened = 0
    unchanged = 0
    purge_candidates = 0

    for d in drawers:
        new_score, action = _calculate_decay_v2(
            current_score=d.metadata.get("decay_score", 1.0),
            importance=d.importance / 5.0,  # 标准化到 0-1
            updated_at=d.created_at,
            # 增量基准：上次衰减时刻（没有则回退创建时间）—— 幂等
            basis_at=d.metadata.get("decay_updated_at"),
            last_accessed=d.metadata.get("last_accessed"),
            now=now,
            decay_base=decay_base,
            decay_floor=decay_floor,
            touch_boost_short=touch_boost_short,
            touch_boost_long=touch_boost_long,
            night_decay_factor=night_decay_factor,
            min_idle_hours=min_idle_hours,
        )

        if new_score < decay_floor:
            purge_candidates += 1

        if abs(new_score - d.metadata.get("decay_score", 1.0)) > 0.001:
            # ⚠ 必须先取旧值再写：此前先写 `decay_score = new_score`，随后
            # `if new_score > d.metadata.get("decay_score", 1.0)` 变成"新值 > 自身"
            # 恒为 False，strengthened 永远是 0、所有变化都算 decayed（实测
            # monkeypatch 让 new=0.9 > old=0.5 仍得到 strengthened=0）。
            old_score = d.metadata.get("decay_score", 1.0)
            if not dry_run:
                d.metadata["decay_score"] = new_score
                d.metadata["decay_updated_at"] = now.isoformat()
            if new_score > old_score:
                strengthened += 1
            else:
                decayed += 1
        else:
            unchanged += 1

    stats = {
        "total": len(drawers),
        "decayed": decayed,
        "strengthened": strengthened,
        "unchanged": unchanged,
        "purge_candidates": purge_candidates,
        "dry_run": dry_run,
    }

    if dry_run:
        logger.info(f"Decay dry-run: {stats}")
    else:
        logger.info(f"Decay: {decayed} down, {strengthened} up, {purge_candidates} below floor")

    return stats


def _calculate_decay_v2(
    current_score: float,
    importance: float,
    updated_at: str,
    now: datetime,
    decay_base: float = 0.95,
    decay_floor: float = 0.15,
    touch_boost_short: float = 1.35,
    touch_boost_long: float = 1.06,
    night_decay_factor: float = 1.2,
    min_idle_hours: float = 0.5,
    basis_at: str | None = None,
    last_accessed: str | None = None,
) -> tuple:
    """计算衰减分数 v2 — 含夜间因子和重要性保护。

    修复（2026-09-19）：基础衰减改为**按时间差增量**（basis_at = 上次衰减时刻，
    首次回退创建时间）。此前 `base_decay` 用距创建的总年龄、又乘在 current_score
    上 —— 每次跑都重复应用同一段年龄的衰减（不幂等）：30 天记忆单次因子≈0.81，
    跑 3 次≈0.53，实测 171 条里 129 条（75%）已被打到 floor 0.15。
    `decay_updated_at` 一直只写不读，正是这里该读的"上次衰减时刻"。

    其余因子（重要性/夜间/触碰保护）保持原语义：idle_hours 仍指"距创建"的年龄。
    """
    try:
        updated_dt = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return current_score, "unchanged"

    idle_hours = (now - updated_dt).total_seconds() / 3600

    # 增量基准：上次衰减时刻（没有则=创建时间，首次衰减用全年龄）
    basis_raw = basis_at or updated_at
    try:
        basis_dt = datetime.fromisoformat(basis_raw)
    except (ValueError, TypeError):
        basis_dt = updated_dt
    elapsed_hours = max(0.0, (now - basis_dt).total_seconds() / 3600)

    # 低于最小空闲时间，不衰减（对"距上次衰减"判定 —— 防止频繁重跑叠加）
    if elapsed_hours < min_idle_hours:
        return current_score, "unchanged"

    # 基础衰减（每周衰减率）：只对"距上次衰减的新增时长"生效 → 幂等
    base_decay = decay_base ** (elapsed_hours / 168)

    # 重要性因子：高重要性记忆衰减更慢
    importance_factor = 1.0 - (importance * 0.4)

    # 夜间因子：凌晨3-5点衰减最强（模拟睡眠巩固）
    hour = now.hour + now.minute / 60.0
    night_factor = 1.0 - (night_decay_factor - 1.0) * math.exp(-0.5 * ((hour - 5.0) / 1.5) ** 2)

    # 时间保护因子（2026-09-19 接真实访问）：此前 idle_hours 恒为"距创建"的年龄，
    # touch_boost 名为访问加固实为年龄加成 —— 天天被搜的记忆照样衰减。现在优先用
    # metadata.last_accessed（record_access 在搜索命中时写），没有才回退创建时间。
    touch_hours = idle_hours
    if last_accessed:
        try:
            la = datetime.fromisoformat(last_accessed)
            touch_hours = max(0.0, (now - la).total_seconds() / 3600)
        except (ValueError, TypeError):
            pass
    if touch_hours < 24:
        touch_factor = touch_boost_short
    elif touch_hours > 720:  # 30天
        touch_factor = touch_boost_long
    else:
        touch_factor = 1.0

    new_score = current_score * base_decay * importance_factor * night_factor * touch_factor
    new_score = max(decay_floor, min(1.0, new_score))

    if new_score > current_score:
        action = "strengthened"
    elif new_score < current_score:
        action = "decayed"
    else:
        action = "unchanged"

    return round(new_score, 6), action


def get_purge_candidates(
    drawers: list[Drawer],
    decay_floor: float = 0.15,
) -> list[Drawer]:
    """获取低于衰减底限的记忆（清除候选）"""
    return [d for d in drawers if d.metadata.get("decay_score", 1.0) < decay_floor]


def purge_below_floor(
    drawers: list[Drawer],
    decay_floor: float = 0.15,
    dry_run: bool = True,
) -> dict:
    """清除低于衰减底限的记忆"""
    candidates = get_purge_candidates(drawers, decay_floor)
    purged = 0

    if not dry_run:
        for d in candidates:
            d.metadata["archived"] = True
            d.metadata["purged_at"] = datetime.now().isoformat()
            purged += 1

    logger.info(f"Purge: {len(candidates)} candidates, dry_run={dry_run}")
    return {
        "purged": purged if not dry_run else 0,
        "candidates": len(candidates),
        "dry_run": dry_run,
        "ids": [d.id for d in candidates],
    }


def get_decay_stats(drawers: list[Drawer]) -> dict:
    """获取衰减统计"""
    if not drawers:
        return {"total": 0}

    scores = [d.metadata.get("decay_score", 1.0) for d in drawers]
    avg_score = sum(scores) / len(scores) if scores else 0
    below_floor = sum(1 for s in scores if s < 0.15)
    healthy = sum(1 for s in scores if s > 0.7)

    return {
        "total": len(drawers),
        "avg_decay_score": round(avg_score, 4),
        "below_floor": below_floor,
        "healthy": healthy,
        "health_pct": round(healthy / len(drawers) * 100, 1) if drawers else 0,
    }
