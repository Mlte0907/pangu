#!/usr/bin/env python3
"""为所有抽屉生成 ONNX 嵌入并重建向量索引"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.config import PanguConfig
from pangu.memory.embedding import get_embedding_service
from pangu.memory.vector_index import get_vector_index


def main():
    config = PanguConfig.load()
    drawers_file = Path(config.palace_path) / "drawers.json"

    if not drawers_file.exists():
        print("No drawers.json found")
        return 1

    with open(drawers_file, encoding="utf-8") as f:
        drawers = json.load(f)

    print(f"Loaded {len(drawers)} drawers")

    embed_svc = get_embedding_service()
    vector_idx = get_vector_index()

    # 清空旧索引
    vector_idx.clear()

    embedded = 0
    skipped = 0
    failed = 0
    start = time.time()

    for i, d in enumerate(drawers):
        content = d.get("content", "")
        if not content or len(content) < 10:
            skipped += 1
            continue

        # 检查是否已有嵌入
        existing_emb = d.get("metadata", {}).get("embedding")
        if existing_emb and len(existing_emb) == 384:
            vector_idx.add(existing_emb, d["id"])
            embedded += 1
            continue

        # 生成嵌入
        try:
            embedding = embed_svc.embed(content)
            if embedding and len(embedding) == 384:
                # 保存到 drawer metadata
                if "metadata" not in d:
                    d["metadata"] = {}
                d["metadata"]["embedding"] = embedding
                d["metadata"]["embedding_skipped"] = False
                d["metadata"]["embedding_dim"] = 384
                d["metadata"]["embedded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

                # 添加到向量索引
                vector_idx.add(embedding, d["id"])
                embedded += 1
            else:
                failed += 1
                print(f"  [{i}] Bad embedding for {d['id'][:8]}: dim={len(embedding) if embedding else 0}")
        except Exception as e:
            failed += 1
            print(f"  [{i}] Failed for {d['id'][:8]}: {e}")

        # 每 5 条打印进度
        if (i + 1) % 5 == 0:
            print(f"  Progress: {i+1}/{len(drawers)} (embedded={embedded}, skipped={skipped}, failed={failed})")

    elapsed = time.time() - start

    # 保存更新后的 drawers（含嵌入）
    with open(drawers_file, "w", encoding="utf-8") as f:
        json.dump(drawers, f, ensure_ascii=False, indent=2)

    # 保存向量索引
    vector_idx._save()

    print(f"\n=== 完成 ===")
    print(f"  总计: {len(drawers)} 抽屉")
    print(f"  嵌入成功: {embedded}")
    print(f"  跳过: {skipped}")
    print(f"  失败: {failed}")
    print(f"  耗时: {elapsed:.2f}s")
    print(f"  向量索引大小: {vector_idx.size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
