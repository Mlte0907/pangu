"""P0-0 回归测试：统一权威记忆路径 + 空写保护。

## 这个缺陷家族为什么需要专门的回归测试

全仓 49 处 `MemoryStack(...)` 调用点中，只有 2 处（API 19529 / MCP）显式构造了
指向 v2 的 config，其余 47 处传默认 config → 读 v1 `palace/drawers.json`。
而 v1 文件实际是空的 `[]`（2 字节），真实存量在 v2 `db_path/v2_memories/`。

后果不是崩溃，而是**静默的空库**：CLI、8866 web 服务、自主维护全部读 0 条，
与 API 侧答案相反，且不报任何错。自主维护据此连续空转 81 次而无人察觉。

所以本文件的核心断言是**关系**而非数值：

    「同一时刻，CLI/调度器看到的记忆数 == API 看到的记忆数」

这条测试若早期存在，81 次空转不会发生。

## 为什么不硬编码条数

生产库是**活的**（19529 服务持续写入）。任何写死的数字（64/66/67…）都会随
时间漂移，让测试变成 flaky。这里一律断关系与不变量。

## 空写保护为什么也要测

`_save_drawers()` 原有的守卫条件是 `missing = self._primary_ids - disk_ids`；
当内存为空时 `_primary_ids` 也是空集 ⇒ `missing` 为空 ⇒ **守卫恒不触发** ⇒
直接覆写。实测（假 HOME，v1 预置 3 条）：`_drawers=[]` + `_primary_ids=set()`
→ 文件从 3 条被清成 **0 条**。这正是 v1 变成 `[]` 的可达路径——不需要专门
代码，走既有 save 路径即可把非空存储清空。故必须有一条测试钉住它。
"""

import json
import os
from pathlib import Path

import pytest

from pangu.core.config import PanguConfig
from pangu.memory.layers import Drawer, MemoryStack


def _write_drawers(path: Path, n: int, prefix: str = "d") -> None:
    """在指定 drawers.json 写入 n 条可辨识记录。

    `prefix` 必须区分 v1/v2 两个文件：`_load_drawers()` 按 **id 去重** 合并
    主存与只读源（layers.py 的 `seen` 集合），若两个文件用同一批 id，
    合并结果会被去重成主存的条数，测不出"合并"这件事。

    ⚠ 写盘前**强制**校验目标在临时目录下（见 `_assert_safe_write_path`）。
    """
    _assert_safe_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "id": f"{prefix}{i}",
                    "content": f"content-{i}",
                    "wing": "w",
                    "room": "r",
                }
                for i in range(n)
            ]
        ),
        encoding="utf-8",
    )


# 真实生产数据目录——任何测试都不允许写入这里。
_REAL_DATA_MARKERS = ("/.pangu/palace/", "/.pangu/pangu.db/", "/.pangu/")


def _assert_safe_write_path(path: Path) -> None:
    """硬防线：拒绝向生产 `~/.pangu` 写盘。

    为什么需要它（真实事故）：本文件曾因 `clean_home` 的 HOME 隔离在
    **并发跑测试**时未生效，`PanguConfig.load()` 解析到了生产 config.json
    （其 base_dir/db_path 是**绝对路径**，不随 HOME 变化），
    于是 `_write_drawers(cfg.authoritative_drawers_path, 10)` 直接把生产 v2
    从 66 条覆盖成 10 条 —— 真实数据丢失。

    教训：**只靠 HOME 环境变量隔离是不够的**（绝对路径配置 + 并发进程可绕过）。
    因此把防线放在实际写盘的那一个函数里，用真实路径判断，
    任何绕过隔离的调用都会 fail 而不是静默污染生产库。
    """
    s = str(Path(path).resolve())
    real_home = str(Path.home().resolve())
    is_tmp = any(s.startswith(p) for p in ("/tmp/", "/var/folders/", "/private/var/"))
    if not is_tmp:
        raise AssertionError(
            f"拒绝写盘：目标 {s} 不在临时目录下。"
            f"测试绝不允许写入生产数据目录（真实 HOME={real_home}）。"
            "请检查 clean_home/conftest 隔离是否生效。"
        )
    # 即便在 /tmp 下，也要确保没有指回真实 ~/.pangu
    if any(m in s for m in _REAL_DATA_MARKERS) and "pytest-" not in s and "tmp" not in s:
        raise AssertionError(f"拒绝写盘：目标 {s} 疑似生产数据路径。")


