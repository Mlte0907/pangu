/**
 * 管理页（盘古 → 管理 → 平台）渲染回归测试。
 *
 * 为什么单独建文件：这个页面曾经**整体崩成空白**，而且原因极不显眼 ——
 *
 * 1) AdminPane 里用了 `config?.pangu_base_url`（平台接入说明文案），但 `config`
 *    是**父组件 PanguTab 的状态**，AdminPane 只收到 `initialSection`。
 *    ⇒ 渲染时抛 `ReferenceError: config is not defined` ⇒ React 卸载整个
 *    管理页 ⇒ 用户看到"点击管理标签什么都不显示"。
 * 2) 即便修了 1)，"未配置管理密钥"时宿主返回的是**内层信封**
 *    `{ok:false, error}`（外层仍是协议信封 `{ok:true, value}`），旧 unwrap 只解
 *    外层 ⇒ 错误被当成正常载荷 ⇒ 平台区静默空白，用户看不出要填管理密钥。
 *
 * 本脚本用**真实 client.js** 挂载组件、喂**真实 wire 形状**，把这两种情形钉死。
 *
 * 运行：node test/admin/admin-pane.mjs
 *
 * 依赖：jsdom / react / react-dom 由宿主提供（插件自身只依赖 zod）。
 * 设置 PANGU_TEST_MODULES 指向含它们的 node_modules；缺依赖时打印准备命令并以 0 退出。
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

/** 真实平台数据（字段与后端 /api/v2/platforms 一致） */
const PLATFORMS = [
  {
    token_id: 'ptok_test1', platform: 'opencode', platform_name: 'OpenCode Agent',
    permissions: ['read', 'write', 'search'], status: 'active',
    created_at: '2026-09-20T02:04:21', last_used_at: '2026-09-21T14:41:20',
    approved_at: '2026-09-20T02:05:04', revoked_at: null, request_ip: '113.12.15.55',
  },
]

/**
 * 复刻宿主 → 前端经过 Typert 网关后的形状。
 * 外层恒为协议信封 {ok:true, value}（失败也走 ok:false 而不会 reject）；
 * value 就是宿主服务的业务返回，管理接口在缺密钥时给 {ok:false, error}。
 */
function makeRemotes(adminConfigured) {
  const env = (v) => ({ ok: true, value: v })
  const adminErr = {
    ok: false,
    error: '未配置管理凭据：请在 DSH 设置 →「盘古记忆系统」填入「盘古凭据」（安装横幅的「DSH 填写卡」里有）…',
  }
  return {
    panguDashboard: {
      data: async () => env({ stats: { total: 6 }, usage: null }),
      deepHealth: async () => env({
        ok: true, status: 'ok',
        checks: ['structure', 'memory', 'embedding'].map((name) => ({ name, status: 'ok' })),
      }),
      stats: async () => env({ snapshots: [] }),
      checkUpdate: async () => env({ hasUpdate: false }),
      backup: async () => env({ ok: true, memories: 6, size: 1024 }),
    },
    panguPlatforms: {
      listPlatforms: async () => env(adminConfigured ? { platforms: PLATFORMS, count: PLATFORMS.length } : adminErr),
      listPending: async () => env(adminConfigured ? { platforms: [], count: 0 } : adminErr),
    },
    panguKG: { graph: async () => env({ ok: true, nodes: [], edges: [] }) },
    panguConfig: {
      get: async () => env({
        ok: true, versions: null,
        config: { pangu_base_url: 'http://127.0.0.1:19529', api_key_set: true, admin_secret_set: adminConfigured },
      }),
    },
    panguAdminKeys: { listRooms: async () => env({ ok: true, rooms: [] }) },
  }
}

