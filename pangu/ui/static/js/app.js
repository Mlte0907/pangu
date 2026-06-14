/**
 * 盘古 — 专业记忆系统 Web UI
 * 单页应用，通过 API 与后端交互
 * 专注记忆管理：存储、检索、组织、知识结晶
 */

// ── 状态管理 ──
const state = {
    currentView: 'dashboard',
    currentWing: null,
    stats: {},
    memories: [],
    wikiPages: [],
    palace3d: null,
    knowledgeGraph: null,
    timeline: null,
};

// ── API 工具 ──
const API = {
    async get(url) {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        return resp.json();
    },
    async post(url, data) {
        const isForm = data instanceof FormData;
        const resp = await fetch(url, {
            method: 'POST',
            headers: isForm ? {} : { 'Content-Type': 'application/json' },
            body: isForm ? data : JSON.stringify(data),
        });
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        return resp.json();
    },
    async del(url) {
        const resp = await fetch(url, { method: 'DELETE' });
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        return resp.json();
    },
};

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

// ── 视图加载 ──
async function loadView(viewName) {
    switch (viewName) {
        case 'dashboard': await loadDashboard(); break;
        case 'memories': await loadMemories(); break;
        case 'wiki': await loadWiki(); break;
        case 'search': break;
        case 'graph': await loadGraph(); break;
        case 'palace3d': await loadPalace3D(); break;
        case 'timeline': await loadTimeline(); break;
        case 'analytics': await loadAnalytics(); break;
        case 'settings': await loadSettings(); break;
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

        // 唤醒上下文
        const wakeData = await API.get('/api/memories/wake-up');
        document.getElementById('wake-up-content').innerHTML = `<pre style="white-space:pre-wrap;font-size:13px;color:var(--text-secondary)">${escapeHtml(wakeData.context)}</pre>`;

        // 最近记忆
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
    } catch (e) {
        console.error('加载仪表盘失败:', e);
    }
}

// ── 记忆库 ──
async function loadMemories(wing = null) {
    const params = wing ? `?wing=${encodeURIComponent(wing)}` : '?limit=50';
    try {
        const data = await API.get(`/api/memories${params}`);
        state.memories = data.memories || [];

        const list = document.getElementById('memories-list');
        if (state.memories.length) {
            list.innerHTML = state.memories.map(m => `
                <div class="memory-item">
                    <div class="meta">
                        <span>${escapeHtml(m.wing)}</span>/<span>${escapeHtml(m.room)}</span>
                        <span style="float:right">${escapeHtml(m.hall)}</span>
                    </div>
                    <div class="content">${escapeHtml(m.content)}</div>
                </div>
            `).join('');
        } else {
            list.innerHTML = '<p class="placeholder">暂无记忆，点击"添加记忆"或"挖掘文件"开始</p>';
        }
    } catch (e) {
        console.error('加载记忆失败:', e);
    }
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
            list.innerHTML = '<p class="placeholder">暂无 Wiki 页面，点击"新建页面"或"LMM 自动生成"创建</p>';
        }
    } catch (e) {
        console.error('加载 Wiki 失败:', e);
    }
}

async function viewWikiPage(pageId) {
    try {
        const data = await API.get(`/api/wiki/pages/${pageId}`);
        const page = data.page;
        showModal(`
            <h3>${escapeHtml(page.title)}</h3>
            <div class="markdown-content">${page.content || '(无内容)'}</div>
            <div style="margin-top:16px;font-size:12px;color:var(--text-muted)">
                Wing: ${escapeHtml(page.wing)} | 版本: ${page.version} | 标签: ${(page.tags || []).join(', ')}
            </div>
            <div class="btn-row">
                <button class="btn btn-outline" onclick="closeModal()">关闭</button>
            </div>
        `);
    } catch (e) {
        console.error('加载 Wiki 页面失败:', e);
    }
}

// ── 知识图谱 ──
async function loadGraph() {
    try {
        const data = await API.get('/api/graph');
        const kg = data.knowledge_graph || {};

        if (!state.knowledgeGraph) {
            state.knowledgeGraph = new KnowledgeGraph('graph-container');
        }

        state.knowledgeGraph.loadData(kg);
    } catch (e) {
        console.error('加载图谱失败:', e);
    }
}