def _count(path: Path) -> int:
    return len(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
def clean_home(monkeypatch, tmp_path):
    """把 HOME 指向临时目录，得到**真正干净**的 `~/.pangu`。

    为什么必须改 HOME 而不是只设 `PANGU_BASE_DIR` / `PANGU_DB_PATH`：
    `PanguConfig.load()` 的配置路径**写死**为 `~/.pangu/config.json`
    （core/config.py:400，不读 `PANGU_CONFIG_PATH`），随后
    `cls(**json_data)` 直接用文件里的值构造实例。而真实 config.json 里
    显式写了 `base_dir` / `db_path` / `palace_path` 等全部路径字段——
    于是环境变量**被文件覆盖**，monkeypatch 形同虚设。

    实测（本仓库真实 config.json 含 `"db_path": "~/.pangu/pangu.db"`）：
    只设环境变量时 `PanguConfig.load()` 仍返回生产路径，测试会去读真库。
    改 HOME 后 `~/.pangu/config.json` 不存在 ⇒ load() 走纯默认值 ⇒ 环境变量生效。
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("PANGU_BASE_DIR", str(fake_home / ".pangu"))
    monkeypatch.setenv("PANGU_DB_PATH", str(fake_home / ".pangu" / "pangu.db"))

    # 硬校验①：环境隔离必须真的生效。若 `~/.pangu/config.json` 仍被读到
    # （并发/绝对路径配置等场景），这里立刻 fail，而不是让后续写盘命中生产库。
    cfg = PanguConfig.load()
    real = Path.home().resolve()
    if Path(cfg.memory_data_dir).resolve() != (fake_home / ".pangu" / "pangu.db" / "v2_memories").resolve():
        raise AssertionError(
            f"HOME 隔离未生效：memory_data_dir={cfg.memory_data_dir}，"
            f"预期在 {fake_home} 下。真实 HOME={real}。"
            "绝不能在未隔离的情况下继续，否则会覆盖生产记忆库。"
        )
    # 硬校验②：权威路径绝不能指向真实 ~/.pangu
    if str(Path(cfg.authoritative_drawers_path).resolve()).startswith(str(real)) and real != fake_home:
        raise AssertionError(f"权威路径指向真实 HOME：{cfg.authoritative_drawers_path}")
    return fake_home


# ── 1. 权威路径解析 ─────────────────────────────────────────────


class TestAuthoritativePathResolution:
    def test_memory_data_dir_points_at_v2(self, tmp_path):
        """权威记忆目录必须是 db_path/v2_memories，而不是 palace_path。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        assert cfg.memory_data_dir == tmp_path / "pangu.db" / "v2_memories"
        assert cfg.authoritative_drawers_path == cfg.memory_data_dir / "drawers.json"
        # 与 v1 路径必须是两个不同的位置
        assert cfg.memory_data_dir != Path(cfg.palace_path)

    def test_override_wins(self, tmp_path):
        """显式 override 优先于派生（迁移/测试需要）。"""
        cfg = PanguConfig(
            base_dir=tmp_path,
            db_path=tmp_path / "pangu.db",
            memory_data_dir_override=str(tmp_path / "elsewhere"),
        )
        assert cfg.memory_data_dir == tmp_path / "elsewhere"

    def test_authoritative_config_redirects_memory_paths(self, tmp_path, no_derived_path_isolation):
        """authoritative_memory_config() 把记忆相关路径指向 v2 且不改原对象。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        acc = cfg.authoritative_memory_config()
        assert acc.palace_path == str(cfg.memory_data_dir)
        # ⚠ 这里**刻意不再断言** identity/wiki 被迁移到 v2 目录。
        # 早期版本断言过 `Path(acc.identity_path).parent == cfg.memory_data_dir`，
        # 那其实是在给一个 **bug** 背书：identity 的契约是 `.txt`
        # （config.py:329 默认 identity.txt），改成 v2 下的 identity.json
        # 会让已配置身份的用户静默丢失 L0；wiki_path 则是**目录**语义。
        # 二者都不该跟着 drawers 迁移 —— 详见
        # TestAuthoritativeConfigPreservesIdentityAndWiki 与 config.py 的注释。
        # 原 config 不被就地修改（避免影响 Palace/Wiki/KG 的 v1 语义）
        assert cfg.palace_path == str(tmp_path / "palace")

    def test_empty_v1_is_not_a_merge_source(self, tmp_path):
        """v1 为空 `[]` 时不得作为合并源——合并它只会让人误以为读了 v1。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        _write_drawers(cfg.legacy_drawers_path(), 0)
        assert cfg.authoritative_extra_drawers_files() == []

    def test_nonempty_v1_is_a_merge_source(self, tmp_path):
        """v1 非空时保留为只读合并源（不丢历史数据）。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        _write_drawers(cfg.legacy_drawers_path(), 3)
        assert cfg.authoritative_extra_drawers_files() == [cfg.legacy_drawers_path()]


# ── 2. 默认构造（不传 config）必须读到权威库 ──────────────────────
#  这覆盖了那 47 处「传默认 config」的调用点中最危险的一类：完全不传。


class TestDefaultConstructionReadsAuthoritativeStore:
    def test_default_stack_targets_v2_dir(self, clean_home):
        """MemoryStack() 不传 config 时，palace_path 必须落在 v2 目录。"""
        stack = MemoryStack()
        assert Path(stack.config.palace_path) == clean_home / ".pangu" / "pangu.db" / "v2_memories"

    def test_default_stack_sees_v2_records_when_v1_empty(self, clean_home):
        """v1 空 + v2 非空 ⇒ 默认构造必须读到 v2 的条数且 > 0。

        这是「空转 81 次」的直接反例：修复前这里读到的是 0。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)  # v1 空
        _write_drawers(cfg.authoritative_drawers_path, 5)  # v2 有真数据

        stack = MemoryStack()
        assert stack.status()["total_memories"] == 5
        assert stack.status()["total_memories"] > 0

    def test_default_stack_merges_nonempty_v1(self, clean_home):
        """v2 主存 + v1 只读源 ⇒ 合并计数（不丢任何一边）。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 4, prefix="v2-")
        _write_drawers(cfg.legacy_drawers_path(), 2, prefix="v1-")

        stack = MemoryStack()
        assert stack.status()["total_memories"] == 6

    def test_explicit_config_is_still_respected(self, tmp_path):
        """显式传入的 config 语义不变（API/MCP 那 2 处传 v2 config，不得回归）。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        _write_drawers(cfg.legacy_drawers_path(), 3)

        stack = MemoryStack(config=cfg)
        assert stack.status()["total_memories"] == 3


# ── 3. 核心一致性断言：CLI/调度器 == API ─────────────────────────


