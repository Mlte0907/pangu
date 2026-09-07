"""盘古 MemoryJudge — LLM 记忆价值判断

从伏羲移植：Agent 任务完成后，调用 LLM 判断产出是否值得写入长期记忆。
分类决策：A=写 longterm / B=写普通抽屉 / C=标记待复盘

纯大脑能力：不做执行，只做价值判断。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger("pangu.memory.judge")


class JudgmentVerdict(str, Enum):
    A = "A"  # 写入 longterm — 高价值，未来会复用
    B = "B"  # 写入普通区域 — 有参考价值但非关键
    C = "C"  # 标记待复盘 — 不确定，需要后续评估


@dataclass
class JudgmentResult:
    verdict: JudgmentVerdict
    reasoning: str = ""
    confidence: float = 0.5
    suggested_tags: list = field(default_factory=list)
    suggested_importance: float = 0.5
    suggested_wing: str = ""
    suggested_room: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


JUDGMENT_PROMPT = """你是一个记忆价值评估助手。你的任务是判断一个任务产出是否值得存入长期记忆。

评估标准：
- 如果这个产出在未来遇到类似任务时很可能被复用，评 A
- 如果这个产出有参考价值但不是关键知识，评 B
- 如果这个产出是一次性的或价值不确定，评 C

请用以下 JSON 格式输出（只输出 JSON）：
{"verdict": "A/B/C", "reasoning": "一句话理由", "confidence": 0.0-1.0, "tags": ["标签1", "标签2"], "importance": 0.0-1.0}

---

任务类型：{task_type}
任务描述：{task_description}
产出摘要：{output_summary}
"""


class MemoryJudge:
    """记忆价值判断器 — LLM 驱动的 Nudge 决策

    由 Agent 任务完成后调用，判断产出是否值得进入长期记忆。
    """

    def __init__(self, config=None):
        self.config = config
        self._history: list = []  # 最近判断历史
        self._llm_engine = None

    @property
    def llm_engine(self):
        if self._llm_engine is None:
            try:
                from ..core.llm import LLMEngine

                self._llm_engine = LLMEngine(self.config)
            except ImportError:
                self._llm_engine = None
        return self._llm_engine

    def evaluate(
        self,
        task_type: str,
        task_description: str,
        output_summary: str,
        agent_id: str = "",
    ) -> JudgmentResult:
        """评估任务产出是否值得写入长期记忆"""
        prompt = JUDGMENT_PROMPT.format(
            task_type=task_type,
            task_description=task_description,
            output_summary=output_summary[:2000],
        )

        reply = self._call_llm(prompt)
        result = self._parse_reply(reply)

        # 记录判断历史
        self._history.append(
            {
                "task_type": task_type,
                "agent_id": agent_id,
                "verdict": result.verdict.value,
                "confidence": result.confidence,
                "ts": result.timestamp,
            }
        )
        if len(self._history) > 50:
            self._history = self._history[-50:]

        return result

    def evaluate_batch(
        self,
        items: list[dict],
        agent_id: str = "",
    ) -> list[JudgmentResult]:
        """批量评估多个产出"""
        results = []
        for item in items:
            result = self.evaluate(
                task_type=item.get("task_type", "unknown"),
                task_description=item.get("description", ""),
                output_summary=item.get("summary", ""),
                agent_id=agent_id,
            )
            results.append(result)
        return results

    def _call_llm(self, prompt: str) -> str | None:
        """调用 LLM 进行判断"""
        if not self.llm_engine:
            return None

        try:
            resp = self.llm_engine.chat([{"role": "user", "content": prompt}])
            return resp.content.strip() if resp else None
        except Exception as e:
            logger.debug(f"MemoryJudge LLM call failed: {e}")
        return None

    def _parse_reply(self, reply: str | None) -> JudgmentResult:
        """解析 LLM 返回的判断 JSON"""
        if not reply:
            return self._fallback_judgment()

        try:
            data = json.loads(reply)
        except json.JSONDecodeError:
            m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', reply)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    return self._fallback_judgment()
            else:
                return self._fallback_judgment()

        verdict_str = data.get("verdict", "B").upper()
        try:
            verdict = JudgmentVerdict(verdict_str)
        except ValueError:
            verdict = JudgmentVerdict.B

        return JudgmentResult(
            verdict=verdict,
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.5)),
            suggested_tags=data.get("tags", []),
            suggested_importance=float(data.get("importance", 0.5)),
        )

    def _fallback_judgment(self) -> JudgmentResult:
        """LLM 不可用时的降级判断 — 默认 B（写入普通区域）"""
        return JudgmentResult(
            verdict=JudgmentVerdict.B,
            reasoning="LLM 不可用，默认写入普通区域",
            confidence=0.3,
        )

    def apply_verdict(
        self,
        result: JudgmentResult,
        content: str,
        agent_id: str = "",
        wing_override: str = None,
        room_override: str = None,
    ) -> dict:
        """执行判断结果 — 将记忆写入对应位置

        A → longterm wing
        B → {agent_id} wing 或 default
        C → default，标记待复盘
        """
        if wing_override:
            wing = wing_override
        elif result.verdict == JudgmentVerdict.A:
            wing = "longterm"
        elif result.verdict == JudgmentVerdict.B:
            wing = f"{agent_id}_agent" if agent_id else "default"
        else:
            wing = "default"

        room = room_override or "general"
        tags = result.suggested_tags + ["judged", result.verdict.value]
        importance = result.suggested_importance

        if result.verdict == JudgmentVerdict.C:
            tags.append("待复盘")
            importance = max(0.3, importance)

        return {
            "wing": wing,
            "room": room,
            "importance": importance,
            "tags": tags,
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        }

    @property
    def history(self) -> list:
        return list(self._history)

    def stats(self) -> dict:
        """判断统计"""
        if not self._history:
            return {"total": 0, "A": 0, "B": 0, "C": 0}

        counts = {"A": 0, "B": 0, "C": 0}
        for h in self._history:
            counts[h["verdict"]] = counts.get(h["verdict"], 0) + 1

        return {
            "total": len(self._history),
            "A": counts["A"],
            "B": counts["B"],
            "C": counts["C"],
            "A_ratio": round(counts["A"] / len(self._history), 2) if self._history else 0,
        }


_judge: MemoryJudge | None = None


def get_memory_judge(config=None) -> MemoryJudge:
    """获取记忆判断器单例"""
    global _judge
    if _judge is None:
        _judge = MemoryJudge(config)
    return _judge
