"""P2-1 模块处置清单：从真实入口出发做可达性分析，把模块分三类。

方法（不猜、不靠 grep 字符串）：
1. 用 ast 解析每个文件的 import（含函数内 import 与相对 import）；
2. 从入口集合出发求传递闭包 = 主链路；
3. 主链路之外的模块按「被引用关系 + 是否在 experimental/ + 有无动态 import」
   分成：真有用但没入口 / 实验性保留 / 概念性待删候选。

注意：动态 import（importlib / __import__ / 字符串注册表）无法静态解析，
脚本会单独标出这些引用，避免把「被动态加载」误判为死代码。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "pangu"

# 真实入口：进程启动时会被执行/导入的模块
ROOTS = [
    "pangu.api.server",        # FastAPI/REST 应用
    "pangu.server.mcp_server",  # MCP 服务
    "pangu.server.web_server",  # 旧 web（8866）
    "pangu.cli",                # CLI
    "pangu.client",             # Python 客户端
]


def modname(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def collect_modules() -> dict[str, Path]:
    mods: dict[str, Path] = {}
    for base in (PKG, ROOT / "experimental"):
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            mods[modname(p)] = p
    return mods


def relative_base(name: str, level: int, is_package: bool) -> str:
    """把相对 import 的 level 换算成绝对包前缀。

    关键区别：对**包**（`__init__.py`）而言 level=1 指包自身；对普通模块则是父包。
    这条差异曾让 `handlers/__init__.py` 里 `from . import multimodal` 被解析成
    `pangu.server.multimodal`（丢了一层），从而把 19 个 handler 的整棵子树都误判成
    「不可达」。
    """
    parts = name.split(".") if name else []
    if not is_package and parts:
        parts = parts[:-1]  # 模块：level 1 = 父包
    drop = level - 1
    if drop > 0:
        parts = parts[: len(parts) - drop] if drop <= len(parts) else []
    return ".".join(parts)


def parse_imports(path: Path, name: str, is_package: bool) -> tuple[set[str], set[str]]:
    """返回 (静态 import 目标集合, 动态 import 字符串集合)。"""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set(), set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = relative_base(name, node.level, is_package)
                if node.module:
                    base = f"{base}.{node.module}" if base else node.module
            else:
                base = node.module or ""
            for a in node.names:
                found.add(f"{base}.{a.name}" if base else a.name)

    dynamic = set(
        re.findall(r'import_module\(\s*["\']([\w\.]+)', src)
        + re.findall(r'__import__\(\s*["\']([\w\.]+)', src)
    )
    return found, dynamic


def resolve(target: str, mods: dict[str, Path]) -> str | None:
    """把 import 目标解析到本包内的模块（尽量精确，否则取父包）。"""
    if target in mods:
        return target
    parts = target.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in mods:
            return cand
        parts.pop()
    return None


def main() -> int:
    mods = collect_modules()
    edges: dict[str, set[str]] = {}
    dyn_edges: dict[str, set[str]] = {}
    dynamic_refs: dict[str, set[str]] = {}  # 被动态引用的模块 -> 引用者

    for name, path in mods.items():
        found, dynamic = parse_imports(path, name, is_package=path.name == "__init__.py")
        resolved = {r for r in (resolve(t, mods) for t in found) if r and r != name}
        edges[name] = resolved
        dyn_edges[name] = {r for r in (resolve(t, mods) for t in dynamic) if r and r != name}
        for d in dyn_edges[name]:
            dynamic_refs.setdefault(d, set()).add(name)

    # 隐式边：导入任何子模块都会先执行其祖先包的 __init__，因此祖先包（连同包内
    # 静态导入的模块）实际都会被加载。缺了这条边，会把「只被包 __init__ 导入」的
    # 模块误判成死代码（实例：pangu.server.websocket_server 只被 pangu/server
    # /__init__.py 导入，而它正是插件 /ws 事件通道的实现）。
    for name in list(mods):
        parts = name.split(".")
        for i in range(1, len(parts)):
            ancestor = ".".join(parts[:i])
            if ancestor in mods:
                edges[name].add(ancestor)

    # 传递闭包
    reachable: set[str] = set()
    stack = [r for r in ROOTS if r in mods]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(edges.get(cur, ()))
        stack.extend(dyn_edges.get(cur, ()))

    outside = sorted(set(mods) - reachable)

    # 每个模块的行数与 docstring 首行
    def info(m: str) -> tuple[int, str]:
        text = mods[m].read_text(encoding="utf-8")
        try:
            doc = ast.get_docstring(ast.parse(text)) or ""
        except SyntaxError:
            doc = ""
        first = next((l.strip() for l in doc.splitlines() if l.strip()), "")
        return len(text.splitlines()), first[:70]

    # 被主链路引用的（作为「被谁 import」的证据）
    inbound: dict[str, set[str]] = {}
    for src, tgts in {**edges, **{k: v for k, v in dyn_edges.items() if k not in edges}}.items():
        for t in tgts:
            inbound.setdefault(t, set()).add(src)

    experimental = [m for m in outside if m == "experimental" or m.startswith("experimental.")]
    normal = [m for m in outside if m not in experimental]

    def report(title: str, group: list[str]) -> None:
        print(f"\n=== {title}（{len(group)} 个）")
        for m in group:
            loc, doc = info(m)
            refs = inbound.get(m, set())
            dyn = " [动态引用]" if m in dynamic_refs else ""
            who = f" <- {', '.join(sorted(refs)[:3])}" if refs else " <- 无任何引用"
            print(f"  {m}  ({loc} 行){dyn}{who}")
            if doc:
                print(f"      {doc}")

    print(f"总模块数 {len(mods)}；主链路可达 {len(reachable)}；主链路外 {len(outside)}")
    print(f"其中 experimental 容器内 {len(experimental)}；容器外 {len(normal)}")
    report("主链路外 · experimental 容器内", experimental)
    report("主链路外 · 容器外", normal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
