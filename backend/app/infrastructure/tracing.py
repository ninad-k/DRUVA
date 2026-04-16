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

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(
    *,
    service_name: str,
    service_version: str,
    otlp_endpoint: str,
) -> None:
    """Install a global TracerProvider with OTLP export."""
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

    # Auto-instrumentations are opt-in to keep import time fast; call these
    # from ``main.py`` once their targets (app, engine, client) exist.
    # Example:
    #   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    #   FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer for the given module name."""
    return trace.get_tracer(name)
