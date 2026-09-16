"""P2-1 Step 1 回归测试：domain_knowledge 接入。

背景：domain_knowledge.py 之前有两个被测试假绿遮蔽的真实 bug：
  1. `:577` 用 `Counter` 但没 `from collections import Counter` →
     `get_stats()` 生产 100% NameError（tests 里 `try/except NameError: pass` 吞掉）。
  2. `:108` 硬编码 `Path.home() / '.pangu' / 'domain_knowledge.db'`，
     完全忽略 config → 测试隔离失效，数据落进生产 HOME。

P2-1 Step 1 修法：
  - 补 `Counter` import；
  - 路径改为 `config.domain_knowledge_db_path`；
  - PanguConfig 新增该字段 + env 覆盖名单（config.py + api/server.py）。

核心断言（三方向，遵循本项目"单向验证不够"纪律）：
  - must-block：隔离环境里 DB 必须落在 tmp_path（不落生产 HOME）；
  - must-allow：设 PANGU_DOMAIN_KNOWLEDGE_DB_PATH 后 DB 落在指定位置；
  - 异常输入：`get_stats()` 必须真实可用（不再被 NameError 吞）。
"""

import json
import os
from pathlib import Path

import pytest

from pangu.core.config import PanguConfig
from pangu.memory.domain_knowledge import DomainKnowledge


@pytest.fixture
def iso_env(monkeypatch, tmp_path):
    """隔离数据目录：DB 路径必须受 env 控制，不落生产 HOME。

    ⚠ 同时隔离 HOME —— `PanguConfig.load()` 用 `~/.pangu/config.json`
    定位配置，若不隔离会读到**真实生产配置**（并可能被其绝对路径带偏）。
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    data_dir = tmp_path / "pangu_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.joinpath("palace").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PANGU_BASE_DIR", str(data_dir))
    monkeypatch.setenv("PANGU_DB_PATH", str(data_dir / "pangu.db"))
    return data_dir


def _make(iso_env, db_path=None):
    cfg = PanguConfig.load()
    if db_path is not None:
        cfg.domain_knowledge_db_path = Path(db_path)
    return DomainKnowledge(cfg)


def test_db_path_follows_base_dir(iso_env, monkeypatch, tmp_path):
    """must-block：DB 路径必须跟随 PANGU_BASE_DIR，而不是硬编码的 HOME。

    为什么断言"在 base_dir 之下"而不是"不在 /home"：
    本 fixture 把 HOME 也指向 tmp_path/home，所以 bug 版
    `Path.home() / ".pangu" / "domain_knowledge.db"` **同样**会落在 tmp_path 下
    —— 只断言"在 tmp 下"或"不在 /home"根本抓不到它（单向验证不够）。
    唯一能区分两者的判据是：正确版跟随 `PANGU_BASE_DIR`（=iso_env），
    bug 版跟随 HOME（=tmp_path/home）。故断言 DB 必须在 base_dir 之下。
    """
    dk = _make(iso_env)
    db = Path(dk.db_path)
    assert str(iso_env) in str(db), f"DB 应跟随 PANGU_BASE_DIR={iso_env}，实际: {db}（硬编码 HOME 的退化）"
    # 反向断言：不得落在 HOME/.pangu 下（bug 版的确切位置）
    home_pangu = Path(os.environ["HOME"]) / ".pangu"
    assert not str(db).startswith(str(home_pangu)), f"DB 落进了 HOME/.pangu: {db}"


def test_db_path_moves_with_base_dir(monkeypatch, tmp_path, no_derived_path_isolation):
    """must-allow：改 PANGU_BASE_DIR，DB 路径必须跟着移动到新的 base_dir。

    这是"路径由 config 派生"的最强判据：硬编码 HOME 的实现**不会**随
    base_dir 移动，故该断言能把它钉死。
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    dir_a = tmp_path / "base_a"
    dir_b = tmp_path / "base_b"
    dir_a.mkdir(parents=True, exist_ok=True)
    dir_b.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PANGU_BASE_DIR", str(dir_a))
    monkeypatch.setenv("PANGU_DB_PATH", str(dir_a / "pangu.db"))
    db_a = Path(DomainKnowledge(PanguConfig.load()).db_path)

    monkeypatch.setenv("PANGU_BASE_DIR", str(dir_b))
    monkeypatch.setenv("PANGU_DB_PATH", str(dir_b / "pangu.db"))
    db_b = Path(DomainKnowledge(PanguConfig.load()).db_path)

    assert str(dir_a) in str(db_a), f"base_a 下应有 DB，实际: {db_a}"
    assert str(dir_b) in str(db_b), f"base_b 下应有 DB，实际: {db_b}"
    assert db_a != db_b, "DB 路径必须随 base_dir 变化（硬编码 HOME 则不变）"


