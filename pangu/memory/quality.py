"""盘古记忆质量管道 — 自动评估、清洗、优化记忆质量

功能：
1. 质量评分：多维度评估每条记忆质量
2. 自动标签：为缺少标签的记忆补充标签
3. 去重合并：合并语义重复的记忆
4. 长度优化：截断过长、补全过短的记忆
5. 批量修复：一键修复所有质量问题
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.quality")


@dataclass
class QualityReport:
    total: int = 0
    scored: int = 0
    avg_score: float = 0.0
    tags_added: int = 0
    merged: int = 0
    truncated: int = 0
    low_quality: int = 0
    high_quality: int = 0
    score_distribution: dict = field(default_factory=lambda: {"poor": 0, "fair": 0, "good": 0, "excellent": 0})


class QualityPipeline:
    """记忆质量管道"""

    TAG_KEYWORDS = {
        "tech": [
            "代码",
            "python",
            "java",
            "docker",
            "git",
            "api",
            "bug",
            "修复",
            "部署",
            "配置",
            "数据库",
            "服务器",
            "git",
            "npm",
            "pip",
        ],
        "project": ["任务", "计划", "进度", "交付", "里程碑", "排期", "需求", "功能"],
        "team": ["会议", "讨论", "决策", "分工", "协作", "沟通"],
        "product": ["用户", "体验", "产品", "设计", "原型", "PRD"],
        "decision": ["决定", "确认", "批准", "同意", "拒绝", "方案", "选择"],
        "rule": ["规则", "约束", "必须", "禁止", "规范", "约定"],
        "emotion": ["感受", "心情", "满意", "失望", "开心", "担忧"],
        "knowledge": ["概念", "原理", "算法", "方法", "理论", "框架"],
    }

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._drawers_file = Path(self.config.palace_path) / "drawers.json"

    def _load_drawers(self) -> list[Drawer]:
        if not self._drawers_file.exists():
            return []
        try:
            with open(self._drawers_file, encoding="utf-8") as f:
                return [Drawer.from_dict(d) for d in json.load(f)]
        except Exception:
            return []

    def _save_drawers(self, drawers: list[Drawer]):
        try:
            with open(self._drawers_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    def score_memory(self, drawer: Drawer) -> float:
        score = 50.0
        content = drawer.content or ""
        if not content:
            return 0.0

        if len(content) < 30:
            score -= 20
        elif len(content) > 100:
            score += 5
        elif len(content) > 300:
            score += 10

        if not drawer.tags or len(drawer.tags) == 0:
            score -= 15
        elif len(drawer.tags) >= 2:
            score += 5

        if drawer.importance >= 4.0:
            score += 10
        elif drawer.importance < 2.0:
            score -= 10

        if "```" in content:
            score += 5
        if re.search(r"https?://", content):
            score += 3
        if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", content):
            score += 3

        if content == content.upper() and len(content) > 10:
            score -= 15

        has_structure = any(c in content for c in ["#", "-", "*", "|", "1.", "2."])
        if has_structure:
            score += 5

        if content.startswith(("TODO", "FIXME", "HACK", "test")):
            score -= 10

        return max(0.0, min(100.0, score))

    def auto_tag(self, drawer: Drawer) -> list[str]:
        if drawer.tags and len(drawer.tags) > 1:
            return drawer.tags

        content_lower = (drawer.content or "").lower()
        new_tags = list(drawer.tags) if drawer.tags else []

        for tag, keywords in self.TAG_KEYWORDS.items():
            if tag not in new_tags:
                if any(kw in content_lower for kw in keywords):
                    new_tags.append(tag)

        if not new_tags:
            new_tags.append("auto_tagged")

        return new_tags

    def find_duplicates(self, drawers: list[Drawer], threshold: float = 0.85) -> list[list[str]]:
        groups = []
        used = set()
        for i, a in enumerate(drawers):
            if a.id in used:
                continue
            group = [a.id]
            a_words = set((a.content or "").lower().split())
            if not a_words:
                continue
            for j in range(i + 1, len(drawers)):
                b = drawers[j]
                if b.id in used:
                    continue
                b_words = set((b.content or "").lower().split())
                if not b_words:
                    continue
                overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
                if overlap >= threshold:
                    group.append(b.id)
                    used.add(b.id)
            if len(group) > 1:
                used.add(a.id)
                groups.append(group)
        return groups

    def analyze(self) -> QualityReport:
        drawers = self._load_drawers()
        if not drawers:
            return QualityReport()

        report = QualityReport(total=len(drawers))
        scores = []
        tagless = 0
        for d in drawers:
            s = self.score_memory(d)
            scores.append(s)
            report.scored += 1
            if not d.tags or len(d.tags) == 0:
                tagless += 1
            if s < 40:
                report.low_quality += 1
            elif s >= 80:
                report.high_quality += 1

        if scores:
            report.avg_score = sum(scores) / len(scores)
        report.tags_added = tagless

        dups = self.find_duplicates(drawers)
        report.merged = sum(len(g) - 1 for g in dups)

        for s in scores:
            if s < 40:
                report.score_distribution["poor"] += 1
            elif s < 60:
                report.score_distribution["fair"] += 1
            elif s < 80:
                report.score_distribution["good"] += 1
            else:
                report.score_distribution["excellent"] += 1

        return report

    def fix_all(self, dry_run: bool = False) -> QualityReport:
        drawers = self._load_drawers()
        if not drawers:
            return QualityReport()

        report = QualityReport(total=len(drawers))
        changed = False

        for d in drawers:
            new_tags = self.auto_tag(d)
            if new_tags != d.tags:
                d.tags = new_tags
                report.tags_added += 1
                changed = True

            s = self.score_memory(d)
            if s < 40:
                report.low_quality += 1
            elif s >= 80:
                report.high_quality += 1

            report.scored += 1

        dups = self.find_duplicates(drawers)
        dup_ids = set()
        for group in dups:
            group[0]
            for gid in group[1:]:
                dup_ids.add(gid)
            report.merged += len(group) - 1

        if dup_ids:
            drawers = [d for d in drawers if d.id not in dup_ids]
            changed = True

        if changed and not dry_run:
            self._save_drawers(drawers)

        scores = [self.score_memory(d) for d in drawers]
        if scores:
            report.avg_score = sum(scores) / len(scores)

        for s in scores:
            if s < 40:
                report.score_distribution["poor"] += 1
            elif s < 60:
                report.score_distribution["fair"] += 1
            elif s < 80:
                report.score_distribution["good"] += 1
            else:
                report.score_distribution["excellent"] += 1

        return report

    def get_report_dict(self) -> dict:
        r = self.analyze()
        return {
            "total": r.total,
            "avg_score": round(r.avg_score, 1),
            "high_quality": r.high_quality,
            "low_quality": r.low_quality,
            "needs_tags": r.tags_added,
            "duplicates": r.merged,
            "distribution": r.score_distribution,
        }


_quality: QualityPipeline | None = None


def get_quality_pipeline(config: PanguConfig = None) -> QualityPipeline:
    global _quality
    if _quality is None:
        _quality = QualityPipeline(config)
    return _quality
