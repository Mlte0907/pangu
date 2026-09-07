'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const { createMessageCache } = require('../../lib/proactive/message-cache')
const { createInjectionPipeline } = require('../../lib/proactive/injection-pipeline')
const { createCircuitBreaker } = require('../../lib/proactive/circuit-breaker')
const { createDedupTracker } = require('../../lib/proactive/dedup-tracker')
const { createStatsCollector } = require('../../lib/proactive/stats-collector')
const { filterSensitive } = require('../../lib/proactive/sensitive-filter')
const { createConsolidationWriter } = require('../../lib/proactive/consolidation-writer')

function mockPanguClient(results) {
  return {
    async call(tool, args) {
      if (tool === 'pangu_search_memories') {
        return { ok: true, data: { result: { content: [{ text: JSON.stringify({ results: results || [] }) }] } } }
      }
      if (tool === 'pangu_add_memory') {
        return { ok: true, data: { result: { content: [{ text: JSON.stringify({ drawer_id: 'new-' + Date.now(), wing: args.wing }) }] } } }
      }
      return { ok: false, error: { kind: 'unknown', message: 'no mock' } }
    },
  }
}

function setup(client, cfg) {
  const mc = createMessageCache()
  const cb = createCircuitBreaker()
  const dt = createDedupTracker('session')
  const stats = createStatsCollector()
  const pipe = createInjectionPipeline({ getConfig: () => ({ injection: { enabled: true, max_memories: 5, token_budget: 500, search_timeout_ms: 2000, ...(cfg || {}) } }), messageCache: mc, client, circuitBreaker: cb, dedupTracker: dt, sensitiveFilter: filterSensitive, statsCollector: stats })
  return { pipe, mc, cb, dt, stats }
}

test('集成：首轮唤醒注入记忆', async () => {
  const client = mockPanguClient([{ id: 'm1', content: '历史记忆', wing: 'p', tags: ['t'], score: 0.9, importance: 4, created_at: new Date().toISOString() }])
  const { pipe, mc } = setup(client)
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询历史' }] } })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1', turn: 1 } } })
  assert.equal(assembly.contexts.length, 1)
  assert.match(assembly.contexts[0].text, /历史记忆/)
})

test('集成：会话内去重', async () => {
  const client = mockPanguClient([{ id: 'm1', content: '记忆A', wing: 'p', tags: [], score: 0.9, importance: 4, created_at: new Date().toISOString() }])
  const { pipe, mc } = setup(client)
  const ctx = { agent: { id: 'a1', session: { id: 's1', turn: 1 } } }
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询' }] } })
  const a1 = { contexts: [] }
  await pipe.run(a1, ctx)
  assert.equal(a1.contexts.length, 1)
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询2' }] } })
  const a2 = { contexts: [] }
  await pipe.run(a2, ctx)
  assert.equal(a2.contexts.length, 0)
})

test('集成：盘古不可达会话正常', async () => {
  const client = { async call() { return { ok: false, error: { kind: 'unreachable', message: 'x' } } } }
  const { pipe, mc } = setup(client)
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询' }] } })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})

test('集成：连续3次失败熔断', async () => {
  const client = { async call() { return { ok: false, error: { kind: 'unreachable', message: 'x' } } } }
  const { pipe, mc, cb } = setup(client)
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询' }] } })
  const ctx = { agent: { id: 'a1', session: { id: 's1' } } }
  for (let i = 0; i < 3; i++) await pipe.run({ contexts: [] }, ctx)
  assert.equal(cb.shouldAllow('s1'), false)
})

test('集成：沉淀写入成功', async () => {
  const stats = createStatsCollector()
  const client = mockPanguClient([])
  const writer = createConsolidationWriter({ getConfig: () => ({ injection: { consolidate_enabled: true, consolidate_max_per_turn: 1, search_timeout_ms: 2000, wing_map: {} } }), client, sensitiveFilter: filterSensitive, statsCollector: stats, getAssistantText: async () => '修复了根因：内存泄漏问题' })
  await writer.run({ agent: { id: 'a1', session: { id: 's1' } }, turn: 1 })
  assert.equal(stats.query().consolidateSuccess, 1)
})

test('集成：沉淀查重跳过', async () => {
  const stats = createStatsCollector()
  const client = mockPanguClient([{ id: 'm1', content: '[自动沉淀] 修复了根因：内存泄漏问题', wing: 'p', tags: [], score: 0.9, importance: 4, created_at: new Date().toISOString() }])
  const writer = createConsolidationWriter({ getConfig: () => ({ injection: { consolidate_enabled: true, consolidate_max_per_turn: 1, search_timeout_ms: 2000, wing_map: {} } }), client, sensitiveFilter: filterSensitive, statsCollector: stats, getAssistantText: async () => '修复了根因：内存泄漏问题' })
  await writer.run({ agent: { id: 'a1', session: { id: 's1' } }, turn: 1 })
  assert.equal(stats.query().consolidateSuccess, 0)
})

test('集成：配置禁用无注入', async () => {
  const client = mockPanguClient([{ id: 'm1', content: '历史', wing: 'p', tags: [], score: 0.9, importance: 4, created_at: new Date().toISOString() }])
  const { pipe, mc } = setup(client, { enabled: false })
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: '查询' }] } })
  const assembly = { contexts: [] }
  await pipe.run(assembly, { agent: { id: 'a1', session: { id: 's1' } } })
  assert.equal(assembly.contexts.length, 0)
})