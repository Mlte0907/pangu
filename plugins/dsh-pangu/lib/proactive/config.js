'use strict'

const fsp = require('fs/promises')
const fs = require('fs')
const os = require('os')
const path = require('path')

const CONFIG_PATH = path.join(os.homedir(), '.pangu', 'config.json')

/**
 * 解析盘古身份凭据（同步版，供 fetchJson 这类没有 await 的调用点复用）。
 *
 * 唯一来源：config.json 的 api_key —— 即插件设置页「盘古凭据」字段。
 *
 * 明确**不做**环境变量 / `~/.pangu/.mcp_key` 文件回落（2026-09-21）：
 * 插件视作客户端，设置页填什么就用什么。隐式回落会让"设置页显示指向 A、
 * 实际却用了 B 的凭据"这类问题无从解释（曾表现为地址已改本地、凭据仍是
 * 云端 pgp_ 令牌 → 每个请求 401）。
 *
 * @param {object} [parsedRaw] 已解析的 config.json，避免重复读盘
 * @returns {string} 凭据原文，未配置时为空串
*/
function readStoredApiKey(parsedRaw) {
  try {
    const raw = parsedRaw ?? JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'))
    if (typeof raw?.api_key === 'string') return raw.api_key.trim()
  } catch (_) { /* config.json 缺失或损坏 = 未配置 */ }
  return ''
}

const DEFAULTS = {
  enabled: true,
  max_memories: 5,
  token_budget: 500,
  dedup_scope: 'session',
  search_timeout_ms: 2000,
  consolidate_enabled: true,
  consolidate_max_per_turn: 1,
  wing_map: {},
}

function validate(raw, logger) {
  const cfg = { ...DEFAULTS }
  const warn = (msg) => { try { logger?.warn?.('[pangu.injection] config fallback: ' + msg) } catch (_) {} }
  if (!raw || typeof raw !== 'object') return { injection: cfg, apiKey: '' }

  const inj = raw.injection
  if (inj && typeof inj === 'object') {
    if (typeof inj.enabled === 'boolean') cfg.enabled = inj.enabled
    else if ('enabled' in inj) warn('enabled non-boolean')

    if (Number.isInteger(inj.max_memories) && inj.max_memories >= 1 && inj.max_memories <= 10) cfg.max_memories = inj.max_memories
    else if ('max_memories' in inj) warn('max_memories out of range')

    if (Number.isInteger(inj.token_budget) && inj.token_budget >= 100 && inj.token_budget <= 2000) cfg.token_budget = inj.token_budget
    else if ('token_budget' in inj) warn('token_budget out of range')

    if (inj.dedup_scope === 'session' || inj.dedup_scope === 'global') cfg.dedup_scope = inj.dedup_scope
    else if ('dedup_scope' in inj) warn('dedup_scope invalid')

    if (Number.isInteger(inj.search_timeout_ms) && inj.search_timeout_ms >= 500 && inj.search_timeout_ms <= 5000) cfg.search_timeout_ms = inj.search_timeout_ms
    else if ('search_timeout_ms' in inj) warn('search_timeout_ms out of range')

    if (typeof inj.consolidate_enabled === 'boolean') cfg.consolidate_enabled = inj.consolidate_enabled
    else if ('consolidate_enabled' in inj) warn('consolidate_enabled non-boolean')

    if (Number.isInteger(inj.consolidate_max_per_turn) && inj.consolidate_max_per_turn >= 1 && inj.consolidate_max_per_turn <= 5) cfg.consolidate_max_per_turn = inj.consolidate_max_per_turn
    else if ('consolidate_max_per_turn' in inj) warn('consolidate_max_per_turn out of range')

    if (inj.wing_map && typeof inj.wing_map === 'object' && !Array.isArray(inj.wing_map)) cfg.wing_map = inj.wing_map
    else if ('wing_map' in inj) warn('wing_map non-object')
  }

  const apiKey = typeof raw.api_key === 'string' ? raw.api_key : ''
  const baseUrl = typeof raw.pangu_base_url === 'string' ? raw.pangu_base_url.trim() : ''
  return { injection: cfg, apiKey, baseUrl }
}

async function loadInjectionConfig(logger) {
  let raw = {}
  try {
    raw = JSON.parse(await fsp.readFile(CONFIG_PATH, 'utf8'))
  } catch (e) {
    try { logger?.warn?.('[pangu.injection] config file unreadable: ' + (e.code || String(e))) } catch (_) {}
    raw = {}
  }
  const result = validate(raw, logger)
  // 唯一来源：config.json 的 api_key（设置页填写的盘古凭据）
  result.apiKey = readStoredApiKey(raw)
  return result
}

module.exports = { loadInjectionConfig, readStoredApiKey, validateInjectionConfig: validate, DEFAULTS, CONFIG_PATH }