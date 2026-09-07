'use strict'

const DEFAULT_BASE = 'http://127.0.0.1:19529'

function classifyError(e, res) {
  if (res) {
    if (res.status === 401 || res.status === 403) return { kind: 'auth', message: 'HTTP ' + res.status }
  }
  const name = e?.name || ''
  const code = e?.code || ''
  if (name === 'AbortError' || name === 'TimeoutError') return { kind: 'timeout', message: 'request timeout' }
  if (code === 'ECONNREFUSED' || code === 'ENOTFOUND' || code === 'ECONNRESET' || code === 'EAI_AGAIN') {
    return { kind: 'unreachable', message: code + ' ' + (e?.message || '') }
  }
  if (name === 'SyntaxError') return { kind: 'format', message: 'json parse failed: ' + (e?.message || '') }
  return { kind: 'unknown', message: String(e?.message || e || 'unknown') }
}

function createPanguMcpClient({ apiKey, baseUrl, logger } = {}) {
  const base = baseUrl || DEFAULT_BASE
  const key = typeof apiKey === 'string' ? apiKey : ''

  async function call(toolName, args, timeoutMs) {
    const timeout = Number(timeoutMs) > 0 ? Number(timeoutMs) : 2000
    let res
    try {
      res = await fetch(base + '/mcp', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(key ? { authorization: 'Bearer ' + key } : {}),
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'tools/call',
          params: { name: toolName, arguments: args || {} },
        }),
        signal: AbortSignal.timeout(timeout),
      })
    } catch (e) {
      return { ok: false, error: classifyError(e, null) }
    }

    if (!res.ok) {
      return { ok: false, error: classifyError(null, res) }
    }

    let body
    try {
      body = await res.json()
    } catch (e) {
      return { ok: false, error: classifyError(e, null) }
    }
    return { ok: true, data: body }
  }

  return { call }
}

module.exports = { createPanguMcpClient, classifyError, DEFAULT_BASE }