class TestConsumerParity:
    def test_cli_memory_view_equals_api_memory_view(self, clean_home):
        """★ 核心回归 ★ CLI 看到的记忆数 == API 看到的记忆数。

        这条断言是「自主维护/CLI/8866 与 API 答案相反」这一 P0-0 缺陷的
        直接编码。修复前 CLI 侧读 v1 空库为 0、API 侧读 v2 为 7，必然失败。

        只比较关系、不比较绝对值（活库会漂移）。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)  # v1 空（真实故障态）
        _write_drawers(cfg.authoritative_drawers_path, 7)  # v2 真库

        # API 侧：server.py 的做法——显式构造指向 v2 的 config
        v2_cfg = PanguConfig()
        v2_dir = Path(v2_cfg.db_path) / "v2_memories"
        v2_cfg.palace_path = str(v2_dir)
        api_view = MemoryStack(
            config=v2_cfg,
            extra_drawers_files=v2_cfg.authoritative_extra_drawers_files(),
        ).status()["total_memories"]

        # CLI 侧：cli.get_memory_stack()（34 处 CLI 调用点的唯一入口）
        from pangu.cli import get_memory_stack

        cli_view = get_memory_stack(PanguConfig.load()).status()["total_memories"]

        assert cli_view == api_view
        assert cli_view > 0

    def test_pre_fix_v1_construction_now_sees_v2(self, clean_home):
        """★ 真正钉住"两个答案"的测试 ★

        模拟修复前的两种调用姿势，断言它们**不再分叉**：
          - 姿势 A（旧 CLI/维护/8866）：`MemoryStack(PanguConfig.load())`
            —— 修复前读空 v1 → 0 条；修复后：显式 config 仍尊重其语义，
               所以这个用例断言的是「CLI 的入口 helper」不再用这种姿势。
          - 姿势 B（旧 routes_memory 兜底）：`MemoryStack(PanguConfig())`
                ⇒ 修复后必须与 API 一致。

        这里直接比较"修复前会分叉的两个消费者"修复后的实际读数。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 5)

        from pangu.api.routes_memory import _memory_stack as routes_fallback
        from pangu.cli import get_config, get_memory_stack

        class _FakeApp:
            class state:  # noqa: N801 - 模拟无 memory 属性的 app.state
                pass

        class _FakeRequest:
            app = _FakeApp()

        cli_view = get_memory_stack(get_config()).status()["total_memories"]
        fallback_view = routes_fallback(_FakeRequest()).status()["total_memories"]

        assert cli_view == fallback_view == 5
        # 修复前：cli_view == 0（读空 v1）而 fallback_view == 0，API 侧 == 5

    def test_cli_default_view_equals_default_stack_view(self, clean_home):
        """CLI 入口与「裸 MemoryStack()」也必须一致（不得再出现两条路径）。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 3)

        from pangu.cli import get_config, get_memory_stack

        via_helper = get_memory_stack(get_config()).status()["total_memories"]
        via_bare = MemoryStack().status()["total_memories"]
        assert via_helper == via_bare == 3

    def test_routes_memory_fallback_does_not_read_empty_v1(self, clean_home):
        """routes_memory 的兜底路径必须与 app.state.memory 给同一答案。

        此前兜底是 `MemoryStack(config=PanguConfig())` → 读空 v1，
        于是同一进程内两条路径给出两个答案（列表时好时坏且不报错）。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 2)

        from pangu.api.routes_memory import _memory_stack

        class _FakeApp:
            class state:  # noqa: N801 - 模拟 Starlette app.state，故意无 memory 属性
                pass

        class _FakeRequest:
            app = _FakeApp()

        fallback_view = _memory_stack(_FakeRequest()).status()["total_memories"]
        assert fallback_view == 2

    def test_cli_stats_command_does_not_crash(self, clean_home):
        """`pangu stats` 必须能跑通（修复前 KeyError: 'L0_identity'）。

        顺带钉住 CLI 与 status() 的契约：该命令读 layers.L0_identity.tokens。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 4)

        from pangu.cli import get_config, get_memory_stack

        memory = get_memory_stack(get_config())
        st = memory.status()
        # 契约：L0 tokens 在 layers 子字典内，且顶层有 total_drawers
        assert "L0_identity" in st["layers"]
        assert isinstance(st["layers"]["L0_identity"]["tokens"], int)
        assert st["total_drawers"] == st["total_memories"] == 4


# ── 4. 空写保护（防数据丢失）─────────────────────────────────────


class TestEmptyWriteProtection:
    def test_empty_memory_does_not_wipe_nonempty_disk(self, tmp_path):
        """★ 核心回归 ★ 磁盘非空 + 内存主集为空 ⇒ 文件条数必须不变。

        修复前实测 3 → 0（数据被清空）。这是 v1 变成 `[]` 的 runtime 可达路径。
        """
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 3)

        stack = MemoryStack(config=cfg)
        stack._drawers = []
        stack._primary_ids = set()
        stack._save_drawers()

        assert _count(target) == 3  # 修复前为 0

    def test_guard_is_not_based_on_primary_ids(self, tmp_path):
        """守卫必须基于磁盘条数。

        若用 `_primary_ids` 判断（旧代码），内存为空时它同样是空集，
        守卫恒不触发——本用例在那种实现下会失败。
        """
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 2)

        stack = MemoryStack(config=cfg)
        stack._drawers = []
        stack._primary_ids = set()  # 空集：旧守卫的失效点
        assert stack._disk_has_records() is True
        stack._save_drawers()
        assert _count(target) == 2

    def test_empty_disk_allows_write(self, tmp_path):
        """磁盘本来就空时不该拦截正常写入（不得变成"永远写不进去"）。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 0)

        stack = MemoryStack(config=cfg)
        stack._drawers = []
        stack._primary_ids = set()
        stack._save_drawers()  # 不应抛异常
        assert _count(target) == 0

    def test_legitimate_add_still_persists(self, tmp_path):
        """合法写入必须照常落盘（守卫不能误伤）。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 1)

        stack = MemoryStack(config=cfg)
        stack.add_drawer(Drawer(id="new-1", content="hello", wing="w", room="r"))
        assert _count(target) == 2

    def test_legitimate_delete_still_persists(self, tmp_path):
        """合法的"记录数变少"（真删）也必须能落盘。

        空写保护只在「内存主集为空」时触发，不影响"还有记录但变少"的情形。
        """
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 4)

        stack = MemoryStack(config=cfg)
        stack._drawers = stack._load_drawers()[:1]
        stack._primary_ids = {d.id for d in stack._drawers}
        stack._save_drawers()
        assert _count(target) == 1

    def test_guard_covers_storage_backend_path(self, tmp_path):
        """存储后端分支也必须受保护（它是无条件写入，对 [] 零防护）。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        target = cfg.legacy_drawers_path()
        _write_drawers(target, 3)

        stack = MemoryStack(config=cfg)
        stack._drawers = []
        stack._primary_ids = set()
        # 注入一个"无条件写入"的假后端，模拟 JsonDrawerStorage.save()
        saved = []

        class _Unconditional:
            def load(self):
                return json.loads(target.read_text(encoding="utf-8"))

            def save(self, drawers):
                saved.append(list(drawers))
                target.write_text(json.dumps([d.to_dict() for d in drawers]), encoding="utf-8")

        stack._storage = _Unconditional()
        stack._save_drawers()

        assert saved == []  # 后端未被调用
        assert _count(target) == 3


# ── 5. 真实环境冒烟（不依赖 tmp_path 之外的任何东西）───────────────


