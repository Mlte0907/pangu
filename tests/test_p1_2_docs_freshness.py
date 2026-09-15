"""P1-2 回归测试：文档新鲜度——版本号/工具名/镜像 tag 必须与代码一致。

灵感来自 Hindsight 的 docs-freshness.test.ts：文档过期就测试失败。

盘古真实案例：镜像 tag 被写成 v0.2.0（实际是 0.2.0），没有任何测试能发现。
"""

import re

import pytest


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── 版本号一致性 ──────────────────────────────────────────────────


def _get_version_from_init() -> str:
    """从 pangu/__init__.py 提取版本号"""
    content = _read_file("pangu/__init__.py")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return m.group(1) if m else ""


def _get_version_from_pyproject() -> str:
    """从 pyproject.toml 提取版本号"""
    content = _read_file("pyproject.toml")
    m = re.search(r"^version\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE)
    return m.group(1) if m else ""


def test_version_consistent_init_pyproject():
    """pangu/__init__.py 和 pyproject.toml 版本号必须一致。"""
    v_init = _get_version_from_init()
    v_proj = _get_version_from_pyproject()
    assert v_init, "__init__.py 中未找到 __version__"
    assert v_proj, "pyproject.toml 中未找到 version"
    assert v_init == v_proj, f"版本不一致: __init__.py={v_init} vs pyproject={v_proj}"


def test_readme_mentions_current_version():
    """README.md 必须提及当前版本号（不接受过期版本）。"""
    version = _get_version_from_init()
    readme = _read_file("README.md")
    # README 应包含当前版本号（带或不带 v 前缀）
    assert version in readme or f"v{version}" in readme, f"README.md 未提及当前版本 v{version}。可能有过期版本号。"


def test_readme_no_outdated_version():
    """README.md 不应包含比当前版本更旧的版本号（作为标题/徽章）。"""
    version = _get_version_from_init()
    readme = _read_file("README.md")
    # 找出所有版本号（vX.Y.Z 格式）
    found_versions = set(re.findall(r"v?(\d+\.\d+\.\d+)", readme))
    for v in found_versions:
        # 允许引用历史版本（如 "v0.1.0 起..."），但不允许作为主版本号
        # 检查是否在标题行（# 或 ** 包裹）
        lines = [l for l in readme.split("\n") if v in l]
        for line in lines:
            if re.match(r"^#+\s", line) or "**" in line[:50]:
                # 如果标题行只有旧版本（没有当前版本），则失败
                if version not in line:
                    pytest.fail(f"README.md 标题行包含过期版本 v{v}，当前版本 v{version}: {line[:80]}")


# ── 镜像 tag 格式 ────────────────────────────────────────────────


def test_docker_image_tag_format():
    """docs/ 中的 ghcr.io 镜像 tag 不应有 v 前缀（ghcr.io 惯例是 0.2.0 而非 v0.2.0）。"""
    import glob

    docs_files = glob.glob("docs/**/*.md", recursive=True)
    for path in docs_files:
        content = _read_file(path)
        # 找 ghcr.io 镜像引用（仅在代码块/行内代码中的，排除描述问题的上下文）
        for m in re.finditer(r"ghcr\.io/[^:]+:(v\d+\.\d+\.\d+)", content):
            tag = m.group(1)
            # 获取所在行
            line_start = content.rfind("\n", 0, m.start()) + 1
            line = content[line_start : content.find("\n", m.end())]
            # 如果行包含 "→" 或 "HTTP" 或 "实际是" 等描述性文字，跳过（这是在描述问题）
            if any(kw in line for kw in ["→", "HTTP", "实际是", "应该是", "正确"]):
                continue
            pytest.fail(f"{path}: ghcr.io 镜像 tag 不应有 v 前缀: {tag}（应为 {tag[1:]}）")


# ── 工具名一致性 ──────────────────────────────────────────────────


def test_doc_tool_names_exist():
    """docs/ 中提到的 pangu_ 工具名（在代码块/表格中）必须真实存在于代码中。"""
    import glob

    # 收集代码中所有工具名
    code_tools = set()
    for path in glob.glob("pangu/server/handlers/*.py"):
        content = _read_file(path)
        code_tools.update(re.findall(r'"(pangu_\w+)"', content))

    # 收集文档中提到的工具名（排除计划文档、报告、历史文档）
    skip_files = {
        "PLAN-v0.3.0.md",
        "P0-0-勘察报告.md",
        "P0-1-IMPLEMENTATION-BLUEPRINT.md",
        "P2-1-INTEGRATION-PLAN.md",
        "P2-1-MODULE-AUDIT.md",
        "P0-0-变更报告.md",
    }
    docs_files = [
        f
        for f in glob.glob("docs/**/*.md", recursive=True)
        if f.split("/")[-1] not in skip_files and "/history/" not in f
    ]

    for path in docs_files:
        content = _read_file(path)
        # 只检查代码块和表格中的工具名（排除自由文本中的误匹配）
        # 提取 ``` 代码块内容
        code_blocks = re.findall(r"```.*?\n(.*?)```", content, re.DOTALL)
        # 提取表格行（| 分隔的）
        table_lines = [l for l in content.split("\n") if l.strip().startswith("|")]

        check_text = "\n".join(code_blocks + table_lines)
        tools_in_doc = set(re.findall(r"pangu_[a-z_]+", check_text))

        for tool in tools_in_doc:
            # 跳过 prometheus 指标名（任何常见指标后缀）
            PROM_SUFFIXES = r"(seconds|total|count|bucket|bytes|ratio|avg|p99|p95|p50|max|min|sum|std|info|created|hit_rate|miss_rate|latency|duration|size|usage|utilization|entries|evictions|gauge|current|pending|active|idle|open|closed|connected|running|stopped|enabled|disabled|configured|available|missing|stale|expired|flushed|warmed|cold|hot|warm|ready|building|blocked|queue)"
            if re.match(rf"pangu_[a-z_]+_({PROM_SUFFIXES})", tool):
                continue
            # 跳过 CLI 子命令
            if tool.startswith("pangu_cli_") or tool.startswith("pangu_serve"):
                continue
            # 跳过目录/文件名
            if re.match(r"pangu_(copy|data|db|dir|home|log|path|tmp|venv|work|backend|server)", tool):
                continue
            # 跳过拼写错误（pangu_pangu_xxx 等）
            if "pangu_pangu" in tool:
                continue
            # 跳过 fixture 名
            if tool.startswith("pangu_cache") and "_" in tool[7:]:
                continue
            # 精确匹配或前缀匹配
            if tool not in code_tools:
                has_prefix = any(t.startswith(tool + "_") or t == tool for t in code_tools)
                if not has_prefix:
                    pytest.fail(f"{path}: 文档提到工具 '{tool}'，但代码中未找到")


# ── 变更日志 ──────────────────────────────────────────────────────


def test_changelog_mentions_current_version():
    """CHANGELOG.md 如果存在，必须包含当前版本条目。"""
    import os

    if not os.path.exists("CHANGELOG.md"):
        pytest.skip("CHANGELOG.md 不存在")
    version = _get_version_from_init()
    changelog = _read_file("CHANGELOG.md")
    assert f"v{version}" in changelog or version in changelog, f"CHANGELOG.md 未包含当前版本 v{version} 的条目"
