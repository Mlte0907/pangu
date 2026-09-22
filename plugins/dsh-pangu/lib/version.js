/**
 * 版本号比较。
 *
 * 为什么单独一个模块：设置页要判断"本机跑的是不是落后于上游"，而版本比较
 * 必须**按段比数字** —— 字符串比较会得出 `0.4.10 < 0.4.9` 这种荒谬结论。
 * 抽成纯函数也便于单测（调用方在宿主进程里，不方便直接测）。
 *
 * 容错：容忍 `v` 前缀（`v0.4.1`）、非数字尾缀（`0.4.1-beta`）、位数不齐。
 */

/** 把版本号拆成数字数组：`v0.4.1-beta` → [0, 4, 1]。非数字开头则返回空数组。 */
function parseVersion(v) {
  const s = String(v == null ? '' : v).trim().replace(/^[vV]/, '')
  const m = s.match(/^\d+(?:\.\d+)*/)
  if (!m) return []
  return m[0].split('.').map((x) => parseInt(x, 10))
}

/**
 * a 是否**严格新于** b。任一方无法解析为版本号时返回 false（不敢误报"有新版本"）。
 */
function isNewer(a, b) {
  const va = parseVersion(a)
  const vb = parseVersion(b)
  if (!va.length || !vb.length) return false
  const n = Math.max(va.length, vb.length)
  for (let i = 0; i < n; i++) {
    const x = va[i] || 0
    const y = vb[i] || 0
    if (x > y) return true
    if (x < y) return false
  }
  return false
}

module.exports = { parseVersion, isNewer }
