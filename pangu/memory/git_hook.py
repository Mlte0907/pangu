"""盘古 Git Hook 集成 — 自动记录 git 操作到记忆

核心能力：
1. commit 记录：自动提取 commit message、author、files 改动
2. push 记录：记录 push 到远程仓库
3. 状态查询：查看最近的 git 操作记录
4. 自动入库：commit 信息自动存入 Palace 记忆
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig

logger = logging.getLogger("pangu.memory.git_hook")


class GitHook:
    """Git Hook 集成"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._state_file = Path(self.config.palace_path) / "git_hook_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"commits": [], "total_commits": 0, "last_commit": None}

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存 git hook 状态失败: {e}")

    def _run_git(self, args: list[str], cwd: str = None) -> str:
        """执行 git 命令"""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
            )
            return result.stdout.strip()
        except Exception as e:
            logger.debug(f"git command failed: {e}")
            return ""

    def record_commit(self, repo_path: str = ".", auto_store: bool = True) -> dict:
        """记录最近一次 git commit"""
        sha = self._run_git(["rev-parse", "HEAD"], cwd=repo_path)
        if not sha:
            return {"error": "无 git 仓库或无 commit"}

        # 检查是否已记录
        if self._state.get("last_commit") == sha:
            return {"status": "already_recorded", "sha": sha[:12]}

        message = self._run_git(["log", "--oneline", "-1", "--format=%s"], cwd=repo_path)
        author = self._run_git(["log", "--oneline", "-1", "--format=%an"], cwd=repo_path)
        date = self._run_git(["log", "--oneline", "-1", "--format=%ai"], cwd=repo_path)
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)

        # 获取改动文件列表
        files = self._run_git(["diff", "--name-only", "HEAD~1", "HEAD"], cwd=repo_path)
        file_list = [f.strip() for f in files.split("\n") if f.strip()] if files else []

        # 获取 diff 统计
        stat = self._run_git(["diff", "--stat", "HEAD~1", "HEAD"], cwd=repo_path)

        commit_info = {
            "sha": sha[:12],
            "message": message,
            "author": author,
            "date": date,
            "branch": branch,
            "files_changed": len(file_list),
            "files": file_list[:20],
            "stat": stat,
        }

        self._state["commits"].append(commit_info)
        self._state["total_commits"] += 1
        self._state["last_commit"] = sha
        if len(self._state["commits"]) > 100:
            self._state["commits"] = self._state["commits"][-100:]
        self._save_state()

        # 自动存入 Palace
        if auto_store:
            self._store_commit(commit_info)

        return commit_info

    def record_push(self, repo_path: str = ".", remote: str = "origin") -> dict:
        """记录 push 操作"""
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
        ahead = self._run_git(["rev-list", "--count", f"{remote}/{branch}..HEAD"], cwd=repo_path)
        commit_count = int(ahead) if ahead.isdigit() else 0

        if commit_count == 0:
            return {"status": "nothing_to_push"}

        last_sha = self._run_git(["rev-parse", "--short", "HEAD"], cwd=repo_path)
        message = self._run_git(["log", "--oneline", f"{remote}/{branch}..HEAD", "--format=%s"], cwd=repo_path)

        push_info = {
            "type": "push",
            "remote": remote,
            "branch": branch,
            "commits": commit_count,
            "sha": last_sha,
            "messages": message.split("\n")[:5],
            "date": datetime.now().isoformat(),
        }

        self._state["commits"].append(push_info)
        self._state["total_commits"] += 1
        self._save_state()

        self._store_commit(push_info)
        return push_info

    def get_recent(self, limit: int = 10) -> list[dict]:
        """获取最近的 git 操作"""
        return self._state.get("commits", [])[-limit:]

    def get_stats(self) -> dict:
        """获取 git 统计"""
        return {
            "total_commits": self._state.get("total_commits", 0),
            "recent_commits": len(self._state.get("commits", [])),
            "last_commit": self._state.get("last_commit"),
        }

    def _store_commit(self, commit_info: dict):
        """将 commit 信息存入 Palace"""
        try:
            from ..memory.ingestion import remember

            content = f"Git {commit_info.get('type', 'commit')}: {commit_info.get('message', '')}"
            if commit_info.get("files"):
                content += f"\n改动文件: {', '.join(commit_info['files'][:5])}"
            if commit_info.get("author"):
                content += f"\n作者: {commit_info['author']}"
            if commit_info.get("sha"):
                content += f"\nSHA: {commit_info['sha']}"

            remember(
                raw_text=content[:500],
                wing="system",
                room="git",
                importance=0.4,
                tags=["git", commit_info.get("type", "commit")],
                source="git_hook",
            )
        except Exception as e:
            logger.debug(f"存储 git commit 失败: {e}")


_hook: GitHook | None = None


def get_git_hook(config: PanguConfig = None) -> GitHook:
    global _hook
    if _hook is None:
        _hook = GitHook(config)
    return _hook
