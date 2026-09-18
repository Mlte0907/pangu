"""scope 强制 + config 保护名单（2026-09-19 安全收口）。

三个洞（主动排查发现）：
1. scope（readwrite/readonly/admin）自建钥匙起**只存不查** —— readonly 钥匙实际拥有
   全部写权限（增删记忆/导入/改配置）。修：mcp_server 在唯一执行点强制，写类拒绝
   （code=1003，WRITE_TOOLS 名单）。
2. pangu_config_set 只查 hasattr(config, key) 就放行 —— base_dir/db_path/palace_path
   （改存储路径）、jwt_secret（伪造 JWT 提权）、host/port（改监听）全可改。修：保护名单。
3. pangu_config_get 明文返回 jwt_secret。修：排除名单扩展。

本文件覆盖 2/3 的 handler 行为 + 名单完整性；1 的行为验证走端到端
（readonly 实测：stats 放行、add_memory/set_source/config_set 全部 1003）。
"""

import asyncio
import json

import pytest

from pangu.core.config import PanguConfig


@pytest.fixture
def cfg(tmp_path):
    c = PanguConfig()
    c.base_dir = tmp_path
    c.db_path = tmp_path
    c.palace_path = str(tmp_path / "palace")
    c.ensure_dirs()
    return c


class _S:
    """最小 server 桩：config 工具只用 server.config（invalidate 为可选防御）。"""

    def __init__(self, config):
        self.config = config


def _call_set(cfg, **args):
    from pangu.server.handlers.system import handle_config_set

    return json.loads(asyncio.run(handle_config_set(_S(cfg), [], args)))


def test_config_set_blocks_protected_keys(cfg):
    """路径/端口/jwt/secret 类一律拒绝（此前任何有效钥匙可改）。"""
    protected = (
        "base_dir",
        "db_path",
        "palace_path",
        "identity_path",
        "backup_dir",
        "config_path",
        "jwt_secret",
        "jwt_secret_file",
        "host",
        "port",
        "web_host",
        "web_port",
        "api_key",  # 主钥匙明文（可被改 = 拒绝服务/换锁）
        "jwt_access_ttl",  # jwt 整族（含 default_password/roles/users = 提权面）
        "jwt_roles",
    )
    for key in protected:
        r = _call_set(cfg, key=key, value="/tmp/evil")
        assert "受保护" in str(r.get("error")), f"{key} 应被拒绝: {r}"
    assert str(cfg.base_dir) != "/tmp/evil", "受保护项的值必须纹丝不动"


def test_config_set_allows_normal_knobs(cfg):
    """普通行为参数照常可改（不误伤设置页/正常调参）。"""
    r = _call_set(cfg, key="importance_decay_rate", value=0.5)
    assert r.get("status") == "updated", r


def test_config_get_hides_secrets(cfg):
    """密钥类不再明文返回（jwt_secret 拿到可伪造 JWT 提权）。"""
    from pangu.server.handlers.system import handle_config_get

    out = json.loads(asyncio.run(handle_config_get(_S(cfg), [], {})))
    for k in ("jwt_secret", "jwt_secret_file", "api_key", "llm_api_key", "siliconflow_key"):
        assert k not in out, f"{k} 不应出现在 config_get 返回里"


def test_write_tools_sane():
    """写类名单完整性：工具必须真实存在；名字不得混入读类（防拼写漂移）。"""
    from pangu.server.handlers import HANDLERS
    from pangu.server.module_registry import WRITE_TOOLS

    missing = WRITE_TOOLS - set(HANDLERS)
    assert not missing, f"名单里有不存在的工具: {missing}"
    # 抽查：读类工具绝不能进写名单（否则 readonly 连读都被拦）
    read_only = {"pangu_stats", "pangu_search_memories", "pangu_recall", "pangu_system_health"}
    assert not (read_only & WRITE_TOOLS), "读类工具被误列进写名单"


def test_admin_tools_sane():
    """管理类名单（2026-09-19 产品决策）：存在性 + 与写类名单的包含关系 + 刻意排除项。"""
    from pangu.server.handlers import HANDLERS
    from pangu.server.module_registry import ADMIN_TOOLS, WRITE_TOOLS

    assert ADMIN_TOOLS, "管理类名单不应为空"
    missing = ADMIN_TOOLS - set(HANDLERS)
    assert not missing, f"名单里有不存在的工具: {missing}"
    # readonly 应先被 1003 拦（管理类必须同时是写类）
    assert ADMIN_TOOLS <= WRITE_TOOLS, "管理类工具应同时属于写类"
    # 刻意排除：config_set（设置页要用；handler 内已有保护名单）
    assert "pangu_config_set" not in ADMIN_TOOLS
    # 刻意排除：backup/export（只读数据 + 写文件，不破坏本体）
    assert "pangu_backup" not in ADMIN_TOOLS and "pangu_export" not in ADMIN_TOOLS
    # 判据核心：恢复与导入类在列
    assert {"pangu_restore_backup", "pangu_import", "pangu_batch_import"} <= ADMIN_TOOLS
