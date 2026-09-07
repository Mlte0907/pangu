"""盘古 — Wikilink 实体解析器（从伏羲 v1.5.6 移植）

支持格式:
  [[Page Title]]           → 解析为 (page_title, page_title)
  [[Page Title|Display]]   → 解析为 (page_title, display)

用于记忆摄入时自动提取实体链接，建立跨记忆的知识关联。
"""

import re
from dataclasses import dataclass

from pangu.core.palace import Drawer


@dataclass
class WikilinkMatch:
    target: str
    display: str
    full_match: str


# Wikilink 正则表达式
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
QUALIFIED_WIKILINK_RE = re.compile(r"\[\[([a-z0-9]+:[^\]|]+)(?:\|([^\]]+))?\]\]")


def parse_wikilinks(text: str) -> list[WikilinkMatch]:
    """解析文本中的所有 Wikilink"""
    if not text:
        return []

    matches = []
    # 优先匹配限定格式（source:path）
    for m in QUALIFIED_WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        display = m.group(2).strip() if m.group(2) else target
        matches.append(WikilinkMatch(target=target, display=display, full_match=m.group(0)))

    # 匹配普通 [[Page]] 格式（排除已匹配的）
    for m in WIKILINK_RE.finditer(text):
        if ":" in m.group(1):
            continue
        target = m.group(1).strip()
        display = m.group(2).strip() if m.group(2) else target
        matches.append(WikilinkMatch(target=target, display=display, full_match=m.group(0)))

    return matches


def resolve_wikilink_to_item(target: str, existing_drawers: list[Drawer]) -> str | None:
    """解析 Wikilink 目标到 item_id

    优先精确匹配，其次模糊匹配
    """
    # 精确匹配
    for d in existing_drawers:
        if target.lower() in d.content.lower():
            return d.id

    # 模糊匹配（取最高相似度）
    best_id = None
    best_score = 0.0
    for d in existing_drawers:
        if target.lower() in d.content.lower():
            score = len(target) / max(len(d.content), 1)
            if score > best_score:
                best_score = score
                best_id = d.id

    return best_id


def _build_edge_dict(target_id: str, link: WikilinkMatch) -> dict:
    return {
        "target_id": target_id,
        "edge_type": "mentions",
        "metadata": {"wikilink": True, "display": link.display, "target": link.target},
    }


def _resolve_link_to_edge(link: WikilinkMatch, source_item_id: str, existing_drawers: list[Drawer]) -> dict | None:
    """解析单个 wikilink 为边字典，无法解析返回 None"""
    target_id = resolve_wikilink_to_item(link.target, existing_drawers)
    if not target_id or target_id == source_item_id:
        return None
    return _build_edge_dict(target_id, link)


def extract_entity_links(text: str, source_item_id: str, existing_drawers: list[Drawer]) -> list[dict]:
    """从文本中提取实体链接，返回边列表

    Returns:
        [{"target_id": str, "edge_type": str, "metadata": dict}, ...]
    """
    links = parse_wikilinks(text)
    edges = []

    for link in links:
        edge = _resolve_link_to_edge(link, source_item_id, existing_drawers)
        if edge:
            edges.append(edge)

    return edges


def get_wikilink_stats(text: str) -> dict:
    """获取文本中 Wikilink 的统计信息"""
    links = parse_wikilinks(text)
    return {
        "total": len(links),
        "links": [{"target": link.target, "display": link.display} for link in links],
    }
