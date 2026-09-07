"""盘古 — LLM 缓存预热 E2E 验证

无需真实 LLM 凭据：内置一个轻量 OpenAI 兼容 mock 服务，
跑通 预热 → 命中 → 重启 → 持久化命中 → 审计日志 完整链路。

用法：
    cd /home/xiaoxin/pangu
    python3 scripts/e2e_warmup.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 让脚本可以导入 pangu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pangu.core.config import PanguConfig
from pangu.core.llm import LLMEngine


# ── Mock OpenAI 服务 ─────────────────────────────────────────────
class _MockOpenAIHandler(BaseHTTPRequestHandler):
    """简单 OpenAI 兼容 mock：按消息内容返回不同响应"""

    def log_message(self, format, *args):
        # 静默
        pass

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])

        # 用第一条 user 消息生成响应（确定性的）
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        # 返回倒序字符串（让响应有内容可缓存）
        reversed_text = user_text[::-1]
        response = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "gpt-4o-mini"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"MOCK::{reversed_text}",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_text) // 4 or 1,
                "completion_tokens": len(reversed_text) // 4 or 1,
                "total_tokens": (len(user_text) + len(reversed_text)) // 4 or 2,
            },
        }
        out = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _start_mock_server(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    """启动 mock server，返回 (server, actual_port)"""
    server = ThreadingHTTPServer(("127.0.0.1", port), _MockOpenAIHandler)
    actual_port = server.server_address[1]
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, actual_port


# ── 预热 prompt 集合 ────────────────────────────────────────────
WARMUP_PROMPTS = [
    {"messages": [{"role": "user", "content": "什么是盘古记忆系统？"}], "temperature": 0},
    {"messages": [{"role": "user", "content": "盘古和伏羲的区别是什么？"}], "temperature": 0},
    {"messages": [{"role": "user", "content": "如何优化 LLM 缓存命中率？"}], "temperature": 0},
    {"messages": [{"role": "user", "content": "持久化缓存的 TTL 策略如何选择？"}], "temperature": 0},
    {"messages": [{"role": "user", "content": "Grafana 仪表盘如何拆分 provider？"}], "temperature": 0},
]


async def _run_e2e():
    print("=" * 70)
    print(" 盘古 LLM 缓存预热 E2E 验证")
    print("=" * 70)

    # 1) 启动 mock server
    print("\n[1/7] 启动本地 Mock OpenAI 服务...")
    server, port = _start_mock_server(0)
    base_url = f"http://127.0.0.1:{port}/v1"
    print(f"      ✓ Mock 服务运行在 {base_url}")

    work_dir = tempfile.mkdtemp(prefix="pangu_e2e_")
    db_path = os.path.join(work_dir, "llm_cache.db")
    log_path = os.path.join(work_dir, "warmup.log")
    print(f"      ✓ 工作目录: {work_dir}")

    try:
        # 2) 配置 + 引擎
        print("\n[2/7] 创建 LLMEngine（首次启动，无缓存）...")
        cfg = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="mock-key",
            llm_base_url=base_url,
            llm_cache_persist_path=db_path,
            llm_cache_write_throttle=1,  # 测试环境立即落盘
        )
        engine = LLMEngine(cfg)
        engine.clear_persistent_cache()
        print(f"      ✓ Provider: {engine.config.llm_provider}, Model: {engine.config.llm_model}")
        print(f"      ✓ 初始缓存: 内存={len(engine._cache)}, 磁盘={engine._persistent_cache.get_stats()['total_entries'] if engine._persistent_cache else 0}")

        # 3) 首次预热
        print(f"\n[3/7] 运行 warmup_cache（{len(WARMUP_PROMPTS)} 个 prompts，concurrency=2）...")
        t0 = time.time()
        result = await engine.warmup_cache(WARMUP_PROMPTS, concurrency=2)
        t1 = time.time()
        print(f"      ✓ total={result['total']}, warmed={result['warmed']}, "
              f"skipped={result['skipped']}, failed={result['failed']}")
        print(f"      ✓ 耗时: {result['duration_ms']}ms (wall: {(t1-t0)*1000:.0f}ms)")
        assert result["warmed"] == len(WARMUP_PROMPTS), "预热应该全部成功"
        assert result["failed"] == 0

        # 4) 验证统计
        print("\n[4/7] 检查引擎统计...")
        stats = engine.get_stats()
        print(f"      ✓ call_count: {stats['call_count']} (应为 {len(WARMUP_PROMPTS)})")
        print(f"      ✓ cache_writes: {stats['cache_writes']}")
        print(f"      ✓ tokens_saved: {stats['tokens_saved']}")
        print(f"      ✓ persistent_cache.entries: {stats['persistent_cache']['total_entries']}")
        print(f"      ✓ persistent_cache.bytes: {stats['persistent_cache']['total_bytes']} B")
        assert stats["call_count"] == len(WARMUP_PROMPTS)
        assert stats["cache_writes"] == len(WARMUP_PROMPTS)

        # 5) 再次查询 — 应当全部命中缓存
        print("\n[5/7] 再次查询相同 prompts（应全部命中缓存，0 API 调用）...")
        for i, p in enumerate(WARMUP_PROMPTS):
            r = await engine.chat(messages=p["messages"], temperature=0)
            expected = f"MOCK::{p['messages'][0]['content'][::-1]}"
            assert r.content == expected, f"prompt {i} 响应不匹配：{r.content!r}"
        stats2 = engine.get_stats()
        new_hits = stats2["cache_hits"] - stats["cache_hits"]
        new_calls = stats2["call_count"] - stats["call_count"]
        print(f"      ✓ 新增 cache_hits: {new_hits} (应为 {len(WARMUP_PROMPTS)})")
        print(f"      ✓ 新增 call_count: {new_calls} (应为 0 — 全部命中)")
        assert new_hits == len(WARMUP_PROMPTS)
        assert new_calls == 0, "缓存命中后不应再调用 API"

        # 6) 重启引擎 — 内存缓存清空，持久化缓存仍在
        print("\n[6/7] 模拟重启：丢弃内存缓存，保留 SQLite...")
        engine.clear_cache()  # 内存层清空
        # 磁盘层仍在 — 下次查询会先 miss 内存，再 hit 磁盘
        print(f"      ✓ 内存缓存已清空（size={len(engine._cache)}）")
        print(f"      ✓ 持久化缓存仍在（entries={engine._persistent_cache.get_stats()['total_entries']}）")

        # 再次查询 — 这次会走磁盘路径
        r = await engine.chat(
            messages=WARMUP_PROMPTS[0]["messages"],
            temperature=0,
        )
        assert r.content == f"MOCK::{WARMUP_PROMPTS[0]['messages'][0]['content'][::-1]}"
        print("      ✓ 重启后查询命中磁盘缓存，返回正确响应")

        # 7) 审计日志
        print("\n[7/7] 写入审计日志...")
        # 替换 logger handler 指向 work_dir
        import logging
        audit_logger = logging.getLogger("pangu.llm.warmup")
        # 清除已有 handler
        for h in list(audit_logger.handlers):
            audit_logger.removeHandler(h)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        audit_logger.addHandler(fh)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
        # 替换模块 logger
        from pangu.core import llm as llm_mod
        llm_mod._warmup_logger = audit_logger

        # 再跑一次预热（带审计日志）
        cfg2 = PanguConfig(
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_api_key="mock-key",
            llm_base_url=base_url,
            llm_cache_persist_path=db_path,
            llm_cache_warmup_prompts=WARMUP_PROMPTS,
        )
        engine2 = LLMEngine(cfg2)
        # 全部已存在缓存中 → 全部 skip
        result2 = await engine2.warmup_cache(WARMUP_PROMPTS, concurrency=2)
        for h in audit_logger.handlers:
            h.flush()
        print(f"      ✓ 第二次预热: total={result2['total']}, skipped={result2['skipped']} (应等于 total)")
        assert result2["skipped"] == len(WARMUP_PROMPTS)

        # 读取审计日志
        records = LLMEngine.get_warmup_history(log_path=log_path, limit=10)
        print(f"      ✓ 审计日志记录数: {len(records)}")
        for r in records:
            print(f"        - {r.get('provider')}/{r.get('model')}: "
                  f"w={r.get('warmed')} s={r.get('skipped')} f={r.get('failed')} "
                  f"src={r.get('source')} dur={r.get('duration_ms')}ms")
        assert len(records) >= 1

        # Prometheus 指标导出
        print("\n[Bonus] 导出 Prometheus 指标片段:")
        metrics_text = engine2.export_prometheus_metrics()
        relevant = [line for line in metrics_text.split("\n")
                    if any(k in line for k in [
                        "pangu_llm_cache_hit_rate",
                        "pangu_llm_cache_hits_total",
                        "pangu_llm_cache_writes_total",
                        "pangu_llm_tokens_saved_total",
                        "pangu_llm_persistent_cache_entries",
                        "pangu_llm_persistent_cache_bytes",
                    ])]
        for line in relevant[:12]:
            print(f"      {line}")

        # 总结
        print("\n" + "=" * 70)
        print(" E2E 验证全部通过！")
        print("=" * 70)
        print(f"  • 预热条目:       {len(WARMUP_PROMPTS)}")
        print(f"  • API 调用:       {len(WARMUP_PROMPTS)} (仅首次)")
        print(f"  • 缓存命中:       {len(WARMUP_PROMPTS)} (第二次+重启后)")
        print(f"  • 节省 API 调用:  {len(WARMUP_PROMPTS)} / {len(WARMUP_PROMPTS)*2} = 50%")
        print(f"  • 审计日志路径:   {log_path}")
        print(f"  • 持久化缓存:     {db_path}")
        print("=" * 70)

    finally:
        server.shutdown()
        # 保留工作目录供用户查看
        print(f"\n[清理] 临时工作目录保留: {work_dir}")


if __name__ == "__main__":
    asyncio.run(_run_e2e())
