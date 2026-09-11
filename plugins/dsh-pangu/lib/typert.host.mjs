/**
 * dsh-pangu Host 面 Typert 清单 v3。
 * panguDashboard.data 扩展宫殿/图谱统计与健康详情;服务清单与 v2 兼容。
 */
import { z } from 'zod'

const _string = z.string()
const _bool = z.boolean()
const _number = z.number()

const statsSchema = z.object({
  ok: _bool,
  error: _string.optional(),
  total: _number.optional(),
  wings: _number.optional(),
  rooms: _number.optional(),
  kgEntities: _number.optional(),
  kgRelations: _number.optional(),
  byWing: z.record(z.any()).optional(),
  health: _string.optional(),
  healthScore: _number.optional(),
  version: _string.optional(),
  uptimeSeconds: _number.optional(),
  ts: _number.optional(),
})

const usageWindowSchema = z.object({
  status: _string.optional(),
  percent: _number.optional(),
  resetsAt: _string.optional(),
})

const usageSchema = z.object({
  rolling: usageWindowSchema.optional(),
  weekly: usageWindowSchema.optional(),
  monthly: usageWindowSchema.optional(),
})

const usageInfoSchema = z.object({
  keySet: _bool,
  base: _string.optional(),
  model: _string.optional(),
  provider: _string.optional(),
  usage: usageSchema.optional(),
})

const dashboardDataSchema = z.object({
  stats: statsSchema.optional(),
  usage: usageInfoSchema.optional(),
})

const kgNodeSchema = z.object({
  id: _string,
  name: _string.optional(),
  type: _string.optional(),
  description: _string.optional(),
  memory_count: _number.optional(),
})

const kgEdgeSchema = z.object({
  source: _string,
  target: _string,
  predicate: _string.optional(),
})

const kgDataSchema = z.object({
  ok: _bool,
  nodes: z.array(kgNodeSchema).optional(),
  edges: z.array(kgEdgeSchema).optional(),
  error: _string.optional(),
})

const configDataSchema = z.object({
  ok: _bool,
  config: z.record(z.any()).optional(),
})

const backupResultSchema = z.object({
  ok: _bool,
  backupId: _string.optional(),
  memories: _number.optional(),
  size: _number.optional(),
  error: _string.optional(),
})

const eventsSchema = z.object({
  count: _number,
  lastTs: _number.optional(),
  connected: _bool.optional(),
  events: z.array(z.object({ ts: _number, type: _string, topic: _string.optional() })).optional(),
})

const addResultSchema = z.object({
  ok: _bool,
  id: _string.optional(),
  wing: _string.optional(),
  error: _string.optional(),
})

const deepHealthCheckSchema = z.object({
  name: _string,
  status: _string,
})

const deepHealthSchema = z.object({
  ok: _bool,
  status: _string.optional(),
  checks: z.array(deepHealthCheckSchema).optional(),
  error: _string.optional(),
})

const okResultSchema = z.object({
  ok: _bool,
  value: z.any().optional(),
})

const testLlmResultSchema = z.object({
  ok: _bool,
  ms: _number.optional(),
  status: _number.optional(),
  model: _string.optional(),
  provider: _string.optional(),
  baseUrl: _string.optional(),
  sample: _string.optional(),
  error: _string.optional(),
})