def test_db_path_respects_custom_value(iso_env, tmp_path):
    """must-allow：显式设 domain_knowledge_db_path 后 DB 落在指定处。"""
    custom = tmp_path / "custom" / "knowledge.db"
    dk = _make(iso_env, db_path=custom)
    db = Path(dk.db_path)
    assert db == custom, f"DB 应落在 {custom}，实际: {db}"
    assert db.exists(), f"DB 文件应已创建: {db}"


def test_get_stats_no_nameerror(iso_env, tmp_path):
    """异常输入：get_stats() 必须真实可用，不再被 Counter NameError 吞。"""
    dk = _make(iso_env)
    # 若 Counter 未导入，此处应抛 NameError 而非静默
    stats = dk.get_stats()
    assert stats.total_entries > 0
    assert isinstance(stats.by_domain, dict)
    assert stats.avg_confidence >= 0
    assert isinstance(stats.top_tags, list)


def test_config_field_default_exists():
    """PanguConfig 应有 domain_knowledge_db_path 字段（默认派生自 base_dir）。"""
    cfg = PanguConfig()
    assert hasattr(cfg, "domain_knowledge_db_path")
    assert str(cfg.domain_knowledge_db_path).endswith("domain_knowledge.db")


def test_env_override_registered_in_load(monkeypatch, tmp_path):
    """config.load() 的 env 覆盖名单必须包含 domain_knowledge_db_path（F2-b 延伸）。

    验证方法：构造一份 config.json，里面显式写了生产绝对路径，再设对应 env，
    断言 load() 会摘掉该 key（交给 pydantic-settings 从 env 取值）。
    """
    # ⚠ 必须隔离 HOME：`PanguConfig.load()` 用
    # `os.path.expanduser("~/.pangu/config.json")` 定位配置文件，而
    # `expanduser` 读 `$HOME`。若不隔离，本测试会把 config.json 写进
    # **真实用户 HOME** —— 这正是 P0-0 记录的"测试写生产"事故模式。
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    data_dir = tmp_path / "pangu_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PANGU_BASE_DIR", str(data_dir))
    monkeypatch.setenv("PANGU_DB_PATH", str(data_dir / "pangu.db"))

    prod = tmp_path / "prod_place.db"
    env_db = tmp_path / "env_place.db"
    monkeypatch.setenv("PANGU_DOMAIN_KNOWLEDGE_DB_PATH", str(env_db))

    # 在**隔离的 HOME** 下构造 config.json，显式写一个"生产式"绝对路径，
    # 模拟真实失效场景（config.json 的显式值会压过 env —— F2 家族 bug）。
    cfg_json = {
        "base_dir": "/home/xiaoxin/.pangu",
        "db_path": "/home/xiaoxin/.pangu/pangu.db",
        "domain_knowledge_db_path": str(prod),
    }
    pangu_cfg_dir = fake_home / ".pangu"
    pangu_cfg_dir.mkdir(parents=True, exist_ok=True)
    (pangu_cfg_dir / "config.json").write_text(json.dumps(cfg_json))

    cfg = PanguConfig.load()
    # env 覆盖后，domain_knowledge_db_path 应等于 env 而非 config.json 值
    assert str(cfg.domain_knowledge_db_path) == str(env_db), (
        f"env 应压过 config.json，实际: {cfg.domain_knowledge_db_path}"
    )


def test_crud_end_to_end(iso_env, tmp_path):
    """端到端 CRUD：create→get→update→search→delete 全链路。"""
    from pangu.memory.domain_knowledge import (
        DomainType,
        KnowledgeCategory,
        KnowledgeEntry,
    )

    dk = _make(iso_env)
    entry = KnowledgeEntry(
        id="t_e2e_1",
        domain=DomainType("software_engineering"),
        category=KnowledgeCategory("design_pattern"),
        title="回归测试条目",
        content="pass3内容",
        tags=["p2-1", "test"],
        confidence=0.9,
        importance=0.7,
    )
    created = dk.create_entry(entry)
    assert created.id == "t_e2e_1"

    got = dk.get_entry("t_e2e_1")
    assert got is not None
    assert got.title == "回归测试条目"

    updated = dk.update_entry("t_e2e_1", importance=0.95)
    assert updated is not None
    assert updated.importance == 0.95

    hits = dk.search_by_keywords(["p2-1"])
    assert any(h.id == "t_e2e_1" for h in hits)

    ok = dk.delete_entry("t_e2e_1")
    assert ok is True
    assert dk.get_entry("t_e2e_1") is None
