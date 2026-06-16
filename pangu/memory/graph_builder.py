"""盘古记忆图谱构建器 — 自动从记忆中构建和维护知识图谱

核心能力：
1. 实体自动抽取：从记忆内容中自动识别和抽取实体
2. 关系自动发现：自动发现实体之间的关系
3. 图谱质量评估：评估构建的图谱质量
4. 图谱增量更新：新记忆写入时增量更新图谱
5. 图谱统计分析：图谱结构和连接分析
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.graph_builder")


@dataclass
class ExtractedEntity:
    """抽取的实体"""
    name: str
    entity_type: str
    confidence: float
    context: str


@dataclass
class ExtractedRelation:
    """抽取的关系"""
    subject: str
    predicate: str
    object: str
    confidence: float
    source_memory_id: str


class GraphBuilder:
    """记忆图谱构建引擎"""

    ENTITY_PATTERNS = {
        "technology": [
            r'(?:ONNX|FAISS|SQLite|Python|Docker|Redis|PostgreSQL|Nginx|FastAPI|PyTorch|TensorFlow)',
            r'(?:API|SDK|CLI|MCP|REST|gRPC)',
        ],
        "system": [
            r'(?:盘古|伏羲|OpenClaw|羲和|玄女|轩辕)',
            r'(?:记忆系统|知识图谱|搜索引擎|向量索引)',
        ],
        "concept": [
            r'(?:嵌入|向量|推理|检索|巩固|衰减|压缩|聚类|蒸馏|遗忘)',
            r'(?:注意力|上下文|工作记忆|长期记忆|短期记忆)',
        ],
        "person": [
            r'(?:主人|用户|开发者)',
        ],
    }

    RELATION_PATTERNS = [
        (r'(\S+?)(?:是|为|作为)(\S+?)的', "is_a"),
        (r'(\S+?)(?:使用|采用|利用)(\S+?)', "uses"),
        (r'(\S+?)(?:依赖|基于)(\S+?)', "depends_on"),
        (r'(\S+?)(?:包含|含有|拥有)(\S+?)', "contains"),
        (r'(\S+?)(?:提升|优化|增强)(\S+?)', "improves"),
        (r'因为(\S+?).*所以(\S+?)', "causes"),
    ]

    def __init__(self, config=None):
        self.config = config
        self._entities: dict[str, ExtractedEntity] = {}
        self._relations: list[ExtractedRelation] = []
        self._build_history: list[dict] = []

    def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """从文本中抽取实体"""
        entities = []
        for etype, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    name = match.strip()
                    if len(name) >= 2 and name not in [e.name for e in entities]:
                        entities.append(ExtractedEntity(
                            name=name,
                            entity_type=etype,
                            confidence=0.8,
                            context=text[:80],
                        ))
        return entities

    def extract_relations(self, text: str, memory_id: str) -> list[ExtractedRelation]:
        """从文本中抽取关系"""
        relations = []
        for pattern, predicate in self.RELATION_PATTERNS:
            matches = re.finditer(pattern, text)
            for m in matches:
                groups = m.groups()
                if len(groups) >= 2:
                    subj = groups[0].strip()[:20]
                    obj = groups[1].strip()[:20]
                    if len(subj) >= 2 and len(obj) >= 2 and subj != obj:
                        relations.append(ExtractedRelation(
                            subject=subj,
                            predicate=predicate,
                            object=obj,
                            confidence=0.6,
                            source_memory_id=memory_id,
                        ))
        return relations

    def build_from_drawers(self, drawers: list, max_drawers: int = 100) -> dict:
        """从记忆构建图谱"""
        entities_count = 0
        relations_count = 0

        for d in drawers[:max_drawers]:
            entities = self.extract_entities(d.content)
            for e in entities:
                key = f"{e.entity_type}:{e.name}"
                if key not in self._entities:
                    self._entities[key] = e
                    entities_count += 1

            relations = self.extract_relations(d.content, d.id)
            self._relations.extend(relations)
            relations_count += len(relations)

        self._build_history.append({
            "timestamp": datetime.now().isoformat(),
            "drawers_processed": min(len(drawers), max_drawers),
            "entities_added": entities_count,
            "relations_added": relations_count,
        })

        return {
            "entities_added": entities_count,
            "relations_added": relations_count,
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
        }

    def get_entity(self, name: str) -> ExtractedEntity | None:
        """获取实体"""
        for key, entity in self._entities.items():
            if entity.name == name:
                return entity
        return None

    def get_entity_relations(self, name: str) -> list[dict]:
        """获取实体的关系"""
        relations = []
        for r in self._relations:
            if r.subject == name or r.object == name:
                relations.append({
                    "subject": r.subject,
                    "predicate": r.predicate,
                    "object": r.object,
                    "confidence": r.confidence,
                })
        return relations

    def find_path(self, from_name: str, to_name: str, max_depth: int = 3) -> list[dict]:
        """查找两个实体间的路径"""
        visited = set()
        queue = [(from_name, [])]

        for _ in range(max_depth):
            next_queue = []
            for current, path in queue:
                if current in visited:
                    continue
                visited.add(current)

                if current == to_name and path:
                    return path

                for r in self._relations:
                    if r.subject == current and r.object not in visited:
                        next_queue.append((r.object, path + [{"from": r.subject, "via": r.predicate, "to": r.object}]))
                    elif r.object == current and r.subject not in visited:
                        next_queue.append((r.subject, path + [{"from": r.object, "via": r.predicate, "to": r.subject}]))

            queue = next_queue
            if not queue:
                break

        return []

    def assess_quality(self) -> dict:
        """评估图谱质量"""
        total_entities = len(self._entities)
        total_relations = len(self._relations)

        if total_entities == 0:
            return {"quality": 0, "status": "empty"}

        avg_degree = (total_relations * 2) / total_entities if total_entities > 0 else 0
        type_distribution = {}
        for e in self._entities.values():
            type_distribution[e.entity_type] = type_distribution.get(e.entity_type, 0) + 1

        connected = set()
        for r in self._relations:
            connected.add(r.subject)
            connected.add(r.object)
        connectivity = len(connected) / total_entities if total_entities > 0 else 0

        quality = min(1.0, (
            min(1.0, total_entities / 10) * 0.3 +
            min(1.0, total_relations / 20) * 0.3 +
            min(1.0, avg_degree / 3) * 0.2 +
            connectivity * 0.2
        ))

        return {
            "quality": round(quality, 3),
            "total_entities": total_entities,
            "total_relations": total_relations,
            "avg_degree": round(avg_degree, 2),
            "type_distribution": type_distribution,
            "connectivity": round(connectivity, 3),
        }

    def get_graph_stats(self) -> dict:
        """获取图谱统计"""
        return {
            "entities": len(self._entities),
            "relations": len(self._relations),
            "build_count": len(self._build_history),
            "latest_build": self._build_history[-1] if self._build_history else None,
        }


_builder: GraphBuilder | None = None


def get_builder(config=None) -> GraphBuilder:
    """获取全局图谱构建器实例"""
    global _builder
    if _builder is None:
        _builder = GraphBuilder(config)
    return _builder
