'use strict'

function format(memories) {
  if (!Array.isArray(memories) || memories.length === 0) return null
  let text = '[盘古记忆系统 - 相关历史记忆]\n'
  text += '以下是与当前任务相关的历史记忆，请参考避免重复踩坑：\n\n'
  for (const m of memories) {
    const content = typeof m?.content === 'string' ? m.content : ''
    const wing = m?.wing || 'default'
    const tags = Array.isArray(m?.tags) ? m.tags.join(', ') : ''
    text += `- [${wing}] ${content}`
    if (tags) text += ` (标签: ${tags})`
    text += '\n'
  }
  text += '[/盘古记忆系统]\n'
  return text
}

module.exports = { format }