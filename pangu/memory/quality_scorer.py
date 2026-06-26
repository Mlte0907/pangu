"""盘古记忆质量评分 — 全面评估和改善记忆质量

核心能力：
1. 多维度评分：从完整性、独特性、时效性、关联性等维度评分
2. 批量评估：对所有记忆进行质量评估
3. 改进建议：针对低质量记忆提供改善建议
4. 质量趋势：跟踪记忆质量的变化趋势
5. 自动修复：自动修复可修复的质量问题
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.quality_scorer")


@dataclass
class QualityDimension:
    """质量维度"""

    name: str
    score: float  # 0-1
    weight: float
    detail: str


@dataclass
class QualityAssessment:
    """质量评估结果"""

    memory_id: str
    overall_score: float
    dimensions: list[QualityDimension]
    grade: str  # A/B/C/D/F
    issues: list[str]
    suggestions: list[str]


class QualityScorer:
    """记忆质量评分引擎"""

    GRADE_THRESHOLDS = {
        "A": 0.85,
        "B": 0.70,
        "C": 0.55,
        "D": 0.40,
        "F": 0.0,
    }

    def __init__(self, config=None):
        self.config = config
        self._assessment_history: list[dict] = []

    def score_completeness(self, drawer) -> QualityDimension:
        """完整性评分"""
        content_len = len(drawer.content)
        len(drawer.tags) > 0
        has_wing = bool(drawer.wing)

        length_score = min(1.0, content_len / 100)
        tag_score = min(1.0, len(drawer.tags) * 0.25)
        wing_score = 1.0 if has_wing else 0.0

        score = length_score * 0.4 + tag_score * 0.35 + wing_score * 0.25
        detail = f"内容{content_len}字, 标签{len(drawer.tags)}个"

        return QualityDimension("completeness", round(score, 3), 0.25, detail)

    def score_uniqueness(self, drawer, all_drawers: list) -> QualityDimension:
        """独特性评分"""
        content = drawer.content[:50]
        duplicates = sum(1 for d in all_drawers if d.id != drawer.id and d.content[:50] == content)
        score = max(0, 1.0 - duplicates * 0.3)
        detail = f"重复数: {duplicates}"

        return QualityDimension("uniqueness", round(score, 3), 0.20, detail)

    def score_relevance(self, drawer) -> QualityDimension:
        """关联性评分"""
        tag_count = len(drawer.tags)
        content_words = len(drawer.content.split())
        tag_ratio = tag_count / max(content_words // 5, 1)

        score = min(1.0, tag_ratio * 2 + 0.3)
        detail = f"标签/内容比: {tag_ratio:.2f}"

        return QualityDimension("relevance", round(min(score, 1.0), 3), 0.20, detail)

    def score_information_density(self, drawer) -> QualityDimension:
        """信息密度评分"""
        content = drawer.content
        total_chars = len(content)
        if total_chars == 0:
            return QualityDimension("density", 0.0, 0.15, "空内容")

        unique_chars = len(set(content))
        char_diversity = unique_chars / total_chars

        meaningful = len(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+", content))
        meaningful_ratio = meaningful / max(total_chars // 2, 1)

        score = char_diversity * 0.5 + min(1.0, meaningful_ratio) * 0.5
        detail = f"字符多样性: {char_diversity:.2f}, 有意义词: {meaningful}"

        return QualityDimension("density", round(min(score, 1.0), 3), 0.15, detail)

    def score_importance(self, drawer) -> QualityDimension:
        """重要性评分"""
        imp = drawer.importance / 5.0
        detail = f"重要性: {drawer.importance}/5.0"

        return QualityDimension("importance", round(imp, 3), 0.20, detail)

    def assess(self, drawer, all_drawers: list) -> QualityAssessment:
        """综合评估单条记忆"""
        dimensions = [
            self.score_completeness(drawer),
            self.score_uniqueness(drawer, all_drawers),
            self.score_relevance(drawer),
            self.score_information_density(drawer),
            self.score_importance(drawer),
        ]

        overall = sum(d.score * d.weight for d in dimensions)
        overall = round(overall, 3)

        grade = "F"
        for g, threshold in self.GRADE_THRESHOLDS.items():
            if overall >= threshold:
                grade = g
                break

        issues = []
        suggestions = []
        for d in dimensions:
            if d.score < 0.3:
                issues.append(f"{d.name}: {d.detail}")
                if d.name == "completeness":
                    suggestions.append("添加更多内容和标签")
                elif d.name == "uniqueness":
                    suggestions.append("合并重复记忆或删除冗余")
                elif d.name == "relevance":
                    suggestions.append("增加相关标签")
                elif d.name == "density":
                    suggestions.append("精简内容，去除冗余信息")

        return QualityAssessment(
            memory_id=drawer.id,
            overall_score=overall,
            dimensions=dimensions,
            grade=grade,
            issues=issues,
            suggestions=suggestions,
        )

    def batch_assess(self, drawers: list) -> dict:
        """批量评估"""
        assessments = []
        grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        total_score = 0.0

        for d in drawers:
            assessment = self.assess(d, drawers)
            assessments.append(assessment)
            grade_counts[assessment.grade] = grade_counts.get(assessment.grade, 0) + 1
            total_score += assessment.overall_score

        avg_score = total_score / max(len(assessments), 1)

        self._assessment_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "total": len(assessments),
                "avg_score": round(avg_score, 3),
                "grades": grade_counts.copy(),
            }
        )

        return {
            "total_assessed": len(assessments),
            "avg_score": round(avg_score, 3),
            "grade_distribution": grade_counts,
            "top_issues": self._collect_top_issues(assessments),
            "worst_memories": [
                {"id": a.memory_id, "score": a.overall_score, "grade": a.grade}
                for a in sorted(assessments, key=lambda x: x.overall_score)[:5]
            ],
            "best_memories": [
                {"id": a.memory_id, "score": a.overall_score, "grade": a.grade}
                for a in sorted(assessments, key=lambda x: x.overall_score, reverse=True)[:5]
            ],
        }

    def _collect_top_issues(self, assessments: list) -> list[dict]:
        """收集常见问题"""
        issue_counts: dict[str, int] = {}
        for a in assessments:
            for issue in a.issues:
                key = issue.split(":")[0]
                issue_counts[key] = issue_counts.get(key, 0) + 1

        return [
            {"issue": issue, "count": count} for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1])[:5]
        ]

    def auto_fix(self, drawers: list) -> dict:
        """自动修复可修复的质量问题"""
        fixed = 0
        for d in drawers:
            if not d.tags:
                words = [w for w in d.content.split() if len(w) >= 2]
                d.tags = list(set(w for w in words if re.match(r"^[\u4e00-\u9fff]+$", w)))[:5]
                if not d.tags:
                    d.tags = ["auto_tagged"]
                fixed += 1

            if d.importance < 1.0:
                d.importance = 1.0
                fixed += 1

        return {"auto_fixed": fixed, "total_checked": len(drawers)}

    def get_quality_stats(self) -> dict:
        """获取质量统计"""
        if not self._assessment_history:
            return {"total_assessments": 0}

        latest = self._assessment_history[-1]
        return {
            "total_assessments": len(self._assessment_history),
            "latest_avg_score": latest["avg_score"],
            "latest_grades": latest["grades"],
        }


_scorer: QualityScorer | None = None


def get_scorer(config=None) -> QualityScorer:
    """获取全局质量评分实例"""
    global _scorer
    if _scorer is None:
        _scorer = QualityScorer(config)
    return _scorer
