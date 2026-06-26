"""盘古核心配置模块 — 基于 pydantic-settings（伏羲移植）"""

import json
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class PanguConfig(BaseSettings):
    """盘古全局配置 — 伏羲移植增强版"""

    model_config = SettingsConfigDict(env_prefix="PANGU_", extra="ignore")

    # ── 路径配置 ──
    base_dir: Path = Path(os.path.expanduser("~/.pangu"))
    palace_path: str = ""
    wiki_path: str = ""
    identity_path: str = ""
    config_path: str = ""
    db_path: Path = Path(".")
    backup_dir: Path = Path(".")

    # ── 服务配置 ──
    host: str = "0.0.0.0"
    port: int = 19528
    web_host: str = "127.0.0.1"
    web_port: int = 8866
    api_key: str = ""

    # ── JWT 鉴权配置 ──
    jwt_secret: str = ""  # 留空时从 jwt_secret_file 自动加载/生成
    jwt_secret_file: str = ""  # 默认 {data_dir}/.jwt_secret
    jwt_algorithm: str = "HS256"
    jwt_access_ttl: int = 3600  # access token 1 小时
    jwt_refresh_ttl: int = 7 * 86400  # refresh token 7 天
    jwt_default_user: str = "admin"
    jwt_default_password: str = "pangu-admin"  # 部署后建议通过 jwt_users 覆盖
    jwt_users: dict = Field(default_factory=dict)  # {username: bcrypt_hash}，留空则用 default

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
    onnx_model_id: str = "Xenova/all-MiniLM-L6-v2"
    onnx_quantized: bool = True
    onnx_max_length: int = 128
    onnx_cache_dir: str = ""
    onnx_mirror_base: str = "https://hf-mirror.com"

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
            "http://192.168.5.8:19529",  # LAN
            "http://192.168.5.8:8866",
            "http://192.168.5.8:19528",
            "http://172.16.42.1:19529",  # VPN
            "http://172.16.42.1:8866",
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

    @classmethod
    def load(cls, config_path: str | None = None) -> "PanguConfig":
        """从配置文件加载配置（保持向后兼容）"""
        config_path = config_path or os.path.expanduser("~/.pangu/config.json")

        # 先从 JSON 文件加载
        json_data = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                json_data = json.load(f)

        # 用 pydantic-settings 创建实例（自动从环境变量覆盖）
        config = cls(**json_data)
        config.config_path = config_path
        return config

    def save(self, config_path: str | None = None) -> None:
        """保存配置到文件（保持向后兼容）"""
        config_path = config_path or self.config_path
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        data = self.model_dump(
            exclude={"api_key", "llm_api_key", "siliconflow_key", "jwt_secret", "jwt_default_password"}
        )
        # 转换 Path 对象为字符串
        for k, v in data.items():
            if isinstance(v, Path):
                data[k] = str(v)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def ensure_dirs(self) -> None:
        """确保所有必要的目录存在"""
        os.makedirs(self.palace_path, exist_ok=True)
        os.makedirs(self.wiki_path, exist_ok=True)
        os.makedirs(os.path.dirname(self.identity_path), exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

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
