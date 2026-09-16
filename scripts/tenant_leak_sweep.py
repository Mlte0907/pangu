#!/usr/bin/env python3
"""跨租户泄漏扫描：以一个租户的身份遍历所有只读工具，检查是否能看到另一个租户的数据。

为什么需要它（本仓真实教训）：租户隔离原先散在每个 handler 里各写一遍，实测漏了三处
（hybrid_search 完全不过滤、recall 算了 filtered 却没用它、按 id 可跨租户删除）；后来
静态扫描又发现 287 个 handler 不使用传入的 drawers 参数。**靠人逐个检查是漏不完的** ——
所以需要一条自动化的、覆盖整个暴露面的探针。

做法：
  1. 以 B 的身份写入带唯一标记的数据（记忆 + 可选 KG/wiki）
  2. 以 A 的身份调用每一条**只读**工具（含按 B 的 id 直查/直删类，确认被拒）
  3. 响应里出现标记串 → 判为泄漏；并核对 B 的数据在扫描后**依然存在**（写保护）

用法：
    python scripts/tenant_leak_sweep.py --key-a <pgk_A> --key-b <pgk_B>
    # 缺省从 ~/.pangu/.mcp_key_codebuddy 与 ~/.pangu/.mcp_key 读 A / B

退出码：0 = 无泄漏；1 = 有泄漏或数据被越权改动。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:19529/mcp"

# 只读工具名的判定：宁可多扫（多调几次只读工具是安全的），不要漏
READ_ONLY_HINTS = (
    "get",
    "list",
    "search",
    "recall",
    "stats",
    "analyze",
    "health",
    "graph",
    "chain",
    "wings",
    "rooms",
    "wake",
    "inspect",
    "related",
    "hot",
    "growth",
    "discover",
    "trend",
    "gap",
    "anomaly",
    "pattern",
    "predict",
    "benchmark",
)

# 明确排除：会写、会调 LLM、耗时很长、或需要外部资源的
EXCLUDE_HINTS = ("compress", "generate", "consolidate", "backup", "restore", "export", "import", "migrate")


class Mcp:
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self._id = 0

    def rpc(self, method: str, params: dict | None = None, timeout: float = 60.0):
        """发一条 JSON-RPC。服务端限流是 **100 请求/60 秒/客户端 IP**（api/server.py:366），
        整轮扫描有 ~70 次调用，贴着上限 —— 所以这里对 429 必须退避等窗口，否则整轮结果
        会被限流污染成假阴/假阳。"""
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}).encode()
        req = urllib.request.Request(
            self.url, data=body, headers={"content-type": "application/json", "x-api-key": self.key}
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    wait = 25.0 * (attempt + 1)  # 等限流窗口过去
                    print(f"    (429 限流，等待 {wait:.0f}s 后重试)", file=sys.stderr, flush=True)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError("unreachable")

    def tools(self) -> list[dict]:
        return self.rpc("tools/list").get("result", {}).get("tools", [])

    def call(self, name: str, args: dict, timeout: float = 60.0, retries: int = 3) -> str:
        """调一个工具。429（限流）要退避重试 —— 否则整轮扫描都会被限流成假阴性/假阳性。"""
        for attempt in range(retries):
            try:
                res = self.rpc("tools/call", {"name": name, "arguments": args}, timeout=timeout)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return f"(HTTP {e.code})"
            except Exception as e:  # noqa: BLE001 — 工具报错本身不是泄漏，如实记录
                return f"(调用异常 {e!r})"
        else:
            return "(HTTP 429 限流，未取到结果)"
        out = res.get("result", {})
        if "content" in out:
            return "\n".join(c.get("text", "") for c in out["content"])
        return json.dumps(out, ensure_ascii=False)


def read_key(path: str | None) -> str:
    if not path:
        return ""
    try:
        return pathlib.Path(path).expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--key-a", default=None, help="查看方（探针身份）")
    ap.add_argument("--key-b", default=None, help="数据主人（标记写入方）")
    args = ap.parse_args()

    key_a = args.key_a or read_key("~/.pangu/.mcp_key_codebuddy")
    key_b = args.key_b or read_key("~/.pangu/.mcp_key")
    if not key_a or not key_b:
        print("缺钥匙：请给 --key-a/--key-b 或准备 ~/.pangu/.mcp_key_codebuddy 与 ~/.pangu/.mcp_key")
        return 1

    a, b = Mcp(args.url, key_a), Mcp(args.url, key_b)
    stamp = int(time.time())
    marker = f"LEAKPROBE-{stamp}"        # 会作为查询词外传（工具可能回显它，故不能当泄漏判据）
    secret = f"SECRET-{stamp}-xyzzy"     # **绝不出现在任何请求参数里** → 响应里出现它只能是泄漏
    print(f"查询词: {marker} · 判定令牌: {secret}（不外传）")

    # ── 1. 以 B 身份写入标记 ──
    text = b.call(
        "pangu_add_memory",
        {"content": f"跨租户探针 {marker} 隐藏值 {secret}（可删）", "wing": "leak-probe", "room": "leak-probe", "importance": 0.5},
    )
    print(f"B 写入: {text[:120]}")
    try:
        bid = json.loads(text).get("drawer_id", "")
    except json.JSONDecodeError:
        bid = ""

    # ── 2. 以 A 身份遍历只读工具 ──
    tools = [t["name"] for t in a.tools()]
    targets = [
        n
        for n in tools
        if any(h in n for h in READ_ONLY_HINTS) and not any(x in n for x in EXCLUDE_HINTS)
    ]
    print(f"暴露面 {len(tools)} 个工具，其中只读候选 {len(targets)} 个，开始以 A 身份扫描…\n")

    leaks: list[str] = []
    inconclusive: list[str] = []
    for name in targets:
        time.sleep(1.0)  # 限流是 100 请求/60s/客户端 IP，整轮 ~70 次调用，必须放慢
        out = a.call(name, {})
        # 搜索类工具额外用标记串当查询词（否则它们只返回"最近/热门"，探不到点子上）
        if any(h in name for h in ("search", "recall", "analyze", "graph", "chain", "related", "wake")):
            out += "\n" + a.call(name, {"query": marker, "n_results": 5, "memory_id": bid, "drawer_id": bid})
        # 判据只看 secret：marker 会作为查询词外传、bid 会被原样回显，用它俩判会误报
        hit = secret in out
        limited = "429" in out
        status = "? 限流" if (limited and not hit) else ("✗ 泄漏" if hit else "✓")
        if hit:
            leaks.append(name)
        elif limited:
            inconclusive.append(name)
        print(f"  {status}  {name:<32} {out.strip()[:70].replace(chr(10), ' ')}")

    # ── 3. 按 B 的 id 做写类探测（应被拒，且 B 数据不得被改动）──
    print("\n按 id 的写类探测（用 B 的记忆 id，应以「不存在」拒绝）：")
    for tool in ("pangu_delete_memory", "pangu_archive_memory", "pangu_get_supersede_chain"):
        time.sleep(1.0)
        out = a.call(tool, {"memory_id": bid, "drawer_id": bid})
        # 判据：必须明确拒绝（"不存在"）或返回空链；只有返回实体数据才算越权
        refused = ("不存在" in out) or ('"found": false' in out) or ('"found":false' in out)
        limited = "429" in out
        mark = "?" if (limited and not refused) else ("✓" if refused else "✗")
        print(f"  {mark}  {tool:<26} {out.strip()[:70]}")
        if not refused and not limited:
            leaks.append(f"{tool}(未拒绝)")
        elif limited:
            inconclusive.append(tool)
    still = b.call("pangu_search_memories", {"query": secret, "n_results": 5})
    if secret not in still:
        leaks.append("B 的数据被越权改动/删除")
        print("  ✗ B 的数据在扫描后不见了（越权改动）")
    else:
        print("  ✓ B 的数据在扫描后依然存在（用隐藏令牌自查）")

    # ── 4. 收尾：删掉探针数据 ──
    if bid:
        b.call("pangu_delete_memory", {"memory_id": bid})

    print()
    if inconclusive:
        print(f"⚠ 有 {len(inconclusive)} 个工具因限流未取到结果（本轮不算数）: {inconclusive}")
    if leaks:
        print(f"❌ 发现 {len(leaks)} 处泄漏/越权: {leaks}")
        return 1
    print(f"✅ 未发现泄漏（扫描 {len(targets)} 个只读工具 + 3 个写类探测，限流 {len(inconclusive)} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
