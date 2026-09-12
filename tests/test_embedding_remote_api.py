"""盘古 — 远程 Embedding API 分支可用性测试（v0.1.3 P0）

## 为什么需要这个文件

`EmbeddingService` 的第一级降级是远程 API（`_call_api` / `_call_api_batch`）。
修复前它用 `import aiohttp`，而 **aiohttp 从未被声明为依赖**：

    $ grep -rn aiohttp pyproject.toml requirements*.txt
    （无输出）
    $ .venv/bin/python -c "import aiohttp"
    ModuleNotFoundError: No module named 'aiohttp'

而这行 import 位于 `try/except Exception` 内部，于是后果是：

1. 用户配置 `PANGU_EMBED_API_URL` 后，**永远走不到** API 分支；
2. 每次都静默落到 ONNX（或更糟，hash）；
3. 只留下一条 `Embed API failed (1): No module named 'aiohttp'` 的
   WARNING，与"网络抖动"的日志长得几乎一样，极易被忽略。

即"远程 API 路由结构性不可达"。修复方式是改用**已声明的** `httpx`
（`pyproject.toml:25`；同仓库 `onnx_embedder.py:140` 也用它下载模型）。

## 测试策略

用**真实 HTTP 服务**（`http.server` 起在本地随机端口）而非 mock：
mock 会替换掉 `httpx.post` 本身，从而**永远发现不了 import 缺失**——
这正是这个 bug 能长期潜伏的原因。真服务 + 真 httpx 才能覆盖整条链路。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pangu.core.config import PanguConfig

EMBED_DIM = 384


class _EmbedAPIHandler(BaseHTTPRequestHandler):
    """最小 OpenAI 风格 /v1/embeddings 服务"""

    def do_POST(self):  # noqa: N802 (stdlib 命名)
        try:
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            inp = body.get("input")
            items = inp if isinstance(inp, list) else [inp]
            data = [{"embedding": [0.25] * EMBED_DIM, "index": i} for i in range(len(items))]
            payload = json.dumps({"data": data}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:  # pragma: no cover
            self.send_error(500)

    def log_message(self, *args):  # 静音
        pass


class _FailingHandler(BaseHTTPRequestHandler):
    """始终返回 500，用于验证错误处理与电路断路器"""

    def do_POST(self):  # noqa: N802
        self.send_error(500, "boom")

    def log_message(self, *args):
        pass


@pytest.fixture
def api_server():
    """起一个真实 HTTP 服务，返回其 URL"""
    server = HTTPServer(("127.0.0.1", 0), _EmbedAPIHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/v1/embeddings"
    server.shutdown()
    server.server_close()


@pytest.fixture
def failing_server():
    server = HTTPServer(("127.0.0.1", 0), _FailingHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/v1/embeddings"
    server.shutdown()
    server.server_close()


def _service(api_url: str):
    from pangu.memory.embedding import EmbeddingService

    cfg = PanguConfig()
    cfg.embed_api_url = api_url
    cfg.embedding_model = cfg.embedding_model or "test-model"
    return EmbeddingService(cfg)


class TestRemoteApiReachable:
    """核心：远程 API 分支必须真的能打通"""

    def test_call_api_returns_vector(self, api_server):
        """`_call_api` 必须返回真实向量，而非因缺依赖而 None

        修复前此断言失败：aiohttp 未安装 → 异常被吞 → 返回 None。
        """
        svc = _service(api_server)
        vec = svc._call_api("测试文本")
        assert vec is not None, (
            "_call_api 返回 None —— 远程 API 分支不可达。最常见原因：用了未声明的 HTTP 客户端库（如 aiohttp）。"
        )
        assert len(vec) == EMBED_DIM

    def test_call_api_batch_returns_vectors(self, api_server):
        """`_call_api_batch` 同理"""
        svc = _service(api_server)
        vecs = svc._call_api_batch(["一", "二", "三"])
        assert vecs is not None, "_call_api_batch 返回 None —— 批量 API 分支不可达"
        assert len(vecs) == 3
        assert all(len(v) == EMBED_DIM for v in vecs)

    def test_embed_uses_api_backend(self, api_server):
        """端到端：embed() 应报告 backend='api'"""
        svc = _service(api_server)
        vec = svc.embed("测试文本")
        assert vec is not None
        assert svc.active_backend == "api", f"应使用 api 后端，实际 {svc.active_backend} —— 说明静默降级到了本地"
        assert svc.is_degraded is False

    def test_no_httpx_import_fallback_needed(self, api_server):
        """确认走的不是 hash 兜底"""
        svc = _service(api_server)
        svc.embed("测试")
        assert svc.stats["active_backend"] == "api"


class TestRemoteApiFailureHandling:
    """API 失败路径仍需正确降级，不能因此崩溃"""

    def test_failure_falls_back_without_crash(self, failing_server):
        """API 返回 500 时应降级而非抛异常"""
        svc = _service(failing_server)
        vec = svc._call_api("测试")
        assert vec is None, "API 失败应返回 None（交给上层降级）"
        assert svc._fail_count == 1

    def test_embed_still_works_when_api_down(self, failing_server):
        """API 挂掉时 embed() 仍应产出向量（降级），不抛异常"""
        svc = _service(failing_server)
        vec = svc.embed("测试文本")
        assert vec is not None
        assert len(vec) == EMBED_DIM

    def test_circuit_opens_after_threshold(self, failing_server):
        """连续失败 5 次应打开电路断路器"""
        svc = _service(failing_server)
        for i in range(5):
            svc._call_api(f"失败-{i}")
        assert svc._fail_count >= 5
        assert svc._circuit_open is True


class TestNoUndeclaredDependency:
    """防止回退到未声明的依赖"""

    def test_embedding_module_does_not_import_aiohttp(self):
        """embedding.py 不得再 import aiohttp

        aiohttp 不在 pyproject.toml / requirements 中，用它等于让该分支
        在任何标准安装下必然失败。锁死这个约束。
        """
        import inspect

        import pangu.memory.embedding as mod

        src = inspect.getsource(mod)
        # 允许注释中提及（说明历史），但不允许真正的 import 语句
        code_lines = [ln.strip() for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
        offenders = [ln for ln in code_lines if "aiohttp" in ln]
        assert not offenders, f"embedding.py 仍在 import 未声明的 aiohttp: {offenders}"

    def test_httpx_is_declared_dependency(self):
        """httpx 必须是被正式声明的依赖（API 分支现在依赖它）"""
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        assert "httpx" in pyproject.read_text(encoding="utf-8"), (
            "httpx 未出现在 pyproject.toml —— 远程 API 分支会再次变成不可达"
        )
