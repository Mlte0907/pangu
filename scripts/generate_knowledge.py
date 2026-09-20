#!/usr/bin/env python3
"""盘古知识生成脚本 — 从记忆中提取知识

读取所有记忆，按来源分组，使用 LLM 分析并生成知识条目。
"""

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_memories():
    """加载所有记忆"""
    drawers_path = Path.home() / ".pangu" / "pangu.db" / "v2_memories" / "drawers.json"
    if not drawers_path.exists():
        print("❌ drawers.json 不存在")
        return []
    
    with open(drawers_path, encoding="utf-8") as f:
        drawers = json.load(f)
    
    print(f"✅ 加载 {len(drawers)} 条记忆")
    return drawers


def load_config():
    """加载 LLM 配置"""
    config_path = Path.home() / ".pangu" / "config.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    # 读取 API Key
    key_path = Path.home() / ".pangu" / ".llm_api_key"
    api_key = ""
    if key_path.exists():
        api_key = key_path.read_text(encoding="utf-8").strip()
    
    return {
        "provider": config.get("llm_provider", "openai"),
        "model": config.get("llm_model", "MiniCPM5-2B"),
        "base_url": config.get("llm_base_url", "https://developer.amd.com.cn/radeon/api/v1"),
        "api_key": api_key,
    }


def call_llm(prompt: str, config: dict) -> str:
    """调用 LLM"""
    import urllib.request
    import urllib.error
    
    url = f"{config['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    data = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "你是一个知识提取专家。从给定的记忆中提取有价值的知识，生成结构化的知识条目。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        return ""


def extract_knowledge_from_memories(memories: list, config: dict) -> list:
    """从记忆中提取知识"""
    # 按来源分组
    by_source = defaultdict(list)
    for m in memories:
        source = m.get("source") or m.get("room") or "unknown"
        by_source[source].append(m)
    
    print(f"\n📊 记忆来源分布:")
    for source, mems in sorted(by_source.items(), key=lambda x: -len(x[1])):
        print(f"  {source}: {len(mems)} 条")
    
    knowledge_entries = []
    
    # 为每个来源生成知识
    for source, mems in by_source.items():
        if len(mems) < 2:
            continue  # 太少的记忆跳过
        
        print(f"\n🔍 分析来源: {source} ({len(mems)} 条记忆)")
        
        # 准备记忆内容
        memory_texts = []
        for m in mems[:20]:  # 最多取 20 条
            content = m.get("content", "")
            tags = m.get("tags", [])
            wing = m.get("wing", "")
            memory_texts.append(f"[{wing}] {content} (标签: {', '.join(tags) if tags else '无'})")
        
        prompt = f"""分析以下来自 "{source}" 的记忆，提取有价值的知识。

记忆列表:
{chr(10).join(f"{i+1}. {text}" for i, text in enumerate(memory_texts))}

请提取 1-3 条最有价值的知识，每条包含:
1. title: 知识标题 (简洁明了)
2. content: 知识内容 (详细描述)
3. category: 类别 (best_practice/solution/guide/insight 之一)
4. tags: 标签列表 (3-5 个)
5. confidence: 置信度 (0.0-1.0)

返回 JSON 格式:
```json
[
  {{
    "title": "...",
    "content": "...",
    "category": "...",
    "tags": ["..."],
    "confidence": 0.8
  }}
]
```"""
        
        response = call_llm(prompt, config)
        if not response:
            continue
        
        # 解析 JSON 响应
        try:
            # 提取 JSON 部分
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                entries = json.loads(json_str)
                
                for entry in entries:
                    entry["source"] = source
                    entry["source_memory_count"] = len(mems)
                    knowledge_entries.append(entry)
                    print(f"  ✅ 提取: {entry.get('title', '未命名')} ({entry.get('category', '未知')})")
            else:
                print(f"  ⚠️ 无法解析 LLM 响应")
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON 解析失败: {e}")
        
        time.sleep(1)  # 避免 API 限流
    
    return knowledge_entries


def save_knowledge(entries: list):
    """保存知识到知识库"""
    import secrets
    from datetime import datetime
    
    knowledge_path = Path.home() / ".pangu" / "knowledge_base.json"
    
    # 读取现有知识
    existing = []
    if knowledge_path.exists():
        try:
            with open(knowledge_path, encoding="utf-8") as f:
                existing = json.load(f)
        except:
            existing = []
    
    saved = 0
    for entry in entries:
        try:
            knowledge_entry = {
                "id": f"kb_{secrets.token_hex(8)}",
                "title": entry["title"],
                "content": entry["content"],
                "category": entry["category"],
                "source_memories": [],
                "tags": entry.get("tags", []),
                "confidence": entry.get("confidence", 0.8),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "usage_count": 0,
                "related_knowledge": [],
            }
            existing.append(knowledge_entry)
            saved += 1
            print(f"  ✅ 保存: {entry['title']}")
        except Exception as e:
            print(f"  ❌ 保存失败: {e}")
    
    # 写入文件
    knowledge_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    knowledge_path.chmod(0o600)
    
    print(f"\n✅ 保存 {saved} 条知识到知识库")
    return saved


def main():
    print("🧠 盘古知识生成器")
    print("=" * 50)
    
    # 加载记忆
    memories = load_memories()
    if not memories:
        return
    
    # 加载配置
    config = load_config()
    if not config["api_key"]:
        print("❌ 未配置 LLM API Key")
        return
    
    print(f"\n🤖 LLM: {config['model']} @ {config['base_url'][:30]}...")
    
    # 提取知识
    knowledge_entries = extract_knowledge_from_memories(memories, config)
    
    if not knowledge_entries:
        print("\n⚠️ 未提取到知识")
        return
    
    # 保存知识
    print(f"\n📝 提取了 {len(knowledge_entries)} 条知识")
    save_knowledge(knowledge_entries)
    
    # 显示统计
    knowledge_path = Path.home() / ".pangu" / "knowledge_base.json"
    if knowledge_path.exists():
        with open(knowledge_path, encoding="utf-8") as f:
            all_knowledge = json.load(f)
        
        categories = {}
        for k in all_knowledge:
            cat = k.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n📊 知识库统计:")
        print(f"  总计: {len(all_knowledge)} 条")
        for cat, count in categories.items():
            print(f"  {cat}: {count} 条")


if __name__ == "__main__":
    main()
