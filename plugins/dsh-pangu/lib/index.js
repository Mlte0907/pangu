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

const crypto = require('crypto')
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
// 密钥不落 config.json（PanguConfig.save() 用 exclude 排除），而是独立存这个文件（0600）。
// 所以判断「Key 是否已配置」必须看这个文件，光读 config.json 会永远显示未配置。
const SECRET_FILE = path.join(os.homedir(), '.pangu', '.llm_api_key')
const HTTP_TIMEOUT_MS = 8000
// OpenCode Go 网关要求每个请求携带稳定的会话标识，缺失会直接 400。
// 与 pangu/core/llm.py 的 httpx 默认头保持一致（同样可用 PANGU_LLM_SESSION_ID 固定），
// 否则「测试连接」会比真实调用更容易失败/更容易成功，失去验证意义。
const LLM_SESSION_ID = process.env.PANGU_LLM_SESSION_ID || crypto.randomBytes(8).toString('hex')

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
  // 敏感字段：读取时脱敏，避免明文 API Key 经过 Typert Remote 流入前端
  // (前端一旦拿到明文就会出现在 React state / devtools / 可能的日志里)。
  const SECRET_KEYS = ['llm_api_key', 'api_key']

  /** 把配置里的密钥替换为「是否已设置」提示，永不返回明文 */
  function redactConfig(cfg) {
    const out = { ...cfg }
    for (const k of SECRET_KEYS) {
      const raw = out[k]
      out[k] = ''
      out[k + '_set'] = typeof raw === 'string' && raw.length > 0
      // 仅在已设置时给出尾部 4 位，便于用户辨认自己填的是哪一把 Key
      out[k + '_hint'] = typeof raw === 'string' && raw.length > 4 ? '****' + raw.slice(-4) : ''
    }
    return out
  }

  // 说明：不需要单独调用 pangu_config_reload —— 该工具**不在服务端默认暴露面内**
  // （默认 28 个工具里只有 pangu_config_get / pangu_config_set），调它会得到
  // code=1002。而 pangu_config_set 自身在落盘后就会失效依赖 config 的缓存组件
  // （见 handle_config_set 的 invalidate_config_dependents），因此保存即生效。

  /**
   * 把配置推给运行中的盘古服务，使其立即生效。
   *
   * 为什么不能只写 config.json：服务端在启动时读一次配置，之后组件
   * （LLMEngine / HybridSearch / WikiEngine）都持有该 config 对象。
   * 直接改文件对已运行的进程没有任何影响。pangu_config_set 会
   * setattr + 落盘 + 丢弃这些组件缓存，是唯一生效的通道。
   */
  async function pushToServer(patch) {
    const applied = []
    const failed = []
    for (const [key, value] of Object.entries(patch || {})) {
      try {
        const body = await fetchJson(`${PANGU_BASE}/mcp`, {
          method: 'POST',
          body: JSON.stringify({
            jsonrpc: '2.0', id: 1, method: 'tools/call',
            params: { name: 'pangu_config_set', arguments: { key, value } },
          }),
        })
        const text = body?.result?.content?.[0]?.text
        const parsed = text ? JSON.parse(text) : null
        if (parsed?.status === 'updated') applied.push(key)
        else failed.push(`${key}: ${parsed?.error || '未知响应'}`)
      } catch (e) {
        failed.push(`${key}: ${e}`)
      }
    }
    return {
      ok: failed.length === 0,
      applied,
      error: failed.length ? failed.join('; ') : undefined,
    }
  }

  /**
   * 读取运行中盘古服务的**生效**配置。
   *
   * config.json 只落盘用户改过的键，embedding_model / palace_path 这类从未写过
   * 的字段不会出现，设置页「只读信息」就会空白。默认值由 Python 侧 PanguConfig
   * 持有，这里经 pangu_config_get 取回，避免把默认值硬编码进插件造成两处漂移。
   * 服务不可达时返回 null，调用方保持原样（仅相应行空白，不报错）。
   */
  async function effectiveConfig() {
    try {
      const body = await fetchJson(`${PANGU_BASE}/mcp`, {
        method: 'POST',
        body: JSON.stringify({
          jsonrpc: '2.0', id: 1, method: 'tools/call',
          params: { name: 'pangu_config_get', arguments: {} },
        }),
      })
      const text = body?.result?.content?.[0]?.text
      const parsed = text ? JSON.parse(text) : null
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch (_) {
      return null
    }
  }

  // 只允许用生效配置**补全**这些只读字段；用户显式写入 config.json 的值优先。
  const READONLY_FALLBACK_KEYS = ['embedding_model', 'palace_path']

  const configService = {
    async get() {
      const config = await readConfig()
      // config.json 不含密钥（见 SECRET_FILE 注释），故单独读密钥文件来判定
      // 「已配置」状态，否则设置页在保存后仍会显示未配置，看起来像没保存成功。
      // 只取尾 4 位用于展示，明文不出本函数。
      if (!config.llm_api_key) {
        try {
          const secret = (await fsp.readFile(SECRET_FILE, 'utf8')).trim()
          if (secret) config.llm_api_key = secret
        } catch (_) { /* 文件不存在 = 未配置 */ }
      }
      const live = await effectiveConfig()
      if (live) {
        for (const key of READONLY_FALLBACK_KEYS) {
          if (config[key] === undefined || config[key] === '') config[key] = live[key]
        }
      }
      return { ok: true, config: redactConfig(config) }
    },
    async save(args) {
      const patch = args?.patch ?? args
      // 空字符串代表「不修改」（前端不会拿到明文，无法回填原值）；
      // 若要真正清空密钥，前端需显式传 null。
      const clean = {}
      for (const [k, v] of Object.entries(patch || {})) {
        if (SECRET_KEYS.includes(k)) {
          if (v === null) clean[k] = ''
          else if (typeof v === 'string' && v.length > 0) clean[k] = v
          // undefined / '' → 跳过，保持原值
        } else {
          clean[k] = v
        }
      }
      const res = await saveConfig(clean)
      // saveConfig 直接改 ~/.pangu/config.json，但**运行中的服务不会自动感知**；
      // 必须经 pangu_config_set 让服务端重读并失效旧组件缓存。
      if (res.ok) res.reload = await pushToServer(clean)
      return res
    },
    async testLlm() {
      // 用当前已落盘配置直接打一次 LLM 端点，验证 provider/base_url/model/key
      // 这个组合真的可用。不经过盘古的 LLM 工具（那些是缓存管理类，且默认
      // 未暴露），而是复刻 LLMEngine._call_openai_compatible 的最小请求。
      const cfg = await readConfig()
      const started = Date.now()
      const PROVIDER_URLS = {
        openai: 'https://api.openai.com/v1',
        openrouter: 'https://openrouter.ai/api/v1',
        deepseek: 'https://api.deepseek.com/v1',
        zhipu: 'https://open.bigmodel.cn/api/paas/v4',
        qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        ollama: 'http://localhost:11434/v1',
        anthropic: 'https://api.anthropic.com/v1',
      }
      const provider = String(cfg.llm_provider || 'openai').toLowerCase()
      const base = String(cfg.llm_base_url || PROVIDER_URLS[provider] || '').replace(/\/+$/, '')
      const key = String(cfg.llm_api_key || '')
      const model = String(cfg.llm_model || '')

      if (!base) return { ok: false, ms: 0, error: `未知 provider「${provider}」，请填写 Base URL` }
      if (!model) return { ok: false, ms: 0, error: '未填写模型名' }
      if (!key && provider !== 'ollama') {
        return { ok: false, ms: 0, error: '未填写 API Key（Ollama 等本地端点可留空）' }
      }

      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 20000)
        const res = await fetch(`${base}/chat/completions`, {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'x-opencode-session': LLM_SESSION_ID,
            ...(key ? { authorization: `Bearer ${key}` } : {}),
          },
          body: JSON.stringify({
            model,
            messages: [{ role: 'user', content: '回复两个字：可用' }],
            max_tokens: 16,
            temperature: 0,
          }),
          signal: ctrl.signal,
        }).finally(() => clearTimeout(timer))

        const raw = await res.text()
        const ms = Date.now() - started
        let data = null
        try { data = JSON.parse(raw) } catch (_) {}
        if (!res.ok) {
          const msg = data?.error?.message || data?.message || raw.slice(0, 200)
          return { ok: false, ms, status: res.status, model, provider, baseUrl: base, error: `HTTP ${res.status}: ${msg}` }
        }
        // 部分推理模型（minimax-m3 等）把思考过程内联在 content 里；探测结果只需要
        // 可见回复，剥掉 <think>…</think>（含被 max_tokens 截断而未闭合的情况）。
        const sample = String(data?.choices?.[0]?.message?.content || '')
          .replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, '')
          .trim()
        return { ok: true, ms, status: res.status, model, provider, baseUrl: base, sample: sample.slice(0, 120) }
      } catch (e) {
        const ms = Date.now() - started
        const hint = e?.name === 'AbortError' ? '请求超时(20s)，请检查 Base URL 是否可达' : String(e)
        return { ok: false, ms, model, provider, baseUrl: base, error: hint }
      }
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
