'use strict'

const PATTERNS = [
  /sk-[A-Za-z0-9]{20,}/,
  /AKIA[0-9A-Z]{16}/,
  /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/,
  /-----BEGIN [A-Z ]+PRIVATE KEY-----/,
  /(password|passwd|pwd)\s*[:=]\s*\S+/i,
  /(token|api_key|apikey|secret)\s*[:=]\s*\S+/i,
  /Bearer\s+[A-Za-z0-9_.-]+/,
]

function filterSensitive(text) {
  if (typeof text !== 'string' || text.length === 0) return text || ''
  let out = text
  for (const re of PATTERNS) {
    out = out.replace(re, '[REDACTED]')
  }
  return out
}

module.exports = { filterSensitive, PATTERNS }