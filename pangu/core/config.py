"""盘古核心配置模块 — 基于 pydantic-settings（伏羲移植）"""

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# 加载 .env 文件（兼容 shell 语法）
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


# ── 密钥文件读写（0600）──────────────────────────────
# 与 jwt_secret 的做法一致：敏感值不落 config.json，改存独立的受保护文件。
def read_secret_file(path: str | os.PathLike) -> str:
    """读取密钥文件，不存在或为空返回空串。"""
    if not path:
        return ""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    return text


def write_secret_file(path: str | os.PathLike, value: str) -> None:
    """写入密钥文件并收紧权限到 0600；value 为空则删除该文件。"""
    if not path:
        return
    p = Path(path)
    try:
        if not value:
            p.unlink(missing_ok=True)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        # 先创建再写，避免出现「先写后 chmod」的短暂可读窗口
        p.touch(mode=0o600, exist_ok=True)
        p.write_text(value, encoding="utf-8")
        p.chmod(0o600)
    except OSError as e:
        logger.warning(f"LLM API Key 写入失败({e})，该 Key 将仅在当前进程内有效")


class ExposureConfig(BaseModel):
    """工具暴露面配置（~/.pangu/config.json 的 exposure 段）

    控制三层工具暴露：
    - enabled_optional_modules: 已启用的可选模块集合
    - enabled_experiments: 已启用的实验组集合
    - enabled_core_modules: 额外展开的 core 模块集合（见下方说明）

    缺省时暴露面自动收敛为白名单 28 个核心工具。
    extra="ignore" 保证旧配置（无 exposure 段）被接受。

    enabled_core_modules 说明：
      core 层模块（memory_ops / search / system / io_tools / palace / batch）
      默认启用，但其中只有 28 个白名单工具默认暴露，余下约 76 个工具
      （如 pangu_fts_search、pangu_holographic_encode、pangu_wm_push）
      此前**没有任何配置途径**可以展开——只判断了 optional 层，形成死区。
      该字段用于按需展开某个 core 模块的全部工具，默认空集以保持
      "开箱 28 个工具"的既有行为不变。
    """

    enabled_optional_modules: set[str] = Field(default_factory=set)
    enabled_experiments: set[str] = Field(default_factory=set)
    enabled_core_modules: set[str] = Field(default_factory=set)


