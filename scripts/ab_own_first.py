"""搜索「本平台优先」改造前后的 A/B 对比（只读，不改任何数据）。

为什么要这个脚本：改造已经上线，不能靠回滚生产来取「改前」的数据。
本脚本在**同一进程、同一份数据、同一时刻**把两条路径各跑一遍：

  BEFORE = engine.search(n_results=limit)                        # 改造前：直接用引擎结果
  AFTER  = engine.search(n_results=limit*3) → 稳定分档 → 截到 limit   # 改造后

搜索池与可见性过滤完全照抄 handle_search_memories（set_tenant_scope + 同样的
tenant/public 过滤），所以两条路径的唯一差别就是「本平台优先」本身。

用法：/root/pangu/.venv/bin/python /root/ab_own_first.py
"""

import sys

sys.path.insert(0, "/root/pangu")

from pangu.core.config import PanguConfig
from pangu.memory.layers import MemoryStack, reset_tenant_scope, set_tenant_scope
from pangu.search.engine import HybridSearch

ROOM = "opencode"  # 以 opencode 平台身份检索
LIMIT = 10
OVERFETCH = 3

QUERIES = [
    "dsh 插件 MCP 接入 排查",
    "盘古 记忆 系统 部署",
    "浏览器 自动化 点击 失败",
    "记忆 检索 召回 排序",
    "pangu 图谱 实体 重复",
    "gradle 构建 失败 缓存",
]


def partition_own_first(items, owner_by_id, own_tenant):
    """A：硬分两档。"""
    if not own_tenant or not owner_by_id:
        return items
    own, other = [], []
    for it in items:
        (own if owner_by_id.get(it.get("id")) == own_tenant else other).append(it)
    return own + other


def boost_own(items, owner_by_id, own_tenant, positions=4):
    """B：位次加权 —— 本平台每条提前 N 位。

    与 A 的关键差别：改前第 1 名若属于别平台，它**留在第 1 名**；A 会把它整块挤到
    本平台那批之后。
    """
    if not own_tenant or not owner_by_id or len(items) < 2:
        return items
    tagged = []
    for i, it in enumerate(items):
        eff = i - (positions if owner_by_id.get(it.get("id")) == own_tenant else 0)
        tagged.append((eff, i, it))
    tagged.sort(key=lambda t: (t[0], t[1]))
    return [it for _, _, it in tagged]


def main():
    cfg = PanguConfig.load().authoritative_memory_config()
    token = set_tenant_scope(ROOM, "", 0)
    try:
        stack = MemoryStack(config=cfg)
        all_drawers = stack.get_drawers() or []
        # 与 handle_search_memories 完全一致的可见性过滤
        drawers = [
            d
            for d in all_drawers
            if (d.metadata or {}).get("tenant_id", "") == ROOM
            or (d.metadata or {}).get("visibility", "") == "public"
        ]
        owner_by_id = {d.id: (d.metadata or {}).get("tenant_id", "") for d in drawers}
        engine = HybridSearch(cfg)

        print(f"平台身份 room={ROOM!r} | 记忆库 {len(all_drawers)} 条 → 可见 {len(drawers)} 条")
        print(f"其中本平台 {sum(1 for v in owner_by_id.values() if v == ROOM)} 条")
        print()

        for q in QUERIES:
            before = engine.search(q, drawers, n_results=LIMIT) or []
            pool = engine.search(q, drawers, n_results=LIMIT * OVERFETCH) or []
            a_split = partition_own_first(pool, owner_by_id, ROOM)[:LIMIT]
            b_boost = boost_own(pool, owner_by_id, ROOM)[:LIMIT]

            b_ids = [x["id"][:8] for x in before]
            a_ids = [x["id"][:8] for x in a_split]
            w_ids = [x["id"][:8] for x in b_boost]

            def own_cnt(xs):
                return sum(1 for x in xs if owner_by_id.get(x["id"]) == ROOM)

            # 关键指标：改前第 1 名还在不在前 5 / 前 10 里
            top1 = b_ids[0] if b_ids else None

            def rank_of(seq, target):
                return seq.index(target) + 1 if target in seq else None

            print(f"── 查询：{q}")
            print(f"   改前(原始) 本平台 {own_cnt(before):>2}/{LIMIT} | {' '.join(b_ids)}")
            print(f"   A 分档     本平台 {own_cnt(a_split):>2}/{LIMIT} | {' '.join(a_ids)}")
            print(f"   B 加权     本平台 {own_cnt(b_boost):>2}/{LIMIT} | {' '.join(w_ids)}")
            print(
                f"   改前第1名({top1}) 的位次：  A={rank_of(a_ids, top1)}  B={rank_of(w_ids, top1)}"
                f"   （None = 掉出前{LIMIT}）"
            )
            print(f"   A 与 B 差异位次：{[i + 1 for i, (a, w) in enumerate(zip(a_ids, w_ids)) if a != w]}")
            print()

        sweep(QUERIES, engine, drawers, owner_by_id, ROOM, LIMIT, OVERFETCH)
    finally:
        reset_tenant_scope(token)


def sweep(queries, engine, drawers, owner_by_id, room, limit, overfetch):
    """扫不同提前位次，用两个指标给默认值找依据：

      keep@3 / keep@5 = 改前第 1 名仍在前 3 / 前 5 的比例（保相关性）
      own%            = 本平台条目占比（提熟悉度）

    两个指标此消彼长，取拐点。位次 0 等于「完全不干预」，可当基线。
    """
    pools = {}
    for q in queries:
        pools[q] = {
            "before": engine.search(q, drawers, n_results=limit) or [],
            "pool": engine.search(q, drawers, n_results=limit * overfetch) or [],
        }

    print()
    print("═ 位次扫描（每个查询一条，本平台占比 / 改前第1名保住率）═")
    header = f"{'位次':<6}{'keep@3':<9}{'keep@5':<9}{'keep@10':<10}{'本平台占比':<12}"
    print(header + "─" * 20)
    for pos in (0, 2, 4, 6, 8, 12, 20):
        keep3 = keep5 = keep10 = 0
        own_total = 0
        cap = 0
        for q in queries:
            before = pools[q]["before"]
            if pos == 0:
                ranked = before[:limit]
            else:
                ranked = boost_own(pools[q]["pool"], owner_by_id, room, pos)[:limit]
            seq = [x["id"] for x in ranked]
            if not before:
                continue
            top1 = before[0]["id"]
            rank = seq.index(top1) + 1 if top1 in seq else 999
            keep3 += rank <= 3
            keep5 += rank <= 5
            keep10 += rank <= 10
            own_total += sum(1 for x in ranked if owner_by_id.get(x["id"]) == room)
            cap += len(ranked)
        n = len(queries)
        pct = own_total / cap * 100 if cap else 0
        label = "0(基线)" if pos == 0 else str(pos)
        print(f"{label:<8}{keep3}/{n:<7}{keep5}/{n:<7}{keep10}/{n:<8}{pct:>5.1f}%")


if __name__ == "__main__":
    main()
