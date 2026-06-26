"""盘古 Session Bridge — 跨会话共享上下文

核心能力：
1. 会话摘要：自动为每个会话生成结构化摘要
2. 会话存储：摘要存入 Palace 可被其他会话检索
3. 上下文注入：新会话启动时自动加载相关历史上下文
4. 跨会话链接：发现并链接不同会话间的关联记忆
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.session_bridge")


class SessionBridge:
    """跨会话桥接引擎"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._sessions_file = Path(self.config.palace_path) / "sessions.json"
        self._sessions = self._load_sessions()

    def _load_sessions(self) -> dict:
        if self._sessions_file.exists():
            try:
                with open(self._sessions_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sessions": []}

    def _save_sessions(self):
        try:
            with open(self._sessions_file, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存会话数据失败: {e}")

    def start_session(self, session_id: str, agent: str = "claude", description: str = "") -> dict:
        """记录新会话开始"""
        session = {
            "id": session_id,
            "agent": agent,
            "description": description,
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "tools_called": [],
            "key_events": [],
            "files_modified": [],
            "memories_written": 0,
            "memories_read": 0,
            "summary": "",
        }
        self._sessions["sessions"].append(session)
        self._save_sessions()
        return {"status": "started", "session_id": session_id}

    def end_session(
        self, session_id: str, summary: str = "", key_events: list[str] = None, files_modified: list[str] = None
    ) -> dict:
        """记录会话结束，生成摘要"""
        for s in self._sessions["sessions"]:
            if s["id"] == session_id:
                s["ended_at"] = datetime.now().isoformat()
                s["summary"] = summary
                s["key_events"] = key_events or []
                s["files_modified"] = files_modified or []
                self._save_sessions()

                # 自动存入 Palace
                self._store_session_summary(s)
                return {"status": "ended", "session_id": session_id, "summary": summary[:100]}
        return {"error": f"会话 {session_id} 未找到"}

    def record_event(self, session_id: str, event_type: str, detail: str) -> dict:
        """记录会话中的事件"""
        for s in self._sessions["sessions"]:
            if s["id"] == session_id:
                s["key_events"].append(
                    {
                        "type": event_type,
                        "detail": detail[:200],
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                self._save_sessions()
                return {"status": "recorded"}
        return {"error": f"会话 {session_id} 未找到"}

    def record_tool_call(self, session_id: str, tool_name: str, result_summary: str = "") -> dict:
        """记录工具调用"""
        for s in self._sessions["sessions"]:
            if s["id"] == session_id:
                s["tools_called"].append(
                    {
                        "tool": tool_name,
                        "summary": result_summary[:100],
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                self._save_sessions()
                return {"status": "recorded"}
        return {"error": f"会话 {session_id} 未找到"}

    def get_resume_context(self, agent: str = "claude", limit: int = 3) -> dict:
        """获取上一个会话的恢复上下文"""
        sessions = [s for s in self._sessions["sessions"] if s["agent"] == agent]
        if not sessions:
            return {"context": "无历史会话", "sessions": []}

        # 最近 N 个会话
        recent = sorted(sessions, key=lambda s: s.get("started_at", ""), reverse=True)[:limit]

        context_parts = []
        for s in recent:
            summary = s.get("summary", "无摘要")
            events = s.get("key_events", [])[-3:]
            tools = [t["tool"] for t in s.get("tools_called", [])[-5:]]
            files = s.get("files_modified", [])[-5:]

            parts = [f"会话 {s['id'][:12]} ({s.get('started_at', '')[:10]})"]
            if summary:
                parts.append(f"  摘要: {summary[:150]}")
            if events:
                event_strs = [e["type"] if isinstance(e, dict) else str(e) for e in events]
                parts.append(f"  事件: {', '.join(event_strs[:5])}")
            if tools:
                parts.append(f"  工具: {', '.join(tools)}")
            if files:
                parts.append(f"  文件: {', '.join(f.split('/')[-1] for f in files)}")
            context_parts.append("\n".join(parts))

        return {
            "context": "\n\n".join(context_parts),
            "sessions": [
                {"id": s["id"], "summary": s.get("summary", ""), "started_at": s.get("started_at", "")} for s in recent
            ],
            "total_sessions": len(sessions),
        }

    def get_session_stats(self) -> dict:
        """获取会话统计"""
        sessions = self._sessions.get("sessions", [])
        total_tools = sum(len(s.get("tools_called", [])) for s in sessions)
        total_events = sum(len(s.get("key_events", [])) for s in sessions)
        total_files = sum(len(s.get("files_modified", [])) for s in sessions)

        return {
            "total_sessions": len(sessions),
            "total_tools_called": total_tools,
            "total_events": total_events,
            "total_files_modified": total_files,
            "agents": list(set(s.get("agent", "unknown") for s in sessions)),
        }

    def _store_session_summary(self, session: dict):
        """将会话摘要存入 Palace"""
        try:
            from ..memory.ingestion import remember

            summary = session.get("summary", "")
            if not summary:
                events = session.get("key_events", [])
                tools = [t["tool"] for t in session.get("tools_called", [])]
                summary = f"会话 {session['id'][:12]}: 使用了 {', '.join(tools[:5])} 工具"
                if events:
                    summary += f", 关键事件: {', '.join(e['type'] for e in events[:3])}"

            remember(
                raw_text=summary[:500],
                wing="system",
                room="sessions",
                importance=0.5,
                tags=["session_summary", session.get("agent", "unknown")],
                source="session_bridge",
            )
        except Exception as e:
            logger.debug(f"存储会话摘要失败: {e}")


_bridge: SessionBridge | None = None


def get_session_bridge(config: PanguConfig = None) -> SessionBridge:
    global _bridge
    if _bridge is None:
        _bridge = SessionBridge(config)
    return _bridge
