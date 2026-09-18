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

import contextvars
import functools
import json
import logging
import os
import threading
import time

# ── drawers 文件 IO 的进程内串行锁（2026-09-18）──
#
# 为什么需要：`_load_drawers` / `_save_drawers` 是所有读写路径的必经点（MemoryStack 的
# add/update/remove、以及 lifecycle 的维护任务都会经过），而 lifecycle 的三个维护方法
# 是「读全库快照 → 改 → 整份写回」。两个线程交错时**后写的会覆盖前者的改动** ——
# 表现是"并发写入的记忆无声消失"，且没有任何报错。
# 单进程内用一把可重入锁串行化即可（跨进程/CLI 直改文件不在覆盖范围）。
_DRAWERS_IO_LOCK = threading.RLock()


def drawers_io_lock() -> "threading.RLock":
    """暴露给需要让整段「读-改-写」保持原子的调用方（lifecycle 的维护任务）。"""
    return _DRAWERS_IO_LOCK


def _synchronized(fn):
    """把方法体放进 _DRAWERS_IO_LOCK。RLock 可重入，内部互调不会死锁。"""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _DRAWERS_IO_LOCK:
            return fn(*args, **kwargs)

    return wrapper


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

    def retrieve(
        self, drawers: list[Drawer], wing: str = None, room: str = None, n_results: int = 10, token_budget: int = None
    ) -> str:
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

        # 按重要性排序（防御非数值 importance）
        filtered.sort(key=lambda d: d.importance if isinstance(d.importance, (int, float)) else 0.0, reverse=True)

        lines = []
        header = f"## L2 — 按需检索 ({min(n_results, len(filtered))}/{len(filtered)} 条, budget={budget}t)"
        lines.append(header)
        used_tokens = _estimate_tokens(header)
        included = 0

        for drawer in filtered[:n_results]:
            snippet = drawer.content.strip().replace("\n", " ")
            if len(snippet) > self.MAX_CHARS_PER_ENTRY:
                snippet = snippet[: self.MAX_CHARS_PER_ENTRY - 3] + "..."
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

    def search(
        self,
        query: str,
        drawers: list[Drawer],
        wing: str = None,
        room: str = None,
        n_results: int = 5,
        token_budget: int = None,
    ) -> str:
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
            return f'## L3 — 未找到与 "{query}" 相关的结果'

        # 简单关键词匹配评分
        query_lower = query.lower()
        keywords = query_lower.split()

        scored = []
        for d in filtered:
            content_lower = d.content.lower()
            score = sum(content_lower.count(kw) for kw in keywords)
            # 重要性加权（防御非数值 importance）
            imp = d.importance if isinstance(d.importance, (int, float)) else 3.0
            score += imp * 0.5
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
                snippet = snippet[: self.MAX_CHARS_PER_ENTRY - 3] + "..."
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
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
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


# ── 请求级租户作用域 ──────────────────────────────────────────────
# 隔离轴：metadata.tenant_id == 当前租户，或 metadata.visibility == "public"。
#
# 为什么必须有它：收口最初只做在 call_tool 的 drawers 参数上，但静态扫描发现 287 个
# handler 根本不使用该参数 —— 它们直接调 server.memory.*（by-id 查、聚合、wake_up…），
# 而那些方法自己会 _load_drawers() 重读全库。于是收口形同虚设：实测面板仍报全库 124、
# find_forgotten 返回全库内容、wake_up 把全库记忆拼进 L1 上下文。
#
# 所以真正的收口点在本模块：call_tool 在唯一入口 set_tenant_scope(room)，下面所有
# **读**方法走 _read_drawers() 据此裁剪；**写**方法一律用全库快照（_save_drawers 落的是
# self._drawers 全量，若被裁剪就是把别的租户的数据删掉）。
_TENANT_SCOPE: contextvars.ContextVar[str] = contextvars.ContextVar("pangu_tenant_scope", default="")
_KEY_SCOPE: contextvars.ContextVar[str] = contextvars.ContextVar("pangu_key_scope", default="")
_CLEARANCE: contextvars.ContextVar[int] = contextvars.ContextVar("pangu_clearance", default=0)

