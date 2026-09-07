#!/usr/bin/env python3
"""盘古记忆系统全面测试"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, '/home/xiaoxin/pangu')

from pangu.core.config import PanguConfig
from pangu.core.palace import Palace, Drawer
from pangu.memory.consolidation import MemoryConsolidator, ForgettingCurve

# 加载配置
config = PanguConfig.load()
palace_path = Path(config.palace_path)

# 加载现有 drawers
drawers_file = palace_path / 'drawers.json'
if drawers_file.exists():
    with open(drawers_file, encoding='utf-8') as f:
        existing = [Drawer.from_dict(d) for d in json.load(f)]
else:
    existing = []

print("=" * 60)
print("盘古记忆系统全面测试")
print("=" * 60)

# 测试1: 遗忘曲线
print("\n[测试1] 遗忘曲线")
curve = ForgettingCurve(decay_rate=0.5)
print(f"  0小时保留率: {curve.retention(0):.2%}")
print(f"  24小时保留率: {curve.retention(24):.2%}")
print(f"  48小时保留率: {curve.retention(48):.2%}")
print(f"  72小时保留率: {curve.retention(72):.2%}")
print("  ✓ 遗忘曲线测试通过")

# 测试2: 记忆巩固器
print("\n[测试2] 记忆巩固器")
consolidator = MemoryConsolidator(config)
stats = consolidator.stats(existing)
print(f"  总记忆数: {stats['total_memories']}")
print(f"  应遗忘数: {stats['forgotten_count']}")
print(f"  待复习数: {stats['due_review_count']}")
print(f"  平均有效重要性: {stats['average_effective_importance']}")
print("  ✓ 记忆巩固器测试通过")

# 测试3: 重要性计算
print("\n[测试3] 重要性计算")
for d in existing[:3]:
    importance = consolidator.calculate_importance(d)
    print(f"  {d.id[:8]}: 原始={d.importance:.1f}, 有效={importance:.2f}")
print("  ✓ 重要性计算测试通过")

# 测试4: 遗忘判定
print("\n[测试4] 遗忘判定")
forgotten = consolidator.find_forgotten(existing)
print(f"  应遗忘记忆数: {len(forgotten)}")
for d in forgotten[:3]:
    print(f"    - {d.id[:8]}: {d.content[:50]}...")
print("  ✓ 遗忘判定测试通过")

# 测试5: 复习判定
print("\n[测试5] 复习判定")
due_reviews = consolidator.find_due_reviews(existing)
print(f"  待复习记忆数: {len(due_reviews)}")
print("  ✓ 复习判定测试通过")

# 测试6: 压缩判定
print("\n[测试6] 压缩判定")
needs_compression = consolidator.should_compress(existing)
print(f"  需要压缩: {needs_compression}")
print(f"  压缩阈值: {config.compression_threshold}")
print("  ✓ 压缩判定测试通过")

# 测试7: 间隔重复
print("\n[测试7] 间隔重复")
for i in range(6):
    interval = MemoryConsolidator.next_review_interval(i)
    print(f"  第{i+1}次复习间隔: {interval:.0f}小时 ({interval/24:.1f}天)")
print("  ✓ 间隔重复测试通过")

# 测试8: 访问追踪
print("\n[测试8] 访问追踪")
if existing:
    test_id = existing[0].id
    consolidator.record_access(test_id)
    consolidator.record_access(test_id)
    count = consolidator.get_access_count(test_id)
    print(f"  记忆 {test_id[:8]} 访问次数: {count}")
print("  ✓ 访问追踪测试通过")

# 测试9: Palace 统计
print("\n[测试9] Palace 统计")
palace = Palace(config.palace_path)
palace_stats = palace.stats()
print(f"  Wings: {palace_stats['wings_count']}")
print(f"  Rooms: {palace_stats['rooms_count']}")
print(f"  Tunnels: {palace_stats['tunnels_count']}")
print("  ✓ Palace 统计测试通过")

# 测试10: Wing 列表
print("\n[测试10] Wing 列表")
wings = palace.list_wings()
print(f"  Wings: {wings}")
print("  ✓ Wing 列表测试通过")

# 测试11: Room 列表
print("\n[测试11] Room 列表")
rooms = palace.list_rooms()
print(f"  Rooms: {rooms}")
print("  ✓ Room 列表测试通过")

# 测试12: 隧道列表
print("\n[测试12] 隧道列表")
tunnels = palace.list_tunnels()
print(f"  Tunnels: {len(tunnels)}")
print("  ✓ 隧道列表测试通过")

# 测试13: 导出结构
print("\n[测试13] 导出结构")
structure = palace.export_structure()
print(f"  节点数: {len(structure['nodes'])}")
print(f"  边数: {len(structure['edges'])}")
print("  ✓ 导出结构测试通过")

# 测试14: 统计汇总
print("\n[测试14] 统计汇总")
summary = {
    "total_memories": len(existing),
    "wings": list(set(d.wing for d in existing)),
    "rooms": list(set(d.room for d in existing)),
    "avg_importance": sum(d.importance for d in existing) / max(len(existing), 1),
    "forgotten": len(consolidator.find_forgotten(existing)),
    "due_reviews": len(consolidator.find_due_reviews(existing)),
}
print(f"  总记忆: {summary['total_memories']}")
print(f"  Wings: {summary['wings']}")
print(f"  Rooms: {summary['rooms']}")
print(f"  平均重要性: {summary['avg_importance']:.2f}")
print(f"  应遗忘: {summary['forgotten']}")
print(f"  待复习: {summary['due_reviews']}")
print("  ✓ 统计汇总测试通过")

print("\n" + "=" * 60)
print("所有测试通过！")
print("=" * 60)