// ── 3D记忆宫殿 ──
async function loadPalace3D() {
    try {
        const data = await API.get('/api/wings');
        const wings = data.wings || [];

        // 获取每个wing的rooms
        const wingsWithRooms = await Promise.all(wings.map(async (wing) => {
            const roomsData = await API.get(`/api/wings/${wing.name}/rooms`);
            return {
                ...wing,
                rooms: roomsData.rooms || []
            };
        }));

        if (!state.palace3d) {
            state.palace3d = new Palace3D('palace3d-container', 'palace3d-canvas');
        }

        state.palace3d.loadPalaceData({ wings: wingsWithRooms });
    } catch (e) {
        console.error('加载3D宫殿失败:', e);
    }
}

// ── 时间线 ──
async function loadTimeline() {
    try {
        const range = document.getElementById('timeline-range')?.value || '7d';
        const data = await API.get('/api/memories?limit=100');

        if (!state.timeline) {
            state.timeline = new Timeline('timeline-container');
        }

        state.timeline.setRange(range);
        state.timeline.loadData(data);
    } catch (e) {
        console.error('加载时间线失败:', e);
    }
}

// ── 分析看板 ──
async function loadAnalytics() {
    try {
        const data = await API.get('/api/stats');

        // 健康评分
        const healthScore = data.health?.score || 0;
        const healthEl = document.getElementById('health-score');
        if (healthEl) {
            healthEl.innerHTML = `
                <svg viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="45" fill="none" stroke="var(--bg-hover)" stroke-width="8"/>
                    <circle cx="50" cy="50" r="45" fill="none" stroke="${getHealthColor(healthScore)}" stroke-width="8"
                        stroke-dasharray="${healthScore * 2.83} 283" stroke-linecap="round" transform="rotate(-90 50 50)"/>
                    <text x="50" y="55" text-anchor="middle" font-size="24" fill="var(--text-primary)">${healthScore}</text>
                </svg>
            `;
        }

        // 标签云
        await loadTagCloud();

        // 活跃时段
        await loadActivityHeatmap();
    } catch (e) {
        console.error('加载分析看板失败:', e);
    }
}

function getHealthColor(score) {
    if (score >= 80) return 'var(--success)';
    if (score >= 60) return 'var(--warning)';
    return 'var(--danger)';
}

async function loadTagCloud() {
    try {
        const data = await API.get('/api/memories?limit=200');
        const memories = data.memories || [];

        // 统计标签
        const tagCounts = {};
        memories.forEach(m => {
            (m.tags || []).forEach(tag => {
                tagCounts[tag] = (tagCounts[tag] || 0) + 1;
            });
        });

        // 排序并取前20
        const topTags = Object.entries(tagCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 20);

        const tagCloud = document.getElementById('tag-cloud');
        if (tagCloud) {
            tagCloud.innerHTML = topTags.map(([tag, count]) => {
                const size = Math.min(24, 12 + count * 2);
                return `<span class="tag" style="font-size:${size}px">${tag}</span>`;
            }).join('');
        }
    } catch (e) {
        console.error('加载标签云失败:', e);
    }
}

async function loadActivityHeatmap() {
    try {
        const data = await API.get('/api/memories?limit=500');
        const memories = data.memories || [];

        // 统计每小时活跃度
        const hourlyActivity = new Array(24).fill(0);
        memories.forEach(m => {
            const hour = new Date(m.created_at).getHours();
            hourlyActivity[hour]++;
        });

        const maxActivity = Math.max(...hourlyActivity, 1);

        const heatmap = document.getElementById('activity-heatmap');
        if (heatmap) {
            heatmap.innerHTML = hourlyActivity.map((count, hour) => {
                const intensity = count / maxActivity;
                const opacity = 0.2 + intensity * 0.8;
                return `<div class="heatmap-cell" style="opacity:${opacity}" title="${hour}时: ${count}条记忆"></div>`;
            }).join('');
        }
    } catch (e) {
        console.error('加载活跃时段失败:', e);
    }
}

