#!/usr/bin/env python3
"""盘古记忆自动提取脚本
从OpenClaw会话中提取重要记忆并存入盘古系统
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加pangu到路径
sys.path.insert(0, "/home/xiaoxin/pangu")

from pangu.core.config import PanguConfig
from pangu.core.palace import Palace, Drawer
from pangu.memory.ingestion import remember


def extract_from_session(session_file: str, wing: str = "sessions") -> list[dict]:
    """从会话文件中提取重要记忆"""
    memories = []
    
    try:
        with open(session_file, encoding="utf-8") as f:
            content = f.read()
        
        # 解析JSONL格式
        for line in content.strip().split("\n"):
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
                    
                    if text and len(text) > 50:  # 只提取有意义的内容
                        # 检测重要性
                        importance = detect_importance(text)
                        if importance > 0.3:
                            memories.append({
                                "content": text[:500],  # 截断长文本
                                "role": role,
                                "importance": importance,
                                "timestamp": data.get("timestamp", ""),
                            })
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"解析会话文件失败: {e}")
    
    return memories


def detect_importance(text: str) -> float:
    """检测内容的重要性"""
    importance = 0.3  # 基础重要性
    
    # 关键词提升
    high_importance_keywords = [
        "决策", "决定", "确认", "重要", "关键", "必须", "需要",
        "bug", "修复", "问题", "错误", "失败", "成功",
        "部署", "发布", "上线", "配置", "设置",
        "架构", "设计", "方案", "计划", "任务",
    ]
    
    for kw in high_importance_keywords:
        if kw in text:
            importance += 0.1
    
    # 长度加成
    if len(text) > 200:
        importance += 0.1
    if len(text) > 500:
        importance += 0.1
    
    return min(importance, 1.0)


def load_drawers(palace_path: str) -> list[Drawer]:
    """从drawers.json加载drawers"""
    drawers_file = Path(palace_path) / "drawers.json"
    if not drawers_file.exists():
        return []
    
    with open(drawers_file, encoding="utf-8") as f:
        data = json.load(f)
    
    return [Drawer.from_dict(d) for d in data]


def main():
    """主函数"""
    config = PanguConfig.load()
    palace = Palace(config.palace_path)
    
    # 加载现有drawers
    existing_drawers = load_drawers(config.palace_path)
    print(f"加载了 {len(existing_drawers)} 条现有记忆")
    
    # 扫描OpenClaw会话目录
    session_dirs = [
        "/home/xiaoxin/.openclaw/agents/main/sessions",
        "/home/xiaoxin/.openclaw/agents/xuanyuan/sessions",
    ]
    
    total_extracted = 0
    
    for session_dir in session_dirs:
        if not os.path.exists(session_dir):
            continue
        
        print(f"扫描: {session_dir}")
        
        for file_path in Path(session_dir).glob("*.jsonl"):
            # 跳过trajectory文件
            if "trajectory" in file_path.name:
                continue
            
            print(f"  处理: {file_path.name}")
            memories = extract_from_session(str(file_path))
            
            for mem in memories:
                try:
                    # 根据会话目录确定wing
                    if "xuanyuan" in session_dir:
                        wing = "xuanyuan"
                    else:
                        wing = "main"
                    
                    item_id, drawer = remember(
                        raw_text=mem["content"],
                        wing=wing,
                        room="auto_extracted",
                        importance=mem["importance"],
                        tags=["auto_extracted", mem["role"]],
                        source="session_extract",
                        existing_drawers=existing_drawers,
                    )
                    existing_drawers.append(drawer)
                    total_extracted += 1
                    print(f"    提取: {item_id[:8]} - {mem['content'][:50]}...")
                except Exception as e:
                    print(f"    提取失败: {e}")
    
    print(f"\n完成！共提取 {total_extracted} 条记忆")


if __name__ == "__main__":
    main()