# 可见性三档（与 api/abac.py 的 Resource.visibility 同一套词汇，**不要**合并：
#   public —— 所有租户可读（毕业区，有意共享）
#   tenant —— 同租户可读（默认；房间=租户，同屋的多把钥匙互相可见）
#   private —— 仅**属主那把钥匙**可读（同租户的其他钥匙也看不到）
# 未标注（空串）按 tenant 处理 —— 历史数据的实际语义就是同租户可见，收紧会让老数据凭空消失。
VIS_PUBLIC = "public"
VIS_TENANT = "tenant"
VIS_PRIVATE = "private"


def set_tenant_scope(room: str = "", key_id: str = "", clearance: int | None = None):
    """设置本请求的作用域（租户 + 钥匙 + 密级），返回 token 供 reset_tenant_scope 复原。

    - key_id：第三档 private 的判据（写入时记下的 owner_key_id 与之相同才可见）
    - clearance：密级（0=public…3=secret），决定能否读到带 classification 的记忆
    """
    _KEY_SCOPE.set(key_id or "")
    _CLEARANCE.set(int(clearance) if clearance is not None else 0)
    return _TENANT_SCOPE.set(room or "")


def reset_tenant_scope(token) -> None:
    """复原租户作用域（call_tool 在 finally 里调用，避免作用域泄漏到下一个请求）。"""
    _TENANT_SCOPE.reset(token)
    _KEY_SCOPE.set("")


def current_tenant() -> str:
    """当前请求的租户；空串＝全库视角（CLI、自主维护、后台任务）。"""
    return _TENANT_SCOPE.get()


def current_key_id() -> str:
    """当前请求所用钥匙的 id；用于判定 private 档。"""
    return _KEY_SCOPE.get()


def current_clearance() -> int:
    """当前请求的密级（0=public…3=secret）。"""
    return int(_CLEARANCE.get() or 0)


def metadata_visible(md: dict | None, tenant: str, key_id: str = "") -> bool:
    """三档可见性判据（记忆/KG/wiki 共用同一套语义，改这里全仓生效）。

    作用域为空（CLI/后台/admin）＝全库视角 → 由调用方直接返回 True，不进本函数。
    """
    md = md or {}
    vis = md.get("visibility") or ""
    if vis == VIS_PUBLIC:
        return True
    if md.get("tenant_id", "") != tenant:
        return False
    if vis == VIS_PRIVATE:
        owner = md.get("owner_key_id") or ""
        if not owner:
            # 老数据没有属主字段（KG 的行根本没有这一列）：按 tenant 档处理。
            # 收紧成"没人可见"会让历史数据凭空消失 —— 那比"放宽"危险得多。
            return True
        return owner == key_id
    return True


def tenant_visible(drawer, tenant: str, key_id: str = "") -> bool:
    """隔离轴判据（抽屉）：三档语义见 metadata_visible。"""
    return metadata_visible(getattr(drawer, "metadata", None), tenant, key_id or current_key_id())