class TestRealEnvironmentSmoke:
    def test_no_consumer_reads_empty_v1_when_v2_has_data(self, clean_home):
        """端到端：构造 v1 空 / v2 有数据，所有消费者入口都必须 > 0。

        覆盖 API、CLI、web_server(8866) 三条实际故障路径的构造方式。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 6)

        from pangu.cli import get_config, get_memory_stack

        # CLI
        assert get_memory_stack(get_config()).status()["total_memories"] == 6
        # API（server.py 的构造方式）
        assert MemoryStack(config=cfg.authoritative_memory_config()).status()["total_memories"] == 6
        # web_server(8866) 的构造方式
        assert (
            MemoryStack(
                config=cfg.authoritative_memory_config(),
                extra_drawers_files=cfg.authoritative_extra_drawers_files(),
            ).status()["total_memories"]
            == 6
        )

    def test_v1_empty_file_is_recognised_as_empty(self, tmp_path):
        """`[]`（2 字节）必须被识别为"无内容"，而不是一个有效的空库。"""
        cfg = PanguConfig(base_dir=tmp_path, db_path=tmp_path / "pangu.db")
        v1 = cfg.legacy_drawers_path()
        _write_drawers(v1, 0)
        assert v1.read_text(encoding="utf-8") == "[]"
        assert cfg.authoritative_extra_drawers_files() == []


@pytest.mark.parametrize("n_v2", [1, 3, 10])
def test_v2_count_is_authoritative_for_default_stack(clean_home, n_v2):
    """参数化：默认栈读到的条数始终等于 v2 条数（v1 为空）。"""
    cfg = PanguConfig.load()
    _write_drawers(cfg.legacy_drawers_path(), 0)
    _write_drawers(cfg.authoritative_drawers_path, n_v2)

    assert MemoryStack().status()["total_memories"] == n_v2


def _write_drawers_raw(path, items) -> None:
    """写入任意 drawer 字典列表（写盘前同样强制安全校验）。"""
    _assert_safe_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items), encoding="utf-8")


# ── 端点级验收：三条一致性（MCP / REST stats 的 health+tokens / REST search）──
class TestStatsEndpointParity:
    """复现队长在线上实测到的缺口形态。

    缺口历史：`/api/v2/memories/stats` 的 health 段曾走 v1，线上返回
    `{"drawers_file": {"count": 0}, "status": "degraded"}`——健康检查
    因读空库而**自报降级**。而 tokens 段当时已修好，
    所以**只断言 tokens 会让 health 缺口继续漏网**。本类两个字段都断言。
    """

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from pangu.api.routes_memory import router

        app = FastAPI()
        # 前缀必须与 pangu/api/server.py 的挂载方式一致
        # （`app.include_router(mem_router, prefix="/api/v2")`），
        # 否则测试打的是 404，会把"路由不存在"误判成"读不到数据"。
        app.include_router(router, prefix="/api/v2")
        return TestClient(app)

    def test_stats_health_and_tokens_both_nonzero(self, clean_home):
        """health.drawers_file.count 与 tokens.total 必须**同时** > 0。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)  # v1 空（真实故障态）
        _write_drawers(cfg.authoritative_drawers_path, 6)  # v2 真库

        r = self._client().get("/api/v2/memories/stats")
        assert r.status_code == 200
        d = r.json()
        body = d.get("data", d)

        health = body.get("health")
        assert health is not None, f"health 缺失: {list(body)}"
        count = health["drawers_file"]["count"]
        assert count == 6, f"health.drawers_file.count 应来自 v2(=6)，实得 {count}"
        # 不得因读空库而自报降级
        assert health.get("status") != "degraded" or count > 0

        tokens = body.get("tokens")
        assert tokens is not None, f"tokens 缺失: {list(body)}"
        assert tokens["total"] > 0, "tokens.total 应来自 v2，实得 0"

    def test_stats_health_matches_search_matches_stack(self, clean_home):
        """★ 三条一致性 ★ health.count == search.total == stack.total_memories。

        不硬编码条数（活库会漂移），只断言三者相等。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 4)

        client = self._client()
        body = client.get("/api/v2/memories/stats").json()
        body = body.get("data", body)
        health_count = body["health"]["drawers_file"]["count"]

        sr = client.get("/api/v2/memories/search", params={"q": "content", "limit": 50}).json()
        sr = sr.get("data", sr)
        search_total = sr.get("total")

        stack_total = MemoryStack(
            config=cfg.authoritative_memory_config(),
            extra_drawers_files=cfg.authoritative_extra_drawers_files(),
        ).status()["total_memories"]

        assert health_count == search_total == stack_total, (
            f"三者应一致：health={health_count} search={search_total} stack={stack_total}"
        )
        assert health_count > 0

    def test_search_route_reads_authoritative_store(self, clean_home):
        """`GET /memories/search`（无鉴权、匿名可打）必须能搜到 v2 内容。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        _write_drawers(cfg.authoritative_drawers_path, 3)

        r = self._client().get("/api/v2/memories/search", params={"q": "content", "limit": 10})
        assert r.status_code == 200
        body = r.json()
        body = body.get("data", body)
        assert body.get("total", 0) > 0, f"搜索读不到 v2 内容: {body}"


