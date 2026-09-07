'use strict'

function digest(text, sensitiveFilter) {
  let s = typeof text === 'string' ? text : ''
  if (sensitiveFilter) {
    try { s = sensitiveFilter(s) } catch (_) {}
  }
  if (s.length > 50) s = s.slice(0, 50) + '...'
  return s
}

function createStatsCollector({ logger, sensitiveFilter } = {}) {
  const counters = {
    totalAttempts: 0,
    successCount: 0,
    failCount: 0,
    latencySum: 0,
    tokensSum: 0,
    circuitBreakCount: 0,
    consolidateSuccess: 0,
    consolidateFail: 0,
  }

  function log(obj) {
    try { logger?.info?.(JSON.stringify(obj)) } catch (_) {}
  }

  function recordInject(event) {
    const status = event?.status || 'fail'
    if (status === 'success' || status === 'fail') {
      counters.totalAttempts++
      if (status === 'success') counters.successCount++
      else counters.failCount++
      if (typeof event?.latencyMs === 'number') counters.latencySum += event.latencyMs
      if (status === 'success' && typeof event?.tokensUsed === 'number') counters.tokensSum += event.tokensUsed
    }
    log({
      event: 'pangu.inject',
      sessionId: event?.sessionId,
      agentId: event?.agentId,
      turn: event?.turn,
      queryDigest: digest(event?.query, sensitiveFilter),
      resultCount: event?.resultCount,
      injectedCount: event?.injectedCount,
      latencyMs: event?.latencyMs,
      tokensUsed: event?.tokensUsed,
      status,
      failReason: event?.failReason || null,
      ts: Date.now(),
    })
  }

  function recordConsolidate(event) {
    const status = event?.status || 'fail'
    if (status === 'success') counters.consolidateSuccess++
    else if (status === 'fail') counters.consolidateFail++
    log({
      event: 'pangu.consolidate',
      sessionId: event?.sessionId,
      turn: event?.turn,
      contentDigest: digest(event?.content, sensitiveFilter),
      wing: event?.wing,
      tags: event?.tags,
      importance: event?.importance,
      status,
      memoryId: event?.memoryId || null,
      ts: Date.now(),
    })
  }

  function recordCircuitBreak(sessionId) {
    counters.circuitBreakCount++
    log({ event: 'pangu.circuit_break', sessionId, consecutiveFailures: 3, ts: Date.now() })
  }

  function query() {
    const attempts = counters.totalAttempts
    return {
      totalAttempts: counters.totalAttempts,
      successCount: counters.successCount,
      failCount: counters.failCount,
      avgLatencyMs: attempts ? counters.latencySum / attempts : 0,
      avgTokensUsed: counters.successCount ? counters.tokensSum / counters.successCount : 0,
      circuitBreakCount: counters.circuitBreakCount,
      consolidateSuccess: counters.consolidateSuccess,
      consolidateFail: counters.consolidateFail,
    }
  }

  function reset() {
    counters.totalAttempts = 0
    counters.successCount = 0
    counters.failCount = 0
    counters.latencySum = 0
    counters.tokensSum = 0
    counters.circuitBreakCount = 0
    counters.consolidateSuccess = 0
    counters.consolidateFail = 0
  }

  return { recordInject, recordConsolidate, recordCircuitBreak, query, reset }
}

module.exports = { createStatsCollector }