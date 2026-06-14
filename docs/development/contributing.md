# 贡献规范

## 工作流

1. **fork** → 创建分支 `feature/<short-desc>` 或 `fix/<issue-num>`
2. **写代码 + 测试**（新功能必须有测试）
3. **`pytest`**：必须全过；新增/修改部分 ≥ 90% 覆盖
4. **`ruff check`**：必须 0 warning
5. **`bandit`**：必须无 NEW HIGH
6. **commit** 风格见下
7. **push** + **PR** + 触发 CI
8. **Code Review**：至少 1 人 LGTM
9. **Squash merge** → 自动发版本

## Commit 规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

type：
- `feat` 新功能
- `fix` 修 bug
- `refactor` 重构（无功能变化）
- `perf` 性能
- `test` 测试
- `docs` 文档
- `chore` 构建 / 工具
- `security` 安全修复

scope：`memory` / `core` / `api` / `cli` / `kg` / `wiki` / `mcp` ...

subject：50 字符内，祈使句，无句号

示例：
```
fix(embedding): correct config field name to embed_api_url

embedding.py:209,251 referenced self.config.embedding_api_url but
the actual PanguConfig field is embed_api_url. Caused runtime
AttributeError when external embed API was configured.

Fixes #123
```

## PR 规范

- 标题：`<type>: <subject>`，与首个 commit 对齐
- 描述：What + Why + How + 测试
- 链接相关 Issue：`Closes #N` / `Refs #N`
- 截图（如涉及 UI）
- 破坏性变更：必须标注 ⚠️ BREAKING 并写 `docs/BREAKING.md`

## Code Review 要点

- [ ] 命名清晰
- [ ] 无 hardcoded 密钥
- [ ] 错误处理不吞异常
- [ ] 性能影响（关键路径 > 5% 标 ⚠️）
- [ ] 公共 API 类型 hint 完整
- [ ] docstring 覆盖主要入口
- [ ] 测试覆盖关键分支

## 风格

- Python 3.10+ 语法
- 行宽 100
- import 分组：标准库 / 第三方 / 本地
- 类型 hint 优先
- 中文 docstring 优先
- 函数尽量 < 50 行

## 提交前自检

```bash
# 格式化
ruff check --fix .

# 静态分析
bandit -r pangu -ll

# 测试
pytest tests/ -q

# 完整回归
python tests/run_full_regression.py
```

## 发布

- 维护者用 `release.yml` workflow
- 自动生成 draft release notes
- 打 tag 后自动 push 到 PyPI + Docker Hub