# ── 空写保护的**反例**测试：合法删除必须真的落盘 ──
class TestEmptyWriteGuardDoesNotBlockLegitimateDeletes:
    """守卫必须区分"假空"与"真空"。

    缺陷历史（真实回归）：早期守卫条件为
        `if not primary_drawers and self._disk_has_records(): ... return`
    只看"结果形状"（空 vs 非空）。但**删掉最后一条**时这两个条件恰好也成立
    ⇒ 合法删除被当成误写拦截 ⇒ `remove_drawer()` 返回 True 而**磁盘没变**
    ⇒ 内存与磁盘静默不一致。回归证据：`tests/test_core.py::test_remove_drawer`。

    修法：引入 `_loaded_ok`——只有"内存**从未成功加载过**"（假空）才拦，
    "加载成功后删空"（真空）必须放行。
    """

    def test_remove_last_drawer_empties_disk(self, clean_home):
        """删掉最后一条 ⇒ 磁盘必须真的变空。"""
        from pangu.core.palace import Drawer

        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 1)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        assert ms.count_drawers() == 1
        assert ms.remove_drawer("d0") is True
        assert ms.count_drawers() == 0

        # 关键断言：磁盘也必须是空的（这正是回归漏掉的那半）
        import json

        on_disk = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert on_disk == [], f"磁盘应被清空，实得 {len(on_disk)} 条"

    def test_remove_drawers_all_empties_disk(self, clean_home):
        """批量删光 ⇒ 磁盘必须真的变空（同一缺陷的第二条路径）。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 3)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        assert ms.remove_drawers(["d0", "d1", "d2"]) == 3
        assert ms.count_drawers() == 0

        import json

        on_disk = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert on_disk == [], f"磁盘应被清空，实得 {len(on_disk)} 条"

    def test_delete_then_add_roundtrip_is_consistent(self, clean_home):
        """删空后再新增一条，磁盘必须与内存一致（防止守卫状态残留）。"""
        from pangu.core.palace import Drawer

        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 1)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        ms.remove_drawer("d0")
        ms.add_drawer(Drawer(id="new1", content="x", wing="w", room="r"))

        import json

        on_disk = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert [d["id"] for d in on_disk] == ["new1"]

    def test_fake_empty_still_protected(self, clean_home):
        """反向：**假空**（内存被清但从未成功加载）仍必须被拦截。

        这是守卫存在的原始理由——不能为了让删除通过而把保护也拆掉。
        """
        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 3)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        # 模拟"读失败后的空库误写"：绕过加载，直接制造空内存 + 未加载标志
        ms._drawers = []
        ms._primary_ids = set()
        ms._loaded_ok = False
        assert ms._save_drawers() is False, "假空必须被拦截"

        import json

        on_disk = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert len(on_disk) == 3, "磁盘不应被清空"

    def test_save_drawers_reports_success(self, clean_home):
        """`_save_drawers()` 必须返回布尔值，让调用方能感知"是否真的落盘"。

        早期实现静默 `return`（返回 None），调用方无从得知保存被跳过，
        于是出现"返回成功但磁盘未更新"的静默不一致。
        """
        from pangu.core.palace import Drawer

        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 1)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        ms.add_drawer(Drawer(id="z1", content="y", wing="w", room="r"))
        assert ms._save_drawers() is True


# ── B1 回归：维护函数在"v2 有数据"时不得崩（空库测试测不到）──
class TestMaintenanceFunctionsWithRealData:
    """★ 关键：必须用**非空**库测试 ★

    缺陷历史：`lifecycle.py` 的写回语句引用 `drawers_file`，但改读权威路径时
    把同函数内的赋值删掉了 ⇒ `NameError: name 'drawers_file' is not defined`。

    ⚠ 为什么原有测试全绿却没发现：库为空时这些函数走
    `return {"status": "no_memories"}` **提前返回**，根本到不了崩溃点。
    一旦 v2 有记忆（修复后必然如此）就必崩。而 autonomous 调度用 `except`
    包裹 ⇒ 只记 failed 不报警 ⇒ 又一次**静默失败**。

    所以本类**刻意造非空数据**，覆盖 early-return 绕过的代码路径。
    """

    def _make_lifecycle(self, cfg, n=8):
        from pangu.memory.lifecycle import LifecycleManager

        # importance 低 + created_at 旧 ⇒ 触发衰减/强化/遗忘等分支，
        # 让函数真正走到"写回"那一行（而不是因为无事可做提前返回）
        items = [
            {
                "id": f"m{i}",
                "content": "足够长的记忆内容用于触发压缩与融合路径 " * 3,
                "wing": "w",
                "room": "r",
                "importance": 0.2,
                "created_at": "2020-01-01T00:00:00",
            }
            for i in range(n)
        ]
        _write_drawers_raw(cfg.authoritative_drawers_path, items)
        return LifecycleManager(cfg)

    @pytest.mark.parametrize(
        "method",
        ["run_decay", "run_auto_decay", "run_consolidation", "run_auto_fusion", "run_auto_compress"],
    )
    def test_no_nameerror_with_real_data(self, clean_home, method):
        """每个维护入口在有数据时都必须不抛 NameError。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)
        lm = self._make_lifecycle(cfg, 8)

        result = getattr(lm, method)()  # 抛出 NameError 即测试失败
        assert isinstance(result, dict)

    def test_decay_writes_back_to_authoritative_path(self, clean_home):
        """写回必须落在 v2（与读取同路径），不能写成 v1 的新分叉。"""
        import json

        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)  # v1 保持空
        lm = self._make_lifecycle(cfg, 8)

        lm.run_decay()

        # v2 仍应是有效 JSON 且条数未丢
        v2 = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert len(v2) == 8
        # v1 必须**仍然为空**——若被写入就说明产生了"读 v2 写 v1"的新分叉
        v1 = json.loads(cfg.legacy_drawers_path().read_text(encoding="utf-8"))
        assert v1 == [], f"v1 不应被写入，实得 {len(v1)} 条"


# ── B2 回归：解析失败必须识别为"假空"，不得清空磁盘 ──
class TestCorruptFileIsNotTreatedAsEmpty:
    """★ "读失败" ≠ "读到 0 条" ★

    缺陷历史：`JsonDrawerStorage.load()` 内部 `except Exception` 吞掉解析异常
    返回空列表，而 `MemoryStack._load_drawers()` 在调用**之后**无条件置
    `_loaded_ok = True` ⇒ "解析失败"被误判成"成功加载到 0 条"
    ⇒ 后续落盘把磁盘上**尚可挽救**的内容清空
    （实测：133 字节的损坏文件被清成 `[]`，2 字节）。

    另一处同源缺陷：`_disk_has_records()` 的 `except: return False`
    让空写守卫失效（它调 `self._storage.load()`，同样吞异常返回 []）。
    """

    def _corrupt_bytes(self, path):
        """写一个"前 2 条完好但整体 JSON 截断"的文件。"""
        good = [
            {"id": "g0", "content": "AAAA", "wing": "w", "room": "r"},
            {"id": "g1", "content": "BBBB", "wing": "w", "room": "r"},
        ]
        _assert_safe_write_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(good)[:-1] + ',{"id":"broken",', encoding="utf-8")
        return path.stat().st_size

    def test_parse_failure_is_marked_not_ok(self, clean_home):
        """解析失败时 `_loaded_ok` 必须为 False（而不是被当成成功读到 0 条）。"""
        cfg = PanguConfig.load()
        size = self._corrupt_bytes(cfg.authoritative_drawers_path)
        assert size > 0

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        ms.count_drawers()
        assert ms._loaded_ok is False, "解析失败被错判成成功加载"
        assert ms._storage.last_load_ok is False

    def test_corrupt_file_is_not_overwritten(self, clean_home):
        """损坏文件不得被空写清空——磁盘字节数应保持不变。"""
        cfg = PanguConfig.load()
        path = cfg.authoritative_drawers_path
        size = self._corrupt_bytes(path)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        ms.count_drawers()
        assert ms._save_drawers() is False, "空写保护应拦截"

        assert path.stat().st_size == size, f"损坏文件被改写：{size} → {path.stat().st_size} 字节"

    def test_disk_has_records_true_on_corrupt(self, clean_home):
        """`_disk_has_records()` 在解析失败时必须保守返回 True。

        否则守卫会因为"读不出来"而失效（这正是清库的最后一道缺口）。
        """
        cfg = PanguConfig.load()
        self._corrupt_bytes(cfg.authoritative_drawers_path)

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        assert ms._disk_has_records() is True

    def test_genuinely_empty_file_still_writable(self, clean_home):
        """反向：真正空的库（`[]` / 文件不存在）必须仍可正常写入。

        不能因为修 B2 就把"合法空库"也锁死。
        """
        from pangu.core.palace import Drawer

        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 0)  # 合法空 `[]`

        ms = MemoryStack(config=cfg.authoritative_memory_config())
        ms.count_drawers()
        assert ms._loaded_ok is True, "合法空库应判为成功加载"

        ms.add_drawer(Drawer(id="n1", content="hello", wing="w", room="r"))
        on_disk = json.loads(cfg.authoritative_drawers_path.read_text(encoding="utf-8"))
        assert [d["id"] for d in on_disk] == ["n1"]


