'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const { createMessageCache } = require('../../lib/proactive/message-cache')
const { rank } = require('../../lib/proactive/score-ranker')
const { createDedupTracker } = require('../../lib/proactive/dedup-tracker')
const { allocate } = require('../../lib/proactive/budget-allocator')
const { format } = require('../../lib/proactive/context-formatter')
const { createCircuitBreaker } = require('../../lib/proactive/circuit-breaker')
const { extractResults } = require('../../lib/proactive/memory-fetcher')

test('MessageCache claimed缓存与source.kind过滤', () => {
  const mc = createMessageCache()
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'user' }, content: [{ type: 'text', text: 'hello' }] } })
  assert.equal(mc.get('a1').text, 'hello')
  mc.handleClaimed({ agent: { id: 'a1' }, message: { source: { kind: 'plugin' }, content: [{ type: 'text', text: 'inject' }] } })
  assert.equal(mc.get('a1').text, 'hello')
  mc.delete('a1')
  assert.equal(mc.get('a1'), null)
})

test('ScoreRanker 公式与排序', () => {
  const now = new Date().toISOString()
  const r = rank([{ id: '1', score: 0.8, importance: 5, created_at: now }, { id: '2', score: 0.4, importance: 1, created_at: '2020-01-01' }], 5)
  assert.equal(r[0].id, '1')
  assert.ok(r[0].finalScore > r[1].finalScore)
  assert.equal(r[0].finalScore, 1.0)
})

test('ScoreRanker 全零score与created_at缺失', () => {
  const r = rank([{ id: '1', score: 0, importance: 3, created_at: null }], 5)
  assert.equal(r[0].relevance, 0)
  assert.equal(r[0].recency, 0.3)
})

test('DedupTracker 已注入排除', () => {
  const d = createDedupTracker('session')
  d.markInjected('s1', ['a'])
  assert.deepEqual(d.filter([{ id: 'a' }, { id: 'b' }], 's1').map(x => x.id), ['b'])
})

test('DedupTracker global跨会话去重', () => {
  const d = createDedupTracker('global')
  d.markInjected('s1', ['a'])
  assert.deepEqual(d.filter([{ id: 'a' }], 's2').map(x => x.id), [])
})

test('BudgetAllocator 预算内全入选', () => {
  const { injected, tokensUsed } = allocate([{ id: '1', content: 'short' }, { id: '2', content: 'tiny' }], 500)
  assert.equal(injected.length, 2)
  assert.ok(tokensUsed <= 500)
})

test('BudgetAllocator 超预算截断', () => {
  const { injected, tokensUsed } = allocate([{ id: '1', content: 'x'.repeat(800) }], 300)
  assert.equal(injected.length, 1)
  assert.equal(tokensUsed, 300)
  assert.ok(injected[0].content.length < 800)
})

test('BudgetAllocator 单条200字符截断', () => {
  const { injected } = allocate([{ id: '1', content: 'x'.repeat(800) }], 2000)
  assert.ok(injected[0].content.length <= 201)
})

test('ContextFormatter 边界标记与零结果null', () => {
  assert.equal(format([]), null)
  const text = format([{ content: 'c', wing: 'w', tags: ['t'] }])
  assert.match(text, /\[盘古记忆系统/)
  assert.match(text, /\[w\]/)
  assert.match(text, /标签: t/)
})

test('CircuitBreaker 3次熔断与session重置', () => {
  let trips = 0
  const c = createCircuitBreaker({ onTrip: () => trips++ })
  c.recordFailure('s1'); c.recordFailure('s1'); c.recordFailure('s1')
  assert.equal(c.shouldAllow('s1'), false)
  assert.equal(trips, 1)
  c.onSessionStart('s1')
  assert.equal(c.shouldAllow('s1'), true)
})

test('CircuitBreaker 鉴权永久跳过', () => {
  const c = createCircuitBreaker()
  c.recordAuthFailure('s1')
  assert.equal(c.shouldAllow('s1'), false)
  c.recordSuccess('s1')
  assert.equal(c.shouldAllow('s1'), false)
})

test('MemoryFetcher extractResults解析', () => {
  const cand = extractResults({ result: { content: [{ text: JSON.stringify({ results: [{ id: 'm1', content: 'hello', wing: 'p', tags: ['t'], score: 0.5, importance: 4, created_at: '2026-09-08' }] }) }] } })
  assert.equal(cand[0].id, 'm1')
  assert.equal(cand[0].content, 'hello')
})

test('MemoryFetcher extractResults非JSON抛错', () => {
  assert.throws(() => extractResults({ result: { content: [{ text: 'notjson' }] } }))
})