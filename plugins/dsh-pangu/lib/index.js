/**
 * pangu-dashboard 宿主插件 v5。
 * 提供:
 *  1. panguDashboard Typert Remote — 面板数据/深度健康/备份/实时事件/快速添加记忆
 *  2. panguKG Typert Remote — 知识图谱节点与关系
 *  3. panguConfig Typert Remote — 记忆系统配置读写
 *  4. panguAdminKeys Typert Remote — 钥匙/房间管理
 *  5. panguPlatforms Typert Remote — 平台Token管理
 *  6. panguKnowledge Typert Remote — 知识库浏览
 * v5: 架构 v2.1 重构——新增平台Token管理、知识库浏览、记忆快照、来源分布。
 * v4: 新增 /ws 实时事件监听(断线指数退避重连)供客户端事件驱动刷新;
 *     新增 pangu_add_memory 快速添加;图谱拉取放宽到 limit=400。
 */
'use strict'

const crypto = require('crypto')
const fsp = require('fs/promises')
const os = require('os')
const path = require('path')

const { createMessageCache } = require('./proactive/message-cache')
const { loadInjectionConfig, readStoredApiKey, DEFAULTS: INJECTION_DEFAULTS } = require('./proactive/config')
const { createPanguMcpClient } = require('./proactive/mcp-client')
const { createCircuitBreaker } = require('./proactive/circuit-breaker')
const { createDedupTracker } = require('./proactive/dedup-tracker')
const { createStatsCollector } = require('./proactive/stats-collector')
const { filterSensitive } = require('./proactive/sensitive-filter')
const { createInjectionPipeline } = require('./proactive/injection-pipeline')
const { createConsolidationWriter } = require('./proactive/consolidation-writer')

const PLUGIN_VERSION = require('../package.json').version
const CONFIG_PATH = path.join(os.homedir(), '.pangu', 'config.json')
// 密钥不落 config.json（PanguConfig.save() 用 exclude 排除），而是独立存这个文件（0600）。
// 所以判断「Key 是否已配置」必须看这个文件，光读 config.json 会永远显示未配置。
const SECRET_FILE = path.join(os.homedir(), '.pangu', '.llm_api_key')
const HTTP_TIMEOUT_MS = 8000

// ── 目标地址解析（2026-09-21 盘古多部署形态）──
// 解析优先级：~/.pangu/config.json 的 pangu_base_url > 环境变量 PANGU_BASE_URL
// > 默认本地 http://127.0.0.1:19529（盘古标准本机部署）。部署在云端/局域网的
// 用户在设置页填自己的地址即可。仅允许 http/https；host 不做公网限制 ——
// 本机/局域网部署是合法形态（单人系统，无 SSRF 威胁模型）。
const DEFAULT_PANGU_BASE = 'http://127.0.0.1:19529'

function resolvePanguBase() {
  let candidate = ''
  try {
    const raw = JSON.parse(require('fs').readFileSync(CONFIG_PATH, 'utf8'))
    candidate = String((raw && raw.pangu_base_url) || '').trim()
  } catch (_) {}
  if (!candidate) candidate = String(process.env.PANGU_BASE_URL || '').trim()
  if (!candidate) candidate = DEFAULT_PANGU_BASE
  try {
    const u = new URL(candidate)
    if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('仅允许 http/https')
    return candidate.replace(/\/+$/, '')
  } catch (e) {
    console.error(`[dsh-pangu] pangu_base_url 非法（${candidate}）：${e.message}，回退默认 ${DEFAULT_PANGU_BASE}`)
    return DEFAULT_PANGU_BASE
  }
}

// let 而非 const：设置页保存 pangu_base_url 后热切换（resolvePanguBase 重读），
// 全部调用点用模板字符串引用，取值时才求值，无需重启即对 REST/WS 生效。
let PANGU_BASE = resolvePanguBase()
// OpenCode Go 网关要求每个请求携带稳定的会话标识，缺失会直接 400。
// 与 pangu/core/llm.py 的 httpx 默认头保持一致（同样可用 PANGU_LLM_SESSION_ID 固定），
// 否则「测试连接」会比真实调用更容易失败/更容易成功，失去验证意义。
const LLM_SESSION_ID = process.env.PANGU_LLM_SESSION_ID || crypto.randomBytes(8).toString('hex')

