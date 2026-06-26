"""盘古挖掘模块 — 从各种来源提取记忆"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import PanguConfig
from ..core.palace import Drawer


class FileMiner:
    """文件挖掘器 — 从项目文件中提取记忆"""

    EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".swift",
        ".md",
        ".txt",
        ".rst",
        ".yml",
        ".yaml",
        ".toml",
        ".json",
        ".html",
        ".css",
        ".scss",
        ".less",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
    }

    SKIP_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def scan_directory(self, directory: str, wing: str = None) -> list[Drawer]:
        """扫描目录，提取文件内容为记忆片段"""
        directory = Path(directory)
        if not directory.exists():
            return []

        wing = wing or directory.name
        drawers = []

        for file_path in directory.rglob("*"):
            if file_path.is_dir():
                if any(skip in file_path.parts for skip in self.SKIP_DIRS):
                    continue
                continue

            if file_path.suffix not in self.EXTENSIONS:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    continue

                # 按段落分块
                room = self._detect_room(file_path, directory)
                chunks = self._chunk_content(content)

                for i, chunk in enumerate(chunks):
                    drawer = Drawer(
                        id=f"file_{file_path.stem}_{i}_{datetime.now().timestamp():.0f}",
                        content=chunk,
                        wing=wing,
                        room=room,
                        hall="hall_facts",
                        source_file=str(file_path),
                        importance=3.0,
                    )
                    drawers.append(drawer)

            except Exception:
                continue

        return drawers

    def _detect_room(self, file_path: Path, base_dir: Path) -> str:
        """自动检测文件所属 Room"""
        relative = file_path.relative_to(base_dir)
        parts = relative.parts

        if len(parts) > 1:
            return parts[0]  # 用第一级目录名作为 room
        return "root"

    def _chunk_content(self, content: str, max_chunk_size: int = 2000) -> list[str]:
        """将内容分块"""
        paragraphs = content.split("\n\n")
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) > max_chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                if current:
                    current += "\n\n"
                current += para

        if current.strip():
            chunks.append(current.strip())

        return chunks if chunks else [content[:max_chunk_size]]


class ConvoMiner:
    """对话挖掘器 — 从对话记录中提取记忆"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def parse_claude_jsonl(self, file_path: str, wing: str = None) -> list[Drawer]:
        """解析 Claude Code JSONL 格式的对话"""
        file_path = Path(file_path)
        if not file_path.exists():
            return []

        wing = wing or file_path.stem
        drawers = []

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return []

        for i, line in enumerate(lines):
            try:
                data = json.loads(line.strip())
                role = data.get("role", "unknown")
                content = data.get("content", "")

                if isinstance(content, list):
                    content = " ".join(item.get("text", "") for item in content if isinstance(item, dict))

                if content.strip():
                    drawer = Drawer(
                        id=f"conv_{file_path.stem}_{i}_{datetime.now().timestamp():.0f}",
                        content=content.strip(),
                        wing=wing,
                        room=self._detect_room_from_content(content),
                        hall="hall_events",
                        source_file=str(file_path),
                        importance=3.0,
                        metadata={"role": role, "line": i},
                    )
                    drawers.append(drawer)

            except (json.JSONDecodeError, KeyError):
                continue

        return drawers

    def parse_chatgpt_json(self, file_path: str, wing: str = None) -> list[Drawer]:
        """解析 ChatGPT JSON 格式的对话"""
        file_path = Path(file_path)
        if not file_path.exists():
            return []

        wing = wing or file_path.stem
        drawers = []

        try:
            with open(file_path, encoding="utf-8") as f:
                conversations = json.load(f)
        except Exception:
            return []

        if not isinstance(conversations, list):
            conversations = [conversations]

        for conv_idx, conv in enumerate(conversations):
            messages = conv.get("messages", conv.get("conversation", []))
            title = conv.get("title", file_path.stem)

            for msg_idx, msg in enumerate(messages):
                role = msg.get("role", msg.get("author", "unknown"))
                content = msg.get("content", "")

                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            parts.append(item)
                    content = " ".join(parts)

                if content.strip():
                    drawer = Drawer(
                        id=f"chatgpt_{file_path.stem}_{conv_idx}_{msg_idx}",
                        content=content.strip(),
                        wing=wing,
                        room=title[:50],
                        hall="hall_events",
                        source_file=str(file_path),
                        importance=3.0,
                        metadata={"role": role, "title": title},
                    )
                    drawers.append(drawer)

        return drawers

    def _detect_room_from_content(self, content: str) -> str:
        """从内容中检测 Room 名称"""
        # 简单的关键词检测
        keywords = {
            "auth": "auth",
            "认证": "auth",
            "deploy": "deploy",
            "部署": "deploy",
            "bug": "bugfix",
            "fix": "bugfix",
            "修复": "bugfix",
            "api": "api",
            "接口": "api",
            "database": "database",
            "数据库": "database",
            "ui": "ui",
            "界面": "ui",
            "test": "testing",
            "测试": "testing",
            "config": "config",
            "配置": "config",
        }

        content_lower = content.lower()
        for kw, room in keywords.items():
            if kw in content_lower:
                return room

        return "general"


