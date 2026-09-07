#!/usr/bin/env python3
"""Phase 3: 智能增强 — 去重 + KG 丰富化 + 管道验证"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.dedup import MemoryDeduplicator
from pangu.memory.knowledge_graph import KnowledgeGraph


def run_dedup(drawers: list[Drawer]) -> dict:
    """运行去重检查"""
    dedup = MemoryDeduplicator()
    groups = dedup.find_duplicates(drawers, threshold=0.85, method="keyword")
    print(f"  去重检查: {len(groups)} 个重复组")
    for g in groups:
        print(f"    组 {g.id[:8]}: {len(g.memory_ids)} 条记忆, 平均相似度 {g.avg_similarity:.2f}")
    return {"groups": len(groups), "total_duplicates": sum(len(g.memory_ids) for g in groups)}


def enrich_kg(drawers: list[Drawer], kg: KnowledgeGraph) -> dict:
    """从记忆中提取实体和关系，丰富知识图谱"""
    entities_added = 0
    relations_added = 0

    # 预定义的实体类型映射
    ENTITY_TYPES = {
        "盘古": "system", "伏羲": "system", "羲和": "agent",
        "玄女": "agent", "轩辕": "agent", "OpenClaw": "system",
        "ONNX": "technology", "SQLite": "technology", "FTS5": "technology",
        "向量": "concept", "嵌入": "concept", "记忆": "concept",
        "知识图谱": "concept", "检索": "concept", "巩固": "concept",
        "MCP": "protocol", "REST": "protocol", "API": "protocol",
    }

    for d in drawers:
        content = d.content

        # 提取实体
        for name, etype in ENTITY_TYPES.items():
            if name in content:
                eid = f"entity_{name}"
                existing = kg.get_entity(eid)
                if not existing:
                    kg.add_entity(eid, name, etype, description=f"从记忆 {d.id[:8]} 提取")
                    entities_added += 1

        # 提取关系（基于 wing/room 分类）
        if d.wing == "tech" and d.room == "architecture":
            # 技术架构记忆 → 系统之间的关系
            for name1 in ENTITY_TYPES:
                for name2 in ENTITY_TYPES:
                    if name1 != name2 and name1 in content and name2 in content:
                        rid = f"rel_{name1}_{name2}_{d.id[:8]}"
                        try:
                            kg.add_relation(rid, f"entity_{name1}", "related_to", f"entity_{name2}",
                                           description=f"从记忆 {d.id[:8]} 提取")
                            relations_added += 1
                        except Exception:
                            pass

    result = {
        "entities_added": entities_added,
        "relations_added": relations_added,
        "total_entities": len(kg.list_entities()),
    }
    print(f"  KG 丰富化: +{entities_added} 实体, +{relations_added} 关系 (总计 {result['total_entities']} 实体)")
    return result


def main():
    config = PanguConfig.load()
    drawers_file = Path(config.palace_path) / "drawers.json"

    with open(drawers_file, encoding="utf-8") as f:
        drawers = [Drawer.from_dict(d) for d in json.load(f)]

    print(f"=== Phase 3: 智能增强 ===")
    print(f"加载 {len(drawers)} 条记忆\n")

    # 1. 去重
    print("--- 1. 去重检查 ---")
    dedup_result = run_dedup(drawers)

    # 2. KG 丰富化
    print("\n--- 2. 知识图谱丰富化 ---")
    kg = KnowledgeGraph(config)
    kg_result = enrich_kg(drawers, kg)

    # 3. 验证检索
    print("\n--- 3. 检索验证 ---")
    from pangu.memory.fts_search import FTS5SearchEngine
    engine = FTS5SearchEngine(config)
    r = engine.search("盘古记忆系统", drawers, limit=3)
    print(f"  搜索 \"盘古记忆系统\": {r['total']} 结果")
    for item in r["results"][:2]:
        print(f"    [{item['id'][:8]}] {item['content'][:50]}")

    print(f"\n=== Phase 3 完成 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
