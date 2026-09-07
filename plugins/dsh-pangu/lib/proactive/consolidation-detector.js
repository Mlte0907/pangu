'use strict'

const memoryFetcher = require('./memory-fetcher')

const ROOT_CAUSE_RE = /(根因|原因是|因为|导致|修复|改为|解决方案|fix|root cause)/i
const CONCLUSION_RE = /(结论|决定|因此|综上|decided|conclusion|therefore)/i
const ENV_FACT_RE = /(版本|端口|路径|配置|环境|version|port|path)/i

function tokenize(text) {
  return (text || '').toLowerCase().split(/[\s,，。.;；!！?？]+/).filter(Boolean)
}

function jaccard(a, b) {
  const sa = new Set(tokenize(a))
  const sb = new Set(tokenize(b))
  let inter = 0
  for (const t of sa) if (sb.has(t)) inter++
  const union = sa.size + sb.size - inter
  if (union === 0) return 0
  return inter / union
}

function detect(text) {
  if (typeof text !== 'string' || text.length === 0) return { shouldWrite: false }
  let match, importance, tags, keyword
  if ((match = text.match(ROOT_CAUSE_RE))) {
    importance = 4; tags = ['root-cause', 'fix']; keyword = match[0]
  } else if ((match = text.match(CONCLUSION_RE))) {
    importance = 4; tags = ['conclusion']; keyword = match[0]
  } else if ((match = text.match(ENV_FACT_RE))) {
    const last = text.trim().slice(-1)
    if (last === '?' || last === '？' || last === '!' || last === '！') return { shouldWrite: false }
    importance = 3; tags = ['env-fact']; keyword = match[0]
  } else {
    return { shouldWrite: false }
  }
  const idx = text.indexOf(keyword)
  const start = Math.max(0, idx - 50)
  const end = Math.min(text.length, idx + keyword.length + 50)
  let content = '[自动沉淀] ' + text.slice(start, end)
  if (content.length > 500) content = content.slice(0, 500)
  return { shouldWrite: true, content, importance, tags }
}

async function checkDuplicate(content, client, timeoutMs, threshold = 0.85) {
  try {
    const res = await memoryFetcher.search({ query: content.slice(0, 100) }, client, timeoutMs)
    if (!res.ok || !res.candidates) return false
    for (const c of res.candidates.slice(0, 10)) {
      if (jaccard(content, c.content) > threshold) return true
    }
    return false
  } catch (_) {
    return false
  }
}

module.exports = { detect, checkDuplicate, jaccard, tokenize }