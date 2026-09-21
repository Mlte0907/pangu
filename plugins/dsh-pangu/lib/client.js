/**
 * pangu-dashboard DSH 客户端 v5.0。
 * 注册:
 *  - sidebar.footer.action:  侧边栏指标卡 + 快捷记忆(宽/窄双形态,独占一行)
 *  - conversation.view:      顶部标签页(概览 / 3D 星系图谱 / 知识卡片 / 知识库 / 管理)
 *  - settings.section:       设置页(真实读写 ~/.pangu/config.json)
 * v5.0: 架构 v2.1 重构——平台Token管理、知识库浏览、记忆快照、来源分布。
 *       管理页拆分为 体检/平台/钥匙/快照 四个子区。
 * v4.3: 星系图 Obsidian 式搜索 dim 高亮(过滤不再移除节点);侧边栏「快速记一条」
 *       直接入库;事件驱动刷新(/ws 事件缓冲,有变化才拉全量)。
 * v4.2: 知识图谱改 3D 星系视图——Canvas2D 手写透视投影(盘面分布/自转/拖拽视角/
 *       发光星点/星尘视差),不引入第三方依赖;侧边栏卡利用 wide 列状态重排。
 *       结构色沿用 DSH --dsw-alias-* 设计令牌,盘古紫仅作点缀。
 */
