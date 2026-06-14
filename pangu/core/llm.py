"""盘古 LMM 集成层 — 大语言模型驱动的智能记忆处理
=====================================================
盘古定位为专业的记忆系统，LMM 仅用于记忆处理，不包含 Agent 执行功能：
- 记忆分类与标注
- 记忆摘要与压缩
- 知识结晶（Wiki 页面生成）
- 记忆关联检测
- 记忆洞察提取

支持多提供商：OpenAI / Anthropic / Ollama / OpenRouter / DeepSeek / 智谱 / 通义千问

注意：盘古不提供问答、对话、任务执行等 Agent 功能。
这些应由上层 Agent 框架通过 MCP 接口调用盘古的记忆检索结果后自行实现。

性能优化（v0.1.1+）：
- 响应缓存（LRU）：相同 prompt 重复调用直接返回缓存
- 批量并发：asyncio.gather + Semaphore 控制并发度
- Token 跟踪：累计 prompt/completion/cost
- JSON 模式：原生 response_format 支持
- 自动重试：失败时指数退避
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx

from .config import PanguConfig

# 缓存预热审计日志：单独 logger + 单独文件（~/.pangu/logs/llm_cache_warmup.log）
_warmup_logger = logging.getLogger("pangu.llm.warmup")
if not _warmup_logger.handlers:
    _warmup_logger.setLevel(logging.INFO)
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".pangu", "logs")
        os.makedirs(log_dir, exist_ok=True)
        _fh = logging.FileHandler(
            os.path.join(log_dir, "llm_cache_warmup.log"),
            encoding="utf-8",
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        _warmup_logger.addHandler(_fh)
        _warmup_logger.propagate = False
    except Exception:
        # 文件日志失败不应影响主流程
        pass


@dataclass
class LLMResponse:
    """LMM 响应"""
    content: str
    model: str = ""
    usage: dict = field(default_factory=dict)
    provider: str = ""
    latency_ms: float = 0.0


# ── 提供商 URL 映射 ──

PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
}

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "ollama": None,  # Ollama 不需要 key
    "anthropic": "ANTHROPIC_API_KEY",
}

# ── 每 1K token 价格 (USD) — 2026 年初公开报价 ──
# 用于内部成本估算，仅供参考
PRICING_PER_1K = {
    # provider: (input_per_1k, output_per_1k)
    "openai": {
        "gpt-4o": (0.005, 0.015),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-3.5-turbo": (0.0005, 0.0015),
    },
    "zhipu": {
        "glm-4-flash": (0.0, 0.0),  # 新用户免费
        "glm-4-air": (0.0007, 0.0007),
        "glm-4-plus": (0.007, 0.007),
        "glm-4": (0.014, 0.014),
    },
    "deepseek": {
        "deepseek-chat": (0.00014, 0.00028),
        "deepseek-coder": (0.00014, 0.00028),
        "deepseek-reasoner": (0.00055, 0.00219),
    },
    "qwen": {
        "qwen-turbo": (0.0003, 0.0006),
        "qwen-plus": (0.0014, 0.0028),
    },
    "ollama": {},  # 本地免费
    "openrouter": {},  # 多模型，按实际模型计费
}


class LLMEngine:
    """LMM 引擎 — 多提供商统一调用接口，支持重试和回退

    优化特性：
    - 响应缓存（LRU + 持久化）：内存 LRU + SQLite 磁盘层，重启后仍有效
    - 批量并发：asyncio.gather + Semaphore 控制并发度
    - Token 跟踪：累计 prompt/completion/cost
    - JSON 模式：原生 response_format 支持
    - 自动重试：失败时指数退避
    - Prometheus 指标：cache_hit_rate / tokens / cost / latency
    """

    def __init__(self, config: PanguConfig = None):
        self.config = config or PanguConfig.load()
        self._client: httpx.AsyncClient | None = None
        self._call_count: int = 0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._cache_disk_hits: int = 0  # 仅来自磁盘的命中
        self._cache_writes: int = 0  # 持久化缓存写入次数
        self._tokens_saved: int = 0  # 缓存命中累计节省的 token
        self._total_latency: float = 0.0
        # token 与成本统计
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._estimated_cost_usd: float = 0.0
        # LRU 响应缓存（内存层）
        self._cache: OrderedDict[str, LLMResponse] = OrderedDict()
        self._cache_max: int = getattr(config, "llm_cache_max", 128) if config else 128
        self._cache_enabled: bool = getattr(config, "llm_cache_enabled", True) if config else True
        # 持久化缓存（磁盘层）
        self._persistent_cache = None
        if config is not None and self._cache_enabled and getattr(config, "llm_cache_persist", True):
            try:
                from .cache import PersistentCache
                self._persistent_cache = PersistentCache(
                    db_path=getattr(config, "llm_cache_persist_path", "") or "",
                    ttl_days=getattr(config, "llm_cache_ttl_days", 7),
                    max_disk_mb=getattr(config, "llm_cache_max_disk_mb", 100.0),
                    write_throttle=getattr(config, "llm_cache_write_throttle", 10),
                )
            except Exception:
                # 持久化失败不应影响引擎工作
                self._persistent_cache = None
        # 并发控制
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    @property
    def avg_latency_ms(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._total_latency / self._call_count

    def _get_api_key(self, provider: str) -> str:
        """获取 API Key，优先使用配置，其次环境变量"""
        if self.config.llm_api_key:
            return self.config.llm_api_key
        env_key = PROVIDER_ENV_KEYS.get(provider)
        if env_key:
            return os.environ.get(env_key, "")
        return ""

    def _get_base_url(self, provider: str) -> str:
        """获取 API Base URL"""
        if self.config.llm_base_url:
            return self.config.llm_base_url
        return PROVIDER_URLS.get(provider, "https://api.openai.com/v1")

    async def _call_openai_compatible(
        self, provider: str, messages: list[dict], system: str = "",
        temperature: float = 0.7, max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        """调用 OpenAI 兼容 API（OpenAI, DeepSeek, OpenRouter, 智谱, 通义千问, Ollama）

        Args:
            json_mode: 启用 JSON 模式（response_format: {"type": "json_object"}）
                       大多数 OpenAI 兼容 API 都支持，包括智谱 GLM-4 系列
        """
        base_url = self._get_base_url(provider)
        api_key = self._get_api_key(provider)

        if not api_key and provider != "ollama":
            return LLMResponse(
                content=f"[LMM 未配置 API Key，请设置 {PROVIDER_ENV_KEYS.get(provider, 'API_KEY')}]",
                provider=provider,
            )

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        # 智谱/OpenAI JSON 模式要求 prompt 暗示输出 JSON
        if json_mode:
            # 在最后追加 system 消息以确保模型输出 JSON
            json_hint = "你必须只输出合法的 JSON，不要包含任何其他文字、解释或 markdown 标记。"
            full_messages.insert(0, {"role": "system", "content": json_hint})
        full_messages.extend(messages)

        payload = {
            "model": self.config.llm_model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # 启用 JSON 输出模式
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # OpenRouter 特殊处理
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/pangu"
            headers["X-Title"] = "Pangu Memory System"

        start = time.time()
        try:
            resp = await self.client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            latency = (time.time() - start) * 1000
            self._call_count += 1
            self._total_latency += latency

            # 累计 token 用量
            usage = data.get("usage", {})
            self._total_prompt_tokens += usage.get("prompt_tokens", 0)
            self._total_completion_tokens += usage.get("completion_tokens", 0)
            self._estimated_cost_usd += self._estimate_cost(
                provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            )

            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=self.config.llm_model,
                usage=usage,
                provider=provider,
                latency_ms=latency,
            )
        except httpx.HTTPStatusError as e:
            return LLMResponse(
                content=f"[LMM 调用失败 ({provider}): HTTP {e.response.status_code}]",
                provider=provider,
            )
        except Exception as e:
            return LLMResponse(
                content=f"[LMM 调用失败 ({provider}): {e}]",
                provider=provider,
            )

    async def _call_anthropic(
        self, messages: list[dict], system: str = "",
        temperature: float = 0.7, max_tokens: int = 4096,
    ) -> LLMResponse:
        """调用 Anthropic Messages API"""
        api_key = self._get_api_key("anthropic")

        if not api_key:
            return LLMResponse(
                content="[LMM 未配置 Anthropic API Key]",
                provider="anthropic",
            )

        anthropic_messages = []
        for msg in messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}],
            })

        payload = {
            "model": self.config.llm_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system:
            payload["system"] = [{"type": "text", "text": system}]

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        start = time.time()
        try:
            resp = await self.client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            latency = (time.time() - start) * 1000
            self._call_count += 1
            self._total_latency += latency

            return LLMResponse(
                content=data["content"][0]["text"],
                model=self.config.llm_model,
                provider="anthropic",
                latency_ms=latency,
            )
        except Exception as e:
            return LLMResponse(
                content=f"[LMM 调用失败 (anthropic): {e}]",
                provider="anthropic",
            )

    async def chat(
        self,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        use_cache: bool = True,
    ) -> LLMResponse:
        """通用聊天接口 — 支持缓存、重试、JSON 模式

        Args:
            json_mode: 启用 JSON 模式（自动注入提示 + response_format），
                       如果 JSON 解析失败会自动重试一次
            use_cache: 是否使用响应缓存（默认 True，相同 prompt 直接返回缓存）

        Returns:
            LLMResponse — content 包含模型响应或错误标识
        """
        # 1) 缓存查询（仅对确定性参数生效：temperature=0）
        cache_key = None
        if use_cache and self._cache_enabled and temperature == 0:
            cache_key = self._make_cache_key(
                provider=self.config.llm_provider.lower(),
                model=self.config.llm_model,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            # 1a) 先查内存 LRU
            if cache_key in self._cache:
                self._cache_hits += 1
                cached = self._cache[cache_key]
                self._cache.move_to_end(cache_key)
                # 累计节省的 token（粗略估计：按 usage 中的 prompt+completion）
                if cached.usage:
                    self._tokens_saved += (
                        cached.usage.get("prompt_tokens", 0)
                        + cached.usage.get("completion_tokens", 0)
                    )
                return cached
            # 1b) 再查持久化缓存
            if self._persistent_cache is not None:
                try:
                    disk_entry = self._persistent_cache.get(cache_key)
                    if disk_entry is not None:
                        self._cache_hits += 1
                        self._cache_disk_hits += 1
                        # 累计节省的 token
                        if disk_entry.response.usage:
                            self._tokens_saved += (
                                disk_entry.response.usage.get("prompt_tokens", 0)
                                + disk_entry.response.usage.get("completion_tokens", 0)
                            )
                        # 提升到内存缓存
                        self._put_cache(cache_key, disk_entry.response)
                        return disk_entry.response
                except Exception:
                    pass

        self._cache_misses += 1

        # 2) 实际调用
        provider = self.config.llm_provider.lower()
        response = None
        for attempt in range(self.config.llm_max_retries):
            response = await self._do_chat(
                provider, messages, system, temperature, max_tokens, json_mode
            )
            # JSON 模式：解析失败时重试
            if json_mode and not response.content.startswith("[LMM"):
                parsed = self._extract_json(response.content, default=None)
                if parsed is None and attempt < self.config.llm_max_retries - 1:
                    await asyncio.sleep(self.config.llm_retry_delay * (attempt + 1))
                    continue
            if not response.content.startswith("[LMM 调用失败"):
                # 3) 写入缓存（仅当 temperature=0）
                if cache_key and not response.content.startswith("[LMM"):
                    self._put_cache(cache_key, response)
                    # 写入持久化缓存
                    if self._persistent_cache is not None:
                        try:
                            self._persistent_cache.put(
                                cache_key,
                                provider=self.config.llm_provider.lower(),
                                model=self.config.llm_model,
                                request={
                                    "messages": messages,
                                    "system": system,
                                    "max_tokens": max_tokens,
                                    "json_mode": json_mode,
                                },
                                response=response,
                            )
                            self._cache_writes += 1
                        except Exception:
                            pass
                return response
            if attempt < self.config.llm_max_retries - 1:
                await asyncio.sleep(self.config.llm_retry_delay * (attempt + 1))

        return response

    async def _do_chat(
        self, provider: str, messages: list[dict], system: str = "",
        temperature: float = 0.7, max_tokens: int = 4096, json_mode: bool = False,
    ) -> LLMResponse:
        """执行实际的 LLM 调用"""
        if provider == "anthropic":
            return await self._call_anthropic(messages, system, temperature, max_tokens)
        else:
            return await self._call_openai_compatible(
                provider, messages, system, temperature, max_tokens, json_mode
            )

    async def stream_chat(
        self, messages: list[dict], system: str = "",
        temperature: float = 0.7, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式聊天 — 逐 token 返回"""
        provider = self.config.llm_provider.lower()
        base_url = self._get_base_url(provider)
        api_key = self._get_api_key(provider)

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        payload = {
            "model": self.config.llm_model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        headers = {"Content-Type": "application/json"}
        if api_key and provider != "ollama":
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with self.client.stream(
                "POST", f"{base_url}/chat/completions",
                json=payload, headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception:
            yield "[LMM 流式调用失败]"

    # ── 记忆专用方法 ──

    async def summarize_memories(self, memories: list[dict], max_summary_length: int = 500) -> str:
        """总结记忆片段"""
        if not memories:
            return "暂无记忆。"

        memory_text = "\n\n---\n\n".join([
            f"[{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:1000]}"
            for m in memories[:10]
        ])

        system = """你是盘古记忆系统的智能摘要引擎。请将以下记忆片段总结为简洁的摘要。
要求：
1. 提取关键信息、决策和洞察
2. 保持客观，不添加推测
3. 使用中文输出
4. 控制在 500 字以内"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请总结以下记忆片段：\n\n{memory_text}"}],
            system=system,
            max_tokens=max_summary_length * 2,
        )
        return response.content

    async def classify_memory(self, content: str) -> dict:
        """智能分类记忆片段"""
        system = """你是盘古记忆系统的分类引擎。请将以下内容分类。
返回 JSON 格式：{"hall": "殿堂类型", "room": "建议房间名", "importance": 1-5, "tags": ["标签1", "标签2"]}

殿堂类型选项：
- hall_facts: 事实与决策
- hall_events: 事件与里程碑
- hall_discoveries: 发现与洞察
- hall_preferences: 偏好与习惯
- hall_advice: 建议与方案
- hall_concepts: 概念与理论
- hall_relations: 关系与网络"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请分类以下内容：\n\n{content[:2000]}"}],
            system=system,
            temperature=0.3,
            max_tokens=500,
            json_mode=True,
        )

        return self._extract_json(response.content, default={
            "hall": "hall_events", "room": "general", "importance": 3, "tags": []
        })

    async def generate_wiki_page(self, title: str, memories: list[dict], existing_pages: list[dict] = None) -> dict:
        """从记忆片段生成 Wiki 页面"""
        memory_text = "\n\n---\n\n".join([
            f"[{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:1500]}"
            for m in memories[:8]
        ])

        existing_context = ""
        if existing_pages:
            existing_context = "\n\n已存在的相关页面：\n" + "\n".join([
                f"- {p.get('title', '')}: {p.get('summary', '')[:200]}"
                for p in existing_pages[:5]
            ])

        system = """你是盘古记忆系统的 Wiki 生成引擎。请根据记忆片段生成一个知识页面。

要求：
1. 使用 Markdown 格式
2. 包含：标题、摘要、关键信息、相关概念、时间线
3. 识别并标注与现有页面的关联
4. 客观、准确、结构化
5. 使用中文输出

返回 JSON 格式：
{
  "title": "页面标题",
  "summary": "一句话摘要",
  "content": "完整的 Markdown 内容",
  "linked_pages": ["关联页面标题1", "关联页面标题2"],
  "tags": ["标签1", "标签2"]
}"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请为以下记忆生成 Wiki 页面：\n\n主题：{title}\n\n记忆片段：\n{memory_text}{existing_context}"}],
            system=system,
            temperature=0.5,
            max_tokens=2000,
            json_mode=True,
        )

        return self._extract_json(response.content, default={
            "title": title, "summary": "", "content": "", "linked_pages": [], "tags": []
        })

    async def detect_links(self, page: dict, all_pages: list[dict]) -> list[str]:
        """检测页面之间的关联"""
        system = """你是盘古记忆系统的链接检测引擎。请分析当前页面与所有页面的关联。

