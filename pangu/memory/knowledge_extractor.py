"""盘古知识提取引擎 — 从会话中自动提取结构化知识

核心能力：
1. 模式识别：从对话中识别决策、教训、配置、流程
2. 去噪过滤：跳过闲聊、测试、重复内容
3. 结构化存储：提取的知识带类型、标签、关联
4. 增量提取：只处理新会话，避免重复

使用方式：
    extractor = KnowledgeExtractor()
    result = extractor.extract_from_sessions()
    # 或提取单个会话
    result = extractor.extract_from_file(session_path)
"""

import ast
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("pangu.memory.knowledge_extractor")

# 知识类型
KNOWLEDGE_TYPES = {
    "decision": "决策 — 用户想要做或已决定做的事情",
    "learning": "教训 — 从错误或经验中学到的",
    "config": "配置 — 系统设置、参数、环境",
    "process": "流程 — 操作步骤、工作流",
    "pattern": "模式 — 反复出现的行为或问题",
    "fact": "事实 — 确认的信息或状态",
    "insight": "洞察 — 分析得出的深层理解",
}

# 噪声模式（跳过这些内容）
NOISE_PATTERNS = [
    r"^\[message_id:",
    r"^\[System:",
    r"^\[cron:",
    r"^heartbeat",
    r"^\[OpenClaw",
    r"^-{3,}",
    r"^={3,}",
    r"^```",
    r"^\d+\.\s",  # 纯数字列表
    r"^搜索.*中",  # 搜索动作描述
    r"^\[工具调用",  # 工具调用日志
    r"^Tool result",  # 工具结果
    r"^读取文件",  # 文件操作
    r"^执行命令",  # 命令执行
    r"^写入文件",  # 文件写入
    r"^(?:像|如同|仿佛|like)",  # 比喻/诗意
    r"^(?:灯|夜空|果实|幽灵)",  # 文学内容
]

# 知识提取模式
KNOWLEDGE_PATTERNS = {
    "decision": [
        r"(?:决定|确认|选择|采用|切换到|改为|使用)",
        r"(?:decided|confirmed|chose|switched to|use)",
        r"(?:取消|停止|禁用|删除)",
        r"(?:我想|我要|希望|想要|打算|计划|准备)",
        r"(?:想把|要把|改成|换成|变成)",
        r"(?:加一个|加个|新增|添加|做一个|做个)",
        r"(?:删掉|去掉|移除|关闭)",
        r"(?:优化|改进|提升|增强|完善)",
        r"(?:i want to|i'd like to|plan to|going to)",
        r"(?:把.*(?:改|优|加|删|换))",
    ],
    "learning": [
        r"(?:发现|原来|原因是|根因|教训|注意|小心|避免)",
        r"(?:found|turns out|root cause|lesson|careful|avoid)",
        r"(?:修复|解决|fix|resolved|bug)",
    ],
    "config": [
        r"(?:配置|设置|环境变量|env|api.?key|端口|port)",
        r"(?:config|setting|environment|baseUrl|endpoint)",
        r"(?:systemd|service|timer|cron)",
    ],
    "process": [
        r"(?:步骤|流程|操作|执行|运行|重启|部署)",
        r"(?:step|process|execute|run|restart|deploy)",
        r"(?:先.*然后|先.*再|第一步|第二步)",
    ],
    "pattern": [
        r"(?:总是|每次|经常|反复|习惯)",
        r"(?:always|every time|often|repeatedly)",
        r"(?:之前.*也是|上次.*也|历史.*相同)",
    ],
    "fact": [
        r"(?:当前|现在|版本|状态|运行中|已安装)",
        r"(?:current|version|status|running|installed)",
        r"(?:端口|pid|路径|文件)",
    ],
    "insight": [
        r"(?:本质|关键|核心|根本|深层|逻辑)",
        r"(?:essentially|key|core|fundamental|underlying)",
        r"(?:因为.*所以|原因.*是|问题.*在于)",
    ],
}


@dataclass
class ExtractedKnowledge:
    """提取的知识条目"""

    content: str
    knowledge_type: str
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_session: str = ""
    source_role: str = ""
    context: str = ""  # 上下文（前后消息摘要）
    related_to: list[str] = field(default_factory=list)  # 关联的其他知识ID


