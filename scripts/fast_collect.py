#!/usr/bin/env python3
"""盘古自动采集脚本 — 简化版（跳过嵌入）"""
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "/home/xiaoxin/pangu")

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.auto_collector import AutoCollector, ImportanceFilter, CategoryClassifier


def collect_without_embedding():
    """采集记忆但跳过嵌入（加速处理）"""
    config = PanguConfig.load()
    collector = AutoCollector()
    
    # 加载现有记忆
    drawers_file = Path(config.palace_path) / "drawers.json"
    if drawers_file.exists():
        with open(drawers_file, encoding="utf-8") as f:
            existing = [Drawer.from_dict(d) for d in json.load(f)]
    else:
        existing = []
    
    print(f"现有记忆: {len(existing)} 条")
    
    # 扫描会话
    sessions = collector.scan_sessions()
    print(f"待处理会话: {len(sessions)} 个")
    
    total_new = 0
    
    # 只处理前5个会话
    for session in sessions[:5]:
        agent = session["agent"]
        file_path = session["path"]
        
        print(f"\n处理: {agent} - {Path(file_path).name}")
        
        # 解析会话
        messages = collector.parser.parse_session(file_path)
        
        # 只处理最后10条消息
        recent = messages[-10:] if len(messages) > 10 else messages
        
        for msg in recent:
            content = msg["content"]
            role = msg["role"]
            
            # 计算重要性
            importance = collector.filter.calculate_importance(content, role)
            if importance < 0.3:
                continue
            
            # 去重检查
            content_hash = hashlib.md5(content.encode()).hexdigest()
            if any(d.metadata.get("content_hash") == content_hash for d in existing):
                continue
            
            # 分类
            wing, room = collector.classifier.classify(content, role)
            
            # 创建记忆（跳过嵌入）
            item_id = hashlib.sha256(content.encode()).hexdigest()[:16]
            now = datetime.now().isoformat()
            
            drawer = Drawer(
                id=item_id,
                content=content[:500],
                wing=wing,
                room=room,
                importance=importance * 5.0,
                tags=["auto_collected", agent, role],
                created_at=now,
                metadata={
                    "source": f"auto_collect:{agent}",
                    "content_hash": content_hash,
                    "collected_at": now,
                    "embedding_skipped": True,
                },
            )
            
            existing.append(drawer)
            total_new += 1
            print(f"  + {item_id[:8]}: {content[:50]}...")
    
    # 保存
    if total_new > 0:
        with open(drawers_file, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in existing], f, ensure_ascii=False, indent=2)
        print(f"\n保存成功，新增 {total_new} 条记忆")
    
    # 更新已处理记录
    collector._save_processed()
    
    print(f"\n=== 采集完成 ===")
    print(f"总记忆数: {len(existing)}")
    print(f"新增: {total_new}")


if __name__ == "__main__":
    collect_without_embedding()
