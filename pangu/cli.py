"""盘古 CLI — 命令行入口
=========================
盘古定位为专业的记忆系统（智能体的大脑组件），CLI 只提供记忆管理功能。
不包含 Agent 执行功能（问答、对话、任务执行等）。"""
import asyncio
import json
import os
import sys
import time

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .core.config import PanguConfig
from .core.llm import LLMEngine
from .core.palace import Palace
from .memory.adaptive_params import get_adaptive_engine
from .memory.attention import AttentionStrategy, get_attention_system
from .memory.differential_privacy import DifferentialPrivacy
from .memory.distill_enhanced import DistillationTower
from .memory.enhanced_evaluation import EnhancedContradictionDetector, TrajectoryTracker
from .memory.fts_search import FTS5SearchEngine, get_search_stats, holographic_search
from .memory.hologram import get_holographic_encoder
from .memory.judge import get_memory_judge
from .memory.knowledge_graph import KnowledgeGraph
from .memory.layers import MemoryStack
from .memory.reconsolidation import ReconsolidationEngine, ResonanceEngine
from .memory.sanitizer import MemorySanitizer
from .memory.streaming_index import StreamingIndexer
from .memory.vector_index import get_vector_index
from .memory.verification import VerificationLoop
from .memory.working_memory import WMItem, get_working_memory
from .mining.miners import ConvoMiner, FileMiner
from .search.engine import HybridSearch
from .wiki.engine import WikiEngine

app = typer.Typer(
    name="pangu",
    help='盘古 — 专业记忆系统（智能体的大脑组件）',
    add_completion=False,
)

console = Console()


def get_config() -> PanguConfig:
    return PanguConfig.load()


# ── 初始化 ──

