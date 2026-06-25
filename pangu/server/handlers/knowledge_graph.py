"""盘古 MCP Handler — knowledge_graph (7 tools)"""
import json

TOOLS = [
    {"name": "pangu_kg_add_entity", "description": "\u6dfb\u52a0\u77e5\u8bc6\u56fe\u8c31\u5b9e\u4f53"},
    {"name": "pangu_kg_add_relation", "description": "\u6dfb\u52a0\u77e5\u8bc6\u56fe\u8c31\u5173\u7cfb"},
    {"name": "pangu_kg_query", "description": "\u67e5\u8be2\u77e5\u8bc6\u56fe\u8c31"},
    {"name": "pangu_kg_neighbors", "description": "\u83b7\u53d6\u5b9e\u4f53\u90bb\u5c45"},
    {"name": "pangu_kg_auto_extract", "description": "\u4ece\u8bb0\u5fc6\u4e2d\u81ea\u52a8\u63d0\u53d6\u5b9e\u4f53\u548c\u5173\u7cfb\u4e30\u5bccKG"},
    {"name": "pangu_kg_cross_domain", "description": "\u8de8\u9886\u57df\u77e5\u8bc6\u8fc1\u79fb"},
    {"name": "pangu_kg_similar_patterns", "description": "\u67e5\u627e\u76f8\u4f3c\u6a21\u5f0f"},
]

HANDLERS = {}

async def handle_kg_add_entity(server, drawers, arguments):
    """添加知识图谱实体"""
    entity = server.knowledge_graph.add_entity(
        id=arguments.get("id", ""),
        name=arguments.get("name", ""),
        entity_type=arguments.get("type", "concept"),
        description=arguments.get("description", ""),
    )
    return json.dumps(entity, ensure_ascii=False)

HANDLERS["pangu_kg_add_entity"] = handle_kg_add_entity

async def handle_kg_add_relation(server, drawers, arguments):
    """添加知识图谱关系"""
    rel = server.knowledge_graph.add_relation(
        id=arguments.get("id", ""),
        subject_id=arguments.get("subject_id", ""),
        predicate=arguments.get("predicate", ""),
        object_id=arguments.get("object_id", ""),
        valid_from=arguments.get("valid_from"),
        valid_until=arguments.get("valid_until"),
        confidence=arguments.get("confidence", 1.0),
        source=arguments.get("source", ""),
    )
    return json.dumps(rel, ensure_ascii=False)

HANDLERS["pangu_kg_add_relation"] = handle_kg_add_relation

async def handle_kg_query(server, drawers, arguments):
    """查询知识图谱"""
    relations = server.knowledge_graph.query_relations(
        subject_id=arguments.get("subject_id"),
        object_id=arguments.get("object_id"),
        predicate=arguments.get("predicate"),
        at_time=arguments.get("at_time"),
    )
    return json.dumps(relations, ensure_ascii=False, indent=2)

HANDLERS["pangu_kg_query"] = handle_kg_query

async def handle_kg_neighbors(server, drawers, arguments):
    """获取实体邻居"""
    neighbors = server.knowledge_graph.get_neighbors(
        entity_id=arguments.get("entity_id", ""),
        at_time=arguments.get("at_time"),
    )
    return json.dumps(neighbors, ensure_ascii=False, indent=2)

HANDLERS["pangu_kg_neighbors"] = handle_kg_neighbors

async def handle_kg_auto_extract(server, drawers, arguments):
    """从记忆中自动提取实体和关系丰富KG"""
    from ...memory.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(server.config)
    max_d = arguments.get("max_drawers", 50)
    result = kg.auto_extract_entities(drawers, max_d)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_kg_auto_extract"] = handle_kg_auto_extract

async def handle_kg_cross_domain(server, drawers, arguments):
    """跨领域知识迁移"""
    from ...memory.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(server.config)
    source = arguments.get("source_domain", "")
    target = arguments.get("target_domain", "")
    result = kg.cross_domain_transfer(source, target)
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_kg_cross_domain"] = handle_kg_cross_domain

async def handle_kg_similar_patterns(server, drawers, arguments):
    """查找相似模式"""
    from ...memory.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(server.config)
    entity_id = arguments.get("entity_id", "")
    patterns = kg.find_similar_patterns(entity_id)
    return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, indent=2)

HANDLERS["pangu_kg_similar_patterns"] = handle_kg_similar_patterns