返回 JSON 格式：{"linked_titles": ["关联页面标题1", "关联页面标题2"]}"""

        all_pages_text = "\n".join([
            f"- {p.get('title', '')}: {p.get('summary', '')[:100]}"
            for p in all_pages[:20]
        ])

        response = await self.chat(
            messages=[{"role": "user", "content": f"当前页面：\n标题：{page.get('title', '')}\n摘要：{page.get('summary', '')}\n\n所有页面：\n{all_pages_text}"}],
            system=system,
            temperature=0.3,
            max_tokens=500,
        )

        return self._extract_json(response.content, default={"linked_titles": []}).get("linked_titles", [])

    async def generate_insight(self, memories: list[dict]) -> str:
        """从记忆中生成洞察"""
        memory_text = "\n\n".join([
            f"[{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:800]}"
            for m in memories[:5]
        ])

        system = """你是盘古记忆系统的洞察引擎。请从以下记忆片段中提取洞察。

要求：
1. 发现隐藏的模式和关联
2. 提出有价值的见解
3. 使用中文输出
4. 控制在 200 字以内"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请分析以下记忆片段并提取洞察：\n\n{memory_text}"}],
            system=system,
            max_tokens=500,
        )
        return response.content

    async def compress_memories(self, memories: list[dict], target_count: int = 5) -> str:
        """将多条记忆压缩为精简摘要"""
        memory_text = "\n\n---\n\n".join([
            f"[{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:500]}"
            for m in memories[:20]
        ])

        system = f"""你是盘古记忆压缩引擎。请将以下多条记忆片段压缩为 {target_count} 条精简摘要。
要求：
1. 保留核心信息和关键决策
2. 合并重复或相似的内容
3. 每条摘要控制在 100 字以内
4. 使用中文输出
5. 返回 JSON 格式：{{"compressed": ["摘要1", "摘要2", ...], "merged_count": N}}"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请压缩以下记忆：\n\n{memory_text}"}],
            system=system,
            max_tokens=2000,
        )

        return response.content

    async def detect_associations(self, memories: list[dict]) -> list[dict]:
        """自动检测记忆之间的关联"""
        memory_text = "\n\n---\n\n".join([
            f"[{i}] [{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:300]}"
            for i, m in enumerate(memories[:10])
        ])

        system = """你是盘古记忆关联引擎。请分析以下记忆片段，找出它们之间的关联。

