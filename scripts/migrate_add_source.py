#!/usr/bin/env python3
"""盘古数据迁移脚本 — 给现有记忆添加 source 字段

运行方式：
    cd /home/xiaoxin/pangu
    .venv/bin/python scripts/migrate_add_source.py

功能：
    1. 读取所有记忆
    2. 根据 room 字段推断 source
    3. 添加 source 字段
    4. 保存迁移后的数据
"""

import json
import sys
from pathlib import Path
from collections import Counter


def infer_source(room: str, metadata: dict = None) -> str:
    """根据 room 和 metadata 推断 source"""
    # 如果已有 tenant_id，使用它
    if metadata and isinstance(metadata, dict):
        tenant_id = metadata.get("tenant_id", "")
        if tenant_id:
            return tenant_id

    # 根据 room 名称推断
    room_lower = room.lower() if room else ""
    
    if "dsh" in room_lower:
        return "dsh"
    elif "mcp" in room_lower:
        return "mcp"
    elif "api" in room_lower:
        return "api"
    elif "test" in room_lower:
        return "test"
    elif "ci" in room_lower:
        return "ci"
    elif "review" in room_lower:
        return "review"
    elif "pangu" in room_lower:
        return "pangu"
    else:
        return room or "default"


def migrate():
    """执行数据迁移"""
    # 找到记忆文件
    base_dir = Path.home() / ".pangu"
    drawers_path = base_dir / "pangu.db" / "v2_memories" / "drawers.json"
    
    if not drawers_path.exists():
        print(f"❌ 找不到记忆文件: {drawers_path}")
        return False
    
    print(f"📂 读取记忆文件: {drawers_path}")
    
    # 读取数据
    with open(drawers_path, encoding="utf-8") as f:
        data = json.load(f)
    
    drawers = data if isinstance(data, list) else data.get("drawers", [])
    print(f"📊 找到 {len(drawers)} 条记忆")
    
    # 统计 source 分布
    source_before = Counter()
    source_after = Counter()
    modified = 0
    
    for d in drawers:
        # 记录迁移前的 source
        old_source = d.get("source", "")
        source_before[old_source or "(empty)"] += 1
        
        # 推断 source
        new_source = infer_source(
            d.get("room", ""),
            d.get("metadata", {})
        )
        
        # 添加/更新 source 字段
        if not old_source or old_source != new_source:
            d["source"] = new_source
            modified += 1
        
        source_after[new_source] += 1
    
    print(f"\n📈 Source 分布变化:")
    print(f"  迁移前: {dict(source_before)}")
    print(f"  迁移后: {dict(source_after)}")
    print(f"  修改了 {modified} 条记忆")
    
    # 备份原文件
    backup_path = drawers_path.with_suffix(".json.bak")
    if not backup_path.exists():
        import shutil
        shutil.copy2(drawers_path, backup_path)
        print(f"💾 已备份到: {backup_path}")
    
    # 保存迁移后的数据
    with open(drawers_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 迁移完成！已保存到: {drawers_path}")
    return True


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
