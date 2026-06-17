"""盘古图推理引擎 — 基于知识图谱的推理能力

核心功能：
1. 实体识别：从文本中提取实体
2. 路径查找：查找实体间的关联路径
3. 规则推理：基于边类型进行逻辑推理
4. 语义推理：基于向量相似度推断隐含关系
5. 因果链分析：追溯因果关系链
6. 时序推理：基于时间线推断因果关系
7. 矛盾检测：检测图中的矛盾关系
8. 推理链可视化：展示推理过程和依据
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.config import PanguConfig
from .knowledge_graph import KnowledgeGraph

logger = logging.getLogger("pangu.memory.graph_reasoning")


@dataclass
class InferenceResult:
    """推理结果"""
    query: str
    entities: list[dict]
    paths: list[list[dict]]
    inferences: list[dict]
    confidence: float
    reasoning_chain: list[str]


class GraphReasoning:
    """图推理引擎 — 基于知识图谱的推理"""

    # 推理规则：如果 A→B 且 B→C，则 A→C
    INFERENCE_RULES = {
        "causes": ["causes", "enables", "depends_on"],
        "enables": ["enables", "related_to"],
        "depends_on": ["depends_on", "related_to"],
        "related_to": ["related_to"],
    }

    # 矛盾关系
    CONTRADICTION_PAIRS = [
        ("causes", "hinders"),
        ("enables", "hinders"),
        ("supports", "contradicts"),
    ]

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.kg = KnowledgeGraph(config)

    def infer(self, query: str) -> InferenceResult:
        """基于图谱推理回答问题

        Args:
            query: 查询文本

        Returns:
            InferenceResult 包含实体、路径、推理结果
        """
        reasoning_chain = []

        # 1. 实体识别
        entities = self._extract_entities(query)
        reasoning_chain.append(f"识别到 {len(entities)} 个实体: {[e.get('name', '') for e in entities]}")

        # 2. 路径查找
        paths = []
        if len(entities) >= 2:
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    path = self.kg.find_path(
                        entities[i]["id"],
                        entities[j]["id"],
                        max_depth=3
                    )
                    if path:
                        paths.extend(path)
                        reasoning_chain.append(
                            f"找到路径: {entities[i].get('name', '')} → {entities[j].get('name', '')}"
                        )

        # 3. 规则推理
        inferences = self._apply_rules(entities, paths)
        if inferences:
            reasoning_chain.append(f"规则推理: 推导出 {len(inferences)} 个新关系")

        # 4. 计算置信度
        confidence = self._calculate_confidence(entities, paths, inferences)

        return InferenceResult(
            query=query,
            entities=entities,
            paths=paths,
            inferences=inferences,
            confidence=confidence,
            reasoning_chain=reasoning_chain,
        )

    def _extract_entities(self, text: str) -> list[dict]:
        """从文本中提取实体"""
        entities = []
        all_entities = self.kg.list_entities()

        for entity in all_entities:
            name = entity.get("name", "")
            if name and name.lower() in text.lower():
                entities.append(entity)

        return entities

    def _apply_rules(self, entities: list[dict], paths: list[list[dict]]) -> list[dict]:
        """基于规则推理"""
        inferences = []

        for path in paths:
            if len(path) < 2:
                continue

            # 检查传递性：A→B→C ⟹ A→C
            for i in range(len(path) - 1):
                rel_a = path[i]
                rel_b = path[i + 1]

                pred_a = rel_a.get("predicate", "")
                pred_b = rel_b.get("predicate", "")

                # 如果两个关系可以传递，则推导出新关系
                if pred_b in self.INFERENCE_RULES.get(pred_a, []):
                    inferences.append({
                        "type": "transitivity",
                        "source": pred_a,
                        "target": pred_b,
                        "inferred": pred_a,
                        "from_entity": rel_a.get("subject_id", ""),
                        "to_entity": rel_b.get("object_id", ""),
                        "confidence": rel_a.get("confidence", 1.0) * rel_b.get("confidence", 1.0),
                    })

        return inferences

    def _calculate_confidence(
        self,
        entities: list[dict],
        paths: list[list[dict]],
        inferences: list[dict],
    ) -> float:
        """计算推理置信度"""
        if not entities:
            return 0.0

        # 实体覆盖度
        entity_score = min(len(entities) / 3, 1.0)

        # 路径覆盖度
        path_score = min(len(paths) / 2, 1.0) if paths else 0.0

        # 推理质量
        inference_score = 0.0
        if inferences:
            avg_conf = sum(i.get("confidence", 0) for i in inferences) / len(inferences)
            inference_score = avg_conf

        # 综合置信度
        confidence = entity_score * 0.3 + path_score * 0.3 + inference_score * 0.4
        return round(confidence, 3)

    def causal_chain_analysis(self, entity_id: str, max_depth: int = 5) -> list[dict]:
        """因果链分析 — 追溯因果关系链

        Args:
            entity_id: 起始实体 ID
            max_depth: 最大追溯深度

        Returns:
            因果链列表
        """
        chain = []
        current = entity_id
        visited = set()

        for _ in range(max_depth):
            if current in visited:
                break
            visited.add(current)

            entity = self.kg.get_entity(current)
            if not entity:
                break

            # 查找因果关系
            relations = self.kg.query_relations(subject_id=current)
            causal_rels = [r for r in relations if r.get("predicate") in ("causes", "enables", "leads_to")]

            if causal_rels:
                for rel in causal_rels[:2]:  # 只取前2个因果关系
                    chain.append({
                        "entity": entity.get("name", ""),
                        "relation": rel.get("predicate", ""),
                        "target": rel.get("object_id", ""),
                        "confidence": rel.get("confidence", 1.0),
                    })
                    current = rel.get("object_id", "")
                    break
            else:
                break

        return chain

    def temporal_reasoning(self, query: str) -> dict:
        """时序推理 — 基于时间线推断因果关系

        Args:
            query: 查询文本

        Returns:
            时序推理结果
        """
        # 提取时间相关的实体
        time_entities = []
        all_entities = self.kg.list_entities()

        time_patterns = [
            r'(\d{4})年',
            r'(\d{1,2})月',
            r'(\d{1,2})日',
            r'昨天', r'今天', r'明天',
            r'上周', r'本周', r'下周',
        ]

        for entity in all_entities:
            name = entity.get("name", "")
            for pattern in time_patterns:
                if re.search(pattern, name):
                    time_entities.append(entity)
                    break

        # 分析时序关系
        temporal_relations = []
        for i, e1 in enumerate(time_entities):
            for e2 in time_entities[i+1:]:
                # 查找两个实体间的关系
                relations = self.kg.query_relations(
                    subject_id=e1["id"],
                    object_id=e2["id"]
                )
                if relations:
                    temporal_relations.append({
                        "from": e1.get("name", ""),
                        "to": e2.get("name", ""),
                        "relation": relations[0].get("predicate", ""),
                    })

        return {
            "time_entities": len(time_entities),
            "temporal_relations": temporal_relations,
            "chain": temporal_relations[:5],
        }

    def analogy_detection(self, query: str) -> dict:
        """类比检测 — 发现不同领域的相似模式

        Args:
            query: 查询文本

        Returns:
            类比检测结果
        """
        entities = self._extract_entities(query)
        if len(entities) < 2:
            return {"analogies": [], "count": 0}

        # 查找不同类型的实体间的相似关系
        analogies = []
        entity_types = set(e.get("type", "") for e in entities)

        if len(entity_types) >= 2:
            for e1 in entities:
                for e2 in entities:
                    if e1.get("type") != e2.get("type"):
                        self._find_analogy_pair(e1, e2, analogies)

        return {"analogies": analogies[:5], "count": len(analogies)}

    def _find_analogy_pair(self, e1, e2, analogies):
        rels1 = self.kg.query_relations(subject_id=e1["id"])
        rels2 = self.kg.query_relations(subject_id=e2["id"])
        pred1 = set(r.get("predicate", "") for r in rels1)
        pred2 = set(r.get("predicate", "") for r in rels2)
        common = pred1 & pred2
        if common:
            analogies.append({
                "entity1": e1.get("name", ""),
                "entity2": e2.get("name", ""),
                "common_relations": list(common),
                "type1": e1.get("type", ""),
                "type2": e2.get("type", ""),
            })

    def detect_contradictions(self) -> list[dict]:
        """检测图中的矛盾关系"""
        contradictions = []
        all_relations = []

        # 获取所有关系
        with self.kg._conn() as conn:
            rows = conn.execute("SELECT * FROM relations").fetchall()
            all_relations = [dict(r) for r in rows]

        # 检查矛盾对
        for i, rel_a in enumerate(all_relations):
            for rel_b in all_relations[i + 1:]:
                result = self._check_relation_contradiction(rel_a, rel_b)
                if result:
                    contradictions.append(result)

        return contradictions

    def _check_relation_contradiction(self, rel_a: dict, rel_b: dict) -> dict | None:
        pred_a = rel_a.get("predicate", "")
        pred_b = rel_b.get("predicate", "")
        for p1, p2 in self.CONTRADICTION_PAIRS:
            if (pred_a == p1 and pred_b == p2) or (pred_a == p2 and pred_b == p1):
                if (rel_a.get("subject_id") == rel_b.get("subject_id") or
                    rel_a.get("object_id") == rel_b.get("object_id")):
                    return {
                        "relation_a": rel_a,
                        "relation_b": rel_b,
                        "type": f"{pred_a} vs {pred_b}",
                        "severity": "major",
                    }
        return None

    def get_reasoning_summary(self, result: InferenceResult) -> str:
        """生成推理摘要"""
        lines = [f"查询: {result.query}"]
        lines.append(f"置信度: {result.confidence:.1%}")

        if result.entities:
            lines.append(f"实体: {', '.join(e.get('name', '') for e in result.entities)}")

        if result.paths:
            lines.append(f"找到 {len(result.paths)} 条路径")

        if result.inferences:
            lines.append(f"推导出 {len(result.inferences)} 个新关系")
            for inf in result.inferences[:3]:
                lines.append(f"  - {inf.get('inferred', '')}: {inf.get('from_entity', '')} → {inf.get('to_entity', '')}")

        if result.reasoning_chain:
            lines.append("推理过程:")
            for step in result.reasoning_chain:
                lines.append(f"  {step}")

        return "\n".join(lines)

    def visualize_reasoning(self, result: InferenceResult) -> dict:
        """可视化推理过程 — 生成结构化的推理展示"""
        visualization = {
            "query": result.query,
            "confidence": result.confidence,
            "steps": [],
            "entities": [],
            "paths": [],
            "conclusions": [],
        }

        # 实体可视化
        for entity in result.entities:
            visualization["entities"].append({
                "id": entity.get("id", ""),
                "name": entity.get("name", ""),
                "type": entity.get("type", ""),
            })

        # 路径可视化
        for path in result.paths:
            path_viz = []
            for rel in path:
                path_viz.append({
                    "from": rel.get("subject_id", ""),
                    "relation": rel.get("predicate", ""),
                    "to": rel.get("object_id", ""),
                })
            visualization["paths"].append(path_viz)

        # 推理步骤
        for i, step in enumerate(result.reasoning_chain):
            visualization["steps"].append({
                "step": i + 1,
                "description": step,
            })

        # 结论
        if result.inferences:
            for inf in result.inferences:
                visualization["conclusions"].append({
                    "type": inf.get("type", ""),
                    "statement": f"{inf.get('from_entity', '')} → {inf.get('to_entity', '')}",
                    "confidence": inf.get("confidence", 0),
                })

        return visualization
