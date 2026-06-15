"""盘古搜索结果聚类 — 按标签/时间分组展示"""

import logging
from collections import defaultdict
from datetime import datetime

from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.cluster")


def cluster_by_tags(results: list[dict]) -> dict[str, list[dict]]:
    """按标签聚类搜索结果

    Args:
        results: 搜索结果列表（含 tags 字段）

    Returns:
        {tag: [results]} 按标签分组
    """
    clusters = defaultdict(list)
    for r in results:
        tags = r.get("tags", [])
        if tags:
            # 使用第一个标签作为主分类
            primary_tag = tags[0]
            clusters[primary_tag].append(r)
        else:
            clusters["未分类"].append(r)

    # 按数量排序
    return dict(sorted(clusters.items(), key=lambda x: -len(x[1])))


def cluster_by_time(results: list[dict], buckets: int = 3) -> dict[str, list[dict]]:
    """按时间聚类搜索结果

    Args:
        results: 搜索结果列表（含 created_at 字段）
        buckets: 时间段数量

    Returns:
        {time_range: [results]} 按时间分段
    """
    if not results:
        return {}

    # 解析时间
    timestamps = []
    for r in results:
        try:
            ts = datetime.fromisoformat(r.get("created_at", ""))
            timestamps.append((ts, r))
        except (ValueError, TypeError):
            timestamps.append((datetime.min, r))

    timestamps.sort(key=lambda x: x[0])

    if len(timestamps) <= buckets:
        # 结果少于分段数，按单条分组
        return {f"第{i+1}条": [r] for i, (_, r) in enumerate(timestamps)}

    # 按时间段分组
    chunk_size = len(timestamps) // buckets
    clusters = {}
    for i in range(buckets):
        start = i * chunk_size
        end = start + chunk_size if i < buckets - 1 else len(timestamps)
        chunk = timestamps[start:end]

        if chunk:
            start_time = chunk[0][0]
            end_time = chunk[-1][0]
            if start_time == end_time:
                label = start_time.strftime("%Y-%m-%d")
            else:
                label = f"{start_time.strftime('%m-%d')} ~ {end_time.strftime('%m-%d')}"
            clusters[label] = [r for _, r in chunk]

    return clusters


def cluster_by_wing(results: list[dict]) -> dict[str, list[dict]]:
    """按 Wing 聚类搜索结果"""
    clusters = defaultdict(list)
    for r in results:
        wing = r.get("wing", "default")
        clusters[wing].append(r)
    return dict(sorted(clusters.items(), key=lambda x: -len(x[1])))


def get_cluster_summary(clusters: dict[str, list[dict]]) -> list[dict]:
    """获取聚类摘要"""
    summary = []
    for name, items in clusters.items():
        summary.append({
            "name": name,
            "count": len(items),
            "items": items[:3],  # 只返回前3条
        })
    return summary
