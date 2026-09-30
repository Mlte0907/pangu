#!/usr/bin/env python3
"""用**当前默认模型**重算所有抽屉的 `metadata["embedding"]`，并原子写回。

为什么需要它（2026-09-30）
-------------------------
`ingestion._embed_and_store` 走 `ingestion._embed_text` → `get_onnx_embedder()` **无参**调用，
而那个无参默认值曾长期硬编码旧的纯英文 `all-MiniLM-L6-v2`。于是云端 418/418 条抽屉里
的向量**全部是英文模型算的**，而搜索侧 `VectorEmbedder` 用的是多语模型 —— 两套向量
不在同一空间（实测中文判别力 0.1209 vs 0.3789，差 3.1 倍）。

⚠ **改了模型就必须重算存量**，否则新旧向量混在同一个字段里被
`retrieval._search_vectors_bruteforce` 互相比较 —— 那比"全用旧模型"更糟。
`scripts/embed_all.py` **不能替代本脚本**：它重建的是 `vector_index`（纯内存 HNSW，
不落盘），而这里要改的是抽屉 metadata 里那个持久化字段。

安全性
------
* 写前把原文件复制成 `drawers.json.bak-<时间戳>`
* **原子写**：tmp + fs.flush + os.fsync + os.replace（与 `layers._save_drawers` 同款）
* 默认 `--dry-run`，必须显式 `--apply` 才落盘
* 每条都记 `metadata.embedding_model`，日后能一眼看出这条向量是谁算的

用法
----
    python scripts/rewrite_drawer_embeddings.py --dry-run     # 只报告
    python scripts/rewrite_drawer_embeddings.py --apply       # 真写（先自动备份）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pangu.core.config import PanguConfig  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="用当前默认模型重算抽屉向量")
    ap.add_argument("--apply", action="store_true", help="真写盘（默认只 dry-run）")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="显式声明只报告、不写盘（**本来就是默认行为**，加它只是让意图显眼）",
    )
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（调试用）")
    args = ap.parse_args()

    config = PanguConfig.load()
    drawers_file = Path(config.palace_path) / "drawers.json"
    if not drawers_file.exists():
        print(f"找不到 {drawers_file}")
        return 1

    # 延迟导入：构造嵌入器会加载 ~113MB 模型权重，dry-run 也要用到，但别污染 import 期
    from pangu.memory.ingestion import (
        EMBEDDING_DIM_LIMIT,
        MIN_EMBEDDING_NORM,
        _embed_text,
    )
    from pangu.memory.onnx_embedder import _default_model_id

    model_id = _default_model_id()
    print(f"模型（config.onnx_model_id 解析而来）: {model_id}")
    print(f"抽屉文件: {drawers_file}")

    with open(drawers_file, encoding="utf-8") as f:
        drawers = json.load(f)
    if not isinstance(drawers, list):
        print(f"顶层不是 list（是 {type(drawers).__name__}），结构与预期不符，**中止**")
        return 1
    print(f"共 {len(drawers)} 条")

    if args.limit:
        drawers = drawers[: args.limit]
        print(f"--limit 生效，只处理 {len(drawers)} 条")

    # 先探一条，确认模型可用再批量（避免跑了 300 条才发现模型加载不了）
    probe = next((d for d in drawers if d.get("content")), None)
    if probe is None:
        print("没有带正文的条目，没什么可做")
        return 0
    try:
        vec0 = _embed_text(probe["content"][:200])
    except Exception as e:  # noqa: BLE001
        print(f"模型不可用，中止：{type(e).__name__}: {e}")
        return 1
    if not vec0:
        print("模型返回空向量，中止")
        return 1
    print(f"探测成功，向量维度 {len(vec0)}")

    ok = skipped = failed = cleared = 0
    unchanged = 0
    t0 = time.time()
    for i, d in enumerate(drawers, 1):
        content = d.get("content") or ""
        md = d.setdefault("metadata", {})
        if len(content) < 10:
            # 正文太短：ingestion 侧本来也不会给它算向量。若存量有陈旧值，
            # **清掉** —— 混着两个模型的向量比没有更糟。
            if md.pop("embedding", None) is not None:
                md.pop("embedding_model", None)
                cleared += 1
            else:
                skipped += 1
            continue

        old_model = md.get("embedding_model")
        try:
            vec = _embed_text(content)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}] {d.get('id', '?')[:8]} 失败：{type(e).__name__}: {e}")
            failed += 1
            continue

        if not vec or all(abs(v) < MIN_EMBEDDING_NORM for v in vec):
            if md.pop("embedding", None) is not None:
                md.pop("embedding_model", None)
                cleared += 1
            else:
                skipped += 1
            continue

        md["embedding"] = list(vec[:EMBEDDING_DIM_LIMIT]) if len(vec) > EMBEDDING_DIM_LIMIT else list(vec)
        md["embedding_model"] = model_id
        md["embedding_dim"] = len(md["embedding"])
        md["embedded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        ok += 1
        if old_model == model_id:
            unchanged += 1
        if i % 50 == 0:
            print(f"  进度 {i}/{len(drawers)}（ok={ok} skip={skipped} fail={failed} clear={cleared}）")

    elapsed = time.time() - t0
    print()
    print(f"重算完成：ok={ok}（其中本来就是本模型 {unchanged}） skip={skipped} fail={failed} 清除陈旧向量={cleared}")
    print(f"耗时 {elapsed:.1f}s")

    # 抽查：确认写进去的向量确实变了（不是被跳过却仍留着旧值）
    sample = next((d for d in drawers if len(d.get("metadata", {}).get("embedding", [])) == 384), None)
    if sample:
        e = sample["metadata"]["embedding"]
        print(f"抽查 {sample.get('id', '?')[:8]}：dim={len(e)} 前 4 值={[round(float(v), 5) for v in e[:4]]}")
        print(f"       embedding_model={sample['metadata'].get('embedding_model')}")

    if not args.apply:
        print("\n**dry-run，未写盘**（要真写加 --apply）")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = drawers_file.with_suffix(f".json.bak-rewrite-emb-{stamp}")
    shutil.copy2(drawers_file, backup)
    print(f"\n已备份: {backup}")

    tmp = drawers_file.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(drawers, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, drawers_file)
    print(f"已原子写回: {drawers_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())