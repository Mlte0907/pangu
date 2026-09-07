#!/usr/bin/env python3
"""盘古 — LLM 缓存调试脚本

用途：将 LLM 持久化缓存导出为 JSON，用于调试/审计/迁移。

用法：
    # 导出全部缓存
    python scripts/dump_llm_cache.py

    # 导出到指定文件
    python scripts/dump_llm_cache.py -o cache_dump.json

    # 按 provider 筛选
    python scripts/dump_llm_cache.py --provider openai

    # 按 model 筛选
    python scripts/dump_llm_cache.py --model gpt-4o-mini

    # 限制条目数
    python scripts/dump_llm_cache.py --limit 50

    # 不导出响应内容（节省空间）
    python scripts/dump_llm_cache.py --no-content

    # 查看统计模式（不导出）
    python scripts/dump_llm_cache.py --stats-only
"""
import argparse
import json
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="导出 LLM 持久化缓存为 JSON")
    parser.add_argument("-o", "--output", default="", help="输出文件路径（默认 stdout）")
    parser.add_argument("--provider", default="", help="按 provider 筛选")
    parser.add_argument("--model", default="", help="按 model 筛选")
    parser.add_argument("--limit", type=int, default=0, help="限制条目数（0=不限）")
    parser.add_argument("--no-content", action="store_true", help="不导出响应内容")
    parser.add_argument("--stats-only", action="store_true", help="仅显示统计，不导出数据")
    parser.add_argument("--db-path", default="", help="SQLite 数据库路径（默认自动检测）")
    args = parser.parse_args()

    try:
        import sqlite3
    except ImportError:
        print("[ERROR] sqlite3 不可用", file=sys.stderr)
        sys.exit(1)

    # 确定 DB 路径
    db_path = args.db_path
    if not db_path:
        default = os.path.expanduser("~/.pangu/llm_cache.db")
        if os.path.exists(default):
            db_path = default
        else:
            print("[ERROR] 未找到缓存数据库，请指定 --db-path", file=sys.stderr)
            print(f"  默认路径: {default}", file=sys.stderr)
            sys.exit(1)

    if not os.path.exists(db_path):
        print(f"[ERROR] 数据库文件不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 获取总条目数
    total = conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
    print(f"数据库: {db_path}")
    print(f"总条目: {total}")
    if total == 0:
        print("[INFO] 缓存为空，无需导出")
        conn.close()
        return

    # 构建查询
    where_clauses = []
    params = []
    if args.provider:
        where_clauses.append("provider = ?")
        params.append(args.provider)
    if args.model:
        where_clauses.append("model = ?")
        params.append(args.model)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    limit_sql = ""
    if args.limit > 0:
        limit_sql = f"LIMIT {args.limit}"

    query = f"SELECT * FROM llm_cache {where_sql} ORDER BY hit_count DESC, last_accessed DESC {limit_sql}"

    # 仅统计模式
    if args.stats_only:
        stats = conn.execute(
            f"""SELECT provider, model, COUNT(*) as entries,
                       SUM(hit_count) as total_hits,
                       SUM(prompt_tokens + completion_tokens) as total_tokens,
                       MIN(created_at) as oldest,
                       MAX(created_at) as newest
                FROM llm_cache {where_sql}
                GROUP BY provider, model
                ORDER BY total_hits DESC""",
            params,
        ).fetchall()

        print("\n┌─ 按 Provider/Model 统计 ─┐")
        for row in stats:
            print(f"  {row['provider']}/{row['model']}")
            print(f"    条目: {row['entries']}  命中: {row['total_hits']}  Token: {row['total_tokens'] or 0}")
            oldest_age = _human_age(row["oldest"])
            newest_age = _human_age(row["newest"])
            print(f"    最早: {oldest_age}  最新: {newest_age}")
            print()

        # 总体统计
        overall = conn.execute(
            f"""SELECT SUM(hit_count) as total_hits,
                       SUM(prompt_tokens + completion_tokens) as total_tokens,
                       COUNT(*) as entries
                FROM llm_cache {where_sql}""",
            params,
        ).fetchone()
        print(f"总计: {overall['entries']} 条目, {overall['total_hits']} 命中, {overall['total_tokens'] or 0} token")
        conn.close()
        return

    # 导出数据
    rows = conn.execute(query, params).fetchall()
    entries = []
    for row in rows:
        entry = {
            "key": row["key"],
            "provider": row["provider"],
            "model": row["model"],
            "hit_count": row["hit_count"],
            "created_at": row["created_at"],
            "last_accessed": row["last_accessed"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
        }
        if not args.no_content:
            entry["response_content"] = row.get("response_content", "")
        entries.append(entry)

    result = {
        "exported_at": time.time(),
        "db_path": db_path,
        "total_in_db": total,
        "exported_count": len(entries),
        "filters": {
            "provider": args.provider or "all",
            "model": args.model or "all",
            "limit": args.limit or "all",
        },
        "entries": entries,
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"\n已导出 {len(entries)} 条到 {args.output}")
        size = os.path.getsize(args.output)
        print(f"文件大小: {_human_size(size)}")
    else:
        print(output_json)

    conn.close()


def _human_age(timestamp: float) -> str:
    """人类可读的时间差"""
    if not timestamp:
        return "-"
    diff = time.time() - timestamp
    if diff < 60:
        return f"{int(diff)}s 前"
    if diff < 3600:
        return f"{int(diff / 60)}m 前"
    if diff < 86400:
        return f"{int(diff / 3600)}h 前"
    return f"{int(diff / 86400)}d 前"


def _human_size(size: int) -> str:
    """人类可读的文件大小"""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    main()
