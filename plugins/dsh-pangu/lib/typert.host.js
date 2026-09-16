/**
 * dsh-pangu Host 面 Typert 清单 v4（dsh 0.1.6 兼容）。
 * panguDashboard.data 扩展宫殿/图谱统计与健康详情;服务清单与 v2 兼容。
 * panguAdminKeys: 钥匙/房间管理。
 */
const { z } = require('zod')

// ── Schema 工厂（延迟创建，供 codec.create 引用）──
let _dashboardData$v
const _dashboardData = () => (_dashboardData$v ??= z.object({
  stats: z.object({
    ok: z.boolean(), error: z.string().optional(),
    total: z.number().optional(), wings: z.number().optional(), rooms: z.number().optional(),
    kgEntities: z.number().optional(), kgRelations: z.number().optional(),
    byWing: z.record(z.any()).optional(), health: z.string().optional(),
    healthScore: z.number().optional(), version: z.string().optional(),
    uptimeSeconds: z.number().optional(), ts: z.number().optional(),
  }).optional(),
  usage: z.object({
    keySet: z.boolean(), base: z.string().optional(), model: z.string().optional(),
    provider: z.string().optional(),
    usage: z.object({
      rolling: z.object({ status: z.string().optional(), percent: z.number().optional(), resetsAt: z.string().optional() }).optional(),
      weekly: z.object({ status: z.string().optional(), percent: z.number().optional(), resetsAt: z.string().optional() }).optional(),
      monthly: z.object({ status: z.string().optional(), percent: z.number().optional(), resetsAt: z.string().optional() }).optional(),
    }).optional(),
  }).optional(),
}))

let _ping$v
const _ping = () => (_ping$v ??= z.object({ pong: z.boolean() }))

let _deepHealth$v
const _deepHealth = () => (_deepHealth$v ??= z.object({
  ok: z.boolean(), status: z.string().optional(),
  checks: z.array(z.object({ name: z.string(), status: z.string() })).optional(),
  error: z.string().optional(),
}))

let _backupResult$v
const _backupResult = () => (_backupResult$v ??= z.object({
  ok: z.boolean(), backupId: z.string().optional(),
  memories: z.number().optional(), size: z.number().optional(), error: z.string().optional(),
}))

let _events$v
const _events = () => (_events$v ??= z.object({
  count: z.number(), lastTs: z.number().optional(), connected: z.boolean().optional(),
  events: z.array(z.object({ ts: z.number(), type: z.string(), topic: z.string().optional() })).optional(),
}))

let _addResult$v
const _addResult = () => (_addResult$v ??= z.object({
  ok: z.boolean(), id: z.string().optional(), wing: z.string().optional(), error: z.string().optional(),
}))

let _kgData$v
const _kgData = () => (_kgData$v ??= z.object({
  ok: z.boolean(),
  nodes: z.array(z.object({ id: z.string(), name: z.string().optional(), type: z.string().optional(), description: z.string().optional(), memory_count: z.number().optional() })).optional(),
  edges: z.array(z.object({ source: z.string(), target: z.string(), predicate: z.string().optional() })).optional(),
  error: z.string().optional(),
}))

let _configData$v
const _configData = () => (_configData$v ??= z.object({
  ok: z.boolean(), config: z.record(z.any()).optional(),
}))

let _okResult$v
const _okResult = () => (_okResult$v ??= z.object({
  ok: z.boolean(), value: z.any().optional(),
}))

let _testLlmResult$v
const _testLlmResult = () => (_testLlmResult$v ??= z.object({
  ok: z.boolean(), ms: z.number().optional(), status: z.number().optional(),
  model: z.string().optional(), provider: z.string().optional(),
  baseUrl: z.string().optional(), sample: z.string().optional(), error: z.string().optional(),
}))

let _sinceCodec$v
const _sinceCodec = () => (_sinceCodec$v ??= z.number().optional())

let _addArgsCodec$v
const _addArgsCodec = () => (_addArgsCodec$v ??= z.record(z.any()))

let _patchCodec$v
const _patchCodec = () => (_patchCodec$v ??= z.record(z.any()))

let _keyList$v
const _keyList = () => (_keyList$v ??= z.object({
  keys: z.array(z.object({
    key_id: z.string(), room: z.string(), scope: z.string(),
    created_at: z.string().optional(), last_used_at: z.string().optional(), revoked_at: z.string().optional(),
  })).optional(),
}))

let _keyCreate$v
const _keyCreate = () => (_keyCreate$v ??= z.object({
  key_id: z.string(), room: z.string(), scope: z.string(), key: z.string(),
}))

let _keyRevoke$v
const _keyRevoke = () => (_keyRevoke$v ??= z.object({
  ok: z.boolean(), key_id: z.string().optional(), error: z.string().optional(),
}))

let _roomList$v
const _roomList = () => (_roomList$v ??= z.object({
  rooms: z.array(z.object({
    room: z.string(), memory_count: z.number(), chars: z.number(),
    last_write_at: z.string().optional(), key_count: z.number(),
  })).optional(),
}))

let _rekeyResult$v
const _rekeyResult = () => (_rekeyResult$v ??= z.object({
  ok: z.boolean(), room: z.string().optional(),
  revoked: z.array(z.string()).optional(),
  key_id: z.string().optional(), key: z.string().optional(), error: z.string().optional(),
}))