class KnowledgeExtractor:
    """知识提取引擎"""

    def __init__(self, config=None):
        from pangu.core.config import PanguConfig

        self.config = config or PanguConfig.load()
        self._processed_file = Path(self.config.palace_path) / "extracted_sessions.json"
        self._processed: set[str] = self._load_processed()

    def _load_processed(self) -> set[str]:
        """加载已处理的会话列表"""
        if self._processed_file.exists():
            try:
                with open(self._processed_file, encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_processed(self):
        """保存已处理的会话列表"""
        try:
            with open(self._processed_file, "w", encoding="utf-8") as f:
                json.dump(list(self._processed), f)
        except Exception as e:
            logger.error(f"Failed to save processed sessions: {e}")

    def _is_noise(self, content: str) -> bool:
        """判断是否为噪声内容"""
        content = content.strip()
        if len(content) < 10:
            return True
        for pattern in NOISE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True

        # 诗意/文学内容过滤
        poetic_markers = [
            "像",
            "如同",
            "仿佛",
            "like",
            "the ",
            "and ",
            "黄昏",
            "夜空",
            "灯光",
            "桥",
            "散落",
            "骨头",
            "幽灵",
            "果子",
            "星座",
            "石子",
            "日记本",
            "I ",
            "We ",
            "The ",
            "And ",
        ]
        poetic_count = sum(1 for m in poetic_markers if m in content)
        if poetic_count >= 2:
            return True

        # 时间戳条目
        if re.search(r"Current time:.*\d{4}", content):
            return True
        if re.search(r"Reference UTC:", content):
            return True

        # 纯指令（无知识价值）
        if re.search(r"^Write a dream diary", content):
            return True
        if re.search(r"^-\s*Assistant:", content) and len(content) < 60:
            return True

        return False

    def _detect_knowledge_type(self, content: str) -> str:
        """检测知识类型"""
        scores = {k: 0 for k in KNOWLEDGE_PATTERNS}

        for ktype, patterns in KNOWLEDGE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    scores[ktype] += 1

        if max(scores.values()) == 0:
            return "fact"  # 默认为事实

        return max(scores, key=scores.get)

    def _extract_tags(self, content: str, knowledge_type: str) -> list[str]:
        """提取标签"""
        tags = [knowledge_type]

        # 技术标签
        tech_keywords = {
            "python": "python",
            "docker": "docker",
            "systemd": "systemd",
            "nginx": "nginx",
            "redis": "redis",
            "postgres": "postgres",
            "openclaw": "openclaw",  # 保留为词典数据，非适配代码
            "fuxi": "fuxi",
            "pangu": "pangu",
            "feishu": "feishu",
            "lark": "lark",
            "mcp": "mcp",
            "api": "api",
            "cli": "cli",
            "git": "git",
        }

        content_lower = content.lower()
        for keyword, tag in tech_keywords.items():
            if keyword in content_lower:
                tags.append(tag)

        return list(set(tags))

    def _calculate_confidence(self, content: str, role: str) -> float:
        """计算置信度"""
        confidence = 0.5  # 基础分适中

        # 用户消息通常更可靠
        if role == "user":
            confidence += 0.1

        # 包含具体信息的更可靠
        if re.search(r"\d+", content):  # 包含数字
            confidence += 0.05
        if re.search(r"[A-Z][a-z]+", content):  # 包含英文单词（模型名等）
            confidence += 0.1
        if len(content) > 50:  # 中等长度
            confidence += 0.05
        if len(content) > 100:  # 较长内容
            confidence += 0.1

        # 包含技术关键词加分
        tech_words = [
            "config",
            "setting",
            "fix",
            "bug",
            "error",
            "deploy",
            "配置",
            "修复",
            "部署",
            "错误",
            "问题",
            "解决",
            "决定",
            "确认",
            "选择",
            "采用",
            "切换",
            "建议",
            "deepseek",
            "glm",
            "model",
            "模型",
        ]
        if any(w in content.lower() for w in tech_words):
            confidence += 0.1

        # 包含具体建议/决策的加分
        if re.search(r"(?:建议|推荐|应该|需要|必须)", content):
            confidence += 0.1

        # 包含不确定性的降低置信度
        if re.search(r"(?:可能|也许|大概|possibly|maybe|似乎|好像)", content):
            confidence -= 0.15

        # 纯指令/操作描述降低置信度
        if re.search(r"^(?:请|帮我|执行|运行|查看)", content):
            confidence -= 0.1

        # 诗意/文学内容大幅降低置信度
        poetic_words = ["像", "仿佛", "黄昏", "夜空", "桥", "散落", "骨头", "幽灵"]
        if sum(1 for w in poetic_words if w in content) >= 2:
            confidence -= 0.3

        # 纯时间/日期信息
        if re.search(r"(?:Current time|Reference UTC|July|June|August)", content):
            confidence -= 0.4

        return min(max(confidence, 0.1), 1.0)

    def _parse_session_messages(self, file_path: str) -> list[dict]:
        """解析会话文件中的消息"""
        messages = []

        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") != "message":
                        continue

                    msg_str = entry.get("message", "")
                    ts = entry.get("timestamp", "")

                    try:
                        msg = ast.literal_eval(msg_str) if isinstance(msg_str, str) else msg_str
                    except (ValueError, SyntaxError):
                        continue

                    role = msg.get("role", "")
                    content = msg.get("content", "")

                    # 处理 content 列表格式
                    if isinstance(content, list):
                        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        content = " ".join(texts)

                    if isinstance(content, str) and len(content) > 5:
                        messages.append(
                            {
                                "role": role,
                                "content": content,
                                "timestamp": ts,
                            }
                        )
        except Exception as e:
            logger.error(f"Failed to parse session {file_path}: {e}")

        return messages

    def _extract_from_exchange(self, user_msg: str, assistant_msg: str, session_id: str) -> list[ExtractedKnowledge]:
        """从一轮对话中提取知识"""
        extracted = []

        # 合并内容分析
        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"

        # 检查是否包含有价值的知识
        knowledge_type = self._detect_knowledge_type(combined)
        confidence = self._calculate_confidence(combined, "user")

        # 提取关键句子
        sentences = re.split(r"[。！？\n]", user_msg)
        for sentence in sentences:
            sentence = sentence.strip()
            if self._is_noise(sentence):
                continue
            if len(sentence) < 10:  # 至少10个字符
                continue

            ktype = self._detect_knowledge_type(sentence)
            tags = self._extract_tags(sentence, ktype)
            conf = self._calculate_confidence(sentence, "user")

            if conf >= 0.4:  # 置信度阈值
                extracted.append(
                    ExtractedKnowledge(
                        content=sentence[:500],
                        knowledge_type=ktype,
                        tags=tags,
                        confidence=conf,
                        source_session=session_id,
                        source_role="user",
                    )
                )

        # 从助手回复中提取
        if assistant_msg:
            # 助手回复中的关键信息
            key_patterns = [
                r"(?:总结|结论|结果|状态)[:：]\s*(.+)",
                r"(?:已|完成|修复|解决)[:：]\s*(.+)",
                r"(?:发现|原因)[:：]\s*(.+)",
            ]
            for pattern in key_patterns:
                match = re.search(pattern, assistant_msg)
                if match:
                    content = match.group(1).strip()
                    if len(content) > 10:
                        ktype = self._detect_knowledge_type(content)
                        tags = self._extract_tags(content, ktype)
                        extracted.append(
                            ExtractedKnowledge(
                                content=content[:500],
                                knowledge_type=ktype,
                                tags=tags,
                                confidence=0.6,
                                source_session=session_id,
                                source_role="assistant",
                            )
                        )

        return extracted

    def extract_from_file(self, file_path: str) -> list[ExtractedKnowledge]:
        """从单个会话文件提取知识"""
        session_id = Path(file_path).stem
        messages = self._parse_session_messages(file_path)

        extracted = []
        i = 0
        while i < len(messages):
            msg = messages[i]

            # 找用户消息
            if msg["role"] == "user":
                user_content = msg["content"]

                # 找对应的助手回复
                assistant_content = ""
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    assistant_content = messages[i + 1]["content"]
                    i += 2
                else:
                    i += 1

                # 提取知识
                knowledge = self._extract_from_exchange(user_content, assistant_content, session_id)
                extracted.extend(knowledge)
            else:
                i += 1

        return extracted

    def extract_from_sessions(self, max_sessions: int = 10) -> dict:
        """从所有会话中提取知识"""
        from pangu.core.palace import Drawer

        # 已移除 openclaw 路径探测
        if not sessions_dir.exists():
            return {"error": "Sessions directory not found"}

        # 找到所有会话文件
        session_files = list(sessions_dir.glob("*.jsonl"))
        session_files = [f for f in session_files if "trajectory" not in f.name]

        # 过滤已处理的
        new_sessions = []
        for f in session_files:
            if f.stem not in self._processed:
                new_sessions.append(f)

        # 按修改时间排序，取最新的
        new_sessions.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        new_sessions = new_sessions[:max_sessions]

        if not new_sessions:
            return {"status": "no_new_sessions", "processed": len(self._processed)}

        # 加载现有记忆
        drawers_file = Path(self.config.palace_path) / "drawers.json"
        if drawers_file.exists():
            with open(drawers_file, encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = []

        # 提取知识
        all_extracted = []
        for session_file in new_sessions:
            logger.info(f"Extracting from: {session_file.name}")
            extracted = self.extract_from_file(str(session_file))
            all_extracted.extend(extracted)
            self._processed.add(session_file.stem)

        # 去重并转换为记忆
        seen_hashes = set()
        new_memories = []

        for k in all_extracted:
            content_hash = hashlib.sha256(k.content.encode()).hexdigest()

            # 去重
            if content_hash in seen_hashes:
                continue
            if any(d.get("metadata", {}).get("content_hash") == content_hash for d in existing):
                continue

            seen_hashes.add(content_hash)
            now = datetime.now().isoformat()

            memory = {
                "id": f"knowledge_{content_hash[:12]}",
                "content": k.content,
                "wing": "tech" if "tech" in k.tags else "default",
                "room": k.knowledge_type,
                "importance": k.confidence * 5.0,
                "tags": k.tags + ["auto_extracted"],
                "created_at": now,
                "metadata": {
                    "source": f"knowledge_extract:{k.source_session}",
                    "content_hash": content_hash,
                    "knowledge_type": k.knowledge_type,
                    "confidence": k.confidence,
                    "source_role": k.source_role,
                    "extracted_at": now,
                },
            }
            new_memories.append(memory)

        # 保存
        if new_memories:
            existing.extend(new_memories)
            with open(drawers_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        self._save_processed()

        return {
            "status": "success",
            "sessions_processed": len(new_sessions),
            "knowledge_extracted": len(all_extracted),
            "new_memories": len(new_memories),
            "total_memories": len(existing),
        }


def main():
    """命令行入口"""
    logging.basicConfig(level=logging.INFO)

    extractor = KnowledgeExtractor()
    result = extractor.extract_from_sessions()

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
