"""
OpenTelemetry Distributed Tracing setup.
Auto-instruments FastAPI, SQLAlchemy, Redis, and httpx.
Exports traces via OTLP (compatible with Jaeger, Datadog, Honeycomb, etc).
"""
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("telemetry")
settings = get_settings()

_tracer_provider = None


def setup_telemetry():
    """Initialize OpenTelemetry tracing if enabled."""
    global _tracer_provider

    if not settings.OTEL_ENABLED:
        logger.info("otel_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        resource = Resource.create({
            SERVICE_NAME: settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
        })

        _tracer_provider = TracerProvider(resource=resource)

        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_ENDPOINT,
            insecure=settings.OTEL_EXPORTER_ENDPOINT.startswith("http://"),
        )
        _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(_tracer_provider)

        # Auto-instrument libraries
        _instrument_fastapi()
        _instrument_sqlalchemy()
        _instrument_redis()
        _instrument_httpx()

        logger.info(
            "otel_initialized",
            endpoint=settings.OTEL_EXPORTER_ENDPOINT,
            service=settings.OTEL_SERVICE_NAME,
        )

    except ImportError as e:
        logger.warning("otel_import_error", error=str(e), hint="Install opentelemetry packages")
    except Exception as e:
        logger.error("otel_setup_error", error=str(e))


def shutdown_telemetry():
    """Gracefully shutdown the tracer provider."""
    global _tracer_provider
    if _tracer_provider:
        try:
            _tracer_provider.shutdown()
            logger.info("otel_shutdown")
        except Exception as e:
            logger.error("otel_shutdown_error", error=str(e))
        _tracer_provider = None


def _instrument_fastapi():
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument()
        logger.info("otel_instrumented", library="fastapi")
    except ImportError:
        pass


def _instrument_sqlalchemy():
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.info("otel_instrumented", library="sqlalchemy")
    except ImportError:
        pass


def _instrument_redis():
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.info("otel_instrumented", library="redis")
    except ImportError:
        pass


def _instrument_httpx():
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("otel_instrumented", library="httpx")
    except ImportError:
        pass