返回 JSON 格式：
{
  "associations": [
    {"from_idx": 0, "to_idx": 1, "relation": "关联描述", "strength": 0.8},
    ...
  ],
  "clusters": [
    {"theme": "主题", "member_indices": [0, 1, 2], "summary": "簇摘要"}
  ]
}"""

        response = await self.chat(
            messages=[{"role": "user", "content": f"请分析以下记忆的关联：\n\n{memory_text}"}],
            system=system,
            temperature=0.3,
            max_tokens=2000,
        )

        return self._extract_json(response.content, default={"associations": [], "clusters": []})

    # ── 工具方法 ──

    @staticmethod
    def _extract_json(text: str, default: dict | None = None) -> dict:
        """从 LLM 响应中提取 JSON — 支持多种格式

        处理场景：
        1. 纯 JSON：`{"key": "value"}`
        2. Markdown 包裹：` ```json\\n{...}\\n``` `
        3. 前后有废话：'好的，输出如下：\\n{...}\\n如上'
        4. 嵌套代码块：尝试找到第一个完整的 {...} 块
        """
        if default is None:
            default = {}
        text = text.strip()
        if not text:
            return default

        # 1) 直接解析
        try:
            parsed = json.loads(text)
            # 始终返回 dict，列表自动包装
            if isinstance(parsed, list):
                return {"items": parsed}
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # 2) 移除 markdown 代码块
        content = text
        if "```json" in content:
            try:
                content = content.split("```json", 1)[1].split("```", 1)[0].strip()
                parsed = json.loads(content)
                return {"items": parsed} if isinstance(parsed, list) else parsed
            except (json.JSONDecodeError, IndexError, ValueError):
                pass
        if "```" in content:
            try:
                content = content.split("```", 1)[1].split("```", 1)[0].strip()
                parsed = json.loads(content)
                return {"items": parsed} if isinstance(parsed, list) else parsed
            except (json.JSONDecodeError, IndexError, ValueError):
                pass

        # 3) 寻找第一个 { 到最后一个 } 之间的内容
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = content[start : end + 1]
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                pass

        # 4) 寻找 [ 到 ] 之间的数组
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = content[start : end + 1]
            try:
                return {"items": json.loads(candidate)}
            except (json.JSONDecodeError, ValueError):
                pass

        return default

    def _estimate_cost(self, provider: str, prompt_tokens: int, completion_tokens: int) -> float:
        """估算调用成本（USD）

        基于 PRICING_PER_1K 表，未匹配的模型返回 0。
        """
        if prompt_tokens == 0 and completion_tokens == 0:
            return 0.0
        provider_pricing = PRICING_PER_1K.get(provider.lower(), {})
        # 精确匹配 → 模糊匹配（模型名前缀）
        if self.config.llm_model in provider_pricing:
            in_p, out_p = provider_pricing[self.config.llm_model]
        else:
            # 尝试前缀匹配
            matched = None
            for model_key in provider_pricing:
                if self.config.llm_model.startswith(model_key):
                    matched = model_key
                    break
            if matched is None:
                return 0.0
            in_p, out_p = provider_pricing[matched]
        return (prompt_tokens / 1000.0) * in_p + (completion_tokens / 1000.0) * out_p

    def get_stats(self) -> dict:
        """获取引擎统计信息（调用次数/延迟/token/成本/缓存）"""
        total_lookups = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / total_lookups * 100 if total_lookups > 0 else 0.0
        )
        stats = {
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "call_count": self._call_count,
            "avg_latency_ms": self.avg_latency_ms,
            "total_latency_ms": self._total_latency,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "estimated_cost_usd": round(self._estimated_cost_usd, 6),
            # 内存缓存统计
            "memory_cache_enabled": self._cache_enabled,
            "cache_hits": self._cache_hits,
            "cache_disk_hits": self._cache_disk_hits,
            "cache_memory_hits": self._cache_hits - self._cache_disk_hits,
            "cache_misses": self._cache_misses,
            "cache_writes": self._cache_writes,
            "tokens_saved": self._tokens_saved,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "cache_size": len(self._cache),
            "cache_max": self._cache_max,
        }
        # 持久化缓存统计
        if self._persistent_cache is not None:
            try:
                stats["persistent_cache"] = self._persistent_cache.get_stats()
            except Exception:
                stats["persistent_cache"] = {"error": "unavailable"}
        return stats

    def clear_cache(self) -> int:
        """清空内存缓存"""
        count = len(self._cache)
        self._cache.clear()
        return count

    def clear_persistent_cache(self) -> int:
        """清空持久化缓存"""
        if self._persistent_cache is None:
            return 0
        return self._persistent_cache.clear()

    def vacuum_persistent_cache(self) -> dict:
        """对持久化缓存执行 VACUUM，释放 SQLite 碎片空间

        Returns:
            {"before_bytes": 释放前, "after_bytes": 释放后, "freed_bytes": 释放量,
             "duration_ms": 耗时, "skipped": bool}
        """
        import os as _os
        if self._persistent_cache is None:
            return {"skipped": True, "reason": "persistent cache disabled"}
        before_path = self._persistent_cache.db_path
        before_bytes = _os.path.getsize(before_path) if _os.path.exists(before_path) else 0
        start = time.time()
        try:
            self._persistent_cache.vacuum()
        except Exception as e:
            return {"error": str(e), "skipped": True}
        duration_ms = round((time.time() - start) * 1000, 2)
        after_bytes = _os.path.getsize(before_path) if _os.path.exists(before_path) else 0
        freed = max(0, before_bytes - after_bytes)
        return {
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "freed_bytes": freed,
            "duration_ms": duration_ms,
            "skipped": False,
        }

    async def start_periodic_vacuum(self, interval_hours: float = 24.0):
        """启动周期 VACUUM 任务（永久循环，直到任务被取消）

        Args:
            interval_hours: 间隔小时数（默认 24）

        使用：
            task = asyncio.create_task(engine.start_periodic_vacuum(24))
            ... 之后可以 task.cancel() 停止
        """
        if self._persistent_cache is None:
            return
        if interval_hours <= 0:
            return
        interval_seconds = interval_hours * 3600.0
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                result = self.vacuum_persistent_cache()
                _warmup_logger.info(json.dumps({
                    "ts": time.time(),
                    "event": "llm_cache_vacuum",
                    "interval_hours": interval_hours,
                    **result,
                }, ensure_ascii=False))
            except Exception as e:
                _warmup_logger.info(json.dumps({
                    "ts": time.time(),
                    "event": "llm_cache_vacuum",
                    "error": str(e),
                }, ensure_ascii=False))

    def auto_vacuum_on_start(self) -> dict:
        """启动时自动 VACUUM（如果配置启用）"""
        if not getattr(self.config, "llm_cache_vacuum_on_start", False):
            return {"skipped": True, "reason": "vacuum_on_start disabled"}
        if self._persistent_cache is None:
            return {"skipped": True, "reason": "persistent cache disabled"}
        return self.vacuum_persistent_cache()

    async def warmup_cache(
        self,
        prompts: list[dict] | None = None,
        concurrency: int = 3,
        skip_existing: bool = True,
    ) -> dict:
        """预热缓存：批量调用 LLM 并将结果写入缓存

        用法：引擎启动后，调用常见 prompt 让它们提前进入缓存，
        后续真实请求可直接命中缓存，零延迟 + 零成本。

        Args:
            prompts: 要预热的 prompt 列表，每项格式：
                {
                    "messages": [{"role": "user", "content": "..."}],
                    "system": "...",        # 可选
                    "temperature": 0,        # 可选，默认 0
                    "max_tokens": 100,      # 可选
                    "json_mode": False,     # 可选
                }
                如果为 None，使用 config.llm_cache_warmup_prompts
            concurrency: 并发数（建议 2-5，避免触发 LLM 限流）
            skip_existing: 跳过已缓存的 prompt（节省时间和成本）

        Returns:
            预热结果统计：
            {
                "total": 总数,
                "warmed": 实际预热数,
                "skipped": 跳过数（已存在）,
                "failed": 失败数,
                "duration_ms": 总耗时,
            }

        审计日志：每次预热会在 ~/.pangu/logs/llm_cache_warmup.log 写一条 JSON 行
        （包含 timestamp / total / warmed / skipped / failed / duration_ms / provider / model），
        可通过 `pangu llm-cache-warmup-log` 或 engine.get_warmup_history() 查看。
        """
        if prompts is None:
            prompts = getattr(self.config, "llm_cache_warmup_prompts", []) or []

        if not prompts:
            return {
                "total": 0, "warmed": 0, "skipped": 0, "failed": 0, "duration_ms": 0,
            }

        start = time.time()
        result = {
            "total": len(prompts),
            "warmed": 0,
            "skipped": 0,
            "failed": 0,
            "source": "auto" if prompts is getattr(
                self.config, "llm_cache_warmup_prompts", None
            ) else "manual",
        }

        # 预过滤已存在的（基于缓存键）
        to_call = []
        for prompt in prompts:
            if skip_existing and self._is_cached(prompt):
                result["skipped"] += 1
                continue
            to_call.append(prompt)

        # 批量并发调用
        if to_call:
            try:
                responses = await self.batch_chat(to_call, concurrency=concurrency)
                for resp in responses:
                    if resp.content.startswith("[LMM 调用失败"):
                        result["failed"] += 1
                    else:
                        result["warmed"] += 1
            except Exception as e:
                result["failed"] = len(to_call)
                result["error"] = str(e)

        result["duration_ms"] = round((time.time() - start) * 1000, 2)

        # 审计日志
        self._log_warmup(result)
        return result

    def _log_warmup(self, result: dict) -> None:
        """写一条预热审计日志（JSON 行）"""
        try:
            entry = {
                "ts": time.time(),
                "event": "llm_cache_warmup",
                "provider": self.config.llm_provider,
                "model": self.config.llm_model,
                **result,
            }
            _warmup_logger.info(json.dumps(entry, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    def get_warmup_history(log_path: str = "", limit: int = 20) -> list[dict]:
        """读取最近的预热审计日志

        Args:
            log_path: 日志路径，默认 ~/.pangu/logs/llm_cache_warmup.log
            limit: 返回最多多少条（按时间倒序）

        Returns:
            预热记录列表，按时间倒序
        """
        if not log_path:
            log_path = os.path.join(
                os.path.expanduser("~"), ".pangu", "logs", "llm_cache_warmup.log"
            )
        if not os.path.exists(log_path):
            return []
        records: list[dict] = []
        try:
            with open(log_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 跳过时间戳前缀（格式：2026-06-08 12:34:56,789 {...}）
            json_start = line.find("{")
            if json_start == -1:
                continue
            try:
                rec = json.loads(line[json_start:])
                records.append(rec)
            except (json.JSONDecodeError, ValueError):
                continue
        records.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return records[:limit]

    def _is_cached(self, prompt: dict) -> bool:
        """检查单个 prompt 是否已缓存"""
        if not self._cache_enabled:
            return False
        try:
            cache_key = self._make_cache_key(
                provider=self.config.llm_provider.lower(),
                model=self.config.llm_model,
                messages=prompt.get("messages", []),
                system=prompt.get("system", ""),
                max_tokens=prompt.get("max_tokens", 4096),
                json_mode=prompt.get("json_mode", False),
            )
            if cache_key in self._cache:
                return True
            if self._persistent_cache is not None:
                return self._persistent_cache.get(cache_key) is not None
        except Exception:
            pass
        return False

    async def auto_warmup_on_start(self) -> dict:
        """启动时自动预热（如果配置启用）"""
        if not getattr(self.config, "llm_cache_warmup_on_start", False):
            return {"skipped": True, "reason": "warmup_on_start disabled"}
        if not getattr(self.config, "llm_cache_warmup_prompts", []):
            return {"skipped": True, "reason": "no warmup prompts configured"}
        return await self.warmup_cache(concurrency=3)

    def export_prometheus_metrics(self) -> str:
        """导出 Prometheus 格式指标

        指标列表：
        - pangu_llm_calls_total — 实际 LLM 调用次数
        - pangu_llm_cache_hits_total — 缓存命中次数
        - pangu_llm_cache_disk_hits_total — 持久化命中次数
        - pangu_llm_cache_misses_total — 缓存未命中次数
        - pangu_llm_cache_writes_total — 持久化缓存写入次数
        - pangu_llm_cache_hit_rate — 缓存命中率（百分比）
        - pangu_llm_cache_size — 内存缓存条目数
        - pangu_llm_prompt_tokens_total — 累计 prompt token
        - pangu_llm_completion_tokens_total — 累计 completion token
        - pangu_llm_cost_usd_total — 累计成本（USD）
        - pangu_llm_avg_latency_ms — 平均延迟（毫秒）
        - pangu_llm_persistent_cache_entries — 持久化缓存条目数
        - pangu_llm_persistent_cache_bytes — 持久化缓存字节数
        - pangu_llm_persistent_cache_max_bytes — 持久化缓存最大字节
        - pangu_llm_persistent_cache_hit_count_total — 持久化累计命中
        - pangu_llm_persistent_cache_tokens_saved_total — 累计节省 token
        """
        provider = self.config.llm_provider.lower()
        model = self.config.llm_model

        # 辅助函数
        def metric(name: str, value: float, mtype: str = "gauge", help_text: str = "") -> str:
            return (
                f"# HELP {name} {help_text}\n"
                f"# TYPE {name} {mtype}\n"
                f"{name}{{provider=\"{provider}\",model=\"{model}\"}} {value}\n"
            )

        lines = []
        total_lookups = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_lookups * 100 if total_lookups > 0 else 0.0

        # 调用统计
        lines.append(metric(
            "pangu_llm_calls_total", self._call_count, "counter",
            "LLM 实际调用次数"
        ))
        # 缓存统计
        lines.append(metric(
            "pangu_llm_cache_hits_total", self._cache_hits, "counter",
            "缓存命中次数（内存+磁盘）"
        ))
        lines.append(metric(
            "pangu_llm_cache_disk_hits_total", self._cache_disk_hits, "counter",
            "持久化磁盘缓存命中次数"
        ))
        lines.append(metric(
            "pangu_llm_cache_misses_total", self._cache_misses, "counter",
            "缓存未命中次数"
        ))
        lines.append(metric(
            "pangu_llm_cache_writes_total", self._cache_writes, "counter",
            "持久化缓存写入次数"
        ))
        lines.append(metric(
            "pangu_llm_cache_hit_rate", round(hit_rate, 2), "gauge",
            "缓存命中率（百分比 0-100）"
        ))
        lines.append(metric(
            "pangu_llm_memory_cache_size", len(self._cache), "gauge",
            "内存 LRU 缓存当前条目数"
        ))
        # Token 与成本
        lines.append(metric(
            "pangu_llm_prompt_tokens_total", self._total_prompt_tokens, "counter",
            "累计 prompt tokens"
        ))
        lines.append(metric(
            "pangu_llm_completion_tokens_total", self._total_completion_tokens, "counter",
            "累计 completion tokens"
        ))
        lines.append(metric(
            "pangu_llm_cost_usd_total", round(self._estimated_cost_usd, 6), "counter",
            "累计估算成本（USD）"
        ))
        # 性能
        lines.append(metric(
            "pangu_llm_avg_latency_ms", round(self.avg_latency_ms, 2), "gauge",
            "LLM 平均延迟（毫秒）"
        ))
        # 节省的 token
        lines.append(metric(
            "pangu_llm_tokens_saved_total", self._tokens_saved, "counter",
            "缓存命中累计节省的 token 数"
        ))
        # 持久化缓存
        if self._persistent_cache is not None:
            try:
                pstats = self._persistent_cache.get_stats()
                lines.append(metric(
                    "pangu_llm_persistent_cache_entries", pstats["total_entries"], "gauge",
                    "持久化缓存条目数"
                ))
                lines.append(metric(
                    "pangu_llm_persistent_cache_bytes", pstats["total_bytes"], "gauge",
                    "持久化缓存占用字节"
                ))
                lines.append(metric(
                    "pangu_llm_persistent_cache_max_bytes", pstats["max_disk_bytes"], "gauge",
                    "持久化缓存最大允许字节"
                ))
                lines.append(metric(
                    "pangu_llm_persistent_cache_hit_count_total", pstats["total_hits"], "counter",
                    "持久化缓存累计命中次数"
                ))
                lines.append(metric(
                    "pangu_llm_persistent_cache_tokens_saved_total",
                    pstats.get("total_tokens_saved", 0), "counter",
                    "持久化缓存累计节省 token"
                ))
            except Exception:
                pass

        return "\n".join(lines)

    def _make_cache_key(
        self, provider: str, model: str, messages: list, system: str,
        max_tokens: int, json_mode: bool,
    ) -> str:
        """生成缓存键（基于完整参数哈希）"""
        # 使用 SHA256 而非简单 hash，更稳定且抗碰撞
        payload = {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _put_cache(self, key: str, response: LLMResponse) -> None:
        """写入缓存（LRU 淘汰）"""
        if not self._cache_enabled:
            return
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = response
        # 超出容量时淘汰最旧的
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _get_semaphore(self, limit: int) -> asyncio.Semaphore:
        """获取并发信号量（懒初始化）"""
        if self._semaphore is None or self._semaphore._value != limit:
            self._semaphore = asyncio.Semaphore(limit)
        return self._semaphore

    async def batch_chat(
        self,
        batch: list[dict],
        concurrency: int = 5,
        use_cache: bool = True,
    ) -> list[LLMResponse]:
        """批量并发调用

        Args:
            batch: 请求列表，每项格式：
                {"messages": [...], "system": "", "temperature": 0.7,
                 "max_tokens": 4096, "json_mode": False}
            concurrency: 最大并发数（默认 5）
            use_cache: 是否使用响应缓存

        Returns:
            与 batch 等长的响应列表

        性能对比（智谱 glm-4-flash）：
            串行 10 次：~30s
            并发 5 + 缓存：~6s（首次）→ 0s（重复）
        """
        if not batch:
            return []
        semaphore = self._get_semaphore(concurrency)

        async def _one_call(req: dict) -> LLMResponse:
            async with semaphore:
                return await self.chat(
                    messages=req.get("messages", []),
                    system=req.get("system", ""),
                    temperature=req.get("temperature", 0.7),
                    max_tokens=req.get("max_tokens", 4096),
                    json_mode=req.get("json_mode", False),
                    use_cache=use_cache,
                )

        return await asyncio.gather(
            *[_one_call(req) for req in batch],
            return_exceptions=False,
        )

    async def batch_classify_memories(
        self,
        memories: list[dict],
        concurrency: int = 5,
    ) -> list[dict]:
        """批量并发分类记忆片段

        Args:
            memories: 记忆列表，每项 {"content": "...", "id": "..."}
            concurrency: 最大并发数

        Returns:
            与 memories 等长的分类结果列表：
            [{"id": "...", "classification": {...}}, ...]
        """
        if not memories:
            return []

        batch = [
            {
                "messages": [{"role": "user", "content": m["content"][:2000]}],
                "system": self._get_classify_system(),
                "temperature": 0.3,
                "max_tokens": 500,
                "json_mode": True,
            }
            for m in memories
        ]
        responses = await self.batch_chat(batch, concurrency=concurrency)

        results = []
        for memory, resp in zip(memories, responses, strict=False):
            cls = self._extract_json(resp.content, default={
                "hall": "hall_events", "room": "general", "importance": 3, "tags": []
            })
            results.append({"id": memory.get("id"), "classification": cls})
        return results

    async def batch_generate_wiki_pages(
        self,
        pages: list[dict],
        concurrency: int = 3,
    ) -> list[dict]:
        """批量并发生成 Wiki 页面

        Args:
            pages: 页面请求列表，每项 {"title": "...", "memories": [...]}
            concurrency: 最大并发数（Wiki 生成较慢，建议 2-3）

        Returns:
            与 pages 等长的 wiki 结果列表
        """
        if not pages:
            return []

        results = []
        for page in pages:
            memory_text = "\n\n---\n\n".join([
                f"[{m.get('wing', '?')}/{m.get('room', '?')}] {m.get('content', '')[:300]}"
                for m in page.get("memories", [])[:10]
            ])
            batch_item = {
                "messages": [{
                    "role": "user",
                    "content": f"请为以下记忆生成 Wiki 页面：\n\n主题：{page['title']}\n\n记忆片段：\n{memory_text}",
                }],
                "system": self._get_wiki_system(),
                "temperature": 0.5,
                "max_tokens": 2000,
                "json_mode": True,
            }
            results.append(batch_item)

        responses = await self.batch_chat(results, concurrency=concurrency)
        return [
            self._extract_json(r.content, default={
                "title": p["title"], "summary": "", "content": "", "tags": []
            })
            for p, r in zip(pages, responses, strict=False)
        ]

    @staticmethod
    def _get_classify_system() -> str:
        """获取分类 system prompt（独立方法以复用）"""
        return """你是盘古记忆系统的分类引擎。请将以下内容分类。
返回 JSON 格式：{"hall": "殿堂类型", "room": "建议房间名", "importance": 1-5, "tags": ["标签1", "标签2"]}

殿堂类型选项：
- hall_facts: 事实与决策
- hall_events: 事件与里程碑
- hall_discoveries: 发现与洞察
- hall_preferences: 偏好与习惯
- hall_advice: 建议与方案
- hall_concepts: 概念与理论
- hall_relations: 关系与网络"""

    @staticmethod
    def _get_wiki_system() -> str:
        """获取 Wiki system prompt"""
        return """你是盘古记忆系统的 Wiki 生成引擎。请根据记忆片段生成一个知识页面。

要求：
1. 使用 Markdown 格式
2. 包含：标题、摘要、关键信息、相关概念、时间线
3. 客观、准确、结构化
4. 使用中文输出

返回 JSON 格式：
{
  "title": "页面标题",
  "summary": "一句话摘要",
  "content": "完整的 Markdown 内容",
  "linked_pages": ["关联页面标题1"],
  "tags": ["标签1", "标签2"]
}"""

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