def _coerce_classification(value) -> int:
    """把密级归一化成 int（0=public…3=secret），非法值按 0 处理。

    ⚠ 历史数据里写过字符串（例如 `"normal"`，13 条），而 REST/ABAC 侧是
    `int(md.get("classification", 0))` —— 直接对这些行求值会 ValueError。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, min(3, value))
    try:
        return max(0, min(3, int(str(value).strip() or 0)))
    except (TypeError, ValueError):
        return 0


def clamp_classification(value, clearance: int | None = None) -> int:
    """把写入方标定的密级钳制到**不超过自己的 clearance**。

    策略原因：否则低密级调用方可以把数据标成绝密 —— 那样谁（包括它自己）都读不了，
    等于自锁；也让密级变成任意调用方都能伪造的属性（标低也不是他想标就能标）。
    """
    level = _coerce_classification(value)
    cap = current_clearance() if clearance is None else int(clearance or 0)
    return min(level, max(0, cap))


def metadata_readable(md, tenant: str | None = None, key_id: str | None = None, clearance: int | None = None) -> bool:
    """**是否可读** —— 两条轴的合取：

      1. 租户轴：metadata_visible（我的 / public / private 属主）
      2. 密级轴：clearance >= classification（与 ABAC 的 classification_based 同规则）

    两条轴正交：租户对了但密级不够 → 仍不可读。作用域为空（CLI/后台/admin）＝全库视角，
    密级仍按传入值判定（默认取当前请求的 clearance）。
    """
    md = md or {}
    t = current_tenant() if tenant is None else tenant
    k = current_key_id() if key_id is None else key_id
    if not t:
        # 全库视角（CLI / 后台维护 / admin）＝系统自身：不做租户与密级过滤。
        # 否则后台巩固/备份会因为 clearance=0 而漏掉高密级记忆 —— 那是"系统看不见自己
        # 的数据"，比放宽危险得多。
        return True
    if not metadata_visible(md, t, k):
        return False
    return _coerce_classification(md.get("classification")) <= (current_clearance() if clearance is None else clearance)


class MemoryStack:
    """4 层记忆栈统一接口 — 带缓存和访问追踪"""

    def __init__(self, config: PanguConfig = None, extra_drawers_files: list = None, use_sqlite: bool = False):
        # P0-0 修复：未显式指定 config 时，走**权威记忆路径**（v2
        # `db_path/v2_memories`），而不是默认 config 的 v1 `palace_path`。
        #
        # 此前 `config or PanguConfig.load()` 让全仓 49 处调用点中的 40 处
        # （CLI 34 处、routes_memory、web_server(8866)、warmup、自主维护…）
        # 全部读到空的 v1 `palace/drawers.json`，与 API 侧（显式传 v2 config）
        # 给出两个答案。把默认指向权威路径后，调用点无需逐个修改即自动对齐。
        #
        # 显式传入的 config 一律尊重（API/MCP 那 2 处已传 v2 config，行为不变）；
        # 显式传入的 v1 config 也保持原语义——只在"完全没传"时改默认。
        if config is None:
            original = PanguConfig.load()
            # 先取 v1 路径（权威化后 palace_path 会指向 v2，v1 路径就丢了）
            if extra_drawers_files is None:
                extra_drawers_files = original.authoritative_extra_drawers_files()
            config = original.authoritative_memory_config()
        self.config = config
        # 写路径互斥锁（2026-09-19）：MCP 主循环与自主调度线程都会写记忆，
        # add/update/remove 是"读-改-写"组合，无锁时并发会丢更新。
        #
        # ⚠ 必须复用模块级 _DRAWERS_IO_LOCK（_synchronized 用的同一把），不能新起一个
        # 实例锁：lifecycle 的维护任务通过 get_drawers_io_lock() 持模块锁包"整段读-改-
        # 写"，若这里另起锁，两把锁互不排斥，等于没锁住。（初版用 threading.RLock()
        # 新建 —— 2026-09-19 修正。）
        self._write_lock = _DRAWERS_IO_LOCK
        self.l0 = Layer0(self.config.identity_path)
        self.l1 = Layer1(self.config.palace_path)
        self.l2 = Layer2(self.config.palace_path)
        self.l3 = Layer3(self.config.palace_path)

        # 内存中的抽屉缓存
        self._drawers: list[Drawer] = []
        self._drawers_file = Path(self.config.palace_path) / "drawers.json"
        # 合并只读源（如 v1 palace/drawers.json），仅用于读取，不写回
        self._extra_drawers_files: list[Path] = [Path(p) for p in (extra_drawers_files or [])]
        self._primary_ids: set[str] = set()  # 来自主文件的 drawer id（保存时仅写这些）
        # 是否**成功加载过**主存。用于空写保护区分"假空"与"真空"：
        #   False = 加载异常/从未加载 ⇒ 内存为空是**假空**，落盘会清库 → 拦
        #   True  = 加载成功（含"文件不存在"）⇒ 内存为空是**真空** → 放行
        # 详见 `_save_drawers()` 的空写保护判据。
        self._loaded_ok: bool = False

        # 存储后端
        self._use_sqlite = use_sqlite
        self._storage = None
        self._init_storage()

        # LRU 缓存
        self._cache = LRUCache(max_size=500)
        self._cache_ttl = 30.0  # 缓存 30 秒
        self._last_cache_time: float = 0.0

        # 访问追踪器
        self._access_tracker: dict[str, int] = {}
        self._consolidator = None  # 懒加载

    def _init_storage(self) -> None:
        """初始化存储后端"""
        if self._use_sqlite:
            from .drawer_storage import SqliteDrawerStorage

            db_path = Path(self.config.palace_path) / "drawers.db"
            self._storage = SqliteDrawerStorage(str(db_path))
        else:
            from .drawer_storage import JsonDrawerStorage

            self._storage = JsonDrawerStorage(str(self._drawers_file))

    @property
    def consolidator(self):
        """懒加载巩固引擎"""
        if self._consolidator is None:
            from .consolidation import MemoryConsolidator

            self._consolidator = MemoryConsolidator(self.config)
        return self._consolidator

    # ── 缓存逻辑 ──

    @_synchronized
    def _load_drawers(self) -> list[Drawer]:
        """从磁盘加载抽屉（带缓存），合并主文件 + 只读源，按 id 去重"""
        cache_key = f"drawers_{self._drawers_file}"
        now = time.time()

        if self._cache_ttl > 0 and (now - self._last_cache_time) < self._cache_ttl:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result: list[Drawer] = []
        seen: set[str] = set()
        self._primary_ids = set()

        # 使用存储后端加载主数据
        if self._storage:
            try:
                primary_drawers = self._storage.load()
                for dr in primary_drawers:
                    if dr.id in seen:
                        continue
                    seen.add(dr.id)
                    self._primary_ids.add(dr.id)
                    result.append(dr)
                # ⚠ 必须看后端自己报的 last_load_ok，不能因为"调用没抛异常"就置 True。
                # `JsonDrawerStorage.load()` 内部 `except Exception` 会吞掉解析异常
                # 并返回空列表——若在这里无条件置 True，就把"解析失败"错判成
                # "成功加载到 0 条"，随后落盘会把磁盘上尚可挽救的内容清空
                # （实测：57 字节损坏文件 → 被清成 `[]`）。
                self._loaded_ok = bool(getattr(self._storage, "last_load_ok", True))
            except Exception as e:
                self._loaded_ok = False
                logger.warning(f"存储后端读取失败: {e}")
        else:
            # 回退到 JSON 文件
            if self._drawers_file.exists():
                try:
                    with open(self._drawers_file, encoding="utf-8") as f:
                        data = json.load(f)
                    for d in data:
                        dr = Drawer.from_dict(d)
                        if dr.id in seen:
                            continue
                        seen.add(dr.id)
                        self._primary_ids.add(dr.id)
                        result.append(dr)
                    self._loaded_ok = True
                except Exception as e:
                    # 解析失败 ⇒ 内存里是"假空"，禁止后续落盘覆盖磁盘
                    self._loaded_ok = False
                    logger.warning(f"主 drawers.json 读取失败（已标记假空，禁止空写）: {e}")
            else:
                # 文件不存在 == 空库，这是**成功**判定（不是读取失败）
                self._loaded_ok = True

        # 合并只读源（v1 等），不加入 _primary_ids（保存时不写回）
        for extra in self._extra_drawers_files:
            if not extra.exists():
                continue
            try:
                with open(extra, encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    dr = Drawer.from_dict(d)
                    if dr.id in seen:
                        continue
                    seen.add(dr.id)
                    result.append(dr)
            except Exception as e:
                logger.warning(f"只读源 {extra} 读取失败: {e}")

        self._cache.set(cache_key, result)
        self._last_cache_time = now
        return result

    def _disk_has_records(self) -> bool:
        """权威存储当前是否已有记录（用于空写保护）。

        基于**磁盘实际条数**判断，而不是内存里的 `_primary_ids`——
        后者在"内存以为是空库"时恰好也是空集，会形成恒不触发的死守卫。

        ⚠ 解析失败（文件损坏）时必须返回 **True**（谨慎侧）：
        此时"读不出记录"不等于"没有记录"，磁盘上可能还有可挽救的内容。
        早期实现 `except: return False` 会让守卫失效——实测一个 133 字节的
        损坏文件被直接清成 `[]`（2 字节）。宁可拒绝一次合法写入
        （有 `_loaded_ok` 兜底，正常路径不会走到这里），也不能静默清库。
        """
        try:
            if self._storage is not None:
                drawers = self._storage.load()
                if getattr(self._storage, "last_load_ok", True):
                    return bool(drawers)
                # 解析失败：磁盘"有内容但读不出来" ⇒ 保守判为有记录
                return True
            if self._drawers_file.exists():
                with open(self._drawers_file, encoding="utf-8") as f:
                    return bool(json.load(f))
        except Exception:  # noqa: BLE001
            # 文件存在却解析失败 ⇒ 保守判为"有记录"，阻止空写覆盖
            return self._drawers_file.exists()
        return False

    @_synchronized
    def _save_drawers(self) -> bool:
        """保存抽屉到磁盘并刷新缓存（带脏检查 + 原子写，防止并发写入损坏文件）

        仅写回属于主文件的 drawer（_primary_ids），只读合并源不被修改。

        Returns:
            bool: **是否真的落盘**。`False` 表示被空写保护拦截（跳过保存）。
        返回值存在的意义：早期实现静默 `return`，调用方无从得知"我没保存"，
            于是 `remove_drawer()` 返回 `True` 而磁盘未更新——**静默的数据不一致**。
            这与本项目反复出现的 `except: return []` 是同一类失败模式，
            所以这里让"跳过"变成调用方可感知的事实。
        """
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            # 仅取主文件来源的 drawer 做脏检查与落盘
            primary_drawers = [d for d in self._drawers if d.id in self._primary_ids]

            # P0-0 修复：存储后端路径也必须受空写保护约束。
            # 下面 JSON 分支的守卫管不到这里——`JsonDrawerStorage.save()` /
            # `SqliteDrawerStorage.save()` 都是**无条件**写入，对 `[]` 零防护，
            # 于是"内存以为自己是空库"时会直接把非空存储清成 0 条
            # （实测：预置 3 条 → 0 条）。故在分派前统一做一次保护。
            #
            # ⚠ 判据必须区分**意图**，不能只看"结果形状"（空 vs 非空）：
            #   危险：内存从未成功加载（读异常）→ 内存空是**假空** → 落盘会清库 → 拦
            #   合法：加载成功后用户删光 → 内存空是**真空** → 必须落盘
            # 早期版本只判 `not primary_drawers and _disk_has_records()`，
            # 导致 `remove_drawer()` 删除**最后一条**时被误拦：
            # 返回 True 但磁盘没变 ⇒ 内存与磁盘静默不一致
            # （回归证据：tests/test_core.py::test_remove_drawer）。
            # 引入 `_loaded_ok` 后，两种场景被正确区分。
            if not primary_drawers and not self._loaded_ok and self._disk_has_records():
                logger.warning("跳过保存: 内存主集为空且主存从未成功加载，疑似读失败后的空库误写（数据保护）")
                return False

            if self._storage:
                try:
                    # 使用存储后端保存
                    self._storage.save(primary_drawers)
                    self._cache.invalidate()
                    return True
                except Exception as e:
                    logger.error(f"存储后端保存失败: {e}")
                    # 回退到 JSON 文件

            # JSON 文件保存逻辑
            try:
                if self._drawers_file.exists():
                    with open(self._drawers_file, encoding="utf-8") as f:
                        disk_data = json.load(f)
                    disk_ids = {x.get("id") for x in disk_data}
                    # 主文件在内存中的集合不可凭空丢失（合并源不计入），否则跳过以防误覆盖
                    missing = self._primary_ids - disk_ids
                    if missing and len(disk_data) >= len(primary_drawers):
                        logger.warning(f"跳过保存: 内存主文件集缺少 {len(missing)} 条磁盘记录")
                        return False
                    # P0-0 修复：空写保护（上面那条守卫在内存为空时**失效**——
                    # 内存为空 ⇒ _primary_ids 也是空集 ⇒ missing 为空 ⇒ 守卫不触发）。
                    # 实测（假 HOME，v1 预置 3 条）：_drawers=[] + _primary_ids=set()
                    # → 文件从 3 条被清成 0 条，这正是 v1 变成 `[]` 的可达路径。
                    # 判断必须基于**磁盘条数 > 0**（而不是 _primary_ids），否则又是
                    # 一个恒不触发的死守卫。
                    # 同时用 `_loaded_ok` 区分意图：加载成功后删空必须放行。
                    if disk_data and not primary_drawers and not self._loaded_ok:
                        logger.warning(
                            f"跳过保存: 内存主集为空且主存从未成功加载，磁盘有 "
                            f"{len(disk_data)} 条记录，疑似空库误写（数据保护）"
                        )
                        return False
            except Exception as e:
                # 磁盘文件损坏/不可读时记录警告，用内存数据原子覆写以修复损坏
                logger.warning(f"磁盘 drawers.json 读取失败，将用内存数据覆写: {e}")

            tmp_file = self._drawers_file.with_suffix(".json.tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump([d.to_dict() for d in primary_drawers], f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, self._drawers_file)
            self._cache.invalidate()
            return True

    def invalidate_cache(self) -> None:
        """手动刷新缓存"""
        self._cache.invalidate()

    def close(self) -> None:
        """关闭存储后端"""
        if self._storage:
            self._storage.close()

    # ── 抽屉操作 ──

    def add_drawer(self, drawer: Drawer) -> None:
        """添加记忆抽屉"""
        # P0-1: 必须同时清 MemoryStack 缓存 + storage 缓存。
        # _persist_supersede_update 用独立的 JsonDrawerStorage 实例写盘，
        # 但 stack._storage 有自己独立的缓存——不清它，_load_drawers() 读到
        # 旧数据（无 superseded_by），再保存回去就覆盖了 supersede 更新。
        self._cache.invalidate()
        self._last_cache_time = 0  # 强制 bypass TTL 检查
        if self._storage and hasattr(self._storage, "_cache"):
            self._storage._cache.clear()  # JsonDrawerStorage._cache 是 dict
        self._drawers = self._load_drawers()
        self._drawers.append(drawer)
        self._primary_ids.add(drawer.id)
        self._save_drawers()

    def add_drawers(self, drawers: list[Drawer]) -> None:
        """批量添加记忆抽屉"""
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            self._drawers = self._load_drawers()
            self._drawers.extend(drawers)
            for drawer in drawers:
                self._primary_ids.add(drawer.id)
            self._save_drawers()
            self._cache.invalidate()

    def update_drawer(self, drawer: Drawer) -> bool:
        """按 id 替换抽屉内容（P0-1：supersede 等场景的落盘）

        复用 save_incremental 的"按 id 集合删除 + 重新插入"思路；
        不同：返回 bool 让调用方知道是否真的替换了某条记录。

        Returns:
            True — 找到了匹配的 id 并完成替换；
            False — 未找到匹配 id（无操作）。
        """
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            self._drawers = self._load_drawers()
            found = False
            for i, d in enumerate(self._drawers):
                if d.id == drawer.id:
                    self._drawers[i] = drawer
                    found = True
                    break
            if not found:
                return False
            saved = self._save_drawers()
            if saved:
                self._cache.invalidate()
                # 顺便清掉 search_cache：supersede 写完后旧 drawer 的 metadata 变了，
                # 之前的查询结果（缓存里可能还把旧 drawer 当"未取代"返回）必须失效。
                try:
                    from pangu.memory.search_cache import get_search_cache

                    get_search_cache().clear()
                except Exception:
                    pass
            else:
                logger.warning(f"update_drawer({drawer.id[:8]}): 内存已替换但落盘被拦截")
            return found

    def _visible(self, drawers: list[Drawer]) -> list[Drawer]:
        """按当前请求的租户作用域裁剪（作用域为空 → 原样返回＝全库视角）。"""
        tenant = current_tenant()
        if not tenant:
            return drawers  # 全库视角＝系统自身，两条轴都不拦（见 metadata_readable）
        key_id = current_key_id()
        return [d for d in drawers if metadata_readable(d.metadata or {}, tenant, key_id, current_clearance())]

    def _read_drawers(self) -> list[Drawer]:
        """读路径入口：加载后按租户作用域裁剪。

        所有**读**方法都应走它，而不是 _load_drawers()。写路径（add/remove/save）必须
        继续用 _load_drawers() —— _save_drawers 落盘的是 self._drawers 全量，一旦写回
        裁剪后的列表就是把别的租户的数据删掉。
        """
        return self._visible(self._load_drawers())

    def get_drawers(self) -> list[Drawer]:
        """获取所有抽屉（读路径：受请求级租户作用域裁剪，见 _read_drawers）"""
        return self._read_drawers()

    def get_drawer_by_id(self, drawer_id: str) -> Drawer | None:
        """按 ID 获取抽屉（读路径：受租户作用域裁剪）

        作用域内不可见的条目**等同于不存在** —— 这是 by-id 系工具的租户闸门
        （冲突检查、重要性、supersede 链、删除、归档都先经此查询）：拿不到别的租户的
        drawer，就无法借 id 探测其内容，也无法在删除类工具里越权。
        """
        for d in self._read_drawers():
            if d.id == drawer_id:
                # 记录访问
                self._access_tracker[drawer_id] = self._access_tracker.get(drawer_id, 0) + 1
                self.consolidator.record_access(drawer_id)
                return d
        return None

    def count_drawers(self) -> int:
        """获取抽屉总数（读路径：本租户可见集合的规模）"""
        return len(self._read_drawers())

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
        """删除指定抽屉（自动备份 + 向量索引同步）

        写路径用**全库**快照；作用域非空时先做所有权检查 —— 本租户不可见的 id 视为
        不存在，拒绝删除（否则调用方可用别的租户的 id 越权删除）。
        """
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            if current_tenant() and not any(d.id == drawer_id for d in self._read_drawers()):
                logger.warning(f"remove_drawer({drawer_id}): 该条目在本租户作用域内不可见，拒绝删除")
                return False
            self._drawers = self._load_drawers()
            original_len = len(self._drawers)
            self._drawers = [d for d in self._drawers if d.id != drawer_id]
            if len(self._drawers) < original_len:
                self._backup_drawers()
                saved = self._save_drawers()
                if saved:
                    self._remove_from_vector_index([drawer_id])
                    self._cache.invalidate()
                else:
                    # 不再静默：落盘被拦时内存与磁盘已不一致，必须让调用方知道
                    logger.warning(
                        f"remove_drawer({drawer_id}): 删除已应用到内存但**未落盘**（被空写保护拦截），磁盘仍含该记录"
                    )
                return True
            return False

    def remove_drawers(self, drawer_ids: list[str]) -> int:
        """批量删除抽屉（自动备份 + 向量索引同步）

        同 remove_drawer：先按租户作用域过滤掉不可见的 id（越权保护），再全库快照写回。
        """
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            if current_tenant():
                visible = {d.id for d in self._read_drawers()}
                skipped = [i for i in drawer_ids if i not in visible]
                if skipped:
                    logger.warning(f"remove_drawers: 跳过 {len(skipped)} 个本租户不可见的 id（越权保护）")
                drawer_ids = [i for i in drawer_ids if i in visible]
                if not drawer_ids:
                    return 0
            self._drawers = self._load_drawers()
            ids_set = set(drawer_ids)
            original_len = len(self._drawers)
            self._drawers = [d for d in self._drawers if d.id not in ids_set]
            removed = original_len - len(self._drawers)
            if removed > 0:
                self._backup_drawers()
                saved = self._save_drawers()
                self._remove_from_vector_index(drawer_ids)
                self._cache.invalidate()
                if not saved:
                    logger.warning(
                        f"remove_drawers: 已从内存删除 {removed} 条但**未落盘**（被空写保护拦截），磁盘未同步"
                    )
            return removed

    def replace_all(self, drawers: list[Drawer]) -> bool:
        """整体替换主文件抽屉（恢复备份用）。

        与 add/remove 的差别：这是"把整个库换成另一份"的操作，所以额外做三件事：
        - 拒绝空列表：空备份恢复 == 清库（本仓出现过"内存假空 → 落盘清库"的失败模式，
          这里直接挡在入口；真要清空必须显式调 remove_drawers）
        - 落盘前自动快照（_backup_drawers）：恢复本身可回滚
        - 向量索引摘掉"恢复后已不存在"的 id，否则搜索会返回幽灵 id
        """
        # 与自主调度线程互斥（见 __init__._write_lock 注释）
        with self._write_lock:
            if not drawers:
                raise ValueError("replace_all 拒绝空列表（防清库）；要清空请显式调用 remove_drawers")
            self._backup_drawers()
            self._drawers = list(drawers)
            # 恢复的语义就是"库 == 这份备份"，故全部视为主文件来源
            self._primary_ids = {d.id for d in drawers}
            saved = self._save_drawers()
            if saved:
                keep = {d.id for d in drawers}
                try:
                    from pangu.memory.vector_index import get_vector_index

                    idx = get_vector_index()
                    stale = [i for i in list(getattr(idx, "_ids", [])) if i not in keep]
                    if stale:
                        self._remove_from_vector_index(stale)
                except Exception as e:
                    logger.warning(f"replace_all: 向量索引清理跳过（{e}）")
                self._cache.invalidate()
                try:
                    from pangu.memory.search_cache import get_search_cache

                    get_search_cache().clear()
                except Exception:
                    pass
            else:
                logger.warning("replace_all: 内存已替换但**未落盘**（被空写保护拦截）")
            return saved

        # ── 记忆栈接口 ──

    def wake_up(self, wing: str = None) -> str:
        """唤醒: L0 + L1 (~600-900 tokens)（读路径：本租户可见集合）"""
        parts = [self.l0.render(), ""]
        drawers = self._read_drawers()

        if wing:
            drawers = [d for d in drawers if d.wing == wing]

        l1_text = self.l1.generate(drawers)
        parts.append(l1_text)

        result = "\n".join(parts)
        _log_token_stats(
            "wake_up",
            {
                "L0": _estimate_tokens(parts[0]),
                "L1": _estimate_tokens(l1_text),
            },
        )
        return result

    def _dynamic_budget(self, level: str = "L2") -> int:
        """根据记忆总数动态计算 token 预算

        策略（基于每条记忆平均 40 token 估算）：
        - <50 条: 基础预算（800t）
        - 50-200 条: 标准预算（1500t）
        - 200-500 条: 增长预算（2500t）
        - >500 条: 限制预算（3000t，防止 context 溢出）
        """
        total = len(self._read_drawers())
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

    def recall(self, wing: str = None, room: str = None, n_results: int = 10, drawers: list | None = None) -> str:
        """按需回忆: L2（动态 token 预算截断）

        drawers: 显式指定候选集合。用于按调用方身份（租户）收口 —— 此前本方法只读
        自身存储，调用方算好的过滤集合无处传入，于是 `handle_recall` 里的租户过滤
        等于空转（实测：dsh 钥匙的 recall 返回了 default 租户的记忆，分母仍是全库
        125 条）。
        """
        candidates = self._read_drawers() if drawers is None else drawers
        budget = self._dynamic_budget("L2")
        result = self.l2.retrieve(candidates, wing=wing, room=room, n_results=n_results, token_budget=budget)
        _log_token_stats(
            "recall",
            {
                "L2": _estimate_tokens(result),
                "budget": budget,
                "total_drawers": len(candidates),
            },
        )
        return result

    def search(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> str:
        """深度搜索: L3（动态 token 预算截断）（读路径：本租户可见集合）"""
        drawers = self._read_drawers()
        budget = self._dynamic_budget("L3")
        result = self.l3.search(query, drawers, wing=wing, room=room, n_results=n_results, token_budget=budget)
        _log_token_stats(
            "search",
            {
                "L3": _estimate_tokens(result),
                "budget": budget,
                "query": query,
            },
        )
        return result

    # ── 巩固集成 ──

    def get_consolidation_stats(self) -> dict:
        """获取巩固统计信息（读路径：本租户可见集合）"""
        drawers = self._read_drawers()
        return self.consolidator.stats(drawers)

    def find_forgotten(self) -> list[Drawer]:
        """找出应被遗忘的记忆（读路径：本租户可见集合 —— 原先返回全库内容）"""
        drawers = self._read_drawers()
        return self.consolidator.find_forgotten(drawers)

    def find_compressible(self) -> list[Drawer]:
        """找出可压缩的记忆（读路径：本租户可见集合 —— 原先会把全库内容送去压缩）"""
        drawers = self._read_drawers()
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
            for v in checks.values()
            if isinstance(v, dict)
        )
        checks["status"] = "healthy" if all_ok else "degraded"

        return checks

    def status(self) -> dict:
        """记忆栈状态（含各层 token 估算 + 动态预算 + 搜索统计）（读路径：本租户可见集合）"""
        drawers = self._read_drawers()
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
            from pangu.memory.retrieval import get_search_history, get_search_stats

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
                    "utilization": f"{l2_tokens / l2_budget * 100:.0f}%",
                },
                "L3_deep_search": {
                    "tokens_sample": l3_sample,
                    "budget": l3_budget,
                    "utilization": f"{l3_sample / l3_budget * 100:.0f}%",
                },
            },
            "token_summary": {
                "always_load": always_load,
                "l2_budget": l2_budget,
                "l3_budget": l3_budget,
                "total_if_all": l0_tokens + l1_tokens + l2_tokens + l3_sample,
                "savings_vs_full": f"{(1 - always_load / (l0_tokens + l1_tokens + l2_tokens + l3_sample)) * 100:.0f}%",
            },
            "search_stats": search_stats,
            "total_drawers": len(drawers),
            "cache_size": len(self._cache),
            # 语义化命名（R3）：`cache_ttl` 未标明单位与所属对象，多个组件
            # 都有同名字段时无法区分。新名带对象前缀与单位后缀。
            # 旧字段保留以兼容既有调用方。
            "memory_stack_cache_ttl_seconds": self._cache_ttl,
            "cache_ttl": self._cache_ttl,
            "consolidation": self.get_consolidation_stats() if self.config.consolidation_enabled else None,
        }
