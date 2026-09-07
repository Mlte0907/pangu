'use strict'

const GLOBAL_KEY = '__global__'
const GLOBAL_LIMIT = 10000

function createDedupTracker(scope = 'session') {
  const maps = new Map()

  function getSet(key) {
    let s = maps.get(key)
    if (!s) { s = new Set(); maps.set(key, s) }
    return s
  }

  function keyFor(sessionId) {
    return scope === 'global' ? GLOBAL_KEY : sessionId
  }

  function filter(candidates, sessionId) {
    if (!Array.isArray(candidates)) return []
    const set = getSet(keyFor(sessionId))
    return candidates.filter(c => c && c.id != null && !set.has(c.id))
  }

  function markInjected(sessionId, ids) {
    const set = getSet(keyFor(sessionId))
    for (const id of ids || []) set.add(id)
    if (scope === 'global' && set.size > GLOBAL_LIMIT) {
      maps.set(GLOBAL_KEY, new Set())
    }
  }

  function onSessionStart(sessionId) {
    if (scope !== 'global' && sessionId) maps.set(sessionId, new Set())
  }

  function onDisposed(sessionId) {
    if (scope !== 'global' && sessionId) maps.delete(sessionId)
  }

  function clear() { maps.clear() }

  return { filter, markInjected, onSessionStart, onDisposed, clear }
}

module.exports = { createDedupTracker, GLOBAL_LIMIT }