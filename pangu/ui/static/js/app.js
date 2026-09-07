/**
 * 盘古 — 专业记忆系统 Web UI v2
 * 侧边栏指标、知识图谱/卡片标签页、精简设置
 */

const API_BASE = window.location.origin;
const KG_COLORS = {
    person:'#58a6ff', org:'#3fb950', tech:'#d29922', concept:'#bc8cff',
    event:'#f85149', location:'#79c0ff', memory:'#56d364', default:'#8b949e',
};
const CARD_ICONS = {
    person:'👤', org:'🏢', tech:'💻', concept:'💡',
    event:'📌', location:'📍', memory:'🧠', default:'📄',
};

// ── 状态 ──
const state = {
    currentView: 'dashboard',
    stats: {},
    memories: [],
    wikiPages: [],
    // Knowledge graph
    kgNodes: [], kgEdges: [],
    filteredNodes: [], filteredEdges: [],
    dragNode: null, offsetX: 0, offsetY: 0,
    hoverNode: null, selectedNode: null,
    zoom: 1, panX: 0, panY: 0,
    isPanning: false, lastMouseX: 0, lastMouseY: 0,
    animFrame: null,
    modelUsageTotal: 0,
};

// ── API ──
const API = {
    async get(url) { const r = await fetch(API_BASE + url); if (!r.ok) throw new Error(r.status); return r.json(); },
    async post(url, data) {
        const isForm = data instanceof FormData;
        const r = await fetch(API_BASE + url, { method:'POST', headers: isForm ? {} : {'Content-Type':'application/json'}, body: isForm ? data : JSON.stringify(data) });
        if (!r.ok) throw new Error(r.status); return r.json();
    },
    async del(url) { const r = await fetch(API_BASE + url, {method:'DELETE'}); if (!r.ok) throw new Error(r.status); return r.json(); },
};

// ── 工具 ──
function escapeHtml(t) { if(!t)return''; const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }

// ── 视图切换 ──
function switchView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item[data-view]').forEach(n => n.classList.remove('active'));
    const view = document.getElementById(`view-${viewName}`);
    const nav = document.querySelector(`.nav-item[data-view="${viewName}"]`);
    if (view) view.classList.add('active');
    if (nav) nav.classList.add('active');
    state.currentView = viewName;
    loadView(viewName);
}

function loadView(v) {
    switch(v) {
        case 'dashboard': loadDashboard(); break;
        case 'knowledge': loadKnowledge(); break;
        case 'memories': loadMemories(); break;
        case 'wiki': loadWiki(); break;
        case 'timeline': loadTimeline(); break;
        case 'settings': loadSettings(); break;
    }
}

// ── 侧边栏指标 ──
async function refreshSidebarMetrics() {
    try {
        const stats = await API.get('/api/stats');
        state.stats = stats;
        const totalMem = stats.memory?.total_drawers || 0;
        const healthScore = stats.health?.score || 0;
        const maxMem = 1000;

        document.getElementById('sm-mem-count').textContent = totalMem;
        document.getElementById('sm-mem-bar').style.width = Math.min(100, (totalMem / maxMem) * 100) + '%';

        document.getElementById('sm-health-score').textContent = healthScore + '/100';
        document.getElementById('sm-health-bar').style.width = healthScore + '%';
        const hBar = document.getElementById('sm-health-bar');
        hBar.className = 'progress-fill ' + (healthScore >= 80 ? 'progress-green' : healthScore >= 50 ? 'progress-fill' : 'progress-fill');
        hBar.style.background = healthScore >= 80 ? 'linear-gradient(90deg,#00b894,#00cec9)' : healthScore >= 50 ? 'linear-gradient(90deg,#e17055,#fdcb6e)' : 'linear-gradient(90deg,#d63031,#ff7675)';

        // Model usage: count all memories as proxy
        document.getElementById('sm-model-usage').textContent = state.modelUsageTotal || totalMem;
        document.getElementById('sm-model-bar').style.width = Math.min(100, ((state.modelUsageTotal || totalMem) / maxMem) * 100) + '%';
    } catch(e) {
        console.warn('sidebar metrics:', e);
    }
}

