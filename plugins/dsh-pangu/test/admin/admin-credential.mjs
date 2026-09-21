/**
 * 管理凭据来源的回归测试。
 *
 * 背景：服务端两把钥匙是两套独立校验 ——
 *   数据面 `X-API-Key`  → config.api_key
 *   管理面 `X-Admin-Key` → ~/.pangu/.admin_secret 的内容
 * 但 install.sh 自 2026-09-21 起让两个文件**取同一个值**，因此设置页只需填
 * 一处「盘古凭据」：管理接口在「管理密钥」留空时回退用 api_key。
 *
 * 本脚本用**真实 index.js** + **stub fetch**（不碰网络）把优先级钉死：
 *   1) 有 admin_secret → 用它（显式优先）
 *   2) 只有 api_key    → 回退用它（新装"只填一处"的关键）
 *   3) 两个都没有      → 不发请求，返回可操作的提示
 *
 * 运行：node test/admin/admin-credential.mjs
 */
import { createRequire } from 'node:module'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const require = createRequire(import.meta.url)
const PLUGIN = path.join(path.dirname(new URL(import.meta.url).pathname), '..', '..')

/** 用给定 config.json 内容挂载插件宿主，返回被 stub 捕获的请求头 */
async function captureAdminHeaders(cfg) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'pangu-cred-'))
  fs.mkdirSync(path.join(home, '.pangu'), { recursive: true })
  fs.writeFileSync(path.join(home, '.pangu', 'config.json'), JSON.stringify(cfg))
  process.env.HOME = home
  const entry = require.resolve(path.join(PLUGIN, 'lib', 'index.js'))
  delete require.cache[entry]

  const captured = []
  const realFetch = global.fetch
  global.fetch = async (url, options = {}) => {
    captured.push({ url: String(url), headers: options.headers || {} })
    return { ok: true, status: 200, json: async () => ({ platforms: [], count: 0 }) }
  }

  try {
    const ex = require(entry)
    const provided = {}
    const noop = () => {}
    const ctx = {
      get: () => undefined,
      provide: (n, s) => { provided[n] = s },
      on: noop, effect: noop, emit: noop, emitAsync: async () => [],
      logger: { info: noop, warn: noop, error: noop, debug: noop },
      slots: { inject: (n, cb) => cb(), register: () => () => {} },
      timer: { setInterval: () => 0, clearInterval: noop, setTimeout: (f, t) => setTimeout(f, t), clearTimeout: setTimeout },
      remote: { $mount: async () => () => {} },
    }
    await ex.apply(ctx)
    const res = await provided.panguPlatforms.listPlatforms()
    return { captured, res }
  } finally {
    global.fetch = realFetch
    fs.rmSync(home, { recursive: true, force: true })
  }
}

let fail = 0
const chk = (name, ok, extra) => {
  console.log((ok ? '  ✓ ' : '  ✗ ') + name + (extra && !ok ? '  → ' + extra : ''))
  if (!ok) fail++
}
const hdr = (c) => {
  const h = c.headers || {}
  for (const k of Object.keys(h)) if (k.toLowerCase() === 'x-admin-key') return h[k]
  return undefined
}

console.log()
console.log('═══ 1) 两把都填 → 管理面用「管理密钥」（显式优先）═══')
{
  const { captured } = await captureAdminHeaders({
    pangu_base_url: 'http://127.0.0.1:19529', api_key: 'API-KEY-VALUE', admin_secret: 'ADMIN-SECRET-VALUE',
  })
  chk('发出了管理请求', captured.length === 1, '请求数 ' + captured.length)
  chk('X-Admin-Key 用的是 admin_secret', hdr(captured[0]) === 'ADMIN-SECRET-VALUE', String(hdr(captured[0])))
}

console.log()
console.log('═══ 2) 只填「盘古凭据」→ 管理面回退用 api_key（新装只填一处）═══')
{
  const { captured, res } = await captureAdminHeaders({
    pangu_base_url: 'http://127.0.0.1:19529', api_key: 'API-KEY-VALUE',
  })
  chk('发出了管理请求（没有因缺密钥而短路）', captured.length === 1, '请求数 ' + captured.length)
  chk('X-Admin-Key 回退为 api_key', hdr(captured[0]) === 'API-KEY-VALUE', String(hdr(captured[0])))
  chk('请求成功时不报错', !res || res.ok !== false, JSON.stringify(res).slice(0, 80))
}

console.log()
console.log('═══ 3) 两个都没填 → 不发请求，给出可操作提示 ═══')
{
  const { captured, res } = await captureAdminHeaders({ pangu_base_url: 'http://127.0.0.1:19529' })
  chk('不发出请求', captured.length === 0, '请求数 ' + captured.length)
  chk('提示指向「盘古凭据」', /未配置管理凭据/.test(String(res && res.error)) && /盘古凭据/.test(String(res && res.error)), String(res && res.error).slice(0, 90))
}

console.log()
console.log('═══ 4) 鉴权失败必须显式上报（不再静默空白）═══')
{
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'pangu-cred-'))
  fs.mkdirSync(path.join(home, '.pangu'), { recursive: true })
  fs.writeFileSync(path.join(home, '.pangu', 'config.json'), JSON.stringify({ pangu_base_url: 'http://127.0.0.1:19529', api_key: 'WRONG' }))
  process.env.HOME = home
  const entry = require.resolve(path.join(PLUGIN, 'lib', 'index.js'))
  delete require.cache[entry]
  const realFetch = global.fetch
  global.fetch = async () => ({ ok: false, status: 401, json: async () => ({ detail: 'nope' }) })
  try {
    const ex = require(entry)
    const provided = {}
    const noop = () => {}
    await ex.apply({
      get: () => undefined,
      provide: (n, s) => { provided[n] = s },
      on: noop, effect: noop, emit: noop, emitAsync: async () => [],
      logger: { info: noop, warn: noop, error: noop, debug: noop },
      slots: { inject: (n, cb) => cb(), register: () => () => {} },
      timer: { setInterval: () => 0, clearInterval: noop, setTimeout: (f, t) => setTimeout(f, t), clearTimeout: setTimeout },
      remote: { $mount: async () => () => {} },
    })
    const res = await provided.panguPlatforms.listPlatforms()
    chk('401 被转成可读错误而不是当成数据', res && res.ok === false && /鉴权失败/.test(String(res.error)), JSON.stringify(res).slice(0, 100))
  } finally {
    global.fetch = realFetch
    fs.rmSync(home, { recursive: true, force: true })
  }
}

console.log()
console.log(fail === 0 ? '★ 管理凭据来源与失败上报全部正确' : `✗ ${fail} 项失败`)
process.exit(fail === 0 ? 0 : 1)
