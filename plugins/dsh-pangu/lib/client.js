/**
 * pangu-dashboard DSH 客户端 v4.3。
 * 注册:
 *  - sidebar.footer.action:  侧边栏指标卡 + 快捷记忆(宽/窄双形态,独占一行)
 *  - conversation.view:      顶部标签页(概览 / 3D 星系图谱 / 知识卡片)
 *  - settings.section:       设置页(真实读写 ~/.pangu/config.json)
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
     * 与 lib/typert.host.mjs 的 invocations 对应;浏览器端用轻量 {parse} codec。
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
        { id: 'dsh-pangu#panguDashboard/data', service: 'panguDashboard', namespace: 'panguDashboard', method: 'data', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#DashboardData', schema: okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/ping', service: 'panguDashboard', namespace: 'panguDashboard', method: 'ping', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#Ping', schema: okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/deepHealth', service: 'panguDashboard', namespace: 'panguDashboard', method: 'deepHealth', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#DeepHealth', schema: okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/backup', service: 'panguDashboard', namespace: 'panguDashboard', method: 'backup', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#BackupResult', schema: okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/events', service: 'panguDashboard', namespace: 'panguDashboard', method: 'events', invocation: { kind: 'direct' }, parameters: [{ name: 'since', wire: 'since', source: 'json', schema: patchCodec, codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Since', schema: patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#Events', schema: okEnvelope } },
        { id: 'dsh-pangu#panguDashboard/add', service: 'panguDashboard', namespace: 'panguDashboard', method: 'add', invocation: { kind: 'direct' }, parameters: [{ name: 'args', wire: 'args', source: 'json', schema: patchCodec, codec: { mode: 'strict', typeSymbol: 'dsh-pangu#AddArgs', schema: patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#AddResult', schema: okEnvelope } },
        { id: 'dsh-pangu#panguKG/graph', service: 'panguKG', namespace: 'panguKG', method: 'graph', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#KGData', schema: okEnvelope } },
        { id: 'dsh-pangu#panguConfig/get', service: 'panguConfig', namespace: 'panguConfig', method: 'get', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#ConfigData', schema: okEnvelope } },
        { id: 'dsh-pangu#panguConfig/save', service: 'panguConfig', namespace: 'panguConfig', method: 'save', invocation: { kind: 'direct' }, parameters: [{ name: 'patch', wire: 'patch', source: 'json', schema: patchCodec, codec: { mode: 'strict', typeSymbol: 'dsh-pangu#SavePatch', schema: patchCodec } }], result: { mode: 'strict', typeSymbol: 'dsh-pangu#SaveResult', schema: okEnvelope } },
        { id: 'dsh-pangu#panguConfig/testLlm', service: 'panguConfig', namespace: 'panguConfig', method: 'testLlm', invocation: { kind: 'direct' }, parameters: [], result: { mode: 'strict', typeSymbol: 'dsh-pangu#TestLlmResult', schema: okEnvelope } },
      ],
    }

    /* ════════════════ 设计令牌 ════════════════ */
    const ACCENT = '#6c5ce7'
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
.pangu-tab:hover{color:var(--dsw-alias-label-primary,#171a23)}
.pangu-input:focus{border-color:${ACCENT}80 !important;box-shadow:0 0 0 2px ${ACCENT}1f}
.pangu-btn:hover{background:var(--dsw-alias-interactive-bg-hover,rgba(38,49,72,.06))}
.pangu-card{transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
.pangu-card:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.09);border-color:var(--dsw-alias-border-l4,rgba(0,0,0,.2))}
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
      event: '#f85149', location: '#79c0ff', memory: '#56d364',
    }
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
    function unwrap(r) {
      if (r && r.ok) return r.value
      throw new Error((r && r.error) || '远程调用失败')
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
        // 事件驱动:实时通道有新记忆事件时提前刷新(无变化时零开销)
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
        return () => { if (stop) stop(); if (stop2) stop2(); if (offReset) offReset() }
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

      // footer.action 槽位是横向 flex 且不换行,卡片会和设置按钮等挤在一行;
      // 向上找到横向 flex 容器补 wrap,本卡 width:100% 独占一行(上下排)。
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
      const u = state.data?.usage
      const total = s?.total || 0
      const score = s?.healthScore || 0
      const mpct = u?.usage?.rolling?.percent || 0
      const loading = state.status === 'loading'

      // 窄栏(56px rail):只渲染 logo 小胶囊,状态用透明度表达
      if (!wide) {
        return h('div', { ref: rootRef, title: '盘古记忆系统' + (state.status === 'error' ? '(离线)' : ''), style: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 28, margin: '2px auto 6px', borderRadius: 8, background: css.bg2, border: `1px solid ${css.borderSoft}` } },
          loading
            ? h(Skeleton, { w: 12, h: 12, r: 4 })
            : h('span', { style: { width: 14, height: 14, borderRadius: 5, background: `linear-gradient(135deg, ${ACCENT}, #a78bfa)`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', opacity: state.status === 'error' ? 0.35 : 1 } },
                h(Icon, { name: 'box', size: 9, color: '#fff' }),
              ),
        )
      }

      return h('div', { ref: rootRef, style: { width: '100%', flexShrink: 0, boxSizing: 'border-box', margin: '14px 0 8px', padding: '10px 12px 8px', background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, animation: 'panguFade .25s ease' } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 9 } },
          h('span', { style: { width: 14, height: 14, borderRadius: 5, background: `linear-gradient(135deg, ${ACCENT}, #a78bfa)`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' } },
            h(Icon, { name: 'box', size: 9, color: '#fff' }),
          ),
          h('span', { style: { fontSize: 10, fontWeight: 700, color: css.t2, letterSpacing: '1px' } }, '盘古'),
          h('span', { style: { flex: 1 } }),
          loading
            ? h(Skeleton, { w: 34, h: 8 })
            : h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 5 }, title: state.status === 'error' ? '无法连接盘古服务' : '服务正常' },
                h(StatusDot, { state: state.status === 'error' ? 'error' : 'ok' }),
                h('span', { style: { fontSize: 9.5, color: css.t3 } }, fmtAgo(state.at)),
              ),
        ),
        loading ? (
          [0, 1, 2].map((i) => h('div', { key: i, style: { marginBottom: 12 } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 4 } },
              h(Skeleton, { w: 46, h: 9 }), h(Skeleton, { w: 24, h: 9 }),
            ),
            h(Skeleton, { w: '100%', h: 4, r: 2 }),
          ))
        ) : (
          [
            h(Metric, { key: 'm', icon: 'database', tint: ACCENT, label: '记忆', value: fmtNum(total), pct: (total / 1000) * 100 }),
            h(Metric, { key: 'h', icon: 'pulse', tint: css.ok, label: '健康', value: (s ? score : 0) + '/100', pct: score, danger: score < 40 ? 'err' : score < 70 ? 'warn' : null }),
            h(Metric, { key: 'u', icon: 'gauge', tint: css.info, label: '用量', value: mpct + '%', pct: mpct, danger: mpct >= 80 ? 'err' : mpct >= 50 ? 'warn' : null }),
          ]
        ),
        h('div', { key: 'quickadd', style: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 } },
          h('input', {
            className: 'pangu-input', value: draft,
            placeholder: addState.s === 'ok' ? '已入库 ✓' : '快速记一条…(回车入库)',
            onChange: (e) => setDraft(e.target.value),
            onKeyDown: (e) => { if (e.key === 'Enter') doAdd() },
            style: { flex: 1, minWidth: 0, padding: '4px 8px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg1, color: addState.s === 'ok' ? css.ok : css.t1, fontSize: 11, outline: 'none', boxSizing: 'border-box' },
          }),
          h('button', {
            className: 'pangu-btn', onClick: doAdd,
            disabled: addState.s === 'saving' || !draft.trim(),
            title: '添加到盘古记忆',
            style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: 7, border: 'none', background: draft.trim() ? ACCENT : css.bg3, color: draft.trim() ? '#fff' : css.t3, fontSize: 13, fontWeight: 700, cursor: draft.trim() ? 'pointer' : 'default', flexShrink: 0, transition: 'background .15s' },
          }, addState.s === 'saving' ? '…' : '+'),
        ),
        addState.s === 'error' && h('div', { style: { fontSize: 10, color: css.err, marginTop: 3 } }, addState.msg),
      )
    }

    /* ════════════════════════════════════════════
     * 2. 顶部标签页 — 概览 / 3D 星系图谱 / 卡片
     * ════════════════════════════════════════════ */
    function StatTile({ icon, tint, label, value }) {
      return h('div', { className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 12, padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 6 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
          h('span', { style: { width: 22, height: 22, borderRadius: 7, background: tint + '1c', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' } },
            h(Icon, { name: icon, size: 13, color: tint }),
          ),
          h('span', { style: { fontSize: 11.5, color: css.t3 } }, label),
        ),
        h('div', { style: { fontSize: 22, fontWeight: 700, color: css.t1, fontVariantNumeric: 'tabular-nums', lineHeight: 1.1 } }, value),
      )
    }

    function StatusPill({ status }) {
      const color = status === 'ok' ? css.ok : status === 'fail' || status === 'degraded' ? css.err : css.t3
      return h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, color: css.t1 } },
        h('span', { style: { width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 } }),
        status === 'ok' ? '正常' : status === 'fail' ? '异常' : status || '—',
      )
    }

    function WingDistCard({ byWing }) {
      const entries = Object.entries(byWing || {}).sort((a, b) => b[1] - a[1]).slice(0, 8)
      const max = Math.max(1, ...entries.map((e) => e[1]))
      return h('div', { className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 12, padding: '13px 14px' } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 } },
          h(Icon, { name: 'layers', size: 13, color: css.ok }),
          h('span', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1 } }, '知识翼分布'),
        ),
        entries.length ? entries.map(([w, count]) => h('div', { key: w, style: { padding: '6px 0', borderBottom: `1px solid ${css.borderSoft}` } },
          h('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 12 } },
            h('span', { style: { color: css.t2 } }, wingLabel(w)),
            h('span', { style: { color: css.t1, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, fmtNum(count)),
          ),
          h('div', { style: { height: 4, background: css.bg3, borderRadius: 2, overflow: 'hidden' } },
            h('div', { style: { height: '100%', width: Math.max(3, (count / max) * 100) + '%', background: `linear-gradient(90deg, ${ACCENT}80, ${ACCENT})`, borderRadius: 2 } }),
          ),
        )) : h('div', { style: { fontSize: 12, color: css.t3, padding: '10px 0' } }, '暂无翼数据'),
      )
    }

    function OverviewPane({ dash, config, dashErr, loading, onRetry }) {
      const [deep, setDeep] = React.useState(null)
      const [bk, setBk] = React.useState({ s: 'idle', msg: '' })

      React.useEffect(() => {
        let alive = true
        callRemote('panguDashboard', 'deepHealth')
          .then(unwrap)
          .then((v) => { if (alive) setDeep(v) })
          .catch(() => { if (alive) setDeep({ ok: false }) })
        return () => { alive = false }
      }, [])

      const doBackup = async () => {
        setBk({ s: 'saving', msg: '' })
        try {
          const v = unwrap(await callRemote('panguDashboard', 'backup'))
          if (!v?.ok) throw new Error(v?.error || '备份失败')
          setBk({ s: 'done', msg: `${fmtNum(v.memories)}条 · ${fmtSize(v.size)}` })
          setTimeout(() => setBk({ s: 'idle', msg: '' }), 4000)
        } catch (e) {
          setBk({ s: 'error', msg: String(e.message || e) })
        }
      }

      if (dashErr && !dash) return h(ErrorState, { text: '无法连接盘古服务(' + dashErr + ')', onRetry })
      const s = dash?.stats, u = dash?.usage
      if (loading && !dash) {
        return h('div', { style: { padding: 16 } },
          h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10 } },
            [0, 1, 2, 3].map((i) => h(Skeleton, { key: i, w: '100%', h: 68, r: 12 })),
          ),
          h(Skeleton, { w: '100%', h: 140, r: 12, style: { marginTop: 12 } }),
        )
      }
      const usage = u?.usage
      const windows = usage ? [['rolling', '实时'], ['weekly', '本周'], ['monthly', '本月']].filter(([k]) => usage[k]) : []
      const checkRow = (name, label) => {
        const c = deep?.checks?.find((x) => x.name === name)
        return h(InfoRow, { key: name, label, value: c ? h(StatusPill, { status: c.status }) : deep ? '—' : '…' })
      }
      return h('div', { style: { padding: 16, overflow: 'auto', height: '100%', boxSizing: 'border-box', animation: 'panguFade .25s ease' } },
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10 } },
          h(StatTile, { icon: 'database', tint: ACCENT, label: '记忆总数', value: fmtNum(s?.total) }),
          h(StatTile, { icon: 'layers', tint: css.ok, label: '知识翼', value: fmtNum(s?.wings) }),
          h(StatTile, { icon: 'graph', tint: css.info, label: '图谱实体', value: fmtNum(s?.kgEntities) }),
          h(StatTile, { icon: 'network', tint: css.warn, label: '图谱关系', value: fmtNum(s?.kgRelations) }),
        ),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 10, marginTop: 12 } },
          h('div', { className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 12, padding: '13px 14px' } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 } },
              h(Icon, { name: 'cpu', size: 13, color: css.info }),
              h('span', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1, flex: 1 } }, '服务信息'),
              h('button', { className: 'pangu-btn', onClick: doBackup, disabled: bk.s === 'saving', title: '创建记忆备份快照', style: { display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10.5, color: bk.s === 'error' ? css.err : css.t2, background: 'transparent', border: `1px solid ${css.border}`, borderRadius: 6, padding: '2px 8px', cursor: 'pointer' } },
                h(Icon, { name: bk.s === 'done' ? 'check' : 'database', size: 11, color: bk.s === 'done' ? css.ok : undefined }),
                bk.s === 'saving' ? '备份中…' : bk.s === 'done' ? '已备份' : '立即备份',
              ),
            ),
            (bk.s === 'done' || bk.s === 'error') && h('div', { style: { fontSize: 10.5, color: bk.s === 'done' ? css.ok : css.err, marginBottom: 4 } }, bk.msg),
            h(InfoRow, { label: '状态', value: s ? (s.health || '—') + ' · ' + fmtUptime(s.uptimeSeconds) : '—' }),
            h(InfoRow, { label: '版本', value: s?.version }),
            checkRow('structure', '结构检查'),
            checkRow('memory', '记忆检查'),
            checkRow('embedding', '嵌入检查'),
            h(InfoRow, { label: 'LLM', value: config ? [config.llm_provider, config.llm_model].filter(Boolean).join(' / ') : '—' }),
          ),
          h('div', { className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 12, padding: '13px 14px' } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 } },
              h(Icon, { name: 'gauge', size: 13, color: ACCENT }),
              h('span', { style: { fontSize: 12.5, fontWeight: 600, color: css.t1 } }, '模型用量'),
            ),
            u?.keySet ? (
              windows.length ? windows.map(([k, label]) => {
                const w = usage[k], pct = w?.percent || 0
                const c = pct >= 80 ? css.err : pct >= 50 ? css.warn : css.info
                return h('div', { key: k, style: { padding: '7px 0', borderBottom: `1px solid ${css.borderSoft}` } },
                  h('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 } },
                    h('span', { style: { color: css.t3 } }, label),
                    h('span', { style: { color: c, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, pct + '%'),
                  ),
                  h('div', { style: { height: 4, background: css.bg3, borderRadius: 2, overflow: 'hidden' } },
                    h('div', { style: { height: '100%', width: Math.min(100, pct) + '%', background: c, borderRadius: 2, transition: 'width .6s cubic-bezier(.22,1,.36,1)' } }),
                  ),
                )
              }) : h('div', { style: { fontSize: 12, color: css.t3, padding: '10px 0' } }, '暂无用量数据')
            ) : h('div', { style: { fontSize: 12, color: css.t3, padding: '10px 0' } }, '未配置 LLM API Key'),
          ),
          h(WingDistCard, { byWing: s?.byWing }),
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
            g.addColorStop(0.35, color + (pal.isDark ? '66' : '55'))
            g.addColorStop(1, color + '00')
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
            h('span', { style: { width: 7, height: 7, borderRadius: '50%', background: typeColor(tp), boxShadow: `0 0 5px ${typeColor(tp)}88` } }),
            typeLabel(tp),
          )),
        ),
      )
    }

    function CardsPane({ nodes, kgErr, loading, onRetry }) {
      if (kgErr && !nodes.length) return h(ErrorState, { text: '图谱加载失败(' + kgErr + ')', onRetry })
      if (loading && !nodes.length) return h('div', { style: { padding: 16 } }, h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 } }, [0, 1, 2, 3, 4, 5].map((i) => h(Skeleton, { key: i, w: '100%', h: 92, r: 10 }))))
      return h('div', { style: { overflow: 'auto', height: '100%', boxSizing: 'border-box', padding: '14px 16px', animation: 'panguFade .25s ease' } },
        nodes.length === 0
          ? h('div', { style: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 8, color: css.t3 } },
              h(Icon, { name: 'search', size: 22, color: css.t3 }),
              h('span', { style: { fontSize: 12.5 } }, '没有匹配的实体'),
            )
          : h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, alignContent: 'start' } },
              nodes.map((n) => {
                const color = typeColor(n.type)
                return h('div', { key: n.id, className: 'pangu-card', style: { background: css.bg2, border: `1px solid ${css.borderSoft}`, borderRadius: 10, padding: 12, position: 'relative', overflow: 'hidden' } },
                  h('div', { style: { position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${color}, ${color}44)` } }),
                  h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 } },
                    h('span', { style: { width: 24, height: 24, borderRadius: 7, background: color + '1c', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 } },
                      h(Icon, { name: 'box', size: 12, color }),
                    ),
                    h('div', { style: { flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, color: css.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, n.name || n.id),
                    h(TypeChip, { type: n.type }),
                  ),
                  n.description && h('div', { style: { fontSize: 11.5, color: css.t2, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', marginBottom: 6 } }, n.description),
                  n.memory_count ? h('div', { style: { fontSize: 10.5, color: css.t3 } }, '关联记忆 ' + n.memory_count + ' 条') : null,
                )
              }),
            ),
      )
    }

    function PanguTab() {
      const [tab, setTab] = React.useState('overview')
      const [dash, setDash] = React.useState(null)
      const [kg, setKg] = React.useState(null)
      const [config, setConfig] = React.useState(null)
      const [dashErr, setDashErr] = React.useState(null)
      const [kgErr, setKgErr] = React.useState(null)
      const [loading, setLoading] = React.useState(true)
      const [refreshing, setRefreshing] = React.useState(false)
      const [search, setSearch] = React.useState('')
      const [typeFilter, setTypeFilter] = React.useState('')

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
        return () => { clearInterval(id); if (offReset) offReset() }
      }, [])

      const allNodes = React.useMemo(() => kg?.nodes || [], [kg])
      const graphEdges = React.useMemo(() => kg?.edges || [], [kg])
      // 搜索/类型过滤:卡片页物理移除;星系页全量保留 + dim 高亮(Obsidian 式)
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
        style: { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '7px 14px', border: 'none', borderBottom: tab === key ? '2px solid ' + ACCENT : '2px solid transparent', background: 'transparent', color: tab === key ? ACCENT : css.t2, fontSize: 12.5, fontWeight: tab === key ? 600 : 400, cursor: 'pointer', transition: 'color .15s' },
      }, h(Icon, { name: icon, size: 13 }), text)

      const inputStyle = { padding: '5px 10px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12, outline: 'none', boxSizing: 'border-box' }

      return h('div', { style: { height: '100%', display: 'flex', flexDirection: 'column', color: css.t1 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6, padding: '0 12px', borderBottom: `1px solid ${css.borderSoft}`, flexShrink: 0 } },
          tabBtn('overview', 'overview', '概览'),
          tabBtn('graph', 'orbit', '星系'),
          tabBtn('cards', 'grid', '卡片'),
          h('div', { style: { flex: 1 } }),
          tab !== 'overview' && h('input', { className: 'pangu-input', value: search, onChange: (e) => setSearch(e.target.value), placeholder: '搜索实体…', style: { ...inputStyle, width: 150 } }),
          tab !== 'overview' && h('select', { className: 'pangu-input', value: typeFilter, onChange: (e) => setTypeFilter(e.target.value), style: { ...inputStyle, padding: '4.5px 6px' } },
            h('option', { value: '' }, '全部类型'),
            [...new Set((kg?.nodes || []).map((n) => n.type || 'default'))].map((tp) => h('option', { key: tp, value: tp }, typeLabel(tp))),
          ),
          tab !== 'overview' && h('span', { style: { fontSize: 11, color: css.t3, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' } }, graphNodes.length + ' 实体'),
          h('button', { className: 'pangu-btn', onClick: () => load(), title: '刷新', style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 7, border: 'none', background: 'transparent', color: css.t2, cursor: 'pointer', opacity: refreshing ? 0.5 : 1 } },
            h(Icon, { name: 'refresh', size: 13 }),
          ),
        ),
        tab === 'overview'
          ? h(OverviewPane, { dash, config, dashErr, loading, onRetry: () => load() })
          : tab === 'graph'
            ? h(GraphPane, { nodes: allNodes, edges: graphEdges, matchSet: matched, kgErr, loading, onRetry: () => load() })
            : h(CardsPane, { nodes: graphNodes, kgErr, loading, onRetry: () => load() }),
      )
    }

    /* ════════════════════════════════════════════
     * 3. 设置页 — 真实读写 ~/.pangu/config.json
     * ════════════════════════════════════════════ */
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

    function PanguSettings() {
      const [config, setConfig] = React.useState(null)
      const [draft, setDraft] = React.useState(null)
      const [loadErr, setLoadErr] = React.useState(null)
      const [saveState, setSaveState] = React.useState({ s: 'idle', msg: '' })
      const [testState, setTestState] = React.useState({ s: 'idle', msg: '', ok: false })
      const [keyDirty, setKeyDirty] = React.useState(false)  // 用户是否重新输入了 Key

      const load = React.useCallback(async () => {
        try {
          const value = unwrap(await callRemote('panguConfig', 'get'))
          const cfg = value?.config || {}
          setConfig(cfg)
          setDraft({
            ce: cfg.consolidation_enabled !== false,
            ci: Number(cfg.consolidation_interval_hours) || 24,
            provider: cfg.llm_provider || 'openai',
            model: cfg.llm_model || '',
            baseUrl: cfg.llm_base_url || '',
            // 明文 Key 永不下发，这里恒为空；placeholder 提示是否已设置
            apiKey: '',
          })
          setKeyDirty(false)
          setLoadErr(null)
        } catch (e) {
          setLoadErr(String(e.message || e))
        }
      }, [])

      React.useEffect(() => { load() }, [])

      const dirty = config && draft && (
        draft.ce !== (config.consolidation_enabled !== false) ||
        draft.ci !== (Number(config.consolidation_interval_hours) || 24) ||
        draft.provider !== (config.llm_provider || 'openai') ||
        draft.model !== (config.llm_model || '') ||
        draft.baseUrl !== (config.llm_base_url || '') ||
        keyDirty
      )

      const save = async () => {
        setSaveState({ s: 'saving', msg: '' })
        try {
          const patch = {
            consolidation_enabled: draft.ce,
            consolidation_interval_hours: draft.ci,
            llm_provider: draft.provider,
            llm_model: draft.model,
            llm_base_url: draft.baseUrl,
          }
          // 仅在用户真的输入了新 Key 时才提交，避免用空串覆盖已存的 Key
          if (keyDirty && draft.apiKey) patch.llm_api_key = draft.apiKey
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

      const pickProvider = (id) => {
        const p = LLM_PROVIDERS.find((x) => x.id === id)
        setDraft((prev) => ({
          ...prev,
          provider: id,
          // 切换提供商时带出默认端点/模型，但不覆盖用户已手填的非默认值
          baseUrl: p && (!prev.baseUrl || LLM_PROVIDERS.some((x) => x.url === prev.baseUrl)) ? p.url : prev.baseUrl,
          model: p && !prev.model ? p.model : prev.model,
        }))
      }

      if (loadErr) return h('div', { style: { padding: 20, maxWidth: 520 } }, h('div', { style: { height: 220 } }, h(ErrorState, { text: '配置读取失败(' + loadErr + ')', onRetry: load })))

      const keySet = config?.llm_api_key_set
      const keyHint = config?.llm_api_key_hint

      return h('div', { style: { padding: 20, color: css.t1, maxWidth: 520, animation: 'panguFade .25s ease' } },
        h('div', { style: { fontSize: 15, fontWeight: 600, margin: '0 0 3px' } }, '记忆系统'),
        h('div', { style: { fontSize: 12, color: css.t3, margin: '0 0 4px' } }, '以下设置直接读写 ~/.pangu/config.json，保存后自动热加载生效'),
        draft ? [
          h(SectionTitle, { key: 'llm-t', style: { marginTop: 14 } }, 'LLM 配置'),
          h('div', { key: 'llm-d', style: { fontSize: 11, color: css.t3, margin: '2px 0 8px', lineHeight: 1.6 } },
            '用于知识结晶、记忆蒸馏、摘要等需要语言模型的能力。未配置时这些功能会被静默跳过，其余记忆检索不受影响。',
          ),
          h(SettingRow, { key: 'prov', label: '提供商', desc: '选择后会带出默认 Base URL' },
            h('select', {
              value: draft.provider,
              onChange: (e) => pickProvider(e.target.value),
              style: { padding: '6px 9px', borderRadius: 7, border: `1px solid ${css.border}`, background: css.bg2, color: css.t1, fontSize: 12.5, outline: 'none', cursor: 'pointer', minWidth: 150 },
            }, LLM_PROVIDERS.map((p) => h('option', { key: p.id, value: p.id }, p.label))),
          ),
          h(TextField, {
            key: 'model', label: '模型', value: draft.model,
            placeholder: (LLM_PROVIDERS.find((p) => p.id === draft.provider) || {}).model || 'gpt-4o',
            onChange: (v) => setDraft((p) => ({ ...p, model: v })), mono: true,
          }),
          h(TextField, {
            key: 'base', label: 'Base URL', value: draft.baseUrl,
            desc: '留空使用该提供商的默认端点。自建/代理端点填此处（OpenAI 兼容即可）。',
            placeholder: (LLM_PROVIDERS.find((p) => p.id === draft.provider) || {}).url || '',
            onChange: (v) => setDraft((p) => ({ ...p, baseUrl: v })), mono: true,
          }),
          h(TextField, {
            key: 'key', label: 'API Key', value: draft.apiKey, password: true, mono: true,
            desc: keySet
              ? `已配置（${keyHint || '已设置'}）。出于安全考虑不回显明文，留空即保持原 Key 不变；填入新值则覆盖。`
              : '尚未配置。Key 仅写入本机 ~/.pangu/config.json（权限 600），不会回传到界面。',
            placeholder: keySet ? '留空保持不变' : '粘贴 API Key（Ollama 可留空）',
            onChange: (v) => { setKeyDirty(true); setDraft((p) => ({ ...p, apiKey: v })) },
          }),
          h('div', { key: 'llm-actions', style: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 } },
            h('button', {
              onClick: runTest, type: 'button', disabled: testState.s === 'testing',
              style: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 13px', borderRadius: 8, border: `1px solid ${css.border}`, background: css.bg2, color: css.t2, fontSize: 12, fontWeight: 500, cursor: testState.s === 'testing' ? 'default' : 'pointer' },
            }, testState.s === 'testing' ? '测试中…' : '测试连接'),
            testState.s === 'done' && h('span', {
              style: { fontSize: 11.5, color: testState.ok ? css.ok : css.err, overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.5 },
            }, testState.msg),
            testState.s === 'done' && h('button', {
              onClick: () => setTestState({ s: 'idle', msg: '', ok: false }), type: 'button',
              style: { marginLeft: 'auto', padding: '3px 8px', borderRadius: 6, border: 'none', background: 'transparent', color: css.t3, fontSize: 11, cursor: 'pointer' },
            }, '清除'),
          ),
          h('div', { key: 'llm-note', style: { fontSize: 11, color: css.t3, marginTop: 8, lineHeight: 1.6 } },
            '测试连接使用「已保存」的配置。若刚改动过，请先点下方保存再测试。',
          ),

          h(SectionTitle, { key: 'mem-t', style: { marginTop: 22 } }, '记忆维护'),
          h(SettingRow, { key: 'ce', label: '自动巩固', desc: '定期合并相关记忆片段、衰减低价值记忆' },
            h(Toggle, { checked: draft.ce, onChange: () => setDraft((p) => ({ ...p, ce: !p.ce })) }),
          ),
          h('div', { key: 'ci', style: { padding: '11px 0' } },
            h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14 } },
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { fontSize: 13, fontWeight: 500, color: css.t1 } }, '巩固间隔'),
                h('div', { style: { fontSize: 11, color: css.t3, marginTop: 2 } }, '两次自动巩固之间的时间间隔'),
              ),
              h('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
                h('input', { type: 'range', min: 1, max: 72, step: 1, value: draft.ci, onChange: (e) => setDraft((p) => ({ ...p, ci: Number(e.target.value) })), style: { width: 110, accentColor: ACCENT } }),
                h('span', { style: { fontSize: 12, fontWeight: 600, color: ACCENT, minWidth: 32, textAlign: 'right', fontVariantNumeric: 'tabular-nums' } }, draft.ci + 'h'),
              ),
            ),
          ),
          h('div', { key: 'save', style: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, flexWrap: 'wrap' } },
            h('button', { onClick: save, disabled: !dirty || saveState.s === 'saving', style: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 16px', borderRadius: 8, border: 'none', background: dirty ? ACCENT : css.bg3, color: dirty ? '#fff' : css.t3, fontSize: 12.5, fontWeight: 600, cursor: dirty ? 'pointer' : 'default', transition: 'background .2s' } },
              h(Icon, { name: saveState.s === 'saved' ? 'check' : 'save', size: 13 }),
              saveState.s === 'saving' ? '保存中…' : '保存',
            ),
            dirty && saveState.s !== 'saving' && h('span', { style: { fontSize: 11.5, color: css.warn } }, '有未保存的更改'),
            saveState.s === 'saved' && h('span', { style: { fontSize: 11.5, color: css.ok, display: 'inline-flex', alignItems: 'center', gap: 4 } }, saveState.msg || '已保存并生效'),
            saveState.s === 'error' && h('span', { style: { fontSize: 11.5, color: css.err, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, saveState.msg),
          ),
        ] : h('div', { style: { marginTop: 12 } }, [0, 1, 2, 3].map((i) => h(Skeleton, { key: i, w: '100%', h: 40, r: 8, style: { marginBottom: 8 } }))),
        h(SectionTitle, null, '只读信息'),
        h(InfoRow, { label: 'LLM', value: config ? [config.llm_provider, config.llm_model].filter(Boolean).join(' / ') : null }),
        h(InfoRow, { label: 'API Key', value: keySet ? (keyHint || '已配置') : '未配置' }),
        h(InfoRow, { label: '嵌入模型', value: config?.embedding_model }),
        h(InfoRow, { label: '记忆库', value: config?.palace_path }),
        h(InfoRow, { label: 'MCP 服务', value: '127.0.0.1:19529' }),
      )
    }

    /* ════════════════ 挂载 ════════════════ */
    async function apply(ctxRef) {
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
    }

    module.exports = { apply, inject }
    return module.exports
  },
})
