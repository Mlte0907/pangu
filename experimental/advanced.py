"""实验工具实现 — 自 pangu/server/handlers/advanced.py 迁入

本模块包含实验性功能工具的实现，默认不加载。
"""

from __future__ import annotations

# ── 实验工具定义（按前缀分组）──

# cognitive 组
COGNITIVE_TOOLS = [
    {"name": "pangu_cognitive_loop", "description": "运行一次认知循环（observe→think→evaluate→act）"},
    {"name": "pangu_cognitive_stats", "description": "获取认知循环统计"},
]

# worldmodel 组
WORLDMODEL_TOOLS = [
    {"name": "pangu_worldmodel_forecast", "description": "基于当前状态预测未来情景"},
    {"name": "pangu_worldmodel_plan", "description": "为指定情景生成应对计划"},
    {"name": "pangu_worldmodel_match", "description": "将事件与预测情景匹配"},
    {"name": "pangu_worldmodel_stats", "description": "获取世界模型统计"},
]

# autonomous 组
AUTONOMOUS_TOOLS = [
    {"name": "pangu_autonomous_analyze", "description": "分析任务复杂度并推荐能力"},
    {"name": "pangu_autonomous_tick", "description": "检查是否需要运行自主维护周期"},
    {"name": "pangu_autonomous_run", "description": "运行一次自主记忆管理周期（融合/压缩/衰减/遗忘/探索）"},
    {"name": "pangu_autonomous_status", "description": "查看自主引擎状态和任务调度"},
]

# neural 组
NEURAL_TOOLS = [
    {"name": "pangu_neural_stats", "description": "获取海马体-新皮层双系统统计"},
    {"name": "pangu_neural_sleep", "description": "触发神经睡眠固化（海马体→新皮层重播）"},
    {"name": "pangu_neural_spreading", "description": "基于种子记忆执行扩散激活，找到关联记忆"},
    {"name": "pangu_neural_inhibition", "description": "对一组记忆执行竞争抑制，返回有效激活值"},
    {"name": "pangu_neural_decay", "description": "对所有记忆应用个性化衰减"},
]

# dream 组
DREAM_TOOLS = [
    {"name": "pangu_dream_cycle", "description": "运行一次梦境固化周期（fetch→dedup→link→decay→distill）"},
    {"name": "pangu_dream_stats", "description": "获取梦境固化统计"},
]

# evolution 组
EVOLUTION_TOOLS = [
    {"name": "pangu_evolution_plan", "description": "生成进化计划"},
    {"name": "pangu_evolution_stats", "description": "获取进化统计"},
]

# meta 组
META_TOOLS = [
    {"name": "pangu_metacognition_monitor", "description": "系统级健康监测（策略表现、观察数据、建议）"},
    {"name": "pangu_metacognition_reconfig", "description": "自重构检测（低效策略、未使用策略、异常模块）"},
    {"name": "pangu_meta_observe", "description": "记录性能观察"},
    {"name": "pangu_meta_recommend", "description": "推荐最优策略"},
    {"name": "pangu_meta_tune", "description": "自动调优参数"},
    {"name": "pangu_meta_insights", "description": "获取学习洞察"},
    {"name": "pangu_meta_stats", "description": "元学习统计"},
]

# self_aware 组
SELF_AWARE_TOOLS = [
    {"name": "pangu_persona_identity", "description": "获取系统身份和人格特质"},
    {"name": "pangu_persona_values", "description": "获取系统价值观和原则"},
    {"name": "pangu_persona_health", "description": "系统综合健康度检查"},
]

# causal 组
CAUSAL_TOOLS = [
    {"name": "pangu_find_causal_links", "description": "发现记忆间的因果关联"},
]

# autopilot 组
AUTOPILOT_TOOLS = [
    {"name": "pangu_autopilot_status", "description": "获取自动驾驶状态"},
    {"name": "pangu_autopilot_enable", "description": "启用自动驾驶"},
    {"name": "pangu_autopilot_disable", "description": "禁用自动驾驶"},
]

# ── 合并 TOOLS 和 HANDLERS ──

TOOLS = (
    COGNITIVE_TOOLS
    + WORLDMODEL_TOOLS
    + AUTONOMOUS_TOOLS
    + NEURAL_TOOLS
    + DREAM_TOOLS
    + EVOLUTION_TOOLS
    + META_TOOLS
    + SELF_AWARE_TOOLS
    + CAUSAL_TOOLS
    + AUTOPILOT_TOOLS
)

HANDLERS: dict[str, callable] = {}