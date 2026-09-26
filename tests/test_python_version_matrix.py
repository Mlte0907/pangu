"""CI 的 Python 矩阵必须与 `pyproject.toml` 的声明一致，且覆盖开发实际使用的版本。

## 为什么要有这条测试

2026-09-26 实测发现的矛盾（三条都对不上）：

| 事实 | 值 |
| --- | --- |
| `pyproject.toml` 的 `requires-python` | `>=3.11` |
| `ci.yml` 门禁用的版本 | 3.12 |
| `test.yml` 矩阵 | 3.10, 3.11, 3.12 |
| **云端实际部署的版本** | **3.11.2** |
| **本地开发/验证用的版本** | **3.13.5** |

两个真问题：

1. **矩阵里有 3.10，低于声明的 `>=3.11`** —— 在测一个项目官方不声称支持的版本。
   要么声明错了，要么矩阵错了，二者必须有一个改。
2. **3.13 根本不在任何 CI job 里** —— 而 3.13 恰恰是日常开发（包括 agent）实际
   跑测试的版本。于是「本地全绿」这件事，CI 从来没验证过那个版本能不能跑。
   缺口的方向和大多数人以为的**正好相反**：不是「CI 没测生产版本」
   （3.11 一直在被测），而是「CI 没测开发版本」（3.13）。

这类不一致的的特点是**没有任何症状**：CI 照样绿，PR 照样合，
只是某天有人用 3.13 才能跑的语法提交，线上（3.11）直接崩，而 CI 一路放行。
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
TEST_YML = ROOT / ".github" / "workflows" / "test.yml"

# 云端 /root/pangu 的 .venv 实测值（2026-09-26）。改了要同步这里，也同步说明书 §15。
CLOUD_PYTHON = (3, 11)


def _declared_min() -> tuple[int, int]:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text)
    assert m, "pyproject.toml 里找不到 requires-python —— 矩阵一致性无从校验"
    return int(m.group(1)), int(m.group(2))


def _matrix() -> list[tuple[int, int]]:
    text = TEST_YML.read_text(encoding="utf-8")
    m = re.search(r"python-version:\s*\[(.*?)\]", text, re.S)
    assert m, "test.yml 里找不到 python-version 矩阵"
    out = []
    for raw in re.findall(r'"(\d+)\.(\d+)"', m.group(1)):
        out.append((int(raw[0]), int(raw[1])))
    assert out, "矩阵解析为空"
    return out


def test_matrix_has_no_version_below_declared_minimum():
    """矩阵里不能有低于 `requires-python` 的版本。

    测一个官方不声称支持的版本，得到的绿灯**没有意义**：它可能只是碰巧过，
    也可能掩盖了真实的兼容性问题。声明与矩阵必须一致。
    """
    lo = _declared_min()
    offenders = [v for v in _matrix() if v < lo]
    assert not offenders, (
        f"test.yml 矩阵里有低于 requires-python (>={lo[0]}.{lo[1]}) 的版本 {offenders}。"
        f"要么把声明改宽，要么把矩阵收窄 —— 二者必须一致。"
    )


def test_matrix_covers_the_version_running_in_production():
    """**矩阵必须包含云端实际部署的 Python 版本。**

    这是最容易漏的一条：CI 测 3.10/3.12/3.13 看着很全，但线上跑 3.11，
    那条路径就没人守。声明的最低支持版本 = 生产最可能用的版本，必须在矩阵里。
    """
    assert CLOUD_PYTHON in _matrix(), (
        f"云端实际跑 Python {CLOUD_PYTHON[0]}.{CLOUD_PYTHON[1]}，"
        f"但它不在 test.yml 矩阵 {_matrix()} 里 —— 线上那条路径没有 CI 守着"
    )


def test_matrix_covers_the_version_used_for_local_development():
    """**矩阵必须包含本地开发实际使用的版本。**

    2026-09-26 之前的缺口就是这个方向：本地在 3.13 上跑测试（本地全绿），
    而 3.13 不在任何 CI job 里 —— 于是「本地绿」这件事从未被 CI 验证过。
    """
    local = (3, 13)
    assert local in _matrix(), (
        f"本地开发用 Python {local[0]}.{local[1]}，但它不在 test.yml 矩阵 {_matrix()} 里。"
        f"日常验证跑在一个 CI 从不测试的版本上。"
    )


def test_ci_default_version_is_in_the_matrix():
    """ci.yml 门禁用的版本应该在 test.yml 矩阵里，否则门禁和矩阵各测各的。"""
    text = CI.read_text(encoding="utf-8")
    m = re.search(r'PYTHON_DEFAULT:\s*"(\d+)\.(\d+)"', text)
    assert m, "ci.yml 里找不到 PYTHON_DEFAULT"
    default = (int(m.group(1)), int(m.group(2)))
    assert default in _matrix(), (
        f"ci.yml 门禁用 {default}，但它不在 test.yml 矩阵 {_matrix()} 里"
    )


@pytest.mark.parametrize("ver", [(3, 11), (3, 13)])
def test_no_version_specific_syntax_in_code(ver):
    """占位：确认 3.11 与 3.13 都不需要 3.12+ 独占语法。

    真正的检查在 `_scan_pep695.py` 这类工具里；这里只钉住一条最常见的
    3.12 新语法 —— PEP 695 的 `type X = ...` 别名。出现过就说明
    **低于该版本的部署会直接 SyntaxError**，而这类错误在矩阵缺位时是静默的。
    """
    if ver < (3, 12):
        pytest.skip("3.12+ 才有的语法，与低版本无关")
    hits = []
    for p in (ROOT / "pangu").rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.match(r"^\s*type\s+\w+\s*=", line):
                hits.append(f"{p.relative_to(ROOT)}:{i}")
    assert not hits, (
        f"发现 PEP 695 `type X = ...` 别名（3.12+ 语法）{hits[:5]}；"
        f"生产是 Python {CLOUD_PYTHON[0]}.{CLOUD_PYTHON[1]}，会直接 SyntaxError"
    )
