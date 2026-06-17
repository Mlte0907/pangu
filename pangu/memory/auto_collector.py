"""盘古 — OpenClaw 会话自动采集器

自动从 OpenClaw 会话中提取重要记忆，经过筛选、去重、分类后存入盘古。

流程：
1. 监控会话目录，检测新会话或会话更新
2. 解析 JSONL 会话文件，提取对话内容
3. 重要性过滤（关键词、长度、角色）
4. 去重检查（精确匹配 + 语义相似度）
5. 自动分类（wing/room）
6. 调用 remember() 入库
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer

logger = logging.getLogger("pangu.memory.auto_collector")


class ConversationParser:
    """会话解析器 — 从 JSONL 文件提取结构化对话"""

    def __init__(self):
        self._cache: dict[str, float] = {}  # file_path -> last_mtime

    def parse_session(self, file_path: str) -> list[dict]:
        """解析会话文件，返回结构化消息列表"""
        messages = []
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    msg = self._parse_line(line)
                    if msg:
                        messages.append(msg)
        except Exception as e:
            logger.error(f"Failed to parse session {file_path}: {e}")
        return messages

    def _parse_line(self, line: str) -> Optional[dict]:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
            return self._extract_message(data)
        except json.JSONDecodeError:
            return None

    def _extract_message(self, data: dict) -> Optional[dict]:
        """从 JSONL 行中提取消息"""
        if data.get("type") != "message":
            return None

        msg = data.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 处理列表格式的内容
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "toolCall":
                        # 记录工具调用
                        tool_name = item.get("name", "")
                        tool_args = item.get("arguments", {})
                        if tool_name:
                            text_parts.append(f"[工具调用: {tool_name}]")
            content = " ".join(text_parts)

        if not content or not isinstance(content, str):
            return None

        return {
            "role": role,
            "content": content,
            "timestamp": data.get("timestamp", ""),
        }


class ImportanceFilter:
    """重要性过滤器 — 判断内容是否值得保存"""

    # 高重要性关键词
    HIGH_KEYWORDS = {
        # 决策相关
        "决定", "确认", "批准", "同意", "拒绝", "取消",
        "优先级", "P0", "P1", "P2", "紧急", "重要",
        # 任务相关
        "任务", "完成", "进行中", "待处理", "阻塞", "卡点",
        "交付", "验收", "上线", "发布",
        # 技术相关
        "bug", "修复", "问题", "错误", "失败", "成功",
        "部署", "配置", "架构", "设计", "方案",
        # 规则相关
        "必须", "禁止", "不能", "需要", "要求",
        "铁律", "规矩", "约束", "规则",
    }

    # 低重要性关键词（会降低重要性）
    LOW_KEYWORDS = {
        "测试", "试试", "看看", "随便",
        "hello", "hi", "ok", "好的", "收到",
    }

    # 角色权重
    ROLE_WEIGHTS = {
        "user": 1.0,      # 用户消息
        "assistant": 0.8,  # AI 回复
        "toolResult": 0.3, # 工具结果（通常不重要）
    }

    def calculate_importance(
        self,
        content: str,
        role: str = "user",
        context: dict | None = None,
    ) -> float:
        """计算内容重要性 (0.0-1.0)"""
        if not content or len(content) < 20:
            return 0.0

        score = 0.3  # 基础分

        # 长度加成
        if len(content) > 100:
            score += 0.1
        if len(content) > 300:
            score += 0.1
        if len(content) > 500:
            score += 0.05

        # 关键词加成
        content_lower = content.lower()
        high_count = sum(1 for kw in self.HIGH_KEYWORDS if kw in content_lower)
        score += min(high_count * 0.08, 0.3)

        # 低关键词扣分
        low_count = sum(1 for kw in self.LOW_KEYWORDS if kw in content_lower)
        score -= min(low_count * 0.05, 0.15)

        # 角色权重
        role_weight = self.ROLE_WEIGHTS.get(role, 0.5)
        score *= role_weight

        # 格式特征加分
        if "@@" in content or "<at" in content:
            score += 0.1  # 包含 @ 提及
        if "```" in content:
            score += 0.05  # 包含代码块
        if "http" in content:
            score += 0.05  # 包含链接

        return max(0.0, min(1.0, score))


class CategoryClassifier:
    """分类器 — 自动分配 wing/room"""

    # Wing 映射规则
    WING_RULES = {
        "tech": [
            "代码", "bug", "修复", "部署", "配置", "架构",
            "API", "服务器", "数据库", "向量", "嵌入",
            "python", "javascript", "docker", "git",
        ],
        "product": [
            "需求", "功能", "用户", "体验", "产品",
            "PRD", "优先级", "迭代", "版本", "发布",
        ],
        "project": [
            "任务", "计划", "进度", "里程碑", "交付",
            "项目", "排期", "工时", "阻塞",
        ],
        "team": [
            "会议", "讨论", "决策", "分工", "协作",
            "@", "玄女", "轩辕", "羲和",
        ],
    }

    # Room 映射规则
    ROOM_RULES = {
        "decisions": ["决定", "确认", "批准", "同意", "拒绝"],
        "tasks": ["任务", "完成", "进行中", "待处理", "阻塞"],
        "issues": ["bug", "问题", "错误", "失败", "修复"],
        "discussions": ["讨论", "想法", "建议", "意见"],
        "rules": ["规则", "约束", "必须", "禁止", "铁律"],
    }

    def classify(self, content: str, role: str = "user") -> tuple[str, str]:
        """分类内容，返回 (wing, room)"""
        content_lower = content.lower()

        # 确定 wing
        wing_scores = {}
        for wing, keywords in self.WING_RULES.items():
            score = sum(1 for kw in keywords if kw.lower() in content_lower)
            wing_scores[wing] = score

        wing = max(wing_scores, key=wing_scores.get) if any(wing_scores.values()) else "default"

        # 确定 room
        room_scores = {}
        for room, keywords in self.ROOM_RULES.items():
            score = sum(1 for kw in keywords if kw.lower() in content_lower)
            room_scores[room] = score

        room = max(room_scores, key=room_scores.get) if any(room_scores.values()) else "general"

        return wing, room


class AutoCollector:
    """自动采集器 — 从 OpenClaw 会话中采集记忆"""

    def __init__(self, config: PanguConfig | None = None):
        self.config = config or PanguConfig.load()
        self.parser = ConversationParser()
        self.filter = ImportanceFilter()
        self.classifier = CategoryClassifier()

        # 已处理的文件记录
        self._processed_file = Path(self.config.palace_path) / "auto_collected.json"
        self._processed: dict[str, float] = self._load_processed()

        # OpenClaw 会话目录
        self._session_dirs = [
            Path.home() / ".openclaw" / "agents" / "main" / "sessions",
            Path.home() / ".openclaw" / "agents" / "xuanyuan" / "sessions",
            Path.home() / ".openclaw" / "agents" / "xuannv" / "sessions",
        ]

    def _load_processed(self) -> dict[str, float]:
        """加载已处理记录"""
        if self._processed_file.exists():
            try:
                with open(self._processed_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_processed(self):
        """保存已处理记录"""
        try:
            with open(self._processed_file, "w", encoding="utf-8") as f:
                json.dump(self._processed, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save processed record: {e}")

    def scan_sessions(self) -> list[dict]:
        """扫描会话目录，返回待处理的会话文件"""
        sessions = []
        for session_dir in self._session_dirs:
            if not session_dir.exists():
                continue

            for file_path in session_dir.glob("*.jsonl"):
                # 跳过 trajectory 文件
                if "trajectory" in file_path.name:
                    continue

                # 检查是否已处理
                mtime = file_path.stat().st_mtime
                last_processed = self._processed.get(str(file_path), 0)

                if mtime > last_processed:
                    sessions.append({
                        "path": str(file_path),
                        "agent": session_dir.parent.name,
                        "mtime": mtime,
                        "last_processed": last_processed,
                    })

        return sessions

    def collect_from_session(
        self,
        session_path: str,
        agent: str = "main",
        max_messages: int = 50,
        min_importance: float = 0.4,
    ) -> list[dict]:
        """从单个会话文件采集记忆"""
        from pangu.memory.ingestion import remember

        results = []
        messages = self.parser.parse_session(session_path)

        # 加载现有记忆用于去重
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        existing_drawers = []
        if drawers_file.exists():
            try:
                with open(drawers_file, encoding="utf-8") as f:
                    existing_drawers = [Drawer.from_dict(d) for d in json.load(f)]
            except Exception:
                pass

        # 只处理最后 N 条消息
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages

        for msg in recent_messages:
            content = msg["content"]
            role = msg["role"]

            # 计算重要性
            importance = self.filter.calculate_importance(content, role)
            if importance < min_importance:
                continue

            # 分类
            wing, room = self.classifier.classify(content, role)

            # 提取标签
            tags = ["auto_collected", agent]
            if role == "user":
                tags.append("user_input")
            elif role == "assistant":
                tags.append("ai_response")

            # 去重检查（blake2b 哈希）
            from pangu.core.hashing import hex_digest
            content_hash = hex_digest(content)
            if any(d.metadata.get("content_hash") == content_hash for d in existing_drawers):
                continue

            # 调用 remember 入库
            try:
                item_id, drawer = remember(
                    raw_text=content[:1000],  # 截断长文本
                    wing=wing,
                    room=room,
                    importance=importance,
                    tags=tags,
                    source=f"auto_collect:{agent}",
                    existing_drawers=existing_drawers,
                )
                drawer.metadata["content_hash"] = content_hash
                drawer.metadata["collected_at"] = datetime.now().isoformat()
                existing_drawers.append(drawer)

                results.append({
                    "id": item_id,
                    "wing": wing,
                    "room": room,
                    "importance": importance,
                    "content_preview": content[:100],
                })
                logger.info(f"Collected: {item_id[:8]} from {agent} (importance={importance:.2f})")
            except Exception as e:
                logger.error(f"Failed to collect memory: {e}")

        # 保存更新后的记忆
        if results:
            try:
                with open(drawers_file, "w", encoding="utf-8") as f:
                    json.dump([d.to_dict() for d in existing_drawers], f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save drawers: {e}")

        # 更新已处理记录
        self._processed[session_path] = time.time()
        self._save_processed()

        return results

    def collect_all(self, max_messages_per_session: int = 30) -> dict:
        """扫描所有会话并采集"""
        stats = {
            "sessions_scanned": 0,
            "memories_collected": 0,
            "by_agent": {},
        }

        sessions = self.scan_sessions()
        for session in sessions:
            stats["sessions_scanned"] += 1
            agent = session["agent"]

            results = self.collect_from_session(
                session["path"],
                agent=agent,
                max_messages=max_messages_per_session,
            )

            count = len(results)
            stats["memories_collected"] += count
            stats["by_agent"][agent] = stats["by_agent"].get(agent, 0) + count

        return stats

    def get_stats(self) -> dict:
        """获取采集统计"""
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        total_memories = 0
        auto_collected = 0

        if drawers_file.exists():
            try:
                with open(drawers_file, encoding="utf-8") as f:
                    drawers = json.load(f)
                total_memories = len(drawers)
                auto_collected = sum(
                    1 for d in drawers
                    if d.get("tags") and "auto_collected" in d["tags"]
                )
            except Exception:
                pass

        return {
            "total_memories": total_memories,
            "auto_collected": auto_collected,
            "processed_files": len(self._processed),
            "session_dirs": [str(d) for d in self._session_dirs if d.exists()],
        }


def run_collection():
    """运行一次采集"""
    collector = AutoCollector()
    stats = collector.collect_all()
    print(f"采集完成: 扫描 {stats['sessions_scanned']} 个会话, "
          f"采集 {stats['memories_collected']} 条记忆")
    if stats["by_agent"]:
        for agent, count in stats["by_agent"].items():
            print(f"  - {agent}: {count} 条")


if __name__ == "__main__":
    run_collection()