/**
 * 把一个普通服务对象绑定到 Typert Remote 网关。
 *
 * 网关的 validateBinding 要求服务对象上存在可见的 typertRemote 绑定
 * （形如 { service, serviceKey, namespace }）；缺了它，该命名空间下**每个**
 * 端点都会以 `gateway/binding-invalid: Service "X" has no visible typertRemote
 * binding` 失败。
 *
 * 特别注意：lib/typert.host.js 清单只声明端点描述符，**不会**替你装这个绑定 ——
 * 清单经 typert loader 注册进 registry，加载器全程不接触服务对象。
 * 因此即使清单完整，也必须在这里逐服务挂绑定。
 */
function bindRemote(service, serviceKey, namespace = serviceKey) {
  Object.defineProperty(service, 'typertRemote', {
    configurable: false, enumerable: false, writable: false,
    value: { service, serviceKey, namespace },
  })
  return service
}

async function apply(ctx) {
  async function fetchJson(url, options = {}) {
    const headers = { 'content-type': 'application/json', ...(options.headers || {}) }
    // 身份凭据挂所有发往盘古本机的请求（/mcp、/health、/api/v2/graph 等 —— REST
    // 网关已接入钥匙体系）。fetchJson 也会被 /v1/usage 复用，但那是以 LLM 供应商
    // 的 base_url 开头的外部端点 —— 把 pgk_* 钥匙发过去等于主动外泄，所以按
    // URL 前缀判定，而不是无差别加头。
    if (url.startsWith(PANGU_BASE)) {
      const key = readStoredApiKey()
      if (key) headers['x-api-key'] = key
    }
    const res = await fetch(url, {
      method: options.method || 'GET',
      headers,
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

  // P0-1 热修：统一 LLM Key 读取路径
  // configService.get() 有 SECRET_FILE 回退，但 fetchUsage/testConnection 没有
  // → 它们永远读到空，导致"未配置"误报。抽公共 helper 解决。
  function resolveLlmApiKey(cfg) {
    if (cfg.llm_api_key) return cfg.llm_api_key
    try {
      const secret = require('fs').readFileSync(SECRET_FILE, 'utf8').trim()
      if (secret) return secret
    } catch (_) { /* 文件不存在 = 未配置 */ }
    return ''
  }

  async function fetchPanguStats() {
    let total = 0
    let wings = 0
    let rooms = 0
    let kgEntities = 0
    let kgRelations = 0
    let byWing
    let byClass
    let pipeline
    let parsed = null
    try {
      // 面板是管理 UI：概览要显示**全库**规模（用户 2026-09-16 定），所以走 admin 通道
      // 的 /admin/stats —— MCP 的 pangu_stats 自 P1-3 收口后按调用方租户裁剪，只显示
      // 本租户那一份，不适合当"全库看板"。admin secret 只在插件后端读取，前端不接触。
      // admin 不可用时回退到 /mcp（退化为本租户视角，面板仍然可用）。
      parsed = null
      const adminStats = await adminFetch(`${PANGU_BASE}/api/v2/admin/stats`)
      if (adminStats && !adminStats.error && (adminStats.memory || adminStats.palace)) {
        parsed = adminStats
      } else {
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
        try { parsed = JSON.parse(text) } catch (_) {}
        if (!parsed) {
          total = Number((text.match(/"total_memories".{0,3}[: ]+([0-9]+)/) || [])[1]) || 0
          wings = Number((text.match(/"wings_count".{0,3}[: ]+([0-9]+)/) || [])[1]) || 0
        }
      }
      if (parsed) {
        total = Number(parsed?.memory?.total_memories) || 0
        wings = Number(parsed?.palace?.wings_count) || 0
        rooms = Number(parsed?.palace?.rooms_count) || 0
        kgEntities = Number(parsed?.knowledge_graph?.entities) || 0
        kgRelations = Number(parsed?.knowledge_graph?.relations) || 0
        byWing = parsed?.memory?.by_wing
        byClass = parsed?.classification
        pipeline = parsed?.pipeline
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

    // 高密级＝classification>=2（机密/绝密）。管理视角看全库，租户视角看自己那份。
    const highClass = byClass
      ? Number(byClass['2'] || 0) + Number(byClass['3'] || 0)
      : 0

    // 活跃平台数（2026-09-20 补）：侧边栏「平台接入」此前错用 bySource 的键数
    // （记忆来源类型），与真实注册平台数对不上。
    let platformsCount = null
    try {
      const pl = await adminFetch(`${PANGU_BASE}/api/v2/platforms`)
      platformsCount = Array.isArray(pl?.platforms)
        ? pl.platforms.filter((p) => p.status === 'active').length
        : null
    } catch (_) {}

    // 7 日记忆脉搏：按 created_at 聚合最近 7 天的创建数（供前端 sparkline）
    let dailyCounts = []
    try {
      const palacePath = parsed?.memory?.palace_path
      if (palacePath) {
        const drawers = JSON.parse(require('fs').readFileSync(require('path').join(palacePath, 'drawers.json'), 'utf8'))
        const now = new Date()
        const counts = {}
        for (let i = 6; i >= 0; i--) {
          const d = new Date(now); d.setDate(d.getDate() - i)
          counts[d.toISOString().slice(0, 10)] = 0
        }
        for (const m of drawers) {
          const dt = (m.created_at || '').slice(0, 10)
          if (counts[dt] !== undefined) counts[dt]++
        }
        dailyCounts = Object.entries(counts).map(([date, count]) => ({ date, count }))
      }
    } catch (_) {}

    // 7 日召回序列（插件侧采集，见 bumpRecallDaily）—— 与 dailyCounts 配对画双序列脉搏图
    let dailyRecalls = []
    try {
      const data = readRecallDaily()
      const now = new Date()
      for (let i = 6; i >= 0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        const key = d.toISOString().slice(0, 10)
        dailyRecalls.push({ date: key, count: Number(data[key]) || 0 })
      }
    } catch (_) {}

    // 知识库和快照统计（从 dashboard/stats 获取）
    let knowledge = { total: 0, categories: {} }
    let snapshots = { total: 0 }
    let bySource = {}
    try {
      const dashStats = await adminFetch(`${PANGU_BASE}/api/v2/dashboard/stats`)
      if (dashStats && !dashStats.error) {
        knowledge = dashStats.knowledge || knowledge
        snapshots = dashStats.snapshots || snapshots
        bySource = dashStats.memories?.by_source || {}
      }
    } catch (_) {}

    return { ok: true, total, wings, rooms, kgEntities, kgRelations, byWing, byClass, pipeline, highClass, health, healthScore, version, uptimeSeconds, dailyCounts, dailyRecalls, knowledge, snapshots, bySource, platformsCount, ts: Date.now() }
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

  // 本地真实版本：插件读自己的 package.json，盘古服务读 /health 自报版本。
  // 设置页「关于与更新」用它显示本地版本 —— 原先那里是写死的字符串，会与实际不符。
  async function localVersions() {
    const versions = { plugin: PLUGIN_VERSION }
    try {
      const hd = await fetchJson(`${PANGU_BASE}/health`)
      const v = hd?.data?.version
      if (v) versions.server = String(v)
    } catch (_) { /* 服务不可达时只显示插件版本 */ }
    return versions
  }

  // ── 实时事件:连 pangu /ws(SEC-004 修复后需 api_key/JWT),断线指数退避重连 ──
  // ── 召回日计数（7 日脉搏的「召回」序列）──
  // 为什么从插件侧采集：盘古只存每条记忆的 access_count 累计值，没有"哪一天召回了几次"的
  // 历史（~/.pangu/events 也是空的）。而设计稿的脉搏是「创建柱 + 召回折线」双序列，
  // 所以这里接 /ws 的 memory_recall 事件按天累加，落 30 天滚动 JSON —— 7 天后自然完整。
  const RECALL_DAILY_FILE = require('path').join(
    require('os').homedir(), '.dsh', 'storages', 'pangu-recall-daily.json',
  )

  function bumpRecallDaily() {
    try {
      const today = new Date().toISOString().slice(0, 10)
      let data = {}
      try { data = JSON.parse(require('fs').readFileSync(RECALL_DAILY_FILE, 'utf8')) } catch (_) {}
      data[today] = (Number(data[today]) || 0) + 1
      const keep = {}
      for (const k of Object.keys(data).sort().slice(-30)) keep[k] = data[k]
      require('fs').mkdirSync(require('path').dirname(RECALL_DAILY_FILE), { recursive: true })
      require('fs').writeFileSync(RECALL_DAILY_FILE, JSON.stringify(keep), 'utf8')
    } catch (_) {}
  }

  function readRecallDaily() {
    try { return JSON.parse(require('fs').readFileSync(RECALL_DAILY_FILE, 'utf8')) } catch (_) { return {} }
  }

  const evState = { list: [], lastTs: 0, ws: null, retryMs: 1000, closed: false, reconnectTimer: null }

  async function startEvents() {
    if (evState.ws) return
    let token = ''
    try {
      // 与 MCP headers / fetchJson 同源：只认设置页填写的 config.json.api_key。
      // 为空则不带 token 握手，服务端会拒绝 —— 这是预期行为，提示用户去设置页
      // 填「盘古凭据」即可（不再隐式回落 ~/.pangu/.mcp_key，避免地址/凭据错配）。
      token = (await readConfig()).api_key || ''
    } catch (_) {}
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
          // 召回计数（7 日脉搏的召回序列）
          if (item.type === 'memory_recall') bumpRecallDaily()
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
    const key = resolveLlmApiKey(cfg)
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
              // importance 走 0.0–1.0 契约（remember() 的校验），旧值 3 属 1–5 量纲
              arguments: { content, wing: args?.wing || 'default', importance: Number(args?.importance) || 0.5 },
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

    async checkUpdate() {
      try {
        const proxy = 'https://gh-proxy.org/'
        const api = 'https://api.github.com/repos/Mlte0907/pangu/releases/latest'
        const res = await fetch(proxy + api, { signal: AbortSignal.timeout(10000) })
        if (!res.ok) return { ok: false, error: 'GitHub API ' + res.status }
        const data = await res.json()
        const asset = (data.assets || [])[0] || null
        return {
          ok: true,
          tag: data.tag_name || '',
          name: data.name || data.tag_name || '',
          publishedAt: data.published_at || '',
          body: (data.body || '').slice(0, 800),
          size: asset ? asset.size : 0,
          downloadUrl: asset ? asset.browser_download_url : null,
        }
      } catch (e) {
        return { ok: false, error: String(e.message || e) }
      }
    },
    async injectionStats() {
      try { return { ok: true, stats: statsCollector.query() } }
      catch (e) { return { ok: false, error: String(e) } }
    },
  }
  // 绑定必须逐服务挂：清单只声明端点描述符，加载器不会碰服务对象（见 bindRemote 注释）
  ctx.provide('panguDashboard', bindRemote(dashboardService, 'panguDashboard'))

  // ── KG Remote ──
  const kgService = {
    async graph() {
      return fetchKG()
    },
  }
  ctx.provide('panguKG', bindRemote(kgService, 'panguKG'))

  // ── Config Remote ──
  // 敏感字段：读取时脱敏，避免明文 API Key 经过 Typert Remote 流入前端
  // (前端一旦拿到明文就会出现在 React state / devtools / 可能的日志里)。
  const SECRET_KEYS = ['llm_api_key', 'api_key', 'admin_secret']

  /**
   * 密钥短于这个长度就不给任何掩码 —— 6+4=10 个可见字符对短密钥等于泄漏一半。
   * 盘古凭据（pgk_ 主密钥 43 位 / pgp_ 平台令牌 65 位）远超此线。
   */
  const HINT_MIN_LEN = 20

  /** 把配置里的密钥替换为「是否已设置」提示，永不返回明文 */
  function redactConfig(cfg) {
    const out = { ...cfg }
    for (const k of SECRET_KEYS) {
      const raw = out[k]
      out[k] = ''
      out[k + '_set'] = typeof raw === 'string' && raw.length > 0
      // 掩码形如 `pgk_J_*****kXq8`：前缀 6 位 + ***** + 尾 4 位（2026-09-21）。
      // 原先只有 `****kXq8`（尾 4 位）—— 用户看到"已配置"却认不出是哪一把，
      // 尤其 pgk_ 主密钥与 pgp_ 平台令牌混用时完全无从分辨；前缀还能看出凭据类型。
      out[k + '_hint'] = typeof raw === 'string' && raw.length >= HINT_MIN_LEN
        ? raw.slice(0, 6) + '*****' + raw.slice(-4)
        : ''
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

  // config.json 只落盘用户改过的键，这些键的**权威值在服务端**（没写过时由
  // PanguConfig 的默认值决定）。本地没写就用生效值补全，否则设置页会显示成
  // 与服务端不一致 —— whisper 尤其明显：本地没写 ≠ 开启，服务端默认才作准。
  // 用户显式写入 config.json 的值优先。
  const READONLY_FALLBACK_KEYS = [
    'embedding_model',
    'palace_path',
    'whisper_enabled',
    'whisper_model',
    'multimodal_enabled',
    // 暴露面：多模态开关要基于**服务端现值**增删 'multimodal'，取不到就不能改 ——
    // 否则凭空构造一份 exposure 会把服务端已有的 enabled_optional_modules
    // （analytics / knowledge …）一并冲掉（2026-09-21）。
    'exposure',
  ]

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
      // admin_secret 不自动读本机文件：管理面直接复用「盘古凭据」
      // （见 readAdminSecret —— admin_secret || api_key）
      const live = await effectiveConfig()
      if (live) {
        for (const key of READONLY_FALLBACK_KEYS) {
          if (config[key] === undefined || config[key] === '') config[key] = live[key]
        }
      }
      return { ok: true, config: redactConfig(config), versions: await localVersions() }
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
      // pangu_base_url（插件目标地址，2026-09-21）：写盘前校验（仅 http/https），
      // 保存成功后热切换 PANGU_BASE —— 设置页改地址即生效，无需重启。
      // 此键是插件本地设置（MCP 客户端 cordis.patch.yml 也读它），不推给盘古服务。
      if (clean.pangu_base_url !== undefined) {
        const candidate = String(clean.pangu_base_url || '').trim()
        let bad = null
        if (candidate === '') {
          clean.pangu_base_url = '' // 留空 = 回退默认本地
        } else {
          try {
            const u = new URL(candidate)
            if (u.protocol !== 'http:' && u.protocol !== 'https:') bad = '仅允许 http/https'
          } catch (_) { bad = '不是合法 URL' }
          if (bad) return { ok: false, error: `盘古服务地址无效：${bad}` }
        }
      }
      const res = await saveConfig(clean)
      if (res.ok) {
        if (clean.pangu_base_url !== undefined) PANGU_BASE = resolvePanguBase()
        const serverPatch = { ...clean }
        // 以下三类是「插件本地设置」，不推给盘古服务：
        //  · pangu_base_url —— 插件的目标地址，服务端根本没有这个键；
        //  · api_key / admin_secret —— 服务端 handle_config_set 把二者列为受保护
        //    字段并直接拒绝（"该配置项受保护，禁止远程修改"）。推过去必然让设置页
        //    弹出一句假的"服务端热加载失败"，看起来像保存没生效。
        //    它们的用途只是「插件 → 服务端」的认证，留在 config.json 即可。
        delete serverPatch.pangu_base_url
        delete serverPatch.api_key
        delete serverPatch.admin_secret
        // saveConfig 直接改 ~/.pangu/config.json，但**运行中的服务不会自动感知**；
        // 必须经 pangu_config_set 让服务端重读并失效旧组件缓存。
        res.reload = await pushToServer(serverPatch)
      }
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
      const key = resolveLlmApiKey(cfg)
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
            // 推理模型会把整段思考也计入 completion，16 tokens 时常见的结局是
            // 「思考没写完、答案还没开始」（实测 MiniCPM5-2B 即如此）。给到 64
            // 让思考收尾并吐出答案，探测成本仍然可忽略。
            max_tokens: 64,
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
        // 推理模型会把思考过程内联在 content 里，探测结果只需要可见回复。两种形态：
        //   1. 成对标签（minimax-m3 等）：`<think>思考</think>\n\n答案`，被 max_tokens
        //      截断时没有闭合标签；
        //   2. 只带闭合标签（MiniCPM5-2B 经 AMD 网关实测）：`思考…\n</think>\n\n答案`，
        //      开头标签被模板吃掉了。
        // 先剥成对标签，再剥「到最后一个 </think> 为止」的前缀；仍为空说明整段都是
        // 被截断的思考，此时不展示 sample（前端已处理空 sample）。
        const sample = String(data?.choices?.[0]?.message?.content || '')
          .replace(/<think>[\s\S]*?(?:<\/think>|$)/gi, '')
          .replace(/^[\s\S]*<\/think>\s*/i, '')
          .trim()
        return { ok: true, ms, status: res.status, model, provider, baseUrl: base, sample: sample.slice(0, 120) }
      } catch (e) {
        const ms = Date.now() - started
        const hint = e?.name === 'AbortError' ? '请求超时(20s)，请检查 Base URL 是否可达' : String(e)
        return { ok: false, ms, model, provider, baseUrl: base, error: hint }
      }
    },
  }
  ctx.provide('panguConfig', bindRemote(configService, 'panguConfig'))

  // ── 阶段 5：Admin Key Service（钥匙/房间管理）──
  // 管理凭据来源：config.json 的 admin_secret → **缺省则复用「盘古凭据」**。
  //
  // 为什么可以复用：install.sh 自 2026-09-21 起让 ~/.pangu/.api_key 与
  // ~/.pangu/.admin_secret **取同一个值**（服务端仍是两套独立校验 ——
  // 数据面 X-API-Key、管理面 X-Admin-Key，只是安装期的取值策略统一了）。
  // 于是设置页只需填一处「盘古凭据」，管理面一并可用，少一个出错点。
  //
  // admin_secret 只可能来自**老部署或手工写入 config.json**（设置页已无此字段）。
  // 这类部署若两把不同，复用会带上不匹配的 X-Admin-Key → 服务端 401；
  // 失败经 adminFetch 显式上报，并提示"在服务端统一两把"，不再静默空白。
  async function readAdminSecret() {
    const cfg = await readConfig()
    return cfg.admin_secret || cfg.api_key || ''
  }
  async function adminFetch(url, options = {}) {
    const secret = await readAdminSecret()
    if (!secret) {
      return {
        ok: false,
        error:
          '未配置管理凭据：请在 DSH 设置 →「盘古记忆系统」填入「盘古凭据」'
          + '（安装横幅的「DSH 填写卡」里有；新装默认它与管理密钥是同一把）。',
      }
    }
    const res = await fetch(url, {
      ...options,
      headers: { 'X-Admin-Key': secret, 'content-type': 'application/json', ...(options.headers || {}) },
    })
    // ⚠ 鉴权失败必须显式上报（2026-09-21 修）：此前不看状态码、一律 res.json()，
    // 于是 401 的响应体被当成"正常数据" ⇒ 管理区又是一片静默空白。
    if (res.status === 401 || res.status === 403) {
      return {
        ok: false,
        error:
          `管理接口鉴权失败（HTTP ${res.status}）：当前「盘古凭据」不被管理面接受。`
          + '正常情况两边同值（安装脚本保证）。若这台服务端是早期部署、'
          + '~/.pangu/.admin_secret 与 REST 主密钥不同，'
          + '在服务端把 .admin_secret 改成与「盘古凭据」相同的值即可（或重跑 install.sh）。',
      }
    }
    return res.json()
  }
  const adminKeyService = {
    async listKeys() { return adminFetch(`${PANGU_BASE}/api/v2/admin/keys`) },
    async createKey(args) { return adminFetch(`${PANGU_BASE}/api/v2/admin/keys`, { method: 'POST', body: JSON.stringify(args) }) },
    async revokeKey(args) { return adminFetch(`${PANGU_BASE}/api/v2/admin/keys/revoke`, { method: 'POST', body: JSON.stringify(args) }) },
    async listRooms() { return adminFetch(`${PANGU_BASE}/api/v2/admin/rooms`) },
    async rekeyRoom(args) { return adminFetch(`${PANGU_BASE}/api/v2/admin/rooms/` + encodeURIComponent(args.room) + '/rekey', { method: 'POST' }) },
    async listPublicMemories() { return adminFetch(`${PANGU_BASE}/api/v2/admin/public-memories`) },
    async listRecentMemories() { return adminFetch(`${PANGU_BASE}/api/v2/admin/recent-memories?limit=20`) },
  }
  ctx.provide('panguAdminKeys', bindRemote(adminKeyService, 'panguAdminKeys'))

  // ── 平台管理服务 ──
  const platformService = {
    async listPlatforms() { return adminFetch(`${PANGU_BASE}/api/v2/platforms`) },
    async listPending() { return adminFetch(`${PANGU_BASE}/api/v2/platforms/pending`) },
    async approve(args) { return adminFetch(`${PANGU_BASE}/api/v2/platforms/approve`, { method: 'POST', body: JSON.stringify(args) }) },
    // 2026-09-20 修：后端只有 `POST /platforms/reject`（body 传 token_id）与
    // `DELETE /platforms/{token_id}`；此前写的是 `POST /platforms/{id}/reject|revoke`，
    // 实际 404，而前端 `catch(_){}` 把错误吞掉 ⇒ 点击「拒绝/撤销」没有任何反应。
    async reject(args) { return adminFetch(`${PANGU_BASE}/api/v2/platforms/reject`, { method: 'POST', body: JSON.stringify({ token_id: args && args.token_id }) }) },
    async revoke(args) { return adminFetch(`${PANGU_BASE}/api/v2/platforms/` + encodeURIComponent(args.token_id), { method: 'DELETE' }) },
  }
  ctx.provide('panguPlatforms', bindRemote(platformService, 'panguPlatforms'))

  // ── 知识库服务 ──
  const knowledgeService = {
    async list(args) {
      const q = args && args.category ? '?category=' + encodeURIComponent(args.category) : ''
      return adminFetch(`${PANGU_BASE}/api/v2/dashboard/knowledge` + q)
    },
    async search(args) {
      const q = args && args.query ? '?query=' + encodeURIComponent(args.query) : ''
      return adminFetch(`${PANGU_BASE}/api/v2/dashboard/knowledge/search` + q)
    },
    async get(args) {
      // 知识条目详情：通过 list + filter 实现（后端无单条 API）
      const all = await adminFetch(`${PANGU_BASE}/api/v2/dashboard/knowledge`)
      const entries = all?.knowledge || []
      const entry = entries.find(e => e.id === args.id)
      return entry || null
    },
    async stats() {
      const stats = await adminFetch(`${PANGU_BASE}/api/v2/dashboard/stats`)
      return {
        total: stats?.knowledge?.total || 0,
        categories: stats?.knowledge?.categories || {},
      }
    },
  }
  ctx.provide('panguKnowledge', bindRemote(knowledgeService, 'panguKnowledge'))

  // 实时事件通道(随插件卸载关闭,断线自动重连)
  startEvents()

  // ── 主动记忆注入与主动沉淀（proactive_memory）──
  let currentConfig = { injection: { ...INJECTION_DEFAULTS }, apiKey: '' }
  try { currentConfig = await loadInjectionConfig(ctx.logger) } catch (_) {}

  const messageCache = createMessageCache()
  const statsCollector = createStatsCollector({ logger: ctx.logger, sensitiveFilter: filterSensitive })
  const circuitBreaker = createCircuitBreaker({ onTrip: (sid) => statsCollector.recordCircuitBreak(sid) })
  const dedupTracker = createDedupTracker(currentConfig.injection.dedup_scope)
  const mcpClient = createPanguMcpClient({ apiKey: currentConfig.apiKey, baseUrl: currentConfig.baseUrl, logger: ctx.logger })
  const getConfig = () => currentConfig

  async function extractAssistantText(payload) {
    const agent = payload?.agent
    // DSH 0.1.5+ 弃用 snapshotEvents，改用 ownEvents；更早版本只有 snapshotEvents
    const sess = agent?.session
    const snapshot = typeof sess?.snapshotEvents === 'function'
      ? sess.snapshotEvents
      : typeof sess?.ownEvents === 'function'
        ? sess.ownEvents
        : null
    if (!snapshot) return ''
    try {
      const events = await snapshot.call(sess)
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

  // 双事件注册：旧基线(≤0.1.4)只有 session-start，新基线(≥0.1.5)只有 agent/created
  // 处理器本身按会话重置状态、天然幂等，保留两者确保前后兼容
  const onSessionCreated = async (payload) => {
    try {
      currentConfig = await loadInjectionConfig(ctx.logger)
      const sid = payload?.agent?.session?.id
      if (sid) { circuitBreaker.onSessionStart(sid); dedupTracker.onSessionStart(sid) }
    } catch (_) {}
  }
  ctx.on('agent/session-start', onSessionCreated)
  ctx.on('agent/created', onSessionCreated)

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
