"""P1-1 回归测试：安装体验（upgrade / uninstall / --server）。"""

import inspect
import os

import pytest

# ── upgrade 命令 ──────────────────────────────────────────────────


def test_upgrade_command_exists():
    """pangu upgrade 子命令必须存在。"""
    from pangu.cli import app

    # typer 的 CommandInfo.name 可能为 None，用 callback.__name__ 检测
    callbacks = []
    for cmd in app.registered_commands:
        cb = getattr(cmd, "callback", None)
        if cb and hasattr(cb, "__name__"):
            callbacks.append(cb.__name__)
    assert "upgrade" in callbacks, f"upgrade 未注册, 现有: {callbacks[-5:]}"


def test_upgrade_has_check_flag():
    """upgrade 必须有 --check 参数。"""
    from pangu.cli import upgrade

    sig = inspect.signature(upgrade)
    assert "check_only" in sig.parameters, "upgrade 缺少 check_only 参数"


def test_upgrade_has_force_flag():
    """upgrade 必须有 --force 参数。"""
    from pangu.cli import upgrade

    sig = inspect.signature(upgrade)
    assert "force" in sig.parameters, "upgrade 缺少 force 参数"


# ── uninstall 命令 ────────────────────────────────────────────────


def test_uninstall_command_exists():
    """pangu uninstall 子命令必须存在。"""
    from pangu.cli import app

    callbacks = []
    for cmd in app.registered_commands:
        cb = getattr(cmd, "callback", None)
        if cb and hasattr(cb, "__name__"):
            callbacks.append(cb.__name__)
    assert "uninstall" in callbacks, f"uninstall 未注册, 现有: {callbacks[-5:]}"


def test_uninstall_has_remove_data_flag():
    """uninstall 必须有 --remove-data 参数。"""
    from pangu.cli import uninstall

    sig = inspect.signature(uninstall)
    assert "remove_data" in sig.parameters, "uninstall 缺少 remove_data 参数"


def test_uninstall_has_yes_flag():
    """uninstall 必须有 -y/--yes 参数。"""
    from pangu.cli import uninstall

    sig = inspect.signature(uninstall)
    assert "yes" in sig.parameters, "uninstall 缺少 yes 参数"


# ── install.sh 参数 ──────────────────────────────────────────────


def test_install_sh_has_uninstall_flag():
    """install.sh 必须支持 --uninstall 参数。"""
    script = open("install.sh").read()
    assert "--uninstall" in script, "install.sh 缺少 --uninstall 参数"


def test_install_sh_has_server_flag():
    """install.sh 必须支持 --server 参数。"""
    script = open("install.sh").read()
    assert "--server" in script, "install.sh 缺少 --server 参数"


def test_install_sh_help_includes_new_flags():
    """install.sh --help 注释必须包含新参数说明。"""
    script = open("install.sh").read()
    # 头部注释块应包含 --uninstall 和 --server
    header = script.split("\n\n")[0]  # 第一段注释
    assert "--uninstall" in header or "uninstall" in header.lower()
    assert "--server" in header or "server" in header.lower()


# ── 版本一致性 ────────────────────────────────────────────────────


def test_version_consistent():
    """__version__ 和 pyproject.toml 版本号必须一致。"""
    from pangu import __version__

    with open("pyproject.toml") as f:
        for line in f:
            if line.strip().startswith("version"):
                pyproject_ver = line.split("=")[1].strip().strip('"')
                assert __version__ == pyproject_ver, (
                    f"版本不一致: __version__={__version__} vs pyproject={pyproject_ver}"
                )
                break
