// 用 harness 真实加载器测量两个报错会话的「实际回放体积」
// 走 apps/cli 的 node_modules 解析链（与运行实例同版本）
import { createRequire } from 'node:module'
const require = createRequire('/home/xiaoxin/deepseek-harness/apps/cli/package.json')

const { SessionPreparation } = await import(import.meta.resolve?.('@deepseek-ai/dsh-session') ?? '/home/xiaoxin/deepseek-harness/packages/core/session/src/index.ts').catch(async () => {
  // 源码不可直接 import 时退回 tsx 加载的 lib
  return await import('/home/xiaoxin/deepseek-harness/apps/cli/node_modules/@deepseek-ai/dsh-base/node_modules/@deepseek-ai/dsh-session/dist/index.js').catch(() => null) ?? {}
}) ?? {}

console.log('SessionPreparation loaded:', typeof SessionPreparation?.create)
