'use strict'

const SINGLE_MAX = 200
const MIN_KEEP = 20
const TOKEN_FACTOR = 1.5

function allocate(candidates, tokenBudget) {
  const budget = Number(tokenBudget) > 0 ? Number(tokenBudget) : 500
  const injected = []
  let tokensUsed = 0

  if (!Array.isArray(candidates)) return { injected, tokensUsed }

  for (const c of candidates) {
    let content = typeof c?.content === 'string' ? c.content : ''
    if (content.length > SINGLE_MAX) content = content.slice(0, SINGLE_MAX) + '…'
    const estTokens = Math.ceil(content.length * TOKEN_FACTOR)

    if (tokensUsed + estTokens <= budget) {
      injected.push({ ...c, content })
      tokensUsed += estTokens
      continue
    }

    const remaining = budget - tokensUsed
    if (remaining <= 0) break
    const truncatedLen = Math.floor(remaining / TOKEN_FACTOR)
    if (truncatedLen >= MIN_KEEP) {
      injected.push({ ...c, content: content.slice(0, truncatedLen) + '…' })
      tokensUsed = budget
    }
    break
  }

  return { injected, tokensUsed }
}

module.exports = { allocate, SINGLE_MAX, MIN_KEEP, TOKEN_FACTOR }