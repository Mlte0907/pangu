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
  versions: z.object({ plugin: z.string().optional(), server: z.string().optional() }).optional(),
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

let _checkUpdate$v
const _checkUpdate = () => (_checkUpdate$v ??= z.object({
  ok: z.boolean(), tag: z.string().optional(), name: z.string().optional(),
  publishedAt: z.string().optional(), body: z.string().optional(),
  size: z.number().optional(), downloadUrl: z.string().nullable().optional(),
  error: z.string().optional(),
}))

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
    id: z.string(), content: z.string(),
    // 历史脏数据：个别记录 tags 被写成逗号串（非数组）。codec 是"边界校验"，
    // 不应因历史数据的类型漂移让整个列表空白 —— 统一归一化为数组。
    tags: z.union([z.array(z.string()), z.string()]).nullish().transform((v) =>
      Array.isArray(v) ? v : (typeof v === 'string' && v.trim() ? v.split(',').map(s => s.trim()).filter(Boolean) : [])),
    source_room: z.string().optional(), graduated_at: z.string().nullish(),
    created_at: z.string().optional(), chars: z.number().optional(),
    summary: z.string().nullish(),
    encrypted: z.boolean().nullish(),
    wing: z.string().nullish(),
    importance: z.number().nullish(),
    admission: z.string().nullish(),
  }).passthrough()).optional(),
  count: z.number(),
}))

let _recentMemories$v
const _recentMemories = () => (_recentMemories$v ??= z.object({
  memories: z.array(z.object({
    id: z.string(), content: z.string(), wing: z.string().optional(),
    room: z.string().optional(), tags: z.array(z.string()).optional(),
    importance: z.number().nullable().optional(), created_at: z.string().optional(),
    admission: z.string().nullable().optional(),
  })).optional(),
  count: z.number(),
}))

// ── 平台管理相关类型 ──
// 后端 list_tokens/get_pending 对未发生的时间字段返回 null 而非省略，
// Zod 的 .optional() 不接受 null，strict 验证会整体失败，故统一用 .nullish()。
let _platformList$v
const _platformList = () => (_platformList$v ??= z.object({
  platforms: z.array(z.object({
    token_id: z.string(), platform: z.string(), platform_name: z.string(),
    permissions: z.array(z.string()), status: z.string(),
    created_at: z.string(), last_used_at: z.string().nullish(),
    approved_at: z.string().nullish(), revoked_at: z.string().nullish(),
    request_ip: z.string().nullish(),
  })).optional(),
  count: z.number(),
}))

let _pendingList$v
const _pendingList = () => (_pendingList$v ??= z.object({
  platforms: z.array(z.object({
    token_id: z.string(), platform: z.string(), platform_name: z.string(),
    permissions: z.array(z.string()), status: z.string(),
    created_at: z.string(), request_ip: z.string().nullish(),
    last_used_at: z.string().nullish(),
    approved_at: z.string().nullish(),
    revoked_at: z.string().nullish(),
  })).optional(),
  count: z.number(),
}))

let _approveResult$v
const _approveResult = () => (_approveResult$v ??= z.object({
  ok: z.boolean(), token_id: z.string(), status: z.string(),
}))

let _rejectResult$v
const _rejectResult = () => (_rejectResult$v ??= z.object({
  ok: z.boolean(), token_id: z.string(), status: z.string(),
}))

let _revokePlatformResult$v
const _revokePlatformResult = () => (_revokePlatformResult$v ??= z.object({
  ok: z.boolean(), token_id: z.string(), status: z.string(),
}))

// ── 知识库相关类型 ──
let _knowledgeList$v
const _knowledgeList = () => (_knowledgeList$v ??= z.object({
  knowledge: z.array(z.object({
    id: z.string(), title: z.string(), content: z.string(),
    category: z.string(), tags: z.array(z.string()),
    confidence: z.number(), created_at: z.string(),
    updated_at: z.string(), usage_count: z.number(),
    source_memories: z.array(z.any()).optional(),
    related_knowledge: z.array(z.any()).optional(),
  })).optional(),
  count: z.number(),
}))

let _knowledgeEntry$v
const _knowledgeEntry = () => (_knowledgeEntry$v ??= z.object({
  id: z.string(), title: z.string(), content: z.string(),
  category: z.string(), tags: z.array(z.string()),
  confidence: z.number(), created_at: z.string(),
  updated_at: z.string(), usage_count: z.number(),
  source_memories: z.array(z.string()),
  related_knowledge: z.array(z.string()),
}))

