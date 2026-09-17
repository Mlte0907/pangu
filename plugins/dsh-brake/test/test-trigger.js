/**
 * dsh-brake 触发测试（直接测核心逻辑，不依赖 cordis 事件链）
 * 运行：node test/test-trigger.js
 */
'use strict'

const assert = require('assert')

// ── 从插件复制核心逻辑（保持一致） ──
const TOOL_FAMILIES = {
  filesystem: /^(read|write|edit|glob|grep|read_image|modlens_read_image|sidebar_open)$/i,
  network: /^(web_search|web_fetch|read_page|x_search|curl)/i,
  search: /^(univer|find_dsh_plugin|skill)$/i,
  code: /^(bash|python|node)/i,
}
function classifyTool(name) {
  for (const [family, pattern] of Object.entries(TOOL_FAMILIES)) {
    if (pattern.test(name)) return family
  }
  return 'other'
}

class SlidingWindow {
  constructor(size = 12) { this.size = size; this.entries = [] }
  push(e) { this.entries.push(e); if (this.entries.length > this.size) this.entries.shift() }
  clear() { this.entries = [] }
  dominantFamily() {
    if (!this.entries.length) return { family: 'other', ratio: 0 }
    const c = {}; for (const e of this.entries) c[e.family] = (c[e.family] || 0) + 1
    let max = 0, d = 'other'
    for (const [f, n] of Object.entries(c)) { if (n / this.entries.length > max) { max = n / this.entries.length; d = f } }
    return { family: d, ratio: max }
  }
}

function createState(windowSize = 12) {
  return {
    window: new SlidingWindow(windowSize),
    consecutiveSteps: 0,
    lastWarnedStep: -1,
    lastDeniedStep: -1,
  }
}

function detectLoop(state, cfg) {
  const { familyThreshold = 0.75, warnSteps = 6, denySteps = 10 } = cfg
  if (state.window.entries.length < 4) return null
  const { family, ratio } = state.window.dominantFamily()
  if (family === 'other' || ratio < familyThreshold) return null
  // 重复率检测：同一工具名出现次数 / 总数 < 50% → 正常工作流
  const nameCounts = {}
  for (const e of state.window.entries) nameCounts[e.name] = (nameCounts[e.name] || 0) + 1
  let maxNameCount = 0
  for (const c of Object.values(nameCounts)) if (c > maxNameCount) maxNameCount = c
  if (maxNameCount / state.window.entries.length < 0.5) return null
  state.consecutiveSteps++
  if (state.consecutiveSteps >= denySteps && state.lastDeniedStep < state.consecutiveSteps) {
    state.lastDeniedStep = state.consecutiveSteps
    return { level: 'deny', family, ratio, steps: state.consecutiveSteps }
  }
  if (state.consecutiveSteps >= warnSteps && state.lastWarnedStep < state.consecutiveSteps) {
    state.lastWarnedStep = state.consecutiveSteps
    return { level: 'warn', family, ratio, steps: state.consecutiveSteps }
  }
  return null
}

function feedTools(state, toolNames, cfg) {
  const results = []
  for (const name of toolNames) {
    state.window.push({ name, family: classifyTool(name), heavy: false, ts: Date.now() })
    const loop = detectLoop(state, cfg)
    if (loop) results.push(loop)
  }
  return results
}

// ── 测试 ──
let passed = 0, failed = 0
function test(name, fn) {
  try { fn(); passed++; console.log(`  ✅ ${name}`) }
  catch (e) { failed++; console.log(`  ❌ ${name}: ${e.message}`) }
}

console.log('dsh-brake trigger tests\n')

// ── 1: 不触发 ──
console.log('1. mixed tools — no trigger')
test('no trigger for mixed tools', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  const r = feedTools(s, ['read', 'bash', 'web_search', 'grep', 'pangu_add_memory', 'edit', 'curl_xxx', 'glob', 'write', 'bash', 'web_fetch', 'read'], cfg)
  assert.strictEqual(r.length, 0)
})

