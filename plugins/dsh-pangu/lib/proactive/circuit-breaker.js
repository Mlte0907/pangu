'use strict'

const TRIP_THRESHOLD = 3

function createCircuitBreaker({ onTrip } = {}) {
  const states = new Map()

  function get(sessionId) {
    let s = states.get(sessionId)
    if (!s) { s = { consecutiveFailures: 0, tripped: false, authFailed: false }; states.set(sessionId, s) }
    return s
  }

  function shouldAllow(sessionId) {
    const s = get(sessionId)
    return !(s.tripped || s.authFailed)
  }

  function recordFailure(sessionId) {
    const s = get(sessionId)
    s.consecutiveFailures++
    if (s.consecutiveFailures >= TRIP_THRESHOLD && !s.tripped) {
      s.tripped = true
      try { onTrip?.(sessionId) } catch (_) {}
    }
    return s
  }

  function recordAuthFailure(sessionId) {
    const s = get(sessionId)
    s.authFailed = true
  }

  function recordSuccess(sessionId) {
    const s = get(sessionId)
    s.consecutiveFailures = 0
  }

  function onSessionStart(sessionId) {
    if (sessionId) states.set(sessionId, { consecutiveFailures: 0, tripped: false, authFailed: false })
  }

  function onDisposed(sessionId) {
    if (sessionId) states.delete(sessionId)
  }

  function clear() { states.clear() }

  return { shouldAllow, recordFailure, recordAuthFailure, recordSuccess, onSessionStart, onDisposed, clear }
}

module.exports = { createCircuitBreaker, TRIP_THRESHOLD }