// ── 仪表盘 ──
async function loadDashboard() {
    try {
        const stats = await API.get('/api/stats');
        state.stats = stats;
        document.getElementById('stat-wings').textContent = stats.palace?.wings_count || 0;
        document.getElementById('stat-drawers').textContent = stats.memory?.total_drawers || 0;
        document.getElementById('stat-wiki-pages').textContent = stats.wiki?.total_pages || 0;
        document.getElementById('stat-kg-entities').textContent = stats.knowledge_graph?.entities || 0;

        try {
            const wakeData = await API.get('/api/memories/wake-up');
            document.getElementById('wake-up-content').innerHTML = `<pre style="white-space:pre-wrap;font-size:13px;color:var(--text-secondary)">${escapeHtml(wakeData.context)}</pre>`;
        } catch(e) { document.getElementById('wake-up-content').innerHTML = '<p class="placeholder">暂无上下文</p>'; }

        const memData = await API.get('/api/memories?limit=10');
        const memList = document.getElementById('recent-memories');
        if (memData.memories?.length) {
            memList.innerHTML = memData.memories.map(m => `
                <div class="memory-item">
                    <div class="meta"><span>${escapeHtml(m.wing)}</span>/<span>${escapeHtml(m.room)}</span></div>
                    <div class="content">${escapeHtml(m.content?.substring(0, 150))}...</div>
                </div>
            `).join('');
        } else {
            memList.innerHTML = '<p class="placeholder">暂无记忆</p>';
        }

        refreshSidebarMetrics();
    } catch(e) { console.error('仪表盘加载失败:', e); }
}

// ── 知识总览（标签页） ──
async function loadKnowledge() {
    await loadKnowledgeGraph();
    await loadKnowledgeCards();
}

function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');
        });
    });
}

// ── 知识图谱 (Canvas) ──
async function loadKnowledgeGraph() {
    try {
        const data = await API.get('/api/graph');
        const kg = data.knowledge_graph || {};
        state.kgNodes = (kg.nodes || []).map((n, i) => ({
            ...n,
            x: 200 + (i % 10) * 80 + Math.random() * 40,
            y: 150 + Math.floor(i / 10) * 80 + Math.random() * 40,
            vx: 0, vy: 0,
            radius: Math.min(20, 6 + (n.memory_count || 1) * 2),
        }));
        state.kgEdges = kg.edges || [];
        state.filteredNodes = [...state.kgNodes];
        state.filteredEdges = [...state.kgEdges];
        document.getElementById('graph-stats').textContent = `${state.kgNodes.length} 实体, ${state.kgEdges.length} 关系`;
        buildGraphLegend();
        runForceLayout();
    } catch(e) {
        console.warn('知识图谱加载失败:', e);
        document.getElementById('graph-stats').textContent = '无数据';
    }
}

function buildGraphLegend() {
    const types = new Set(state.kgNodes.map(n => n.type));
    const el = document.getElementById('graph-legend');
    el.innerHTML = '<div style="font-weight:600;margin-bottom:4px;font-size:12px">图例</div>';
    types.forEach(t => {
        el.innerHTML += `<div class="legend-item"><div class="legend-dot" style="background:${KG_COLORS[t]||KG_COLORS.default}"></div>${t} (${state.kgNodes.filter(n=>n.type===t).length})</div>`;
    });
}

function getCanvas() { return document.getElementById('knowledge-canvas'); }

function resizeGraphCanvas() {
    const c = getCanvas();
    if (!c) return;
    const wrap = c.parentElement;
    c.width = wrap.clientWidth;
    c.height = wrap.clientHeight;
}

