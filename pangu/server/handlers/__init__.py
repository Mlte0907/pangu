"""盘古 MCP Handler 路由"""

TOOLS = []
HANDLERS = {}

from . import advanced

TOOLS.extend(advanced.TOOLS)
HANDLERS.update(advanced.HANDLERS)
from . import analytics

TOOLS.extend(analytics.TOOLS)
HANDLERS.update(analytics.HANDLERS)
from . import batch

TOOLS.extend(batch.TOOLS)
HANDLERS.update(batch.HANDLERS)
from . import consolidation

TOOLS.extend(consolidation.TOOLS)
HANDLERS.update(consolidation.HANDLERS)
from . import embed

TOOLS.extend(embed.TOOLS)
HANDLERS.update(embed.HANDLERS)
from . import io_tools

TOOLS.extend(io_tools.TOOLS)
HANDLERS.update(io_tools.HANDLERS)
from . import knowledge_graph

TOOLS.extend(knowledge_graph.TOOLS)
HANDLERS.update(knowledge_graph.HANDLERS)
from . import llm_tools

TOOLS.extend(llm_tools.TOOLS)
HANDLERS.update(llm_tools.HANDLERS)
from . import memory_ops

TOOLS.extend(memory_ops.TOOLS)
HANDLERS.update(memory_ops.HANDLERS)
from . import multimodal

TOOLS.extend(multimodal.TOOLS)
HANDLERS.update(multimodal.HANDLERS)
from . import palace

TOOLS.extend(palace.TOOLS)
HANDLERS.update(palace.HANDLERS)
from . import quality

TOOLS.extend(quality.TOOLS)
HANDLERS.update(quality.HANDLERS)
from . import search

TOOLS.extend(search.TOOLS)
HANDLERS.update(search.HANDLERS)
from . import session

TOOLS.extend(session.TOOLS)
HANDLERS.update(session.HANDLERS)
from . import system

TOOLS.extend(system.TOOLS)
HANDLERS.update(system.HANDLERS)
from . import timeline

TOOLS.extend(timeline.TOOLS)
HANDLERS.update(timeline.HANDLERS)
from . import wiki

TOOLS.extend(wiki.TOOLS)
HANDLERS.update(wiki.HANDLERS)

TOTAL_TOOLS = len(TOOLS)
TOTAL_HANDLERS = len(HANDLERS)
