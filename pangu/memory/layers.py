"""盘古 4 层记忆栈 — 渐进式记忆加载 + 性能优化
===================================================
L0: 身份层 (~100 tokens)  — 始终加载，定义"我是谁"
L1: 概要层 (~500-800 tokens) — 始终加载，关键记忆摘要
L2: 按需层 (~200-500 tokens) — 话题触发时加载
L3: 深度搜索 (无限) — 全文语义搜索

性能优化：
- LRU 缓存减少磁盘 I/O
- 批量操作支持
- 记忆访问追踪（用于巩固引擎）"""
import json
import logging
import os
import time
from collections import OrderedDict, defaultdict
from pathlib import Path

logger = logging.getLogger("pangu.memory.layers")

from ..core.config import PanguConfig
from ..core.palace import Drawer


class LRUCache:
    """简单的 LRU 缓存，用于减少磁盘 I/O"""

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def invalidate(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)


class Layer0:
    """L0 身份层 — 读取 ~/.pangu/identity.txt"""

    def __init__(self, identity_path: str = None):
        self.path = identity_path or os.path.expanduser("~/.pangu/identity.txt")

    def render(self) -> str:
        """渲染身份文本"""
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                return f.read().strip()
        return "## L0 — 身份未配置\n请创建 ~/.pangu/identity.txt 定义 AI 身份"

    def set_identity(self, text: str) -> None:
        """设置身份文本"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text.strip())

    def token_estimate(self) -> int:
        return len(self.render()) // 4


class Layer1:
    """L1 概要层 — 从最重要/最近的记忆中生成摘要"""

    MAX_DRAWERS = 15
    MAX_CHARS = 3200

    def __init__(self, palace_path: str, wing: str = None):
        self.palace_path = palace_path
        self.wing = wing

    def generate(self, drawers: list[Drawer]) -> str:
        """从抽屉列表中生成 L1 摘要"""
        if not drawers:
            return "## L1 — 暂无记忆"

        # 按重要性排序
        scored = [(d.importance, d) for d in drawers]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_DRAWERS]

        # 按 room 分组
        by_room = defaultdict(list)
        for _imp, drawer in top:
            by_room[drawer.room].append(drawer)

        lines = ["## L1 — 记忆概要"]
        total_len = 0

        for room, entries in sorted(by_room.items()):
            room_line = f"\n[{room}]"
            lines.append(room_line)
            total_len += len(room_line)

            for drawer in entries:
                snippet = drawer.content.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                entry_line = f"  - {snippet}"
                if drawer.source_file:
                    entry_line += f"  ({Path(drawer.source_file).name})"

                if total_len + len(entry_line) > self.MAX_CHARS:
                    lines.append("  ... (更多内容在 L3 深度搜索)")
                    return "\n".join(lines)

                lines.append(entry_line)
                total_len += len(entry_line)

        return "\n".join(lines)


class Layer2:
    """L2 按需层 — Wing/Room 过滤检索 + token 预算截断"""

    MAX_CHARS_PER_ENTRY = 300
    DEFAULT_TOKEN_BUDGET = 1000

    def __init__(self, palace_path: str, token_budget: int = None):
        self.palace_path = palace_path
        self.token_budget = token_budget or self.DEFAULT_TOKEN_BUDGET

    def retrieve(self, drawers: list[Drawer], wing: str = None, room: str = None,
                 n_results: int = 10, token_budget: int = None) -> str:
        """按 Wing/Room 过滤检索，超过 token 预算自动截断"""
        budget = token_budget or self.token_budget
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if room and d.room != room:
                continue
            filtered.append(d)

        if not filtered:
            label = f"wing={wing} room={room}" if wing or room else "全部"
            return f"## L2 — {label} 下暂无记忆"

        # 按重要性排序
        filtered.sort(key=lambda d: d.importance, reverse=True)

        lines = []
        header = f"## L2 — 按需检索 ({min(n_results, len(filtered))}/{len(filtered)} 条, budget={budget}t)"
        lines.append(header)
        used_tokens = _estimate_tokens(header)
        included = 0

        for drawer in filtered[:n_results]:
            snippet = drawer.content.strip().replace("\n", " ")
            if len(snippet) > self.MAX_CHARS_PER_ENTRY:
                snippet = snippet[:self.MAX_CHARS_PER_ENTRY - 3] + "..."
            entry = f"  [{drawer.room}] {snippet}"
            if drawer.source_file:
                entry += f"  ({Path(drawer.source_file).name})"

            entry_tokens = _estimate_tokens(entry)
            if used_tokens + entry_tokens > budget:
                lines.append(f"  ... ({len(filtered) - included} 条超出预算，已截断)")
                break
            lines.append(entry)
            used_tokens += entry_tokens
            included += 1

        return "\n".join(lines)


class Layer3:
    """L3 深度搜索 — 全文语义搜索 + token 预算截断"""

    MAX_CHARS_PER_ENTRY = 300
    DEFAULT_TOKEN_BUDGET = 2000

    def __init__(self, palace_path: str, token_budget: int = None):
        self.palace_path = palace_path
        self.token_budget = token_budget or self.DEFAULT_TOKEN_BUDGET

    def search(self, query: str, drawers: list[Drawer], wing: str = None,
               room: str = None, n_results: int = 5, token_budget: int = None) -> str:
        """深度搜索，超过 token 预算自动截断"""
        budget = token_budget or self.token_budget
        # 过滤
        filtered = []
        for d in drawers:
            if wing and d.wing != wing:
                continue
            if room and d.room != room:
                continue
            filtered.append(d)

        if not filtered:
            return f"## L3 — 未找到与 \"{query}\" 相关的结果"

        # 简单关键词匹配评分
        query_lower = query.lower()
        keywords = query_lower.split()

        scored = []
        for d in filtered:
            content_lower = d.content.lower()
            score = sum(content_lower.count(kw) for kw in keywords)
            # 重要性加权
            score += d.importance * 0.5
            scored.append((score, d))

        scored.sort(key=lambda x: x[0], reverse=True)

        lines = []
        header = f'## L3 — 搜索结果: "{query}" (budget={budget}t)'
        lines.append(header)
        used_tokens = _estimate_tokens(header)
        included = 0

        for i, (score, drawer) in enumerate(scored[:n_results], 1):
            snippet = drawer.content.strip().replace("\n", " ")
            if len(snippet) > self.MAX_CHARS_PER_ENTRY:
                snippet = snippet[:self.MAX_CHARS_PER_ENTRY - 3] + "..."
            entry = f"  [{i}] {drawer.wing}/{drawer.room} (score={score:.1f})\n      {snippet}"
            if drawer.source_file:
                entry += f"\n      src: {Path(drawer.source_file).name}"

            entry_tokens = _estimate_tokens(entry)
            if used_tokens + entry_tokens > budget:
                lines.append(f"  ... ({len(scored) - included} 条超出预算，已截断)")
                break
            lines.append(entry)
            used_tokens += entry_tokens
            included += 1

        return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字 ≈ 1.5 token，英文 1 词 ≈ 1 token"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25)


def _log_token_stats(operation: str, layers: dict) -> None:
    """打印各层 token 统计"""
    token_parts = {}
    extra_parts = {}
    for k, v in layers.items():
        if isinstance(v, (int, float)):
            token_parts[k] = v
        else:
            extra_parts[k] = v
    total = sum(token_parts.values())
    parts = [f"{k}={v}" for k, v in token_parts.items()]
    if extra_parts:
        parts.extend(f"{k}={v}" for k, v in extra_parts.items())
    logger.info(f"[tokens] {operation}: {' | '.join(parts)} | total={total}")


class MemoryStack:
    """4 层记忆栈统一接口 — 带缓存和访问追踪"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self.l0 = Layer0(self.config.identity_path)
        self.l1 = Layer1(self.config.palace_path)
        self.l2 = Layer2(self.config.palace_path)
        self.l3 = Layer3(self.config.palace_path)

        # 内存中的抽屉缓存
        self._drawers: list[Drawer] = []
        self._drawers_file = Path(self.config.palace_path) / "drawers.json"

        # LRU 缓存
        self._cache = LRUCache(max_size=500)
        self._cache_ttl = 30.0  # 缓存 30 秒
        self._last_cache_time: float = 0.0

        # 访问追踪器
        self._access_tracker: dict[str, int] = {}
        self._consolidator = None  # 懒加载

    @property
    def consolidator(self):
        """懒加载巩固引擎"""
        if self._consolidator is None:
            from .consolidation import MemoryConsolidator
            self._consolidator = MemoryConsolidator(self.config)
        return self._consolidator

    # ── 缓存逻辑 ──

    def _load_drawers(self) -> list[Drawer]:
        """从磁盘加载抽屉（带缓存）"""
        cache_key = f"drawers_{self._drawers_file}"
        now = time.time()

        if self._cache_ttl > 0 and (now - self._last_cache_time) < self._cache_ttl:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        if self._drawers_file.exists():
            with open(self._drawers_file, encoding="utf-8") as f:
                data = json.load(f)
            result = [Drawer.from_dict(d) for d in data]
        else:
            result = []

        self._cache.set(cache_key, result)
        self._last_cache_time = now
        return result

    def _save_drawers(self) -> None:
        """保存抽屉到磁盘并刷新缓存（带脏检查，防止覆盖外部修改）"""
        try:
            if self._drawers_file.exists():
                with open(self._drawers_file, encoding="utf-8") as f:
                    disk_data = json.load(f)
                if len(disk_data) > len(self._drawers):
                    logger.warning(f"跳过保存: 磁盘有 {len(disk_data)} 条，内存仅 {len(self._drawers)} 条")
                    return
        except Exception:
            pass

        with open(self._drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in self._drawers], f, ensure_ascii=False, indent=2)
        self._cache.invalidate()

    def invalidate_cache(self) -> None:
        """手动刷新缓存"""
        self._cache.invalidate()

    # ── 抽屉操作 ──

    def add_drawer(self, drawer: Drawer) -> None:
        """添加记忆抽屉"""
        self._drawers = self._load_drawers()
        self._drawers.append(drawer)
        self._save_drawers()
        self._cache.invalidate()

    def add_drawers(self, drawers: list[Drawer]) -> None:
        """批量添加记忆抽屉"""
        self._drawers = self._load_drawers()
        self._drawers.extend(drawers)
        self._save_drawers()
        self._cache.invalidate()

    def get_drawers(self) -> list[Drawer]:
        """获取所有抽屉"""
        return self._load_drawers()

    def get_drawer_by_id(self, drawer_id: str) -> Drawer | None:
        """按 ID 获取抽屉"""
        drawers = self._load_drawers()
        for d in drawers:
            if d.id == drawer_id:
                # 记录访问
                self._access_tracker[drawer_id] = self._access_tracker.get(drawer_id, 0) + 1
                self.consolidator.record_access(drawer_id)
                return d
        return None

    def count_drawers(self) -> int:
        """获取抽屉总数"""
        return len(self._load_drawers())

    def _backup_drawers(self) -> str | None:
        """备份 drawers.json，返回备份路径"""
        import shutil
        from datetime import datetime
        if not self._drawers_file.exists():
            return None
        backup_dir = Path(self.config.palace_path) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"drawers_{ts}.json"
        shutil.copy2(self._drawers_file, backup_path)
        # 保留最近 5 个备份
        backups = sorted(backup_dir.glob("drawers_*.json"))
        for old in backups[:-5]:
            old.unlink()
        return str(backup_path)

    def _remove_from_vector_index(self, drawer_ids: list[str]) -> None:
        """从向量索引中删除指定记忆"""
        try:
            from pangu.memory.vector_index import get_vector_index
            idx = get_vector_index()
            for did in drawer_ids:
                if did in idx._ids:
                    idx._ids.remove(did)
                    idx._size -= 1
            idx._save()
        except Exception:
            pass

    def remove_drawer(self, drawer_id: str) -> bool:
        """删除指定抽屉（自动备份 + 向量索引同步）"""
        self._drawers = self._load_drawers()
        original_len = len(self._drawers)
        self._drawers = [d for d in self._drawers if d.id != drawer_id]
        if len(self._drawers) < original_len:
            self._backup_drawers()
            self._save_drawers()
            self._remove_from_vector_index([drawer_id])
            self._cache.invalidate()
            return True
        return False

    def remove_drawers(self, drawer_ids: list[str]) -> int:
        """批量删除抽屉（自动备份 + 向量索引同步）"""
        self._drawers = self._load_drawers()
        ids_set = set(drawer_ids)
        original_len = len(self._drawers)
        self._drawers = [d for d in self._drawers if d.id not in ids_set]
        removed = original_len - len(self._drawers)
        if removed > 0:
            self._backup_drawers()
            self._save_drawers()
            self._remove_from_vector_index(drawer_ids)
            self._cache.invalidate()
        return removed

    # ── 记忆栈接口 ──

    def wake_up(self, wing: str = None) -> str:
        """唤醒: L0 + L1 (~600-900 tokens)"""
        parts = [self.l0.render(), ""]
        drawers = self._load_drawers()

        if wing:
            drawers = [d for d in drawers if d.wing == wing]

        l1_text = self.l1.generate(drawers)
        parts.append(l1_text)

        result = "\n".join(parts)
        _log_token_stats("wake_up", {
            "L0": _estimate_tokens(parts[0]),
            "L1": _estimate_tokens(l1_text),
        })
        return result

    def _dynamic_budget(self, level: str = "L2") -> int:
        """根据记忆总数动态计算 token 预算

        策略（基于每条记忆平均 40 token 估算）：
        - <50 条: 基础预算（800t）
        - 50-200 条: 标准预算（1500t）
        - 200-500 条: 增长预算（2500t）
        - >500 条: 限制预算（3000t，防止 context 溢出）
        """
        total = len(self._load_drawers())
        if total < 50:
            base = 1000
        elif total < 200:
            base = 1500
        elif total < 500:
            base = 2500
        else:
            base = 3000

        if level == "L3":
            base = int(base * 1.5)  # L3 = 1.5x L2
        return base

    def recall(self, wing: str = None, room: str = None, n_results: int = 10) -> str:
        """按需回忆: L2（动态 token 预算截断）"""
        drawers = self._load_drawers()
        budget = self._dynamic_budget("L2")
        result = self.l2.retrieve(drawers, wing=wing, room=room, n_results=n_results, token_budget=budget)
        _log_token_stats("recall", {
            "L2": _estimate_tokens(result),
            "budget": budget,
            "total_drawers": len(drawers),
        })
        return result

    def search(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> str:
        """深度搜索: L3（动态 token 预算截断）"""
        drawers = self._load_drawers()
        budget = self._dynamic_budget("L3")
        result = self.l3.search(query, drawers, wing=wing, room=room, n_results=n_results, token_budget=budget)
        _log_token_stats("search", {
            "L3": _estimate_tokens(result),
            "budget": budget,
            "query": query,
        })
        return result

    # ── 巩固集成 ──

    def get_consolidation_stats(self) -> dict:
        """获取巩固统计信息"""
        drawers = self._load_drawers()
        return self.consolidator.stats(drawers)

    def find_forgotten(self) -> list[Drawer]:
        """找出应被遗忘的记忆"""
        drawers = self._load_drawers()
        return self.consolidator.find_forgotten(drawers)

    def find_compressible(self) -> list[Drawer]:
        """找出可压缩的记忆"""
        drawers = self._load_drawers()
        return self.consolidator.find_compressible(drawers)

    def get_memory_importance(self, drawer_id: str) -> float:
        """获取记忆的综合重要性"""
        drawer = self.get_drawer_by_id(drawer_id)
        if drawer:
            return self.consolidator.calculate_importance(drawer)
        return 0.0

    def health_check(self) -> dict:
        """系统健康检查 — 验证所有组件状态"""
        checks = {}
        drawers = self._load_drawers()

        # 1. 数据文件
        checks["drawers_file"] = {
            "exists": self._drawers_file.exists(),
            "size_kb": round(self._drawers_file.stat().st_size / 1024, 1) if self._drawers_file.exists() else 0,
            "count": len(drawers),
        }

        # 2. 身份文件
        identity_exists = os.path.exists(self.config.identity_path)
        checks["identity"] = {"exists": identity_exists}

        # 3. ONNX 嵌入器
        try:
            from pangu.memory.onnx_embedder import get_onnx_embedder
            onnx = get_onnx_embedder()
            checks["onnx"] = {"available": onnx.is_available, "loaded": onnx.is_loaded}
        except Exception as e:
            checks["onnx"] = {"available": False, "error": str(e)}

        # 4. 向量索引
        try:
            from pangu.memory.vector_index import get_vector_index
            idx = get_vector_index()
            checks["vector_index"] = {"size": idx.size, "backend": "FAISS" if idx._use_faiss else "numpy"}
        except Exception as e:
            checks["vector_index"] = {"error": str(e)}

        # 5. 神经记忆
        try:
            from pangu.memory.neural_memory import get_neural_engine
            engine = get_neural_engine()
            checks["neural_memory"] = {
                "hippocampus": engine.hippocampus.buffer_size,
                "neocortex": engine.neocortex.count(),
            }
        except Exception as e:
            checks["neural_memory"] = {"error": str(e)}

        # 6. 加密状态
        try:
            from pangu.memory.encryption import is_enabled
            checks["encryption"] = {"enabled": is_enabled()}
        except Exception:
            checks["encryption"] = {"enabled": False}

        # 7. 搜索统计
        try:
            from pangu.memory.retrieval import get_search_stats
            checks["search"] = get_search_stats()
        except Exception:
            checks["search"] = {}

        # 总体状态
        all_ok = all(
            v.get("exists", True) and v.get("available", True) and "error" not in v
            for v in checks.values() if isinstance(v, dict)
        )
        checks["status"] = "healthy" if all_ok else "degraded"

        return checks

    def status(self) -> dict:
        """记忆栈状态（含各层 token 估算 + 动态预算 + 搜索统计）"""
        drawers = self._load_drawers()
        l0_tokens = self.l0.token_estimate()
        l1_text = self.l1.generate(drawers)
        l1_tokens = _estimate_tokens(l1_text)
        l2_tokens = _estimate_tokens(self.l2.retrieve(drawers, n_results=10))
        l3_sample = _estimate_tokens(self.l3.search("最近", drawers, n_results=5))

        always_load = l0_tokens + l1_tokens
        l2_budget = self._dynamic_budget("L2")
        l3_budget = self._dynamic_budget("L3")

        # 记忆分布
        by_wing = {}
        for d in drawers:
            by_wing[d.wing] = by_wing.get(d.wing, 0) + 1

        # 搜索统计
        try:
            from pangu.memory.retrieval import get_search_stats, get_search_history
            search_stats = get_search_stats()
            search_stats["recent_history"] = get_search_history(limit=5)
        except Exception:
            search_stats = {}

        return {
            "palace_path": self.config.palace_path,
            "total_memories": len(drawers),
            "by_wing": by_wing,
            "layers": {
                "L0_identity": {
                    "tokens": l0_tokens,
                    "budget": "always",
                    "path": self.config.identity_path,
                },
                "L1_essential": {
                    "tokens": l1_tokens,
                    "budget": "always",
                    "drawers": min(len(drawers), 15),
                },
                "L2_on_demand": {
                    "tokens": l2_tokens,
                    "budget": l2_budget,
                    "utilization": f"{l2_tokens/l2_budget*100:.0f}%",
                },
                "L3_deep_search": {
                    "tokens_sample": l3_sample,
                    "budget": l3_budget,
                    "utilization": f"{l3_sample/l3_budget*100:.0f}%",
                },
            },
            "token_summary": {
                "always_load": always_load,
                "l2_budget": l2_budget,
                "l3_budget": l3_budget,
                "total_if_all": l0_tokens + l1_tokens + l2_tokens + l3_sample,
                "savings_vs_full": f"{(1 - always_load/(l0_tokens + l1_tokens + l2_tokens + l3_sample))*100:.0f}%",
            },
            "search_stats": search_stats,
            "total_drawers": len(drawers),
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
            "consolidation": self.get_consolidation_stats() if self.config.consolidation_enabled else None,
        }
