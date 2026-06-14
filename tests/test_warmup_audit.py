"""盘古 — 缓存预热审计日志测试"""

import json
import os

import pytest

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine


class TestWarmupAuditLog:
    """预热审计日志"""

    @pytest.mark.asyncio
    async def test_warmup_writes_audit_log(self, tmp_path, monkeypatch):
        """warmup_cache 写入审计日志"""
        # 用临时 log 路径替换
        from pangu.core import llm as llm_mod

        class _FakeLogPath:
            def __init__(self, p):
                self.p = p

        # 重新初始化 logger handler 指向 tmp_path
        log_file = str(tmp_path / "warmup_audit.log")
        # 直接构造一个独立 logger
        import logging
        test_logger = logging.getLogger("pangu.llm.warmup.test")
        test_logger.handlers.clear()
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        test_logger.addHandler(fh)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False

        # Monkey-patch the warmup logger
        monkeypatch.setattr(llm_mod, "_warmup_logger", test_logger)

        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="test",
            llm_base_url="https://api.test.com/v1",
            llm_cache_persist_path=str(tmp_path / "audit.db"),
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()

        # 预热一个空列表 — 不会写日志（无意义事件）
        await engine.warmup_cache([])

        # 写入内容：手动调用 _log_warmup
        engine._log_warmup({"total": 3, "warmed": 3, "skipped": 0, "failed": 0, "duration_ms": 12.5, "source": "manual"})
        # flush handler
        for h in test_logger.handlers:
            h.flush()

        # 验证日志已写入
        assert os.path.exists(log_file)
        with open(log_file, encoding="utf-8") as f:
            content = f.read()
        assert "llm_cache_warmup" in content
        # 提取 JSON 部分
        json_start = content.find("{")
        rec = json.loads(content[json_start:])
        assert rec["total"] == 3
        assert rec["warmed"] == 3
        assert rec["source"] == "manual"
        assert rec["provider"] == "openai"
        assert rec["model"] == "gpt-4o-mini"

    def test_get_warmup_history_empty(self, tmp_path):
        """无日志文件时返回空列表"""
        # 使用不存在的路径
        records = LLMEngine.get_warmup_history(
            log_path=str(tmp_path / "nonexistent.log"), limit=10
        )
        assert records == []

    def test_get_warmup_history_parses(self, tmp_path):
        """正确解析日志条目"""
        log_file = tmp_path / "history.log"
        # 写入两条模拟日志
        entries = [
            {"ts": 1000.0, "event": "llm_cache_warmup", "total": 2, "warmed": 2, "skipped": 0, "failed": 0, "duration_ms": 5.0, "source": "auto", "provider": "openai", "model": "gpt-4o"},
            {"ts": 2000.0, "event": "llm_cache_warmup", "total": 1, "warmed": 0, "skipped": 1, "failed": 0, "duration_ms": 1.0, "source": "manual", "provider": "zhipu", "model": "glm-4"},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"2026-06-08 12:00:00,000 {json.dumps(e)}\n")

        records = LLMEngine.get_warmup_history(log_path=str(log_file), limit=10)
        # 倒序
        assert len(records) == 2
        assert records[0]["ts"] == 2000.0
        assert records[0]["provider"] == "zhipu"
        assert records[1]["ts"] == 1000.0
        assert records[1]["source"] == "auto"

    def test_get_warmup_history_respects_limit(self, tmp_path):
        """limit 参数生效"""
        log_file = tmp_path / "history.log"
        with open(log_file, "w", encoding="utf-8") as f:
            for i in range(5):
                f.write(f"2026-06-08 {json.dumps({'ts': float(i), 'event': 'llm_cache_warmup', 'warmed': i, 'provider': 'p', 'model': 'm'})}\n")
        records = LLMEngine.get_warmup_history(log_path=str(log_file), limit=3)
        assert len(records) == 3
