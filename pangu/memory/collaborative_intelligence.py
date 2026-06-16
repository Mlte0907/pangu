"""盘古多 Agent 协作智能 — Agent 间知识共享和协作推理

核心能力：
1. 知识共享：Agent 间共享记忆和发现
2. 协作推理：多 Agent 联合推理
3. 分工协调：根据 Agent 专长分配任务
4. 冲突解决：解决 Agent 间知识冲突
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("pangu.memory.collaborative_intelligence")


@dataclass
class AgentProfile:
    """Agent 画像"""
    agent_id: str
    name: str
    specialties: list[str]  # 专长领域
    shared_knowledge: list[str]  # 共享的知识 ID
    trust_score: float = 0.8  # 信任度


@dataclass
class CollaborationResult:
    """协作结果"""
    task: str
    participants: list[str]
    shared_findings: list[dict]
    consensus: str
    confidence: float


class CollaborativeIntelligence:
    """协作智能引擎"""

    def __init__(self, config=None):
        self.config = config
        self._agents: dict[str, AgentProfile] = {}
        self._shared_knowledge: dict[str, list[str]] = {}
        self._collaboration_history: list[dict] = []

    def register_agent(self, agent_id: str, name: str, specialties: list[str] = None) -> dict:
        """注册 Agent"""
        self._agents[agent_id] = AgentProfile(
            agent_id=agent_id,
            name=name,
            specialties=specialties or [],
            shared_knowledge=[],
        )
        return {"agent_id": agent_id, "name": name, "status": "registered"}

    def share_knowledge(self, from_agent: str, to_agent: str, knowledge_ids: list[str]) -> dict:
        """Agent 间共享知识"""
        if from_agent not in self._agents:
            return {"error": f"Agent {from_agent} not found"}
        if to_agent not in self._agents:
            return {"error": f"Agent {to_agent} not found"}

        shared_count = 0
        for kid in knowledge_ids:
            if kid not in self._shared_knowledge:
                self._shared_knowledge[kid] = []
            if to_agent not in self._shared_knowledge[kid]:
                self._shared_knowledge[kid].append(to_agent)
                shared_count += 1

        self._agents[to_agent].shared_knowledge.extend(knowledge_ids)

        return {
            "from": from_agent,
            "to": to_agent,
            "shared": shared_count,
            "total_shared": len(self._agents[to_agent].shared_knowledge),
        }

    def find_best_agent(self, task_domain: str) -> dict | None:
        """找到最适合某任务的 Agent"""
        best = None
        best_score = 0

        for agent in self._agents.values():
            score = 0
            for spec in agent.specialties:
                if spec.lower() in task_domain.lower() or task_domain.lower() in spec.lower():
                    score += 2
            score += agent.trust_score

            if score > best_score:
                best_score = score
                best = agent

        if best:
            return {
                "agent_id": best.agent_id,
                "name": best.name,
                "score": best_score,
                "specialties": best.specialties,
            }
        return None

    def collaborative_reasoning(self, task: str, agent_ids: list[str] = None) -> CollaborationResult:
        """协作推理"""
        participants = agent_ids or list(self._agents.keys())[:3]

        findings = []
        for agent_id in participants:
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                findings.append({
                    "agent": agent.name,
                    "domain": agent.specialties[:2] if agent.specialties else ["general"],
                    "shared_knowledge_count": len(agent.shared_knowledge),
                })

        consensus = f"基于 {len(participants)} 个 Agent 的协作分析"
        confidence = min(0.9, 0.5 + len(participants) * 0.1)

        result = CollaborationResult(
            task=task,
            participants=participants,
            shared_findings=findings,
            consensus=consensus,
            confidence=confidence,
        )

        self._collaboration_history.append({
            "task": task,
            "participants": participants,
            "timestamp": datetime.now().isoformat(),
            "confidence": confidence,
        })

        return result

    def resolve_conflict(self, agent_a_id: str, agent_b_id: str, topic: str) -> dict:
        """解决 Agent 间知识冲突"""
        agent_a = self._agents.get(agent_a_id)
        agent_b = self._agents.get(agent_b_id)

        if not agent_a or not agent_b:
            return {"error": "Agent not found"}

        if agent_a.trust_score > agent_b.trust_score:
            winner = agent_a
            loser = agent_b
        elif agent_b.trust_score > agent_a.trust_score:
            winner = agent_b
            loser = agent_a
        else:
            winner = agent_a
            loser = agent_b

        winner.trust_score = min(1.0, winner.trust_score + 0.05)
        loser.trust_score = max(0.1, loser.trust_score - 0.03)

        return {
            "topic": topic,
            "winner": winner.name,
            "loser": loser.name,
            "winner_trust": winner.trust_score,
            "loser_trust": loser.trust_score,
        }

    def get_agent_stats(self) -> dict:
        """获取 Agent 统计"""
        return {
            "total_agents": len(self._agents),
            "shared_knowledge_count": len(self._shared_knowledge),
            "collaboration_count": len(self._collaboration_history),
            "agents": [
                {"id": a.agent_id, "name": a.name, "trust": a.trust_score,
                 "specialties": a.specialties, "shared": len(a.shared_knowledge)}
                for a in self._agents.values()
            ],
        }


_collaborative: CollaborativeIntelligence | None = None


def get_collaborative(config=None) -> CollaborativeIntelligence:
    """获取全局协作智能实例"""
    global _collaborative
    if _collaborative is None:
        _collaborative = CollaborativeIntelligence(config)
    return _collaborative
