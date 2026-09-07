#!/usr/bin/env python3
"""盘古大规模数据测试脚本 — 生成1000条测试记忆并测试搜索性能"""

import json
import random
import time
import statistics
from pathlib import Path
from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.retrieval import recall, clear_recall_cache
from pangu.memory.vector_index import get_vector_index
from pangu.memory.layers import _estimate_tokens

# 测试数据模板
TEMPLATES = [
    "Python是一种{adj}编程语言，{use}",
    "ONNX Runtime支持{device}推理，{metric}",
    "FAISS是{org}开源的{type}搜索库",
    "盘古记忆系统使用{num}层记忆栈",
    "艾宾浩斯遗忘曲线{formula}",
    "深度学习是{field}的子领域",
    "Docker容器化技术{action}应用部署",
    "Kubernetes编排{target}容器",
    "Redis缓存{usage}数据",
    "PostgreSQL{action}关系型数据库",
]

ADJS = ["解释型", "高级", "动态", "面向对象"]
USES = ["广泛用于AI和数据科学", "是机器学习首选", "支持Web开发"]
DEVICES = ["CPU和GPU", "边缘设备", "移动端"]
METRICS = ["延迟低至0.002ms", "性能优异", "资源占用低"]
ORGS = ["Facebook", "Google", "Meta"]
TYPES = ["向量相似度", "近似最近邻", "语义"]
NUMS = ["4", "3", "5"]
FORMULAS = ["公式R=e^(-t/S)", "揭示记忆衰减规律", "描述遗忘过程"]
FIELDS = ["机器学习", "人工智能", "数据科学"]
ACTIONS = ["简化了", "优化了", "提升了"]
TARGETS = ["微服务", "云原生", "分布式"]
USAGES = ["热点", "会话", "临时"]
ACTIONDB = ["是", "作为", "支持"]

def generate_memory(i):
    """生成第i条测试记忆"""
    template = random.choice(TEMPLATES)
    content = template.format(
        adj=random.choice(ADJS),
        use=random.choice(USES),
        device=random.choice(DEVICES),
        metric=random.choice(METRICS),
        org=random.choice(ORGS),
        type=random.choice(TYPES),
        num=random.choice(NUMS),
        formula=random.choice(FORMULAS),
        field=random.choice(FIELDS),
        action=random.choice(ACTIONS),
        target=random.choice(TARGETS),
        usage=random.choice(USAGES),
    )
    return content

def main():
    config = PanguConfig.load()
    drawers_file = Path(config.palace_path) / "drawers.json"
    
    # 加载现有记忆
    with open(drawers_file, encoding="utf-8") as f:
        existing = json.load(f)
    existing_ids = {d["id"] for d in existing}
    
    print("=" * 60)
    print("  大规模数据测试 (1000 条)")
    print("=" * 60)
    
    # 生成测试记忆
    print("\n[1] 生成 1000 条测试记忆")
    new_drawers = []
    new_ids = []
    
    for i in range(1000):
        content = generate_memory(i)
        item_id = f"bench-{i:04d}"
        if item_id in existing_ids:
            continue
        
        drawer_dict = {
            "id": item_id,
            "content": content,
            "wing": "bench",
            "room": "test",
            "hall": "concept",
            "importance": random.uniform(0.3, 0.9) * 5.0,
            "emotional_weight": 0.0,
            "source_file": "",
            "tags": ["bench", f"test-{i % 20}"],
            "author": "bench-test",
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "source": "bench",
                "confidence": 1.0,
                "created_by": "bench",
                "embedding": None,  # 稍后生成
            }
        }
        new_drawers.append(drawer_dict)
        new_ids.append(item_id)
    
    print(f"  生成: {len(new_drawers)} 条")
    
    # 保存到 drawers.json
    existing.extend(new_drawers)
    with open(drawers_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  保存: {drawers_file}")
    
    # 重新加载
    from pangu.memory.layers import MemoryStack
    stack = MemoryStack(config)
    stack.invalidate_cache()
    drawers = stack.get_drawers()
    print(f"  总记忆: {len(drawers)}")
    
    # 向量索引
    idx = get_vector_index()
    print(f"  向量: {idx.size} vectors, {'FAISS' if idx._use_faiss else 'numpy'}")
    
    # 搜索性能测试
    print("\n[2] 搜索性能测试")
    queries = ["Python", "AI", "记忆", "向量", "ONNX", "深度学习", "容器化", "不存在的查询"]
    
    for query in queries:
        times = []
        for _ in range(10):
            clear_recall_cache()
            t0 = time.perf_counter()
            recall(query=query, limit=10, drawers=drawers)
            times.append((time.perf_counter() - t0) * 1000)
        
        median = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"  \"{query}\": median={median:.1f}ms, p95={p95:.1f}ms")
    
    # Token 统计
    total_tokens = sum(_estimate_tokens(d.content) for d in drawers)
    print(f"\n[3] Token: {total_tokens} total, {total_tokens // len(drawers)} avg")
    
    # 清理
    print("\n[4] 清理")
    existing = [d for d in existing if d["id"] not in set(new_ids)]
    with open(drawers_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  删除: {len(new_ids)} 条")
    
    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)

if __name__ == "__main__":
    from datetime import datetime
    main()