// ── 2: 警告触发 ──
console.log('\n2. filesystem loop — warn at step 6')
test('first warn at step 6 (9th call = 4th detect)', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  const tools = Array(12).fill('grep')
  const results = feedTools(s, tools, cfg)
  assert.ok(results.length > 0, 'should trigger')
  assert.strictEqual(results[0].level, 'warn')
  assert.strictEqual(results[0].steps, 6)
})

// ── 3: 拒绝触发 ──
console.log('\n3. filesystem loop — deny at step 10')
test('deny at step 10', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  const tools = Array(14).fill('grep')
  const results = feedTools(s, tools, cfg)
  const denyResult = results.find(r => r.level === 'deny')
  assert.ok(denyResult, 'should have deny')
  assert.strictEqual(denyResult.steps, 10)
})

// ── 4: 用户消息重置 ──
console.log('\n4. reset after user message')
test('reset clears state', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  feedTools(s, Array(8).fill('grep'), cfg)
  assert.ok(s.consecutiveSteps >= 4, 'should have accumulated steps')
  // 模拟用户消息重置
  s.consecutiveSteps = 0; s.window.clear(); s.lastWarnedStep = -1; s.lastDeniedStep = -1
  const results = feedTools(s, Array(5).fill('grep'), cfg)
  assert.strictEqual(results.length, 0, 'should not trigger after reset')
})

// ── 5: 阈值可配 ──
console.log('\n5. configurable thresholds')
test('warnSteps=3 triggers earlier', () => {
  const s = createState()
  const cfg = { warnSteps: 3, denySteps: 5, familyThreshold: 0.75 }
  const results = feedTools(s, Array(7).fill('read'), cfg)
  assert.ok(results.length >= 1, 'should trigger')
  assert.strictEqual(results[0].steps, 3)
})

test('familyThreshold=0.5 triggers with less concentration', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.5 }
  // 7 filesystem + 5 code = 7/12 = 58% filesystem
  const tools = [...Array(7).fill('grep'), ...Array(5).fill('bash')]
  const results = feedTools(s, tools, cfg)
  assert.ok(results.length > 0, 'should trigger at 50% threshold')
})

// ── 6: other 工具不计数 ──
console.log('\n6. "other" tools are transparent')
test('pangu tools dont count as filesystem', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  // 5 grep + 7 pangu = grep ratio = 5/12 = 42% → no trigger
  const tools = [...Array(5).fill('grep'), ...Array(7).fill('pangu_add_memory')]
  const results = feedTools(s, tools, cfg)
  assert.strictEqual(results.length, 0)
})

// ── 7: 正常工作流不触发（不同工具同族） ──
console.log('\n7. normal workflow — different tools in same family')
test('git add→commit→push does NOT trigger (different tool names)', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  // bash 族但不同工具名：bash(git add), bash(git commit), bash(git push), ...
  // classifyTool 只看前缀，但实际工具名是 bash。需要模拟不同名字。
  // 用 code 族的不同工具：bash, python, node
  const tools = ['bash', 'python', 'node', 'bash', 'python', 'node', 'bash', 'python', 'node', 'bash', 'python', 'node']
  const results = feedTools(s, tools, cfg)
  assert.strictEqual(results.length, 0, 'different tool names in same family should NOT trigger')
})

test('read→write→edit→grep does NOT trigger (different filesystem tools)', () => {
  const s = createState()
  const cfg = { warnSteps: 6, denySteps: 10, familyThreshold: 0.75 }
  const tools = ['read', 'write', 'edit', 'grep', 'read', 'write', 'edit', 'grep', 'read', 'write', 'edit', 'grep']
  const results = feedTools(s, tools, cfg)
  assert.strictEqual(results.length, 0, 'different filesystem tools should NOT trigger')
})

// ── 汇总 ──
console.log(`\n${passed + failed} tests, ${passed} passed, ${failed} failed`)
process.exit(failed > 0 ? 1 : 0)
