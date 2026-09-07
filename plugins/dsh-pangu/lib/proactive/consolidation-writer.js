'use strict'

const path = require('path')
const { detect, checkDuplicate } = require('./consolidation-detector')

function mapWing(wingMap) {
  const cwd = process.cwd()
  if (wingMap && typeof wingMap === 'object' && wingMap[cwd]) return wingMap[cwd]
  const base = path.basename(cwd)
  if (!base || base === '.') return 'default'
  return base
}

function createConsolidationWriter(deps) {
  const { getConfig, client, sensitiveFilter, statsCollector, getAssistantText } = deps
  const turnCounts = new Map()

  function record(stats, event) {
    try { stats?.recordConsolidate?.(event) } catch (_) {}
  }

  async function run(payload) {
    const agentId = payload?.agent?.id
    const sessionId = payload?.agent?.session?.id || agentId
    const turn = payload?.turn ?? 0
    let config
    try { config = (getConfig()?.injection) || {} } catch (_) { config = {} }

    if (config.consolidate_enabled === false) return

    const maxPerTurn = Number(config.consolidate_max_per_turn) > 0 ? Number(config.consolidate_max_per_turn) : 1
    const tkey = (sessionId || 'unknown') + ':' + turn
    if ((turnCounts.get(tkey) || 0) >= maxPerTurn) return

    let text
    try { text = getAssistantText ? await getAssistantText(payload) : '' } catch (_) { text = '' }
    if (!text) return

    const detected = detect(text)
    if (!detected.shouldWrite) {
      record(statsCollector, { sessionId, turn, content: text, status: 'skip_value' })
      return
    }

    const isDup = await checkDuplicate(detected.content, client, config.search_timeout_ms)
    if (isDup) {
      record(statsCollector, { sessionId, turn, content: detected.content, status: 'skip_dedup' })
      return
    }

    const content = sensitiveFilter(detected.content)
    const wing = mapWing(config.wing_map)
    const tags = detected.tags.slice(0, 8)
    const importance = detected.importance

    let res
    try {
      res = await client.call('pangu_add_memory', { content, wing, importance, tags }, config.search_timeout_ms)
    } catch (_) {
      record(statsCollector, { sessionId, turn, content, wing, tags, importance, status: 'fail' })
      return
    }

    if (res.ok) {
      let drawerId = null
      try {
        const t = res.data?.result?.content?.[0]?.text
        if (t) drawerId = (JSON.parse(t)?.drawer_id) || null
      } catch (_) {}
      if (drawerId) {
        turnCounts.set(tkey, (turnCounts.get(tkey) || 0) + 1)
        record(statsCollector, { sessionId, turn, content, wing, tags, importance, status: 'success', memoryId: drawerId })
      } else {
        record(statsCollector, { sessionId, turn, content, wing, tags, importance, status: 'fail' })
      }
    } else {
      record(statsCollector, { sessionId, turn, content, wing, tags, importance, status: 'fail' })
    }
  }

  function clear() { turnCounts.clear() }

  return { run, clear, mapWing }
}

module.exports = { createConsolidationWriter, mapWing }