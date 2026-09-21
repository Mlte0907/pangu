/**
 * 设置页「保存」语义的独立进程验证。
 *
 * 为什么单独一个脚本（而不是放进 node:test）：node:test 运行器在同进程内
 * 多次初始化 jsdom + React 后，事件绑定会串到前一个 document，导致 onChange
 * 不更新组件状态（表现为输入框 DOM 值变了、但 dirty 仍为 false）。
 *
 * 验证两条安全语义：
 *   A) 未动 Key 框 → 提交的 patch 不含 llm_api_key（否则会用空串覆盖已存 Key）
 *   B) 填入新 Key  → 提交的 patch 含 llm_api_key（新值必须能写入）
 *
 * 运行：node test/settings/save-semantics.mjs
 *
 * 依赖：插件包只依赖 zod（react 由宿主注入），所以测试依赖从宿主解析。
 * 设置 PANGU_TEST_MODULES 指向含 react / react-dom / jsdom 的 node_modules 目录；
 * 默认 /tmp/pangu-render-test/node_modules。缺依赖时打印准备命令并以 0 退出。
 */
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..', '..')
const MODULES = process.env.PANGU_TEST_MODULES || '/tmp/pangu-render-test/node_modules'

const req = createRequire(path.join(MODULES, 'noop.js'))
let React, jsdomPkg
try {
  jsdomPkg = req('jsdom')
  React = req('react')
} catch (err) {
  console.log(`﹣ 跳过：无法从 ${MODULES} 加载 jsdom/react（${err.code}）。`)
  console.log('  准备依赖（宿主路径按实际位置调整）：')
  console.log('    mkdir -p /tmp/pangu-render-test/node_modules')
  console.log('    ln -sfn <dsh>/node_modules/.pnpm/react@18.3.1/node_modules/react        /tmp/pangu-render-test/node_modules/react')
  console.log('    ln -sfn <dsh>/node_modules/.pnpm/react-dom@18.3.1_react@18.3.1/node_modules/react-dom /tmp/pangu-render-test/node_modules/react-dom')
  console.log('    ln -sfn <dsh>/node_modules/.pnpm/jsdom@29.1.1_@noble+hashes@2.3.0/node_modules/jsdom /tmp/pangu-render-test/node_modules/jsdom')
  process.exit(0)
}

const { JSDOM } = jsdomPkg
const dom = new JSDOM('<!doctype html><html><head></head><body><div id="root"></div></body></html>', {
  url: 'http://127.0.0.1:3080/',
  pretendToBeVisual: true,
})
const win = dom.window
for (const k of ['document', 'navigator', 'HTMLElement', 'Element', 'Node', 'HTMLIFrameElement',
  'HTMLInputElement', 'HTMLSelectElement', 'HTMLButtonElement', 'Event', 'MouseEvent',
  'KeyboardEvent', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame',
  'SVGElement', 'DocumentFragment', 'Text', 'Comment']) {
  if (win[k] !== undefined) { try { global[k] = win[k] } catch { /* 只读 */ } }
}
global.IS_REACT_ACT_ENVIRONMENT = true
global.window = win
win.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => '{}' })
win.WebSocket = class { constructor() {} close() {} addEventListener() {} removeEventListener() {} }
win.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
win.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} }
global.WebSocket = win.WebSocket
global.fetch = win.fetch
global.ResizeObserver = win.ResizeObserver
global.IntersectionObserver = win.IntersectionObserver

// react-dom 必须在 global.window 就绪之后才 require：
// 它在加载时会捕获当时的全局环境，过早加载会绑定到错误的 document，
// 表现为 onChange 不更新组件状态（按钮恒 disabled）。
let ReactDOMClient, act
try {
  ReactDOMClient = req('react-dom/client')
  act = req('react-dom/test-utils').act
} catch (err) {
  console.log(`﹣ 跳过：无法加载 react-dom（${err.code}）。`)
  process.exit(0)
}

// 加载真实 client.js
let mod = null
win.__ModuleLoader__ = { load: (m) => { mod = m } }
global.__ModuleLoader__ = win.__ModuleLoader__
eval(fs.readFileSync(path.join(ROOT, 'lib', 'client.js'), 'utf8'))

const calls = []
const svc = {
  get: async () => ({
    ok: true,
    value: {
      config: {
        llm_provider: 'deepseek', llm_model: 'deepseek-chat',
        llm_base_url: 'https://api.deepseek.com/v1',
        llm_api_key: '', llm_api_key_set: true, llm_api_key_hint: '****4455',
        api_key: '', api_key_set: true, api_key_hint: 'pgk_J_*****tnX6',
        consolidation_enabled: true, consolidation_interval_hours: 24,
      },
    },
  }),
  save: async (a) => { calls.push(['save', a]); return { ok: true, value: { ok: true } } },
  testLlm: async () => ({ ok: true, value: { ok: true } }),
}
const captured = []
const registry = {
  slots: { inject: (n, cb) => cb(), register: (m, c) => { captured.push({ ...m, component: c }); return () => {} } },
  timer: { setInterval: () => 0, clearInterval: () => {}, setTimeout: (f, t) => setTimeout(f, t), clearTimeout: (id) => clearTimeout(id) },
  remote: { $mount: async () => () => {} },
  'remote.panguConfig': svc,
}
const ctx = { get: (k) => registry[k], effect: () => {} }

