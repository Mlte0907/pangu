// 用 harness 同款 MCP SDK 模拟 mcp-client 插件的完整握手流程
// 用法: node mcp_sdk_probe.mjs <url> [apiKey]
const url = process.argv[2] || 'http://127.0.0.1:19529/mcp'
const apiKey = process.argv[3] || ''

const { StreamableHTTPClientTransport } = await import(
  '/home/xiaoxin/deepseek-harness/apps/cli/node_modules/@deepseek-ai/dsh-mcp-client/node_modules/@modelcontextprotocol/sdk/dist/esm/client/streamableHttp.js'
)
const { Client } = await import(
  '/home/xiaoxin/deepseek-harness/apps/cli/node_modules/@deepseek-ai/dsh-mcp-client/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js'
)

const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' }
if (apiKey) headers['X-API-Key'] = apiKey

const transport = new StreamableHTTPClientTransport(new URL(url), {
  requestInit: { headers },
})
const client = new Client({ name: 'pangu-probe', version: '0.0.1' })

try {
  await client.connect(transport, { timeoutMs: 15000 })
  console.log('CONNECTED. serverInfo:', JSON.stringify(client.getServerVersion()))
  const tools = await client.listTools()
  console.log('TOOLS:', tools.tools.length)
  for (const t of tools.tools.slice(0, 8)) console.log(' -', t.name)
  // 真实调用一次
  const r = await client.callTool({ name: 'pangu_fts_search', arguments: { query: '盘古修复验证', limit: 2 } })
  const text = r?.content?.map((c) => c.text || '').join('\n') || JSON.stringify(r).slice(0, 200)
  console.log('CALL RESULT:', String(text).slice(0, 200))
} catch (e) {
  console.error('PROBE FAILED:', e.message)
  console.error(e.cause ? `cause: ${e.cause}` : '')
  process.exitCode = 1
} finally {
  try {
    await client.close()
  } catch {}
}
