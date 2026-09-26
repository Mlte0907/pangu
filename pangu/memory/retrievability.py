"""记忆可检索性体检（2026-09-26）。

## 它解决什么

对每条重要记忆，用**它自己的内容**造一个探针查询去搜，看它能不能被搜回来。
搜不回来的，报告为「埋住了」。

## 它**不**解决什么（2026-09-26 实测，重要，别误读）

立项动机是：用户说「云端盘古是可以从宿主机连上的，这条我在别的会话说过，你没找到」
—— 那批信息**确实在记忆里**，但埋在一篇《dsh-remote-x 0.3.0 公网上线》中间，那篇的
主题是移动端登录。立项时把目标写成了「检测内容重要但埋在不相干记忆里的事实」。

**上线后实测证明它检测不到那个案例。** 定向验证（云端 max_memories=60）：
- 新写的独立记忆 `7b90f314`（云端盘古访问方式）→ 判为可检索 ✓
- 旧的 `1af98ad5`（dsh-remote-x 上线记录，SSH 信息埋在正文中间）→ **也判为可检索 ✗**

原因：体检问的是「用**它自己的**罕见词能不能搜到它」。而 `1af98ad5` 的罕见词是
`ai.jinlange.top` / `frps.toml` / `8444` —— 用这些词搜**确实**能搜到它。真实失败是
「按『云端盘古 怎么连』去搜能不能搜到」。**这是两个不同的问题。**

所以本任务实际检测的是「**难以用自身特征词检索**」，主要命中**叙述型**记忆（发布记录、
踩坑流水账）：它们的罕见词是内部标识符，没人会拿那些词去搜，因而搜不回自己。实测
40 条候选报 23、60 条报 38 —— 数字看着高，但多数正是这类**误报**。

要检测「跨主题埋藏的关键事实」，必须判断「用户会怎么问」，那是语义判断，得靠 LLM 或
agent 读这份报告来判断，规则版做不到。**别把这个任务当成那个问题的答案。**

## 成本

候选按重要度取前 `max_memories` 条（默认 40），每条 1 次搜索。实测 275 条语料下单次
搜索 0.1~0.5s ⇒ 单轮约 3~20s，24h 一次可接受。`max_memories=0` 表示全量（贵）。
"""

import json
import re
import time
from collections import Counter
from pathlib import Path

from ..core.palace import Drawer
from .encryption import decrypt

# 只保留「像专有名词/标识符」的词，目的是拿到有区分度的检索词，而不是「部署」「系统」
# 这种到处都是的词。**顺序有意义**：finditer 取最左匹配，同一起点按列出顺序优先，
# 所以 IPv4 必须排在纯数字之前 —— 否则 113.45.134.86 会被 `\d{2,}` 切成 "113"。
#
# 踩过的坑：最初没有 IPv4 分支，探针词造出来是 'ssh/id_rsa_113 19529 113'，
# "113" 纯属垃圾（IP 的第一段），拼进查询反而拉低相关性。
_TOKEN_RE = re.compile(
    r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?"  # IPv4（可带端口）：113.45.134.86 / 127.0.0.1:19529
    r"|[A-Za-z][\w]*(?:[./:_-][\w]+)+"  # 路径/标识：~/.ssh/id_rsa_113 / pangu/memory
    r"|[A-Za-z][\w]*(?:\.[A-Za-z][\w]+)+"  # 域名：example.com
    r"|\b[A-Z]{2,}\b"  # 全大写缩写：SSH / MCP / API
    r"|\b[a-z]+[A-Z]\w*\b"  # 驼峰：FastAPI / Drawer
    r"|\b[a-z]{3,}\b"  # 普通小写词：gradle / nginx / uvicorn —— 恰恰是常被搜的词
    r"|\b\d{4,}\b"  # 4 位以上数字：端口 19529（不要 2~3 位，那会切出 IP 碎片）
)
# 上面那条小写词分支是有意加的。早期版本只收「像标识符」的词，结果 gradle / nginx /
# uvicorn 这类**最常被搜的词全被丢掉**，探针造不出来 —— 实测「用 gradle 构建，ssh 连不上」
# 造出的是空串。区分「常见词」靠的是 build_probe_query 里的 doc_freq 排序，不是靠词形：
# 常见词文档频率高、自然排到后面取不到。_STOP 只拦真正的虚词。
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "were",
    "not", "but", "you", "are", "all", "can", "will", "http", "https", "www", "com",
    "一个", "这个", "那个", "可以", "没有", "就是", "因为", "所以",
}


