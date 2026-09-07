'use strict'

const scoreRanker = require('./score-ranker')
const budgetAllocator = require('./budget-allocator')
const contextFormatter = require('./context-formatter')
const memoryFetcher = require('./memory-fetcher')

function createInjectionPipeline(deps) {
  const {
    getConfig, messageCache, client, circuitBreaker, dedupTracker,
    sensitiveFilter, statsCollector,
  } = deps

  function record(stats, event) {
    try { stats?.recordInject?.(event) } catch (_) {}
  }

  async function run(assembly, context) {
    const agentId = context?.agent?.id
    const sessionId = context?.agent?.session?.id || agentId
    const turn = context?.agent?.session?.turn ?? 0
    const startedAt = Date.now()
    const latency = () => Date.now() - startedAt

    let config
    try { config = (getConfig()?.injection) || {} } catch (_) { config = {} }

    if (config.enabled === false) {
      record(statsCollector, { sessionId, agentId, turn, status: 'skip', failReason: 'disabled', latencyMs: latency() })
      return
    }

    const cached = messageCache.get(agentId)
    const query = (cached?.text || '').trim()
    if (!query || query.length < 2) {
      record(statsCollector, { sessionId, agentId, turn, query, status: 'skip', failReason: 'empty_query', latencyMs: latency() })
      return
    }

    if (!circuitBreaker.shouldAllow(sessionId)) {
      record(statsCollector, { sessionId, agentId, turn, query, status: 'circuit', latencyMs: latency() })
      return
    }

    const searchRes = await memoryFetcher.search({ query }, client, config.search_timeout_ms)
    if (!searchRes.ok) {
      const kind = searchRes.error?.kind
      if (kind === 'auth') circuitBreaker.recordAuthFailure(sessionId)
      else circuitBreaker.recordFailure(sessionId)
      record(statsCollector, { sessionId, agentId, turn, query, status: 'fail', failReason: kind, latencyMs: latency() })
      return
    }

    const ranked = scoreRanker.rank(searchRes.candidates, config.max_memories)

    if (ranked.length === 0) {
      circuitBreaker.recordSuccess(sessionId)
      record(statsCollector, { sessionId, agentId, turn, query, status: 'skip', failReason: 'zero_results', resultCount: 0, latencyMs: latency() })
      return
    }

    const deduped = dedupTracker.filter(ranked, sessionId)
    if (deduped.length === 0) {
      circuitBreaker.recordSuccess(sessionId)
      record(statsCollector, { sessionId, agentId, turn, query, status: 'skip', failReason: 'all_deduped', resultCount: ranked.length, latencyMs: latency() })
      return
    }

    const { injected, tokensUsed } = budgetAllocator.allocate(deduped, config.token_budget)

    const filtered = injected.map(c => ({ ...c, content: sensitiveFilter(c.content || '') }))
    const text = contextFormatter.format(filtered)
    if (!text) {
      circuitBreaker.recordSuccess(sessionId)
      record(statsCollector, { sessionId, agentId, turn, query, status: 'success', resultCount: searchRes.candidates.length, injectedCount: 0, tokensUsed, latencyMs: latency() })
      return
    }

    assembly.contexts.push({ name: 'pangu-memory', text })
    dedupTracker.markInjected(sessionId, injected.map(c => c.id).filter(Boolean))
    circuitBreaker.recordSuccess(sessionId)
    record(statsCollector, { sessionId, agentId, turn, query, status: 'success', resultCount: searchRes.candidates.length, injectedCount: injected.length, tokensUsed, latencyMs: latency() })
  }

  return { run }
}

module.exports = { createInjectionPipeline }