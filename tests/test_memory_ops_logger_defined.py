"""回归测试：memory_ops 的 `logger` 必须真实存在（2026-10-12 线上故障）。

## 故障现象

线上（云端 113.45.134.86）`pangu_add_memory` 间歇性返回：

    {"code": 5000, "error": "name 'logger' is not defined"}

`memory_ops.py` 在三处直接调用 `logger.`，却从未 `import logging`、也从未定义
`logger`。全仓扫描确认这是**唯一**一处「用了没定义」。

## 两条互相独立的失败路径（都要防回归）

路径① 钳制告警 —— 需要 `classification > clearance`：

    requested = _coerce_classification(arguments.get("classification", 0))
    granted = clamp_classification(requested)
    if granted != requested:
        logger.warning(...)      # ← NameError，整个 handler 抛出

路径② 记忆进化日志 —— **与 classification 完全无关**，只要 `should_replace`
判定新记忆该替换旧记忆就必炸：

    replaced_count += 1
    logger.info(...)             # ← NameError，被同层 except 接住
    ...
    except Exception as e:
        logger.debug(...)        # ← 二次 NameError 逃出 except → 逃出函数

路径② 才是「同样内容，改短就成功」的真正原因：长文 / 高信息密度的新记忆
质量分更容易超过旧记忆的 1.1 倍而触发替换，与密级无关。报告最初归因为
「线上代码比本地镜像新」，此处用测试钉死真实成因。

## 为什么用 AST 而不是 grep

grep `logger.` 只能看到「用了」，看不到「定义在哪」。本测试解析模块 AST，
收集全部绑定名（import / def / class / 赋值 / 参数 / except-as / 推导式变量），
再找**裸用**（无接收者）的 `logger.`。这样即使日后有人把 `logger.warning`
改成别的名字或挪进别的模块，测试仍能报出真实的未定义名。

此外单独验证路径② 的语义：except 体内抛出的异常不会被同一个 except 捕获，
所以「接住了异常」并不等于「写入了成功」——这正是线上 6 条悬空
`replaced_by` 引用的成因（旧记忆已被 update_drawer 升版，新记忆却从未落盘）。
"""

import ast
import builtins
import inspect
from pathlib import Path

import pytest


def _module_path() -> Path:
    from pangu.server.handlers import memory_ops

    return Path(inspect.getfile(memory_ops))


def _collect_bound_names(tree: ast.Module) -> set:
    """收集模块内所有被绑定的名字（= 可能作为全局解析的名字）。"""
    names: set = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
    return names


def test_logger_is_defined_at_module_level():
    """模块级必须存在 `logger = ...`，而不是只有局部 import。"""
    source = _module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)
    bound = _collect_bound_names(tree)

    assert "logger" in bound, (
        "memory_ops 用了 logger. 却没有模块级定义 —— 这就是线上 code 5000 的成因。"
        "需要在文件顶部补 `import logging` + `logger = logging.getLogger(__name__)`。"
    )

    # 确认确实是 logging 拿的，而不是随手 `logger = None` 之类
    assert "logging.getLogger" in source, "logger 应由 logging.getLogger 提供，才能真的输出日志"


def test_no_undefined_bare_names_anywhere_in_module():
    """全模块不得存在任何「裸用但未绑定」的名字（不只 logger）。"""
    source = _module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)
    bound = _collect_bound_names(tree)

    used: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.setdefault(node.id, []).append(node.lineno)

    undefined = {
        name: lines
        for name, lines in used.items()
        if name not in bound and not name.startswith("_")
    }
    assert not undefined, f"memory_ops 存在未定义的全局名: {undefined}"


def test_clamp_warning_branch_does_not_raise_nameerror():
    """路径①：classification 被钳制时，写入不得因 NameError 失败。

    直接执行 handler 里那一段等价代码，用真实 clamp/current_clearance，
    断言不抛 NameError —— 旧代码在这里必然抛。
    """
    from pangu.memory.layers import _coerce_classification, clamp_classification

    requested = _coerce_classification(3)
    granted = clamp_classification(requested)
    # 复刻 memory_ops.py 的钳制告警写法（含 logger. 调用）
    if granted != requested:
        from pangu.server.handlers import memory_ops

        memory_ops.logger.warning(
            f"密级 {requested} 超过调用方 clearance 0，已钳制为 {granted}"
        )


def test_except_body_exception_is_not_caught_by_same_handler():
    """路径② 的语义前提：except 体内抛异常会逃出函数（故旧代码整条写入丢失）。

    这条不是测盘古代码，而是把「为什么接住了异常仍然写入失败」钉成可执行事实，
    防止日后有人误以为 try/except 已经兜住了。
    """

    def outer():
        try:
            raise ValueError("原始异常")
        except Exception:
            undefined_logger.debug("兜底日志")  # noqa: F821 —— 复刻旧代码的 except 体

    with pytest.raises(NameError):
        outer()


def test_import_memory_ops_does_not_emit_nameerror_at_call_time():
    """导入即绑定 logger（getLogger 是惰性的，但名字必须在）。"""
    from pangu.server.handlers import memory_ops

    assert hasattr(memory_ops, "logger"), "memory_ops.logger 不存在"
    assert memory_ops.logger.name == "pangu.server.handlers.memory_ops"