def _plaintext(drawer: Drawer) -> str:
    """取明文。记忆在盘古里是 Fernet 密文落库（content 以 gAAAAA 开头）。

    解密失败要**显式跳过**而不是把密文当明文 —— 那是 2026-09-19 修过的同类坑
    （search/recall/hybrid/embeddings 四处都漏过）。
    """
    c = getattr(drawer, "content", "") or ""
    if isinstance(c, str) and c.startswith("gAAAAA"):
        try:
            return decrypt(c)
        except Exception:  # noqa: BLE001 — 密钥不匹配/数据损坏：这条跳过，不猜
            return ""
    return str(c)


def _tokenize(text: str) -> list[str]:
    out = []
    for m in _TOKEN_RE.finditer(text or ""):
        w = m.group(0)
        if len(w) < 2 or w.lower() in _STOP:
            continue
        out.append(w)
    return out


def build_probe_query(text: str, doc_freq: Counter, max_terms: int = 3) -> str:
    """从内容里挑 IDF 最高的几个词拼成探针查询。

    IDF 用语料内的文档频率近似：越少见的词越有区分度。全语料都出现的词（比如
    「盘古」出现在几十条里）排后面。取不到区分词时返回空串。
    """
    cands = _tokenize(text)
    if not cands:
        return ""
    uniq = list(dict.fromkeys(cands))  # 去重但保序
    scored = sorted(uniq, key=lambda w: (doc_freq.get(w.lower(), 0), -len(w)))
    return " ".join(scored[:max_terms])


def _candidates(drawers: list[Drawer], max_memories: int) -> list[Drawer]:
    """挑「值得体检」的记忆：已毕业（public）或高重要度优先。

    只查重要的：低重要度的记忆搜不到无所谓，混进体检只会稀释报告。
    """

    def rank(d: Drawer) -> tuple:
        md = d.metadata or {}
        return (1 if md.get("visibility") == "public" else 0, float(d.importance or 0))

    pool = [d for d in drawers if getattr(d, "id", None)]
    pool.sort(key=rank, reverse=True)
    return pool if max_memories <= 0 else pool[:max_memories]


def audit_retrievability(config, max_memories: int = 40, top_n: int = 10) -> dict:
    """跑一轮体检。返回可直接 JSON 序列化的报告。"""
    from .layers import MemoryStack

    from ..search.engine import HybridSearch

    started = time.time()
    token = None
    try:
        from .layers import reset_tenant_scope, set_tenant_scope

        # 全库视角：体检要看全部记忆，不该被当前请求的租户作用域裁掉
        token = set_tenant_scope("", "", 0)
        stack = MemoryStack(config=config)
        drawers = stack.get_drawers() or []
        if not drawers:
            return {"checked": 0, "buried": [], "note": "记忆库为空", "duration_ms": 0}

        doc_freq: Counter = Counter()
        texts: dict[str, str] = {}
        for d in drawers:
            t = _plaintext(d)
            texts[d.id] = t
            for w in set(w.lower() for w in _tokenize(t)):
                doc_freq[w] += 1

        engine = HybridSearch(config)
        cands = _candidates(drawers, max_memories)
        buried, ok = [], 0
        for d in cands:
            q = build_probe_query(texts.get(d.id, ""), doc_freq)
            if not q:
                continue
            try:
                hits = engine.search(q, drawers, n_results=top_n) or []
            except Exception:  # noqa: BLE001 — 单条搜索失败不该中断整轮体检
                continue
            ids = [h.get("id") for h in hits]
            if d.id in ids:
                ok += 1
            else:
                buried.append(
                    {
                        "id": d.id,
                        "head": (texts.get(d.id, "") or "")[:100],
                        "probe_query": q,
                        "rank": ids.index(d.id) + 1 if d.id in ids else None,
                        "importance": d.importance,
                        "visibility": (d.metadata or {}).get("visibility"),
                        "tags": (d.tags or [])[:6],
                    }
                )
        return {
            "checked": len(cands),
            "recall_ok": ok,
            "buried_count": len(buried),
            "buried": sorted(buried, key=lambda b: -(b.get("importance") or 0)),
            "duration_ms": round((time.time() - started) * 1000, 1),
        }
    finally:
        if token is not None:
            try:
                from .layers import reset_tenant_scope

                reset_tenant_scope(token)
            except Exception:  # noqa: BLE001
                pass


def report_path(config) -> Path:
    return Path(config.palace_path) / "retrievability_report.json"


def save_report(config, report: dict) -> Path:
    p = report_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_report(config) -> dict | None:
    p = report_path(config)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 报告文件损坏不该影响主流程
        return None
