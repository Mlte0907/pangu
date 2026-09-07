'use strict'

function extractResults(data) {
  const text = data?.result?.content?.[0]?.text
  if (!text) return []
  let parsed
  try { parsed = JSON.parse(text) } catch (_) {
    const e = new Error('json parse failed')
    e.name = 'SyntaxError'
    throw e
  }
  const results = parsed?.results
  if (!Array.isArray(results)) return []
  return results.map(r => ({
    id: r?.id != null ? String(r.id) : (r?.drawer_id != null ? String(r.drawer_id) : null),
    content: typeof r?.content === 'string' ? r.content : '',
    wing: r?.wing || '',
    tags: Array.isArray(r?.tags) ? r.tags : [],
    score: Number(r?.score) || 0,
    importance: Number(r?.importance) || 3,
    created_at: r?.created_at || r?.createdAt || null,
  }))
}

async function search({ query, wing, room }, client, timeoutMs) {
  const args = { query: String(query || '') }
  if (wing) args.wing = wing
  if (room) args.room = room
  const res = await client.call('pangu_search_memories', args, timeoutMs)
  if (!res.ok) return { ok: false, error: res.error }
  try {
    const candidates = extractResults(res.data)
    return { ok: true, candidates }
  } catch (e) {
    return { ok: false, error: { kind: 'format', message: 'result parse failed: ' + (e?.message || '') } }
  }
}

module.exports = { search, extractResults }