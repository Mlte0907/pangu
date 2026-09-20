"""一次性触发知识结晶（绕过时间窗口，跳过 LLM 用规则式）"""
import os, json, time, sys
os.environ.setdefault("HOME", "/home/xiaoxin")
os.environ.setdefault("PANGU_ENCRYPTION", "off")

from pangu.core.config import PanguConfig
from pangu.memory.layers import MemoryStack
from pangu.memory.knowledge import get_knowledge_engine

cfg = PanguConfig.load().authoritative_memory_config()
stack = MemoryStack(config=cfg)
drawers = stack.get_drawers()
print(f"记忆总数: {len(drawers)}", flush=True)

# 直接用规则式结晶（跳过 LLM，避免网络超时）
knowledge_engine = get_knowledge_engine()
existing = knowledge_engine.list_knowledge()
covered = set()
for e in existing:
    covered.update(e.source_memories or [])

# 按主题分组
from collections import defaultdict
tag_groups = defaultdict(list)
for d in drawers:
    md = d.metadata if isinstance(d.metadata, dict) else {}
    if (md.get("admission") == "graduated"
            or md.get("last_feedback") in ("recall_success", "verified")
            or (d.importance or 0) >= 1.5):
        for tag in (d.tags or [])[:5]:
            tag_groups[tag].append(d)

print(f"已验证记忆主题组: {len(tag_groups)}", flush=True)
created = 0
for tag, group in sorted(tag_groups.items(), key=lambda x: -len(x[1])):
    if created >= 5:
        break
    if len(group) < 2:
        continue
    ids = {d.id for d in group}
    if ids <= covered:
        continue
    texts = []
    for d in group[:3]:
        first = str(d.content or "").strip().split("\n")[0][:60]
        if first:
            texts.append(first)
    if len(texts) < 2:
        continue

    title = f"【{tag}】{len(group)} 条经验的结晶"
    content = "；".join(texts)

    entry = knowledge_engine.create_knowledge(
        title=title,
        content=content,
        category="insight",
        source_memories=sorted(ids),
        tags=[tag],
        confidence=min(0.95, 0.5 + len(group) * 0.08),
        metadata={"model": "rule-based", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
    )
    covered.update(ids)
    created += 1
    print(f"  生成: {title} ({len(ids)} 条来源)", flush=True)

print(f"\n结晶完成: 新增 {created} 条知识")
total = knowledge_engine.get_stats()
print(f"知识库总计: {total['total']} 条")
