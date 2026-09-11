'use strict'

/**
 * 设置页 LLM 表单的渲染与交互回归测试。
 *
 * 用 jsdom 真实渲染 PanguSettings，断言：
 *  - LLM 表单四个字段都渲染出来
 *  - API Key 输入框 value 恒为空（明文绝不下发到前端）
 *  - 「测试连接」点击后确实调用 remote.testLlm
 *  - 保存时未动 Key 框则 patch 不含 llm_api_key（不覆盖已存 Key）
 *
 * 依赖 jsdom，而插件运行时只依赖 zod（react 由宿主注入）。
 * 找不到 jsdom / react 时整组跳过，不让 CI 因缺依赖而红。
 *
 * 运行：node --test test/settings/llm-form.test.js
 */

const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')

const ROOT = path.join(__dirname, '..', '..')
const CLIENT = path.join(ROOT, 'lib', 'client.js')

// 依赖探测：jsdom 与 react 由外部提供
function tryRequire(name) {
  try { return require(name) } catch { return null }
}

const jsdomPkg = tryRequire('jsdom')
const reactPkg = tryRequire('react')
// 注意：react-dom 不在这里加载 —— 它在 require 时会捕获当时的全局环境，
// 必须在每次搭好 jsdom 的 global.window 之后才加载，否则事件绑定会串到
// 错误的 document（表现为 onChange 不更新状态、保存按钮恒 disabled）。
const haveCore = Boolean(jsdomPkg && reactPkg)
const skip = haveCore ? false : '需要 jsdom 与 react（宿主环境提供）；本机未找到，跳过渲染测试'

/** 搭一次 jsdom + 加载真实 client.js，挂载设置页组件 */
function mountSettings(config) {
  const { JSDOM } = jsdomPkg
  const dom = new JSDOM(
    '<!doctype html><html><head></head><body><div id="root"></div></body></html>',
    { url: 'http://127.0.0.1:3080/', pretendToBeVisual: true },
  )
  const win = dom.window

  // react-dom 需要这些全局
  for (const k of ['document', 'navigator', 'HTMLElement', 'Element', 'Node',
    'HTMLIFrameElement', 'HTMLInputElement', 'HTMLSelectElement', 'HTMLButtonElement',
    'Event', 'MouseEvent', 'KeyboardEvent', 'FocusEvent', 'CustomEvent', 'getComputedStyle',
    'requestAnimationFrame', 'cancelAnimationFrame', 'DOMParser', 'XMLHttpRequest',
    'SVGElement', 'DocumentFragment', 'Text', 'Comment', 'NodeList', 'HTMLCollection',
    'MutationObserver', 'AbortController']) {
    if (win[k] !== undefined) {
      try { global[k] = win[k] } catch { /* 只读则跳过 */ }
    }
  }
  global.IS_REACT_ACT_ENVIRONMENT = true
  global.window = win
  global.self = win

  win.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => '{}' })
  win.WebSocket = class { constructor() {} close() {} addEventListener() {} removeEventListener() {} }
  win.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  win.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} }
  global.WebSocket = win.WebSocket
  global.fetch = win.fetch
  global.ResizeObserver = win.ResizeObserver
  global.IntersectionObserver = win.IntersectionObserver

  const React = reactPkg
  // 关键：在 global.window 就绪之后才加载 react-dom
  const { act } = tryRequire('react-dom/test-utils')
  const reactDomClient = tryRequire('react-dom/client')

  // 加载真实 client.js（走宿主的 ModuleLoader 契约）
  let mod = null
  win.__ModuleLoader__ = { load: (m) => { mod = m } }
  global.__ModuleLoader__ = win.__ModuleLoader__
  // eslint-disable-next-line no-eval
  eval(fs.readFileSync(CLIENT, 'utf8'))

  const calls = []
  const remoteHub = { $mount: async () => () => {} }
  // 复刻真实契约：callRemote 用 ctx.get('remote.<name>')，返回 {ok, value} 信封
  const panguConfigSvc = {
    get: async () => { calls.push('get'); return { ok: true, value: { config } } },
    save: async (a) => { calls.push(['save', a]); return { ok: true, value: { ok: true, reload: { ok: true } } } },
    testLlm: async () => {
      calls.push('testLlm')
      return { ok: true, value: { ok: true, ms: 123, model: 'deepseek-chat', sample: '可用' } }
    },
  }

  const captured = []
  const slots = {
    inject: (name, cb) => cb(),
    register: (meta, component) => { captured.push({ ...meta, component }); return () => {} },
  }
  const registry = {
    slots,
    timer: {
      setInterval: () => 0, clearInterval: () => {},
      setTimeout: (f, t) => setTimeout(f, t), clearTimeout: (id) => clearTimeout(id),
    },
    remote: remoteHub,
    'remote.panguConfig': panguConfigSvc,
  }
  const ctx = { get: (k) => registry[k], effect: () => {} }

  const exportsObj = mod.factory((name) => (name === 'react' ? React : {}))
  return { win, React, act, reactDomClient, exportsObj, ctx, captured, calls }
}

