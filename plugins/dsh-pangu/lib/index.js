/**
 * pangu-dashboard 宿主插件 v4。
 * 提供:
 *  1. panguDashboard Typert Remote — 面板数据/深度健康/备份/实时事件/快速添加记忆
 *  2. panguKG Typert Remote — 知识图谱节点与关系
 *  3. panguConfig Typert Remote — 记忆系统配置读写
 * v4: 新增 /ws 实时事件监听(断线指数退避重连)供客户端事件驱动刷新;
 *     新增 pangu_add_memory 快速添加;图谱拉取放宽到 limit=400。
 */
'use strict'

const fsp = require('fs/promises')
const os = require('os')
const path = require('path')

const { createMessageCache } = require('./proactive/message-cache')
const { loadInjectionConfig, DEFAULTS: INJECTION_DEFAULTS } = require('./proactive/config')
const { createPanguMcpClient } = require('./proactive/mcp-client')
const { createCircuitBreaker } = require('./proactive/circuit-breaker')
const { createDedupTracker } = require('./proactive/dedup-tracker')
const { createStatsCollector } = require('./proactive/stats-collector')
const { filterSensitive } = require('./proactive/sensitive-filter')
const { createInjectionPipeline } = require('./proactive/injection-pipeline')
const { createConsolidationWriter } = require('./proactive/consolidation-writer')

const PANGU_BASE = 'http://127.0.0.1:19529'
const CONFIG_PATH = path.join(os.homedir(), '.pangu', 'config.json')
const HTTP_TIMEOUT_MS = 8000