window.__ModuleLoader__.load({
  id: 'dsh-pangu',
  factory: (require) => {
    const module = { exports: {} }
    const React = require('react')
    const inject = ['slots', 'timer', 'remote']
    const h = React.createElement

    let ctx = null
    let timer = null

    /* ════════════════ Typert Remote 清单(客户端面) ════════════════
     * 与 lib/typert.host.js 的 invocations 对应;浏览器端用轻量 {parse} codec。
     * 必须 remote.$mount 之后 ctx.get('remote.<namespace>') 才可用。 */
    function codec(parse) { return { parse } }
    function assertObject(v, name) {
      if (v === null || typeof v !== 'object' || Array.isArray(v)) throw new TypeError(name + ' 必须是对象')
      return v
    }
    const okEnvelope = codec((v) => { assertObject(v, 'result'); return v })
    const patchCodec = codec((v) => assertObject(v, 'patch'))
    const DESCRIPTORS = {
      package: 'dsh-pangu',
      descriptors: [
        { id: 'dsh-pangu#panguDashboard/data', service: 'panguDashboard', namespace: 'panguDashboard', method: 'data', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#DashboardData', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/ping', service: 'panguDashboard', namespace: 'panguDashboard', method: 'ping', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#Ping', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/deepHealth', service: 'panguDashboard', namespace: 'panguDashboard', method: 'deepHealth', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#DeepHealth', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/backup', service: 'panguDashboard', namespace: 'panguDashboard', method: 'backup', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#BackupResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/events', service: 'panguDashboard', namespace: 'panguDashboard', method: 'events', invocation: { kind: 'direct' }, parameters: [{ name: 'since', wire: 'since', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Since', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#Events', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/add', service: 'panguDashboard', namespace: 'panguDashboard', method: 'add', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#AddArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#AddResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguKG/graph', service: 'panguKG', namespace: 'panguKG', method: 'graph', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KGData', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguConfig/get', service: 'panguConfig', namespace: 'panguConfig', method: 'get', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#ConfigData', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguConfig/save', service: 'panguConfig', namespace: 'panguConfig', method: 'save', invocation: { kind: 'direct' }, parameters: [{ name: 'patch', wire: 'patch', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#SavePatch', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#SaveResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguConfig/testLlm', service: 'panguConfig', namespace: 'panguConfig', method: 'testLlm', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#TestLlmResult', create: () => okEnvelope } },
        // ── 阶段 5A 钥匙与房间管理 ──
        // 这 6 个此前只在宿主清单（lib/typert.host.js）里声明，客户端清单漏了，
        // 于是 callRemote('panguAdminKeys', …) 在客户端就找不到服务（"远程服务
        // panguAdminKeys 未就绪"），而调用处是 Promise.allSettled + catch(_){} ——
        // 错误被静默吞掉，表现为钥匙列表 / 房间卡片 / 星系 / 公共区整片空白。
        // 无参方法必须零参展开，带参方法统一传单个对象（见 callRemote 的注释）。
        { id: 'dsh-pangu#panguAdminKeys/listKeys', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listKeys', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/listRooms', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listRooms', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#RoomList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/listPublicMemories', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listPublicMemories', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#PublicMemories', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/listRecentMemories', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listRecentMemories', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#RecentMemories', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/createKey', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'createKey', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyCreateArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyCreate', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/revokeKey', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'revokeKey', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyRevokeArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyRevoke', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguAdminKeys/rekeyRoom', service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'rekeyRoom', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RekeyArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#RekeyResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/checkUpdate', service: 'panguDashboard', namespace: 'panguDashboard', method: 'checkUpdate', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#CheckUpdateResult', create: () => okEnvelope } },
        // ── 平台管理 ──
        { id: 'dsh-pangu#panguPlatforms/listPlatforms', service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'listPlatforms', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#PlatformList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguPlatforms/listPending', service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'listPending', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#PendingList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguPlatforms/approve', service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'approve', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#ApproveArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#ApproveResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguPlatforms/reject', service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'reject', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RejectArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#RejectResult', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguPlatforms/revoke', service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'revoke', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RevokePlatformArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#RevokePlatformResult', create: () => okEnvelope } },
        // ── 知识库 ──
        { id: 'dsh-pangu#panguKnowledge/list', service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'list', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeListArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguKnowledge/search', service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'search', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeSearchArgs', create: () => patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeList', create: () => okEnvelope } },
        { id: 'dsh-pangu#panguKnowledge/stats', service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'stats', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeStats', create: () => okEnvelope } },
      ],
    }

    /* ════════════════ 设计令牌 ════════════════ */
    const ACCENT = '#33705d'
    const ACCENT_DEEP = '#255648'
    const V = (name, fallback) => `var(${name}, ${fallback})`
    const css = {
      bg1: V('--dsw-alias-bg-layer-1', '#fff'),
      bg2: V('--dsw-alias-bg-layer-2', '#f7f8fa'),
      bg3: V('--dsw-alias-bg-layer-3', '#f2f3f5'),
      skeleton: V('--dsw-alias-bg-skeleton', 'rgba(0,0,0,.06)'),
      border: V('--dsw-alias-border-l2', 'rgba(0,0,0,.1)'),
      borderSoft: V('--dsw-alias-border-l1', 'rgba(0,0,0,.05)'),
      t1: V('--dsw-alias-label-primary', '#171a23'),
      t2: V('--dsw-alias-label-secondary', '#4b5563'),
      t3: V('--dsw-alias-label-tertiary', '#6b7280'),
      ok: V('--dsw-alias-state-success-primary', '#22c55e'),
      warn: V('--dsw-alias-state-warn-primary', '#f59e0b'),
      err: V('--dsw-alias-state-error-primary', '#dc2626'),
      info: V('--dsw-alias-state-business-primary', '#4d6bfe'),
      hover: V('--dsw-alias-interactive-bg-hover', 'rgba(38,49,72,.06)'),
      shadow: '0 4px 16px rgba(0,0,0,.10)',
    }

    const STYLE_ID = 'dsh-pangu-style'
    function ensureStyles() {
      let el = document.getElementById(STYLE_ID)
      if (el) return
      el = document.createElement('style')
      el.id = STYLE_ID
      el.setAttribute('data-plugin', 'dsh-pangu')
      el.textContent = `
@keyframes panguBlink{0%,100%{opacity:.4}50%{opacity:1}}
@keyframes panguFade{from{opacity:0;transform:translateY(2px)}to{opacity:1;transform:none}}
@keyframes panguRing{0%{transform:scale(1);opacity:.55}70%,100%{transform:scale(2.1);opacity:0}}
@keyframes panguPulse{0%,100%{opacity:1}50%{opacity:.35}}
.pangu-tab:hover{color:var(--dsw-alias-label-primary,#171a23)}
.pangu-input:focus{border-color:${ACCENT}80 !important;box-shadow:0 0 0 2px ${ACCENT}1f}
.pangu-btn:hover{background:var(--dsw-alias-interactive-bg-hover,rgba(38,49,72,.06))}
.pangu-card{transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
.pangu-card:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.09);border-color:var(--dsw-alias-border-l4,rgba(0,0,0,.2))}
.pangu-vital+.pangu-vital{border-left:1px solid var(--dsw-alias-border-l1,rgba(0,0,0,.05))}
.pangu-stampline{display:inline-flex;align-items:center;gap:4px;border:1px dashed ${ACCENT};color:${ACCENT};border-radius:4px;padding:0 5px;font-size:9.5px;vertical-align:1px}
`
      document.head.appendChild(el)
    }
    /* ════════════════ 图标(内联 SVG) ════════════════ */
    const ICONS = {
      database: 'M12 3c4.97 0 9 1.34 9 3s-4.03 3-9 3-9-1.34-9-3 4.03-3 9-3Z M3 6v12c0 1.66 4.03 3 9 3s9-1.34 9-3V6 M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3',
      pulse: 'M22 12h-4l-3 9L9 3l-3 9H2',
      gauge: 'M12 14l3.5-3.5 M3.34 19a10 10 0 1 1 17.32 0',
      layers: 'M12 2 21 7l-9 5-9-5 9-5Z M2 12l10 5 10-5 M2 17l10 5 10-5',
      graph: 'M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M8.6 10.5l6.8-4 M8.6 13.5l6.8 4',
      network: 'M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M18 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M8.4 7.8l7.2 2.4 M8.4 16.2l7.2-2.4',
      overview: 'M3 3h7v9H3Z M14 3h7v5h-7Z M14 12h7v9h-7Z M3 16h7v5H3Z',
      grid: 'M3 3h7v7H3Z M14 3h7v7h-7Z M3 14h7v7H3Z M14 14h7v7h-7Z',
      search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Z M21 21l-4.35-4.35',
      refresh: 'M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8 M21 3v5h-5',
      alert: 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z M12 9v4 M12 17h.01',
      check: 'M20 6 9 17l-5-5',
      save: 'M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z M17 21v-8H7v8 M7 3v5h8',
      clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M12 7v5l3.5 2',
      cpu: 'M5 5h14v14H5Z M9 9h6v6H9Z M9 2v3 M15 2v3 M9 19v3 M15 19v3 M2 9h3 M2 15h3 M19 9h3 M19 15h3',
      box: 'M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.73Z M3.3 7 12 12l8.7-5 M12 22V12',
      orbit: 'M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0 M18.6 13.4c.6 2.9-1.3 6-4.6 7.4-3.4 1.5-7.2.6-8.9-1.9 M5.4 10.6C4.8 7.7 6.7 4.6 10 3.2c3.4-1.5 7.2-.6 8.9 1.9',
    }
    function Icon({ name, size, color, style }) {
      return h('svg', {
        width: size || 14, height: size || 14, viewBox: '0 0 24 24', fill: 'none',
        stroke: color || 'currentColor', strokeWidth: 1.7,
        strokeLinecap: 'round', strokeLinejoin: 'round',
        style: { flexShrink: 0, ...style },
      }, h('path', { d: ICONS[name] || ICONS.box }))
    }

    /* ════════════════ 工具 ════════════════ */
    const TYPE_COLORS = {
      person: '#58a6ff', org: '#3fb950', tech: '#d29922', concept: '#bc8cff',
      event: '#f85149', location: '#79c0ff', memory: '#56d364', room: '#f0883e',
    }
    // 2026-09-20：房间（room）概念已取消，从类型标签里移除
    const TYPE_LABELS = { person: '人物', org: '组织', tech: '技术', concept: '概念', event: '事件', location: '地点', memory: '记忆' }
    const WING_LABELS = {
      default: '通用', tech: '技术', daily: '日常', preferences: '偏好',
      self_improvement: '自我提升', system: '系统', project: '项目', work: '工作',
    }
    function wingLabel(w) { return WING_LABELS[w] || w }
    function typeColor(type) {
      if (TYPE_COLORS[type]) return TYPE_COLORS[type]
      let hash = 0
      const s = String(type || 'default')
      for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) >>> 0
      return `hsl(${hash % 360} 60% 58%)`
    }
    function withAlpha(color, hexSuffix) {
      if (color.startsWith('#')) return color + hexSuffix
      if (color.startsWith('hsl(')) {
        const inner = color.slice(4, -1)
        const [h, s, l] = inner.split(/\s+/)
        const a = parseInt(hexSuffix, 16) / 255
        return `hsla(${h},${s},${l},${a.toFixed(2)})`
      }
      // CSS 变量（var(...)）无法在 JS 侧拆解，用 color-mix 在浏览器端混合透明度
      if (color.startsWith('var(')) {
        const a = (parseInt(hexSuffix, 16) / 255 * 100).toFixed(0)
        return `color-mix(in srgb, ${color} ${a}%, transparent)`
      }
      return color
    }
    function typeLabel(type) { return TYPE_LABELS[type] || type || '其他' }

    function fmtNum(n) {
      n = Number(n) || 0
      if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M'
      if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'k'
      return String(n)
    }
    function fmtUptime(s) {
      s = Number(s) || 0
      const d = Math.floor(s / 86400), hh = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
      if (d > 0) return `${d}天${hh}小时`
      if (hh > 0) return `${hh}小时${m}分`
      return `${m}分钟`
    }
    function fmtSize(bytes) {
      bytes = Number(bytes) || 0
      if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + 'MB'
      if (bytes >= 1e3) return (bytes / 1e3).toFixed(1) + 'KB'
      return bytes + 'B'
    }
    function fmtAgo(ts) {
      const s = Math.max(0, Math.round((Date.now() - ts) / 1000))
      if (s < 5) return '刚刚'
      if (s < 60) return `${s}秒前`
      if (s < 3600) return `${Math.floor(s / 60)}分前`
      return `${Math.floor(s / 3600)}时前`
    }

    async function callRemote(name, method, args) {
      const remote = (ctx.get && ctx.get('remote.' + name)) || (ctx.remote && ctx.remote[name])
      if (!remote || typeof remote[method] !== 'function') throw new Error('远程服务 ' + name + ' 未就绪')
      // typert 网关按声明参数个数严格校验,无参调用必须零参展开
      return args === undefined ? remote[method]() : remote[method](args)
    }
    /** 把远程错误（字符串 / RemoteFailure 对象）转成可读文案 */
    function describeRemoteError(err) {
      if (typeof err === 'string' && err) return err
      if (err && typeof err.message === 'string' && err.message) return err.message
      try { return JSON.stringify(err) } catch (_) { return '远程调用失败' }
    }

    /**
     * 解开返回值，失败一律抛错（调用方统一用错误态呈现）。
     *
     * ⚠ 有两层信封，别只解一层：
     *  ① 外层是 Typert 协议信封 {ok:true, value} / {ok:false, error}
     *     （dsh 的 packages/typert/protocol/src/types.ts:68-77：
     *      "carrier failures into the error branch" —— 失败走 ok:false，不 reject）
     *  ② 内层是**宿主服务自己的** {ok:false, error}：index.js 的 adminFetch
     *     在「未配置管理密钥」等情况下就是这么返回的。
     * 此前只解外层，于是内层错误被当成正常载荷：取 platforms 得到 undefined
     * → 平台区静默空白，用户完全看不出要填管理密钥（2026-09-21 修）。
     */
    function unwrap(r) {
      if (r === null || r === undefined) throw new Error('远程调用失败：返回为空')
      if (r.ok === false) throw new Error(describeRemoteError(r.error))
      const value = r.ok === true && 'value' in r ? r.value : r
      if (value && typeof value === 'object' && value.ok === false) {
        throw new Error(describeRemoteError(value.error))
      }
      return value
    }

    /* ── canvas 用:从 body 读取令牌实际色值,明暗切换时重读 ── */
    function readPalette() {
      const s = getComputedStyle(document.body)
      const g = (n, f) => { const v = s.getPropertyValue(n).trim(); return v || f }
      return {
        label: g('--dsw-alias-label-secondary', '#8e8e93'),
        edge: g('--dsw-alias-border-l3', 'rgba(128,128,128,.25)'),
        accent: ACCENT,
        isDark: document.body.hasAttribute('data-ds-dark-theme'),
      }
    }
    function useCanvasPalette() {
      const [pal, setPal] = React.useState(readPalette)
      React.useEffect(() => {
        const obs = new MutationObserver(() => setPal(readPalette()))
        obs.observe(document.body, { attributes: true, attributeFilter: ['data-ds-dark-theme', 'class'] })
        return () => obs.disconnect()
      }, [])
      return pal
    }

    /* ── 通用小件 ── */
    function Skeleton({ w, h: hh, r, style }) {
      return h('div', { style: { width: w, height: hh, borderRadius: r || 4, background: css.skeleton, animation: 'panguBlink 1.4s ease-in-out infinite', ...style } })
    }
    function ErrorState({ text, onRetry }) {
      return h('div', { style: { height: '100%', minHeight: 160, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, color: css.t3, animation: 'panguFade .25s ease' } },
        h(Icon, { name: 'alert', size: 22, color: css.err }),
        h('div', { style: { fontSize: 12.5, color: css.t2 } }, text || '加载失败'),
        onRetry && h('button', { className: 'pangu-btn', onClick: onRetry, style: { padding: '5px 14px', fontSize: 12, borderRadius: 7, border: `1px solid ${css.border}`, background: 'transparent', color: css.t1, cursor: 'pointer' } }, '重试'),
      )
    }
    function StatusDot({ state }) {
      const color = state === 'ok' ? css.ok : state === 'error' ? css.err : css.t3
      return h('span', { style: { position: 'relative', width: 8, height: 8, display: 'inline-block', flexShrink: 0 } },
        state === 'ok' && h('span', { style: { position: 'absolute', inset: 0, borderRadius: '50%', background: color, animation: 'panguRing 2.2s ease-out infinite' } }),
        h('span', { style: { position: 'absolute', inset: 0, borderRadius: '50%', background: color } }),
      )
    }
    function TypeChip({ type }) {
      const c = typeColor(type)
      return h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 4, padding: '1px 8px', borderRadius: 999, background: c + '1c', color: c, fontSize: 10, fontWeight: 600, lineHeight: '16px', flexShrink: 0 } },
        h('span', { style: { width: 5, height: 5, borderRadius: '50%', background: c } }),
        typeLabel(type),
      )
    }
    function SectionTitle({ children, style }) {
      return h('div', { style: { fontSize: 11, fontWeight: 600, color: css.t3, margin: '18px 0 4px', textTransform: 'uppercase', letterSpacing: '0.6px', ...(style || {}) } }, children)
    }
    function InfoRow({ label, value }) {
      return h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: `1px solid ${css.borderSoft}` } },
        h('span', { style: { fontSize: 12, color: css.t3, flexShrink: 0 } }, label),
        h('span', { style: { fontSize: 12, color: css.t1, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, value || '—'),
      )
    }

    /* ════════════════════════════════════════════
     * 1. 侧边栏内联指标卡(宽/窄双形态,独占一行)
     * ════════════════════════════════════════════ */
    function Metric({ icon, tint, label, value, pct, danger }) {
      const c = danger === 'err' ? css.err : danger === 'warn' ? css.warn : tint
      return h('div', { style: { marginBottom: 9 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 } },
          h(Icon, { name: icon, size: 12, color: c }),
          h('span', { style: { fontSize: 11, color: css.t2, flex: 1 } }, label),
          h('span', { style: { fontSize: 11, fontWeight: 600, color: css.t1, fontVariantNumeric: 'tabular-nums' } }, value),
        ),
        h('div', { style: { height: 4, background: css.bg3, borderRadius: 2, overflow: 'hidden' } },
          h('div', { style: { height: '100%', width: Math.min(100, Math.max(0, pct)) + '%', background: `linear-gradient(90deg, ${c}b3, ${c})`, borderRadius: 2, transition: 'width .6s cubic-bezier(.22,1,.36,1)' } }),
        ),
      )
    }


    /* ════════════════════════════════════════════
     * 1. 侧边栏体征帧(v5:方向 A——状态点+三格体征+管线行+快速入库)
     * ════════════════════════════════════════════ */

    // 7 日记忆脉搏 sparkline（内联 SVG，供侧栏和概览页共用）
    // 侧栏迷你脉搏（v6 改进）：柱=创建 + 线=召回，与概览页 PulseChart 同一视觉语言。
    // 此前是一条 140×22 的裸折线：无填充/端点/标签，宽度写死（226px 的侧栏里偏窄），
    // 且只有创建没有召回。
    function Sparkline7({ created, recalled, data, height, showLabel }) {
      // 兼容旧调用（data 即 created）
      const days = ((created || data || []).slice(-7))
      const rcs = (recalled || []).slice(-7)
      if (!days || days.length < 2) return null
      const wrapRef = React.useRef(null)
      const [W, setW] = React.useState(190)
      React.useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === 'undefined') return undefined
        const ro = new ResizeObserver((entries) => {
          const w = entries[0] && entries[0].contentRect ? entries[0].contentRect.width : 0
          if (w) setW(Math.max(120, Math.round(w)))
        })
        ro.observe(el)
        return () => ro.disconnect()
      }, [])
      const H = height || 30, TOP = 4, BOTTOM = H - 4
      const n = days.length
      const step = W / n
      const maxC = Math.max(1, ...days.map((d) => Number(d.count) || 0))
      const maxR = Math.max(1, ...rcs.map((d) => Number(d.count) || 0))
      const barW = Math.max(6, Math.min(16, Math.round(step * 0.5)))
      const xC = (i) => Math.round(step * i + step / 2)
      const barH = (c) => Math.round(((BOTTOM - TOP) * (Number(c) || 0)) / maxC)
      const yR = (c) => Math.round(BOTTOM - ((BOTTOM - TOP) * (Number(c) || 0)) / maxR)
      const hasRecall = rcs.some((d) => (Number(d.count) || 0) > 0)
      const total = days.reduce((a, d) => a + (Number(d.count) || 0), 0)
      const rTotal = rcs.reduce((a, d) => a + (Number(d.count) || 0), 0)
      const today = Number(days[n - 1]?.count) || 0
      const yesterday = Number(days[n - 2]?.count) || 0
      const delta = today - yesterday
      return h('div', { ref: wrapRef, style: { marginTop: 8 } },
        h('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', style: { width: '100%', height: H, display: 'block' }, 'aria-hidden': 'true' },
          // 基线
          h('line', { x1: 0, y1: BOTTOM, x2: W, y2: BOTTOM, stroke: css.borderSoft, strokeWidth: 1 }),
          // 创建柱（accent，随高度加深）
          h('g', null, days.map((d, i) => {
            const hh = Math.max(2, barH(d.count))
            return h('rect', { key: i, x: xC(i) - barW / 2, y: BOTTOM - hh, width: barW, height: hh, rx: 2, fill: ACCENT, opacity: (0.35 + (0.45 * hh) / (BOTTOM - TOP)).toFixed(2) })
          })),
          // 召回折线（info；没采集到时不出）
          hasRecall && h('polyline', { points: rcs.map((d, i) => xC(i) + ',' + yR(d.count)).join(' '), fill: 'none', stroke: css.info, strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round', opacity: 0.9 }),
          // 今日端点
          h('circle', { cx: xC(n - 1), cy: BOTTOM - Math.max(2, barH(today)), r: 2.5, fill: ACCENT }),
        ),
        showLabel !== false && h('div', { style: { fontSize: 9.5, color: css.t3, marginTop: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' } },
          h('span', null, '7日 ', h('b', { style: { color: css.t2 } }, total), ' 条',
            hasRecall ? h('span', null, ' · 召回 ', h('b', { style: { color: css.t2 } }, rTotal)) : null),
          h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', color: delta > 0 ? css.ok : delta < 0 ? css.warn : css.t3 } },
            '今日 ' + today, delta !== 0 ? (delta > 0 ? ' ↑' + delta : ' ↓' + Math.abs(delta)) : ''),
        ),
      )
    }
    function SidebarCard({ wide }) {
      const [state, setState] = React.useState({ status: 'loading', data: null, at: 0 })
      const [addState, setAddState] = React.useState({ s: 'idle', msg: '' })
      const [draft, setDraft] = React.useState('')
      const rootRef = React.useRef(null)
      const lastTsRef = React.useRef(0)
      const load = React.useCallback(async () => {
        try {
          const value = unwrap(await callRemote('panguDashboard', 'data'))
          setState({ status: 'ok', data: value, at: Date.now() })
        } catch (e) {
          console.warn('[pangu-dashboard] 侧边栏数据加载失败:', String((e && e.message) || e))
          setState((p) => ({ status: p.data ? 'ok' : 'error', data: p.data, at: p.at || Date.now() }))
        }
      }, [])

      React.useEffect(() => {
        load()
        const tick = () => { if (!document.hidden) load() }
        const stop = timer && timer.interval
          ? timer.interval(tick, 30000)
          : (() => { const id = setInterval(tick, 30000); return () => clearInterval(id) })()
        const evTick = async () => {
          try {
            const v = unwrap(await callRemote('panguDashboard', 'events', { since: lastTsRef.current }))
            lastTsRef.current = v?.lastTs || lastTsRef.current
            if (v?.count > 0 && !document.hidden) load()
          } catch (_) {}
        }
        const stop2 = timer && timer.interval
          ? timer.interval(evTick, 12000)
          : (() => { const id = setInterval(evTick, 12000); return () => clearInterval(id) })()
        const offReset = ctx && ctx.on ? ctx.on('connection/reset', load) : null
        return () => { if (stop) stop(); if (stop2) stop(); if (offReset) offReset() }
      }, [])

      const doAdd = async () => {
        const content = draft.trim()
        if (!content || addState.s === 'saving') return
        setAddState({ s: 'saving', msg: '' })
        try {
          const v = unwrap(await callRemote('panguDashboard', 'add', { content }))
          if (!v?.ok) throw new Error(v?.error || '添加失败')
          setDraft('')
          setAddState({ s: 'ok', msg: '已入库' })
          load()
          setTimeout(() => setAddState({ s: 'idle', msg: '' }), 2500)
        } catch (e) {
          setAddState({ s: 'error', msg: String(e.message || e).slice(0, 60) })
          setTimeout(() => setAddState({ s: 'idle', msg: '' }), 3500)
        }
      }

      React.useEffect(() => {
        let el = rootRef.current
        for (let i = 0; i < 3 && el; i++) {
          el = el.parentElement
          if (!el) break
          const cs = getComputedStyle(el)
          if (cs.display === 'flex' && cs.flexDirection === 'row') {
            el.style.flexWrap = 'wrap'
            break
          }
        }
      }, [])

      const s = state.data?.stats
      const total = s?.total || 0
      const health = s?.health || '?'
      const degraded = health === 'degraded' || health === 'unreachable'
      const loading = state.status === 'loading'

      if (!wide) {
        return h('div', { ref: rootRef, title: '盘古记忆系统' + (state.status === 'error' ? '(离线)' : ''), style: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 28, margin: '2px auto 6px', borderRadius: 8, background: css.bg2, border: `1px solid ${css.borderSoft}` } },
          loading
            ? h(Skeleton, { w: 12, h: 12, r: 4 })
            : h('span', { style: { width: 14, height: 14, borderRadius: 5, background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_DEEP})`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', opacity: state.status === 'error' ? 0.35 : 1 } },
                h(Icon, { name: 'box', size: 9, color: '#fff' }),
              ),
        )
      }

      const pipeRow = (dotColor, label, value, onClick) =>
        h('button', {
          onClick, style: { display: 'flex', alignItems: 'center', gap: 6, width: '100%', border: 'none', background: 'transparent', padding: '3px 4px', borderRadius: 6, cursor: onClick ? 'pointer' : 'default', color: css.t2, fontSize: 10.5, textAlign: 'left', transition: 'background .15s' },
        },
          h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0 } }),
          h('span', { style: { flex: 1 } }, label),
          h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10.5, fontWeight: 600, color: css.t1 } }, value),
        )

      return h('div', { ref: rootRef, style: { width: '100%', flexShrink: 0, boxSizing: 'border-box', margin: '14px 0 8px', padding: '11px 13px 9px', background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, animation: 'panguFade .25s ease' } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
          h('span', { style: { width: 8, height: 8, borderRadius: '50%', background: degraded ? css.warn : ACCENT, flexShrink: 0, animation: 'panguPulse 2.6s ease-in-out infinite' } }),
          h('span', { style: { fontSize: 12, fontWeight: 600, color: css.t1 } }, '盘古 · ' + (state.status === 'error' ? '离线' : '在线')),
          h('span', { style: { marginLeft: 'auto', fontSize: 9.5, color: css.t3, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' } }, fmtAgo(state.at)),
        ),
        loading
          ? h('div', { style: { marginTop: 9 } }, [0, 1, 2].map((i) => h(Skeleton, { key: i, w: '100%', h: 10, r: 3, style: { marginBottom: 6 } })))
          : [
              h('div', { key: 'vol', style: { marginTop: 7, fontSize: 11.5, color: css.t2 } },
                h('b', { style: { color: css.t1, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' } }, fmtNum(total)),
                ' 条记忆', h('span', { style: { color: css.border, margin: '0 5px' } }, '·'),
                '健康 ', h('b', { style: { color: degraded ? css.warn : css.t1, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' } }, health),
              ),
              h(Sparkline7, { key: 'pulse', created: s?.dailyCounts, recalled: s?.dailyRecalls, height: 30 }),
              h('div', { key: 'mini', style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', marginTop: 8, borderTop: `1px solid ${css.borderSoft}`, borderBottom: `1px solid ${css.borderSoft}` } },
                // 2026-09-20：knowledge/platformsCount 挂在 wire 的 stats 下（网关把
                // host 扁平返回包一层 stats），顶层读不到 → 双路径兜底
                [['实体', s?.kgEntities != null ? fmtNum(s.kgEntities) : '—'],
                 ['知识', (state.data?.knowledge ?? s?.knowledge)?.total != null ? fmtNum((state.data?.knowledge ?? s?.knowledge).total) : '—'],
                 ['来源', Object.keys(state.data?.bySource || s?.bySource || {}).length || '—']].map(([l, v]) =>
                  h('div', { key: l, className: 'pangu-vital', style: { padding: '7px 2px 6px', textAlign: 'center' } },
                    h('div', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 14, fontWeight: 600, color: css.t1, lineHeight: 1.15 } }, v),
                    h('div', { style: { fontSize: 9, color: css.t3, letterSpacing: '.05em', marginTop: 1 } }, l),
                  )),
              ),
              h('div', { key: 'pipe', style: { marginTop: 7, paddingTop: 7, borderTop: `1px dashed ${css.borderSoft}`, display: 'flex', flexDirection: 'column', gap: 2 } },
                pipeRow(css.ok, '知识库', (state.data?.knowledge ?? s?.knowledge)?.total != null ? fmtNum((state.data?.knowledge ?? s?.knowledge).total) + ' 条' : '—', () => window.dispatchEvent(new CustomEvent('pangu:goto', { detail: { tab: 'knowledge' } }))),
                // 2026-09-20 修复：平台接入数此前错用 bySource 键数（记忆来源类型）；
                // 且 platformsCount 与 knowledge 一样挂在 wire 的 stats 下，需双路径兜底。
                pipeRow(css.info, '平台接入', (state.data?.platformsCount ?? s?.platformsCount) != null ? (state.data?.platformsCount ?? s?.platformsCount) + ' 个' : '—', () => window.dispatchEvent(new CustomEvent('pangu:goto', { detail: { tab: 'admin' } }))),
              ),
            ],
        h('div', { key: 'quickadd', style: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 9 } },
          h('input', {
            className: 'pangu-input', value: draft,
            placeholder: addState.s === 'ok' ? '已入库 ✓' : '快速记一条…(回车入库)',
            onChange: (e) => setDraft(e.target.value),
            onKeyDown: (e) => { if (e.key === 'Enter') doAdd() },
            style: { flex: 1, minWidth: 0, padding: '5px 9px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg1, color: addState.s === 'ok' ? css.ok : css.t1, fontSize: 11, outline: 'none', boxSizing: 'border-box' },
          }),
          h('button', {
            className: 'pangu-btn', onClick: doAdd,
            disabled: addState.s === 'saving' || !draft.trim(),
            title: '添加到盘古记忆',
            style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 25, height: 25, borderRadius: 7, border: 'none', background: draft.trim() ? ACCENT : css.bg3, color: draft.trim() ? '#fff' : css.t3, fontSize: 13, fontWeight: 700, cursor: draft.trim() ? 'pointer' : 'default', flexShrink: 0, transition: 'background .15s' },
          }, addState.s === 'saving' ? '…' : '+'),
        ),
        addState.s === 'error' && h('div', { style: { fontSize: 10, color: css.err, marginTop: 3 } }, addState.msg),
      )
    }

    /* ════════════════════════════════════════════
     * 2. 顶部标签页 — 概览 / 星系 / 结晶 / 管理 (v5)
     * ════════════════════════════════════════════ */
    function StatusPill({ status }) {
      const color = status === 'ok' ? css.ok : status === 'fail' || status === 'degraded' ? css.err : css.t3
      return h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, color: css.t1 } },
        h('span', { style: { width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 } }),
        status === 'ok' ? '正常' : status === 'fail' ? '异常' : status || '—',
      )
    }

    function Vital({ v, l, d, danger }) {
      return h('div', { className: 'pangu-vital', style: { flex: 1, padding: '11px 6px 10px', textAlign: 'center' } },
        h('div', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 20, fontWeight: 600, color: danger ? css.warn : css.t1, letterSpacing: '-.015em', lineHeight: 1.1 } }, v),
        h('div', { style: { fontSize: 9.5, color: css.t3, letterSpacing: '.07em', marginTop: 3 } }, l),
        d && h('div', { style: { fontSize: 9.5, color: css.t3, marginTop: 3 } }, d),
      )
    }

    function SecHead({ num, title, hint }) {
      return h('div', { style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '2px 0 7px', borderBottom: `1px solid ${css.borderSoft}`, margin: '20px 0 0' } },
        h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, num),
        h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, title),
        hint && h('span', { style: { fontSize: 10.5, color: css.t3 } }, hint),
      )
    }

    function PipelineBox({ st, v, small, d, warn, off, arrow }) {
      return h('div', { style: { flex: 1, minWidth: 0, padding: '10px 12px', position: 'relative' } },
        h('div', { style: { fontSize: 9.5, color: css.t3, letterSpacing: '.08em' } }, st),
        h('div', { style: { fontSize: 15, fontWeight: 600, marginTop: 2, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', color: warn ? css.warn : off ? css.t3 : css.t1 } }, v, small && h('span', { style: { fontSize: 10, color: css.t3, fontWeight: 400, marginLeft: 3 } }, small)),
        d && h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 3, lineHeight: 1.5 } }, d),
        arrow && h('span', { style: { position: 'absolute', right: -8, top: '50%', transform: 'translateY(-50%)', width: 15, height: 15, border: `1px solid ${css.borderSoft}`, background: css.bg1, borderRadius: '50%', display: 'grid', placeItems: 'center', color: css.t3, fontSize: 9, zIndex: 2 } }, '→'),
      )
    }

    function MemRow({ m }) {
      // 点击整行展开/收起：摘要默认 2 行截断（line-clamp），此前行是死的 —— 截断后
      // 没有任何办法看到全文（用户报"底部无法点击"）。
      const [open, setOpen] = React.useState(false)
      // 优先用后端给的 encrypted 字段（后端已解密并给出 summary）
      const enc = m.encrypted === true || (typeof m.content === 'string' && m.content.startsWith('gAAAAA'))
      const imp = Number(m.importance || 0)
      return h('div', {
        onClick: () => setOpen((v) => !v),
        title: open ? '点击收起' : '点击展开全文',
        style: { display: 'flex', gap: 10, padding: '9px 2px', borderBottom: `1px solid ${css.borderSoft}`, alignItems: 'flex-start', cursor: 'pointer' },
      },
        h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, color: css.t3, width: 34, flexShrink: 0, paddingTop: 2 } }, (m.graduated_at || m.created_at || '').slice(5, 10)),
        h('div', { style: { flex: 1, minWidth: 0 } },
          h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center', fontSize: 10, color: css.t3 } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', color: css.t2 } }, (m.source_wing || m.wing || '?') + ' / ' + (m.source_room || m.room || '?')),
            (m.tags || []).slice(0, 3).map((t) => h('span', { key: t, style: { border: `1px solid ${css.borderSoft}`, borderRadius: 4, padding: '0 5px', fontSize: 9.5 } }, t)),
            enc && h('span', { className: 'pangu-stampline' }, '已加密'),
          ),
          h('div', { style: { fontSize: 11.5, color: (enc && !m.summary) ? css.t3 : css.t1, marginTop: 3, lineHeight: 1.55, fontStyle: (enc && !m.summary) ? 'italic' : 'normal', display: '-webkit-box', WebkitLineClamp: open ? 'unset' : 2, WebkitBoxOrient: 'vertical', overflow: open ? 'visible' : 'hidden' } },
            // 2026-09-20 修复：展开时显示全文 —— 原来无条件 slice(0,120)，
            // 行截断已由 line-clamp 承担，slice 导致展开后也只有 120 字。
            m.summary || (enc ? '（加密内容 · 摘要不可用）' : (open ? (m.content || '') : (m.content || '').slice(0, 120)))),
          open && h('div', { style: { fontSize: 9.5, color: css.t3, marginTop: 3 } }, '点击收起'),
        ),
        h('div', { style: { flexShrink: 0, textAlign: 'right' } },
          h('div', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 11.5, fontWeight: 600 } }, imp ? imp.toFixed(1) : '—'),
          h('div', { style: { fontSize: 9, color: css.t3 } }, '印象'),
        ),
      )
    }
    // 7 日记忆脉搏：创建柱（accent）+ 召回折线（info），照重设计稿样品实现。
    // created 来自后端按 created_at 现算；recalled 来自插件侧按天采集的 /ws memory_recall
    // （盘古没有按日召回历史，采集从本版本开始，前几日为 0 属预期）。
    function PulseChart({ created, recalled }) {
      const days = (created || []).slice(-7)
      const recalls = (recalled || []).slice(-7)
      const n = Math.max(1, days.length)
      // 宽度跟随容器：viewBox 与实际像素 1:1，柱宽/字号/圆都按设计值固定。
      // 此前 viewBox 固定 620 + preserveAspectRatio:'none'，容器一宽（宽屏实测 1248px）
      // 整个图被横向拉 2.01 倍 —— 字变胖、柱变宽、圆变椭圆（用户报"宽屏拉长变形"）。
      const wrapRef = React.useRef(null)
      const [W, setW] = React.useState(620)
      React.useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === 'undefined') return undefined
        const ro = new ResizeObserver((entries) => {
          const w = entries[0] && entries[0].contentRect ? entries[0].contentRect.width : 0
          if (w) setW(Math.max(320, Math.round(w)))
        })
        ro.observe(el)
        return () => ro.disconnect()
      }, [])
      const H = 132, TOP = 26, BOTTOM = 102
      const maxC = Math.max(1, ...days.map((d) => Number(d.count) || 0))
      const maxR = Math.max(1, ...recalls.map((d) => Number(d.count) || 0))
      const step = W / n
      // 柱宽取设计值 22，但容器很窄时收窄到 step 的 60% 防重叠（宽屏下不再被拉宽）
      const barW = Math.max(8, Math.min(22, Math.round(step * 0.6)))
      const xC = (i) => Math.round(step * i + step / 2)
      const barH = (c) => Math.round(((BOTTOM - TOP) * (Number(c) || 0)) / maxC)
      const yR = (c) => Math.round(BOTTOM - ((BOTTOM - TOP) * (Number(c) || 0)) / maxR)
      const hasRecall = recalls.some((d) => (Number(d.count) || 0) > 0)
      return h('div', { ref: wrapRef },
        // preserveAspectRatio 用 meet（非 none）：首帧测量未回来时宁可两侧留白也不拉伸
        h('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet', style: { width: '100%', height: H, display: 'block' }, 'aria-hidden': 'true' },
          h('g', { stroke: css.borderSoft, strokeWidth: 1 },
            [TOP, Math.round((TOP + BOTTOM) / 2), BOTTOM].map((y, i) => h('line', { key: i, x1: 0, y1: y, x2: W, y2: y })),
          ),
          hasRecall && h('polyline', {
            points: recalls.map((d, i) => xC(i) + ',' + yR(d.count)).join(' '),
            fill: 'none', stroke: css.info, strokeWidth: 1.7, opacity: 0.9,
          }),
          hasRecall && h('g', { fill: css.info },
            recalls.map((d, i) => h('circle', { key: i, cx: xC(i), cy: yR(d.count), r: 2.5 })),
          ),
          h('g', null, days.map((d, i) => {
            const hh = Math.max(2, barH(d.count))
            return h('rect', {
              key: i, x: xC(i) - barW / 2, y: BOTTOM - hh, width: barW, height: hh, rx: 2.5,
              fill: ACCENT, opacity: (0.45 + (0.5 * hh) / (BOTTOM - TOP)).toFixed(2),
            })
          })),
          h('g', { fontSize: 9, fill: css.t3, textAnchor: 'middle', fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' },
            days.map((d, i) => h('text', { key: i, x: xC(i), y: H - 8 }, i === n - 1 ? '今日' : String((d.date || '').slice(5)))),
          ),
        ),
        h('div', { style: { display: 'flex', gap: 14, marginTop: 3, fontSize: 10.5, color: css.t3 } },
          h('span', null,
            h('i', { style: { display: 'inline-block', width: 9, height: 9, borderRadius: 2, marginRight: 4, verticalAlign: -1, background: ACCENT } }),
            '摄入（条）'),
          h('span', null,
            h('i', { style: { display: 'inline-block', width: 9, height: 9, borderRadius: '50%', marginRight: 4, verticalAlign: -1, background: css.info } }),
            hasRecall ? '召回（次）' : '召回（本版起采集）'),
          h('span', { style: { marginLeft: 'auto' } },
            '夜间巩固窗口 ', h('b', { style: { color: css.t2 } }, '03:00–05:00')),
        ),
      )
    }

    function OverviewPane({ dash, config, dashErr, loading, onRetry }) {
      const [pubMems, setPubMems] = React.useState([])
      React.useEffect(() => {
        let alive = true
        callRemote('panguAdminKeys', 'listRecentMemories')
          .then(unwrap)
          .then((v) => { if (alive) setPubMems(v?.memories || []) })
          .catch(() => {})
        return () => { alive = false }
      }, [])

      if (dashErr && !dash) return h(ErrorState, { text: '无法连接盘古服务(' + dashErr + ')', onRetry })
      const s = dash?.stats
      if (loading && !dash) {
        return h('div', { style: { padding: 16 } },
          h(Skeleton, { w: '100%', h: 64, r: 10 }),
          h(Skeleton, { w: '100%', h: 96, r: 10, style: { marginTop: 12 } }),
          h(Skeleton, { w: '100%', h: 90, r: 10, style: { marginTop: 12 } }),
        )
      }
      const degraded = s?.health === 'degraded' || s?.health === 'unreachable'
      // 管线真实数据（后端 stats.pipeline）。此前三格是硬编码：审核写死 '—' 把 57 条待审
      // 藏了、加密错取高密级数（真实 62 条已加密显示成 0）、巩固写死 '未运行'。
      const pipe = s?.pipeline
      const cons = pipe?.consolidation
      const relTime = (iso) => {
        const t = Date.parse(iso)
        if (!t) return '—'
        const sec = Math.max(0, (Date.now() - t) / 1000)
        if (sec < 3600) return Math.max(1, Math.floor(sec / 60)) + ' 分钟前'
        if (sec < 86400) return Math.floor(sec / 3600) + ' 小时前'
        return Math.floor(sec / 86400) + ' 天前'
      }
      const consLabel = cons?.last_run ? relTime(cons.last_run) : cons ? '从未运行' : '—'
      return h('div', { style: { padding: '14px 16px 20px', overflow: 'auto', height: '100%', boxSizing: 'border-box', animation: 'panguFade .25s ease' } },
        // 宽屏下内容会被无限拉长（宽屏实测主区 1248px）：卡片横条、管线三格右侧出现大片
        // 空白，脉搏图更被拉变形。统一限宽居中 —— 面板是用来读数字的，不是铺满大屏的仪表盘。
        h('div', { style: { maxWidth: 1120, margin: '0 auto' } },
        // ① 体征带
        h('div', { style: { display: 'flex', borderTop: `1px solid ${css.borderSoft}`, borderBottom: `1px solid ${css.borderSoft}` } },
          h(Vital, { v: fmtNum(s?.total || 0), l: '记忆总量', d: h('span', null, '健康 ', h('b', { style: { color: degraded ? css.warn : css.t2 } }, s ? (s.health || '—') : '—')) }),
          h(Vital, { v: s?.wings != null ? fmtNum(s.wings) : '—', l: '知识翼', d: '宫殿结构' }),
          h(Vital, { v: (dash?.knowledge ?? s?.knowledge)?.total != null ? fmtNum((dash?.knowledge ?? s?.knowledge).total) : (s?.kgEntities != null ? fmtNum(s.kgEntities) : '—'), l: '知识库', d: (dash?.knowledge ?? s?.knowledge)?.total != null ? Object.keys(((dash?.knowledge ?? s?.knowledge).categories) || {}).length + ' 类' : '知识结晶' }),
          h(Vital, { v: dash?.snapshots?.total != null ? fmtNum(dash.snapshots.total) : '—', l: '进化快照', d: '记忆替换记录' }),
        ),
        // ② 7日记忆脉搏
        h('div', { style: { marginTop: 4 } },
          h(SecHead, { num: '02', title: '7日记忆脉搏', hint: '创建与召回 · 数据源 /ws + created_at' }),
          h('div', { style: { marginTop: 9, border: `1px solid ${css.borderSoft}`, borderRadius: 12, padding: '12px 14px 8px', background: css.bg1 } },
            h(PulseChart, { created: s?.dailyCounts, recalled: s?.dailyRecalls }),
          ),
        ),
        // ③ 记忆管线
        h('div', { style: { marginTop: 4 } },
          h(SecHead, { num: '03', title: '记忆管线', hint: '去重 → 审核准入 → 毕业 → 夜间巩固' }),
          h('div', { style: { display: 'flex', border: `1px solid ${css.borderSoft}`, borderRadius: 10, overflow: 'hidden', marginTop: 9, background: css.bg1 } },
            h(PipelineBox, {
              st: '准入验证',
              v: pipe ? fmtNum(pipe.pending_review) : '—',
              small: '待验证',
              // 不做人工审：记忆被召回成功/被验证（正向反馈）且带来源指针时自动毕业
              // （原文案"缺来源指针进入人工审"不实 —— 全仓没有人工审核入口）。
              d: pipe && pipe.pending_review > 0 ? '召回成功自动毕业' : '全部通过',
              warn: !!(pipe && pipe.pending_review > 0),
              arrow: true,
            }),
            // 2026-09-20：写入加密已按 PANGU_ENCRYPTION=off 关闭（单人系统无需落盘加密），
            // 原「加密存储」格换成「记忆毕业」—— 与管线语义一致（待审 → 毕业）。
            h(PipelineBox, { st: '记忆毕业', v: pipe ? fmtNum(pipe.graduated) : '—', small: '已毕业', d: '准入通过 · 进公共只读区', arrow: true }),
            h(PipelineBox, {
              st: '夜间巩固',
              v: consLabel,
              d: h('span', null, '窗口 ', h('b', { style: { color: css.t2 } }, '03:00–05:00'), ' · 24h'),
              off: !(cons && cons.last_run),
            }),
          ),
          degraded && h('div', { style: { marginTop: 8, border: `1px solid ${css.warn}`, borderRadius: 8, padding: '9px 12px', fontSize: 11, color: css.t2, background: withAlpha(css.warn, '0d'), lineHeight: 1.6 } },
            '健康状态 ', h('b', null, s?.health), ' —— 检查 identity 层（L0）、夜间巩固与检索链路；操作见「管理」页。'),
        ),
        // ③ 宫殿速览
        h('div', { style: { marginTop: 4 } },
          h(SecHead, { num: '04', title: '宫殿速览', hint: 'Wing 分布 · 悬停看计数' }),
          (() => {
            const byWing = s?.byWing || {}
            const entries = Object.entries(byWing).sort((a, b) => b[1] - a[1]).slice(0, 6)
            const total = entries.reduce((a, e) => a + e[1], 0) || 1
            const palette = [ACCENT, css.info, css.ok, css.warn, css.err, css.t3]
            return h('div', { style: { marginTop: 9 } },
              h('div', { style: { display: 'flex', height: 22, borderRadius: 6, overflow: 'hidden', border: `1px solid ${css.borderSoft}` } },
                entries.length ? entries.map(([w, n], i) => h('div', {
                  key: w, title: wingLabel(w) + ' · ' + n + ' 条',
                  style: { width: (n / total * 100) + '%', background: palette[i % palette.length], minWidth: 3 },
                })) : h('div', { style: { padding: '4px 10px', fontSize: 10.5, color: css.t3 } }, '暂无翼数据'),
              ),
              h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '5px 14px', marginTop: 7, fontSize: 10.5, color: css.t3 } },
                entries.map(([w, n], i) => h('span', { key: w },
                  h('span', { style: { display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: palette[i % palette.length], marginRight: 4, verticalAlign: '-1px' } }),
                  wingLabel(w), h('b', { style: { color: css.t2, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, marginLeft: 3 } }, n))),
              ),
            )
          })(),
        ),
        // ④ 来源分布
        h('div', { style: { marginTop: 4 } },
          h(SecHead, { num: '05', title: '来源分布', hint: '记忆来源平台 · 悬停看计数' }),
          (() => {
            // 从后端 stats 获取来源分布（by_source 字段）
            const bySource = dash?.bySource || s?.bySource || {}
            const entries = Object.entries(bySource).sort((a, b) => b[1] - a[1]).slice(0, 8)
            const total = entries.reduce((a, e) => a + e[1], 0) || 1
            const palette = [ACCENT, css.info, css.ok, css.warn, css.err, '#bc8cff', '#79c0ff', css.t3]
            return h('div', { style: { marginTop: 9 } },
              h('div', { style: { display: 'flex', height: 22, borderRadius: 6, overflow: 'hidden', border: `1px solid ${css.borderSoft}` } },
                entries.length ? entries.map(([src, n], i) => h('div', {
                  key: src, title: src + ' · ' + n + ' 条',
                  style: { width: (n / total * 100) + '%', background: palette[i % palette.length], minWidth: 3 },
                })) : h('div', { style: { padding: '4px 10px', fontSize: 10.5, color: css.t3 } }, '暂无来源数据'),
              ),
              h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '5px 14px', marginTop: 7, fontSize: 10.5, color: css.t3 } },
                entries.map(([src, n], i) => h('span', { key: src },
                  h('span', { style: { display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: palette[i % palette.length], marginRight: 4, verticalAlign: '-1px' } }),
                  src, h('b', { style: { color: css.t2, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, marginLeft: 3 } }, n))),
              ),
            )
          })(),
        ),
        // ⑥ 最近入库
        h('div', { style: { marginTop: 4 } },
          h(SecHead, { num: '06', title: '最近入库', hint: '全库最新 ' + Math.min(5, pubMems.length) + ' 条 · 点击条目展开全文' }),
          pubMems.length
            ? h('div', { style: { marginTop: 4 } }, pubMems.slice(0, 5).map((m) => h(MemRow, { key: m.id, m })))
            : h('div', { style: { padding: '10px 0', fontSize: 11, color: css.t3 } }, '暂无记忆'),
        ),
        ),
      )
    }
    /* ── 3D 星系图谱:Canvas2D 手写透视投影,无第三方依赖 ── */
    const GALAXY = {
      R: 260,          // 盘面半径(世界坐标)
      FOV: 900,        // 透视焦距
      SPIN: 0.0022,    // 默认自转角速度(弧度/帧)
    }

    function galaxyLayout(nCount) {
      // 盘面螺旋分布:y 随半径微降,z 高斯薄盘,旋臂感由随机角+内密外疏产生
      const pts = []
      for (let i = 0; i < nCount; i++) {
        const t = (i + 0.5) / nCount
        const ang = t * Math.PI * 6 + Math.random() * 0.5
        const rad = GALAXY.R * (0.18 + 0.82 * Math.sqrt(Math.random()))
        pts.push({
          x: Math.cos(ang) * rad,
          y: (Math.random() - 0.5) * 34,
          z: Math.sin(ang) * rad,
        })
      }
      return pts
    }

    function GalaxyCanvas({ nodes, edges, matchSet, palette }) {
      const wrapRef = React.useRef(null)
      const canvasRef = React.useRef(null)
      const st = React.useRef({
        nodes: [], edges: [], nm: new Map(), adj: new Map(), dust: [],
        yaw: 0.5, pitch: -0.42, spin: GALAXY.SPIN, zoom: 1,
        dragView: false, dragNode: null, _lx: 0, _ly: 0,
        hover: null, lastHoverId: null, af: 0, dpr: 1, w: 0, h: 0,
        proj: [], pal: null, alpha: 1,
      })
      const [tooltip, setTooltip] = React.useState(null)
      const [zoomLabel, setZoomLabel] = React.useState(100)
      const palRef = React.useRef(palette)
      palRef.current = palette
      // Obsidian 式搜索高亮:Set 为命中 id;非命中降暗而非移除
      const matchRef = React.useRef(matchSet)
      matchRef.current = matchSet

      // 数据初始化:盘面布局 + 邻接表 + 星尘
      React.useEffect(() => {
        const s = st.current
        const pts = galaxyLayout(nodes.length)
        s.nodes = (nodes || []).map((n, i) => ({
          ...n,
          x: pts[i].x, y: pts[i].y, z: pts[i].z,
          vx: 0, vy: 0, vz: 0,
          r: Math.min(15, 4.5 + Math.sqrt(n.memory_count || 1) * 1.6),
        }))
        s.nm = new Map(s.nodes.map((n) => [n.id, n]))
        s.edges = edges || []
        s.adj = new Map()
        s.edges.forEach((e) => {
          if (!s.adj.has(e.source)) s.adj.set(e.source, [])
          if (!s.adj.has(e.target)) s.adj.set(e.target, [])
          s.adj.get(e.source).push({ other: e.target, edge: e })
          s.adj.get(e.target).push({ other: e.source, edge: e })
        })
        s.dust = []
        for (let i = 0; i < 260; i++) {
          const ang = Math.random() * Math.PI * 2
          const rad = GALAXY.R * (0.15 + 0.95 * Math.random())
          s.dust.push({
            x: Math.cos(ang) * rad,
            y: (Math.random() - 0.5) * 90,
            z: Math.sin(ang) * rad,
            s: 0.5 + Math.random() * 0.9,
            o: 0.08 + Math.random() * 0.2,
          })
        }
        s.hover = null; s.lastHoverId = null
        setTooltip(null)
        s.alpha = 1
      }, [nodes, edges])

      React.useEffect(() => {
        const s = st.current, wrap = wrapRef.current, c = canvasRef.current
        if (!wrap || !c) return
        const ctx2 = c.getContext('2d')

        const resize = () => {
          const w = wrap.clientWidth, hh = wrap.clientHeight
          if (!w || !hh) return
          const dpr = Math.min(2, window.devicePixelRatio || 1)
          c.width = Math.round(w * dpr); c.height = Math.round(hh * dpr)
          s.dpr = dpr; s.w = w; s.h = hh
        }
        resize()
        const ro = new ResizeObserver(resize)
        ro.observe(wrap)

        function project(x, y, z) {
          const cy = Math.cos(s.yaw), sy = Math.sin(s.yaw)
          const x1 = x * cy - z * sy, z1 = x * sy + z * cy
          const cp = Math.cos(s.pitch), sp = Math.sin(s.pitch)
          const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp
          const persp = GALAXY.FOV / (GALAXY.FOV + z2)
          return { sx: s.w / 2 + x1 * persp * s.zoom, sy: s.h / 2 + y2 * persp * s.zoom, persp, depth: z2 }
        }
        // 屏幕位移 → 世界位移(保持相机平面,逆 pitch → 逆 yaw)
        function unprojectDelta(dx, dy) {
          const cy = Math.cos(s.yaw), sy = Math.sin(s.yaw)
          const cp = Math.cos(s.pitch), sp = Math.sin(s.pitch)
          const y1 = dy * cp, z1 = -dy * sp
          return { dx: dx * cy + z1 * sy, dy: y1, dz: -dx * sy + z1 * cy }
        }

        function tick() {
          s.af = requestAnimationFrame(tick)
          if (document.hidden || !s.w) return
          const pal = palRef.current
          s.pal = pal

          // 自转(拖视角时暂停,松手渐复)
          if (!s.dragView && !s.dragNode) s.spin += (GALAXY.SPIN - s.spin) * 0.02
          else s.spin = 0
          s.yaw += s.spin

          // 3D 轻力:斥力 + 弹簧 + 向盘心,聚出星团感
          const a = s.alpha
          if (a >= 0.015) {
            const ns = s.nodes
            for (let i = 0; i < ns.length; i++) for (let j = i + 1; j < ns.length; j++) {
              const dx = ns[j].x - ns[i].x, dy = ns[j].y - ns[i].y, dz = ns[j].z - ns[i].z
              const d2 = dx * dx + dy * dy + dz * dz || 1
              const d = Math.sqrt(d2)
              const f = (150 / d2) * a
              const fx = (dx / d) * f, fy = (dy / d) * f, fz = (dz / d) * f
              ns[i].vx -= fx; ns[i].vy -= fy; ns[i].vz -= fz
              ns[j].vx += fx; ns[j].vy += fy; ns[j].vz += fz
            }
            s.edges.forEach((e) => {
              const a2 = s.nm.get(e.source), b = s.nm.get(e.target)
              if (!a2 || !b) return
              const dx = b.x - a2.x, dy = b.y - a2.y, dz = b.z - a2.z
              const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1
              const f = (d - 70) * 0.005 * a
              a2.vx += (dx / d) * f; a2.vy += (dy / d) * f; a2.vz += (dz / d) * f
              b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; b.vz -= (dz / d) * f
            })
            ns.forEach((n) => {
              n.vx -= n.x * 0.0012 * a; n.vy -= n.y * 0.0012 * a; n.vz -= n.z * 0.0012 * a
              if (n !== s.dragNode) { n.x += n.vx; n.y += n.vy; n.z += n.vz }
              const rad = Math.sqrt(n.x * n.x + n.z * n.z)
              if (rad > GALAXY.R * 1.5) { n.x *= GALAXY.R * 1.5 / rad; n.z *= GALAXY.R * 1.5 / rad }
              n.y = Math.max(-140, Math.min(140, n.y))
              n.vx *= 0.85; n.vy *= 0.85; n.vz *= 0.85
            })
            s.alpha = a * 0.96
          }

          // ── 绘制 ──
          ctx2.setTransform(1, 0, 0, 1, 0, 0)
          ctx2.clearRect(0, 0, c.width, c.height)
          ctx2.setTransform(s.dpr, 0, 0, s.dpr, 0, 0)

          // 星尘(视差背景)
          for (const d0 of s.dust) {
            const p = project(d0.x, d0.y, d0.z)
            if (p.persp <= 0) continue
            ctx2.globalAlpha = d0.o * Math.max(0.2, Math.min(1, 1 - p.depth / (GALAXY.R * 2.2)))
            ctx2.fillStyle = pal.label
            ctx2.beginPath()
            ctx2.arc(p.sx, p.sy, d0.s * p.persp * s.zoom, 0, Math.PI * 2)
            ctx2.fill()
          }
          ctx2.globalAlpha = 1

          // 投影全部节点,按深度从远到近
          const proj = s.nodes.map((n) => ({ n, p: project(n.x, n.y, n.z) }))
          s.proj = proj
          proj.sort((A, B) => B.p.depth - A.p.depth)

          const hover = s.hover
          const neighbors = hover ? new Set(s.adj.get(hover.id)?.map((x) => x.other)) : null
          const isNb = (id) => neighbors && neighbors.has(id)
          const ms = matchRef.current
          const dimmed = (id) => ms && !ms.has(id)
          const depthFade = (d) => Math.max(0.18, Math.min(1, 1 - d / (GALAXY.R * 2.4)))

          if (pal.isDark) ctx2.globalCompositeOperation = 'lighter'

          // 边(id→投影索引,避免逐边线性查找)
          const pmap = new Map(proj.map((P) => [P.n.id, P]))
          s.edges.forEach((e) => {
            const ea = pmap.get(e.source)
            const eb = pmap.get(e.target)
            if (!ea || !eb) return
            const active = hover && (e.source === hover.id || e.target === hover.id)
            const fade = Math.min(depthFade(ea.p.depth), depthFade(eb.p.depth))
            const dim = dimmed(e.source) || dimmed(e.target)
            ctx2.beginPath()
            ctx2.moveTo(ea.p.sx, ea.p.sy)
            ctx2.lineTo(eb.p.sx, eb.p.sy)
            ctx2.strokeStyle = active ? pal.accent : pal.edge
            ctx2.globalAlpha = active ? Math.min(1, fade + 0.35) : fade * 0.55 * (dim ? 0.15 : 1)
            ctx2.lineWidth = active ? 1.6 : 1
            ctx2.stroke()
          })

          // 星点(发光)
          for (const { n, p } of proj) {
            if (p.persp <= 0) continue
            const color = typeColor(n.type)
            const fade = depthFade(p.depth)
            const dim = dimmed(n.id) ? 0.12 : 1
            const rr = Math.max(1.2, n.r * p.persp * s.zoom)
            const active = hover && (hover.id === n.id || isNb(n.id))
            const glow = rr * (pal.isDark ? 3 : 2.2)
            const g = ctx2.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, glow)
            g.addColorStop(0, color)
            g.addColorStop(0.35, withAlpha(color, pal.isDark ? '66' : '55'))
            g.addColorStop(1, withAlpha(color, '00'))
            ctx2.globalAlpha = (active ? 1 : 0.85) * fade * dim
            ctx2.fillStyle = g
            ctx2.beginPath()
            ctx2.arc(p.sx, p.sy, glow, 0, Math.PI * 2)
            ctx2.fill()
            ctx2.globalAlpha = fade * dim
            ctx2.fillStyle = pal.isDark ? '#ffffff' : color
            ctx2.beginPath()
            ctx2.arc(p.sx, p.sy, Math.max(1, rr * 0.45), 0, Math.PI * 2)
            ctx2.fill()
            if (hover && hover.id === n.id) {
              ctx2.globalAlpha = 1
              ctx2.strokeStyle = pal.accent
              ctx2.lineWidth = 1.6
              ctx2.beginPath()
              ctx2.arc(p.sx, p.sy, rr + 4, 0, Math.PI * 2)
              ctx2.stroke()
            }
          }
          ctx2.globalCompositeOperation = 'source-over'
          ctx2.globalAlpha = 1

          // 标签(hover 邻接或少量节点)
          const showLabels = s.nodes.length <= 46 || hover
          if (showLabels) {
            ctx2.font = '10px system-ui'
            ctx2.textAlign = 'center'
            for (const { n, p } of proj) {
              const active = hover && (hover.id === n.id || isNb(n.id))
              if (dimmed(n.id) && !active) continue
              if (!active && !showLabels) continue
              if (!active && p.depth > GALAXY.R * 1.4) continue
              ctx2.globalAlpha = active ? 0.95 : depthFade(p.depth) * 0.8
              ctx2.fillStyle = pal.label
              const name = String(n.name || n.id)
              ctx2.fillText(name.length > 10 ? name.slice(0, 10) + '…' : name, p.sx, p.sy + Math.max(6, n.r * p.persp * s.zoom) + 11)
            }
            ctx2.globalAlpha = 1
          }
        }
        if (!s.af) s.af = requestAnimationFrame(tick)

        const hit = (mx, my) => {
          let best = null, bestD = 1e9
          for (const { n, p } of s.proj) {
            const d2 = (mx - p.sx) ** 2 + (my - p.sy) ** 2
            const hitR = (n.r * p.persp * s.zoom + 5) ** 2
            if (d2 <= hitR && d2 < bestD) { best = n; bestD = d2 }
          }
          return best
        }

        const dn = (e) => {
          const n = hit(e.offsetX, e.offsetY)
          if (n) { s.dragNode = n; s._lx = e.offsetX; s._ly = e.offsetY }
          else { s.dragView = true; s._lx = e.offsetX; s._ly = e.offsetY }
        }
        const up = () => { s.dragView = false; s.dragNode = null }
        const mv = (e) => {
          const dx = e.offsetX - s._lx, dy = e.offsetY - s._ly
          if (s.dragNode) {
            const wv = unprojectDelta(dx / s.zoom, dy / s.zoom)
            s.dragNode.x += wv.dx; s.dragNode.y += wv.dy; s.dragNode.z += wv.dz
            s.dragNode.vx = s.dragNode.vy = s.dragNode.vz = 0
            s._lx = e.offsetX; s._ly = e.offsetY
            const p = project(s.dragNode.x, s.dragNode.y, s.dragNode.z)
            setTooltip((tp) => (tp ? { ...tp, x: p.sx, y: p.sy } : tp))
          } else if (s.dragView) {
            s.yaw += dx * 0.005
            s.pitch = Math.max(-1.35, Math.min(1.35, s.pitch + dy * 0.004))
            s._lx = e.offsetX; s._ly = e.offsetY
          } else {
            const n = hit(e.offsetX, e.offsetY)
            if ((n && n.id) !== s.lastHoverId) {
              s.lastHoverId = n ? n.id : null
              s.hover = n
              c.style.cursor = n ? 'pointer' : 'grab'
              setTooltip(n ? { x: e.offsetX, y: e.offsetY, node: n } : null)
            } else if (n) {
              setTooltip((tp) => (tp ? { ...tp, x: e.offsetX, y: e.offsetY } : tp))
            }
          }
        }
        const wh = (e) => {
          e.preventDefault()
          s.zoom = Math.min(2.6, Math.max(0.35, s.zoom * (e.deltaY > 0 ? 0.9 : 1.1)))
          setZoomLabel(Math.round(s.zoom * 100))
        }
        const reset = () => {
          s.yaw = 0.5; s.pitch = -0.42; s.zoom = 1; s.alpha = 1
          setZoomLabel(100)
        }
        st.current._reset = reset

        c.addEventListener('mousedown', dn)
        c.addEventListener('mouseup', up)
        c.addEventListener('mouseleave', up)
        c.addEventListener('mousemove', mv)
        c.addEventListener('wheel', wh, { passive: false })
        c.addEventListener('dblclick', reset)
        c.style.cursor = 'grab'
        return () => {
          ro.disconnect()
          if (s.af) cancelAnimationFrame(s.af); s.af = 0
          c.removeEventListener('mousedown', dn)
          c.removeEventListener('mouseup', up)
          c.removeEventListener('mouseleave', up)
          c.removeEventListener('mousemove', mv)
          c.removeEventListener('wheel', wh)
          c.removeEventListener('dblclick', reset)
        }
      }, [])

      const tp = tooltip
      const connCount = tp ? (st.current.adj.get(tp.node.id)?.length || 0) : 0
      return h('div', { ref: wrapRef, style: { position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: palRef.current && palRef.current.isDark ? 'transparent' : 'transparent' } },
        h('canvas', { ref: canvasRef, style: { width: '100%', height: '100%', display: 'block' } }),
        tp && h('div', { style: { position: 'absolute', left: Math.max(6, Math.min(tp.x + 14, (st.current.w || 300) - 244)), top: Math.max(6, Math.min(tp.y + 14, (st.current.h || 200) - 130)), width: 230, background: css.bg1, border: `1px solid ${css.border}`, borderRadius: 10, boxShadow: css.shadow, padding: '10px 12px', pointerEvents: 'none', animation: 'panguFade .15s ease', zIndex: 5 } },
          h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 } },
            h('span', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, tp.node.name || tp.node.id),
            h(TypeChip, { type: tp.node.type }),
          ),
          tp.node.description && h('div', { style: { fontSize: 11, color: css.t2, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', marginBottom: 5 } }, tp.node.description),
          h('div', { style: { fontSize: 10.5, color: css.t3 } },
            [tp.node.memory_count ? '关联记忆 ' + tp.node.memory_count + ' 条' : null, '连接 ' + connCount + ' 条'].filter(Boolean).join(' · '),
          ),
        ),
        h('div', { style: { position: 'absolute', right: 12, bottom: 10, display: 'flex', alignItems: 'center', gap: 6, zIndex: 4 } },
          h('span', { style: { fontSize: 10.5, color: css.t3, fontVariantNumeric: 'tabular-nums', background: css.bg1, border: `1px solid ${css.borderSoft}`, borderRadius: 6, padding: '3px 7px' } }, zoomLabel + '%'),
          h('button', { className: 'pangu-btn', onClick: () => st.current._reset && st.current._reset(), title: '重置视角(双击画布同效)', style: { fontSize: 10.5, color: css.t2, background: css.bg1, border: `1px solid ${css.borderSoft}`, borderRadius: 6, padding: '3px 8px', cursor: 'pointer' } }, '重置'),
        ),
        h('div', { style: { position: 'absolute', left: 12, bottom: 10, fontSize: 10, color: css.t3, background: css.bg1, border: `1px solid ${css.borderSoft}`, borderRadius: 6, padding: '3px 8px', zIndex: 4, display: 'inline-flex', alignItems: 'center', gap: 5 } },
          h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: ACCENT, boxShadow: `0 0 6px ${ACCENT}` } }),
          '拖拽旋转 · 滚轮缩放 · 双击重置',
        ),
      )
    }

    function GraphPane({ nodes, edges, matchSet, kgErr, loading, onRetry }) {
      const palette = useCanvasPalette()
      const types = [...new Set(nodes.map((n) => n.type || 'default'))].slice(0, 8)
      if (kgErr && !nodes.length) return h(ErrorState, { text: '图谱加载失败(' + kgErr + ')', onRetry })
      if (loading && !nodes.length) return h('div', { style: { padding: 16, height: '100%', boxSizing: 'border-box' } }, h(Skeleton, { w: '100%', h: '92%', r: 12 }))
      if (!nodes.length) return h(ErrorState, { text: '暂无图谱数据' })
      return h('div', { style: { position: 'relative', flex: 1, minHeight: 320, animation: 'panguFade .25s ease' } },
        h(GalaxyCanvas, { nodes, edges, matchSet, palette }),
        h('div', { style: { position: 'absolute', left: 12, top: 10, display: 'flex', flexWrap: 'wrap', gap: '4px 12px', maxWidth: '65%', background: css.bg1, border: `1px solid ${css.borderSoft}`, borderRadius: 8, padding: '6px 10px', zIndex: 4 } },
          types.map((tp) => h('span', { key: tp, style: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: css.t3 } },
            h('span', { style: { width: 7, height: 7, borderRadius: '50%', background: typeColor(tp), boxShadow: `0 0 5px ${withAlpha(typeColor(tp), '88')}` } }),
            typeLabel(tp),
          )),
        ),
      )
    }


    function CrystalPane({ nodes, edges, kgErr, loading, onRetry }) {
      const types = React.useMemo(() => {
        const c = {}
        for (const n of nodes) { const t = n.type || 'default'; c[t] = (c[t] || 0) + 1 }
        return Object.entries(c).sort((a, b) => b[1] - a[1])
      }, [nodes])
      const predicates = React.useMemo(() => {
        const c = {}
        for (const e of edges) { const p = e.relation || e.predicate || e.type || '关联'; c[p] = (c[p] || 0) + 1 }
        return Object.entries(c).sort((a, b) => b[1] - a[1])
      }, [edges])
      if (kgErr && !nodes.length) return h(ErrorState, { text: '图谱加载失败(' + kgErr + ')', onRetry })
      if (loading && !nodes.length) return h('div', { style: { padding: 16 } }, h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 } }, [0, 1, 2, 3, 4, 5].map((i) => h(Skeleton, { key: i, w: '100%', h: 92, r: 10 }))))
      return h('div', { style: { overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '14px 16px 20px', animation: 'panguFade .25s ease' } },
        h(SecHead, { num: '01', title: '知识结晶', hint: nodes.length + ' 实体 / ' + edges.length + ' 关系 · 以实体为中心' }),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10, marginTop: 9 } },
          nodes.map((n) => {
            const color = typeColor(n.type)
            const rels = edges.filter((e) => (e.subject_id || e.source) === n.id || (e.object_id || e.target) === n.id).slice(0, 3)
            return h('div', { key: n.id, className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: 12, position: 'relative', overflow: 'hidden' } },
              h('div', { style: { position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${color}, ${withAlpha(color, '44')})` } }),
              h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 } },
                h('span', { style: { width: 22, height: 22, borderRadius: 7, background: withAlpha(color, '1c'), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 } },
                  h(Icon, { name: 'box', size: 11, color }),
                ),
                h('div', { style: { flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: css.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, n.name || n.id),
                h(TypeChip, { type: n.type }),
              ),
              n.description && h('div', { style: { fontSize: 11, color: css.t2, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } }, n.description),
              rels.length > 0 && h('div', { style: { fontSize: 10, color: css.t3, marginTop: 6, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', lineHeight: 1.7 } },
                rels.map((e, i) => {
                  const subj = nodes.find((x) => x.id === (e.subject_id || e.source))
                  const obj = nodes.find((x) => x.id === (e.object_id || e.target))
                  const pred = e.relation || e.predicate || e.type || '关联'
                  return h('div', { key: i }, h('i', { style: { fontStyle: 'normal', color: ACCENT } }, pred), ' · ', (subj?.name || '?'), ' → ', (obj?.name || '?'))
                }),
              ),
            )
          }),
        ),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10, marginTop: 12 } },
          h('div', { style: { border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '11px 13px', background: css.bg1 } },
            h('div', { style: { fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 } }, h(Icon, { name: 'network', size: 12, color: css.info }), '关系类型分布'),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', lineHeight: 1.8 } },
              predicates.length ? predicates.map(([p, n]) => p + ' ×' + n).join(' · ') : '—'),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, lineHeight: 1.55 } }, '关系由记忆自动抽取（Wikilink + 谓词识别），每条带来源记忆指针与置信度。'),
          ),
          h('div', { style: { border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '11px 13px', background: css.bg1 } },
            h('div', { style: { fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 } }, h(Icon, { name: 'grid', size: 12, color: ACCENT }), '实体类型构成'),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', lineHeight: 1.8 } },
              types.length ? types.map(([t, n]) => typeLabel(t) + ' ' + n).join(' · ') : '—'),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, lineHeight: 1.55 } }, '类型色在星系视图、结晶卡两处同色，跨视图可追踪。'),
          ),
        ),
      )
    }

    /* ── 知识库页 KnowledgePane：知识浏览 / 搜索 / 分类 ── */
    function KnowledgePane() {
      const [entries, setEntries] = React.useState([])
      const [stats, setStats] = React.useState(null)
      const [category, setCategory] = React.useState('')
      const [query, setQuery] = React.useState('')
      const [loading, setLoading] = React.useState(true)
      const [selected, setSelected] = React.useState(null)

      const load = React.useCallback(async () => {
        setLoading(true)
        try {
          const [kl, ks] = await Promise.allSettled([
            // 2026-09-20 修复：list 声明了 1 个参数，无分类也要传 {} —— 原来传
            // undefined 会被 callRemote 展开成零参调用，网关按声明参数个数严格校验
            // 直接拒绝（错误被 allSettled 吞掉 → 知识列表永远为空）。
            callRemote('panguKnowledge', 'list', { category }).then(unwrap),
            callRemote('panguKnowledge', 'stats').then(unwrap),
          ])
          if (kl.status === 'fulfilled') setEntries(kl.value?.knowledge || [])
          if (ks.status === 'fulfilled') setStats(ks.value)
        } catch (_) {}
        setLoading(false)
      }, [category])
      // 2026-09-20 修复：依赖必须是 [load]（随 category 变化重建）—— 原来是 []，
      // 点分类按钮只改了 state 从不重新拉取，切换分类永远不出现对应列表。
      React.useEffect(() => { load() }, [load])

      const doSearch = async () => {
        if (!query.trim()) { load(); return }
        setLoading(true)
        try {
          const r = unwrap(await callRemote('panguKnowledge', 'search', { query: query.trim() }))
          setEntries(r?.knowledge || [])
        } catch (_) {}
        setLoading(false)
      }

      const CAT_LABELS = { best_practice: '最佳实践', solution: '解决方案', guide: '使用指南', insight: '洞察发现', other: '其他' }
      const CAT_COLORS = { best_practice: css.ok, solution: css.info, guide: ACCENT, insight: css.warn, other: css.t3 }
      const categories = stats?.categories || {}
      const catEntries = Object.entries(categories).sort((a, b) => b[1] - a[1])

      return h('div', { style: { overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '14px 16px 20px', animation: 'panguFade .25s ease' } },
        // 2026-09-20：去掉 maxWidth 900 —— 与结晶页一致自适应宽度（此前知识页
        // 居中缩窄、两侧留白，结晶页却是全宽，两个标签视觉不一致）
        h('div', null,
          // 搜索栏
          h('div', { style: { display: 'flex', gap: 8, marginBottom: 14 } },
            h('input', {
              className: 'pangu-input', value: query,
              onChange: (e) => setQuery(e.target.value),
              onKeyDown: (e) => { if (e.key === 'Enter') doSearch() },
              placeholder: '搜索知识库…',
              style: { flex: 1, padding: '7px 12px', borderRadius: 8, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12.5, outline: 'none' },
            }),
            h('button', { onClick: doSearch, style: { padding: '7px 16px', borderRadius: 8, border: 'none', background: ACCENT, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5 } },
              h(Icon, { name: 'search', size: 13, color: '#fff' }), '搜索'),
          ),
          // 分类筛选
          h('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 } },
            h('button', {
              onClick: () => { setCategory(''); setSelected(null) },
              style: { padding: '4px 12px', borderRadius: 999, border: `1px solid ${!category ? ACCENT : css.borderSoft}`, background: !category ? withAlpha(ACCENT, '0d') : 'transparent', color: !category ? ACCENT : css.t2, fontSize: 11, cursor: 'pointer', fontWeight: !category ? 600 : 400 },
            }, '全部 (' + (stats?.total || 0) + ')'),
            catEntries.map(([cat, count]) => h('button', {
              key: cat, onClick: () => { setCategory(category === cat ? '' : cat); setSelected(null) },
              style: { padding: '4px 12px', borderRadius: 999, border: `1px solid ${category === cat ? (CAT_COLORS[cat] || ACCENT) : css.borderSoft}`, background: category === cat ? withAlpha(CAT_COLORS[cat] || ACCENT, '0d') : 'transparent', color: category === cat ? (CAT_COLORS[cat] || ACCENT) : css.t2, fontSize: 11, cursor: 'pointer', fontWeight: category === cat ? 600 : 400 },
            }, (CAT_LABELS[cat] || cat) + ' (' + count + ')')),
          ),
          // 知识列表
          loading
            ? h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 } }, [0, 1, 2, 3].map((i) => h(Skeleton, { key: i, w: '100%', h: 100, r: 10 })))
            : entries.length > 0
              ? h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 } },
                  entries.map((e) => {
                    const catColor = CAT_COLORS[e.category] || css.t3
                    return h('div', {
                      key: e.id, className: 'pangu-card',
                      onClick: () => setSelected(selected === e.id ? null : e.id),
                      style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: 12, cursor: 'pointer', position: 'relative', overflow: 'hidden' },
                    },
                      h('div', { style: { position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${catColor}, ${withAlpha(catColor, '44')})` } }),
                      h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 } },
                        h('span', { style: { fontSize: 11, padding: '1px 7px', borderRadius: 999, background: withAlpha(catColor, '15'), color: catColor, fontWeight: 600 } }, CAT_LABELS[e.category] || e.category),
                        h('span', { style: { marginLeft: 'auto', fontSize: 10, color: css.t3 } }, '置信 ' + Number(e.confidence || 0).toFixed(0) + '%'),
                      ),
                      h('div', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1, marginBottom: 4, lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: selected === e.id ? 'unset' : 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } }, e.title),
                      h('div', { style: { fontSize: 11, color: css.t2, lineHeight: 1.55, display: '-webkit-box', WebkitLineClamp: selected === e.id ? 'unset' : 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' } }, e.content),
                      h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 } },
                        (e.tags || []).slice(0, 3).map((t) => h('span', { key: t, style: { fontSize: 9.5, padding: '1px 6px', borderRadius: 4, border: `1px solid ${css.borderSoft}`, color: css.t3 } }, t)),
                      ),
                      h('div', { style: { fontSize: 9.5, color: css.t3, marginTop: 5, display: 'flex', justifyContent: 'space-between' } },
                        h('span', null, '来源 ' + (e.source_memories || []).length + ' 条记忆'),
                        h('span', null, '使用 ' + (e.usage_count || 0) + ' 次'),
                      ),
                    )
                  }),
                )
              : h('div', { style: { padding: '30px 0', textAlign: 'center', color: css.t3, fontSize: 12 } },
                  h(Icon, { name: 'grid', size: 28, color: css.t3, style: { opacity: 0.4, marginBottom: 8 } }),
                  h('div', null, '知识库暂无内容'),
                  h('div', { style: { fontSize: 11, marginTop: 4 } }, '盘古会从记忆中自动提取知识'),
                ),
        ),
      )
    }

    /* ── 管理页 AdminPane：备份 / 深度体检 / 平台管理 / 快照 ── */
    function AdminPane({ initialSection, config }) {
      const [deep, setDeep] = React.useState(null)
      const [bk, setBk] = React.useState({ s: 'idle', msg: '' })
      const [platforms, setPlatforms] = React.useState([])
      const [pending, setPending] = React.useState([])
      const [snapshots, setSnapshots] = React.useState([])
      const [loading, setLoading] = React.useState(true)
      const [adminErr, setAdminErr] = React.useState('')
      const [activeSection, setActiveSection] = React.useState(initialSection || 'health') // health | platforms | snapshots

      // 当 initialSection 变化时更新
      React.useEffect(() => {
        if (initialSection) setActiveSection(initialSection)
      }, [initialSection])

      const load = React.useCallback(async () => {
        setLoading(true)
        try {
          const [dh, pl, pend, sn] = await Promise.allSettled([
            callRemote('panguDashboard', 'deepHealth').then(unwrap),
            callRemote('panguPlatforms', 'listPlatforms').then(unwrap),
            callRemote('panguPlatforms', 'listPending').then(unwrap),
            callRemote('panguDashboard', 'stats').then(unwrap),
          ])
          if (dh.status === 'fulfilled') setDeep(dh.value)
          if (pl.status === 'fulfilled' && pl.value) setPlatforms(pl.value.platforms || [])
          if (pend.status === 'fulfilled' && pend.value) setPending(pend.value.platforms || [])
          if (sn.status === 'fulfilled' && sn.value) setSnapshots(sn.value?.snapshots || [])
          // 管理类接口（平台/钥匙）走 X-Admin-Key：未配置或填错「管理密钥」时
          // 它们会整体失败。此前失败被 allSettled 静默吞掉，界面只是"空"，
          // 用户完全看不出要填管理密钥（2026-09-21 修）。
          const failed = [pl, pend].find((r) => r.status === 'rejected')
          setAdminErr(failed ? String(failed.reason?.message || failed.reason || '管理接口调用失败') : '')
        } catch (e) {
          setAdminErr(String(e?.message || e || '管理接口调用失败'))
        }
        setLoading(false)
      }, [])
      React.useEffect(() => { load() }, [])

      const doBackup = async () => {
        setBk({ s: 'saving', msg: '' })
        try {
          const v = unwrap(await callRemote('panguDashboard', 'backup'))
          if (!v?.ok) throw new Error(v?.error || '备份失败')
          setBk({ s: 'done', msg: fmtNum(v.memories) + '条 · ' + fmtSize(v.size) })
          setTimeout(() => setBk({ s: 'idle', msg: '' }), 4000)
        } catch (e) { setBk({ s: 'error', msg: String(e.message || e) }) }
      }

      // 平台管理操作
      const doApprove = async (tokenId) => {
        if (!window.confirm('审核通过该平台接入？')) return
        try { await callRemote('panguPlatforms', 'approve', { token_id: tokenId }); load() } catch (_) {}
      }
      const doReject = async (tokenId) => {
        if (!window.confirm('拒绝该平台接入？')) return
        try { await callRemote('panguPlatforms', 'reject', { token_id: tokenId }); load() } catch (_) {}
      }
      const doRevokePlatform = async (tokenId) => {
        if (!window.confirm('撤销该平台接入？')) return
        try { await callRemote('panguPlatforms', 'revoke', { token_id: tokenId }); load() } catch (_) {}
      }

      const checkRow = (name, label) => {
        const c = deep?.checks?.find((x) => x.name === name)
        return h(InfoRow, { key: name, label, value: c ? h(StatusPill, { status: c.status }) : deep ? '—' : '…' })
      }

      const sectionBtn = (key, icon, text) => h('button', {
        onClick: () => setActiveSection(key),
        style: { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 11px', borderRadius: 6, border: activeSection === key ? `1px solid ${ACCENT}` : `1px solid ${css.borderSoft}`, background: activeSection === key ? withAlpha(ACCENT, '0d') : 'transparent', color: activeSection === key ? ACCENT : css.t2, fontSize: 11, fontWeight: activeSection === key ? 600 : 400, cursor: 'pointer', transition: 'all .15s' },
      }, h(Icon, { name: icon, size: 12 }), text)

      return h('div', { style: { overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '14px 16px 20px', animation: 'panguFade .25s ease' } },
        // 分区导航
        h('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 } },
          sectionBtn('health', 'pulse', '体检'),
          sectionBtn('platforms', 'box', '平台 (' + (platforms.length + pending.length) + ')'),
          sectionBtn('snapshots', 'clock', '快照'),
        ),

        // 管理接口不可用时的显式提示（否则平台/钥匙区只会是一片空白）
        adminErr && h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: 8, border: `1px solid ${css.warn}`, borderRadius: 8, padding: '9px 12px', marginBottom: 12, background: withAlpha(css.warn, '0d') } },
          h(Icon, { name: 'alert', size: 13, color: css.warn, style: { marginTop: 2 } }),
          h('div', { style: { flex: 1, minWidth: 0, fontSize: 11.5, color: css.t2, lineHeight: 1.6 } },
            '管理接口不可用：', adminErr),
          h('button', { onClick: load, style: { flexShrink: 0, padding: '4px 10px', borderRadius: 6, border: `1px solid ${css.border}`, background: css.bg2, color: css.t2, fontSize: 11, cursor: 'pointer' } }, '重试'),
        ),

        // ── 健康检查 ──
        activeSection === 'health' && h(React.Fragment, null,
          h(SecHead, { num: '01', title: '深度体检', hint: deep ? ('状态 ' + (deep.status || '?')) : '…' }),
          h('div', { style: { border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '10px 14px', marginTop: 9, background: css.bg1 } },
            checkRow('structure', '结构检查'),
            checkRow('memory', '记忆检查'),
            checkRow('embedding', '嵌入检查'),
          ),
          h(SecHead, { num: '02', title: '备份快照', hint: '全量记忆 + 宫殿结构 + FTS 索引' }),
          h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, marginTop: 9, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '11px 14px', background: css.bg1 } },
            h('div', { style: { flex: 1, fontSize: 11, color: css.t2, lineHeight: 1.55 } },
              bk.s === 'done' ? h('span', { style: { color: css.ok } }, '✓ ' + bk.msg) : bk.s === 'error' ? h('span', { style: { color: css.err } }, bk.msg) : '创建当前记忆库的手动快照。'),
            h('button', { className: 'pangu-btn', onClick: doBackup, disabled: bk.s === 'saving', style: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, padding: '6px 14px', borderRadius: 7, border: 'none', background: ACCENT, color: '#fff', fontWeight: 600, cursor: bk.s === 'saving' ? 'default' : 'pointer', flexShrink: 0 } },
              h(Icon, { name: bk.s === 'done' ? 'check' : 'database', size: 12, color: '#fff' }),
              bk.s === 'saving' ? '备份中…' : '立即备份'),
          ),
        ),

        // ── 平台管理 ──
        activeSection === 'platforms' && h(React.Fragment, null,
          // 接入指南卡片（2026-09-20 重写：四步 MCP 教程 → 一段可复制的任务描述。
          // 使用流程 = 用户把这段话发给目标平台的 Agent，Agent 自行申请，用户只管点「通过」）
          h('div', { style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '12px 14px', marginBottom: 14 } },
            h('div', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 } },
              h(Icon, { name: 'info', size: 13, color: css.info }), '平台接入 · 一段话搞定'),
            h('div', { style: { fontSize: 11, color: css.t2, lineHeight: 1.7, marginBottom: 8 } },
              '把下面这段话原样发给目标平台的 Agent，等它执行完，你在这里点「通过」就接通了：'),
            h('pre', {
              style: { background: css.bg3, borderRadius: 6, padding: '10px 12px', fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10.5, lineHeight: 1.65, margin: '0 0 8px 0', overflowX: 'auto', whiteSpace: 'pre-wrap', userSelect: 'all', color: css.t2 },
            },
              `请接入盘古记忆系统：\n1) 执行 curl -X POST ${config?.pangu_base_url || 'http://127.0.0.1:19529'}/api/v2/platforms/request -H "Content-Type: application/json" -d '{"platform":"<你的平台ID>","platform_name":"<显示名>"}'\n2) 保存返回的 token（pgp_ 开头，只显示一次），等管理员在后台审核通过\n3) 通过后用它调 REST API：写记忆 POST ${config?.pangu_base_url || 'http://127.0.0.1:19529'}/api/v2/memories（头 Authorization: Bearer <token>，body 的 text 必填，wing/room/importance/tags 可选）；搜索 GET ${config?.pangu_base_url || 'http://127.0.0.1:19529'}/api/v2/memories/search?q=<关键词>`),
            h('div', { style: { fontSize: 10.5, color: css.t3 } },
              '审核前平台没有任何权限（pending 连鉴权都不通过）；点「通过」后即为全权（读/写/改/删/搜）。token 丢失就撤销后重新申请。'),
          ),

          h(SecHead, { num: '01', title: '已接入平台', hint: platforms.length + ' 个' }),
          loading
            ? h(Skeleton, { w: '100%', h: 60, r: 8, style: { marginTop: 9 } })
            : h('div', { style: { marginTop: 9 } },
                platforms.length > 0
                  ? h('table', { style: { width: '100%', fontSize: 11.5, borderCollapse: 'collapse' } },
                      h('thead', null, h('tr', null,
                        ['平台', '名称', '权限', '状态', '最后使用', ''].map((th, i) => h('th', { key: i, style: { textAlign: 'left', padding: '4px 6px', borderBottom: `1px solid ${css.borderSoft}`, color: css.t3, fontWeight: 500, fontSize: 10.5 } }, th)))),
                      h('tbody', null, platforms.map((p) => h('tr', { key: p.token_id },
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}`, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10.5 } }, p.platform),
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}` } }, p.platform_name || '—'),
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}`, fontSize: 10 } }, (p.permissions || []).join(', ')),
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}` } },
                          h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10.5, color: p.status === 'active' ? css.ok : p.status === 'revoked' ? css.err : css.t3 } },
                            h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: p.status === 'active' ? css.ok : p.status === 'revoked' ? css.err : css.t3 } }),
                            p.status === 'active' ? '活跃' : p.status === 'revoked' ? '已撤销' : p.status)),
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}`, fontSize: 10.5, color: css.t3 } }, p.last_used_at ? fmtAgo(Date.parse(p.last_used_at)) : '未使用'),
                        h('td', { style: { padding: '5px 6px', borderBottom: `1px solid ${css.borderSoft}`, textAlign: 'right' } },
                          p.status === 'active' && h('button', { onClick: () => doRevokePlatform(p.token_id), style: { fontSize: 11, color: css.err, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' } }, '撤销')),
                      ))),
                    )
                  : h('div', { style: { padding: '10px 0', fontSize: 11, color: css.t3 } }, '暂无已接入平台'),
              ),
          pending.length > 0 && h(React.Fragment, null,
            h(SecHead, { num: '02', title: '待审核平台', hint: pending.length + ' 个', style: { marginTop: 16 } }),
            h('div', { style: { marginTop: 9 } },
              pending.map((p) => h('div', { key: p.token_id, style: { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', border: `1px solid ${css.borderSoft}`, borderRadius: 8, marginBottom: 6, background: css.bg1 } },
                h('div', { style: { flex: 1, minWidth: 0 } },
                  h('div', { style: { fontSize: 12, fontWeight: 600, color: css.t1 } }, p.platform_name || p.platform),
                  h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 2 } },
                    h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' } }, p.platform),
                    ' · ', (p.permissions || []).join(', '),
                    p.request_ip && h('span', null, ' · IP: ' + p.request_ip))),
                h('div', { style: { display: 'flex', gap: 6, flexShrink: 0 } },
                  h('button', { onClick: () => doApprove(p.token_id), style: { padding: '4px 12px', borderRadius: 6, border: 'none', background: css.ok, color: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer' } }, '通过'),
                  h('button', { onClick: () => doReject(p.token_id), style: { padding: '4px 12px', borderRadius: 6, border: `1px solid ${css.err}`, background: 'transparent', color: css.err, fontSize: 11, cursor: 'pointer' } }, '拒绝'),
                ),
              )),
            ),
          ),
        ),

        // ── 快照管理 ──
        activeSection === 'snapshots' && h(React.Fragment, null,
          h(SecHead, { num: '01', title: '记忆快照', hint: snapshots.length + ' 个' }),
          loading
            ? h(Skeleton, { w: '100%', h: 60, r: 8, style: { marginTop: 9 } })
            : h('div', { style: { marginTop: 9 } },
                snapshots.length > 0
                  ? snapshots.slice(0, 20).map((s) => h('div', { key: s.id, style: { display: 'flex', gap: 10, padding: '8px 2px', borderBottom: `1px solid ${css.borderSoft}`, alignItems: 'flex-start' } },
                      h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, color: css.t3, width: 60, flexShrink: 0 } }, (s.created_at || '').slice(5, 10)),
                      h('div', { style: { flex: 1, minWidth: 0 } },
                        h('div', { style: { fontSize: 11.5, color: css.t1, lineHeight: 1.5 } }, s.reason || '快照'),
                        h('div', { style: { fontSize: 10, color: css.t3, marginTop: 2 } },
                          '替换: ', h('code', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 9.5 } }, (s.replaced_by || '').slice(0, 8)), '…',
                          s.quality_score && h('span', null, ' · 质量 ' + Number(s.quality_score).toFixed(2))),
                      ),
                    ))
                  : h('div', { style: { padding: '10px 0', fontSize: 11, color: css.t3 } }, '暂无记忆快照（记忆进化时自动生成）'),
              ),
        ),
      )
    }

    /* ════════════════════════════════════════════
     * 3. 标签页容器 — 概览 / 星系 / 结晶 / 管理 (v5)
     * ════════════════════════════════════════════ */
    function PanguTab() {
      const [tab, setTab] = React.useState('overview')
      const [dash, setDash] = React.useState(null)
      const [kg, setKg] = React.useState(null)
      const [config, setConfig] = React.useState(null)
      // 2026-09-20：房间（palace room）概念已取消，不再把 listRooms 的房间合成进图谱
      // 节点 —— 此前星系/结晶视图里因此残留「房间」卡片。
      const [dashErr, setDashErr] = React.useState(null)
      const [kgErr, setKgErr] = React.useState(null)
      const [loading, setLoading] = React.useState(true)
      const [refreshing, setRefreshing] = React.useState(false)
      const [search, setSearch] = React.useState('')
      const [typeFilter, setTypeFilter] = React.useState('')
      const [adminSection, setAdminSection] = React.useState('health')

      const load = React.useCallback(async (silent) => {
        if (!silent) setLoading(true)
        setRefreshing(true)
        const [d, g, c] = await Promise.allSettled([
          callRemote('panguDashboard', 'data').then(unwrap),
          callRemote('panguKG', 'graph').then(unwrap),
          callRemote('panguConfig', 'get').then(unwrap),
        ])
        if (d.status === 'fulfilled') { setDash(d.value); setDashErr(null) } else setDashErr(String(d.reason?.message || d.reason))
        if (g.status === 'fulfilled') {
          if (g.value?.ok) { setKg(g.value); setKgErr(null) } else setKgErr(String(g.value?.error || '图谱数据为空'))
        } else setKgErr(String(g.reason?.message || g.reason))
        if (c.status === 'fulfilled') setConfig(c.value?.config || null)
        setLoading(false)
        setRefreshing(false)
      }, [])

      React.useEffect(() => {
        load()
        const id = setInterval(() => { if (!document.hidden) load(true) }, 60000)
        const offReset = ctx && ctx.on ? ctx.on('connection/reset', () => load(true)) : null
        const onGoto = (e) => {
          setTab(e.detail?.tab || 'overview')
          // 传递 section 参数给 AdminPane
          if (e.detail?.tab === 'admin' && e.detail?.section) {
            setAdminSection(e.detail.section)
          }
        }
        window.addEventListener('pangu:goto', onGoto)
        return () => { clearInterval(id); if (offReset) offReset(); window.removeEventListener('pangu:goto', onGoto) }
      }, [])

      const allNodes = React.useMemo(() => kg?.nodes || [], [kg])
      const graphEdges = React.useMemo(() => kg?.edges || [], [kg])
      const matched = React.useMemo(() => {
        if (!search && !typeFilter) return null
        const q = search.toLowerCase()
        const set = new Set()
        for (const n of allNodes) {
          const okS = !search || (n.name || '').toLowerCase().includes(q) || (n.type || '').toLowerCase().includes(q) || (n.description || '').toLowerCase().includes(q)
          const okT = !typeFilter || (n.type || 'default') === typeFilter
          if (okS && okT) set.add(n.id)
        }
        return set
      }, [allNodes, search, typeFilter])
      const graphNodes = React.useMemo(
        () => (matched ? allNodes.filter((n) => matched.has(n.id)) : allNodes),
        [allNodes, matched],
      )

      const tabBtn = (key, icon, text) => h('button', {
        className: 'pangu-tab', onClick: () => setTab(key),
        style: { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '7px 13px', border: 'none', borderBottom: tab === key ? '2px solid ' + ACCENT : '2px solid transparent', background: 'transparent', color: tab === key ? ACCENT : css.t2, fontSize: 12.5, fontWeight: tab === key ? 600 : 400, cursor: 'pointer', transition: 'color .15s' },
      }, h(Icon, { name: icon, size: 13 }), text)

      const inputStyle = { padding: '5px 10px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12, outline: 'none', boxSizing: 'border-box' }

      return h('div', { style: { height: '100%', display: 'flex', flexDirection: 'column', color: css.t1 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, padding: '0 12px', borderBottom: `1px solid ${css.borderSoft}`, flexShrink: 0 } },
          tabBtn('overview', 'overview', '概览'),
          tabBtn('graph', 'orbit', '星系'),
          tabBtn('crystal', 'grid', '结晶'),
          tabBtn('knowledge', 'layers', '知识'),
          tabBtn('admin', 'cpu', '管理'),
          h('div', { style: { flex: 1 } }),
          (tab === 'graph' || tab === 'crystal') && h('input', { className: 'pangu-input', value: search, onChange: (e) => setSearch(e.target.value), placeholder: '搜索实体…', style: { ...inputStyle, width: 150 } }),
          tab === 'graph' && h('select', { className: 'pangu-input', value: typeFilter, onChange: (e) => setTypeFilter(e.target.value), style: { ...inputStyle, padding: '4.5px 6px' } },
            h('option', { value: '' }, '全部类型'),
            [...new Set(allNodes.map((n) => n.type || 'default'))].map((tp) => h('option', { key: tp, value: tp }, typeLabel(tp))),
          ),
          (tab === 'graph' || tab === 'crystal') && h('span', { style: { fontSize: 11, color: css.t3, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' } }, graphNodes.length + ' 实体'),
          h('button', { className: 'pangu-btn', onClick: () => load(), title: '刷新', style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 7, border: 'none', background: 'transparent', color: css.t2, cursor: 'pointer', opacity: refreshing ? 0.5 : 1 } },
            h(Icon, { name: 'refresh', size: 13 }),
          ),
        ),
        tab === 'overview'
          ? h(OverviewPane, { dash, config, dashErr, loading, onRetry: () => load() })
          : tab === 'graph'
            ? h(GraphPane, { nodes: allNodes, edges: graphEdges, matchSet: matched, kgErr, loading, onRetry: () => load() })
            : tab === 'crystal'
              ? h(CrystalPane, { nodes: graphNodes, edges: graphEdges, kgErr, loading, onRetry: () => load() })
              : tab === 'knowledge'
                ? h(KnowledgePane, null)
                : h(AdminPane, { initialSection: adminSection, config }),
      )
    }
    function Toggle({ checked, onChange }) {
      return h('label', { style: { position: 'relative', display: 'inline-block', width: 38, height: 22, cursor: 'pointer', flexShrink: 0 } },
        h('input', { type: 'checkbox', checked, onChange, style: { opacity: 0, width: 0, height: 0 } }),
        h('span', { style: { position: 'absolute', inset: 0, borderRadius: 11, background: checked ? ACCENT : css.bg3, border: checked ? 'none' : `1px solid ${css.border}`, transition: 'background .2s', boxSizing: 'border-box' } },
          h('span', { style: { position: 'absolute', width: 16, height: 16, left: checked ? '19px' : '3px', bottom: '2.5px', background: '#fff', borderRadius: '50%', transition: 'left .2s cubic-bezier(.22,1,.36,1)', boxShadow: '0 1px 3px rgba(0,0,0,.2)' } }),
        ),
      )
    }

    function SettingRow({ label, desc, children }) {
      return h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, padding: '11px 0', borderBottom: `1px solid ${css.borderSoft}` } },
        h('div', { style: { flex: 1, minWidth: 0 } },
          h('div', { style: { fontSize: 13, fontWeight: 500, color: css.t1 } }, label),
          desc && h('div', { style: { fontSize: 11, color: css.t3, marginTop: 2 } }, desc),
        ),
        children,
      )
    }

    // 提供商预设：与 pangu/core/llm.py 的 PROVIDER_URLS 保持一致
    const LLM_PROVIDERS = [
      { id: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o' },
      { id: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
      { id: 'zhipu', label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus' },
      { id: 'qwen', label: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
      { id: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o' },
      { id: 'ollama', label: 'Ollama (本地)', url: 'http://localhost:11434/v1', model: 'llama3.1' },
    ]

    /** 受控文本输入框，风格与设置页一致 */
    function TextField({ label, desc, value, onChange, placeholder, password, disabled, mono }) {
      const [reveal, setReveal] = React.useState(false)
      return h('div', { style: { padding: '10px 0', borderBottom: `1px solid ${css.borderSoft}` } },
        h('div', { style: { fontSize: 13, fontWeight: 500, color: css.t1, marginBottom: 5 } }, label),
        desc && h('div', { style: { fontSize: 11, color: css.t3, marginBottom: 6, lineHeight: 1.5 } }, desc),
        h('div', { style: { display: 'flex', gap: 6, alignItems: 'center' } },
          h('input', {
            type: password && !reveal ? 'password' : 'text',
            value: value ?? '',
            placeholder: placeholder || '',
            disabled,
            spellCheck: false,
            autoComplete: 'off',
            onChange: (e) => onChange(e.target.value),
            style: {
              flex: 1, minWidth: 0, padding: '7px 10px', borderRadius: 7, fontSize: 12.5,
              border: `1px solid ${css.border}`, background: disabled ? css.bg3 : css.bg2,
              color: css.t1, outline: 'none', boxSizing: 'border-box',
              fontFamily: mono ? 'ui-monospace,SFMono-Regular,Menlo,monospace' : 'inherit',
            },
          }),
          password && h('button', {
            onClick: () => setReveal((v) => !v),
            title: reveal ? '隐藏' : '显示',
            type: 'button',
            style: { flexShrink: 0, padding: '6px 9px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t2, fontSize: 11, cursor: 'pointer' },
          }, reveal ? '隐藏' : '显示'),
        ),
      )
    }


    /* ════════════════════════════════════════════
     * 4. 设置页 — 真实读写 ~/.pangu/config.json (v5)
     * ════════════════════════════════════════════ */
    function ProvCard({ label, model, active, onPick }) {
      return h('button', {
        onClick: onPick, type: 'button',
        style: { border: active ? `1.5px solid ${ACCENT}` : `1px solid ${css.border}`, borderRadius: 8, background: active ? withAlpha(ACCENT, '0d') : css.bg2, padding: '7px 6px 6px', textAlign: 'center', cursor: 'pointer', position: 'relative', transition: 'border-color .15s, background .15s', minWidth: 0 },
      },
        h('div', { style: { fontSize: 11.5, fontWeight: 600, color: active ? ACCENT : css.t1 } }, label),
        h('div', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 8.5, color: css.t3, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, model),
        active && h('span', { style: { position: 'absolute', top: 5, right: 5, width: 6, height: 6, borderRadius: '50%', background: ACCENT } }),
      )
    }

    function PanguSettings() {
      const [config, setConfig] = React.useState(null)
      const [draft, setDraft] = React.useState(null)
      const [loadErr, setLoadErr] = React.useState(null)
      const [saveState, setSaveState] = React.useState({ s: 'idle', msg: '' })
      const [testState, setTestState] = React.useState({ s: 'idle', msg: '', ok: false })
      const [keyDirty, setKeyDirty] = React.useState(false)
      const [rooms, setRooms] = React.useState([])
      const [updateInfo, setUpdateInfo] = React.useState(null)
      const [updateLoading, setUpdateLoading] = React.useState(false)
      const [versions, setVersions] = React.useState(null)

      const load = React.useCallback(async () => {
        try {
          const value = unwrap(await callRemote('panguConfig', 'get'))
          const cfg = value?.config || {}
          setConfig(cfg)
          setVersions(value?.versions || null)
          setDraft({
            ce: cfg.consolidation_enabled !== false,
            ci: Number(cfg.consolidation_interval_hours) || 24,
            pb: cfg.pangu_base_url || '',
            pk: '',
            provider: cfg.llm_provider || 'openai',
            model: cfg.llm_model || '',
            baseUrl: cfg.llm_base_url || '',
            apiKey: '',
            whisperEnabled: cfg.whisper_enabled !== false,
            whisperModel: cfg.whisper_model || 'base',
          })
          setKeyDirty(false)
          setLoadErr(null)
          // fetch rooms for section 04
          callRemote('panguAdminKeys', 'listRooms').then(unwrap).then((v) => setRooms(v?.rooms || [])).catch(() => {})
          // auto-check update on load
          callRemote('panguDashboard', 'checkUpdate').then(unwrap).then((v) => setUpdateInfo(v)).catch(() => {})
        } catch (e) {
          setLoadErr(String(e.message || e))
        }
      }, [])

      React.useEffect(() => { load() }, [])

      const dirty = config && draft && (
        draft.ce !== (config.consolidation_enabled !== false) ||
        draft.ci !== (Number(config.consolidation_interval_hours) || 24) ||
        draft.pb !== (config.pangu_base_url || '') ||
        draft.provider !== (config.llm_provider || 'openai') ||
        draft.model !== (config.llm_model || '') ||
        draft.baseUrl !== (config.llm_base_url || '') ||
        draft.whisperEnabled !== (config.whisper_enabled !== false) ||
        draft.whisperModel !== (config.whisper_model || 'base') ||
        // 密码类输入框不回填原值，非空即视为「有改动」——否则只填凭据时
        // 保存按钮一直是灰的，等于存不下去（2026-09-21 修）。
        draft.pk !== '' ||
        keyDirty
      )

      const save = async () => {
        setSaveState({ s: 'saving', msg: '' })
        try {
          const patch = {
            pangu_base_url: draft.pb,
            consolidation_enabled: draft.ce,
            consolidation_interval_hours: draft.ci,
            llm_provider: draft.provider,
            llm_model: draft.model,
            llm_base_url: draft.baseUrl,
            whisper_enabled: draft.whisperEnabled,
            whisper_model: draft.whisperModel,
          }
          if (keyDirty && draft.apiKey) patch.llm_api_key = draft.apiKey
          if (draft.pk) patch.api_key = draft.pk
          const value = unwrap(await callRemote('panguConfig', 'save', patch))
          if (!value?.ok) throw new Error(value?.error || '写入失败')
          const rl = value.reload
          setSaveState({
            s: 'saved',
            msg: rl && rl.ok === false ? '已保存，但服务端热加载失败：' + (rl.error || '未知原因') : '',
          })
          await load()
          setTimeout(() => setSaveState({ s: 'idle', msg: '' }), 3500)
        } catch (e) {
          setSaveState({ s: 'error', msg: String(e.message || e) })
        }
      }

      const runTest = async () => {
        setTestState({ s: 'testing', msg: '', ok: false })
        try {
          const value = unwrap(await callRemote('panguConfig', 'testLlm'))
          if (value?.ok) {
            setTestState({ s: 'done', ok: true, msg: `连接成功 · ${value.model} · ${value.ms}ms${value.sample ? ' · 返回「' + value.sample.trim() + '」' : ''}` })
          } else {
            setTestState({ s: 'done', ok: false, msg: value?.error || '连接失败' })
          }
        } catch (e) {
          setTestState({ s: 'done', ok: false, msg: String(e.message || e) })
        }
      }

      const checkUpdate = async () => {
        setUpdateLoading(true)
        try {
          const v = unwrap(await callRemote('panguDashboard', 'checkUpdate'))
          setUpdateInfo(v)
        } catch (_) {}
        setUpdateLoading(false)
      }

      const pickProvider = (id) => {
        const p = LLM_PROVIDERS.find((x) => x.id === id)
        setDraft((prev) => ({
          ...prev,
          provider: id,
          baseUrl: p && (!prev.baseUrl || LLM_PROVIDERS.some((x) => x.url === prev.baseUrl)) ? p.url : prev.baseUrl,
          model: p && !prev.model ? p.model : prev.model,
        }))
      }

      if (loadErr) return h('div', { style: { padding: 20, maxWidth: 560 } }, h('div', { style: { height: 220 } }, h(ErrorState, { text: '配置读取失败(' + loadErr + ')', onRetry: load })))

      const keySet = config?.llm_api_key_set
      const keyHint = config?.llm_api_key_hint
      const provider = LLM_PROVIDERS.find((p) => p.id === draft?.provider) || {}

      return h('div', { style: { padding: '18px 20px 20px', color: css.t1, maxWidth: 560, animation: 'panguFade .25s ease' } },
        h('div', { style: { fontSize: 15, fontWeight: 600, margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 8 } },
          h('span', { style: { width: 16, height: 16, borderRadius: 5, background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_DEEP})`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' } },
            h(Icon, { name: 'box', size: 9, color: '#fff' })),
          '盘古记忆系统',
        ),
        h('div', { style: { fontSize: 11.5, color: css.t3, margin: '0 0 10px', lineHeight: 1.6 } },
          '以下设置直接读写 ', h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10.5 } }, '~/.pangu/config.json'),
          '，保存后自动热加载生效。明文密钥只写入本机，永不回传界面。'),
        config && h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 4 } },
          h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 10.5, border: `1px solid ${css.borderSoft}`, borderRadius: 999, padding: '3px 11px', color: css.t3, background: css.bg2 } },
            h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: css.ok } }), 'MCP 服务已就绪'),
          h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 10.5, border: `1px solid ${css.borderSoft}`, borderRadius: 999, padding: '3px 11px', color: css.t3, background: css.bg2 } },
            h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: keySet ? css.ok : css.t3 } }),
            keySet ? 'LLM 已配置 · ' + (draft.provider || '—') : 'LLM 未配置'),
        ),
        draft ? [
          h('div', { key: 's0-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '14px 0 7px', borderBottom: `1px solid ${css.borderSoft}`, marginTop: 12 } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '00'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '盘古服务地址'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, '本机或云端部署都从这里配'),
          ),
          h('div', { key: 's0', style: { padding: '12px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 8 } },
              h('div', { style: { fontSize: 12.5, fontWeight: 500 } }, '盘古 MCP / API 地址'),
              h('div', { style: { fontSize: 10.5, color: css.t3 } }, '本机部署填 http://IP:19529 · 云端填 https://域名'),
            ),
            h('input', {
              className: 'pangu-input', value: draft.pb, placeholder: 'https://你的域名',
              onChange: (e) => setDraft((prev) => ({ ...prev, pb: e.target.value })),
              style: { width: '100%', boxSizing: 'border-box', padding: '7px 12px', borderRadius: 8, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', outline: 'none' },
            }),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, lineHeight: 1.6 } },
              '保存即对插件的 REST/WS 生效；DSH 的 MCP 客户端共用此地址，重启 DSH 后重新挂载。仅允许 http/https，留空回退默认本地。'),
          ),
          // 只保留**一个**凭据字段（2026-09-21）。
          // 服务端本来有两个密钥（config.api_key / ~/.pangu/.admin_secret），
          // 而安装脚本已让两者取同一个值，插件在管理面直接复用本字段即可 ——
          // 再摆一个"可留空的管理密钥"只会让人疑惑"到底要不要填"。
          // 老部署若两把确实不同，见管理面板的错误提示（改服务端文件或重跑安装）。
          h('div', { key: 's0-cred', style: { padding: '12px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 8 } },
              h('div', { style: { fontSize: 12.5, fontWeight: 500 } }, '盘古凭据'),
              h('div', { style: { fontSize: 10.5, color: css.t3 } }, '必须填写 · 记忆与「管理」页都用它'),
            ),
            h('input', {
              className: 'pangu-input', type: 'password', value: draft.pk, placeholder: config?.api_key_set ? '已配置，留空保持不变' : '粘贴安装时打印的盘古凭据',
              onChange: (e) => setDraft((prev) => ({ ...prev, pk: e.target.value })),
              style: { width: '100%', boxSizing: 'border-box', padding: '7px 12px', borderRadius: 8, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12, fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', outline: 'none' },
            }),
            h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 6, lineHeight: 1.6 } },
              '上面「盘古服务地址」那台机器安装时打印的凭据（安装横幅的「DSH 填写卡」里有）。记忆读写/搜索用它，管理面板也用它。明文不回显，留空保持原值。'),
          ),
          h('div', { key: 's1-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '14px 0 7px', borderBottom: `1px solid ${css.borderSoft}`, marginTop: 12 } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '01'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, 'LLM 配置'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, '结晶 / 蒸馏 / 摘要用 · 未配置时静默跳过'),
          ),
          h('div', { key: 'prov', style: { padding: '12px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 8 } },
              h('div', { style: { fontSize: 12.5, fontWeight: 500 } }, '提供商'),
              h('div', { style: { fontSize: 10.5, color: css.t3 } }, '点选即带出默认端点与模型，已填的自定义值不会被覆盖'),
            ),
            h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7 } },
              LLM_PROVIDERS.map((p) => h(ProvCard, { key: p.id, label: p.label, model: p.model, active: draft.provider === p.id, onPick: () => pickProvider(p.id) })),
            ),
          ),
          h(TextField, {
            key: 'model', label: '模型', value: draft.model,
            desc: '可选：不填则自动从端点发现最佳模型（结晶/蒸馏时用）',
            placeholder: '(不填则自动选择最佳可用模型)',
            onChange: (v) => setDraft((p) => ({ ...p, model: v })), mono: true,
          }),
          h(TextField, {
            key: 'base', label: 'Base URL', value: draft.baseUrl,
            desc: '自建 / 代理端点填此处，OpenAI 兼容即可。留空使用默认端点。',
            placeholder: provider.url || '',
            onChange: (v) => setDraft((p) => ({ ...p, baseUrl: v })), mono: true,
          }),
          h(TextField, {
            key: 'key', label: 'API Key', value: draft.apiKey, password: true, mono: true,
            desc: keySet
              ? `已配置（${keyHint || '已设置'}）。明文不回显，留空即保持原 Key 不变；填入新值则覆盖。`
              : '尚未配置。Key 仅写入本机（权限 600），不会回传到界面。',
            placeholder: keySet ? '留空保持不变' : '粘贴 API Key（Ollama 可留空）',
            onChange: (v) => { setKeyDirty(true); setDraft((p) => ({ ...p, apiKey: v })) },
          }),
          h('div', { key: 'test', style: { padding: '11px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 } },
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { fontSize: 12.5, fontWeight: 500, color: css.t1 } }, '连接验证'),
                h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 2 } }, '使用「已保存」的配置测试；刚改过请先保存'),
              ),
              h('button', {
                onClick: runTest, type: 'button', disabled: testState.s === 'testing',
                style: { flexShrink: 0, padding: '6px 14px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t2, fontSize: 12, fontWeight: 500, cursor: testState.s === 'testing' ? 'default' : 'pointer' },
              }, testState.s === 'testing' ? '测试中…' : '测试连接'),
            ),
            testState.s === 'done' && h('div', {
              style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, border: `1px solid ${testState.ok ? css.ok : css.err}`, borderRadius: 8, padding: '7px 11px', fontSize: 11.5, background: testState.ok ? withAlpha(css.ok, '0d') : withAlpha(css.err, '0d') },
            },
              h('span', { style: { width: 7, height: 7, borderRadius: '50%', background: testState.ok ? css.ok : css.err, flexShrink: 0 } }),
              h('span', { style: { flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', color: css.t2, lineHeight: 1.5 } }, testState.msg),
              h('button', { onClick: () => setTestState({ s: 'idle', msg: '', ok: false }), type: 'button', style: { marginLeft: 'auto', padding: '2px 7px', border: 'none', background: 'transparent', color: css.t3, fontSize: 10.5, cursor: 'pointer', flexShrink: 0 } }, '清除'),
            ),
          ),
          h('div', { key: 's2-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '16px 0 7px', borderBottom: `1px solid ${css.borderSoft}` } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '02'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '记忆维护'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, '巩固动力学 · 与「盘古」标签页管线联动'),
          ),
          h(SettingRow, { key: 'ce', label: '自动巩固', desc: '定期合并相关记忆片段、衰减低价值记忆（03:00–05:00 窗口加权）' },
            h(Toggle, { checked: draft.ce, onChange: () => setDraft((p) => ({ ...p, ce: !p.ce })) }),
          ),
          h('div', { key: 'ci', style: { padding: '11px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14 } },
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { fontSize: 12.5, fontWeight: 500, color: css.t1 } }, '巩固间隔'),
                h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 2 } }, '两次自动巩固之间的间隔小时数'),
              ),
              h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 } },
                h('input', { type: 'range', min: 1, max: 72, step: 1, value: draft.ci, onChange: (e) => setDraft((p) => ({ ...p, ci: Number(e.target.value) })), style: { width: 110, accentColor: ACCENT } }),
                h('span', { style: { fontSize: 12, fontWeight: 600, color: ACCENT, minWidth: 32, textAlign: 'right', fontVariantNumeric: 'tabular-nums' } }, draft.ci + 'h'),
              ),
            ),
          ),
          // ── 语音转写 (Whisper) ──
          h('div', { key: 'whisper-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '16px 0 7px', borderBottom: `1px solid ${css.borderSoft}` } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '02B'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '语音转写'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, 'Whisper 模型 · 关闭可节省 140-800MB 内存'),
          ),
          h(SettingRow, { key: 'whisper-toggle', label: '启用 Whisper', desc: '启用后可将音频文件转为文字记忆' },
            h(Toggle, { checked: draft.whisperEnabled, onChange: () => setDraft((p) => ({ ...p, whisperEnabled: !p.whisperEnabled })) }),
          ),
          draft.whisperEnabled && h('div', { key: 'whisper-model', style: { padding: '11px 0', borderBottom: `1px solid ${css.borderSoft}` } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14 } },
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { fontSize: 12.5, fontWeight: 500, color: css.t1 } }, '模型大小'),
                h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 2 } }, '越大精度越高，内存占用也越大'),
              ),
              h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 } },
                h('select', {
                  value: draft.whisperModel,
                  onChange: (e) => setDraft((p) => ({ ...p, whisperModel: e.target.value })),
                  style: { padding: '6px 12px', borderRadius: 6, border: `1px solid ${css.borderSoft}`, background: css.bg1, color: css.t1, fontSize: 12 }
                },
                  h('option', { value: 'tiny' }, 'Tiny (75MB)'),
                  h('option', { value: 'base' }, 'Base (140MB)'),
                  h('option', { value: 'small' }, 'Small (460MB)'),
                  h('option', { value: 'medium' }, 'Medium (1.5GB)'),
                ),
              ),
            ),
          ),
          h('div', { key: 's3-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '16px 0 7px', borderBottom: `1px solid ${css.borderSoft}` } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '03'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '只读信息'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, '运行时快照 · 不可编辑'),
          ),
          h('div', { key: 's3-body', style: { paddingTop: 2 } },
            h(InfoRow, { label: '端点', value: config?.llm_base_url || '(未配置)' }),
            h(InfoRow, { label: 'API Key', value: keySet ? (keyHint || '已配置') : '未配置' }),
            h(InfoRow, { label: '指定模型', value: config?.llm_model || '(自动选择)' }),
            h(InfoRow, { label: '可用模型', value: (config?.llm_fallback_models || []).join(', ') || '(由端点动态发现)' }),
            h(InfoRow, { label: '嵌入模型', value: config?.embedding_model }),
            h(InfoRow, { label: '记忆库', value: config?.palace_path }),
            h(InfoRow, { label: '盘古服务地址', value: config?.pangu_base_url || '默认本地 127.0.0.1:19529' }),
          ),
          // ── 04 平台接入与审核 ──
          h('div', { key: 's4-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '16px 0 7px', borderBottom: `1px solid ${css.borderSoft}` } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '04'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '平台接入'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, 'pgp_* Token · 审核管理'),
          ),
          h('div', { key: 's4-body', style: { marginTop: 6, lineHeight: 1.7 } },
            h('div', { style: { fontSize: 11.5, color: css.t2 } },
              h('b', null, '接入流程'),
              h('ol', { style: { margin: '6px 0 0 16px', padding: 0, fontSize: 11, color: css.t2 } },
                h('li', null, '新平台调用 ', h('code', { style: { background: css.bg3, padding: '1px 4px', borderRadius: 3, fontSize: 10.5 } }, 'POST /api/v2/platforms/request'), '，提供平台名和名称'),
                h('li', null, '平台获得临时 Token（状态 pending）'),
                h('li', null, '管理员在', h('b', null, '「盘古」标签页 → 管理 → 平台'), ' 中审核'),
                h('li', null, '审核通过后平台获得正式 Token（pgp_* 前缀，状态 active）'),
              ),
            ),
            h('div', { style: { display: 'flex', gap: 8, marginTop: 10 } },
              h('button', { onClick: () => window.dispatchEvent(new CustomEvent('pangu:goto', { detail: { tab: 'admin', section: 'platforms' } })), style: { padding: '6px 14px', borderRadius: 7, border: 'none', background: ACCENT, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5 } },
                h(Icon, { name: 'box', size: 12, color: '#fff' }), '前往管理平台'),
            ),
          ),
          // ── 05 关于与更新 ──
          h('div', { key: 's5-head', style: { display: 'flex', alignItems: 'baseline', gap: 9, padding: '16px 0 7px', borderBottom: `1px solid ${css.borderSoft}` } },
            h('span', { style: { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace', fontSize: 10, fontWeight: 600, color: ACCENT } }, '05'),
            h('span', { style: { fontSize: 12.5, fontWeight: 600 } }, '关于与更新'),
            h('span', { style: { fontSize: 10.5, color: css.t3 } }, '版本信息 · 在线更新'),
          ),
          h('div', { key: 's5-body', style: { marginTop: 6 } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: '12px 14px', background: css.bg1 } },
              h('div', { style: { flex: 1 } },
                h('div', { style: { fontSize: 12.5, fontWeight: 600 } },
                  'dsh-pangu v' + (versions?.plugin || '…'),
                  h('span', { style: { fontSize: 10.5, fontWeight: 400, color: css.t3, marginLeft: 8 } },
                    '盘古服务 v' + (versions?.server || '未识别')),
                ),
                h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 3 } },
                  '架构 v2.1 · 平台Token · 记忆进化 · 知识生成'),
                h('div', { style: { fontSize: 10.5, color: css.t3, marginTop: 3 } },
                  updateInfo
                    ? updateInfo.ok
                      ? h('span', null, '上游发布 ', h('b', { style: { color: css.t1 } }, updateInfo.tag),
                        updateInfo.publishedAt && h('span', null, ' · 发布于 ' + updateInfo.publishedAt.slice(0, 10)),
                        h('span', { style: { color: css.t3 } }, '（GitHub Release，仅供参考；本地是否最新以 git 为准）'))
                      : h('span', { style: { color: css.warn } }, '上游检查失败：' + (updateInfo.error || ''))
                    : h('span', null, updateLoading ? '检查中…' : '点击右侧按钮检查上游发布'),
                ),
                updateInfo?.ok && updateInfo.body && h('div', { style: { fontSize: 10, color: css.t3, marginTop: 5, lineHeight: 1.6, maxHeight: 60, overflow: 'hidden' } }, updateInfo.body),
              ),
              h('button', { onClick: checkUpdate, disabled: updateLoading, style: { flexShrink: 0, padding: '6px 14px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t2, fontSize: 12, fontWeight: 500, cursor: updateLoading ? 'default' : 'pointer' } },
                updateLoading ? '检查中…' : '检查更新'),
            ),
            h('div', { style: { fontSize: 10, color: css.t3, marginTop: 6, lineHeight: 1.6 } },
              '上游发布仅作参考（GitHub Releases，经 gh-proxy.org 加速）；本机是本地源码运行，更新方式：',
              h('code', { style: { background: css.bg3, padding: '1px 4px', borderRadius: 3, fontSize: 10 } }, 'cd ~/pangu && git pull origin master && pnpm install'),
            ),
          ),
          h('div', { key: 'save', style: { position: 'sticky', bottom: 0, display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, padding: '10px 14px', border: `1px solid ${css.borderSoft}`, borderRadius: 10, background: css.bg2 } },
            h('button', { onClick: save, disabled: !dirty || saveState.s === 'saving', style: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 17px', borderRadius: 7, border: 'none', background: dirty ? ACCENT : css.bg3, color: dirty ? '#fff' : css.t3, fontSize: 12.5, fontWeight: 600, cursor: dirty ? 'pointer' : 'default', transition: 'background .2s' } },
              h(Icon, { name: saveState.s === 'saved' ? 'check' : 'save', size: 13, color: dirty ? '#fff' : undefined }),
              saveState.s === 'saving' ? '保存中…' : '保存',
            ),
            dirty && saveState.s !== 'saving' && h('span', { style: { fontSize: 11.5, color: css.warn, display: 'inline-flex', alignItems: 'center', gap: 5 } }, '● 有未保存的更改'),
            saveState.s === 'saved' && h('span', { style: { fontSize: 11.5, color: css.ok, display: 'inline-flex', alignItems: 'center', gap: 4 } }, saveState.msg || '已保存并生效'),
            saveState.s === 'error' && h('span', { style: { fontSize: 11.5, color: css.err, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, saveState.msg),
            h('span', { style: { marginLeft: 'auto', fontSize: 10.5, color: css.t3, flexShrink: 0 } }, 'Esc 放弃更改'),
          ),
        ] : h('div', { style: { marginTop: 12 } }, [0, 1, 2, 3].map((i) => h(Skeleton, { key: i, w: '100%', h: 40, r: 8, style: { marginBottom: 8 } }))),
      )
    }
    async function apply(ctxRef) {
      try {
      ctx = ctxRef
      const slots = ctxRef.get('slots')
      timer = ctxRef.get('timer')
      if (slots === undefined) return
      ensureStyles()

      // 先挂载 Typert Remote 贡献,之后 ctx.get('remote.<ns>') 才可用
      const remoteHub = ((ctxRef.get && ctxRef.get('remote')) || ctxRef.remote)
      if (remoteHub && typeof remoteHub.$mount === 'function') {
        const disposeRemote = await remoteHub.$mount(DESCRIPTORS)
        ctxRef.effect(() => () => disposeRemote(), 'pangu-dashboard: remote contribution')
      } else {
        console.error('[pangu-dashboard] remote hub 不可用:', typeof remoteHub, '; remote 面板数据将不可用')
      }

      slots.inject('sidebar.footer.action', () =>
        slots.register({ name: 'sidebar.footer.action', id: 'pangu-card', order: 99 }, SidebarCard),
      )
      slots.inject('conversation.view', () =>
        slots.register({ name: 'conversation.view', id: 'pangu-kg-tab', order: 20, label: '盘古' }, () => h(PanguTab, null)),
      )
      slots.inject('settings.section', () =>
        slots.register({ name: 'settings.section', id: 'pangu-settings', order: 40, label: () => '盘古记忆系统' }, PanguSettings),
      )
      } catch (e) { console.error('[dsh-pangu] apply error:', e) }
    }

    module.exports = { apply, inject }
    return module.exports
  },
})
