#!/usr/bin/env python3
"""盘古记忆巩固定时任务
定期执行记忆巩固：遗忘、压缩、间隔重复
P1-3 收尾：接入 MemoryCompressor（保守参数：>30天 且 importance<0.3，单轮限量5条）
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, "/home/xiaoxin/pangu")

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer, Palace
from pangu.memory.consolidation import MemoryConsolidator


def main():
    """执行记忆巩固"""
    print(f"[{datetime.now().isoformat()}] 开始记忆巩固...")

    config = PanguConfig.load().authoritative_memory_config()
    palace = Palace(config.palace_path)
    consolidator = MemoryConsolidator(config)

    # 用权威 v2 路径加载 drawers
    from pangu.memory.drawer_storage import JsonDrawerStorage
    v2_path = config.authoritative_drawers_path
    storage = JsonDrawerStorage(str(v2_path))
    drawers = storage.load()
    if not drawers:
        print("无记忆，跳过巩固")
        return
    print(f"总记忆数: {len(drawers)}")

    # 1. 遗忘检查
    forgotten = consolidator.find_forgotten(drawers)
    print(f"应遗忘记忆: {len(forgotten)}")
    for d in forgotten:
        print(f"  遗忘: {d.id[:8]} - {d.content[:50]}...")
        drawers = [x for x in drawers if x.id != d.id]

    # 2. 压缩检查（保守参数：>30天 且 importance<0.3，单轮限量5条）
    if consolidator.should_compress(drawers):
        print("需要压缩记忆")
        compressible = consolidator.find_compressible(drawers)
        print(f"可压缩记忆: {len(compressible)}")

        from pangu.memory.compression import MemoryCompressor
        compressor = MemoryCompressor()
        compressed_count = 0
        MAX_COMPRESS_PER_CYCLE = 5

        for d in compressible:
            if compressed_count >= MAX_COMPRESS_PER_CYCLE:
                print(f"  达到单轮上限 {MAX_COMPRESS_PER_CYCLE}，跳过剩余")
                break
            try:
                days_old = (datetime.now() - datetime.fromisoformat(d.created_at)).total_seconds() / 86400
                if days_old < 30:
                    continue
                if d.importance >= 0.3:
                    continue
            except (ValueError, TypeError):
                continue

            result = compressor.compress(d)
            if result and result.compressed_content:
                d.content = result.compressed_content
                d.metadata["compressed"] = True
                d.metadata["compressed_at"] = datetime.now().isoformat()
                d.metadata["compression_ratio"] = result.compression_ratio
                compressed_count += 1
                print(f"  压缩: {d.id[:8]} ({result.compression_ratio:.0%}) {d.content[:50]}...")

        if compressed_count > 0:
            print(f"  本轮压缩 {compressed_count} 条")

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

    # 保存
    storage.save(drawers)
    consolidator.mark_consolidated()
    print(f"\n[{datetime.now().isoformat()}] 记忆巩固完成")


if __name__ == "__main__":
    main()
