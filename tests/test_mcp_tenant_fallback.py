"""MCP 写入的 tenant_id 归属回退（2026-09-26）。

锁的坑：`identity.get("room", 默认值)` **只在 key 缺失时回退**。api_key 凭据的 identity 里
room 是「存在但为空串」（mcp_server.py: `tenant = identity.get("room", "")`），默认值因此
永不生效，写入的 tenant_id 是 ''。

后果不是「多一个空值」那么轻：metadata_visible 对 vis='tenant' 的判据是
`md.get("tenant_id","") != tenant` 即拒绝（layers.py:389），而空串不等于任何平台的 room，
于是这批记忆**对每个平台 agent 都不可见**，只有全库视角（admin / 后台 / 图谱）看得到。
云端实测 46 条这样的记忆（source_session 全为 'key:api_key_user@'）。

本测试只锁「回退行为」，不锁「这些记忆最终该谁可见」—— 那是产品政策，见 README 与
issue 追踪，不在单测里替你定。
"""

import inspect
import pathlib
import tempfile

import pytest

from pangu.core.config import PanguConfig
from pangu.core.palace import Drawer
from pangu.memory.layers import metadata_visible


def _handler_source() -> str:
    from pangu.server.handlers import memory_ops

    return inspect.getsource(memory_ops.handle_add_memory)


def _handler_code_only() -> str:
    """去掉整行注释与行尾注释，只留可执行代码。

    必须这样：修复说明里本身就要引用 `identity.get("room", 默认值)` 这个旧写法，
    直接对全文做字符串匹配会被注释自己命中。
    """
    lines = []
    for raw in _handler_source().splitlines():
        if raw.strip().startswith("#"):
            continue
        lines.append(raw.split("  #", 1)[0])
    return "\n".join(lines)


def test_tenant_fallback_is_or_chain_not_get_default():
    """源码级锁定：`metadata["tenant_id"]` 那行不能再用「只在 key 缺失时才回退」的写法。

    只盯这一处赋值，不扫全函数 —— 同函数里 `drawer.source = identity.get("platform","")
    or identity.get("room","") or "mcp"` 是**正确**的（外面套了 or），不该被误伤。
    """
    code = _handler_code_only()
    lines = code.splitlines()
    idx = next((i for i, ln in enumerate(lines) if 'metadata["tenant_id"]' in ln), None)
    assert idx is not None, "找不到 tenant_id 赋值行 —— 实现被挪走了？"
    # 赋值可能是多行括号续写，取接下来几行拼起来看
    rhs = " ".join(" ".join(lines[idx:idx + 5]).split())
    assert 'identity.get("room",' not in rhs, f"tenant_id 又退回只在 key 缺失时才回退：{rhs}"
    assert 'identity.get("room") or' in rhs, f"room 必须用 or 链回退，空串也要往下走：{rhs}"


def test_empty_room_falls_back_to_default_tenant():
    """空 room → 落到 abac_default_tenant，而不是空串。

    直接复刻修好后的表达式，不依赖 handler 的运行时装配（那需要整套 server）。
    """
    cfg = PanguConfig()
    identity = {"key_id": "api-key-id", "room": ""}  # api_key 凭据的实际形状
    got = identity.get("room") or None or getattr(cfg, "abac_default_tenant", "default")
    assert got == "default", got
    assert got != "", "空串就是 bug 本身"


def test_real_room_still_wins():
    """平台 token 的 room 必须原样保留，不能被回退逻辑吃掉。"""
    identity = {"key_id": "ptok_x", "room": "opencode"}
    got = identity.get("room") or None or "default"
    assert got == "opencode", got


def test_empty_tenant_row_is_invisible_to_every_platform():
    """把后果钉死：tenant_id='' 且 vis='tenant' 的记忆，任何平台都读不到。

    这条是本测试存在的理由 —— 它证明那 46 条不是「无害的空值」。
    """
    md = {"tenant_id": "", "visibility": "tenant"}
    for platform in ("opencode", "deepseek-harness", "workbuddy", "mimo-desktop-agent"):
        assert metadata_visible(md, platform, "some-key") is False, f"{platform} 不该看到它"


def test_backfilled_row_is_visible_to_its_own_tenant_only():
    """回填成 default 之后：default 租户可见，其它平台仍不可见。

    这条同时说明**光修代码不够** —— 已写入的 46 条需要单独回填，而回填成什么值
    取决于「平台之间要不要互相可见」这个产品决定。
    """
    md = {"tenant_id": "default", "visibility": "tenant"}
    assert metadata_visible(md, "default", "k") is True
    assert metadata_visible(md, "opencode", "k") is False


def test_public_row_is_visible_to_all_platforms():
    """对照：vis='public' 的行对所有平台可见 —— 这才是「所有平台共享记忆」的落法。"""
    md = {"tenant_id": "deepseek-harness", "visibility": "public"}
    for platform in ("opencode", "deepseek-harness", "workbuddy"):
        assert metadata_visible(md, platform, "k") is True, platform
