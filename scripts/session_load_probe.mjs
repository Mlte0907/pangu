// 用 harness 同款加载器复现两个报错会话的加载/修复过程
const HOME = '/home/xiaoxin/.dsh/sessions/--home-xiaoxin--'
const targets = [
  ['c567fe87 (GUI窗口测试)', `${HOME}/session-c567fe87-5948-4ef7-a2c9-4ed1a1b0e688/session.jsonl.zstd`],
  ['56427aa3 (DSH补丁测试)', `${HOME}/session-56427aa3-d16b-421f-813d-0af2b7f5546c/session.jsonl.zstd`],
  ['我的会话(对照,能恢复)', '/home/xiaoxin/.dsh/sessions/--home-xiaoxin-pangu--/session-e87846da-5332-4bc2-89b2-47cebfdc24de/session.jsonl.zstd'],
]

const { Session } = await import('/home/xiaoxin/deepseek-harness/node_modules/@deepseek-ai/cordis/dist/index.js').catch(() => ({})) ?? {}
// 直接用 core/session 的 Session + repair
const coreSession = await import('/home/xiaoxin/deepseek-harness/apps/cli/node_modules/@deepseek-ai/dsh-base/node_modules/@deepseek-ai/cordis/dist/index.js').catch(() => null)

// 更可靠：从 session 包入手
let loadModule = null
for (const p of [
  '/home/xiaoxin/deepseek-harness/packages/session/session-persistence/src/index.ts',
]) {
  try {
    loadModule = await import(p)
    console.log('loaded', p)
    break
  } catch (e) {
    console.log('skip', p, String(e).slice(0, 80))
  }
}
if (!loadModule) {
  console.log('FALLBACK: 手工解析')
}