function runForceLayout() {
    resizeGraphCanvas();
    const c = getCanvas();
    if (!c) return;
    const ctx = c.getContext('2d');
    const nodes = state.kgNodes;
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const W = c.width, H = c.height;
    let alpha = 1;

    function tick() {
        if (alpha < 0.01) return;
        alpha *= 0.95;
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                let dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
                let d = Math.sqrt(dx * dx + dy * dy) || 1;
                let f = 200 / (d * d) * alpha;
                nodes[i].vx -= dx * f; nodes[i].vy -= dy * f;
                nodes[j].vx += dx * f; nodes[j].vy += dy * f;
            }
        }
        state.filteredEdges.forEach(e => {
            const s = nodeMap.get(e.source), t = nodeMap.get(e.target);
            if (!s || !t) return;
            let dx = t.x - s.x, dy = t.y - s.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
            let f = (d - 100) * 0.005 * alpha;
            s.vx += dx * f; s.vy += dy * f;
            t.vx -= dx * f; t.vy -= dy * f;
        });
        nodes.forEach(n => {
            n.vx += (W / 2 - n.x) * 0.001 * alpha;
            n.vy += (H / 2 - n.y) * 0.001 * alpha;
            n.vx *= 0.8; n.vy *= 0.8;
            if (n !== state.dragNode) { n.x += n.vx; n.y += n.vy; }
            n.x = Math.max(20, Math.min(W - 20, n.x));
            n.y = Math.max(20, Math.min(H - 20, n.y));
        });
        drawGraph(ctx, c);
        state.animFrame = requestAnimationFrame(tick);
    }
    if (state.animFrame) cancelAnimationFrame(state.animFrame);
    tick();
}

function drawGraph(ctx, c) {
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.save();
    ctx.translate(state.panX, state.panY);
    ctx.scale(state.zoom, state.zoom);
    const nodeMap = new Map(state.kgNodes.map(n => [n.id, n]));
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();

    state.filteredEdges.forEach(e => {
        const s = nodeMap.get(e.source), t = nodeMap.get(e.target);
        if (!s || !t) return;
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y);
        const isHover = state.hoverNode && (e.source === state.hoverNode.id || e.target === state.hoverNode.id);
        ctx.strokeStyle = isHover ? '#6c5ce7' : 'rgba(139,148,158,0.2)';
        ctx.lineWidth = isHover ? 2 : 1;
        ctx.stroke();
        const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2;
        ctx.fillStyle = 'rgba(139,148,158,0.5)';
        ctx.font = '9px system-ui';
        ctx.fillText(e.predicate || '', mx, my - 4);
    });

    state.filteredNodes.forEach(n => {
        const color = KG_COLORS[n.type] || KG_COLORS.default;
        const isH = state.hoverNode && state.hoverNode.id === n.id;
        const isS = state.selectedNode && state.selectedNode.id === n.id;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = isH || isS ? color : color + 'cc';
        ctx.fill();
        if (isH || isS) { ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.stroke(); }
        ctx.fillStyle = textColor;
        ctx.font = `${isH ? 'bold ' : ''}${Math.max(10, Math.min(12, n.radius))}px system-ui`;
        ctx.textAlign = 'center';
        ctx.fillText((n.name || n.id).substring(0, 12), n.x, n.y + n.radius + 12);
    });
    ctx.restore();
}

function getGraphNode(mx, my) {
    const c = getCanvas(); if (!c) return null;
    const x = (mx - state.panX) / state.zoom, y = (my - state.panY) / state.zoom;
    for (let i = state.filteredNodes.length - 1; i >= 0; i--) {
        const n = state.filteredNodes[i];
        if ((x - n.x) ** 2 + (y - n.y) ** 2 <= n.radius ** 2) return n;
    }
    return null;
}

