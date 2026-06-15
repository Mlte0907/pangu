"""盘古搜索结果聚类 — 标签/时间/层次聚类"""

import logging
import math
from collections import defaultdict
from datetime import datetime

from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.cluster")


# ── 基础聚类 ──

def cluster_by_tags(results: list[dict]) -> dict[str, list[dict]]:
    """按标签聚类搜索结果"""
    clusters = defaultdict(list)
    for r in results:
        tags = r.get("tags", [])
        if tags:
            primary_tag = tags[0]
            clusters[primary_tag].append(r)
        else:
            clusters["未分类"].append(r)
    return dict(sorted(clusters.items(), key=lambda x: -len(x[1])))


def cluster_by_time(results: list[dict], buckets: int = 3) -> dict[str, list[dict]]:
    """按时间聚类搜索结果"""
    if not results:
        return {}

    timestamps = []
    for r in results:
        try:
            ts = datetime.fromisoformat(r.get("created_at", ""))
            timestamps.append((ts, r))
        except (ValueError, TypeError):
            timestamps.append((datetime.min, r))

    timestamps.sort(key=lambda x: x[0])

    if len(timestamps) <= buckets:
        return {f"第{i+1}条": [r] for i, (_, r) in enumerate(timestamps)}

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
            "items": items[:3],
        })
    return summary


# ── 层次聚类 ──

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a[:n], b[:n]))
    norm_a = math.sqrt(sum(x * x for x in a[:n]))
    norm_b = math.sqrt(sum(x * x for x in b[:n]))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(text: str) -> list[float] | None:
    """获取文本嵌入向量"""
    try:
        from ..memory.onnx_embedder import get_onnx_embedder
        onnx = get_onnx_embedder()
        if onnx.is_available:
            return onnx.embed(text)
    except Exception:
        pass
    return None


def hierarchical_cluster(
    results: list[dict],
    max_clusters: int = 5,
    min_similarity: float = 0.3,
) -> list[dict]:
    """层次聚类 — 基于向量相似度的自底向上聚合

    Args:
        results: 搜索结果列表
        max_clusters: 最大聚类数
        min_similarity: 最小相似度阈值

    Returns:
        [{"name": str, "count": int, "items": list, "centroid": str}]
    """
    if len(results) <= 1:
        return [{"name": "全部", "count": len(results), "items": results, "centroid": ""}]

    # 获取嵌入向量
    embeddings = {}
    for r in results:
        emb = _get_embedding(r.get("content", ""))
        if emb:
            embeddings[r["id"]] = emb

    if len(embeddings) < 2:
        # 无法获取嵌入，降级到标签聚类
        clusters = cluster_by_tags(results)
        return [{"name": k, "count": len(v), "items": v, "centroid": ""} for k, v in clusters.items()]

    # 计算相似度矩阵
    ids = list(embeddings.keys())
    n = len(ids)
    sim_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(embeddings[ids[i]], embeddings[ids[j]])
            sim_matrix[i][j] = sim
            sim_matrix[j][i] = sim

    # 层次聚类（自底向上聚合）
    clusters = {i: [ids[i]] for i in range(n)}

    while len(clusters) > max_clusters:
        # 找最相似的两个聚类
        best_sim = -1
        best_pair = None
        cluster_ids = list(clusters.keys())

        for i in range(len(cluster_ids)):
            for j in range(i + 1, len(cluster_ids)):
                ci, cj = cluster_ids[i], cluster_ids[j]
                # 聚类间相似度 = 平均链接
                total_sim = 0.0
                count = 0
                for mi in clusters[ci]:
                    for mj in clusters[cj]:
                        idx_i = ids.index(mi)
                        idx_j = ids.index(mj)
                        total_sim += sim_matrix[idx_i][idx_j]
                        count += 1
                avg_sim = total_sim / count if count > 0 else 0.0

                if avg_sim > best_sim:
                    best_sim = avg_sim
                    best_pair = (ci, cj)

        if best_sim < min_similarity or best_pair is None:
            break

        # 合并两个聚类
        ci, cj = best_pair
        clusters[ci].extend(clusters[cj])
        del clusters[cj]

    # 构建结果
    result = []
    id_map = {r["id"]: r for r in results}
    for cluster_id, member_ids in clusters.items():
        items = [id_map[mid] for mid in member_ids if mid in id_map]
        # 生成聚类名称（取第一个内容的前20字）
        centroid = items[0].get("content", "")[:20] if items else ""
        result.append({
            "name": f"聚类{len(result)+1}",
            "count": len(items),
            "items": items,
            "centroid": centroid,
        })

    return result
