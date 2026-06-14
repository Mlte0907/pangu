# 测试指南

## 测试层级

| 层级 | 工具 | 范围 | 时长 |
|:---|:---|:---|:---|
| 单元 | `pytest` | 模块内部 | < 1s / test |
| 集成 | `pytest` | 模块间 + 临时 SQLite | < 5s / file |
| 接口 | `manual_api_smoke.py` | REST/MCP/CLI 黑盒 | < 30s |
| 性能 | `manual_perf.py` | 嵌入 / 缓存 / 检索 | < 60s |
| 安全 | `manual_security.py` | secret / SAST / 越权 | < 10s |
| 回归 | `run_full_regression.py` | 全部 + 基线对比 | < 3 min |

## 跑测试

```bash
# 全部
.venv/bin/python tests/run_full_regression.py

# 只跑单元
.venv/bin/pytest tests/test_core.py -q

# 跳过网络依赖
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/pytest tests/test_onnx_embedder.py
```

## 写新测试

```python
# tests/test_<module>.py
import pytest
from pangu.<module> import <Class>


class TestXxx:
    def test_basic(self, tmp_path):
        """一句话描述：输入 → 期望"""
        # Arrange
        obj = Class()
        # Act
        result = obj.method(...)
        # Assert
        assert result == expected
```

### 约定

- 文件名 `test_<module>.py`
- 类名 `Test<Feature>` 或 `Test<Module>`
- 函数名 `test_<scenario>_<expected>`
- 一个断言聚焦一件事
- 临时文件用 `tmp_path` fixture

### 异步测试

```python
@pytest.mark.asyncio
async def test_async_method():
    result = await obj.async_method()
    assert result is not None
```

## 性能基线

`tests/manual_perf.py` 跑完会写 `reports/perf.json`。
脚本会与 `reports/perf_baseline.json` 对比；劣化 > 5% 标红。

```bash
# 首次：建立基线
python tests/manual_perf.py --update-baseline

# 后续：检测回归
python tests/run_full_regression.py
```

## 安全测试

```bash
# 一次性
python tests/manual_security.py

# 输出 reports/security.json
```

覆盖：secret 扫描、危险 API、SQL 注入、路径穿越、越权、auth bypass。

## 兼容性矩阵

| Python | linux/amd64 | linux/arm64 |
|:---:|:---:|:---:|
| 3.10 | ✅ | ⚠️ 部分 wheel 缺失 |
| 3.11 | ✅ | ✅ |
| 3.12 | ✅ | ✅ |

CI 矩阵覆盖全表。

## 调试技巧

```bash
# 跑到某 test 停下
pytest tests/test_x.py::test_y -x

# 详细输出
pytest tests/test_x.py -vvv -s

# 进入 pdb
pytest tests/test_x.py --pdb

# 计时
pytest tests/test_x.py --durations=10
```

## 覆盖率

```bash
pytest --cov=pangu --cov-report=html tests/
# 报告 htmlcov/index.html
```

目标：核心模块 ≥ 85%。