const FAKE_CFG = {
  llm_provider: 'deepseek',
  llm_model: 'deepseek-chat',
  llm_base_url: 'https://api.deepseek.com/v1',
  llm_api_key: '',
  llm_api_key_set: true,
  llm_api_key_hint: '****4455',
  consolidation_enabled: true,
  consolidation_interval_hours: 24,
  embedding_model: 'all-MiniLM-L6-v2',
  palace_path: '/home/xiaoxin/.pangu/palace',
}

async function render(env) {
  const { win, React, act, reactDomClient, exportsObj, ctx, captured } = env
  await exportsObj.apply(ctx)
  const Comp = captured.find((c) => c.name === 'settings.section').component
  const container = win.document.getElementById('root')
  const root = reactDomClient.createRoot(container)
  await act(async () => { root.render(React.createElement(Comp)) })
  await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
  return { container, root }
}

test('设置页注册到 settings.section 槽', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  await render(env)
  const ids = env.captured.map((c) => c.id)
  assert.ok(ids.includes('pangu-settings'), `未注册设置页贡献, 实际: ${ids.join(',')}`)
})

test('LLM 表单四个字段与两个按钮都渲染', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)

  const inputs = [...container.querySelectorAll('input, select')]
  const buttons = [...container.querySelectorAll('button')].map((b) => b.textContent.trim())

  assert.ok(inputs.some((i) => i.tagName === 'SELECT'), '缺少提供商下拉')
  assert.ok(inputs.some((i) => i.value === 'deepseek-chat'), '缺少模型输入框')
  assert.ok(inputs.some((i) => i.value === 'https://api.deepseek.com/v1'), '缺少 Base URL 输入框')
  assert.ok(inputs.some((i) => i.getAttribute('type') === 'password'), '缺少 API Key 密码框')
  assert.ok(buttons.some((b) => b.includes('测试连接')), '缺少「测试连接」按钮')
  assert.ok(buttons.some((b) => b === '保存'), '缺少「保存」按钮')
})

test('提供商选项齐全且与 llm.py 的 PROVIDER_URLS 对齐', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  const options = [...container.querySelectorAll('option')].map((o) => o.textContent.trim())
  for (const label of ['OpenAI', 'DeepSeek', '智谱 GLM', '通义千问', 'OpenRouter', 'Ollama (本地)']) {
    assert.ok(options.includes(label), `缺少提供商选项: ${label}`)
  }
})

test('API Key 框 value 恒为空，明文绝不下发到前端', { skip }, async () => {
  // 即便服务端「不小心」下发了明文，前端也不该把它渲染进 value
  const env = mountSettings({ ...FAKE_CFG, llm_api_key: 'sk-leaked-plaintext-key' })
  const { container } = await render(env)

  const pw = [...container.querySelectorAll('input')].find((i) => i.getAttribute('type') === 'password')
  assert.equal(pw.value, '', 'Key 输入框 value 不为空，存在回显明文的风险')
  assert.ok(!container.textContent.includes('sk-leaked-plaintext-key'), '页面文本中出现了明文 Key')
})

