"""「监听暴露 + MCP 免鉴权」告警的单测。

背景（2026-09-22 实测）：/mcp 默认无凭据也放行。只监听回环时安全；一旦监听
非回环地址，任何能连到该端口的人都能直接读写记忆，且不经过平台令牌审核。
所以启动时必须能喊一声，且不能对本机部署误报。
"""
from pangu.api.server import mcp_auth_exposure_warning


def test_loopback_is_fine():
    """只听回环 = 能连上即身份，不该报警"""
    for host in ("127.0.0.1", "::1", "localhost"):
        assert mcp_auth_exposure_warning(host, False) == "", host


def test_exposed_without_auth_warns():
    for host in ("0.0.0.0", "::", "192.168.1.10"):
        msg = mcp_auth_exposure_warning(host, False)
        assert msg, f"{host} 应当告警"
        assert host in msg, "告警里要写明是哪个地址暴露了"
        assert "mcp_require_auth" in msg, "告警必须给出可执行的修法"


def test_exposed_with_auth_is_quiet():
    """已强制鉴权 ⇒ 不报警（anonymous 会被拦在审核门之外）"""
    assert mcp_auth_exposure_warning("0.0.0.0", True) == ""


def test_unknown_host_does_not_false_alarm():
    """拿不到监听地址（手工启动未设 PANGU_HOST）时不误报"""
    assert mcp_auth_exposure_warning("", False) == ""


def test_ipv6_all_interfaces_warns():
    assert mcp_auth_exposure_warning("::", False)