class PanguConfig(BaseSettings):
    """盘古全局配置 — 伏羲移植增强版"""

    model_config = SettingsConfigDict(env_prefix="PANGU_", extra="ignore")

    # ── 工具暴露面配置 ──
    exposure: ExposureConfig = Field(default_factory=ExposureConfig)

    # ── 路径配置 ──
    base_dir: Path = Path(os.path.expanduser("~/.pangu"))
    palace_path: str = ""
    wiki_path: str = ""
    identity_path: str = ""
    config_path: str = ""
    db_path: Path = Path(".")
    backup_dir: Path = Path(".")
    # 权威记忆存储目录（v2）。留空时由 db_path 派生（见 memory_data_dir）。
    # 显式设置可覆盖，供迁移/测试指向别处。
    memory_data_dir_override: str = ""
    # 领域知识库独立 SQLite DB 路径（P2-1 Step 1）。
    # 留空时在 model_post_init 派生为 base_dir / "domain_knowledge.db"。
    # **必须**走 config 而不是硬编码 Path.home()，否则测试隔离失效
    # （参考 P0-0 路径分叉教训）。
    domain_knowledge_db_path: Path = Path("")

    # ── 服务配置 ──
    host: str = "0.0.0.0"
    port: int = 19528
    web_host: str = "127.0.0.1"
    web_port: int = 8866
    api_key: str = ""

    # ── JWT 鉴权配置 ──
    jwt_secret: str = ""  # 留空时从 jwt_secret_file 自动加载/生成
    jwt_secret_file: str = ""  # 默认 {data_dir}/.jwt_secret
    # LLM API Key 不入 config.json（save() 已将其排除），改存独立文件，
    # 否则通过设置页/ pangu_config_set 写入的 Key 一重启就丢失。
    llm_api_key_file: str = ""  # 默认 {data_dir}/.llm_api_key
    jwt_algorithm: str = "HS256"
    jwt_access_ttl: int = 3600  # access token 1 小时
    jwt_refresh_ttl: int = 7 * 86400  # refresh token 7 天
    jwt_default_user: str = "admin"
    jwt_default_password: str = ""  # 部署后建议通过 jwt_users 或环境变量设置
    jwt_users: dict = Field(default_factory=dict)  # {username: bcrypt_hash}，留空则用 default

    # ── MCP 认证开关 ──
    mcp_require_auth: bool = False  # true 时 /mcp 无凭据或无效钥匙 → 401

    # ── RBAC 角色权限配置 ──
    jwt_default_role: str = "admin"  # 未指定用户的默认角色
    jwt_roles: dict = Field(default_factory=dict)  # 角色 → scope 列表；空则用 ROLE_PRESETS
    jwt_user_roles: dict = Field(default_factory=dict)  # {username: role_name}

    # ── ABAC 多租户 / 策略配置 ──
    abac_enabled: bool = True  # 是否启用 ABAC 策略引擎
    abac_default_tenant: str = "default"  # 缺省 tenant_id
    abac_tenant_header: str = "x-tenant-id"  # 从 header 提取租户
    abac_policies: list = Field(default_factory=list)  # 自定义策略（JSON list）
    abac_user_attrs: dict = Field(default_factory=dict)  # {username: {tenant_id, department, clearance, groups}}

    # ── LMM 配置 ──
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_fallback_models: list = Field(default_factory=lambda: ["gpt-4o-mini", "claude-3-haiku"])
    llm_max_retries: int = 3
    llm_retry_delay: float = 2.0

    # ── 响应缓存配置 ──
    llm_cache_enabled: bool = True
    llm_cache_max: int = 128
    llm_cache_persist: bool = True
    llm_cache_persist_path: str = ""
    llm_cache_ttl_days: int = 7
    llm_cache_max_disk_mb: float = 100.0
    llm_cache_write_throttle: int = 10
    # ── 缓存预热 ──
    # ── Embedding 预热 ──
    embed_warmup_on_start: bool = False  # 启动时预热 embedding 缓存
    embed_warmup_queries: list = Field(
        default_factory=lambda: ["Python", "ONNX", "FAISS", "记忆系统", "向量搜索", "盘古", "深度学习"],
        description="启动时预热的查询列表",
    )
    llm_cache_warmup_on_start: bool = False  # 启动时自动预热
    llm_cache_warmup_prompts: list = Field(
        default_factory=list,
        description="预热 prompt 列表（每项为 {messages, system, temperature, max_tokens, json_mode}）",
    )
    # ── 持久化缓存维护 ──
    llm_cache_vacuum_on_start: bool = False  # 启动时自动 VACUUM 释放空间
    llm_cache_vacuum_interval_hours: float = 0.0  # 周期 VACUUM（0=禁用）

    # ── 嵌入模型配置 ──
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embed_cache_max: int = 256
    embed_api_url: str = ""
    embed_api_model: str = ""
    embed_fail_threshold: int = 3

    # ── ONNX 本地加速配置 ──
    onnx_enabled: bool = True
    # 多语模型（2026-09-19）：原默认 all-MiniLM-L6-v2 是纯英文模型，中文分词几乎
    # 全变 [UNK]，所有中文文本的向量趋同（任意两中文串 cos 0.9+）→ 语义搜索对
    # 中文从未真正工作过（"万金油结果"的根因）。paraphrase-multilingual 同为
    # 384 维（索引维度不用改）、覆盖中文、无需 query 前缀。
    onnx_model_id: str = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
    onnx_quantized: bool = True
    onnx_max_length: int = 128
    onnx_cache_dir: str = ""
    onnx_mirror_base: str = "https://hf-mirror.com"

    # ── 降级策略 ──
    # ONNX 不可用时，`_local_embed` 会返回**基于字符 trigram 的 hash 向量**。
    # 它是合法的 384 维向量、不抛异常，服务照常启动、检索照常返回结果——
    # 但结果**没有任何语义能力**（实测 cos(猫,dog)=0.0000、cos(猫,猫咪)=0.7071
    # 纯属字符巧合）。也就是说：不报错的降级 = 用户拿到"能跑但结果是错的"系统。
    #
    # 故默认 **`False`（拒绝降级）**：启动/首次嵌入时若发现只能走 hash，
    # 记 ERROR 日志并通过 /health 上报 degraded，让问题**可见**。
    # 弱网/离线环境确实需要接受 hash 向量时，显式设
    # `PANGU_ALLOW_HASH_FALLBACK=1` 打开。
    allow_hash_fallback: bool = False

    # ── 后端配置 ──
    backend: str = "chromadb"

    # ── 数据库配置 ──
    db_pool_max: int = 5
    db_pool_timeout: int = 10
    db_write_queue_enabled: bool = False

    # ── 检索配置 ──
    recall_cache_max: int = 128
    vector_weight_default: float = 0.6
    fts_weight_default: float = 4.0
    similarity_threshold: float = 0.65  # ONNX 语义嵌入需要更高阈值

    # ── 衰减配置 ──
    decay_base: float = 0.95
    night_decay_factor: float = 0.5
    touch_boost_short: float = 1.35
    touch_boost_long: float = 1.06
    decay_floor: float = 0.15

    # ── 工作记忆配置 ──
    wm_capacity: int = 40
    wm_capacity_adaptive: bool = True

    # ── 记忆栈配置 ──
    l1_max_drawers: int = 15
    l1_max_chars: int = 3200
    l2_default_results: int = 10
    l3_default_results: int = 5
    default_context_budget: int = 1000

    # ── 记忆压缩配置 ──
    compression_min_age_days: int = 30  # 最小压缩天数
    compression_min_importance: float = 0.3  # 最小压缩重要性
    compression_min_length: int = 100  # 最小压缩长度
    compression_max_key_points: int = 3  # 最大关键点数

    # ── 记忆巩固配置 ──
    consolidation_enabled: bool = True
    consolidation_interval_hours: float = 24.0
    forgetting_curve_decay: float = 0.5
    importance_decay_rate: float = 0.1
    min_importance_threshold: float = 0.5
    compression_threshold: int = 100
    reflection_daily_cap: int = 20

    # ── 神经记忆配置 ──
    neural_enabled: bool = True
    neural_hippocampus_capacity: int = 40
    neural_consolidation_threshold: float = 0.3
    neural_sleep_load_threshold: float = 0.6
    neural_decay_rates: dict = Field(
        default_factory=lambda: {
            "episodic": 0.6,
            "semantic": 0.15,
            "procedural": 0.08,
            "emotional": 0.3,
        }
    )
    neural_spreading_depth: int = 3
    neural_spreading_decay: float = 0.6

    # ── 梦境配置 ──
    dream_interval: int = 1800

    # ── 置信度来源 ──
    confidence_sources: dict = Field(default_factory=lambda: {"direct": 1.0, "inferred": 0.6, "hearsay": 0.3})

    # ── 图谱配置 ──
    edge_types: list = Field(
        default_factory=lambda: [
            "causes",
            "contradicts",
            "refines",
            "depends_on",
            "related_to",
            "temporal",
            "enables",
            "hinders",
            "supersedes",
            "wikilink",
            "mentions",
        ]
    )

    # ── 自愈配置 ──
    self_heal_max_retries: int = 3

    # ── 备份配置 ──
    backup_max_count: int = 7

    # ── 外部服务密钥 ──
    siliconflow_key: str = ""
    pangu_llm_model: str = "glm-5.1"

    # ── CORS 配置（精确域名；Starlette 不支持通配符模式） ──
    cors_origins: list = Field(
        default_factory=lambda: [
            "http://localhost:19528",
            "http://127.0.0.1:19528",
            "http://localhost:8866",
            "http://127.0.0.1:8866",
            "http://localhost:3000",  # 常见前端 dev 端口
            "http://127.0.0.1:3000",
            "http://localhost:5173",  # Vite
            "http://127.0.0.1:5173",
            # 局域网/VPN 来源请通过 config.json 的 cors_origins 或 PANGU_CORS_ORIGINS 配置
        ]
    )

    # ── 飞书告警 ──
    feishu_webhook_url: str = ""

    # ── 日志配置 ──
    log_level: str = "INFO"
    log_format: str = "json"

    # ── 引擎分层 ──
    engine_tier: str = "standard"

    def model_post_init(self, _context):
        """初始化后处理：设置派生路径"""
        if not self.palace_path:
            self.palace_path = str(self.base_dir / "palace")
        if not self.wiki_path:
            self.wiki_path = str(self.base_dir / "wiki")
        if not self.identity_path:
            self.identity_path = str(self.base_dir / "identity.txt")
        if not self.config_path:
            self.config_path = str(self.base_dir / "config.json")
        if "db_path" not in self.model_fields_set:
            self.db_path = self.base_dir / "pangu.db"
        if "backup_dir" not in self.model_fields_set:
            self.backup_dir = self.base_dir / "backups"
        if not self.jwt_secret_file:
            self.jwt_secret_file = str(self.base_dir / ".jwt_secret")
        if not self.llm_api_key_file:
            self.llm_api_key_file = str(self.base_dir / ".llm_api_key")
        if not self.domain_knowledge_db_path or str(self.domain_knowledge_db_path) == ".":
            self.domain_knowledge_db_path = self.base_dir / "domain_knowledge.db"

    # ── 权威记忆路径（P0-0 修复）────────────────────────────
    # 背景：全仓 49 处 `MemoryStack(...)` 调用点中，只有 pangu/api/server.py 与
    # pangu/server/mcp_server.py 显式构造了指向 v2 的 config，其余（CLI 34 处、
    # routes_memory、web_server(8866)、warmup、autonomous 维护等）都传默认
    # config → 读 v1 `palace_path/drawers.json`。而 v1 文件实际是空的 `[]`
    # （实测 2 字节），真实存量在 v2 `db_path/v2_memories/drawers.json`
    # （实测 66 条）。后果是同一进程内「两条路径给出两个答案」：API 看得到记忆，
    # CLI/维护/8866 看空库，自主维护连续空转 81 次。
    #
    # 修法：不在 40 处调用点逐处硬改（必然改漏），而是在 config 上集中定义
    # **唯一权威路径**，让 MemoryStack 默认就取对。
    @property
    def memory_data_dir(self) -> Path:
        """权威记忆数据目录。

        语义：`db_path/v2_memories` 优先，它是 API/MCP 两侧共同的真实存储。
        `memory_data_dir_override` 显式设置时优先于派生（迁移/测试用）。
        """
        if self.memory_data_dir_override:
            return Path(os.path.expanduser(self.memory_data_dir_override))
        return Path(self.db_path) / "v2_memories"

    @property
    def authoritative_drawers_path(self) -> Path:
        """权威 drawers.json 路径（v2 主存储）。"""
        return self.memory_data_dir / "drawers.json"

    def legacy_drawers_path(self) -> Path:
        """v1 遗留 drawers.json（只读合并源，可能为空或不存在）。"""
        return Path(self.palace_path) / "drawers.json"

    def authoritative_memory_config(self) -> "PanguConfig":
        """返回一份指向权威（v2）存储的 config 副本。

        与 v1 的 `palace_path` 区分：identity/wiki 也一并指到 v2 目录，
        避免 L0/L1 层从遗留路径读到错位内容。

        ⚠ 语义边界（重要）：`memory_data_dir` 是 **property**，不是 pydantic
        字段，`model_copy()` 不会把它带过去——副本的 `memory_data_dir` 仍然
        依据**副本自己的 `db_path`** 重新派生。
        因此：该副本的权威路径语义**取决于它的 db_path**。
        本方法是**幂等**的（对副本再调用一次，得到相同的 memory_data_dir，
        因为 db_path 未被改动），实测已验证。但若将来需要把副本指向另一个
        库，必须显式改 `db_path`（或 `memory_data_dir_override`），
        只改 `palace_path` 不足以改变 `authoritative_drawers_path`。
        """
        cfg = self.model_copy(deep=True)
        v2_dir = self.memory_data_dir
        cfg.palace_path = str(v2_dir)
        # ⚠ identity_path / wiki_path **不跟着记忆库迁移**，必须保持原值。
        #
        # 这里曾经写成 `v2_dir / "identity.json"` 和 `v2_dir / "wiki.json"`，
        # 是两处真实 bug（都是"改默认时改错了语义"）：
        #
        # 1) identity_path：L0 身份层的契约是 **`.txt`**
        #    （layers.py:55 "读取 ~/.pangu/identity.txt"；:65 提示语同样写 .txt；
        #     config.py:329 的默认值也是 `base_dir / "identity.txt"`）。
        #    权威化后变成 v2 目录下的 `identity.json` ⇒ **文件明明存在却读不到**，
        #    已配置身份的用户会静默丢失 L0 身份（不报错，只报 degraded）。
        # 2) wiki_path：`wiki/engine.py:17-21` 把它当**目录**用
        #    （`mkdir(parents=True)`，再往里面写 `wiki_index.json` 和 `<id>.md`），
        #    而原来赋的是文件路径 `wiki.json` ⇒ 语义错误。
        #
        # 语义判断依据：身份文件是**用户手工创建的配置文件**，Wiki 是独立的
        # 知识库目录，二者都不是"记忆抽屉数据"，不该跟着 drawers 的迁移走。
        # 记忆栈只迁移 `palace_path`（drawers/状态）——与 lifecycle_state.json
        # 保留在 v1 是同一个判断。
        return cfg

    def authoritative_extra_drawers_files(self) -> list[Path]:
        """权威读取时应合并的只读 v1 源：仅在文件存在且非空时返回。"""
        v1 = self.legacy_drawers_path()
        # 空 `[]` 是"无内容"，不是有效合并源——合并它只会让人误以为读了 v1
        return [v1] if self.load_drawers_nonempty(v1) else []

    @staticmethod
    def load_drawers_nonempty(path: "Path | str") -> list:
        """读取 drawers.json，返回记录列表；不存在/损坏/**空 `[]`** 一律返回 `[]`。

        这是「空 `[]` 不算数据源」这条规则的**唯一定义处**。此前该规则散落在
        多个调用点，标准不一致——例如 `rebuild_vector_index()` 的回退分支只
        检查了"文件存在"，于是读到空 `[]` 后继续往下走、`vector_idx.clear()`
        之后一条都不加，**仍然把向量索引清零**（队长复核发现的逻辑倒置）。

        统一到此处后，所有"拿现有记忆"的地方都得到同一语义：
        空文件 == 没有记忆，而不是"有一份空的记忆"。
        """
        try:
            p = Path(path)
            if not p.exists():
                return []
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if data else []
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
            return []

    @classmethod
    def load(cls, config_path: str | None = None) -> "PanguConfig":
        """从配置文件加载配置（保持向后兼容）"""
        config_path = config_path or os.path.expanduser("~/.pangu/config.json")

        # 先从 JSON 文件加载（损坏时回退默认暴露面）
        json_data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    json_data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"配置文件加载失败({e})，回退默认暴露面")

        # 移除敏感字段（仅当对应环境变量已设置时）
        # 这样保持向后兼容：没有设置环境变量时仍从 JSON 读取
        sensitive_keys = {
            "api_key": "PANGU_API_KEY",
            "llm_api_key": "PANGU_LLM_API_KEY",
            "siliconflow_key": "PANGU_SILICONFLOW_KEY",
            "jwt_secret": "PANGU_JWT_SECRET",
            "jwt_default_password": "PANGU_JWT_DEFAULT_PASSWORD",
        }
        removed_keys = []
        for key, env_var in sensitive_keys.items():
            if key in json_data and os.environ.get(env_var):
                removed_keys.append(key)
                del json_data[key]
        if removed_keys:
            logger.warning(f"从 config.json 中移除了敏感字段 {removed_keys}，请通过环境变量（PANGU_ 前缀）设置这些值。")

        # 用 pydantic-settings 创建实例（自动从环境变量覆盖）
        #
        # ⚠ F2 修复：`cls(**json_data)` 会把 config.json 里的**显式**值作为
        # **构造参数**传入，而 pydantic-settings 中「显式构造参数 > 环境变量」。
        # 于是本机 config.json 里写死的绝对路径
        # `"db_path": "/home/xiaoxin/.pangu/pangu.db"` 会**静默压过** `PANGU_DB_PATH`，
        # 导致任何调用 `load()` 的测试/进程都拿到**生产路径**并写入生产库
        # —— 实测造成 v2 权威库被反复清空（P0-0 事故的主要污染渠道）。
        #
        # F2-b 修复（P0-0 遗留）：让**已显式设置的环境变量获胜**，
        # 把这些键从 json_data 里摘掉，交给 pydantic-settings 从环境变量取值。
        # 这不是新语义，而是把 `pangu/api/server.py` 早已声明的设计补全：
        #     _ENV_OVERRIDABLE_PATHS = ("db_path", "base_dir")
        # 该逻辑此前只写在 `create_app()` 里，`load()` 从未实现，两处行为不一致。
        # 未设置对应环境变量时行为完全不变（仍读 config.json，向后兼容）。
        #
        # F2-b 新增：palace_path/identity_path/wiki_path/backup_dir 也需要覆盖，
        # 否则 config.json 里的绝对路径会静默压过测试隔离设置的 env。
        # 这些字段的 env 名遵循 PANGU_ 前缀（pydantic-settings env_prefix="PANGU_"）。
        #
        # P2-1 Step 1 新增：domain_knowledge_db_path（PanguConfig 字段）也必须覆盖，
        # 否则 domain_knowledge 的 DB 路径会和生产路径冲突（参考 P0-0 教训）。
        for _key in (
            "db_path",
            "base_dir",
            "palace_path",
            "identity_path",
            "wiki_path",
            "backup_dir",
            "domain_knowledge_db_path",
        ):
            if os.environ.get(f"PANGU_{_key.upper()}") and _key in json_data:
                json_data.pop(_key)
        config = cls(**json_data)
        config.config_path = config_path
        # 密钥类字段不入 config.json（见 save() 的 exclude），从独立文件回填。
        # 优先级：环境变量 > 密钥文件 > 空。这样通过设置页写入的 Key
        # 在服务重启后依然可用（此前只存在内存里，重启即丢）。
        if not config.llm_api_key:
            config.llm_api_key = read_secret_file(config.llm_api_key_file)
        return config

    def save_llm_api_key(self, value: str) -> None:
        """把 LLM API Key 写入独立密钥文件（0600），空串表示清除。"""
        write_secret_file(self.llm_api_key_file, value)
        self.llm_api_key = value

    def save(self, config_path: str | None = None) -> None:
        """保存配置到文件（保持向后兼容）"""
        config_path = config_path or self.config_path
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        data = self.model_dump(
            exclude={"api_key", "llm_api_key", "siliconflow_key", "jwt_secret", "jwt_default_password"}
        )

        # 递归转换：Path → str, set → list
        def _convert(obj):
            if isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, set):
                return list(obj)
            elif isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_convert(item) for item in obj]
            return obj

        data = _convert(data)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def ensure_dirs(self) -> None:
        """确保所有必要的目录存在"""
        os.makedirs(self.palace_path, exist_ok=True)
        os.makedirs(self.wiki_path, exist_ok=True)
        os.makedirs(os.path.dirname(self.identity_path), exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        # 权威记忆目录（MemoryStack 的 _drawers_file 落在这里）。
        # 此前漏建 —— 服务长期运行时该目录早已存在所以没暴露；全新部署/测试环境
        # 首次写入会以 "No such file or directory: .../v2_memories/drawers.json.tmp"
        # 失败（2026-09-19 在备份恢复测试中撞到）。
        try:
            os.makedirs(os.path.join(str(self.db_path), "v2_memories"), exist_ok=True)
        except Exception:
            pass

    @classmethod
    def reload(cls) -> "PanguConfig":
        """热更新配置 — 重新加载 env 文件并重建 Config"""
        import importlib

        import pangu.core.config as mod

        importlib.reload(mod)

        # 重置 Embedding 服务的电路断路器
        try:
            from pangu.memory.embedding import get_embedding_service

            svc = get_embedding_service()
            svc.reset_circuit()
        except Exception:
            pass

        return mod.config


# 全局单例
config = PanguConfig()