function initGraphInteraction() {
    const c = getCanvas(); if (!c) return;
    c.addEventListener('mousedown', e => {
        const n = getGraphNode(e.offsetX, e.offsetY);
        if (n) { state.dragNode = n; state.offsetX = e.offsetX / state.zoom - state.panX / state.zoom - n.x; state.offsetY = e.offsetY / state.zoom - state.panY / state.zoom - n.y; }
        else { state.isPanning = true; state.lastMouseX = e.offsetX; state.lastMouseY = e.offsetY; }
    });
    c.addEventListener('mousemove', e => {
        if (state.dragNode) {
            state.dragNode.x = (e.offsetX - state.panX) / state.zoom - state.offsetX;
            state.dragNode.y = (e.offsetY - state.panY) / state.zoom - state.offsetY;
            state.dragNode.vx = 0; state.dragNode.vy = 0;
            const ctx = c.getContext('2d'); drawGraph(ctx, c);
        } else if (state.isPanning) {
            state.panX += e.offsetX - state.lastMouseX; state.panY += e.offsetY - state.lastMouseY;
            state.lastMouseX = e.offsetX; state.lastMouseY = e.offsetY;
            const ctx = c.getContext('2d'); drawGraph(ctx, c);
        } else {
            const n = getGraphNode(e.offsetX, e.offsetY);
            if (n !== state.hoverNode) { state.hoverNode = n; c.style.cursor = n ? 'pointer' : 'default'; const ctx = c.getContext('2d'); drawGraph(ctx, c); }
        }
    });
    c.addEventListener('mouseup', () => { state.dragNode = null; state.isPanning = false; });
    c.addEventListener('dblclick', e => { const n = getGraphNode(e.offsetX, e.offsetY); if (n) showGraphSidebar(n); });
    c.addEventListener('wheel', e => {
        e.preventDefault();
        const f = e.deltaY > 0 ? 0.9 : 1.1;
        state.zoom *= f;
        state.panX = e.offsetX - (e.offsetX - state.panX) * f;
        state.panY = e.offsetY - (e.offsetY - state.panY) * f;
        const ctx = c.getContext('2d'); drawGraph(ctx, c);
    }, { passive: false });
}

function showGraphSidebar(n) {
    state.selectedNode = n;
    const el = document.getElementById('graph-sidebar');
    const content = document.getElementById('graph-sidebar-content');
    const related = state.kgEdges.filter(e => e.source === n.id || e.target === n.id);
    const nodeMap = new Map(state.kgNodes.map(n => [n.id, n]));
    content.innerHTML = `
        <h3>${n.name || n.id}</h3>
        <div class="field"><div class="label">类型</div><div class="value" style="color:${KG_COLORS[n.type]||KG_COLORS.default}">${n.type||'unknown'}</div></div>
        ${n.memory_count ? `<div class="field"><div class="label">关联记忆</div><div class="value">${n.memory_count} 条</div></div>` : ''}
        ${n.description ? `<div class="field"><div class="label">描述</div><div class="value">${n.description}</div></div>` : ''}
        <div class="field"><div class="label">关系 (${related.length})</div>
        ${related.map(r => {
            const other = r.source === n.id ? nodeMap.get(r.target) : nodeMap.get(r.source);
            return `<div style="font-size:12px;margin:2px 0;color:var(--text-secondary)">→ ${r.predicate}: ${other?.name || r.target}</div>`;
        }).join('')}
        </div>`;
    el.classList.add('active');
}

function closeGraphSidebar() {
    document.getElementById('graph-sidebar').classList.remove('active');
    state.selectedNode = null;
}

function filterGraph(q) {
    if (!q) { state.filteredNodes = [...state.kgNodes]; state.filteredEdges = [...state.kgEdges]; }
    else {
        const ql = q.toLowerCase();
        state.filteredNodes = state.kgNodes.filter(n => (n.name || '').toLowerCase().includes(ql) || (n.type || '').toLowerCase().includes(ql));
        const ids = new Set(state.filteredNodes.map(n => n.id));
        state.filteredEdges = state.kgEdges.filter(e => ids.has(e.source) || ids.has(e.target));
    }
    resizeGraphCanvas();
    const c = getCanvas(); if (c) { const ctx = c.getContext('2d'); drawGraph(ctx, c); }
}

