"""盘古 MCP Handler — supersede (1 tool)

追踪 P0-1 supersede 关系的变更链：给定 memory_id，返回 supersedes /
superseded_by 与 versioning 历史。
"""

from __future__ import annotations

import json

TOOLS = [
    {
        "name": "pangu_get_supersede_chain",
        "description": "获取某条记忆的 supersede 变更链（含 supersedes / superseded_by 与 versioning 历史）",
    },
]

HANDLERS: dict[str, object] = {}


async def handle_get_supersede_chain(server, drawers, arguments):
    """获取记忆的 supersede 链

    Input:
      {
        "memory_id": "<必填>",   # 任意方向都可：可传入旧 id 或新 id
        "direction": "both" | "forward" | "backward"  # 默认 both
      }

    Output:
      {
        "memory_id": "<入参 id>",
        "found": true | false,
        "chain": [                  # supersede 关系链（按时间排序）
          {"id": ..., "content_preview": ..., "created_at": ..., "role": "root|old|new",
           "supersedes": [...], "superseded_by": [...]}
        ],
        "versions": [               # 来自 versioning 引擎
          {"memory_id": ..., "version": int, "change_type": str,
           "timestamp": str, "metadata": {...}}
        ],
        "depth": int                # 链上节点数（不含当前节点）
      }
    """
    memory_id = arguments.get("memory_id", "")
    if not memory_id:
        return json.dumps(
            {"code": 2002, "error": "memory_id is required"},
            ensure_ascii=False,
        )

    direction = arguments.get("direction", "both")
    if direction not in ("both", "forward", "backward"):
        direction = "both"

    # 通过 server.memory（MemoryStack 单例）拿 drawer
    target = None
    try:
        if server is not None and getattr(server, "memory", None) is not None:
            target = server.memory.get_drawer_by_id(memory_id)
        else:
            # 测试 / 独立调用场景：直接用全局 MemoryStack
            from pangu.core.config import PanguConfig
            from pangu.memory.layers import MemoryStack

            target = MemoryStack(config=PanguConfig.load().authoritative_memory_config()).get_drawer_by_id(memory_id)
    except Exception:
        target = None

    if target is None:
        return json.dumps(
            {
                "memory_id": memory_id,
                "found": False,
                "chain": [],
                "versions": [],
                "depth": 0,
            },
            ensure_ascii=False,
        )

    def _get(mid: str):
        try:
            if server is not None and getattr(server, "memory", None) is not None:
                return server.memory.get_drawer_by_id(mid)
        except Exception:
            return None
        return None

    visited: set[str] = {memory_id}
    chain_nodes: list[dict] = []

    def _to_node(d, role: str) -> dict:
        meta = d.metadata or {}
        return {
            "id": d.id,
            "content_preview": (d.content or "")[:80],
            "created_at": d.created_at,
            "role": role,
            "supersedes": meta.get("supersedes", []) if isinstance(meta.get("supersedes"), list) else [],
            "superseded_by": meta.get("superseded_by", []) if isinstance(meta.get("superseded_by"), list) else [],
        }

    chain_nodes.append(_to_node(target, "root"))

    # backward：沿 supersedes 找更早的版本
    if direction in ("both", "backward"):
        queue = list((target.metadata or {}).get("supersedes", []) or [])
        while queue:
            old_id = queue.pop(0)
            if old_id in visited:
                continue
            visited.add(old_id)
            old_d = _get(old_id)
            if old_d is None:
                continue
            chain_nodes.append(_to_node(old_d, "old"))
            queue.extend((old_d.metadata or {}).get("supersedes", []) or [])

    # forward：沿 superseded_by 找更新的版本
    if direction in ("both", "forward"):
        queue = list((target.metadata or {}).get("superseded_by", []) or [])
        while queue:
            new_id = queue.pop(0)
            if new_id in visited:
                continue
            visited.add(new_id)
            new_d = _get(new_id)
            if new_d is None:
                continue
            chain_nodes.append(_to_node(new_d, "new"))
            queue.extend((new_d.metadata or {}).get("superseded_by", []) or [])

    # versions from versioning 引擎
    versions: list[dict] = []
    try:
        from pangu.memory.versioning import get_version_control

        vc = get_version_control()
        for n in chain_nodes:
            try:
                for v in vc.get_versions(n["id"]):
                    versions.append(
                        {
                            "memory_id": n["id"],
                            "version": v.version,
                            "change_type": v.change_type,
                            "timestamp": v.timestamp,
                            "metadata": v.metadata,
                        }
                    )
            except Exception:
                continue
    except Exception:
        pass

    return json.dumps(
        {
            "memory_id": memory_id,
            "found": True,
            "chain": chain_nodes,
            "versions": versions,
            "depth": len(chain_nodes) - 1,
        },
        ensure_ascii=False,
        indent=2,
    )


HANDLERS["pangu_get_supersede_chain"] = handle_get_supersede_chain
