'use strict'

const fsp = require('fs/promises')
const os = require('os')
const path = require('path')

const CONFIG_PATH = path.join(os.homedir(), '.pangu', 'config.json')

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
  return { injection: cfg, apiKey }
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
  const envKey = typeof process.env.PANGU_API_KEY === 'string' ? process.env.PANGU_API_KEY : ''
  if (envKey) result.apiKey = envKey
  return result
}

module.exports = { loadInjectionConfig, validateInjectionConfig: validate, DEFAULTS, CONFIG_PATH }