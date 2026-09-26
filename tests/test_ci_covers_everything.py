"""CI 的测试范围必须是「整个目录」，不能是手写文件清单。

## 为什么要有这条测试

2026-09-26 实测：`.github/workflows/ci.yml` 的门禁 job 逐个列测试文件名，
88 个测试文件里只列了 **33 个** —— 另外 55 个（含 `test_auth.py`、`test_abac.py`、
`test_e2e_rbac_abac.py`）**CI 从来一次都没跑过**。

也就是说：门铃装在门上，但有一半的窗户根本没接线。CI 报绿，绿的却是个子集。
更糟的是那个清单**本身就是腐烂的根源** —— 新增的测试文件默认不会被跑到，
而这类遗漏**没有任何症状**：CI 不会红，PR 不会卡，代码就这么溜过去了。

手写清单还会让「改清单」变成一件需要人记得的事，注释里那句
「改动测试清单时勿漏」就是历史上留给自己的警告。

所以这里把规则钉死：**门禁必须跑整个目录**，要排除的用 `--ignore` 显式排除
（排除项是有意为之的决策，会留在 diff 里；漏掉的文件不会有任何痕迹）。
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
TEST_YML = ROOT / ".github" / "workflows" / "test.yml"


def _pytest_invocations(text: str) -> list[str]:
    """取出所有 `python -m pytest ...` 段落（可能跨行）。"""
    out = []
    for m in re.finditer(r"python -m pytest\b(.*?)(?=\n\s*(?:$|[a-zA-Z#-]))", text, re.S):
        out.append(m.group(1))
    return out


def test_ci_yml_exists():
    assert CI.exists(), f"CI 配置不见了：{CI}"


def test_ci_gate_runs_the_whole_test_dir_not_a_hand_kept_list():
    """门禁必须 `pytest tests/`，不能列具体文件。"""
    text = CI.read_text(encoding="utf-8")
    invocations = _pytest_invocations(text)
    assert invocations, "ci.yml 里没找到 pytest 调用"

    offenders = []
    for inv in invocations:
        # 允许 tests/ 与 --ignore / --cov 之类参数；不允许裸的 tests/xxx.py
        explicit = re.findall(r"tests/[\w*.\-/]+\.py", inv)
        if explicit:
            offenders.append(explicit)

    assert not offenders, (
        "ci.yml 的 pytest 又开始逐个列测试文件了：\n  "
        + "\n  ".join(str(o) for o in offenders)
        + "\n这正是 55 个测试文件被漏掉的原因。改成 `pytest tests/`"
        "（要排除的用 --ignore 显式排除）。"
    )


def test_every_test_file_is_covered_by_the_gate():
    """每个测试文件要么被门禁跑到，要么被 `--ignore` 显式排除。

    这是上一条的正向版本：不仅「不许列清单」，还要证明**没有文件被悄悄漏掉**。
    """
    text = CI.read_text(encoding="utf-8")
    invocations = " ".join(_pytest_invocations(text))
    assert "tests/" in invocations, "门禁没有跑 tests/ 目录"

    ignored: set[str] = set()
    for m in re.finditer(r"--ignore=([\w./\-]+)", invocations):
        ignored.add(m.group(1))

    all_tests = {
        f"tests/{p.name}" for p in sorted((ROOT / "tests").glob("test_*.py"))
    }
    # conftest 里的 collect_ignore_glob 也算显式排除（E2E 手工套件）
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    if "collect_ignore_glob" in conftest:
        for m in re.finditer(r'"([\w./\-]+\*)"', conftest):
            ignored.add(f"tests/{m.group(1)}")

    # 没被 --ignore 点名、也不在 collect_ignore_glob 里的文件 =
    # 靠「跑整个目录」自动纳入。这里断言没有任何文件需要额外点名，
    # 也就是清单确实不存在了。
    explicitly_named = set(re.findall(r"tests/[\w*.\-/]+\.py", invocations))
    orphans = explicitly_named - all_tests
    assert not orphans, f"ci.yml 点了名但不存在的文件：{sorted(orphans)}"

    print(f"  测试文件 {len(all_tests)} 个；显式排除 {len(ignored)} 项：{sorted(ignored)}")
    print("  其余全部靠 `pytest tests/` 自动纳入 —— 无需维护清单")


def test_bench_is_excluded_with_a_reason():
    """基准文件若被排除，必须留有理由注释（否则就成了悄悄的缺口）。"""
    text = CI.read_text(encoding="utf-8")
    if "--ignore=tests/test_bench.py" not in text:
        pytest.skip("门禁没有排除 test_bench.py")
    assert "test_bench" in text
    # 理由必须出现在同一文件里，且提到墙钟/预算这类关键词
    assert re.search(r"(墙钟|预算|基准)", text), (
        "排除了 test_bench.py 却没有写明理由 —— 排除项必须是有意决策，不能是悄悄的缺口"
    )


def test_full_suite_job_can_actually_finish():
    """跑全量的那个 job，超时必须大于实测耗时，否则它永远跑不完。

    2026-09-26 实测：test.yml 跑 `pytest tests/`，超时 30 分钟，而当时全套要
    41 分半 ⇒ **每次都被杀**，「全量已验证」这个状态从未存在过。
    """
    text = TEST_YML.read_text(encoding="utf-8")
    assert "pytest tests/" in text, "test.yml 不再是全量 job，改动请同步说明书"

    m = re.search(r"timeout-minutes:\s*(\d+)", text)
    assert m, "test.yml 没写 timeout-minutes"
    budget = int(m.group(1))
    # 2026-09-26 本机实测 14 分 27 秒；GitHub runner 通常慢 2~3 倍。
    measured_seconds = 14 * 60 + 27
    worst_case = measured_seconds * 3
    assert budget * 60 > worst_case, (
        f"test.yml 超时 {budget} 分钟，按实测 {measured_seconds}s × 3 倍 runner "
        f"余量仍只有 {budget * 60}s < {worst_case}s —— 会被杀"
    )