# ── B3 回归：权威化不得改变 identity / wiki 的语义 ──
class TestAuthoritativeConfigPreservesIdentityAndWiki:
    """★ 权威化只迁移记忆路径，不得顺手改掉身份/知识库的语义 ★

    缺陷历史（P0-0 修复**引入**的回归）：`authoritative_memory_config()` 曾写成
        cfg.identity_path = str(v2_dir / "identity.json")
        cfg.wiki_path     = str(v2_dir / "wiki.json")
    两处都错，且错法不同：

    1) identity 的契约是 **`.txt`**（`config.py:329` 默认 `identity.txt`；
       `layers.py:55/65` 文档与提示语同样是 `.txt`）。
       改成 v2 目录下的 `identity.json` ⇒ **文件存在却读不到**：
       已配置身份的用户静默丢失 L0 身份（不报错，只报 degraded）。
    2) wiki_path 被 `wiki/engine.py:17-21` 当**目录**用
       （`mkdir` 后往里写 `wiki_index.json` 和 `<id>.md`），
       而原来赋的是**文件路径** `wiki.json` —— 类型就错了。

    语义判断：身份文件是用户手工创建的配置文件、wiki 是独立知识库目录，
    都不是"记忆抽屉数据"，不该跟着 drawers 迁移。
    """

    def _seed_identity(self, home: Path) -> Path:
        p = home / ".pangu" / "identity.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("我是盘古测试身份", encoding="utf-8")
        return p

    def test_identity_path_keeps_txt_and_is_readable(self, clean_home, no_derived_path_isolation):
        """identity.txt 存在时，权威化后 L0 必须仍能读到。"""
        home = Path(clean_home)
        ident = self._seed_identity(home)

        cfg = PanguConfig.load()
        auth = cfg.authoritative_memory_config()

        assert auth.identity_path.endswith(".txt"), f"identity 契约是 .txt，实得 {auth.identity_path}"
        assert Path(auth.identity_path) == ident
        assert os.path.exists(auth.identity_path), "身份文件存在却指向了不存在的路径"

        stack = MemoryStack(config=auth)
        assert "身份未配置" not in stack.l0.render(), "L0 身份丢失"

    def test_wiki_path_stays_a_directory(self, clean_home):
        """wiki_path 必须仍是目录语义（不能变成 wiki.json 这种文件路径）。"""
        cfg = PanguConfig.load()
        auth = cfg.authoritative_memory_config()

        assert not auth.wiki_path.endswith(".json"), f"wiki_path 是目录语义，不该是文件路径：{auth.wiki_path}"
        # engine 会对它 mkdir 并往里写文件，这里直接验证该契约成立
        from pangu.wiki.engine import WikiEngine

        engine = WikiEngine(auth)  # 内部 mkdir(exist_ok=True)，不是目录会抛错
        assert Path(engine.wiki_path).is_dir()

    def test_authoritative_still_moves_memory_path(self, clean_home):
        """反向：**记忆**路径必须仍然迁移到 v2（别把 B3 修过头）。"""
        cfg = PanguConfig.load()
        auth = cfg.authoritative_memory_config()

        assert Path(auth.palace_path) == Path(cfg.memory_data_dir)
        assert auth.authoritative_drawers_path == cfg.authoritative_drawers_path


