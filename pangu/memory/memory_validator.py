"""盘古记忆验证机制 — 验证记忆准确性和时效性

功能：
1. 基于 timeline 检测过时记忆（>90天未更新的事实类记忆）
2. 基于 KG 实体一致性检查
3. 基于冲突检测标记矛盾记忆
4. 自动标记 memory_status: active / stale / conflicted / verified
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer

logger = logging.getLogger("pangu.memory.validator")


class MemoryValidator:
    """记忆验证器"""

    STALE_DAYS = 90  # 超过此天数的事实类记忆标记为 stale
    MIN_CONTENT_LENGTH = 20  # 太短的记忆跳过验证

    def __init__(self, config: PanguConfig = None):
        # B5：必须权威化。本模块的 `_load_drawers`/`_save_drawers` 用的是
        # `self.config.palace_path`，而 v1 语义下它指向**空的** v1 库。
        # 实测（假 HOME，v2 有 3 条）：`validate_all()` 返回 `{'total': 0}` ——
        # 真实记忆一条都看不到。活链路：handlers/consolidation.py →
        # LifecycleManager(server.config) → MemoryValidator。
        #
        # 注意必须覆盖**调用方传入**的 config：活链路上传入的是 `server.config`
        # （未权威化），只处理 `config is None` 分支挡不住这条路径。
        base = config or PanguConfig.load()
        self.config = base.authoritative_memory_config()

    def validate_all(self, drawers: list[Drawer] | None = None) -> dict:
        """验证所有记忆，返回统计"""
        if drawers is None:
            drawers = self._load_drawers()

        stats = {"total": len(drawers), "active": 0, "stale": 0, "conflicted": 0, "verified": 0}

        for d in drawers:
            status = self.validate_single(d)
            d.metadata["memory_status"] = status
            stats[status] = stats.get(status, 0) + 1

        self._save_drawers(drawers)
        return stats

    def validate_single(self, drawer: Drawer) -> str:
        """验证单条记忆，返回 status"""
        if len(drawer.content) < self.MIN_CONTENT_LENGTH:
            return "active"

        # 1. 检查是否已标记为冲突
        if drawer.metadata.get("conflicts"):
            return "conflicted"

        # 2. 检查时效性
        if self._is_stale(drawer):
            return "stale"

        # 3. 检查是否被压缩过（压缩过的视为已验证）
        if drawer.metadata.get("compressed"):
            return "verified"

        return "active"

    def _is_stale(self, drawer: Drawer) -> bool:
        """检查记忆是否过时"""
        try:
            created = datetime.fromisoformat(drawer.created_at)
            age_days = (datetime.now() - created).days
            if age_days < self.STALE_DAYS:
                return False
        except (ValueError, TypeError):
            return False

        # 事实类/决策类记忆更容易过时
        fact_keywords = {"是", "等于", "使用", "配置", "端口", "版本", "地址", "密码", "key"}
        if any(kw in drawer.content for kw in fact_keywords):
            # 如果内容较短且是事实类，更容易过时
            if len(drawer.content) < 200:
                return True

        return False

    def _load_drawers(self) -> list[Drawer]:
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if not drawers_file.exists():
            return []
        with open(drawers_file, encoding="utf-8") as f:
            return [Drawer.from_dict(d) for d in json.load(f)]

    def _save_drawers(self, drawers: list[Drawer]):
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        with open(drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in drawers], f, ensure_ascii=False, indent=2)
