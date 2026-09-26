#!/usr/bin/env python3
"""生成「文件职责索引」→ docs/FILE_INDEX.md。

**为什么自动生成**：盘古 345 个 py 文件、10.6 万行。手写索引一定腐烂，而索引腐烂比
没有索引更糟（它会误导人）。所以索引由本脚本从真实目录树 + 每个文件的 docstring 首句
生成，测试 `tests/test_file_index.py` 负责保鲜。

用法：
    .venv/bin/python scripts/gen_file_index.py            # 写入 docs/FILE_INDEX.md
    .venv/bin/python scripts/gen_file_index.py --check     # 只校验是否最新（CI 用）
    .venv/bin/python scripts/gen_file_index.py --stdout    # 打到标准输出，便于预览
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "FILE_INDEX.md"

SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}


def skipped(rel: Path) -> str | None:
    """返回跳过原因，None 表示不跳过。

    点开头的目录一律跳过：2026-09-26 在云端实测到 `.bak-decrypt-fix/` 里的 4 个
    旧版 .py 被当成正常文件数进索引（343 里占 4 个），索引就开始撒谎了。
    备份目录是排查时留下的，不属于「这个仓库现在是什么」。
    """
    for part in rel.parts[:-1]:
        if part in SKIP_DIRS or part.startswith("."):
            return part
    return None

# 一级目录的中文说明（手写，属于「推导不出来」的那部分）
SUBSYSTEMS = {
    "pangu/core": "核心设施：配置、LLM 接入、加密、哈希、缓存、宫殿数据模型",
    "pangu/memory": "记忆系统主体（136 文件）：存取管道、搜索、知识、生命周期、质量治理、推理",
    "pangu/search": "搜索层：嵌入引擎 + 混合检索引擎",
    "pangu/api": "FastAPI 层：路由、鉴权（ABAC/RBAC/JWT）、平台 Token、MCP-HTTP 传输",
    "pangu/server": "服务器层：MCP 服务器、Web 服务器、WebSocket、工具 handler 与暴露面",
    "pangu/wiki": "Wiki 知识页引擎",
    "pangu/store": "存储 schema 与增量迁移",
    "pangu/mining": "记忆挖掘：从外部来源提取记忆",
    "pangu/observability": "可观测性：健康检查、Prometheus 指标、OpenTelemetry 追踪",
    "pangu/plugins": "插件系统",
    "tests": "测试",
    "scripts": "运维脚本",
    "docs": "文档",
    "deploy": "部署配置",
    "monitoring": "监控配置",
    "experimental": "实验性功能",
}

HEADER = """<!-- 本文件由 scripts/gen_file_index.py 自动生成，**不要手改**。 -->
<!-- 改动生成器后重新运行；tests/test_file_index.py 会校验它与真实目录树一致。 -->

# 盘古文件职责索引

> 全仓库 `*.py` 的逐文件职责。**行数**用于判断体量，**首句 docstring** 是职责摘要。
> 想了解「盘古是什么 / 怎么跑 / 架构与边界」→ 读 [`MAINTAINERS.md`](../MAINTAINERS.md)，本文件只回答「哪个文件干什么」。

"""

FOOTER = """
---

## 怎么读这个索引

- **改动前**：先在 `MAINTAINERS.md` 找相关子系统，再到这里定位文件。
- **改动后**：`tests/test_file_index.py` 会校验索引与真实目录树一致；新增文件忘了重新生成
  就会红。
- docstring 缺失的文件会标 `(无 docstring)` —— 那本身是个信号，说明该文件缺文档。
"""


def first_docstring(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError) as e:
        return f"(解析失败: {type(e).__name__})"
    doc = ast.get_docstring(tree)
    if not doc:
        return "(无 docstring)"
    line = doc.strip().split("\n")[0].strip()
    return line or "(空 docstring)"


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def group_key(rel: Path) -> str:
    """分组键：`pangu/xxx/...` 归到 `pangu/xxx`，其余按首段。

    早期版本只用首段，结果 `pangu/core`、`pangu/memory` 全被并进 `pangu/`，
    索引失去导航价值。
    """
    parts = rel.parts
    if parts[0] == "pangu" and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0] if len(parts) > 1 else "(仓库根)"


def display_path(rel: Path, group: str) -> str:
    """组内显示相对路径，避免多个 `__init__.py` 无法分辨。"""
    try:
        return str(rel.relative_to(Path(group)))
    except ValueError:
        return str(rel)


def collect() -> dict[str, list[tuple[str, int, str]]]:
    groups: dict[str, list[tuple[str, int, str]]] = {}
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if skipped(rel) is not None:
            continue
        key = group_key(rel)
        groups.setdefault(key, []).append((display_path(rel, key), count_lines(p), first_docstring(p)))
    return groups


def render() -> str:
    groups = collect()
    out = [HEADER]
    total_files = sum(len(v) for v in groups.values())
    total_lines = sum(l for v in groups.values() for _, l, _ in v)
    out.append(f"共 **{total_files}** 个 py 文件 / **{total_lines:,}** 行。\n\n")
    for top in sorted(groups, key=lambda k: -sum(l for _, l, _ in groups[k])):
        files = sorted(groups[top], key=lambda t: t[0])
        sub = sum(l for _, l, _ in files)
        desc = SUBSYSTEMS.get(top, "")
        out.append(f"\n## `{top}/` — {len(files)} 文件 / {sub:,} 行\n")
        if desc:
            out.append(f"\n{desc}\n")
        out.append("\n| 文件 | 行 | 职责（首句 docstring） |\n")
        out.append("| --- | ---: | --- |\n")
        for rel, lines, doc in files:
            out.append(f"| `{rel}` | {lines} | {doc} |\n")
    out.append(FOOTER)
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验是否最新，不写入")
    ap.add_argument("--stdout", action="store_true", help="打到标准输出")
    args = ap.parse_args()

    content = render()
    if args.stdout:
        sys.stdout.write(content)
        return 0
    if args.check:
        if not OUT.exists():
            print(f"{OUT} 不存在，请运行 scripts/gen_file_index.py", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != content:
            print(
                f"{OUT.relative_to(ROOT)} 已过期（目录树或 docstring 变了）。"
                f"请运行: .venv/bin/python scripts/gen_file_index.py",
                file=sys.stderr,
            )
            return 1
        print("文件索引是最新的。")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    n = sum(1 for line in content.splitlines() if line.startswith("| `"))
    print(f"已写入 {OUT.relative_to(ROOT)}（{n} 个文件条目）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