let _publicMemories$v
const _publicMemories = () => (_publicMemories$v ??= z.object({
  memories: z.array(z.object({
    id: z.string(), content: z.string(), tags: z.array(z.string()),
    source_room: z.string(), graduated_at: z.string().optional(),
    created_at: z.string().optional(), chars: z.number(),
  })).optional(),
  count: z.number(),
}))

const TYPERT = {
  package: 'dsh-pangu',
  face: 'host',
  schemas: [],
  invocations: [
    {
      id: 'dsh-pangu#panguDashboard/data',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'data',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#DashboardData', create: _dashboardData },
    },
    {
      id: 'dsh-pangu#panguDashboard/ping',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'ping',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#Ping', create: _ping },
    },
    {
      id: 'dsh-pangu#panguDashboard/deepHealth',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'deepHealth',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#DeepHealth', create: _deepHealth },
    },
    {
      id: 'dsh-pangu#panguDashboard/backup',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'backup',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#BackupResult', create: _backupResult },
    },
    {
      id: 'dsh-pangu#panguDashboard/events',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'events',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'since', wire: 'since', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Since', create: _sinceCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#Events', create: _events },
    },
    {
      id: 'dsh-pangu#panguDashboard/add',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'add',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#AddArgs', create: _addArgsCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#AddResult', create: _addResult },
    },
    {
      id: 'dsh-pangu#panguKG/graph',
      service: 'panguKG', namespace: 'panguKG', method: 'graph',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KGData', create: _kgData },
    },
    {
      id: 'dsh-pangu#panguConfig/get',
      service: 'panguConfig', namespace: 'panguConfig', method: 'get',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#ConfigData', create: _configData },
    },
    {
      id: 'dsh-pangu#panguConfig/save',
      service: 'panguConfig', namespace: 'panguConfig', method: 'save',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'patch', wire: 'patch', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#SavePatch', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#SaveResult', create: _okResult },
    },
    {
      id: 'dsh-pangu#panguConfig/testLlm',
      service: 'panguConfig', namespace: 'panguConfig', method: 'testLlm',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#TestLlmResult', create: _testLlmResult },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/listKeys',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listKeys',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyList', create: _keyList },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/createKey',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'createKey',
      invocation: { kind: 'direct' },
      parameters: [
        { name: 'room', wire: 'room', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Room', create: () => z.string() } },
        { name: 'scope', wire: 'scope', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Scope', create: () => z.string() } },
      ],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyCreate', create: _keyCreate },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/revokeKey',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'revokeKey',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'key_id', wire: 'key_id', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyId', create: () => z.string() } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyRevoke', create: _keyRevoke },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/listRooms',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listRooms',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RoomList', create: _roomList },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/rekeyRoom',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'rekeyRoom',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'room', wire: 'room', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#Room', create: () => z.string() } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RekeyResult', create: _rekeyResult },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/listPublicMemories',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listPublicMemories',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#PublicMemories', create: _publicMemories },
    },
  ],
  model: {
    services: [
      {
        key: 'panguDashboard', exportName: 'PanguDashboardService', tags: [],
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
        key: 'panguKG', exportName: 'PanguKGService', tags: [],
        members: [
          { kind: 'method', name: 'graph', signature: 'graph(): KGData', summary: '获取知识图谱节点与关系。' },
        ],
        types: [],
      },
      {
        key: 'panguConfig', exportName: 'PanguConfigService', tags: [],
        members: [
          { kind: 'method', name: 'get', signature: 'get(): ConfigData', summary: '读取盘古配置。' },
          { kind: 'method', name: 'save', signature: 'save(patch): SaveResult', summary: '保存盘古配置。' },
          { kind: 'method', name: 'testLlm', signature: 'testLlm(): TestLlmResult', summary: '用当前已落盘配置实际请求一次 LLM 端点，验证 provider/Base URL/模型/Key 组合可用。' },
        ],
        types: [],
      },
      {
        key: 'panguAdminKeys', exportName: 'PanguAdminKeysService', tags: [],
        members: [
          { kind: 'method', name: 'listKeys', signature: 'listKeys(): KeyList', summary: '列出所有钥匙。' },
          { kind: 'method', name: 'createKey', signature: 'createKey(room, scope): KeyCreate', summary: '创建钥匙（需 admin 凭据）。' },
          { kind: 'method', name: 'revokeKey', signature: 'revokeKey(key_id): KeyRevoke', summary: '吊销钥匙。' },
          { kind: 'method', name: 'listRooms', signature: 'listRooms(): RoomList', summary: '房间总览：按 tenant_id 聚合记忆条数、字符体积、钥匙数。' },
          { kind: 'method', name: 'rekeyRoom', signature: 'rekeyRoom(room): RekeyResult', summary: '重发钥匙：吊销旧钥+创建新钥。' },
          { kind: 'method', name: 'listPublicMemories', signature: 'listPublicMemories(): PublicMemories', summary: '公共区知识卡片：visibility=public 的记忆，只读。' },
        ],
        types: [],
      },
    ],
    events: [],
    objects: [],
  },
}

module.exports = { TYPERT }
