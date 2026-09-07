'use strict'

const { test } = require('node:test')
const assert = require('node:assert/strict')
const { validateInjectionConfig, DEFAULTS } = require('../../lib/proactive/config')
const { filterSensitive } = require('../../lib/proactive/sensitive-filter')
const { createStatsCollector } = require('../../lib/proactive/stats-collector')
const { classifyError } = require('../../lib/proactive/mcp-client')

test('InjectionConfig 缺省默认值', () => {
  const { injection } = validateInjectionConfig({}, { warn() {} })
  assert.equal(injection.enabled, true)
  assert.equal(injection.max_memories, 5)
  assert.equal(injection.token_budget, 500)
  assert.equal(injection.dedup_scope, 'session')
  assert.equal(injection.search_timeout_ms, 2000)
  assert.equal(injection.consolidate_enabled, true)
  assert.equal(injection.consolidate_max_per_turn, 1)
  assert.deepEqual(injection.wing_map, {})
})

test('InjectionConfig 超范围回退默认并告警', () => {
  const warns = []
  const { injection } = validateInjectionConfig({ injection: { max_memories: 50, token_budget: 0, dedup_scope: 'x', search_timeout_ms: 10, consolidate_max_per_turn: 99 } }, { warn: (m) => warns.push(m) })
  assert.equal(injection.max_memories, 5)
  assert.equal(injection.token_budget, 500)
  assert.equal(injection.dedup_scope, 'session')
  assert.equal(injection.search_timeout_ms, 2000)
  assert.equal(injection.consolidate_max_per_turn, 1)
  assert.ok(warns.length >= 5)
})

test('InjectionConfig 类型错误回退', () => {
  const { injection } = validateInjectionConfig({ injection: { enabled: 'yes', wing_map: 'x' } }, { warn() {} })
  assert.equal(injection.enabled, true)
  assert.deepEqual(injection.wing_map, {})
})

test('InjectionConfig 合法值保留', () => {
  const { injection, apiKey } = validateInjectionConfig({ api_key: 'k1', injection: { max_memories: 10, token_budget: 2000, dedup_scope: 'global' } }, { warn() {} })
  assert.equal(injection.max_memories, 10)
  assert.equal(injection.token_budget, 2000)
  assert.equal(injection.dedup_scope, 'global')
  assert.equal(apiKey, 'k1')
})

test('SensitiveFilter 7类模式遮蔽', () => {
  assert.match(filterSensitive('key=sk-abcdefghijklmnopqrstuvwxyz1234567890'), /\[REDACTED\]/)
  assert.match(filterSensitive('AKIAIOSFODNN7EXAMPLE'), /\[REDACTED\]/)
  assert.match(filterSensitive('eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature'), /\[REDACTED\]/)
  assert.match(filterSensitive('-----BEGIN RSA PRIVATE KEY-----'), /\[REDACTED\]/)
  assert.match(filterSensitive('password: secret123'), /\[REDACTED\]/)
  assert.match(filterSensitive('token: abc123'), /\[REDACTED\]/)
  assert.match(filterSensitive('Bearer abc.def.ghi'), /\[REDACTED\]/)
})

test('SensitiveFilter 无匹配透传', () => {
  assert.equal(filterSensitive('普通文本无敏感信息'), '普通文本无敏感信息')
})

test('SensitiveFilter 多模式叠加', () => {
  const out = filterSensitive('password: secret123 and token: xyz789')
  assert.ok(!out.includes('secret123'))
  assert.ok(!out.includes('xyz789'))
})

test('StatsCollector 计数与平均', () => {
  const sc = createStatsCollector()
  sc.recordInject({ status: 'success', latencyMs: 100, tokensUsed: 50 })
  sc.recordInject({ status: 'success', latencyMs: 200, tokensUsed: 70 })
  sc.recordInject({ status: 'fail', latencyMs: 50, failReason: 'timeout' })
  sc.recordCircuitBreak('s1')
  const q = sc.query()
  assert.equal(q.totalAttempts, 3)
  assert.equal(q.successCount, 2)
  assert.equal(q.failCount, 1)
  assert.equal(q.avgLatencyMs, 350 / 3)
  assert.equal(q.avgTokensUsed, 60)
  assert.equal(q.circuitBreakCount, 1)
})

test('PanguMcpClient classifyError 四类', () => {
  assert.equal(classifyError({ name: 'AbortError' }, null).kind, 'timeout')
  assert.equal(classifyError({ code: 'ECONNREFUSED' }, null).kind, 'unreachable')
  assert.equal(classifyError({ name: 'SyntaxError' }, null).kind, 'format')
  assert.equal(classifyError(null, { status: 401 }).kind, 'auth')
  assert.equal(classifyError(null, { status: 403 }).kind, 'auth')
  assert.equal(classifyError({ message: 'x' }, null).kind, 'unknown')
})