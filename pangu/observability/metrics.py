"""盘古 Prometheus 指标导出（伏羲移植）"""

import contextlib
import logging
import time
from collections.abc import Callable
from functools import wraps

logger = logging.getLogger("pangu.observability.metrics")

_prom_available = False
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _prom_available = True
except ImportError:
    logger.debug("prometheus_client not installed, metrics disabled")


# ── 内存操作指标 ──
if _prom_available:
    MEMORY_CREATED = Counter(
        "pangu_memory_created_total",
        "Total number of memories created",
        ["wing"],
    )
    MEMORY_ACCESSED = Counter(
        "pangu_memory_accessed_total",
        "Total number of memory accesses",
        ["wing"],
    )
    MEMORY_DELETED = Counter(
        "pangu_memory_deleted_total",
        "Total number of memories deleted",
    )
    MEMORY_SEARCHED = Counter(
        "pangu_memory_search_total",
        "Total number of memory searches",
    )
    ACTIVE_MEMORIES = Gauge(
        "pangu_active_memories",
        "Current number of active memories",
    )

    # ── 引擎指标 ──
    ENGINE_RUNS = Counter(
        "pangu_engine_runs_total",
        "Total number of engine runs",
        ["engine_name", "status"],
    )
    ENGINE_RUN_DURATION = Histogram(
        "pangu_engine_run_duration_seconds",
        "Engine run duration in seconds",
        ["engine_name"],
        buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 60.0],
    )
    ENGINE_ERRORS = Counter(
        "pangu_engine_errors_total",
        "Total number of engine errors",
        ["engine_name"],
    )

    # ── API指标 ──
    API_REQUESTS = Counter(
        "pangu_api_requests_total",
        "Total number of API requests",
        ["method", "path", "status_code"],
    )
    API_REQUEST_DURATION = Histogram(
        "pangu_api_request_duration_seconds",
        "API request duration in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
    )

    # ── 嵌入指标 ──
    EMBED_REQUESTS = Counter(
        "pangu_embed_requests_total",
        "Total embedding requests by outcome",
        ["mode", "outcome"],
    )
    EMBED_LATENCY = Histogram(
        "pangu_embed_latency_seconds",
        "Embedding API call latency in seconds",
        ["mode"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    )
    EMBED_BATCH_SIZE = Histogram(
        "pangu_embed_batch_size",
        "Number of texts per embedding batch call",
        buckets=[1, 5, 10, 25, 50, 100, 200, 500],
    )
    EMBED_CIRCUIT_OPEN = Gauge(
        "pangu_embed_circuit_open",
        "1 when embedding API circuit breaker is open, 0 otherwise",
    )
    EMBED_FAIL_COUNT = Gauge(
        "pangu_embed_fail_count",
        "Consecutive embedding API failure count",
    )
    EMBED_CACHE_SIZE = Gauge(
        "pangu_embed_cache_size",
        "Current number of cached embeddings",
    )

    # ── 数据库指标 ──
    DB_SIZE = Gauge(
        "pangu_db_size_bytes",
        "Database file size in bytes",
    )
    MEMORY_COUNT = Gauge(
        "pangu_memory_count",
        "Total number of memory items",
    )

    # ── LLM 缓存指标 (v0.1.2) ──
    LLM_CACHE_HITS = Counter(
        "pangu_llm_cache_hits_total",
        "Total LLM cache hits (memory + persistent)",
        ["provider", "model", "layer"],  # layer: memory | disk
    )
    LLM_CACHE_MISSES = Counter(
        "pangu_llm_cache_misses_total",
        "Total LLM cache misses",
        ["provider", "model"],
    )
    LLM_CACHE_HIT_RATE = Gauge(
        "pangu_llm_cache_hit_rate",
        "LLM cache hit rate (0-100 percentage)",
        ["provider", "model"],
    )
    LLM_CACHE_SIZE = Gauge(
        "pangu_llm_cache_size",
        "Current LLM cache size (entries)",
        ["layer"],  # memory | persistent
    )
    LLM_CACHE_BYTES = Gauge(
        "pangu_llm_cache_bytes",
        "Persistent LLM cache disk usage in bytes",
    )
    LLM_TOKENS_TOTAL = Counter(
        "pangu_llm_tokens_total",
        "Total LLM tokens used",
        ["provider", "model", "type"],  # type: prompt | completion
    )
    LLM_COST_USD = Counter(
        "pangu_llm_cost_usd_total",
        "Total LLM cost in USD",
        ["provider", "model"],
    )
    LLM_CALLS = Counter(
        "pangu_llm_calls_total",
        "Total actual LLM API calls (cache miss)",
        ["provider", "model"],
    )
    LLM_LATENCY = Histogram(
        "pangu_llm_latency_seconds",
        "LLM call latency in seconds",
        ["provider", "model"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )
    # ── 知识图谱指标 ──
    KG_ENTITIES = Gauge(
        "pangu_kg_entities_total",
        "Total number of knowledge graph entities",
    )
    KG_RELATIONS = Gauge(
        "pangu_kg_relations_total",
        "Total number of knowledge graph relations",
    )

    # ── 搜索指标 ──
    SEARCH_LATENCY = Histogram(
        "pangu_search_latency_seconds",
        "Search latency in seconds",
        ["method"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    )
    SEARCH_RESULTS = Histogram(
        "pangu_search_results_count",
        "Number of search results returned",
        ["method"],
        buckets=[0, 1, 2, 5, 10, 20, 50],
    )

    # ── 向量索引指标 ──
    VECTOR_INDEX_SIZE = Gauge(
        "pangu_vector_index_size",
        "Number of vectors in the index",
    )
    VECTOR_SEARCH_LATENCY = Histogram(
        "pangu_vector_search_latency_seconds",
        "Vector search latency in seconds",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
    )

else:

    class _NoopMetric:
        def labels(self, **kw):
            return self

        def inc(self, *a, **kw):
            pass

        def dec(self, *a, **kw):
            pass

        def set(self, *a, **kw):
            pass

        def observe(self, *a, **kw):
            pass

    _noop = _NoopMetric()
    MEMORY_CREATED = MEMORY_ACCESSED = MEMORY_DELETED = MEMORY_SEARCHED = _noop
    ACTIVE_MEMORIES = _noop
    ENGINE_RUNS = ENGINE_RUN_DURATION = ENGINE_ERRORS = _noop
    API_REQUESTS = API_REQUEST_DURATION = _noop
    EMBED_REQUESTS = EMBED_LATENCY = EMBED_BATCH_SIZE = _noop
    EMBED_CIRCUIT_OPEN = EMBED_FAIL_COUNT = EMBED_CACHE_SIZE = _noop
    DB_SIZE = MEMORY_COUNT = _noop
    LLM_CACHE_HITS = LLM_CACHE_MISSES = LLM_CACHE_HIT_RATE = _noop
    LLM_CACHE_SIZE = LLM_CACHE_BYTES = _noop
    LLM_TOKENS_TOTAL = LLM_COST_USD = LLM_CALLS = LLM_LATENCY = _noop
    KG_ENTITIES = KG_RELATIONS = _noop
    SEARCH_LATENCY = SEARCH_RESULTS = _noop
    VECTOR_INDEX_SIZE = VECTOR_SEARCH_LATENCY = _noop


def track_engine_run(engine_name: str):
    """装饰器：追踪引擎运行"""

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kw):
            start = time.time()
            try:
                result = fn(*args, **kw)
                ENGINE_RUNS.labels(engine_name=engine_name, status="success").inc()
                return result
            except Exception:
                ENGINE_RUNS.labels(engine_name=engine_name, status="error").inc()
                ENGINE_ERRORS.labels(engine_name=engine_name).inc()
                raise
            finally:
                ENGINE_RUN_DURATION.labels(engine_name=engine_name).observe(time.time() - start)

        return wrapper

    return decorator


def get_metrics_response() -> tuple:
    """获取 Prometheus metrics 端点响应内容"""
    if not _prom_available:
        _content = "# prometheus_client not installed\n"
        _type = "text/plain; charset=utf-8"
    else:
        _content = generate_latest(REGISTRY)
        _type = CONTENT_TYPE_LATEST
    return _content, _type


def update_memory_count(count: int):
    """更新活跃记忆数指标"""
    with contextlib.suppress(Exception):
        ACTIVE_MEMORIES.set(count)


def record_api_request(method: str, path: str, status_code: int, duration: float):
    """记录一次 API 请求"""
    try:
        API_REQUESTS.labels(method=method, path=path, status_code=str(status_code)).inc()
        API_REQUEST_DURATION.labels(method=method, path=path).observe(duration)
    except Exception:
        pass


def update_llm_metrics(engine) -> None:
    """将 LLM 引擎统计同步到 Prometheus 指标

    应在每次 /metrics 端点被调用时执行，保证指标最新。

    Args:
        engine: LLMEngine 实例
    """
    try:
        provider = engine.config.llm_provider.lower()
        model = engine.config.llm_model

        # 缓存命中分桶
        memory_hits = engine._cache_hits - engine._cache_disk_hits
        disk_hits = engine._cache_disk_hits
        if memory_hits > 0:
            LLM_CACHE_HITS.labels(provider=provider, model=model, layer="memory").inc(memory_hits)
        if disk_hits > 0:
            LLM_CACHE_HITS.labels(provider=provider, model=model, layer="disk").inc(disk_hits)
        if engine._cache_misses > 0:
            LLM_CACHE_MISSES.labels(provider=provider, model=model).inc(engine._cache_misses)

        # 命中率
        total_lookups = engine._cache_hits + engine._cache_misses
        if total_lookups > 0:
            hit_rate = engine._cache_hits / total_lookups * 100
            LLM_CACHE_HIT_RATE.labels(provider=provider, model=model).set(hit_rate)

        # 内存缓存大小
        LLM_CACHE_SIZE.labels(layer="memory").set(len(engine._cache))

        # 持久化缓存
        if engine._persistent_cache is not None:
            try:
                pstats = engine._persistent_cache.get_stats()
                LLM_CACHE_SIZE.labels(layer="persistent").set(pstats["total_entries"])
                LLM_CACHE_BYTES.set(pstats["total_bytes"])
            except Exception:
                pass

        # Tokens 与成本
        if engine._total_prompt_tokens > 0:
            LLM_TOKENS_TOTAL.labels(provider=provider, model=model, type="prompt").inc(engine._total_prompt_tokens)
        if engine._total_completion_tokens > 0:
            LLM_TOKENS_TOTAL.labels(provider=provider, model=model, type="completion").inc(
                engine._total_completion_tokens
            )
        if engine._estimated_cost_usd > 0:
            LLM_COST_USD.labels(provider=provider, model=model).inc(engine._estimated_cost_usd)

        # 调用次数
        if engine._call_count > 0:
            LLM_CALLS.labels(provider=provider, model=model).inc(engine._call_count)

        # 平均延迟
        if engine.avg_latency_ms > 0:
            LLM_LATENCY.labels(provider=provider, model=model).observe(engine.avg_latency_ms / 1000.0)
    except Exception as e:
        logger.debug("update_llm_metrics failed: %s", e)


def update_kg_metrics(entity_count: int, relation_count: int):
    """更新知识图谱指标"""
    with contextlib.suppress(Exception):
        KG_ENTITIES.set(entity_count)
        KG_RELATIONS.set(relation_count)


def record_search(method: str, latency: float, result_count: int):
    """记录一次搜索"""
    try:
        SEARCH_LATENCY.labels(method=method).observe(latency)
        SEARCH_RESULTS.labels(method=method).observe(result_count)
    except Exception:
        pass


def update_vector_index_size(size: int):
    """更新向量索引大小"""
    with contextlib.suppress(Exception):
        VECTOR_INDEX_SIZE.set(size)
