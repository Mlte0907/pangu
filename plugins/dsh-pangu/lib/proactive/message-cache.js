'use strict'

function extractText(message) {
  const content = message?.content
  if (Array.isArray(content)) {
    let text = ''
    for (const part of content) {
      if (part && part.type === 'text' && typeof part.text === 'string') text += part.text
    }
    return text
  }
  if (typeof content === 'string') return content
  return ''
}

function createMessageCache() {
  const map = new Map()
  return {
    set(agentId, entry) {
      if (!agentId) return
      map.set(agentId, entry)
    },
    get(agentId) {
      if (!agentId) return null
      return map.get(agentId) || null
    },
    delete(agentId) {
      if (agentId) map.delete(agentId)
    },
    clear() { map.clear() },
    handleClaimed(payload) {
      try {
        const agent = payload?.agent
        const message = payload?.message
        if (!agent?.id) return
        if (message?.source?.kind !== 'user') return
        const text = extractText(message).trim()
        if (!text) return
        map.set(agent.id, { text, turn: payload?.turn ?? 0, ts: Date.now() })
      } catch (_) {}
    },
  }
}

module.exports = { createMessageCache, extractText }