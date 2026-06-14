"""盘古 — OpenTelemetry 分布式追踪模块

提供请求级追踪，支持导出到 Jaeger/Zipkin/OTLP。

使用方式：
1. 自动初始化：import 即生效
2. 手动埋点：with tracer.start_as_current_span("name"): ...
3. 导出配置：OTEL_EXPORTER_OTLP_ENDPOINT 环境变量
"""
import logging
import os

logger = logging.getLogger("pangu.observability.tracing")

_tracer = None
_available = False


def _init_tracer():
    """初始化 OpenTelemetry tracer"""
    global _tracer, _available

    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        # 创建 provider
        provider = TracerProvider(resource=trace.Resource.create({
            "service.name": "pangu",
            "service.version": "0.1.0",
        }))

        # 尝试 OTLP 导出
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(f"OTLP exporter configured: {endpoint}")
            except Exception as e:
                logger.debug(f"OTLP exporter failed: {e}, falling back to console")

        # Console 导出（调试用）
        if os.environ.get("OTEL_CONSOLE_EXPORT", "").lower() in ("1", "true"):
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("pangu", "0.1.0")
        _available = True
        return _tracer
    except ImportError:
        logger.debug("opentelemetry not installed, tracing disabled")
        return None
    except Exception as e:
        logger.debug(f"Tracing init failed: {e}")
        return None


def get_tracer():
    """获取 tracer 实例"""
    return _init_tracer()


def is_available() -> bool:
    """检查 tracing 是否可用"""
    _init_tracer()
    return _available


class traced:
    """装饰器：自动追踪函数调用

    Usage:
        @traced("memory.remember")
        def remember(...):
            ...
    """
    def __init__(self, span_name: str = None):
        self.span_name = span_name

    def __call__(self, fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer is None:
                return fn(*args, **kwargs)

            name = self.span_name or f"{fn.__module__}.{fn.__qualname__}"
            with tracer.start_as_current_span(name) as span:
                try:
                    result = fn(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    raise
        return wrapper
