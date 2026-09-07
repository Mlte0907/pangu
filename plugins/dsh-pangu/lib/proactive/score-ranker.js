'use strict'

function daysSince(createdAt) {
  if (!createdAt) return Infinity
  const t = Date.parse(createdAt)
  if (Number.isNaN(t)) return Infinity
  return (Date.now() - t) / 86400000
}

function recencyScore(createdAt) {
  const d = daysSince(createdAt)
  if (d < 7) return 1.0
  if (d < 30) return 0.8
  if (d < 90) return 0.5
  return 0.3
}

function rank(results, maxMemories) {
  if (!Array.isArray(results) || results.length === 0) return []
  const scores = results.map(r => Number(r?.score) || 0)
  const max = Math.max(...scores, 0)
  const scored = results.map(r => {
    const score = Number(r?.score) || 0
    const relevance = max > 0 ? Math.min(1.0, score / max) : 0
    const importance = Number(r?.importance) || 3
    const importanceNorm = importance / 5.0
    const recency = recencyScore(r?.created_at || r?.createdAt)
    const finalScore = 0.5 * relevance + 0.3 * importanceNorm + 0.2 * recency
    return { ...r, relevance, recency, finalScore }
  })
  scored.sort((a, b) => b.finalScore - a.finalScore)
  const limit = Number(maxMemories) > 0 ? Number(maxMemories) : 5
  return scored.slice(0, limit)
}

module.exports = { rank, recencyScore, daysSince }