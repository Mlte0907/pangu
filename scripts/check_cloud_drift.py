#!/usr/bin/env python3
"""云端漂移体检：本地仓库 vs 云端 `/root/pangu`（云端**不是 git 仓库**）。

为什么需要它
------------
云端没有版本控制，所以「本地改了」不会自动过去，「云端被谁改过」也没人提醒。
§10 已知坑第 7 条记的就是一次真实事故：当天修的三个洞，**回归测试和清理脚本一个都没
部署到云端**，线上没有任何测试在保护那三个修复，而且**没有任何症状**。

本脚本把那条教训变成可执行的检查，并且回答一个关键问题：

    差异是「云端落后」还是「有人在云端手改」？

两者的处置完全相反 —— 前者 scp 同步即可，后者必须人工判断（可能是有意的热修，
覆盖上去会丢；也可能是别人改错了，得先问）。判定办法：**拿云端文件的内容去比对本地
git 的历史版本**。命中某个旧提交 = 云端落后；**一个版本都命中不了 = 云端被手改过**。

用法
----
    python scripts/check_cloud_drift.py                # 用默认主机
    python scripts/check_cloud_drift.py --host 1.2.3.4 --key ~/.ssh/id_rsa_x
    python scripts/check_cloud_drift.py --json         # 机器可读

退出码：0 = 无「云端手改」的文件；1 = 有（**需要人工处理**，别直接覆盖）。
「云端落后 / 本地缺失 / 云端多余」不算失败，会打印出来供同步时参考。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 排除：虚拟环境 / VCS / 缓存 / 运行期产物 / 二进制数据
EXCLUDE_DIRS = {
    ".venv", ".git", "__pycache__", "node_modules", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dist", "build", ".idea", ".vscode",
}
# 运行期产物 / 二进制数据。
# `.coverage` 是 pytest-cov 的数据文件：`pytest --cov` 一跑就生成，属纯产物、
# 从不部署，漏掉它会让漂移体检每次都报「本地有、云端缺」（2026-10-02 实测）。
EXCLUDE_SUFFIX = (".pyc", ".log", ".db", ".db-shm", ".db-wal", ".orig", ".rej", ".tgz", ".tar.gz", ".coverage")

# 有意不同步的路径（附理由，改动前请先确认理由仍成立）
EXCLUDE_PATHS = {
    # 本仓内嵌的 dsh-pangu 副本是**故意落后**的：DSH 真正加载的插件在
    # /home/xiaoxin/dsh-pangu-src（以 link: 进 ~/.dsh/profiles/web）。
    # 同步这份副本只会制造「改错地方」的错觉，见 AGENTS.md。
    "plugins/dsh-pangu",
}

REMOTE_FIND = r"""
cd {root} && find . -type f \
  -not -path "./.venv/*" -not -path "./.git/*" \
  -not -path "*/__pycache__/*" \
  -not -path "./node_modules/*" -not -path "./.pytest_cache/*" -not -path "./.ruff_cache/*" \
  -not -name "*.pyc" -not -name "*.log" -not -name "*.coverage" \
  -not -name "*.db" -not -name "*.db-shm" -not -name "*.db-wal" \
  -not -name "*.orig" -not -name "*.rej" -not -name "*.bak*" \
  -print0 | xargs -0 -I{{}} sh -c 'printf "%s  %s\n" "$(md5sum "{{}}" | cut -d" " -f1)" "{{}}"' \
  | sort -k2
