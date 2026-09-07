# CLI 工具

`pangu-cli` 是基于 `typer` 的命令行入口，覆盖运维与调试场景。

## 顶层命令

```bash
pangu-cli --help
```

子命令分组：
- `memory` — 记忆 CRUD
- `wiki` — Wiki 引擎
- `kg` — 知识图谱
- `cache` — 缓存管理
- `backup` — 备份 / 恢复
- `system` — 系统管理

## memory 子命令

```bash
# 写入
pangu-cli memory add "用户在 2026-06-08 询问过盘古" --importance 4 --tags interaction

# 列出
pangu-cli memory list --limit 20 --tag interaction

# 检索
pangu-cli memory search "询问" --top-k 5 --mode hybrid

# 详情
pangu-cli memory get d_2026-06-08_a1b2c3

# 更新
pangu-cli memory update d_... --importance 4.5

# 删除
pangu-cli memory delete d_...

# 统计
pangu-cli memory stats
```

## wiki 子命令

```bash
pangu-cli wiki write --title "盘古架构" --file arch.md
pangu-cli wiki read <page-id>
pangu-cli wiki search "4 层"
pangu-cli wiki list
```

## kg 子命令

```bash
pangu-cli kg add-relation --subject 盘古 --predicate causes --object "知识结晶"
pangu-cli kg query --entity 盘古 --depth 2
pangu-cli kg export --file kg.jsonl
```

## cache 子命令

```bash
# 状态
pangu-cli cache status

# 清空
pangu-cli cache clear --all

# 预热（从 prompt 文件）
pangu-cli cache warmup --file warmup.yaml

# 统计
pangu-cli cache stats
```

## backup 子命令

```bash
# 导出
pangu-cli backup export --output /backup/pangu-2026-06-08.tar.gz

# 导入
pangu-cli backup import --input /backup/pangu-2026-06-08.tar.gz

# 列出
pangu-cli backup list

# 恢复指定版本
pangu-cli backup restore pangu-2026-06-07
```

## system 子命令

```bash
# 健康
pangu-cli system health

# 性能
pangu-cli system perf --duration 30

# 关闭
pangu-cli system shutdown
```

## 全局选项

- `--config <path>` 指定配置文件
- `--data-dir <path>` 数据目录
- `--json` JSON 输出
- `--quiet` 静默
- `--verbose` 详细日志

## 环境变量

CLI 与服务端共享 `PANGU_*` 配置；如 `PANGU_API_KEY` 在调用 HTTP 端点时使用。

## 退出码

- `0` 成功
- `1` 业务错误
- `2` 参数错误
- `3` 网络错误
- `4` 鉴权失败
- `5` 内部错误
