"""盘古 Wiki 引擎 — 知识页面的创建、链接和维护"""

import json
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.llm import LLMEngine
from ..core.palace import WikiPage

# 复用记忆层的请求级租户作用域 —— 全仓只有这一套语义（tenant_id + visibility），
# 不在 wiki 里另起字段名，否则跨域查询/审计/迁移都要做翻译。
from ..memory.layers import current_tenant


def page_tenant(page: WikiPage) -> str:
    """页面归属租户（无 metadata 或未标注 → 空串＝无主）。"""
    return str((page.metadata or {}).get("tenant_id", "") or "")


def page_is_public(page: WikiPage) -> bool:
    """是否公开（毕业区语义：跨租户可读）。"""
    return (page.metadata or {}).get("visibility", "") == "public"


class WikiEngine:
    """Wiki 知识引擎 — 管理知识页面的生命周期"""

    def __init__(self, config: PanguConfig = None):
        self.config = (config or PanguConfig.load()).authoritative_memory_config()
        self.wiki_path = Path(self.config.wiki_path)
        self.wiki_path.mkdir(parents=True, exist_ok=True)

        # 页面索引文件
        self.index_file = self.wiki_path / "wiki_index.json"
        self._pages: dict[str, WikiPage] = {}
        self._load_index()

    def _load_index(self) -> None:
        """加载 Wiki 索引"""
        if self.index_file.exists():
            with open(self.index_file, encoding="utf-8") as f:
                data = json.load(f)
            self._pages = {pid: WikiPage.from_dict(pdata) for pid, pdata in data.get("pages", {}).items()}
        else:
            self._pages = {}
            self._save_index()

    def _save_index(self) -> None:
        """保存 Wiki 索引"""
        data = {
            "pages": {pid: page.to_dict() for pid, page in self._pages.items()},
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 租户作用域（读路径的唯一收口点）──

    def _visible(self, page: WikiPage | None) -> bool:
        """当前请求作用域下该页面是否可见。

        判据与记忆/KG 完全一致：本租户 或 visibility='public'；作用域为空＝全库视角。
        不可见＝不存在（对外表现与"没有这个页面"一致，不泄露存在性）。
        """
        if page is None:
            return False
        tenant = current_tenant()
        if not tenant:
            return True
        return page_tenant(page) == tenant or page_is_public(page)

    def visible_pages(self) -> list[WikiPage]:
        """读路径入口：按作用域过滤后的页面集合。**所有读方法都应走它**。

        为什么集中在一处：本引擎的读入口有 8 个（get_page / get_page_by_title /
        list_pages / get_linked_pages / get_backlinks / export_graph / stats /
        auto_generate_page 的 LLM 上下文），逐个加条件必然漏一个 —— 记忆层的教训是
        287 个 handler 里漏了 18 个，靠人工扫描才发现。
        """
        tenant = current_tenant()
        if not tenant:
            return list(self._pages.values())
        return [p for p in self._pages.values() if self._visible(p)]

    def _owned_by_current(self, page: WikiPage | None) -> bool:
        """写路径判据（比可见性更严）：必须是**本租户**的页面。

        public 只是"可读"——不能因为别的租户把页面标了 public，我就能改它/删它。
        作用域为空（后台维护）时不做限制，保持原有全库语义。
        """
        if page is None:
            return False
        tenant = current_tenant()
        if not tenant:
            return True
        return page_tenant(page) == tenant

    def _non_colliding_id(self, page: WikiPage) -> str:
        """不覆盖别的租户的页面（索引以 id 为键，直接赋值就是跨租户覆盖）。

        本租户同 id ＝ "覆盖自己那份"（原有语义）；别人占用了同名 id 则另起后缀，两份共存
        —— 与 KG 用复合主键达成的效果一致（同名各租户各一份）。
        """
        owner = page_tenant(page)
        candidate = page.id
        n = 1
        while True:
            existing = self._pages.get(candidate)
            if existing is None or page_tenant(existing) == owner:
                return candidate
            n += 1
            candidate = f"{page.id}-{n}"

    # ── 页面 CRUD ──

    def create_page(self, page: WikiPage) -> WikiPage:
        """创建 Wiki 页面（落当前租户归属）"""
        page.metadata = dict(page.metadata or {})
        if not page.metadata.get("tenant_id"):
            page.metadata["tenant_id"] = current_tenant()
        page.id = self._non_colliding_id(page)
        self._pages[page.id] = page

        # 保存页面内容到独立文件
        page_file = self.wiki_path / f"{page.id}.md"
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(f"# {page.title}\n\n")
            f.write(f"> 摘要: {page.summary}\n\n")
            f.write(f"> Wing: {page.wing} | 标签: {', '.join(page.tags)}\n\n")
            f.write("---\n\n")
            f.write(page.content)

        self._save_index()
        return page

    def get_page(self, page_id: str) -> WikiPage | None:
        """获取 Wiki 页面（读路径：受租户作用域裁剪，不可见＝不存在）"""
        page = self._pages.get(page_id)
        return page if self._visible(page) else None

    def get_page_by_title(self, title: str) -> WikiPage | None:
        """按标题查找页面（读路径：只在可见集合里找）"""
        for page in self.visible_pages():
            if page.title.lower() == title.lower():
                return page
        return None

    def list_pages(self, wing: str = None, tag: str = None) -> list[WikiPage]:
        """列出页面（读路径：只列可见的）"""
        pages = self.visible_pages()
        if wing:
            pages = [p for p in pages if p.wing == wing]
        if tag:
            pages = [p for p in pages if tag in p.tags]
        return sorted(pages, key=lambda p: p.updated_at, reverse=True)

    def update_page(self, page: WikiPage) -> WikiPage:
        """更新 Wiki 页面（写路径：只允许改本租户的页面；public 只是可读，不等于可写）"""
        existing = self._pages.get(page.id)
        if existing is None or not self._visible(existing):
            raise ValueError(f"页面 {page.id} 不存在")
        if not self._owned_by_current(existing):
            raise ValueError(f"页面 {page.id} 不属于当前租户，拒绝更新")

        page.version += 1
        page.updated_at = datetime.now().isoformat()
        self._pages[page.id] = page

        # 更新内容文件
        page_file = self.wiki_path / f"{page.id}.md"
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(f"# {page.title}\n\n")
            f.write(f"> 摘要: {page.summary}\n\n")
            f.write(f"> Wing: {page.wing} | 标签: {', '.join(page.tags)}\n\n")
            f.write(f"> 版本: {page.version} | 更新: {page.updated_at}\n\n")
            f.write("---\n\n")
            f.write(page.content)

        self._save_index()
        return page

    def delete_page(self, page_id: str) -> bool:
        """删除 Wiki 页面（写路径：只允许删本租户的页面）"""
        page = self._pages.get(page_id)
        if page is None or not self._visible(page):
            return False
        if not self._owned_by_current(page):
            return False

        del self._pages[page_id]
        page_file = self.wiki_path / f"{page_id}.md"
        if page_file.exists():
            page_file.unlink()

        self._save_index()
        return True

    # ── 智能功能 ──

    async def auto_generate_page(self, llm: LLMEngine, title: str, wing: str, memories: list[dict]) -> WikiPage:
        """使用 LMM 自动从记忆中生成 Wiki 页面"""
        # 获取已有页面作为上下文
        # 读路径：送进 LLM 的"已有页面"上下文也必须过滤 —— 否则别的租户的页面标题/摘要
        # 会被当成生成上下文送给模型（既是数据泄漏，也会让生成结果串味）。
        existing_pages = [{"title": p.title, "summary": p.summary} for p in self.visible_pages() if p.wing == wing]

        result = await llm.generate_wiki_page(title, memories, existing_pages)

        page = WikiPage(
            id=f"wiki_{datetime.now().strftime('%Y%m%d%H%M%S')}_{title[:20]}",
            title=result.get("title", title),
            wing=wing,
            content=result.get("content", ""),
            summary=result.get("summary", ""),
            tags=result.get("tags", []),
        )

        # 检测页面关联
        all_pages = [{"title": p.title, "summary": p.summary} for p in self.visible_pages()]
        linked_titles = await llm.detect_links({"title": page.title, "summary": page.summary}, all_pages)
        for linked_title in linked_titles:
            linked_page = self.get_page_by_title(linked_title)
            if linked_page:
                page.linked_pages.append(linked_page.id)

        return self.create_page(page)

    async def enrich_page(self, llm: LLMEngine, page_id: str, memories: list[dict]) -> WikiPage:
        """使用 LMM 丰富已有页面"""
        page = self.get_page(page_id)
        if not page:
            raise ValueError(f"页面 {page_id} 不存在")

        # 用新记忆更新页面
        system = """你是盘古 Wiki 编辑引擎。请将新记忆融合到已有 Wiki 页面中。

要求：
1. 保留原有内容，补充新信息
2. 更新摘要以反映最新状态
3. 使用 Markdown 格式
4. 使用中文输出"""

        memory_text = "\n\n---\n\n".join([m.get("content", "")[:1000] for m in memories[:5]])

        llm_response = await llm.chat(
            messages=[
                {
                    "role": "user",
                    "content": f"现有页面：\n标题：{page.title}\n内容：\n{page.content}\n\n新记忆：\n{memory_text}\n\n请融合更新。",
                }
            ],
            system=system,
            max_tokens=4096,
        )

        page.content = llm_response.content
        page.updated_at = datetime.now().isoformat()
        return self.update_page(page)

    # ── 链接管理 ──

    def add_link(self, page_id: str, linked_page_id: str) -> bool:
        """添加页面关联"""
        page = self.get_page(page_id)
        linked = self.get_page(linked_page_id)
        # 双向写入：两端都必须是本租户的页面，否则就是往别人的页面里塞反链（跨租户写）
        if not page or not linked or not self._owned_by_current(page) or not self._owned_by_current(linked):
            return False

        if linked_page_id not in page.linked_pages:
            page.linked_pages.append(linked_page_id)
        if page_id not in linked.linked_pages:
            linked.linked_pages.append(page_id)

        self._save_index()
        return True

    def remove_link(self, page_id: str, linked_page_id: str) -> bool:
        """移除页面关联"""
        page = self.get_page(page_id)
        linked = self.get_page(linked_page_id)
        if not page or not linked or not self._owned_by_current(page) or not self._owned_by_current(linked):
            return False

        if linked_page_id in page.linked_pages:
            page.linked_pages.remove(linked_page_id)
        if page_id in linked.linked_pages:
            linked.linked_pages.remove(page_id)

        self._save_index()
        return True

    def get_linked_pages(self, page_id: str) -> list[WikiPage]:
        """获取关联页面"""
        page = self.get_page(page_id)
        if not page:
            return []
        return [self.get_page(pid) for pid in page.linked_pages if self.get_page(pid)]

    def get_backlinks(self, page_id: str) -> list[WikiPage]:
        """获取反向链接（哪些页面链接到当前页面）"""
        backlinks = []
        for page in self.visible_pages():
            if page_id in page.linked_pages:
                backlinks.append(page)
        return backlinks

    # ── 知识图谱 ──

    def export_graph(self) -> dict:
        """导出 Wiki 知识图谱"""
        nodes = []
        edges = []

        for page in self.visible_pages():
            nodes.append(
                {
                    "id": page.id,
                    "label": page.title,
                    "type": "wiki_page",
                    "wing": page.wing,
                    "summary": page.summary,
                    "version": page.version,
                }
            )

            for linked_id in page.linked_pages:
                if linked_id in self._pages:
                    edges.append(
                        {
                            "from": page.id,
                            "to": linked_id,
                            "type": "wiki_link",
                        }
                    )

        return {"nodes": nodes, "edges": edges}

    def stats(self) -> dict:
        """Wiki 统计信息（读路径：只统计可见页面）"""
        pages = self.visible_pages()
        wings = set(p.wing for p in pages)
        all_tags = set()
        for p in pages:
            all_tags.update(p.tags)

        return {
            "total_pages": len(pages),
            "total_wings": len(wings),
            "total_links": sum(len(p.linked_pages) for p in pages),
            "total_tags": len(all_tags),
            "average_version": sum(p.version for p in pages) / max(len(pages), 1),
            "last_updated": max((p.updated_at for p in pages), default=""),
        }
