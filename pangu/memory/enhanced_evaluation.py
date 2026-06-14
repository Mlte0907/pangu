"""盘古增强评估 — LLM 驱动矛盾检测 + 轨迹追踪

从伏羲移植：
1. LLM Judge 矛盾检测 — 6种裁决类型
2. 轨迹追踪 — 追踪记忆的时间演变，检测回归
3. 评估缓存 — 避免重复 LLM 调用

纯大脑能力：只做评估和检测，不执行任务。
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("pangu.memory.enhanced_evaluation")

VERDICTS = {
    "contradiction": "真正的矛盾",
    "temporal_supersession": "新 claim 替代旧 claim（正常）",
    "temporal_regression": "指标/状态倒退（需标记）",
    "temporal_evolution": "合法的时间演变",
    "negation_artifact": "LLM 误读否定词（数据正确）",
    "no_contradiction": "兼容",
}


class EvaluationCache:
    """评估结果缓存，避免重复 LLM 调用"""

    def __init__(self, cache_path: str = "~/.pangu/evaluation_cache.jsonl"):
        self.cache_path = Path(cache_path).expanduser()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, prompt_hash: str) -> dict | None:
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path) as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("hash") == prompt_hash:
                        return entry
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache read error: {e}")
        return None

    def put(self, prompt_hash: str, verdict: str, confidence: float) -> None:
        try:
            with open(self.cache_path, "a") as f:
                f.write(json.dumps({
                    "hash": prompt_hash,
                    "verdict": verdict,
                    "confidence": confidence,
                    "timestamp": datetime.now().isoformat(),
                }) + "\n")
        except OSError as e:
            logger.warning(f"Cache write error: {e}")


class EnhancedContradictionDetector:
    """增强矛盾检测器 — LLM Judge + 启发式降级"""

    def __init__(self, config=None):
        self.config = config
        self._llm_engine = None
        self.cache = EvaluationCache()

    @property
    def llm_engine(self):
        if self._llm_engine is None:
            try:
                from ..core.llm import LLMEngine
                self._llm_engine = LLMEngine(self.config)
            except ImportError:
                self._llm_engine = None
        return self._llm_engine

    def detect_contradictions(self, drawers: list, top_k: int = 50) -> dict:
        """检测记忆对之间的矛盾

        Returns:
            {"verdicts": [...], "stats": {...}}
        """
        # 按重要性排序，取 top_k
        sorted_drawers = sorted(drawers, key=lambda d: d.importance, reverse=True)[:top_k]

        if len(sorted_drawers) < 2:
            return {"verdicts": [], "stats": {"reason": "insufficient_items"}}

        verdicts = []
        for i in range(min(10, len(sorted_drawers) - 1)):
            for j in range(i + 1, min(15, len(sorted_drawers))):
                text_a = sorted_drawers[i].content[:500]
                text_b = sorted_drawers[j].content[:500]

                combined = text_a + "|||" + text_b
                prompt_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]

                cached = self.cache.get(prompt_hash)
                if cached:
                    verdicts.append({
                        "source_id": sorted_drawers[i].id,
                        "target_id": sorted_drawers[j].id,
                        "verdict": cached["verdict"],
                        "confidence": cached.get("confidence", 1.0),
                        "cached": True,
                    })
                    continue

                verdict, confidence = self._judge(text_a, text_b)
                self.cache.put(prompt_hash, verdict, confidence)

                verdicts.append({
                    "source_id": sorted_drawers[i].id,
                    "target_id": sorted_drawers[j].id,
                    "verdict": verdict,
                    "confidence": confidence,
                    "cached": False,
                })

        stats = self._compute_stats(verdicts)
        return {"verdicts": verdicts, "stats": stats}

    def _judge(self, text_a: str, text_b: str) -> tuple[str, float]:
        """LLM 判断两个记忆是否存在矛盾"""
        if self.llm_engine:
            try:
                prompt = f"""判断以下两段记忆是否存在矛盾。

记忆A: {text_a}

记忆B: {text_b}

请用以下 JSON 格式输出：
{{"verdict": "contradiction|temporal_supersession|temporal_regression|temporal_evolution|negation_artifact|no_contradiction", "confidence": 0.0-1.0, "reasoning": "一句话理由"}}