test('显示脱敏 hint 与「已配置」状态', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  assert.ok(container.textContent.includes('****4455'), '未显示脱敏 hint')
  assert.ok(container.textContent.includes('已配置'), '未提示 Key 已配置')
})

test('点击「测试连接」调用 remote.testLlm 并渲染结果', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  const btn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('测试连接'))
  await env.act(async () => { btn.dispatchEvent(new env.win.MouseEvent('click', { bubbles: true })) })
  await env.act(async () => { await new Promise((r) => setTimeout(r, 80)) })

  assert.ok(env.calls.includes('testLlm'), '未调用 remote.testLlm')
  assert.ok(container.textContent.includes('连接成功'), '未渲染成功提示')
  assert.ok(container.textContent.includes('123ms'), '未渲染耗时')
})

test('未动 Key 框时保存的 patch 不含 llm_api_key', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  const setVal = (el, v) => {
    const setter = Object.getOwnPropertyDescriptor(env.win.HTMLInputElement.prototype, 'value').set
    setter.call(el, v)
    el.dispatchEvent(new env.win.Event('input', { bubbles: true }))
  }
  const base = [...container.querySelectorAll('input')].find((i) => i.value.startsWith('https://api.deepseek.com'))
  await env.act(async () => { setVal(base, 'https://api.deepseek.com/beta') })
  await env.act(async () => { await new Promise((r) => setTimeout(r, 50)) })

  const saveBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.trim() === '保存')
  await env.act(async () => { saveBtn.dispatchEvent(new env.win.MouseEvent('click', { bubbles: true })) })
  await env.act(async () => { await new Promise((r) => setTimeout(r, 80)) })

  const call = env.calls.find((c) => Array.isArray(c) && c[0] === 'save')
  assert.ok(call, `未触发 save（calls=${JSON.stringify(env.calls)}）`)
  assert.equal(call[1].llm_base_url, 'https://api.deepseek.com/beta')
  assert.ok(!('llm_api_key' in call[1]), '未动 Key 框却提交了 llm_api_key，会覆盖已存 Key')
})

test('填入新 Key 时保存的 patch 含 llm_api_key', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  const setVal = (el, v) => {
    const setter = Object.getOwnPropertyDescriptor(env.win.HTMLInputElement.prototype, 'value').set
    setter.call(el, v)
    el.dispatchEvent(new env.win.Event('input', { bubbles: true }))
  }
  const pw = [...container.querySelectorAll('input')].find((i) => i.getAttribute('type') === 'password')
  await env.act(async () => { setVal(pw, 'sk-brand-new-key-abcdef') })
  await env.act(async () => { await new Promise((r) => setTimeout(r, 50)) })

  const saveBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.trim() === '保存')
  await env.act(async () => { saveBtn.dispatchEvent(new env.win.MouseEvent('click', { bubbles: true })) })
  await env.act(async () => { await new Promise((r) => setTimeout(r, 80)) })

  const call = env.calls.find((c) => Array.isArray(c) && c[0] === 'save')
  assert.ok(call, '未触发 save')
  assert.equal(call[1].llm_api_key, 'sk-brand-new-key-abcdef')
})

test('原有记忆维护设置未被破坏', { skip }, async () => {
  const env = mountSettings(FAKE_CFG)
  const { container } = await render(env)
  assert.ok(container.textContent.includes('自动巩固'), '缺少「自动巩固」开关')
  assert.ok(container.textContent.includes('巩固间隔'), '缺少「巩固间隔」设置')
  const range = [...container.querySelectorAll('input')].find((i) => i.getAttribute('type') === 'range')
  assert.ok(range, '缺少巩固间隔滑块')
  assert.equal(range.value, '24')
})
