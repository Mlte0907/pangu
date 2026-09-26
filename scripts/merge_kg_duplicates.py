"""合并 entities_all / relations_all 里同 id 多属主的重复行（2026-09-26）。

背景：`entities_all` / `relations_all` 主键是 (id, tenant_id)，所以同一个 id 可以在多个
属主下各有一行；而 `INSERT OR REPLACE` 只覆盖「同 id 同属主」那一份。云端实测：09-22 晚间
把记忆归属整体改写成按平台分之后，09-26 的 kg_enrichment 抽取对同一批实体换了属主，
entities_all 从 19 行涨到 33 行（default 19 + deepseek-harness 14），图谱上每个实体出现两次。

本脚本**只做读取侧的等价合并**，不碰多租户语义：
  * 每个 id 只留一行 —— 取 created_at 最新的那条（与 graph_data 的 _kg_row_rank 同规则）
  * 不删除任何描述/名称/关系语义：留下的那一行就是当前真相，被合并掉的行是同 id 的旧属主副本
  * 幂等：重复执行不会二次改动（合并后每个 id 只剩一行）
  * 全程事务；执行前自动备份 .db

用法：
    python3 -c "import sys; sys.path.insert(0,'/root/pangu'); from pangu.memory.knowledge_graph import KnowledgeGraph; ..."
或直接：
    /root/pangu/.venv/bin/python merge_kg_duplicates.py [--db <path>] [--apply]

默认 dry-run，只打印将要发生的改动；确认无误后加 --apply 真正写入。
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = "/root/.pangu/pangu.db/v2_memories/knowledge_graph.db"


def pick_winner(rows: list[dict]) -> dict:
    """留哪一行：created_at 最新的优先。规则必须与 graph_data._kg_row_rank 一致。"""
    return max(rows, key=lambda r: str(r.get("created_at") or ""))


def plan(conn, table: str) -> list[tuple[str, str, str, str]]:
    """返回 [(id, 留下的 tenant_id, 删掉的 tenant_id, created_at)]。"""
    out = []
    dup_ids = [r[0] for r in conn.execute(f"SELECT id FROM {table} GROUP BY id HAVING COUNT(*)>1")]
    for eid in dup_ids:
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE id=?", (eid,))]
        win = pick_winner(rows)
        for r in rows:
            if r["tenant_id"] != win["tenant_id"]:
                out.append((eid, win["tenant_id"], r["tenant_id"], win.get("created_at", "")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="真正写入（默认只 dry-run 打印）")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"找不到 {db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    before = {
        t: (
            conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0],
            conn.execute(f"SELECT COUNT(DISTINCT id) FROM {t}").fetchone()[0],
        )
        for t in ("entities_all", "relations_all")
    }
    print("【执行前】")
    for t, (rows, ids) in before.items():
        print(f"  {t}: {rows} 行 / {ids} 个唯一 id")

    todo = {t: plan(conn, t) for t in ("entities_all", "relations_all")}
    total = sum(len(v) for v in todo.values())
    if total == 0:
        print("\n没有需要合并的重复行 —— 已是干净状态（脚本幂等）。")
        conn.close()
        return 0

    print(f"\n【将合并 {total} 行】")
    for t, items in todo.items():
        print(f"  ── {t}：{len(items)} 行")
        for eid, keep, drop, ts in items:
            print(f"     {eid}  保留 {keep}  删除 {drop}   (created_at={ts})")

    if not args.apply:
        print("\n这是 dry-run。确认无误后加 --apply 执行。")
        conn.close()
        return 0

    backup = db.with_suffix(f".db.bak-merge-{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(db, backup)
    print(f"\n已备份 → {backup}")

    conn.execute("BEGIN")
    try:
        for t, items in todo.items():
            for eid, keep, drop, _ts in items:
                cur = conn.execute(f"DELETE FROM {t} WHERE id=? AND tenant_id=?", (eid, drop))
                if cur.rowcount != 1:
                    raise RuntimeError(f"{t}: {eid}/{drop} 预期删 1 行，实删 {cur.rowcount}")
        conn.commit()
    except Exception:
        conn.rollback()
        print("已回滚，未做任何改动。", file=sys.stderr)
        conn.close()
        return 1

    print("\n【执行后】")
    ok = True
    for t in ("entities_all", "relations_all"):
        rows = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        ids = conn.execute(f"SELECT COUNT(DISTINCT id) FROM {t}").fetchone()[0]
        print(f"  {t}: {rows} 行 / {ids} 个唯一 id")
        if rows != ids:
            print(f"  ✗ {t} 仍有重复 id！", file=sys.stderr)
            ok = False
    # 复核：关系两端指向的实体必须都还在，否则图会出现悬空边
    orphan = conn.execute(
        "SELECT COUNT(*) FROM relations_all r WHERE r.subject_id NOT IN (SELECT id FROM entities_all)"
        " OR r.object_id NOT IN (SELECT id FROM entities_all)"
    ).fetchone()[0]
    print(f"  悬空关系: {orphan}")
    if orphan:
        ok = False
    conn.close()
    print("\n全部校验通过。" if ok else "\n校验未通过，请用备份回滚。", file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
