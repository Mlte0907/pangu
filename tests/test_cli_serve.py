"""`pangu serve` 的命令行语义测试

为什么单独建文件：`serve` 是安装流程里用户**唯一**要敲的服务启动命令，
但此前没有任何测试覆盖它。v0.1.3 给它加了 `--api`（启动带 `/mcp` 的 API
服务），而端口选择逻辑有一个**隐蔽的坑**：

    早期实现把 `--port` 的默认值写成 8866，再在 `--api` 分支里判断
    `if port == 8866: port = 19529`。这**无法区分**"用户没传 --port"与
    "用户显式传了 --port 8866"——后一种情况下用户的明确要求被静默改写。
    这正是本项目最该消除的那类行为：不报错、照常运行、但做的不是你要的事。

修法：默认值改为 `None` 作为可区分哨兵
（未传时按模式取默认，传了就一定尊重）。
下面的测试把这个语义钉死。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pangu.cli import app

runner = CliRunner()


def _run_serve(argv: list[str]) -> dict:
    """跑 `pangu serve <argv>`，拦下 uvicorn.run，返回它收到的参数

    不真的起服务器：我们要测的是**参数解析与端口选择**，
    真起服务会让测试变慢且依赖端口可用性。
    """
    recorded: dict = {}

    def fake_run(target, **kwargs):
        recorded["target"] = target
        recorded.update(kwargs)

    with patch("uvicorn.run", side_effect=fake_run):
        result = runner.invoke(app, ["serve", *argv], catch_exceptions=False)

    assert result.exit_code == 0, f"serve 退出码非 0：{result.output}"
    return recorded


class TestServeApiFlag:
    """`--api` 必须启动 api.server（含 /mcp），而不是 web_server"""

    def test_api_flag_targets_api_server(self):
        r = _run_serve(["--api"])
        assert "api.server" in r["target"], f"--api 应启动 api.server，实际 {r['target']}"

    def test_default_targets_web_server(self):
        """不带 --api 时仍启动 Web UI（向后兼容，不能改默认行为）"""
        r = _run_serve([])
        assert "web_server" in r["target"], f"默认应启动 web_server，实际 {r['target']}"

    def test_api_uses_factory(self):
        """api.server 是无参工厂函数，必须用 factory=True 构造"""
        r = _run_serve(["--api"])
        assert r["factory"] is True


class TestServePortSelection:
    """端口选择：显式传入的必须被尊重，未传入才用模式默认值

    这是本文件存在的核心理由——见模块 docstring 里描述的静默改写缺陷。
    """

    def test_api_default_port_is_19529(self):
        """--api 不传端口 → 19529（API 约定端口，避免与 Web UI 的 8866 混淆）"""
        assert _run_serve(["--api"])["port"] == 19529

    def test_web_default_port_is_8866(self):
        assert _run_serve([])["port"] == 8866

    def test_explicit_port_wins_for_api(self):
        """★ 回归测试：显式 --port 8866 配 --api 时**必须**保持 8866

        旧实现会把它静默改成 19529。用户要的就是 8866，改成别的端口
        会让他的反向代理/防火墙规则全部失效，而且没有任何提示。
        """
        r = _run_serve(["--api", "--port", "8866"])
        assert r["port"] == 8866, f"显式 --port 8866 被改成了 {r['port']}"

    def test_explicit_port_wins_for_web(self):
        assert _run_serve(["--port", "9000"])["port"] == 9000

    def test_explicit_arbitrary_port_for_api(self):
        assert _run_serve(["--api", "--port", "12345"])["port"] == 12345

    def test_api_does_not_step_on_web_port_by_default(self):
        """两个模式的默认端口必须不同，否则同机部署会互抢端口"""
        assert _run_serve(["--api"])["port"] != _run_serve([])["port"]


class TestServeHostBinding:
    def test_explicit_host_is_passed(self):
        assert _run_serve(["--api", "--host", "127.0.0.1"])["host"] == "127.0.0.1"

    def test_default_host_is_all_interfaces(self):
        """默认 0.0.0.0（容器/远程部署需要）"""
        assert _run_serve(["--api"])["host"] == "0.0.0.0"

    def test_reload_is_forwarded(self):
        """--reload 应传下去（开发用）；默认关闭"""
        assert _run_serve(["--api"])["reload"] is False
        assert _run_serve(["--api", "--reload"])["reload"] is True


class TestServeHelp:
    """帮助文本要能澄清"两个服务"这个最大混淆点"""

    @pytest.mark.parametrize("argv", [["--help"], ["--api", "--help"]])
    def test_help_mentions_mcp(self, argv):
        result = runner.invoke(app, ["serve", *argv], catch_exceptions=False)
        assert result.exit_code == 0
        assert "mcp" in result.output.lower()