裁决说明：
- contradiction: 真正的矛盾
- temporal_supersession: 新 claim 替代旧 claim（正常）
- temporal_regression: 指标/状态倒退
- temporal_evolution: 合法的时间演变
- negation_artifact: LLM 误读否定词
- no_contradiction: 兼容"""
                resp = self.llm_engine.chat([{"role": "user", "content": prompt}])
                if resp and resp.content:
                    data = json.loads(resp.content)
                    return data.get("verdict", "no_contradiction"), float(data.get("confidence", 0.5))
            except Exception as e:
                logger.debug(f"LLM judge failed: {e}")

        return self._simple_judge(text_a, text_b)

    def _simple_judge(self, text_a: str, text_b: str) -> tuple[str, float]:
        """简单的启发式矛盾判断"""
        _negations = {"不", "没", "否", "非", "无", "不是", "没有", "不会", "不能"}

        regression_keywords = ["下降", "倒退", "减少", "恶化", "衰退", "下跌"]
        if any(kw in text_a + text_b for kw in regression_keywords):
            return "temporal_regression", 0.6

        evolution_keywords = ["后来", "最终", "现在", "目前", "最终发现"]
        if any(kw in text_b for kw in evolution_keywords) and any(
            kw in text_a for kw in ["最初", "之前", "起初"]
        ):
            return "temporal_evolution", 0.6

        if any(kw in text_a for kw in ["因为", "导致"]) and any(
            kw in text_b for kw in ["所以", "因此"]
        ):
            return "temporal_supersession", 0.5

        return "no_contradiction", 0.5

    @staticmethod
    def _compute_stats(verdicts: list) -> dict:
        counts = {}
        for v in verdicts:
            counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1

        return {
            "total_pairs": len(verdicts),
            "contradiction": counts.get("contradiction", 0),
            "temporal_regression": counts.get("temporal_regression", 0),
            "temporal_supersession": counts.get("temporal_supersession", 0),
            "temporal_evolution": counts.get("temporal_evolution", 0),
            "negation_artifact": counts.get("negation_artifact", 0),
            "no_contradiction": counts.get("no_contradiction", 0),
        }


class TrajectoryTracker:
    """轨迹追踪器 — 追踪记忆的时间演变

    检测时间线上的事件序列，发现回顾、倒退和演变模式。
    """

    def __init__(self, config=None):
        self.config = config

    def track(self, drawers: list, item_id: str = None,
              wing: str = None, room: str = None) -> dict:
        """追踪记忆的时间轨迹

        Returns:
            {"timeline": [...], "regressions": [...], "stats": {...}}
        """
        events = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if room and d.room != room:
                continue
            if item_id and d.id != item_id:
                continue

            try:
                ts = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                ts = datetime.now()

            events.append({
                "id": d.id,
                "content": d.content[:200],
                "timestamp": ts.isoformat(),
                "importance": d.importance,
                "wing": d.wing,
                "room": d.room,
                "tags": d.tags,
            })

        events.sort(key=lambda e: e["timestamp"])

        # 检测回归
        regressions = self._detect_regressions(events)

        return {
            "timeline": events,
            "total_events": len(events),
            "regressions": regressions,
            "regression_count": len(regressions),
            "span": f"{events[0]['timestamp'][:10]} ~ {events[-1]['timestamp'][:10]}" if events else "无事件",
            "stats": {
                "total_events": len(events),
                "regressions": len(regressions),
                "avg_importance": round(sum(e["importance"] for e in events) / max(len(events), 1), 2),
            },
        }

    def _detect_regressions(self, events: list) -> list[dict]:
        """检测时间线上的倒退模式"""
        regressions = []
        for i in range(1, len(events)):
            prev = events[i - 1]
            curr = events[i]

            # 重要性下降且超过 50%
            if prev["importance"] > 0 and curr["importance"] < prev["importance"] * 0.5:
                regressions.append({
                    "type": "importance_drop",
                    "from": prev["id"],
                    "to": curr["id"],
                    "from_importance": prev["importance"],
                    "to_importance": curr["importance"],
                    "from_time": prev["timestamp"],
                    "to_time": curr["timestamp"],
                })

        return regressions

    def compare_periods(self, drawers: list, period_a: str, period_b: str) -> dict:
        """比较两个时间段的记忆变化"""
        events_a = []
        events_b = []

        for d in drawers:
            try:
                ts = datetime.fromisoformat(d.created_at)
            except (ValueError, TypeError):
                continue

            event = {
                "id": d.id,
                "content": d.content[:200],
                "importance": d.importance,
                "wing": d.wing,
                "tags": d.tags,
            }

            if ts.isoformat()[:10] == period_a:
                events_a.append(event)
            elif ts.isoformat()[:10] == period_b:
                events_b.append(event)

        return {
            "period_a": {"date": period_a, "count": len(events_a)},
            "period_b": {"date": period_b, "count": len(events_b)},
            "delta": len(events_b) - len(events_a),
            "change_pct": round((len(events_b) - len(events_a)) / max(len(events_a), 1) * 100, 1),
        }