"""


def _excluded(rel: str) -> bool:
    # 归一化：去掉 "./" 前缀，否则 startswith(EXCLUDE_PATHS) 永远不命中
    rel = rel[2:] if rel.startswith("./") else rel
    parts = Path(rel).parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if rel.endswith(EXCLUDE_SUFFIX):
        return True
    return any(rel == p or rel.startswith(p + "/") for p in EXCLUDE_PATHS)


def local_inventory() -> dict[str, str]:
    inv: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = "./" + str(full.relative_to(REPO))
            if _excluded(rel):
                continue
            inv[rel] = hashlib.md5(full.read_bytes()).hexdigest()
    return inv


def remote_inventory(host: str, key: str, root: str) -> dict[str, str]:
    if not Path(key).exists():
        print(
            f"❌ 私钥不存在：{key}\n"
            f"   这把钥匙只在**开发机**上；要在云端跑体检，请显式指定：\n"
            f"     python scripts/check_cloud_drift.py --host <ip> --key <开发机上的私钥路径>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    script = REMOTE_FIND.format(root=root)
    out = subprocess.run(
        ["ssh", "-4", "-o", "StrictHostKeyChecking=no", "-i", key, f"root@{host}", script],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        print(f"❌ 连不上云端 {host}：{out.stderr.strip()[:200]}", file=sys.stderr)
        raise SystemExit(2)
    inv: dict[str, str] = {}
    for ln in out.stdout.splitlines():
        if "  " not in ln:
            continue
        h, f = ln.split("  ", 1)
        inv[f.strip()] = h.strip()
    return inv


def classify_remote_file(rel: str, remote_md5: str) -> tuple[str, str]:
    """云端这个文件是「本地 git 的旧版本」还是「谁手改的」？

    返回 (kind, detail)：kind ∈ {stale, hand-edited, untracked}
      stale       —— 命中本地 git 某个历史版本 ⇒ 云端落后，可安全同步
      hand-edited —— **一个历史版本都命中不了** ⇒ 云端有本地 git 里不存在的改动
      untracked   —— 本地 git 从未跟踪过这个路径（例如新增后又删除）
    """
    p = subprocess.run(["git", "log", "--format=%H", "--", rel], cwd=REPO,
                       capture_output=True, text=True).stdout.split()
    for rev in p:
        blob = subprocess.run(["git", "show", f"{rev}:{rel.lstrip('./')}"], cwd=REPO,
                              capture_output=True).stdout
        if blob and hashlib.md5(blob).hexdigest() == remote_md5:
            msg = subprocess.run(["git", "log", "-1", "--format=%h %ad", "--date=short", rev],
                                 cwd=REPO, capture_output=True, text=True).stdout.strip()
            return "stale", msg
    return "hand-edited", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="云端漂移体检")
    ap.add_argument("--host", default=os.environ.get("PANGU_CLOUD_HOST", "113.45.134.86"))
    # 注意：云端**自己**没有那把私钥（它在开发机上），所以在云端跑这个脚本
    # 必须显式指到开发机的密钥路径，否则会静默退回 /root/.ssh/… 然后报"连不上"。
    ap.add_argument(
        "--key",
        default=os.environ.get("PANGU_SSH_KEY", str(Path.home() / ".ssh/id_rsa_113")),
    )
    ap.add_argument("--root", default="/root/pangu")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    L = local_inventory()
    R = remote_inventory(args.host, args.key, args.root)

    same = [f for f in sorted(set(L) & set(R)) if L[f] == R[f]]
    differ = [f for f in sorted(set(L) & set(R)) if L[f] != R[f]]
    only_local = sorted(set(L) - set(R))
    only_remote = sorted(set(R) - set(L))

    stale, hand = [], []
    for f in differ:
        kind, detail = classify_remote_file(f, R[f])
        (stale if kind == "stale" else hand).append((f, detail))

    if args.json:
        print(json.dumps({
            "identical": len(same), "differ": len(differ),
            "cloud_stale": [f for f, _ in stale], "cloud_hand_edited": [f for f, _ in hand],
            "only_local": only_local, "only_cloud": only_remote,
        }, ensure_ascii=False, indent=2))
        return 1 if hand else 0

    print(f"本地 {len(L)} 文件 / 云端 {len(R)} 文件（已排除 {', '.join(sorted(EXCLUDE_PATHS))}）\n")
    print(f"✅ 一致            {len(same)}")
    print(f"🕐 云端落后（可同步）{len(differ)}")
    for f, d in stale:
        print(f"     {f}   ← 云端是本地 {d or '某个旧提交'} 的版本")
    print(f"🚨 云端被手改过      {len(hand)}")
    for f, _ in hand:
        print(f"     {f}   ← **本地 git 历史里找不到这个版本，别直接覆盖，先问**")
    print(f"\n➕ 本地有、云端缺    {len(only_local)}")
    for f in only_local:
        print(f"     {f}")
    print(f"➖ 云端有、本地缺    {len(only_remote)}")
    for f in only_remote:
        print(f"     {f}")

    if hand:
        print(f"\n结论：**{len(hand)} 个文件云端有本地不存在的改动**，必须人工确认后再动。")
        return 1
    print("\n结论：没有「云端手改」的漂移；其余都是可安全同步的部署滞后 / 缺失文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())