/** 挂载 PanguTab 并切到「管理 → 平台」，返回页面文本 */
async function renderAdminPlatforms(adminConfigured) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><div id="root"></div></body></html>', {
    url: 'http://127.0.0.1:3080/', pretendToBeVisual: true,
  })
  const win = dom.window
  for (const k of ['document', 'navigator', 'HTMLElement', 'Element', 'Node', 'HTMLIFrameElement',
    'HTMLInputElement', 'HTMLSelectElement', 'HTMLButtonElement', 'Event', 'MouseEvent',
    'KeyboardEvent', 'CustomEvent', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame',
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

  // 渲染崩溃（如 ReferenceError）会被 React 记到 console.error 并卸载组件 —— 收集起来断言
  const errors = []
  const origError = console.error
  console.error = (...a) => { errors.push(a.map(String).join(' ')) }

  let mod = null
  win.__ModuleLoader__ = { load: (m) => { mod = m } }
  global.__ModuleLoader__ = win.__ModuleLoader__
  try {
    eval(fs.readFileSync(path.join(ROOT, 'lib', 'client.js'), 'utf8'))

    const ReactDOMClient = req('react-dom/client')
    const { act } = req('react-dom/test-utils')

    const captured = []
    const registry = {
      slots: { inject: (n, cb) => cb(), register: (m, c) => { captured.push({ ...m, component: c }); return () => {} } },
      timer: { setInterval: () => 0, clearInterval: () => {}, setTimeout: (f, t) => setTimeout(f, t), clearTimeout: (id) => clearTimeout(id) },
      remote: { $mount: async () => () => {} },
    }
    for (const [k, v] of Object.entries(makeRemotes(adminConfigured))) registry['remote.' + k] = v
    const ctx = { get: (k) => registry[k], effect: () => {}, on: () => null }

    const ex = mod.factory((n) => (n === 'react' ? React : {}))
    await ex.apply(ctx)
    const Comp = captured.find((c) => c.name === 'conversation.view').component

    const container = win.document.getElementById('root')
    const root = ReactDOMClient.createRoot(container)
    await act(async () => { root.render(React.createElement(Comp)) })
    await act(async () => { await new Promise((r) => setTimeout(r, 120)) })
    await act(async () => { win.dispatchEvent(new win.CustomEvent('pangu:goto', { detail: { tab: 'admin' } })) })
    await act(async () => { await new Promise((r) => setTimeout(r, 150)) })
    const platBtn = [...container.querySelectorAll('button')].find((b) => /^平台/.test(b.textContent.trim()))
    if (platBtn) {
      await act(async () => { platBtn.dispatchEvent(new win.MouseEvent('click', { bubbles: true })) })
      await act(async () => { await new Promise((r) => setTimeout(r, 150)) })
    }
    return { text: container.textContent.replace(/\s+/g, ' '), button: platBtn && platBtn.textContent.trim(), errors }
  } finally {
    console.error = origError
  }
}

let fail = 0
const chk = (name, ok, extra) => {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name + (extra && !ok ? '  → ' + extra : ''))
  if (!ok) fail++
}

console.log()
console.log('═══ 场景 A：未配置管理密钥（宿主返回内层错误信封）═══')
const a = await renderAdminPlatforms(false)
chk('管理页未崩溃（无 ReferenceError）', !a.errors.some((e) => /ReferenceError/.test(e)), a.errors[0])
chk('平台区已渲染（不是整体空白）', a.text.includes('平台接入 · 一段话搞定'), a.text.slice(0, 120))
chk('给出「管理接口不可用」可操作提示', a.text.includes('管理接口不可用') && a.text.includes('未配置管理凭据'), a.text.slice(0, 200))

console.log()
console.log('═══ 场景 B：已配置管理密钥（宿主返回平台列表）═══')
const b = await renderAdminPlatforms(true)
chk('管理页未崩溃', !b.errors.some((e) => /ReferenceError/.test(e)), b.errors[0])
chk('平台列表渲染出真实平台名', b.text.includes('OpenCode Agent'), b.text.slice(0, 160))
chk('平台计数不再是 0', /平台 \(1\)/.test(b.button || ''), b.button)
chk('不再出现管理不可用提示', !b.text.includes('管理接口不可用'))

console.log()
console.log(fail === 0 ? '★ 管理页渲染全部正确' : `✗ ${fail} 项失败`)
process.exit(fail === 0 ? 0 : 1)
