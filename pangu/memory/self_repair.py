"""盘古自评估+自修复引擎 — 定期检查并自动修复问题

核心能力：
1. 自评估：检查记忆质量、索引健康、重复内容、标签完整性
2. 自修复：自动修复发现的问题（去重、补标签、清理垃圾）
3. 健康报告：生成系统健康报告
4. 修复日志：记录所有自动修复操作

使用方式：
    engine = SelfRepairEngine()
    report = engine.run_evaluation()
    # 或只运行修复
    fix_result = engine.run_repair()
"""

import json
import hashlib
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.self_repair")


@dataclass
class Issue:
    """发现的问题"""

    issue_type: str  # duplicate, low_quality, missing_tag, orphan, short_content, noise
    severity: str  # critical / warning / info
    description: str
    memory_ids: list[str] = field(default_factory=list)
    fixable: bool = True


@dataclass
class FixResult:
    """修复结果"""

    issue_type: str
    fixed_count: int
    details: list[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    """评估报告"""

    timestamp: str
    total_memories: int
    issues_found: int
    issues_fixed: int
    health_score: float  # 0-100
    issues: list[Issue] = field(default_factory=list)
    fixes: list[FixResult] = field(default_factory=list)
    summary: str = ""


class SelfRepairEngine:
    """自评估+自修复引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._drawers_file = Path(self.config.palace_path) / "drawers.json"
        self._report_file = Path(self.config.palace_path) / "last_evaluation.json"

    def _load_drawers(self) -> list[dict]:
        """加载记忆"""
        if self._drawers_file.exists():
            with open(self._drawers_file, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_drawers(self, drawers: list[dict]):
        """保存记忆"""
        with open(self._drawers_file, "w", encoding="utf-8") as f:
            json.dump(drawers, f, ensure_ascii=False, indent=2)

    # ── 评估检查 ──────────────────────────────────────────────

    def check_duplicates(self, drawers: list[dict]) -> Issue | None:
        """检查重复记忆"""
        content_hashes = defaultdict(list)
        for d in drawers:
            content = d.get("content", "")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            content_hashes[content_hash].append(d.get("id", ""))

        duplicates = {h: ids for h, ids in content_hashes.items() if len(ids) > 1}
        if not duplicates:
            return None

        all_ids = []
        for ids in duplicates.values():
            all_ids.extend(ids[1:])  # 保留第一条，其余标记为重复

        return Issue(
            issue_type="duplicate",
            severity="warning",
            description=f"发现 {len(duplicates)} 组重复记忆（共 {len(all_ids)} 条）",
            memory_ids=all_ids,
            fixable=True,
        )

    def check_low_quality(self, drawers: list[dict]) -> Issue | None:
        """检查低质量记忆"""
        low_quality = []
        for d in drawers:
            content = d.get("content", "")
            score = self._calculate_quality_score(d)
            if score < 30:
                low_quality.append(d.get("id", ""))

        if not low_quality:
            return None

        return Issue(
            issue_type="low_quality",
            severity="warning",
            description=f"发现 {len(low_quality)} 条低质量记忆（score < 30）",
            memory_ids=low_quality,
            fixable=True,
        )

    def check_missing_tags(self, drawers: list[dict]) -> Issue | None:
        """检查缺少标签的记忆"""
        missing = []
        for d in drawers:
            tags = d.get("tags", [])
            if not tags or len(tags) < 1:
                missing.append(d.get("id", ""))

        if not missing:
            return None

        return Issue(
            issue_type="missing_tag",
            severity="info",
            description=f"发现 {len(missing)} 条缺少标签的记忆",
            memory_ids=missing,
            fixable=True,
        )

    def check_short_content(self, drawers: list[dict]) -> Issue | None:
        """检查内容过短的记忆"""
        short = []
        for d in drawers:
            content = d.get("content", "")
            if len(content) < 20:
                short.append(d.get("id", ""))

        if not short:
            return None

        return Issue(
            issue_type="short_content",
            severity="info",
            description=f"发现 {len(short)} 条内容过短的记忆（<20字符）",
            memory_ids=short,
            fixable=False,  # 需要人工判断是否删除
        )

    def check_noise(self, drawers: list[dict]) -> Issue | None:
        """检查噪声内容"""
        noise_patterns = [
            r"^\[message_id:",
            r"^\[System:",
            r"^heartbeat",
            r"^={3,}",
            r"^-{3,}",
        ]
        noise = []
        for d in drawers:
            content = d.get("content", "")
            for pattern in noise_patterns:
                if re.search(pattern, content):
                    noise.append(d.get("id", ""))
                    break

        if not noise:
            return None

        return Issue(
            issue_type="noise",
            severity="warning",
            description=f"发现 {len(noise)} 条噪声内容",
            memory_ids=noise,
            fixable=True,
        )

    def _calculate_quality_score(self, d: dict) -> float:
        """计算质量分"""
        content = d.get("content", "")
        tags = d.get("tags", [])
        score = 0

        # 长度分
        if len(content) > 200:
            score += 30
        elif len(content) > 100:
            score += 20
        elif len(content) > 50:
            score += 10

        # 标签分
        score += min(len(tags) * 5, 20)

        # 结构分
        if re.search(r"[：:]", content):
            score += 5
        if re.search(r"✅|❌|⚠️", content):
            score += 10

        # 内容丰富度
        words = len(content.split())
        if words > 30:
            score += 30
        elif words > 20:
            score += 20
        elif words > 10:
            score += 10

        return min(score, 100)

    # ── 修复操作 ──────────────────────────────────────────────

    def fix_duplicates(self, drawers: list[dict]) -> FixResult:
        """修复重复记忆"""
        content_hashes = defaultdict(list)
        for i, d in enumerate(drawers):
            content = d.get("content", "")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            content_hashes[content_hash].append(i)

        removed = 0
        indices_to_remove = set()
        for h, indices in content_hashes.items():
            if len(indices) > 1:
                # 保留第一条，删除其余
                for idx in indices[1:]:
                    indices_to_remove.add(idx)
                    removed += 1

        if indices_to_remove:
            drawers = [d for i, d in enumerate(drawers) if i not in indices_to_remove]

        return FixResult(
            issue_type="duplicate",
            fixed_count=removed,
            details=[f"删除了 {removed} 条重复记忆"],
        ), drawers

    def fix_low_quality(self, drawers: list[dict]) -> FixResult:
        """修复低质量记忆（删除 score < 20 的）"""
        cleaned = []
        removed = 0
        for d in drawers:
            score = self._calculate_quality_score(d)
            if score < 20:
                removed += 1
            else:
                cleaned.append(d)

        return FixResult(
            issue_type="low_quality",
            fixed_count=removed,
            details=[f"删除了 {removed} 条极低质量记忆（score < 20）"],
        ), cleaned

    def fix_missing_tags(self, drawers: list[dict]) -> FixResult:
        """修复缺少标签的记忆"""
        fixed = 0
        for d in drawers:
            tags = d.get("tags", [])
            if not tags:
                content = d.get("content", "")
                # 自动打标签
                new_tags = []
                if re.search(r"python|java|docker|api|bug|修复|部署", content, re.IGNORECASE):
                    new_tags.append("tech")
                if re.search(r"决定|确认|选择|采用", content):
                    new_tags.append("decision")
                if re.search(r"发现|原来|教训|注意", content):
                    new_tags.append("learning")
                if not new_tags:
                    new_tags.append("general")
                d["tags"] = new_tags
                fixed += 1

        return FixResult(
            issue_type="missing_tag",
            fixed_count=fixed,
            details=[f"为 {fixed} 条记忆补充了标签"],
        ), drawers

    def fix_noise(self, drawers: list[dict]) -> FixResult:
        """修复噪声内容"""
        noise_patterns = [
            r"^\[message_id:",
            r"^\[System:",
            r"^heartbeat",
            r"^={3,}",
            r"^-{3,}",
        ]
        cleaned = []
        removed = 0
        for d in drawers:
            content = d.get("content", "")
            is_noise = False
            for pattern in noise_patterns:
                if re.search(pattern, content):
                    is_noise = True
                    break
            if is_noise:
                removed += 1
            else:
                cleaned.append(d)

        return FixResult(
            issue_type="noise",
            fixed_count=removed,
            details=[f"删除了 {removed} 条噪声内容"],
        ), cleaned

    # ── 主入口 ──────────────────────────────────────────────

    def run_evaluation(self) -> EvaluationReport:
        """运行完整评估"""
        drawers = self._load_drawers()

        issues = []
        for check in [
            self.check_duplicates,
            self.check_low_quality,
            self.check_missing_tags,
            self.check_short_content,
            self.check_noise,
        ]:
            issue = check(drawers)
            if issue:
                issues.append(issue)

        # 计算健康分
        total_issues = sum(len(i.memory_ids) for i in issues)
        critical = sum(1 for i in issues if i.severity == "critical")
        warning = sum(1 for i in issues if i.severity == "warning")

        health_score = max(0, 100 - critical * 20 - warning * 10 - total_issues * 0.5)

        report = EvaluationReport(
            timestamp=datetime.now().isoformat(),
            total_memories=len(drawers),
            issues_found=len(issues),
            issues_fixed=0,
            health_score=round(health_score, 1),
            issues=issues,
            summary=f"发现 {len(issues)} 类问题，共 {total_issues} 条记忆需要处理",
        )

        # 保存报告
        self._save_report(report)
        return report

    def run_repair(self) -> list[FixResult]:
        """运行自动修复"""
        drawers = self._load_drawers()
        fixes = []

        # 修复重复
        fix, drawers = self.fix_duplicates(drawers)
        fixes.append(fix)

        # 修复低质量
        fix, drawers = self.fix_low_quality(drawers)
        fixes.append(fix)

        # 修复噪声
        fix, drawers = self.fix_noise(drawers)
        fixes.append(fix)

        # 修复缺少标签
        fix, drawers = self.fix_missing_tags(drawers)
        fixes.append(fix)

        # 保存
        self._save_drawers(drawers)

        # 更新报告
        report = self._load_report()
        if report:
            report.fixes = fixes
            report.issues_fixed = sum(f.fixed_count for f in fixes)
            self._save_report(report)

        return fixes

    def _save_report(self, report: EvaluationReport):
        """保存评估报告"""
        try:
            data = {
                "timestamp": report.timestamp,
                "total_memories": report.total_memories,
                "issues_found": report.issues_found,
                "issues_fixed": report.issues_fixed,
                "health_score": report.health_score,
                "summary": report.summary,
                "issues": [
                    {
                        "type": i.issue_type,
                        "severity": i.severity,
                        "description": i.description,
                        "count": len(i.memory_ids),
                    }
                    for i in report.issues
                ],
            }
            with open(self._report_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    def _load_report(self) -> EvaluationReport | None:
        """加载评估报告"""
        if not self._report_file.exists():
            return None
        try:
            with open(self._report_file, encoding="utf-8") as f:
                data = json.load(f)
            return EvaluationReport(
                timestamp=data.get("timestamp", ""),
                total_memories=data.get("total_memories", 0),
                issues_found=data.get("issues_found", 0),
                issues_fixed=data.get("issues_fixed", 0),
                health_score=data.get("health_score", 0),
                summary=data.get("summary", ""),
            )
        except Exception:
            return None

    def get_health_report(self) -> dict:
        """获取健康报告"""
        report = self._load_report()
        if not report:
            return {"status": "no_report", "message": "尚未运行评估"}

        return {
            "health_score": report.health_score,
            "total_memories": report.total_memories,
            "issues_found": report.issues_found,
            "issues_fixed": report.issues_fixed,
            "last_evaluation": report.timestamp,
            "summary": report.summary,
        }


# 单例
_engine: SelfRepairEngine | None = None


def get_self_repair_engine() -> SelfRepairEngine:
    """获取单例引擎"""
    global _engine
    if _engine is None:
        _engine = SelfRepairEngine()
    return _engine