@app.command()
def init(
    path: str = typer.Option("~/.pangu", help="盘古数据目录"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新初始化"),
):
    """初始化盘古记忆系统"""
    path = os.path.expanduser(path)
    config = PanguConfig()
    config.palace_path = os.path.join(path, "palace")
    config.wiki_path = os.path.join(path, "wiki")
    config.identity_path = os.path.join(path, "identity.txt")
    config.config_path = os.path.join(path, "config.json")

    if os.path.exists(config.config_path) and not force:
        console.print("[yellow]盘古已初始化，使用 --force 强制重新初始化[/yellow]")
        return

    config.ensure_dirs()
    config.save(config.config_path)

    # 初始化宫殿
    palace = Palace(config.palace_path)
    palace.create_wing("default", "默认空间")

    # 创建默认身份文件
    if not os.path.exists(config.identity_path):
        with open(config.identity_path, "w", encoding="utf-8") as f:
            f.write("""## L0 — 盘古身份
我是盘古，一个专业的记忆系统（智能体的大脑组件）。
我专注于记忆的存储、检索、组织和知识结晶。
我通过 MCP 接口为上层 Agent 框架提供记忆服务。

特点：深度记忆、知识关联、智能分类
使命：为智能系统提供类人记忆能力""")

    console.print(Panel.fit(
        f"[bold green]盘古记忆系统初始化完成！[/bold green]\n\n"
        f"数据目录: {path}\n"
        f"宫殿路径: {config.palace_path}\n"
        f"Wiki 路径: {config.wiki_path}\n"
        f"身份文件: {config.identity_path}\n\n"
        f"运行 [bold]pangu serve[/bold] 启动 Web 界面\n"
        f"运行 [bold]pangu --help[/bold] 查看更多命令",
        title="盘古",
    ))


# ── 挖掘 ──

@app.command()
def mine(
    path: str = typer.Argument(..., help="要挖掘的目录路径"),
    wing: str = typer.Option(None, help="归属的 Wing 名称"),
    mode: str = typer.Option("files", help="挖掘模式: files, convos"),
    format: str = typer.Option("jsonl", help="对话格式: jsonl, chatgpt"),
):
    """从文件或对话中挖掘记忆"""
    config = get_config()
    config.ensure_dirs()

    if mode == "files":
        miner = FileMiner(config)
        drawers = miner.scan_directory(path, wing=wing)
    elif mode == "convos":
        miner = ConvoMiner(config)
        if format == "chatgpt":
            drawers = miner.parse_chatgpt_json(path, wing=wing)
        else:
            drawers = miner.parse_claude_jsonl(path, wing=wing)
    else:
        console.print(f"[red]未知模式: {mode}[/red]")
        return

    if not drawers:
        console.print("[yellow]未发现可挖掘的内容[/yellow]")
        return

    memory = MemoryStack(config)
    memory.add_drawers(drawers)

    # 统计
    rooms = set(d.room for d in drawers)
    wings = set(d.wing for d in drawers)

    table = Table(title="挖掘结果")
    table.add_column("项目", style="cyan")
    table.add_column("数量", style="green")
    table.add_row("记忆片段", str(len(drawers)))
    table.add_row("Wing", str(len(wings)))
    table.add_row("Room", str(len(rooms)))
    console.print(table)


# ── 搜索 ──

@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词"),
    wing: str = typer.Option(None, help="限定 Wing"),
    room: str = typer.Option(None, help="限定 Room"),
    n_results: int = typer.Option(10, help="返回结果数"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """搜索记忆"""
    config = get_config()
    memory = MemoryStack(config)
    searcher = HybridSearch(config)

    drawers = memory.get_drawers()
    results = searcher.search(query, drawers, wing=wing, room=room, n_results=n_results)

    if json_output:
        console.print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        console.print(f"[yellow]未找到与 \"{query}\" 相关的结果[/yellow]")
        return

    console.print(f"\n[bold]搜索结果: \"{query}\"[/bold]\n")
    for i, r in enumerate(results, 1):
        content = r.get("content", "")[:200]
        score = r.get("score", "N/A")
        wing_name = r.get("wing", "?")
        room_name = r.get("room", "?")
        console.print(f"[cyan][{i}][/cyan] {wing_name}/{room_name} [dim](score={score})[/dim]")
        console.print(f"    {content}...\n")


# ── 唤醒 ──

@app.command()
def wake_up(
    wing: str = typer.Option(None, help="指定 Wing"),
):
    """获取唤醒上下文 (L0 + L1)"""
    config = get_config()
    memory = MemoryStack(config)
    context = memory.wake_up(wing=wing)
    console.print(Markdown(context))


# ── 回忆 ──

@app.command()
def recall(
    wing: str = typer.Option(None, help="限定 Wing"),
    room: str = typer.Option(None, help="限定 Room"),
    n_results: int = typer.Option(10, help="返回结果数"),
):
    """按 Wing/Room 回忆记忆"""
    config = get_config()
    memory = MemoryStack(config)
    result = memory.recall(wing=wing, room=room, n_results=n_results)
    console.print(Markdown(result))


# ── Wiki ──

@app.command()
def wiki_list(
    wing: str = typer.Option(None, help="限定 Wing"),
    tag: str = typer.Option(None, help="限定标签"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """列出 Wiki 页面"""
    config = get_config()
    wiki = WikiEngine(config)
    pages = wiki.list_pages(wing=wing, tag=tag)

    if json_output:
        console.print(json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2))
        return

    if not pages:
        console.print("[yellow]暂无 Wiki 页面[/yellow]")
        return

    table = Table(title="Wiki 页面")
    table.add_column("标题", style="cyan")
    table.add_column("Wing", style="green")
    table.add_column("摘要", style="dim")
    table.add_column("版本", style="magenta")

    for p in pages:
        table.add_row(p.title, p.wing, p.summary[:50], str(p.version))

    console.print(table)


@app.command()
def wiki_generate(
    title: str = typer.Argument(..., help="页面标题"),
    wing: str = typer.Option("default", help="归属 Wing"),
):
    """使用 LMM 自动生成 Wiki 页面"""
    config = get_config()
    memory = MemoryStack(config)
    wiki = WikiEngine(config)
    llm = LLMEngine(config)

    drawers = memory.get_drawers()
    memories = [
        {"content": d.content, "wing": d.wing, "room": d.room}
        for d in drawers if d.wing == wing
    ]

    console.print(f"[cyan]正在为 \"{title}\" 生成 Wiki 页面...[/cyan]")
    page = asyncio.run(wiki.auto_generate_page(llm, title, wing, memories))

    console.print(Panel.fit(
        Markdown(page.content),
        title=f"[bold]{page.title}[/bold]",
        subtitle=f"Wing: {page.wing} | Tags: {', '.join(page.tags)}",
    ))


# ── 知识图谱 ──

@app.command()
def kg_stats():
    """知识图谱统计"""
    config = get_config()
    kg = KnowledgeGraph(config)
    stats = kg.stats()

    table = Table(title="知识图谱统计")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)


# ── 统计 ──

@app.command()
def stats(json_output: bool = typer.Option(False, "--json", help="JSON 格式输出")):
    """系统统计信息"""
    config = get_config()
    palace = Palace(config.palace_path)
    memory = MemoryStack(config)
    wiki = WikiEngine(config)
    kg = KnowledgeGraph(config)

    all_stats = {
        "palace": palace.stats(),
        "memory": memory.status(),
        "wiki": wiki.stats(),
        "knowledge_graph": kg.stats(),
    }

    if json_output:
        console.print(json.dumps(all_stats, ensure_ascii=False, indent=2))
        return

    console.print(Panel.fit(
        f"[bold]宫殿[/bold]\n"
        f"  Wings: {all_stats['palace']['wings_count']}\n"
        f"  Rooms: {all_stats['palace']['rooms_count']}\n"
        f"  Tunnels: {all_stats['palace']['tunnels_count']}\n\n"
        f"[bold]记忆[/bold]\n"
        f"  Drawers: {all_stats['memory']['total_drawers']}\n"
        f"  L0 Tokens: {all_stats['memory']['L0_identity']['tokens']}\n\n"
        f"[bold]Wiki[/bold]\n"
        f"  Pages: {all_stats['wiki']['total_pages']}\n"
        f"  Links: {all_stats['wiki']['total_links']}\n\n"
        f"[bold]知识图谱[/bold]\n"
        f"  Entities: {all_stats['knowledge_graph']['entities']}\n"
        f"  Relations: {all_stats['knowledge_graph']['relations']}",
        title="盘古系统统计",
    ))


# ── 记忆巩固 ──

@app.command()
def consolidate():
    """查看记忆巩固状态（遗忘/复习/压缩）"""
    config = get_config()
    memory = MemoryStack(config)
    stats = memory.get_consolidation_stats()

    console.print(Panel.fit(
        f"[bold]记忆巩固状态[/bold]\n\n"
        f"总记忆数: {stats['total_memories']}\n"
        f"待遗忘: {stats['forgotten_count']}\n"
        f"待复习: {stats['due_review_count']}\n"
        f"平均有效重要性: {stats['average_effective_importance']}\n"
        f"需要压缩: {'是' if stats['needs_compression'] else '否'}\n"
        f"总访问次数: {stats['total_accesses']}",
        title="盘古记忆巩固",
    ))


@app.command()
def forget(
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示将被遗忘的记忆，不实际删除"),
):
    """遗忘低重要性记忆"""
    config = get_config()
    memory = MemoryStack(config)
    forgotten = memory.find_forgotten()

    if not forgotten:
        console.print("[green]没有需要遗忘的记忆[/green]")
        return

    table = Table(title=f"将被遗忘的记忆 ({len(forgotten)} 条)")
    table.add_column("ID", style="dim")
    table.add_column("内容", style="cyan")
    table.add_column("重要性", style="yellow")

    for d in forgotten:
        table.add_row(d.id[:20], d.content[:60], f"{d.importance:.1f}")

    console.print(table)

    if not dry_run:
        ids = [d.id for d in forgotten]
        removed = memory.remove_drawers(ids)
        console.print(f"[green]已遗忘 {removed} 条记忆[/green]")

@app.command()
def compress(
    wing: str = typer.Option(None, help="限定 Wing"),
    target_count: int = typer.Option(5, help="压缩目标条数"),
):
    """压缩旧记忆为精简摘要"""
    config = get_config()
    memory = MemoryStack(config)
    llm = LLMEngine(config)

    compressible = memory.find_compressible()
    if wing:
        compressible = [d for d in compressible if d.wing == wing]

    if not compressible:
        console.print("[yellow]没有可压缩的记忆[/yellow]")
        return

    console.print(f"[cyan]正在压缩 {len(compressible)} 条记忆...[/cyan]")
    memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in compressible]
    result = asyncio.run(llm.compress_memories(memories, target_count=target_count))
    console.print(Markdown(result))


@app.command()
def associations(
    wing: str = typer.Option(None, help="限定 Wing"),
):
    """检测记忆之间的关联"""
    config = get_config()
    memory = MemoryStack(config)
    llm = LLMEngine(config)

    drawers = memory.get_drawers()
    if wing:
        drawers = [d for d in drawers if d.wing == wing]

    if len(drawers) < 2:
        console.print("[yellow]需要至少 2 条记忆才能检测关联[/yellow]")
        return

    console.print(f"[cyan]正在分析 {len(drawers)} 条记忆的关联...[/cyan]")
    memories = [{"content": d.content, "wing": d.wing, "room": d.room} for d in drawers[:20]]
    result = asyncio.run(llm.detect_associations(memories))

    if result.get("associations"):
        table = Table(title="记忆关联")
        table.add_column("来源", style="cyan")
        table.add_column("目标", style="green")
        table.add_column("关系", style="yellow")
        table.add_column("强度", style="magenta")

        for assoc in result["associations"]:
            table.add_row(
                str(assoc.get("from_idx", "")),
                str(assoc.get("to_idx", "")),
                assoc.get("relation", ""),
                str(assoc.get("strength", "")),
            )
        console.print(table)

    if result.get("clusters"):
        console.print("\n[bold]记忆簇:[/bold]")
        for cluster in result["clusters"]:
            console.print(f"  [cyan]{cluster.get('theme', '')}[/cyan]: {cluster.get('summary', '')}")


# ── 迁移与备份 ──

@app.command()
def export(
    output: str = typer.Option("pangu_export.json", "--output", "-o", help="输出文件路径"),
    format: str = typer.Option("json", "--format", "-f", help="导出格式: json, zip"),
    wing: str = typer.Option(None, help="限定 Wing"),
):
    """导出记忆数据"""
    config = get_config()
    from .memory.migration import MemoryExporter
    exporter = MemoryExporter(config)

    if wing:
        path = exporter.export_memories(output, wing=wing)
    else:
        path = exporter.export_all(output, format=format)

    console.print(f"[green]数据已导出到: {path}[/green]")


@app.command()
def import_data(
    file_path: str = typer.Argument(..., help="要导入的文件路径"),
    merge: bool = typer.Option(True, "--merge/--replace", help="合并还是替换现有数据"),
):
    """导入记忆数据"""
    config = get_config()
    from .memory.migration import MemoryImporter
    importer = MemoryImporter(config)

    stats = importer.import_from_file(file_path, merge=merge)

    table = Table(title="导入结果")
    table.add_column("项目", style="cyan")
    table.add_column("数量", style="green")
    table.add_row("记忆", str(stats.get("memories_imported", 0)))
    table.add_row("Wiki 页面", str(stats.get("wiki_pages_imported", 0)))
    table.add_row("实体", str(stats.get("entities_imported", 0)))
    console.print(table)


@app.command()
def backup(
    label: str = typer.Option(None, help="备份标签"),
):
    """创建备份快照"""
    config = get_config()
    from .memory.migration import BackupManager
    manager = BackupManager(config)

    path = manager.create_backup(label=label)
    console.print(f"[green]备份已创建: {path}[/green]")


@app.command()
def list_backups():
    """列出所有备份"""
    config = get_config()
    from .memory.migration import BackupManager
    manager = BackupManager(config)

    backups = manager.list_backups()
    if not backups:
        console.print("[yellow]暂无备份[/yellow]")
        return

    table = Table(title="备份列表")
    table.add_column("名称", style="cyan")
    table.add_column("大小 (MB)", style="green")
    table.add_column("创建时间", style="dim")

    for b in backups:
        table.add_row(b["name"], str(b["size_mb"]), b["created_at"])

    console.print(table)


@app.command()
def restore(
    backup_name: str = typer.Argument(..., help="备份名称"),
    merge: bool = typer.Option(False, "--merge", help="合并模式"),
):
    """从备份恢复"""
    config = get_config()
    from .memory.migration import BackupManager
    manager = BackupManager(config)

    result = manager.restore_backup(backup_name, merge=merge)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
    else:
        console.print(f"[green]已恢复: {result}[/green]")


# ── 聚类 ──

@app.command()
def cluster(
    wing: str = typer.Option(None, help="限定 Wing"),
    n_clusters: int = typer.Option(0, help="目标聚类数（0=自动）"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """将记忆自动聚类为主题分组"""
    config = get_config()
    from .memory.clustering import MemoryClusterer
    clusterer = MemoryClusterer(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    if wing:
        drawers = [d for d in drawers if d.wing == wing]

    clusters = clusterer.cluster(drawers, n_clusters=n_clusters)
    stats = clusterer.cluster_stats(clusters)

    if json_output:
        result = {"stats": stats, "clusters": [
            {"id": c.id, "label": c.label, "keywords": c.keywords,
             "size": c.size, "cohesion": c.cohesion, "memory_ids": c.memory_ids[:5]}
            for c in clusters
        ]}
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]聚类统计:[/bold] {stats['total_clusters']} 个聚类, "
                  f"平均内聚度 {stats['avg_cohesion']}, 平均大小 {stats['avg_size']}\n")

    table = Table(title="记忆聚类")
    table.add_column("标签", style="cyan")
    table.add_column("关键词", style="green")
    table.add_column("大小", style="yellow")
    table.add_column("内聚度", style="magenta")

    for c in clusters:
        table.add_row(c.label, ", ".join(c.keywords[:3]), str(c.size), str(c.cohesion))

    console.print(table)


@app.command()
def conflicts(
    wing: str = typer.Option(None, help="限定 Wing"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """检测记忆中的矛盾和不一致"""
    config = get_config()
    from .memory.conflict import ConflictDetector
    detector = ConflictDetector(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    if wing:
        drawers = [d for d in drawers if d.wing == wing]

    conflicts = detector.detect_conflicts(drawers)

    if json_output:
        console.print(json.dumps([
            {"id": c.id, "memory_a": c.memory_a, "memory_b": c.memory_b,
             "content_a": c.content_a[:100], "content_b": c.content_b[:100],
             "description": c.description, "severity": c.severity.value,
             "confidence": c.confidence, "suggestion": detector.resolve_suggestion(c)}
            for c in conflicts
        ], ensure_ascii=False, indent=2))
        return

    if not conflicts:
        console.print("[green]未发现冲突[/green]")
        return

    severity_colors = {"critical": "red", "major": "yellow", "minor": "cyan", "potential": "dim"}
    console.print(f"\n[bold]发现 {len(conflicts)} 个冲突:[/bold]\n")

    for c in conflicts:
        color = severity_colors.get(c.severity.value, "white")
        console.print(f"[{color}]●[/{color}] [bold]{c.severity.value.upper()}[/bold] "
                      f"(置信度: {c.confidence:.2f})")
        console.print(f"  A: {c.content_a[:80]}...")
        console.print(f"  B: {c.content_b[:80]}...")
        console.print(f"  → {detector.resolve_suggestion(c)}\n")


@app.command()
def dedup(
    threshold: float = typer.Option(0.85, help="相似度阈值"),
    method: str = typer.Option("auto", help="方法: auto, vector, hash, keyword"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示，不实际合并"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """检测并合并重复记忆"""
    config = get_config()
    from .memory.dedup import MemoryDeduplicator
    deduper = MemoryDeduplicator(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    groups = deduper.find_duplicates(drawers, threshold=threshold, method=method)
    stats = deduper.dedup_stats(groups)

    if json_output:
        console.print(json.dumps({"stats": stats, "groups": [
            {"id": g.id, "primary_id": g.primary_id, "duplicate_ids": g.duplicate_ids,
             "avg_similarity": g.avg_similarity} for g in groups
        ]}, ensure_ascii=False, indent=2))
        return

    if not groups:
        console.print("[green]未发现重复记忆[/green]")
        return

    console.print(f"\n[bold]发现 {stats['duplicate_groups']} 组重复记忆, "
                  f"共 {stats['total_duplicate_memories']} 条可合并[/bold]\n")

    merged_count = 0
    for g in groups:
        console.print(f"[cyan]●[/cyan] 组 {g.id}: 主记忆={g.primary_id}, "
                      f"重复={g.duplicate_ids}, 相似度={g.avg_similarity:.4f}")
        if not dry_run:
            merged = deduper.merge_duplicates(g, drawers)
            if merged:
                memory.remove_drawers(g.duplicate_ids)
                memory.add_drawer(merged)
                merged_count += len(g.duplicate_ids)

    if not dry_run and merged_count:
        console.print(f"\n[green]已合并 {merged_count} 条重复记忆[/green]")


@app.command()
def analyze(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """生成全面记忆分析报告"""
    config = get_config()
    from .memory.analytics import MemoryAnalyzer
    analyzer = MemoryAnalyzer(config)
    memory = MemoryStack(config)
    wiki = WikiEngine(config)
    drawers = memory.get_drawers()
    wiki_count = wiki.stats().get("total_pages", 0)

    analysis = analyzer.analyze(drawers, wiki_page_count=wiki_count)

    if json_output:
        console.print(json.dumps(analysis.__dict__, ensure_ascii=False, indent=2))
        return

    report = analyzer.summary_report(analysis)
    console.print(report)


@app.command()
def health():
    """检查记忆系统健康度"""
    config = get_config()
    from .memory.analytics import MemoryAnalyzer
    analyzer = MemoryAnalyzer(config)
    memory = MemoryStack(config)
    wiki = WikiEngine(config)
    drawers = memory.get_drawers()
    wiki_count = wiki.stats().get("total_pages", 0)

    analysis = analyzer.analyze(drawers, wiki_page_count=wiki_count)

    # 健康度颜色
    if analysis.health_score >= 80:
        color = "green"
    elif analysis.health_score >= 50:
        color = "yellow"
    else:
        color = "red"

    console.print(Panel.fit(
        f"[bold {color}]健康评分: {analysis.health_score}/100[/bold {color}]\n\n" +
        ("[问题]\n" + "\n".join(f"  - {i}" for i in analysis.health_issues) + "\n\n"
         if analysis.health_issues else "") +
        ("[建议]\n" + "\n".join(f"  - {r}" for r in analysis.recommendations)
         if analysis.recommendations else ""),
        title="盘古健康检查",
    ))


# ── 时间线 ──

@app.command()
def timeline(
    wing: str = typer.Option(None, help="限定 Wing"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """构建记忆时间线"""
    config = get_config()
    from .memory.timeline import TimelineEngine
    engine = TimelineEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    events = engine.build_timeline(drawers, wing=wing)
    stats = engine.timeline_stats(events)

    if json_output:
        console.print(json.dumps({"stats": stats, "events": [
            {"id": e.drawer_id, "content": e.content[:150], "timestamp": e.timestamp,
             "wing": e.wing, "room": e.room}
            for e in events[:30]
        ]}, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]时间线:[/bold] {stats['total_events']} 个事件, "
                  f"跨度 {stats['span_days']} 天, 日均 {stats['events_per_day']} 条\n")

    table = Table(title="记忆时间线")
    table.add_column("时间", style="dim")
    table.add_column("位置", style="cyan")
    table.add_column("内容", style="green")
    table.add_column("重要性", style="yellow")

    for e in events[:20]:
        table.add_row(e.timestamp[:16], f"{e.wing}/{e.room}",
                      e.content[:80], f"{e.importance:.1f}")

    console.print(table)


@app.command()
def causal(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """发现记忆间的因果关系"""
    config = get_config()
    from .memory.timeline import TimelineEngine
    engine = TimelineEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    events = engine.build_timeline(drawers)
    links = engine.find_causal_links(events)

    if json_output:
        console.print(json.dumps([
            {"source_id": link.source_id, "target_id": link.target_id,
             "confidence": link.confidence, "reason": link.reason}
            for link in links[:20]
        ], ensure_ascii=False, indent=2))
        return

    if not links:
        console.print("[yellow]未发现因果关系[/yellow]")
        return

    console.print(f"\n[bold]发现 {len(links)} 条因果关联:[/bold]\n")
    for link in links[:10]:
        color = "green" if link.confidence >= 0.8 else "yellow" if link.confidence >= 0.5 else "dim"
        console.print(f"[{color}]●[/{color}] [{link.confidence:.2f}] {link.reason}")


@app.command()
def event_chains(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """构建事件链"""
    config = get_config()
    from .memory.timeline import TimelineEngine
    engine = TimelineEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    events = engine.build_timeline(drawers)
    chains = engine.build_event_chain(events)

    if json_output:
        console.print(json.dumps({
            "total_chains": len(chains),
            "chains": [{"id": c.id, "span": c.span, "summary": c.summary,
                        "event_count": len(c.events)} for c in chains]
        }, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]事件链: {len(chains)} 条[/bold]\n")
    for c in chains[:10]:
        console.print(f"[cyan]●[/cyan] {c.span}: {c.summary[:120]}...")


# ── 融合 ──

@app.command()
def fuse(
    topic: str = typer.Argument(..., help="主题关键词"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """融合同一主题的记忆"""
    config = get_config()
    from .memory.fusion import FusionEngine
    engine = FusionEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    fused = engine.fuse_topic(topic, drawers)

    if json_output and fused:
        console.print(json.dumps({
            "id": fused.id, "topic": fused.topic, "summary": fused.summary,
            "key_points": fused.key_points, "confidence": fused.confidence,
        }, ensure_ascii=False, indent=2))
    elif fused:
        console.print(Panel.fit(
            f"[bold]{fused.topic}[/bold] (置信度: {fused.confidence:.2f})\n\n"
            f"{fused.summary}\n\n"
            f"[bold]关键要点:[/bold]\n" +
            "\n".join(f"  - {p}" for p in fused.key_points[:5]),
            title="融合理解",
        ))
    else:
        console.print(f"[yellow]未找到与 '{topic}' 相关的记忆[/yellow]")


@app.command()
def crystallize(
    topic: str = typer.Option("", help="限定主题"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """从记忆中结晶可复用知识"""
    config = get_config()
    from .memory.fusion import FusionEngine
    engine = FusionEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    knowledge = engine.crystallize_knowledge(drawers, topic=topic)

    if json_output:
        console.print(json.dumps(knowledge, ensure_ascii=False, indent=2))
        return

    console.print(Panel.fit(
        f"[bold]知识结晶[/bold]\n\n"
        f"事实: {len(knowledge['facts'])} 条\n"
        f"教训: {len(knowledge['lessons'])} 条\n"
        f"决策: {len(knowledge['decisions'])} 条\n"
        f"模式: {len(knowledge['patterns'])} 条",
        title="盘古知识结晶",
    ))


# ── 模式 ──

@app.command()
def patterns(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """发现记忆中的隐藏模式"""
    config = get_config()
    from .memory.patterns import PatternEngine
    engine = PatternEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    patterns = engine.discover_all(drawers)
    stats = engine.pattern_stats(patterns)
    insights = engine.pattern_insights(patterns)

    if json_output:
        console.print(json.dumps({"stats": stats, "insights": insights, "patterns": [
            {"id": p.id, "type": p.pattern_type, "description": p.description,
             "confidence": p.confidence} for p in patterns[:20]
        ]}, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]发现 {stats['total_patterns']} 个模式[/bold]\n")
    for insight in insights:
        console.print(f"  [cyan]●[/cyan] {insight}")

    if patterns:
        console.print()
        table = Table(title="模式详情")
        table.add_column("类型", style="cyan")
        table.add_column("描述", style="green")
        table.add_column("置信度", style="yellow")

        for p in patterns[:10]:
            table.add_row(p.pattern_type, p.description[:80], f"{p.confidence:.2f}")

        console.print(table)


# ── 回放 ──

@app.command()
def replay(
    topic: str = typer.Option(None, help="主题回放"),
    wing: str = typer.Option(None, help="限定 Wing"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """回放记忆（时间线 / 主题 / 精彩集锦）"""
    config = get_config()
    from .memory.replay import ReplayEngine
    engine = ReplayEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    if topic:
        session = engine.topic_replay(topic, drawers)
    else:
        session = engine.timeline_replay(drawers, wing=wing)

    if json_output:
        console.print(json.dumps({
            "id": session.id, "title": session.title, "span": session.span,
            "event_count": session.event_count, "wings": session.wings,
            "key_moments": [{"time": m["time"][:16], "content": m["content"][:100]}
                            for m in session.key_moments[:5]],
        }, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]{session.title}[/bold]: {session.span}\n")

    if session.key_moments:
        console.print("[bold]关键时刻:[/bold]")
        for i, m in enumerate(session.key_moments, 1):
            console.print(f"  [cyan]{i}.[/cyan] [{m['time'][:16]}] {m['content'][:100]}")

    if session.events:
        console.print(f"\n[bold]事件列表 ({session.event_count} 条):[/bold]")
        for i, e in enumerate(session.events[:15], 1):
            change = e.get("change", "")
            marker = f"[yellow][{change}][/yellow] " if change else ""
            console.print(f"  [dim]{i}.[/dim] [{e['time'][:16]}] {marker}{e['content'][:80]}")


@app.command()
def highlights(
    top_n: int = typer.Option(10, help="返回数量"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """提取最重要的记忆时刻（精彩集锦）"""
    config = get_config()
    from .memory.replay import ReplayEngine
    engine = ReplayEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    session = engine.highlight_reel(drawers, top_n=top_n)

    if json_output:
        console.print(json.dumps({
            "id": session.id, "title": session.title,
            "highlights": [{"time": m["time"][:16], "content": m["content"][:100],
                            "importance": m["importance"]}
                           for m in session.key_moments],
        }, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]精彩集锦[/bold] ({len(session.key_moments)} 个高光时刻)\n")
    for i, m in enumerate(session.key_moments, 1):
        stars = "★" * min(5, int(m["importance"]))
        console.print(f"  [cyan]{i}.[/cyan] [{m['time'][:10]}] {stars} {m['content'][:100]}")


# ── 多模态 ──

@app.command()
def mm_extract(
    path: str = typer.Argument(..., help="文件或目录路径"),
    wing: str = typer.Option("default", help="归属 Wing"),
    recursive: bool = typer.Option(True, help="递归扫描目录"),
    tags: str = typer.Option("", help="标签，逗号分隔"),
):
    """从文件中提取多模态记忆"""
    from .memory.multimodal import MultimodalExtractor
    extractor = MultimodalExtractor()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    if os.path.isdir(path):
        console.print(f"[cyan]正在扫描目录: {path}...[/cyan]")
        memories = extractor.extract_from_directory(path, wing=wing, recursive=recursive, tags=tag_list)
    else:
        memory = extractor.extract_from_file(path, wing=wing, tags=tag_list)
        memories = [memory]

    if not memories:
        console.print("[yellow]未发现支持的文件[/yellow]")
        return

    table = Table(title=f"多模态记忆提取 ({len(memories)} 条)")
    table.add_column("模态", style="cyan")
    table.add_column("文件", style="green")
    table.add_column("大小", style="dim")
    table.add_column("描述", style="yellow")

    for mm in memories:
        size_mb = mm.file_size / (1024 * 1024)
        table.add_row(mm.modality, mm.file_name, f"{size_mb:.1f}MB", mm.content[:80])

    console.print(table)


# ── 伏羲移植：FTS5 混合搜索 ──

@app.command()
def fts_search(
    query: str = typer.Argument(..., help="搜索查询"),
    wing: str = typer.Option(None, help="限定 Wing"),
    room: str = typer.Option(None, help="限定 Room"),
    limit: int = typer.Option(10, help="返回数量"),
    vector_weight: float = typer.Option(None, help="向量权重 (0-1)"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """FTS5全文+向量混合搜索(RRF融合)"""
    config = get_config()
    engine = FTS5SearchEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    engine.build_index(drawers)

    result = engine.search(
        query=query, drawers=drawers, wing=wing, room=room,
        limit=limit, vector_weight=vector_weight,
    )

    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not result["results"]:
        console.print(f"[yellow]未找到与 '{query}' 相关的结果[/yellow]")
        return

    console.print(f"\n[bold]搜索: '{query}'[/bold] ({result['method']}, {result['total']} 条)\n")
    for i, r in enumerate(result["results"], 1):
        content = r.get("content", "")[:120]
        score = r.get("search_score", "N/A")
        console.print(f"[cyan][{i}][/cyan] [{r['wing']}/{r['room']}] score={score}")
        console.print(f"    {content}...\n")


@app.command()
def fts_stats(json_output: bool = typer.Option(False, "--json", help="JSON 格式输出")):
    """获取搜索引擎统计"""
    stats = get_search_stats()
    if json_output:
        console.print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    console.print("[bold]搜索统计:[/bold]")
    for k, v in stats.items():
        console.print(f"  {k}: {v}")


# ── 伏羲移植：全息记忆 ──

@app.command()
def holo_encode(
    text: str = typer.Argument(..., help="要编码的文本"),
    wing: str = typer.Option("", help="归属 Wing"),
    room: str = typer.Option("", help="归属 Room"),
    causal: str = typer.Option("", help="因果摘要"),
    source: str = typer.Option("", help="来源类型"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """将记忆编码为全息投影（5维）"""
    config = get_config()
    encoder = get_holographic_encoder(config)
    holo = encoder.encode(
        item_id=f"cli_{os.urandom(4).hex()}",
        raw_text=text, wing=wing, room=room,
        causal_summary=causal, source_type=source,
    )
    if json_output:
        console.print(json.dumps({
            "item_id": holo.item_id, "dimensions": holo.all_dims(),
            "byte_size": holo.byte_size,
        }, ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]编码完成:[/green] {len(holo.all_dims())} 维度, {holo.byte_size} bytes")


@app.command()
def holo_search(
    query: str = typer.Argument(..., help="搜索查询"),
    top_k: int = typer.Option(10, help="返回数量"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """全息跨维度融合检索"""
    config = get_config()
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    results = holographic_search(query, drawers, top_k=top_k)

    if json_output:
        console.print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        console.print(f"[yellow]未找到与 '{query}' 相关的结果[/yellow]")
    else:
        console.print(f"\n[bold]全息搜索: '{query}'[/bold] ({len(results)} 条)\n")
        for i, r in enumerate(results, 1):
            console.print(f"[cyan][{i}][/cyan] [{r['wing']}/{r['room']}] score={r['holographic_score']}")
            console.print(f"    {r['content'][:120]}...\n")


# ── 伏羲移植：记忆法官 ──

@app.command()
def judge(
    task_type: str = typer.Option(..., help="任务类型"),
    description: str = typer.Option(..., help="任务描述"),
    summary: str = typer.Option(..., help="产出摘要"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """LLM判断记忆价值(A/B/C三级分类)"""
    config = get_config()
    judge_engine = get_memory_judge(config)
    result = judge_engine.evaluate(
        task_type=task_type, task_description=description,
        output_summary=summary,
    )
    if json_output:
        console.print(json.dumps({
            "verdict": result.verdict.value, "reasoning": result.reasoning,
            "confidence": result.confidence, "suggested_tags": result.suggested_tags,
            "suggested_importance": result.suggested_importance,
        }, ensure_ascii=False, indent=2))
    else:
        verdict_color = {"A": "green", "B": "yellow", "C": "red"}.get(result.verdict.value, "white")
        console.print(Panel.fit(
            f"[bold {verdict_color}]判定: {result.verdict.value}[/bold {verdict_color}]\n"
            f"理由: {result.reasoning}\n"
            f"置信度: {result.confidence:.2f}\n"
            f"建议重要性: {result.suggested_importance}\n"
            f"建议标签: {result.suggested_tags}",
            title="记忆法官",
        ))


@app.command()
def judge_stats(json_output: bool = typer.Option(False, "--json", help="JSON 格式输出")):
    """获取判断统计"""
    config = get_config()
    judge_engine = get_memory_judge(config)
    stats = judge_engine.stats()
    if json_output:
        console.print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        console.print(f"总判断: {stats['total']}, A: {stats['A']}, B: {stats['B']}, C: {stats['C']}")


# ── 伏羲移植：自适应参数 ──

@app.command()
def adaptive_params(
    reset: bool = typer.Option(False, "--reset", help="重置为默认参数"),
    history: bool = typer.Option(False, "--history", help="显示调整历史"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """获取/调整自适应参数"""
    config = get_config()
    engine = get_adaptive_engine(config)

    if reset:
        engine.reset()
        console.print("[green]参数已重置为默认值[/green]")
        return

    if history:
        hist = engine.get_history()
        console.print(json.dumps(hist, ensure_ascii=False, indent=2) if json_output
                      else "\n".join(f"{h['ts'][:16]}: {h['reasons']}" for h in hist))
        return

    params = engine.get_params()
    if json_output:
        console.print(json.dumps(params.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print("[bold]自适应参数:[/bold]")
        for k, v in params.to_dict().items():
            console.print(f"  {k}: {v}")


@app.command()
def adaptive_evaluate(
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """根据系统统计评估并调整参数"""
    config = get_config()
    engine = get_adaptive_engine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    stats = {
        "total_memories": len(drawers),
        "growth_rate": 0, "duplicate_rate": 0,
        "forget_rate": 0, "avg_search_score": 0.5,
    }
    params = engine.evaluate(stats)
    if json_output:
        console.print(json.dumps(params.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[{'green' if params.update_reason != 'no_change' else 'yellow'}]"
                      f"更新: {params.update_reason}[/]")


# ── 伏羲移植：工作记忆 ──

@app.command()
def wm_push(
    content: str = typer.Argument(..., help="内容"),
    item_id: str = typer.Option(None, help="记忆项 ID"),
    valence: float = typer.Option(0.0, help="情感值 (-1.0~1.0)"),
    urgency: float = typer.Option(0.0, help="紧迫度 (0.0~1.0)"),
):
    """推入工作记忆项"""
    wm = get_working_memory()
    item = WMItem(
        id=item_id or f"wm_cli_{os.urandom(4).hex()}",
        content=content, emotional_valence=valence,
        urgency=urgency, tokens=len(content) // 4,
    )
    evicted = wm.push(item)
    console.print(f"[green]已推入: {item.id[:16]}[/green] (槽位: {len(wm.slots)})")
    if evicted:
        console.print(f"[yellow]驱逐: {evicted.id[:16]}[/yellow]")


@app.command()
def wm_get(
    item_id: str = typer.Option(None, help="记忆项 ID"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """获取工作记忆项"""
    wm = get_working_memory()
    if item_id:
        item = wm.get(item_id)
        if item:
            console.print(json.dumps({"id": item.id, "content": item.content[:200],
                                        "activation": item.activation}, ensure_ascii=False, indent=2)
                          if json_output else f"[{item.id[:16]}] 激活度={item.activation:.4f}: {item.content[:120]}")
        else:
            console.print("[red]未找到[/red]")
    else:
        focus = wm.focus
        if focus:
            console.print(f"[bold]焦点:[/bold] [{focus.id[:16]}] {focus.content[:120]}")
        console.print(f"槽位使用: {len(wm.slots)}/{wm.capacity}")


@app.command()
def wm_stats(json_output: bool = typer.Option(False, "--json", help="JSON 格式输出")):
    """获取工作记忆统计"""
    wm = get_working_memory()
    stats = wm.stats
    if json_output:
        console.print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        console.print(f"容量: {stats['capacity']}, 使用: {stats['slots_used']}, "
                      f"驱逐: {stats['evictions']}, Token: {stats['token_usage_pct']}%")


@app.command()
def wm_clear():
    """清空工作记忆"""
    wm = get_working_memory()
    wm.clear()
    console.print("[green]工作记忆已清空[/green]")


# ── 伏羲移植：记忆脱敏 ──

@app.command()
def sanitize(
    text: str = typer.Argument(..., help="要脱敏的文本"),
    level: str = typer.Option("standard", help="脱敏级别: minimal/standard/strict"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """脱敏记忆内容"""
    sanitized, redactions = MemorySanitizer.sanitize(text, level=level)
    if json_output:
        console.print(json.dumps({"sanitized": sanitized, "redactions": redactions,
                                   "total": sum(redactions.values())}, ensure_ascii=False, indent=2))
    else:
        console.print(f"[bold]脱敏结果 ({level}):[/bold]")
        console.print(f"  脱敏项: {sum(redactions.values())} ({redactions})")
        console.print(f"  {sanitized[:200]}")


# ── 伏羲移植：再巩固 + 共鸣 ──

@app.command()
def reconsolidate(
    min_importance: float = typer.Option(0.3, help="最低重要性"),
    max_importance: float = typer.Option(0.7, help="最高重要性"),
    limit: int = typer.Option(20, help="处理上限"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """再巩固记忆（刷新衰减分数）"""
    config = get_config()
    engine = ReconsolidationEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    result = engine.run(drawers, min_importance=min_importance,
                        max_importance=max_importance, limit=limit)
    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]再巩固: {result['boosted']}/{result['candidates']} 条提升[/green]")


@app.command()
def resonance(
    cross_wing: bool = typer.Option(False, "--cross-wing", help="跨 Wing 共鸣"),
    sim_threshold: float = typer.Option(0.7, help="相似度阈值"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """发现情感/语义共鸣的记忆对"""
    config = get_config()
    engine = ResonanceEngine(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    if cross_wing:
        matches = engine.find_cross_wing_resonance(drawers, sim_threshold=sim_threshold)
    else:
        matches = engine.find_resonance(drawers, sim_threshold=sim_threshold)

    if json_output:
        console.print(json.dumps(matches, ensure_ascii=False, indent=2))
    elif matches:
        console.print(f"\n[bold]发现 {len(matches)} 对共鸣:[/bold]\n")
        for m in matches:
            console.print(f"[cyan]●[/cyan] 相似度={m['similarity']}")
            console.print(f"  [{m.get('source_wing', m.get('wing', '?'))}] {m['source_content'][:60]}...")
            console.print(f"  [{m.get('target_wing', '?')}] {m['target_content'][:60]}...\n")
    else:
        console.print("[yellow]未发现共鸣[/yellow]")


# ── 伏羲移植：知识蒸馏增强 ──

@app.command()
def distill(
    texts: list[str] | None = None,
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """从记忆中蒸馏结构化知识卡片"""
    config = get_config()
    tower = DistillationTower(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    if texts is None:
        texts = [d.content for d in drawers[:10]]

    card = tower.distill(texts)
    if json_output:
        console.print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        kc = card.get("knowledge_card", {})
        console.print(Panel.fit(
            f"[bold]{kc.get('concept', '')}[/bold]\n"
            f"原理: {kc.get('principle', '')}\n"
            f"置信度: {kc.get('confidence', 0)}",
            title="知识卡片",
        ))


@app.command()
def causal_chains(json_output: bool = typer.Option(False, "--json", help="JSON 格式输出")):
    """提取所有因果链"""
    config = get_config()
    tower = DistillationTower(config)
    chains = tower.get_causal_chains()
    if json_output:
        console.print(json.dumps(chains, ensure_ascii=False, indent=2))
    elif chains:
        for c in chains:
            console.print(f"[cyan]●[/cyan] {c['concept']}: {c['causal_link']}")
    else:
        console.print("[yellow]无因果链[/yellow]")


# ── 伏羲移植：向量索引 ──

@app.command()
def vector_index(
    build: bool = typer.Option(False, "--build", help="构建索引"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """向量索引管理"""
    config = get_config()
    idx = get_vector_index()

    if build:
        from .search.embedder import VectorEmbedder
        embedder = VectorEmbedder(config)
        memory = MemoryStack(config)
        drawers = memory.get_drawers()
        success = idx.build_from_drawers(drawers, embedder=embedder)
        console.print(f"[{'green' if success else 'yellow'}]{'已构建' if success else '跳过'}[/]")
    else:
        stats = idx.stats()
        if json_output:
            console.print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            console.print(f"已构建: {stats['is_built']}, 大小: {stats['size']}, 内存: {stats['memory_mb']}MB")


# ── 伏羲移植：注意力系统 ──

@app.command()
def attention(
    switch: str = typer.Option(None, help="切换策略: bottom_up/focus/explore/emotion/urgency"),
    ab_test: str = typer.Option(None, help="A/B测试: strategy_a,strategy_b"),
    stop_ab: bool = typer.Option(False, "--stop-ab", help="停止A/B测试"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """注意力系统管理"""
    attn = get_attention_system()

    if stop_ab:
        result = attn.stop_ab_test()
        console.print(json.dumps(result, ensure_ascii=False, indent=2) if json_output
                      else f"胜者: {result.get('winner', 'N/A')}")
        return

    if switch:
        try:
            strategy = AttentionStrategy(switch)
        except ValueError:
            console.print(f"[red]无效策略: {switch}, 可选: {[s.value for s in AttentionStrategy]}[/red]")
            return
        old, new = attn.switch(strategy)
        console.print(f"[green]{old.value} → {new.value}[/green]")
        return

    if ab_test:
        parts = ab_test.split(",")
        if len(parts) == 2:
            try:
                sa = AttentionStrategy(parts[0].strip())
                sb = AttentionStrategy(parts[1].strip())
            except ValueError:
                console.print("[red]无效策略名[/red]")
                return
            attn.start_ab_test(sa, sb)
            console.print(f"[green]A/B测试启动: {sa.value} vs {sb.value}[/green]")
        return

    stats = attn.stats
    if json_output:
        console.print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        console.print(f"活跃策略: {stats['active_strategy']}, 预算: {stats['budget']}")


# ── 伏羲移植：增强评估 ──

@app.command()
def enhanced_contradictions(
    top_k: int = typer.Option(50, help="检查的记忆对数"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """LLM驱动矛盾检测（6种裁决）"""
    config = get_config()
    detector = EnhancedContradictionDetector(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    result = detector.detect_contradictions(drawers, top_k=top_k)
    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        stats = result.get("stats", {})
        console.print(f"总对: {stats.get('total_pairs', 0)}, "
                      f"矛盾: {stats.get('contradiction', 0)}, "
                      f"回归: {stats.get('temporal_regression', 0)}")


@app.command()
def trajectory(
    wing: str = typer.Option(None, help="限定 Wing"),
    period_a: str = typer.Option(None, help="对比时间段A (YYYY-MM-DD)"),
    period_b: str = typer.Option(None, help="对比时间段B (YYYY-MM-DD)"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """追踪记忆时间轨迹"""
    config = get_config()
    tracker = TrajectoryTracker(config)
    memory = MemoryStack(config)
    drawers = memory.get_drawers()

    if period_a and period_b:
        result = tracker.compare_periods(drawers, period_a, period_b)
    else:
        result = tracker.track(drawers, wing=wing)

    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print(f"事件: {result.get('total_events', 0)}, "
                      f"回归: {result.get('regression_count', 0)}")


# ── 伏羲移植：流式索引 ──

@app.command()
def streaming_index(
    merge: bool = typer.Option(False, "--merge", help="合并 WAL"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """增量索引管理"""
    config = get_config()
    memory = MemoryStack(config)
    drawers = memory.get_drawers()
    indexer = StreamingIndexer(config)

    if merge:
        count = indexer.merge_wal()
        console.print(f"[green]WAL合并: {count} 条[/green]")
    else:
        from .search.embedder import VectorEmbedder
        embedder = VectorEmbedder(config)
        result = indexer.index(drawers, embedder=embedder)
        if json_output:
            console.print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            console.print(f"扫描: {result['scanned']}, 索引: {result['indexed']}")


# ── 伏羲移植：验证循环 ──

@app.command()
def verify(
    phase: str = typer.Option(None, help="单阶段: build/type_check/lint/tests/security/diff_review"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """运行验证循环"""
    loop = VerificationLoop()

    if phase:
        phase_map = {
            "build": loop.run_build, "type_check": loop.run_type_check,
            "lint": loop.run_lint, "tests": loop.run_tests,
            "security": loop.run_security_scan, "diff_review": loop.run_diff_review,
        }
        if phase in phase_map:
            result = phase_map[phase]()
            console.print(f"[{'green' if result.passed else 'red'}]{phase}: {'PASS' if result.passed else 'FAIL'}[/]")
            if result.output:
                console.print(result.output[:500])
        else:
            console.print(f"[red]未知阶段: {phase}[/red]")
    else:
        result = loop.run_full_verification()
        if json_output:
            console.print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for name, data in result.items():
                if isinstance(data, dict) and "passed" in data:
                    color = "green" if data["passed"] else "red"
                    console.print(f"[{color}]{name}: {'PASS' if data['passed'] else 'FAIL'}[/{color}]")


# ── 伏羲移植：差分隐私 ──

@app.command()
def privacy(
    count: int = typer.Option(None, help="隐私化计数"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """差分隐私管理"""
    dp = DifferentialPrivacy()

    if count is not None:
        result = dp.privatize_count(count)
        console.print(f"原始: {count} → 隐私化: {result}")
    else:
        stats = dp.stats()
        if json_output:
            console.print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            console.print(f"预算: {stats['remaining_budget']}/{stats['total_budget']} "
                          f"({stats['budget_usage_pct']}%), 查询: {stats['query_count']}")


# ── 伏羲移植：系统健康 ──

@app.command()
def system_health(
    deep: bool = typer.Option(False, "--deep", help="深度检查"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """系统健康检查"""
    from .observability.health import deep_health_check, quick_health_check
    result = deep_health_check() if deep else quick_health_check()
    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print(f"[{'green' if result['status'] == 'ok' else 'yellow'}]"
                      f"状态: {result['status']}, 运行: {result['uptime_seconds']}s[/]")


@app.command()
def system_metrics():
    """获取 Prometheus 格式系统指标"""
    from .observability.metrics import get_metrics_response
    content, _ = get_metrics_response()
    if isinstance(content, bytes):
        content = content.decode()
    console.print(content[:2000])


# ── ONNX 加速嵌入 ──

@app.command()
def onnx_embed(
    text: str = typer.Argument(..., help="要嵌入的文本"),
    show_vec: bool = typer.Option(False, "--vec", help="显示完整向量"),
):
    """使用 ONNX 本地推理嵌入单条文本（CPU 加速 3-10x）"""
    from .memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    vec = emb.embed(text)
    if vec is None:
        console.print("[red]ONNX 嵌入失败（依赖缺失或模型下载失败）[/red]")
        raise typer.Exit(1)
    console.print("[green]✓ ONNX 嵌入成功[/green]")
    console.print(f"  文本: {text}")
    console.print(f"  维度: {len(vec)}")
    console.print(f"  模型: {emb.model_id} (quantized={emb.quantized})")
    console.print(f"  来源: {'onnx' if emb.is_loaded else 'unavailable'}")
    if show_vec:
        console.print(f"  向量: {vec}")
    else:
        console.print(f"  前 5 维: {vec[:5]}")


@app.command()
def onnx_embed_batch(
    texts: list[str] = typer.Argument(..., help="要嵌入的多条文本"),  # noqa: B008
):
    """ONNX 批量嵌入多条文本"""
    from .memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    import time
    start = time.time()
    results = emb.embed_batch(texts)
    elapsed_ms = (time.time() - start) * 1000
    if not results or any(r is None for r in results):
        console.print("[red]部分或全部 ONNX 嵌入失败[/red]")
        raise typer.Exit(1)
    console.print("[green]✓ ONNX 批量嵌入成功[/green]")
    console.print(f"  数量: {len(results)}")
    console.print(f"  维度: {emb.embedding_dim}")
    console.print(f"  耗时: {elapsed_ms:.1f}ms ({elapsed_ms/len(results):.1f}ms/条)")


@app.command()
def onnx_status():
    """查看 ONNX 嵌入器状态（模型/缓存/性能）"""
    from .memory.embedding import get_embedding_service
    svc = get_embedding_service()
    console.print_json(json.dumps(svc.stats, ensure_ascii=False, indent=2, default=str))


@app.command()
def onnx_similarity(
    text_a: str = typer.Argument(..., help="第一条文本"),
    text_b: str = typer.Argument(..., help="第二条文本"),
):
    """使用 ONNX 计算两条文本的余弦相似度"""
    import math

    from .memory.onnx_embedder import get_onnx_embedder
    emb = get_onnx_embedder()
    va = emb.embed(text_a)
    vb = emb.embed(text_b)
    if va is None or vb is None:
        console.print("[red]ONNX 嵌入失败[/red]")
        raise typer.Exit(1)
    dot = sum(x * y for x, y in zip(va, vb, strict=False))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    sim = dot / (na * nb + 1e-9)
    console.print(f"[cyan]文本 A:[/cyan] {text_a}")
    console.print(f"[cyan]文本 B:[/cyan] {text_b}")
    console.print(f"[green]余弦相似度: {sim:.4f}[/green]")


# ── 服务 ──

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="绑定地址"),
    port: int = typer.Option(8866, help="绑定端口"),
    reload: bool = typer.Option(False, help="自动重载"),
):
    """启动 Web 服务器"""
    import uvicorn

    console.print(Panel.fit(
        f"[bold green]盘古 Web 服务器启动[/bold green]\n\n"
        f"地址: [bold cyan]http://{host}:{port}[/bold cyan]\n"
        f"API 文档: [bold cyan]http://{host}:{port}/docs[/bold cyan]",
        title="盘古",
    ))

    uvicorn.run(
        "pangu.server.web_server:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command()
def mcp():
    """启动 MCP 服务器 (stdio)"""
    from .server.mcp_server import MCPServer
    from rich.console import Console as RichConsole

    config = get_config()
    config.ensure_dirs()
    server = MCPServer(config)

    RichConsole(file=sys.stderr).print("[cyan]盘古 MCP 服务器启动 (stdio)[/cyan]")
    asyncio.run(server.run_stdio())


# ── 身份 ──

@app.command()
def identity(
    text: str = typer.Option(None, "--set", help="设置身份文本"),
):
    """查看或设置 AI 身份"""
    config = get_config()
    memory = MemoryStack(config)

    if text:
        memory.l0.set_identity(text)
        console.print("[green]身份已设置[/green]")
    else:
        console.print(Markdown(memory.l0.render()))


# ── LLM 缓存管理 ──

@app.command(name="llm-cache-stats")
def llm_cache_stats():
    """查看 LLM 响应缓存统计（内存+持久化）"""
    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    cfg = PanguConfig()
    engine = LLMEngine(cfg)
    stats = engine.get_stats()

    table = Table(title="LLM 缓存统计", show_header=True, header_style="bold")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="magenta")
    table.add_row("Provider", str(stats.get("provider")))
    table.add_row("Model", str(stats.get("model")))
    table.add_row("实际调用次数", str(stats.get("call_count")))
    table.add_row("缓存命中（总）", str(stats.get("cache_hits")))
    table.add_row("  ├ 内存命中", str(stats.get("cache_memory_hits")))
    table.add_row("  └ 磁盘命中", str(stats.get("cache_disk_hits")))
    table.add_row("缓存未命中", str(stats.get("cache_misses")))
    table.add_row("缓存命中率", f"{stats.get('cache_hit_rate')}%")
    table.add_row("内存缓存条目", f"{stats.get('cache_size')}/{stats.get('cache_max')}")
    table.add_row("累计 token", f"{stats.get('total_tokens')} ({stats.get('total_prompt_tokens')}+{stats.get('total_completion_tokens')})")
    table.add_row("估算成本", f"${stats.get('estimated_cost_usd')}")
    console.print(table)

    # 持久化缓存详情
    pstats = stats.get("persistent_cache")
    if pstats and pstats.get("backend") == "sqlite":
        console.print("\n[bold cyan]持久化缓存[/bold cyan]")
        console.print(f"  路径: {pstats.get('db_path')}")
        console.print(f"  条目: {pstats.get('total_entries')}")
        console.print(f"  大小: {pstats.get('total_mb')} MB")
        console.print(f"  累计命中: {pstats.get('total_hits')}")
        console.print(f"  节省 token: {pstats.get('total_tokens_saved')}")
        console.print(f"  最旧条目: {pstats.get('oldest_age_hours')} 小时前")
    elif pstats and pstats.get("error"):
        console.print(f"\n[yellow]持久化缓存不可用: {pstats.get('error')}[/yellow]")


@app.command(name="llm-cache-top")
def llm_cache_top(
    limit: int = typer.Option(10, "--limit", "-n", help="显示前 N 条"),
):
    """查看访问最频繁的缓存键"""
    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    engine = LLMEngine(PanguConfig())
    if engine._persistent_cache is None:
        console.print("[yellow]持久化缓存未启用[/yellow]")
        return
    rows = engine._persistent_cache.get_top_keys(limit)
    if not rows:
        console.print("[yellow]缓存为空[/yellow]")
        return
    table = Table(title=f"访问最频繁的 {len(rows)} 个缓存条目")
    table.add_column("键", style="cyan", no_wrap=True)
    table.add_column("Provider", style="magenta")
    table.add_column("Model")
    table.add_column("命中次数", justify="right", style="green")
    table.add_column("Token", justify="right")
    table.add_column("最后访问", justify="right")
    for r in rows:
        table.add_row(
            r["key"],
            r["provider"],
            r["model"],
            str(r["hit_count"]),
            str(r["tokens"]),
            time.strftime("%Y-%m-%d %H:%M", time.localtime(r["last_accessed"])),
        )
    console.print(table)


@app.command(name="llm-cache-clear")
def llm_cache_clear(
    memory: bool = typer.Option(True, "--memory/--no-memory", help="清空内存缓存"),
    persistent: bool = typer.Option(False, "--persistent", help="清空持久化缓存"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清空 LLM 响应缓存"""
    if not force and (memory or persistent):
        confirm = typer.confirm("确定要清空 LLM 缓存吗？")
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    engine = LLMEngine(PanguConfig())
    if memory:
        n = engine.clear_cache()
        console.print(f"[green]✓[/green] 内存缓存已清空 ({n} 条)")
    if persistent:
        n = engine.clear_persistent_cache()
        console.print(f"[green]✓[/green] 持久化缓存已清空 ({n} 条)")


@app.command(name="llm-cache-metrics")
def llm_cache_metrics():
    """导出 Prometheus 格式的 LLM 缓存指标"""
    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    engine = LLMEngine(PanguConfig())
    print(engine.export_prometheus_metrics())


@app.command(name="llm-cache-warmup")
def llm_cache_warmup(
    prompts_file: str = typer.Option(
        None, "--file", "-f", help="JSON 文件路径（含 prompts 列表）"
    ),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="并发数"),
):
    """预热 LLM 缓存（从 JSON 文件或配置文件读取 prompts）"""
    import asyncio
    import json

    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    # 加载 prompts
    prompts = []
    if prompts_file:
        with open(prompts_file) as f:
            data = json.load(f)
            if isinstance(data, list):
                prompts = data
            else:
                prompts = data.get("prompts", [])
        console.print(f"[cyan]从 {prompts_file} 加载 {len(prompts)} 个 prompts[/cyan]")
    else:
        cfg = PanguConfig()
        prompts = getattr(cfg, "llm_cache_warmup_prompts", []) or []
        if not prompts:
            console.print("[yellow]未配置预热 prompts，请提供 --file 或设置 llm_cache_warmup_prompts[/yellow]")
            return

    engine = LLMEngine(PanguConfig())

    async def _run():
        return await engine.warmup_cache(prompts, concurrency=concurrency)

    with console.status("[bold green]正在预热..."):
        result = asyncio.run(_run())

    # 打印结果
    table = Table(title="预热结果", show_header=True)
    table.add_column("指标", style="cyan")
    table.add_column("值", style="magenta")
    table.add_row("总数", str(result.get("total", 0)))
    table.add_row("已预热", f"[green]{result.get('warmed', 0)}[/green]")
    table.add_row("已跳过", f"[yellow]{result.get('skipped', 0)}[/yellow]")
    table.add_row("失败", f"[red]{result.get('failed', 0)}[/red]")
    table.add_row("耗时", f"{result.get('duration_ms', 0)}ms")
    console.print(table)
    console.print("[dim]审计日志: ~/.pangu/logs/llm_cache_warmup.log[/dim]")


@app.command(name="llm-cache-warmup-log")
def llm_cache_warmup_log(
    limit: int = typer.Option(20, "--limit", "-n", help="显示最近 N 条"),
    log_path: str = typer.Option("", "--path", "-p", help="日志路径（默认 ~/.pangu/logs/llm_cache_warmup.log）"),
):
    """查看 LLM 缓存预热审计日志"""
    from pangu.core.llm import LLMEngine

    records = LLMEngine.get_warmup_history(log_path=log_path, limit=limit)
    if not records:
        console.print("[yellow]暂无预热记录[/yellow]")
        return

    table = Table(title=f"预热审计日志（最近 {len(records)} 条）", show_header=True)
    table.add_column("时间", style="cyan")
    table.add_column("Provider/Model", style="magenta")
    table.add_column("总数", justify="right")
    table.add_column("预热", justify="right", style="green")
    table.add_column("跳过", justify="right", style="yellow")
    table.add_column("失败", justify="right", style="red")
    table.add_column("耗时(ms)", justify="right")
    table.add_column("来源", style="dim")

    for rec in records:
        ts = rec.get("ts", 0)
        from datetime import datetime
        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
        table.add_row(
            time_str,
            f"{rec.get('provider', '?')}/{rec.get('model', '?')}",
            str(rec.get("total", 0)),
            str(rec.get("warmed", 0)),
            str(rec.get("skipped", 0)),
            str(rec.get("failed", 0)),
            f"{rec.get('duration_ms', 0):.1f}",
            rec.get("source", "-"),
        )
    console.print(table)


@app.command(name="llm-cache-vacuum")
def llm_cache_vacuum():
    """对 LLM 持久化缓存执行 VACUUM，释放 SQLite 碎片空间"""
    from pangu.core.config import PanguConfig
    from pangu.core.llm import LLMEngine

    engine = LLMEngine(PanguConfig())
    if engine._persistent_cache is None:
        console.print("[yellow]持久化缓存未启用[/yellow]")
        return
    result = engine.vacuum_persistent_cache()
    if result.get("skipped"):
        console.print(f"[yellow]跳过: {result.get('reason', result.get('error', '未知'))}[/yellow]")
        return
    table = Table(title="VACUUM 结果", show_header=False)
    table.add_column("指标", style="cyan")
    table.add_column("值", style="magenta")
    table.add_row("释放前", f"{result.get('before_bytes', 0):,} B")
    table.add_row("释放后", f"{result.get('after_bytes', 0):,} B")
    table.add_row("回收空间", f"[green]{result.get('freed_bytes', 0):,} B[/green]")
    table.add_row("耗时", f"{result.get('duration_ms', 0)} ms")
    console.print(table)
    console.print("[dim]审计日志: ~/.pangu/logs/llm_cache_warmup.log[/dim]")


# ── 主入口 ──

def main():
    app()


if __name__ == "__main__":
    main()
