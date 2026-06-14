#!/usr/bin/env python3
"""测试自动提取功能"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '/home/xiaoxin/pangu')

from pangu.core.config import PanguConfig
from pangu.core.palace import Palace, Drawer
from pangu.memory.ingestion import remember

def load_drawers(palace_path: str) -> list[Drawer]:
    drawers_file = Path(palace_path) / "drawers.json"
    if not drawers_file.exists():
        return []
    with open(drawers_file, encoding="utf-8") as f:
        data = json.load(f)
    return [Drawer.from_dict(d) for d in data]

def extract_from_session(session_file: str) -> list[dict]:
    memories = []
    try:
        with open(session_file, encoding="utf-8") as f:
            content = f.read()
        for line in content.strip().split("\n")[:100]:  # 只处理前100行
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "message":
                    msg = data.get("message", {})
                    role = msg.get("role", "")
                    text = msg.get("content", "")
                    if isinstance(text, list):
                        text = " ".join(item.get("text", "") for item in text if isinstance(item, dict))
                    if text and len(text) > 50:
                        importance = 0.5
                        memories.append({
                            "content": text[:300],
                            "role": role,
                            "importance": importance,
                        })
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"解析失败: {e}")
    return memories

config = PanguConfig.load()
existing = load_drawers(config.palace_path)
print(f"现有记忆: {len(existing)} 条")

# 测试一个会话文件
session_dir = Path("/home/xiaoxin/.openclaw/agents/main/sessions")
session_files = list(session_dir.glob("*.jsonl"))
session_files = [f for f in session_files if "trajectory" not in f.name]

if session_files:
    test_file = session_files[0]
    print(f"\n测试文件: {test_file.name}")
    memories = extract_from_session(str(test_file))
    print(f"提取到 {len(memories)} 条记忆")
    
    # 只添加前3条
    for mem in memories[:3]:
        try:
            item_id, drawer = remember(
                raw_text=mem["content"],
                wing="main",
                room="test_extract",
                importance=mem["importance"],
                tags=["test_extract", mem["role"]],
                source="test",
                existing_drawers=existing,
            )
            existing.append(drawer)
            print(f"  ✓ {item_id[:8]}: {mem['content'][:50]}...")
        except Exception as e:
            print(f"  ✗ 失败: {e}")
    
    # 保存
    drawers_file = Path(config.palace_path) / "drawers.json"
    with open(drawers_file, 'w', encoding='utf-8') as f:
        json.dump([d.to_dict() for d in existing], f, ensure_ascii=False, indent=2)
    print(f"\n保存成功，总记忆数: {len(existing)}")
else:
    print("没有找到会话文件")
