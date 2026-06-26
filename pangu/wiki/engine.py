"""盘古 Wiki 引擎 — 知识页面的创建、链接和维护"""

import json
from datetime import datetime
from pathlib import Path

from ..core.config import PanguConfig
from ..core.llm import LLMEngine
from ..core.palace import WikiPage


class WikiEngine:
    """Wiki 知识引擎 — 管理知识页面的生命周期"""

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
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

    # ── 页面 CRUD ──

    def create_page(self, page: WikiPage) -> WikiPage:
        """创建 Wiki 页面"""
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
        """获取 Wiki 页面"""
        return self._pages.get(page_id)

    def get_page_by_title(self, title: str) -> WikiPage | None:
        """按标题查找页面"""
        for page in self._pages.values():
            if page.title.lower() == title.lower():
                return page
        return None

    def list_pages(self, wing: str = None, tag: str = None) -> list[WikiPage]:
        """列出页面"""
        pages = list(self._pages.values())
        if wing:
            pages = [p for p in pages if p.wing == wing]
        if tag:
            pages = [p for p in pages if tag in p.tags]
        return sorted(pages, key=lambda p: p.updated_at, reverse=True)

    def update_page(self, page: WikiPage) -> WikiPage:
        """更新 Wiki 页面"""
        if page.id not in self._pages:
            raise ValueError(f"页面 {page.id} 不存在")

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
        """删除 Wiki 页面"""
        if page_id not in self._pages:
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
        existing_pages = [{"title": p.title, "summary": p.summary} for p in self._pages.values() if p.wing == wing]

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
        all_pages = [{"title": p.title, "summary": p.summary} for p in self._pages.values()]
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
        if not page or not linked:
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
        if not page or not linked:
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
        for page in self._pages.values():
            if page_id in page.linked_pages:
                backlinks.append(page)
        return backlinks

    # ── 知识图谱 ──

    def export_graph(self) -> dict:
        """导出 Wiki 知识图谱"""
        nodes = []
        edges = []

        for page in self._pages.values():
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
        """Wiki 统计信息"""
        pages = list(self._pages.values())
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
