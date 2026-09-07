'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const { detect, jaccard } = require('../../lib/proactive/consolidation-detector')
const { mapWing } = require('../../lib/proactive/consolidation-writer')
const { createInjectionPipeline } = require('../../lib/proactive/injection-pipeline')
const { createMessageCache } = require('../../lib/proactive/message-cache')
const { createCircuitBreaker } = require('../../lib/proactive/circuit-breaker')
const { createDedupTracker } = require('../../lib/proactive/dedup-tracker')
const { filterSensitive } = require('../../lib/proactive/sensitive-filter')
const { createStatsCollector } = require('../../lib/proactive/stats-collector')

test('ConsolidationDetector 根因判定', () => {
  const d = detect('修复了根因：内存泄漏')
  assert.equal(d.shouldWrite, true)
  assert.equal(d.importance, 4)
  assert.deepEqual(d.tags, ['root-cause', 'fix'])
})

test('ConsolidationDetector 结论判定', () => {
  const d = detect('综上决定使用方案A')
  assert.equal(d.shouldWrite, true)
  assert.equal(d.importance, 4)
})

test('ConsolidationDetector 环境事实陈述句', () => {
  const d = detect('服务端口配置为8080')
  assert.equal(d.shouldWrite, true)
  assert.equal(d.tags[0], 'env-fact')
})

test('ConsolidationDetector 环境事实疑问句不沉淀', () => {
  assert.equal(detect('端口配置是多少？').shouldWrite, false)
})

test('ConsolidationDetector 不匹配不沉淀', () => {
  assert.equal(detect('你好世界').shouldWrite, false)
})

test('ConsolidationDetector jaccard相似度', () => {
  assert.equal(jaccard('修复内存泄漏', '修复内存泄漏'), 1)
  assert.equal(jaccard('a b c', 'd e f'), 0)
})

test('mapWing basename与映射', () => {
  assert.ok(mapWing({}))
  assert.equal(mapWing({ [process.cwd()]: 'mapped' }), 'mapped')
})

function setupPipeline(mockClient, cfgOverride) {
  const mc = createMessageCache()
  const cb = createCircuitBreaker()
  const dt = createDedupTracker('session')
  const stats = createStatsCollector()
  const cfg = { injection: { enabled: true, max_memories: 5, token_budget: 500, search_timeout_ms: 2000, ...(cfgOverride || {}) } }
  const pipe = createInjectionPipeline({ getConfig: () => cfg, messageCache: mc, client: mockClient, circuitBreaker: cb, dedupTracker: dt, sensitiveFilter: filterSensitive, statsCollector: stats })
  return { pipe, mc, cb, dt, stats, cfg }
}

test('InjectionPipeline 成功注入', async () => {
  const mockClient = { async call() { return { ok: true, data: { result: { content: [{ text: JSON.stringify({ results: [{ id: 'm1', content: '历史', wing: 'p', tags: ['t'], score: 0.9, importance: 4, created_at: new Date().toISOString() }] }) }] } } } } }
  const { pipe, mc } = setupPipeline(mockClient)
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1', turn: 1 } } })
  assert.equal(assembly.contexts.length, 1)
  assert.equal(assembly.contexts[0].name, 'pangu-memory')
})

test('InjectionPipeline 禁用跳过', async () => {
  const { pipe, mc, cfg } = setupPipeline({ async call() { return { ok: true, data: {} } } })
  cfg.injection.enabled = false
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})

test('InjectionPipeline 空查询跳过', async () => {
  const { pipe } = setupPipeline({ async call() { return { ok: true, data: {} } } })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})

test('InjectionPipeline 检索失败计失败', async () => {
  const mockClient = { async call() { return { ok: false, error: { kind: 'unreachable', message: 'x' } } } }
  const { pipe, mc, stats } = setupPipeline(mockClient)
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  await pipe.run({ contexts: [] }, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(stats.query().failCount, 1)
})

test('InjectionPipeline 零结果不注入', async () => {
  const mockClient = { async call() { return { ok: true, data: { result: { content: [{ text: JSON.stringify({ results: [] }) }] } } } } }
  const { pipe, mc } = setupPipeline(mockClient)
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})

test('InjectionPipeline 熔断后跳过检索', async () => {
  let callCount = 0
  const mockClient = { async call() { callCount++; return { ok: false, error: { kind: 'unreachable', message: 'x' } } } }
  const { pipe, mc, cb } = setupPipeline(mockClient)
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const ctx = { agent: { id: 'a1', session: { id: 's1' } } }
  await pipe.run({ contexts: [] }, ctx)
  await pipe.run({ contexts: [] }, ctx)
  await pipe.run({ contexts: [] }, ctx)
  assert.equal(cb.shouldAllow('s1'), false)
  const before = callCount
  await pipe.run({ contexts: [] }, ctx)
  assert.equal(callCount, before)
})

test('InjectionPipeline 全去重不注入', async () => {
  const mockClient = { async call() { return { ok: true, data: { result: { content: [{ text: JSON.stringify({ results: [{ id: 'm1', content: '历史', wing: 'p', tags: [], score: 0.9, importance: 4, created_at: new Date().toISOString() }] }) }] } } } } }
  const { pipe, mc, dt } = setupPipeline(mockClient)
  dt.markInjected('s1', ['m1'])
  mc.set('a1', { text: '查询', turn: 1, ts: Date.now() })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})