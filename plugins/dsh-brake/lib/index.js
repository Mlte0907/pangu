/**
 * dsh-brake — 死循环刹车器
 *
 * 检测"方法循环"：agent 反复用同类工具尝试同一方向，但没有进展。
 * 与 repeat-tool-reminder（检测同一工具连续重复）互补：
 *   repeat-tool-reminder → bash×5 同参数 ✅
 *   dsh-brake            → grep→curl→read→bash→grep 循环 ✅
 *
 * 检测算法：
 *   1. 维护最近 N 次 tool call 的滑动窗口
 *   2. 将工具按功能族分类（filesystem/network/search/code）
 *   3. 当同一功能族占比超过阈值 + 无用户消息打断 + 连续 step 数超标 → 触发
 *   4. 轻度触发：注入警告 message
 *   5. 重度触发：拒绝执行（deny）
 *
 * 配置：
 *   windowSize:     滑动窗口大小（默认 12）
 *   familyThreshold: 功能族占比阈值（默认 0.75）
 *   warnSteps:      连续 step 数达此值时警告（默认 6）
 *   denySteps:      连续 step 数达此值时拒绝（默认 10）
 */
'use strict'

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

/** 判断是否为"重工具"（有副作用/开销大的工具） */
const HEAVY_TOOLS = /^(write|edit|bash|web_fetch|modlens_read_image)/i

function isHeavy(name) {
  return HEAVY_TOOLS.test(name)
}

/**
 * 滑动窗口：记录最近 N 次工具调用
 * @typedef {{ name: string, family: string, heavy: boolean, ts: number }} WindowEntry
 */
class SlidingWindow {
  constructor(size = 12) {
    this.size = size
    this.entries = []
  }

  push(entry) {
    this.entries.push(entry)
    if (this.entries.length > this.size) {
      this.entries.shift()
    }
  }

  /** 清空窗口 */
  clear() {
    this.entries = []
  }

  /** 统计各功能族占比 */
  familyRatios() {
    if (this.entries.length === 0) return {}
    const counts = {}
    for (const e of this.entries) {
      counts[e.family] = (counts[e.family] || 0) + 1
    }
    const total = this.entries.length
    const ratios = {}
    for (const [family, count] of Object.entries(counts)) {
      ratios[family] = count / total
    }
    return ratios
  }

  /** 最大功能族的占比 */
  maxFamilyRatio() {
    const ratios = this.familyRatios()
    let max = 0
    for (const ratio of Object.values(ratios)) {
      if (ratio > max) max = ratio
    }
    return max
  }

  /** 最大功能族的名称 */
  dominantFamily() {
    const ratios = this.familyRatios()
    let max = 0
    let dominant = 'other'
    for (const [family, ratio] of Object.entries(ratios)) {
      if (ratio > max) {
        max = ratio
        dominant = family
      }
    }
    return { family: dominant, ratio: max }
  }
}

/** 预定义的轻度警告消息 */
const WARN_MESSAGE = '[dsh-brake] 检测到方法循环：最近的工具调用集中在同一功能方向，'
  + '但任务未取得进展。请停下来重新分析问题：'
  + '\n1. 换一个完全不同的思路'
  + '\n2. 向用户确认当前方向是否正确'
  + '\n3. 如果证据已经足够，直接给出结论'

/** 预定义的重度警告消息（即将 deny） */
const DENY_PREVIEW = '[dsh-brake] 方法循环仍在继续。'
  + '下一次同类工具调用将被拒绝。'
  + '请立即改变方向或向用户报告当前困境。'

/**
 * 安装刹车器监听器
 * @param {import('@deepseek-ai/cordis').Context} ctx
 * @param {object} config
 */
function apply(ctx, config) {
  const windowSize = config.windowSize || 12
  const familyThreshold = config.familyThreshold || 0.75
  const warnSteps = config.warnSteps || 6
  const denySteps = config.denySteps || 10

  /** 每个 agent 的状态 */
  const agentState = new WeakMap()

  function getState(agent) {
    if (!agent) return null
    let state = agentState.get(agent)
    if (!state) {
      state = {
        window: new SlidingWindow(windowSize),
        consecutiveSteps: 0,
        lastWarnedStep: -1,
        lastDeniedStep: -1,
        hasUserMessage: true, // 初始为 true，第一次 tool call 前不会触发
      }
      agentState.set(agent, state)
    }
    return state
  }

  /** 检测是否循环 */
  function detectLoop(state) {
    if (state.window.entries.length < 4) return null

    const { family, ratio } = state.window.dominantFamily()
    if (family === 'other') return null
    if (ratio < familyThreshold) return null

    // 关键区分：正常工作流用不同工具（git add→commit→push），
    // 死循环重复同一工具（grep→grep→grep）。
    // 计算最大工具名重复率：同一工具名出现次数 / 总数
    const nameCounts = {}
    for (const e of state.window.entries) nameCounts[e.name] = (nameCounts[e.name] || 0) + 1
    let maxNameCount = 0
    for (const c of Object.values(nameCounts)) if (c > maxNameCount) maxNameCount = c
    const repeatRatio = maxNameCount / state.window.entries.length

    // 重复率 < 50% → 正常工作流（不同工具做同族操作），不触发
    if (repeatRatio < 0.5) return null

    // 计算连续 step 数
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

  // ── 工具执行后：记录到滑动窗口 + 检测循环 ──
  ctx.on('tools/post-execute', async (exec, _result, next) => {
    if (!exec.agent) return next()
    const state = getState(exec.agent)
    if (!state) return next()

    state.window.push({
      name: exec.name,
      family: classifyTool(exec.name),
      heavy: isHeavy(exec.name),
      ts: Date.now(),
    })

    const loop = detectLoop(state)
    if (!loop) return next()

    const msg = loop.level === 'deny'
      ? DENY_PREVIEW
      : `${WARN_MESSAGE}\n\n当前集中方向: ${loop.family} (${(loop.ratio * 100).toFixed(0)}%), 连续 ${loop.steps} 个 step。`

    const reminder = {
      type: 'text',
      text: msg,
    }

    return {
      kind: 'accept',
      additionalContexts: [{
        role: 'user',
        content: [reminder],
        source: { kind: 'plugin', plugin: 'dsh-brake', form: 'notice', summary: `loop detected: ${loop.family} × ${loop.steps}` },
      }],
    }
  })

  // ── 用户消息：重置循环计数 ──
  ctx.on('agent/pre-step', ({ agent, messages }, next) => {
    if (messages.some(m => m.source?.kind === 'user')) {
      const state = getState(agent)
      if (state) {
        state.consecutiveSteps = 0
        state.window.clear()
        state.hasUserMessage = true
        state.lastWarnedStep = -1
        state.lastDeniedStep = -1
      }
    }
    return next()
  })
}

module.exports = { apply, name: 'dsh-brake' }