class WikiMiner:
    """Wiki 挖掘器 — 从 Wiki 页面提取结构化记忆"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()

    def extract_from_page(self, page_title: str, page_content: str, wing: str = "default") -> list[Drawer]:
        """从 Wiki 页面内容提取记忆片段"""
        drawers = []

        # 按段落分块
        sections = page_content.split("\n## ")
        for i, section in enumerate(sections):
            if section.strip():
                drawer = Drawer(
                    id=f"wiki_{page_title[:20]}_{i}_{datetime.now().timestamp():.0f}",
                    content=section.strip(),
                    wing=wing,
                    room=page_title[:50],
                    hall="hall_concepts",
                    source_file=f"wiki://{page_title}",
                    importance=4.0,
                    metadata={"page_title": page_title, "section_index": i},
                )
                drawers.append(drawer)

        return drawers


class OpenClawMiner:
    """OpenClaw 会话挖掘器 — 从 OpenClaw 对话记录中提取记忆

    支持：
    - 自动发现所有 agent 的会话
    - 按时间范围筛选（N 分钟内）
    - 按关键词/主题过滤
    - 提取 user + assistant 消息
    - 根据 token 数量估算重要性
    """

    # OpenClaw 默认会话存储路径
    DEFAULT_STORE = os.path.expanduser("~/.openclaw/agents")

    def __init__(self, config: PanguConfig = None, store_path: str = None):
        self.config = config or PanguConfig.load()
        self.store_path = Path(store_path or self.DEFAULT_STORE)

    def discover_sessions(self) -> list[dict]:
        """发现所有 agent 的会话

        返回会话元信息列表，每条包含：
        - agent_id, session_key, session_id
        - updated_at, model, total_tokens
        - jsonl_path: 会话内容文件路径
        """
        sessions = []
        if not self.store_path.exists():
            return sessions

        for agent_dir in self.store_path.iterdir():
            if not agent_dir.is_dir():
                continue
            session_dir = agent_dir / "sessions"
            sessions_json = session_dir / "sessions.json"
            if not sessions_json.exists():
                continue

            try:
                with open(sessions_json) as f:
                    index = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            for session_key, meta in index.items():
                session_id = meta.get("sessionId", "")
                jsonl_file = session_dir / f"{session_id}.jsonl"
                sessions.append(
                    {
                        "agent_id": agent_dir.name,
                        "session_key": session_key,
                        "session_id": session_id,
                        "updated_at": meta.get("updatedAt", 0),
                        "model": meta.get("model", ""),
                        "total_tokens": meta.get("totalTokens", 0),
                        "input_tokens": meta.get("inputTokens", 0),
                        "output_tokens": meta.get("outputTokens", 0),
                        "kind": meta.get("kind", "direct"),
                        "jsonl_path": str(jsonl_file) if jsonl_file.exists() else None,
                    }
                )

        # 按更新时间降序
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions

    def mine_recent(
        self,
        minutes: int = 60,
        agent_id: str = None,
        wing: str = "openclaw",
    ) -> list[Drawer]:
        """挖掘最近 N 分钟内的会话

        Args:
            minutes: 时间窗口（分钟）
            agent_id: 限定 agent（None = 所有）
            wing: 目标宫殿殿堂
        """
        cutoff = datetime.now(timezone.utc).timestamp() - minutes * 60
        all_sessions = self.discover_sessions()
        drawers = []

        for session in all_sessions:
            # 时间筛选
            updated_ts = session["updated_at"] / 1000.0  # ms → s
            if updated_ts < cutoff:
                continue
            # agent 筛选
            if agent_id and session["agent_id"] != agent_id:
                continue

            mined = self.mine_session(session, wing=wing)
            drawers.extend(mined)

        return drawers

    def mine_session(
        self,
        session_info: dict,
        wing: str = "openclaw",
        min_message_length: int = 20,
        filter_keywords: list[str] = None,
    ) -> list[Drawer]:
        """挖掘单个会话的内容

        Args:
            session_info: discover_sessions() 返回的条目
            wing: 目标 wing 名称
            min_message_length: 最短消息长度（字符），过滤过短消息
            filter_keywords: 关键词过滤列表（None = 不过滤）
        """
        jsonl_path = session_info.get("jsonl_path")
        if not jsonl_path:
            return []

        drawers = []
        session_id = session_info["session_id"][:8]
        agent_id = session_info["agent_id"]
        model = session_info.get("model", "")

        try:
            with open(jsonl_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []

        # 计算重要性：token 越多 → 会话越有价值
        total_tokens = session_info.get("total_tokens", 0)
        importance = min(5.0, 2.0 + (total_tokens / 10000.0))

        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "message":
                continue

            msg = entry.get("message", {})
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue

            # 提取文本内容（处理 content blocks 格式）
            content_blocks = msg.get("content", "")
            text = self._extract_text(content_blocks)

            # 过滤过短 / 空消息
            if len(text) < min_message_length:
                continue

            # 关键词过滤
            if filter_keywords:
                if not any(kw.lower() in text.lower() for kw in filter_keywords):
                    continue

            # 检测 room 分类
            room = self._classify_topic(text)

            drawer = Drawer(
                id=f"oc_{agent_id}_{session_id}_{i}_{datetime.now().timestamp():.0f}",
                content=text,
                wing=wing,
                room=room,
                hall="hall_events" if role == "user" else "hall_insights",
                source_file=jsonl_path,
                importance=importance,
                metadata={
                    "role": role,
                    "agent": agent_id,
                    "session": session_info["session_key"],
                    "model": model,
                    "session_tokens": total_tokens,
                },
            )
            drawers.append(drawer)

        return drawers

    def mine_all(
        self,
        agent_id: str = None,
        wing: str = "openclaw",
        **kwargs,
    ) -> list[Drawer]:
        """挖掘所有会话"""
        all_sessions = self.discover_sessions()
        drawers = []
        for session in all_sessions:
            if agent_id and session["agent_id"] != agent_id:
                continue
            mined = self.mine_session(session, wing=wing, **kwargs)
            drawers.extend(mined)
        return drawers

    # ── 内部工具方法 ──

    @staticmethod
    def _extract_text(content) -> str:
        """从 OpenClaw content blocks 中提取纯文本

        支持格式：
        - 纯字符串
        - [{"type": "text", "text": "..."}, ...]
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        # 工具调用：保留工具名和输入概要
                        name = block.get("name", "unknown_tool")
                        inp = block.get("input", {})
                        inp_str = json.dumps(inp, ensure_ascii=False)[:200]
                        parts.append(f"[调用工具: {name}] {inp_str}")
                    elif block.get("type") == "tool_result":
                        parts.append("[工具返回]")
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(p.strip() for p in parts if p.strip())
        return str(content)

    @staticmethod
    def _classify_topic(text: str) -> str:
        """从文本内容中推断话题分类"""
        topic_patterns = [
            (r"(bug|错误|异常|崩溃|crash|error|fix|修复)", "bugfix"),
            (r"(deploy|部署|k8s|docker|上线|发布|CI|CD)", "deploy"),
            (r"(auth|认证|鉴权|权限|RBAC|JWT|OAuth)", "auth"),
            (r"(api|接口|REST|GraphQL|端点|endpoint)", "api"),
            (r"(database|数据库|SQL|migrat|索引|index|表)", "database"),
            (r"(performance|性能|优化|优化|benchmark|profiling)", "performance"),
            (r"(test|测试|unittest|pytest|coverage)", "testing"),
            (r"(config|配置|env|环境变量|setting)", "config"),
            (r"(security|安全|vulnerability|漏洞|penetrat)", "security"),
            (r"(ui|界面|前端|frontend|css|html|组件)", "ui"),
            (r"(memory|记忆|记忆|知识库|knowledge|RAG)", "memory"),
            (r"(code|代码|refactor|重构|review|审查)", "code"),
            (r"(doc|文档|documentation|readme|说明)", "docs"),
        ]
        text_lower = text.lower()
        for pattern, category in topic_patterns:
            if re.search(pattern, text_lower):
                return category
        return "general"
