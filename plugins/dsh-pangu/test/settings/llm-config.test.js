'use strict'

/**
 * 设置页 LLM 配置的回归测试。
 *
 * 覆盖两条「填了也没用」的真实缺陷：
 *  - 密钥脱敏：明文 Key 绝不能经 Remote 下发到前端
 *  - 保存语义：留空 = 保持原值，填新值 = 覆盖，null = 清除
 *
 * 运行：node --test test/settings/llm-config.test.js
 */

const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const os = require('node:os')
const fs = require('node:fs')

const ROOT = path.join(__dirname, '..', '..')

// ── 从 lib/index.js 源码中提取脱敏与保存清洗逻辑做纯函数测试 ──
// 直接 import 会拉起整个宿主插件上下文，故以源码为准做等价复刻，
// 并加一条「源码仍然如此实现」的守卫，避免复刻与实现漂移。
const indexSrc = fs.readFileSync(path.join(ROOT, 'lib', 'index.js'), 'utf8')

const SECRET_KEYS = ['llm_api_key', 'api_key']

function redactConfig(cfg) {
  const out = { ...cfg }
  for (const k of SECRET_KEYS) {
    const raw = out[k]
    out[k] = ''
    out[k + '_set'] = typeof raw === 'string' && raw.length > 0
    out[k + '_hint'] = typeof raw === 'string' && raw.length > 4 ? '****' + raw.slice(-4) : ''
  }
  return out
}

function cleanPatch(patch) {
  const clean = {}
  for (const [k, v] of Object.entries(patch || {})) {
    if (SECRET_KEYS.includes(k)) {
      if (v === null) clean[k] = ''
      else if (typeof v === 'string' && v.length > 0) clean[k] = v
    } else {
      clean[k] = v
    }
  }
  return clean
}

// ── 守卫：实现必须仍然按上面复刻的方式写 ──────────────
test('lib/index.js 仍按预期实现脱敏', () => {
  assert.match(indexSrc, /out\[k \+ '_set'\]/, '脱敏的 _set 标记实现已变更')
  assert.match(indexSrc, /out\[k \+ '_hint'\]/, '脱敏的 _hint 提示实现已变更')
  assert.match(indexSrc, /SECRET_KEYS/, 'SECRET_KEYS 常量已移除')
})

test('lib/index.js 不再调用未暴露的 pangu_config_reload', () => {
  // 该工具不在默认 28 个工具的暴露面内，调用会得到 code=1002
  assert.ok(
    !/name:\s*'pangu_config_reload'/.test(indexSrc),
    '仍在使用未暴露的 pangu_config_reload，应改用 pangu_config_set 推送',
  )
  assert.match(indexSrc, /name:\s*'pangu_config_set'/, '未找到 pangu_config_set 推送逻辑')
})

// ── 脱敏 ─────────────────────────────────────────────
test('明文 Key 不出现在脱敏结果中', () => {
  const secret = 'sk-abcdef1234567890'
  const r = redactConfig({ llm_provider: 'deepseek', llm_api_key: secret })
  assert.equal(r.llm_api_key, '', '脱敏后 llm_api_key 必须为空')
  assert.ok(!JSON.stringify(r).includes(secret), '脱敏结果中残留了明文 Key')
})

test('脱敏暴露 _set 与 _hint（仅尾 4 位）', () => {
  const r = redactConfig({ llm_api_key: 'sk-abcdef1234567890' })
  assert.equal(r.llm_api_key_set, true)
  assert.equal(r.llm_api_key_hint, '****7890')
})

test('未设置 Key 时 _set 为 false 且无 hint', () => {
  for (const cfg of [{}, { llm_api_key: '' }]) {
    const r = redactConfig(cfg)
    assert.equal(r.llm_api_key_set, false)
    assert.equal(r.llm_api_key_hint, '')
  }
})

test('过短的 Key 不给出 hint（避免全量暴露）', () => {
  const r = redactConfig({ llm_api_key: 'abcd' })
  assert.equal(r.llm_api_key_set, true)
  assert.equal(r.llm_api_key_hint, '', '4 位以下的 Key 不应回显')
})

test('非密钥字段不受脱敏影响', () => {
  const r = redactConfig({ llm_provider: 'deepseek', llm_model: 'deepseek-chat' })
  assert.equal(r.llm_provider, 'deepseek')
  assert.equal(r.llm_model, 'deepseek-chat')
})

// ── 保存语义 ─────────────────────────────────────────
test('留空表示保持原值（不提交该字段）', () => {
  const p = cleanPatch({ llm_provider: 'openai', llm_api_key: '' })
  assert.ok(!('llm_api_key' in p), '空串不应进入 patch，否则会覆盖已存 Key')
  assert.equal(p.llm_provider, 'openai')
})

test('undefined 同样表示保持原值', () => {
  const p = cleanPatch({ llm_provider: 'openai', llm_api_key: undefined })
  assert.ok(!('llm_api_key' in p))
})

test('填入新 Key 时正常提交', () => {
  const p = cleanPatch({ llm_api_key: 'sk-new-value-123' })
  assert.equal(p.llm_api_key, 'sk-new-value-123')
})

test('null 表示显式清除（提交空串）', () => {
  const p = cleanPatch({ llm_api_key: null })
  assert.equal(p.llm_api_key, '')
})

test('普通字段即使是空串也照常提交', () => {
  const p = cleanPatch({ llm_model: '', llm_base_url: '' })
  assert.equal(p.llm_model, '')
  assert.equal(p.llm_base_url, '')
})

// ── 密钥文件探测（设置页「已配置」状态的数据来源）────────
test('lib/index.js 会读密钥文件判断「已配置」', () => {
  assert.match(indexSrc, /SECRET_FILE/, '缺少密钥文件常量')
  assert.match(indexSrc, /readFile\(SECRET_FILE/, '未读取密钥文件，设置页会永远显示未配置')
})

test('密钥文件路径与 Python 侧一致（~/.pangu/.llm_api_key）', () => {
  const m = indexSrc.match(/const SECRET_FILE = (.+)/)
  assert.ok(m, '未找到 SECRET_FILE 定义')
  assert.ok(m[1].includes("'.pangu'"), '路径应位于 ~/.pangu 下')
  assert.ok(m[1].includes("'.llm_api_key'"), '文件名应为 .llm_api_key（与 PanguConfig 一致）')
})