export const TYPERT = {
  package: 'dsh-pangu',
  face: 'host',
  schemas: [],
  invocations: [
    {
      id: 'dsh-pangu#panguDashboard/data',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'data',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#DashboardData', schema: dashboardDataSchema },
    },
    {
      id: 'dsh-pangu#panguDashboard/ping',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'ping',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#Ping', schema: z.object({ pong: _bool }) },
    },
    {
      id: 'dsh-pangu#panguDashboard/deepHealth',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'deepHealth',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#DeepHealth', schema: deepHealthSchema },
    },
    {
      id: 'dsh-pangu#panguDashboard/backup',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'backup',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#BackupResult', schema: backupResultSchema },
    },
    {
      id: 'dsh-pangu#panguDashboard/events',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'events',
      invocation: { kind: 'direct' },
      parameters: [{
        name: 'since',
        wire: 'since',
        source: 'json',
        schema: z.number().optional(),
        codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Since', schema: z.number().optional() },
      }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#Events', schema: eventsSchema },
    },
    {
      id: 'dsh-pangu#panguDashboard/add',
      service: 'panguDashboard',
      namespace: 'panguDashboard',
      method: 'add',
      invocation: { kind: 'direct' },
      parameters: [{
        name: 'args',
        wire: 'args',
        source: 'json',
        schema: z.record(z.any()),
        codec: { mode: 'strict', typeSymbol: 'dsh-pangu#AddArgs', schema: z.record(z.any()) },
      }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#AddResult', schema: addResultSchema },
    },
    {
      id: 'dsh-pangu#panguKG/graph',
      service: 'panguKG',
      namespace: 'panguKG',
      method: 'graph',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KGData', schema: kgDataSchema },
    },
    {
      id: 'dsh-pangu#panguConfig/get',
      service: 'panguConfig',
      namespace: 'panguConfig',
      method: 'get',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#ConfigData', schema: configDataSchema },
    },
    {
      id: 'dsh-pangu#panguConfig/save',
      service: 'panguConfig',
      namespace: 'panguConfig',
      method: 'save',
      invocation: { kind: 'direct' },
      parameters: [{
        name: 'patch',
        wire: 'patch',
        source: 'json',
        schema: z.record(z.any()),
        codec: { mode: 'strict', typeSymbol: 'dsh-pangu#SavePatch', schema: z.record(z.any()) },
      }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#SaveResult', schema: okResultSchema },
    },
    {
      id: 'dsh-pangu#panguConfig/testLlm',
      service: 'panguConfig',
      namespace: 'panguConfig',
      method: 'testLlm',
      invocation: { kind: 'direct' },
      parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#TestLlmResult', schema: testLlmResultSchema },
    },
  ],
  model: {
    services: [
      {
        key: 'panguDashboard',
        exportName: 'PanguDashboardService',
        tags: [],
        members: [
          { kind: 'method', name: 'data', signature: 'data(): DashboardData', summary: '抓取盘古记忆/宫殿/图谱统计、服务健康与用量。' },
          { kind: 'method', name: 'ping', signature: 'ping(): { pong: boolean }', summary: '插件探活。' },
          { kind: 'method', name: 'deepHealth', signature: 'deepHealth(): DeepHealth', summary: '深度健康检查(结构/记忆/嵌入),按需调用。' },
          { kind: 'method', name: 'backup', signature: 'backup(): BackupResult', summary: '创建记忆备份快照。' },
          { kind: 'method', name: 'events', signature: 'events(since): Events', summary: '获取 since 之后的事件(实时通道缓冲),用于增量刷新。' },
          { kind: 'method', name: 'add', signature: 'add(args): AddResult', summary: '快速添加一条记忆片段。' },
        ],
        types: [],
      },
      {
        key: 'panguKG',
        exportName: 'PanguKGService',
        tags: [],
        members: [
          { kind: 'method', name: 'graph', signature: 'graph(): KGData', summary: '获取知识图谱节点与关系。' },
        ],
        types: [],
      },
      {
        key: 'panguConfig',
        exportName: 'PanguConfigService',
        tags: [],
        members: [
          { kind: 'method', name: 'get', signature: 'get(): ConfigData', summary: '读取盘古配置。' },
          { kind: 'method', name: 'save', signature: 'save(patch): SaveResult', summary: '保存盘古配置。' },
          { kind: 'method', name: 'testLlm', signature: 'testLlm(): TestLlmResult', summary: '用当前已落盘配置实际请求一次 LLM 端点，验证 provider/Base URL/模型/Key 组合可用。' },
        ],
        types: [],
      },
    ],
    events: [],
    objects: [],
  },
}

export default TYPERT