# ── B4 回归：importance_feedback 必须读写 v2，且不静默吞错 ──
class TestImportanceFeedbackUsesAuthoritativePath:
    """★ 这条曾造成**生产污染** ★

    缺陷历史：`retrieval.py:594 importance_feedback` 读写都硬编码
    `Path(cfg.palace_path) / "drawers.json"`（v1），且写回包在
    `except Exception: pass` 里。当调用方传入 `drawers=[...]` 时，
    函数会**无条件把整个列表写进 v1 生产库** —— 测试数据 `fb_min`
    就是这样落进 `~/.pangu/palace/drawers.json` 的。
    """

    def test_reads_from_v2_not_v1(self, clean_home):
        """不传 drawers 时应从 v2 读；生效目标是 v2 里的那条。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.legacy_drawers_path(), 0)  # v1 空
        _write_drawers(cfg.authoritative_drawers_path, 3)

        from pangu.memory.retrieval import importance_feedback

        result = importance_feedback("d1", "vote_up")
        assert "error" not in result, f"应从 v2 读到该记忆，实得 {result}"
        assert result["new_importance"] > result["old_importance"]

    def test_does_not_write_v1(self, clean_home):
        """关键回归断言：v1 必须字节不变（生产污染的直接测法）。"""
        cfg = PanguConfig.load()
        v1 = cfg.legacy_drawers_path()
        _write_drawers(v1, 0)
        size_before = v1.stat().st_size
        _write_drawers(cfg.authoritative_drawers_path, 3)

        from pangu.memory.retrieval import importance_feedback

        importance_feedback("d1", "vote_up")

        assert v1.stat().st_size == size_before, "v1 被写入了"
        assert json.loads(v1.read_text(encoding="utf-8")) == []

    def test_does_not_overwrite_with_empty_list(self, clean_home):
        """空列表 + 非空磁盘 ⇒ 必须拒绝落盘（不静默清库）。"""
        cfg = PanguConfig.load()
        _write_drawers(cfg.authoritative_drawers_path, 3)
        size_before = cfg.authoritative_drawers_path.stat().st_size

        from pangu.memory.retrieval import importance_feedback

        result = importance_feedback("nope", "vote_up")  # 目标不存在
        assert "error" in result
        assert cfg.authoritative_drawers_path.stat().st_size == size_before


class TestFtsIndexEmptyLockIn:
    """B7-c：`doc_count=0` 的磁盘索引**不得**阻止重建。

    真实事故（P0-0 漏网缺陷 5）：`warmup.py` 用未权威化的 `PanguConfig.load()`
    取到 v1 **空库**，启动时把 `~/.pangu/fts_index.json` 写成
    `{doc_count: 0, tokens: {}}`；而 `FTS5SearchEngine._indexed_count` 的初始值
    也是 `0`，`_load_index_from_disk` 里 `doc_count != _indexed_count`
    退化成 `0 != 0` → False ⇒ 空索引被判为"最新"加载并返回成功，
    于是 `build_index` 永不重建、搜索**恒为 0 条且重启不自愈**。

    这条测试若早期存在，服务搜索不会挂。断言的是**行为**（能重建 + 能搜到），
    而不是内部字段，因此对实现方式不敏感。
    """

    def _engine(self, cfg, monkeypatch, tmp_path):
        """构造一个把索引文件指向临时目录的引擎，避免碰生产 ~/.pangu。"""
        from pangu.memory.fts_search import FTS5SearchEngine

        idx = tmp_path / "fts_index.json"
        _assert_safe_write_path(idx)
        monkeypatch.setattr(FTS5SearchEngine, "_get_index_path", lambda self: idx)
        return FTS5SearchEngine(cfg), idx

    def test_empty_disk_index_does_not_block_rebuild(self, clean_home, monkeypatch, tmp_path):
        from pangu.memory.fts_search import FTS5SearchEngine

        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 5, prefix="fts")
        drawers = PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)
        assert len(drawers) == 5

        engine, idx = self._engine(cfg, monkeypatch, tmp_path)
        # 注入"锁死条件"：磁盘上是空索引，且 doc_count=0
        idx.write_text(json.dumps({"tokens": {}, "doc_count": 0}), encoding="utf-8")

        from pangu.memory.layers import Drawer

        ds = [Drawer.from_dict(d) for d in drawers]
        tokens = engine.build_index(ds)

        assert tokens > 0, "doc_count=0 的空索引被当成'最新'加载了，索引永远无法重建（B7-b 哨兵值撞车复发）"

    def test_empty_disk_index_is_never_persisted(self, clean_home, monkeypatch, tmp_path):
        """空索引不落盘：否则会给下一个进程制造锁死条件。"""
        from pangu.memory.fts_search import FTS5SearchEngine

        cfg = PanguConfig.load().authoritative_memory_config()
        engine, idx = self._engine(cfg, monkeypatch, tmp_path)
        engine.build_index([])  # 0 条

        if idx.exists():
            data = json.loads(idx.read_text(encoding="utf-8"))
            assert data.get("doc_count"), (
                f"空索引被写入磁盘（doc_count={data.get('doc_count')}），这会让后续启动加载空索引并跳过重建"
            )

    def test_search_recovers_after_injected_empty_index(self, clean_home, monkeypatch, tmp_path):
        """端到端：注入空索引后，FTS 检索仍能命中（证明锁死已解除）。

        ⚠ 这里刻意走 `_fts_search` 而不是 `search()`：后者会触发向量嵌入
        （ONNX 推理，首次调用可能数十秒甚至更久），而本用例要证明的是
        **FTS 索引是否被正确重建**，与向量无关。走向量路径会让用例既慢
        又不稳定，还会掩盖真正被测的行为。
        """
        from pangu.memory.fts_search import FTS5SearchEngine
        from pangu.memory.layers import Drawer

        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 3, prefix="fts")
        drawers = PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)

        engine, idx = self._engine(cfg, monkeypatch, tmp_path)
        idx.write_text(json.dumps({"tokens": {}, "doc_count": 0}), encoding="utf-8")

        ds = [Drawer.from_dict(d) for d in drawers]
        engine.build_index(ds)
        assert engine._indexed_count == 3, "索引未按权威库条数重建"

        hits = engine._fts_search("content-0", ds, limit=5)
        assert hits, "注入空索引后 FTS 检索仍为 0 条 —— 锁死未解除"


class TestWarmupUsesAuthoritativePath:
    """B7-a：`warmup.py` 必须走权威路径，否则服务每次启动都用 v1 空库建索引。"""

    def test_warmup_config_is_authoritative(self, clean_home):
        """warmup 的 config 必须解析到权威库，且能看到真实记忆。"""
        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 4, prefix="wu")

        stack = MemoryStack(PanguConfig.load().authoritative_memory_config())
        assert stack.count_drawers() == 4, "warmup 取不到权威库的记忆（仍在读 v1 空库）"

    def test_warmup_source_does_not_use_bare_load(self):
        """静态守护：warmup 的 MemoryStack 构造点不得使用裸 PanguConfig.load()。

        只检查**代码行**，跳过注释——修复说明里会引用旧写法的字样
        （"此前这里是裸 `PanguConfig.load()`"），那是对历史的记录，
        不是需要修的代码。
        """
        src = Path(__file__).resolve().parent.parent / "pangu" / "memory" / "warmup.py"
        lines = src.read_text(encoding="utf-8").splitlines()
        offenders = []
        for i, line in enumerate(lines, 1):
            code = line.split("#", 1)[0]
            if "PanguConfig.load()" in code and "authoritative_memory_config" not in code:
                offenders.append(i)
        assert not offenders, (
            f"warmup.py 第 {offenders} 行存在未权威化的 PanguConfig.load()，会导致用 v1 空库预热 FTS 索引（B7-a 复发）"
        )


class TestSubsetMustNotOverwriteSuperset:
    """F1/F3：子集写回**不得**覆盖全集。

    事故机制：`retrieval.importance_feedback(id, sig, drawers=[单条])` 把
    调用方传入的 1 条列表**整表覆盖**权威库（v2 被清成 402 字节的 fb_min）。
    这是 P0-0 生产数据丢失的**直接机制**，与路径是否正确无关 —— 即使
    `drawers_file` 指向 v2，覆盖行为本身依然是错的。

    断言的是**库不缩小**这一可观测性质，对内部实现（合并算法）不敏感。
    """

    def test_feedback_with_subset_does_not_shrink_store(self, clean_home):
        from pangu.memory.layers import Drawer
        from pangu.memory.retrieval import importance_feedback

        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 12, prefix="sub")
        before = _count(cfg.authoritative_drawers_path)
        assert before == 12

        # 只传"1 条"给函数——正是测试与真实调用方常见的用法
        one = Drawer.from_dict(PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)[0])
        importance_feedback(one.id, "vote_up", drawers=[one])

        after = _count(cfg.authoritative_drawers_path)
        assert after == before, (
            f"传入 1 条子集后权威库被覆盖：{before} → {after}。子集写回必须合并而非覆盖（F1/F3 复发）"
        )

    def test_feedback_updates_target_in_place(self, clean_home):
        """合并语义要真的改到目标那条，不能只是"什么都没做"。"""
        from pangu.memory.layers import Drawer
        from pangu.memory.retrieval import importance_feedback

        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 5, prefix="tgt")
        items = PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)
        target = next(i for i in items if i["id"] == "tgt2")
        target["importance"] = 0.5

        res = importance_feedback("tgt2", "vote_up", drawers=[Drawer.from_dict(target)])
        assert "error" not in res, res
        assert res["new_importance"] > 0.5

        after = PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)
        assert len(after) == 5, "合并过程中丢记录"
        got = next(i for i in after if i["id"] == "tgt2")
        assert got["importance"] == res["new_importance"], "目标记录的重要性未落盘"

    def test_feedback_appends_unknown_id_without_losing_others(self, clean_home):
        """传入磁盘上不存在的新记录 ⇒ 追加，且不丢原有记录。"""
        from pangu.memory.layers import Drawer
        from pangu.memory.retrieval import importance_feedback

        cfg = PanguConfig.load().authoritative_memory_config()
        _write_drawers(cfg.authoritative_drawers_path, 4, prefix="keep")

        new = Drawer(id="brand_new", content="x", wing="w", room="r", importance=0.5)
        importance_feedback("brand_new", "vote_up", drawers=[new])

        after = PanguConfig.load_drawers_nonempty(cfg.authoritative_drawers_path)
        ids = {i["id"] for i in after}
        assert "brand_new" in ids, "新记录未被追加"
        assert len([i for i in ids if i.startswith("keep")]) == 4, "原有 4 条被丢弃"


class TestEnvOverridesConfigJson:
    """F2：`PANGU_*` 环境变量必须**优先于** config.json（否则测试写生产库）。

    真实事故根因：`PanguConfig.load()` 执行 `cls(**json_data)`，把 config.json
    里的**绝对** `db_path` 作为构造参数传入；pydantic-settings 中
    **显式构造参数优先于环境变量**，于是 `PANGU_DB_PATH` 被静默压过，
    任何调用 `load()` 的测试都拿到生产路径并写入生产库
    （实测 v2 被反复覆盖）。

    `pangu/api/server.py` 早已声明 `_ENV_OVERRIDABLE_PATHS = ("db_path","base_dir")`
    表明 env 应可覆盖，但 `load()` 从未实现该语义 —— 本类锁死这一契约。
    """

    def test_env_db_path_beats_config_json(self, monkeypatch, tmp_path):
        cfgfile = tmp_path / "config.json"
        cfgfile.write_text(
            json.dumps(
                {
                    "base_dir": "/home/xiaoxin/.pangu",
                    "db_path": "/home/xiaoxin/.pangu/pangu.db",
                }
            ),
            encoding="utf-8",
        )
        isolated = tmp_path / "iso"
        monkeypatch.setenv("PANGU_BASE_DIR", str(isolated))
        monkeypatch.setenv("PANGU_DB_PATH", str(isolated / "pangu.db"))

        cfg = PanguConfig.load(str(cfgfile))
        assert str(cfg.db_path) == str(isolated / "pangu.db"), (
            f"环境变量被 config.json 覆盖：db_path={cfg.db_path}。这会让测试写入生产库（F2 复发）"
        )

    def test_env_unset_still_reads_config_json(self, monkeypatch, tmp_path):
        """不设 env 时必须保持旧行为（向后兼容，不能修出新回归）。"""
        target = tmp_path / "fromjson"
        cfgfile = tmp_path / "config.json"
        cfgfile.write_text(
            json.dumps({"base_dir": str(target), "db_path": str(target / "pangu.db")}),
            encoding="utf-8",
        )
        monkeypatch.delenv("PANGU_BASE_DIR", raising=False)
        monkeypatch.delenv("PANGU_DB_PATH", raising=False)

        cfg = PanguConfig.load(str(cfgfile))
        assert str(cfg.db_path) == str(target / "pangu.db"), "未设 env 时 config.json 应生效"

    def test_authoritative_path_stays_in_tmp_under_env(self, monkeypatch, tmp_path):
        """端到端：env 生效后，权威库路径必须落在隔离目录内（不会碰生产）。"""
        cfgfile = tmp_path / "config.json"
        cfgfile.write_text(
            json.dumps({"base_dir": "/home/xiaoxin/.pangu", "db_path": "/home/xiaoxin/.pangu/pangu.db"}),
            encoding="utf-8",
        )
        isolated = tmp_path / "iso2"
        monkeypatch.setenv("PANGU_BASE_DIR", str(isolated))
        monkeypatch.setenv("PANGU_DB_PATH", str(isolated / "pangu.db"))

        p = PanguConfig.load(str(cfgfile)).authoritative_memory_config().authoritative_drawers_path
        assert "pytest-" in str(p) or str(isolated) in str(p), f"权威库路径逃出隔离目录：{p}"
        _assert_safe_write_path(p)
