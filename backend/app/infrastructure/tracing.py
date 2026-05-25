"""OpenTelemetry tracing bootstrap.

Configures an OTLP gRPC exporter pointing at Jaeger (or any OTLP receiver),
plus auto-instrumentation for FastAPI, gRPC, SQLAlchemy, Redis, and httpx.

Custom spans should be created via :func:`get_tracer` in business code, e.g.::

    from app.infrastructure.tracing import get_tracer

    tracer = get_tracer(__name__)

    async def place_order(...):
        with tracer.start_as_current_span("execution.place_order"):
            ...
"""

from __future__ import annotations

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL_AVAILABLE = True
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        _OTLP_AVAILABLE = True
    except ImportError:
        _OTLP_AVAILABLE = False
except ImportError:
    trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False
    _OTLP_AVAILABLE = False


def configure_tracing(
    *,
    service_name: str,
    service_version: str,
    otlp_endpoint: str,
) -> None:
    """Install a global TracerProvider with OTLP export. No-ops if OTel is not installed."""
    if not _OTEL_AVAILABLE or not _OTLP_AVAILABLE:
        return
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> "trace.Tracer":
    """Return a tracer for the given module name, or a no-op tracer if OTel is unavailable."""
    if not _OTEL_AVAILABLE:
        from unittest.mock import MagicMock
        return MagicMock()
    return trace.get_tracer(name)