// ── 知识卡片 ──
async function loadKnowledgeCards() {
    try {
        const data = await API.get('/api/graph');
        const nodes = (data.knowledge_graph?.nodes || []);
        renderKnowledgeCards(nodes);
    } catch(e) {
        document.getElementById('knowledge-cards-grid').innerHTML = '<p class="placeholder">暂无知识数据</p>';
    }
}

function renderKnowledgeCards(nodes, filter) {
    const grid = document.getElementById('knowledge-cards-grid');
    let filtered = nodes;
    const q = document.getElementById('card-search')?.value?.toLowerCase() || '';
    const typeF = filter || document.getElementById('card-type-filter')?.value || '';
    if (q) filtered = filtered.filter(n => (n.name||'').toLowerCase().includes(q) || (n.description||'').toLowerCase().includes(q));
    if (typeF) filtered = filtered.filter(n => n.type === typeF);

    if (!filtered.length) {
        grid.innerHTML = '<p class="placeholder">暂无匹配的知识卡片</p>';
        return;
    }
    grid.innerHTML = filtered.map(n => {
        const icon = CARD_ICONS[n.type] || CARD_ICONS.default;
        const color = KG_COLORS[n.type] || KG_COLORS.default;
        return `
        <div class="k-card" style="--card-accent:${color}" onclick="showGraphSidebar(state.kgNodes.find(x=>x.id==='${n.id}')||{id:'${n.id}',name:'${escapeHtml(n.name)}',type:'${n.type}',description:'${escapeHtml(n.description||'')}',memory_count:${n.memory_count||0}})">
            <div class="k-card-header">
                <div class="k-card-icon" style="background:${color}22;color:${color}">${icon}</div>
                <div>
                    <div class="k-card-title">${escapeHtml(n.name || n.id)}</div>
                    <div class="k-card-type">${n.type || 'unknown'}</div>
                </div>
                ${n.memory_count ? `<span class="k-card-count">${n.memory_count} 条记忆</span>` : ''}
            </div>
            <div class="k-card-body">${escapeHtml(n.description || '暂无描述')}</div>
        </div>`;
    }).join('');
}

// ── 记忆库 ──
async function loadMemories(wing) {
    const params = wing ? `?wing=${encodeURIComponent(wing)}` : '?limit=50';
    try {
        const data = await API.get(`/api/memories${params}`);
        state.memories = data.memories || [];
        const list = document.getElementById('memories-list');
        if (state.memories.length) {
            list.innerHTML = state.memories.map(m => `
                <div class="memory-item">
                    <div class="meta"><span>${escapeHtml(m.wing)}</span>/<span>${escapeHtml(m.room)}</span><span style="float:right">${escapeHtml(m.hall)}</span></div>
                    <div class="content">${escapeHtml(m.content)}</div>
                </div>
            `).join('');
        } else {
            list.innerHTML = '<p class="placeholder">暂无记忆，点击"添加记忆"或"挖掘文件"开始</p>';
        }
    } catch(e) { console.error('加载记忆失败:', e); }
}

// ── Wiki ──
async function loadWiki() {
    try {
        const data = await API.get('/api/wiki/pages');
        state.wikiPages = data.pages || [];
        const list = document.getElementById('wiki-pages-list');
        if (state.wikiPages.length) {
            list.innerHTML = state.wikiPages.map(p => `
                <div class="wiki-card" onclick="viewWikiPage('${p.id}')">
                    <h4>${escapeHtml(p.title)}</h4>
                    <div class="summary">${escapeHtml(p.summary?.substring(0, 100) || '')}</div>
                    <div class="tags">${(p.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>
                </div>
            `).join('');
        } else {
            list.innerHTML = '<p class="placeholder">暂无 Wiki 页面</p>';
        }
    } catch(e) { console.error('加载 Wiki 失败:', e); }
}

