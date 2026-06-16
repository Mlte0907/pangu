"""盘古记忆差异对比 — 比较记忆版本和内容差异

核心能力：
1. 内容差异：逐行对比两条记忆的内容差异
2. 版本追踪：记录记忆变更历史
3. 批量对比：批量比较多条记忆的差异
4. 变更摘要：生成变更摘要报告
5. 相似度矩阵：计算记忆间的相似度矩阵
"""
import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("pangu.memory.memory_diff")


@dataclass
class DiffLine:
    """差异行"""
    line_num: int
    type: str  # added / removed / unchanged / modified
    old_text: str
    new_text: str


@dataclass
class DiffResult:
    """差异结果"""
    memory_id_a: str
    memory_id_b: str
    similarity: float
    added: int
    removed: int
    unchanged: int
    modified: int
    lines: list[DiffLine]


class MemoryDiffEngine:
    """记忆差异引擎"""

    def __init__(self, config=None):
        self.config = config
        self._diff_history: list[dict] = []

    def diff_content(self, content_a: str, content_b: str,
                     id_a: str = "a", id_b: str = "b") -> DiffResult:
        """对比两段内容"""
        lines_a = content_a.split("\n")
        lines_b = content_b.split("\n")

        diff_lines = []
        added = removed = unchanged = modified = 0

        max_len = max(len(lines_a), len(lines_b))
        for i in range(max_len):
            la = lines_a[i] if i < len(lines_a) else None
            lb = lines_b[i] if i < len(lines_b) else None

            if la is None:
                diff_lines.append(DiffLine(i + 1, "added", "", lb))
                added += 1
            elif lb is None:
                diff_lines.append(DiffLine(i + 1, "removed", la, ""))
                removed += 1
            elif la == lb:
                diff_lines.append(DiffLine(i + 1, "unchanged", la, la))
                unchanged += 1
            else:
                diff_lines.append(DiffLine(i + 1, "modified", la, lb))
                modified += 1

        total = added + removed + unchanged + modified
        similarity = unchanged / max(total, 1)

        result = DiffResult(
            memory_id_a=id_a, memory_id_b=id_b,
            similarity=round(similarity, 3),
            added=added, removed=removed,
            unchanged=unchanged, modified=modified,
            lines=diff_lines,
        )

        self._diff_history.append({
            "id_a": id_a, "id_b": id_b,
            "similarity": result.similarity,
            "timestamp": datetime.now().isoformat(),
        })

        return result

    def diff_drawers(self, drawer_a, drawer_b) -> DiffResult:
        """对比两条记忆"""
        return self.diff_content(
            drawer_a.content, drawer_b.content,
            drawer_a.id, drawer_b.id,
        )

    def batch_diff(self, drawers: list, reference_id: str = None) -> list[dict]:
        """批量差异对比"""
        if not reference_id and len(drawers) >= 2:
            reference_id = drawers[0].id

        ref = next((d for d in drawers if d.id == reference_id), None)
        if not ref:
            return []

        results = []
        for d in drawers:
            if d.id == reference_id:
                continue
            diff = self.diff_drawers(ref, d)
            results.append({
                "memory_id": d.id,
                "similarity": diff.similarity,
                "added": diff.added,
                "removed": diff.removed,
                "modified": diff.modified,
            })

        results.sort(key=lambda x: -x["similarity"])
        return results

    def similarity_matrix(self, drawers: list) -> dict:
        """计算相似度矩阵"""
        ids = [d.id for d in drawers[:20]]
        matrix = {}

        for i in range(len(drawers)):
            row = {}
            for j in range(len(drawers)):
                if i == j:
                    row[drawers[j].id] = 1.0
                else:
                    diff = self.diff_content(
                        drawers[i].content, drawers[j].content,
                        drawers[i].id, drawers[j].id,
                    )
                    row[drawers[j].id] = diff.similarity
            matrix[drawers[i].id] = row

        return {
            "ids": ids,
            "matrix": matrix,
            "size": len(ids),
        }

    def generate_change_summary(self, diff: DiffResult) -> str:
        """生成变更摘要"""
        parts = []
        if diff.added > 0:
            parts.append(f"+{diff.added} 行新增")
        if diff.removed > 0:
            parts.append(f"-{diff.removed} 行删除")
        if diff.modified > 0:
            parts.append(f"~{diff.modified} 行修改")
        if diff.unchanged > 0:
            parts.append(f"={diff.unchanged} 行不变")

        return f"差异: {', '.join(parts)} | 相似度: {diff.similarity:.1%}"

    def get_diff_stats(self) -> dict:
        """获取差异统计"""
        if not self._diff_history:
            return {"total_diffs": 0}

        avg_sim = sum(d["similarity"] for d in self._diff_history) / len(self._diff_history)
        return {
            "total_diffs": len(self._diff_history),
            "avg_similarity": round(avg_sim, 3),
        }


_diff_engine: MemoryDiffEngine | None = None


def get_diff_engine(config=None) -> MemoryDiffEngine:
    """获取全局差异引擎实例"""
    global _diff_engine
    if _diff_engine is None:
        _diff_engine = MemoryDiffEngine(config)
    return _diff_engine