const ex = mod.factory((n) => (n === 'react' ? React : {}))
await ex.apply(ctx)
const Comp = captured.find((c) => c.name === 'settings.section').component

const container = win.document.getElementById('root')
const root = ReactDOMClient.createRoot(container)
await act(async () => { root.render(React.createElement(Comp)) })
await act(async () => { await new Promise((r) => setTimeout(r, 80)) })

const setVal = (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value').set
  setter.call(el, v)
  el.dispatchEvent(new win.Event('input', { bubbles: true }))
}
const saveBtn = () => [...container.querySelectorAll('button')].find((b) => b.textContent.trim() === '保存')
const lastPatch = () => {
  const c = calls.filter((x) => Array.isArray(x) && x[0] === 'save').pop()
  return c ? c[1] : null
}
const click = async (el) => {
  await act(async () => { el.dispatchEvent(new win.MouseEvent('click', { bubbles: true })) })
  await act(async () => { await new Promise((r) => setTimeout(r, 80)) })
}

let fail = 0
const chk = (name, ok, extra) => {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name + (extra && !ok ? '  → ' + extra : ''))
  if (!ok) fail++
}

console.log()
console.log('═══ 场景 A：只改 Base URL，不动 Key 框 ═══')
const base = [...container.querySelectorAll('input')].find((i) => i.value.startsWith('https://api.deepseek.com'))
await act(async () => { setVal(base, 'https://api.deepseek.com/beta') })
await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
console.log(`  输入框值: ${base.value} | 保存按钮 disabled: ${saveBtn()?.disabled}`)
await click(saveBtn())
const patchA = lastPatch()
console.log('  提交的 patch:', JSON.stringify(patchA))
chk('触发 save', !!patchA)
chk('含新 base_url', patchA?.llm_base_url === 'https://api.deepseek.com/beta')
chk('不含 llm_api_key（未动 Key 框，不覆盖已存值）', patchA && !('llm_api_key' in patchA))
chk('含 provider / model', patchA?.llm_provider === 'deepseek' && patchA?.llm_model === 'deepseek-chat')

console.log()
console.log('═══ 场景 B：填入新 Key ═══')
// 注意：不能取「第一个 password 输入框」—— 设置页在 LLM 区之前还有
// 「盘古凭据」也是密码框，直接取第一个会命中它（而不是 LLM API Key）。
// 以 Base URL 输入框为锚点，取它之后的第一个密码框，才是 LLM API Key。
const allInputs = [...container.querySelectorAll('input')]
const baseIdx = allInputs.findIndex((i) => i.value.startsWith('https://api.deepseek.com'))
const pw = allInputs.slice(baseIdx + 1).find((i) => i.getAttribute('type') === 'password')
await act(async () => { setVal(pw, 'sk-brand-new-key-abcdef') })
await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
await click(saveBtn())
const patchB = lastPatch()
console.log('  提交的 patch:', JSON.stringify(patchB))
chk('填入新 Key 后 patch 含 llm_api_key', patchB?.llm_api_key === 'sk-brand-new-key-abcdef')

console.log()
console.log('═══ 场景 C：只填「盘古凭据」，不碰其它字段 ═══')
// 设计：设置页**只有一个**凭据字段（2026-09-21 决定）。
// 服务端两个密钥已由 install.sh 取同值，插件管理面复用「盘古凭据」，
// 再摆一个"可留空的管理密钥"只会让人疑惑到底要不要填。
chk('不再有第二个凭据字段「管理密钥」', !container.textContent.includes('管理密钥'))
const credInput = [...container.querySelectorAll('input')].find((i) => i.getAttribute('type') === 'password')
// 用户反馈（2026-09-21）：填了凭据没有任何反馈，而没填时框里却写着「已配置」。
// 修法：**框内直接显示脱敏值**（一眼看到生效的是哪一把），空配置时才给说明文字。
chk('已配置时框内显示脱敏值', credInput.placeholder === 'pgk_J_*****tnX6')
// 必须是 placeholder 而非 value：否则保存时会把掩码当凭据提交上去
chk('掩码只作占位、不是待提交的值', credInput.value === '')
// 回归（2026-09-21）：dirty 此前不统计密码框，只填凭据时保存按钮恒灰，
// 等于「填了也存不下去」。这里断言：填了凭据 → 按钮可点 → patch 写出 api_key。
await act(async () => { setVal(credInput, 'pgk-LOCAL-ONLY') })
await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
chk('填了凭据后保存按钮可点', !saveBtn()?.disabled)
await click(saveBtn())
const patchC = lastPatch()
console.log('  提交的 patch:', JSON.stringify(patchC))
chk('patch 含 api_key（写入插件凭据）', patchC?.api_key === 'pgk-LOCAL-ONLY')

console.log()
console.log(fail === 0 ? '★ 保存语义全部正确' : `✗ ${fail} 项失败`)
process.exit(fail === 0 ? 0 : 1)