async function viewWikiPage(pageId) {
    try {
        const data = await API.get(`/api/wiki/pages/${pageId}`);
        const p = data.page;
        showModal(`
            <h3>${escapeHtml(p.title)}</h3>
            <div class="markdown-content">${p.content || '(无内容)'}</div>
            <div style="margin-top:16px;font-size:12px;color:var(--text-muted)">Wing: ${escapeHtml(p.wing)} | 版本: ${p.version} | 标签: ${(p.tags||[]).join(', ')}</div>
            <div class="btn-row"><button class="btn btn-outline" onclick="closeModal()">关闭</button></div>
        `);
    } catch(e) { console.error(e); }
}

// ── 时间线 ──
async function loadTimeline() {
    try {
        const data = await API.get('/api/memories?limit=100');
        const events = (data.memories || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        const container = document.getElementById('timeline-events');
        const line = document.getElementById('timeline-line');
        if (!container || !line) return;
        if (!events.length) { container.innerHTML = '<p class="placeholder" style="text-align:center">暂无时间线数据</p>'; line.style.display='none'; return; }
        line.style.display = '';
        container.innerHTML = events.map((m, i) => {
            const side = i % 2 === 0 ? 'left' : 'right';
            const time = new Date(m.created_at).toLocaleString('zh-CN', { hour:'2-digit', minute:'2-digit', month:'numeric', day:'numeric' });
            return `<div class="timeline-event ${side}"><div class="event-content"><div class="event-time">${time}</div><div class="event-text">${escapeHtml(m.content?.substring(0, 100))}</div><div class="event-meta"><span class="event-wing">${escapeHtml(m.wing)}</span><span class="event-room">${escapeHtml(m.room)}</span></div></div></div>`;
        }).join('');
    } catch(e) { console.error(e); }
}

// ── 设置（仅记忆系统开关 + 参数） ──
async function loadSettings() {
    try {
        const data = await API.get('/api/config');
        const c = data.config || {};
        const form = document.getElementById('memory-settings-form');
        if (!form) return;
        form.innerHTML = `
            <div class="setting-group">
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">自动遗忘</div>
                        <div class="setting-desc">启用遗忘曲线，自动衰减低重要性记忆</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-forget" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">记忆巩固</div>
                        <div class="setting-desc">定期合并相关记忆片段</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-consolidate" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">自动压缩</div>
                        <div class="setting-desc">长记忆自动摘要压缩</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-compress" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">标签增强</div>
                        <div class="setting-desc">自动为记忆添加标签</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-tags" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

            <div class="setting-group">
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">遗忘衰减率</div>
                        <div class="setting-desc">衰减速度（越大遗忘越快）</div>
                    </div>
                    <div class="setting-control">
                        <div class="range-control">
                            <input type="range" id="set-decay" min="0.1" max="1" step="0.05" value="${c.forgetting_curve_decay || 0.5}">
                            <span class="range-value" id="set-decay-val">${c.forgetting_curve_decay || 0.5}</span>
                        </div>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">巩固间隔（小时）</div>
                        <div class="setting-desc">自动巩固的时间间隔</div>
                    </div>
                    <div class="setting-control">
                        <div class="range-control">
                            <input type="range" id="set-interval" min="1" max="72" step="1" value="${c.consolidation_interval_hours || 24}">
                            <span class="range-value" id="set-interval-val">${c.consolidation_interval_hours || 24}h</span>
                        </div>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">最大记忆长度</div>
                        <div class="setting-desc">单条记忆最大字符数</div>
                    </div>
                    <div class="setting-control">
                        <div class="range-control">
                            <input type="range" id="set-maxlen" min="500" max="20000" step="500" value="${c.max_memory_length || 10000}">
                            <span class="range-value" id="set-maxlen-val">${(c.max_memory_length || 10000)/1000}k</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="setting-group">
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">自动备份</div>
                        <div class="setting-desc">每日自动备份记忆数据库</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-backup" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
                <div class="setting-row">
                    <div class="setting-info">
                        <div class="setting-name">知识图谱同步</div>
                        <div class="setting-desc">新记忆自动提取实体关系</div>
                    </div>
                    <div class="setting-control">
                        <label class="toggle"><input type="checkbox" id="set-kg-sync" checked><span class="toggle-slider"></span></label>
                    </div>
                </div>
            </div>

            <p style="color:var(--text-muted);font-size:12px;margin-top:16px">完整配置请编辑 ~/.pangu/config.json</p>
        `;

        // Range slider live update
        document.getElementById('set-decay')?.addEventListener('input', e => { document.getElementById('set-decay-val').textContent = e.target.value; });
        document.getElementById('set-interval')?.addEventListener('input', e => { document.getElementById('set-interval-val').textContent = e.target.value + 'h'; });
        document.getElementById('set-maxlen')?.addEventListener('input', e => { document.getElementById('set-maxlen-val').textContent = (e.target.value/1000).toFixed(1) + 'k'; });
    } catch(e) { console.error('加载设置失败:', e); }
}

// ── 模态框 ──
function showModal(html) {
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() { document.getElementById('modal-overlay').classList.add('hidden'); }

// ── 添加记忆 ──
function showAddMemoryModal() {
    showModal(`
        <h3>添加记忆</h3>
        <div class="form-group"><label>内容</label><textarea id="add-memory-content" placeholder="输入记忆内容..."></textarea></div>
        <div class="form-group"><label>Wing</label><input id="add-memory-wing" value="default"></div>
        <div class="form-group"><label>Room</label><input id="add-memory-room" value="general"></div>
        <div class="form-group"><label>殿堂</label><select id="add-memory-hall">
            <option value="hall_events">事件与里程碑</option><option value="hall_facts">事实与决策</option>
            <option value="hall_discoveries">发现与洞察</option><option value="hall_preferences">偏好与习惯</option>
            <option value="hall_advice">建议与方案</option><option value="hall_concepts">概念与理论</option>
        </select></div>
        <div class="btn-row"><button class="btn btn-outline" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="addMemory()">添加</button></div>
    `);
}

async function addMemory() {
    const content = document.getElementById('add-memory-content').value.trim();
    if (!content) return;
    try {
        await API.post('/api/memories', {
            content,
            wing: document.getElementById('add-memory-wing').value || 'default',
            room: document.getElementById('add-memory-room').value || 'general',
            hall: document.getElementById('add-memory-hall').value || 'hall_events',
        });
        closeModal(); loadMemories(); refreshSidebarMetrics();
    } catch(e) { alert('添加失败: ' + e.message); }
}

// ── Wiki 创建 ──
function showCreateWikiModal() {
    showModal(`
        <h3>新建 Wiki 页面</h3>
        <div class="form-group"><label>标题</label><input id="wiki-title" placeholder="页面标题"></div>
        <div class="form-group"><label>Wing</label><input id="wiki-wing" value="default"></div>
        <div class="form-group"><label>内容 (Markdown)</label><textarea id="wiki-content" placeholder="# 标题\n\n内容..."></textarea></div>
        <div class="form-group"><label>标签</label><input id="wiki-tags" placeholder="标签1, 标签2"></div>
        <div class="btn-row"><button class="btn btn-outline" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="createWikiPage()">创建</button></div>
    `);
}

async function createWikiPage() {
    const title = document.getElementById('wiki-title').value.trim();
    if (!title) return;
    try {
        await API.post('/api/wiki/pages', {
            title, wing: document.getElementById('wiki-wing').value || 'default',
            content: document.getElementById('wiki-content').value || '',
            tags: (document.getElementById('wiki-tags').value || '').split(',').map(t => t.trim()).filter(Boolean),
        });
        closeModal(); loadWiki();
    } catch(e) { alert('创建失败: ' + e.message); }
}

function showGenerateWikiModal() {
    showModal(`
        <h3>自动生成 Wiki</h3>
        <p style="color:var(--text-secondary);margin-bottom:16px">分析当前记忆，自动生成结构化 Wiki 页面。</p>
        <div class="form-group"><label>页面标题</label><input id="gen-wiki-title" placeholder="输入主题"></div>
        <div class="form-group"><label>Wing</label><input id="gen-wiki-wing" value="default"></div>
        <div class="btn-row"><button class="btn btn-outline" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="generateWikiPage()">🤖 生成</button></div>
    `);
}

async function generateWikiPage() {
    const title = document.getElementById('gen-wiki-title').value.trim();
    if (!title) return;
    try {
        const fd = new FormData(); fd.append('title', title); fd.append('wing', document.getElementById('gen-wiki-wing').value || 'default');
        await API.post('/api/wiki/generate', fd); closeModal(); loadWiki();
    } catch(e) { alert('生成失败: ' + e.message); }
}

function showMineFilesModal() {
    showModal(`
        <h3>挖掘文件</h3>
        <div class="form-group"><label>目录路径</label><input id="mine-dir" placeholder="~/projects/myapp"></div>
        <div class="form-group"><label>Wing (可选)</label><input id="mine-wing" placeholder="自动使用目录名"></div>
        <div class="btn-row"><button class="btn btn-outline" onclick="closeModal()">取消</button><button class="btn btn-primary" onclick="mineFiles()">开始挖掘</button></div>
    `);
}

async function mineFiles() {
    const dir = document.getElementById('mine-dir').value.trim();
    if (!dir) return;
    try {
        const fd = new FormData(); fd.append('directory', dir);
        const wing = document.getElementById('mine-wing').value.trim();
        if (wing) fd.append('wing', wing);
        const result = await API.post('/api/mine/files', fd);
        closeModal(); alert(`挖掘完成! 新增 ${result.count} 条记忆`); loadDashboard();
    } catch(e) { alert('挖掘失败: ' + e.message); }
}

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
    // 导航
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
        item.addEventListener('click', e => { e.preventDefault(); switchView(item.dataset.view); });
    });

    // 按钮
    document.getElementById('quick-mine-btn')?.addEventListener('click', showMineFilesModal);
    document.getElementById('refresh-stats-btn')?.addEventListener('click', loadDashboard);
    document.getElementById('add-memory-btn')?.addEventListener('click', showAddMemoryModal);
    document.getElementById('mine-files-btn')?.addEventListener('click', showMineFilesModal);
    document.getElementById('create-wiki-btn')?.addEventListener('click', showCreateWikiModal);
    document.getElementById('generate-wiki-btn')?.addEventListener('click', showGenerateWikiModal);

    // 模态框关闭
    document.getElementById('modal-overlay')?.addEventListener('click', e => { if (e.target === e.currentTarget) closeModal(); });

    // 标签页
    initTabs();

    // 知识图谱交互
    initGraphInteraction();

    // 图谱搜索
    document.getElementById('graph-search')?.addEventListener('input', e => filterGraph(e.target.value));

    // 卡片搜索/筛选
    document.getElementById('card-search')?.addEventListener('input', () => {
        const nodes = state.kgNodes;
        renderKnowledgeCards(nodes);
    });
    document.getElementById('card-type-filter')?.addEventListener('change', () => {
        renderKnowledgeCards(state.kgNodes);
    });

    // 图谱按钮
    document.getElementById('graph-zoom-in-btn')?.addEventListener('click', () => { state.zoom *= 1.2; const c = getCanvas(); if(c){drawGraph(c.getContext('2d'),c);} });
    document.getElementById('graph-zoom-out-btn')?.addEventListener('click', () => { state.zoom *= 0.8; const c = getCanvas(); if(c){drawGraph(c.getContext('2d'),c);} });
    document.getElementById('graph-reset-btn')?.addEventListener('click', () => { state.zoom=1; state.panX=0; state.panY=0; if(state.kgNodes.length) runForceLayout(); });

    // 窗口缩放
    window.addEventListener('resize', () => { if (state.currentView === 'knowledge') { resizeGraphCanvas(); const c = getCanvas(); if(c){drawGraph(c.getContext('2d'),c);} } });

    // 初始加载
    loadDashboard();
    refreshSidebarMetrics();
    setInterval(refreshSidebarMetrics, 30000);
});

console.log('盘古记忆系统 Web UI v2 已就绪');
