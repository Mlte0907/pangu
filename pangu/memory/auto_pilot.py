"""盘古自动驾驶模式 — 接入后自动完成记忆管理

核心能力：
1. 自动捕获：监控文件变更，自动提取重要修改存入记忆
2. 自动组织：新记忆自动打标签、自动关联
3. 自动推荐：基于当前上下文主动推送相关记忆
4. 自动维护：定期执行融合、衰减、压缩
5. 自动报告：每日自动生成记忆使用报告
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.auto_pilot")


class AutoPilot:
    """自动驾驶模式 — 接入后自动管理记忆"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._state_file = Path(self.config.palace_path) / "auto_pilot_state.json"
        self._state = self._load_state()
        self._active = False

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_capture": None,
            "last_organize": None,
            "last_suggest": None,
            "last_maintain": None,
            "last_report": None,
            "capture_count": 0,
            "organize_count": 0,
            "suggest_count": 0,
            "maintain_count": 0,
        }

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存自动驾驶状态失败: {e}")

    def activate(self) -> dict:
        """激活自动驾驶模式"""
        self._active = True
        self._save_state()
        logger.info("Auto-Pilot activated")
        return {"status": "activated", "message": "自动驾驶模式已激活，将自动管理记忆"}

    def deactivate(self) -> dict:
        """停用自动驾驶模式"""
        self._active = False
        self._save_state()
        return {"status": "deactivated"}

    def tick(self, drawers: list[Drawer] = None) -> dict:
        """自动驾驶 tick — 检查并执行所有自动任务"""
        if not self._active:
            return {"status": "inactive"}

        results = {"tasks_run": [], "tasks_skipped": []}

        # 1. 自动组织
        if self._should_run("organize", interval=300):
            organize_result = self.auto_organize(drawers)
            results["tasks_run"].append({"task": "organize", "result": organize_result})
            self._state["last_organize"] = datetime.now().isoformat()
            self._state["organize_count"] += 1

        # 2. 自动维护
        if self._should_run("maintain", interval=3600):
            maintain_result = self.auto_maintain()
            results["tasks_run"].append({"task": "maintain", "result": maintain_result})
            self._state["last_maintain"] = datetime.now().isoformat()
            self._state["maintain_count"] += 1

        # 3. 自动生成报告
        if self._should_run("report", interval=86400):
            report = self.auto_report(drawers)
            results["tasks_run"].append({"task": "report", "result": report})
            self._state["last_report"] = datetime.now().isoformat()

        self._save_state()
        results["tasks_count"] = len(results["tasks_run"])
        return results

    def auto_organize(self, drawers: list[Drawer] = None) -> dict:
        """自动组织：给无标签记忆打标签"""
        if drawers is None:
            drawers = self._load_drawers()

        tagged = 0
        for d in drawers:
            if not d.tags or len(d.tags) == 0:
                tags = self._infer_tags(d)
                if tags:
                    d.tags = tags
                    tagged += 1

        if tagged > 0:
            self._save_drawers(drawers)

        return {"tagged": tagged, "total": len(drawers)}

    def auto_suggest(self, context: str = "", drawers: list[Drawer] = None,
                     limit: int = 5) -> dict:
        """自动推荐：基于当前上下文主动推送相关记忆"""
        if not context and not drawers:
            return {"suggestions": [], "reason": "no context"}

        if drawers is None:
            drawers = self._load_drawers()

        suggestions = []
        query_words = set(context.lower().split()) if context else set()

        for d in drawers:
            score = 0.0
            content_lower = (d.content or "").lower()

            # 关键词匹配
            for w in query_words:
                if w in content_lower:
                    score += 0.3

            # 标签匹配
            for tag in (d.tags or []):
                if tag.lower() in context.lower():
                    score += 0.2

            # 重要性加成
            score += (d.importance or 0) * 0.1

            if score > 0.2:
                suggestions.append({
                    "id": d.id,
                    "content": (d.content or "")[:100],
                    "wing": d.wing,
                    "importance": d.importance,
                    "score": round(score, 3),
                    "reason": self._generate_reason(d, context),
                })

        suggestions.sort(key=lambda x: -x["score"])

        # 解密内容
        try:
            import importlib
            encryption_mod = importlib.import_module("pangu.memory.encryption")
            decrypt = encryption_mod.decrypt
            for s in suggestions:
                c = s.get("content", "")
                if c and c.startswith("gAAAAAB"):
                    try:
                        s["content"] = decrypt(c)
                    except Exception:
                        pass
        except Exception:
            pass

        return {"suggestions": suggestions[:limit], "total_matches": len(suggestions)}

    def auto_maintain(self) -> dict:
        """自动维护：执行融合、衰减、质量检查"""
        results = {}

        try:
            from .autonomous import get_autonomous_engine
            engine = get_autonomous_engine(self.config)
            cycle = engine.run_cycle()
            results["maintenance"] = {
                "tasks_run": cycle.tasks_run,
                "tasks_failed": cycle.tasks_failed,
                "duration_ms": cycle.total_duration_ms,
            }
        except Exception as e:
            results["maintenance"] = {"error": str(e)}

        return results

    def auto_report(self, drawers: list[Drawer] = None) -> dict:
        """自动生成记忆使用报告"""
        if drawers is None:
            drawers = self._load_drawers()

        total = len(drawers)
        by_wing = defaultdict(int)
        by_modality = defaultdict(int)
        recent_count = 0
        now = datetime.now()

        for d in drawers:
            by_wing[d.wing] += 1
            mod = d.metadata.get("modality", "text")
            by_modality[mod] += 1

            try:
                created = datetime.fromisoformat(d.created_at)
                if (now - created).days <= 1:
                    recent_count += 1
            except Exception:
                pass

        report = {
            "date": now.strftime("%Y-%m-%d"),
            "total_memories": total,
            "recent_24h": recent_count,
            "top_wings": dict(sorted(by_wing.items(), key=lambda x: -x[1])[:5]),
            "modality_distribution": dict(by_modality),
        }

        self._state["last_report"] = now.isoformat()
        self._save_state()
        return report

    def get_proactive_suggestion(self, current_task: str = "") -> dict:
        """基于当前任务主动推荐"""
        drawers = self._load_drawers()
        if not drawers:
            return {"suggestion": "暂无记忆可推荐"}

        query = current_task.lower()
        relevant = []

        for d in drawers:
            content = (d.content or "").lower()
            if any(w in content for w in query.split() if len(w) >= 2):
                relevant.append(d)

        if not relevant:
            return {"suggestion": f"未找到与「{current_task}」相关的记忆", "count": 0}

        relevant.sort(key=lambda x: -(x.importance or 0))
        top = relevant[:3]

        suggestion_parts = [f"发现 {len(relevant)} 条相关记忆，推荐以下 {len(top)} 条："]
        for d in top:
            suggestion_parts.append(f"  - [{d.wing}] {(d.content or '')[:80]}")

        return {
            "suggestion": "\n".join(suggestion_parts),
            "count": len(relevant),
            "top_ids": [d.id for d in top],
        }

    def get_status(self) -> dict:
        """获取自动驾驶状态"""
        return {
            "active": self._active,
            "last_capture": self._state.get("last_capture"),
            "last_organize": self._state.get("last_organize"),
            "last_maintain": self._state.get("last_maintain"),
            "last_report": self._state.get("last_report"),
            "capture_count": self._state.get("capture_count", 0),
            "organize_count": self._state.get("organize_count", 0),
            "maintain_count": self._state.get("maintain_count", 0),
        }

    def _should_run(self, task: str, interval: int = 300) -> bool:
        last = self._state.get(f"last_{task}", None)
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            return (datetime.now() - last_dt).total_seconds() >= interval
        except Exception:
            return True

    def _infer_tags(self, drawer: Drawer) -> list[str]:
        """基于内容推断标签"""
        content = (drawer.content or "").lower()
        tags = []

        tech_kw = {"python", "java", "docker", "git", "api", "bug", "deploy", "config", "server", "database"}
        product_kw = {"需求", "功能", "用户", "产品", "体验", "PRD"}
        team_kw = {"会议", "讨论", "决策", "分工", "协作"}

        if any(kw in content for kw in tech_kw):
            tags.append("tech")
        if any(kw in content for kw in product_kw):
            tags.append("product")
        if any(kw in content for kw in team_kw):
            tags.append("team")
        if not tags:
            tags.append("auto_tagged")

        return tags

    def _generate_reason(self, drawer: Drawer, context: str) -> str:
        content = (drawer.content or "").lower()
        matched = [w for w in context.lower().split() if w in content]
        if matched:
            return f"包含关键词: {', '.join(matched[:3])}"
        return f"与当前上下文相关 (重要性: {drawer.importance})"

    def _load_drawers(self) -> list[Drawer]:
        if not self._drawers_file.exists():
            return []
        try:
            with open(self._drawers_file, encoding="utf-8") as f:
                return [Drawer.from_dict(d) for d in json.load(f)]
        except Exception:
            return []

    @property
    def _drawers_file(self):
        return Path(self.config.palace_path) / "drawers.json"

    def _save_drawers(self, drawers: list[Drawer]):
        try:
            with open(self._drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")


_pilot: AutoPilot | None = None


def get_auto_pilot(config: PanguConfig = None) -> AutoPilot:
    global _pilot
    if _pilot is None:
        _pilot = AutoPilot(config)
    return _pilot
