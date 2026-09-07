/**
 * 盘古知识图谱可视化
 * 使用 D3.js 实现交互式知识图谱探索
 */

class KnowledgeGraph {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.links = [];
        this.selectedNode = null;
        this.zoom = null;
        this.init();
    }

    init() {
        this.svg = d3.select(`#${this.container.id} svg`)
            .attr('width', '100%')
            .attr('height', '100%');

        // 添加缩放
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.svg.select('g').attr('transform', event.transform);
            });

        this.svg.call(this.zoom);

        // 添加箭头定义
        this.svg.append('defs').append('marker')
            .attr('id', 'arrowhead')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', '#6c5ce7');

        // 创建主容器
        this.svg.append('g');

        // 设置拖拽
        this.drag = d3.drag()
            .on('start', (event, d) => this.dragStarted(event, d))
            .on('drag', (event, d) => this.dragged(event, d))
            .on('end', (event, d) => this.dragEnded(event, d));
    }

    loadData(data) {
        this.nodes = (data.entities || []).map(e => ({
            id: e.id,
            name: e.name,
            type: e.type,
            description: e.description,
            importance: e.importance || 5,
            x: Math.random() * 500,
            y: Math.random() * 500
        }));

        this.links = (data.relations || []).map(r => ({
            source: r.subject_id,
            target: r.object_id,
            predicate: r.predicate,
            confidence: r.confidence || 1.0
        }));

        this.render();
    }

    render() {
        const g = this.svg.select('g');
        g.selectAll('*').remove();

        // 力导向模拟
        this.simulation = d3.forceSimulation(this.nodes)
            .force('link', d3.forceLink(this.links).id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(
                this.container.clientWidth / 2,
                this.container.clientHeight / 2
            ))
            .force('collision', d3.forceCollide().radius(30));

        // 绘制链接
        const link = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(this.links)
            .enter().append('line')
            .attr('stroke', '#6c5ce7')
            .attr('stroke-opacity', 0.6)
            .attr('stroke-width', d => Math.max(1, d.confidence * 3))
            .attr('marker-end', 'url(#arrowhead)');

        // 绘制节点
        const node = g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .enter().append('g')
            .call(this.drag);

        // 节点圆形
        node.append('circle')
            .attr('r', d => Math.max(8, d.importance * 2))
            .attr('fill', d => this.getNodeColor(d.type))
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .style('cursor', 'pointer')
            .on('mouseover', (event, d) => this.nodeHover(event, d))
            .on('mouseout', () => this.nodeOut())
            .on('click', (event, d) => this.nodeClick(event, d));

        // 节点标签
        node.append('text')
            .attr('dx', 12)
            .attr('dy', 4)
            .attr('font-size', '10px')
            .attr('fill', '#e8e8f0')
            .text(d => d.name);

        // 链接标签
        const linkLabel = g.append('g')
            .attr('class', 'link-labels')
            .selectAll('text')
            .data(this.links)
            .enter().append('text')
            .attr('font-size', '8px')
            .attr('fill', '#a0a0b8')
            .attr('text-anchor', 'middle')
            .text(d => d.predicate);

        // 更新模拟
        this.simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${d.x},${d.y})`);

            linkLabel
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);
        });
    }

    getNodeColor(type) {
        const colors = {
            'person': '#00cec9',
            'system': '#6c5ce7',
            'technology': '#fdcb6e',
            'concept': '#a29bfe',
            'event': '#ff7675',
            'default': '#6c5ce7'
        };
        return colors[type] || colors.default;
    }

    dragStarted(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    dragEnded(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    nodeHover(event, d) {
        const tooltip = document.getElementById('graph-tooltip');
        tooltip.innerHTML = `
            <strong>${d.name}</strong><br>
            <span>类型: ${d.type}</span><br>
            <span>${d.description || ''}</span>
        `;
        tooltip.style.left = (event.pageX + 10) + 'px';
        tooltip.style.top = (event.pageY - 10) + 'px';
        tooltip.classList.remove('hidden');
    }

    nodeOut() {
        const tooltip = document.getElementById('graph-tooltip');
        tooltip.classList.add('hidden');
    }

    nodeClick(event, d) {
        this.selectedNode = d;
        this.highlightNode(d);
    }

    highlightNode(node) {
        const g = this.svg.select('g');

        // 重置所有节点
        g.selectAll('.nodes circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 2);

        // 高亮选中节点
        g.selectAll('.nodes circle')
            .filter(d => d.id === node.id)
            .attr('stroke', '#fdcb6e')
            .attr('stroke-width', 4);

        // 高亮相关链接
        g.selectAll('.links line')
            .attr('stroke-opacity', d =>
                d.source.id === node.id || d.target.id === node.id ? 1 : 0.2
            );
    }

    zoomIn() {
        this.svg.transition().call(this.zoom.scaleBy, 1.5);
    }

    zoomOut() {
        this.svg.transition().call(this.zoom.scaleBy, 0.67);
    }

    resetZoom() {
        this.svg.transition().call(
            this.zoom.transform,
            d3.zoomIdentity
        );
    }

    dispose() {
        if (this.simulation) {
            this.simulation.stop();
        }
    }
}

// 导出
window.KnowledgeGraph = KnowledgeGraph;
