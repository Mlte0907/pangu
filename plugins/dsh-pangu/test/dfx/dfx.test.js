'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const { createMessageCache } = require('../../lib/proactive/message-cache')
const { createInjectionPipeline } = require('../../lib/proactive/injection-pipeline')
const { createCircuitBreaker } = require('../../lib/proactive/circuit-breaker')
const { createDedupTracker } = require('../../lib/proactive/dedup-tracker')
const { createStatsCollector } = require('../../lib/proactive/stats-collector')
const { filterSensitive } = require('../../lib/proactive/sensitive-filter')
const { validateInjectionConfig } = require('../../lib/proactive/config')

test('DFX性能：注入P95≤500ms（100轮）', async () => {
  const mc = createMessageCache()
  const cb = createCircuitBreaker()
  const dt = createDedupTracker('session')
  const stats = createStatsCollector()
  const client = { async call() { return { ok: true, data: { result: { content: [{ text: JSON.stringify({ results: [{ id: 'm1', content: '历史', wing: 'p', tags: [], score: 0.9, importance: 4, created_at: new Date().toISOString() }] }) }] } } } } }
  const pipe = createInjectionPipeline({ getConfig: () => ({ injection: { enabled: true, max_memories: 5, token_budget: 500, search_timeout_ms: 2000 } }), messageCache: mc, client, circuitBreaker: cb, dedupTracker: dt, sensitiveFilter: filterSensitive, statsCollector: stats })
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const ctx = { agent: { id: 'a1', session: { id: 's1', turn: 1 } } }
  const latencies = []
  for (let i = 0; i < 100; i++) {
    const t0 = Date.now()
    await pipe.run({ contexts: [] }, ctx)
    latencies.push(Date.now() - t0)
  }
  latencies.sort((a, b) => a - b)
  const p95 = latencies[Math.floor(latencies.length * 0.95)]
  assert.ok(p95 <= 500, 'P95=' + p95)
})

test('DFX安全：敏感信息过滤零泄露', () => {
  const secret = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'
  const out = filterSensitive('token: ' + secret)
  assert.ok(!out.includes(secret))
})

test('DFX兼容：旧配置无injection段按默认值运行', () => {
  const { injection } = validateInjectionConfig({ api_key: 'k' }, { warn() {} })
  assert.equal(injection.enabled, true)
  assert.equal(injection.max_memories, 5)
  assert.equal(injection.token_budget, 500)
})

test('DFX兼容：非法配置回退默认值', () => {
  const { injection } = validateInjectionConfig({ injection: { token_budget: 0, max_memories: 999 } }, { warn() {} })
  assert.equal(injection.token_budget, 500)
  assert.equal(injection.max_memories, 5)
})