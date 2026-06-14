#!/usr/bin/env python3
"""盘古记忆巩固定时任务
定期执行记忆巩固：遗忘、压缩、间隔重复
"""
import sys
import os
from datetime import datetime

# 添加pangu到路径
sys.path.insert(0, "/home/xiaoxin/pangu")

from pangu.core.config import PanguConfig
from pangu.core.palace import Palace
from pangu.memory.consolidation import MemoryConsolidator


def main():
    """执行记忆巩固"""
    print(f"[{datetime.now().isoformat()}] 开始记忆巩固...")
    
    config = PanguConfig.load()
    palace = Palace(config.palace_path)
    consolidator = MemoryConsolidator(config)
    
    # 获取所有记忆
    drawers = palace.drawers
    print(f"总记忆数: {len(drawers)}")
    
    # 1. 遗忘检查
    forgotten = consolidator.find_forgotten(drawers)
    print(f"应遗忘记忆: {len(forgotten)}")
    
    for d in forgotten:
        print(f"  遗忘: {d.id[:8]} - {d.content[:50]}...")
        palace.remove_drawer(d.id)
    
    # 2. 压缩检查
    if consolidator.should_compress(drawers):
        print("需要压缩记忆")
        compressible = consolidator.find_compressible(drawers)
        print(f"可压缩记忆: {len(compressible)}")
        # TODO: 实现记忆压缩
    
    # 3. 复习检查
    due_reviews = consolidator.find_due_reviews(drawers)
    print(f"待复习记忆: {len(due_reviews)}")
    
    for d in due_reviews:
        print(f"  复习: {d.id[:8]} - {d.content[:50]}...")
        consolidator.record_access(d.id)
    
    # 4. 统计信息
    stats = consolidator.stats(drawers)
    print(f"\n巩固统计:")
    print(f"  总记忆: {stats['total_memories']}")
    print(f"  已遗忘: {stats['forgotten_count']}")
    print(f"  待复习: {stats['due_review_count']}")
    print(f"  平均重要性: {stats['average_effective_importance']:.2f}")
    
    # 标记已完成巩固
    consolidator.mark_consolidated()
    print(f"\n[{datetime.now().isoformat()}] 记忆巩固完成")


if __name__ == "__main__":
    main()