async function apply(ctx) {
  async function fetchJson(url, options = {}) {
    const res = await fetch(url, {
      method: options.method || 'GET',
      headers: { 'content-type': 'application/json', ...(options.headers || {}) },
      body: options.body,
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
  }

  async function readConfig() {
    try {
      return JSON.parse(await fsp.readFile(CONFIG_PATH, 'utf8'))
    } catch (_) {
      return {}
    }
  }

  async function fetchPanguStats() {
    let total = 0
    let wings = 0
    let rooms = 0
    let kgEntities = 0
    let kgRelations = 0
    let byWing
    try {
      const body = await fetchJson(`${PANGU_BASE}/mcp`, {
        method: 'POST',
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'tools/call',
          params: { name: 'pangu_stats', arguments: {} },
        }),
      })
      const text = body?.result?.content?.[0]?.text
      if (!text) return { ok: false, error: 'pangu stats empty' }
      // pangu_stats 返回缩进 JSON;解析失败时回退正则
      let parsed = null
      try { parsed = JSON.parse(text) } catch (_) {}
      if (parsed) {
        total = Number(parsed?.memory?.total_memories) || 0
        wings = Number(parsed?.palace?.wings_count) || 0
        rooms = Number(parsed?.palace?.rooms_count) || 0
        kgEntities = Number(parsed?.knowledge_graph?.entities) || 0
        kgRelations = Number(parsed?.knowledge_graph?.relations) || 0
        byWing = parsed?.memory?.by_wing
      } else {
        total = Number((text.match(/"total_memories".{0,3}[: ]+([0-9]+)/) || [])[1]) || 0
        wings = Number((text.match(/"wings_count".{0,3}[: ]+([0-9]+)/) || [])[1]) || 0
      }
    } catch (e) {
      return { ok: false, error: 'pangu MCP unreachable: ' + String(e) }
    }

    let health = '?'
    let healthScore = 0
    let version
    let uptimeSeconds
    try {
      const hd = await fetchJson(`${PANGU_BASE}/health`)
      const d = hd?.data || {}
      health = d.status || 'ok'
      version = d.version
      uptimeSeconds = d.uptime_seconds
      healthScore = health === 'ok' ? 100 : health === 'degraded' ? 70 : 0
    } catch (_) {
      health = 'unreachable'
    }

    return { ok: true, total, wings, rooms, kgEntities, kgRelations, byWing, health, healthScore, version, uptimeSeconds, ts: Date.now() }
  }

  async function fetchKG() {
    try {
      const body = await fetchJson(`${PANGU_BASE}/api/v2/graph?limit=400`)
      if (body?.code !== 0) return { ok: false, error: body?.error || 'graph error' }
      return { ok: true, nodes: body?.data?.nodes || [], edges: body?.data?.edges || [] }
    } catch (e) {
      return { ok: false, error: 'graph unreachable: ' + String(e) }
    }
  }

  // ── 实时事件:连 pangu /ws(SEC-004 修复后需 api_key/JWT),断线指数退避重连 ──
  const evState = { list: [], lastTs: 0, ws: null, retryMs: 1000, closed: false, reconnectTimer: null }

  async function startEvents() {
    if (evState.ws) return
    let token = ''
    try { token = (await readConfig()).api_key || '' } catch (_) {}
    const url = `${PANGU_BASE.replace('http', 'ws')}/ws` + (token ? `?token=${encodeURIComponent(token)}` : '')
    try {
      const ws = new WebSocket(url)
      evState.ws = ws
      ws.onopen = () => {
        evState.retryMs = 1000
        try { ws.send(JSON.stringify({ action: 'subscribe', topic: '*' })) } catch (_) {}
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : '')
          const item = { ts: Date.now(), type: msg.type || 'event', topic: msg.topic || '' }
          evState.list.push(item)
          if (evState.list.length > 100) evState.list.shift()
          evState.lastTs = item.ts
        } catch (_) {}
      }
      ws.onclose = () => {
        evState.ws = null
        if (!evState.closed) {
          if (!evState.reconnectTimer) {
            evState.reconnectTimer = setTimeout(() => { evState.reconnectTimer = null; startEvents() }, evState.retryMs)
          }
          evState.retryMs = Math.min(30000, evState.retryMs * 2)
        }
      }
      ws.onerror = () => { try { ws.close() } catch (_) {} }
    } catch (_) {
      if (!evState.closed && !evState.reconnectTimer) {
        evState.reconnectTimer = setTimeout(() => { evState.reconnectTimer = null; startEvents() }, evState.retryMs)
        evState.retryMs = Math.min(30000, evState.retryMs * 2)
      }
    }
  }

  async function fetchUsage() {
    const cfg = await readConfig()
    const key = cfg.llm_api_key
    const base = cfg.llm_base_url
    let usage = null
    if (key && base) {
      try {
        usage = (await fetchJson(base.replace(/\/v1$/, '') + '/v1/usage', {
          headers: { authorization: `Bearer ${key}` },
        }))?.usage || null
      } catch (_) {
        usage = null
      }
    }
    return { keySet: !!key, base, model: cfg.llm_model, provider: cfg.llm_provider, usage }
  }

  async function saveConfig(patch) {
    try {
      const cfg = await readConfig()
      Object.assign(cfg, patch)
      const tmpFile = CONFIG_PATH + '.tmp-' + process.pid
      await fsp.writeFile(tmpFile, JSON.stringify(cfg, null, 2))
      await fsp.rename(tmpFile, CONFIG_PATH)
      return { ok: true }
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  async function fetchDeepHealth() {
    try {
      const body = await fetchJson(`${PANGU_BASE}/health/deep`)
      const d = body?.data || {}
      const checks = d.checks || {}
      return {
        ok: true,
        status: d.status || '?',
        checks: ['structure', 'memory', 'embedding'].map((k) => ({ name: k, status: checks[k]?.status || 'unknown' })),
      }
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  async function runBackup() {
    try {
      const body = await fetchJson(`${PANGU_BASE}/mcp`, {
        method: 'POST',
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'tools/call',
          params: { name: 'pangu_backup', arguments: { description: 'dsh-dashboard 手动备份' } },
        }),
      })
      const text = body?.result?.content?.[0]?.text
      let parsed = null
      try { parsed = JSON.parse(text) } catch (_) {}
      if (!parsed?.backup_id) return { ok: false, error: '备份未返回结果' }
      return { ok: true, backupId: parsed.backup_id, memories: Number(parsed.memories) || 0, size: Number(parsed.size) || 0 }
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  // ── Dashboard Remote ──
  // 方法返回值即 typert 清单中的 result schema,不再自行包 { ok, value }(网关已包一层)
  const dashboardService = {
    async data() {
      const [stats, usage] = await Promise.all([fetchPanguStats(), fetchUsage()])
      return { stats, usage }
    },
    async ping() {
      return { pong: true }
    },
    async deepHealth() {
      return fetchDeepHealth()
    },
    async backup() {
      return runBackup()
    },
    async events(args) {
      const since = Number(args?.since) || 0
      const events = evState.list.filter((e) => e.ts > since).slice(-20)
      return { count: events.length, lastTs: evState.lastTs, events, connected: !!evState.ws }
    },
    async add(args) {
      const content = String(args?.content || '').trim()
      if (!content) return { ok: false, error: '内容为空' }
      try {
        const body = await fetchJson(`${PANGU_BASE}/mcp`, {
          method: 'POST',
          body: JSON.stringify({
            jsonrpc: '2.0',
            id: 1,
            method: 'tools/call',
            params: {
              name: 'pangu_add_memory',
              arguments: { content, wing: args?.wing || 'default', importance: Number(args?.importance) || 3 },
            },
          }),
        })
        const text = body?.result?.content?.[0]?.text
        let parsed = null
        try { parsed = JSON.parse(text) } catch (_) {}
        if (!parsed?.drawer_id) return { ok: false, error: '服务未返回 drawer_id' }
        return { ok: true, id: parsed.drawer_id, wing: parsed.wing }
      } catch (e) {
        return { ok: false, error: String(e) }
      }
    },
    async injectionStats() {
      try { return { ok: true, stats: statsCollector.query() } }
      catch (e) { return { ok: false, error: String(e) } }
    },
  }
  Object.defineProperty(dashboardService, 'typertRemote', {
    configurable: false, enumerable: false, writable: false,
    value: { service: dashboardService, serviceKey: 'panguDashboard', namespace: 'panguDashboard' },
  })
  ctx.provide('panguDashboard', dashboardService)

  // ── KG Remote ──
  const kgService = {
    async graph() {
      return fetchKG()
    },
  }
  Object.defineProperty(kgService, 'typertRemote', {
    configurable: false, enumerable: false, writable: false,
    value: { service: kgService, serviceKey: 'panguKG', namespace: 'panguKG' },
  })
  ctx.provide('panguKG', kgService)

  // ── Config Remote ──
  const configService = {
    async get() {
      const config = await readConfig()
      return { ok: true, config }
    },
    async save(args) {
      return saveConfig(args?.patch ?? args)
    },
  }
  Object.defineProperty(configService, 'typertRemote', {
    configurable: false, enumerable: false, writable: false,
    value: { service: configService, serviceKey: 'panguConfig', namespace: 'panguConfig' },
  })
  ctx.provide('panguConfig', configService)

  // 实时事件通道(随插件卸载关闭,断线自动重连)
  startEvents()

  // ── 主动记忆注入与主动沉淀（proactive_memory）──
  let currentConfig = { injection: { ...INJECTION_DEFAULTS }, apiKey: '' }
  try { currentConfig = await loadInjectionConfig(ctx.logger) } catch (_) {}

  const messageCache = createMessageCache()
  const statsCollector = createStatsCollector({ logger: ctx.logger, sensitiveFilter: filterSensitive })
  const circuitBreaker = createCircuitBreaker({ onTrip: (sid) => statsCollector.recordCircuitBreak(sid) })
  const dedupTracker = createDedupTracker(currentConfig.injection.dedup_scope)
  const mcpClient = createPanguMcpClient({ apiKey: currentConfig.apiKey, logger: ctx.logger })
  const getConfig = () => currentConfig

  async function extractAssistantText(payload) {
    const agent = payload?.agent
    const snapshot = agent?.session?.snapshotEvents
    if (typeof snapshot !== 'function') return ''
    try {
      const events = await snapshot()
      const msgs = (events || []).filter(e => e.type === 'assistant/message')
      const last = msgs[msgs.length - 1]
      const content = last?.data?.content
      if (Array.isArray(content)) return content.filter(p => p?.type === 'text').map(p => p.text || '').join('')
      if (typeof content === 'string') return content
      return ''
    } catch (_) { return '' }
  }

  const pipeline = createInjectionPipeline({
    getConfig, messageCache, client: mcpClient, circuitBreaker, dedupTracker,
    sensitiveFilter: filterSensitive, statsCollector,
  })
  const consolidationWriter = createConsolidationWriter({
    getConfig, client: mcpClient, sensitiveFilter: filterSensitive, statsCollector,
    getAssistantText: extractAssistantText,
  })

  ctx.on('agent/inbox/claimed', (payload) => { messageCache.handleClaimed(payload) })

  ctx.on('system-prompt/assemble', async (assembly, context, next) => {
    try { await pipeline.run(assembly, context) } catch (_) {}
    return next()
  })

  ctx.on('agent/turn-stopping', async (payload) => {
    try { await consolidationWriter.run(payload) } catch (_) {}
  })

  ctx.on('agent/session-start', async (payload) => {
    try {
      currentConfig = await loadInjectionConfig(ctx.logger)
      const sid = payload?.agent?.session?.id
      if (sid) { circuitBreaker.onSessionStart(sid); dedupTracker.onSessionStart(sid) }
    } catch (_) {}
  })

  ctx.on('agent/disposed', (payload) => {
    try {
      const aid = payload?.agent?.id
      const sid = payload?.agent?.session?.id
      messageCache.delete(aid)
      if (sid) { circuitBreaker.onDisposed(sid); dedupTracker.onDisposed(sid) }
    } catch (_) {}
  })

  ctx.effect(
    () => () => {
      evState.closed = true
      if (evState.reconnectTimer) clearTimeout(evState.reconnectTimer)
      try { evState.ws?.close() } catch (_) {}
      try { messageCache.clear() } catch (_) {}
      try { dedupTracker.clear() } catch (_) {}
      try { circuitBreaker.clear() } catch (_) {}
      try { consolidationWriter.clear() } catch (_) {}
      try { statsCollector.reset() } catch (_) {}
    },
    'pangu-dashboard: remote services',
  )
}

module.exports = { name: 'pangu-dashboard', apply }
module.exports.default = module.exports
