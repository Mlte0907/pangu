# 盘古 v2.0 迭代路线图

> 核心原则：**接通已有 > 写新代码**。盘古已有大量高质量模块处于"存在但未充分利用"状态。

## Phase 1: 激活死代码 + 接通管道 (Week 1-2)

### 1.1 激活 neural_memory.py (761行死代码)
- 将 Hippocampus-Neocortex 双系统接入 `remember()` 和 `recall()` 管道
- 替代简单的 `ForgettingCurve`，用 `PersonalizedDecay` 做记忆衰减
- 用 `Amygdala` 做情感调制，替代硬编码的 emotional_valence
- 添加 MCP 工具：`pangu_neural_encode`, `pangu_neural_consolidate`
- 添加 CLI 命令：`pangu neural status`, `pangu neural consolidate`

### 1.2 激活 multi_agent.py (734行半死代码)
- 暴露 MCP 工具：`pangu_multi_add`, `pangu_multi_search`, `pangu_multi_sync`
- 接入 OpenClaw 的多 agent 体系 (羲和/玄女/轩辕)
- 实现 IMMEDIATE 同步策略，agent 写入时自动同步到共享池

### 1.3 激活 social_memory.py (347行半死代码)
- 暴露 MCP 工具：`pangu_vote`, `pangu_comment`, `pangu_rank`
- 接入 recall()，投票高分记忆优先召回

## Phase 2: 主动推送 + 自适应 (Week 3-4)

### 2.1 主动记忆推送
- 新增 `pangu/proactive/push_engine.py`
- 基于 working_memory 当前上下文，预加载相关记忆到 L0/L1 层
- 利用 event_bus 监听新记忆事件，自动触发关联推送
- 接口：`GET /api/v2/proactive/context` — 返回当前上下文相关记忆
- MCP 工具：`pangu_proactive_suggest`

### 2.2 记忆重要性自适应
- 增强 `adaptive_params.py`，接入 feedback 信号
- 召回成功 +1.0x, 召回失败 -0.5x, 投票 UP +0.3x, 投票 DOWN -0.2x
- 每次 recall() 后自动更新 importance
- 新增 `importance_feedback(drawer_id, signal)` 接口

## Phase 3: 冲突检测 + 验证 (Week 5-6)

### 3.1 冲突检测增强
- 增强 `conflict.py`，接入 enhanced_evaluation.py 的 LLM Judge
- 新增 `auto_resolve()` — 对 CRITICAL 以下冲突自动合并
- 接入 event_bus，新记忆写入时自动触发冲突检查
- MCP 工具：`pangu_conflict_auto_resolve`

### 3.2 记忆验证机制
- 新增 `pangu/memory/memory_validator.py`
- 基于 timeline.py 的时间推理，检测过时记忆
- 基于 KG 的实体一致性检查
- 新增 `memory_status` 字段：ACTIVE / STALE / CONFLICTED / VERIFIED
- 定期验证 cron，标记 STALE 记忆供 lifecycle 清理

## Phase 4: 融合抽象 + 压缩 (Week 7-8)

### 4.1 记忆融合自动化
- 增强 `fusion.py`，接入 clustering.py 的自动主题发现
- 每小时自动扫描：同主题 >3 条记忆 → 触发 fuse_topic()
- 融合结果写入新 Drawer，标记 `fused_from` 源 ID 列表
- lifecycle 每日自动执行一次全量融合

### 4.2 记忆压缩摘要
- 增强 `consolidation.py` 的压缩功能
- >30天 且 importance <0.3 的记忆 → 自动压缩为 50 字摘要
- >90天 的记忆 → 进一步压缩为一句话
- 压缩前备份到 `~/.pangu/archive/`

## Phase 5: 跨会话整合 + 检索优化 (Week 9-10)

### 5.1 跨会话记忆整合
- 新增 `pangu/memory/cross_session.py`
- 利用 session_hook 监听新会话结束事件
- 自动提取会话中的关键记忆，与历史记忆建立关联
- 接入 KG，构建跨会话实体关系链

### 5.2 检索算法优化
- 融合 FTS + Vector + KG 三路召回
- RRF (Reciprocal Rank Fusion) 合并排序
- 利用 attention.py 的策略选择，根据查询类型自动切换
- 新增 `hybrid_search()` 接口替代纯 FTS

## Phase 6: 持久化 + 生产化 (Week 11-12)

### 6.1 routes_tasks.py 持久化
- 内存 `_tasks` 迁移到 SQLite
- 复用 knowledge_graph.py 的 WAL 模式

### 6.2 MCP 工具整合
- 新增 15+ MCP 工具覆盖所有新功能
- 统一工具命名：`pangu_<module>_<action>`

### 6.3 测试补全
- neural_memory.py 单元测试 (新建)
- multi_agent.py MCP 集成测试
- social_memory.py 完整测试
- 新功能回归测试