let _knowledgeStats$v
const _knowledgeStats = () => (_knowledgeStats$v ??= z.object({
  total: z.number(),
  categories: z.record(z.number()),
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
      id: 'dsh-pangu#panguDashboard/checkUpdate',
      service: 'panguDashboard', namespace: 'panguDashboard', method: 'checkUpdate',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#CheckUpdateResult', create: _checkUpdate },
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
      // 实现与客户端都以「单个对象」传参（createKey(args)），此处原先声明成两个独立
      // 参数 room/scope。typert 按声明严格校验，两侧不一致会让调用在网关就被拒
      // （客户端则表现为静默失败：Promise.allSettled 吞掉错误 → UI 空白）。
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyCreateArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyCreate', create: _keyCreate },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/revokeKey',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'revokeKey',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KeyRevokeArgs', create: _patchCodec } }],
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
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RekeyArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RekeyResult', create: _rekeyResult },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/listPublicMemories',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listPublicMemories',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#PublicMemories', create: _publicMemories },
    },
    {
      id: 'dsh-pangu#panguAdminKeys/listRecentMemories',
      service: 'panguAdminKeys', namespace: 'panguAdminKeys', method: 'listRecentMemories',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RecentMemories', create: _recentMemories },
    },
    // ── 平台管理调用 ──
    {
      id: 'dsh-pangu#panguPlatforms/listPlatforms',
      service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'listPlatforms',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#PlatformList', create: _platformList },
    },
    {
      id: 'dsh-pangu#panguPlatforms/listPending',
      service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'listPending',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#PendingList', create: _pendingList },
    },
    {
      id: 'dsh-pangu#panguPlatforms/approve',
      service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'approve',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#ApproveArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#ApproveResult', create: _approveResult },
    },
    {
      id: 'dsh-pangu#panguPlatforms/reject',
      service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'reject',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RejectArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RejectResult', create: _rejectResult },
    },
    {
      id: 'dsh-pangu#panguPlatforms/revoke',
      service: 'panguPlatforms', namespace: 'panguPlatforms', method: 'revoke',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#RevokePlatformArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#RevokePlatformResult', create: _revokePlatformResult },
    },
    // ── 知识库调用 ──
    {
      id: 'dsh-pangu#panguKnowledge/list',
      service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'list',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeListArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeList', create: _knowledgeList },
    },
    {
      id: 'dsh-pangu#panguKnowledge/search',
      service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'search',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeSearchArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeList', create: _knowledgeList },
    },
    {
      id: 'dsh-pangu#panguKnowledge/get',
      service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'get',
      invocation: { kind: 'direct' },
      parameters: [{ name: 'args', wire: 'args', source: 'json', codec: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeGetArgs', create: _patchCodec } }],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeEntry', create: _knowledgeEntry },
    },
    {
      id: 'dsh-pangu#panguKnowledge/stats',
      service: 'panguKnowledge', namespace: 'panguKnowledge', method: 'stats',
      invocation: { kind: 'direct' }, parameters: [],
      result: { mode: 'strict', typeSymbol: 'dsh-pangu#KnowledgeStats', create: _knowledgeStats },
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
          { kind: 'method', name: 'checkUpdate', signature: 'checkUpdate(): CheckUpdateResult', summary: '查询 GitHub Releases 最新版本。' },
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
          { kind: 'method', name: 'listRecentMemories', signature: 'listRecentMemories(): RecentMemories', summary: '最近入库：全库最新记忆，不限毕业状态。' },
        ],
        types: [],
      },
      // ── 平台管理服务 ──
      {
        key: 'panguPlatforms', exportName: 'PanguPlatformsService', tags: [],
        members: [
          { kind: 'method', name: 'listPlatforms', signature: 'listPlatforms(): PlatformList', summary: '列出已接入平台。' },
          { kind: 'method', name: 'listPending', signature: 'listPending(): PendingList', summary: '获取待审核平台列表。' },
          { kind: 'method', name: 'approve', signature: 'approve(token_id): ApproveResult', summary: '审核通过平台接入。' },
          { kind: 'method', name: 'reject', signature: 'reject(token_id): RejectResult', summary: '拒绝平台接入。' },
          { kind: 'method', name: 'revoke', signature: 'revoke(token_id): RevokeResult', summary: '撤销平台接入。' },
        ],
        types: [],
      },
      // ── 知识库服务 ──
      {
        key: 'panguKnowledge', exportName: 'PanguKnowledgeService', tags: [],
        members: [
          { kind: 'method', name: 'list', signature: 'list(category): KnowledgeList', summary: '列出知识库条目。' },
          { kind: 'method', name: 'search', signature: 'search(query): KnowledgeList', summary: '搜索知识库。' },
          { kind: 'method', name: 'get', signature: 'get(id): KnowledgeEntry', summary: '获取知识条目详情。' },
          { kind: 'method', name: 'stats', signature: 'stats(): KnowledgeStats', summary: '获取知识库统计。' },
        ],
        types: [],
      },
    ],
    events: [],
    objects: [],
  },
}

module.exports = { TYPERT }
