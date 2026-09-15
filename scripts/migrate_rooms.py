#!/usr/bin/env python3
"""存量迁移：把缺 tenant_id 的存量记忆标 'dsh'

用法：
  python scripts/migrate_rooms.py --dry-run    # 预览改动（默认）
  python scripts/migrate_rooms.py --apply       # 执行迁移
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig


def main():
    parser = argparse.ArgumentParser(description="存量记忆迁移：标 tenant_id='dsh'")
    parser.add_argument("--apply", action="store_true", help="执行迁移（默认 dry-run）")
    parser.add_argument("--room", default="dsh", help="目标房间（默认 dsh）")
    args = parser.parse_args()

    cfg = PanguConfig.load().authoritative_memory_config()
    drawers_file = cfg.authoritative_drawers_path

    if not drawers_file.exists():
        print("无 drawers 文件，跳过")
        return

    with open(drawers_file, encoding="utf-8") as f:
        drawers = json.load(f)

    if not drawers:
        print("空库，跳过")
        return

    modified = 0
    for d in drawers:
        md = d.get("metadata", {})
        if not isinstance(md, dict):
            md = {}
            d["metadata"] = md
        if not md.get("tenant_id"):
            md["tenant_id"] = args.room
            md["migrated_at"] = datetime.now().isoformat()
            modified += 1

    print(f"总记忆: {len(drawers)}, 需迁移: {modified}")

    if modified == 0:
        print("无需迁移")
        return

    if not args.apply:
        print("（dry-run 模式，未写入。用 --apply 执行）")
        for d in drawers[:5]:
            md = d.get("metadata", {})
            if md.get("migrated_at"):
                print(f"  {d.get('id', '?')[:8]}: tenant_id={md.get('tenant_id')}")
        if len(drawers) > 5:
            print(f"  ... 共 {modified} 条")
        return

    # 备份
    backup = drawers_file.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(drawers_file, backup)
    print(f"备份: {backup}")

    # 写入
    tmp = drawers_file.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(drawers, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, drawers_file)
    print(f"已迁移 {modified} 条记忆到房间 '{args.room}'")


if __name__ == "__main__":
    main()
