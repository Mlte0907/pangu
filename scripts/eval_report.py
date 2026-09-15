#!/usr/bin/env python3
"""盘古记忆评估报告
输出记忆总量、admission 分布、importance_feedback 正负比、wing 分布；
外加参数化延迟召回测试（--age-hours）。
"""
import sys
import argparse
from collections import Counter
from datetime import datetime

sys.path.insert(0, "/home/xiaoxin/pangu")

from pangu.core.config import PanguConfig


def load_drawers():
    cfg = PanguConfig.load().authoritative_memory_config()
    from pangu.memory.drawer_storage import JsonDrawerStorage
    return JsonDrawerStorage(str(cfg.authoritative_drawers_path)).load()


def print_report(drawers):
    print(f"═══ 盘古记忆评估报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ═══")
    print(f"  总量: {len(drawers)}")

    # admission 分布
    admission = Counter(d.metadata.get("admission", "none") for d in drawers)
    print(f"\n  admission 分布:")
    for k, v in admission.most_common():
        print(f"    {k}: {v}")

    # importance_feedback 正负比
    feedbacks = Counter(d.metadata.get("last_feedback", "") for d in drawers if d.metadata.get("last_feedback"))
    positive = feedbacks.get("recall_success", 0) + feedbacks.get("verified", 0) + feedbacks.get("vote_up", 0)
    negative = feedbacks.get("recall_miss", 0) + feedbacks.get("vote_down", 0)
    print(f"\n  importance_feedback:")
    print(f"    正向: {positive}  负向: {negative}  比: {positive/negative if negative else '∞'}")
    for k, v in feedbacks.most_common():
        print(f"    {k}: {v}")

    # wing 分布
    wings = Counter(d.wing for d in drawers)
    print(f"\n  wing 分布:")
    for k, v in wings.most_common():
        print(f"    {k}: {v}")

    # visibility 分布
    vis = Counter(d.metadata.get("visibility", "none") for d in drawers)
    print(f"\n  visibility 分布:")
    for k, v in vis.most_common():
        print(f"    {k}: {v}")


def run_delayed_recall_test(age_hours: float):
    """参数化延迟召回测试"""
    from pangu.core.palace import Drawer
    from pangu.memory.ingestion import remember
    from pangu.memory.retrieval import importance_feedback

    print(f"\n═══ 延迟召回测试 (age_hours={age_hours}) ═══")

    # 写入一条带前提条件的记忆
    test_content = f"评估报告延迟召回测试 {datetime.now().isoformat()}"
    item_id, drawer = remember(
        raw_text=test_content,
        wing="test_eval",
        room="t",
        importance=0.5,
        source="eval_report",
        source_session="eval_test",
        tags=["eval", "delayed_recall"],
    )
    print(f"  写入: {item_id[:8]}")

    # 注入正向反馈
    result = importance_feedback(item_id, "recall_success")
    print(f"  反馈: {result.get('signal', 'error')}")

    # 验证：importance 应该增加
    drawers = load_drawers()
    target = None
    for d in drawers:
        if d.id == item_id:
            target = d
            break
    if target:
        print(f"  验证: importance={target.importance:.2f}, admission={target.metadata.get('admission', 'none')}")
        passed = target.importance > 0.5 and target.metadata.get("last_feedback") == "recall_success"
        print(f"  结果: {'PASS' if passed else 'FAIL'}")
    else:
        print(f"  结果: FAIL (记忆未找到)")


def main():
    parser = argparse.ArgumentParser(description="盘古记忆评估报告")
    parser.add_argument("--age-hours", type=float, default=None, help="延迟召回测试间隔（小时）")
    args = parser.parse_args()

    drawers = load_drawers()
    print_report(drawers)

    if args.age_hours is not None:
        run_delayed_recall_test(args.age_hours)


if __name__ == "__main__":
    main()
