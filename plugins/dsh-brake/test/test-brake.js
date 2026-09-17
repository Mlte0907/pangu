/**
 * dsh-brake 单元测试
 * 运行：node test/test-brake.js
 */
'use strict'

const assert = require('assert')

// ── 导入插件内部逻辑（通过 require 插件然后提取） ──
// 由于插件用 module.exports = { apply }，我们需要直接测试核心逻辑。
// 这里重新实现核心类以便测试（与 lib/index.js 保持一致）。

/** 工具功能族分类 */
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
  constructor(size = 12) {
    this.size = size
    this.entries = []
  }
  push(entry) {
    this.entries.push(entry)
    if (this.entries.length > this.size) this.entries.shift()
  }
  clear() { this.entries = [] }
  familyRatios() {
    if (this.entries.length === 0) return {}
    const counts = {}
    for (const e of this.entries) counts[e.family] = (counts[e.family] || 0) + 1
    const total = this.entries.length
    const ratios = {}
    for (const [f, c] of Object.entries(counts)) ratios[f] = c / total
    return ratios
  }
  maxFamilyRatio() {
    const ratios = this.familyRatios()
    return Math.max(0, ...Object.values(ratios))
  }
  dominantFamily() {
    const ratios = this.familyRatios()
    let max = 0, dominant = 'other'
    for (const [f, r] of Object.entries(ratios)) {
      if (r > max) { max = r; dominant = f }
    }
    return { family: dominant, ratio: max }
  }
}

// ── 测试 ──
let passed = 0
let failed = 0

function test(name, fn) {
  try {
    fn()
    passed++
    console.log(`  ✅ ${name}`)
  } catch (e) {
    failed++
    console.log(`  ❌ ${name}: ${e.message}`)
  }
}

console.log('dsh-brake unit tests\n')

// ── classifyTool ──
console.log('classifyTool:')
test('read → filesystem', () => assert.strictEqual(classifyTool('read'), 'filesystem'))
test('write → filesystem', () => assert.strictEqual(classifyTool('write'), 'filesystem'))
test('edit → filesystem', () => assert.strictEqual(classifyTool('edit'), 'filesystem'))
test('glob → filesystem', () => assert.strictEqual(classifyTool('glob'), 'filesystem'))
test('grep → filesystem', () => assert.strictEqual(classifyTool('grep'), 'filesystem'))
test('web_search → network', () => assert.strictEqual(classifyTool('web_search'), 'network'))
test('web_fetch → network', () => assert.strictEqual(classifyTool('web_fetch'), 'network'))
test('bash → code', () => assert.strictEqual(classifyTool('bash'), 'code'))
test('pangu_add_memory → other', () => assert.strictEqual(classifyTool('pangu_add_memory'), 'other'))
test('mcp__pangu__pangu_search_memories → other', () => assert.strictEqual(classifyTool('mcp__pangu__pangu_search_memories'), 'other'))
test('curl_xxx → network', () => assert.strictEqual(classifyTool('curl_something'), 'network'))

// ── SlidingWindow ──
console.log('\nSlidingWindow:')
test('empty window → no dominant', () => {
  const w = new SlidingWindow(5)
  assert.strictEqual(w.maxFamilyRatio(), 0)
})

test('single entry → ratio 1.0', () => {
  const w = new SlidingWindow(5)
  w.push({ name: 'read', family: 'filesystem', heavy: false, ts: 1 })
  assert.strictEqual(w.maxFamilyRatio(), 1)
})

test('window respects size limit', () => {
  const w = new SlidingWindow(3)
  for (let i = 0; i < 5; i++) {
    w.push({ name: 'read', family: 'filesystem', heavy: false, ts: i })
  }
  assert.strictEqual(w.entries.length, 3)
})

test('mixed families → correct ratios', () => {
  const w = new SlidingWindow(10)
  w.push({ name: 'read', family: 'filesystem', heavy: false, ts: 1 })
  w.push({ name: 'grep', family: 'filesystem', heavy: false, ts: 2 })
  w.push({ name: 'bash', family: 'code', heavy: true, ts: 3 })
  const ratios = w.familyRatios()
  assert.strictEqual(ratios.filesystem, 2 / 3)
  assert.strictEqual(ratios.code, 1 / 3)
})

test('dominant family detected', () => {
  const w = new SlidingWindow(10)
  for (let i = 0; i < 8; i++) w.push({ name: 'read', family: 'filesystem', heavy: false, ts: i })
  for (let i = 0; i < 2; i++) w.push({ name: 'bash', family: 'code', heavy: true, ts: i + 8 })
  const { family, ratio } = w.dominantFamily()
  assert.strictEqual(family, 'filesystem')
  assert.ok(ratio > 0.7)
})

test('clear resets window', () => {
  const w = new SlidingWindow(5)
  w.push({ name: 'read', family: 'filesystem', heavy: false, ts: 1 })
  w.clear()
  assert.strictEqual(w.entries.length, 0)
})

// ── 死循环检测模拟 ──
console.log('\nLoop detection simulation:')

test('grep→curl→read→bash 循环 → filesystem 主导', () => {
  const w = new SlidingWindow(12)
  // 模拟死循环：全是 filesystem 类工具
  const tools = ['grep', 'read', 'grep', 'read', 'grep', 'bash', 'grep', 'read', 'grep', 'bash', 'grep', 'read']
  tools.forEach((t, i) => w.push({ name: t, family: classifyTool(t), heavy: false, ts: i }))
  const { family, ratio } = w.dominantFamily()
  assert.strictEqual(family, 'filesystem')
  assert.ok(ratio >= 0.75, `ratio ${ratio} should be >= 0.75`)
})

test('混合工具 → 无主导族', () => {
  const w = new SlidingWindow(12)
  const tools = ['read', 'bash', 'web_search', 'grep', 'pangu_add_memory', 'edit', 'curl_xxx', 'glob', 'write', 'bash', 'web_fetch', 'read']
  tools.forEach((t, i) => w.push({ name: t, family: classifyTool(t), heavy: false, ts: i }))
  const { ratio } = w.dominantFamily()
  assert.ok(ratio < 0.75, `ratio ${ratio} should be < 0.75 for mixed tools`)
})

test('用户消息后重置 → 窗口清空', () => {
  const w = new SlidingWindow(12)
  for (let i = 0; i < 10; i++) w.push({ name: 'grep', family: 'filesystem', heavy: false, ts: i })
  assert.ok(w.maxFamilyRatio() > 0.75)
  w.clear()
  assert.strictEqual(w.maxFamilyRatio(), 0)
})

// ── 汇总 ──
console.log(`\n${passed + failed} tests, ${passed} passed, ${failed} failed`)
process.exit(failed > 0 ? 1 : 0)
