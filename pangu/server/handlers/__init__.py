"""盘古 MCP Handler 路由

本模块聚合 17 个 handler 工具的 TOOLS 与 HANDLERS，并支持实验模块的动态加载。

实验模块加载：
- 默认不加载实验模块（enabled_experiments = {}）
- 服务启动时调用 load_experimental_tools(config) 按需加载
- 实验工具经暴露面过滤器的第三层暴露
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("pangu.handlers")

# ── 核心与可选模块（默认加载）──

TOOLS: list[dict[str, Any]] = []
HANDLERS: dict[str, Any] = {}

# 核心模块（6 个）
from . import memory_ops

TOOLS.extend(memory_ops.TOOLS)
HANDLERS.update(memory_ops.HANDLERS)

from . import search

TOOLS.extend(search.TOOLS)
HANDLERS.update(search.HANDLERS)

from . import system

TOOLS.extend(system.TOOLS)
HANDLERS.update(system.HANDLERS)

from . import io_tools

TOOLS.extend(io_tools.TOOLS)
HANDLERS.update(io_tools.HANDLERS)

from . import palace

TOOLS.extend(palace.TOOLS)
HANDLERS.update(palace.HANDLERS)

from . import batch

TOOLS.extend(batch.TOOLS)
HANDLERS.update(batch.HANDLERS)

# 可选模块（10 个，默认加载，由暴露面过滤器控制可见性）
from . import analytics

TOOLS.extend(analytics.TOOLS)
HANDLERS.update(analytics.HANDLERS)

from . import consolidation

TOOLS.extend(consolidation.TOOLS)
HANDLERS.update(consolidation.HANDLERS)

from . import embed

TOOLS.extend(embed.TOOLS)
HANDLERS.update(embed.HANDLERS)

from . import knowledge_graph

TOOLS.extend(knowledge_graph.TOOLS)
HANDLERS.update(knowledge_graph.HANDLERS)

from . import llm_tools

TOOLS.extend(llm_tools.TOOLS)
HANDLERS.update(llm_tools.HANDLERS)

from . import multimodal

TOOLS.extend(multimodal.TOOLS)
HANDLERS.update(multimodal.HANDLERS)

from . import quality

TOOLS.extend(quality.TOOLS)
HANDLERS.update(quality.HANDLERS)

from . import session

TOOLS.extend(session.TOOLS)
HANDLERS.update(session.HANDLERS)

from . import timeline

TOOLS.extend(timeline.TOOLS)
HANDLERS.update(timeline.HANDLERS)

from . import wiki

TOOLS.extend(wiki.TOOLS)
HANDLERS.update(wiki.HANDLERS)

# advanced 模块（实验容器，默认不加载，由暴露面过滤器控制）
# 注意：advanced 中的实验工具已被提取到 experimental/，此处仅作兼容
from . import advanced

TOOLS.extend(advanced.TOOLS)
HANDLERS.update(advanced.HANDLERS)

# ── 实验模块动态加载 ──

_EXPERIMENTAL_LOADED: set[str] = set()


def load_experimental_tools(config: Any) -> None:
    """根据配置加载实验模块

    Args:
        config: PanguConfig 实例，从中读取 exposure.enabled_experiments

    注意：
    - 默认 enabled_experiments = {}，不加载任何实验模块
    - 已加载的实验组不会重复加载
    - 加载失败记录 ERROR 日志，服务继续启动
    """
    global _EXPERIMENTAL_LOADED

    if config is None:
        return

    exposure = getattr(config, "exposure", None)
    if exposure is None:
        return

    enabled_experiments = getattr(exposure, "enabled_experiments", set())
    if not enabled_experiments:
        return

    # 实验组名到模块名的映射
    group_to_module = {
        "cognitive": "experimental.cognitive",
        "worldmodel": "experimental.worldmodel",
        "causal": "experimental.causal",
        "autonomous": "experimental.autonomous",
        "autopilot": "experimental.autopilot",
        "neural": "experimental.neural",
        "dream": "experimental.dream",
        "evolution": "experimental.evolution",
        "meta": "experimental.meta",
        "self_aware": "experimental.self_aware",
    }

    for group_name in enabled_experiments:
        if group_name in _EXPERIMENTAL_LOADED:
            continue

        module_name = group_to_module.get(group_name)
        if not module_name:
            # advanced 是 experimental 层的容器模块（handlers/advanced.py），
            # 它的 TOOLS/HANDLERS 在模块导入时已随本包一并加载，无需再次
            # import——它没有独立的 pangu.experimental.advanced 模块。
            # 若在此报"未知实验组"并跳过，会让人误以为启用失败：实际上
            # tools/list 会因 exposure 侧按模块名放行而列出这些工具，
            # 但 handler 缺失导致 tools/call 调用即失败，问题极难定位。
            from pangu.server.module_registry import MODULE_REGISTRY as _REG

            if any(e.name == group_name and e.level == "experimental" for e in _REG):
                _EXPERIMENTAL_LOADED.add(group_name)
                logger.info(f"实验组 {group_name} 为内置容器模块，已由包导入加载")
            else:
                logger.warning(f"未知实验组: {group_name}，跳过")
            continue

        try:
            mod = __import__(
                module_name,
                globals(),
                locals(),
                fromlist=["TOOLS", "HANDLERS"],
            )
            # 按工具名去重后再追加。
            #
            # 这些实验工具的 schema 在包导入时已随 handlers/advanced.py 一并
            # 进入 TOOLS（advanced 是 experimental 层的容器模块，两者内容
            # 重叠），此处按 enabled_experiments 再 import 会重复追加同一
            # 批工具。后果不只是数字变大：**MCP 服务端要求工具名唯一，
            # 重名会让官方 SDK 整表拒收**（tools/list 全废）。
            existing = {t.get("name") for t in TOOLS}
            added = [t for t in getattr(mod, "TOOLS", []) if t.get("name") not in existing]
            if added:
                TOOLS.extend(added)
                existing.update(t.get("name") for t in added)
            HANDLERS.update(getattr(mod, "HANDLERS", {}))
            _EXPERIMENTAL_LOADED.add(group_name)
            logger.info(f"已加载实验组: {group_name}（新增 {len(added)} 个工具）")
        except Exception as e:
            logger.error(f"加载实验组 {group_name} 失败: {e}")


def get_total_tools() -> int:
    """返回当前工具总数（含实验模块）"""
    return len(TOOLS)


def get_total_handlers() -> int:
    """返回当前处理器总数（含实验模块）"""
    return len(HANDLERS)


# ── MCP 规范合规后处理 ──
# 标准 MCP 客户端（官方 SDK / DSH mcp-client）对 tools/list 做强 schema 校验：
# 1. 每个工具必须携带 object 类型的 inputSchema；
# 2. 工具名不得重复，否则整个列表被拒收。
# 此处对全部工具统一补齐 inputSchema 并按名去重（保留首个）。

# 高频工具的精确参数 schema；未列出的工具回退到宽松默认
_TOOL_SCHEMAS = {
    "pangu_fts_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回条数上限", "default": 5},
            "wing": {"type": "string", "description": "限定 Wing（可选）"},
        },
        "required": ["query"],
    },
    "pangu_search_memories": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "查询文本"},
            "wing": {"type": "string", "description": "限定 Wing（可选）"},
            "room": {"type": "string", "description": "限定 Room（可选）"},
        },
        "required": ["query"],
    },
    "pangu_add_memory": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容"},
            "wing": {"type": "string", "description": "Wing 名称", "default": "default"},
            "room": {"type": "string", "description": "Room 名称", "default": "general"},
            "importance": {"type": "number", "description": "重要性", "default": 3.0},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
        },
        "required": ["content"],
    },
    "pangu_recall": {
        "type": "object",
        "properties": {
            "wing": {"type": "string", "description": "Wing 名称"},
            "room": {"type": "string", "description": "Room 名称"},
            "limit": {"type": "integer", "description": "返回条数上限"},
        },
    },
    "pangu_ingest_text": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容（必填）"},
            "text": {"type": "string", "description": "兼容旧参数名（等同于 content，content 优先）"},
            "wing": {"type": "string", "description": "Wing 名称", "default": "default"},
            "room": {"type": "string", "description": "Room 名称", "default": "general"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
            "description": {"type": "string", "description": "描述（会与内容合并）"},
            "modality": {"type": "string", "description": "模态标签", "default": "text"},
        },
        "required": ["content"],
    },
    "pangu_delete_memory": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "要硬删除的记忆 id"},
        },
        "required": ["memory_id"],
    },
    "pangu_archive_memory": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "要归档的记忆 id"},
        },
        "required": ["memory_id"],
    },
}

_PERMISSIVE_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": True}

_seen_names: set[str] = set()
_deduped_tools: list[dict] = []
for _tool in TOOLS:
    if not isinstance(_tool, dict) or not _tool.get("name"):
        continue
    _name = _tool["name"]
    if _name in _seen_names:
        continue
    _seen_names.add(_name)
    _tool.setdefault("inputSchema", _TOOL_SCHEMAS.get(_name, _PERMISSIVE_SCHEMA))
    _deduped_tools.append(_tool)

TOOLS[:] = _deduped_tools
TOTAL_TOOLS = len(TOOLS)