// ── 设置 ──
async function loadSettings() {
    try {
        const data = await API.get('/api/config');
        const config = data.config || {};

        const form = document.getElementById('config-form');
        if (form) {
            form.innerHTML = `
                <div class="form-group">
                    <label>LLM 提供商</label>
                    <input type="text" value="${config.llm_provider || 'openai'}" disabled>
                </div>
                <div class="form-group">
                    <label>LLM 模型</label>
                    <input type="text" value="${config.llm_model || 'gpt-4o'}" disabled>
                </div>
                <div class="form-group">
                    <label>嵌入模型</label>
                    <input type="text" value="${config.embedding_model || 'all-MiniLM-L6-v2'}" disabled>
                </div>
                <div class="form-group">
                    <label>记忆巩固间隔 (小时)</label>
                    <input type="number" value="${config.consolidation_interval_hours || 24}" disabled>
                </div>
                <div class="form-group">
                    <label>遗忘曲线衰减率</label>
                    <input type="number" value="${config.forgetting_curve_decay || 0.5}" step="0.1" disabled>
                </div>
                <p style="color:var(--text-muted);font-size:12px;margin-top:16px">
                    配置修改请编辑 ~/.pangu/config.json
                </p>
            `;
        }
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

// ── 搜索 ──
async function performSearch() {
    const query = document.getElementById('deep-search-input').value.trim();
    if (!query) return;

    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<p class="placeholder">搜索中...</p>';

    try {
        const data = await API.post('/api/memories/search', { query, n_results: 10 });
        const results = data.results || [];

        if (results.length) {
            resultsDiv.innerHTML = results.map((r, i) => `
                <div class="search-result">
                    <div class="meta">
                        <span>${escapeHtml(r.wing)}</span>/<span>${escapeHtml(r.room)}</span>
                        <span class="score" style="float:right">相关度: ${r.score}</span>
                    </div>
                    <div class="content">${escapeHtml(r.content?.substring(0, 200))}...</div>
                </div>
            `).join('');
        } else {
            resultsDiv.innerHTML = '<p class="placeholder">未找到结果</p>';
        }
    } catch (e) {
        resultsDiv.innerHTML = '<p class="placeholder">搜索失败</p>';
        console.error('搜索失败:', e);
    }
}

// ── 模态框 ──
function showModal(html) {
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

// ── 添加记忆 ──
function showAddMemoryModal() {
    showModal(`
        <h3>添加记忆</h3>
        <div class="form-group">
            <label>内容</label>
            <textarea id="add-memory-content" placeholder="输入记忆内容..."></textarea>
        </div>
        <div class="form-group">
            <label>Wing (空间)</label>
            <input id="add-memory-wing" value="default" placeholder="default">
        </div>
        <div class="form-group">
            <label>Room (房间)</label>
            <input id="add-memory-room" value="general" placeholder="general">
        </div>
        <div class="form-group">
            <label>殿堂</label>
            <select id="add-memory-hall">
                <option value="hall_events">事件与里程碑</option>
                <option value="hall_facts">事实与决策</option>
                <option value="hall_discoveries">发现与洞察</option>
                <option value="hall_preferences">偏好与习惯</option>
                <option value="hall_advice">建议与方案</option>
                <option value="hall_concepts">概念与理论</option>
            </select>
        </div>
        <div class="btn-row">
            <button class="btn btn-outline" onclick="closeModal()">取消</button>
            <button class="btn btn-primary" onclick="addMemory()">添加</button>
        </div>
    `);
}

async function addMemory() {
    const content = document.getElementById('add-memory-content').value.trim();
    if (!content) return;

    const data = {
        content,
        wing: document.getElementById('add-memory-wing').value || 'default',
        room: document.getElementById('add-memory-room').value || 'general',
        hall: document.getElementById('add-memory-hall').value || 'hall_events',
    };

    try {
        await API.post('/api/memories', data);
        closeModal();
        loadMemories();
    } catch (e) {
        alert('添加失败: ' + e.message);
    }
}

// ── 新建 Wiki 页面 ──
function showCreateWikiModal() {
    showModal(`
        <h3>新建 Wiki 页面</h3>
        <div class="form-group">
            <label>标题</label>
            <input id="wiki-title" placeholder="页面标题">
        </div>
        <div class="form-group">
            <label>Wing</label>
            <input id="wiki-wing" value="default">
        </div>
        <div class="form-group">
            <label>内容 (Markdown)</label>
            <textarea id="wiki-content" placeholder="# 标题\n\n内容..."></textarea>
        </div>
        <div class="form-group">
            <label>标签 (逗号分隔)</label>
            <input id="wiki-tags" placeholder="标签1, 标签2">
        </div>
        <div class="btn-row">
            <button class="btn btn-outline" onclick="closeModal()">取消</button>
            <button class="btn btn-primary" onclick="createWikiPage()">创建</button>
        </div>
    `);
}

async function createWikiPage() {
    const title = document.getElementById('wiki-title').value.trim();
    if (!title) return;

    const data = {
        title,
        wing: document.getElementById('wiki-wing').value || 'default',
        content: document.getElementById('wiki-content').value || '',
        tags: (document.getElementById('wiki-tags').value || '').split(',').map(t => t.trim()).filter(Boolean),
    };

    try {
        await API.post('/api/wiki/pages', data);
        closeModal();
        loadWiki();
    } catch (e) {
        alert('创建失败: ' + e.message);
    }
}

// ── LMM 自动生成 Wiki ──
function showGenerateWikiModal() {
    showModal(`
        <h3>LMM 自动生成 Wiki 页面</h3>
        <p style="color:var(--text-secondary);margin-bottom:16px">LMM 将分析当前记忆，自动生成结构化的 Wiki 页面。</p>
        <div class="form-group">
            <label>页面标题</label>
            <input id="gen-wiki-title" placeholder="输入页面主题">
        </div>
        <div class="form-group">
            <label>Wing</label>
            <input id="gen-wiki-wing" value="default">
        </div>
        <div class="btn-row">
            <button class="btn btn-outline" onclick="closeModal()">取消</button>
            <button class="btn btn-primary" onclick="generateWikiPage()">🤖 生成</button>
        </div>
    `);
}

async function generateWikiPage() {
    const title = document.getElementById('gen-wiki-title').value.trim();
    const wing = document.getElementById('gen-wiki-wing').value || 'default';
    if (!title) return;

    const formData = new FormData();
    formData.append('title', title);
    formData.append('wing', wing);

    try {
        await API.post('/api/wiki/generate', formData);
        closeModal();
        loadWiki();
    } catch (e) {
        alert('生成失败: ' + e.message);
    }
}

// ── 快速挖掘文件 ──
function showMineFilesModal() {
    showModal(`
        <h3>挖掘文件</h3>
        <div class="form-group">
            <label>目录路径</label>
            <input id="mine-dir" placeholder="~/projects/myapp">
        </div>
        <div class="form-group">
            <label>Wing 名称 (可选)</label>
            <input id="mine-wing" placeholder="自动使用目录名">
        </div>
        <div class="btn-row">
            <button class="btn btn-outline" onclick="closeModal()">取消</button>
            <button class="btn btn-primary" onclick="mineFiles()">开始挖掘</button>
        </div>
    `);
}

async function mineFiles() {
    const dir = document.getElementById('mine-dir').value.trim();
    if (!dir) return;

    const formData = new FormData();
    formData.append('directory', dir);
    const wing = document.getElementById('mine-wing').value.trim();
    if (wing) formData.append('wing', wing);

    try {
        const result = await API.post('/api/mine/files', formData);
        closeModal();
        alert(`挖掘完成! 新增 ${result.count} 条记忆片段`);
        loadDashboard();
    } catch (e) {
        alert('挖掘失败: ' + e.message);
    }
}

// ── 工具函数 ──
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── 初始化 ──
document.addEventListener('DOMContentLoaded', () => {
    // 导航切换
    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            switchView(item.dataset.view);
        });
    });

    // 仪表盘按钮
    document.getElementById('quick-mine-btn')?.addEventListener('click', showMineFilesModal);
    document.getElementById('refresh-stats-btn')?.addEventListener('click', loadDashboard);

    // 记忆库按钮
    document.getElementById('add-memory-btn')?.addEventListener('click', showAddMemoryModal);
    document.getElementById('mine-files-btn')?.addEventListener('click', showMineFilesModal);

    // Wiki 按钮
    document.getElementById('create-wiki-btn')?.addEventListener('click', showCreateWikiModal);
    document.getElementById('generate-wiki-btn')?.addEventListener('click', showGenerateWikiModal);

    // 搜索
    document.getElementById('deep-search-btn')?.addEventListener('click', performSearch);
    document.getElementById('deep-search-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    // 3D宫殿按钮
    document.getElementById('reset-camera-btn')?.addEventListener('click', () => {
        state.palace3d?.resetCamera();
    });
    document.getElementById('toggle-labels-btn')?.addEventListener('click', () => {
        state.palace3d?.toggleLabels();
    });

    // 知识图谱按钮
    document.getElementById('graph-zoom-in-btn')?.addEventListener('click', () => {
        state.knowledgeGraph?.zoomIn();
    });
    document.getElementById('graph-zoom-out-btn')?.addEventListener('click', () => {
        state.knowledgeGraph?.zoomOut();
    });
    document.getElementById('graph-reset-btn')?.addEventListener('click', () => {
        state.knowledgeGraph?.resetZoom();
    });

    // 时间线范围选择
    document.getElementById('timeline-range')?.addEventListener('change', (e) => {
        state.timeline?.setRange(e.target.value);
        loadTimeline();
    });

    // 分析看板刷新
    document.getElementById('refresh-analytics-btn')?.addEventListener('click', loadAnalytics);

    // 模态框关闭
    document.getElementById('modal-overlay')?.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });

    // 初始加载
    loadDashboard();
});

console.log('盘古记忆系统 Web UI 已就绪');